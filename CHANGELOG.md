# Changelog
## 0.5.0 — 2026-08-28

### Added

- Added a single `VERSION` source, a GitHub Releases update check, `GET /api/update/status`, and a top-bar update badge with a footer refresh control.
- Added shared empty/loading/error state presentation and a clearer action hierarchy with primary, secondary, segmented, and disabled control treatments.

### Changed

- Reworked the frontend into a consistent dark-brass design system with centralized tokens, six-step typography and spacing scales, clearer sunken/standard/raised surfaces, stronger field boundaries, and system font stacks without bundled or remote font assets.
- Split the frontend styling into Tailwind entry, token, base, and component stylesheets; removed duplicate purple/brass token vocabulary and mapped remaining legacy `dracula-*` utilities onto the brass palette pending component cleanup.
- Moved the Oracle decoration into a dedicated CFO header grid column so it no longer overlaps market state or simulation controls.
- Restored the pre-surface-pass outline color on panels, cards, decision blocks, profit-route cards, and the update modal while retaining the newer divider and field borders.
- Packaged Windows builds now include `VERSION`, and CI/release verification requires `VERSION`, `frontend/package.json`, and tagged releases to agree.

### Release

- Bumped the application/frontend version to `0.5.0` for the design-system overhaul and GitHub Releases update-checking flow.

## 0.4.0 — 2026-08-27

### Added

- Added a typed, budget-bounded `batch_plan` to existing profit routes with exact card quantities, expected outcomes, cumulative-depth cost/revenue/net, break-even proceeds, effort and lock ranges, maximum recommended batch, binding constraint, and advisory trade links.
- Added finite-positive `budget_chaos` and `horizon_hours` inputs to `/api/profit-routes`; requests without a budget remain read-only and omit the plan.
- Added divination-card registry health and curation diagnostics for accepted and rejected records, missing market identities, stale patch records, unsupported reward categories, and read-only shadow-evaluation results.
- Added exact-match deterministic unique-reward sell-listing collection with ten-ID fetch batching, a minimum three-listing nearby-price cluster, isolated-outlier rejection, a strictly positive configurable haircut, and persisted `sell_listing_floor` provenance.
- Added README PAPER workflow capture at `docs/screenshots/cfo-paper-workflow.mp4`.

### Changed

- Curated the existing Doctor → Headhunter definition with explicit manual verification and a direct definition source; no unsupported recipes or probabilistic rewards were added.
- Added the Profit Routes budget/horizon controls and batch-plan display, including exact quantities, Chaos economics, effort/lock units, constraints, expected outcomes, and safe manual search links.
- Preserved validated Path of Exile trade-search URLs with collected execution quotes so the planner can surface them without submitting searches, sending whispers, or executing game input.
- Allowed deterministic unique rewards without buyer bids to use a conservative haircut sell-listing floor for manual batch planning; buyer-side executable depth and sell-listing evidence remain explicitly distinguishishable in route outputs, batch plans, reasons, and verification metadata.

### Fixed

- Failed closed on ambiguous market variants, missing exact reward prices, stale recipe patches, malformed trade links, and random/corrupted/influenced records presented as deterministic.
- Reported exact stale recipe IDs during patch rollover and withheld every mismatched divination-card route instead of carrying old verification forward.
- Kept unique-reward routes fail-closed when exact listing identity, minimum nearby depth, price clustering, quote freshness, or provenance validation is missing.

### Release

- Bumped the frontend package and lockfile to `0.4.0` for the additive profit-route planner contract and UI.

## 0.3.1 — 2026-08-26

### Fixed

- Rejected boolean, non-finite, zero, and negative execution-depth prices and quantities before ladder arithmetic.
- Kept routes fully theoretical when either executable buy or sell depth is unavailable or stale, with no executable profit or scalable capacity.

## 0.3.0 — 2026-08-26

### Changed

- Corrected the public `ProfitRoute` contract with documented Chaos, ratio, hour, capacity, and `[0, 1]` confidence units. Ambiguous execution/sale and profit-rate fields were replaced by `active_execution_time`, `capital_lock_time`, `elapsed_cycle_time`, `profit_per_active_hour`, and `roi_per_lock_hour`.
- Split route economics into theoretical, exact-depth executable, and journal-actual profit fields. Theoretical routes remain visible while missing or stale executable depth fails closed with zero scalable capacity.
- Corrected finite-outcome executable value to probability-weighted expected liquidation value (`Σ(probability × quantity × executable liquidation value)`), retaining each outcome's probability and liquidation capacity.
- Added cumulative batch-depth evaluation from one batch through each bounded maximum. Market, budget, and recommended capacities now derive from this ladder and stop on missing depth, budget, horizon, or non-positive safe net; first-level averages are never extrapolated.
- Updated allocator adaptation and the Profit Routes UI to consume the clean route contract, show units, and distinguish theoretical, executable, and actual values.

### Release

- Bumped the frontend package and lockfile to `0.3.0` for the observable ProfitRoute API contract change.


## 0.2.0 — 2026-08-25

### Added

- Added a single category contract for exchange and stash market types, shared by the API, collector, and historical market queries.
- Added selectable 24-hour, 72-hour, and 7-day history windows across the dashboard, signals, and Explorer views.
- Added an Explorer SVG price-history chart with time labels and accessible chart semantics.
- Added persisted CFO bankroll and preference inputs, keyboard-expandable position and signal rows, and curated signal details with an expandable raw payload.
- Added retry controls for boot and item-loading failures, a tab-level render-error boundary, Alt+1 through Alt+6 tab navigation, and a local inline favicon.
- Added Windows package-build verification to CI, including executable and checksum checks.

### Changed

- Centralized slug formatting and Divine-to-Chaos resolution; live rates now fall back to the latest stored Currency snapshot when the live feed is unavailable.
- Updated the backend Uvicorn requirement to 0.52.4 and CI checkout actions to v7 as part of release validation.
- Trade-depth collection now uses the shared live/fallback Divine rate and the collector reuses its request client across categories.
- Reused one HTTP client across each flip request and collector cycle instead of opening a client per category or fallback call.
- Flip requests now require a non-empty league and a finite positive budget, and flip responses validate against an explicit API model.
- Normalized nullable or malformed poe.ninja fields before returning flip results, including names, icons, variants, numeric values, and nullable sparkline samples.
- Improved frontend error messaging and retry behavior, preserving the paper-portfolio link across transient failures and clearing it only when the server reports not found.
