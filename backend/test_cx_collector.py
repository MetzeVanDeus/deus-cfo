import asyncio

import cx_collector


def _install(monkeypatch, records, stored):
    progress = []

    async def leagues():
        return {"Allflame"}

    async def get_progress(_key):
        return 1

    async def fetch(_change_id):
        return {"next_change_id": 2}

    async def insert(_records, _timestamp):
        return stored

    async def set_progress(_key, change_id):
        progress.append(change_id)

    monkeypatch.setattr(cx_collector, "_fetch_leagues", leagues)
    monkeypatch.setattr(cx_collector.database, "get_cx_progress", get_progress)
    monkeypatch.setattr(cx_collector, "fetch_currency_exchange", fetch)
    monkeypatch.setattr(cx_collector, "_parse_hour", lambda _data, _wanted: ("hour", records))
    monkeypatch.setattr(cx_collector.database, "insert_cx_hour", insert)
    monkeypatch.setattr(cx_collector.database, "set_cx_progress", set_progress)
    return progress


def test_poll_does_not_advance_progress_when_storage_is_paused(monkeypatch):
    progress = _install(monkeypatch, [{"market": 1}], stored=0)

    assert asyncio.run(cx_collector.poll_latest_cx()) == 0
    assert progress == []


def test_backfill_stops_without_advancing_when_storage_is_paused(monkeypatch):
    progress = _install(monkeypatch, [{"market": 1}], stored=0)

    assert asyncio.run(cx_collector.backfill_currency_exchange(max_hours=1)) == 0
    assert progress == []


def test_empty_hour_can_advance_progress(monkeypatch):
    progress = _install(monkeypatch, [], stored=0)

    assert asyncio.run(cx_collector.poll_latest_cx()) == 0
    assert progress == [2]
