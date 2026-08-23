"""Currency metadata ID -> short ID / display name / icon mapping.

The Currency Exchange API identifies currencies by base item metadata IDs
(e.g. "Metadata/Items/Currency/CurrencyRerollRare" = Chaos Orb), while the
trade site uses short IDs ("chaos").  This module builds a mapping from:

1. A hardcoded map of the most common currencies, researched against the
   official Currency Exchange API and poe.ninja.
2. An optional map from the supported trade-site ``/api/trade/data/static``
   endpoint.  This endpoint is supported by the project owner but is not
   listed as an official GGG Developer API resource.
3. A slug-fallback: metadata IDs (or any unknown ID) get a human-readable
   display name via the shared slug formatter.

"""

import base64
import json
import os
import re

import httpx

STATIC_URL = "https://www.pathofexile.com/api/trade/data/static"  # supported trade-site endpoint; not official Developer API

# (metadata ID, display name) for the most common currencies, per research.
HARDCODED = [
    ("Metadata/Items/Currency/CurrencyRerollRare", "Chaos Orb"),
    ("Metadata/Items/Currency/CurrencyModValues", "Divine Orb"),
    ("Metadata/Items/Currency/CurrencyCorrupt", "Vaal Orb"),
    ("Metadata/Items/Currency/CurrencyVaal", "Vaal Orb"),
    ("Metadata/Items/Currency/CurrencyPortal", "Portal Scroll"),
    ("Metadata/Items/Currency/CurrencyIdentification", "Scroll of Wisdom"),
    ("Metadata/Items/Currency/CurrencyUpgradeToRare", "Orb of Alchemy"),
    ("Metadata/Items/Currency/CurrencyGemQuality", "Gemcutter's Prism"),
    ("Metadata/Items/Currency/CurrencyAddModToRare", "Exalted Orb"),
    ("Metadata/Items/Currency/CurrencyRerollSocketLinks", "Orb of Fusing"),
    ("Metadata/Items/Currency/CurrencyRerollSocketColours", "Chromatic Orb"),
    ("Metadata/Items/Currency/CurrencyRerollSocketNumbers", "Jeweller's Orb"),
    ("Metadata/Items/Currency/CurrencyUpgradeRandomly", "Orb of Chance"),
    ("Metadata/Items/Currency/CurrencyMapQuality", "Cartographer's Chisel"),
    ("Metadata/Items/Currency/CurrencyConvertToNormal", "Orb of Scouring"),
    ("Metadata/Items/Currency/CurrencyImplicitMod", "Blessed Orb"),
    ("Metadata/Items/Currency/CurrencyPassiveSkillRefund", "Orb of Regret"),
    ("Metadata/Items/Currency/CurrencyUpgradeMagicToRare", "Regal Orb"),
    ("Metadata/Items/Currency/CurrencyDuplicate", "Mirror of Kalandra"),
    ("Metadata/Items/Currency/CurrencyRerollMagic", "Orb of Alteration"),
    ("Metadata/Items/Currency/CurrencyUpgradeToMagic", "Orb of Transmutation"),
    ("Metadata/Items/Currency/CurrencyAddModToMagic", "Orb of Augmentation"),
    ("Metadata/Items/Currency/CurrencyArmourQuality", "Armourer's Scrap"),
    ("Metadata/Items/Currency/CurrencyWeaponQuality", "Blacksmith's Whetstone"),
    ("Metadata/Items/Currency/CurrencyFlaskQuality", "Glassblower's Bauble"),
]


def _format_slug(slug: str) -> str:
    """Metadata ID -> readable fallback, including CamelCase legacy IDs."""
    tail = slug.replace("-", "_").split("/")[-1]
    tail = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", tail)
    tail = re.sub(r"(?<=[A-Za-z])(?=[0-9])", " ", tail)
    parts = re.split(r"[_\s]+", tail)
    small = {"of", "the", "a", "an", "and", "or", "in", "on", "to", "for"}
    return " ".join(
        word.lower() if (word.lower() in small and i > 0) else word.capitalize()
        for i, word in enumerate(parts)
    )


def _short_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _normalize_mapping(mapping: dict) -> dict:
    """Upgrade legacy numeric-key caches to metadata-path keys used by CX rows."""
    normalized = {}
    for key, value in mapping.items():
        entry = dict(value)
        entry_id = entry.get("id", "")
        if entry_id.startswith("Metadata/Items/"):
            meta = entry_id
            entry["id"] = _short_slug(entry.get("name") or _format_slug(meta))
        else:
            meta = key
        normalized[meta] = entry
    return normalized


