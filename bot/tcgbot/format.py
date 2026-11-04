"""Message text for every command, kept free of Discord objects so it can be tested.

Each function returns a dict: title, description, fields [(name, value, inline)], url, thumbnail, color.
"""
from __future__ import annotations

from .store import best_price, with_year

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


def card_embed(card: dict, game_name: str = "") -> dict:
    fields = []
    for sub, v in (card.get("prices") or {}).items():
        if v and (v.get("market") or v.get("low")):
            fields.append((sub, f"**{money(v.get('market') or v.get('low'))}**\nLowest listing {money(v.get('low'))}\n"
                                f"7 days {chg(v.get('d7'))} · 30 days {chg(v.get('d30'))}", True))
    if card.get("low90") and card.get("high90"):
        fields.append(("Last 90 days", f"{money(card['low90'])} to {money(card['high90'])}\n{card.get('zone_label') or ''}", True))
    if not card.get("sealed"):
        fields.append(("Pull odds", one_in(card.get("boxes_per_hit")), True))
    where = " · ".join(x for x in (game_name, with_year(card.get("set_name") or card.get("set"), card.get("set_year")), card.get("number")) if x)
    desc = f"{card.get('kind', '')} · {where}".strip(" ·")
    if card.get("no_sale"):
        desc += "\n⚠️ No recent sales: this is only what sellers are asking."
    elif card.get("falling"):
        desc += "\nListings are well under the last sale, so the price is probably dropping."
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


def box_embed(s: dict, d: dict, paid: float | None, dash: str, game_name: str = "") -> dict:
    """s: the set's summary row, d: its detail file."""
    h = s.get("hero") or {}
    name = with_year(s["name"], s.get("year"))
    title = f"{game_name} · {name}" if game_name else name
    zone = f"\n{h.get('zone_label')} (90 days: {money(h.get('low90'))} to {money(h.get('high90'))})" if h.get("low90") else ""
    if d.get("ev_hold"):
        return {"title": f"{title}: box value being checked", "url": dash, "color": ORANGE,
                "description": "This set's box value is hidden until it passes the daily checks: " + "; ".join(d["ev_hold"])}
    if not d.get("modeled"):
        chase = "\n".join(f"{c['name']}: {money(c['price'])}" for c in d.get("chase", [])[:5])
        return {"title": f"{title} {(h.get('kind_label') or 'sealed').lower()}", "url": dash, "color": PURPLE,
                "description": f"{h.get('kind_label') or 'Sealed'} {money(h.get('market') or h.get('low'))} (MSRP {money(h.get('msrp'))}){zone}\n"
                               "*No box value for this set: there's no reliable pack data for it.*",
                "fields": [("Top cards", clip(chase or "—", 1024), False)]}
    paid = paid or h.get("market") or (d.get("msrp") or {}).get("box")
    e, n = d["ev"], d["sim"]["net"]
    beat = share_at_least(n["quantiles"], paid)
    gap = e["box_net"] - paid
    hits = "\n".join(f"{x['label']}: {round(x['chance_in_box'] * 100)}% chance per box" for x in d.get("hit_odds", []))
    chase = "\n".join(f"{c['name']}: {money(c['price'])} ({one_in(c.get('boxes_per_hit'))})" for c in d.get("chase", [])[:5])
    ways = " · ".join(f"{w['label']} {money(w['per_pack'])}/pack" for w in d.get("ways_to_buy", [])[:3])
    rip = "\n".join(f"{r['label']}: pay {money(r['pay'])}, rip {pct(r['rip_return'])}"
                     + (f", held {pct(r['hold']['change'])} since {r['hold']['since']}" if r.get("hold") else "") for r in d.get("rip_or_hold", []))
    return {
        "title": f"{title} booster box at {money(paid)}", "url": dash, "color": GREEN if gap >= 0 else ORANGE,
        "description": f"**{d['open_vs_hold']['verdict']}**\nAn average box {'makes' if gap >= 0 else 'loses'} about "
                       f"{money(abs(gap))} once you sell the cards, and {round(beat * 100)} in 100 boxes come out ahead.{zone}",
        "fields": [
            ("Box price today", f"{money(h.get('market'))} ({pct(h.get('vs_msrp'))} vs MSRP)", True),
            ("Average value inside", money(e["box_sticker"]), True),
            ("You'd pocket (average)", money(e["box_net"]), True),
            ("Typical box (pocket)", f"{money(n['median'])}\nhalf do better, half worse", True),
            ("Bad box / great box", f"{money(n['p10'])} / {money(n['p90'])}", True),
            ("Cheapest per pack", ways or "—", True),
            ("Rip or hold", rip or "—", False),
            ("Hits", hits or "—", False),
            ("Top chase cards", clip(chase or "—", 1024), False),
        ],
    }


