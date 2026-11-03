# tcg-bot

Riftbound price tracker, booster box value analyzer and Discord bot.

- **Dashboard:** https://siddly-lab.github.io/tcg-bot/ (rebuilt every day around 2:30pm Pacific)
- **Discord bot:** `/price`, `/box`, `/sets`, `/sealed`, `/movers`, `/watch`, `/collection`, plus a daily price post

## How it fits together

1. `.github/workflows/daily.yml` runs every day after tcgcsv.com refreshes TCGplayer's prices.
2. `tcg/build.py` pulls every Riftbound product and price, sorts cards into rarity buckets
   (`tcg/classify.py`), works out each set's pack and box value and opens 10,000 virtual boxes
   (`tcg/ev.py`), and writes `site/data/latest.json` and `site/data/cards.json`.
3. Each day's prices are saved to `data/history/` (TCGplayer keeps no history of its own), which
   drives the sealed price charts, the box value history and the movers.
4. The `site/` folder is published to GitHub Pages. The Discord bot reads the same data files.

## Changing the odds

Pack odds live in `config/sets.json`. Every rate says where it came from (`official`, `community`
or `assumed`), and the dashboard shows that label. When a new set comes out, add a line to `sets`
with its name, release date and MSRP. The dashboard flags a new set as soon as TCGplayer lists it.

## Running locally

```bash
pip install -r requirements-dev.txt -r bot/requirements.txt
python -m pytest -q
python -m tcg.build
```

## Bot on the NAS

See [deploy/SETUP.md](deploy/SETUP.md).
