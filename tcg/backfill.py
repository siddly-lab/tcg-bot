"""One-time backfill of price history from tcgcsv's daily archives.

Each archive holds every game's prices for one day (prices-YYYY-MM-DD.ppmd.7z). We keep only
Riftbound's and save them in the same snapshot format as the daily build.

    python -m tcg.backfill --start 2025-10-24 --weekly-before-days 35
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import tempfile
import urllib.request
from pathlib import Path

from . import history, tcgcsv

ARCHIVE = "https://tcgcsv.com/archive/tcgplayer/prices-{d}.ppmd.7z"


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


def snapshot_from_archive(path: Path, cat: int, workdir: Path) -> dict[str, list]:
    import py7zr  # only needed here

    with py7zr.SevenZipFile(path, "r") as z:
        names = [n for n in z.getnames() if f"/{cat}/" in n and n.endswith("prices")]
        z.extract(path=workdir, targets=names)
    snap = {}
    for n in names:
        try:
            data = json.loads((workdir / n).read_text())
        except Exception:
            continue
        rows = data.get("results", data) if isinstance(data, dict) else data
        for p in rows:
            m, low = p.get("marketPrice"), p.get("lowPrice")
            if m is not None or low is not None:
                snap[history.key(p["productId"], p.get("subTypeName") or "Normal")] = [m, low]
    return snap


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2025-10-24")
    ap.add_argument("--end", default=None)
    ap.add_argument("--recent-days", type=int, default=35)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "data" / "history"))
    a = ap.parse_args(argv)
    out = Path(a.out)
    have = {p.name[:10] for p in out.glob("*.json.gz")}
    end = dt.date.fromisoformat(a.end) if a.end else dt.date.today() - dt.timedelta(days=1)
    todo = dates_to_fetch(dt.date.fromisoformat(a.start), end, a.recent_days, have)
    print(f"{len(todo)} days to fetch")
    ok = 0
    for d in todo:
        tmp = Path(tempfile.mkdtemp())
        try:
            arc = tmp / "a.7z"
            req = urllib.request.Request(ARCHIVE.format(d=d), headers=tcgcsv.UA)
            with urllib.request.urlopen(req, timeout=300) as r, open(arc, "wb") as f:
                shutil.copyfileobj(r, f)
            snap = snapshot_from_archive(arc, tcgcsv.RIFTBOUND_CATEGORY, tmp)
            if snap:
                history.write_snapshot(out, d, snap)
                ok += 1
            print(f"{d}: {len(snap)} prices ({arc.stat().st_size // 1_000_000} MB archive)", flush=True)
        except Exception as e:
            print(f"{d}: skipped ({e})", flush=True)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    print(f"saved {ok} days")


if __name__ == "__main__":
    main()
