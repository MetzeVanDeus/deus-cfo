# Privacy and local data

DeusCFO runs as a loopback application. Market snapshots, Currency Exchange history, coverage calculations, journals, and paper portfolios are stored in the local SQLite database under `backend/` and are not uploaded by DeusCFO to a project server.

The collector contacts the documented Currency Exchange CDN and poe.ninja, and optional trade-site collection uses the supported `/api/trade/search`, `/api/trade/fetch`, and `/api/trade/data/static` paths. Requests retain bounded rate limits and a configured User-Agent. Upstream services receive normal request metadata such as IP address and User-Agent; consult their policies separately.

The local database may contain free-form journal text and paper-trade notes. Keep the loopback port private, do not share logs or database files without review, and remove local runtime files before distributing diagnostics. The per-process session token protects state-changing local requests; it is not an account credential.
