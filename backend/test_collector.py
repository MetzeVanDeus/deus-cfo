import asyncio
import pytest
from datetime import datetime, timedelta, timezone

import collector


def test_configured_league_requires_explicit_value(tmp_path, monkeypatch):
    monkeypatch.setattr(collector, "CONFIG_PATH", tmp_path / "missing.json")
    monkeypatch.delenv("DEUSCFO_LEAGUE", raising=False)
    assert collector.configured_league() == ""
    monkeypatch.setenv("DEUSCFO_LEAGUE", "Settlers")
    assert collector.configured_league() == "Settlers"


def test_poe_ninja_category_types_use_current_singular_api_keys():
    assert all(category == api_type for category, api_type in collector._EXCHANGE_TYPES.items())
    assert all(category == api_type for category, api_type in collector._STASH_TYPES.items())


def test_collector_uses_api_type_keys_and_blocks_stash_history(monkeypatch):
    requests = []
    inserted = []

    class Response:
        status_code = 200

        def __init__(self, lines):
            self._lines = lines

        def json(self):
            return {"lines": self._lines}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def get(self, url, params):
            requests.append((url, params.copy()))
            if params["type"] == collector._EXCHANGE_TYPES["Scarab"]:
                return Response([{"id": "ambush-scarab", "primaryValue": 5, "volumePrimaryValue": 100}])
            return Response([{
                "id": 123,
                "detailsId": "awakened-empower-support-4",
                "name": "Awakened Empower Support",
                "variant": "4",
                "chaosValue": 100,
                "listingCount": 3,
            }])

    async def insert(records, timestamp=None):
        inserted.extend(records)
        return len(records)

    monkeypatch.setattr(collector.httpx, "AsyncClient", lambda **_: Client())
    monkeypatch.setattr(collector.database, "insert_snapshots", insert)

    assert asyncio.run(collector.collect_snapshot("Allflame", "Scarab")) == 1
    with pytest.raises(ValueError, match="disabled"):
        asyncio.run(collector.collect_snapshot("Allflame", "SkillGem"))

    assert requests[0][1]["type"] == collector._EXCHANGE_TYPES["Scarab"]
    assert inserted[0]["item_id"] == "ambush-scarab"
    assert collector.stash_item_id({
        "id": 123, "detailsId": "awakened-empower-support-4"
    }) == "awakened-empower-support-4"


def test_required_unique_reward_category_is_persisted(monkeypatch):
    inserted = []

    class Response:
        status_code = 200
        def json(self):
            return {"lines": [{
                "detailsId": "headhunter-leather-belt", "name": "Headhunter",
                "chaosValue": 410, "listingCount": 17,
            }]}

    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_):
            return None
        async def get(self, _url, params):
            assert params["type"] == collector._STASH_TYPES["UniqueAccessory"]
            return Response()

    async def insert(records, timestamp=None):
        inserted.extend(records)
        return len(records)

    monkeypatch.setattr(collector.httpx, "AsyncClient", lambda **_: Client())
    monkeypatch.setattr(collector.database, "insert_snapshots", insert)
    assert asyncio.run(collector.collect_snapshot("Allflame", "UniqueAccessory")) == 1
    assert inserted[0]["category"] == "UniqueAccessory"
    assert inserted[0]["item_id"] == "headhunter-leather-belt"
def test_no_sparkline_backfill_in_persisted_snapshots(monkeypatch):
    """Synthetic sparkline reconstruction must never enter snapshots."""
    insert_calls: list[tuple[list, str | None]] = []

    async def insert(records, timestamp=None):
        insert_calls.append((records, timestamp))
        return len(records)

    class Response:
        status_code = 200
        def __init__(self, lines):
            self._lines = lines
        def json(self):
            return {"lines": self._lines}

    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_):
            return None
        async def get(self, url, params):
            return Response([{
                "id": "ambush-scarab",
                "primaryValue": 120,
                "volumePrimaryValue": 100,
                "sparkline": {"data": [-10, 0, 20]},
            }])

    monkeypatch.setattr(collector.httpx, "AsyncClient", lambda **_: Client())
    monkeypatch.setattr(collector.database, "insert_snapshots", insert)

    asyncio.run(collector.collect_snapshot("Allflame", "Scarab"))

    # Only one insert call — the direct observation. No synthetic backfill.
    assert len(insert_calls) == 1
    records, _ = insert_calls[0]
    assert all(r["observation_type"] == "DIRECT_OBSERVATION" for r in records)
    assert all(r["source"] == "poe.ninja" for r in records)
    assert not any(r.get("source", "").startswith("poe.ninja_sparkline") for r in records)


