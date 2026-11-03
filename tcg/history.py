"""Daily price snapshots, kept in data/history/YYYY-MM-DD.json.gz (TCGplayer itself keeps no history)."""
from __future__ import annotations

import datetime as dt
import gzip
import json
from pathlib import Path


def key(pid: int, sub: str) -> str:
    return f"{pid}:{sub}"


def write_snapshot(folder: Path, date: str, prices: dict[str, list]) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{date}.json.gz"
    with gzip.open(path, "wt") as f:
        json.dump({"date": date, "p": prices}, f, separators=(",", ":"))
    return path


def load_all(folder: Path) -> dict[str, dict[str, list]]:
    out = {}
    if not folder.exists():
        return out
    for path in sorted(folder.glob("*.json.gz")):
        try:
            with gzip.open(path, "rt") as f:
                d = json.load(f)
            out[d["date"]] = d["p"]
        except Exception:
            continue
    return out


def on_or_before(hist: dict, date: str, days_back: int) -> dict | None:
    """Snapshot from `days_back` days before `date` (or the closest earlier one, up to 3 days slack)."""
    target = dt.date.fromisoformat(date) - dt.timedelta(days=days_back)
    for slack in range(0, 4):
        d = (target - dt.timedelta(days=slack)).isoformat()
        if d in hist:
            return hist[d]
    return None


def market(entry) -> float | None:
    if not entry:
        return None
    m, low = entry[0], entry[1]
    return m if m else low


def pct(new, old):
    if new is None or not old:
        return None
    return round((new - old) / old * 100, 1)
