"""Daily build: pull prices for every game, run the box math, write the dashboard's data files.

    python -m tcg.build                 live data, every game
    python -m tcg.build --offline       reuse the cached raw pulls in data/raw/
    python -m tcg.build --game pokemon  one game only
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
import sys
import time
from pathlib import Path

from . import __version__, backfill, ev, history, market, tcgcsv
from .games import load as load_game

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
HIST = ROOT / "data" / "history"
RAW = ROOT / "data" / "raw"
OUT = ROOT / "site" / "data"
MAIN_KINDS = ("box", "case", "etb", "bundle", "pack")


def load_config() -> tuple[dict, list[dict]]:
    common = json.loads((CONFIG / "common.json").read_text())
    games = [json.loads(p.read_text()) for p in sorted((CONFIG / "games").glob("*.json"))]
    games.sort(key=lambda g: g.get("order", 99))
    return common, games


# ---------------------------------------------------------------- fetching

def fetch_raw(cat: int) -> dict:
    groups = tcgcsv.groups(cat)
    out = {"category": cat, "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "source_updated": tcgcsv.last_updated(), "groups": []}
    for g in groups:
        gid = g["groupId"]
        out["groups"].append({"group": g, "products": tcgcsv.products(cat, gid), "prices": tcgcsv.prices(cat, gid)})
        if len(groups) > 40:
            time.sleep(0.1)  # big catalogs: be gentle
    return out


# ---------------------------------------------------------------- shaping

def base_name(name: str) -> str:
    """'Riven, The Exile (Signature)' -> 'Riven, The Exile'."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()


def shape(raw: dict, gcfg: dict, mod) -> tuple[dict[int, dict], list[dict], list[dict]]:
    groups = [g["group"] for g in raw["groups"]]
    by_group = {g["group"]["groupId"]: g["products"] for g in raw["groups"]}
    sets = mod.sets_from_groups(groups, by_group, gcfg)
    gid_to_set = {s["group_id"]: s for s in sets}
    unknown = mod.unknown_sets(groups, by_group, gcfg, set(gid_to_set))
    products: dict[int, dict] = {}
    for g in raw["groups"]:
        grp = g["group"]
        sset = gid_to_set.get(grp["groupId"])
        if not sset:
            continue
        prices: dict[int, dict] = {}
        for p in g["prices"]:
            prices.setdefault(p["productId"], {})[p.get("subTypeName") or "Normal"] = {
                "market": p.get("marketPrice"), "low": p.get("lowPrice")}
        for p in g["products"]:
            rec = {"id": p["productId"], "name": mod.card_name(p["name"]), "group": grp["name"], "set": sset["code"],
                   "number": _ext(p, "Number"), "rarity": _ext(p, "Rarity"), "url": p.get("url"),
                   "image": p.get("imageUrl") if p.get("imageCount", 1) else None,
                   "prices": prices.get(p["productId"], {}),
                   "presale": bool((p.get("presaleInfo") or {}).get("isPresale"))}
            if mod.is_sealed(p):
                rec["sealed"] = mod.sealed_type(p["name"])
                rec["name"] = p["name"].strip()
            else:
                rec["bucket"] = mod.classify_card(p)
            products[rec["id"]] = rec
    fill_missing_images(products)
    return products, sets, unknown


def _ext(p, k):
    for e in p.get("extendedData") or []:
        if e.get("name") == k:
            return e.get("value")
    return None


def fill_missing_images(products: dict[int, dict]) -> None:
    """Borrow the picture of the same card's other version when TCGplayer has no photo yet."""
    by_number, by_name = {}, {}
    for p in products.values():
        if not p.get("image") or p.get("sealed"):
            continue
        if p.get("number"):
            by_number.setdefault((p["set"], p["number"].replace("*", "")), p["image"])
        by_name.setdefault((p["set"], base_name(p["name"])), p["image"])
    for p in products.values():
        if p.get("image") or p.get("sealed"):
            continue
        img = by_number.get((p["set"], (p.get("number") or "").replace("*", ""))) or by_name.get((p["set"], base_name(p["name"])))
        if img:
            p["image"] = img
            p["image_standin"] = True


