#!/usr/bin/env bash
set -euo pipefail

# If the first arg is "gunicorn" (web service) or "rq" (worker), run db upgrade first.
case "${1:-}" in
  gunicorn|rq)
    echo "[entrypoint] running db upgrade"
    flask --app safeharbor.wsgi:app db upgrade -d migrations || {
      echo "[entrypoint] db upgrade failed; aborting"
      exit 1
    }
    ;;
esac

exec "$@"
