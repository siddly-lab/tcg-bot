"""Look at how TCGplayer lists Pokemon, to plan the multi-game support."""
import collections, json, time, urllib.request
UA = {"User-Agent": "tcg-bot (+https://github.com/siddly-lab/tcg-bot)"}
def get(u):
    time.sleep(0.15)
    with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60) as r:
        return json.load(r)
cats = get("https://tcgcsv.com/tcgplayer/categories")["results"]
for c in cats:
    if "pok" in c["name"].lower() or "one piece" in c["name"].lower() or "lorcana" in c["name"].lower() or "magic" in c["name"].lower():
        print("CAT", c["categoryId"], c["name"])
groups = get("https://tcgcsv.com/tcgplayer/3/groups")["results"]
groups.sort(key=lambda g: g.get("publishedOn") or "")
print("GROUP COUNT", len(groups))
for g in groups:
    print("G", g["groupId"], g.get("abbreviation"), g.get("publishedOn", "")[:10], repr(g["name"]))
tot_p = tot_pr = 0
per = []
for g in groups:
    try:
        pr = get(f"https://tcgcsv.com/tcgplayer/3/{g['groupId']}/prices")["results"]
    except Exception as e:
        print("ERR", g["name"], e); continue
    n_mkt2 = sum(1 for x in pr if (x.get("marketPrice") or 0) >= 2)
    tot_pr += len(pr); per.append((g["name"], len(pr), n_mkt2))
print("TOTAL PRICES", tot_pr, "with market>=2:", sum(x[2] for x in per))
recent = [g for g in groups if (g.get("publishedOn") or "") >= "2025-01-01"][-14:]
for g in recent + [x for x in groups if x["name"] in ("Base Set", "Evolving Skies", "Prismatic Evolutions")]:
    prods = get(f"https://tcgcsv.com/tcgplayer/3/{g['groupId']}/products")["results"]
    prices = get(f"https://tcgcsv.com/tcgplayer/3/{g['groupId']}/prices")["results"]
    def ed(p, k):
        return next((e["value"] for e in p.get("extendedData", []) if e["name"] == k), None)
    rar = collections.Counter(ed(p, "Rarity") for p in prods)
    print(f"\n=== {g['name']} ({g.get('abbreviation')}, {g.get('publishedOn','')[:10]}) products={len(prods)}")
    print("EXT", sorted({e['name'] for p in prods for e in p.get('extendedData', [])}))
    print("RARITY", dict(rar))
    print("SUBTYPES", dict(collections.Counter(x.get("subTypeName") for x in prices)))
    sealed = [p["name"] for p in prods if ed(p, "Rarity") is None]
    print("SEALED", sealed[:40])
    top = sorted(((x.get("marketPrice") or 0, x["productId"], x["subTypeName"]) for x in prices), reverse=True)[:8]
    names = {p["productId"]: (p["name"], ed(p, "Rarity"), ed(p, "Number")) for p in prods}
    print("TOP", [(round(m), names.get(pid), s) for m, pid, s in top])