def test_market_history_backfill_imports_real_daily_samples(monkeypatch):
    inserted = []
    now = datetime.now(timezone.utc)

    class Response:
        status_code = 200

        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def get(self, url, params):
            if url.endswith("/overview"):
                if params["type"] == "UniqueAccessory":
                    return Response({"lines": [{
                        "id": 42,
                        "detailsId": "test-belt",
                        "name": "Test Belt",
                        "chaosValue": 100,
                        "listingCount": 50,
                    }]})
                return Response({"lines": [{
                    "id": f"test-{params['type'].lower().replace(' ', '-')}",
                    "primaryValue": 10,
                    "volumePrimaryValue": 100,
                }]})
            if "exchange" in url:
                return Response({"pairs": [{"id": "chaos", "history": [
                    {
                        "timestamp": (now - timedelta(days=2)).isoformat(),
                        "rate": 8,
                        "volumePrimaryValue": 80,
                    },
                    {
                        "timestamp": (now - timedelta(days=1)).isoformat(),
                        "rate": 9,
                        "volumePrimaryValue": 90,
                    },
                ]}]})
            return Response([
                {"daysAgo": 2, "value": 90, "count": 40},
                {"daysAgo": 1, "value": 95, "count": 45},
            ])

    async def insert(records, timestamp=None):
        inserted.extend((timestamp, record) for record in records)
        return len(records)

    async def prune(*_args, **_kwargs):
        return {}

    monkeypatch.setattr(collector.httpx, "AsyncClient", lambda **_: Client())
    monkeypatch.setattr(collector.database, "insert_snapshots", insert)
    monkeypatch.setattr(collector.database, "prune_market_data", prune)

    result = asyncio.run(collector.backfill_market_history("Allflame"))

    assert result == {"categories_processed": 9, "items_processed": 9, "rows_stored": 18}
    assert len(inserted) == 18
    assert all(record["observation_type"] == "IMPORTED_TRUSTED" for _, record in inserted)
    assert any(record["item_id"] == "test-belt" for _, record in inserted)
    assert {record["category"] for _, record in inserted} == set(collector.PERSISTED_CATEGORIES)


def test_category_sweep_uses_one_timestamp(monkeypatch):
    timestamps = []

    async def collect(_league, _category, _exchange, _stash, timestamp, **_kwargs):
        timestamps.append(timestamp)
        return 1

    async def prune(_categories, **_kwargs):
        return {}

    monkeypatch.setattr(collector, "collect_snapshot", collect)
    monkeypatch.setattr(collector.database, "prune_market_data", prune)
    results = asyncio.run(collector.collect_all_categories("Allflame"))

    assert len(results) == len(collector._COLLECTION_TYPES)
    assert len(timestamps) == len(collector._COLLECTION_TYPES)
    assert len(set(timestamps)) == 1


def test_category_sweep_stops_before_storage_headroom_is_exhausted(monkeypatch):
    calls = []

    async def prune(_categories, **_kwargs):
        calls.append("prune")
        return {}

    async def collect(*_args):
        calls.append("collect")
        return 1

    monkeypatch.setattr(collector.database, "prune_market_data", prune)
    monkeypatch.setattr(collector.database, "collection_allowed", lambda: False)
    monkeypatch.setattr(collector, "collect_snapshot", collect)

    results = asyncio.run(collector.collect_all_categories("Allflame"))

    assert set(results.values()) == {0}
    assert calls == ["prune"]



def test_snapshot_skips_malformed_rows_without_losing_valid_rows(monkeypatch):
    inserted = []

    class Response:
        status_code = 200

        def json(self):
            return {"lines": [None, {"id": 7, "primaryValue": "bad"}, {
                "id": "chaos", "primaryValue": 5, "volumePrimaryValue": 3,
            }]}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def get(self, _url, params):
            assert params["type"] == "Currency"
            return Response()

    async def insert(records, timestamp=None):
        inserted.extend(records)
        return len(records)

    monkeypatch.setattr(collector.httpx, "AsyncClient", lambda **_: Client())
    monkeypatch.setattr(collector.database, "insert_snapshots", insert)

    assert asyncio.run(collector.collect_snapshot("Allflame", "Currency")) == 1
    assert inserted[0]["item_id"] == "chaos"

def test_category_sweep_reuses_one_http_client(monkeypatch):
    clients = []
    seen = []

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

    def make_client(**_kwargs):
        client = Client()
        clients.append(client)
        return client

    async def collect(_league, _category, _exchange, _stash, _timestamp, client):
        seen.append(client)
        return 1

    async def prune(_categories, **_kwargs):
        return {}

    monkeypatch.setattr(collector.httpx, "AsyncClient", make_client)
    monkeypatch.setattr(collector, "_collect_snapshot", collect)
    monkeypatch.setattr(collector.database, "prune_market_data", prune)
    results = asyncio.run(collector.collect_all_categories("Allflame"))
    assert len(results) == len(collector._COLLECTION_TYPES)
    assert clients == [seen[0]]
    assert len(set(map(id, seen))) == 1
