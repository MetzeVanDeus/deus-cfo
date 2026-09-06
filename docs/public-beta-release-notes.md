# DeusCFO public beta release notes

DeusCFO is a local Path of Exile market research terminal for historical prices, evidence-quality signals, and paper decision support. The beta includes the verified **Doctor → Headhunter** divination-card route; deterministic provider readiness and evidence blockers for other route families are surfaced in Profit Routes.

## Before using it

- Choose and save one live league on first run. The UI and collector share `deuscfo.config.json`.
- Allow the collector to build current snapshots. Currency Exchange backfill is optional and visible in Data readiness.
- Expect `WAIT` when history, liquidity, patch evidence, or production strategy coverage is insufficient.

Profit Routes now supports a manual minimum safe profit per evaluated batch and a conservative execution-bias percentage. Route details separate certainty, pricing, liquidity, and historical confidence, and trace each market leg to its source, timestamps, freshness policy, and blocker. Stale quotes remain visible as evidence but cannot create executable capacity.

## Known limits

The application does not execute gameplay or trades. Assembly, vendor, graph, and six-link providers remain evidence-gated: the Profit Routes view reports whether each family is unsupported, awaiting market data, theoretical-only, or ready, including backend-provided reasons. The Windows packaging script emits a SHA-256 checksum, but artifacts are not code-signed and clean-machine verification is not claimed.

This product isn't affiliated with or endorsed by Grinding Gear Games in any way. Optional donations remain pending GGG guidance and are not part of this beta.
