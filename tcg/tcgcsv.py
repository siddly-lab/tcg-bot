"""Small client for tcgcsv.com, a free daily copy of TCGplayer's catalog and prices."""
from __future__ import annotations

import json
import time
import urllib.request

BASE = "https://tcgcsv.com/tcgplayer"
UA = {"User-Agent": "tcg-bot (+https://github.com/siddly-lab/tcg-bot)"}
RIFTBOUND_CATEGORY = 89


def get_json(url: str, tries: int = 4):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as e:  # network hiccup: back off and retry
            last = e
            time.sleep(2 ** i)
    raise RuntimeError(f"failed to fetch {url}: {last}")


def find_category() -> int:
    try:
        cats = get_json(f"{BASE}/categories")["results"]
        for c in cats:
            if "riftbound" in (c.get("name") or "").lower():
                return int(c["categoryId"])
    except Exception:
        pass
    return RIFTBOUND_CATEGORY


def groups(cat: int) -> list[dict]:
    return get_json(f"{BASE}/{cat}/groups")["results"]


def products(cat: int, group: int) -> list[dict]:
    return get_json(f"{BASE}/{cat}/{group}/products")["results"]


def prices(cat: int, group: int) -> list[dict]:
    return get_json(f"{BASE}/{cat}/{group}/prices")["results"]


def last_updated() -> str | None:
    try:
        req = urllib.request.Request("https://tcgcsv.com/last-updated.txt", headers=UA)
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode().strip()
    except Exception:
        return None
