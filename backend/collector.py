"""Periodic snapshot collection from poe.ninja into SQLite."""

import argparse
import asyncio
import json
import logging
import math
import os
from datetime import datetime, timedelta, timezone
from statistics import median
from pathlib import Path
from urllib.parse import quote
import httpx

import cx_collector
import database
import market_data

log = logging.getLogger("deuscfo.collector")

POE_NINJA_BASE = "https://poe.ninja"
EXCHANGE_URL = f"{POE_NINJA_BASE}/poe1/api/economy/exchange/current/overview"
STASH_URL = f"{POE_NINJA_BASE}/poe1/api/economy/stash/current/item/overview"
EXCHANGE_HISTORY_URL = f"{POE_NINJA_BASE}/poe1/api/economy/exchange/current/details"
STASH_HISTORY_URL = f"{POE_NINJA_BASE}/poe1/api/economy/stash/current/item/history"
HISTORY_ITEMS_PER_CATEGORY = 20
_history_task: asyncio.Task | None = None
_history_lock = asyncio.Lock()
_history_status = {
    "status": "idle",
    "league": None,
    "categories_processed": 0,
    "items_processed": 0,
    "rows_stored": 0,
    "error": None,
}

TRADE_API_BASE = "https://www.pathofexile.com/api/trade"
# These are trade-site endpoints, not entries in GGG's official Developer API reference.
TRADE_DEPTH_ENV = "DEUSCFO_TRADE_DEPTH"
TRADE_DEPTH_LIMIT_ENV = "DEUSCFO_TRADE_DEPTH_LIMIT"
TRADE_REQUEST_DELAY_ENV = "DEUSCFO_TRADE_REQUEST_DELAY"
TRADE_USER_AGENT_ENV = "DEUSCFO_TRADE_USER_AGENT"
TRADE_FEE_ENV = "DEUSCFO_TRADE_FEE_RATE"
SELL_LISTING_MIN_COUNT_ENV = "DEUSCFO_SELL_LISTING_MIN_COUNT"
SELL_LISTING_CLUSTER_SPREAD_ENV = "DEUSCFO_SELL_LISTING_CLUSTER_SPREAD"
SELL_LISTING_HAIRCUT_ENV = "DEUSCFO_SELL_LISTING_HAIRCUT"
CONFIG_PATH = Path(os.environ["DEUSCFO_CONFIG_PATH"]) if os.environ.get("DEUSCFO_CONFIG_PATH") else Path(__file__).resolve().parent.parent / "deuscfo.config.json"

# Shared category ids and poe.ninja API type values.
_EXCHANGE_TYPES = market_data.EXCHANGE_TYPES
_STASH_TYPES = market_data.STASH_TYPES
_COLLECTION_TYPES = market_data.COLLECTION_TYPES


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


def _sell_listing_settings() -> tuple[int, float, float]:
    try:
        minimum_count = int(os.environ.get(SELL_LISTING_MIN_COUNT_ENV, "3"))
    except ValueError:
        minimum_count = 3
    try:
        cluster_spread = float(os.environ.get(SELL_LISTING_CLUSTER_SPREAD_ENV, "0.15"))
    except ValueError:
        cluster_spread = 0.15
    try:
        haircut = float(os.environ.get(SELL_LISTING_HAIRCUT_ENV, "0.10"))
    except ValueError:
        haircut = 0.10
    return (
        minimum_count if 3 <= minimum_count <= 50 else 3,
        cluster_spread if math.isfinite(cluster_spread) and 0.01 <= cluster_spread <= 0.50 else 0.15,
        haircut if math.isfinite(haircut) and 0.01 <= haircut <= 0.50 else 0.10,
    )


def _trade_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "User-Agent": os.environ.get(
            TRADE_USER_AGENT_ENV,
            "DeusCFO/3.0 (+https://github.com/MetzeVanDeus/deus-cfo)",
        ),
    }
PERSISTED_CATEGORIES = frozenset(_COLLECTION_TYPES)




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
        item_name = market_data.format_slug(item_id) if isinstance(item_id, str) else ""
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


def _history_candidates(data, league: str, category: str, is_exchange: bool) -> list[tuple[object, dict]]:
    """Return the most liquid overview items with their normalized identities."""
    if not isinstance(data, dict) or not isinstance(data.get("lines"), list):
        return []
    candidates = []
    for line in data["lines"]:
        record = _normalize(line, league, category, is_exchange)
        request_id = line.get("id") if isinstance(line, dict) else None
        if record is None or record["price_chaos"] <= 0 or not isinstance(request_id, (str, int)):
            continue
        rank = _finite_number(
            line.get("volumePrimaryValue") if is_exchange else line.get("listingCount") or line.get("count"),
            0,
        )
        candidates.append((float(rank or 0), request_id, record))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return [(request_id, record) for _, request_id, record in candidates[:HISTORY_ITEMS_PER_CATEGORY]]


