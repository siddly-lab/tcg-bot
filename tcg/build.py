"""Daily build: pull Riftbound prices, run the box math, write the dashboard's data files.

Run:  python -m tcg.build            (live data)
      python -m tcg.build --offline  (reuse the cached raw pull in data/raw.json)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path

from . import __version__, classify, ev, history, tcgcsv

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "sets.json"
HIST = ROOT / "data" / "history"
RAW = ROOT / "data" / "raw.json"
OUT = ROOT / "site" / "data"


# ---------------------------------------------------------------- fetching

def fetch_raw() -> dict:
    cat = tcgcsv.find_category()
    groups = tcgcsv.groups(cat)
    out = {"category": cat, "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "source_updated": tcgcsv.last_updated(), "groups": []}
    for g in groups:
        gid = g["groupId"]
        out["groups"].append({"group": g, "products": tcgcsv.products(cat, gid), "prices": tcgcsv.prices(cat, gid)})
    return out


# ---------------------------------------------------------------- shaping

def match_set(group_name: str, sets: list[dict]) -> dict | None:
    n = group_name.strip().lower()
    for s in sets:
        if n in [m.lower() for m in s["match"]] or n == s["name"].lower():
            return s
    return None


def shape(raw: dict, cfg: dict) -> tuple[dict[int, dict], list[dict]]:
    """Every product with its prices, bucket and set; plus groups that look like new sets we don't know yet."""
    products: dict[int, dict] = {}
    unknown = []
    for g in raw["groups"]:
        grp = g["group"]
        sset = match_set(grp["name"], cfg["sets"])
        prices: dict[int, dict] = {}
        for p in g["prices"]:
            prices.setdefault(p["productId"], {})[p.get("subTypeName") or "Normal"] = {
                "market": p.get("marketPrice"), "low": p.get("lowPrice"), "mid": p.get("midPrice"),
                "high": p.get("highPrice")}
        has_display = False
        for p in g["products"]:
            rarity = classify.ext(p, "Rarity")
            is_sealed = rarity is None and classify.ext(p, "Number") is None and not (p.get("extendedData"))
            rec = {
                "id": p["productId"], "name": classify.clean_name(p["name"]), "group": grp["name"],
                "group_id": grp["groupId"], "set": sset["code"] if sset else None,
                "number": classify.ext(p, "Number"), "rarity": rarity, "url": p.get("url"),
                "image": p.get("imageUrl") if p.get("imageCount", 1) else None,
                "prices": prices.get(p["productId"], {}),
                "presale": bool((p.get("presaleInfo") or {}).get("isPresale")),
            }
            if is_sealed:
                rec["sealed"] = classify.sealed_type(p["name"])
                has_display = has_display or rec["sealed"] == "box"
            else:
                rec["bucket"] = classify.classify_card(p)
            products[rec["id"]] = rec
        if not sset and has_display:
            unknown.append({"name": grp["name"], "published": grp.get("publishedOn")})
    fill_missing_images(products)
    return products, unknown


def fill_missing_images(products: dict[int, dict]) -> None:
    """TCGplayer often has no photo for Signature and some Overnumbered cards yet.

    Borrow the picture of the same card in the same set: first the version with the same
    collector number (a Signature 173*/167 uses the Overnumbered 173/167 art), then any version
    with the same name. Marked so the page can say it's a stand-in.
    """
    by_number, by_name = {}, {}
    for p in products.values():
        if not p.get("image") or not p.get("set"):
            continue
        if p.get("number"):
            by_number.setdefault((p["set"], p["number"].replace("*", "")), p["image"])
        by_name.setdefault((p["set"], base_name(p["name"])), p["image"])
    for p in products.values():
        if p.get("image") or p.get("sealed") or not p.get("set"):
            continue
        img = by_number.get((p["set"], (p.get("number") or "").replace("*", ""))) or by_name.get((p["set"], base_name(p["name"])))
        if img:
            p["image"] = img
            p["image_standin"] = True


def base_name(name: str) -> str:
    """'Riven, The Exile (Signature)' -> 'Riven, The Exile'."""
    import re
    return re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()


def snapshot_of(products: dict[int, dict]) -> dict[str, list]:
    snap = {}
    for p in products.values():
        for sub, v in p["prices"].items():
            if v.get("market") is not None or v.get("low") is not None:
                snap[history.key(p["id"], sub)] = [v.get("market"), v.get("low")]
    return snap


