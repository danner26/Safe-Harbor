#!/usr/bin/env bash
set -euo pipefail

# If the first arg is "gunicorn" (web service) or "rq" (worker), run db upgrade first.
case "${1:-}" in
  gunicorn|rq)
    echo "[entrypoint] checking migration state"
    current_revision="$(
      flask --app safeharbor.wsgi:app db current 2>/dev/null \
        | awk 'NF{ rev=$1 } END{ print rev }'
    )"
    heads_revision="$(
      flask --app safeharbor.wsgi:app db heads 2>/dev/null \
        | awk 'NF{ rev=$1 } END{ print rev }'
    )"
    if [[ -n "$current_revision" && -n "$heads_revision" && "$current_revision" != "$heads_revision" ]]; then
      echo "[entrypoint] pending migrations detected; creating pre-upgrade backup"
      flask --app safeharbor.wsgi:app safeharbor backup --output "/backups/pre-upgrade-$(date +%Y%m%d-%H%M%S).tar.gz" || {
        echo "[entrypoint] pre-upgrade backup failed; continuing"
        true
      }
    fi

    echo "[entrypoint] running db upgrade"
    flask --app safeharbor.wsgi:app db upgrade -d migrations || {
      echo "[entrypoint] db upgrade failed; aborting"
      exit 1
    }
    flask --app safeharbor.wsgi:app safeharbor seed || {
      echo "[entrypoint] seed failed; continuing"
      true
    }
    ;;
esac

exec "$@"
