"""Settings from the .env file next to docker-compose.yml."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Settings:
    token: str
    guild_id: int | None
    channel_id: int | None
    data_url: str
    dashboard_url: str
    db_path: str
    refresh_minutes: int


def load() -> Settings:
    def num(k):
        v = os.getenv(k, "").strip()
        return int(v) if v.isdigit() else None
    dash = os.getenv("DASHBOARD_URL", "https://siddly-lab.github.io/tcg-bot/").rstrip("/") + "/"
    return Settings(
        token=os.getenv("DISCORD_TOKEN", "").strip(),
        guild_id=num("GUILD_ID"),
        channel_id=num("CHANNEL_ID"),
        data_url=os.getenv("DATA_URL", dash + "data/").rstrip("/") + "/",
        dashboard_url=dash,
        db_path=os.getenv("DB_PATH", "/app/data/tcgbot.sqlite3"),
        refresh_minutes=int(os.getenv("REFRESH_MINUTES", "30")),
    )
