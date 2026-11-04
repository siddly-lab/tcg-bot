import json

import numpy as np
import pytest

from tcg import build, ev, market
from tcg.games import pokemon, riftbound as classify
from tests import fixtures


@pytest.fixture()
def cfg():
    common, games = build.load_config()
    return {"common": common, **{g["id"]: g for g in games}}


@pytest.fixture()
def tmp_build(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "HIST", tmp_path / "hist")
    monkeypatch.setattr(build, "RAW", tmp_path / "raw")
    monkeypatch.setattr(build, "OUT", tmp_path / "out")
    (tmp_path / "raw").mkdir()
    return tmp_path


def write_raw(tmp, rb=None, pk=None):
    (tmp / "raw" / "riftbound.json").write_text(json.dumps(rb or fixtures.raw()))
    (tmp / "raw" / "pokemon.json").write_text(json.dumps(pk or fixtures.pokemon_raw()))


def load(tmp, game, name):
    return json.loads((tmp / "out" / game / name).read_text())


def test_classify_names_from_live_feed():
    def b(name, rarity, number):
        return classify.classify_card({"name": name, "extendedData": [
            {"name": "Rarity", "value": rarity}, {"name": "Number", "value": number}]})
    assert b("Sett, The Boss (Signature)", "Showcase", "310*/298") == "Signature"
    assert b("K'Sante, Courageous (Heartsteel Overnumbered)", "Showcase", "178/167") == "Overnumbered"
    assert b("Kayn, Unleashed (Heartsteel Signature)", "Showcase", "182*/167") == "Signature"
    assert b("Packed Amphitheater (Ultimate)", "Showcase", "184/167") == "Ultimate"
    assert b("Jayce, Brilliant Inventor (Alternate Art)", "Epic", "068a/166") == "AltArt"
    assert b("Calm Rune", "Common", "R02") == "Rune"
    assert b("Calm Rune (R02a)", "Showcase", "R02a") == "RuneAlt"
    assert b("Calm Rune (R02b)", "Promo", "R02b") is None
    assert b("Fury Rune (Alternate Art)", "Showcase", "007a/298") == "RuneAlt"
    assert b("Fury Rune", "Common", "007/298") == "Rune"
    assert b("Mech // Recruit", "Common", "T06 // T07") == "Token"
    assert b("Reflection // Buff", "None", "T06 // T04") == "Token"
    assert b("Evelynn, In Control (K/DA Special Art Card)", "Showcase", "SP3/005") == "Special"
    assert b("Void Gate (Oversized)", "Uncommon", "296/298") is None
    assert b("Blazing Scorcher", "Common", "001/298") == "Common"


def test_sealed_types():
    assert classify.sealed_type("Origins - Booster Display") == "box"
    assert classify.sealed_type("Origins - Booster Display Case") == "case"
    assert classify.sealed_type("Origins - Booster Pack") == "pack"
    assert classify.sealed_type("Origins - Sleeved Booster Pack Art Bundle [Set of 3]") == "other"
    assert pokemon.sealed_type("Delta Reign Booster Box") == "box"
    assert pokemon.sealed_type("Delta Reign Half Booster Box") == "other"
    assert pokemon.sealed_type("Delta Reign Booster Box Case") == "case"
    assert pokemon.sealed_type("Delta Reign Elite Trainer Box") == "etb"
    assert pokemon.sealed_type("Delta Reign Pokemon Center Elite Trainer Box (Exclusive)") == "other"
    assert pokemon.sealed_type("Delta Reign Booster Bundle") == "bundle"
    assert pokemon.card_name("Zinnia's Trust - 140/103") == "Zinnia's Trust"


def test_net_value(cfg):
    s = cfg["common"]["selling"]
    assert ev.net_value(0.10, s) == pytest.approx(0.02)
    assert ev.net_value(100, s) == pytest.approx(100 * (1 - 0.1325) - 1.0)


def test_slots_sum_to_one_and_upgrades(cfg):
    t = cfg["riftbound"]["templates"]["riftbound"]
    sizes = {k: 3 for k in classify.PACK_BUCKETS}
    slots = ev.build_slots(t, sizes)
    for s in slots:
        assert sum(s["weights"].values()) == pytest.approx(1.0)
    foil = next(s for s in slots if s["name"] == "Foil")
    assert foil["weights"]["Signature"] == pytest.approx(0.001389)
    assert foil["weights"]["Overnumbered"] == pytest.approx(0.0125)
    sizes["Ultimate"] = 0
    assert "Ultimate" not in next(s for s in ev.build_slots(t, sizes) if s["name"] == "Foil")["weights"]
    pk = ev.build_slots(cfg["pokemon"]["templates"]["mega"], {k: 3 for k in pokemon.PACK_BUCKETS})
    rare = next(s for s in pk if s["name"] == "Rare or better")
    assert rare["weights"]["Double Rare"] == pytest.approx(0.20)
    assert sum(rare["weights"].values()) == pytest.approx(1.0)


