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

def test_sparkline_history_reconstructs_dated_prices():
    line = {
        "id": "ambush-scarab",
        "primaryValue": 120,
        "volumePrimaryValue": 100,
        "sparkline": {"data": [-10, 0, 20]},
    }
    record = collector._normalize(line, "Allflame", "Scarab", True)

    history = collector._sparkline_history(line, record, "2026-08-12T15:00:00+00:00")

    assert [timestamp for timestamp, _ in history] == [
        "2026-08-10T00:00:00+00:00",
        "2026-08-11T00:00:00+00:00",
    ]
    assert [row["price_chaos"] for _, row in history] == [90, 100]
    assert all(row["volume"] == 0 for _, row in history)
    assert all(
        row["source"] == "poe.ninja_sparkline_reconstructed"
        for _, row in history
    )


def test_category_sweep_uses_one_timestamp(monkeypatch):
    timestamps = []

    async def collect(_league, _category, _exchange, _stash, timestamp):
        timestamps.append(timestamp)
        return 1

    async def prune(_categories):
        return {}

    monkeypatch.setattr(collector, "collect_snapshot", collect)
    monkeypatch.setattr(collector.database, "prune_market_data", prune)
    results = asyncio.run(collector.collect_all_categories("Allflame"))

    assert len(results) == 8
    assert len(timestamps) == 8
    assert len(set(timestamps)) == 1


def test_category_sweep_stops_before_storage_headroom_is_exhausted(monkeypatch):
    calls = []

    async def prune(_categories):
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
