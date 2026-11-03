"""Message text for every command, kept free of Discord objects so it can be tested.

Each function returns a dict: title, description, fields [(name, value, inline)], url, thumbnail, color.
"""
from __future__ import annotations

from .store import best_price

PURPLE, GREEN, ORANGE = 0x5B4BDB, 0x1D8A55, 0xC2410C


def money(v):
    if v is None:
        return "—"
    return f"${v:,.0f}" if abs(v) >= 100 else f"${v:,.2f}"


def pct(v, plus=True):
    if v is None:
        return "—"
    return f"{'+' if plus and v > 0 else ''}{v * 100:.0f}%"


def chg(v):
    if v is None:
        return "—"
    arrow = "▲" if v > 0 else "▼" if v < 0 else "•"
    return f"{arrow} {abs(v):.1f}%"


def one_in(n):
    if not n:
        return "not in packs"
    if n < 1.05:
        return "most boxes"
    return f"1 in {n:,.1f} boxes" if n < 10 else f"1 in {round(n):,} boxes"


def clip(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def card_embed(card: dict) -> dict:
    fields = []
    for sub, label in (("normal", "Normal"), ("foil", "Foil")):
        v = card.get(sub)
        if v and (v.get("market") or v.get("low")):
            fields.append((label, f"**{money(v.get('market') or v.get('low'))}**\nLowest listing {money(v.get('low'))}\n"
                                  f"7 days {chg(v.get('d7'))} · 30 days {chg(v.get('d30'))}", True))
    if not card.get("sealed"):
        fields.append(("Pull odds", one_in(card.get("boxes_per_hit")), True))
    desc = f"{card.get('kind', '')} · {card.get('set') or ''} {card.get('number') or ''}".strip(" ·")
    if card.get("thin"):
        desc += "\n⚠️ Thin market: few recent sales, so treat the price as rough."
    return {"title": clip(card["name"], 256), "url": card.get("url"), "description": desc, "fields": fields,
            "thumbnail": card.get("image"), "color": PURPLE}


def share_at_least(q: list[float], x: float) -> float:
    n = len(q) - 1
    if x <= q[0]:
        return 1.0
    if x > q[-1]:
        return 0.0
    for i in range(1, n + 1):
        if q[i] >= x:
            lo, hi = q[i - 1], q[i]
            f = 0 if hi == lo else (x - lo) / (hi - lo)
            return 1 - (i - 1 + f) / n
    return 0.0


def box_embed(s: dict, paid: float | None, dash: str) -> dict:
    b = s.get("box") or {}
    if not s.get("ev"):
        return {"title": f"{s['name']} booster box", "description": s.get("note", "No value yet."), "color": PURPLE,
                "fields": [("Box price", f"{money(b.get('market') or b.get('low'))} (MSRP {money(s.get('msrp_box'))})", False)],
                "url": dash}
    paid = paid or b.get("market") or s["msrp_box"]
    e, n = s["ev"], s["sim"]["net"]
    beat = share_at_least(n["quantiles"], paid)
    gap = e["box_net"] - paid
    hits = "\n".join(f"{h['label']}: {round(h['chance_in_box'] * 100)}% chance per box" for h in s.get("hit_odds", []))
    chase = "\n".join(f"{c['name']}: {money(c['price'])} ({one_in(c['boxes_per_hit'])})" for c in s.get("chase", [])[:5])
    return {
        "title": f"{s['name']} booster box at {money(paid)}", "url": dash, "color": GREEN if gap >= 0 else ORANGE,
        "description": f"**{s['open_vs_hold']['verdict']}**\nAn average box {'makes' if gap >= 0 else 'loses'} about "
                       f"{money(abs(gap))} once you sell the cards, and {round(beat * 100)} in 100 boxes come out ahead.",
        "fields": [
            ("Box price today", f"{money(b.get('market'))} ({pct(b.get('vs_msrp'))} vs MSRP)", True),
            ("Average value inside", money(e["box_sticker"]), True),
            ("You'd pocket (average)", money(e["box_net"]), True),
            ("Typical box (pocket)", f"{money(n['median'])}\nhalf do better, half worse", True),
            ("Bad box / great box", f"{money(n['p10'])} / {money(n['p90'])}", True),
            ("Sell it sealed instead", money(s["open_vs_hold"].get("sell_sealed_net")), True),
            ("Hits", hits or "—", False),
            ("Top chase cards", clip(chase or "—", 1024), False),
        ],
    }


def sets_embed(latest: dict, dash: str) -> dict:
    lines = []
    for s in latest["sets"]:
        b = s.get("box") or {}
        if s.get("ev"):
            lines.append(f"**{s['name']}**: box {money(b.get('market'))} · pocket avg {money(s['ev']['box_net'])} · "
                         f"typical {money(s['sim']['net']['median'])} · {round((s['sim']['net']['beat_market'] or 0) * 100)}% pay for themselves")
        else:
            lines.append(f"**{s['name']}**: pre-order box {money(b.get('market') or b.get('low'))} · releases {s['release']}")
    return {"title": "Riftbound booster boxes today", "url": dash, "color": PURPLE,
            "description": clip("\n".join(lines), 4000) + "\n\n*Pocket = after TCGplayer fees and shipping. Typical = the middle box.*"}


def sealed_embed(latest: dict, dash: str) -> dict:
    lines = []
    for r in latest["sealed"]:
        if r["kind"] not in ("box", "case"):
            continue
        per_year = "too new" if r.get("annualized") is None else f"{pct(r['annualized'])}/yr"
        lines.append(f"**{r['name']}**: {money(r.get('market') or r.get('low'))} · {pct(r.get('vs_msrp'))} vs MSRP · "
                     f"{per_year} · 30d {chg(r.get('change_30d'))}{' · pre-order' if r.get('presale') else ''}")
    return {"title": "Sealed boxes and cases", "url": dash + "#sealed", "color": PURPLE, "description": clip("\n".join(lines), 4000)}


def movers_embed(latest: dict, period: str, dash: str) -> dict:
    m = latest["movers"]
    key, up, down, label = ("d1", m["up_1d"], m["down_1d"], "since yesterday") if period == "day" else ("d7", m["up_7d"], m["down_7d"], "this week")
    fmt = lambda rows: "\n".join(f"{r['name']} ({r['set']}): {money(r['price'])} {chg(r[key])}" for r in rows[:8]) or "Not enough history yet."
    return {"title": f"Biggest price moves {label}", "url": dash, "color": PURPLE,
            "fields": [("Up", clip(fmt(up), 1024), False), ("Down", clip(fmt(down), 1024), False)]}


def digest_embed(latest: dict, dash: str) -> dict:
    """The daily post."""
    lines = []
    for s in latest["sets"]:
        b = s.get("box") or {}
        if not b:
            continue
        extra = f" · pocket avg {money(s['ev']['box_net'])}" if s.get("ev") else " · pre-order"
        lines.append(f"**{s['name']}** box {money(b.get('market') or b.get('low'))} ({chg(b.get('change_7d'))} 7d){extra}")
    m = latest["movers"]
    up = "\n".join(f"{r['name']}: {money(r['price'])} {chg(r['d1'])}" for r in m["up_1d"][:3])
    down = "\n".join(f"{r['name']}: {money(r['price'])} {chg(r['d1'])}" for r in m["down_1d"][:3])
    fields = [("Biggest risers today", up or "Not enough history yet.", True), ("Biggest drops today", down or "—", True)]
    for n in latest.get("new_sets") or []:
        fields.append(("New set spotted", f"{n['name']} is now listed on TCGplayer.", False))
    return {"title": f"Riftbound prices for {latest['price_date']}", "url": dash, "color": PURPLE,
            "description": clip("\n".join(lines), 4000), "fields": fields}


def check_watch(w: dict, card: dict | None) -> tuple[str, float | None]:
    """'fire' when the price crosses the target, 'rearm' when it moves back, else 'none'."""
    if not card:
        return "none", None
    price, _ = best_price(card, w["printing"])
    if price is None:
        return "none", None
    hit = price <= w["price"] if w["direction"] == "below" else price >= w["price"]
    if hit and w["armed"]:
        return "fire", price
    if not hit and not w["armed"]:
        return "rearm", price
    return "none", price


def collection_embed(rows: list[dict], cards: dict) -> dict:
    total = cost = 0.0
    have_cost = False
    lines = []
    for r in rows:
        c = cards.get(r["card_id"])
        price, _ = best_price(c, r["printing"]) if c else (None, None)
        val = (price or 0) * r["qty"]
        total += val
        if r["paid_each"] is not None:
            cost += r["paid_each"] * r["qty"]
            have_cost = True
        name = c["name"] if c else f"#{r['card_id']}"
        lines.append((val, f"{r['qty']}× {name} ({r['printing']}): {money(val)}"))
    lines.sort(key=lambda x: -x[0])
    desc = "\n".join(l for _, l in lines[:25]) or "Nothing yet. Add cards with /collection add."
    if len(lines) > 25:
        desc += f"\n…and {len(lines) - 25} more"
    fields = [("Worth today", money(total), True)]
    if have_cost:
        fields += [("You paid", money(cost), True), ("Gain", f"{money(total - cost)} ({pct(total / cost - 1) if cost else '—'})", True)]
    return {"title": "Your collection", "description": clip(desc, 4000), "fields": fields, "color": PURPLE}
