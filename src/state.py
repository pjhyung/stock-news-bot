"""watchlist.json 입출력과 git commit/push.

state 구조:
{
  "stocks": [{"name": "삼성전자", "ticker": "005930"}, ...],
  "threshold": 7,
  "telegram_offset": 0,
  "last_run_kst": "2026-06-07T11:00:00+09:00"
}
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

from src.window import now_kst

STATE_PATH = Path(__file__).resolve().parents[1] / "watchlist.json"


@dataclass
class Stock:
    name: str
    ticker: str


@dataclass
class State:
    stocks: list[Stock] = field(default_factory=list)
    threshold: int = 7
    telegram_offset: int = 0
    last_run_kst: str | None = None

    def to_dict(self) -> dict:
        return {
            "stocks": [asdict(s) for s in self.stocks],
            "threshold": self.threshold,
            "telegram_offset": self.telegram_offset,
            "last_run_kst": self.last_run_kst,
        }


def load_state() -> State:
    if not STATE_PATH.exists():
        return State()
    raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return State(
        stocks=[Stock(**s) for s in raw.get("stocks", [])],
        threshold=raw.get("threshold", 7),
        telegram_offset=raw.get("telegram_offset", 0),
        last_run_kst=raw.get("last_run_kst"),
    )


def save_state(state: State) -> None:
    state.last_run_kst = now_kst().isoformat()
    STATE_PATH.write_text(
        json.dumps(state.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _run(args: list[str]) -> tuple[int, str]:
    proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def git_commit_and_push_if_changed() -> bool:
    """watchlist.json에 변경이 있으면 commit & push. 변경되었으면 True."""
    if not os.environ.get("GITHUB_ACTIONS"):
        # 로컬 실행에서는 자동 push하지 않음 (디버깅 안정성)
        return False

    code, out = _run(["git", "status", "--porcelain", str(STATE_PATH)])
    if code != 0 or not out:
        return False

    _run(["git", "config", "user.name", "stock-news-bot"])
    _run(["git", "config", "user.email", "bot@users.noreply.github.com"])
    _run(["git", "add", str(STATE_PATH)])
    code, out = _run(["git", "commit", "-m", "chore: update watchlist state"])
    if code != 0:
        return False
    _run(["git", "push"])
    return True
