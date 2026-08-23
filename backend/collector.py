"""Periodic snapshot collection from poe.ninja into SQLite."""

import argparse
import asyncio
import json
import logging
import math
import os
from datetime import datetime, timezone
from pathlib import Path
import httpx

import cx_collector
import database

log = logging.getLogger("deuscfo.collector")

POE_NINJA_BASE = "https://poe.ninja"
EXCHANGE_URL = f"{POE_NINJA_BASE}/poe1/api/economy/exchange/current/overview"
STASH_URL = f"{POE_NINJA_BASE}/poe1/api/economy/stash/current/item/overview"

TRADE_API_BASE = "https://www.pathofexile.com/api/trade"
# These are trade-site endpoints, not entries in GGG's official Developer API reference.
TRADE_DEPTH_ENV = "DEUSCFO_TRADE_DEPTH"
TRADE_DEPTH_LIMIT_ENV = "DEUSCFO_TRADE_DEPTH_LIMIT"
TRADE_REQUEST_DELAY_ENV = "DEUSCFO_TRADE_REQUEST_DELAY"
TRADE_USER_AGENT_ENV = "DEUSCFO_TRADE_USER_AGENT"
TRADE_FEE_ENV = "DEUSCFO_TRADE_FEE_RATE"
CONFIG_PATH = Path(os.environ["DEUSCFO_CONFIG_PATH"]) if os.environ.get("DEUSCFO_CONFIG_PATH") else Path(__file__).resolve().parent.parent / "deuscfo.config.json"

# poe.ninja 'type' param per category (same mapping as main.py)
_EXCHANGE_TYPES = {
    category: category
    for category in (
        "Currency", "Fragment", "Scarab", "Essence", "Oil", "Fossil",
        "DeliriumOrb", "DivinationCard",
    )
}
_STASH_TYPES = {
    category: category
    for category in (
        "SkillGem", "UniqueWeapon", "UniqueArmour", "UniqueAccessory",
        "UniqueJewel", "UniqueFlask", "Map", "BlightedMap", "UniqueMap",
    )
}
_COLLECTION_TYPES = {
    **_EXCHANGE_TYPES,
    # Deterministic div-card rewards need a real stash-backed price.
    "UniqueAccessory": "UniqueAccessory",
}


def trade_depth_enabled() -> bool:
    return os.environ.get(TRADE_DEPTH_ENV, "").casefold() in {"1", "true", "yes", "on"}


def _trade_limit(value: int | None = None) -> int:
    raw = value if value is not None else os.environ.get(TRADE_DEPTH_LIMIT_ENV, "20")
    try:
        return max(1, min(50, int(raw)))
    except (TypeError, ValueError):
        return 20


def _trade_delay() -> float:
    try:
        value = float(os.environ.get(TRADE_REQUEST_DELAY_ENV, "0.25"))
    except ValueError:
        return 0.25
    return value if math.isfinite(value) and 0 <= value <= 10 else 0.25


def configured_league(override: str | None = None) -> str:
    """Read the shared league each cycle unless the caller supplied an override."""
    if override:
        return override
    try:
        with CONFIG_PATH.open(encoding="utf-8") as handle:
            value = json.load(handle).get("league")
        if isinstance(value, str) and value.strip():
            return value.strip()
    except (OSError, json.JSONDecodeError, AttributeError):
        pass
    return os.environ.get("DEUSCFO_LEAGUE", "").strip()


def _trade_fee() -> float:
    try:
        value = float(os.environ.get(TRADE_FEE_ENV, "0"))
    except ValueError:
        return 0.0
    return value if math.isfinite(value) and 0 <= value < 1 else 0.0


def _trade_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "User-Agent": os.environ.get(
            TRADE_USER_AGENT_ENV,
            "DeusCFO/3.0 (+https://github.com/MetzeVanDeus/deus-cfo)",
        ),
    }
PERSISTED_CATEGORIES = frozenset(_COLLECTION_TYPES)


def _format_slug(slug: str) -> str:
    """Turn 'abyss-scarab-of-descending' into 'Abyss Scarab of Descending'."""
    parts = slug.replace("_", "-").split("-")
    small = {"of", "the", "a", "an", "and", "or", "in", "on", "to", "for"}
    return " ".join(
        w.lower() if (w.lower() in small and i > 0) else w.capitalize()
        for i, w in enumerate(parts)
    )


def stash_item_id(line: dict) -> str:
    """Return poe.ninja's stable stash identity, including variant details."""
    return str(line.get("detailsId") or line.get("id", ""))


