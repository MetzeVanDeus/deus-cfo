import asyncio
import sqlite3

import aiosqlite

import database


def test_concurrent_get_db_migrates_current_shaped_database(tmp_path, monkeypatch):
    path = tmp_path / "deuscfo.db"
    seed = sqlite3.connect(path)
    seed.executescript("""
        CREATE TABLE portfolio_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
            bankroll_json TEXT NOT NULL, positions_json TEXT NOT NULL,
            reserve REAL NOT NULL, expected_profit REAL NOT NULL,
            expected_duration_hours REAL, expected_distribution_json TEXT NOT NULL,
            baseline_hold_return REAL, baseline_random_return REAL,
            baseline_raw_roi_return REAL, baseline_flip_score_return REAL
        );
        CREATE TABLE trade_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT, portfolio_id INTEGER,
            position_id INTEGER, opportunity_id TEXT NOT NULL, confidence REAL,
            predicted_entry_price REAL, actual_entry_price REAL,
            predicted_exit_price REAL, actual_exit_price REAL,
            predicted_duration_hours REAL, actual_duration_hours REAL,
            predicted_profit REAL, realized_profit REAL, profitable INTEGER,
            recorded_at TEXT NOT NULL
        );
    """)
    seed.close()
    monkeypatch.setattr(database, "DB_PATH", str(path))
    database._schema_path = None

    async def open_and_close():
        db = await database.get_db()
        await db.close()

    async def run():
        await asyncio.gather(*(open_and_close() for _ in range(20)))
        db = await aiosqlite.connect(path)
        try:
            for table, columns in {
                "portfolio_recommendations": ("league", "mode", "recommendation", "reason", "capital_currency", "chaos_per_divine"),
                "trade_records": ("quantity", "chaos_per_divine", "capital_currency"),
            }.items():
                cursor = await db.execute(f"PRAGMA table_info({table})")
                names = {row[1] for row in await cursor.fetchall()}
                assert set(columns) <= names
        finally:
            await db.close()

    asyncio.run(run())


def test_prune_market_data_removes_unsupported_and_expired_rows(tmp_path, monkeypatch):
    path = tmp_path / "deuscfo.db"
    monkeypatch.setattr(database, "DB_PATH", str(path))
    database._schema_path = None

    def snapshot(category, item_id):
        return {
            "league": "Allflame", "category": category, "item_id": item_id,
            "item_name": item_id, "price_chaos": 1,
        }

    cx_record = {
        "league": "Allflame", "market_id": 1, "item_a": "a", "item_b": "b",
    }
    other_snapshot = snapshot("Currency", "other-old")
    other_snapshot["league"] = "OtherLeague"

    async def run():
        await database.insert_snapshots([snapshot("Currency", "old")], "2000-01-01T00:00:00+00:00")
        await database.insert_snapshots([other_snapshot], "2000-01-01T00:00:00+00:00")
        await database.insert_snapshots([snapshot("Currency", "keep")])
        await database.insert_snapshots([snapshot("SkillGem", "drop")])
        await database.insert_cx_hour([cx_record], "2000-01-01T00:00:00+00:00")
        await database.insert_cx_hour([{**cx_record, "market_id": 2}], database.now_iso())
        await database.insert_cx_hour(
            [{**cx_record, "league": "OtherLeague", "market_id": 3}],
            "2000-01-01T00:00:00+00:00",
        )

        deleted = await database.prune_market_data({"Currency"}, 1, 1, league="Allflame")
        assert deleted == {
            "unsupported_snapshots": 1,
            "expired_snapshots": 1,
            "expired_cx_rows": 1,
        }

        db = await database.get_db()
        try:
            rows = await (await db.execute(
                "SELECT category, item_id FROM snapshots"
            )).fetchall()
            assert [tuple(row) for row in rows] == [
                ("Currency", "keep"),
                ("Currency", "other-old"),
            ]
            cx_rows = await (await db.execute(
                "SELECT COUNT(*) FROM cx_history"
            )).fetchone()
            assert cx_rows[0] == 2
            max_pages = int((await (await db.execute("PRAGMA max_page_count")).fetchone())[0])
            page_size = int((await (await db.execute("PRAGMA page_size")).fetchone())[0])
            assert max_pages * page_size <= database.MAX_DATABASE_BYTES
        finally:
            await db.close()

    asyncio.run(run())


