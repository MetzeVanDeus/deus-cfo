# DeusCFO V3 — Deferred / Unimplemented Instructions

> **Note:** This file contains the deferred, not-yet-implemented V3 instructions, extracted from `DeusCFO V3 — The Hideout Economy Engine.md`. The Mission and Part I sections 1–5 remain in the original document; this file continues from Part I section 6 onward. Text is preserved verbatim.


# 6. Stop requiring the desktop application to collect history

Split collection from the UI.

Target:

```text
deuscfo-ui
deuscfo-api
deuscfo-collector
```

The collector must be runnable independently.

It should work as:

```text
Docker service
OR
scheduled cloud worker
OR
small always-on server process
```

The React frontend should have absolutely no responsibility for historical collection.

The analytical backend should not have to remain open on the user's gaming PC.

---

# 7. Remote historical collector

Make the collector deployable on a cheap always-on host.

Do not redesign the entire project around cloud infrastructure.

Keep it simple:

```text
collector
    ↓
persistent database
```

A single small server is sufficient initially.

SQLite is still acceptable if only one collector/database process owns it.

If remote/multi-process requirements eventually make SQLite awkward, introduce another database only after that requirement is demonstrated.

Avoid premature infrastructure work.

---

# 8. Historical archival

GGG may not retain historical CX records forever.

Therefore DeusCFO should treat official history as:

```text
FETCH ONCE
PRESERVE FOREVER
```

Optionally create periodic compressed backups:

```text
league/
    cx_hourly/
    market_snapshots/
```

The raw source observation should never be discarded merely because derived statistics exist.

Derived data can always be recalculated.

Raw observations cannot.

---

# PART II — PROFIT THROUGH TRANSFORMATION

The existing project mainly finds:

```text
buy X
↓
wait
↓
sell X
```

V3 must add:

```text
buy X
↓
DO SOMETHING
↓
sell Y
```

This is where DeusCFO becomes a true hideout-warrior tool.

---

# 9. Build the Transformation Engine

Introduce a generic abstraction:

```text
Transformation {
    id
    name
    strategy_family

    inputs[]
    costs[]

    outputs[]

    deterministic
    outcome_probabilities

    execution_time
    manual_actions

    requirements

    source
    verified_version
}
```

Example:

```text
5 × Card X
↓
turn in complete set
↓
1 × Item Y
```

or:

```text
3 × Item A
↓
vendor
↓
1 × Item B
```

or:

```text
Unique X
+
deterministic linking method
↓
6-linked Unique X
```

Transformation definitions should be DATA.

Do not write a separate algorithm for every recipe.

Use JSON/YAML/database definitions.

---

# 10. ProfitRoute

Transformation evaluation should produce:

```text
ProfitRoute {
    transformation_id

    total_input_cost
    realistic_output_value

    gross_profit
    expected_net_profit

    roi

    capital_required

    capacity

    expected_execution_time
    expected_sale_time

    profit_per_hour
    profit_per_divine_hour

    confidence

    pricing_confidence

    strategy_confidence

    execution_risk

    reasons[]
}
```

These become normal InvestableOpportunities consumed by the existing CFO allocator.

The portfolio engine should not care whether profit came from:

- a statistical flip
- a divination-card turn-in
- a vendor transformation
- a six-link
- a currency conversion
- a Harvest transformation

Everything becomes capital deployment.

---

# PART III — FIRST PROFIT PROVIDERS

Do NOT attempt universal crafting.

Implement a deliberately small number of highly modelable strategy providers.

---

# 11. Strategy Provider #1 — Divination Card Set Arbitrage

This should be the first major V3 profit finder.

Model:

```text
card_price × set_size
=
complete_set_cost
```

versus:

```text
realistic_reward_value
```

Then:

```text
reward_value
-
set_cost
=
profit
```

Example conceptually:

```text
Card:
The Example

Set size:
8

Card acquisition:
42c × 8
= 336c

Reward:
Item X

Realistic reward value:
410c

Gross profit:
74c

ROI:
22%

Estimated turnover:
15–40 minutes
```

