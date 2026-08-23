"""Tests for data provenance filtering, CX idempotency, coverage, and providers."""

import asyncio
import sqlite3


import database
import market_data
import coverage
import providers


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _setup_db(tmp_path, monkeypatch):
    path = tmp_path / "deuscfo.db"
    monkeypatch.setattr(database, "DB_PATH", str(path))
    database._schema_path = None
    return path


async def _insert_snapshot(db, league, category, item_id, price, ts, obs_type="DIRECT_OBSERVATION", source="poe.ninja"):
    await db.execute(
        """INSERT INTO snapshots
           (timestamp, league, category, item_id, item_name, variant,
            price_chaos, volume, listing_count, icon,
            source, observation_type, observed_at, market_timestamp, confidence_grade)
           VALUES (?, ?, ?, ?, ?, '', ?, 0, 0, '', ?, ?, ?, ?, 'B')""",
        (ts, league, category, item_id, item_id, price, source, obs_type, ts, ts),
    )
    await db.commit()


# ---------------------------------------------------------------------------
# provenance filtering
# ---------------------------------------------------------------------------

def test_estimated_snapshots_excluded_from_empirical_queries(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)

    async def run():
        db = await database.get_db()
        try:
            await _insert_snapshot(db, "L", "Currency", "chaos", 1.0,
                                   "2026-08-10T00:00:00+00:00", "DIRECT_OBSERVATION")
            await _insert_snapshot(db, "L", "Currency", "chaos", 2.0,
                                   "2026-08-11T00:00:00+00:00", "ESTIMATED")
            await _insert_snapshot(db, "L", "Currency", "chaos", 3.0,
                                   "2026-08-12T00:00:00+00:00", "SYNTHETIC")
        finally:
            await db.close()

        hist = await market_data.get_price_history("L", "Currency", "chaos", hours=10000)
        assert len(hist) == 1
        assert hist[0][1] == 1.0  # only the DIRECT_OBSERVATION row

    asyncio.run(run())
def test_legacy_reconstructed_source_is_excluded(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)

    async def run():
        db = await database.get_db()
        try:
            await _insert_snapshot(
                db, "L", "Currency", "chaos", 99.0,
                "2026-08-12T00:00:00+00:00",
                "DIRECT_OBSERVATION",
                "poe.ninja_sparkline_reconstructed",
            )
            await _insert_snapshot(
                db, "L", "Currency", "chaos", 1.0,
                "2026-08-13T00:00:00+00:00",
                "DIRECT_OBSERVATION",
                "poe.ninja",
            )
        finally:
            await db.close()

        hist = await market_data.get_price_history("L", "Currency", "chaos", hours=10000)
        assert len(hist) == 1
        assert hist[0][1] == 1.0

    asyncio.run(run())




def test_synthetic_snapshots_excluded_from_latest_prices(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)

    async def run():
        db = await database.get_db()
        try:
            await _insert_snapshot(db, "L", "Currency", "chaos", 1.0,
                                   "2026-08-10T00:00:00+00:00", "DIRECT_OBSERVATION")
            await _insert_snapshot(db, "L", "Currency", "chaos", 99.0,
                                   "2026-08-12T00:00:00+00:00", "SYNTHETIC")
        finally:
            await db.close()

        latest = await market_data.get_latest_prices("L", "Currency")
        assert "chaos" in latest
        assert latest["chaos"]["price_chaos"] == 1.0  # not 99

    asyncio.run(run())


# ---------------------------------------------------------------------------
# CX idempotency
# ---------------------------------------------------------------------------

def test_cx_insert_is_idempotent(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)

    record = {
        "league": "Allflame", "market_id": "a|b", "item_a": "a", "item_b": "b",
        "volume_a": 10, "volume_b": 5, "realm": "poe1",
    }
    ts = "2026-08-10T00:00:00+00:00"

    async def run():
        assert await database.insert_cx_hour([record], ts) == 1
        # Re-insert the same hour/market → no duplicate
        assert await database.insert_cx_hour([record], ts) == 0
        db = await database.get_db()
        try:
            cur = await db.execute("SELECT COUNT(*) FROM cx_history")
            assert (await cur.fetchone())[0] == 1
        finally:
            await db.close()

    asyncio.run(run())


