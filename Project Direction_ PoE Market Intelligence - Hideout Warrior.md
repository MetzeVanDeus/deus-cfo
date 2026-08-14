# Project Direction: PoE Market Intelligence / Hideout Warrior

You are extending an existing Path of Exile 1 market-analysis tool.

The current implementation already has:

- poe.ninja economy data ingestion
- Currency / Scarabs / Essences / Oils / Fossils / Delirium Orbs / Divination Cards / Fragments
- Skill Gems / Uniques / Maps
- category switching
- chaos/divine budget display
- item icons and names
- a cohort-relative Flip Score using:
  - dipFromPeak
  - swingDepth
  - liquidity
  - monotonic-decline penalty
- result sorting and filtering
- a Dracula-style UI

The current goal is NOT simply to build a better "flip finder".

The actual goal is:

> Find low-effort, repeatable ways for a player sitting in their hideout to turn capital/time into profit by detecting market inefficiencies, transformations, trends and opportunities.

Think of this as a **PoE market intelligence terminal**, not a flipping website.

---

## 1. Preserve the existing system

Do not throw away the current Flip Score.

Refactor it so it becomes one opportunity detector among several.

The UI should eventually have opportunity types such as:

- Flip
- Arbitrage
- Conversion
- Recipe / Transformation
- Market Reversion
- Momentum
- Supply Shock
- Demand Spike
- Crafting EV
- Undervalued Listing
- Bundle / Bulk Inefficiency

A single item can potentially appear in multiple opportunity types.

---

## 2. Build a historical data layer

The biggest architectural improvement should be persistent historical data.

Do NOT rely exclusively on the current poe.ninja snapshot.

Store periodic snapshots locally.

At minimum record:

```text
timestamp
league
category
item
variant
price
volume
listing_count if available
```

Use a time-series friendly schema but keep the implementation simple.

SQLite is completely acceptable initially.

The system should be able to answer:

- price 1h ago
- price 6h ago
- price 24h ago
- price 3d ago
- rolling average
- rolling median
- volatility
- percentile within recent history
- rate of change
- volume change
- unusual deviation from normal behavior

Do not calculate everything from the raw frontend.

Create a proper market-data service.

---

## 3. Exploit official historical Currency Exchange data

Investigate and implement the official PoE API Currency Exchange history.

The official API currently exposes hourly historical currency-exchange market data, including:

- market pair
- traded volume
- lowest stock
- highest stock
- lowest ratio
- highest ratio

This should be treated as a first-class historical source for currency markets.

Do not assume poe.ninja is the only possible historical source.

Store this data independently so the application can build its own longer-term history.

Handle API rate limits and incremental pagination properly.

---

## 4. Build a "market regime" detector

Instead of simply asking:

> "Did this item fall?"

ask:

> "What kind of market is this item currently experiencing?"

Classify items into regimes such as:

- Stable
- Trending Up
- Trending Down
- Recovering
- Crashing
- Pumping
- Mean-Reverting
- Volatility Expansion
- Volatility Compression
- Volume Spike
- Supply Shock
- Demand Shock

Example:

A 20% price decrease means very different things if:

A) volume is normal and price is slowly declining

versus

B) volume suddenly triples and price falls aggressively

versus

C) price falls 20%, volume collapses, then price stabilizes

The detector should distinguish these situations.

---

## 5. Detect statistical anomalies

Implement anomaly detection against each item's own history.

Useful signals:

- z-score against recent price
- percentile against 24h / 3d / 7d history
- abnormal volume
- sudden price acceleration
- price/volume divergence
- deviation from moving median
- volatility spike
- recovery after a large deviation

Do not blindly use simple moving averages everywhere.

Prefer robust statistics such as median / MAD when appropriate because PoE prices can have extreme outliers.

---

# 6. Build an opportunity engine

Create a normalized opportunity model.

Something like:

```text
Opportunity {
    type
    item
    input
    output
    capital_required
    expected_profit
    roi
    profit_per_capital
    liquidity
    confidence
    estimated_time
    risk
    reasons[]
}
```

The important change is that an opportunity does NOT necessarily represent:

> buy X → sell X

It can represent:

> buy X → transform X → sell Y

or:

> buy cheap X → exchange into Y → sell Y

or:

> X is temporarily undervalued relative to Y

or:

> X normally behaves like this, but today's market is abnormal.

---

# 7. Arbitrage / conversion graph

Model the economy as a graph.

Nodes:

```text
items / currencies / fragments / scarabs / essences / etc.
```

Edges:

```text
X can be converted into Y
```

Each edge should contain:

```text
input quantity
output quantity
cost
fees/losses
expected value
```

Then search for profitable paths.

Examples:

```text
A → B
A → C
B → C
```

Detect situations where:

```text
A → B → C
```

has meaningfully different value from:

```text
A → C
```

Start with deterministic/simple conversions before attempting complicated crafting systems.

The important concept is **profit after all conversion costs**, not theoretical gross value.