def with_prices(cards: list[dict], snap: dict) -> list[dict]:
    """Copy of cards with prices taken from a historic snapshot."""
    out = []
    for c in cards:
        pr = {}
        for sub in ("Normal", "Foil"):
            e = snap.get(history.key(c["id"], sub))
            if e:
                pr[sub] = {"market": e[0], "low": e[1]}
        out.append({**c, "prices": pr})
    return out


def thin_market(p: dict) -> bool:
    """No recent sale price, or the cheapest listing is far from the sale price: the price is less reliable."""
    for v in p["prices"].values():
        m, low = v.get("market"), v.get("low")
        if m and low:
            r = low / m
            if 0.6 <= r <= 1.6:
                return False
    return True


# ---------------------------------------------------------------- per set

def best_market(p: dict | None) -> float | None:
    if not p:
        return None
    vals = [v.get("market") for v in p["prices"].values() if v.get("market")]
    if vals:
        return max(vals)
    lows = [v.get("low") for v in p["prices"].values() if v.get("low")]
    return min(lows) if lows else None


def best_low(p: dict | None) -> float | None:
    if not p:
        return None
    lows = [v.get("low") for v in p["prices"].values() if v.get("low")]
    return min(lows) if lows else None


def sealed_of(products, code, kind):
    cands = [p for p in products.values() if p["set"] == code and p.get("sealed") == kind]
    return cands[0] if cands else None