def test_cx_unique_index_migrates_legacy_duplicates(tmp_path, monkeypatch):
    path = _setup_db(tmp_path, monkeypatch)

    # Create a DB with legacy CX rows (no unique index, no realm column)
    seed = sqlite3.connect(path)
    seed.executescript("""
        CREATE TABLE cx_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL, league TEXT NOT NULL,
            market_id TEXT NOT NULL, item_a TEXT NOT NULL, item_b TEXT NOT NULL,
            volume_a REAL, volume_b REAL, lowest_stock_a REAL, lowest_stock_b REAL,
            highest_stock_a REAL, highest_stock_b REAL,
            lowest_ratio_a REAL, lowest_ratio_b REAL,
            highest_ratio_a REAL, highest_ratio_b REAL
        );
        INSERT INTO cx_history (timestamp, league, market_id, item_a, item_b)
        VALUES ('2026-01-01T00:00:00+00:00', 'L', 'm1', 'a', 'b'),
               ('2026-01-01T00:00:00+00:00', 'L', 'm1', 'a', 'b'),
               ('2026-01-01T00:00:00+00:00', 'L', 'm2', 'a', 'b');
    """)
    seed.close()

    async def run():
        db = await database.get_db()
        try:
            cur = await db.execute("SELECT COUNT(*) FROM cx_history")
            assert (await cur.fetchone())[0] == 2  # one deduped
        finally:
            await db.close()

    asyncio.run(run())


def test_cx_cursor_metadata_roundtrip(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)

    async def run():
        await database.set_cx_progress("default", 100,
                                        first_change_id=50,
                                        first_available_hour="2026-01-01T00:00:00+00:00",
                                        last_synced_hour="2026-01-02T00:00:00+00:00")
        cursor = await database.get_cx_cursor("default")
        assert cursor["first_change_id"] == 50
        assert cursor["last_change_id"] == 100
        assert cursor["first_available_hour"] == "2026-01-01T00:00:00+00:00"
        assert cursor["last_synced_hour"] == "2026-01-02T00:00:00+00:00"

        # Update last_change_id; first_* should be preserved
        await database.set_cx_progress("default", 200, last_synced_hour="2026-01-03T00:00:00+00:00")
        cursor = await database.get_cx_cursor("default")
        assert cursor["last_change_id"] == 200
        assert cursor["first_change_id"] == 50  # preserved
        assert cursor["first_available_hour"] == "2026-01-01T00:00:00+00:00"  # preserved

    asyncio.run(run())


# ---------------------------------------------------------------------------
# coverage
# ---------------------------------------------------------------------------

def test_coverage_reports_zero_for_empty_category(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)

    async def run():
        cov = await coverage.snapshot_coverage("L", "Currency")
        assert cov["hours_present"] == 0
        assert cov["coverage_percentage"] == 0.0
        assert cov["observation_type"] is None

    asyncio.run(run())


def test_coverage_calculates_percentage(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)

    async def run():
        db = await database.get_db()
        try:
            # 3 hours of data out of a 5-hour span
            for i, hour in enumerate([0, 2, 4]):
                ts = f"2026-08-1{hour}T00:00:00+00:00"
                await _insert_snapshot(db, "L", "Currency", "c", 1.0, ts)
        finally:
            await db.close()

        cov = await coverage.snapshot_coverage("L", "Currency")
        assert cov["hours_present"] == 3
        assert cov["coverage_percentage"] > 0

    asyncio.run(run())


def test_can_trust_window_rejects_inadequate_coverage(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)

    async def run():
        result = await coverage.can_trust_window("L", "Currency", hours=24, min_coverage=0.8)
        assert result["trusted"] is False
        assert "no empirical data" in result["reason"]

    asyncio.run(run())


def test_can_trust_window_rejects_synthetic_data(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)

    async def run():
        db = await database.get_db()
        try:
            await _insert_snapshot(db, "L", "Currency", "c", 1.0,
                                   "2026-08-10T00:00:00+00:00", "SYNTHETIC")
        finally:
            await db.close()

        result = await coverage.can_trust_window("L", "Currency", hours=1, min_coverage=0.5)
        assert result["trusted"] is False

    asyncio.run(run())