def test_card_odds(cfg):
    t = cfg["riftbound"]["templates"]["riftbound"]
    sizes = {"Common": 10, "Uncommon": 6, "Rare": 6, "Epic": 4, "Rune": 1, "Overnumbered": 1, "Signature": 1}
    buckets = {k: [{"id": f"{k}{i}"} for i in range(n)] for k, n in sizes.items()}
    odds = ev.card_odds_per_pack(ev.build_slots(t, sizes), buckets)
    assert (odds["Overnumbered0"] + odds["Signature0"]) * 24 == pytest.approx(1 / 3, rel=0.01)
    assert 0.25 < sum(v for k, v in odds.items() if k.startswith("Epic")) < 0.29


def test_simulation_matches_expected_value(cfg):
    t = cfg["riftbound"]["templates"]["riftbound"]
    products, sets, _ = build.shape(fixtures.raw(), cfg["riftbound"], classify)
    buckets = {}
    for p in products.values():
        if p.get("bucket") in classify.PACK_BUCKETS:
            buckets.setdefault(p["bucket"], []).append(p)
    slots = ev.build_slots(t, {k: len(v) for k, v in buckets.items()})
    vals = ev.slot_values(slots, buckets, cfg["common"]["selling"], classify.BUCKET_PRINTING)
    e = ev.expected(slots, vals)
    sim = ev.simulate(slots, vals, 24, boxes=40000, seed="t")
    assert np.mean(sim["sticker"]) == pytest.approx(e["sticker"] * 24, rel=0.05)
    assert np.median(sim["sticker"]) < np.mean(sim["sticker"])


def test_zones(cfg):
    z = cfg["common"]["zones"]
    ser = [(f"2026-10-{d:02d}", 100 + d) for d in range(1, 31)]
    assert market.stats(ser, "2026-10-31", 101, None, z)["zone"] == "good_low"
    assert market.stats(ser, "2026-10-31", 140, None, z)["zone"] == "high"
    assert market.stats(ser, "2026-10-31", 115, None, z)["zone"] == "normal"
    assert market.stats(ser, "2026-10-31", 115, 120, z)["zone"] == "good_msrp"
    assert market.stats(ser[:2], "2026-10-31", 115, None, z)["zone"] == "new"
    flat = [(f"2026-10-{d:02d}", 100) for d in range(1, 31)]
    assert market.stats(flat, "2026-10-31", 100, None, z)["zone"] == "normal"
    assert market.buy_cost(100, 110, "box", cfg["common"]["buying"]) == pytest.approx(100 * 1.0775 + 6)


def test_benchmark_compare(cfg):
    bench = {"spy": [("2025-10-31", 500.0), ("2026-11-03", 600.0)], "tbill": [("2025-11-01", 4.0), ("2026-10-01", 4.0)]}
    c = market.compare("2025-10-31", "2026-11-03", 120, 240, bench, cfg["common"]["benchmark"])
    assert c["sealed"] == pytest.approx(1.0) and c["spy"] == pytest.approx(0.2)
    assert 0.039 < c["tbill"] < 0.043
    assert c["after_tax"]["sealed"] == pytest.approx(0.72)


