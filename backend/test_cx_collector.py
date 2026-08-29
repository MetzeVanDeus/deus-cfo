import asyncio
import httpx

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
        return {"next_change_id": ncid, "markets": [{"league": "Allflame"}]}

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


def test_fetch_retries_transient_connection_failure(monkeypatch):
    calls = 0

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"next_change_id": 2, "markets": []}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        async def get(self, _url):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise httpx.ConnectError("temporary DNS failure")
            return Response()

    monkeypatch.setattr(cx_collector.httpx, "AsyncClient", lambda **_kwargs: Client())
    monkeypatch.setattr(cx_collector, "REQUEST_DELAY", 0)

    assert asyncio.run(cx_collector.fetch_currency_exchange(1))["next_change_id"] == 2
    assert calls == 2


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


def test_backfill_starts_at_requested_recent_window_without_saved_cursor(monkeypatch):
    progress, _ = _install(monkeypatch, [{"market": 1}], stored=1)
    fetched = []

    async def get_progress(_key):
        return None

    async def fetch(change_id):
        fetched.append(change_id)
        return {"next_change_id": change_id + 3600, "markets": [{"league": "Allflame"}]}

    monkeypatch.setattr(cx_collector.database, "get_cx_progress", get_progress)
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


def test_backfill_stops_after_advancing_to_current_hour(monkeypatch):
    progress, _ = _install(monkeypatch, [{"market": 1}], stored=1, ncid=2)
    fetched = []

    async def fetch(change_id):
        fetched.append(change_id)
        return {"next_change_id": 2, "markets": [{"league": "Allflame"}]}

    monkeypatch.setattr(cx_collector, "fetch_currency_exchange", fetch)
    monkeypatch.setattr(cx_collector, "_hour_cursor", lambda _hours_ago=0: 2)

    assert asyncio.run(cx_collector.backfill_currency_exchange(max_hours=5)) == 1
    assert fetched == [1]
    assert progress == [2]


def test_empty_hour_does_not_advance_progress(monkeypatch):
    progress, _ = _install(monkeypatch, [], stored=0)
    assert asyncio.run(cx_collector.poll_latest_cx()) == 0
    assert progress == []


def test_backfill_retries_wanted_empty_hour_without_advancing(monkeypatch):
    progress, _ = _install(monkeypatch, [], stored=0)

    async def fetch(_change_id):
        return {"next_change_id": 2, "markets": [{"league": "Allflame"}]}

    monkeypatch.setattr(cx_collector, "fetch_currency_exchange", fetch)
    assert asyncio.run(cx_collector.backfill_currency_exchange(max_hours=1)) == 0
    assert progress == []


def test_poll_retries_wanted_empty_hour_without_advancing(monkeypatch):
    progress, _ = _install(monkeypatch, [], stored=0)

    async def fetch(_change_id):
        return {"next_change_id": 2, "markets": [{"league": "Allflame"}]}

    monkeypatch.setattr(cx_collector, "fetch_currency_exchange", fetch)
    assert asyncio.run(cx_collector.poll_latest_cx()) == 0
    assert progress == []

def test_backfill_fails_when_league_discovery_is_empty(monkeypatch):
    progress, _ = _install(monkeypatch, [{"market": 1}], stored=1)
    monkeypatch.setattr(cx_collector, "_fetch_leagues", lambda: asyncio.sleep(0, result=set()))
    assert asyncio.run(cx_collector._run_backfill(max_hours=1)) == 0
    assert cx_collector.backfill_status()["backfill_status"] == "failed"
    assert progress == []


def test_poll_does_not_advance_when_league_discovery_is_empty(monkeypatch):
    progress, _ = _install(monkeypatch, [{"market": 1}], stored=1)
    monkeypatch.setattr(cx_collector, "_fetch_leagues", lambda: asyncio.sleep(0, result=set()))
    assert asyncio.run(cx_collector.poll_latest_cx()) == 0
    assert progress == []


