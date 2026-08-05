@~/.codex/AGENTS.md
# Repository Guidelines
project instructions are in `PROJECT_SPEC_Open-R1_CodeVerifier.md`
project proceedings are in `proceedings.md`
## Project Structure & Module Organization

```
open-r1-code-verifier/
├── src/
│   └── code_verifier/
│       ├── __init__.py
│       ├── cli.py                    # CLI entry point (code-verifier)
│       ├── config.py                 # Strict YAML loading
│       ├── environment.py            # Reproducibility metadata collection
│       ├── data/                     # WP1 schema, split, dedup, leakage, export
│       └── training/
│           └── open_r1_adapter.py    # Open-R1 integration boundary
├── tests/
│   ├── integration/
│   │   └── test_wp1_data_pipeline.py
│   └── unit/
│       ├── data/
│       ├── test_cli.py
│       ├── test_config.py
│       ├── test_environment.py
│       └── test_open_r1_adapter.py
├── third_party/
│   └── open-r1/                      # Git submodule (pinned, read-only)
├── .venv/                            # Virtual environment (gitignored)
├── pyproject.toml                    # Project config (ruff, mypy, pytest)
├── Makefile                          # Build/test/lint commands
└── environment.json                  # Recorded environment snapshot
```

Source code lives in `src/code_verifier/`. The `third_party/open-r1/` submodule is **read-only** — all integrations must go through `code_verifier.training.open_r1_adapter`.

## Build, Test, and Development Commands

| Command | Description |
|---------|-------------|
| `make install` | Creates `.venv`, installs project + pinned Open-R1 in editable mode, adds dev tools |
| `make install-full` | Full sync with all Open-R1 training dependencies |
| `make lint` | Runs ruff check, ruff format --check, and mypy on src/ and tests/ |
| `make test` | Runs pytest on unit and integration tests under tests/ |
| `make record-environment` | Records repo/submodule/Python/dependency versions to environment.json |
| `.venv/bin/code-verifier --help` | Shows CLI help |

## Coding Style & Naming Conventions

- **Python version**: 3.10+ (enforced by mypy)
- **Formatter**: Ruff with 119-char line length, double quotes
- **Linter**: Ruff with rules E, F, I, UP, B, SIM, RUF
- **Type checking**: mypy strict mode on `src/` and `tests/`
- **Imports**: Absolute imports from `code_verifier.*` (configured via package-dir in pyproject.toml)

Run `make lint` before committing — it runs all three checks.

## Testing Guidelines

- **Framework**: pytest (configured in pyproject.toml with `-ra` addopts)
- **Test location**: unit tests in `tests/unit/`; end-to-end WP tests in `tests/integration/`
- **Run tests**: `make test` or `.venv/bin/python -m pytest`
- **Coverage**: Not yet configured

## Commit & Pull Request Guidelines

- **Commit messages**: Follow Conventional Commits (e.g., `feat: add environment recording`, `fix: correct submodule pin validation`)
- **Branch naming**: Feature branches from `main` (e.g., `feat/environment-recording`)
- **PR requirements**: 
  - All `make lint` and `make test` checks must pass
  - Link related issues in PR description
  - Keep changes minimal and focused on the stated goal

## Agent-Specific Instructions

- **Never edit `third_party/open-r1/`** — it's a pinned submodule. Use `open_r1_adapter.py` for integrations.
- **Current scope**: WP0 is complete and WP1 Data Layer is implemented. Do not add WP2 parser, WP3 executor, rewards, training, or evaluation without a later WP plan.
- When adding new modules, update `pyproject.toml` `tool.mypy.files` if needed.