def test_full_build_offline(cfg, tmp_build):
    write_raw(tmp_build)
    build.run(offline=True)
    games = load(tmp_build, "", "games.json") if False else json.loads((tmp_build / "out" / "games.json").read_text())
    assert [g["id"] for g in games["games"]] == ["riftbound", "pokemon"]
    s = load(tmp_build, "riftbound", "summary.json")
    sets = {x["code"]: x for x in s["sets"]}
    assert set(sets) == {"OGN", "LEG"} and sets["OGN"]["modeled"] and not sets["LEG"]["modeled"]
    o = load(tmp_build, "riftbound", "sets/OGN.json")
    box = next(r for r in o["sealed"] if r["kind"] == "box")
    assert box["market"] == 150.0 and box["vs_msrp"] == pytest.approx(150 / 119.99 - 1, abs=1e-3)
    assert box["buy_cost"] == pytest.approx(142.5 * 1.0775 + 6, abs=0.01)
    assert o["ev"]["box_sticker"] > o["ev"]["box_net"] > 0
    assert len(o["sim"]["net"]["quantiles"]) == 201
    top = o["chase"][0]
    assert top["name"] == "Sett, The Boss (Signature)" and top["boxes_per_hit"] == pytest.approx(30, rel=0.05)
    assert top["pull_cost"] >= 0 and top["pull_boxes"] == pytest.approx(30, rel=0.05)
    assert 0 < o["top10_share"] <= 1
    assert [w["kind"] for w in o["ways_to_buy"]][0] in ("box", "case", "pack")
    assert s["new_sets"] == [{"name": "Mystery Set", "published": "2027-04-30T00:00:00"}]
    assert any(a["type"] == "upcoming" for a in s["today"]["alerts"])
    cards = load(tmp_build, "riftbound", "cards.json")
    over = next(c for c in cards if c["name"] == "Fortified Position (Oversized)")
    assert not over.get("boxes_per_hit")  # searchable, but not in packs


def test_pokemon_build(cfg, tmp_build):
    write_raw(tmp_build)
    build.run(offline=True)
    s = load(tmp_build, "pokemon", "summary.json")
    sets = {x["code"]: x for x in s["sets"]}
    assert set(sets) == {"DLR", "BS"}  # promos aren't a set
    assert sets["DLR"]["era"] == "Mega Evolution" and sets["DLR"]["modeled"]
    assert sets["BS"]["era"] == "Wizards of the Coast" and not sets["BS"]["modeled"]
    d = load(tmp_build, "pokemon", "sets/DLR.json")
    kinds = {r["kind"] for r in d["sealed"]}
    assert {"box", "case", "etb", "bundle", "pack", "other"} <= kinds
    assert d["ev"]["box_sticker"] > 0
    ways = {w["kind"]: w for w in d["ways_to_buy"]}
    assert ways["box"]["packs"] == 36 and ways["etb"]["packs"] == 9
    assert d["chase"][0]["kind"].startswith("Mega Hyper")
    assert d["chase"][0]["pull_cost"] > d["chase"][0]["buy_cost"]  # chasing a 1-in-100-boxes card costs far more than buying it
    b = load(tmp_build, "pokemon", "sets/BS.json")
    assert b["chase"][0]["name"] == "Charizard" and not b["modeled"]


def test_missing_photos_borrow_other_version(cfg):
    r = fixtures.raw()
    for p in r["groups"][0]["products"]:
        if p["name"] == "Sett, The Boss (Signature)":
            p["imageCount"] = 0
            sig = p["productId"]
        if p["name"] == "Sett, The Boss (Overnumbered)":
            over_img = p["imageUrl"]
    products, _, _ = build.shape(r, cfg["riftbound"], classify)
    assert products[sig]["image"] == over_img and products[sig]["image_standin"]


def test_history_movers_and_zones(cfg, tmp_build):
    for day, bump in (("2026-10-20", 1.0), ("2026-10-27", 1.0), ("2026-11-01", 1.0), ("2026-11-02", 1.0), ("2026-11-03", 1.3)):
        r = fixtures.raw(day)
        for pr in r["groups"][0]["prices"]:
            pr["marketPrice"] = pr["marketPrice"] * bump if pr["marketPrice"] else None
        write_raw(tmp_build, rb=r, pk=fixtures.pokemon_raw(day))
        build.run(offline=True)
    s = load(tmp_build, "riftbound", "summary.json")
    assert s["history_days"] == 5 and s["movers"]["has_1d"]
    assert s["movers"]["up_1d"][0]["d1"] == pytest.approx(30.0, abs=0.2)
    o = load(tmp_build, "riftbound", "sets/OGN.json")
    box = next(r for r in o["sealed"] if r["kind"] == "box")
    assert box["low90"] == 150.0 and box["zone"] == "high"
    assert len(o["ev_series"]) == 5
    hero = next(x for x in s["sets"] if x["code"] == "OGN")["hero"]
    assert hero["lifecycle"][0][0] > 300 and len(hero["spark"]) == 5


def test_backfill_dates():
    import datetime as dt
    from tcg import backfill
    d = backfill.dates_to_fetch(dt.date(2026, 1, 1), dt.date(2026, 2, 28), 10, {"2026-02-27"})
    assert d[0] == "2026-01-01" and "2026-01-08" in d and "2026-01-02" not in d
    assert "2026-02-26" in d and "2026-02-27" not in d and d[-1] == "2026-02-28"