def analyze_set(scfg, cfg, products, hist, today) -> dict:
    code = scfg["code"]
    selling = cfg["selling"]
    pack = ev.merged_pack(cfg["default_pack"], scfg)
    ppb, bpc = pack["packs_per_box"], pack["boxes_per_case"]
    cards = [p for p in products.values() if p["set"] == code and p.get("bucket")]
    buckets: dict[str, list] = {}
    for c in cards:
        buckets.setdefault(c["bucket"], []).append(c)
    sizes = {k: len(v) for k, v in buckets.items()}

    box = sealed_of(products, code, "box")
    case = sealed_of(products, code, "case")
    pk = sealed_of(products, code, "pack")
    box_market, box_low = best_market(box), best_low(box)
    msrp = scfg.get("msrp_box")
    release = scfg.get("release")
    released = bool(release) and release <= today

    res = {
        "code": code, "name": scfg["name"], "release": release, "released": released,
        "msrp_box": msrp, "msrp_pack": scfg.get("msrp_pack"), "msrp_case": round(msrp * bpc, 2) if msrp else None,
        "packs_per_box": ppb, "boxes_per_case": bpc,
        "box": sealed_summary(box, hist, today, msrp, release, selling) if box else None,
        "case": sealed_summary(case, hist, today, msrp * bpc if msrp else None, release, selling) if case else None,
        "pack": sealed_summary(pk, hist, today, scfg.get("msrp_pack"), release, selling) if pk else None,
        "card_counts": {classify.LABELS.get(k, k): v for k, v in sorted(sizes.items(), key=lambda kv: classify.PACK_BUCKETS.index(kv[0]) if kv[0] in classify.PACK_BUCKETS else 99)},
        "odds": odds_table(pack, sizes),
    }
    pack_buckets = {k: v for k, v in buckets.items() if k in classify.PACK_BUCKETS}
    if not pack_buckets.get("Common"):
        res["ev"] = None
        res["note"] = "Card list not published yet, so there is nothing to price. Sealed prices are pre-orders."
        return res

    slots = ev.build_slots(pack, {k: len(v) for k, v in pack_buckets.items()})
    vals = ev.slot_values(slots, pack_buckets, selling)
    e = ev.expected(slots, vals)
    sim = ev.simulate(slots, vals, ppb, boxes=10000, seed=f"{code}-{today}")
    simsum = ev.summarize_sim(sim, box_market, msrp)
    box_sticker, box_net = e["sticker"] * ppb, e["net"] * ppb
    res["ev"] = {
        "pack_sticker": round(e["sticker"], 2), "pack_net": round(e["net"], 2),
        "box_sticker": round(box_sticker, 2), "box_net": round(box_net, 2),
        "case_sticker": round(box_sticker * bpc, 2), "case_net": round(box_net * bpc, 2),
    }
    res["contrib"] = sorted([
        {"bucket": b, "label": classify.LABELS.get(b, b),
         "box_sticker": round(e["by_bucket_sticker"][b] * ppb, 2),
         "box_net": round(e["by_bucket_net"][b] * ppb, 2),
         "share": round(e["by_bucket_sticker"][b] / e["sticker"], 4) if e["sticker"] else 0}
        for b in e["by_bucket_sticker"]], key=lambda x: -x["box_sticker"])
    res["sim"] = simsum
    res["roi"] = {
        "open_vs_market": roi(box_sticker, box_market), "open_net_vs_market": roi(box_net, box_market),
        "open_vs_msrp": roi(box_sticker, msrp), "open_net_vs_msrp": roi(box_net, msrp),
    }
    hold_net = box_market * (1 - selling["sealed_fee_pct"]) - selling["sealed_ship_cost"] if box_market else None
    res["open_vs_hold"] = {
        "open_net_avg": round(box_net, 2), "open_net_typical": simsum["net"]["median"],
        "sell_sealed_net": round(hold_net, 2) if hold_net else None,
        "verdict": verdict(box_net, simsum["net"]["median"], hold_net),
    }
    # chase cards
    odds = ev.card_odds_per_pack(slots, pack_buckets)
    chase = []
    for c in cards:
        if c["bucket"] not in pack_buckets:
            continue
        pr = "Foil" if c["bucket"] in ev.SPECIALS or c["bucket"] in ("Rare", "Epic") and scfg.get("rare_printing") == "Foil" else "Normal"
        price = ev.price_of(c, pr)
        pb = ev.per_box(odds.get(c["id"], 0), ppb)
        chase.append({"id": c["id"], "name": c["name"], "number": c["number"], "bucket": c["bucket"],
                      "label": classify.LABELS.get(c["bucket"]), "price": round(price, 2),
                      "per_box": round(pb, 5), "boxes_per_hit": round(1 / pb, 1) if pb else None,
                      "url": c["url"], "image": c["image"], "standin": bool(c.get("image_standin")),
                      "thin": thin_market(c)})
    chase.sort(key=lambda x: -x["price"])
    res["chase"] = chase[:20]
    res["hit_odds"] = hit_odds(slots, ppb)
    # value history: re-price the same pack model at each saved day's prices
    series = []
    for d in sorted(hist):
        if d > today:
            continue
        hb = {k: with_prices(v, hist[d]) for k, v in pack_buckets.items()}
        hv = ev.slot_values(slots, hb, selling)
        he = ev.expected(slots, hv)
        bm = history.market(hist[d].get(history.key(box["id"], "Normal"))) if box else None
        series.append([d, round(he["sticker"] * ppb, 2), round(he["net"] * ppb, 2), bm])
    res["ev_series"] = series
    res["_odds_per_pack"] = odds
    return res


def roi(value, cost):
    if not cost or value is None:
        return None
    return round(value / cost - 1, 4)


def verdict(open_avg, open_typical, hold_net):
    if hold_net is None:
        return "No sealed box price yet."
    if open_avg >= hold_net and open_typical >= hold_net:
        return "Opening beats selling the box sealed, even for a typical box."
    if open_avg >= hold_net:
        return "Opening beats selling sealed on average, but a typical box comes up short. You need a big hit to come out ahead."
    return "Selling the box sealed beats opening it, even counting the big hits."


def hit_odds(slots, ppb) -> list[dict]:
    out = []
    for b in ("Epic", "AltArt", "Overnumbered", "Signature", "Ultimate"):
        p = sum(s["count"] * s["weights"].get(b, 0) for s in slots)
        if not p:
            continue
        exp_box = p * ppb
        out.append({"bucket": b, "label": classify.LABELS[b], "per_pack": round(p, 5),
                    "per_box": round(exp_box, 3), "chance_in_box": round(1 - math.exp(-exp_box), 4),
                    "boxes_per_hit": round(1 / exp_box, 1)})
    return out


