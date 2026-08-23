# DeusCFO Public Release and Donation Readiness Audit

## Executive summary

DeusCFO is technically substantial and worth releasing, but it should **not be made public in its current state**. The codebase has a polished interface, conservative evidence handling, a real test suite, CI, and a permissive open-source license. The main obstacles are:

1. A small set of trade-site endpoints needs separate documentation or confirmation; the core Currency Exchange collector is officially documented and is not a concern.
2. A permissive localhost CORS configuration that allows arbitrary websites to call read/write API routes.
3. Known advisories in the pinned Python dependency chain.
4. Installation and first-run friction that will prevent most PoE players from reaching a useful result.
5. Narrow production strategy coverage relative to the prominent CFO/Profit Routes promise.
6. Missing public-release documentation, screenshots, packaging, and privacy decisions.

**Donation assessment:** publishing the repository and adding a Ko-fi link alone will probably produce no donations. Occasional small donations become plausible after DeusCFO has a one-click installation, immediate visible value, several useful production strategies, public evidence of usefulness, and a small base of repeat users.

## Implementation status (2026-08-23)

A focused release-readiness pass has implemented the locally actionable items while preserving this document's historical findings below as the baseline.

### Resolved or materially addressed

- The API remains loopback-only, allowed origins are explicit, and state-changing/expensive operations use a per-process local mutation token.
- FastAPI/Starlette are pinned to the reviewed combination; the current `pip-audit` gate is clean.
- UI and collector use one persisted `deuscfo.config.json` league, with visible migration when a configured league is unavailable; the collector no longer relies on a hardcoded `Allflame` default in normal operation.
- Packaged mode serves the built SPA from FastAPI, while Vite remains an explicit development command. The Windows build path packages the service and emits SHA-256 checksums.
- First-run guidance now includes data readiness, honest missing-history/`WAIT` explanations, and bounded Currency Exchange backfill progress.
- Production coverage is truthfully narrowed to the verified Doctor → Headhunter route; unsupported families remain explicit.
- Frontend lint/test scripts and CI/release gates are configured. Current verification reports 139 backend tests passing, Ruff passing, `pip-audit` passing, frontend lint/test/build passing, and `npm audit --audit-level=high` reporting 0 vulnerabilities.
- Public README, contribution, security, changelog, privacy, provenance, issue/PR, release-note, and design-history organization were added. The unprovenanced checked-in raw trade metadata snapshot was removed from the public release path.

### Remaining external or manual release work

- The repository remains private/unpublished and has no public tag release yet.
- Artifacts are checksummed but unsigned; clean-Windows, upgrade, and uninstall verification remain incomplete.
- GGG guidance for optional donations remains pending, and production strategy coverage is intentionally narrow.


---

## Verified strengths

The following checks were performed against the current local worktree:

- **126 backend tests passed** under Python 3.12.
- The frontend production build passed.
- `npm audit --omit=dev` reported **0 vulnerabilities**.
- GitHub Actions CI is present and recent runs on the committed branch were successful.
- An MIT license is present.
- Runtime databases, generated output, dependencies, `.env` files, raw captures, and local process state are ignored by Git.
- Secret scanning found no obvious committed credentials.
- The project contains roughly **12,000 lines of functional code**, excluding the large body of design documentation.
- The interface is visually polished and internally coherent.
- The backend deliberately distinguishes theoretical, non-executable, insufficient-evidence, and executable opportunities.
- Trading remains decision support/paper tracking rather than automated game interaction.
- The backend is conservative about provenance, confidence, depth, liquidity, and unsupported transformations.

These are meaningful trust signals. DeusCFO is already more substantial than a typical hobby dashboard.

---

# P0 — Public-release blockers

## 1. Keep the official Currency Exchange API; verify the separate trade-site endpoints

### Verified official API

`backend/cx_collector.py` uses:

```text
https://web.poecdn.com/api/currency-exchange[/<realm>][/<id>]
```

This endpoint is explicitly listed in GGG's official API Reference under **Currency Exchange → Public API → Get Exchange Markets**. The official changelog also states that the Currency Exchange endpoint is publicly available through the CDN API. **No removal or replacement is required for this collector.**

Official reference: <https://www.pathofexile.com/developer/docs/reference>

### Separate endpoints to verify

- `backend/collector.py:230-257` calls:
  - `/api/trade/search/{league}`
  - `/api/trade/fetch/{ids}`
