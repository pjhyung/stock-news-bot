"""실행 시각별 뉴스 수집 시간창(window) 계산.

규칙 (KST 기준):
- 평일 09:00 (장 시작):  전일 15:30 → 당일 09:00
- 평일 10:00~15:00:      직전 1시간
- 일요일 21:00 (주말 종합): 금요일 15:30 → 일요일 21:00
- 그 외 시각 수동 실행:   직전 1시간 (디버깅용 기본값)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pytz

KST = pytz.timezone("Asia/Seoul")
MARKET_OPEN = (9, 0)    # 09:00
MARKET_CLOSE = (15, 30)  # 15:30


@dataclass(frozen=True)
class Window:
    start: datetime
    end: datetime
    label: str  # 텔레그램 메시지 헤더용

    def contains(self, ts: datetime) -> bool:
        return self.start <= ts <= self.end


def now_kst() -> datetime:
    return datetime.now(tz=KST)


def _at(dt: datetime, hh: int, mm: int) -> datetime:
    return dt.replace(hour=hh, minute=mm, second=0, microsecond=0)


def _previous_business_day(dt: datetime) -> datetime:
    """dt 직전의 영업일(월~금)."""
    d = dt - timedelta(days=1)
    while d.weekday() >= 5:  # 5=토, 6=일
        d -= timedelta(days=1)
    return d


def get_window(now: datetime) -> Window:
    """현재 KST 시각으로 윈도우 결정."""
    if now.tzinfo is None:
        now = KST.localize(now)
    else:
        now = now.astimezone(KST)

    weekday = now.weekday()  # 0=월 ... 6=일

    # 일요일 21시 주말 종합
    if weekday == 6 and now.hour == 21:
        # 금요일 15:30 ~ 일요일 21:00
        days_back = 2  # 일 - 2 = 금
        friday = now - timedelta(days=days_back)
        start = _at(friday, *MARKET_CLOSE)
        end = _at(now, 21, 0)
        return Window(start, end, "주말 종합 (금 15:30 ~ 일 21:00)")

    # 평일 장 시작 (09:00)
    if weekday < 5 and now.hour == 9 and now.minute < 30:
        prev = _previous_business_day(now)
        start = _at(prev, *MARKET_CLOSE)
        end = _at(now, *MARKET_OPEN)
        return Window(
            start,
            end,
            f"장 시작 ({prev.strftime('%m/%d')} 15:30 ~ {now.strftime('%m/%d')} 09:00)",
        )

    # 평일 장중 매시
    if weekday < 5 and 10 <= now.hour <= 15:
        end = _at(now, now.hour, 0)
        start = end - timedelta(hours=1)
        return Window(start, end, f"{start.strftime('%H:%M')} ~ {end.strftime('%H:%M')}")

    # 그 외 (수동 실행/디버깅): 직전 1시간
    end = now
    start = end - timedelta(hours=1)
    return Window(start, end, f"수동 ({start.strftime('%H:%M')} ~ {end.strftime('%H:%M')})")
