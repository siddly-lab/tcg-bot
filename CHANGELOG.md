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

## 0.3.0 — Foil

- **New name: Foil.** The dashboard, page titles and bot status now say Foil. (Name the Discord app "Foil" when you set it up; the repo stays `tcg-bot`.)
- **What was wrong:** long product names (for example "Evolving Skies Elite Trainer Box [Flareon/Jolteon/Umbreon/Leafeon]") pushed prices and range bars out of their cards on the Today page. The card pop-up also spilled sideways on phones, and some tables were cut off at tablet width.
- **What changed:** names clamp to two lines (hover shows the full name), every box lets its contents shrink and wrap, the MSRP note sits on its own line under the range bar, table text wraps, and tablets hide the less important sealed columns.
- **Guard for the future:** a layout check opens every page in a real browser at phone, tablet, laptop and wide-screen sizes, using that day's real data. It fails if anything sticks out of its box, the page scrolls sideways, a table is cut off on a tablet or larger, or the page throws an error. It runs on every change and before every daily publish; if it fails, the update doesn't go live and yesterday's page stays up.
- Browsers now always load the latest files after an update (no more stale pages for up to 10 minutes).

## 0.4.0 — One Piece

- **One Piece Card Game added** as a third game. Every TCGplayer group selling booster boxes or packs is a set (main OP sets, Extra Boosters, Premium Boosters), grouped by year, with a year of price history filled in on the first run.
- **Box value for main OP sets** (OP-01 onward), modeled as 12-card packs, 24 per box, 12 boxes per case. Bandai publishes no pull rates, so every rate is a community estimate or our assumption: about 6 to 7 Super Rares per box, a Secret Rare every 1 to 2 boxes, about 1.3 alternate arts per box, an SP card per 6 boxes, a Treasure Rare per case, a Manga rare per 40 boxes. Extra and Premium Boosters get sealed tracking and card prices only.
- **Left out of the box math:** any version whose odds are unknown: Super Alternate Arts, Wanted Posters, gold-stamped signatures, box toppers and anything else with an unfamiliar label. Only alternate art / parallel, SP, Manga and Treasure Rare versions count. They still appear in chase cards and search with their prices.
- **No MSRP yet for One Piece.** I couldn't confirm an official English MSRP, so "vs MSRP", "per year" and the investment comparison stay blank for One Piece until one is added to `config/games/onepiece.json`. Buy labels still work from the 90-day history.
- "If you sold it" now shows for every sealed product, MSRP or not.
- On phones the game switcher gets its own row so three games fit.

## 0.5.0 — guardrails and rip-or-hold

**What was wrong** (found by a new audit of every set with a box value):
- Cards with no recent sales were valued at their asking price, including placeholder asks like $9,999.99. That inflated One Piece OP-17 (one card was 57% of its box value), OP-09 (44%) and OP-05 (39%).
- TCGplayer lists OP-14 and OP-15 together with Extra Booster EB-04, so about 49 EB-04 cards were counted as pulls from OP packs.
- "Thin market" was really flagging falling prices, not few sales.
- "You'd pocket" assumed you could sell at the last sale even when listings had dropped below it.
- Pokémon "Enhanced" booster boxes and Romance Dawn's two box waves were picked by name length.

**What changed:**
1. Cards with no recent sales count at the typical sale price for their rarity in that set; asking prices of $9,999+ with no sales are ignored. Set pages list these cards.
2. One Piece: a regular card only counts if it carries the set's own number; SP and Treasure Rare reprints still count.
3. Riftbound and Pokémon get the strict label rule: any version label without known odds is left out (Radiance's Heartsteel Overnumbered and Signature cards are now left out until their odds are confirmed).
4. Enhanced and half booster boxes are tracked as other sealed; when a set has several box versions, the cheapest is used and the rest stay listed.
5. "You'd pocket" uses the lower of the last sale and the cheapest listing.
6. New flags: "no recent sales" and "price falling", plus each set's share of box value from no-sale cards.
7. A warning when one card is over 20% of a box's value.
8. Daily checks before a box value is shown: counted cards carry the set's numbering, no unknown labels, no 30%+ overnight jump while the box price holds. A failing set shows "being checked" instead of a number.
9. If TCGplayer's feed didn't refresh, no duplicate day is saved and the page says prices didn't update.
10. New "Rip or hold?" table on every set with a box value: pack, box and case, with what you'd pay delivered, EV, EV after selling, return if you rip, chance a rip profits, and how the sealed product has moved over the last 12 months. The Discord bot's `/box` shows the same.

## 0.5.1 — Grail

- New name: **Grail** (collector slang for the one card you'd chase forever). The dashboard header, browser tab, bot status and setup guide all say Grail. Name the Discord app "Grail" when you set it up; the repo and web address stay `tcg-bot`.

## 0.6.0 — Discord bot ready to install

- **One-command NAS install.** One pasted DSM Task Scheduler command downloads the code, saves the token and IDs, and starts the bot. No Git package, Text Editor or Container Manager project steps. See `deploy/SETUP.md`.
- **Built-in updater.** A small `tcg-bot-updater` container checks GitHub every 5 minutes and restarts the bot when its code changes, with no DSM task needed. Library updates install on restart.
- **Checked before shipping:** CI builds the bot's Docker image and starts it (it reaches the Discord login with a fake token), and builds every message the bot can send from that day's real data: 652 messages across 3 games and 162 sets, all within Discord's limits. Card search answers in under 60 ms.
- Not yet tested against a live Discord server; that happens on your first run.

## 0.6.1

- **What was wrong:** the Nov 6 daily update didn't publish. A Pokémon set was "Above its usual price" for the first time, and on phones that label was wider than its set tile, so the layout check (correctly) refused to publish. Prices were still saved; the site showed the Nov 5 page.
- **What changed:** labels can no longer run past their box (they wrap in tight spots), and set tiles use shorter wording ("Above usual price").
- **Guard:** the layout check now also re-runs every page with every label and price swapped for the longest text it could ever show, so a label that has never appeared yet can't break a real day's publish. It reproduces this failure on the old code and passes on the new.

## 0.6.2

- **What was wrong:** card pictures on the Today page didn't enlarge on hover. The zoom only recognized the small thumbnails in tables.
- **What changed:** on a computer, Today's chase-card tiles, Today's sealed picks and the box art on set pages now zoom on hover too. On a phone, tapping a chase-card tile still opens its details.
