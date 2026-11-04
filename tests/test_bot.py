import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bot"))

from tcg import build  # noqa: E402
from tcgbot import config, db as dbm, format as fmt, main as botmain  # noqa: E402
from tcgbot.store import Store, best_price  # noqa: E402
from tests import fixtures  # noqa: E402


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "HIST", tmp_path / "hist")
    monkeypatch.setattr(build, "RAW", tmp_path / "raw")
    monkeypatch.setattr(build, "OUT", tmp_path / "out")
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "riftbound.json").write_text(json.dumps(fixtures.raw()))
    (tmp_path / "raw" / "pokemon.json").write_text(json.dumps(fixtures.pokemon_raw()))
    (tmp_path / "raw" / "onepiece.json").write_text(json.dumps(fixtures.onepiece_raw()))
    build.run(offline=True)
    out = tmp_path / "out"
    games = json.loads((out / "games.json").read_text())["games"]
    s = Store(tmp_path / "cache")
    s.load(games, {g["id"]: json.loads((out / g["id"] / "summary.json").read_text()) for g in games},
           {g["id"]: json.loads((out / g["id"] / "cards.json").read_text()) for g in games})
    s.out = out
    return s


def detail(store, gid, s):
    return json.loads((store.out / gid / s["file"]).read_text())


def test_search_and_prices(store):
    hits = store.search("sett sig")
    assert hits[0]["name"] == "Sett, The Boss (Signature)" and hits[0]["game"] == "riftbound"
    assert store.search("delta reign booster box")[0].get("sealed")
    assert store.search("charizard")[0]["game"] == "pokemon"
    p, sub = best_price(hits[0])
    assert sub == "Foil" and p == 2000.0
    assert best_price(hits[0], "foil")[0] == 2000.0
    assert store.set_by("origins")[1]["code"] == "OGN" and store.set_by("pokemon:DLR")[0] == "pokemon"


def test_embeds_fit_discord_limits(store):
    dash = "https://example/"
    embeds = [fmt.card_embed(store.search("sett")[0], "Riftbound"), fmt.card_embed(store.search("delta reign booster box")[0], "Pokémon"),
              fmt.digest_embed(store.summary, dash)]
    for gid, s in store.all_sets():
        embeds.append(fmt.box_embed(s, detail(store, gid, s), 120, dash, store.game_name(gid)))
    for gid, sm in store.summary.items():
        embeds += [fmt.sets_embed(sm, dash), fmt.sealed_embed(sm, dash), fmt.movers_embed(sm, "day", dash), fmt.movers_embed(sm, "week", dash)]
    for e in embeds:
        assert len(e["title"]) <= 256 and len(e.get("description") or "") <= 4096
        assert len(e.get("fields", [])) <= 25
        for name, value, _ in e.get("fields", []):
            assert len(name) <= 256 and 0 < len(value) <= 1024
        botmain.to_embed(e)
    gid, s = store.set_by("OGN")
    box = fmt.box_embed(s, detail(store, gid, s), 120, dash)
    assert "Average value inside" in [f[0] for f in box["fields"]]


def test_share_at_least():
    q = [float(i) for i in range(201)]
    assert fmt.share_at_least(q, 100) == pytest.approx(0.5)
    assert fmt.share_at_least(q, -5) == 1.0 and fmt.share_at_least(q, 500) == 0.0


def test_watch_fires_once_and_rearms():
    card = {"prices": {"Normal": {"market": 10.0}}}
    w = {"printing": "Normal", "direction": "below", "price": 12.0, "armed": 1}
    assert fmt.check_watch(w, card)[0] == "fire"
    w["armed"] = 0
    assert fmt.check_watch(w, card)[0] == "none"
    card["prices"]["Normal"]["market"] = 15.0
    assert fmt.check_watch(w, card)[0] == "rearm"
    up = {"printing": "Normal", "direction": "above", "price": 14.0, "armed": 1}
    assert fmt.check_watch(up, card)[0] == "fire"


def test_db_collection_and_watches(tmp_path, store):
    d = dbm.DB(str(tmp_path / "x.sqlite3"))
    sig = store.search("sett sig")[0]
    d.add_card(1, sig["id"], "Foil", 2, 100.0)
    d.add_card(1, sig["id"], "Foil", 2, 300.0)
    rows = [dict(r) for r in d.collection(1)]
    assert rows[0]["qty"] == 4 and rows[0]["paid_each"] == pytest.approx(200.0)
    e = fmt.collection_embed(rows, store.by_id)
    assert e["fields"][0][1] == "$8,000"
    d.add_card(1, sig["id"], "Foil", -4)
    assert d.collection(1) == []
    wid = d.add_watch(1, sig["id"], "Foil", "below", 50)
    assert d.remove_watch(2, wid) is False and d.remove_watch(1, wid) is True
    d.put("k", "v")
    assert d.get("k") == "v"


def test_command_tree_is_valid(tmp_path, monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "x")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "db.sqlite3"))
    bot = botmain.TcgBot(config.load())
    cmds = bot.tree.get_commands()
    names = {c.name for c in cmds}
    assert {"price", "box", "sets", "sealed", "movers", "watch", "collection", "dashboard", "botstatus"} <= names

    def walk(c):
        d = c.to_dict(bot.tree)
        assert len(d["description"]) <= 100, c.name
        for o in d.get("options", []):
            assert len(o["description"]) <= 100, (c.name, o["name"])
        for sub in getattr(c, "commands", []):
            walk(sub)
    for c in cmds:
        walk(c)


def test_config_defaults(monkeypatch):
    monkeypatch.delenv("DATA_URL", raising=False)
    s = config.load()
    assert s.data_url == "https://siddly-lab.github.io/tcg-bot/data/"


def test_set_names_carry_their_year(store):
    from tcgbot.store import with_year
    assert with_year("Origins", "2025") == "Origins (2025)"
    assert with_year("McDonald's Promos 2023", "2023") == "McDonald's Promos 2023"
    assert with_year("Origins", None) == "Origins"
    sig = store.search("sett sig")[0]
    assert "Origins (2025)" in fmt.card_embed(sig, "Riftbound")["description"]
    assert "Origins (2025)" in fmt.sets_embed(store.summary["riftbound"], "x")["description"]
    gid, s = store.set_by("OGN")
    assert "Origins (2025)" in fmt.box_embed(s, detail(store, gid, s), 120, "x", "Riftbound")["title"]