def _finite_number(value, default=0):
    """Return a finite numeric API value, or None when malformed."""
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(float(value)) else None


def _normalize(line: dict, league: str, category: str, is_exchange: bool) -> dict | None:
    """Map one API line into a direct observation, rejecting malformed rows."""
    if not isinstance(line, dict):
        return None
    if is_exchange:
        item_id = line.get("id", "")
        item_name = _format_slug(item_id) if isinstance(item_id, str) else ""
        price = _finite_number(line.get("primaryValue"), 0)
        volume = _finite_number(line.get("volumePrimaryValue"), 0)
        record = {
            "league": league,
            "category": category,
            "item_id": item_id,
            "item_name": item_name,
            "variant": "",
            "price_chaos": price,
            "volume": volume,
            "listing_count": 0,
            "icon": "",
            "source": "poe.ninja",
            "observation_type": "DIRECT_OBSERVATION",
            "confidence_grade": "B",
        }
    else:
        item_id = stash_item_id(line)
        price = _finite_number(line.get("chaosValue"), 0)
        volume = _finite_number(line.get("listingCount") or line.get("count"), 0)
        listing_count = _finite_number(line.get("listingCount"), 0)
        record = {
            "league": league,
            "category": category,
            "item_id": item_id,
            "item_name": line.get("name") if isinstance(line.get("name"), str) else "Unknown",
            "variant": line.get("variant") if isinstance(line.get("variant"), str) else "",
            "price_chaos": price,
            "volume": volume,
            "listing_count": listing_count,
            "icon": line.get("icon") if isinstance(line.get("icon"), str) else "",
            "source": "poe.ninja",
            "observation_type": "DIRECT_OBSERVATION",
            "confidence_grade": "B",
        }
    if (
        not isinstance(item_id, str)
        or not item_id
        or price is None
        or volume is None
        or record["listing_count"] is None
    ):
        return None
    quote = database.validate_execution_quote(line.get("execution_quote"))
    if quote is not None:
        record["execution_quote"] = quote
    return record


def _snapshot_records(data, league: str, category: str, is_exchange: bool) -> list[dict] | None:
    """Normalize a poe.ninja payload; None means the envelope was malformed."""
    if not isinstance(data, dict) or not isinstance(data.get("lines"), list):
        return None
    records = []
    for line in data["lines"]:
        record = _normalize(line, league, category, is_exchange)
        if record is not None and record["price_chaos"] > 0:
            records.append(record)
    return records

def _trade_price(entry: dict, chaos_per_divine: float) -> tuple[float, float] | None:
    listing = entry.get("listing") if isinstance(entry, dict) else None
    price = listing.get("price") if isinstance(listing, dict) else None
    if not isinstance(price, dict):
        return None
    amount, currency = price.get("amount"), str(price.get("currency", "")).casefold()
    if not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount <= 0:
        return None
    multiplier = 1.0 if currency == "chaos" else chaos_per_divine if currency == "divine" else 0.0
    if multiplier <= 0:
        return None
    item = entry.get("item") if isinstance(entry, dict) else None
    quantity = item.get("stackSize", 1) if isinstance(item, dict) else 1
    if not isinstance(quantity, (int, float)) or quantity <= 0:
        quantity = 1
    return float(amount) * multiplier, float(quantity)


def _trade_quote(entries: list[dict], *, side: str, chaos_per_divine: float) -> dict | None:
    levels: dict[float, float] = {}
    observed = []
    for entry in entries:
        value = _trade_price(entry, chaos_per_divine)
        if value is None:
            continue
        price, quantity = value
        levels[price] = levels.get(price, 0.0) + quantity
        indexed = (entry.get("listing") or {}).get("indexed") if isinstance(entry, dict) else None
        if isinstance(indexed, str) and indexed:
            observed.append(indexed)
    if not levels:
        return None
    return {
        f"{side}_levels": [
            {"price": price, "quantity": quantity}
            for price, quantity in sorted(levels.items())
        ],
        "fee_rate": _trade_fee(),
        "observed_at": max(observed) if observed else datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "confidence": 0.6,
        "source": "pathofexile_trade_api",
    }


