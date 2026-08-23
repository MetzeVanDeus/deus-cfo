# DeusCFO V1.2 — Capital Deployment & Profit Engine

DeusCFO now has:

- historical market collection
- anomaly detection
- regime classification
- market signals
- opportunity scoring
- bias-free backtesting
- empirical signal performance
- Wilson confidence intervals
- market-wide event detection
- lagged relationship analysis
- execution-aware opportunity fields
- valid rejection of weak opportunities

The system is correctly refusing to fabricate opportunities when historical evidence is insufficient.

That behavior must be preserved.

The next objective is NOT to add more indicators.

The next objective is:

> Turn market intelligence into an actionable capital-allocation plan.

The system should eventually be able to answer:

> "I currently have 50 divines."

with something resembling:

```text
Recommended Deployment

10d → Opportunity A
Expected return: +12%
Expected duration: 3–6h
Probability of profit: 74%

18d → Opportunity B
Expected return: +8%
Expected duration: 8–14h
Probability of profit: 81%

22d → Hold as liquid reserve

Portfolio expectation:
Capital deployed: 28d
Expected profit: +2.7d
Expected portfolio return: +9.6% on deployed capital
Expected return on total net worth: +5.4%

Expected completion window: 8–14h

Estimated probability portfolio finishes profitable: 83%

Downside scenario:
10th percentile outcome: -0.8d

Do not deploy the remaining 22d because current opportunities do not justify the additional risk.
```

This is the product direction.

---

# 1. Introduce the concept of a bankroll

Create a user portfolio / bankroll model.

At minimum:

```text
Bankroll {
    total_net_worth
    liquid_currency
    currently_invested
    reserved_capital
}
```

Initially this can be configured manually.

Example:

```text
Total net worth: 50d
Liquid: 50d
Invested: 0d
```

Do NOT assume the optimal decision is to invest all available currency.

Unallocated capital is a legitimate position.

---

# 2. User investment preferences

Add configurable constraints.

Example:

```text
Capital: 50d

Risk tolerance:
Low / Medium / High

Desired horizon:
1h / 3h / 6h / 12h / 24h / 3d

Minimum liquidity:
Low / Medium / High

Maximum effort:
Low / Medium / High

Minimum reserve:
20%

Maximum single-position exposure:
30%

Maximum category exposure:
50%
```

Also allow an advanced mode with exact numeric settings.

The user should be able to say:

```text
I have 50 divines.

I don't want to risk more than 10% of my bankroll.

I prefer trades that finish within 12 hours.

Keep at least 15 divines liquid.

I don't want strategies requiring hundreds of trades.
```

The optimizer must respect those constraints.

---

# 3. Turn opportunities into investable positions

The current Opportunity abstraction should be extended into something the allocation engine can reason about.

Example:

```text
InvestableOpportunity {
    id
    strategy_type

    entry_item
    exit_item

    current_price
    realistic_entry_price
    realistic_exit_price

    expected_return
    expected_profit_per_unit

    win_probability

    expected_duration
    duration_distribution

    downside_percentile
    upside_percentile

    historical_sample_size
    confidence

    liquidity
    execution_effort

    minimum_capital
    maximum_reasonable_capital

    opportunity_capacity

    correlation_group

    expiration
}
```

The most important new properties are:

```text
maximum_reasonable_capital
opportunity_capacity
expiration
```

An opportunity may be good with 3 divines but terrible with 30 divines.

Do not assume opportunities scale infinitely.

---

# 4. Opportunity capacity

Estimate how much capital can realistically be deployed.

Example:

```text
Item price: 20c

Historical traded volume:
500 units/hour

Safe participation rate:
5%

Estimated realistic purchase capacity:
25 units/hour
```

An opportunity should therefore expose something like:

```text
Suggested capital range:
2.5d – 7d
```

instead of:

```text
ROI: 18%
```

This prevents the optimizer from doing something absurd like allocating 40 divines into a market where only 3 divines can realistically be moved.

Capacity should consider:

- trading volume
- listing depth where available
- historical liquidity
- expected time horizon
- reasonable market participation percentage
- slippage
- execution confidence

Be conservative.

---

# 5. Position sizing

Build a position-sizing engine.