---

# 8. Look for "processing profit"

One of the most valuable hideout-warrior opportunities is:

> buy an intermediate material cheaply, perform a deterministic transformation, sell the result.

Build a framework for this.

Potential categories:

- vendor recipes
- deterministic currency conversions
- bulk conversion
- fragments
- essences
- fossils
- scarabs
- divination cards
- splinter/fragments
- map-related conversions
- any other deterministic transformation that can be represented reliably

For every transformation calculate:

```text
input_cost
+
conversion_cost
+
expected losses
=
true_cost

output_value
-
true_cost
=
profit
```

Do not assume a conversion is profitable merely because:

```text
output price > input price
```

Liquidity and realistic achievable prices matter.

---

# 9. Divination-card set arbitrage

Investigate special handling for divination cards.

A useful opportunity is:

```text
value of complete reward
-
cost of required cards
```

But also consider:

- number of cards required
- individual card liquidity
- card supply
- reward variance
- chance/value of variants where applicable
- whether the reward is actually easier to liquidate than the cards

Rank these by expected profit and capital efficiency.

The system should explicitly distinguish:

```text
theoretical profit
```

from

```text
realistic profit
```

---

# 10. Liquidity-aware pricing

The current system uses volume, which is good, but improve the concept.

A listed price is not necessarily an executable price.

Whenever possible estimate:

```text
best price
median realistic price
depth near current price
```

For example:

```text
1 listing at 1c
40 listings at 10c
```

should NOT be interpreted the same way as:

```text
50 listings around 1c
```

Create a liquidity/confidence penalty for thin markets.

Never let an absurdly cheap isolated observation dominate an opportunity.

---

# 11. Supply vs demand signals

Try to identify situations where price movements have different causes.

Useful combinations:

```text
price ↑ + volume ↑
price ↑ + volume ↓
price ↓ + volume ↑
price ↓ + volume ↓
```

These should have different interpretations.

Examples:

```text
price ↑ + volume ↑
→ genuine demand expansion / supply shock candidate

price ↑ + volume ↓
→ potentially illiquid price distortion

price ↓ + volume ↑
→ active sell pressure / crash / temporary capitulation

price ↓ + volume ↓
→ potentially abandoned market
```

Do not hardcode these interpretations as truth.

Use them as explanatory signals contributing to confidence.

---

# 12. Cross-category correlation

This is where the tool can become genuinely interesting.

Look for relationships between markets.

Examples conceptually:

```text
Scarabs ↑
→ related mapping outputs ↑

Popular skill ↑
→ associated gems / uniques ↑

Base material ↑
→ crafted product prices may lag behind

Fragment ↑
→ related boss-entry materials may follow
```

The system should search for:

- correlated price movements
- lagged correlations
- leading indicators
- category-wide shocks

For example:

> Item A usually moves 2–6 hours before Item B.

That relationship itself becomes an opportunity detector.

Do not just calculate ordinary correlation.

Investigate lagged correlation.

---

# 13. Build "what changed?" detection

I want a dedicated feature that answers:

> "What is weird about the market today?"

Examples:

```text
12 essences are simultaneously 15–30% below
their 7-day median.

Scarabs have unusually high volume.

A category experienced a synchronized price drop.

This item normally rebounds after volume spikes.

Currency pair X has reached an unusually wide historical range.
```

This is potentially more useful than another giant sortable table.

Have a dashboard section:

## Market Signals

Each signal should say:

```text
WHAT HAPPENED
WHY IT MATTERS
POSSIBLE ACTION
CONFIDENCE
```

---

# 14. Opportunity scoring

Create a second-generation score.

Do NOT simply add every feature together.

Separate the dimensions:

```text
Profit
ROI
Liquidity
Confidence
Capital Efficiency
Time Efficiency
Risk
```

Then calculate a final score.

For example conceptually:

```text
Opportunity Score =
    Profit potential
    × Confidence
    × Liquidity
    × Time efficiency
    × Capital efficiency
    × Risk adjustment
```

The exact formula should be configurable and testable.

Do not let the score hide the underlying numbers.

The UI should always show why an opportunity scored highly.

---

# 15. Add "profit per hour" thinking

This is extremely important for the hideout-warrior use case.

A 30% flip that takes:

```text
20 minutes to execute
```

may be worse than a:

```text
5% conversion
```

that can be repeated hundreds of times.

Estimate:

```text
profit per operation
profit per capital invested
estimated operations/hour
estimated profit/hour
```

Use configurable assumptions.

For example:

```text
buy time
conversion time
listing time
sale time
```

The user should be able to choose:

```text
I have 100 divines
I am willing to spend 30 minutes
I want low interaction
```

and get opportunities optimized for those constraints.

---

# 16. Personal capital simulator

Eventually add a simple "What can I do with my money?" feature.

Inputs:

```text
budget
minimum ROI
minimum liquidity
maximum risk
maximum effort
```

Output:

```text
Opportunity A
→ requires 20d
→ expected +3.1d
→ ~5 minutes
→ high liquidity

Opportunity B
→ requires 60d
→ expected +12d
→ ~30 minutes
→ medium liquidity
```

This should make the application feel like an actual decision tool rather than an analytics dashboard.

---

# 17. Backtesting

Once historical collection works, build a basic backtester.

Given:

```text
signal generated at time T
```

ask:

```text
What happened afterwards?
```

For example:

```text
price +X% within 1h
price +X% within 6h
price +X% within 24h
```

Measure:

```text
win rate
average return
median return
maximum adverse movement
time to recovery
```

This is critical.

Do not optimize signals solely because they "look good."

A signal should demonstrate that historically it actually produced useful outcomes.

---

# 18. Learn which signals work

After backtesting, show:

```text
Signal:
Dip + high volume + recovery

Historical win rate:
68%

Median return:
+11%

Median recovery:
4.2 hours
```

This allows the system to progressively move from:

```text
heuristic scoring
```

towards:

```text
empirical scoring
```

without immediately needing machine learning.

Do NOT add an ML model unless there is enough historical data to justify it.

Good statistics and feature engineering should come first.

---

# 19. UI redesign

Do not make the main screen another enormous spreadsheet.

Suggested structure:

## Dashboard

### Top opportunities

Cards showing:

```text
+8.4d expected
92 confidence
18d capital
High liquidity

WHY:
20% below 7d median
volume +180%
historically rebounds after similar events
```

### Market Signals

```text
🔥 Scarab market unusually volatile
📈 Currency X showing strong upward momentum
⚠ Essence category experiencing supply shock
💰 Divination card set currently undervalued
```

### Opportunity Explorer

Allow filtering by:

```text
profit
ROI
capital
liquidity
risk
time
opportunity type
```

Then retain the existing detailed table as an advanced view.

---

# 20. Explainability is mandatory

Every generated opportunity should be able to explain itself.

Bad:

```text
Score: 87
```

Good:

```text
Score: 87

Why:
• price is at 8th percentile of 7d range
• volume is 2.4× normal
• category is showing recovery
• historical rebounds after similar events
• sufficient market depth
```

The user should never have to trust a mysterious number.

---

# 21. Data quality safeguards

Be extremely conservative about fake opportunities.

Handle:

- stale data
- zero volume
- tiny volume
- price outliers
- missing variants
- item renames
- league transitions
- temporary API failures
- currency normalization problems
- thin markets
- corrupted/missing history

Use confidence penalties rather than pretending uncertain data is reliable.

---

# 22. API architecture

Separate the system into clear layers:

```text
Data Sources
    ↓
Normalization
    ↓
Historical Storage
    ↓
Market Metrics
    ↓
Opportunity Detectors
    ↓
Opportunity Scoring
    ↓
UI
```

Do not put economy calculations directly inside React components.

Each detector should have a clean interface such as:

```text
detect(market_data) -> Opportunity[]
```

This makes it possible to add new strategies without turning the project into spaghetti.

---

# 23. Important API constraint

Do not assume there is an official public Trade API for arbitrary trade-site searching.

GGG's currently documented APIs include Public Stashes and Currency Exchange, while the trade site's internal endpoints are not part of the official supported API surface. Design the application around supported APIs first.

Manual links to the official trade site are fine.

If investigating undocumented endpoints, isolate that integration behind a provider interface so it can be removed/replaced without affecting the rest of the application.

Do not build the entire architecture around an unofficial endpoint.

---

# 24. Priority order

Do this incrementally.

### Phase 1
Persistent historical snapshots.

### Phase 2
Market regime + anomaly detection.

### Phase 3
Opportunity abstraction and multiple detector types.

### Phase 4
Currency Exchange historical integration.

### Phase 5
Transformation / conversion graph.

### Phase 6
Cross-category and lagged correlation detection.

### Phase 7
Backtesting.

### Phase 8
Hideout-warrior optimizer:
budget + time + risk + liquidity constraints.

### Phase 9
Polish dashboard and alerts.

Do not attempt everything at once.

At each phase:

1. implement
2. test with real league data
3. verify calculations
4. add tests for edge cases
5. only then continue

---

# Overall philosophy

The tool should answer:

> "Given the current PoE economy, what is something I can do from my hideout right now that has a good probability of making money?"

Not:

> "Which item has the highest flip score?"

Prefer discovering relationships such as:

```text
cheap input
→ deterministic transformation
→ expensive output
```

or:

```text
temporary price anomaly
→ historical tendency to recover
→ high-confidence opportunity
```

or:

```text
market A moves
→ market B historically follows
→ B is still lagging
```

or:

```text
this item is technically expensive
but its market depth is poor
→ fake opportunity
```

The final product should feel more like a **Bloomberg terminal for PoE's hideout economy** than a simple flipping calculator.

Optimize for:

**low effort + repeatability + liquidity + realistic profit + evidence.**