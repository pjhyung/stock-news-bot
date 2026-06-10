"""중복 뉴스 제거.

1) URL 정규화 후 exact match (utm 등 트래킹 파라미터 제거)
2) 제목 fuzzy match (rapidfuzz, 85% 이상은 동일 사건)

소스 우선순위: 네이버 > Google (네이버가 원문 출판사를 명시하는 경우가 많음)
"""
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from rapidfuzz import fuzz

from src.news_fetcher import NewsItem

TRACK_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"}
SIMILARITY_THRESHOLD = 85
SOURCE_RANK = {"naver": 0, "google": 1}  # 낮을수록 우선


def canonical_url(url: str) -> str:
    p = urlparse(url)
    qs = [(k, v) for k, v in parse_qsl(p.query) if k not in TRACK_PARAMS]
    qs.sort()
    return urlunparse((p.scheme, p.netloc.lower(), p.path.rstrip("/"), "", urlencode(qs), ""))


def _prefer(a: NewsItem, b: NewsItem) -> NewsItem:
    """두 아이템 중 우선할 것을 반환 (소스 우선순위 → 더 긴 제목)."""
    ra = SOURCE_RANK.get(a.source, 9)
    rb = SOURCE_RANK.get(b.source, 9)
    if ra != rb:
        return a if ra < rb else b
    return a if len(a.title) >= len(b.title) else b


def dedup(items: list[NewsItem]) -> list[NewsItem]:
    # 1차: URL canonical
    by_url: dict[str, NewsItem] = {}
    for it in items:
        key = canonical_url(it.url)
        if key in by_url:
            by_url[key] = _prefer(by_url[key], it)
        else:
            by_url[key] = it

    # 2차: 제목 유사도
    survivors: list[NewsItem] = []
    for it in by_url.values():
        merged = False
        for i, kept in enumerate(survivors):
            score = fuzz.token_set_ratio(it.title, kept.title)
            if score >= SIMILARITY_THRESHOLD:
                survivors[i] = _prefer(kept, it)
                merged = True
                break
        if not merged:
            survivors.append(it)

    print(f"dedup: {len(items)}건 → {len(survivors)}건")
    return survivors
