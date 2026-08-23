# Security

DeusCFO is designed to bind its API to loopback and keep market and paper-trading records local. Do not expose the service to a network interface or forward its port.

## Reporting

Please do not publish exploitable details in a public issue. Contact the repository owner through the private security channel configured for the eventual public repository, including the affected version, reproduction steps, and whether data was exposed. Until that channel is configured, use a private maintainer contact rather than posting secrets or private data.

Reports should cover local-origin/CORS bypasses, session-token bypasses, command execution, data leakage, or unsafe packaging behavior. The project does not support automated gameplay or trade execution.

## User safety

Never commit `.env` files, `deuscfo.config.json`, SQLite files, raw API captures, logs, or credentials. Rotate any credential that may have been pasted into an issue or log immediately.
