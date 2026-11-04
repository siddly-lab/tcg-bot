# Grail

The code lives in the `tcg-bot` repo.

Trading card price tracker, booster box value analyzer, buy-timing tool and Discord bot. Covers Riftbound, Pokémon and One Piece.

- **Dashboard:** https://siddly-lab.github.io/tcg-bot/ (rebuilt every day around 2:30pm Pacific)
- **Discord bot:** `/price`, `/box`, `/sets`, `/sealed`, `/movers`, `/watch`, `/collection`, plus a daily price post

## How it fits together

1. `.github/workflows/daily.yml` runs every day after tcgcsv.com refreshes TCGplayer's prices.
2. `tcg/build.py` pulls every Riftbound product and price, sorts cards into rarity buckets
   (`tcg/games/`), works out each set's pack and box value and opens 10,000 virtual boxes
   (`tcg/ev.py`), and writes one summary, one card list and one file per set for each game under `site/data/`.
3. Each day's prices are saved to `data/history/` (TCGplayer keeps no history of its own), which
   drives the sealed price charts, the box value history and the movers.
4. The `site/` folder is published to GitHub Pages. The Discord bot reads the same data files.

## Adding a game or changing the odds

Each game has a file in `config/games/` (its TCGplayer category, how its sets are found, pack layouts
and MSRPs) and a small rules module in `tcg/games/` (how its products are named). Shared settings
(selling fees, sales tax, shipping, buy-label thresholds, tax rates) are in `config/common.json`.

Pack odds live in the game's config file. Every rate says where it came from (`official`, `community`
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