def snapshot_of(products: dict[int, dict], keep) -> dict[str, list]:
    snap = {}
    for p in products.values():
        for sub, v in p["prices"].items():
            val = v.get("market") or v.get("low")
            if val and keep(p["id"], sub, val):
                snap[history.key(p["id"], sub)] = [v.get("market"), v.get("low")]
    return snap


def keeper(gcfg: dict, products: dict, sets: list[dict]):
    if gcfg.get("history", "all") == "all":
        return lambda pid, sub, val: pid in products
    modeled = {s["code"] for s in sets if s.get("modeled")}
    floor = gcfg.get("history_card_min", 20)

    def keep(pid, sub, val):
        p = products.get(pid)
        if not p:
            return False
        return bool(p.get("sealed")) or p["set"] in modeled or (val or 0) >= floor
    return keep


def with_prices(cards: list[dict], snap: dict) -> list[dict]:
    out = []
    for c in cards:
        pr = {}
        for sub in c["prices"] or {"Normal": None}:
            e = snap.get(history.key(c["id"], sub))
            if e:
                pr[sub] = {"market": e[0], "low": e[1]}
        out.append({**c, "prices": pr})
    return out


def thin_market(p: dict) -> bool:
    for v in p["prices"].values():
        m, low = v.get("market"), v.get("low")
        if m and low and 0.6 <= low / m <= 1.6:
            return False
    return True


def best(p: dict | None) -> tuple[float | None, float | None, str | None]:
    """(market, cheapest listing, printing) for the most valuable printing."""
    if not p or not p["prices"]:
        return None, None, None
    sub = max(p["prices"], key=lambda s: (p["prices"][s].get("market") or 0, p["prices"][s].get("low") or 0))
    v = p["prices"][sub]
    return v.get("market") or v.get("low"), v.get("low"), sub


def roi(value, cost):
    if not cost or value is None:
        return None
    return round(value / cost - 1, 4)