def _history_timestamp(value: object, now: datetime) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(timezone.utc)
    if parsed < now - timedelta(days=database.SNAPSHOT_RETENTION_DAYS) or parsed >= now:
        return None
    return parsed.isoformat(timespec="seconds")


def _exchange_history_records(data, record: dict, now: datetime) -> list[tuple[str, dict]]:
    if not isinstance(data, dict) or not isinstance(data.get("pairs"), list):
        return []
    pair = next(
        (
            value for value in data["pairs"]
            if isinstance(value, dict) and value.get("id") == "chaos" and isinstance(value.get("history"), list)
        ),
        None,
    )
    if pair is None:
        return []
    records = []
    for point in pair["history"]:
        if not isinstance(point, dict):
            continue
        timestamp = _history_timestamp(point.get("timestamp"), now)
        price = _finite_number(point.get("rate"), None)
        volume = _finite_number(point.get("volumePrimaryValue"), 0)
        if timestamp and price is not None and price > 0 and volume is not None:
            records.append((timestamp, {
                **record,
                "price_chaos": price,
                "volume": volume,
                "observation_type": "IMPORTED_TRUSTED",
                "market_timestamp": timestamp,
            }))
    return records


def _stash_history_records(data, record: dict, now: datetime) -> list[tuple[str, dict]]:
    if not isinstance(data, list):
        return []
    records = []
    for point in data:
        if not isinstance(point, dict):
            continue
        days_ago = point.get("daysAgo")
        price = _finite_number(point.get("value"), None)
        count = _finite_number(point.get("count"), 0)
        if (
            not isinstance(days_ago, int)
            or isinstance(days_ago, bool)
            or not 0 < days_ago <= database.SNAPSHOT_RETENTION_DAYS
            or price is None
            or price <= 0
            or count is None
        ):
            continue
        timestamp = (now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_ago)).isoformat(timespec="seconds")
        records.append((timestamp, {
            **record,
            "price_chaos": price,
            "volume": count,
            "listing_count": count,
            "observation_type": "IMPORTED_TRUSTED",
            "market_timestamp": timestamp,
        }))
    return records


async def _item_history(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    league: str,
    category: str,
    api_type: str,
    request_id: object,
    record: dict,
    is_exchange: bool,
    now: datetime,
) -> list[tuple[str, dict]]:
    url = EXCHANGE_HISTORY_URL if is_exchange else STASH_HISTORY_URL
    async with semaphore:
        response = await client.get(url, params={"league": league, "type": api_type, "id": request_id})
        response.raise_for_status()
        data = response.json()
    return (
        _exchange_history_records(data, record, now)
        if is_exchange
        else _stash_history_records(data, record, now)
    )


async def backfill_market_history(league: str) -> dict[str, int]:
    """Import real daily poe.ninja history for the most liquid persisted items."""
    global _history_status
    now = datetime.now(timezone.utc)
    grouped: dict[str, list[dict]] = {}
    items_processed = 0
    categories_processed = 0
    semaphore = asyncio.Semaphore(4)
    limits = httpx.Limits(max_connections=4)
    async with httpx.AsyncClient(timeout=20.0, limits=limits) as client:
        for category, api_type in _COLLECTION_TYPES.items():
            is_exchange = category in _EXCHANGE_TYPES
            overview_url = EXCHANGE_URL if is_exchange else STASH_URL
            try:
                response = await client.get(overview_url, params={"league": league, "type": api_type})
                response.raise_for_status()
                candidates = _history_candidates(response.json(), league, category, is_exchange)
            except Exception:
                log.exception("Failed to load history candidates for %s / %s", league, category)
                categories_processed += 1
                _history_status = {**_history_status, "categories_processed": categories_processed}
                continue
            results = await asyncio.gather(
                *(
                    _item_history(
                        client, semaphore, league, category, api_type,
                        request_id, record, is_exchange, now,
                    )
                    for request_id, record in candidates
                ),
                return_exceptions=True,
            )
            for result in results:
                items_processed += 1
                if isinstance(result, BaseException):
                    log.warning("Failed to load one %s history item: %s", category, result)
                    continue
                for timestamp, record in result:
                    grouped.setdefault(timestamp, []).append(record)
            categories_processed += 1
            _history_status = {
                **_history_status,
                "categories_processed": categories_processed,
                "items_processed": items_processed,
            }
    stored = 0
    for timestamp, records in sorted(grouped.items()):
        stored += await database.insert_snapshots(records, timestamp)
    if grouped and stored == 0:
        raise RuntimeError("Market history could not be stored; check the storage limit")
    if not grouped:
        raise RuntimeError("poe.ninja returned no compatible market history")
    await database.prune_market_data(PERSISTED_CATEGORIES, league=league)
    return {
        "categories_processed": categories_processed,
        "items_processed": items_processed,
        "rows_stored": stored,
    }