Do NOT simply allocate the maximum possible capital into the highest-return opportunity.

Position size should depend on:

```text
expected return
confidence
sample size
downside risk
liquidity
market capacity
correlation
time horizon
user risk tolerance
```

A possible conceptual approach is a heavily capped fractional-Kelly-style allocation.

However:

DO NOT blindly implement textbook Kelly Criterion.

Historical PoE market data is noisy and estimated probabilities are uncertain.

If Kelly-inspired sizing is used:

- shrink expected advantage aggressively
- cap allocations
- include estimation uncertainty
- include liquidity capacity
- respect user exposure limits

Conservative position sizing is preferred.

---

# 6. Portfolio construction

The allocator should evaluate combinations of opportunities.

The goal is not:

```text
choose highest score
```

The goal is:

```text
find an allocation with the best expected outcome
subject to risk, liquidity, capacity and user constraints
```

Example candidate portfolio:

```text
Bankroll: 50d

A:
10d
Expected +1.4d
6h
High liquidity

B:
12d
Expected +0.9d
12h
High confidence

C:
5d
Expected +0.8d
4h
Higher risk

Reserve:
23d
```

The optimizer should compare this against alternatives.

---

# 7. Diversification and correlation

Do not treat opportunities as independent.

Example:

```text
Opportunity A:
Buy scarab X

Opportunity B:
Buy scarab Y

Opportunity C:
Buy scarab Z
```

If all three are driven by the same scarab-market event, allocating heavily to all three is effectively one giant position.

Use:

- category
- historical correlations
- market-event membership
- detected leader/laggard relationships
- shared underlying currency exposure

to create correlation groups.

Penalize portfolios with excessive correlated exposure.

Example:

```text
Scarabs: 40%
Essences: 20%
Currency: 15%
Reserve: 25%
```

may be preferable to:

```text
Scarabs: 75%
Reserve: 25%
```

even when the latter has slightly higher theoretical EV.

---

# 8. Portfolio-level simulation

Do not calculate portfolio confidence by averaging individual confidence scores.

Instead simulate portfolio outcomes.

Prefer empirical historical return distributions wherever possible.

For each candidate allocation, estimate:

```text
Expected profit

Median profit

Probability profit > 0

Probability profit > target

10th percentile outcome

25th percentile outcome

75th percentile outcome

90th percentile outcome

Expected completion time

Capital locked over time
```

Monte Carlo simulation is acceptable if implemented carefully.

Avoid pretending variables are normally distributed unless data supports that assumption.

Empirical resampling / bootstrap-based approaches are preferable where enough data exists.

Correlations between opportunities should be preserved where possible.

---

# 9. Expected time must become first-class

The user specifically cares about:

```text
Profit within T amount of time.
```

Therefore every opportunity should have an estimated duration.

Model:

```text
entry_time
holding_time
exit_time
```

Eventually estimate:

```text
P(position exits within 1h)
P(position exits within 3h)
P(position exits within 6h)
P(position exits within 12h)
P(position exits within 24h)
```

Then portfolio output can say:

```text
Expected profit:
+3.1d

Expected time:
8h

80% completion interval:
5–14h
```

Do not present a precise completion time if the underlying data is uncertain.

---

# 10. Capital lockup

Two opportunities with identical profit can behave very differently.

Example:

```text
A:
10d → +1d
capital locked ~1 hour

B:
10d → +1d
capital locked ~18 hours
```

A is dramatically better because the currency can be redeployed.

Introduce metrics such as:

```text
expected_return_per_hour
expected_profit_per_divine_hour
```

Example:

```text
Opportunity A

Capital: 10d
Expected profit: 1d
Expected duration: 2h

Profit / divine-hour:
0.05
```

This metric should NOT completely replace ROI.

Use both.

---

# 11. Opportunity expiration

Market opportunities decay.

An anomaly detected at 14:00 may no longer be actionable at 17:00.

Each opportunity should estimate:

```text
created_at
last_validated_at
expected_half_life
expires_at
```

Re-evaluate active recommendations whenever new snapshots arrive.

An opportunity should automatically become:

```text
STALE
```

or:

```text
INVALIDATED
```

when market conditions change.

Never continue recommending a position merely because it scored highly several hours ago.

---

# 12. Reserve capital