def safe(code: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", code)


# ---------------------------------------------------------------- per product

class Ctx:
    def __init__(self, common, gcfg, mod, products, hist, series, today, bench):
        self.common, self.gcfg, self.mod, self.products = common, gcfg, mod, products
        self.hist, self.series, self.today, self.bench = hist, series, today, bench
        self.prev = {n: history.on_or_before(hist, today, n) or {} for n in (1, 7, 30)}

    def chg(self, pid, sub, now, days):
        return history.pct(now, history.market(self.prev[days].get(history.key(pid, sub))))


def sealed_summary(ctx: Ctx, p: dict, sset: dict, with_series: bool = False) -> dict:
    m, low, sub = best(p)
    kind = p["sealed"]
    msrp = (sset.get("msrp") or {}).get(kind)
    ser = ctx.series.get(history.key(p["id"], sub or "Normal"), [])
    st = market.stats(ser, ctx.today, m, msrp, ctx.common["zones"])
    packs = ctx.gcfg["packs"].get(kind)
    cost = market.buy_cost(low, m, kind, ctx.common["buying"])
    out = {"id": p["id"], "name": p["name"], "set": p["set"], "set_name": sset["name"], "era": sset.get("era"),
           "kind": kind, "kind_label": ctx.mod.SEALED_LABELS.get(kind, kind), "url": p["url"], "image": p["image"],
           "market": m, "low": low, "msrp": msrp, "vs_msrp": roi(m, msrp), "presale": p.get("presale"),
           "change_7d": ctx.chg(p["id"], sub, m, 7), "change_30d": ctx.chg(p["id"], sub, m, 30),
           "buy_cost": cost, "packs": packs, "per_pack": round(cost / packs, 2) if cost and packs else None,
           "thin": thin_market(p), **st}
    release = sset.get("release")
    if release and m and msrp:
        days = (dt.date.fromisoformat(ctx.today) - dt.date.fromisoformat(release)).days
        out["days_since_release"] = days
        out["annualized"] = round((m / msrp) ** (365 / days) - 1, 4) if days >= 90 else None
        sel = ctx.common["selling"]
        out["net_if_sold"] = round(m * (1 - sel["sealed_fee_pct"]) - sel["sealed_ship_cost"], 2)
        out["bench"] = market.compare(release, ctx.today, msrp, m, ctx.bench, ctx.common["benchmark"])
    if with_series:
        out["series"] = [[d, round(v, 2)] for d, v in ser]
    return out


def canonical(products, code, kind):
    c = [p for p in products.values() if p["set"] == code and p.get("sealed") == kind and best(p)[0]]
    return min(c, key=lambda p: (len(p["name"]), p["id"])) if c else None


def card_row(ctx: Ctx, c: dict, odds: dict, ppb: int | None, with_series=False) -> dict:
    m, low, sub = best(c)
    ser = ctx.series.get(history.key(c["id"], sub), []) if sub else []
    st = market.stats(ser, ctx.today, m, None, ctx.common["zones"])
    row = {"id": c["id"], "set": c["set"], "name": c["name"], "number": c["number"], "rarity": c["rarity"],
           "kind": ctx.mod.LABELS.get(c.get("bucket"), c.get("rarity") or ""), "url": c["url"], "image": c["image"],
           "standin": bool(c.get("image_standin")), "thin": thin_market(c), "price": m, "printing": sub,
           "zone": st["zone"], "zone_label": st.get("zone_label"), "low90": st["low90"], "high90": st["high90"],
           "prices": {s: {"market": v.get("market"), "low": v.get("low"), "d7": ctx.chg(c["id"], s, v.get("market"), 7),
                          "d30": ctx.chg(c["id"], s, v.get("market"), 30)} for s, v in c["prices"].items()}}
    if c["id"] in odds and ppb:
        pb = ev.per_box(odds[c["id"]], ppb)
        row["per_box"] = round(pb, 6)
        row["boxes_per_hit"] = round(1 / pb, 1) if pb else None
    if with_series:
        row["series"] = [[d, round(v, 2)] for d, v in ser]
    return row


# ---------------------------------------------------------------- per set

def analyze_set(ctx: Ctx, sset: dict) -> tuple[dict, dict]:
    code, gcfg, common, products = sset["code"], ctx.gcfg, ctx.common, ctx.products
    selling = common["selling"]
    tmpl = gcfg["templates"].get(sset.get("template") or "") if sset.get("modeled") else None
    cards = [p for p in products.values() if p["set"] == code and not p.get("sealed")]
    sealed = [p for p in products.values() if p["set"] == code and p.get("sealed")]
    sealed_rows = sorted((sealed_summary(ctx, p, sset, with_series=True) for p in sealed),
                         key=lambda r: (MAIN_KINDS.index(r["kind"]) if r["kind"] in MAIN_KINDS else 9, r["name"]))
    canon = {k: canonical(products, code, k) for k in MAIN_KINDS}
    canon_rows = {k: next(r for r in sealed_rows if r["id"] == p["id"]) for k, p in canon.items() if p}
    box_row = canon_rows.get("box")
    hero = box_row or canon_rows.get("etb") or canon_rows.get("bundle") or canon_rows.get("pack")
    released = bool(sset.get("release")) and sset["release"] <= ctx.today
    detail = {"code": code, "name": sset["name"], "full_name": sset.get("full_name", sset["name"]), "era": sset.get("era"),
              "release": sset.get("release"), "released": released, "modeled": False, "msrp": sset.get("msrp"),
              "print_status": sset.get("print_status"), "image": (hero or {}).get("image"),
              "sealed": sealed_rows, "canonical": {k: r["id"] for k, r in canon_rows.items()},
              "ways_to_buy": ways_to_buy(canon_rows)}
    buckets: dict[str, list] = {}
    for c in cards:
        if c.get("bucket"):
            buckets.setdefault(c["bucket"], []).append(c)
    odds, ppb = {}, None
    if tmpl and buckets.get("Common"):
        detail["modeled"] = True
        ppb, bpc = tmpl["packs_per_box"], tmpl["boxes_per_case"]
        overrides = {s["name"]: sset["rare_printing"] for s in tmpl["slots"] if s["name"].startswith("Rare")} if sset.get("rare_printing") else {}
        slots = ev.build_slots(tmpl, {k: len(v) for k, v in buckets.items()}, overrides)
        bp = getattr(ctx.mod, "BUCKET_PRINTING", {})
        vals = ev.slot_values(slots, buckets, selling, bp)
        e = ev.expected(slots, vals)
        box_price = (box_row or {}).get("market")
        msrp = (sset.get("msrp") or {}).get("box")
        sim = ev.summarize_sim(ev.simulate(slots, vals, ppb, boxes=10000, seed=f"{gcfg['id']}-{code}-{ctx.today}"), box_price, msrp)
        bs, bn = e["sticker"] * ppb, e["net"] * ppb
        odds = ev.card_odds_per_pack(slots, buckets)
        detail.update({
            "packs_per_box": ppb, "boxes_per_case": bpc,
            "ev": {"pack_sticker": round(e["sticker"], 2), "pack_net": round(e["net"], 2), "box_sticker": round(bs, 2),
                   "box_net": round(bn, 2), "case_sticker": round(bs * bpc, 2), "case_net": round(bn * bpc, 2)},
            "contrib": sorted([{"bucket": b, "label": ctx.mod.LABELS.get(b, b), "box_sticker": round(e["by_bucket_sticker"][b] * ppb, 2),
                                "box_net": round(e["by_bucket_net"][b] * ppb, 2)} for b in e["by_bucket_sticker"]],
                              key=lambda x: -x["box_sticker"]),
            "sim": sim,
            "hit_odds": hit_odds(slots, ppb, tmpl, ctx.mod),
            "odds_notes": tmpl.get("odds_notes", []),
            "card_counts": {ctx.mod.LABELS.get(k, k): len(v) for k, v in buckets.items()},
        })
        hold = box_price * (1 - selling["sealed_fee_pct"]) - selling["sealed_ship_cost"] if box_price else None
        detail["open_vs_hold"] = {"open_net_avg": round(bn, 2), "open_net_typical": sim["net"]["median"],
                                  "sell_sealed_net": round(hold, 2) if hold else None,
                                  "verdict": verdict(bn, sim["net"]["median"], hold)}
        # how much of a box's value rides on its ten most valuable cards
        per_card = sorted(((odds.get(c["id"], 0) * ppb * ev.price_of(c, slot_printing(c, slots, bp)), c["id"]) for c in cards if c["id"] in odds), reverse=True)
        detail["top10_share"] = round(sum(v for v, _ in per_card[:10]) / bs, 4) if bs else None
        detail["ev_series"] = ev_series(ctx, slots, buckets, selling, bp, ppb, box_row)
    # chase cards: most valuable cards in the set, with buy-vs-pull when odds are known
    rows = [card_row(ctx, c, odds, ppb, with_series=True) for c in cards]
    rows.sort(key=lambda r: -(r["price"] or 0))
    for r in rows[:25]:
        r["buy_cost"] = market.buy_cost(best(products[r["id"]])[1], r["price"], "card", common["buying"])
        if r.get("per_box") and box_row and box_row.get("buy_cost") and detail.get("ev"):
            n = 1 / r["per_box"]
            pull = n * (box_row["buy_cost"] - detail["ev"]["box_net"]) + ev.net_value(r["price"] or 0, selling)
            r["pull_cost"] = round(max(pull, 0), 2)
            r["pull_boxes"] = round(n, 1)
    detail["chase"] = rows[:25]
    detail["cards"] = [{k: v for k, v in r.items() if k != "series"} | ({"series": r["series"]} if (r["price"] or 0) >= 1 else {})
                       for r in rows]
    summary = {
        "code": code, "name": sset["name"], "era": sset.get("era"), "release": sset.get("release"), "released": released,
        "year": (sset.get("release") or "")[:4], "modeled": detail["modeled"], "image": detail["image"],
        "file": f"sets/{safe(code)}.json", "print_status": sset.get("print_status"),
        "hero": hero_summary(hero, sset) if hero else None,
        "ev": {"box_sticker": detail["ev"]["box_sticker"], "box_net": detail["ev"]["box_net"],
               "median": detail["sim"]["net"]["median"], "beat_market": detail["sim"]["net"]["beat_market"],
               "verdict": detail["open_vs_hold"]["verdict"], "top10_share": detail.get("top10_share")} if detail["modeled"] else None,
        "chase_top": [{k: r.get(k) for k in ("id", "name", "price", "image", "zone", "zone_label", "low90", "boxes_per_hit", "url")}
                      for r in rows[:8]],
    }
    return detail, summary


def slot_printing(c, slots, bp):
    for s in slots:
        if c.get("bucket") in s["weights"]:
            return bp.get(c["bucket"]) if c["bucket"] in s.get("upgrades", []) else s["printing"]
    return None


def hero_summary(r: dict, sset: dict) -> dict:
    ser = r.get("series") or []
    spark = [v for _, v in ser][-60:]
    life = []
    if sset.get("release"):
        rel = dt.date.fromisoformat(sset["release"])
        life = [[(dt.date.fromisoformat(d) - rel).days, v] for d, v in ser if d >= sset["release"]]
    return {k: r.get(k) for k in ("id", "name", "kind", "kind_label", "market", "low", "msrp", "vs_msrp", "zone", "zone_label",
                                  "low90", "high90", "avg90", "pos90", "buy_cost", "change_7d", "change_30d", "annualized",
                                  "presale", "url", "image")} | {"spark": spark, "lifecycle": life}


def ways_to_buy(canon_rows: dict) -> list[dict]:
    """Cost per pack for each way of buying, cheapest first."""
    rows = [{"kind": k, "label": r["kind_label"], "packs": r["packs"], "buy_cost": r["buy_cost"], "per_pack": r["per_pack"],
             "id": r["id"], "url": r["url"]} for k, r in canon_rows.items() if r.get("per_pack")]
    rows.sort(key=lambda r: r["per_pack"])
    return rows


def ev_series(ctx, slots, buckets, selling, bp, ppb, box_row):
    out = []
    for d in sorted(ctx.hist):
        if d > ctx.today:
            continue
        hb = {k: with_prices(v, ctx.hist[d]) for k, v in buckets.items()}
        he = ev.expected(slots, ev.slot_values(slots, hb, selling, bp))
        bm = None
        if box_row:
            bm = history.market(ctx.hist[d].get(history.key(box_row["id"], "Normal")))
        out.append([d, round(he["sticker"] * ppb, 2), round(he["net"] * ppb, 2), bm])
    return out


def verdict(open_avg, open_typical, hold_net):
    if hold_net is None:
        return "No sealed box price yet."
    if open_avg >= hold_net and open_typical >= hold_net:
        return "Opening beats selling the box sealed, even for a typical box."
    if open_avg >= hold_net:
        return "Opening beats selling sealed on average, but a typical box comes up short. You need a big hit to come out ahead."
    return "Selling the box sealed beats opening it, even counting the big hits."


def hit_odds(slots, ppb, tmpl, mod) -> list[dict]:
    out = []
    for b in tmpl.get("hits", []):
        p = sum(s["count"] * s["weights"].get(b, 0) for s in slots)
        if not p:
            continue
        exp_box = p * ppb
        out.append({"bucket": b, "label": mod.LABELS.get(b, b), "per_pack": round(p, 5), "per_box": round(exp_box, 3),
                    "chance_in_box": round(1 - math.exp(-exp_box), 4), "boxes_per_hit": round(1 / exp_box, 1)})
    return out


# ---------------------------------------------------------------- per game

def movers(ctx: Ctx, set_names: dict) -> dict:
    rows = []
    for p in ctx.products.values():
        for sub, v in p["prices"].items():
            m = v.get("market")
            if not m or m < 2:
                continue
            rows.append({"id": p["id"], "name": p["name"], "printing": sub, "set": p["set"], "set_name": set_names.get(p["set"]),
                         "price": m, "d1": ctx.chg(p["id"], sub, m, 1), "d7": ctx.chg(p["id"], sub, m, 7),
                         "url": p["url"], "image": p["image"], "sealed": bool(p.get("sealed"))})

    def top(key, rev):
        r = [x for x in rows if x[key] is not None and x[key] != 0]
        return sorted(r, key=lambda x: x[key], reverse=rev)[:15]
    return {"up_1d": top("d1", True), "down_1d": top("d1", False), "up_7d": top("d7", True), "down_7d": top("d7", False),
            "has_1d": bool(ctx.prev[1]), "has_7d": bool(ctx.prev[7])}


def today_view(sets_summary, sealed_rows, details, today, unknown) -> dict:
    main = [r for r in sealed_rows if r["kind"] in ("box", "etb", "bundle", "case") and not r.get("presale") and r.get("market")]
    buys = [r for r in main if r["zone"] in ("good_low", "good_msrp")]
    buys.sort(key=lambda r: (r.get("vs_low90") if r.get("vs_low90") is not None else 0, r.get("vs_msrp") or 0))
    moves = sorted((r for r in main if r.get("change_7d")), key=lambda r: -abs(r["change_7d"]))
    chase = [c | {"set_name": d["name"], "set": d["code"]} for d in details for c in d["chase"]
             if c.get("zone") == "good_low" and (c.get("price") or 0) >= 20]
    chase.sort(key=lambda c: -(c["price"] or 0))
    open_value = sorted((s for s in sets_summary if s.get("ev") and s["ev"].get("beat_market") is not None),
                        key=lambda s: -s["ev"]["beat_market"])
    alerts = [{"type": "new_set", "text": f"New set spotted on TCGplayer: {u['name']}. Pack odds need adding before it gets a box value."} for u in unknown]
    for s in sets_summary:
        rel = s.get("release")
        if rel and rel > today and s.get("hero"):
            alerts.append({"type": "upcoming", "set": s["code"], "text": f"{s['name']} releases {rel}.",
                           "price": s["hero"].get("market") or s["hero"].get("low"), "msrp": s["hero"].get("msrp"),
                           "kind": s["hero"].get("kind_label")})
    slim = lambda r: {k: r.get(k) for k in ("id", "name", "set", "set_name", "kind_label", "market", "low90", "high90", "avg90",
                                            "vs_low90", "vs_msrp", "msrp", "zone", "zone_label", "change_7d", "image", "url", "buy_cost")}
    return {"buy_signals": [slim(r) for r in buys[:10]], "sealed_moves": [slim(r) for r in moves[:8]],
            "chase_near_low": [{k: c.get(k) for k in ("id", "name", "set", "set_name", "price", "low90", "high90", "image", "url", "boxes_per_hit")}
                               for c in chase[:10]],
            "open_value": [{"code": s["code"], "name": s["name"], **s["ev"], "box": (s.get("hero") or {}).get("market")} for s in open_value[:5]],
            "alerts": alerts}


def run_game(common, gcfg, raw, bench, out_dir: Path, do_backfill: bool) -> dict:
    mod = load_game(gcfg["module"])
    today = raw["fetched_at"][:10]
    products, sets, unknown = shape(raw, gcfg, mod)
    keep = keeper(gcfg, products, sets)
    hist_dir = HIST / gcfg["id"]
    if do_backfill:
        try:
            backfill.fill([{"id": gcfg["id"], "category": gcfg["category"], "start": gcfg["history_start"], "keep": keep}],
                          HIST, dt.date.fromisoformat(today) - dt.timedelta(days=1))
        except Exception as e:
            print("history backfill skipped:", e)
    history.write_snapshot(hist_dir, today, snapshot_of(products, keep))
    hist = history.load_all(hist_dir)
    ctx = Ctx(common, gcfg, mod, products, hist, history.series_index(hist), today, bench)

    details, summaries = [], []
    for s in sets:
        d, sm = analyze_set(ctx, s)
        details.append(d)
        summaries.append(sm)
    summaries.sort(key=lambda s: s.get("release") or "", reverse=True)
    sealed_rows = []
    for d in details:
        for r in d["sealed"]:
            sealed_rows.append({k: v for k, v in r.items() if k != "series"})
    set_names = {s["code"]: s["name"] for s in sets}
    odds_index = {c["id"]: c for d in details for c in d["cards"] if c.get("boxes_per_hit")}
    card_index = []
    floor = 0 if gcfg.get("history", "all") == "all" else 2
    for d in details:
        for c in d["cards"]:
            if (c["price"] or 0) >= floor:
                card_index.append({k: v for k, v in c.items() if k not in ("series",)} | {"set_name": d["name"]})
    summary = {"game": gcfg["id"], "name": gcfg["name"], "version": __version__,
               "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
               "price_date": today, "source_updated": raw.get("source_updated"), "history_days": len(hist),
               "group_by": gcfg.get("group_by", "year"), "selling": common["selling"], "buying": common["buying"],
               "zones": common["zones"], "benchmark_tax": common["benchmark"], "packs": gcfg["packs"],
               "sets": summaries, "sealed": sealed_rows, "movers": movers(ctx, set_names),
               "today": today_view(summaries, sealed_rows, details, today, unknown), "new_sets": unknown}
    gdir = out_dir / gcfg["id"]
    (gdir / "sets").mkdir(parents=True, exist_ok=True)
    for d in details:
        (gdir / "sets" / f"{safe(d['code'])}.json").write_text(json.dumps(d, separators=(",", ":")))
    (gdir / "summary.json").write_text(json.dumps(summary, separators=(",", ":")))
    (gdir / "cards.json").write_text(json.dumps(card_index, separators=(",", ":")))
    report(gcfg, summary, details, products, len(odds_index))
    return summary


def report(gcfg, summary, details, products, n_odds):
    print(f"\n##### {gcfg['name']}: prices for {summary['price_date']}, {summary['history_days']} days of history, "
          f"{len(summary['sets'])} sets, {len(summary['sealed'])} sealed products")
    for d in details:
        if not d["modeled"]:
            continue
        b = next((r for r in d["sealed"] if r["id"] == d["canonical"].get("box")), {})
        print(f"{d['name']} ({d['code']}): counts {d['card_counts']}")
        print(f"  box {b.get('market')} zone {b.get('zone')} 90d {b.get('low90')}-{b.get('high90')} buy {b.get('buy_cost')} | "
              f"EV {d['ev']['box_sticker']} net {d['ev']['box_net']} typical {d['sim']['net']['median']} "
              f"beat {d['sim']['net']['beat_market']} top10 {d.get('top10_share')}")
        print("  chase", [(c['name'], c['price'], c.get('boxes_per_hit'), c.get('pull_cost')) for c in d["chase"][:4]])
        print("  ways", [(w['label'], w['per_pack']) for w in d["ways_to_buy"]])
    print("today:", {k: len(v) for k, v in summary["today"].items()})
    unb = [p["name"] for p in products.values() if not p.get("sealed") and not p.get("bucket")]
    print(f"cards outside pack math: {len(unb)} e.g. {unb[:12]}")


def run(offline: bool = False, only: str | None = None, do_backfill: bool = True) -> dict:
    common, games = load_config()
    bench = {} if offline else market.fetch_benchmarks()
    OUT.mkdir(parents=True, exist_ok=True)
    out = {}
    index = []
    for g in games:
        if only and g["id"] != only:
            continue
        path = RAW / f"{g['id']}.json"
        if offline and path.exists():
            raw = json.loads(path.read_text())
        elif offline:
            continue
        else:
            raw = fetch_raw(g["category"])
            RAW.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(raw))
        out[g["id"]] = run_game(common, g, raw, bench, OUT, do_backfill and not offline)
    for g in games:
        f = OUT / g["id"] / "summary.json"
        if f.exists():
            s = json.loads(f.read_text())
            index.append({"id": g["id"], "name": g["name"], "price_date": s["price_date"], "sets": len(s["sets"]),
                          "group_by": s["group_by"]})
    (OUT / "games.json").write_text(json.dumps({"version": __version__, "games": index}, separators=(",", ":")))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--game")
    ap.add_argument("--no-backfill", action="store_true")
    a = ap.parse_args(argv)
    run(offline=a.offline, only=a.game, do_backfill=not a.no_backfill)


if __name__ == "__main__":
    sys.exit(main())
