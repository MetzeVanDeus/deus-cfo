"""SQLite snapshot storage for DeusCFO."""

import asyncio
import json
import math
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import aiosqlite

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)
_DEFAULT_DB_PATH = os.path.join(_BACKEND_DIR, "deuscfo.db")
_DATA_DIR = os.environ.get("DEUSCFO_DATA_DIR", "").strip()
if _DATA_DIR:
    _DATA_DIR = os.path.abspath(_DATA_DIR)
    os.makedirs(_DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(_DATA_DIR, "deuscfo.db") if _DATA_DIR else _DEFAULT_DB_PATH
_schema_lock = asyncio.Lock()
_schema_path: str | None = None
MAX_DATABASE_BYTES = 600 * 1024 * 1024
MAX_WAL_BYTES = 32 * 1024 * 1024
SNAPSHOT_RETENTION_DAYS = 14
CX_RETENTION_DAYS = SNAPSHOT_RETENTION_DAYS
PROJECT_ROOT = _PROJECT_ROOT
PROJECT_LIMIT_BYTES = 1024 * 1024 * 1024
COLLECTION_STOP_BYTES = 850 * 1024 * 1024

_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    league TEXT NOT NULL,
    category TEXT NOT NULL,
    item_id TEXT NOT NULL,
    item_name TEXT NOT NULL,
    variant TEXT NOT NULL DEFAULT '',
    price_chaos REAL NOT NULL,
    volume REAL NOT NULL DEFAULT 0,
    listing_count REAL NOT NULL DEFAULT 0,
    icon TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'poe.ninja',
    observation_type TEXT NOT NULL DEFAULT 'DIRECT_OBSERVATION',
    observed_at TEXT NOT NULL DEFAULT '',
    market_timestamp TEXT NOT NULL DEFAULT '',
    confidence_grade TEXT NOT NULL DEFAULT 'B',
    execution_quote TEXT
);
CREATE INDEX IF NOT EXISTS idx_snapshots_lookup
    ON snapshots (league, category, item_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_snapshots_timestamp
    ON snapshots (timestamp);
CREATE UNIQUE INDEX IF NOT EXISTS idx_snapshots_observation
    ON snapshots (timestamp, league, category, item_id, variant);

CREATE TABLE IF NOT EXISTS cx_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    league TEXT NOT NULL,
    market_id TEXT NOT NULL,
    item_a TEXT NOT NULL,
    item_b TEXT NOT NULL,
    volume_a REAL,
    volume_b REAL,
    lowest_stock_a REAL,
    lowest_stock_b REAL,
    highest_stock_a REAL,
    highest_stock_b REAL,
    lowest_ratio_a REAL,
    lowest_ratio_b REAL,
    highest_ratio_a REAL,
    highest_ratio_b REAL,
    realm TEXT NOT NULL DEFAULT 'poe1',
    source TEXT NOT NULL DEFAULT 'ggg_currency_exchange',
    observation_type TEXT NOT NULL DEFAULT 'OFFICIAL_HISTORICAL',
    observed_at TEXT NOT NULL DEFAULT '',
    market_timestamp TEXT NOT NULL DEFAULT '',
    confidence_grade TEXT NOT NULL DEFAULT 'A'
);
CREATE INDEX IF NOT EXISTS idx_cx_lookup
    ON cx_history (league, item_a, item_b, timestamp);
CREATE INDEX IF NOT EXISTS idx_cx_ts
    ON cx_history (timestamp);
-- idx_cx_observation is created in get_db() after dedupe migration

CREATE TABLE IF NOT EXISTS cx_progress (
    key TEXT PRIMARY KEY,
    first_change_id INTEGER,
    last_change_id INTEGER,
    first_available_hour TEXT,
    last_synced_hour TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolio_recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    bankroll_json TEXT NOT NULL,
    positions_json TEXT NOT NULL,
    reserve REAL NOT NULL,
    expected_profit REAL NOT NULL,
    expected_duration_hours REAL,
    expected_distribution_json TEXT NOT NULL,
    baseline_hold_return REAL,
    baseline_random_return REAL,
    baseline_raw_roi_return REAL,
    baseline_flip_score_return REAL,
    league TEXT,
    mode TEXT,
    recommendation TEXT,
    reason TEXT,
    capital_currency TEXT,
    chaos_per_divine REAL
);
CREATE INDEX IF NOT EXISTS idx_recommendations_created
    ON portfolio_recommendations (created_at);

