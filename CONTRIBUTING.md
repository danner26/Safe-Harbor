# Contributing to Safe Harbor
Thank you for helping improve Safe Harbor.

Safe Harbor is a self-hosted Flask app for aquarium hobbyists who track tanks,
livestock, and water-quality readings. This guide covers bug reports, feature
proposals, and pull requests.

## Ways to Contribute
You can help by:
- Reporting bugs with clear reproduction steps.
- Proposing features or workflow improvements.
- Improving documentation.
- Opening pull requests for agreed changes.
- Adding or improving tests.

For non-trivial work, open an issue first. Use the issue to describe the
problem, expected behavior, constraints, and proposed approach before writing a
pull request.

Bug reports should include what you expected, what happened instead, steps to
reproduce the problem, and any useful logs, screenshots, or environment details.

Feature proposals should describe the user problem, the proposed behavior, any
alternatives you considered, and compatibility or migration concerns.

## Development Setup
Safe Harbor uses Python 3.12.

Install development dependencies with:
```bash
uv sync --extra dev
```

Docker is used for the local application stack. Install Docker before running
the full app locally.

## Running the Development Stack
Create a local environment file before starting the stack. Docker Compose reads
values from `.env`, so review the copied values for your machine.
```bash
cp .env.example .env
```
Start the local development stack with:
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Stop the stack with `Ctrl-C` when you are done.

## Tests
Tests live in these directories:
- `tests/unit` for fast unit tests.
- `tests/integration` for database-backed integration tests.
- `tests/visual` for browser-based visual checks.

Run unit tests with:
```bash
uv run pytest -q tests/unit
```

Run integration tests after the Docker services are available:
```bash
uv run pytest -q tests/integration
```

Run visual tests when the app is available locally and Playwright Chromium is
installed:
```bash
uv run playwright install chromium
uv run pytest -q tests/visual
```

## Code Style
Before opening a pull request, run:
```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src/safeharbor
uv run pytest -q tests/unit
```

Use conventional commits style for commit messages, such as `fix: correct tank
reading validation` or `docs: clarify local setup`.

Keep changes focused. Small pull requests are easier to review and safer to
merge.

## Pull Request Process
For non-trivial changes, open an issue before starting the pull request.

Create your branch from `develop`, not from `master`.

Open pull requests against `develop`.

In the pull request description, include the issue or problem being addressed, a
short summary of the change, the tests and checks you ran, and any known
limitations or follow-up work.

Maintainers may ask for changes before merging. Keep discussion focused on
user-facing behavior, maintainability, and test coverage.
