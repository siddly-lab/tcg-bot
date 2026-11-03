"""tcg-bot for Discord: Riftbound prices, box value, sealed tracker, watchlist alerts and collections."""
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
from .store import Store, best_price

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
        day = self.store.latest.get("price_date")
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
            await ch.send(embed=to_embed(fmt.digest_embed(self.store.latest, self.settings.dashboard_url)), silent=True)

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
            label = fmt.clip(f"{c['name']} · {c.get('set') or ''} · {fmt.money(price)}", 100)
            out.append(app_commands.Choice(name=label, value=str(c["id"])))
        return out

    async def set_autocomplete(interaction: discord.Interaction, current: str):
        cur = current.lower()
        return [app_commands.Choice(name=s["name"], value=s["code"]) for s in bot.store.latest.get("sets", [])
                if cur in s["name"].lower() or cur in s["code"].lower()][:25]

    def find(card: str):
        if card.isdigit() and int(card) in bot.store.by_id:
            return bot.store.by_id[int(card)]
        hits = bot.store.search(card, 1)
        return hits[0] if hits else None

    @tree.command(name="price", description="Price, recent change and pull odds for a card or sealed product")
    @app_commands.describe(card="Start typing a card name")
    @app_commands.autocomplete(card=card_autocomplete)
    async def price(interaction: discord.Interaction, card: str):
        c = find(card)
        if not c:
            return await interaction.response.send_message("I couldn't find that card.", ephemeral=True)
        await interaction.response.send_message(embed=to_embed(fmt.card_embed(c)))

    @tree.command(name="box", description="Is a booster box worth opening? Value, odds and chance it pays off")
    @app_commands.describe(set="Which set", paid="What you paid for the box (defaults to today's market price)")
    @app_commands.autocomplete(set=set_autocomplete)
    async def box(interaction: discord.Interaction, set: str, paid: float | None = None):
        s = bot.store.set_by(set)
        if not s:
            return await interaction.response.send_message("I don't know that set.", ephemeral=True)
        await interaction.response.send_message(embed=to_embed(fmt.box_embed(s, paid, dash)))

    @tree.command(name="sets", description="Every set's box price and value at a glance")
    async def sets(interaction: discord.Interaction):
        await interaction.response.send_message(embed=to_embed(fmt.sets_embed(bot.store.latest, dash)))

    @tree.command(name="sealed", description="Sealed box and case prices against MSRP")
    async def sealed(interaction: discord.Interaction):
        await interaction.response.send_message(embed=to_embed(fmt.sealed_embed(bot.store.latest, dash)))

    @tree.command(name="movers", description="Biggest price moves")
    @app_commands.choices(period=[app_commands.Choice(name="Since yesterday", value="day"),
                                  app_commands.Choice(name="This week", value="week")])
    async def movers(interaction: discord.Interaction, period: app_commands.Choice[str] | None = None):
        await interaction.response.send_message(embed=to_embed(fmt.movers_embed(bot.store.latest, period.value if period else "day", dash)))

    @tree.command(name="dashboard", description="Link to the full price dashboard")
    async def dashboard(interaction: discord.Interaction):
        await interaction.response.send_message(dash)

    @tree.command(name="botstatus", description="Bot version and how fresh the prices are")
    async def botstatus(interaction: discord.Interaction):
        L = bot.store.latest
        await interaction.response.send_message(
            f"tcg-bot {__version__} · prices from {L.get('price_date', 'not loaded')} · built {L.get('generated_at', '—')} · "
            f"{L.get('history_days', 0)} days of history · {len(bot.db.watches())} alerts set", ephemeral=True)

    # ---- watchlist
    watch = app_commands.Group(name="watch", description="Price alerts sent to you by DM")

    @watch.command(name="add", description="Alert me when a card's price crosses a number")
    @app_commands.describe(card="Start typing a card name", when="Alert when the price goes above or below", price="Target price in dollars",
                           printing="Which printing (defaults to the more valuable one)")
    @app_commands.autocomplete(card=card_autocomplete)
    @app_commands.choices(when=[app_commands.Choice(name="drops below", value="below"), app_commands.Choice(name="rises above", value="above")],
                          printing=[app_commands.Choice(name="Normal", value="normal"), app_commands.Choice(name="Foil", value="foil")])
    async def watch_add(interaction: discord.Interaction, card: str, when: app_commands.Choice[str], price: float,
                        printing: app_commands.Choice[str] | None = None):
        c = find(card)
        if not c:
            return await interaction.response.send_message("I couldn't find that card.", ephemeral=True)
        pr = printing.value if printing else best_price(c)[1]
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
    @app_commands.describe(card="Start typing a name", qty="How many", printing="Normal or foil", paid_each="What you paid for each, optional")
    @app_commands.autocomplete(card=card_autocomplete)
    @app_commands.choices(printing=[app_commands.Choice(name="Normal", value="normal"), app_commands.Choice(name="Foil", value="foil")])
    async def coll_add(interaction: discord.Interaction, card: str, qty: app_commands.Range[int, 1, 10000] = 1,
                       printing: app_commands.Choice[str] | None = None, paid_each: float | None = None):
        c = find(card)
        if not c:
            return await interaction.response.send_message("I couldn't find that card.", ephemeral=True)
        pr = printing.value if printing else (best_price(c)[1] or "normal")
        bot.db.add_card(interaction.user.id, c["id"], pr, qty, paid_each)
        await interaction.response.send_message(f"Added {qty}× **{c['name']}** ({pr}).", ephemeral=True)

    @coll.command(name="remove", description="Remove cards you sold or traded")
    @app_commands.autocomplete(card=card_autocomplete)
    @app_commands.choices(printing=[app_commands.Choice(name="Normal", value="normal"), app_commands.Choice(name="Foil", value="foil")])
    async def coll_remove(interaction: discord.Interaction, card: str, qty: app_commands.Range[int, 1, 10000] = 1,
                          printing: app_commands.Choice[str] | None = None):
        c = find(card)
        if not c:
            return await interaction.response.send_message("I couldn't find that card.", ephemeral=True)
        pr = printing.value if printing else (best_price(c)[1] or "normal")
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
