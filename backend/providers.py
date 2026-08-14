"""Current vs historical market provider abstractions.

CurrentMarketProvider  — live price estimates (poe.ninja current overview).
HistoricalMarketProvider — stored empirical observations (snapshots / CX history).

The point: code must not assume a provider that reports current prices can
also supply history, or vice versa.  These two protocols make that explicit.
"""

from __future__ import annotations

from typing import Protocol

import market_data
import cx_queries


class CurrentMarketProvider(Protocol):
    """Live price snapshots — NOT suitable for backtesting."""

    async def get_current_prices(self, league: str, category: str) -> dict[str, dict]:
        """item_id -> {price_chaos, volume, ...} from the live source."""
        ...


class HistoricalMarketProvider(Protocol):
    """Empirical historical observations — safe for backtesting."""

    async def get_price_history(self, league: str, category: str, item_id: str, hours: float = 24):
        """(timestamp, price, volume) tuples, oldest first, empirical only."""
        ...

    async def get_category_histories(self, league: str, category: str, hours: float = 24) -> dict:
        """item_id -> ordered empirical history."""
        ...


# --- concrete adapters ------------------------------------------------------


class PoeNinjaCurrentProvider:
    """Current-market adapter wrapping the collector's live fetch.

    Delegates to collector for the actual HTTP call so there is a single
    network path.  Returns the normalized records without persisting them.
    """

    async def get_current_prices(self, league: str, category: str) -> dict[str, dict]:
        import collector
        records = await collector._collect_normalized(league, category)
        return {r["item_id"]: r for r in records}


class SnapshotHistoricalProvider:
    """Historical adapter over stored poe.ninja snapshots (empirical only)."""

    async def get_price_history(self, league, category, item_id, hours=24):
        return await market_data.get_price_history(league, category, item_id, hours)

    async def get_category_histories(self, league, category, hours=24):
        return await market_data.get_category_histories(league, category, hours)


class CXHistoricalProvider:
    """Historical adapter over stored GGG currency-exchange observations."""

    async def get_price_history(self, league, category, item_id, hours=24):
        # CX stores currency-pair rows, not single-item price series.
        # Return raw rows for the item; callers normalise into ratios.
        rows = await cx_queries.cx_history_for(league, [item_id], hours)
        return [(r["timestamp"], r, None) for r in rows]

    async def get_category_histories(self, league, category, hours=24):
        # CX has no category dimension; return empty for non-CX categories.
        if category != "Currency":
            return {}
        ids = await cx_queries.cx_item_ids(league)
        result = {}
        for item_id in ids:
            rows = await cx_queries.cx_history_for(league, [item_id], hours)
            if rows:
                result[item_id] = [(r["timestamp"], r, None) for r in rows]
        return result