The allocator MUST explicitly value liquidity.

Holding currency is not wasted capital.

Reasons to maintain reserve:

- uncertain current market
- opportunity scarcity
- expected future opportunities
- correlated existing positions
- liquidity risk
- user-defined safety buffer

The optimizer should be capable of recommending:

```text
Deploy 17d.
Hold 33d.
```

even if the user owns 50d.

Eventually maintain a dynamic reserve target.

Example:

```text
Normal market:
25% reserve

Highly uncertain market:
50% reserve

Exceptional opportunity:
15% reserve
```

But user minimum reserve must always be respected.

---

# 13. Introduce Opportunity Tiers

Avoid presenting 100 equally important candidates.

Classify opportunities:

```text
Tier S
Strong empirical evidence
High liquidity
Favorable expected value
Good capacity
Acceptable downside

Tier A
Good opportunity but some uncertainty

Tier B
Interesting but insufficient edge

Watch
Potential setup that has not triggered

Rejected
Fails empirical/risk/liquidity thresholds
```

Only Tier S/A opportunities should normally be eligible for portfolio allocation.

---

# 14. Watchlist / future opportunity capital

A major reason to hold reserve is that a promising setup may not yet be ready.

Introduce:

```text
WatchOpportunity
```

Example:

```text
Divination Card X

Current state:
Watching

Trigger:
Price below 7d 15th percentile
AND
volume recovery > 1.4×

Estimated capital requirement:
8–12d

Current trigger probability:
Moderate
```

Then the portfolio allocator can reason:

```text
Keep approximately 10d available because two high-quality setups are close to triggering.
```

This makes reserve capital intelligent instead of arbitrary.

---

# 15. Actual trade plans

The final recommendation should be operational.

Not:

```text
Opportunity Score: 91
```

Instead:

```text
POSITION 1

Item:
X

Action:
Buy

Target entry:
≤ 82c

Maximum entry:
86c

Capital allocation:
8d

Estimated quantity:
~23

Target exit:
96–101c

Stop / invalidation:
Price remains below 78c after 3h
OR
volume trend reverses
OR
market regime becomes Crashing

Expected profit:
+1.2d

Expected duration:
4–8h

Historical sample:
184 comparable events

Historical win rate:
72%

Current confidence:
Moderate-High
```

The system should provide enough information for the user to execute manually.

---

# 16. Exit logic

Entry detection alone is insufficient.

Every opportunity detector should eventually define:

```text
entry_condition
profit_target
time_exit
invalidation_condition
```

Possible exit triggers:

```text
target value reached

historical median rebound reached

signal disappeared

market regime changed

maximum holding time reached

liquidity deteriorated

better capital allocation became available
```

Do NOT simply recommend:

```text
buy low and wait until higher
```

A capital-allocation engine requires exit logic to know when capital becomes available again.

---

# 17. Reallocation

Each new market snapshot should allow the allocator to reevaluate:

```text
existing positions
new opportunities
reserve
```

Example:

```text
Current position:
10d in A

Expected remaining return:
+2%

New opportunity B:
Expected +11%

A is liquid enough to exit.

Recommendation:
Exit A and redeploy 8d into B.
```

However, account for execution costs.

Do not churn positions for tiny theoretical improvements.

Introduce a minimum reallocation advantage.

---

# 18. Paper portfolio

Before trusting real-money recommendations, create a simulated portfolio.

Example:

```text
Starting bankroll:
50d
```

Whenever the allocator produces a plan, allow it to enter simulated positions.

Track:

```text
entry price
predicted exit
actual subsequent price
predicted duration
actual duration
predicted profit
realized simulated profit
```

Maintain equity curve:

```text
50d
52d
49.8d
55.1d
...
```

This is essential.

The system must demonstrate that portfolio recommendations outperform simply holding currency before being trusted.

---

# 19. Prediction calibration

Track whether the system's predictions mean what they claim.

If DeusCFO says:

```text
70% probability of profit
```

then approximately 70% of comparable recommendations should actually be profitable.

Group historical recommendations into confidence buckets:

```text
50–60%
60–70%
70–80%
80–90%
90%+
```

Compare predicted success against actual success.

Example:

```text
Predicted:
70–80%

Actual:
61%
```