def test_backfill_does_not_advance_when_wanted_leagues_vanish(monkeypatch):
    progress, _ = _install(monkeypatch, [{"market": 1}], stored=1)

    async def fetch(_change_id):
        return {"next_change_id": 2, "markets": [{"league": "OtherLeague"}]}

    monkeypatch.setattr(cx_collector, "fetch_currency_exchange", fetch)
    assert asyncio.run(cx_collector.backfill_currency_exchange(max_hours=1)) == 0
    assert progress == []


def test_poll_does_not_advance_when_wanted_leagues_vanish(monkeypatch):
    progress, _ = _install(monkeypatch, [{"market": 1}], stored=1)

    async def fetch(_change_id):
        return {"next_change_id": 2, "markets": [{"league": "OtherLeague"}]}

    monkeypatch.setattr(cx_collector, "fetch_currency_exchange", fetch)
    assert asyncio.run(cx_collector.poll_latest_cx()) == 0
    assert progress == []

def test_poll_stores_cursor_metadata(monkeypatch):
    _, set_calls = _install(monkeypatch, [{"market": 1}], stored=1)
    asyncio.run(cx_collector.poll_latest_cx())
    assert len(set_calls) == 1
    call = set_calls[0]
    assert call["change_id"] == 2
    assert call.get("last_synced_hour") == "hour"


def test_backfill_stores_first_change_id(monkeypatch):
    progress, set_calls = _install(monkeypatch, [{"market": 1}], stored=1)
    async def get_progress(_key):
        return None

    monkeypatch.setattr(cx_collector.database, "get_cx_progress", get_progress)
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

def test_backfill_uses_saved_cursor_when_available(monkeypatch):
    progress, set_calls = _install(monkeypatch, [{"market": 1}], stored=1)
    fetched = []

    async def fetch(change_id):
        fetched.append(change_id)
        return {"next_change_id": change_id + 1, "markets": [{"league": "Allflame"}]}

    monkeypatch.setattr(cx_collector, "fetch_currency_exchange", fetch)
    monkeypatch.setattr(cx_collector, "REQUEST_DELAY", 0)
    assert asyncio.run(cx_collector.backfill_currency_exchange(max_hours=1)) == 1
    assert fetched == [1]
    assert progress == [2]
    assert set_calls[0]["first_change_id"] is None
    assert set_calls[0]["first_available_hour"] is None




def test_start_backfill_prevents_duplicate_workers(monkeypatch):
    async def fake_backfill(max_hours):
        await asyncio.sleep(0)
        return max_hours

    monkeypatch.setattr(cx_collector, "backfill_currency_exchange", fake_backfill)

    async def run():
        first = await cx_collector.start_backfill(max_hours=3)
        second = await cx_collector.start_backfill(max_hours=3)
        assert first == {"status": "started", "hours_requested": 3, "hours_processed": 0}
        assert second == {"status": "in_progress", "hours_requested": 3, "hours_processed": 0}
        await cx_collector._backfill_task
        assert cx_collector.backfill_status() == {
            "backfill_status": "completed",
            "backfill_hours_requested": 3,
            "backfill_hours_processed": 3,
        }

    asyncio.run(run())
def test_backfill_worker_reports_fetch_failure(monkeypatch):
    async def leagues():
        return {"Allflame"}

    async def get_progress(_key):
        return 1

    async def fetch(_change_id):
        raise RuntimeError("upstream unavailable")

    monkeypatch.setattr(cx_collector, "_fetch_leagues", leagues)
    monkeypatch.setattr(cx_collector.database, "get_cx_progress", get_progress)
    monkeypatch.setattr(cx_collector, "fetch_currency_exchange", fetch)

    async def run():
        result = await cx_collector.start_backfill(max_hours=1)
        assert result["status"] == "started"
        await cx_collector._backfill_task
        assert cx_collector.backfill_status()["backfill_status"] == "failed"

    asyncio.run(run())

