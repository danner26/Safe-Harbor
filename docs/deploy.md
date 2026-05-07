# Deployment

Safe Harbor runs as a Docker Compose stack: Flask/Gunicorn for the web app, Postgres for durable data, Redis for background-job plumbing, and an optional Cloudflare Tunnel sidecar for HTTPS staging validation.

## Canonical: Cloudflare Tunnel via the `tunnel` compose profile

This is the Phase 2a staging rehearsal path for `staging.safeharbor.danner.dev`. The v1 production cutover uses the same Cloudflare Tunnel topology, but the final production environment wiring and cutover ritual land in Phase 2c.

!!! warning "Phase 2a staging scope"
    The current compose file is still optimized for local development by default. Do not expose it through a public tunnel unless a local staging override sets `FLASK_CONFIG=production` for `web` and any started `worker` service.

1. Create a Cloudflare Tunnel in the Cloudflare Zero Trust dashboard.
2. Add a public hostname that points to `http://web:8000`.
3. Copy the generated tunnel token into `.env`:

   ```dotenv
   TUNNEL_TOKEN=...
   ```

4. Add a local, uncommitted staging override that disables development config for public tunnel validation:

   ```yaml
   # docker-compose.stage.yml
   services:
     web:
       environment:
         FLASK_CONFIG: production
       ports:
         - "127.0.0.1:8000:8000"
     worker:
       environment:
         FLASK_CONFIG: production
   ```

   The loopback-only port binding keeps direct Gunicorn access off the public network while still allowing local smoke tests.

5. Build and start the stack with the tunnel profile and the staging override:

   ```bash
   docker compose -p safeharbor-stage -f docker-compose.yml -f docker-compose.stage.yml --profile tunnel up -d --build
   ```

6. Confirm the containers are healthy:

   ```bash
   docker compose -p safeharbor-stage ps
   ```

7. Confirm `cloudflared` registered the tunnel:

   ```bash
   docker compose -p safeharbor-stage logs cloudflared | grep -i registered
   ```

8. Confirm the public health check responds:

   ```bash
   curl -fsSI https://staging.safeharbor.danner.dev/healthz
   ```

The app listens on plain HTTP port 8000 inside the compose network. Cloudflare terminates TLS at the edge, `cloudflared` forwards to `web:8000`, and Flask trusts exactly one forwarded proxy hop.

## Why this is the default

Cloudflare Tunnel gives the self-hosted install public HTTPS without opening inbound firewall ports. It also works behind consumer NAT and CGNAT, keeps certificate management at Cloudflare, and avoids exposing the Docker host directly.

This topology is:

- client to Cloudflare edge
- Cloudflare edge to `cloudflared`
- `cloudflared` to `web:8000`

That is exactly one proxy hop from the app's point of view.

## Alternative 1: host-daemon `cloudflared`

You can run `cloudflared` directly on the host instead of in Compose. In that model, omit the compose `tunnel` profile and configure the host daemon to forward the public hostname to `http://localhost:8000` or to the compose network address.

Keep the same reverse-proxy contract:

- preserve `X-Forwarded-Proto`
- preserve `X-Forwarded-Host`
- forward client address through `X-Forwarded-For`
- do not rewrite the app under a path prefix

## Alternative 2: Caddy + Let's Encrypt

Caddy is a good fit when the host can receive inbound HTTP and HTTPS traffic. Put Caddy on the host or in Compose, terminate TLS there, and proxy to `web:8000`.

Example Caddy target:

```caddyfile
safeharbor.example.com {
    reverse_proxy web:8000
}
```

This option requires DNS pointing at the host and ports 80/443 reachable from the internet.

## Alternative 3: Tailscale Funnel

Tailscale Funnel can publish a local service through your tailnet identity. It is useful for private or small-audience installs where Tailscale is already part of the operator workflow.

Forward the Funnel endpoint to the app's HTTP port and preserve standard reverse-proxy headers. Treat Funnel as the single trusted proxy hop.

## Discouraged: bare port-forward + self-signed

Avoid exposing Gunicorn directly to the internet. Gunicorn should sit behind a reverse proxy or tunnel that handles TLS, public routing, and edge behavior.

Self-signed certificates also make mobile and shared-device use harder. If you are publishing the app beyond a private LAN, use Cloudflare Tunnel, Caddy, or another managed TLS front door.

## ProxyFix and reverse-proxy headers

Safe Harbor wires Werkzeug `ProxyFix` for one hop:

- `X-Forwarded-For`: one trusted proxy
- `X-Forwarded-Proto`: one trusted proxy
- `X-Forwarded-Host`: one trusted proxy
- `X-Forwarded-Prefix`: not trusted

This lets Flask generate external URLs with the public HTTPS scheme and host while the app still receives plain HTTP from the proxy. Keep the app reachable only through the expected proxy path in production.
