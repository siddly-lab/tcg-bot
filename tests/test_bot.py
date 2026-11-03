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
    monkeypatch.setattr(build, "RAW", tmp_path / "raw.json")
    monkeypatch.setattr(build, "OUT", tmp_path / "out")
    (tmp_path / "raw.json").write_text(json.dumps(fixtures.raw()))
    latest = build.run(offline=True)
    s = Store(tmp_path / "cache")
    s.load(json.loads((tmp_path / "out" / "latest.json").read_text()), json.loads((tmp_path / "out" / "cards.json").read_text()))
    return s


def test_search_and_prices(store):
    hits = store.search("sett sig")
    assert hits[0]["name"] == "Sett, The Boss (Signature)"
    assert store.search("booster display")[0].get("sealed")
    p, sub = best_price(hits[0])
    assert sub == "foil" and p == 2000.0
    assert store.set_by("origins")["code"] == "OGN" and store.set_by("ogn")


def test_embeds_fit_discord_limits(store):
    dash = "https://example/"
    L = store.latest
    embeds = [fmt.card_embed(store.search("sett")[0]), fmt.box_embed(store.set_by("OGN"), 120, dash),
              fmt.box_embed(store.set_by("LEG"), None, dash), fmt.sets_embed(L, dash), fmt.sealed_embed(L, dash),
              fmt.movers_embed(L, "day", dash), fmt.movers_embed(L, "week", dash), fmt.digest_embed(L, dash)]
    for e in embeds:
        assert len(e["title"]) <= 256 and len(e.get("description") or "") <= 4096
        assert len(e.get("fields", [])) <= 25
        for name, value, _ in e.get("fields", []):
            assert len(name) <= 256 and 0 < len(value) <= 1024
        botmain.to_embed(e)  # builds a real discord embed without error
    box = fmt.box_embed(store.set_by("OGN"), 120, dash)
    assert "Average value inside" in [f[0] for f in box["fields"]]


def test_share_at_least():
    q = [float(i) for i in range(201)]
    assert fmt.share_at_least(q, 100) == pytest.approx(0.5)
    assert fmt.share_at_least(q, -5) == 1.0 and fmt.share_at_least(q, 500) == 0.0


def test_watch_fires_once_and_rearms():
    card = {"normal": {"market": 10.0}}
    w = {"printing": "normal", "direction": "below", "price": 12.0, "armed": 1}
    assert fmt.check_watch(w, card)[0] == "fire"
    w["armed"] = 0
    assert fmt.check_watch(w, card)[0] == "none"
    card["normal"]["market"] = 15.0
    assert fmt.check_watch(w, card)[0] == "rearm"
    up = {"printing": "normal", "direction": "above", "price": 14.0, "armed": 1}
    assert fmt.check_watch(up, card)[0] == "fire"


def test_db_collection_and_watches(tmp_path, store):
    d = dbm.DB(str(tmp_path / "x.sqlite3"))
    sig = store.search("sett sig")[0]
    d.add_card(1, sig["id"], "foil", 2, 100.0)
    d.add_card(1, sig["id"], "foil", 2, 300.0)
    rows = [dict(r) for r in d.collection(1)]
    assert rows[0]["qty"] == 4 and rows[0]["paid_each"] == pytest.approx(200.0)
    e = fmt.collection_embed(rows, store.by_id)
    assert e["fields"][0][1] == "$8,000"
    d.add_card(1, sig["id"], "foil", -4)
    assert d.collection(1) == []
    wid = d.add_watch(1, sig["id"], "foil", "below", 50)
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
