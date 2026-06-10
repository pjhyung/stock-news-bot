"""stock-news-bot 진입점.

파이프라인:
  1. watchlist.json 로드
  2. 텔레그램 명령 처리 + watchlist 업데이트
  3. 현재 시각으로 윈도우 결정
  4. 네이버 + Google News 수집
  5. URL/제목 dedup
  6. Cerebras로 중요도 평가
  7. 임계값 이상 중 최고점 1건 텔레그램 전송
  8. watchlist 변경분 git push (GitHub Actions에서만)
"""
from __future__ import annotations

import os
import sys

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import FinanceDataReader as fdr

from src.dedup import dedup
from src.importance_scorer import Scored, score_items
from src.news_fetcher import fetch_all
from src.state import State, load_state, save_state, git_commit_and_push_if_changed
from src.telegram_bot import apply_telegram_commands, send_message
from src.window import Window, get_window, now_kst


def _ticker_map() -> dict[str, str]:
    """KRX 전 종목 {종목명: 티커} 매핑."""
    try:
        df = fdr.StockListing("KRX")
        return dict(zip(df["Name"].astype(str), df["Code"].astype(str)))
    except Exception as e:
        print(f"KRX listing 실패: {e}")
        return {}


def _format_message(scored: Scored, window: Window) -> str:
    it = scored.item
    return (
        f"🔔 <b>{it.name}</b> 중요뉴스 (점수 {scored.score}/10)\n"
        f"<i>{window.label}</i>\n\n"
        f"<b>{it.title}</b>\n"
        f"{it.publisher} · {it.published.strftime('%m/%d %H:%M')}\n\n"
        f"💡 {scored.reason}\n\n"
        f"🔗 {it.url}"
    )


def run() -> int:
    state = load_state()
    print(f"watchlist: {len(state.stocks)}종목, 임계값 {state.threshold}")

    ticker_map = _ticker_map()
    processed = apply_telegram_commands(state, ticker_map)
    if processed:
        print(f"명령 {processed}건 처리")

    if not state.stocks:
        print("관심종목이 비어 있음. 종료.")
        save_state(state)
        git_commit_and_push_if_changed()
        return 0

    window = get_window(now_kst())
    print(f"윈도우: {window.label} ({window.start} ~ {window.end})")

    items = fetch_all(state.stocks, window)
    if not items:
        print("수집된 뉴스 없음.")
        save_state(state)
        git_commit_and_push_if_changed()
        return 0

    unique = dedup(items)
    scored = score_items(unique, state.stocks)
    if not scored:
        print("평가 결과 없음.")
        save_state(state)
        git_commit_and_push_if_changed()
        return 0

    top = max(scored, key=lambda s: s.score)
    print(f"최고점: {top.score} — {top.item.title[:60]}")

    if top.score >= state.threshold:
        try:
            send_message(_format_message(top, window), disable_preview=False)
            print("텔레그램 전송 완료")
        except Exception as e:
            print(f"전송 실패: {e}")
    else:
        print(f"임계값({state.threshold}) 미달 — 전송 안 함")

    save_state(state)
    git_commit_and_push_if_changed()
    return 0


if __name__ == "__main__":
    sys.exit(run())
