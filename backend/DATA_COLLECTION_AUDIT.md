# Data collection audit

**Evidence captured 2026-08-12 from `backend/deuscfo.db` (read-only).** The audit used 10 bounded aggregate SQLite queries, plus schema/index inspection. No servers were run and no application code was changed.

## Measurements

| Measure | `snapshots` | `cx_history` |
|---|---:|---:|
| Rows | 3,264 | 4,841 |
| Distinct timestamps | 32 | 2 |
| First timestamp | 2026-08-11T20:39:55+00:00 | 2026-08-11T20:00:00+00:00 |
| Last timestamp | 2026-08-11T22:08:03+00:00 | 2026-08-11T21:00:00+00:00 |
| Rows per timestamp | 102 on every timestamp | 2,414 then 2,427 |

The database file is **2,957,312 bytes (2.82 MiB)**. Combined data rows are 8,105, or about **365 bytes/row including the current indexes and SQLite file overhead** (a blended planning estimate, not a guaranteed future row cost).
Schema evidence: `snapshots` has `NOT NULL` timestamp/league/category/item identity and price columns, with `idx_snapshots_lookup(league, category, item_id, timestamp)` and `idx_snapshots_timestamp(timestamp)`. `cx_history` has `NOT NULL` identity columns but nullable volume/stock/ratio metrics, with `idx_cx_lookup(league, item_a, item_b, timestamp)` and `idx_cx_ts(timestamp)`. Neither table declares a uniqueness constraint on its logical observation key.


### Cadence

The snapshot collector did not produce 30-minute cadence in this sample. Its 32 timestamps range from **3 seconds apart** (`20:39:55` → `20:40:00`) to **41m 51s** (`21:23:50` → `22:05:59`), with many bursts of 5–60 seconds. Each timestamp has exactly 102 rows, so a timestamp is one category/league collection batch rather than a reliably scheduled global snapshot.

Currency exchange data is hourly by API change timestamp: `20:00` and `21:00`. The two batches contain 2,414 and 2,427 rows and span 3 and 4 leagues respectively.

### League separation

`snapshots`: **Allflame 3,264 rows / 32 timestamps**; no other league is present.

`cx_history`:

- Allflame: 3,129 rows, 2 timestamps
- Hardcore Allflame: 879 rows, 2 timestamps
- Standard: 832 rows, 2 timestamps
- Hardcore: 1 row, 1 timestamp

The one-row Hardcore result is a likely partial upstream response or filtered market set; it is not mixed with another league because `league` is stored as a column and the lookup index begins with it.

### Duplicates and prices

Exact logical duplicate checks found **0 duplicate groups / 0 extra rows** in both tables. Keys checked were:

- snapshots: `(timestamp, league, category, item_id, variant)`
- currency exchange: `(timestamp, league, market_id, item_a, item_b)`

`snapshots.price_chaos`: **0 NULL**, **0 zero**, minimum **0.0004701**, maximum **146,367.0** across 3,264 rows. This is consistent with `collector.py` filtering `price_chaos <= 0` before insertion. `cx_history` has no single price column; its ratio/stock/volume fields are nullable by schema.

### Stale unchanged runs

A grouped unchanged-value check found **3 item/category/league/variant groups** with more than one row and identical `MIN(price_chaos)`/`MAX(price_chaos)`, covering **96 rows**. This is a candidate signal only: the query does not prove adjacent unchanged runs because the collector timestamps are irregular and each batch is not a globally aligned snapshot.

## Growth projection at 30-minute snapshots

Using the observed 102 snapshot rows per batch:

- 48 batches/day × 102 = **4,896 snapshot rows/day**
- At the blended observed 365 bytes/row: **~1.79 MB/day**, **~53.7 MB/30 days**, **~0.65 GB/year**
- At 30-minute cadence, the current 2.82 MiB file would reach roughly **1 GB in 18–19 months** if row/index overhead remains similar.

This excludes additional currency-exchange rows. If all four observed CX leagues continue hourly at the current ~2,420 rows/hour, CX contributes roughly 58,000 rows/day and will dominate the projection; the blended estimate above is therefore conservative for a combined long-lived database.

## Concrete risks

1. **Cadence is not a snapshot boundary.** `collector.py` writes one timestamp per category call (`database.insert_snapshots` stamps `now_iso()`), so a nominal run can create multiple timestamps and partial runs. A consumer grouping by timestamp can mistake category batches for complete snapshots.
2. **Partial failures are intentionally non-fatal.** `collect_all_categories` catches each category exception, logs it, and records zero for that category. The database therefore has no explicit run ID or completeness marker; missing categories are indistinguishable from a genuinely empty response without logs.
3. **League coverage is asymmetric.** Spot snapshots currently contain only Allflame, while CX contains four leagues (one with a single row). Cross-table comparisons need an explicit league intersection and minimum-row guard.
4. **No uniqueness constraints exist.** The audit found no duplicates, but both logical keys rely on application behavior; retries or a repeated API response could insert duplicates.
5. **Nullable CX numeric fields are accepted.** This is valid for sparse market data but requires downstream null handling; unlike spot prices, there is no collector-level “positive price” filter for CX ratios/stocks.

## SQLite reconsideration thresholds

Keep SQLite while the workload remains single-process/light-write and the file is comfortably below these operational thresholds. Reconsider PostgreSQL (or another server database) when **any** of the following is observed:

- file reaches **5 GB** or sustained growth projects beyond **10 GB**;
- sustained write rate exceeds **100 snapshot batches/minute** or concurrent writers exceed **2**;
- WAL/checkpoint or write-lock waits exceed **1 second p95** for 5 consecutive minutes;
- analytical queries over the active history exceed **2 seconds p95** despite indexes;
- required retention exceeds **12 months** at the measured combined CX + spot rate without archival/partitioning;
- integrity requires database-enforced deduplication/run completeness that cannot be added safely with SQLite constraints.

At the observed spot-only rate, size is not an immediate SQLite problem. The immediate corrective priority is recording a run/batch completeness boundary and handling league/partial-response coverage explicitly, not changing databases.
