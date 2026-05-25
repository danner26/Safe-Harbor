#!/usr/bin/env bash
set -euo pipefail

# If the first arg is "gunicorn" (web service) or "rq" (worker), run db upgrade first.
case "${1:-}" in
  gunicorn|rq)
    echo "[entrypoint] checking migration state"
    db_current_err="$(mktemp)"
    db_heads_err="$(mktemp)"
    cleanup_probe_stderr() {
      rm -f "$db_current_err" "$db_heads_err"
    }
    trap cleanup_probe_stderr EXIT

    if ! db_current_out="$(flask --app safeharbor.wsgi:app db current 2>"$db_current_err")"; then
      echo "[entrypoint] 'flask db current' failed:" >&2
      cat "$db_current_err" >&2
      exit 1
    fi
    current_revision="$(printf '%s\n' "$db_current_out" | awk 'NF{ rev=$1 } END{ print rev }')"

    if ! db_heads_out="$(flask --app safeharbor.wsgi:app db heads 2>"$db_heads_err")"; then
      echo "[entrypoint] 'flask db heads' failed:" >&2
      cat "$db_heads_err" >&2
      exit 1
    fi
    heads_revision="$(printf '%s\n' "$db_heads_out" | awk 'NF{ rev=$1 } END{ print rev }')"
    if [[ -n "$current_revision" && -n "$heads_revision" && "$current_revision" != "$heads_revision" ]]; then
      echo "[entrypoint] pending migrations detected; creating pre-upgrade backup"
      flask --app safeharbor.wsgi:app safeharbor backup --output "/backups/pre-upgrade-$(date +%Y%m%d-%H%M%S).tar" || {
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
