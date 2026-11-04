"""Run the Discord bot's message code against today's real data (CI, after a build).

Loads site/data exactly as the bot would, then builds every message the bot can send for every
game and set, checking each against Discord's size limits, and times card search (autocomplete
must answer within 3 seconds).

    python tests/live_bot_check.py site/data
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bot"))
from tcgbot import format as fmt, main as botmain  # noqa: E402
from tcgbot.store import Store  # noqa: E402

root = Path(sys.argv[1] if len(sys.argv) > 1 else "site/data")
games = json.loads((root / "games.json").read_text())["games"]
store = Store()
store.load(games, {g["id"]: json.loads((root / g["id"] / "summary.json").read_text()) for g in games},
           {g["id"]: json.loads((root / g["id"] / "cards.json").read_text()) for g in games})
dash = "https://siddly-lab.github.io/tcg-bot/"
problems, n = [], 0


def check(e, where):
    global n
    n += 1
    if len(e.get("title") or "") > 256 or len(e.get("description") or "") > 4096 or len(e.get("fields", [])) > 25:
        problems.append(f"{where}: embed too big")
    for name, value, _ in e.get("fields", []):
        if not (0 < len(value) <= 1024) or len(name) > 256:
            problems.append(f"{where}: field '{name}' is {len(value)} chars")
    botmain.to_embed(e)


for gid, s in store.all_sets():
    d = json.loads((root / gid / s["file"]).read_text())
    check(fmt.box_embed(s, d, None, dash, store.game_name(gid)), f"/box {gid}:{s['code']}")
    check(fmt.box_embed(s, d, 99.0, dash, store.game_name(gid)), f"/box {gid}:{s['code']} paid")
for gid, sm in store.summary.items():
    for e, w in ((fmt.sets_embed(sm, dash), "/sets"), (fmt.sealed_embed(sm, dash), "/sealed"),
                 (fmt.movers_embed(sm, "day", dash), "/movers day"), (fmt.movers_embed(sm, "week", dash), "/movers week")):
        check(e, f"{w} {gid}")
check(fmt.digest_embed(store.summary, dash), "daily post")
for c in list(store.by_id.values())[::50]:
    check(fmt.card_embed(c, store.game_name(c.get("game"))), f"/price {c['name']}")
slow = 0.0
for q in ("charizard", "luffy manga", "sett signature", "booster box", "", "zzzz"):
    t = time.time()
    store.search(q, 25)
    slow = max(slow, time.time() - t)
if slow > 1.5:
    problems.append(f"card search took {slow:.2f}s; autocomplete must answer within 3s")
print(f"Built {n} bot messages from real data for {len(games)} games, {sum(1 for _ in store.all_sets())} sets, "
      f"{len(store.by_id):,} searchable products. Slowest search {slow * 1000:.0f} ms.")
if problems:
    print("PROBLEMS:\n- " + "\n- ".join(problems[:40]))
    sys.exit(1)
print("All bot messages fit Discord's limits.")
