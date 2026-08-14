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

    async def run():
        await database.insert_snapshots([snapshot("Currency", "old")], "2000-01-01T00:00:00+00:00")
        await database.insert_snapshots([snapshot("Currency", "keep")])
        await database.insert_snapshots([snapshot("SkillGem", "drop")])
        await database.insert_cx_hour([cx_record], "2000-01-01T00:00:00+00:00")

        deleted = await database.prune_market_data({"Currency"}, 1, 1)
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
            assert [tuple(row) for row in rows] == [("Currency", "keep")]
            max_pages = int((await (await db.execute("PRAGMA max_page_count")).fetchone())[0])
            page_size = int((await (await db.execute("PRAGMA page_size")).fetchone())[0])
            assert max_pages * page_size <= database.MAX_DATABASE_BYTES
        finally:
            await db.close()

    asyncio.run(run())

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