def test_prune_ignores_transient_wal_checkpoint_lock(monkeypatch):
    calls = []

    class Cursor:
        def __init__(self, rowcount=0):
            self.rowcount = rowcount

    class LockedCheckpoint:
        async def execute(self, sql, *_args):
            calls.append(sql)
            if sql.startswith("DELETE FROM snapshots"):
                return Cursor(1)
            if sql.startswith("DELETE FROM cx_history"):
                return Cursor(2)
            if sql == "PRAGMA wal_checkpoint(TRUNCATE)":
                raise aiosqlite.OperationalError("database table is locked")
            return Cursor()

        async def commit(self):
            calls.append("commit")

        async def close(self):
            calls.append("close")

    db = LockedCheckpoint()

    async def get_db():
        return db

    monkeypatch.setattr(database, "get_db", get_db)

    deleted = asyncio.run(database.prune_market_data({"Currency"}, league="Allflame"))

    assert deleted == {
        "unsupported_snapshots": 1,
        "expired_snapshots": 1,
        "expired_cx_rows": 2,
    }
    assert "PRAGMA wal_checkpoint(TRUNCATE)" in calls
    assert calls[-1] == "close"

def test_snapshot_observations_are_idempotent(tmp_path, monkeypatch):
    path = tmp_path / "deuscfo.db"
    monkeypatch.setattr(database, "DB_PATH", str(path))
    database._schema_path = None
    record = {
        "league": "Allflame", "category": "Scarab", "item_id": "ambush-scarab",
        "item_name": "Ambush Scarab", "price_chaos": 5,
    }

    async def run():
        timestamp = "2026-08-11T00:00:00+00:00"
        assert await database.insert_snapshots([record], timestamp) == 1
        assert await database.insert_snapshots([record], timestamp) == 0
        assert await database.count_rows() == 1

    asyncio.run(run())
def test_execution_quote_attachment_preserves_snapshot_provenance(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "provenance.db"))
    database._schema_path = None
    aggregate = {
        "league": "Allflame", "category": "UniqueAccessory", "item_id": "headhunter-leather-belt",
        "item_name": "Headhunter", "price_chaos": 410, "volume": 17,
        "listing_count": 3, "source": "poe.ninja", "observation_type": "DIRECT_OBSERVATION",
        "observed_at": "2026-08-15T00:00:00Z", "market_timestamp": "2026-08-15T00:00:00Z",
        "confidence_grade": "B",
    }
    quote = {
        **aggregate,
        "price_chaos": 399, "volume": 4, "listing_count": 4,
        "source": "pathofexile_trade_api",
        "execution_quote": {
            "sell_levels": [{"price": 399, "quantity": 4}],
            "observed_at": "2026-08-15T00:00:00Z", "confidence": 0.6,
            "source": "pathofexile_trade_api",
        },
    }

    async def run():
        timestamp = "2026-08-15T00:00:00Z"
        assert await database.insert_snapshots([aggregate], timestamp) == 1
        assert await database.insert_snapshots([quote], timestamp) == 1
        db = await database.get_db()
        try:
            row = await (await db.execute(
                "SELECT price_chaos, volume, listing_count, source, observed_at, execution_quote "
                "FROM snapshots"
            )).fetchone()
            assert tuple(row[:5]) == (410, 17, 3, "poe.ninja", "2026-08-15T00:00:00Z")
            assert row["execution_quote"] is not None
        finally:
            await db.close()

    asyncio.run(run())




def test_market_writes_stop_at_project_safety_threshold(tmp_path, monkeypatch):
    path = tmp_path / "deuscfo.db"
    monkeypatch.setattr(database, "DB_PATH", str(path))
    monkeypatch.setattr(database, "collection_allowed", lambda: False)
    database._schema_path = None
    record = {
        "league": "Allflame", "category": "Currency", "item_id": "chaos",
        "item_name": "Chaos Orb", "price_chaos": 1,
    }

    assert asyncio.run(database.insert_snapshots([record])) == 0
    assert not path.exists()
