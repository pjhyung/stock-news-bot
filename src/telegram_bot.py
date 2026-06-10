"""Telegram 봇 — getUpdates 폴링으로 명령 처리 + 메시지 전송.

지원 명령:
  /add <종목명|티커>
  /remove <종목명|티커>
  /list
  /threshold <0~10>
  /status
  /help
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import requests

from src.state import State, Stock

API = "https://api.telegram.org/bot{token}/{method}"


def _token() -> str:
    t = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not t:
        raise RuntimeError("TELEGRAM_BOT_TOKEN 환경변수가 비어있다.")
    return t


def _chat_id() -> str:
    c = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not c:
        raise RuntimeError("TELEGRAM_CHAT_ID 환경변수가 비어있다.")
    return c


def send_message(text: str, disable_preview: bool = False) -> None:
    r = requests.post(
        API.format(token=_token(), method="sendMessage"),
        json={
            "chat_id": _chat_id(),
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": disable_preview,
        },
        timeout=10,
    )
    r.raise_for_status()


@dataclass
class Update:
    update_id: int
    chat_id: str
    text: str


def _poll_updates(offset: int) -> list[Update]:
    r = requests.get(
        API.format(token=_token(), method="getUpdates"),
        params={"offset": offset, "timeout": 0, "allowed_updates": ["message"]},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json().get("result", [])
    updates: list[Update] = []
    for item in data:
        msg = item.get("message") or {}
        updates.append(
            Update(
                update_id=item["update_id"],
                chat_id=str(msg.get("chat", {}).get("id", "")),
                text=(msg.get("text") or "").strip(),
            )
        )
    return updates


# ─────────────────────────────────────────
# 명령 처리
# ─────────────────────────────────────────


def _resolve_stock(query: str, ticker_map: dict[str, str]) -> Stock | None:
    """query가 종목명 또는 티커. ticker_map: {종목명: 티커}."""
    query = query.strip()
    # 티커로 들어왔는지
    if query.isdigit() and len(query) == 6:
        # 역매핑
        for name, ticker in ticker_map.items():
            if ticker == query:
                return Stock(name=name, ticker=ticker)
        return Stock(name=query, ticker=query)  # 이름 모르면 티커로 표시
    # 종목명으로 들어왔는지
    if query in ticker_map:
        return Stock(name=query, ticker=ticker_map[query])
    # 부분 일치 시도
    matches = [n for n in ticker_map if query in n]
    if len(matches) == 1:
        return Stock(name=matches[0], ticker=ticker_map[matches[0]])
    return None


def _handle_command(text: str, state: State, ticker_map: dict[str, str]) -> str:
    parts = text.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd == "/add":
        if not arg:
            return "사용법: /add 삼성전자 또는 /add 005930"
        stock = _resolve_stock(arg, ticker_map)
        if not stock:
            return f"❌ '{arg}' 종목을 찾지 못했다."
        if any(s.ticker == stock.ticker for s in state.stocks):
            return f"⚠️ {stock.name}({stock.ticker})는 이미 등록돼 있다."
        state.stocks.append(stock)
        return f"✅ 추가: {stock.name}({stock.ticker})"

    if cmd == "/remove":
        if not arg:
            return "사용법: /remove 삼성전자 또는 /remove 005930"
        target = _resolve_stock(arg, ticker_map)
        ticker = target.ticker if target else arg
        before = len(state.stocks)
        state.stocks = [s for s in state.stocks if s.ticker != ticker and s.name != arg]
        if len(state.stocks) == before:
            return f"❌ '{arg}' 종목이 목록에 없다."
        return f"✅ 제거: {arg}"

    if cmd == "/list":
        if not state.stocks:
            return f"📋 관심종목 없음.\n임계값: {state.threshold}"
        lines = [f"📋 관심종목 ({len(state.stocks)}개):"]
        lines.extend(f"  • {s.name} ({s.ticker})" for s in state.stocks)
        lines.append(f"\n임계값: {state.threshold}")
        return "\n".join(lines)

    if cmd == "/threshold":
        if not arg.isdigit():
            return "사용법: /threshold 7 (0~10)"
        val = int(arg)
        if not 0 <= val <= 10:
            return "0~10 사이 값으로 설정해라."
        state.threshold = val
        return f"✅ 임계값 변경: {val}"

    if cmd == "/status":
        last = state.last_run_kst or "없음"
        return (
            f"🤖 stock-news-bot\n"
            f"마지막 실행: {last}\n"
            f"관심종목: {len(state.stocks)}개 / 임계값: {state.threshold}"
        )

    if cmd in ("/help", "/start"):
        return (
            "📖 사용 가능 명령:\n"
            "/add &lt;종목명|티커&gt; — 관심종목 추가\n"
            "/remove &lt;종목명|티커&gt; — 제거\n"
            "/list — 현재 목록 + 임계값\n"
            "/threshold &lt;0~10&gt; — 알림 임계값 조정\n"
            "/status — 봇 상태 확인\n"
            "/help — 이 도움말"
        )

    return ""  # 명령 아닌 일반 메시지는 무시


def apply_telegram_commands(state: State, ticker_map: dict[str, str]) -> int:
    """대기 중인 텔레그램 명령을 처리하고 응답을 전송. 처리된 명령 수 반환."""
    updates = _poll_updates(state.telegram_offset)
    if not updates:
        return 0

    processed = 0
    for u in updates:
        # 항상 offset 진행 (오류로 멈추지 않게)
        state.telegram_offset = max(state.telegram_offset, u.update_id + 1)
        if not u.text.startswith("/"):
            continue
        # 보안: 등록된 chat_id의 명령만 처리
        if u.chat_id and u.chat_id != _chat_id():
            continue
        reply = _handle_command(u.text, state, ticker_map)
        if reply:
            try:
                send_message(reply)
            except Exception as e:
                print(f"명령 응답 전송 실패: {e}")
        processed += 1
    return processed
