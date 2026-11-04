"""Per-game rules: how a game's products are named, which are sealed, and which groups are sets."""
from importlib import import_module


def load(module: str):
    return import_module(f"tcg.games.{module}")


def ext(p: dict, key: str):
    for e in p.get("extendedData") or []:
        if e.get("name") == key:
            return e.get("value")
    return None