def test_paper_migration_converts_realized_equity_curve(tmp_path, monkeypatch):
    path = tmp_path / "legacy-paper.db"
    monkeypatch.setattr(database, "DB_PATH", str(path))
    database._schema_path = None

    async def run():
        db = await database.get_db()
        await db.execute(
            "INSERT INTO snapshots (timestamp, league, category, item_id, item_name, price_chaos) "
            "VALUES ('2026-01-01T00:00:00+00:00', 'Allflame', 'Currency', 'divine', 'Divine Orb', 100)"
        )
        rec = await db.execute(
            """INSERT INTO portfolio_recommendations
               (created_at, bankroll_json, positions_json, reserve, expected_profit,
                expected_distribution_json, chaos_per_divine)
               VALUES ('2026-01-01T00:00:00+00:00', '{}', '[]', 0, 0, '{}', 80)"""
        )
        portfolio = await db.execute(
            "INSERT INTO paper_portfolios (name, initial_bankroll, currency, created_at) "
            "VALUES ('legacy', 10, 'Divine', '2026-01-01T00:00:00+00:00')"
        )
        await db.execute(
            "INSERT INTO paper_positions "
            "(portfolio_id, recommendation_id, opportunity_id, quantity, entry_price, predicted_profit, "
            "opened_at, status, realized_profit) VALUES (?, ?, 'legacy', 1, 2, 1, ?, 'realized', 1)",
            (portfolio.lastrowid, rec.lastrowid, "2026-01-01T00:00:00+00:00"),
        )
        await db.execute(
            "INSERT INTO paper_equity (portfolio_id, timestamp, equity, realized_profit, source) "
            "VALUES (?, ?, 10, 0, 'initial'), (?, ?, 11, 1, 'paper_realization')",
            (portfolio.lastrowid, "2026-01-01T00:00:00+00:00", portfolio.lastrowid, "2026-01-02T00:00:00+00:00"),
        )
        await db.execute("PRAGMA user_version = 0")
        await db.commit()
        await db.close()
        database._schema_path = None
        db = await database.get_db()
        paper = await (await db.execute(
            "SELECT initial_bankroll, currency FROM paper_portfolios WHERE id = ?", (portfolio.lastrowid,)
        )).fetchone()
        curve = await (await db.execute(
            "SELECT equity, realized_profit FROM paper_equity WHERE portfolio_id = ? ORDER BY id",
            (portfolio.lastrowid,),
        )).fetchall()
        position = await (await db.execute(
            "SELECT entry_price FROM paper_positions WHERE portfolio_id = ?", (portfolio.lastrowid,)
        )).fetchone()
        await db.close()
        return paper, curve, position

    paper, curve, position = asyncio.run(run())
    assert dict(paper) == {"initial_bankroll": 1000, "currency": "Chaos"}
    assert [dict(row) for row in curve] == [
        {"equity": 1000, "realized_profit": 0},
        {"equity": 1100, "realized_profit": 100},
    ]
    assert position["entry_price"] == 160

def test_collection_guard_counts_database_outside_project(tmp_path, monkeypatch):
    project = tmp_path / "project"
    monkeypatch.setattr(database, "PROJECT_ROOT", str(project))
    monkeypatch.setattr(database, "project_footprint", lambda: 100)
    monkeypatch.setattr(database, "storage_footprint", lambda: {"total": 100})
    monkeypatch.setattr(database, "COLLECTION_STOP_BYTES", 150)

    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "data" / "deuscfo.db"))
    assert database.collection_allowed() is False

    monkeypatch.setattr(database, "DB_PATH", str(project / "deuscfo.db"))
    assert database.collection_allowed() is True

def test_execution_quote_validation_preserves_stale_and_rejects_invalid_timestamp():
    quote = {
        "sell_levels": [{"price": 3, "quantity": 2}],
        "observed_at": "2026-08-15T00:00:00Z", "confidence": 0.8,
        "source": "test", "stale": True,
    }
    assert database.validate_execution_quote(quote)["stale"] is True
    assert database.validate_execution_quote({**quote, "observed_at": "now"}) is None


def test_execution_quote_validation_preserves_sell_listing_floor_provenance():
    quote = {
        "sell_listing_floor_levels": [{"price": 90, "quantity": 3}],
        "quote_kind": "sell_listing_floor",
        "listing_floor": 100,
        "sell_listing_floor": 90,
        "liquidation_haircut": 0.1,
        "listing_sample_count": 4,
        "listing_cluster_count": 3,
        "listing_cluster_depth": 3,
        "listing_cluster_spread": 0.15,
        "observed_at": "2026-08-15T00:00:00Z",
        "confidence": 0.6,
        "source": "pathofexile_trade_listing_floor",
        "trade_url": "https://www.pathofexile.com/trade/search/Test/search-id",
    }
    validated = database.validate_execution_quote(quote)
    assert validated is not None
    assert validated["sell_listing_floor_levels"] == [{"price": 90.0, "quantity": 3.0}]
    assert validated["quote_kind"] == "sell_listing_floor"
    assert validated["listing_floor"] == 100
    assert validated["sell_listing_floor"] == 90
    assert validated["liquidation_haircut"] == 0.1
    assert validated["source"] == "pathofexile_trade_listing_floor"
    assert database.validate_execution_quote({**quote, "listing_cluster_count": 2}) is None
    malformed = [
        {"sell_listing_floor_levels": [{"price": 900, "quantity": 3}]},
        {"sell_listing_floor_levels": [{"price": 90, "quantity": 4}]},
        {"liquidation_haircut": 0},
        {"source": "other"},
        {"listing_cluster_depth": 4},
        {"sell_listing_floor": 91},
    ]
    assert all(database.validate_execution_quote({**quote, **changes}) is None for changes in malformed)
