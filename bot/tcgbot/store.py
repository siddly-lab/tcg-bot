"""The dashboard's data files, fetched from GitHub Pages and searched locally.

Layout: data/games.json, data/<game>/summary.json, data/<game>/cards.json, data/<game>/sets/<code>.json
"""
from __future__ import annotations

import json
import re
from pathlib import Path


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def best_price(card: dict | None, printing: str | None = None) -> tuple[float | None, str | None]:
    """Price for a printing, or the most valuable printing when none is given."""
    if not card:
        return None, printing
    opts = []
    for sub, v in (card.get("prices") or {}).items():
        p = (v or {}).get("market") or (v or {}).get("low")
        if p:
            opts.append((p, sub))
    if printing:
        for p, sub in opts:
            if sub.lower() == printing.lower():
                return p, sub
        return None, printing
    return max(opts) if opts else (None, None)


class Store:
    def __init__(self, cache_dir: str | Path | None = None):
        self.games: list[dict] = []
        self.summary: dict[str, dict] = {}
        self.cards: dict[str, list[dict]] = {}
        self.by_id: dict[int, dict] = {}
        self.set_files: dict[tuple[str, str], dict] = {}
        self.cache = Path(cache_dir) if cache_dir else None

    # ------------------------------------------------------------ loading
    def load(self, games: list[dict], summaries: dict[str, dict], cards: dict[str, list[dict]]):
        self.games, self.summary, self.cards = games, summaries, cards
        self.by_id = {}
        self.set_files = {}
        for gid, rows in cards.items():
            for c in rows:
                self.by_id[c["id"]] = c | {"game": gid}
        for gid, s in summaries.items():
            for r in s.get("sealed", []):
                self.by_id.setdefault(r["id"], {
                    "id": r["id"], "game": gid, "set": r.get("set"), "set_name": r.get("set_name"), "name": r["name"],
                    "kind": r.get("kind_label"), "url": r["url"], "image": r.get("image"), "sealed": True,
                    "zone_label": r.get("zone_label"), "low90": r.get("low90"), "high90": r.get("high90"),
                    "prices": {"Normal": {"market": r.get("market"), "low": r.get("low"), "d7": r.get("change_7d"), "d30": r.get("change_30d")}}})
        if self.cache:
            self.cache.mkdir(parents=True, exist_ok=True)
            (self.cache / "store.json").write_text(json.dumps({"games": games, "summary": summaries, "cards": cards}))

    def load_cache(self) -> bool:
        if not self.cache or not (self.cache / "store.json").exists():
            return False
        d = json.loads((self.cache / "store.json").read_text())
        self.load(d["games"], d["summary"], d["cards"])
        return True

    async def _json(self, session, url):
        async with session.get(url) as r:
            r.raise_for_status()
            return await r.json(content_type=None)

    async def refresh(self, session, base_url: str) -> bool:
        """Fetch fresh files. Card lists are only downloaded when a game's prices changed."""
        idx = await self._json(session, base_url + "games.json")
        games = idx["games"]
        summaries, cards, changed = {}, {}, False
        for g in games:
            s = await self._json(session, f"{base_url}{g['id']}/summary.json")
            summaries[g["id"]] = s
            old = self.summary.get(g["id"], {})
            if old.get("generated_at") != s.get("generated_at") or g["id"] not in self.cards:
                cards[g["id"]] = await self._json(session, f"{base_url}{g['id']}/cards.json")
                changed = True
            else:
                cards[g["id"]] = self.cards[g["id"]]
        self.load(games, summaries, cards)
        return changed

    async def set_detail(self, session, base_url: str, game: str, s: dict) -> dict:
        key = (game, s["code"])
        if key not in self.set_files:
            self.set_files[key] = await self._json(session, f"{base_url}{game}/{s['file']}")
        return self.set_files[key]

    # ------------------------------------------------------------ lookups
    def game_name(self, gid: str) -> str:
        return next((g["name"] for g in self.games if g["id"] == gid), gid)

    @property
    def price_date(self) -> str | None:
        return max((s.get("price_date") or "" for s in self.summary.values()), default=None)

    def search(self, q: str, limit: int = 25) -> list[dict]:
        nq = norm(q)
        items = self.by_id.values()
        if not nq:
            return sorted(items, key=lambda c: -(best_price(c)[0] or 0))[:limit]
        words = nq.split()
        hits = [c for c in items if all(w in norm(f"{c['name']} {c.get('set') or ''} {c.get('set_name') or ''}") for w in words)]
        hits.sort(key=lambda c: (not norm(c["name"]).startswith(nq), -(best_price(c)[0] or 0)))
        return hits[:limit]

    def all_sets(self):
        for gid, s in self.summary.items():
            for x in s.get("sets", []):
                yield gid, x

    def set_by(self, key: str) -> tuple[str, dict] | tuple[None, None]:
        k = key.strip().lower()
        if ":" in k:
            g, c = k.split(":", 1)
            for gid, s in self.all_sets():
                if gid == g and s["code"].lower() == c:
                    return gid, s
        for gid, s in self.all_sets():
            if k in (s["code"].lower(), s["name"].lower()):
                return gid, s
        return None, None