This means the system is overconfident.

Correct future probability estimates accordingly.

Calibration is more important than producing impressive-looking confidence scores.

---

# 20. Predicted versus realized profit

Eventually allow manual real-trade tracking.

The user can mark:

```text
Bought:
22 units @ 84c

Sold:
22 units @ 97c
```

Calculate:

```text
Predicted profit
Realized profit

Predicted duration
Actual duration

Predicted entry
Actual entry

Predicted exit
Actual exit
```

This allows DeusCFO to learn the difference between:

```text
market-theoretical execution
```

and:

```text
this user's real execution
```

For example, it may discover:

```text
Predicted acquisition time:
8 minutes

Actual user acquisition time:
17 minutes
```

Future profit/hour calculations can then become personalized.

Do not automatically execute trades.

The system remains decision support.

---

# 21. Strategy providers

Do not create one enormous universal opportunity algorithm.

Use strategy providers.

Interface conceptually:

```text
StrategyProvider {
    discover(context) -> InvestableOpportunity[]
}
```

Examples:

```text
MeanReversionStrategy

MomentumStrategy

LeaderLaggardStrategy

CurrencySpreadStrategy

DeterministicConversionStrategy

BulkPricingStrategy

CraftStrategy
```

Portfolio allocation should not care how an opportunity was discovered.

It only consumes normalized InvestableOpportunity objects.

---

# 22. Crafting without solving all of Path of Exile

Do NOT attempt to build a universal crafting optimizer.

That is outside the reasonable scope of this project.

Instead create a constrained:

# Transformation Strategy Registry

Represent known profitable processes explicitly.

Example:

```text
Transformation {
    id
    name

    inputs[]

    deterministic_costs[]

    probabilistic_costs[]

    outputs[]

    expected_execution_time

    requirements

    risk_model
}
```

Then a strategy provider can evaluate:

```text
Current input cost
vs.
Current realistic output value
```

This allows easy crafting/conversion opportunities to be added incrementally without attempting to understand every possible PoE crafting interaction.

---

# 23. Simple craft opportunity model

Start only with transformations that can be reasonably modeled.

Prefer:

```text
deterministic transformations
```

then:

```text
small finite-outcome probabilistic transformations
```

Avoid complex multi-stage crafting initially.

Example conceptual calculation:

```text
Expected craft cost:
3.2d

Expected realistic sale value:
4.4d

Expected margin:
1.2d

Estimated time-to-sale:
2.7h

Historical sales confidence:
High

Maximum sensible batch:
4 items

Recommended capital:
12.8d
```

Only expose crafting opportunities when all major cost components can be modeled.

If the system cannot estimate the outcome distribution, reject the opportunity.

---

# 24. Craft recipes should be data, not code

Create recipes using JSON/YAML/database records rather than hardcoding every craft.

Conceptually:

```text
name: Example Transformation

inputs:
  - item: X
    quantity: 1

steps:
  - currency: Y
    quantity: 4

outputs:
  - item: Z
    probability: 1.0
```

Then new transformations can be added later without changing the strategy engine.

This becomes the extensibility point for manually discovered hideout-warrior methods.

---

# 25. Strategy discovery versus strategy validation

Maintain a strict distinction.

A strategy can be:

```text
Experimental
Validated
Rejected
Deprecated
```

A newly added transformation may look profitable right now but have no historical evidence.

Do not mix it with statistically validated opportunities.

Example:

```text
Experimental Opportunity

Estimated ROI:
18%

Historical validation:
Unavailable

Execution confidence:
Medium

Maximum suggested allocation:
2% bankroll
```

The portfolio allocator should cap experimental strategies much more aggressively.

---

# 26. Capital allocation objective

The objective should NOT simply maximize expected profit.

Use something conceptually like:

```text
maximize:

expected portfolio profit

while penalizing:

downside risk
capital lockup
correlated exposure
uncertainty
poor liquidity
execution effort
```

subject to:

```text
available capital
minimum reserve
position capacity
maximum position size
maximum category exposure
user risk tolerance
```

Keep the optimization understandable.

Do not introduce a highly sophisticated mathematical optimizer if a constrained search / heuristic allocator produces equivalent practical results.

Correctness and explainability matter more than mathematical elegance.

