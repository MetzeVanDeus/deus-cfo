import asyncio
import pytest

import collector


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
            if params["type"] == "Scarab":
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

    assert requests[0][1]["type"] == "Scarab"
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
            assert params["type"] == "UniqueAccessory"
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


def test_category_sweep_uses_one_timestamp(monkeypatch):
    timestamps = []

    async def collect(_league, _category, _exchange, _stash, timestamp):
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