async def _run_history_backfill(league: str) -> None:
    global _history_status
    try:
        result = await backfill_market_history(league)
        _history_status = {"status": "completed", "league": league, "error": None, **result}
    except Exception:
        log.exception("Market history backfill failed for %s", league)
        _history_status = {
            **_history_status,
            "status": "failed",
            "error": "Market history import failed; retry when the upstream service is available.",
        }


async def start_market_history_backfill(league: str) -> dict:
    """Start one process-local market history import and return immediately."""
    global _history_task, _history_status
    async with _history_lock:
        if _history_task is not None and not _history_task.done():
            return {**_history_status, "status": "in_progress"}
        _history_status = {
            "status": "running",
            "league": league,
            "categories_processed": 0,
            "items_processed": 0,
            "rows_stored": 0,
            "error": None,
        }
        _history_task = asyncio.create_task(_run_history_backfill(league))
        return {**_history_status, "status": "started"}


def market_history_status() -> dict:
    return dict(_history_status)

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


def _trade_quote(
    entries: list[dict],
    *,
    side: str,
    chaos_per_divine: float,
    trade_url: str | None = None,
) -> dict | None:
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
    result = {
        f"{side}_levels": [
            {"price": price, "quantity": quantity}
            for price, quantity in sorted(levels.items())
        ],
        "fee_rate": _trade_fee(),
        "observed_at": max(observed) if observed else datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "confidence": 0.6,
        "source": "pathofexile_trade_api",
    }
    if trade_url is not None:
        result["trade_url"] = trade_url
    return result


def _exact_trade_entries(entries: list[dict], item_name: str) -> list[dict]:
    exact = []
    for entry in entries:
        item = entry.get("item") if isinstance(entry, dict) else None
        if not isinstance(item, dict):
            continue
        names = {item.get("name"), item.get("typeLine")}
        if item_name not in names or item.get("identified") is False or any(
            item.get(field) for field in (
                "corrupted", "mirrored", "foilVariation", "synthesised",
                "fractured", "split", "duplicated", "influences",
            )
        ):
            continue
        exact.append(entry)
    return exact


