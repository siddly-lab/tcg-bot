"""Per-game rules: how a game's products are named, which are sealed, and which groups are sets."""
from importlib import import_module


def load(module: str):
    return import_module(f"tcg.games.{module}")


def ext(p: dict, key: str):
    for e in p.get("extendedData") or []:
        if e.get("name") == key:
            return e.get("value")
    return None


import re as _re

# "(118)", "(OP14-084)", "(P-084)", "(R02a)", "(271)": just card numbers, not version labels
CODE_TAG = _re.compile(r"^(\d{1,3}[a-z]?|[A-Z]{1,5}\d{0,2}-\d{3}|R\d+[ab]?|T\d+)$")


def labels(name: str) -> list[str]:
    """Version labels in a product name, lower-cased, without card-number tags."""
    return [t.strip().lower() for t in _re.findall(r"\(([^)]*)\)", name or "") if not CODE_TAG.match(t.strip())]


def has_unknown_label(name: str, known: set[str]) -> bool:
    return any(t not in known for t in labels(name))