CREATE TRIGGER IF NOT EXISTS prevent_recommendation_update
BEFORE UPDATE ON portfolio_recommendations
BEGIN
    SELECT RAISE(ABORT, 'portfolio recommendation journal is append-only');
END;
CREATE TRIGGER IF NOT EXISTS prevent_recommendation_delete
BEFORE DELETE ON portfolio_recommendations
BEGIN
    SELECT RAISE(ABORT, 'portfolio recommendation journal is append-only');
END;

CREATE TABLE IF NOT EXISTS paper_portfolios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    initial_bankroll REAL NOT NULL,
    currency TEXT NOT NULL DEFAULT 'Chaos',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id INTEGER NOT NULL REFERENCES paper_portfolios(id),
    recommendation_id INTEGER REFERENCES portfolio_recommendations(id),
    opportunity_id TEXT NOT NULL,
    quantity REAL NOT NULL,
    entry_price REAL NOT NULL,
    predicted_exit_price REAL,
    predicted_duration_hours REAL,
    predicted_profit REAL,
    opened_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    realized_exit_price REAL,
    realized_at TEXT,
    realized_profit REAL
);
CREATE INDEX IF NOT EXISTS idx_paper_positions_portfolio
    ON paper_positions (portfolio_id, status);

CREATE TABLE IF NOT EXISTS trade_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id INTEGER REFERENCES paper_portfolios(id),
    position_id INTEGER REFERENCES paper_positions(id),
    opportunity_id TEXT NOT NULL,
    confidence REAL,
    predicted_entry_price REAL,
    actual_entry_price REAL,
    predicted_exit_price REAL,
    actual_exit_price REAL,
    predicted_duration_hours REAL,
    actual_duration_hours REAL,
    predicted_profit REAL,
    realized_profit REAL,
    profitable INTEGER,
    recorded_at TEXT NOT NULL,
    quantity REAL,
    chaos_per_divine REAL,
    capital_currency TEXT,
    actual_entry_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_trade_records_confidence
    ON trade_records (confidence);
CREATE UNIQUE INDEX IF NOT EXISTS idx_trade_records_position
    ON trade_records (position_id) WHERE position_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS paper_equity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id INTEGER NOT NULL REFERENCES paper_portfolios(id),
    timestamp TEXT NOT NULL,
    equity REAL NOT NULL,
    realized_profit REAL NOT NULL,
    source TEXT NOT NULL,
    trade_id INTEGER REFERENCES trade_records(id)
);
CREATE INDEX IF NOT EXISTS idx_paper_equity_portfolio
    ON paper_equity (portfolio_id, timestamp);
 
