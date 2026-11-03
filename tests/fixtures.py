"""A small fake tcgcsv pull shaped exactly like the live feed (field names checked against it)."""


def card(pid, name, rarity, number, normal=None, foil=None):
    prod = {"productId": pid, "name": name, "cleanName": name, "imageUrl": f"https://img/{pid}.jpg",
            "categoryId": 89, "groupId": 1, "url": f"https://www.tcgplayer.com/product/{pid}",
            "extendedData": [{"name": "Rarity", "displayName": "Rarity", "value": rarity},
                             {"name": "Number", "displayName": "Card Number", "value": number}]}
    prices = []
    if normal is not None:
        prices.append({"productId": pid, "lowPrice": normal * 0.9, "midPrice": normal, "highPrice": normal * 2,
                       "marketPrice": normal, "directLowPrice": None, "subTypeName": "Normal"})
    if foil is not None:
        prices.append({"productId": pid, "lowPrice": foil * 0.9, "midPrice": foil, "highPrice": foil * 2,
                       "marketPrice": foil, "directLowPrice": None, "subTypeName": "Foil"})
    return prod, prices


def sealed(pid, name, price):
    prod = {"productId": pid, "name": name, "cleanName": name, "imageUrl": "", "categoryId": 89, "groupId": 1,
            "url": f"https://www.tcgplayer.com/product/{pid}", "extendedData": []}
    return prod, [{"productId": pid, "lowPrice": price * 0.95, "midPrice": price, "highPrice": price * 1.5,
                   "marketPrice": price, "directLowPrice": None, "subTypeName": "Normal"}]


def origins_group():
    items = []
    pid = 1000
    for i in range(10):
        items.append(card(pid := pid + 1, f"Common {i}", "Common", f"{i+1:03d}/298", 0.10, 0.50))
    for i in range(6):
        items.append(card(pid := pid + 1, f"Uncommon {i}", "Uncommon", f"{i+20:03d}/298", 0.25, 1.00))
    for i in range(6):
        items.append(card(pid := pid + 1, f"Rare {i}", "Rare", f"{i+40:03d}/298", 2.00, 4.00))
    for i in range(4):
        items.append(card(pid := pid + 1, f"Epic {i}", "Epic", f"{i+60:03d}/298", 10.0, 20.0))
    items.append(card(pid := pid + 1, "Calm Rune", "Common", "R02", 0.05, 0.30))
    items.append(card(pid := pid + 1, "Calm Rune (R02a)", "Showcase", "R02a", None, 5.0))
    items.append(card(pid := pid + 1, "Calm Rune (R02b)", "Promo", "R02b", None, 3.0))
    items.append(card(pid := pid + 1, "Mech // Buff", "Common", "T01", 0.05))
    items.append(card(pid := pid + 1, "Jinx, Demolitionist (Alternate Art)", "Showcase", "030a/298", None, 40.0))
    items.append(card(pid := pid + 1, "Sett, The Boss (Overnumbered)", "Showcase", "310/298", None, 300.0))
    items.append(card(pid := pid + 1, "Sett, The Boss (Signature)", "Showcase", "310*/298", None, 2000.0))
    items.append(card(pid := pid + 1, "Fortified Position (Oversized)", "Uncommon", "279/298", 5.0))
    items.append(sealed(pid := pid + 1, "Origins - Booster Display", 150.0))
    items.append(sealed(pid := pid + 1, "Origins - Booster Pack", 6.0))
    items.append(sealed(pid := pid + 1, "Origins - Booster Display Case", 900.0))
    items.append(sealed(pid := pid + 1, "Origins - Champion Deck (Jinx)", 20.0))
    return {"group": {"groupId": 24344, "name": "Origins", "abbreviation": "OGN", "publishedOn": "2025-10-31T00:00:00"},
            "products": [p for p, _ in items], "prices": [x for _, pr in items for x in pr]}


def raw(date="2026-11-03"):
    legacy = {"group": {"groupId": 24832, "name": "Legacy", "publishedOn": "2027-01-29T00:00:00"},
              "products": [sealed(1, "Legacy - Booster Display", 230.0)[0]],
              "prices": sealed(1, "Legacy - Booster Display", 230.0)[1]}
    mystery_p, mystery_pr = sealed(2, "Mystery - Booster Display", 120.0)
    mystery = {"group": {"groupId": 99999, "name": "Mystery Set", "publishedOn": "2027-04-30T00:00:00"},
               "products": [mystery_p], "prices": mystery_pr}
    return {"category": 89, "fetched_at": f"{date}T21:00:00+00:00", "source_updated": None,
            "groups": [origins_group(), legacy, mystery]}
