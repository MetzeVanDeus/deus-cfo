"""Persistence and paper-evaluation services for decision support (never execution)."""

from __future__ import annotations

import json
import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

import database


@dataclass(frozen=True)
class ExitLogic:
    profit_target: float | None = None
    time_exit_hours: float | None = None
    invalidation_condition: str | None = None
    reallocation_condition: str | None = None


@dataclass(frozen=True)
class TradePlan:
    opportunity_id: str
    action: str
    target_entry: float
    maximum_entry: float
    capital_allocation: float
    quantity: float
    target_exit: float | None
    expected_profit: float
    expected_duration_hours: float | None
    entry_condition: str
    exit_logic: ExitLogic


@dataclass(frozen=True)
class ReallocationDecision:
    should_reallocate: bool
    net_advantage: float
    reason: str


def reallocation_advantage(current_remaining_return: float, new_return: float,
                            exit_cost: float = 0.0, entry_cost: float = 0.0) -> float:
    """Return the new position's net edge over holding the current one."""
    if min(exit_cost, entry_cost) < 0:
        raise ValueError("execution costs cannot be negative")
    return new_return - current_remaining_return - exit_cost - entry_cost


def should_reallocate(current_remaining_return: float, new_return: float,
                      exit_cost: float = 0.0, entry_cost: float = 0.0,
                      minimum_advantage: float = 0.0) -> ReallocationDecision:
    advantage = reallocation_advantage(current_remaining_return, new_return, exit_cost, entry_cost)
    if minimum_advantage < 0:
        raise ValueError("minimum_advantage cannot be negative")
    if advantage > minimum_advantage:
        return ReallocationDecision(True, advantage, "net advantage exceeds churn guard")
    return ReallocationDecision(False, advantage, "execution costs or minimum advantage block churn")


_BUCKETS = ((0.5, 0.6, "50–60%"), (0.6, 0.7, "60–70%"), (0.7, 0.8, "70–80%"), (0.8, 0.9, "80–90%"), (0.9, 1.0000001, "90%+"))


def confidence_bucket(probability: float) -> str:
    if not 0 <= probability <= 1:
        raise ValueError("confidence must be between 0 and 1")
    for lower, upper, label in _BUCKETS:
        if lower <= probability < upper:
            return label
    return "below-50%"


def calibration_buckets(records: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, float | int]]:
    """Compare mean predicted probability to realized success by confidence bucket."""
    grouped: dict[str, list[tuple[float, bool]]] = {}
    for record in records:
        confidence = float(record["confidence"])
        bucket = confidence_bucket(confidence)
        grouped.setdefault(bucket, []).append((confidence, bool(record["profitable"])))
    result: dict[str, dict[str, float | int]] = {}
    for bucket, values in grouped.items():
        predicted = sum(value[0] for value in values) / len(values)
        realized = sum(value[1] for value in values) / len(values)
        result[bucket] = {
            "count": len(values),
            "predicted_probability": round(predicted, 6),
            "realized_success_rate": round(realized, 6),
            "calibration_error": round(abs(predicted - realized), 6),
        }
    return result

def calibrate_probability(
    raw_probability: float,
    records: Sequence[Mapping[str, Any]],
    *,
    minimum_samples: int = 20,
    prior_strength: float = 20.0,
) -> dict[str, Any]:
    """Shrink a bucket's realized rate toward the candidate's raw probability.

    The Beta-style prior has ``prior_strength`` pseudo-observations with the
    candidate's raw probability as its mean; no adjustment is applied until
    ``minimum_samples`` completed records exist in the same confidence bucket.
    """
    if not 0 <= raw_probability <= 1:
        raise ValueError("raw_probability must be between 0 and 1")
    if minimum_samples < 1:
        raise ValueError("minimum_samples must be positive")
    if prior_strength < 0 or not math.isfinite(prior_strength):
        raise ValueError("prior_strength must be non-negative and finite")
    bucket = confidence_bucket(raw_probability)
    completed = [
        record for record in records
        if record.get("confidence") is not None
        and record.get("profitable") is not None
        and confidence_bucket(float(record["confidence"])) == bucket
    ]
    count = len(completed)
    wins = sum(bool(record["profitable"]) for record in completed)
    applied = count >= minimum_samples
    calibrated = (
        (wins + prior_strength * raw_probability) / (count + prior_strength)
        if applied else raw_probability
    )
    reason = "applied" if applied else f"insufficient realized samples ({count}/{minimum_samples})"
    return {
        "bucket": bucket,
        "raw": raw_probability,
        "calibrated": calibrated,
        "bucket_count": count,
        "wins": wins,
        "minimum_samples": minimum_samples,
        "prior_strength": prior_strength,
        "applied": applied,
        "reason": reason,
    }
