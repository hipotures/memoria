# Repository Guidelines

## Project Structure & Module Organization

Core code lives in `src/memoria/`. Main subsystems are split by responsibility: `api/` for FastAPI entrypoints, `ingest/` for canonical ingest, `ocr/` and `vision/` for processing stages, `knowledge/` for durable claims, `projections/` for read models, `assistant/` for retrieval and answers, and `storage/` for SQLite/blob helpers. Database migrations live in `alembic/versions/`. Tests are under `tests/unit/` and `tests/integration/`. Design docs and plans live in `docs/` and `docs/superpowers/`.

## Build, Test, and Development Commands

- `uv run pytest -v`: run the full test suite.
- `uv run pytest tests/integration/test_screenshot_read_api.py -v`: run one integration slice.
- `uv run alembic upgrade head`: apply the latest schema to the configured SQLite database.
- `uv run python -c "from memoria.api.app import create_app; ..."`: use for quick local sanity checks when needed.

Use `uv` for all local Python commands so the repo uses the managed environment and pinned dependency resolution.

## Coding Style & Naming Conventions

Use 4-space indentation and follow existing Python style in the repo. Modules and packages use `snake_case`; classes use `PascalCase`; functions, variables, and test names use `snake_case`. Keep responsibilities narrow: prefer small service modules over large mixed files. Preserve the architectural split between canonical state, knowledge, and projections. Do not expose raw filesystem paths in public API payloads.

## Testing Guidelines

Pytest is the test framework. Add unit tests for pure logic and integration tests for DB/API flows. Name tests `test_<behavior>.py` and test functions `test_<expected_behavior>()`. For feature work, cover both happy path and partial-state or failure cases. Run targeted tests first, then finish with `uv run pytest -v`.

## Commit & Pull Request Guidelines

Follow the commit style already used in history: short, imperative prefixes such as `feat:`, `fix:`, `docs:`, `api:`, `vision:`, `gitignore:`. Keep each commit scoped to one logical change. PRs should include a concise summary, the user-visible or architectural impact, and the exact verification commands run. Include example payloads or screenshots only when API/UI behavior changed materially.

## Security & Configuration Tips

Never commit local runtime data. `data/`, `var/`, `.worktrees/`, and local SQLite files are ignored and should stay that way. Keep secrets in `.env`, not in source. Treat blobs and screenshots as sensitive user data; preserve provenance, but do not surface storage internals through the API.
