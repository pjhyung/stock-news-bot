"""Cerebras Llama 3.3 70B로 뉴스 중요도 평가.

dedup된 N개를 한 번의 프롬프트로 묶어 평가 → API 호출 1회.
응답은 JSON 배열: [{"index": 1, "score": 8, "reason": "..."}]
JSON 파싱 실패 시 한 번 재시도 (프롬프트 더 강조).
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

import requests

from src.news_fetcher import NewsItem
from src.state import Stock

CEREBRAS_URL = "https://api.cerebras.ai/v1/chat/completions"
MODEL = "gpt-oss-120b"
TIMEOUT = 30

SYSTEM_PROMPT = """당신은 한국 주식 시장 애널리스트다. 뉴스의 주가 영향 중요도를 평가한다.

점수 기준 (0~10):
  9~10: 즉각적 주가 영향 (실적 발표, M&A 발표, 규제·소송, 경영진 교체, 대형 계약, 가이던스 수정)
  6~8 : 중기 시그널 (산업 트렌드, 경쟁사 동향, 매크로/금리·환율, 정책)
  3~5 : 참고용 (일반 보도, 시장 코멘트, 애널리스트 의견)
  0~2 : 노이즈 (광고성, 단순 시세 보도, 종목 추천 게시물)

응답은 반드시 JSON 배열 한 개로만. 다른 텍스트 금지.
형식: [{"index": <번호>, "score": <0-10>, "reason": "<한 줄 한글 요약 사유>"}]
"""


@dataclass
class Scored:
    item: NewsItem
    score: int
    reason: str


def _build_user_prompt(items: list[NewsItem], stocks: list[Stock]) -> str:
    names = ", ".join(f"{s.name}({s.ticker})" for s in stocks)
    lines = [f"관심종목: {names}", "", "뉴스 목록:"]
    for i, it in enumerate(items, start=1):
        date_str = it.published.strftime("%m/%d %H:%M")
        summary = f" — {it.summary[:120]}" if it.summary else ""
        lines.append(f"{i}. [{it.name}] {it.title} ({date_str}, {it.publisher}){summary}")
    return "\n".join(lines)


def _extract_json(text: str) -> list[dict] | None:
    """모델이 코드펜스나 다른 텍스트를 끼워넣어도 JSON 배열을 추출."""
    text = text.strip()
    # 코드펜스 제거
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    # 가장 바깥 [...] 추출
    m = re.search(r"\[\s*\{.*\}\s*\]", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _call_cerebras(messages: list[dict]) -> str:
    key = os.environ.get("CEREBRAS_API_KEY", "").strip()
    if not key:
        raise RuntimeError("CEREBRAS_API_KEY 환경변수가 비어있다.")
    r = requests.post(
        CEREBRAS_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": MODEL, "messages": messages, "temperature": 0.2, "max_tokens": 2000},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def score_items(items: list[NewsItem], stocks: list[Stock]) -> list[Scored]:
    if not items:
        return []

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_prompt(items, stocks)},
    ]

    try:
        raw = _call_cerebras(messages)
        parsed = _extract_json(raw)
    except Exception as e:
        print(f"Cerebras 호출 실패: {e}")
        return []

    if parsed is None:
        # 재시도: 형식을 더 강하게 강조
        messages.append({"role": "assistant", "content": raw})
        messages.append(
            {
                "role": "user",
                "content": "JSON 배열만 다시. 코드펜스/설명 금지. [{\"index\":1,\"score\":7,\"reason\":\"...\"}] 형식.",
            }
        )
        try:
            raw = _call_cerebras(messages)
            parsed = _extract_json(raw)
        except Exception as e:
            print(f"재시도 실패: {e}")
            return []

    if parsed is None:
        print("JSON 파싱 실패. 원문:", raw[:200])
        return []

    by_index = {int(p["index"]): p for p in parsed if "index" in p}
    results: list[Scored] = []
    for i, it in enumerate(items, start=1):
        p = by_index.get(i)
        if not p:
            continue
        try:
            results.append(
                Scored(
                    item=it,
                    score=max(0, min(10, int(p.get("score", 0)))),
                    reason=str(p.get("reason", "")).strip(),
                )
            )
        except (ValueError, TypeError):
            continue
    print(f"scoring: {len(results)}건 평가 완료")
    return results