- `backend/cx_metadata.py:23,103-120` calls:
  - `/api/trade/data/static`
- `README.md:70` describes the search/fetch path as a public trade API.
- The ignored internal research correctly notes the problem in:
  - `backend/api_research/official_api_findings.md:206-208`
  - `backend/api_research/official_api_findings.md:553-559`

I checked the current official API Reference directly: it documents the Currency Exchange CDN endpoint, but it does **not** list `/api/trade/search`, `/api/trade/fetch`, or `/api/trade/data/static`. GGG's developer policy says it can only support resources in the API Reference or Data Exports. Therefore, the audit concern applies only to these three trade-site endpoints—not to the official Currency Exchange API.

### Required action

No action is required for `web.poecdn.com/api/currency-exchange`. For the three separate trade-site endpoints, choose one of the following before publication:

- Add the official GGG documentation that authorizes them, if such documentation exists elsewhere.
- Obtain explicit written guidance/permission from GGG.
- Otherwise remove or replace them with supported APIs, data exports, or curated local metadata.

This distinction matters: DeusCFO's main historical Currency Exchange work is based on an explicitly documented public API. Only the optional trade-site search/fetch and metadata paths remain unresolved.

### Additional data-provenance question

`backend/api_research/trade_data_static.json` is a checked-in snapshot of a GGG endpoint and is consumed as a fallback by `backend/cx_metadata.py:124-143`. Before publication, document its capture date, source, and redistribution basis, or replace it with a clearly permitted data source.

### Acceptance criteria

- [x] The core Currency Exchange collector is confirmed against GGG's official public API reference.
- [ ] The separate trade search/fetch/static endpoints have an official documentation link, written permission, or are removed/replaced.
- [ ] The README accurately distinguishes official/documented APIs, poe.ninja data, and any manually curated data.
- [ ] Checked-in third-party data has source and licensing/provenance notes.
- [ ] GGG guidance is recorded in the repository if permission is obtained.

---

## 2. Lock down the localhost API and CORS

### Current behavior

`backend/main.py:31-36` currently allows every origin, method, and header:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

The service correctly binds to `127.0.0.1`, but loopback binding alone does not prevent JavaScript on a malicious website from contacting a local service when that service explicitly permits cross-origin requests.

Relevant unauthenticated endpoints include:

- Snapshot collection: `backend/main.py:302`
- Paper portfolios and trade mutations: `backend/main.py:591-751`
- Currency Exchange backfill: `backend/main.py:1141-1150`
- Journals and local analytical data reads

### Risk

While DeusCFO is running, an unrelated website opened in the same browser could potentially read local records or trigger mutations and expensive collection operations.

### Required action

- Restrict allowed origins to the actual local frontend origin(s).
- Validate `Origin`/`Host` on state-changing routes.
- Add CSRF protection or a random per-launch local session token.
- Protect expensive operations such as backfill and manual collection.
- Keep production services bound to loopback by default.
- Avoid running the Vite development server in the packaged release.

### Acceptance criteria

- [ ] Requests from an unrelated origin cannot read the local API.
- [ ] Requests from an unrelated origin cannot mutate local state.
- [ ] The packaged frontend can communicate with the backend.
- [ ] Backfill and collection endpoints require an approved local session.
- [ ] Automated tests cover allowed and denied origins.

---

## 3. Upgrade the Python dependency chain

`backend/requirements.txt` pins `fastapi==0.115.0`, which currently resolves to `starlette==0.38.6`.

The audit command reported **nine findings across seven unique 2026 advisories** affecting that Starlette version:

```powershell
uvx pip-audit -r backend\requirements.txt
```

### Required action

- Upgrade FastAPI/Starlette to a supported safe combination.
- Review all behavior changes and migration notes.
- Rerun the complete backend suite.
- Add dependency auditing to CI so this does not silently regress.

### Acceptance criteria

- [ ] `uvx pip-audit -r backend/requirements.txt` has no unresolved high-impact findings, or documented exceptions exist.
- [ ] All backend tests pass after the upgrade.
- [ ] The application starts and all primary UI/API workflows still function.
- [ ] Dependency auditing runs in CI.

---

## 4. Prepare the actual snapshot that will become public

At audit time, GitHub reported the repository as **private**, with no homepage, stars, or forks. The local worktree had **13 modified and 2 untracked files**, including the untracked `frontend/src/components/OracleLens.jsx`, which is imported by `frontend/src/App.jsx`.

