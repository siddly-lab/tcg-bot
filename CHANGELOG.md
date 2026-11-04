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

## 0.1.1

- **What was wrong:** the first history backfill went too fast and tcgcsv refused the last 13 days (Oct 21 to Nov 2).
- **What changed:** archive downloads now pause 3 seconds between days and wait and retry when told to slow down.
  Every daily run now fills any missing days, so gaps heal on their own.

## 0.1.2

- **What was wrong:** many Signature and some Overnumbered cards showed a broken picture. TCGplayer has no photo for them yet, but the feed still gives a link.
- **What changed:** those cards now borrow the picture of the same card's other version (a Signature uses its Overnumbered art). Hovering says it's a stand-in. Anything still without a photo shows an empty frame instead of a broken image.

## 0.1.3

- Card pictures get bigger when you point at them on a computer, and open large when tapped on a phone (tap again or press Esc to close). Uses TCGplayer's large photo when it has one.

## 0.2.0 — buy timing, redesign, Pokémon

**Buy timing (for collectors)**
- Every sealed product and card is compared with its own last 90 days. Labels: "At or below MSRP", "Near its 90-day low", "In its normal range", "Above its usual price".
- "You'd pay": cheapest listing plus 7.75% sales tax and estimated shipping, not just the market price.
- Cheapest way to get packs: box vs case vs bundle vs ETB vs loose packs, per pack, delivered.
- Price by days since release: every set's box lined up by age, to see where a new set sits compared with older ones at the same point.
- Compared with other investments: what the MSRP would have earned in an S&P 500 fund or Treasury bills since release, before and after federal tax.
- Chase cards: 90-day range and label for each, plus "buy it vs pull it" (expected net cost of opening boxes until you hit that card).
- How much of a box's value rides on its 10 most valuable cards.
- Print status supported per set in the config (left blank until confirmed).

**Redesign**
- New Today page: good prices on sealed, chase cards near their lows, sets worth opening, biggest sealed moves.
- Set browser grouped by year (Riftbound) or era (Pokémon), with box art, price chart, search, and collapsible groups.
- Set pages with a buy-timing panel, 100-box dot chart, card detail pop-up with price history.
- Links to any view (for example `#/pokemon/set/DLR`), sortable tables, "show more" paging, phone-friendly tabs, sun/moon theme button.

**Pokémon**
- All 220 TCGplayer Pokémon groups scanned daily; every group selling boxes or packs becomes a set (about 150), grouped by era.
- Box value for main Scarlet & Violet and Mega Evolution sets, using TCGplayer's measured pull rates (community estimates, labeled).
- Older sets get sealed tracking, buy timing and chase-card prices, but no box value.
- History keeps sealed products, modeled sets' cards and cards worth $20+ (about a tenth of Pokémon's 46,000 daily prices) to keep the repo small.

**Discord bot**
- Commands work across games: `/box` searches every game's sets, `/sets`, `/sealed`, `/movers` take a game. `/sealed` now lists good prices. The daily post covers every game.

## 0.2.1

- Set names now show their release year everywhere on the dashboard and in the bot, for example "Origins (2025)". Names that already contain a year aren't doubled up.
- Sets that haven't been released yet are left off the dashboard and out of the bot until release day (for example Riftbound: Legacy and Pokémon: Delta Reign). Their prices are still saved in the background, so price history is ready the day they come out.
- Set search also matches the year. Year groups on the Riftbound sets page no longer repeat the year, and pre-order alerts show a readable date.
