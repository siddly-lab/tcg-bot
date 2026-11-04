"""Fill gaps in each game's price history from tcgcsv's daily archives.

Each archive (prices-YYYY-MM-DD.ppmd.7z) holds every game's prices for one day, so one download
serves every game that's missing that day. Older history is kept weekly, the last 35 days daily.
"""
from __future__ import annotations

import datetime as dt
import json
import shutil
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import history, tcgcsv

ARCHIVE = "https://tcgcsv.com/archive/tcgplayer/prices-{d}.ppmd.7z"
PAUSE = 3


def download(url: str, dest: Path, tries: int = 4):
    """Download, waiting and retrying when the server says we're going too fast."""
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=tcgcsv.UA)
            with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
                shutil.copyfileobj(r, f)
            return
        except urllib.error.HTTPError as e:
            if e.code != 429 or i == tries - 1:
                raise
            time.sleep(30 * (i + 1))


def dates_to_fetch(start: dt.date, end: dt.date, recent_days: int, have: set[str]) -> list[str]:
    """Weekly points for the older history, every day for the most recent stretch."""
    out = []
    d = start
    cutoff = end - dt.timedelta(days=recent_days)
    while d <= end:
        if d >= cutoff or (d - start).days % 7 == 0:
            if d.isoformat() not in have:
                out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def read_archive(path: Path, cats: set[int], workdir: Path) -> dict[int, list[dict]]:
    import py7zr  # only needed here

    with py7zr.SevenZipFile(path, "r") as z:
        names = [n for n in z.getnames() if n.endswith("prices") and any(f"/{c}/" in n for c in cats)]
        z.extract(path=workdir, targets=names)
    out: dict[int, list[dict]] = {c: [] for c in cats}
    for n in names:
        cat = next(c for c in cats if f"/{c}/" in n)
        try:
            data = json.loads((workdir / n).read_text())
        except Exception:
            continue
        rows = data.get("results", data) if isinstance(data, dict) else data
        out[cat].extend(rows)
    return out


def fill(games: list[dict], hist_root: Path, end: dt.date, recent_days: int = 35, limit: int = 200) -> int:
    """games: [{id, category, start, keep(pid, sub, market) -> bool}]. Returns days saved."""
    need: dict[str, list[dict]] = {}
    for g in games:
        folder = hist_root / g["id"]
        have = {p.name[:10] for p in folder.glob("*.json.gz")} if folder.exists() else set()
        for d in dates_to_fetch(dt.date.fromisoformat(g["start"]), end, recent_days, have):
            need.setdefault(d, []).append(g)
    todo = sorted(need)[-limit:]
    print(f"history: {len(todo)} archive days to fetch")
    saved = 0
    for d in todo:
        tmp = Path(tempfile.mkdtemp())
        try:
            arc = tmp / "a.7z"
            download(ARCHIVE.format(d=d), arc)
            rows = read_archive(arc, {g["category"] for g in need[d]}, tmp)
            for g in need[d]:
                snap = {}
                for p in rows.get(g["category"], []):
                    m, low = p.get("marketPrice"), p.get("lowPrice")
                    sub = p.get("subTypeName") or "Normal"
                    if (m is not None or low is not None) and g["keep"](p["productId"], sub, m or low):
                        snap[history.key(p["productId"], sub)] = [m, low]
                if snap:
                    history.write_snapshot(hist_root / g["id"], d, snap)
                    saved += 1
            print(f"{d}: " + ", ".join(f"{g['id']} {len(rows.get(g['category'], []))}" for g in need[d]), flush=True)
        except Exception as e:
            print(f"{d}: skipped ({e})", flush=True)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            time.sleep(PAUSE)
    return saved
