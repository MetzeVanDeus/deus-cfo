# DeusCFO V3 — The Hideout Economy Engine

## Mission

DeusCFO already has a strong analytical foundation:

- market snapshots
- Currency Exchange history
- regimes
- anomalies
- signals
- backtesting
- confidence intervals
- opportunity scoring
- capital allocation concepts
- execution-aware metrics
- paper validation infrastructure

V3 should NOT primarily add more statistical indicators.

V3 has two major goals:

> **A. Build a trustworthy historical-data architecture that never fabricates observations.**

and

> **B. Expand DeusCFO from market speculation into repeatable hideout profit through deterministic and finite-outcome economic transformations.**

The ultimate product should answer:

> "I have 50 divines. What can I physically do with them right now, from my hideout, to turn them into more currency?"

This includes flipping, but flipping should become only one strategy family.

---

# PART I — FIX HISTORICAL DATA PROPERLY

## 1. Delete synthetic historical backfill from analytical use

The current system appears to have generated or reconstructed portions of historical data from incomplete information.

This is unacceptable for:

- backtesting
- confidence estimates
- probability calculations
- strategy validation
- portfolio simulation

Do not attempt to infer historical prices merely to increase sample size.

Introduce explicit data provenance.

Every historical record must contain something equivalent to:

```text
source
observation_type
observed_at
market_timestamp
confidence_grade
```

Use observation types such as:

```text
OFFICIAL_HISTORICAL
DIRECT_OBSERVATION
IMPORTED_TRUSTED
ESTIMATED
SYNTHETIC
```

`ESTIMATED` and `SYNTHETIC` records MUST NEVER enter empirical backtests.

They may exist for visualization if clearly labelled, but preferably remove synthetic backfill entirely.

---

# 2. Currency Exchange becomes the gold-standard historical dataset

GGG's public Currency Exchange history endpoint provides genuine hourly historical market data.

Implement a robust CX synchronization service.

Its behavior should conceptually be:

```text
no local history
↓
request first available hour
↓
store hour
↓
follow next_change_id
↓
store hour
↓
repeat
↓
reach current stream end
```

After initial synchronization:

```text
last known hour
↓
next_change_id
↓
catch up all missing hours
```

Therefore:

**the application does not need to have been running continuously to maintain Currency Exchange history.**

Make this the first dataset DeusCFO trusts for serious backtesting.

Persist every retrieved historical hour permanently.

Never recompute historical CX data from current prices.

---

# 3. Make CX ingestion idempotent

Use a unique key conceptually similar to:

```text
realm
league
hour
market_id
```

Re-fetching history must not create duplicates.

The sync system should safely survive:

- crashes
- duplicate requests
- partial responses
- restarts
- machine downtime
- network failures

Store the synchronization cursor separately.

Expose:

```text
first_available_hour
last_synced_hour
hours_present
hours_missing
coverage_percentage
```

---

# 4. Historical completeness map

Build a Data Coverage service.

For every data source/category show:

```text
Currency Exchange
2026-02-27 → today
99.8% complete
REAL

Scarabs / poe.ninja
2026-08-01 → today
61% complete
OBSERVED

Unique Items
2026-08-07 → today
28% complete
OBSERVED
```

Backtesting must request data through this layer.

A detector should be able to ask:

```text
Can I trust this window?
```

If coverage is inadequate:

```text
NO
```

then the result is rejected rather than silently calculated.

---

# 5. Separate CURRENT price data from HISTORICAL data

Create explicit concepts:

```text
CurrentMarketProvider
HistoricalMarketProvider
```

Do not let code assume that because a provider can tell us the current price, it can provide historical prices.

Example architecture:

```text
poe.ninja
→ current market estimates

GGG CX historical stream
→ authoritative historical exchange observations

DeusCFO collector
→ directly observed historical snapshots
```

Normalize them above the provider layer.

---

> **Note:** Part I section 6 onward (through the end of the document) is deferred/unimplemented. It has been moved, preserving exact text, to `DeusCFO V3 — Deferred V3 Instructions.md`.

<!-- Remaining deferred sections (Part I §6 onward) relocated to "DeusCFO V3 — Deferred V3 Instructions.md". -->