def odds_table(pack, sizes) -> list[dict]:
    rows = [{"what": "Epic", "rate": pack.get("epic_note"), "source": pack.get("epic_source", "assumed")}]
    for k, v in pack["specials"].items():
        if k.startswith("_"):
            continue
        rows.append({"what": classify.LABELS.get(k, k), "rate": v.get("note"), "source": v.get("source", "assumed"),
                     "in_set": bool(sizes.get(k))})
    rows.append({"what": "Foil slot rarity split", "rate": "55% common, 30% uncommon, 12% rare, 3% epic",
                 "source": pack.get("foil_split_source", "assumed")})
    return rows


def sealed_summary(p, hist, today, msrp, release, selling) -> dict:
    m = best_market(p)
    low = best_low(p)
    series = []
    for d in sorted(hist):
        v = history.market(hist[d].get(history.key(p["id"], "Normal")))
        if v:
            series.append([d, v])
    d7 = history.market((history.on_or_before(hist, today, 7) or {}).get(history.key(p["id"], "Normal")))
    d30 = history.market((history.on_or_before(hist, today, 30) or {}).get(history.key(p["id"], "Normal")))
    out = {"id": p["id"], "name": p["name"], "url": p["url"], "image": p["image"], "market": m, "low": low,
           "presale": p.get("presale"), "msrp": msrp, "vs_msrp": roi(m, msrp),
           "change_7d": history.pct(m, d7), "change_30d": history.pct(m, d30), "series": series,
           "thin": thin_market(p)}
    if release and m and msrp:
        days = (dt.date.fromisoformat(today) - dt.date.fromisoformat(release)).days
        out["days_since_release"] = days
        out["annualized"] = round((m / msrp) ** (365 / days) - 1, 4) if days >= 90 else None
        net = m * (1 - selling["sealed_fee_pct"]) - selling["sealed_ship_cost"]
        out["net_if_sold"] = round(net, 2)
        out["net_profit_vs_msrp"] = round(net - msrp, 2)
    return out


# ---------------------------------------------------------------- outputs

def movers(products, hist, today) -> dict:
    prev1 = history.on_or_before(hist, today, 1)
    prev7 = history.on_or_before(hist, today, 7)
    rows = []
    for p in products.values():
        for sub, v in p["prices"].items():
            m = v.get("market")
            if not m or m < 2:
                continue
            k = history.key(p["id"], sub)
            o1 = history.market((prev1 or {}).get(k))
            o7 = history.market((prev7 or {}).get(k))
            rows.append({"id": p["id"], "name": p["name"], "printing": sub, "set": p["set"] or p["group"],
                         "price": m, "d1": history.pct(m, o1), "d7": history.pct(m, o7),
                         "url": p["url"], "image": p["image"], "sealed": bool(p.get("sealed"))})
    def top(key, rev):
        r = [x for x in rows if x[key] is not None and x[key] != 0]
        return sorted(r, key=lambda x: x[key], reverse=rev)[:15]
    return {"up_1d": top("d1", True), "down_1d": top("d1", False), "up_7d": top("d7", True), "down_7d": top("d7", False),
            "has_1d": prev1 is not None, "has_7d": prev7 is not None}


def card_rows(products, sets_res, hist, today) -> list[dict]:
    odds = {}
    ppb = {}
    for s in sets_res:
        for pid, p in (s.get("_odds_per_pack") or {}).items():
            odds[pid] = p
            ppb[pid] = s["packs_per_box"]
    prev7 = history.on_or_before(hist, today, 7) or {}
    prev30 = history.on_or_before(hist, today, 30) or {}
    out = []
    for p in products.values():
        if p.get("sealed") or not p.get("set"):
            continue
        if not p.get("bucket") and p.get("rarity") not in ("Promo",):
            continue
        row = {"id": p["id"], "set": p["set"], "name": p["name"], "number": p["number"], "rarity": p["rarity"],
               "kind": classify.LABELS.get(p.get("bucket"), p.get("rarity") or ""), "url": p["url"], "image": p["image"],
               "standin": bool(p.get("image_standin")), "thin": thin_market(p)}
        for sub, tag in (("Normal", "normal"), ("Foil", "foil")):
            v = p["prices"].get(sub)
            if v:
                m = v.get("market")
                row[tag] = {"market": m, "low": v.get("low"),
                            "d7": history.pct(m, history.market(prev7.get(history.key(p["id"], sub)))),
                            "d30": history.pct(m, history.market(prev30.get(history.key(p["id"], sub))))}
        if p["id"] in odds:
            pb = ev.per_box(odds[p["id"]], ppb[p["id"]])
            row["per_box"] = round(pb, 5)
            row["boxes_per_hit"] = round(1 / pb, 1) if pb else None
        out.append(row)
    out.sort(key=lambda r: (r["set"], r["name"]))
    return out


