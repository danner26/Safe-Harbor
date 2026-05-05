# AGENTS.md — Safe Harbor

Safe Harbor is a self-hosted Flask app for aquarium hobbyists: track tanks, livestock, and water-quality readings; chart trends; log readings tank-side via mobile.

## Quickstart

```bash
git clone https://github.com/danner26/Safe-Harbor.git
cd Safe-Harbor
uv sync --extra dev
pre-commit install
pytest -q tests/unit
```

## Docker stack

```bash
docker compose up -d --build web
# http://localhost:8000
docker compose down -v
```

## Tests

- **Unit:** `pytest -q tests/unit`
- **Integration** (Postgres-required, runs in container):

  ```bash
  docker compose exec -T web bash -c \
    "DATABASE_URL='postgresql+psycopg://safeharbor:safeharbor@postgres:5432/safeharbor_test' \
     TEST_DATABASE_URL='postgresql+psycopg://safeharbor:safeharbor@postgres:5432/safeharbor_test' \
     FLASK_CONFIG=testing /app/.venv/bin/pytest tests/integration -q"
  ```

- **Visual** (Playwright, needs a live app on :8000):

  ```bash
  pytest -q tests/visual/test_visual.py
  ```

## Lint and types

```bash
ruff check .
ruff format --check .
mypy src/safeharbor
```

Pre-commit runs ruff + ruff-format + a per-file mypy + EOF/whitespace fixes.

## Conventions

- Models live under `src/safeharbor/models/`. Each model imports `Base, TimestampMixin, new_id` from `models/base.py`. UUIDs always come from `new_id()`.
- Service-layer functions (`services/*.py`) flush but do not commit. The view (or CLI command) commits.
- Login-required is the default; opt out with `@public` from `blueprints/auth/decorators.py`.
- Decimal arithmetic uses `Decimal`, never `float`. Storage is `Numeric(12, 4)`; display is 2 decimals.

## Contributing

Open an issue or PR. Run the full test suite + lint + types before submitting. CI runs the same checks.
