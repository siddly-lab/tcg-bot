"""Foil for Discord: Riftbound prices, box value, sealed tracker, watchlist alerts and collections."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import aiohttp
import discord
from discord import app_commands
from discord.ext import tasks

from . import __version__, format as fmt
from .config import Settings, load
from .db import DB
from .store import Store, best_price, with_year

log = logging.getLogger("tcgbot")


def to_embed(d: dict) -> discord.Embed:
    e = discord.Embed(title=d.get("title"), url=d.get("url"), description=d.get("description"), color=d.get("color"))
    for name, value, inline in d.get("fields", []):
        e.add_field(name=fmt.clip(name, 256), value=fmt.clip(value or "—", 1024), inline=inline)
    if d.get("thumbnail"):
        e.set_thumbnail(url=d["thumbnail"])
    return e


class TcgBot(discord.Client):
    def __init__(self, settings: Settings):
        super().__init__(intents=discord.Intents.default())
        self.settings = settings
        self.tree = app_commands.CommandTree(self)
        self.store = Store(Path(settings.db_path).parent / "cache")
        self.db = DB(settings.db_path)
        self.http_session: aiohttp.ClientSession | None = None
        register(self)

    async def setup_hook(self):
        self.http_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60))
        self.store.load_cache()
        try:
            await self.store.refresh(self.http_session, self.settings.data_url)
        except Exception as e:
            log.warning("first data load failed: %s", e)
        if self.settings.guild_id:
            g = discord.Object(id=self.settings.guild_id)
            self.tree.copy_global_to(guild=g)
            await self.tree.sync(guild=g)
            self.tree.clear_commands(guild=None)
            await self.tree.sync()
        else:
            await self.tree.sync()
        self.poll.change_interval(minutes=self.settings.refresh_minutes)
        self.poll.start()

    async def close(self):
        if self.http_session:
            await self.http_session.close()
        await super().close()

    @tasks.loop(minutes=30)
    async def poll(self):
        """Pick up the new daily prices, post the digest once per day, and send watchlist alerts."""
        try:
            await self.store.refresh(self.http_session, self.settings.data_url)
        except Exception as e:
            log.warning("refresh failed: %s", e)
            return
        day = self.store.price_date
        if day and self.db.get("last_digest") != day:
            await self.post_digest()
            self.db.put("last_digest", day)
        await self.run_watches()

    @poll.before_loop
    async def _wait(self):
        await self.wait_until_ready()

    async def channel(self):
        if not self.settings.channel_id:
            return None
        ch = self.get_channel(self.settings.channel_id)
        if ch is None:
            try:
                ch = await self.fetch_channel(self.settings.channel_id)
            except Exception:
                return None
        return ch

    async def post_digest(self):
        ch = await self.channel()
        if ch:
            await ch.send(embed=to_embed(fmt.digest_embed(self.store.summary, self.settings.dashboard_url)), silent=True)

    async def run_watches(self):
        for w in self.db.watches():
            card = self.store.by_id.get(w["card_id"])
            action, price = fmt.check_watch(dict(w), card)
            if action == "rearm":
                self.db.set_armed(w["id"], True)
            if action != "fire":
                continue
            self.db.set_armed(w["id"], False)
            word = "dropped to" if w["direction"] == "below" else "rose to"
            msg = f"🔔 **{card['name']}** {word} {fmt.money(price)} (your alert: {w['direction']} {fmt.money(w['price'])}). {card.get('url') or ''}"
            try:
                user = await self.fetch_user(w["user_id"])
                await user.send(msg)
            except Exception:
                ch = await self.channel()
                if ch:
                    await ch.send(f"<@{w['user_id']}> {msg}")


# ------------------------------------------------------------------ commands

def register(bot: TcgBot):
    tree = bot.tree
    dash = bot.settings.dashboard_url

    async def card_autocomplete(interaction: discord.Interaction, current: str):
        out = []
        for c in bot.store.search(current, 25):
            price, _ = best_price(c)
            label = fmt.clip(f"{c['name']} · {with_year(c.get('set_name') or c.get('set') or '', c.get('set_year'))} · {fmt.money(price)}", 100)
            out.append(app_commands.Choice(name=label, value=str(c["id"])))
        return out

    async def set_autocomplete(interaction: discord.Interaction, current: str):
        cur = current.lower()
        out = []
        for gid, s in bot.store.all_sets():
            label = f"{bot.store.game_name(gid)} · {with_year(s['name'], s.get('year'))} · {s['code']}"
            if cur in label.lower():
                out.append(app_commands.Choice(name=fmt.clip(label, 100), value=f"{gid}:{s['code']}"))
        return out[:25]

    async def game_autocomplete(interaction: discord.Interaction, current: str):
        return [app_commands.Choice(name=g["name"], value=g["id"]) for g in bot.store.games if current.lower() in g["name"].lower()][:25]

    async def printing_autocomplete(interaction: discord.Interaction, current: str):
        c = find(str(getattr(interaction.namespace, "card", "") or ""))
        subs = list((c or {}).get("prices", {}) or {"Normal": None})
        return [app_commands.Choice(name=sub, value=sub) for sub in subs if current.lower() in sub.lower()][:25]

    def find(card: str):
        if card.isdigit() and int(card) in bot.store.by_id:
            return bot.store.by_id[int(card)]
        hits = bot.store.search(card, 1) if card else []
        return hits[0] if hits else None

    def game_summary(game: str | None):
        gid = game or (bot.store.games[0]["id"] if bot.store.games else None)
        return bot.store.summary.get(gid)

    @tree.command(name="price", description="Price, 90-day range and pull odds for a card or sealed product")
    @app_commands.describe(card="Start typing a card or product name")
    @app_commands.autocomplete(card=card_autocomplete)
    async def price(interaction: discord.Interaction, card: str):
        c = find(card)
        if not c:
            return await interaction.response.send_message("I couldn't find that card.", ephemeral=True)
        await interaction.response.send_message(embed=to_embed(fmt.card_embed(c, bot.store.game_name(c.get("game")))))

    @tree.command(name="box", description="Is a booster box worth opening, and is it a good price today?")
    @app_commands.describe(set="Start typing a set name", paid="What you paid for the box (defaults to today's market price)")
    @app_commands.autocomplete(set=set_autocomplete)
    async def box(interaction: discord.Interaction, set: str, paid: float | None = None):
        gid, s = bot.store.set_by(set)
        if not s:
            return await interaction.response.send_message("I don't know that set.", ephemeral=True)
        await interaction.response.defer()
        d = await bot.store.set_detail(bot.http_session, bot.settings.data_url, gid, s)
        link = f"{dash}#/{gid}/set/{s['code']}"
        await interaction.followup.send(embed=to_embed(fmt.box_embed(s, d, paid, link, bot.store.game_name(gid))))

    @tree.command(name="sets", description="Each set's box price and value at a glance, newest first")
    @app_commands.describe(game="Which game (defaults to Riftbound)")
    @app_commands.autocomplete(game=game_autocomplete)
    async def sets(interaction: discord.Interaction, game: str | None = None):
        sm = game_summary(game)
        if not sm:
            return await interaction.response.send_message("Prices aren't loaded yet.", ephemeral=True)
        await interaction.response.send_message(embed=to_embed(fmt.sets_embed(sm, f"{dash}#/{sm['game']}/sets")))

    @tree.command(name="sealed", description="Sealed products at a good price right now")
    @app_commands.describe(game="Which game (defaults to Riftbound)")
    @app_commands.autocomplete(game=game_autocomplete)
    async def sealed(interaction: discord.Interaction, game: str | None = None):
        sm = game_summary(game)
        if not sm:
            return await interaction.response.send_message("Prices aren't loaded yet.", ephemeral=True)
        await interaction.response.send_message(embed=to_embed(fmt.sealed_embed(sm, f"{dash}#/{sm['game']}/sealed")))

    @tree.command(name="movers", description="Biggest price moves")
    @app_commands.describe(game="Which game (defaults to Riftbound)")
    @app_commands.autocomplete(game=game_autocomplete)
    @app_commands.choices(period=[app_commands.Choice(name="Since yesterday", value="day"),
                                  app_commands.Choice(name="This week", value="week")])
    async def movers(interaction: discord.Interaction, period: app_commands.Choice[str] | None = None, game: str | None = None):
        sm = game_summary(game)
        if not sm:
            return await interaction.response.send_message("Prices aren't loaded yet.", ephemeral=True)
        await interaction.response.send_message(embed=to_embed(fmt.movers_embed(sm, period.value if period else "day", f"{dash}#/{sm['game']}/movers")))

    @tree.command(name="dashboard", description="Link to the full price dashboard")
    async def dashboard(interaction: discord.Interaction):
        await interaction.response.send_message(dash)

    @tree.command(name="botstatus", description="Bot version and how fresh the prices are")
    async def botstatus(interaction: discord.Interaction):
        games = ", ".join(f"{g['name']} ({g['sets']} sets)" for g in bot.store.games) or "not loaded"
        await interaction.response.send_message(
            f"Foil {__version__} · prices from {bot.store.price_date or 'not loaded'} · {games} · "
            f"{len(bot.db.watches())} alerts set", ephemeral=True)

    # ---- watchlist
    watch = app_commands.Group(name="watch", description="Price alerts sent to you by DM")

    @watch.command(name="add", description="Alert me when a card or sealed product's price crosses a number")
    @app_commands.describe(card="Start typing a name", when="Alert when the price goes above or below", price="Target price in dollars",
                           printing="Which printing (defaults to the most valuable one)")
    @app_commands.autocomplete(card=card_autocomplete, printing=printing_autocomplete)
    @app_commands.choices(when=[app_commands.Choice(name="drops below", value="below"), app_commands.Choice(name="rises above", value="above")])
    async def watch_add(interaction: discord.Interaction, card: str, when: app_commands.Choice[str], price: float,
                        printing: str | None = None):
        c = find(card)
        if not c:
            return await interaction.response.send_message("I couldn't find that card.", ephemeral=True)
        pr = printing or best_price(c)[1]
        now, _ = best_price(c, pr)
        wid = bot.db.add_watch(interaction.user.id, c["id"], pr, when.value, price)
        await interaction.response.send_message(
            f"Alert #{wid} set: **{c['name']}** ({pr}) {when.name} {fmt.money(price)}. It's {fmt.money(now)} today. "
            f"I check after each daily price update and DM you once when it crosses.", ephemeral=True)

    @watch.command(name="list", description="Your price alerts")
    async def watch_list(interaction: discord.Interaction):
        rows = bot.db.watches(interaction.user.id)
        if not rows:
            return await interaction.response.send_message("No alerts yet. Add one with /watch add.", ephemeral=True)
        lines = []
        for w in rows:
            c = bot.store.by_id.get(w["card_id"])
            now, _ = best_price(c, w["printing"]) if c else (None, None)
            lines.append(f"#{w['id']} {c['name'] if c else w['card_id']} ({w['printing']}) {w['direction']} {fmt.money(w['price'])}, now {fmt.money(now)}"
                         f"{'' if w['armed'] else ' · already sent, resets when it moves back'}")
        await interaction.response.send_message(fmt.clip("\n".join(lines), 1900), ephemeral=True)

    @watch.command(name="remove", description="Delete a price alert")
    @app_commands.describe(alert="The alert number from /watch list")
    async def watch_remove(interaction: discord.Interaction, alert: int):
        ok = bot.db.remove_watch(interaction.user.id, alert)
        await interaction.response.send_message("Removed." if ok else "No alert with that number.", ephemeral=True)

    tree.add_command(watch)

    # ---- collection
    coll = app_commands.Group(name="collection", description="Track what you own and what it's worth")

    @coll.command(name="add", description="Add cards or sealed product you own")
    @app_commands.describe(card="Start typing a name", qty="How many", printing="Which printing (defaults to the most valuable one)", paid_each="What you paid for each, optional")
    @app_commands.autocomplete(card=card_autocomplete, printing=printing_autocomplete)
    async def coll_add(interaction: discord.Interaction, card: str, qty: app_commands.Range[int, 1, 10000] = 1,
                       printing: str | None = None, paid_each: float | None = None):
        c = find(card)
        if not c:
            return await interaction.response.send_message("I couldn't find that card.", ephemeral=True)
        pr = printing or best_price(c)[1] or "Normal"
        bot.db.add_card(interaction.user.id, c["id"], pr, qty, paid_each)
        await interaction.response.send_message(f"Added {qty}× **{c['name']}** ({pr}).", ephemeral=True)

    @coll.command(name="remove", description="Remove cards you sold or traded")
    @app_commands.autocomplete(card=card_autocomplete, printing=printing_autocomplete)
    async def coll_remove(interaction: discord.Interaction, card: str, qty: app_commands.Range[int, 1, 10000] = 1,
                          printing: str | None = None):
        c = find(card)
        if not c:
            return await interaction.response.send_message("I couldn't find that card.", ephemeral=True)
        pr = printing or best_price(c)[1] or "Normal"
        bot.db.add_card(interaction.user.id, c["id"], pr, -qty)
        await interaction.response.send_message(f"Removed {qty}× **{c['name']}** ({pr}).", ephemeral=True)

    @coll.command(name="value", description="What your collection is worth today")
    async def coll_value(interaction: discord.Interaction):
        rows = [dict(r) for r in bot.db.collection(interaction.user.id)]
        await interaction.response.send_message(embed=to_embed(fmt.collection_embed(rows, bot.store.by_id)), ephemeral=True)

    tree.add_command(coll)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    s = load()
    if not s.token:
        raise SystemExit("DISCORD_TOKEN is missing from .env")
    TcgBot(s).run(s.token, log_handler=None)


if __name__ == "__main__":
    main()
