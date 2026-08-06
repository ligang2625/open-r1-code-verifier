@~/.codex/AGENTS.md
# Repository Guidelines
project instructions are in `PROJECT_SPEC_Open-R1_CodeVerifier.md`
project proceedings are in `proceedings.md`
use `uv` to manage virtual environment and python packages
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
│       ├── parsing/
│       │   └── code_extractor.py     # WP2 deterministic fenced-code parser
│       ├── execution/
│       │   ├── base.py               # WP3-a contracts, validation, JSON mapping
│       │   ├── mock.py               # WP3-a non-executing FIFO test double
│       │   ├── harness.py            # WP3-b trusted in-sandbox Python harness
│       │   ├── piston.py             # WP3-b loopback-only single-request executor
│       │   ├── cache.py              # WP3-c versioned private SQLite result cache
│       │   └── batch.py              # WP3-c bounded concurrency and cache policy
│       └── training/
│           └── open_r1_adapter.py    # Open-R1 integration boundary
├── tests/
│   ├── integration/
│   │   ├── test_wp1_data_pipeline.py
│   │   ├── test_wp3a_mock_execution.py
│   │   ├── test_wp3b_piston_execution.py
│   │   └── test_wp3c_batch_execution.py
│   └── unit/
│       ├── data/
│       ├── execution/
│       │   ├── test_base.py
│       │   ├── test_mock.py
│       │   ├── test_harness.py
│       │   ├── test_piston.py
│       │   ├── test_cache.py
│       │   └── test_batch.py
│       ├── parsing/
│       │   └── test_code_extractor.py
│       ├── test_cli.py
│       ├── test_config.py
│       ├── test_environment.py
│       └── test_open_r1_adapter.py
├── configs/
│   └── execution/
│       ├── piston-local.yaml          # WP3-b strict loopback Piston config
│       └── batch-local.yaml           # WP3-c bounded batch/cache config
├── docs/
│   └── piston-local.md                # Local Piston deployment and safety runbook
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
| `make test` | Runs default pytest suite; real Piston tests are skipped without explicit enablement |
| `make test-piston` | Runs the real loopback Piston safety acceptance suite; requires local service/runtime |
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
- **Real sandbox tests**: run `make test-piston` explicitly; any failure or skip blocks WP3 acceptance and merge
- **Coverage**: Not yet configured

## Commit & Pull Request Guidelines

- **Commit messages**: Follow Conventional Commits (e.g., `feat: add environment recording`, `fix: correct submodule pin validation`)
- **Branch naming**: Feature branches from `main` (e.g., `feat/environment-recording`)
- **PR requirements**: 
  - All `make lint` and `make test` checks must pass
  - WP3 execution, batch, or cache changes also require `make test-piston` with 0 failed and 0 skipped
  - Link related issues in PR description
  - Keep changes minimal and focused on the stated goal

## Agent-Specific Instructions

- **Never edit `third_party/open-r1/`** — it's a pinned submodule. Use `open_r1_adapter.py` for integrations.
- **Current scope**: WP0–WP3 are implemented, including execution contracts/mock, loopback Piston, bounded batch concurrency, versioned SQLite caching, and the execution CLI. Do not add WP4 reward/verifier orchestration, training, or evaluation without a later WP plan.
- `MockExecutor` never executes code. Real candidate code may only be sent to the strict local `PistonExecutor`; do not add host `exec`, `eval`, `compile`, or unrestricted subprocess execution paths.
- Preserve the in-sandbox process boundary: the trusted parent alone owns expected values, comparison, and the final marker; the candidate child may receive only the function name and input, and its result must remain an untrusted claimed return value.
- Preserve cache invalidation: any result-affecting executor, harness, comparison, mapping, or stopping-policy change must increment its version constant. Never remove code hash, problem ID, test layer, tests hash, executor version, function name, timeout, or memory from the cache key.
- Training cache remains disabled unless an experiment explicitly opts in and records the resolved policy. Cache files are sensitive artifacts because results may contain bounded stdout/stderr.
- Real Piston tests must be explicitly enabled. Any failed or skipped verdict-tampering, batch/cache, network, user, filesystem, host-isolation, cleanup, PID, timeout, memory, or output probe blocks merge.
- When adding new modules, update `pyproject.toml` `tool.mypy.files` if needed.
