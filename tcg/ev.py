"""Expected value of packs, boxes and cases, plus a simulation of opening many boxes.

A pack template is a list of slots. Each slot has a count, a printing and bucket weights. A slot
with `upgrades` can be replaced, at the stated per-pack chance, by a rarer card (alternate art,
Special Illustration Rare...). A bucket with no cards in a set gives its share back to the slot.
"""
from __future__ import annotations

import hashlib

import numpy as np


def price_sub(card: dict, printing: str | None) -> tuple[float, str | None]:
    """Market price of a printing, falling back to another printing, then to the cheapest listing."""
    pr = card.get("prices") or {}
    order = ([printing] if printing in pr else []) + sorted((s for s in pr if s != printing), key=lambda s: -(pr[s].get("market") or 0))
    for sub in order:
        v = (pr.get(sub) or {}).get("market")
        if v:
            return float(v), sub
    for sub in order:
        v = (pr.get(sub) or {}).get("low")
        if v:
            return float(v), sub
    return 0.0, None


def price_of(card: dict, printing: str | None) -> float:
    return price_sub(card, printing)[0]


def net_value(price: float, selling: dict) -> float:
    """What you'd actually pocket: after fees and shipping supplies, or bulk value if it isn't worth listing."""
    bulk = selling["bulk_value"]
    if price < selling["sell_threshold"]:
        return min(price, bulk) if price > 0 else 0.0
    return max(bulk, price * (1 - selling["fee_pct"]) - selling["per_card_cost"])


def build_slots(template: dict, bucket_sizes: dict[str, int], printing_overrides: dict | None = None) -> list[dict]:
    slots = []
    for s in template["slots"]:
        ups = {k: float(v) for k, v in (s.get("upgrades") or {}).items() if bucket_sizes.get(k)}
        up_total = sum(ups.values())
        w = {k: v * (1 - up_total) for k, v in s["weights"].items() if v > 0 and bucket_sizes.get(k)}
        base_tot = sum(w.values())
        if base_tot <= 0 and not ups:
            continue
        if base_tot > 0:  # rescale the base cards so the slot still sums to one
            w = {k: v / base_tot * (1 - up_total) for k, v in w.items()}
        w.update(ups)
        tot = sum(w.values())
        printing = (printing_overrides or {}).get(s["name"], s.get("printing", "Normal"))
        slots.append({"name": s["name"], "count": int(s["count"]), "printing": printing,
                      "weights": {k: v / tot for k, v in w.items()}, "upgrades": list(ups)})
    return slots


def slot_values(slots, buckets, selling, bucket_printing=None):
    """Per slot and bucket: arrays of sticker and net value for each card in the bucket."""
    out = []
    for s in slots:
        vals = {}
        for b in s["weights"]:
            pr = (bucket_printing or {}).get(b) if b in s.get("upgrades", []) else s["printing"]
            sticker = np.array([price_of(c, pr or s["printing"]) for c in buckets[b]], dtype=float)
            net = np.array([net_value(x, selling) for x in sticker], dtype=float)
            vals[b] = (sticker, net)
        out.append(vals)
    return out


def expected(slots, values) -> dict:
    contrib_s, contrib_n = {}, {}
    for s, vals in zip(slots, values):
        for b, w in s["weights"].items():
            st, nt = vals[b]
            contrib_s[b] = contrib_s.get(b, 0.0) + s["count"] * w * float(st.mean())
            contrib_n[b] = contrib_n.get(b, 0.0) + s["count"] * w * float(nt.mean())
    return {"sticker": sum(contrib_s.values()), "net": sum(contrib_n.values()),
            "by_bucket_sticker": contrib_s, "by_bucket_net": contrib_n}


def card_odds_per_pack(slots, buckets) -> dict[int, float]:
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
    rng = np.random.default_rng(int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16))
    sticker = np.zeros(boxes)
    net = np.zeros(boxes)
    for s, vals in zip(slots, values):
        keys = list(s["weights"])
        probs = np.array([s["weights"][k] for k in keys])
        probs = probs / probs.sum()
        choice = rng.choice(len(keys), size=(boxes, packs_per_box * s["count"]), p=probs)
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
            "mean": round(float(a.mean()), 2), "median": round(float(np.median(a)), 2),
            "p10": round(float(np.percentile(a, 10)), 2), "p25": round(float(np.percentile(a, 25)), 2),
            "p75": round(float(np.percentile(a, 75)), 2), "p90": round(float(np.percentile(a, 90)), 2),
            "p99": round(float(np.percentile(a, 99)), 2),
            "quantiles": [round(float(x), 2) for x in np.percentile(a, qs)],
            "beat_market": round(float((a >= box_market).mean()), 4) if box_market else None,
            "beat_msrp": round(float((a >= msrp).mean()), 4) if msrp else None,
        }
    return out