# ---------------------------------------------------------------------------
# providers
# ---------------------------------------------------------------------------

def test_snapshot_historical_provider_returns_empirical_only(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)

    async def run():
        db = await database.get_db()
        try:
            await _insert_snapshot(db, "L", "Currency", "c", 1.0,
                                   "2026-08-10T00:00:00+00:00", "DIRECT_OBSERVATION")
            await _insert_snapshot(db, "L", "Currency", "c", 99.0,
                                   "2026-08-11T00:00:00+00:00", "ESTIMATED")
        finally:
            await db.close()

        p = providers.SnapshotHistoricalProvider()
        hist = await p.get_price_history("L", "Currency", "c", hours=10000)
        assert len(hist) == 1
        assert hist[0][1] == 1.0

    asyncio.run(run())


def test_cx_historical_provider_returns_rows(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)

    async def run():
        record = {
            "league": "L", "market_id": "a|b", "item_a": "a", "item_b": "b",
            "volume_a": 10, "volume_b": 5, "realm": "poe1",
        }
        await database.insert_cx_hour([record], "2026-08-10T00:00:00+00:00")

        p = providers.CXHistoricalProvider()
        hist = await p.get_price_history("L", "Currency", "a", hours=10000)
        assert len(hist) == 1
        assert hist[0][0] == "2026-08-10T00:00:00+00:00"

    asyncio.run(run())


def test_cx_historical_provider_empty_for_non_currency_category(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)

    async def run():
        p = providers.CXHistoricalProvider()
        result = await p.get_category_histories("L", "Scarab", hours=24)
        assert result == {}

    asyncio.run(run())


# ---------------------------------------------------------------------------
# legacy DB migration
# ---------------------------------------------------------------------------

def test_legacy_snapshots_get_provenance_columns(tmp_path, monkeypatch):
    path = _setup_db(tmp_path, monkeypatch)

    # Create a legacy snapshots table without provenance columns
    seed = sqlite3.connect(path)
    seed.executescript("""
        CREATE TABLE snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL, league TEXT NOT NULL,
            category TEXT NOT NULL, item_id TEXT NOT NULL,
            item_name TEXT NOT NULL, variant TEXT NOT NULL DEFAULT '',
            price_chaos REAL NOT NULL, volume REAL NOT NULL DEFAULT 0,
            listing_count REAL NOT NULL DEFAULT 0, icon TEXT NOT NULL DEFAULT ''
        );
        INSERT INTO snapshots (timestamp, league, category, item_id, item_name, price_chaos)
        VALUES ('2026-01-01T00:00:00+00:00', 'L', 'Currency', 'c', 'C', 1.0);
        CREATE TABLE cx_progress (
            key TEXT PRIMARY KEY, last_change_id INTEGER, updated_at TEXT NOT NULL
        );
        INSERT INTO cx_progress (key, last_change_id, updated_at)
        VALUES ('default', 42, '2026-01-01T00:00:00+00:00');
    """)
    seed.close()

    async def run():
        db = await database.get_db()
        try:
            # All provenance columns must exist
            cur = await db.execute("PRAGMA table_info(snapshots)")
            names = {row[1] for row in await cur.fetchall()}
            assert {"source", "observation_type", "observed_at",
                    "market_timestamp", "confidence_grade"} <= names

            # Legacy rows get DEFAULT values
            cur = await db.execute("SELECT observation_type, confidence_grade, source FROM snapshots")
            row = await cur.fetchone()
            assert row["observation_type"] == "DIRECT_OBSERVATION"
            assert row["confidence_grade"] == "B"
            assert row["source"] == "poe.ninja"

            # cx_progress must have new cursor metadata columns
            cur = await db.execute("PRAGMA table_info(cx_progress)")
            names = {row[1] for row in await cur.fetchall()}
            assert {"first_change_id", "first_available_hour", "last_synced_hour"} <= names

            # Existing progress is preserved
            cur = await db.execute("SELECT last_change_id FROM cx_progress WHERE key = 'default'")
            row = await cur.fetchone()
            assert row["last_change_id"] == 42
        finally:
            await db.close()

    asyncio.run(run())
