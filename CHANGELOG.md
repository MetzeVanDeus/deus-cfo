# Changelog
## Unreleased

### Changed

- Collapsed Shared market context after a live league is saved and limited History window to Dashboard, Signals, and Explorer.
- Replaced the Strategies one-option Horizon dropdown with static 24 hours copy and limited Profit Routes categories to registered divination-card families.
- Softened Profit Routes eyebrow copy and treated patch-blocked states as warnings.
- Surfaced WAIT on Data readiness until 24 snapshot hours exist, and replaced sparse Explorer charts with an empty WAIT state.

### Fixed

- Enabled SAVE LEAGUE from a live draft on first run and league migration instead of gating it on the already-saved league.
- Stopped Dashboard and Signals from spinning when no league is saved, and disabled Find Flips until a league exists.
- Interpolated the Dashboard history-window metric label and rendered Profit Routes API errors with retry.
- Removed the doubled Explorer price-change sign and stopped painting the topbar status dot as healthy when no league is configured.

## 0.5.0 — 2026-08-29

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
- Allowed deterministic unique rewards without buyer bids to use a conservative haircut sell-listing floor for manual batch planning; buyer-side executable depth and sell-listing evidence remain explicitly distinguishable in route outputs, batch plans, reasons, and verification metadata.

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