def _sell_listing_floor_quote(
    entries: list[dict],
    *,
    chaos_per_divine: float,
    trade_url: str,
) -> dict | None:
    minimum_count, cluster_spread, haircut = _sell_listing_settings()
    listings = []
    for entry in entries:
        value = _trade_price(entry, chaos_per_divine)
        if value is None:
            continue
        price, quantity = value
        indexed = (entry.get("listing") or {}).get("indexed")
        if not isinstance(indexed, str):
            continue
        try:
            parsed_indexed = datetime.fromisoformat(indexed.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed_indexed.tzinfo is None:
            continue
        listings.append((price, quantity, parsed_indexed))
    if len(listings) < minimum_count:
        return None
    center = median(price for price, _quantity, _indexed in listings)
    clustered = [
        listing for listing in listings
        if abs(listing[0] - center) / center <= cluster_spread
    ]
    if len(clustered) < minimum_count:
        return None
    if any(indexed > datetime.now(timezone.utc) for _price, _quantity, indexed in clustered):
        return None
    listing_floor = min(price for price, _quantity, _indexed in clustered)
    adjusted_floor = listing_floor * (1 - haircut)
    depth = sum(quantity for _price, quantity, _indexed in clustered)
    observed_at = min(indexed for _price, _quantity, indexed in clustered)
    return {
        "sell_listing_floor_levels": [{"price": adjusted_floor, "quantity": depth}],
        "quote_kind": "sell_listing_floor",
        "listing_floor": listing_floor,
        "sell_listing_floor": adjusted_floor,
        "liquidation_haircut": haircut,
        "listing_sample_count": len(listings),
        "listing_cluster_count": len(clustered),
        "listing_cluster_depth": depth,
        "listing_cluster_spread": cluster_spread,
        "observed_at": observed_at.isoformat(timespec="seconds"),
        "confidence": 0.6,
        "source": "pathofexile_trade_listing_floor",
        "trade_url": trade_url,
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
        search_field: str = "name",
    ) -> dict | None:
        if side not in {"buy", "sell_listing_floor"} or search_field not in {"name", "type"}:
            return None
        try:
            response = await client.post(
                f"{TRADE_API_BASE}/search/{league}",
                json={
                    "query": {"status": {"option": "online"}, search_field: item_name},
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
            entries = []
            for offset in range(0, len(listing_ids), 10):
                if offset:
                    await asyncio.sleep(_trade_delay())
                response = await client.get(
                    f"{TRADE_API_BASE}/fetch/{','.join(listing_ids[offset:offset + 10])}",
                    params={"query": search_id},
                )
                if response.status_code != 200:
                    return None
                payload = response.json()
                chunk = payload.get("result", []) if isinstance(payload, dict) else []
                if not isinstance(chunk, list):
                    return None
                entries.extend(chunk)
            trade_url = (
                f"https://www.pathofexile.com/trade/search/"
                f"{quote(league, safe='')}/{quote(search_id, safe='')}"
            )
            exact_entries = _exact_trade_entries(entries, item_name)
            if side == "sell_listing_floor":
                return _sell_listing_floor_quote(
                    exact_entries,
                    chaos_per_divine=chaos_per_divine,
                    trade_url=trade_url,
                )
            return _trade_quote(
                exact_entries,
                side="buy",
                chaos_per_divine=chaos_per_divine,
                trade_url=trade_url,
            )
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
        requests = {
            (recipe["card_market_key"], "buy"): recipe["card"]
            for recipe in recipes
        }
        for recipe in recipes:
            if recipe.get("deterministic") and recipe.get("reward_type") == "exact_unique":
                requests[(recipe["reward_market_key"], "sell_listing_floor")] = recipe["reward_item"]
        quotes = {}
        async with httpx.AsyncClient(timeout=20, headers=_trade_headers()) as client:
            for index, ((key, side), name) in enumerate(requests.items()):
                if index:
                    await asyncio.sleep(_trade_delay())
                quote_value = await self.quote(
                    client, league, name, side=side, chaos_per_divine=chaos_per_divine,
                    search_field="type" if key.startswith("DivinationCard:") else "name",
                )
                if quote_value is not None:
                    quotes.setdefault(key, {}).update(quote_value)
        return quotes



def _quote_snapshot(key: str, name: str, quote: dict, *, league: str) -> dict | None:
    category, separator, item_id = key.partition(":")
    if not separator:
        return None
    levels = quote.get("buy_levels") or quote.get("sell_levels") or quote.get("sell_listing_floor_levels")
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
        "listing_count": quote.get("listing_cluster_count", len(levels)),
        "source": quote["source"],
        "observation_type": "DIRECT_OBSERVATION",
        "observed_at": quote["observed_at"],
        "confidence_grade": "B",
        "execution_quote": quote,
    }



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
        chaos_per_divine=(await market_data.resolve_chaos_per_divine(league)) or 0.0,
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



async def _collect_snapshot(
    league: str, category: str, exchange_types: dict, stash_types: dict,
    timestamp: str | None, client: httpx.AsyncClient,
) -> int:
    is_exchange = category in exchange_types
    url = EXCHANGE_URL if is_exchange else STASH_URL
    api_type = exchange_types[category] if is_exchange else stash_types[category]
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


async def collect_snapshot(league: str, category: str, exchange_types=None,
                           stash_types=None, timestamp: str | None = None,
                           *, client: httpx.AsyncClient | None = None) -> int:
    """Fetch one persisted category and optionally reuse an existing client."""
    if category not in PERSISTED_CATEGORIES:
        raise ValueError(f"Historical snapshots are disabled for high-cardinality category '{category}'")
    exchange_types = exchange_types or _EXCHANGE_TYPES
    stash_types = stash_types or _STASH_TYPES
    if client is not None:
        return await _collect_snapshot(league, category, exchange_types, stash_types, timestamp, client)
    async with httpx.AsyncClient(timeout=20.0) as owned_client:
        return await _collect_snapshot(league, category, exchange_types, stash_types, timestamp, owned_client)


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
    async with httpx.AsyncClient(timeout=20.0) as client:
        for category in _COLLECTION_TYPES:
            try:
                results[category] = await collect_snapshot(
                    league, category, _EXCHANGE_TYPES, _STASH_TYPES, timestamp, client=client
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