"""




async def _migrate_paper_units(db: aiosqlite.Connection) -> None:
    """Convert safe legacy paper ledgers from Divine values to Chaos values once."""
    cursor = await db.execute("PRAGMA user_version")
    if int((await cursor.fetchone())[0]) >= 5:
        return
    portfolios = await (await db.execute("SELECT * FROM paper_portfolios ORDER BY id")).fetchall()
    if not any(portfolio["currency"] != "Chaos" for portfolio in portfolios):
        await db.execute("PRAGMA user_version = 5")
        await db.commit()
        return
    rate_cursor = await db.execute(
        """SELECT price_chaos FROM snapshots
           WHERE lower(item_id) = 'divine' AND price_chaos > 0
           ORDER BY timestamp DESC LIMIT 1"""
    )
    rate_row = await rate_cursor.fetchone()
    current_rate = float(rate_row["price_chaos"]) if rate_row else None
    if not current_rate or current_rate <= 0:
        raise RuntimeError("cannot migrate Divine paper ledgers without an observed Divine rate")
    for portfolio in portfolios:
        if portfolio["currency"] == "Chaos":
            continue
        positions = await (await db.execute(
            """SELECT p.*, r.chaos_per_divine AS recommendation_rate
               FROM paper_positions p
               LEFT JOIN portfolio_recommendations r ON r.id = p.recommendation_id
               WHERE p.portfolio_id = ? ORDER BY p.id""",
            (portfolio["id"],),
        )).fetchall()
        rates = [
            float(row["recommendation_rate"]) if row["recommendation_rate"] and float(row["recommendation_rate"]) > 0
            else current_rate
            for row in positions
        ]
        initial_rate = current_rate
        await db.execute(
            "UPDATE paper_portfolios SET initial_bankroll = ?, currency = 'Chaos' WHERE id = ?",
            (float(portfolio["initial_bankroll"]) * initial_rate, portfolio["id"]),
        )
        rate_by_position: dict[int, float] = {}
        for row, rate in zip(positions, rates):
            rate_by_position[int(row["id"])] = rate
            await db.execute(
                """UPDATE paper_positions
                   SET entry_price = ?, predicted_exit_price = ?,
                       predicted_profit = ?, realized_exit_price = ?,
                       realized_profit = ?
                   WHERE id = ?""",
                (
                    float(row["entry_price"]) * rate,
                    float(row["predicted_exit_price"]) * rate if row["predicted_exit_price"] is not None else None,
                    float(row["predicted_profit"]) * rate if row["predicted_profit"] is not None else None,
                    float(row["realized_exit_price"]) * rate if row["realized_exit_price"] is not None else None,
                    float(row["realized_profit"]) * rate if row["realized_profit"] is not None else None,
                    row["id"],
                ),
            )
            await db.execute(
                """UPDATE trade_records
                   SET predicted_entry_price = predicted_entry_price * ?,
                       actual_entry_price = actual_entry_price * ?,
                       predicted_exit_price = predicted_exit_price * ?,
                       actual_exit_price = actual_exit_price * ?,
                       predicted_profit = predicted_profit * ?,
                       realized_profit = realized_profit * ?,
                       capital_currency = 'Chaos',
                       chaos_per_divine = COALESCE(chaos_per_divine, ?)
                   WHERE position_id = ?""",
                (rate, rate, rate, rate, rate, rate, rate, row["id"]),
            )
        equity = float(portfolio["initial_bankroll"]) * initial_rate
        equity_rows = await (await db.execute(
            "SELECT * FROM paper_equity WHERE portfolio_id = ? ORDER BY id", (portfolio["id"],)
        )).fetchall()
        linked_trades = await (await db.execute(
            "SELECT position_id, recorded_at FROM trade_records WHERE portfolio_id = ? ORDER BY id",
            (portfolio["id"],)
        )).fetchall()
        for index, row in enumerate(equity_rows):
            if index == 0:
                await db.execute(
                    "UPDATE paper_equity SET equity = ?, realized_profit = 0 WHERE id = ?",
                    (equity, row["id"]),
                )
                continue
            rate = initial_rate
            for trade in linked_trades:
                if trade["recorded_at"] == row["timestamp"] and trade["position_id"] in rate_by_position:
                    rate = rate_by_position[trade["position_id"]]
                    break
            profit = float(row["realized_profit"]) * rate
            equity += profit
            await db.execute(
                "UPDATE paper_equity SET equity = ?, realized_profit = ? WHERE id = ?",
                (equity, profit, row["id"]),
            )
    if int((await (await db.execute("PRAGMA user_version")).fetchone())[0]) in (3, 4):
        for portfolio in portfolios:
            if portfolio["currency"] != "Chaos":
                continue
            positions = await (await db.execute(
                """SELECT r.chaos_per_divine AS recommendation_rate
                   FROM paper_positions p
                   LEFT JOIN portfolio_recommendations r ON r.id = p.recommendation_id
                   WHERE p.portfolio_id = ? ORDER BY p.id""",
                (portfolio["id"],),
            )).fetchall()
            first_rate = next(
                (float(row["recommendation_rate"]) for row in positions if row["recommendation_rate"] and float(row["recommendation_rate"]) > 0),
                None,
            )
            if not first_rate:
                continue
            target_initial = float(portfolio["initial_bankroll"]) / first_rate * current_rate
            await db.execute(
                "UPDATE paper_portfolios SET initial_bankroll = ? WHERE id = ?",
                (target_initial, portfolio["id"]),
            )
            await db.execute(
                """UPDATE paper_equity SET equity = ?
                   WHERE portfolio_id = ? AND source = 'initial'""",
                (target_initial, portfolio["id"]),
            )
    manual_rows = await (await db.execute(
        """SELECT id, opportunity_id, predicted_profit, realized_profit, chaos_per_divine
           FROM trade_records
           WHERE position_id IS NULL AND capital_currency = 'Divine'"""
    )).fetchall()
    for row in manual_rows:
        rate = float(row["chaos_per_divine"]) if row["chaos_per_divine"] and float(row["chaos_per_divine"]) > 0 else current_rate
        await db.execute(
            """UPDATE trade_records
               SET predicted_profit = predicted_profit * ?,
                   realized_profit = realized_profit * ?,
                   capital_currency = 'Chaos'
               WHERE id = ?""",
            (rate, rate, row["id"]),
        )
    remaining = await (await db.execute(
        "SELECT COUNT(*) AS count FROM paper_portfolios WHERE currency = 'Divine'"
    )).fetchone()
    if int(remaining["count"]) != 0:
        raise RuntimeError("paper unit migration left Divine portfolios unconverted")
    await db.execute("PRAGMA user_version = 5")
    await db.commit()

def validate_execution_quote(value) -> dict | None:
    """Return a safe depth quote or None; aggregate rows remain quote-free."""
    if not isinstance(value, dict):
        return None
    result = {}
    for side in ("buy_levels", "sell_levels", "ask_levels", "sell_listing_floor_levels"):
        levels = value.get(side)
        if levels is None:
            continue
        if not isinstance(levels, list) or not levels:
            return None
        normalized = []
        for level in levels:
            if not isinstance(level, dict):
                return None
            price, quantity = level.get("price"), level.get("quantity")
            if (
                not isinstance(price, (int, float))
                or isinstance(price, bool)
                or not math.isfinite(float(price))
                or price <= 0
                or not isinstance(quantity, (int, float))
                or isinstance(quantity, bool)
                or not math.isfinite(float(quantity))
                or quantity <= 0
            ):
                return None
            normalized.append({"price": float(price), "quantity": float(quantity)})
        result[side] = normalized
    if not result:
        return None
    observed_at = value.get("observed_at")
    source = value.get("source")
    confidence = value.get("confidence")
    stale = value.get("stale", False)
    if not isinstance(observed_at, str) or not observed_at:
        return None
    try:
        parsed_observed_at = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed_observed_at.tzinfo is None or not isinstance(stale, bool):
        return None
    if not isinstance(source, str) or not source:
        return None
    if (
        not isinstance(confidence, (int, float))
        or isinstance(confidence, bool)
        or not math.isfinite(float(confidence))
        or not 0 <= confidence <= 1
    ):
        return None
    for field in ("fee_rate", "buy_fee_rate", "sell_fee_rate"):
        if field in value and (
            not isinstance(value[field], (int, float))
            or isinstance(value[field], bool)
            or not math.isfinite(float(value[field]))
            or not 0 <= value[field] < 1
        ):
            return None
    trade_url = value.get("trade_url")
    if trade_url is not None:
        if not isinstance(trade_url, str):
            return None
        parsed = urlsplit(trade_url)
        parts = [part for part in parsed.path.split("/") if part]
        if (
            parsed.scheme != "https"
            or parsed.netloc != "www.pathofexile.com"
            or len(parts) != 4
            or parts[:2] != ["trade", "search"]
            or parsed.query
            or parsed.fragment
        ):
            return None
    if "sell_listing_floor_levels" in result:
        if value.get("quote_kind") != "sell_listing_floor" or trade_url is None:
            return None
        numeric_fields = (
            "listing_floor", "sell_listing_floor", "liquidation_haircut",
            "listing_cluster_depth", "listing_cluster_spread",
        )
        if any(
            isinstance(value.get(field), bool)
            or not isinstance(value.get(field), (int, float))
            or not math.isfinite(float(value[field]))
            for field in numeric_fields
        ):
            return None
        sample_count = value.get("listing_sample_count")
        cluster_count = value.get("listing_cluster_count")
        floor_levels = result["sell_listing_floor_levels"]
        adjusted_from_haircut = value["listing_floor"] * (1 - value["liquidation_haircut"])
        if (
            isinstance(sample_count, bool)
            or not isinstance(sample_count, int)
            or isinstance(cluster_count, bool)
            or not isinstance(cluster_count, int)
            or source != "pathofexile_trade_listing_floor"
            or sample_count < cluster_count
            or cluster_count < 3
            or len(floor_levels) != 1
            or value["listing_floor"] <= 0
            or value["sell_listing_floor"] <= 0
            or value["sell_listing_floor"] > value["listing_floor"]
            or not 0.01 <= value["liquidation_haircut"] <= 0.5
            or not math.isclose(value["sell_listing_floor"], adjusted_from_haircut, rel_tol=1e-9, abs_tol=1e-9)
            or not math.isclose(floor_levels[0]["price"], value["sell_listing_floor"], rel_tol=1e-9, abs_tol=1e-9)
            or not math.isclose(value["listing_cluster_depth"], cluster_count, rel_tol=1e-9, abs_tol=1e-9)
            or not math.isclose(floor_levels[0]["quantity"], value["listing_cluster_depth"], rel_tol=1e-9, abs_tol=1e-9)
            or not 0.01 <= value["listing_cluster_spread"] <= 0.5
        ):
            return None
        result.update({
            "quote_kind": "sell_listing_floor",
            **{field: value[field] for field in numeric_fields},
            "listing_sample_count": sample_count,
            "listing_cluster_count": cluster_count,
        })
    fee = float(value.get("fee_rate", 0))
    result.update({
        "buy_fee_rate": float(value.get("buy_fee_rate", fee)),
        "sell_fee_rate": float(value.get("sell_fee_rate", fee)),
        "observed_at": observed_at,
        "confidence": float(confidence),
        "source": source,
        "stale": stale,
    })
    if trade_url is not None:
        result["trade_url"] = trade_url
    return result



async def _ensure_columns(db: aiosqlite.Connection, table: str, columns: dict[str, str]) -> None:
    cursor = await db.execute(f"PRAGMA table_info({table})")
    existing = {row["name"] for row in await cursor.fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            await db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
    await db.commit()


async def get_db() -> aiosqlite.Connection:
    """Open a connection, creating the schema and additive columns safely."""
    global _schema_path
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        await db.execute("PRAGMA busy_timeout=5000")
        if _schema_path != DB_PATH:
            async with _schema_lock:
                if _schema_path != DB_PATH:
                    cursor = await db.execute(
                        "SELECT COUNT(*) AS count FROM sqlite_master WHERE type = 'table'"
                    )
                    if int((await cursor.fetchone())["count"]) == 0:
                        await db.execute("PRAGMA auto_vacuum=INCREMENTAL")
                    await db.execute("PRAGMA journal_mode=WAL")
                    await db.executescript(_SCHEMA)
                    await _ensure_columns(db, "snapshots", {
                        "source": "TEXT NOT NULL DEFAULT 'poe.ninja'",
                        "observation_type": "TEXT NOT NULL DEFAULT 'DIRECT_OBSERVATION'",
                        "observed_at": "TEXT NOT NULL DEFAULT ''",
                        "market_timestamp": "TEXT NOT NULL DEFAULT ''",
                        "confidence_grade": "TEXT NOT NULL DEFAULT 'B'",
                        "execution_quote": "TEXT",
                    })
                    await _ensure_columns(db, "cx_history", {
                        "realm": "TEXT NOT NULL DEFAULT 'poe1'",
                        "source": "TEXT NOT NULL DEFAULT 'ggg_currency_exchange'",
                        "observation_type": "TEXT NOT NULL DEFAULT 'OFFICIAL_HISTORICAL'",
                        "observed_at": "TEXT NOT NULL DEFAULT ''",
                        "market_timestamp": "TEXT NOT NULL DEFAULT ''",
                        "confidence_grade": "TEXT NOT NULL DEFAULT 'A'",
                    })
                    await _ensure_columns(db, "cx_progress", {
                        "first_change_id": "INTEGER",
                        "first_available_hour": "TEXT",
                        "last_synced_hour": "TEXT",
                    })
                    await _ensure_columns(db, "portfolio_recommendations", {
                        "league": "TEXT", "mode": "TEXT", "recommendation": "TEXT", "reason": "TEXT",
                        "capital_currency": "TEXT", "chaos_per_divine": "REAL",
                    })
                    await _ensure_columns(db, "trade_records", {
                        "quantity": "REAL", "chaos_per_divine": "REAL", "capital_currency": "TEXT",
                        "actual_entry_at": "TEXT",
                    })
                    await db.execute(
                        """UPDATE snapshots
                           SET observation_type = 'SYNTHETIC'
                           WHERE lower(source) LIKE '%synthetic%'
                              OR lower(source) LIKE '%reconstructed%'"""
                    )
                    await db.execute(
                        """UPDATE cx_history
                           SET observation_type = 'SYNTHETIC'
                           WHERE lower(source) LIKE '%synthetic%'
                              OR lower(source) LIKE '%reconstructed%'"""
                    )
                    await _ensure_columns(db, "paper_equity", {
                        "trade_id": "INTEGER REFERENCES trade_records(id)",
                    })
                    await _dedupe_cx_history(db)
                    await db.execute(
                        """UPDATE paper_equity
                           SET trade_id = (
                               SELECT MIN(t.id) FROM trade_records t
                               WHERE t.portfolio_id = paper_equity.portfolio_id
                                 AND t.recorded_at = paper_equity.timestamp
                                 AND t.realized_profit = paper_equity.realized_profit
                                 AND t.position_id IS NOT NULL
                           )
                           WHERE source = 'paper_realization' AND trade_id IS NULL
                             AND 1 = (
                               SELECT COUNT(*) FROM trade_records t
                               WHERE t.portfolio_id = paper_equity.portfolio_id
                                 AND t.recorded_at = paper_equity.timestamp
                                 AND t.realized_profit = paper_equity.realized_profit
                                 AND t.position_id IS NOT NULL
                             )"""
                    )
                    await db.execute(
                        """CREATE UNIQUE INDEX IF NOT EXISTS idx_paper_equity_trade
                           ON paper_equity (trade_id) WHERE trade_id IS NOT NULL"""
                    )
                    await db.commit()
                    await _migrate_paper_units(db)
                    _schema_path = DB_PATH
        page_size = int((await (await db.execute("PRAGMA page_size")).fetchone())[0])
        await db.execute(f"PRAGMA max_page_count={MAX_DATABASE_BYTES // page_size}")
        await db.execute(f"PRAGMA journal_size_limit={MAX_WAL_BYTES}")
        await db.execute("PRAGMA wal_autocheckpoint=1000")
        return db
    except Exception:
        await db.close()
        raise


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")



def project_footprint() -> int:
    total = 0
    for root, _, files in os.walk(PROJECT_ROOT):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def collection_allowed() -> bool:
    footprint = project_footprint()
    try:
        db_path = os.path.abspath(DB_PATH)
        project_root = os.path.abspath(PROJECT_ROOT)
        outside_project = os.path.commonpath((db_path, project_root)) != project_root
    except ValueError:
        # Different Windows drives are still a resolvable external database path.
        outside_project = True
    except OSError:
        # An unresolvable path cannot safely bypass the collection stop guard.
        return False
    if outside_project:
        footprint += storage_footprint()["total"]
    return footprint < COLLECTION_STOP_BYTES


async def _dedupe_cx_history(db: aiosqlite.Connection) -> None:
    """Remove legacy duplicate CX rows before creating the unique index."""
    await db.execute(
        """DELETE FROM cx_history WHERE id NOT IN (
               SELECT MIN(id) FROM cx_history
               GROUP BY realm, league, timestamp, market_id
           )"""
    )
    await db.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_cx_observation
           ON cx_history (realm, league, timestamp, market_id)"""
    )
    await db.commit()


