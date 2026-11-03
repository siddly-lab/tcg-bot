# Changelog

## 0.1.0 — first release

**Dashboard (GitHub Pages, rebuilt daily)**
- Prices for every Riftbound card and sealed product from TCGplayer, via tcgcsv.com.
- Per set: average box value at market prices, what you'd pocket after TCGplayer fees and shipping,
  the typical box, chance a box pays for itself, bad-box/great-box range, and open-vs-sell-sealed.
- "What I paid" box on each set recalculates the return and break-even chance.
- Hit odds (Epic, alternate art, Overnumbered, Signature, Ultimate) and the top 20 chase cards with
  "1 in X boxes" odds for each exact card.
- Sealed tracker: boxes, cases and packs against MSRP, with yearly growth rate, value if sold, and
  7/30-day change. Price history backfilled from tcgcsv's daily archives back to Origins' launch.
- Card search with Normal/Foil prices, 7- and 30-day change and pull odds. Daily movers.
- Flags new sets the moment TCGplayer lists them, and upcoming pre-orders.

**Discord bot (Docker on the NAS)**
- `/price`, `/box set paid`, `/sets`, `/sealed`, `/movers`, `/dashboard`, `/botstatus`.
- `/watch add|list|remove`: DM alerts when a price crosses your number (once, then resets when it moves back).
- `/collection add|remove|value`: what your cards and sealed product are worth, and your gain if you enter what you paid.
- Daily price post to a channel once the new prices land.

**Judgment calls**
- Pack odds: Epic 1 per 4 packs, Overnumbered 1 per 3 boxes, Signature 1 in 10 of those, Ultimate
  1 in 4,000 packs (Riot). Alternate art about 1 in 12 packs (community). The foil-slot rarity split and
  rune/token split are our assumptions, and are labeled that way.
- Within a rarity every card is equally likely. Cards under $3 count as bulk at $0.02.
- From Spiritforged on, rares and epics are priced as foils (that's the only printing TCGplayer lists).
- K/DA special art cards, oversized cards and promo runes are left out of the box math.