class TradeDepthAdapter:
    """Opt-in, bounded adapter for the trade website (not an official API claim)."""

    def __init__(self, *, limit: int | None = None) -> None:
        self.limit = _trade_limit(limit)
    async def quote(
        self,
        client: httpx.AsyncClient,
        league: str,
        item_name: str,
        *,
        side: str,
        chaos_per_divine: float,
    ) -> dict | None:
        if side != "buy":
            return None
        try:
            response = await client.post(
                f"{TRADE_API_BASE}/search/{league}",
                json={
                    "query": {"status": {"option": "online"}, "name": item_name},
                    "sort": {"price": "asc"},
                },
            )
            if response.status_code != 200:
                return None
            search = response.json()
            search_id = search.get("id") if isinstance(search, dict) else None
            listing_ids = search.get("result", []) if isinstance(search, dict) else []
            if not isinstance(search_id, str) or not isinstance(listing_ids, list):
                return None
            listing_ids = [item for item in listing_ids[:self.limit] if isinstance(item, str) and item]
            if not listing_ids:
                return None
            response = await client.get(
                f"{TRADE_API_BASE}/fetch/{','.join(listing_ids)}",
                params={"query": search_id},
            )
            if response.status_code != 200:
                return None
            payload = response.json()
            entries = payload.get("result", []) if isinstance(payload, dict) else []
            if not isinstance(entries, list):
                return None
            return _trade_quote(entries, side="buy", chaos_per_divine=chaos_per_divine)
        except Exception:
            # Trade-site outages and malformed payloads must never become evidence.
            log.warning("trade depth request failed for %s", item_name, exc_info=True)
            return None

    async def collect(
        self,
        league: str,
        recipes: list[dict],
        *,
        chaos_per_divine: float = 0.0,
    ) -> dict[str, dict]:
        items = {recipe["card_market_key"]: recipe["card"] for recipe in recipes}
        quotes = {}
        async with httpx.AsyncClient(timeout=20, headers=_trade_headers()) as client:
            for index, (key, name) in enumerate(items.items()):
                if index:
                    await asyncio.sleep(_trade_delay())
                quote = await self.quote(
                    client, league, name, side="buy", chaos_per_divine=chaos_per_divine
                )
                if quote is not None:
                    quotes[key] = quote
        return quotes



def _quote_snapshot(key: str, name: str, quote: dict, *, league: str) -> dict | None:
    category, separator, item_id = key.partition(":")
    if not separator:
        return None
    levels = quote.get("buy_levels") or quote.get("sell_levels")
    if not levels:
        return None
    return {
        "league": league,
        "category": category,
        "item_id": item_id,
        "item_name": name,
        "variant": "",
        "price_chaos": levels[0]["price"],
        "volume": sum(level["quantity"] for level in levels),
        "listing_count": len(levels),
        "source": quote["source"],
        "observation_type": "DIRECT_OBSERVATION",
        "observed_at": quote["observed_at"],
        "confidence_grade": "B",
        "execution_quote": quote,
    }


async def _stored_chaos_per_divine(league: str) -> float:
    db = await database.get_db()
    try:
        cursor = await db.execute(
            """SELECT price_chaos FROM snapshots
               WHERE league = ? AND category = 'Currency'
                 AND (item_id = 'divine' OR item_name = 'Divine Orb')
               ORDER BY timestamp DESC LIMIT 1""",
            (league,),
        )
        row = await cursor.fetchone()
        value = row["price_chaos"] if row else 0
        return float(value) if isinstance(value, (int, float)) and value > 0 else 0.0
    finally:
        await db.close()


async def collect_trade_depth(
    league: str,
    *,
    timestamp: str | None = None,
    adapter: TradeDepthAdapter | None = None,
) -> dict[str, dict]:
    """Collect opt-in trade depth and persist only validated quote-backed rows."""
    from strategies import default_div_card_registry

    registry = default_div_card_registry()
    quotes = await (adapter or TradeDepthAdapter()).collect(
        league,
        list(registry.records()),
        chaos_per_divine=await _stored_chaos_per_divine(league),
    )
    names = {}
    for recipe in registry.records():
        names[recipe["card_market_key"]] = recipe["card"]
        names[recipe["reward_market_key"]] = recipe["reward_item"]
        for outcome in recipe["outcomes"]:
            names[outcome["reward_market_key"]] = outcome["reward_item"]
    records = [
        record
        for key, quote in quotes.items()
        if key in names
        and (record := _quote_snapshot(key, names[key], quote, league=league)) is not None
    ]
    if records:
        await database.insert_snapshots(records, timestamp=timestamp)
    return quotes



