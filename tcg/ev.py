"""Expected value of packs, boxes and cases, plus a simulation of opening many boxes."""
from __future__ import annotations

import copy
import hashlib

import numpy as np

SPECIALS = ("AltArt", "Overnumbered", "Signature", "Ultimate")


def price_of(card: dict, printing: str) -> float:
    """Market price of the printing a pack gives, falling back to the other printing, then the lowest listing."""
    pr = card.get("prices") or {}
    other = "Foil" if printing == "Normal" else "Normal"
    for sub in (printing, other):
        v = (pr.get(sub) or {}).get("market")
        if v:
            return float(v)
    for sub in (printing, other):
        v = (pr.get(sub) or {}).get("low")
        if v:
            return float(v)
    return 0.0


def net_value(price: float, selling: dict) -> float:
    """What you'd actually pocket: after TCGplayer fees and shipping supplies, or bulk value if it isn't worth listing."""
    bulk = selling["bulk_value"]
    if price < selling["sell_threshold"]:
        return min(price, bulk) if price > 0 else 0.0
    return max(bulk, price * (1 - selling["fee_pct"]) - selling["per_card_cost"])


def merged_pack(default_pack: dict, set_cfg: dict) -> dict:
    pack = copy.deepcopy(default_pack)
    for k, v in (set_cfg.get("pack") or {}).items():
        pack[k] = v
    if set_cfg.get("rare_printing"):
        for s in pack["slots"]:
            if s["name"].startswith("Rare"):
                s["printing"] = set_cfg["rare_printing"]
    for k, v in (set_cfg.get("specials") or {}).items():
        pack["specials"].setdefault(k, {}).update(v)
    return pack


def build_slots(pack: dict, bucket_sizes: dict[str, int]) -> list[dict]:
    """Final slot list: each slot has count, printing and bucket weights that sum to 1.

    Specials (alt art, overnumbered, signature, ultimate) replace the foil-slot card.
    Riot's overnumbered rate includes signatures, so the plain overnumbered share is the difference.
    A bucket with no cards in this set gives its share back to the rest of its slot.
    """
    sp = {k: float(v.get("per_pack", 0)) for k, v in pack["specials"].items() if not k.startswith("_")}
    if "Overnumbered" in sp and "Signature" in sp:
        sp["Overnumbered"] = max(0.0, sp["Overnumbered"] - sp["Signature"])
    slots = []
    for s in pack["slots"]:
        w = dict(s["weights"])
        printing = s.get("printing", "Normal")
        if s["name"] == "Foil":
            special_total = sum(p for k, p in sp.items() if bucket_sizes.get(k))
            w = {k: v * (1 - special_total) for k, v in w.items()}
            for k, p in sp.items():
                if bucket_sizes.get(k):
                    w[k] = p
        w = {k: v for k, v in w.items() if v > 0 and bucket_sizes.get(k)}
        tot = sum(w.values())
        if tot <= 0:
            continue
        slots.append({"name": s["name"], "count": int(s["count"]), "printing": printing,
                      "weights": {k: v / tot for k, v in w.items()}})
    return slots


def slot_values(slots, buckets, selling):
    """Per slot and bucket: arrays of sticker and net value for each card in the bucket."""
    out = []
    for s in slots:
        vals = {}
        for b in s["weights"]:
            pr = "Foil" if b in SPECIALS else s["printing"]
            sticker = np.array([price_of(c, pr) for c in buckets[b]], dtype=float)
            net = np.array([net_value(x, selling) for x in sticker], dtype=float)
            vals[b] = (sticker, net)
        out.append(vals)
    return out


def expected(slots, values) -> dict:
    """Average value per pack, and how much each bucket contributes."""
    contrib_s, contrib_n = {}, {}
    for s, vals in zip(slots, values):
        for b, w in s["weights"].items():
            st, nt = vals[b]
            contrib_s[b] = contrib_s.get(b, 0.0) + s["count"] * w * float(st.mean())
            contrib_n[b] = contrib_n.get(b, 0.0) + s["count"] * w * float(nt.mean())
    return {"sticker": sum(contrib_s.values()), "net": sum(contrib_n.values()),
            "by_bucket_sticker": contrib_s, "by_bucket_net": contrib_n}


def card_odds_per_pack(slots, buckets) -> dict[int, float]:
    """Chance a given card shows up in one pack (any slot)."""
    odds: dict[int, float] = {}
    for s in slots:
        for b, w in s["weights"].items():
            n = len(buckets[b])
            for c in buckets[b]:
                odds[c["id"]] = odds.get(c["id"], 0.0) + s["count"] * w / n
    return odds


def per_box(p_pack: float, packs: int) -> float:
    return 1 - (1 - min(p_pack, 1.0)) ** packs


def simulate(slots, values, packs_per_box: int, boxes: int = 10000, seed: str = "x") -> dict:
    """Open `boxes` virtual boxes. Returns the sticker and net value of each box."""
    rng = np.random.default_rng(int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16))
    sticker = np.zeros(boxes)
    net = np.zeros(boxes)
    for s, vals in zip(slots, values):
        keys = list(s["weights"])
        probs = np.array([s["weights"][k] for k in keys])
        probs = probs / probs.sum()
        n = packs_per_box * s["count"]
        choice = rng.choice(len(keys), size=(boxes, n), p=probs)
        for i, k in enumerate(keys):
            st, nt = vals[k]
            mask = choice == i
            cnt = int(mask.sum())
            if not cnt:
                continue
            idx = rng.integers(0, len(st), size=cnt)
            box_idx = np.nonzero(mask)[0]
            np.add.at(sticker, box_idx, st[idx])
            np.add.at(net, box_idx, nt[idx])
    return {"sticker": sticker, "net": net}


def summarize_sim(sim: dict, box_market: float | None, msrp: float | None) -> dict:
    qs = np.linspace(0, 100, 201)
    out = {"boxes": int(len(sim["net"]))}
    for k in ("sticker", "net"):
        a = sim[k]
        out[k] = {
            "mean": round(float(a.mean()), 2),
            "median": round(float(np.median(a)), 2),
            "p10": round(float(np.percentile(a, 10)), 2),
            "p25": round(float(np.percentile(a, 25)), 2),
            "p75": round(float(np.percentile(a, 75)), 2),
            "p90": round(float(np.percentile(a, 90)), 2),
            "p99": round(float(np.percentile(a, 99)), 2),
            "quantiles": [round(float(x), 2) for x in np.percentile(a, qs)],
            "beat_market": round(float((a >= box_market).mean()), 4) if box_market else None,
            "beat_msrp": round(float((a >= msrp).mean()), 4) if msrp else None,
        }
    return out
