# Changelog
## Unreleased

### Documentation

- Added a labeled PAPER workflow showcase clip (bankroll → plan → paper portfolio) that uses non-observed values for illustration. Default collection and planning are unchanged.

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
- Preserved native table-row semantics with explicit keyboard-accessible detail toggles for expandable position and signal rows, and labeled flip scores with their `/100` scale.
- Replaced the remote Google Fonts dependency with the local system font stack, removed the lone Explorer emoji, corrected timestamp formatting, and reduced visual noise in dense lists and charts.

### Fixed

- Prevented CX backfill and polling cursors from advancing when league discovery is empty, a wanted league is absent from the returned hour, or no valid wanted-league records can be stored.
- Prevented invalid and non-finite flip budgets from silently returning empty candidate lists.
- Prevented malformed nullable market payloads from failing the explicit flip response contract.
- Kept boot metadata failures independent so one successful request cannot hide another startup error.
- Recovered malformed persisted CFO bankroll and preference settings by discarding invalid local values and using safe defaults.
- Kept selected history-period labels accurate in Explorer statistics and separated missing-field from invalid-budget messages.
- Used a zero Divine-rate fallback when trade-depth rate resolution is unavailable.
- Removed unused capital/opportunity compatibility aliases and kept backend tests runnable from both repository-root and backend working directories.
- Preserved first and final valid price samples and filtered invalid prices before Explorer chart calculations.

### Security

- Documented the process-lifetime loopback session-token threat model: any local process able to access the loopback service can read the token, so untrusted local software must not run alongside DeusCFO.
- Disabled persisted checkout credentials in CI and release jobs; release publishing continues to use its explicit `GH_TOKEN`.

### Quality

- Added backend regression coverage for shared category/type and slug contracts, HTTP client reuse, Divine-rate fallback, FlipRequest and nullable FlipResult contracts, and CX cursor safety.
- Added root-compatible pytest configuration so the backend suite can run from the repository root or backend working directory.

## 0.1.4 — 2026-08-23

- Enabled CodeQL analysis for Python, JavaScript/TypeScript, and GitHub Actions, then resolved all three initial path-handling alerts.
- Routed packaged frontend assets through Starlette's traversal-safe static file handler with regression coverage.
- Removed the internal release-readiness audit from the published source tree.

## 0.1.3 — 2026-08-23

- Added explicit packaged Windows download verification and native Windows/Linux source-run instructions.
- Fixed Linux launcher npm resolution and documented the Debian/Ubuntu virtual-environment prerequisite.

## 0.1.2 — 2026-08-23

- Redesigned the terminal visual layer with a brass-led command spine, regime rail, signal choreography, and a reduced-motion-aware Three.js oracle lens.
- Defaulted CFO planning to safe PAPER mode and added low-confidence Currency Exchange mean-reversion watches from direct hourly quotes.
- Kept exploratory paper ideas separate from validated capital positions, with explicit data freshness, liquidity, and evidence warnings.

## 0.1.1 — 2026-08-23

- Added loopback production serving and an explicit Vite development launcher.
- Added shared local league configuration and migration guidance in the UI.
- Added local session-token consumption for state-changing frontend requests.
- Added data-readiness and Currency Exchange backfill guidance.
- Documented conservative Doctor → Headhunter-only production route coverage.
- Added Windows packaging script and SHA-256 artifact generation path.
- Added provenance, privacy, contribution, security, issue, and release documentation.
