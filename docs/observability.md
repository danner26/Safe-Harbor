# Observability

Safe Harbor's v1 observability is intentionally small: structured logs by default, optional Sentry for error reporting, and bring-your-own uptime monitoring against `/healthz`.

## Logs (default)

In production, Python application logs are JSON-formatted. Gunicorn access logs are also emitted as one JSON object per request.

Example access log:

```json
{"time":"2026-05-06T20:30:00+00:00","level":"INFO","logger":"gunicorn.access","method":"GET","path":"/healthz","status":"200 OK","request_id":"-","remote_addr":"172.18.0.1","user_agent":"curl/8.0.0","referer":"-","duration_ms":3}
```

Ship container logs to whatever backend fits your host:

- `journald` on a single Linux host
- Loki or Grafana Cloud for lightweight centralized logs
- Datadog or another hosted log platform if you already use one

Tokenized auth URLs are redacted from Gunicorn access-log path and referer fields before JSON is emitted.

## Sentry (opt-in)

Set `SENTRY_DSN` to enable Sentry error reporting:

```dotenv
SENTRY_DSN=https://public@example.com/1
```

Safe Harbor initializes Sentry only when the DSN is non-empty. By default it sends errors only:

```dotenv
SENTRY_TRACES_SAMPLE_RATE=0.0
```

Operators can raise `SENTRY_TRACES_SAMPLE_RATE` to sample transactions. `send_default_pii` is disabled, so Sentry should not receive default personally-identifying request data from the SDK.

The Sentry environment comes from the resolved Flask config name, such as `development`, `testing`, or `production`.

## Uptime monitoring (BYO)

Point an external monitor at:

```text
https://<your-public-hostname>/healthz
```

Good options include UptimeRobot, Better Stack, healthchecks.io, or an existing monitoring platform. The endpoint is public and returns a lightweight health response without requiring login.