---

# 27. Example desired output

Given:

```text
Net worth:
50d

Risk:
Medium

Maximum horizon:
12h

Effort:
Low/Medium

Minimum reserve:
15d
```

DeusCFO should eventually produce:

# Capital Plan

## Deploy 26d

### 10d — Opportunity A

Expected profit:
+1.4d

Expected duration:
3–5h

Probability profitable:
76%

Downside estimate:
-0.6d

Reason:
Strong mean-reversion event with high liquidity and 214 historical analogues.

---

### 9d — Opportunity B

Expected profit:
+0.8d

Expected duration:
6–10h

Probability profitable:
82%

Downside estimate:
-0.3d

Reason:
Leader-laggard relationship currently triggered.

---

### 7d — Opportunity C

Expected profit:
+0.6d

Expected duration:
4–8h

Probability profitable:
69%

Reason:
Current conversion spread exceeds historical execution threshold.

---

## Hold 24d

Reason:

```text
15d mandatory reserve

5d reserved because Opportunity D is near its entry trigger

4d remains unallocated because available opportunities do not meet risk-adjusted return requirements
```

---

# Portfolio Forecast

```text
Capital deployed:
26d

Expected profit:
+2.8d

Expected return on deployed capital:
+10.8%

Expected return on total net worth:
+5.6%

Probability portfolio profitable:
84%

Median completion:
7.2h

80% completion range:
4.5–12.6h

10th percentile outcome:
-0.7d

Median outcome:
+2.5d

90th percentile outcome:
+6.1d
```

And most importantly:

```text
Recommendation:
DEPLOY
```

or:

```text
Recommendation:
WAIT
```

---

# 28. Dashboard direction

Create a new main dashboard section:

# CFO

This should become the primary screen.

At the top:

```text
Net Worth
50d

Deployed
26d

Reserve
24d

Expected Profit
+2.8d

Portfolio Confidence
84%
```

Below:

## Recommended Actions

Actual actionable positions.

Then:

## Current Positions

Tracked open opportunities.

Then:

## Near Triggers

Markets worth watching.

Then:

## Capital Forecast

Expected portfolio outcome distribution.

Existing Signals / Explorer screens remain available for analysis.

The default experience should answer:

> "What should I do?"

The analytical screens answer:

> "Why?"

---

# 29. Profit journal

Create a history of portfolio recommendations.

Store every generated recommendation even when the user does not act on it.

```text
PortfolioRecommendation {
    timestamp
    bankroll
    positions[]
    reserve
    expected_profit
    expected_duration
    expected_distribution
}
```

Later evaluate what would actually have happened.

This provides rolling forward-testing.

Do not overwrite old recommendations.

The historical record is essential for determining whether DeusCFO actually works.

---

# 30. Performance dashboard

Eventually show:

```text
Paper bankroll:
50d → 68.4d

30-day return:
+36.8%

Maximum drawdown:
-7.2%

Recommendations:
134

Profitable:
89

Median position:
+6.1%

Predicted portfolio EV:
+17.9d

Realized paper profit:
+18.4d

Calibration error:
3.8%
```

Also compare against simple baselines.

For example:

```text
DeusCFO strategy
vs.
Hold Divine
vs.
Random eligible opportunity
vs.
Highest raw ROI
vs.
Highest existing Flip Score
```

If DeusCFO does not outperform simple baselines, improve the model rather than hiding the result.

---

# 31. Current data limitation

The system currently has only:

```text
3,264 snapshots
32 timestamps
```

This is insufficient to make strong empirical claims.

Therefore:

Do NOT weaken validation thresholds simply to produce recommendations.

Instead introduce three modes:

```text
OBSERVE
PAPER
LIVE-CANDIDATE
```

### OBSERVE

Insufficient evidence.

Collect data and show interesting setups only.

### PAPER

Enough evidence to generate simulated allocations.

Track them but do not describe them as validated live recommendations.

### LIVE-CANDIDATE

Only strategies with sufficient history, calibration and forward-test performance become eligible.

This lets development continue while history accumulates.

---

# 32. Avoid waiting for months of data to develop

Although statistical claims require history, the infrastructure can be built now.

Implement:

