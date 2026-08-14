# DeusCFO V1.1 — Validate Before Expanding

DeusCFO has now completed its initial market-intelligence architecture:

- historical SQLite storage
- snapshot collection
- Currency Exchange history
- market regimes
- anomaly detection
- signals
- opportunity abstraction/scoring
- dashboard/signals/explorer UI

Do NOT add another large collection of features yet.

The next objective is to determine whether the existing intelligence is actually useful.

## Priority 1 — Backtesting

Build a backtesting framework for existing signals, anomalies, regimes and opportunities.

For every historical signal at time T, evaluate subsequent market behavior at configurable horizons:

- 1h
- 3h
- 6h
- 12h
- 24h

Calculate:

- sample size
- win rate
- mean return
- median return
- 10th/25th/75th/90th percentile returns
- maximum adverse movement
- maximum favorable movement
- time to recovery
- time to peak

Avoid look-ahead bias completely.

A signal may only use data that would actually have been available at its timestamp.

## Priority 2 — Signal performance

Group results by:

- signal type
- anomaly type
- regime
- category
- liquidity tier
- opportunity type

Expose historical performance through an API.

Example:

```text
Signal: price_drop + volume_spike

Occurrences: 184
6h win rate: 71%
6h median return: +6.2%
6h 10th percentile: -4.1%
6h 90th percentile: +18.7%
```

## Priority 3 — Statistical confidence

Do not treat:

```text
9/10 successful
```

as equivalent to:

```text
680/1000 successful
```

Incorporate sample size into confidence.

Prefer statistically defensible methods over arbitrary penalties.

## Priority 4 — Expected-value opportunities

Extend the opportunity model with historical outcome information.

An opportunity should eventually expose:

```text
expected_return
win_probability
median_return
downside_percentile
sample_size
historical_confidence
```

Keep these separate from the existing heuristic opportunity score.

Do not hide uncertainty inside a single number.

## Priority 5 — Market-wide events

Add detection of synchronized movements across related markets.

Examples:

- many items in a category moving simultaneously
- multiple categories moving simultaneously
- unusual category-wide volume
- correlated price shocks

Create a MarketEvent abstraction distinct from an individual item signal.

Example:

```text
MarketEvent {
    type
    affected_items
    affected_categories
    start_time
    magnitude
    confidence
}
```

## Priority 6 — Lagged relationships

Investigate whether historical data reveals predictive relationships between markets.

For item/category pairs, test lagged relationships such as:

```text
A(t) → B(t + 1h)
A(t) → B(t + 3h)
A(t) → B(t + 6h)
```

Do not simply use Pearson correlation.

Investigate:

- lagged correlation
- directional consistency
- sample size
- statistical significance
- out-of-sample performance

The goal is to discover potential "leader → laggard" relationships.

Example output:

```text
Potential Laggard

A moved +18%.

B normally follows A by 2–4h.

B has only moved +2%.

Historical follow-through: 73%.

Sample size: 142.
```

Do not call this predictive unless backtesting supports it.

## Priority 7 — Opportunity quality

Add realistic execution assumptions.

Distinguish:

- theoretical price
- realistic entry
- realistic exit
- liquidity
- estimated execution effort

An opportunity should eventually be evaluated as:

```text
realistic_profit
capital_required
ROI
estimated_time
profit_per_hour
liquidity
risk
```

Do not allow isolated cheap listings or thin markets to generate enormous false opportunities.

## Priority 8 — "No opportunity" is valid

The system must be allowed to return:

```text
No compelling opportunities currently detected.
```

Do not force every market condition into a positive opportunity.

Define minimum thresholds for historical EV, confidence, liquidity and expected return.

## Priority 9 — Strategy laboratory

Once backtesting is reliable, expose a simple strategy-testing interface.

Allow conditions such as:

```text
price_percentile < 20
volume_ratio > 1.5
regime = recovering
```

to be evaluated historically.

Show:

- occurrences
- win rate
- return distribution
- drawdown
- best/worst periods
- performance by category

This should make it possible to test hypotheses without modifying application code.

## Priority 10 — Data collection quality

Before expanding functionality, inspect the collector.

Determine:

- expected database growth
- snapshot frequency
- missing data
- duplicate snapshots
- API failures
- stale prices
- item identity changes
- league boundaries

Design raw historical storage so it can eventually scale to millions of rows without requiring a premature database migration.

SQLite remains acceptable unless measurements demonstrate otherwise.

## Important

Do not implement machine learning yet.

First establish:

1. reliable historical data
2. correct backtesting
3. statistically meaningful performance measurements
4. realistic execution assumptions

Only after these exist should we consider predictive models.

## Success criterion

At the end of this phase, DeusCFO should be able to answer something much more valuable than:

> "This item has a high score."

It should be able to answer:

> "This opportunity resembles 184 historical situations. 71% were profitable within 6 hours, the median return was +6.2%, the downside percentile was -4.1%, and the current market has sufficient liquidity to make the historical result reasonably actionable."

Correctness and empirical validation are more important than adding more features.