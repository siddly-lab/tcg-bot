"""Print a summary of tcgcsv's Riftbound data so the parser can be checked against the real thing."""
import collections, json, urllib.request

UA = {"User-Agent": "tcg-bot/0.1 (+https://github.com/siddly-lab/tcg-bot)"}

def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return json.load(r)

cats = get("https://tcgcsv.com/tcgplayer/categories")
print("TOP KEYS", list(cats.keys()))
rb = [c for c in cats["results"] if "rift" in (c.get("name", "") + c.get("displayName", "")).lower()]
print("RIFT CATS", json.dumps(rb, indent=1))
cid = rb[0]["categoryId"]
groups = get(f"https://tcgcsv.com/tcgplayer/{cid}/groups")["results"]
for g in groups:
    print("GROUP", g["groupId"], repr(g["name"]), g.get("abbreviation"), g.get("isSupplemental"), g.get("publishedOn"))
for g in groups:
    prods = get(f"https://tcgcsv.com/tcgplayer/{cid}/{g['groupId']}/products")["results"]
    prices = get(f"https://tcgcsv.com/tcgplayer/{cid}/{g['groupId']}/prices")["results"]
    ext = collections.Counter()
    rar = collections.Counter()
    for p in prods:
        for e in p.get("extendedData", []):
            ext[e["name"]] += 1
            if e["name"] == "Rarity":
                rar[e["value"]] += 1
    print(f"\n=== {g['name']} products={len(prods)} prices={len(prices)}")
    print("EXT FIELDS", dict(ext))
    print("RARITIES", dict(rar))
    print("SUBTYPES", dict(collections.Counter(x.get("subTypeName") for x in prices)))
    norar = [p["name"] for p in prods if not any(e["name"] == "Rarity" for e in p.get("extendedData", []))]
    print("NO-RARITY PRODUCTS", norar[:60])
    if g is groups[0] or "origins" in g["name"].lower():
        for p in prods[:2]:
            print("SAMPLE", json.dumps(p)[:1500])
        print("PRICE SAMPLE", json.dumps(prices[:4]))
    # show showcase-ish names and numbers
    def ed(p, k):
        return next((e["value"] for e in p.get("extendedData", []) if e["name"] == k), None)
    by_r = collections.defaultdict(list)
    for p in prods:
        by_r[ed(p, "Rarity")].append(f"{p['name']} #{ed(p, 'Number')}")
    for r, names in by_r.items():
        print("RARITY", r, "e.g.", names[:6], "...", names[-4:])
    odd = [f"{p['name']} #{ed(p,'Number')} [{ed(p,'Rarity')}]" for p in prods if any(s in p["name"].lower() for s in ("alternate", "overnumber", "signature", "showcase", "foil", "(", "ultimate"))]
    print("PAREN NAMES", odd[:40])
try:
    print("LAST UPDATED", urllib.request.urlopen(urllib.request.Request("https://tcgcsv.com/last-updated.txt", headers=UA)).read()[:100])
except Exception as e:
    print("last-updated failed", e)