Making the existing remote public without committing the current work would expose an older product than the one reviewed.

Several existing commits also expose a personal email address in Git author metadata.

### Required action

- Commit or intentionally discard every current worktree change.
- Rerun verification on the exact commit intended for publication.
- Decide whether the existing commit email may be public.
- If not, configure a GitHub no-reply address and rewrite history before publication.
- Tag the first public release candidate.

### Acceptance criteria

- [ ] The worktree is clean.
- [ ] CI passes on the exact release commit.
- [ ] The public repository contains the inspected UI and features.
- [ ] Author-email exposure is an explicit decision.
- [ ] A release tag and release notes exist.

---

# P1 — Highest-value product improvements

## 5. Ship a one-click Windows release

The current README asks users to install Python 3.12, Node.js 20, a virtual environment, Python dependencies, npm dependencies, and three development processes. `deuscfo.py` launches Vite's development server.

This is acceptable for contributors but too much friction for most PoE players.

### Target experience

1. Download a signed or checksummed ZIP/installer.
2. Start `DeusCFO.exe` or one launcher.
3. The backend and collector start locally.
4. The browser opens automatically.
5. No separate Python or Node installation is required.
6. The user can stop/uninstall cleanly.

### Possible implementation direction

- Build the frontend once and serve its static production output from FastAPI.
- Package the Python service and assets with PyInstaller, Nuitka, or another tested Windows packager.
- Include a controlled launcher, logs, status view, and clean shutdown.
- Publish SHA-256 checksums with each GitHub release.

### Acceptance criteria

- [ ] A clean Windows machine can run DeusCFO without installing Python or Node.
- [ ] The release does not start a development server.
- [ ] Startup, shutdown, logs, and update behavior are documented.
- [ ] A release artifact and checksum are attached to GitHub Releases.

---

## 6. Fix the empty first-run experience

### Current behavior

- A fresh installation has no local SQLite history because runtime databases are correctly ignored.
- The normal collector calls `poll_latest_cx()` but does not automatically run the available historical backfill.
- Historical backfill exists at `backend/main.py:1141-1150` but is not exposed in the frontend or documented in the README.
- Several analytical views require accumulated history and sufficient evidence.

The audited local database had substantial history, but the current state still returned:

- 0 current signals
- 0 eligible opportunities
- 1 theoretical profit route
- Historical coverage records
- More than 100 journal entries

This is honest fail-closed behavior, but a new user may interpret it as a broken application.

### Required action

Provide one or more of:

- A guided first-run backfill.
- A data-readiness screen showing coverage and estimated readiness.
- A small clearly labeled demo/sample dataset.
- Explicit explanations of what works immediately and what needs history.
- Clear messaging that `WAIT` or no signal can be a valid result.

### Acceptance criteria

- [ ] A new user sees useful guidance rather than unexplained empty panels.
- [ ] Backfill/collection progress is visible.
- [ ] The UI shows why a signal or route is unavailable.
- [ ] Demo data cannot be confused with live market evidence.
- [ ] The README documents first-run timelines and data sources.

---

## 7. Remove hardcoded league drift

The collector defaults to `Allflame` in `backend/collector.py:462-467`, while the UI dynamically selects the first live league in `frontend/src/App.jsx:27-32`.

After a league transition, the collector and UI may silently use different leagues.

### Required action

- Persist one selected league in a shared configuration source.
- Let the UI and collector read the same value.
- Detect expired/unknown leagues and ask the user to migrate.
- Add a test covering a simulated league transition.

### Acceptance criteria

- [ ] UI, collector, database, and strategy evaluation use the same configured league.
- [ ] League changes are visible and intentional.
- [ ] An expired league does not silently continue collecting while the UI displays another league.

---

## 8. Align the product promise with production coverage

Current production route coverage is narrow:

- `backend/div_card_recipes.json` contains Doctor → Headhunter.
- `backend/transformations.experimental.json` contains a rejected fixture rather than an accepted production strategy.
- The README states that assembly, vendor, graph, and six-link registries have no production records.

The prominent CFO and Profit Routes surfaces can therefore look more comprehensive than the available production strategy set.

### Options

**Option A — Broaden coverage**

Add several well-verified, genuinely useful strategies with explicit patch metadata, costs, outcomes, market keys, execution limitations, and tests.

**Option B — Narrow the promise**