def sets_embed(summary: dict, dash: str) -> dict:
    lines = []
    for s in summary["sets"][:20]:
        h = s.get("hero") or {}
        price = f"{(h.get('kind_label') or 'box').lower()} {money(h.get('market') or h.get('low'))}"
        zone = f" · {h['zone_label'].lower()}" if h.get("zone_label") and h.get("zone") not in ("normal", "new") else ""
        if s.get("ev"):
            lines.append(f"**{with_year(s['name'], s.get('year'))}**: {price}{zone} · pocket avg {money(s['ev']['box_net'])} · "
                         f"{round((s['ev']['beat_market'] or 0) * 100)}% of boxes pay for themselves")
        elif s.get("ev_hold"):
            lines.append(f"**{with_year(s['name'], s.get('year'))}**: {price}{zone} · box value being checked")
        elif s.get("released"):
            lines.append(f"**{with_year(s['name'], s.get('year'))}**: {price}{zone}")
        else:
            lines.append(f"**{with_year(s['name'], s.get('year'))}**: pre-order {price} · releases {s['release']}")
    return {"title": f"{summary['name']} sets, newest first", "url": dash, "color": PURPLE,
            "description": clip("\n".join(lines), 4000) + "\n\n*Pocket = after TCGplayer fees and shipping.*"}


def sealed_embed(summary: dict, dash: str) -> dict:
    lines = []
    for r in summary["today"]["buy_signals"][:12]:
        lines.append(f"**{r['name']}**: {money(r.get('market'))} · {r['zone_label'].lower()} "
                     f"(90 days {money(r.get('low90'))}–{money(r.get('high90'))}) · {pct(r.get('vs_msrp'))} vs MSRP")
    return {"title": f"{summary['name']}: sealed at a good price right now", "url": dash, "color": GREEN,
            "description": clip("\n".join(lines) or "Nothing is near its 90-day low or at MSRP right now.", 4000)}


def movers_embed(summary: dict, period: str, dash: str) -> dict:
    m = summary["movers"]
    key, up, down, label = ("d1", m["up_1d"], m["down_1d"], "since yesterday") if period == "day" else ("d7", m["up_7d"], m["down_7d"], "this week")
    years = {x["code"]: x.get("year") for x in summary.get("sets", [])}
    fmt = lambda rows: "\n".join(f"{r['name']} ({with_year(r.get('set_name') or r['set'], years.get(r['set']))}): {money(r['price'])} {chg(r[key])}" for r in rows[:8]) or "Not enough history yet."
    return {"title": f"{summary['name']}: biggest price moves {label}", "url": dash, "color": PURPLE,
            "fields": [("Up", clip(fmt(up), 1024), False), ("Down", clip(fmt(down), 1024), False)]}


def digest_embed(summaries: dict, dash: str) -> dict:
    """The daily post: buy signals and movers for every game."""
    fields = []
    date = max(s["price_date"] for s in summaries.values())
    for gid, s in summaries.items():
        t = s["today"]
        buys = "\n".join(f"{r['name']}: {money(r['market'])} · {r['zone_label'].lower()}" for r in t["buy_signals"][:4])
        up = "\n".join(f"{r['name']}: {money(r['price'])} {chg(r['d1'])}" for r in s["movers"]["up_1d"][:3])
        fields.append((f"{s['name']}: good prices on sealed", buys or "Nothing near its low today.", False))
        fields.append((f"{s['name']}: biggest risers", up or "Not enough history yet.", False))
        for a in t.get("alerts", [])[:2]:
            fields.append((f"{s['name']}: heads up", a["text"], False))
    return {"title": f"Card prices for {date}", "url": dash, "color": PURPLE, "fields": fields[:25]}


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
    """rows: what the member owns; cards: every product by id."""
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