async def _collect_normalized(league: str, category: str) -> list[dict]:
    """Fetch and normalize a category WITHOUT persisting. For current-price providers."""
    exchange_types = _EXCHANGE_TYPES
    stash_types = _STASH_TYPES
    is_exchange = category in exchange_types
    if not is_exchange and category not in stash_types:
        return []
    url = EXCHANGE_URL if is_exchange else STASH_URL
    api_type = exchange_types[category] if is_exchange else stash_types[category]
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(url, params={"league": league, "type": api_type})
        if resp.status_code != 200:
            return []
        try:
            data = resp.json()
        except (TypeError, ValueError):
            log.error("collect %s/%s: invalid JSON response", league, category)
            return []
    records = _snapshot_records(data, league, category, is_exchange)
    if records is None:
        log.error("collect %s/%s: malformed response payload", league, category)
        return []
    return records



async def collect_snapshot(league: str, category: str, exchange_types=None,
                           stash_types=None, timestamp: str | None = None) -> int:
    """Fetch one persisted category for a league and store it as direct observations."""
    if category not in PERSISTED_CATEGORIES:
        raise ValueError(f"Historical snapshots are disabled for high-cardinality category '{category}'")
    exchange_types = exchange_types or _EXCHANGE_TYPES
    stash_types = stash_types or _STASH_TYPES
    is_exchange = category in exchange_types
    url = EXCHANGE_URL if is_exchange else STASH_URL
    api_type = exchange_types[category] if is_exchange else stash_types[category]
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(url, params={"league": league, "type": api_type})
        if resp.status_code != 200:
            log.error("collect %s/%s: HTTP %s", league, category, resp.status_code)
            return 0
        try:
            data = resp.json()
        except (TypeError, ValueError):
            log.error("collect %s/%s: invalid JSON response", league, category)
            return 0
    timestamp = timestamp or database.now_iso()
    records = _snapshot_records(data, league, category, is_exchange)
    if records is None:
        log.error("collect %s/%s: malformed response payload", league, category)
        return 0
    stored = await database.insert_snapshots(records, timestamp)
    log.info("Stored %d snapshots for %s / %s", stored, league, category)
    return stored


async def collect_all_categories(league: str) -> dict[str, int]:
    """Prune retained history, then collect exchange data plus required reward uniques."""
    keep_categories = set(PERSISTED_CATEGORIES)
    if trade_depth_enabled():
        from strategies import default_div_card_registry

        for recipe in default_div_card_registry().records():
            for key in (recipe["card_market_key"], recipe["reward_market_key"]):
                keep_categories.add(key.split(":", 1)[0])
            for outcome in recipe["outcomes"]:
                keep_categories.add(outcome["reward_market_key"].split(":", 1)[0])
    await database.prune_market_data(keep_categories, league=league)
    if not database.collection_allowed():
        log.error("Collection paused: project storage reached the safety threshold")
        return {category: 0 for category in _COLLECTION_TYPES}
    results = {}
    timestamp = database.now_iso()
    for category in _COLLECTION_TYPES:
        try:
            results[category] = await collect_snapshot(
                league, category, _EXCHANGE_TYPES, _STASH_TYPES, timestamp
            )
        except Exception:
            log.exception("Failed to collect %s / %s", league, category)
            results[category] = 0
    if trade_depth_enabled():
        try:
            results["trade_depth"] = len(
                await collect_trade_depth(league, timestamp=timestamp)
            )
        except Exception:
            log.exception("Failed to collect trade depth for %s", league)
            results["trade_depth"] = 0
    await database.prune_market_data(keep_categories, league=league)
    return results


async def run_collector(league: str | None = None, interval: int = 1800, once: bool = False) -> None:
    """Collect using shared config each cycle, unless an explicit league overrides it."""
    if interval < 1:
        raise ValueError("interval must be positive")
    while True:
        selected_league = configured_league(league)
        if not selected_league:
            log.warning("collector waiting for an explicit league configuration")
            if once:
                return
            await asyncio.sleep(min(interval, 5))
            continue
        results = await collect_all_categories(selected_league)
        cx_stored = await cx_collector.poll_latest_cx()
        log.info("collection cycle complete for %s: %s; cx=%d", selected_league, results, cx_stored)
        if once:
            return
        await asyncio.sleep(interval)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the DeusCFO historical collector.")
    parser.add_argument(
        "--league",
        default=None,
        help="explicit poe.ninja league override; otherwise use deuscfo.config.json",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=int(os.environ.get("DEUSCFO_COLLECTOR_INTERVAL", "1800")),
        help="seconds between collection cycles",
    )
    parser.add_argument("--once", action="store_true", help="collect one cycle and exit")
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = _parse_args()
    asyncio.run(run_collector(args.league, args.interval, args.once))