Position DeusCFO primarily as a historical research terminal, paper portfolio, and evidence-quality dashboard until production route coverage expands.

Do not add weak routes merely to increase the count. The existing conservative behavior is one of the project's strengths.

### Acceptance criteria

- [ ] The README clearly states current production coverage.
- [ ] Prominent UI surfaces do not imply unsupported breadth.
- [ ] Every production strategy has versioned evidence, tests, and explicit limits.
- [ ] Empty results explain whether the cause is market conditions, missing history, or absent strategy coverage.

---

## 9. Rewrite the README around user outcomes

The current README is implementation-heavy and contains no screenshots, GIF, sample output, first-run walkthrough, or demonstrated performance results.

### Recommended opening structure

1. One-sentence value proposition.
2. Screenshot or short GIF.
3. Three concrete use cases.
4. Safety/data caveats.
5. Download link.
6. First-run instructions.
7. Data sources and trust model.
8. Development setup.
9. Detailed strategy coverage and internal contracts.

### Suggested positioning

> **DeusCFO is a local Path of Exile market research terminal that tracks historical prices, tests market signals, and identifies evidence-backed opportunities—without pretending every theoretical profit is executable.**

Potential differentiators:

- Historical validation instead of only current price lookup.
- Paper portfolios and recommendation journals.
- Explicit evidence grades and data coverage.
- Clear separation between theoretical and executable returns.
- A willingness to recommend `WAIT`.

### Acceptance criteria

- [ ] README has at least two current screenshots and one concise walkthrough.
- [ ] The first screen answers what the tool helps a player do tonight.
- [ ] Download/use instructions appear before implementation details.
- [ ] Current strategy coverage and evidence limits are explicit.

---

## 10. Add the required GGG notice and clarify donations

GGG's developer documentation says every public or widely available application should visibly include a notice equivalent to:

> This product isn't affiliated with or endorsed by Grinding Gear Games in any way.

Add this to:

- README
- Application footer or About screen
- Release page/website

GGG's documentation also says, as a general rule, that its intellectual property may not be used to generate commercial revenue. Existing community tools may link to Patreon or other support pages, but that is precedent rather than permission.

### Recommended action

Before relying on Ko-fi, send GGG support a short description:

- Free and open-source local market-research tool
- No automated gameplay or trade execution
- Uses identified public/documented data sources
- Optional donations with no feature gating
- No sale of GGG assets or in-game items

Retain the response with project records.

---

# P2 — Maintainability and public-project hygiene

## 11. Resolve or triage lint findings

The audit's Ruff run reported **61 issues**, with **34 automatically fixable**. Findings included import ordering, modern typing suggestions, unused variables/imports, simplification opportunities, and broad exception handling.

Do not bulk auto-fix blindly. Apply safe fixes, review the remainder, and configure a project-level Ruff policy.

- [ ] Add a Ruff configuration.
- [ ] Fix safe mechanical issues.
- [ ] Document intentional broad exception boundaries.
- [ ] Run Ruff in CI.

## 12. Add frontend tests and linting

Current CI checks that the frontend builds, but there is no configured frontend test or lint command.

Recommended initial coverage:

- League selection and boot errors.
- First-run/no-data states.
- Profit-route status rendering.
- Paper portfolio mutations.
- API error handling.
- Accessibility checks for navigation/forms.

## 13. Reduce concentrated modules

Large modules currently include:

- `backend/strategies.py` — approximately 1,493 lines
- `backend/main.py` — approximately 1,237 lines
- `backend/portfolio.py` — approximately 819 lines
- `backend/database.py` — approximately 778 lines

Suggested direction:

- Split FastAPI routes by domain.
- Separate database schema/migrations/repositories.
- Separate strategy registry parsing, evaluation, and provider families.
- Keep refactors test-preserving and incremental.

## 14. Review the Three.js bundle cost

The Oracle lens produces an approximately **825 KB minified chunk** and triggers Vite's chunk-size warning.

Options:

- Keep it lazy-loaded and accept the cost.
- Replace it with a CSS/SVG effect.
- Load it only after the main application is interactive.
- Document the intentional bundle exception.

This is not a release blocker, but the effect should justify its dependency weight.

## 15. Organize internal planning documents

More than 5,000 lines of internal planning/design documents currently sit at the repository root. Move them under a clear location such as:

```text
docs/
  architecture/
  design-history/
  data-provenance/
```

