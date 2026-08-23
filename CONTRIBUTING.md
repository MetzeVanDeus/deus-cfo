# Contributing

DeusCFO is a local, evidence-first Path of Exile research terminal. Contributions should preserve fail-closed behavior: a missing quote, unsupported league, or unverified strategy must remain visible rather than becoming an invented opportunity.

## Development

1. Install Python 3.12+, Node.js 20+, and the dependencies described in `README.md`.
2. Run the explicit development launcher with `python deuscfo.py dev`, or start the API and Vite separately.
3. Keep runtime databases, captures, local config, and frontend build output out of commits.

Before opening a pull request, run the focused tests for the area changed and the existing frontend checks. Do not include real account credentials, private-league data, or raw captures containing personal information.

## Data and strategies

Every new production strategy needs patch/version metadata, source provenance, bounded assumptions, evidence thresholds, and tests. Do not add speculative strategy records to make an empty surface look populated. Trade-site requests must retain rate limits, an identifying User-Agent, and the existing supported endpoint paths.

## Pull requests

Explain the user-visible outcome, data sources touched, and verification performed. Screenshots are welcome for UI changes, but do not fabricate market results or performance claims.