async def insert_snapshots(records: list[dict], timestamp: str | None = None) -> int:
    """Insert previously unseen snapshot records. Returns inserted row count."""
    if not records or not collection_allowed():
        return 0
    ts = timestamp or now_iso()
    observed = now_iso()
    db = await get_db()
    try:
        before = db.total_changes
        await db.executemany(
            """INSERT INTO snapshots
               (timestamp, league, category, item_id, item_name, variant,
                price_chaos, volume, listing_count, icon,
                source, observation_type, observed_at, market_timestamp,
                confidence_grade, execution_quote)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(timestamp, league, category, item_id, variant)
               DO UPDATE SET execution_quote = COALESCE(
                   snapshots.execution_quote, excluded.execution_quote
               )
               WHERE snapshots.execution_quote IS NULL
                 AND excluded.execution_quote IS NOT NULL""",
            [
                (
                    ts, r["league"], r["category"], r["item_id"], r["item_name"],
                    r.get("variant", ""), r["price_chaos"], r.get("volume", 0),
                    r.get("listing_count", 0), r.get("icon", ""),
                    r.get("source", "poe.ninja"),
                    r.get("observation_type", "DIRECT_OBSERVATION"),
                    r.get("observed_at", observed),
                    r.get("market_timestamp", ts),
                    r.get("confidence_grade", "B"),
                    (
                        json.dumps(quote, sort_keys=True)
                        if (quote := validate_execution_quote(r.get("execution_quote"))) is not None
                        else None
                    ),
                )
                for r in records
            ],
        )
        await db.commit()
        return db.total_changes - before
    finally:
        await db.close()