Scan ALL deterministic divination-card rewards that can be priced reliably.

---

# 12. Div Card reward registry

Create:

```text
DivCardRecipe {
    card
    set_size

    reward_type
    reward_item
    reward_quantity

    variant
    corrupted
    item_level
    special_conditions

    deterministic

    verified_version
}
```

Do NOT guess rewards from card text unless parsing is extremely reliable.

Prefer a maintained structured registry.

Allow manual corrections.

Patch/version changes must be detectable.

---

# 13. Start only with deterministic card rewards

V3.0 should initially reject:

```text
random unique
random currency
random item
random corrupted item
random influenced item
```

unless a trustworthy probability distribution exists.

Start with things such as:

```text
exact item
exact currency stack
exact fragment
exact deterministic reward
```

This makes expected profit meaningful.

Later:

```text
V3.x
```

can add probabilistic card sets.

---

# 14. Div-card execution realism

Do not simply use:

```text
poe.ninja card price × set size
```

and call the difference profit.

Estimate:

```text
acquisition price
reward liquidation price
liquidity
capacity
```

A card set producing 30% theoretical ROI but requiring twenty extremely illiquid cards may be worse than a 7% opportunity that can be repeated ten times per hour.

Expose:

```text
Theoretical ROI
Executable ROI
```

separately.

---

# 15. Repeatability matters

Calculate:

```text
profit_per_set
sets_possible_with_budget
estimated_sets_per_hour
market_capacity
```

Example:

```text
Profit:
0.18d / set

Capital:
1.4d / set

Likely throughput:
8 sets/hour

Estimated:
1.44d/hour

Market capacity:
~12 sets before edge likely disappears
```

THIS is useful hideout-warrior information.

---

# 16. Strategy Provider #2 — Deterministic assembly / disassembly

Build transformations for stackable items that convert deterministically into another item.

Examples conceptually include:

```text
splinters → completed object
shards → completed currency
fragments → assembled item
```

Do not hardcode examples from assumptions.

Create only version-verified transformations.

Then detect:

```text
sum(parts) < whole
```

AND where applicable:

```text
whole < value(parts)
```

This becomes an arbitrage graph.

---

# 17. Strategy Provider #3 — Vendor transformation chains

Create a small verified registry of deterministic vendor conversions.

Examples conceptually:

```text
3 × lower tier
→
1 × higher tier
```

or other fixed-ratio recipes.

Evaluate every registered conversion continuously.

Then evaluate multi-step chains:

```text
A
→ B
→ C
```

against:

```text
A
→ market
```

and:

```text
C direct purchase
```

Search for profitable paths.

Use graph traversal, but keep maximum route length small.

We do NOT need arbitrary 50-step currency cycles.

---

# 18. Multi-step arbitrage graph

Represent:

```text
Item = node
Transformation = edge
```

Then search:

```text
buy A
→ transform B
→ transform C
→ sell C
```

Calculate full route cost.

Example:

```text
A price
+ conversion costs
+ execution friction
=
route cost

C realistic sale
-
route cost
=
route profit
```

Prevent loops.

Initially cap routes to perhaps 3 transformation edges.

---

# 19. Strategy Provider #4 — Deterministic 6-link arbitrage

Investigate cases where DeusCFO can reliably price:

```text
unlinked item
```

and:

```text
same item, six-linked
```

Then evaluate known deterministic linking methods.

Conceptually:

```text
base item cost
+
linking method cost
=
finished cost
```

versus:

```text
6L realistic sale value
```

Only support items/variants where pricing can be matched confidently.

Do not attempt rare-item valuation.

A unique item with known variants is a much safer candidate.

---

# 20. Strategy Provider #5 — Finite-outcome gem transformations

After deterministic strategies work, introduce the first probabilistic provider.

Gems are attractive because outcomes can often be represented as a finite state tree and multiple variants are priceable.

Generic model:

