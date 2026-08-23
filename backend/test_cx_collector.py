import asyncio

import cx_collector


def _install(monkeypatch, records, stored, ncid=2):
    """Wire up mocks for CX collector tests."""
    progress = []
    set_calls: list[dict] = []

    async def leagues():
        return {"Allflame"}

    async def get_progress(_key):
        return 1

    async def fetch(_change_id):
        return {"next_change_id": ncid}

    async def insert(_records, _timestamp):
        return stored

    async def set_progress(key, change_id, **kwargs):
        progress.append(change_id)
        set_calls.append({"key": key, "change_id": change_id, **kwargs})

    monkeypatch.setattr(cx_collector, "_fetch_leagues", leagues)
    monkeypatch.setattr(cx_collector.database, "get_cx_progress", get_progress)
    monkeypatch.setattr(cx_collector, "fetch_currency_exchange", fetch)
    monkeypatch.setattr(cx_collector, "_parse_hour", lambda _data, _wanted: ("hour", records))
    monkeypatch.setattr(cx_collector.database, "insert_cx_hour", insert)
    monkeypatch.setattr(cx_collector.database, "set_cx_progress", set_progress)
    return progress, set_calls


def test_poll_advances_progress_on_new_data(monkeypatch):
    progress, _ = _install(monkeypatch, [{"market": 1}], stored=1)
    assert asyncio.run(cx_collector.poll_latest_cx()) == 1
    assert progress == [2]


def test_poll_does_not_advance_when_already_up_to_date(monkeypatch):
    progress, _ = _install(monkeypatch, [{"market": 1}], stored=0, ncid=1)
    assert asyncio.run(cx_collector.poll_latest_cx()) == 0
    assert progress == []


def test_backfill_processes_hours_and_advances(monkeypatch):
    progress, _ = _install(monkeypatch, [{"market": 1}], stored=1)
    assert asyncio.run(cx_collector.backfill_currency_exchange(max_hours=1)) == 1
    assert progress == [2]


def test_backfill_starts_at_requested_recent_window(monkeypatch):
    progress, _ = _install(monkeypatch, [{"market": 1}], stored=1)
    fetched = []

    async def fetch(change_id):
        fetched.append(change_id)
        return {"next_change_id": change_id + 3600}

    monkeypatch.setattr(cx_collector, "_hour_cursor", lambda hours_ago=0: 10_000 - hours_ago * 3600)
    monkeypatch.setattr(cx_collector, "fetch_currency_exchange", fetch)

    assert asyncio.run(cx_collector.backfill_currency_exchange(max_hours=1)) == 1
    assert fetched == [6400]
    assert progress == [10_000]


def test_backfill_stops_at_current_hour(monkeypatch):
    progress, _ = _install(monkeypatch, [{"market": 1}], stored=1, ncid=1)
    monkeypatch.setattr(cx_collector, "_hour_cursor", lambda _hours_ago=0: 1)
    assert asyncio.run(cx_collector.backfill_currency_exchange(max_hours=5)) == 0
    assert progress == []


def test_empty_hour_can_advance_progress(monkeypatch):
    progress, _ = _install(monkeypatch, [], stored=0)
    assert asyncio.run(cx_collector.poll_latest_cx()) == 0
    assert progress == [2]


def test_poll_stores_cursor_metadata(monkeypatch):
    _, set_calls = _install(monkeypatch, [{"market": 1}], stored=1)
    asyncio.run(cx_collector.poll_latest_cx())
    assert len(set_calls) == 1
    call = set_calls[0]
    assert call["change_id"] == 2
    assert call.get("last_synced_hour") == "hour"


def test_backfill_stores_first_change_id(monkeypatch):
    progress, set_calls = _install(monkeypatch, [{"market": 1}], stored=1)
    monkeypatch.setattr(cx_collector, "_hour_cursor", lambda _hours_ago=0: 1)
    asyncio.run(cx_collector.backfill_currency_exchange(max_hours=1))
    assert progress == [2]
    call = set_calls[0]
    assert call.get("first_change_id") == 2
    assert call.get("first_available_hour") == "hour"
    assert call.get("last_synced_hour") == "hour"


def test_parse_hour_skips_malformed_markets_and_preserves_valid_data():
    data = {
        "next_change_id": 2,
        "markets": [None, {
            "league": "Allflame",
            "market_id": "chaos|divine",
            "market_pair": ["chaos", "divine"],
            "volume_traded": {"chaos": 4, "divine": 2},
        }],
    }

    timestamp, records = cx_collector._parse_hour(data, {"Allflame"})

    assert timestamp
    assert len(records) == 1
    assert records[0]["volume_a"] == 4


def test_poll_does_not_advance_on_malformed_payload(monkeypatch):
    progress = []

    async def leagues():
        return {"Allflame"}

    async def get_progress(_key):
        return 1

    async def fetch(_change_id):
        return {"next_change_id": "bad", "markets": []}

    async def set_progress(*_args, **_kwargs):
        progress.append(True)

    monkeypatch.setattr(cx_collector, "_fetch_leagues", leagues)
    monkeypatch.setattr(cx_collector.database, "get_cx_progress", get_progress)
    monkeypatch.setattr(cx_collector, "fetch_currency_exchange", fetch)
    monkeypatch.setattr(cx_collector.database, "set_cx_progress", set_progress)

    assert asyncio.run(cx_collector.poll_latest_cx()) == 0
    assert progress == []