def _decode_image_metadata(image_url: str) -> str | None:
    """Extract the base item metadata path embedded in a static image URL."""
    m = re.search(r"/gen/image/([A-Za-z0-9_-]+)", image_url or "")
    if not m:
        return None
    raw = m.group(1)
    try:
        payload = json.loads(base64.b64decode(raw + "=" * (-len(raw) % 4)))
        meta = payload[2].get("f")
        if meta:
            return "Metadata/Items/" + meta.replace("2DItems/", "", 1)
    except Exception:
        # Optional third-party image metadata is never allowed to break CX reads.
        return None
    return None


async def _fetch_static_entries() -> dict:
    """Fetch /api/trade/data/static and decode metadata IDs from images."""
    out = {}
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(
                STATIC_URL,
                headers={
                    "User-Agent": os.environ.get(
                        "DEUSCFO_TRADE_USER_AGENT",
                        "DeusCFO/3.0 (+https://github.com/MetzeVanDeus/deus-cfo)",
                    )
                },
            )
            if resp.status_code == 200:
                for section in resp.json().get("result", []):
                    for e in section.get("entries", []):
                        meta = _decode_image_metadata(e.get("image", ""))
                        if meta:
                            out[meta] = {
                                "id": e.get("id", ""),
                                "name": e.get("text", ""),
                                "icon": e.get("image", ""),
                            }
    except Exception:
        # The live trade-site endpoint is optional; use hardcoded/slug fallbacks.
        pass
    return out




async def build_currency_mapping() -> dict:
    """
    Returns {metadata_id: {"id": short_id, "name": display, "icon": url}}.

    Short IDs come from /api/trade/data/static where the image decode
    succeeds; otherwise "id" is derived from the metadata path tail and the
    icon is empty.  The result is cached to cx_currency_map.json.
    """
    # Live static metadata is optional; hardcoded and slug fallbacks remain valid.
    static_entries = await _fetch_static_entries()

    mapping = {}
    for meta, name in HARDCODED:
        mapping[meta] = {"id": meta.split("/")[-1].lower(), "name": name, "icon": ""}
    for meta, entry in static_entries.items():
        mapping[meta] = entry
    return mapping

def _mapping_path() -> str:
    data_dir = os.environ.get("DEUSCFO_DATA_DIR", "").strip()
    if data_dir:
        return os.path.join(os.path.abspath(data_dir), "cx_currency_map.json")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "cx_currency_map.json")


def load_currency_mapping() -> dict:
    """Load the cached mapping JSON (empty dict if absent)."""
    try:
        with open(_mapping_path(), encoding="utf-8") as f:
            return _normalize_mapping(json.load(f))
    except (OSError, json.JSONDecodeError):
        return {}


def save_currency_mapping(mapping: dict) -> None:
    path = _mapping_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)


def resolve_name(mapping: dict, metadata_id: str) -> str:
    """Display name for a metadata ID: mapping, else slug fallback."""
    entry = mapping.get(metadata_id)
    if entry and entry.get("name"):
        return entry["name"]
    return _format_slug(metadata_id)


def resolve_short_id(mapping: dict, metadata_id: str) -> str:
    entry = mapping.get(metadata_id)
    if entry and entry.get("id"):
        return entry["id"]
    # strip the "Currency" prefix off the path tail: CurrencyRerollRare -> rerollrare
    tail = metadata_id.split("/")[-1]
    for prefix in ("Currency", "CurrencyVaal", "MapFragments"):
        if tail.startswith(prefix) and len(tail) > len(prefix):
            return tail[len(prefix):].lower()
    return tail.lower()


def resolve_query_ids(mapping: dict, stored_ids, query: str) -> set[str]:
    """Resolve metadata, short ID, or readable-name slug against stored CX IDs."""
    wanted = query.lower()
    matches = {query}
    for metadata_id in stored_ids:
        aliases = {
            metadata_id.lower(),
            resolve_short_id(mapping, metadata_id).lower(),
            _short_slug(resolve_name(mapping, metadata_id)),
        }
        if wanted in aliases:
            matches.add(metadata_id)
    return matches


async def ensure_currency_mapping() -> dict:
    """Return the mapping, (re)building it if the cache is missing."""
    cached = load_currency_mapping()
    if cached:
        return cached
    fresh = await build_currency_mapping()
    save_currency_mapping(fresh)
    return fresh
