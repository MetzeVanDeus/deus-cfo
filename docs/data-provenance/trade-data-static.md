# Trade metadata snapshot provenance

The public Windows package intentionally does **not** bundle a checked-in `trade_data_static.json` snapshot. This avoids redistributing an offline capture whose precise capture date and separate GGG redistribution basis are not recorded.

Trade metadata uses the supported trade-site endpoint `https://www.pathofexile.com/api/trade/data/static` when available. Project-owner confirmation supports that endpoint for DeusCFO's local collector, but it is not listed as an official GGG Developer API endpoint. Requests retain the existing bounded behavior and identifying User-Agent.

Any future offline snapshot must record its capture time, source URL, integrity, and redistribution guidance before it is checked in or packaged. Until then, a missing upstream response is surfaced as unavailable metadata rather than silently falling back to an unprovenanced file.
