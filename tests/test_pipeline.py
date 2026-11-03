import json

import numpy as np
import pytest

from tcg import build, classify, ev
from tests import fixtures


@pytest.fixture()
def cfg():
    return json.loads(build.CONFIG.read_text())


@pytest.fixture()
def tmp_build(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "HIST", tmp_path / "hist")
    monkeypatch.setattr(build, "RAW", tmp_path / "raw.json")
    monkeypatch.setattr(build, "OUT", tmp_path / "out")
    return tmp_path


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
    assert b("Mech // Recruit", "Common", "T06 // T07") == "Token"
    assert b("Reflection // Buff", "None", "T06 // T04") == "Token"
    assert b("Evelynn, In Control (K/DA Special Art Card)", "Showcase", "SP3/005") == "Special"
    assert b("Void Gate (Oversized)", "Uncommon", "296/298") is None
    assert b("Blazing Scorcher", "Common", "001/298") == "Common"


def test_sealed_types():
    assert classify.sealed_type("Origins - Booster Display") == "box"
    assert classify.sealed_type("Origins - Booster Display Case") == "case"
    assert classify.sealed_type("Origins - Booster Pack") == "pack"
    assert classify.sealed_type("Origins - Sleeved Booster Pack") == "sleeved_pack"
    assert classify.sealed_type("Origins - Sleeved Booster Pack Art Bundle [Set of 3]") == "other"
    assert classify.sealed_type("Vendetta - Vault Bundle") == "other"


def test_net_value(cfg):
    s = cfg["selling"]
    assert ev.net_value(0.10, s) == pytest.approx(0.02)
    assert ev.net_value(0.01, s) == pytest.approx(0.01)
    assert ev.net_value(100, s) == pytest.approx(100 * (1 - 0.1325) - 1.0)


def test_slots_sum_to_one_and_specials_replace_foil(cfg):
    pack = ev.merged_pack(cfg["default_pack"], cfg["sets"][0])
    sizes = {k: 3 for k in classify.PACK_BUCKETS}
    slots = ev.build_slots(pack, sizes)
    for s in slots:
        assert sum(s["weights"].values()) == pytest.approx(1.0)
    foil = next(s for s in slots if s["name"] == "Foil")
    assert foil["weights"]["Signature"] == pytest.approx(0.001389)
    assert foil["weights"]["Overnumbered"] == pytest.approx(0.01389 - 0.001389)
    # an empty bucket hands its share back
    sizes["Ultimate"] = 0
    foil2 = next(s for s in ev.build_slots(pack, sizes) if s["name"] == "Foil")
    assert "Ultimate" not in foil2["weights"]


def test_simulation_matches_expected_value(cfg):
    pack = ev.merged_pack(cfg["default_pack"], cfg["sets"][0])
    raw = fixtures.raw()
    products, _ = build.shape(raw, cfg)
    buckets = {}
    for p in products.values():
        if p.get("bucket") in classify.PACK_BUCKETS:
            buckets.setdefault(p["bucket"], []).append(p)
    slots = ev.build_slots(pack, {k: len(v) for k, v in buckets.items()})
    vals = ev.slot_values(slots, buckets, cfg["selling"])
    e = ev.expected(slots, vals)
    sim = ev.simulate(slots, vals, 24, boxes=40000, seed="t")
    # the average of many simulated boxes lands near the exact average (big hits make it noisy)
    assert np.mean(sim["sticker"]) == pytest.approx(e["sticker"] * 24, rel=0.05)
    assert np.mean(sim["net"]) == pytest.approx(e["net"] * 24, rel=0.05)
    # a typical box is worth less than the average box, because the average includes rare big hits
    assert np.median(sim["sticker"]) < np.mean(sim["sticker"])


def test_card_odds(cfg):
    pack = ev.merged_pack(cfg["default_pack"], cfg["sets"][0])
    sizes = {"Common": 10, "Uncommon": 6, "Rare": 6, "Epic": 4, "Rune": 1, "Overnumbered": 1, "Signature": 1}
    buckets = {k: [{"id": f"{k}{i}"} for i in range(n)] for k, n in sizes.items()}
    slots = ev.build_slots(pack, sizes)
    odds = ev.card_odds_per_pack(slots, buckets)
    # one overnumbered per 3 boxes in total, signature included
    over_box = (odds["Overnumbered0"] + odds["Signature0"]) * 24
    assert over_box == pytest.approx(1 / 3, rel=0.01)
    # one epic per 4 packs (the foil slot adds a few more)
    epic_pack = sum(v for k, v in odds.items() if k.startswith("Epic"))
    assert 0.25 < epic_pack < 0.29


def test_full_build_offline(cfg, tmp_build):
    (tmp_build / "raw.json").write_text(json.dumps(fixtures.raw()))
    out = build.run(offline=True)
    sets = {s["code"]: s for s in out["sets"]}
    assert set(sets) == {"OGN", "LEG"}
    o = sets["OGN"]
    assert o["box"]["market"] == 150.0
    assert o["ev"]["box_sticker"] > o["ev"]["box_net"] > 0
    assert o["sim"]["net"]["median"] < o["sim"]["net"]["mean"]
    assert len(o["sim"]["net"]["quantiles"]) == 201
    assert o["chase"][0]["name"] == "Sett, The Boss (Signature)"
    assert o["chase"][0]["boxes_per_hit"] == pytest.approx(30, rel=0.05)
    assert sets["LEG"]["ev"] is None
    assert out["new_sets"] == [{"name": "Mystery Set", "published": "2027-04-30T00:00:00"}]
    kinds = {r["name"]: r["kind"] for r in out["sealed"]}
    assert kinds["Origins - Booster Display Case"] == "case"
    # Origins released 2025-10-31: about a year, box at 150 vs 119.99 MSRP
    box = o["box"]
    assert box["vs_msrp"] == pytest.approx(150 / 119.99 - 1, abs=1e-3)
    assert box["annualized"] is not None
    cards = json.loads((tmp_build / "out" / "cards.json").read_text())
    names = {c["name"] for c in cards}
    assert "Fortified Position (Oversized)" not in names
    assert any(c.get("boxes_per_hit") for c in cards)


def test_history_movers(cfg, tmp_build):
    (tmp_build / "raw.json").write_text(json.dumps(fixtures.raw("2026-11-02")))
    build.run(offline=True)
    r = fixtures.raw("2026-11-03")
    for pr in r["groups"][0]["prices"]:
        pr["marketPrice"] = pr["marketPrice"] * 1.1 if pr["marketPrice"] else None
    (tmp_build / "raw.json").write_text(json.dumps(r))
    out = build.run(offline=True)
    assert out["history_days"] == 2
    assert out["movers"]["has_1d"]
    assert out["movers"]["up_1d"][0]["d1"] == pytest.approx(10.0, abs=0.2)
    o = next(s for s in out["sets"] if s["code"] == "OGN")
    assert len(o["ev_series"]) == 2
    assert o["ev_series"][1][1] > o["ev_series"][0][1]
