"""뉴스 수집 — 네이버 종목 뉴스 + Google News RSS.

각 항목 표준화:
  {title, url, summary, published(datetime KST), source, ticker, name}
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import quote

import feedparser
import pytz
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from src.state import Stock
from src.window import KST, Window

UA = {"User-Agent": "Mozilla/5.0 (stock-news-bot)"}
NAVER_URL = "https://finance.naver.com/item/news_news.naver?code={code}&page=1"
GOOGLE_URL = (
    "https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"
)


@dataclass
class NewsItem:
    title: str
    url: str
    summary: str
    published: datetime
    source: str  # "naver" | "google"
    publisher: str  # 매체명
    ticker: str
    name: str


# ─────────────────────────────────────────
# 네이버 종목 뉴스
# ─────────────────────────────────────────


def fetch_naver(stock: Stock, window: Window) -> list[NewsItem]:
    try:
        r = requests.get(NAVER_URL.format(code=stock.ticker), headers=UA, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"[naver] {stock.name} 실패: {e}")
        return []

    soup = BeautifulSoup(r.content, "html.parser")
    rows = soup.select("table.type5 tr")  # 일반 뉴스 + 연관 뉴스 모두
    items: list[NewsItem] = []
    for tr in rows:
        a = tr.select_one("a.tit") or tr.select_one("td.title a")
        date_td = tr.select_one("td.date")
        info_td = tr.select_one("td.info")
        if not a or not date_td:
            continue
        title = a.get_text(strip=True)
        href = a.get("href", "")
        if not href:
            continue
        if href.startswith("/"):
            url = "https://finance.naver.com" + href
        else:
            url = href
        date_str = date_td.get_text(strip=True)  # "2026.06.07 10:23"
        try:
            published = KST.localize(datetime.strptime(date_str, "%Y.%m.%d %H:%M"))
        except ValueError:
            continue
        if not window.contains(published):
            continue
        publisher = info_td.get_text(strip=True) if info_td else "네이버"
        items.append(
            NewsItem(
                title=title,
                url=url,
                summary="",
                published=published,
                source="naver",
                publisher=publisher,
                ticker=stock.ticker,
                name=stock.name,
            )
        )
    return items


# ─────────────────────────────────────────
# Google News RSS
# ─────────────────────────────────────────


def _strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()


def fetch_google(stock: Stock, window: Window) -> list[NewsItem]:
    query = quote(f'"{stock.name}" OR {stock.ticker}')
    url = GOOGLE_URL.format(query=query)
    try:
        feed = feedparser.parse(url, request_headers=UA)
    except Exception as e:
        print(f"[google] {stock.name} 실패: {e}")
        return []

    items: list[NewsItem] = []
    for entry in feed.entries:
        try:
            published = dateparser.parse(entry.published).astimezone(KST)
        except (AttributeError, ValueError, TypeError):
            continue
        if not window.contains(published):
            continue
        publisher = ""
        if hasattr(entry, "source") and isinstance(entry.source, dict):
            publisher = entry.source.get("title", "")
        elif hasattr(entry, "source"):
            publisher = getattr(entry.source, "title", "")
        items.append(
            NewsItem(
                title=_strip_html(entry.title),
                url=entry.link,
                summary=_strip_html(getattr(entry, "summary", "")),
                published=published,
                source="google",
                publisher=publisher or "Google News",
                ticker=stock.ticker,
                name=stock.name,
            )
        )
    return items


def fetch_all(stocks: list[Stock], window: Window) -> list[NewsItem]:
    items: list[NewsItem] = []
    for stock in stocks:
        items.extend(fetch_naver(stock, window))
        items.extend(fetch_google(stock, window))
    print(f"수집 완료: {len(items)}건 (윈도우 {window.label})")
    return items
