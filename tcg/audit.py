"""Audit: checks that cards are tied to the right sets and buckets, and that prices feeding the box math are sane.

    python -m tcg.audit            (after a build; reads the raw pulls in data/raw/)
"""
from __future__ import annotations

import collections
import json
import re
import statistics
import sys

from . import build, ev
from .games import load as load_game

CODE_TAG = re.compile(r"^(\d{3}[a-z]?|[A-Z]{1,5}\d{0,2}-\d{3}|R\d+[ab]?|T\d+|SP\d+/\d+)$")


def tags(name):
    return [t.strip() for t in re.findall(r"\(([^)]*)\)", name) if not CODE_TAG.match(t.strip())]


def denominators(cards):
    out = collections.Counter()
    for c in cards:
        m = re.match(r"^[A-Za-z]*\d+[a-z*]?/(\d+)$", (c.get("number") or "").strip())
        if m:
            out[m.group(1)] += 1
    return out


def audit_game(common, gcfg, raw):
    mod = load_game(gcfg["module"])
    products, sets, _ = build.shape(raw, gcfg, mod)
    today = raw["fetched_at"][:10]
    print(f"\n################ {gcfg['name']} ({len(sets)} sets)")
    issues = collections.Counter()
    for s in sets:
        if not s.get("modeled") or (s.get("release") or "9999") > today:
            continue
        tmpl = gcfg["templates"][s["template"]]
        cards = [p for p in products.values() if p["set"] == s["code"] and not p.get("sealed")]
        sealed = [p for p in products.values() if p["set"] == s["code"] and p.get("sealed")]
        inpack = [c for c in cards if c.get("bucket") in mod.PACK_BUCKETS]
        print(f"\n=== {s['name']} ({s['code']}) cards={len(cards)} in-pack={len(inpack)}")
        # 1. labels inside names, by bucket (unknown labels in counted buckets are the One Piece-style risk)
        bt = collections.defaultdict(collections.Counter)
        for c in inpack:
            for t in tags(c["name"]):
                bt[c["bucket"]][t] += 1
        for b, cnt in bt.items():
            print(f"  labels in {b}: {dict(cnt.most_common(8))}")
        # 2. card numbers that don't match the set's numbering
        den = denominators(inpack)
        if den:
            main, n = den.most_common(1)[0]
            odd = [c for c in inpack if re.match(r".*/(\d+)$", c.get("number") or "") and not (c["number"] or "").endswith("/" + main)]
            if odd:
                issues["numbering"] += len(odd)
                print(f"  numbering: set uses /{main}; {len(odd)} counted cards differ: {[(c['name'], c['number'], c['bucket']) for c in odd[:6]]}")
        if gcfg["id"] == "onepiece":
            pre = s["code"][:4]
            odd = [c for c in inpack if not (c.get("number") or "").startswith(pre)]
            kinds = collections.Counter(c["bucket"] for c in odd)
            if odd:
                print(f"  numbering: {len(odd)} counted cards carry another set's number, by bucket {dict(kinds)}")
                if set(kinds) - {"SP"}:
                    issues["numbering"] += sum(v for k, v in kinds.items() if k != "SP")
        # 3. prices
        for b in sorted({c["bucket"] for c in inpack}):
            cs = [c for c in inpack if c["bucket"] == b]
            vals = [ev.price_of(c, None) for c in cs]
            nomkt = [c["name"] for c in cs if not any((v or {}).get("market") for v in c["prices"].values())]
            noprice = [c["name"] for c in cs if not vals[cs.index(c)]]
            med = statistics.median(vals) if vals else 0
            outl = [(c["name"], round(v, 2)) for c, v in zip(cs, vals) if med and v > 15 * med and v > 20]
            ph = [(c["name"], round(v, 2)) for c, v in zip(cs, vals) if v >= 9999]
            if noprice or ph or (outl and b in ("Common", "Uncommon", "Rare", "C", "UC", "R", "L")):
                issues["prices"] += len(noprice) + len(ph) + len(outl)
            print(f"  {b}: n={len(cs)} median=${med:.2f} no-sale-price={len(nomkt)} no-price={len(noprice)}"
                  + (f" OUTLIERS {outl[:4]}" if outl else "") + (f" PLACEHOLDER {ph}" if ph else ""))
        # 4. what drives the box value
        buckets = collections.defaultdict(list)
        for c in inpack:
            buckets[c["bucket"]].append(c)
        slots = ev.build_slots(tmpl, {k: len(v) for k, v in buckets.items()})
        bp = getattr(mod, "BUCKET_PRINTING", {})
        buckets, _ = build.ev_ready(buckets, slots, bp)
        inpack = [c for v in buckets.values() for c in v]
        vals = ev.slot_values(slots, buckets, common["selling"], bp)
        e = ev.expected(slots, vals)
        odds = ev.card_odds_per_pack(slots, buckets)
        ppb = tmpl["packs_per_box"]
        contrib = sorted(((odds[c["id"]] * ppb * ev.price_of(c, build.slot_printing(c, slots, bp)), c) for c in inpack), key=lambda x: -x[0])
        tot = e["sticker"] * ppb
        top = [(c["name"], round(v, 2), f"{v / tot:.0%}") for v, c in contrib[:5]]
        print(f"  box EV ${tot:.2f}; top cards {top}")
        if contrib and contrib[0][0] / tot > 0.2:
            issues["concentration"] += 1
        # 5. sealed products: is the box the right one?
        kinds = collections.defaultdict(list)
        for p in sealed:
            kinds[p["sealed"]].append((p["name"], build.best(p)[0]))
        for k in ("box", "case", "pack"):
            if len(kinds.get(k, [])) > 1:
                pick = build.canonical(products, s["code"], k)
                print(f"  variants for {k} (using the cheapest, {pick['name'] if pick else None}): {kinds[k]}")
            elif not kinds.get(k):
                print(f"  missing {k}")
        # 6. cards left out entirely
        out = [c["name"] for c in cards if not c.get("bucket")]
        spec = [c["name"] for c in cards if c.get("bucket") and c["bucket"] not in mod.PACK_BUCKETS]
        if out or spec:
            print(f"  left out of box math: {len(out)} unclassified e.g. {out[:5]}; {len(spec)} special e.g. {spec[:5]}")
    print(f"\nSUMMARY {gcfg['name']}: {dict(issues)}")
    return issues


def main():
    common, games = build.load_config()
    for g in games:
        path = build.RAW / f"{g['id']}.json"
        if path.exists():
            audit_game(common, g, json.loads(path.read_text()))


if __name__ == "__main__":
    sys.exit(main())
