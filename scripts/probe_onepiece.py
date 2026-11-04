"""How TCGplayer lists One Piece (category 68), to write its rules."""
import collections, json, time, urllib.request
UA = {"User-Agent": "tcg-bot (+https://github.com/siddly-lab/tcg-bot)"}
def get(u):
    time.sleep(0.12)
    with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60) as r:
        return json.load(r)
groups = get("https://tcgcsv.com/tcgplayer/68/groups")["results"]
groups.sort(key=lambda g: g.get("publishedOn") or "")
print("GROUP COUNT", len(groups))
for g in groups:
    print("G", g["groupId"], g.get("abbreviation"), (g.get("publishedOn") or "")[:10], repr(g["name"]))
def ed(p, k):
    return next((e["value"] for e in p.get("extendedData", []) if e["name"] == k), None)
tot = 0
picks = [g for g in groups if g.get("abbreviation", "").startswith(("OP", "EB", "PRB"))][-6:] + [g for g in groups if g.get("abbreviation") in ("OP01", "OP05", "ST01")]
for g in groups:
    pr = get(f"https://tcgcsv.com/tcgplayer/68/{g['groupId']}/prices")["results"]
    tot += len(pr)
print("TOTAL PRICES", tot)
for g in picks:
    prods = get(f"https://tcgcsv.com/tcgplayer/68/{g['groupId']}/products")["results"]
    prices = get(f"https://tcgcsv.com/tcgplayer/68/{g['groupId']}/prices")["results"]
    print(f"\n=== {g['name']} ({g.get('abbreviation')}, {(g.get('publishedOn') or '')[:10]}) products={len(prods)}")
    print("EXT", sorted({e['name'] for p in prods for e in p.get('extendedData', [])}))
    print("RARITY", dict(collections.Counter(ed(p, "Rarity") for p in prods)))
    print("SUBTYPES", dict(collections.Counter(x.get("subTypeName") for x in prices)))
    print("SEALED", [p["name"] for p in prods if ed(p, "Rarity") is None][:30])
    names = {p["productId"]: (p["name"], ed(p, "Rarity"), ed(p, "Number")) for p in prods}
    top = sorted(((x.get("marketPrice") or 0, x["productId"], x["subTypeName"]) for x in prices), reverse=True)[:12]
    print("TOP", [(round(m), names.get(pid), s) for m, pid, s in top])
    paren = collections.Counter()
    for p in prods:
        n = p["name"]
        if "(" in n:
            paren[n[n.index("("):]] += 1
    print("PAREN SUFFIXES", paren.most_common(25))
    by_r = collections.defaultdict(list)
    for p in prods:
        by_r[ed(p, "Rarity")].append(f"{p['name']} #{ed(p, 'Number')}")
    for r, ns in by_r.items():
        print("  R", r, len(ns), ns[:4])