async def count_rows() -> int:
    db = await get_db()
    try:
        cur = await db.execute("SELECT COUNT(*) FROM snapshots")
        row = await cur.fetchone()
        return row[0]
    finally:
        await db.close()


async def db_file_size() -> int:
    try:
        return os.path.getsize(DB_PATH)
    except OSError:
        return 0


async def insert_cx_hour(records: list[dict], timestamp: str) -> int:
    """Insert one hour of currency-exchange markets. Returns inserted row count.

    Idempotent on (realm, league, timestamp, market_id) via ON CONFLICT.
    """
    if not records:
        return 0
    if not collection_allowed():
        return 0
    observed = now_iso()
    db = await get_db()
    try:
        before = db.total_changes
        await db.executemany(
            """INSERT INTO cx_history
               (timestamp, league, market_id, item_a, item_b,
                volume_a, volume_b, lowest_stock_a, lowest_stock_b,
                highest_stock_a, highest_stock_b, lowest_ratio_a,
                lowest_ratio_b, highest_ratio_a, highest_ratio_b,
                realm, source, observation_type, observed_at,
                market_timestamp, confidence_grade)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(realm, league, timestamp, market_id) DO NOTHING""",
            [
                (
                    timestamp, r["league"], r["market_id"], r["item_a"], r["item_b"],
                    r.get("volume_a"), r.get("volume_b"),
                    r.get("lowest_stock_a"), r.get("lowest_stock_b"),
                    r.get("highest_stock_a"), r.get("highest_stock_b"),
                    r.get("lowest_ratio_a"), r.get("lowest_ratio_b"),
                    r.get("highest_ratio_a"), r.get("highest_ratio_b"),
                    r.get("realm", "poe1"),
                    r.get("source", "ggg_currency_exchange"),
                    r.get("observation_type", "OFFICIAL_HISTORICAL"),
                    r.get("observed_at", observed),
                    r.get("market_timestamp", timestamp),
                    r.get("confidence_grade", "A"),
                )
                for r in records
            ],
        )
        await db.commit()
        return db.total_changes - before
    finally:
        await db.close()


