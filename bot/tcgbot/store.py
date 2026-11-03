"""The dashboard's data files, fetched from GitHub Pages and searched locally."""
from __future__ import annotations

import json
import re
from pathlib import Path


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def best_price(card: dict, printing: str | None = None) -> tuple[float | None, str | None]:
    """Price for a printing, or the more valuable printing when none is given."""
    opts = []
    for sub in ("normal", "foil"):
        v = card.get(sub) or {}
        p = v.get("market") or v.get("low")
        if p:
            opts.append((p, sub))
    if printing:
        for p, sub in opts:
            if sub == printing:
                return p, sub
        return None, printing
    return max(opts) if opts else (None, None)


class Store:
    def __init__(self, cache_dir: str | Path | None = None):
        self.latest: dict = {}
        self.cards: list[dict] = []
        self.by_id: dict[int, dict] = {}
        self.cache = Path(cache_dir) if cache_dir else None

    def load(self, latest: dict, cards: list[dict]):
        self.latest, self.cards = latest, cards
        self.by_id = {c["id"]: c for c in cards}
        for s in latest.get("sealed", []):
            # sealed products can be watched and collected too
            self.by_id.setdefault(s["id"], {"id": s["id"], "set": s.get("set"), "name": s["name"], "kind": s["kind_label"],
                                            "url": s["url"], "image": s.get("image"),
                                            "normal": {"market": s.get("market"), "low": s.get("low"),
                                                       "d7": s.get("change_7d"), "d30": s.get("change_30d")},
                                            "sealed": True})
        if self.cache:
            self.cache.mkdir(parents=True, exist_ok=True)
            (self.cache / "latest.json").write_text(json.dumps(latest))
            (self.cache / "cards.json").write_text(json.dumps(cards))

    def load_cache(self) -> bool:
        if not self.cache or not (self.cache / "latest.json").exists():
            return False
        self.load(json.loads((self.cache / "latest.json").read_text()), json.loads((self.cache / "cards.json").read_text()))
        return True

    async def refresh(self, session, base_url: str) -> bool:
        """Fetch fresh files. Returns True when the prices are from a newer build than before."""
        old = self.latest.get("generated_at")
        async with session.get(base_url + "latest.json") as r:
            r.raise_for_status()
            latest = await r.json(content_type=None)
        async with session.get(base_url + "cards.json") as r:
            r.raise_for_status()
            cards = await r.json(content_type=None)
        self.load(latest, cards)
        return latest.get("generated_at") != old

    def search(self, q: str, limit: int = 25) -> list[dict]:
        nq = norm(q)
        if not nq:
            items = sorted(self.by_id.values(), key=lambda c: -(best_price(c)[0] or 0))
            return items[:limit]
        words = nq.split()
        hits = [c for c in self.by_id.values() if all(w in norm(c["name"] + " " + (c.get("set") or "")) for w in words)]
        hits.sort(key=lambda c: (not norm(c["name"]).startswith(nq), -(best_price(c)[0] or 0)))
        return hits[:limit]

    def set_by(self, key: str) -> dict | None:
        k = key.strip().lower()
        for s in self.latest.get("sets", []):
            if k in (s["code"].lower(), s["name"].lower()):
                return s
        return None