- bankroll model
- investable opportunity schema
- allocation engine
- reserve logic
- capacity model
- portfolio simulator
- paper portfolio
- prediction calibration
- trade journal
- transformation registry

Use synthetic fixtures and existing historical data for testing.

Clearly label unreliable predictions.

Do not manufacture confidence.

---

# 33. Do not over-engineer crafting

This deserves explicit emphasis.

Do NOT attempt:

```text
all bases
×
all currencies
×
all crafting benches
×
all fossils
×
all essences
×
all modifiers
×
all influence mechanics
×
all possible outcomes
```

That becomes an entirely separate Path of Exile crafting simulator.

Instead:

```text
discover profitable strategy manually
↓
represent strategy in Transformation Registry
↓
DeusCFO evaluates live economics
↓
Portfolio allocator decides whether it deserves capital
```

This gives us most of the practical value with a fraction of the complexity.

---

# 34. Architecture

Target:

```text
Market Data
    ↓
Signals / Regimes / Anomalies
    ↓
Strategy Providers
    ↓
Investable Opportunities
    ↓
Execution / Capacity Model
    ↓
Historical Outcome Model
    ↓
Portfolio Allocator
    ↓
Capital Plan
    ↓
Paper / Real Trade Journal
    ↓
Calibration
```

The central abstraction becomes:

```text
InvestableOpportunity
```

not:

```text
MarketSignal
```

Signals explain opportunities.

Opportunities receive capital.

---

# 35. Primary success metric

The project should no longer be judged by:

```text
number of opportunities found
```

or:

```text
accuracy of regime classifications
```

The primary metric becomes:

# Growth of bankroll under realistic constraints.

Specifically:

```text
risk-adjusted realized/paper return
```

while measuring:

```text
drawdown
capital utilization
profit per hour
prediction calibration
liquidity failures
execution failures
```

---

# 36. Final philosophy

DeusCFO should think like a portfolio manager.

It should not say:

> "Scarabs look cheap."

It should say:

> "Scarabs look cheap, but the evidence is weak, so do nothing."

It should not say:

> "Opportunity A has 18% ROI."

It should say:

> "A has approximately 18% theoretical ROI, but only enough liquidity for a 4-divine position."

It should not say:

> "Opportunity A is the best."

It should say:

> "With a 50-divine bankroll, allocating 8d to A and 11d to B produces a better risk-adjusted portfolio than allocating 19d to either individually."

It should not say:

> "You have 50d available."

It should say:

> "Only 27d deserves to be deployed under current conditions. Keep the remaining 23d liquid."

And eventually the ideal DeusCFO interaction becomes:

> **User:** I have 50 divines. What do I do?

> **DeusCFO:** Deploy 8d here, 11d here, and 6d here. Keep 25d liquid. The portfolio has a historically calibrated ~79% probability of producing a positive return, with an expected +2.6d over approximately 8 hours. Here are the exact entry, exit and invalidation conditions.

That is the destination.

# DeusCFO UI / UX Direction

The current UI is functional but visually rough. Refine it into a polished dark financial/market intelligence terminal.

Do NOT redesign the application into a generic SaaS dashboard.

Target aesthetic:

> Bloomberg/crypto trading terminal × modern game economy tool × subtle Dracula influence.

Dracula does not need to be followed strictly. Preserve the dark purple identity, but prioritize readability and professional visual hierarchy.

## Core principles

- Dense but not cluttered.
- Information hierarchy over giant cards.
- Important opportunities should immediately attract the eye.
- Secondary analytics should recede visually.
- Reduce unnecessary borders and boxed containers.
- Reduce excessive padding and card height.
- Avoid making every element equally prominent.
- Use color primarily for meaning, not decoration.
- Prefer subtle surfaces, separators, typography and spacing over thick outlines.
- Use consistent 8px-ish spacing rhythm and tighter dashboard layouts.
- Desktop-first; this is a market terminal, not a mobile landing page.

## Color direction

Use a near-black/slightly purple background rather than flat gray.

Suggested character:

Background:
very dark charcoal-purple

Elevated surfaces:
slightly lighter desaturated purple/gray

Primary accent:
muted Dracula purple

Positive:
soft green

Negative:
soft red

Warning:
amber

Informational:
blue/cyan

