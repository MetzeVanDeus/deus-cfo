# DeusCFO public beta release notes

DeusCFO is a local Path of Exile market research terminal for historical prices, evidence-quality signals, and paper decision support. The beta includes the verified **Doctor → Headhunter** divination-card route; deterministic provider readiness and evidence blockers for other route families are surfaced in Profit Routes.

## Before using it

- Choose and save one live league on first run. The UI and collector share `deuscfo.config.json`.
- Allow the collector to build current snapshots. Currency Exchange backfill is optional and visible in Data readiness.
- Expect `WAIT` when history, liquidity, patch evidence, or production strategy coverage is insufficient.

Profit Routes now accepts Chaos or Divine budgets, exposes fresh conversion-rate provenance, and groups backend-ranked results into actionable, deterministic, card, conversion, bounded-EV, and watch/readiness sections. Filters cover minimum safe profit and ROI, planned active effort, elapsed lock time, family, lifecycle, and deterministic certainty. Route details retain exact quantities, cumulative depth, advisory links, buffers, source timestamps, confidence grades, patch health, and allocator blockers.

Completed manual paper or actual executions calibrate future entry cost, exit proceeds, and elapsed lock time without inferring gameplay. Robust medians are shrunk toward the original estimate; two exact-route records or five independent peer-family records are required, with exact route/version/patch/league evidence preferred on equal strength. Planned active effort remains separate from observed elapsed duration.

## Known limits

The application does not execute gameplay or trades. Assembly, vendor, graph, and six-link providers remain evidence-gated: the Profit Routes view reports whether each family is unsupported, awaiting market data, theoretical-only, or ready, including backend-provided reasons. The Windows packaging script emits a SHA-256 checksum, but artifacts are not code-signed and clean-machine verification is not claimed.

This product isn't affiliated with or endorsed by Grinding Gear Games in any way. Optional donations remain pending GGG guidance and are not part of this beta.