async def append_recommendation(recommendation: Mapping[str, Any]) -> int:
    """Append one recommendation; this function never updates prior journal rows."""
    required = {"bankroll", "positions", "reserve", "expected_profit", "expected_distribution"}
    missing = required - set(recommendation)
    if missing:
        raise ValueError(f"recommendation missing {sorted(missing)}")
    db = await database.get_db()
    try:
        cursor = await db.execute(
            """INSERT INTO portfolio_recommendations
               (created_at, bankroll_json, positions_json, reserve, expected_profit,
                expected_duration_hours, expected_distribution_json,
                baseline_hold_return, baseline_random_return,
                baseline_raw_roi_return, baseline_flip_score_return,
                league, mode, recommendation, reason, capital_currency, chaos_per_divine)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                recommendation.get("timestamp", database.now_iso()),
                json.dumps(recommendation["bankroll"], sort_keys=True),
                json.dumps(recommendation["positions"], sort_keys=True),
                float(recommendation["reserve"]),
                float(recommendation["expected_profit"]),
                recommendation.get("expected_duration_hours", recommendation.get("expected_duration")),
                json.dumps(recommendation["expected_distribution"], sort_keys=True),
                recommendation.get("baseline_hold_return"), recommendation.get("baseline_random_return"),
                recommendation.get("baseline_raw_roi_return"), recommendation.get("baseline_flip_score_return"),
                recommendation.get("league"), recommendation.get("mode"),
                recommendation.get("recommendation"), recommendation.get("reason"),
                recommendation.get("capital_currency"), recommendation.get("chaos_per_divine"),
            ),
        )
        await db.commit()
        return int(cursor.lastrowid)
    finally:
        await db.close()


async def list_recommendations() -> list[dict[str, Any]]:
    db = await database.get_db()
    try:
        cursor = await db.execute("SELECT * FROM portfolio_recommendations ORDER BY id")
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["bankroll"] = json.loads(item.pop("bankroll_json"))
            item["positions"] = json.loads(item.pop("positions_json"))
            item["expected_distribution"] = json.loads(item.pop("expected_distribution_json"))
            result.append(item)
        return result
    finally:
        await db.close()


async def create_paper_portfolio(
    initial_bankroll: float,
    chaos_per_divine: float,
    name: str = "default",
) -> int:
    if initial_bankroll < 0 or not name:
        raise ValueError("paper portfolio requires a name and non-negative Divine bankroll")
    if not isinstance(chaos_per_divine, (int, float)) or not math.isfinite(chaos_per_divine) or chaos_per_divine <= 0:
        raise ValueError("chaos_per_divine must be positive and finite")
    initial_chaos = float(initial_bankroll) * float(chaos_per_divine)
    db = await database.get_db()
    try:
        created_at = database.now_iso()
        cursor = await db.execute(
            "INSERT INTO paper_portfolios (name, initial_bankroll, currency, created_at) VALUES (?, ?, 'Chaos', ?)",
            (name, initial_chaos, created_at),
        )
        await db.execute(
            "INSERT INTO paper_equity (portfolio_id, timestamp, equity, realized_profit, source) VALUES (?, ?, ?, ?, ?)",
            (cursor.lastrowid, created_at, initial_chaos, 0, "initial"),
        )
        await db.commit()
        return int(cursor.lastrowid)
    finally:
        await db.close()

async def open_paper_position(portfolio_id: int, opportunity_id: str, quantity: float,
                              entry_price: float, predicted_exit_price: float | None = None,
                              predicted_duration_hours: float | None = None,
                              predicted_profit: float | None = None,
                              recommendation_id: int | None = None,
                              opened_at: str | None = None) -> int:
    if quantity <= 0 or entry_price <= 0 or not opportunity_id:
        raise ValueError("paper position quantity, entry price, and opportunity are required")
    cost = quantity * entry_price
    db = await database.get_db()
    try:
        await db.execute("BEGIN IMMEDIATE")
        portfolio_cursor = await db.execute(
            "SELECT id FROM paper_portfolios WHERE id = ?", (portfolio_id,)
        )
        if await portfolio_cursor.fetchone() is None:
            raise ValueError("paper portfolio not found")
        equity_cursor = await db.execute(
            "SELECT equity FROM paper_equity WHERE portfolio_id = ? ORDER BY id DESC LIMIT 1",
            (portfolio_id,),
        )
        equity_row = await equity_cursor.fetchone()
        deployed_cursor = await db.execute(
            "SELECT COALESCE(SUM(quantity * entry_price), 0) AS deployed "
            "FROM paper_positions WHERE portfolio_id = ? AND status = 'open'",
            (portfolio_id,),
        )
        deployed = float((await deployed_cursor.fetchone())["deployed"])
        equity = float(equity_row["equity"]) if equity_row else 0.0
        if cost > equity - deployed + 1e-9:
            raise ValueError("paper position exceeds liquid capital")
        cursor = await db.execute(
            """INSERT INTO paper_positions
               (portfolio_id, recommendation_id, opportunity_id, quantity, entry_price,
                predicted_exit_price, predicted_duration_hours, predicted_profit, opened_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (portfolio_id, recommendation_id, opportunity_id, quantity, entry_price,
             predicted_exit_price, predicted_duration_hours, predicted_profit, opened_at or database.now_iso()),
        )
        await db.commit()
        return int(cursor.lastrowid)
    finally:
        await db.close()


async def paper_portfolio_status(portfolio_id: int) -> dict[str, Any]:
    """Return current equity, deployed capital, liquid capital, and open count."""
    db = await database.get_db()
    try:
        portfolio_cursor = await db.execute(
            "SELECT id FROM paper_portfolios WHERE id = ?", (portfolio_id,)
        )
        if await portfolio_cursor.fetchone() is None:
            raise ValueError("paper portfolio not found")
        equity_cursor = await db.execute(
            "SELECT equity FROM paper_equity WHERE portfolio_id = ? ORDER BY id DESC LIMIT 1",
            (portfolio_id,),
        )
        equity_row = await equity_cursor.fetchone()
        positions_cursor = await db.execute(
            "SELECT COALESCE(SUM(quantity * entry_price), 0) AS deployed, "
            "COUNT(*) AS open_position_count FROM paper_positions "
            "WHERE portfolio_id = ? AND status = 'open'",
            (portfolio_id,),
        )
        positions = await positions_cursor.fetchone()
        equity = float(equity_row["equity"]) if equity_row else 0.0
        deployed = float(positions["deployed"])
        portfolio_info = await (await db.execute(
            "SELECT currency FROM paper_portfolios WHERE id = ?", (portfolio_id,)
        )).fetchone()
        return {
            "portfolio_id": portfolio_id,
            "currency": portfolio_info["currency"] if portfolio_info else "Chaos",
            "equity": equity,
            "deployed": deployed,
            "liquid": equity - deployed,
            "open_position_count": int(positions["open_position_count"]),
        }
    finally:
        await db.close()


async def paper_positions(portfolio_id: int, status: str | None = None) -> list[dict[str, Any]]:
    """List paper positions, optionally filtered to open or realized rows."""
    if status not in (None, "open", "realized"):
        raise ValueError("status must be open or realized")
    db = await database.get_db()
    try:
        await _require_portfolio(db, portfolio_id)
        if status is None:
            cursor = await db.execute(
                "SELECT * FROM paper_positions WHERE portfolio_id = ? ORDER BY id",
                (portfolio_id,),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM paper_positions WHERE portfolio_id = ? AND status = ? ORDER BY id",
                (portfolio_id, status),
            )
        return [dict(row) for row in await cursor.fetchall()]
    finally:
        await db.close()


async def realize_paper_position(
    position_id: int,
    exit_price: float,
    realized_at: str | None = None,
    confidence: float | None = None,
    actual_entry_at: str | None = None,
    actual_duration_hours: float | None = None,
    actual_entry_price: float | None = None,
    quantity: float | None = None,
) -> dict[str, Any]:
    if exit_price <= 0:
        raise ValueError("exit price must be positive")
    if actual_duration_hours is not None and (
        not isinstance(actual_duration_hours, (int, float))
        or not math.isfinite(actual_duration_hours)
        or actual_duration_hours < 0
    ):
        raise ValueError("actual duration must be non-negative and finite")
    for name, value in (("actual_entry_price", actual_entry_price), ("quantity", quantity)):
        if value is not None and (
            not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0
        ):
            raise ValueError(f"{name} must be positive and finite")
    closed_at = realized_at or database.now_iso()
    _parse_time(closed_at)
    if actual_entry_at is not None:
        _parse_time(actual_entry_at)
    db = await database.get_db()
    try:
        await db.execute("BEGIN IMMEDIATE")
        cursor = await db.execute("SELECT * FROM paper_positions WHERE id = ?", (position_id,))
        position = await cursor.fetchone()
        if position is None:
            raise ValueError("paper position not found")
        existing_cursor = await db.execute(
            "SELECT * FROM trade_records WHERE position_id = ? ORDER BY id LIMIT 1",
            (position_id,),
        )
        existing_trade = await existing_cursor.fetchone()
        if position["status"] != "open":
            if existing_trade is None:
                raise ValueError("paper position is already realized without a calibration record")
            equity_cursor = await db.execute(
                "SELECT equity FROM paper_equity WHERE portfolio_id = ? ORDER BY id DESC LIMIT 1",
                (position["portfolio_id"],),
            )
            equity_row = await equity_cursor.fetchone()
            return {
                "position_id": position_id,
                "trade_id": int(existing_trade["id"]),
                "realized_profit": float(existing_trade["realized_profit"] or 0),
                "actual_duration_hours": float(existing_trade["actual_duration_hours"] or 0),
                "equity": float(equity_row["equity"]) if equity_row else None,
                "status": "realized",
                "idempotent": True,
                "trade": dict(existing_trade),
            }
        opened_at = actual_entry_at or position["opened_at"]
        opened = _parse_time(opened_at)
        actual_duration = (
            float(actual_duration_hours)
            if actual_duration_hours is not None
            else max(0.0, (_parse_time(closed_at) - opened).total_seconds() / 3600)
        )
        entry_price = float(actual_entry_price if actual_entry_price is not None else position["entry_price"])
        actual_quantity = float(quantity if quantity is not None else position["quantity"])
        predicted_profit = (
            (float(position["predicted_exit_price"]) - float(position["entry_price"])) * actual_quantity
            if position["predicted_exit_price"] is not None
            else position["predicted_profit"]
        )
        realized_profit = (exit_price - entry_price) * actual_quantity
        await db.execute(
            """UPDATE paper_positions SET quantity = ?, entry_price = ?, predicted_profit = ?,
               status = 'realized', realized_exit_price = ?, realized_at = ?, realized_profit = ?
               WHERE id = ?""",
            (actual_quantity, entry_price, predicted_profit, exit_price, closed_at, realized_profit, position_id),
        )
        trade_cursor = await db.execute(
            """INSERT INTO trade_records
               (portfolio_id, position_id, opportunity_id, confidence,
                predicted_entry_price, actual_entry_price, predicted_exit_price,
                actual_exit_price, predicted_duration_hours, actual_duration_hours,
                predicted_profit, realized_profit, profitable, recorded_at,
                quantity, chaos_per_divine, capital_currency, actual_entry_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (position["portfolio_id"], position_id, position["opportunity_id"], confidence,
             position["entry_price"], entry_price, position["predicted_exit_price"],
             exit_price, position["predicted_duration_hours"], actual_duration,
             predicted_profit, realized_profit, int(realized_profit > 0), closed_at,
             actual_quantity, None, "Chaos", opened_at),
        )
        trade_id = int(trade_cursor.lastrowid)
        equity_cursor = await db.execute(
            "SELECT equity FROM paper_equity WHERE portfolio_id = ? ORDER BY id DESC LIMIT 1",
            (position["portfolio_id"],),
        )
        equity_row = await equity_cursor.fetchone()
        if equity_row is None:
            portfolio_cursor = await db.execute(
                "SELECT initial_bankroll FROM paper_portfolios WHERE id = ?",
                (position["portfolio_id"],),
            )
            portfolio = await portfolio_cursor.fetchone()
            if portfolio is None:
                raise ValueError("paper portfolio not found")
            equity = portfolio["initial_bankroll"] + realized_profit
        else:
            equity = equity_row["equity"] + realized_profit
        await db.execute(
            """INSERT INTO paper_equity
               (portfolio_id, timestamp, equity, realized_profit, source, trade_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (position["portfolio_id"], closed_at, equity, realized_profit, "paper_realization", trade_id),
        )
        await db.commit()
        trade_cursor = await db.execute("SELECT * FROM trade_records WHERE id = ?", (trade_id,))
        trade = await trade_cursor.fetchone()
        return {
            "position_id": position_id,
            "trade_id": trade_id,
            "realized_profit": realized_profit,
            "actual_duration_hours": actual_duration,
            "equity": equity,
            "status": "realized",
            "idempotent": False,
            "trade": dict(trade),
        }
    finally:
        await db.close()

async def correct_linked_trade(
    trade_id: int,
    quantity: float,
    actual_entry_price: float,
    actual_exit_price: float,
    actual_duration_hours: float,
    confidence: float | None = None,
) -> dict[str, Any]:
    """Correct a realized linked trade and its portfolio ledger atomically."""
    for name, value in (
        ("quantity", quantity),
        ("actual_entry_price", actual_entry_price),
        ("actual_exit_price", actual_exit_price),
    ):
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be positive and finite")
    if not isinstance(actual_duration_hours, (int, float)) or not math.isfinite(actual_duration_hours) or actual_duration_hours < 0:
        raise ValueError("actual_duration_hours must be non-negative and finite")
    if confidence is not None and (
        not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1
    ):
        raise ValueError("confidence must be between 0 and 1")

    db = await database.get_db()
    try:
        await db.execute("BEGIN IMMEDIATE")
        trade = await (await db.execute(
            "SELECT * FROM trade_records WHERE id = ?", (trade_id,)
        )).fetchone()
        if trade is None or trade["position_id"] is None or trade["portfolio_id"] is None:
            raise ValueError("linked trade not found")
        position = await (await db.execute(
            "SELECT * FROM paper_positions WHERE id = ?", (trade["position_id"],)
        )).fetchone()
        if position is None or position["status"] != "realized":
            raise ValueError("linked realized position not found")
        equity_row = await (await db.execute(
            """SELECT id FROM paper_equity
               WHERE portfolio_id = ? AND trade_id = ? AND source = 'paper_realization'""",
            (trade["portfolio_id"], trade_id),
        )).fetchone()
        if equity_row is None:
            raise ValueError("linked equity record not found")

        realized_profit = (actual_exit_price - actual_entry_price) * quantity
        old_profit = float(trade["realized_profit"] or 0)
        delta = realized_profit - old_profit
        predicted_profit = (
            (float(trade["predicted_exit_price"]) - float(trade["predicted_entry_price"])) * quantity
            if trade["predicted_exit_price"] is not None and trade["predicted_entry_price"] is not None
            else trade["predicted_profit"]
        )
        await db.execute(
            """UPDATE paper_positions SET quantity = ?, entry_price = ?, realized_exit_price = ?,
               predicted_profit = ?, realized_profit = ? WHERE id = ?""",
            (quantity, actual_entry_price, actual_exit_price, predicted_profit, realized_profit, position["id"]),
        )
        await db.execute(
            """UPDATE trade_records SET quantity = ?, actual_entry_price = ?, actual_exit_price = ?,
               actual_duration_hours = ?, confidence = ?, predicted_profit = ?, realized_profit = ?,
               profitable = ? WHERE id = ?""",
            (quantity, actual_entry_price, actual_exit_price, actual_duration_hours, confidence,
             predicted_profit, realized_profit, int(realized_profit > 0), trade_id),
        )
        await db.execute(
            "UPDATE paper_equity SET equity = equity + ? WHERE portfolio_id = ? AND id >= ?",
            (delta, trade["portfolio_id"], equity_row["id"]),
        )
        await db.execute(
            "UPDATE paper_equity SET realized_profit = ? WHERE id = ?",
            (realized_profit, equity_row["id"]),
        )
        await db.commit()
        corrected = await (await db.execute(
            "SELECT * FROM trade_records WHERE id = ?", (trade_id,)
        )).fetchone()
        return dict(corrected)
    finally:
        await db.close()



async def paper_equity_curve(portfolio_id: int) -> list[dict[str, Any]]:
    db = await database.get_db()
    try:
        cursor = await db.execute("SELECT * FROM paper_equity WHERE portfolio_id = ? ORDER BY id", (portfolio_id,))
        return [dict(row) for row in await cursor.fetchall()]
    finally:
        await db.close()


async def trade_records(portfolio_id: int | None = None) -> list[dict[str, Any]]:
    db = await database.get_db()
    try:
        if portfolio_id is None:
            cursor = await db.execute("SELECT * FROM trade_records ORDER BY id")
        else:
            cursor = await db.execute(
                "SELECT * FROM trade_records WHERE portfolio_id = ? ORDER BY id",
                (portfolio_id,),
            )
        return [dict(row) for row in await cursor.fetchall()]
    finally:
        await db.close()


async def manual_trade_records(opportunity_id: str | None = None) -> list[dict[str, Any]]:
    """Return unlinked manual observations without mixing them into a portfolio."""
    db = await database.get_db()
    try:
        query = "SELECT * FROM trade_records WHERE position_id IS NULL"
        params: tuple[Any, ...] = ()
        if opportunity_id:
            query += " AND opportunity_id = ?"
            params = (opportunity_id,)
        query += " ORDER BY id"
        cursor = await db.execute(query, params)
        return [dict(row) for row in await cursor.fetchall()]
    finally:
        await db.close()


async def calibrate_opportunity(
    opportunity_id: str,
    fallback_return: float | None = None,
    fallback_duration_hours: float | None = None,
    *,
    minimum_samples: int = 2,
    prior_strength: float = 3.0,
) -> dict[str, Any]:
    """Use only completed observations for this exact opportunity id."""
    if not opportunity_id:
        raise ValueError("opportunity_id is required")
    db = await database.get_db()
    try:
        cursor = await db.execute(
            """SELECT actual_entry_price, quantity, chaos_per_divine,
                      capital_currency, realized_profit, actual_duration_hours
               FROM trade_records
               WHERE opportunity_id = ?
                 AND realized_profit IS NOT NULL
                 AND actual_duration_hours IS NOT NULL
               ORDER BY id""",
            (opportunity_id,),
        )
        rows = await cursor.fetchall()
    finally:
        await db.close()
    returns: list[float] = []
    durations: list[float] = []
    for row in rows:
        capital = float(row["actual_entry_price"] or 0) * float(row["quantity"] or 0)
        profit = float(row["realized_profit"])
        if row["capital_currency"] != "Chaos" and row["chaos_per_divine"]:
            rate = float(row["chaos_per_divine"])
            capital /= rate
            profit /= rate
        if capital > 0:
            returns.append(profit / capital * 100)
        durations.append(max(0.0, float(row["actual_duration_hours"])))
    count = min(len(returns), len(durations))
    if count < minimum_samples:
        return {
            "opportunity_id": opportunity_id,
            "applied": False,
            "sample_size": count,
            "median_return": statistics.median(returns) if returns else None,
            "median_duration_hours": statistics.median(durations) if durations else None,
            "expected_return": fallback_return,
            "expected_duration_hours": fallback_duration_hours,
        }
    observed_return = statistics.median(returns)
    observed_duration = statistics.median(durations)
    weight = count / (count + max(0.0, prior_strength))
    estimated_return = (
        observed_return if fallback_return is None
        else float(fallback_return) + weight * (observed_return - float(fallback_return))
    )
    estimated_duration = (
        observed_duration if fallback_duration_hours is None
        else float(fallback_duration_hours)
        + weight * (observed_duration - float(fallback_duration_hours))
    )
    return {
        "opportunity_id": opportunity_id,
        "applied": True,
        "sample_size": count,
        "weight": weight,
        "median_return": observed_return,
        "median_duration_hours": observed_duration,
        "expected_return": estimated_return,
        "expected_duration_hours": max(0.25, estimated_duration),
    }

async def record_real_trade(
    opportunity_id: str,
    quantity: float,
    predicted_entry_price: float,
    actual_entry_price: float,
    predicted_exit_price: float,
    actual_exit_price: float,
    predicted_duration_hours: float,
    actual_duration_hours: float,
    confidence: float,
    chaos_per_divine: float,
    recorded_at: str | None = None,
) -> dict[str, Any]:
    """Record a manual chaos-denominated trade with chaos-denominated profit."""
    if not opportunity_id:
        raise ValueError("opportunity_id is required")
    for name, value in (
        ("quantity", quantity), ("predicted_entry_price", predicted_entry_price),
        ("actual_entry_price", actual_entry_price), ("predicted_exit_price", predicted_exit_price),
        ("actual_exit_price", actual_exit_price),
    ):
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be positive and finite")
    for name, value in (("predicted_duration_hours", predicted_duration_hours), ("actual_duration_hours", actual_duration_hours)):
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f"{name} must be non-negative and finite")
    if not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise ValueError("confidence must be between 0 and 1")
    if not isinstance(chaos_per_divine, (int, float)) or not math.isfinite(chaos_per_divine) or chaos_per_divine <= 0:
        raise ValueError("chaos_per_divine must be positive and finite")
    predicted_profit = (predicted_exit_price - predicted_entry_price) * quantity
    realized_profit = (actual_exit_price - actual_entry_price) * quantity
    if not math.isfinite(predicted_profit) or not math.isfinite(realized_profit):
        raise ValueError("profit must be finite")
    timestamp = recorded_at or database.now_iso()
    _parse_time(timestamp)
    db = await database.get_db()
    try:
        cursor = await db.execute(
            """INSERT INTO trade_records
               (portfolio_id, position_id, opportunity_id, confidence,
                predicted_entry_price, actual_entry_price, predicted_exit_price,
                actual_exit_price, predicted_duration_hours, actual_duration_hours,
                predicted_profit, realized_profit, profitable, recorded_at,
                quantity, chaos_per_divine, capital_currency)
               VALUES (NULL, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (opportunity_id, confidence, predicted_entry_price, actual_entry_price,
             predicted_exit_price, actual_exit_price, predicted_duration_hours,
             actual_duration_hours, predicted_profit, realized_profit,
             int(realized_profit > 0), timestamp, quantity, chaos_per_divine, "Chaos"),
        )
        await db.commit()
        return {
            "id": int(cursor.lastrowid),
            "portfolio_id": None,
            "position_id": None,
            "opportunity_id": opportunity_id,
            "confidence": confidence,
            "predicted_entry_price": predicted_entry_price,
            "actual_entry_price": actual_entry_price,
            "predicted_exit_price": predicted_exit_price,
            "actual_exit_price": actual_exit_price,
            "predicted_duration_hours": predicted_duration_hours,
            "actual_duration_hours": actual_duration_hours,
            "predicted_profit": predicted_profit,
            "realized_profit": realized_profit,
            "quantity": quantity,
            "chaos_per_divine": chaos_per_divine,
            "capital_currency": "Chaos",
            "profitable": bool(realized_profit > 0),
            "recorded_at": timestamp,
        }
    finally:
        await db.close()


async def paper_performance(portfolio_id: int) -> dict[str, Any]:
    """Summarize realized paper results without inventing unavailable baselines."""
    db = await database.get_db()
    try:
        await _require_portfolio(db, portfolio_id)
        curve_cursor = await db.execute(
            "SELECT equity FROM paper_equity WHERE portfolio_id = ? ORDER BY id",
            (portfolio_id,),
        )
        curve = [float(row["equity"]) for row in await curve_cursor.fetchall()]
        if not curve:
            portfolio_cursor = await db.execute(
                "SELECT initial_bankroll FROM paper_portfolios WHERE id = ?", (portfolio_id,)
            )
            initial = float((await portfolio_cursor.fetchone())["initial_bankroll"])
            curve = [initial]
        initial_equity, current_equity = curve[0], curve[-1]
        total_return = current_equity - initial_equity
        total_return_percent = total_return / initial_equity * 100 if initial_equity else 0.0
        peak = curve[0]
        max_drawdown = 0.0
        max_drawdown_percent = 0.0
        for equity in curve:
            peak = max(peak, equity)
            max_drawdown = min(max_drawdown, equity - peak)
            if peak:
                max_drawdown_percent = min(max_drawdown_percent, (equity - peak) / peak * 100)

        trades_cursor = await db.execute(
            "SELECT * FROM trade_records WHERE portfolio_id = ? ORDER BY id", (portfolio_id,)
        )
        trades = [dict(row) for row in await trades_cursor.fetchall()]
        positions_cursor = await db.execute(
            "SELECT quantity, entry_price, realized_profit FROM paper_positions "
            "WHERE portfolio_id = ? AND status = 'realized' ORDER BY id",
            (portfolio_id,),
        )
        positions = [dict(row) for row in await positions_cursor.fetchall()]
        recommendation_cursor = await db.execute(
            "SELECT COUNT(DISTINCT recommendation_id) AS count FROM paper_positions "
            "WHERE portfolio_id = ? AND status = 'realized' AND recommendation_id IS NOT NULL",
            (portfolio_id,),
        )
        realized_recommendations = int((await recommendation_cursor.fetchone())["count"])
        profitable_count = sum(1 for trade in trades if trade["profitable"])
        position_profits = [float(position["realized_profit"]) for position in positions]
        position_returns = [
            float(position["realized_profit"]) / (float(position["quantity"]) * float(position["entry_price"]))
            for position in positions
        ]
        calibration_records = [
            {"confidence": trade["confidence"], "profitable": trade["profitable"]}
            for trade in trades if trade["confidence"] is not None
        ]
        baselines = {
            "hold_currency": {"available": True, "return": 0.0, "return_percent": 0.0},
            "random": {"available": False, "return": None, "return_percent": None},
            "raw_roi": {"available": False, "return": None, "return_percent": None},
            "flip_score": {"available": False, "return": None, "return_percent": None},
        }
        return {
            "portfolio_id": portfolio_id,
            "initial_equity": initial_equity,
            "current_equity": current_equity,
            "total_return": total_return,
            "total_return_percent": total_return_percent,
            "max_drawdown": max_drawdown,
            "max_drawdown_percent": max_drawdown_percent,
            "realized_recommendation_count": realized_recommendations,
            "realized_trade_count": len(trades),
            "profitable_count": profitable_count,
            "profitable_rate": profitable_count / len(trades) if trades else 0.0,
            "median_position_return": statistics.median(position_returns) if position_returns else 0.0,
            "median_position_return_percent": (statistics.median(position_returns) * 100) if position_returns else 0.0,
            "median_position_profit": statistics.median(position_profits) if position_profits else 0.0,
            "predicted_total_profit": sum(float(trade["predicted_profit"] or 0) for trade in trades),
            "realized_total_profit": sum(float(trade["realized_profit"] or 0) for trade in trades),
            "calibration_buckets": calibration_buckets(calibration_records),
            "baselines": baselines,
            "baseline_availability": {name: values["available"] for name, values in baselines.items()},
        }
    finally:
        await db.close()


async def _require_portfolio(db: Any, portfolio_id: int) -> None:
    cursor = await db.execute("SELECT id FROM paper_portfolios WHERE id = ?", (portfolio_id,))
    if await cursor.fetchone() is None:
        raise ValueError("paper portfolio not found")


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
