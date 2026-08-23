import asyncio
import sqlite3
from pathlib import Path

import pytest

import database
import portfolio
from strategies import TransformationRegistry, TransformationStrategyProvider, validate_transformation


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "test.db"))

def test_additive_column_migration_is_idempotent(tmp_path, monkeypatch):
    path = tmp_path / "legacy.db"
    monkeypatch.setattr(database, "DB_PATH", str(path))
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE portfolio_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
            bankroll_json TEXT NOT NULL, positions_json TEXT NOT NULL,
            reserve REAL NOT NULL, expected_profit REAL NOT NULL,
            expected_duration_hours REAL, expected_distribution_json TEXT NOT NULL,
            baseline_hold_return REAL, baseline_random_return REAL,
            baseline_raw_roi_return REAL, baseline_flip_score_return REAL
        );
        CREATE TABLE trade_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_id INTEGER, position_id INTEGER, opportunity_id TEXT NOT NULL,
            confidence REAL, predicted_entry_price REAL, actual_entry_price REAL,
            predicted_exit_price REAL, actual_exit_price REAL,
            predicted_duration_hours REAL, actual_duration_hours REAL,
            predicted_profit REAL, realized_profit REAL, profitable INTEGER,
            recorded_at TEXT NOT NULL
        );
    """)
    conn.close()

    async def run():
        db = await database.get_db()
        first = {row["name"] for row in await (await db.execute("PRAGMA table_info(portfolio_recommendations)")).fetchall()}
        trade = {row["name"] for row in await (await db.execute("PRAGMA table_info(trade_records)")).fetchall()}
        await db.close()
        db = await database.get_db()
        second = {row["name"] for row in await (await db.execute("PRAGMA table_info(portfolio_recommendations)")).fetchall()}
        await db.close()
        return first, second, trade

    first, second, trade = asyncio.run(run())
    assert first == second
    assert {"league", "mode", "recommendation", "reason", "capital_currency", "chaos_per_divine"} <= first
    assert {"quantity", "chaos_per_divine", "capital_currency"} <= trade


def test_recommendation_journal_is_append_only(isolated_db):
    async def run():
        first = {
            "bankroll": 50, "positions": [{"id": "a"}], "reserve": 20,
            "expected_profit": 2, "expected_distribution": {"p": 0.7},
            "league": "Settlers", "mode": "paper", "recommendation": "Deploy",
            "reason": "validated", "capital_currency": "Divine", "chaos_per_divine": 200,
        }
        second = {"bankroll": 48, "positions": [{"id": "b"}], "reserve": 20, "expected_profit": 1, "expected_distribution": {"p": 0.6}}
        first_id = await portfolio.append_recommendation(first)
        await portfolio.append_recommendation(second)
        rows = await portfolio.list_recommendations()
        with pytest.raises(sqlite3.DatabaseError):
            db = await database.get_db()
            try:
                await db.execute("UPDATE portfolio_recommendations SET reserve = 0 WHERE id = ?", (first_id,))
            finally:
                await db.close()
        rows = await portfolio.list_recommendations()
        assert rows[0]["positions"] == [{"id": "a"}]
        assert rows[0]["expected_distribution"] == {"p": 0.7}
        assert isinstance(rows[0]["bankroll"], int)
        assert rows[0]["reserve"] == pytest.approx(20)
        assert rows[0]["league"] == "Settlers"
        assert rows[0]["mode"] == "paper"
        assert rows[0]["recommendation"] == "Deploy"
        assert rows[0]["reason"] == "validated"
        assert rows[0]["capital_currency"] == "Divine"
        assert rows[0]["chaos_per_divine"] == pytest.approx(200)
    asyncio.run(run())


def test_paper_realization_records_trade_and_equity(isolated_db):
    async def run():
        portfolio_id = await portfolio.create_paper_portfolio(50, 1)
        position_id = await portfolio.open_paper_position(
            portfolio_id, "a", 2, 10, predicted_exit_price=12,
            predicted_duration_hours=2, predicted_profit=4,
            opened_at="2026-01-01T00:00:00+00:00",
        )
        realized = await portfolio.realize_paper_position(
            position_id, 12, realized_at="2026-01-01T02:00:00+00:00", confidence=0.75,
        )
        assert realized["realized_profit"] == pytest.approx(4)
        assert realized["equity"] == pytest.approx(54)
        curve = await portfolio.paper_equity_curve(portfolio_id)
        trades = await portfolio.trade_records(portfolio_id)
        assert curve[-1]["equity"] == pytest.approx(54)
        assert trades[0]["actual_duration_hours"] == pytest.approx(2)
        assert trades[0]["predicted_profit"] == pytest.approx(4)
    asyncio.run(run())

def test_linked_trade_correction_updates_position_trade_and_equity(isolated_db):
    async def run():
        portfolio_id = await portfolio.create_paper_portfolio(100, 1)
        first = await portfolio.open_paper_position(
            portfolio_id, "correct-me", 2, 10, predicted_exit_price=12,
            predicted_duration_hours=2, predicted_profit=4,
        )
        second = await portfolio.open_paper_position(
            portfolio_id, "later", 1, 10, predicted_exit_price=13,
            predicted_duration_hours=2, predicted_profit=3,
        )
        await portfolio.realize_paper_position(first, 12, actual_duration_hours=2)
        realized = await portfolio.realize_paper_position(second, 11, actual_duration_hours=1)

        corrected = await portfolio.correct_linked_trade(
            realized["trade_id"], 3, 9, 12, 1.5, .8,
        )
        position = (await portfolio.paper_positions(portfolio_id))[1]
        curve = await portfolio.paper_equity_curve(portfolio_id)
        assert corrected["quantity"] == pytest.approx(3)
        assert corrected["actual_entry_price"] == pytest.approx(9)
        assert corrected["realized_profit"] == pytest.approx(9)
        assert corrected["predicted_profit"] == pytest.approx(9)
        assert position["quantity"] == pytest.approx(3)
        assert position["entry_price"] == pytest.approx(9)
        assert position["realized_profit"] == pytest.approx(9)
        assert curve[-2]["equity"] == pytest.approx(104)
        assert curve[-2]["realized_profit"] == pytest.approx(4)
        assert curve[-1]["equity"] == pytest.approx(113)
        assert curve[-1]["realized_profit"] == pytest.approx(9)

    asyncio.run(run())

def test_paper_close_is_idempotent_and_calibration_is_exact_and_shrunk(isolated_db):
    async def run():
        portfolio_id = await portfolio.create_paper_portfolio(100, 1)
        position_id = await portfolio.open_paper_position(
            portfolio_id, "matched", 1, 10,
            predicted_exit_price=14, predicted_duration_hours=24,
            predicted_profit=4, opened_at="2026-01-01T00:00:00+00:00",
        )
        first = await portfolio.realize_paper_position(
            position_id, 12, "2026-01-01T01:00:00+00:00", .8,
            actual_entry_at="2026-01-01T00:00:00+00:00",
            actual_duration_hours=1,
        )
        second = await portfolio.realize_paper_position(
            position_id, 12, "2026-01-01T01:00:00+00:00", .8,
            actual_duration_hours=1,
        )
        assert first["idempotent"] is False
        assert second["idempotent"] is True
        assert len(await portfolio.trade_records(portfolio_id)) == 1
        assert (await portfolio.paper_positions(portfolio_id, "realized"))[0]["status"] == "realized"
        assert (await portfolio.trade_records(portfolio_id))[0]["actual_entry_at"].startswith("2026-01-01")

        await portfolio.record_real_trade(
            "matched", 1, 10, 10, 20, 12, 24, 2, .5, chaos_per_divine=1,
        )
        calibration = await portfolio.calibrate_opportunity("matched", 40, 24)
        unrelated = await portfolio.calibrate_opportunity("other", 40, 24)
        assert calibration["applied"] is True
        assert calibration["median_return"] == pytest.approx(20)
        assert calibration["expected_return"] == pytest.approx(32)
        assert calibration["expected_duration_hours"] == pytest.approx(15)
        assert unrelated["applied"] is False
        assert unrelated["expected_return"] == pytest.approx(40)
        assert len(await portfolio.manual_trade_records("matched")) == 1
    asyncio.run(run())



def test_paper_positions_cannot_overcommit_liquid_capital(isolated_db):
    async def run():
        portfolio_id = await portfolio.create_paper_portfolio(50, 1)
        await portfolio.open_paper_position(portfolio_id, "a", 4, 10)
        status = await portfolio.paper_portfolio_status(portfolio_id)
        assert status == {
            "portfolio_id": portfolio_id,
            "currency": "Chaos",
            "equity": 50,
            "deployed": 40,
            "liquid": 10,
            "open_position_count": 1,
        }
        with pytest.raises(ValueError, match="liquid capital"):
            await portfolio.open_paper_position(portfolio_id, "b", 2, 10)
        assert (await portfolio.paper_portfolio_status(portfolio_id))["deployed"] == 40
    asyncio.run(run())


def test_manual_trade_record_validates_and_stores_realized_profit(isolated_db):
    async def run():
        record = await portfolio.record_real_trade(
            "manual-a", 2, 100, 100, 220, 200, 3, 4, 0.8,
            chaos_per_divine=200,
            recorded_at="2026-01-01T04:00:00+00:00",
        )
        assert record["predicted_profit"] == pytest.approx(240)
        assert record["realized_profit"] == pytest.approx(200)
        assert record["chaos_per_divine"] == pytest.approx(200)
        assert record["capital_currency"] == "Chaos"
        assert record["profitable"] is True
        rows = await portfolio.trade_records()
        assert rows[0]["portfolio_id"] is None
        assert rows[0]["realized_profit"] == pytest.approx(200)
        with pytest.raises(ValueError, match="confidence"):
            await portfolio.record_real_trade("bad", 1, 1, 1, 2, 2, 1, 1, 1.1, chaos_per_divine=200)
        with pytest.raises(ValueError, match="chaos_per_divine"):
            await portfolio.record_real_trade("bad", 1, 1, 1, 2, 2, 1, 1, 0.5, chaos_per_divine=0)
    asyncio.run(run())


def test_paper_positions_filter_and_performance_summary(isolated_db):
    async def run():
        portfolio_id = await portfolio.create_paper_portfolio(50, 1)
        first_recommendation = await portfolio.append_recommendation({
            "bankroll": 50, "positions": [{"id": "a"}], "reserve": 20,
            "expected_profit": 3, "expected_distribution": {"p": 0.6},
        })
        second_recommendation = await portfolio.append_recommendation({
            "bankroll": 48, "positions": [{"id": "b"}], "reserve": 20,
            "expected_profit": 4, "expected_distribution": {"p": 0.8},
        })
        first = await portfolio.open_paper_position(
            portfolio_id, "a", 1, 10, predicted_exit_price=13,
            predicted_duration_hours=3, predicted_profit=3,
            recommendation_id=first_recommendation,
            opened_at="2026-01-01T00:00:00+00:00",
        )
        await portfolio.realize_paper_position(first, 8, "2026-01-01T01:00:00+00:00", 0.6)
        second = await portfolio.open_paper_position(
            portfolio_id, "b", 1, 10, predicted_exit_price=14,
            predicted_duration_hours=3, predicted_profit=4,
            recommendation_id=second_recommendation,
            opened_at="2026-01-01T02:00:00+00:00",
        )
        assert len(await portfolio.paper_positions(portfolio_id, "open")) == 1
        await portfolio.realize_paper_position(second, 12, "2026-01-01T03:00:00+00:00", 0.8)
        assert len(await portfolio.paper_positions(portfolio_id, "open")) == 0
        assert len(await portfolio.paper_positions(portfolio_id, "realized")) == 2
        with pytest.raises(ValueError, match="status"):
            await portfolio.paper_positions(portfolio_id, "pending")
        summary = await portfolio.paper_performance(portfolio_id)
        assert summary["initial_equity"] == pytest.approx(50)
        assert summary["current_equity"] == pytest.approx(50)
        assert summary["total_return_percent"] == pytest.approx(0)
        assert summary["max_drawdown"] == pytest.approx(-2)
        assert summary["max_drawdown_percent"] == pytest.approx(-4)
        assert summary["realized_recommendation_count"] == 2
        assert summary["realized_trade_count"] == 2
        assert summary["profitable_count"] == 1
        assert summary["profitable_rate"] == pytest.approx(0.5)
        assert summary["median_position_profit"] == pytest.approx(0)
        assert summary["predicted_total_profit"] == pytest.approx(7)
        assert summary["realized_total_profit"] == pytest.approx(0)
        assert summary["baselines"]["hold_currency"]["return_percent"] == 0
        assert summary["baselines"]["random"]["available"] is False
        assert summary["baselines"]["random"]["return"] is None
        assert summary["calibration_buckets"]["60–70%"]["count"] == 1
        assert summary["calibration_buckets"]["80–90%"]["count"] == 1
    asyncio.run(run())

def test_calibration_math_and_buckets():
    result = portfolio.calibration_buckets([
        {"confidence": 0.70, "profitable": True},
        {"confidence": 0.75, "profitable": False},
    ])
    assert result["70–80%"]["predicted_probability"] == pytest.approx(0.725)
    assert result["70–80%"]["realized_success_rate"] == pytest.approx(0.5)
    assert result["70–80%"]["calibration_error"] == pytest.approx(0.225)


def test_transformation_registry_rejects_unmodelled_and_incomplete_outcomes():
    with pytest.raises(ValueError, match="unmodelled"):
        validate_transformation({"id": "bad", "steps": [{"action": "unknown"}]})
    with pytest.raises(ValueError, match="probabilities"):
        validate_transformation({
            "id": "bad", "name": "bad", "inputs": [{"item": "Divine", "quantity": 1}],
            "deterministic_costs": [{"item": "Divine", "quantity": 1}], "probabilistic_costs": [],
            "outputs": [{"item": "Chaos", "quantity": 1, "probability": 0.5}],
            "expected_execution_time_hours": 1, "risk_model": {"kind": "finite_outcome"},
        })


def test_transform_fixture_is_rejected_until_verified():
    registry = TransformationRegistry.from_json(Path(__file__).with_name("transformations.experimental.json"))
    provider = TransformationStrategyProvider(registry)
    assert registry.records()[0]["status"] == "Rejected"
    context = {"prices": {"Divine": 100, "Chaos": 110}, "bankroll": 50}
    assert provider.evaluate(context) == []
    assert provider.discover(context) == []

def test_reallocation_churn_guard_accounts_for_costs():
    decision = portfolio.should_reallocate(0.08, 0.10, exit_cost=0.01, entry_cost=0.01, minimum_advantage=0.01)
    assert not decision.should_reallocate
    assert decision.net_advantage == pytest.approx(0)