```text
Input gem
+
action
↓
Outcome A with probability P1
Outcome B with probability P2
Outcome C with probability P3
...
```

Then calculate:

```text
EV = Σ(P(outcome) × realistic_value(outcome))
```

minus:

```text
input cost
+
transformation cost
```

DO NOT implement any transformation whose outcome probabilities are unknown or merely assumed.

This is an EV strategy, not a deterministic strategy, and must be clearly labelled.

---

# 21. Strategy Provider #6 — Harvest / bounded reroll strategies

Only after the Transformation Engine is stable.

Some transformations exchange one fungible category member for another or have a bounded set of outcomes.

These are good candidates IF:

```text
input cost
output possibilities
outcome probabilities
crafting cost
```

can all be represented confidently.

Do not model unknown probabilities as uniform just because uniform is convenient.

If probabilities are unknown:

```text
REJECT
```

---

# PART IV — STRATEGY REGISTRY

## 22. Strategies should be extendable manually

A major design objective:

I should be able to discover a money-making trick on Reddit/YouTube/Discord and add it to DeusCFO without rewriting the application.

Example definition:

```yaml
id: example_strategy
name: Example Conversion

inputs:
  - item: Item A
    quantity: 3

costs:
  - item: Currency B
    quantity: 1

outputs:
  - item: Item C
    quantity: 1
    probability: 1

execution:
  seconds: 10
  actions: 2

verified:
  patch: 3.28
```

DeusCFO handles:

```text
pricing
profit
ROI
liquidity
capacity
capital allocation
```

automatically.

This is extremely important.

The application should become a FRAMEWORK for hideout strategies rather than an ever-growing pile of hardcoded strategy logic.

---

# PART V — EXECUTION QUALITY

## 23. Profit must have three levels

Never expose one misleading profit value.

Calculate:

```text
THEORETICAL PROFIT
```

using headline prices.

Then:

```text
REALISTIC PROFIT
```

using conservative entry/exit assumptions.

Then:

```text
REALIZED PROFIT
```

once the user records the actual trade.

Example:

```text
Theoretical:
+0.84d

Realistic:
+0.59d

Actual:
+0.51d
```

This lets DeusCFO learn where its assumptions are wrong.

---

# 24. Add Strategy Friction

Each strategy definition can specify:

```text
manual_actions
estimated_seconds
zone_changes
NPC interaction
trade_count
```

Then estimate an effort score.

Example:

```text
Route A
+11% ROI
43 clicks/trades

Route B
+8% ROI
4 interactions
```

For a hideout warrior, Route B may be clearly superior.

---

# 25. Profit per Divine-Hour

Make this a first-class metric.

```text
expected_profit
/
(capital × time_locked)
```

Example:

```text
10d locked for 30m
Expected +0.8d
```

is economically different from:

```text
10d locked for 10h
Expected +1d
```

Rank strategies using BOTH:

```text
profit/hour
ROI
profit/divine-hour
```

No single metric should dominate every view.

---

# 26. Capital velocity

Track:

```text
How many times can this capital realistically turn over per day?
```

This is how relatively small edges compound.

A repeatable:

```text
5% × many rotations
```

can be substantially more valuable than a speculative:

```text
20% × one slow sale
```

Create:

```text
capital_velocity
```

and:

```text
expected_daily_compounding_value
```

for comparison.

Do not literally promise compounded returns; use this as a strategy-comparison estimate.

---

# PART VI — CFO ALLOCATOR V3

## 27. Feed transformations into the existing allocator

The allocator should receive:

```text
statistical opportunities
+
deterministic transformations
+
finite-outcome EV transformations
```

and construct the best use of capital.

Example:

```text
Net worth:
50d
```

Candidates:

```text
Div card sets
7d capacity
+9% executable ROI
~45m turnover

Vendor chain
4d capacity
+5%
~10m turnover

6L conversion
12d capacity
+13%
~3h turnover

Mean reversion
10d capacity
+8% expected
~8h holding time
```

DeusCFO may recommend:

```text
7d → div-card sets
4d → vendor conversion
10d → 6L conversion
5d → statistical opportunity
24d → reserve
```

This is substantially more useful than:

```text
buy Currency X
```

---

# 28. Prefer deterministic money where appropriate

Introduce strategy certainty classes:

```text
DETERMINISTIC
BOUNDED_EV
STATISTICAL
EXPERIMENTAL
```

A deterministic 6% profit can deserve capital before a statistically predicted 12% move.

However deterministic does NOT imply guaranteed profit because:

```text
input prices move
output prices move
liquidity disappears
execution differs
```

Therefore pricing confidence remains important.

---

# 29. Capital allocation must understand strategy capacity

Example:

```text
Div Card A:
excellent 14% route
maximum realistic deployment: 3d
```

The allocator should use only ~3d.

It should not conclude:

```text
50d × 14% = 7d profit
```

Opportunity capacity must be mandatory.

---

# 30. Batch planner

For transformations, show an actual batch plan.

Example:

```text
DIVINATION SET ROUTE

Capital:
6.8d

Buy:
56 × Card X

Complete:
7 sets

Turn in:
7 sets

Expected outputs:
7 × Item Y

Target sale:
≥ 1.08d each

Expected realistic profit:
+0.76d

Estimated cycle:
25–50 min

Maximum recommended batch:
7 sets
```

This is the hideout-warrior UI.

---

# PART VII — THE "MONEY PRINTER" SCREEN

## 31. Add a dedicated Profit Routes page

Do not mix all of this into Signals.

Create:

# Money Printer

Sections:

```text
BEST RIGHT NOW

DETERMINISTIC

DIVINATION SETS

CONVERSIONS

FINITE EV

WATCHLIST
```

Default sorting:

```text
Expected profit/hour
adjusted for confidence
```

User filters:

```text
Budget
Minimum profit
Minimum ROI
Maximum effort
Maximum cycle time
Strategy type
Deterministic only
```

---

# 32. Example table

```text
Strategy             Capital   Profit   ROI    Time    Confidence
-----------------------------------------------------------------
Card Set: X          7.2d      +0.8d    11%    35m     High
Oil Upgrade Chain    3.1d      +0.2d     7%    8m      Very High
6L Unique X          11d       +1.4d    13%    2.5h    High
Gem EV: Y            5d        +0.9d EV 18%    30m     Medium
Mean Reversion Z     8d        +0.7d EV  9%    8h      Medium
```

Clicking opens the complete execution plan.

---

# PART VIII — DATA-QUALITY AWARE STRATEGIES

## 33. Pricing confidence is independent from strategy certainty

Example:

```text
Transformation:
100% deterministic
```

does NOT mean:

```text
Profit confidence:
100%
```

If output pricing is weak, the trade is still risky.

Expose separately:

```text
Transformation certainty
Pricing confidence
Liquidity confidence
Historical confidence
```

---

# 34. Require a margin of safety

If:

```text
expected executable ROI = 2%
pricing uncertainty = ±5%
```

there is no opportunity.

Require edge > uncertainty.

Conceptually:

```text
safe_edge =
expected_profit
-
pricing_error_buffer
-
execution_buffer
```

Only recommend:

```text
safe_edge > minimum_threshold
```

This should eliminate huge numbers of fake transformation profits.

---

# 35. Price-source hierarchy

For every price record store source.

Prefer higher-quality sources when available.

Conceptually:

```text
live/direct market observation
>
high-confidence current market estimate
>
low-confidence aggregate estimate
```

Do not combine sources without preserving provenance.

The strategy UI should be able to say:

```text
Input pricing:
HIGH

Output pricing:
MEDIUM
```

---

# PART IX — LEARNING FROM ACTUAL EXECUTION

## 36. Trade journal becomes important

Allow manual recording:

```text
Bought 56 cards
Cost 6.65d

Sold outputs
Revenue 7.41d

Time:
37 minutes
```

DeusCFO records:

```text
Predicted:
+0.80d

Actual:
+0.76d
```

and:

```text
Predicted execution:
25m

Actual:
37m
```

---

# 37. Learn user-specific friction

Eventually calculate:

```text
User tends to pay:
+2.7% above modeled entry

User tends to sell:
-1.8% below modeled exit

User execution:
1.3× estimated duration
```

Then future opportunities are adjusted.

This is more useful than attempting increasingly complicated generic pricing heuristics forever.

---

# PART X — DO NOT AUTOMATE GAMEPLAY

## 38. Decision support only

DeusCFO may:

```text
identify opportunity
calculate quantities
generate trade links
show instructions
track results
```

It must NOT:

```text
automatically perform trades
automatically send game inputs
automatically execute crafting interactions
```

The user performs actions manually.

---

# PART XI — V3 IMPLEMENTATION ORDER

## Phase 1 — Data Trust

Implement:

```text
data provenance
remove synthetic data from backtests
CX full historical synchronization
missing-hour detection
coverage API
independent collector
```

Do this first.

---

## Phase 2 — Transformation Core

Implement:

```text
Transformation registry
ProfitRoute model
strategy-provider interface
profit calculation
execution friction
pricing confidence
```

No large strategy library yet.

---

## Phase 3 — Divination Card Sets

Implement the first complete profit provider:

```text
deterministic card → reward mappings
set cost
reward value
ROI
capacity
profit/hour
batch plans
```

Verify aggressively with real market data.

---

## Phase 4 — Deterministic Conversion Graph

Implement:

```text
assembly
vendor upgrades
fixed conversions
short multi-step routes
```

Search for profitable paths.

---

## Phase 5 — Six-Link Provider

Add only safely priceable deterministic linking opportunities.

Do not attempt arbitrary rare-item crafting.

---

## Phase 6 — Finite EV Providers

Introduce:

```text
gem transformations
bounded rerolls
other explicit finite outcome trees
```

only where probabilities are trustworthy.

---

## Phase 7 — CFO Integration

Combine:

```text
market opportunities
+
profit transformations
```

into one bankroll allocator.

The CFO should choose between them based on:

```text
profit
ROI
time
confidence
capacity
risk
capital lock
effort
```

---

## Phase 8 — Money Printer UI

Build the dedicated actionable view.

The first screen should answer:

> "How do I turn my currency into more currency right now?"

not:

> "How many anomalies exist?"

---

# PART XII — WHAT NOT TO BUILD

Do NOT build:

- universal rare-item crafting
- arbitrary modifier valuation
- an AI crafting planner
- automated trade-site scraping as a core dependency
- automated gameplay
- synthetic historical data
- machine learning merely because we have more features
- another fifteen market indicators

These are distractions from the current objective.

---

# Final Product Philosophy

V1 answered:

> "What looks unusual?"

V2 answered:

> "Does historical evidence support this?"

V3 must answer:

> **"What action converts my capital into more capital?"**

DeusCFO should discover four broad forms of money:

```text
PRICE INEFFICIENCY
buy low → sell higher

TRANSFORMATION INEFFICIENCY
buy ingredients → transform → sell output

ASSEMBLY INEFFICIENCY
parts → whole

PROBABILITY INEFFICIENCY
input cost < expected outcome value
```

Then the CFO layer determines which ones deserve capital.

For a 50-divine bankroll, the ideal end result is something like:

```text
BANKROLL
50.0d

DEPLOY
24.5d

7.0d
Divination set arbitrage
+0.72d expected
30–50m

3.5d
Deterministic conversion chain
+0.21d expected
10–20m

9.0d
Six-link transformation
+1.05d expected
1–3h

5.0d
Market opportunity
+0.44d expected
4–8h

RESERVE
25.5d
```

with an explanation:

```text
Why not deploy more?

Current remaining strategies fail one or more of:

margin-of-safety
liquidity
capacity
confidence
time-efficiency
```

That is the V3 destination.

The system should stop being merely good at observing the Path of Exile economy.