def sealed_rows(products, cfg, hist, today) -> list[dict]:
    rel = {s["code"]: s for s in cfg["sets"]}
    out = []
    for p in products.values():
        if not p.get("sealed"):
            continue
        s = rel.get(p["set"]) or {}
        kind = p["sealed"]
        msrp = {"box": s.get("msrp_box"), "pack": s.get("msrp_pack"),
                "case": (s.get("msrp_box") or 0) * cfg["default_pack"]["boxes_per_case"] or None}.get(kind)
        summ = sealed_summary(p, hist, today, msrp, s.get("release"), cfg["selling"])
        summ.update({"set": p["set"], "group": p["group"], "kind": kind, "kind_label": classify.SEALED_LABELS[kind]})
        out.append(summ)
    order = {"box": 0, "case": 1, "pack": 2, "sleeved_pack": 3, "other": 4}
    out.sort(key=lambda r: (order[r["kind"]], r["group"], r["name"]))
    return out


def run(offline: bool = False) -> dict:
    cfg = json.loads(CONFIG.read_text())
    if offline and RAW.exists():
        raw = json.loads(RAW.read_text())
    else:
        raw = fetch_raw()
        RAW.parent.mkdir(parents=True, exist_ok=True)
        RAW.write_text(json.dumps(raw))
    today = raw["fetched_at"][:10]
    products, unknown = shape(raw, cfg)
    history.write_snapshot(HIST, today, snapshot_of(products))
    hist = history.load_all(HIST)

    sets_res = [analyze_set(s, cfg, products, hist, today) for s in cfg["sets"]
                if any(p["set"] == s["code"] for p in products.values())]
    cards = card_rows(products, sets_res, hist, today)
    for s in sets_res:
        s.pop("_odds_per_pack", None)
    latest = {
        "version": __version__, "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "price_date": today, "source_updated": raw.get("source_updated"), "history_days": len(hist),
        "selling": cfg["selling"], "sets": sets_res, "new_sets": unknown,
        "sealed": sealed_rows(products, cfg, hist, today), "movers": movers(products, hist, today),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "latest.json").write_text(json.dumps(latest, separators=(",", ":")))
    (OUT / "cards.json").write_text(json.dumps(cards, separators=(",", ":")))
    report(latest, products)
    return latest


def report(latest, products):
    """Plain summary in the build log, so a bad parse is easy to spot."""
    print(f"tcg-bot {latest['version']} prices for {latest['price_date']} ({latest['history_days']} days of history)")
    for s in latest["sets"]:
        print(f"\n{s['name']} ({s['code']}): counts {s['card_counts']}")
        b = s.get("box") or {}
        print(f"  box market {b.get('market')} low {b.get('low')} msrp {s['msrp_box']}")
        if s.get("ev"):
            e, sim = s["ev"], s["sim"]
            print(f"  EV box sticker {e['box_sticker']} net {e['box_net']}  typical(net) {sim['net']['median']}"
                  f"  beat market(net) {sim['net']['beat_market']}  verdict: {s['open_vs_hold']['verdict']}")
            print("  contrib", [(c['label'], c['box_sticker']) for c in s["contrib"]])
            print("  chase", [(c['name'], c['price'], c['boxes_per_hit']) for c in s["chase"][:5]])
        else:
            print("  ", s.get("note"))
    unb = [p["name"] for p in products.values() if p.get("set") and not p.get("sealed") and not p.get("bucket")]
    print(f"\nCards left out of pack math ({len(unb)}): {unb[:30]}")
    print("New sets not in config:", latest["new_sets"])
    cards = [p for p in products.values() if p.get("set") and not p.get("sealed")]
    print(f"Card images: {sum(1 for p in cards if p.get('image_standin'))} borrowed from another version, "
          f"{sum(1 for p in cards if not p.get('image'))} still missing: {[p['name'] for p in cards if not p.get('image')][:15]}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args(argv)
    run(offline=a.offline)


if __name__ == "__main__":
    sys.exit(main())