Text:
high-contrast off-white for primary text,
muted blue-gray for secondary information.

Avoid neon saturation everywhere.

Colored borders should be exceptional rather than the default.

## Navigation

Make the header considerably more compact.

Current navigation consumes too much vertical space.

Use a slim top bar with:

DeusCFO
Dashboard
CFO
Signals
Explorer
Strategies

Highlight the active section using a subtle filled background or underline rather than the large outlined pill currently used.

The future `CFO` / Capital Plan page should become the primary/default view once implemented.

## Dashboard hierarchy

The page should visually answer, in this order:

1. What should I do?
2. How much money can I make?
3. How confident are we?
4. What changed in the market?
5. Why does DeusCFO believe this?

Do not lead with generic metrics such as "items tracked."

Those can live in a small system-status strip.

Instead, prominent top-level metrics should eventually be:

Net Worth
Capital Deployed
Liquid Reserve
Expected Profit
Portfolio Risk
Market State

## Opportunity cards

Current opportunity cards are far too tall.

Make them compact and decision-oriented.

A good card should resemble:

[MEAN REVERSION] [HIGH CONFIDENCE]

Abrasive Catalyst                         8.2d allocation

BUY ≤ 14.2c        TARGET 16–17c
+11.8% EV          3–6h
74% profitable     High liquidity

↓ 22% below median · Volume +83% · 184 analogues

[View Analysis]

The user should understand the trade within 2–3 seconds.

Long prose such as:

"What happened"
"Why it matters"
"Possible action"

belongs in expanded details, not on every dashboard card.

## Confidence

Never show giant full-width 100% confidence bars.

Confidence should be compact:

74% · High

or a small restrained meter.

100% should be extremely rare and should not visually imply certainty when it simply represents a normalized heuristic score.

Clearly distinguish:

Heuristic Score
Historical Confidence
Probability of Profit

These are not interchangeable.

## Typography

Improve hierarchy substantially.

Use roughly:

Page title        22–26px
Section heading   16–18px
Card title        14–16px
Primary metric    18–24px
Body              13–14px
Metadata          11–12px

Use tabular numerals for prices, percentages and financial values where possible.

Numbers should visually align cleanly.

## Tables

Use tables aggressively where comparison matters.

Not everything should be a card.

Good candidates:

- opportunities
- positions
- watchlist
- strategy performance
- historical signals

Use:

sticky headers
subtle row hover
compact rows
sortable columns
right-aligned numerical values
small inline sparklines where useful

Cards are for summaries and exceptional events.
Tables are for scanning markets.

## Charts

Replace CSS-style decorative charts with proper compact analytical visualizations where useful.

Prefer:

- sparklines
- small price/volume charts
- entry/target markers
- percentile bands
- portfolio equity curve
- allocation donut/bar
- return distributions

Avoid large decorative charts with little decision value.

## Progressive disclosure

The dashboard should show the conclusion first.

Example:

BUY 8d
Expected +0.9d
3–6 hours
74% historical probability

Then allow expanding into:

- historical analogues
- regime
- anomaly evidence
- price history
- backtest statistics
- reasoning
- raw metrics

Do not force users to read analysis before seeing the recommendation.

## Market Signals

Compress low-level signals into a feed rather than enormous cards.

Example:

12:31  🔴 PRICE SHOCK    Abrasive Catalyst    -22%    unusual volume
12:27  🟢 RECOVERY       Divine Beauty         +8%     73% analogue rate
12:18  🟡 LAGGARD        Scarab X              trigger  3h expected lag

Clicking opens full detail.

## Visual polish

Use:
- subtle shadows
- 1px low-contrast separators
- restrained border radius (~6–10px)
- hover transitions around 120–180ms
- excellent alignment
- consistent spacing
- iconography only when useful

Avoid:
- gradients everywhere
- excessive glow
- thick colored borders
- huge rounded pills
- emoji as primary interface icons
- oversized cards
- excessive empty vertical space

Small restrained accents will make the purple theme feel much more premium.

## Overall goal

DeusCFO should feel like software someone leaves open on a second monitor all day.

Not:

> a collection of React cards displaying backend objects

But:

> a compact decision terminal showing where capital should go, what changed, and what deserves attention.

Optimize every screen for scanability and decision speed.