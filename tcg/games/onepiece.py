"""One Piece Card Game: rules for TCGplayer's One Piece catalog (category 68), checked against the live feed.

- Sealed products have no Rarity ("The Time of Battle Booster Box", "Romance Dawn - Booster Box (Wave 1 - Blue)").
- Rarity codes: C, UC, R, SR, SEC, L (leader), TR (treasure rare), plus DON!! and PR.
- Special versions say what they are in the name: "(Alternate Art)" / "(Parallel)", "(SP)", "(Manga)",
  "(TR)", "(Super Alternate Art)", "(Super Leader Alternate Art)", plus extras such as "(Box Topper)".
- Printings are Normal and Foil.
"""
from __future__ import annotations

import re

from . import ext

PACK_BUCKETS = ("C", "UC", "R", "L", "SR", "SEC", "AltArt", "SECAlt", "SP", "TR", "Manga")
LABELS = {"C": "Commons", "UC": "Uncommons", "R": "Rares", "L": "Leaders", "SR": "Super Rares", "SEC": "Secret Rares",
          "AltArt": "Alternate arts", "SECAlt": "Secret Rare alternate arts", "SP": "SP cards", "TR": "Treasure Rares",
          "Manga": "Manga rares", "Special": "Special versions with unknown odds (left out)"}
BUCKET_PRINTING = {b: "Foil" for b in ("SR", "SEC", "AltArt", "SECAlt", "SP", "TR", "Manga")}
SEALED_LABELS = {"box": "Booster box", "case": "Booster box case", "pack": "Booster pack",
                 "sleeved_pack": "Sleeved booster pack", "other": "Other sealed"}
EXTRAS = ("box topper", "pandaman", "heroine leader", "gold stamped", "kentaro yabuki", "pre-release", "serial")


def is_sealed(p: dict) -> bool:
    return ext(p, "Rarity") is None and ext(p, "Number") is None


def sealed_type(name: str) -> str:
    n = name.lower()
    if "art bundle" in n or "display" in n or "double pack" in n:
        return "other"
    if "booster box case" in n:
        return "case"
    if "booster box" in n:
        return "box"
    if "sleeved booster pack" in n:
        return "sleeved_pack"
    if re.search(r"booster pack$", n):
        return "pack"
    return "other"


def card_name(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip()


KNOWN_TAGS = {"alternate art", "parallel", "manga", "sp", "tr"}
CODE_TAG = re.compile(r"^(\d{3}|[A-Z]{1,4}\d{0,2}-\d{3})$")  # "(118)", "(OP14-084)", "(P-084)": just a card number


def tags(name: str) -> list[str]:
    return [t.strip() for t in re.findall(r"\(([^)]*)\)", name)]


def classify_card(p: dict) -> str | None:
    """Only versions with known odds go into the box math. Any other label in the name
    (Super Alternate Art, Wanted Poster, Gold-Stamped Signature, Box Topper...) is left out."""
    name = p.get("name") or ""
    rarity = ext(p, "Rarity")
    if rarity in (None, "DON!!", "PR"):
        return None
    labels = [t.lower() for t in tags(name) if not CODE_TAG.match(t)]
    if any(x in name.lower() for x in EXTRAS):
        return None
    if any(t not in KNOWN_TAGS for t in labels):
        return "Special"
    if "manga" in labels:
        return "Manga"
    if rarity == "TR" or "tr" in labels:
        return "TR"
    if "sp" in labels:
        return "SP"
    if "alternate art" in labels or "parallel" in labels:
        return "SECAlt" if rarity == "SEC" else "AltArt"
    if rarity in ("C", "UC", "R", "L", "SR", "SEC"):
        return rarity
    return None


def code_of(g: dict) -> str:
    ab = (g.get("abbreviation") or "").strip()
    return ab or re.sub(r"[^A-Z0-9]", "", g["name"].upper())[:6]


def sets_from_groups(groups: list[dict], products: dict[int, list[dict]], cfg: dict) -> list[dict]:
    """Every group that sells a booster box or pack is a set. Box value only for main OP boosters."""
    pattern = re.compile(cfg["modeled_set_pattern"])
    out, seen = [], set()
    for g in groups:
        prods = products.get(g["groupId"], [])
        kinds = {sealed_type(p["name"]) for p in prods if is_sealed(p)}
        if not kinds & {"box", "pack"}:
            continue
        code = code_of(g)
        if code in seen:
            code = f"{code}-{g['groupId']}"
        seen.add(code)
        modeled = bool(pattern.match(code))
        out.append({"code": code, "name": g["name"].strip(), "full_name": g["name"], "group_id": g["groupId"],
                    "release": (g.get("publishedOn") or "")[:10], "era": None, "modeled": modeled,
                    "template": "booster" if modeled else None, "msrp": dict(cfg.get("msrp") or {}),
                    "print_status": (cfg.get("print_status") or {}).get(code)})
    return out


def unknown_sets(groups, products, cfg, known_ids):
    return []
