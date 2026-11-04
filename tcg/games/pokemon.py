"""Pokémon: rules for TCGplayer's Pokémon catalog (category 3), checked against the live feed.

- Sealed products have no Rarity ("Delta Reign Booster Box", "... Elite Trainer Box").
- Card names often end in " - 140/103"; the number is also in the Number field, so it's dropped.
- Rarity is spelled out: Common, Uncommon, Rare, Double Rare, Ultra Rare, Illustration Rare,
  Special Illustration Rare, Hyper Rare, Mega Hyper Rare, plus older ones (Holo Rare, Secret Rare...).
- Printings are Normal, Holofoil and Reverse Holofoil.
"""
from __future__ import annotations

import re

from . import ext, has_unknown_label

PACK_BUCKETS = ("Common", "Uncommon", "Rare", "Double Rare", "Ultra Rare", "Illustration Rare",
                "Special Illustration Rare", "Hyper Rare", "Mega Hyper Rare")
LABELS = {b: b + "s" for b in PACK_BUCKETS}
LABELS.update({"Common": "Commons", "Uncommon": "Uncommons", "Rare": "Rares",
               "Special": "Special versions with unknown odds (left out)"})
BUCKET_PRINTING = {"Double Rare": "Holofoil", "Ultra Rare": "Holofoil", "Illustration Rare": "Holofoil",
                   "Special Illustration Rare": "Holofoil", "Hyper Rare": "Holofoil", "Mega Hyper Rare": "Holofoil"}

SEALED_LABELS = {"box": "Booster box", "case": "Booster box case", "etb": "Elite Trainer Box", "bundle": "Booster bundle",
                 "pack": "Booster pack", "sleeved_pack": "Sleeved booster pack", "other": "Other sealed"}

KNOWN_LABELS: set[str] = set()  # Pokémon pack cards carry no version labels; any label means unknown odds

CARD_RARITIES = set(PACK_BUCKETS) | {"Holo Rare", "Secret Rare", "Shiny Rare", "Shiny Ultra Rare", "ACE SPEC Rare",
                                     "Rare Holo", "Amazing Rare", "Radiant Rare", "Rare BREAK", "Prism Rare",
                                     "Classic Collection", "Promo", "Black White Rare"}


def is_sealed(p: dict) -> bool:
    return ext(p, "Rarity") is None and ext(p, "Number") is None


def sealed_type(name: str) -> str:
    n = name.lower()
    # "Enhanced Booster Box" and half boxes have different contents, so they're tracked as other sealed
    if any(w in n for w in ("half booster box", "enhanced booster", "mini", "blister", "build & battle", "art bundle", "display")):
        return "other"
    if "booster box case" in n:
        return "case"
    if "elite trainer box" in n:
        return "other" if "case" in n or "pokemon center" in n else "etb"
    if "booster bundle" in n:
        return "other" if "case" in n else "bundle"
    if "booster box" in n:
        return "box"
    if "sleeved booster" in n and "case" not in n:
        return "sleeved_pack"
    if n.endswith("booster pack") or re.search(r"booster pack( \[.*\])?$", n):
        return "pack"
    return "other"


def card_name(name: str) -> str:
    return re.sub(r"\s+-\s+[A-Za-z]*\d+[a-z]?(/[A-Za-z]*\d+)?\s*$", "", name).strip()


def classify_card(p: dict) -> str | None:
    rarity = ext(p, "Rarity")
    if rarity in PACK_BUCKETS:
        # any version label (stamps, special prints) means odds we don't know
        return "Special" if has_unknown_label(card_name(p.get("name") or ""), set()) else rarity
    return None


def era_of(release: str, eras: list[dict]) -> dict | None:
    for e in eras:
        if release >= e["from"]:
            return e
    return None


def code_of(g: dict) -> str:
    ab = (g.get("abbreviation") or "").strip()
    return ab or re.sub(r"[^A-Z0-9]", "", g["name"].upper())[:6]


def sets_from_groups(groups: list[dict], products: dict[int, list[dict]], cfg: dict) -> list[dict]:
    """Every group that sells a booster box or pack is a set. Older eras get sealed tracking only."""
    pattern = re.compile(cfg["modeled_set_pattern"])
    out, seen = [], set()
    for g in groups:
        prods = products.get(g["groupId"], [])
        kinds = {sealed_type(p["name"]) for p in prods if is_sealed(p)}
        if not kinds & {"box", "pack", "etb", "bundle"}:
            continue
        release = (g.get("publishedOn") or "")[:10]
        era = era_of(release, cfg["eras"]) or {}
        code = code_of(g)
        if code in seen:
            code = f"{code}{g['groupId']}"
        seen.add(code)
        modeled = bool(pattern.match(g["name"])) and era.get("template")
        out.append({"code": code, "name": re.sub(r"^(SV|ME|SWSH)\d+:\s*|^(SV|ME|SWSH|SM|XY):\s*|^(SWSH|SM|XY) - ", "", g["name"]).strip(),
                    "full_name": g["name"], "group_id": g["groupId"], "release": release,
                    "era": era.get("name"), "modeled": bool(modeled), "template": era.get("template") if modeled else None,
                    "msrp": era.get("msrp") or {}, "print_status": (cfg.get("print_status") or {}).get(code)})
    return out


def unknown_sets(groups, products, cfg, known_ids):
    return []
