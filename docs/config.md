# Configuration

Safe Harbor reads configuration from environment variables. Phase 2a introduces the deploy and observability variables below; the full configuration table lands in the public docs sweep.

<!-- 2c: comprehensive env var table -->

## Environment variables (Phase 2a-introduced)

| Name | Required? | Default | Description |
| --- | --- | --- | --- |
| `TUNNEL_TOKEN` | Required when using the `tunnel` compose profile | empty | Cloudflare Tunnel token generated in Cloudflare Zero Trust. Keep this in the local `.env`; do not commit it. |
| `SENTRY_DSN` | No | empty | Enables Sentry error reporting when set. Safe Harbor does not initialize Sentry when this is blank. |
| `SENTRY_TRACES_SAMPLE_RATE` | No | `0.0` | Sentry transaction sampling rate. `0.0` records errors only; set a value from `0.0` to `1.0` to enable performance traces. |
| `LOG_LEVEL` | No | `INFO` | Python application log level. Production logs are JSON-formatted. |

## Notes

`TUNNEL_TOKEN` is only needed for the compose-managed `cloudflared` service. If `cloudflared` runs as a host daemon or you use another reverse proxy, leave it unset.

`SENTRY_DSN` is opt-in. Self-hosted installs can leave it blank and rely on logs plus external uptime checks.