Keep the root focused on the public product.

## 16. Add community-health files

Recommended files:

- `CONTRIBUTING.md`
- `SECURITY.md`
- `CHANGELOG.md`
- Issue templates
- Pull-request template
- Support/donation section
- Privacy and local-data explanation
- Data-source/provenance document

---

# Suggested delegation order

## Workstream A — Security and policy

1. Keep the documented Currency Exchange CDN collector; document, obtain permission for, or replace only the separate trade search/fetch/static endpoints.
2. Restrict CORS and protect local mutation routes.
3. Add GGG non-affiliation notice.
4. Resolve third-party data provenance.
5. Contact GGG about optional donations.

**Merge first.** Other public-release work should build on this result.

## Workstream B — Dependency and quality gates

1. Upgrade FastAPI/Starlette.
2. Run backend tests.
3. Triage Ruff findings.
4. Add Python dependency audit and lint to CI.
5. Add initial frontend lint/tests.

## Workstream C — First-run experience

1. Shared league configuration.
2. Guided Currency Exchange backfill.
3. Coverage/readiness UI.
4. Demo/sample mode if appropriate.
5. Clear explanations for `WAIT`, missing history, and absent strategy coverage.

## Workstream D — Packaging

1. Serve the production frontend from the backend.
2. Remove the Vite development server from normal use.
3. Package a Windows release.
4. Add logs/status/clean shutdown.
5. Test on a clean machine.
6. Publish checksum and release notes.

## Workstream E — Public presentation

1. Rewrite README opening.
2. Add screenshots/GIF.
3. Move planning documents under `docs/`.
4. Add community-health files.
5. Create public-beta release notes.
6. Add Ko-fi only after policy clarification.

## Workstream F — Product coverage

1. Select several high-value strategy families.
2. Add only verified, patch-aware records.
3. Add execution/evidence tests.
4. Publish reproducible backtest or paper-trade demonstrations.
5. Keep unsupported strategies visibly unsupported.

---

# Release verification commands

Run these against the exact commit intended for publication:

```powershell
C:\Python312\python.exe -m pytest backend
npm ci --prefix frontend
npm run build --prefix frontend
npm audit --prefix frontend --omit=dev
uvx pip-audit -r backend\requirements.txt
uvx ruff check backend
```

Additional manual verification:

- [ ] Fresh-install test on a clean Windows environment.
- [ ] First-run test with no existing SQLite database.
- [ ] Backfill and data-readiness test.
- [ ] League-transition test.
- [ ] CORS test from an unrelated origin.
- [ ] Local mutation-route protection test.
- [ ] Offline/failed-upstream behavior test.
- [ ] Upgrade/uninstall test.
- [ ] Git history privacy review.
- [ ] GGG policy/disclaimer review.

---

# Donation strategy after release readiness

A Ko-fi link should be optional and unobtrusive:

- README support section
- About screen or footer
- GitHub repository funding configuration if supported
- Release notes after meaningful milestones

Avoid gating core functionality initially. A better prompt than a generic donation button is:

> If DeusCFO saved you time, helped you avoid a bad trade, or gave you a useful market insight, you can support continued league updates here.

The donation trigger is demonstrated usefulness, not the existence of the button. Publish honest, reproducible examples and evidence limits rather than profit promises.

### Realistic expectation

- Public repository plus Ko-fi only: likely no donations.
- Secure public beta with one-click installation and visible value: occasional small donations become plausible.
- Repeat users and reliable league updates: better chance of covering modest project/API expenses.
- Dependable income: unlikely without a much larger user base or a carefully approved hosted service.

---

# External references

- Path of Exile Developer Docs: <https://www.pathofexile.com/developer/docs/index>
- Path of Exile Terms of Use: <https://www.pathofexile.com/legal/terms-of-use-and-privacy-policy>
- Awakened PoE Trade, an example of a free community tool with a Patreon link: <https://snosme.github.io/awakened-poe-trade/>
- PoE Tools Hub, an example of zero-install competing economy tools: <https://poetools.dev>

---

## Final recommendation

Release DeusCFO as a **public beta after one focused release-readiness pass**. Preserve the project's conservative evidence model. Prioritize security/API compliance, first-run usefulness, and one-click packaging over adding more visual complexity. After users can reach a trustworthy result with little friction, add optional Ko-fi support and promote the tool through honest demonstrations rather than broad profit claims.