async def get_cx_progress(key: str = "default") -> int | None:
    db = await get_db()
    try:
        cur = await db.execute("SELECT last_change_id FROM cx_progress WHERE key = ?", (key,))
        row = await cur.fetchone()
        return row["last_change_id"] if row else None
    finally:
        await db.close()


async def get_cx_cursor(key: str = "default") -> dict:
    """Return full cursor metadata for a sync key."""
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM cx_progress WHERE key = ?", (key,))
        row = await cur.fetchone()
        return dict(row) if row else {}
    finally:
        await db.close()


async def set_cx_progress(
    key: str,
    change_id: int,
    first_change_id: int | None = None,
    first_available_hour: str | None = None,
    last_synced_hour: str | None = None,
) -> None:
    """Atomically advance sync cursor while preserving first-seen metadata."""
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO cx_progress
               (key, first_change_id, last_change_id,
                first_available_hour, last_synced_hour, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET
                   first_change_id = COALESCE(cx_progress.first_change_id, excluded.first_change_id),
                   first_available_hour = COALESCE(cx_progress.first_available_hour, excluded.first_available_hour),
                   last_change_id = CASE
                       WHEN cx_progress.last_change_id IS NULL
                            OR excluded.last_change_id > cx_progress.last_change_id
                       THEN excluded.last_change_id
                       ELSE cx_progress.last_change_id
                   END,
                   last_synced_hour = CASE
                       WHEN (cx_progress.last_change_id IS NULL
                             OR excluded.last_change_id > cx_progress.last_change_id)
                            AND excluded.last_synced_hour IS NOT NULL
                       THEN excluded.last_synced_hour
                       ELSE cx_progress.last_synced_hour
                   END,
                   updated_at = excluded.updated_at""",
            (key, first_change_id, change_id, first_available_hour,
             last_synced_hour, now_iso()),
        )
        await db.commit()
    finally:
        await db.close()


async def prune_market_data(
    keep_categories,
    snapshot_days: int = SNAPSHOT_RETENTION_DAYS,
    cx_days: int = CX_RETENTION_DAYS,
    league: str | None = None,
) -> dict[str, int]:
    """Retain raw market and CX observations for one league window."""
    categories = tuple(keep_categories)
    if not categories or snapshot_days < 1 or cx_days < 1:
        raise ValueError("retention requires categories and positive day counts")
    snapshot_cutoff = (
        datetime.now(timezone.utc) - timedelta(days=snapshot_days)
    ).isoformat(timespec="seconds")
    cx_cutoff = (
        datetime.now(timezone.utc) - timedelta(days=cx_days)
    ).isoformat(timespec="seconds")
    placeholders = ",".join("?" for _ in categories)
    db = await get_db()
    try:
        category_cursor = await db.execute(
            f"DELETE FROM snapshots WHERE category NOT IN ({placeholders})",
            categories,
        )
        if league is None:
            age_cursor = await db.execute(
                "DELETE FROM snapshots WHERE timestamp < ?", (snapshot_cutoff,)
            )
            cx_cursor = await db.execute(
                "DELETE FROM cx_history WHERE timestamp < ?", (cx_cutoff,)
            )
        else:
            age_cursor = await db.execute(
                "DELETE FROM snapshots WHERE league = ? AND timestamp < ?",
                (league, snapshot_cutoff),
            )
            cx_cursor = await db.execute(
                "DELETE FROM cx_history WHERE league = ? AND timestamp < ?",
                (league, cx_cutoff),
            )
        await db.commit()
        await db.execute("PRAGMA incremental_vacuum(2000)")
        try:
            await db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except aiosqlite.OperationalError as exc:
            if "locked" not in str(exc).casefold():
                raise
        return {
            "unsupported_snapshots": max(0, category_cursor.rowcount),
            "expired_snapshots": max(0, age_cursor.rowcount),
            "expired_cx_rows": max(0, cx_cursor.rowcount),
        }
    finally:
        await db.close()


def storage_footprint() -> dict[str, int]:
    """Return SQLite database, WAL, SHM and total bytes."""
    sizes = {
        "database": os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0,
        "wal": os.path.getsize(f"{DB_PATH}-wal") if os.path.exists(f"{DB_PATH}-wal") else 0,
        "shm": os.path.getsize(f"{DB_PATH}-shm") if os.path.exists(f"{DB_PATH}-shm") else 0,
    }
    sizes["total"] = sum(sizes.values())
    return sizes
