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
│       ├── prompting.py              # Shared visible-only §7.2 code prompt
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
│       ├── verification/
│       │   ├── result_types.py        # WP4-a structured sanitized verifier results
│       │   └── verifier.py            # WP4-a parser-to-executor orchestration
│       ├── rewards/
│       │   ├── common.py              # WP4-b shared reward core and component records
│       │   ├── public_reward.py       # WP4-b visible-tests-only Public wrapper
│       │   └── hidden_reward.py       # WP4-b train-hidden-only Hidden wrapper
│       ├── evaluation/
│       │   ├── generate.py            # WP5-a deterministic prompt/generation backend
│       │   ├── evaluate.py            # WP5-a records, three-layer evaluation, strict resume
│       │   ├── bootstrap.py           # WP5-b deterministic problem-level bootstrap
│       │   └── metrics.py             # WP5-b aggregate metrics and summary artifacts
│       └── training/
│           ├── open_r1_adapter.py    # Open-R1 integration boundary
│           ├── sft_data.py           # WP6-a trajectory validation/dataset mapping
│           └── sft.py                # WP6-a LoRA config/runtime/artifacts
├── tests/
│   ├── integration/
│   │   ├── test_wp1_data_pipeline.py
│   │   ├── test_wp3a_mock_execution.py
│   │   ├── test_wp3b_piston_execution.py
│   │   ├── test_wp3c_batch_execution.py
│   │   ├── test_wp4a_verifier_pipeline.py
│   │   ├── test_wp4b_reward_pipeline.py
│   │   ├── test_wp5a_evaluation_pipeline.py
│   │   ├── test_wp5a_gpu_smoke.py
│   │   ├── test_wp5b_metrics_pipeline.py
│   │   └── test_wp6a_sft_integration.py
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
│       ├── verification/
│       │   ├── test_result_types.py
│       │   └── test_verifier.py
│       ├── rewards/
│       │   ├── test_common.py
│       │   ├── test_public_reward.py
│       │   └── test_hidden_reward.py
│       ├── evaluation/
│       │   ├── test_bootstrap.py
│       │   ├── test_generate.py
│       │   ├── test_metrics.py
│       │   ├── test_evaluate.py
│       │   └── test_runner_resume.py
│       ├── training/
│       │   ├── test_sft_data.py
│       │   └── test_sft.py
│       ├── test_cli.py
│       ├── test_config.py
│       ├── test_environment.py
│       └── test_open_r1_adapter.py
├── configs/
│   ├── execution/
│   │   ├── piston-local.yaml          # WP3-b strict loopback Piston config
│   │   └── batch-local.yaml           # WP3-c bounded batch/cache config
│   ├── eval/
│   │   ├── pass1.yaml                 # WP5-a debug deterministic pass@1 config
│   │   └── base.yaml                  # WP5-b immutable CUDA/FP16 Base config
│   └── sft/
│       ├── debug.yaml                 # WP6-a short 0.5B/fp16 config
│       └── main.yaml                  # WP6-a frozen 1.5B/bf16 LoRA config
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
| `make install-gpu` | `uv sync --extra dev --extra gpu`: installs the current pinned Open-R1/Transformers inference/GPU stack plus the pinned CUDA torch wheel (`torch==2.6.0`, CUDA 12.4, PyTorch cu124 index); required for real WP5 generation and GPU smoke tests |
| `make install-full` | Alias for `make install-gpu` (kept for backward compatibility) |
| `make install-train` | Installs the full pinned training-capable dependency stack (including `peft==0.14.0`); safe and recommended on the GTX 1660 Ti for API/integration development, but it does not authorize real SFT/GRPO training |
| `make lint` | Runs ruff check, ruff format --check, and mypy on src/ and tests/ |
| `make test` | Runs default pytest suite; GPU-required tests auto-run when a CUDA-capable GPU is detected and auto-skip with an explicit reason on CPU-only machines; real Piston tests are skipped without explicit enablement |
| `make test-piston` | Runs the real loopback Piston safety acceptance suite; requires local service/runtime |
| `make test-gpu` | Runs only the CUDA generation smoke tests; auto-skips with an explicit reason on machines without a CUDA-capable GPU |
| `make record-environment` | Records repo/submodule/Python/dependency versions to environment.json |
| `.venv/bin/code-verifier --help` | Shows CLI help |
| `.venv/bin/code-verifier evaluate --help` | Shows deterministic evaluation and aggregation options |
| `.venv/bin/code-verifier train-sft --help` | Shows strict LoRA SFT and resume options |

## Coding Style & Naming Conventions

- **Python version**: 3.10+ (enforced by mypy)
- **Formatter**: Ruff with 119-char line length, double quotes
- **Linter**: Ruff with rules E, F, I, UP, B, SIM, RUF
- **Type checking**: mypy strict mode on `src/` and `tests/`
- **Imports**: Absolute imports from `code_verifier.*` (configured via package-dir in pyproject.toml)

Run `make lint` before committing — it runs all three checks.

## Implementation Design Principles

These rules apply to planning, implementation, refactoring, and review. The current project spec and the current-stage acceptance criteria are the source of truth; do not optimize for hypothetical future requirements.

- **Do not preserve backward compatibility.** When a CLI option, config key, schema, module path, artifact format, or internal API is superseded by the current requirements, update all in-repo callers, tests, configs, and docs in the same change and delete the obsolete path. Do not add compatibility aliases, dual-read/dual-write behavior, legacy fallbacks, migration shims, or deprecated wrappers unless the current stage explicitly requires that exact behavior.
- **Choose the smallest complete implementation.** Prefer the simplest design that fully satisfies the current WP/stage. Do not add speculative registries, plugin systems, strategy layers, configuration switches, generalized factories, or indirection for cases that are not required now. Reuse the existing module boundaries before creating new abstractions.
- **Grow by working end-to-end layers.** Implement the smallest vertical slice that works through the affected pipeline and keeps the repository in a passing, usable state; then add the next capability on top. A stage must not replace a working path with a broader framework whose critical path is incomplete, stubbed, or deferred to a later stage.
- **Keep concerns separated.** Preserve the boundaries in `PROJECT_SPEC_Open-R1_CodeVerifier.md`: Data, Generation, Parsing, Execution, Verification, Reward, Training, Evaluation, and Analysis must not absorb one another's responsibilities. In particular, keep execution behind `CodeExecutor`, Open-R1 integration behind `training/open_r1_adapter.py`, and test-layer/payload secrecy at the existing verification/reward/evaluation boundaries.
- **Prefer established libraries when they reduce total complexity or improve reliability.** Use a well-maintained library for standard functionality when it removes meaningful custom code or failure modes; do not reimplement commodity functionality merely to avoid a dependency.
- **Use existing dependencies before adding code or packages.** Before implementing utility logic or adding a dependency, inspect the capabilities, documentation, types, and pinned version of libraries already present in `pyproject.toml`/the lockfile and, where relevant, the read-only `third_party/open-r1/` API surface. Do not assume an existing dependency lacks a needed capability without checking. Add a new package only when the existing stack cannot meet the current requirement cleanly and the added dependency reduces net complexity.

Reviewers should treat unnecessary compatibility code, speculative abstraction, duplicated dependency functionality, cross-layer responsibility leakage, and partially integrated frameworks as design defects even when tests pass.

## Testing Guidelines

- **Framework**: pytest (configured in pyproject.toml with `-ra` addopts)
- **Test location**: unit tests in `tests/unit/`; end-to-end WP tests in `tests/integration/`
- **Run tests**: `make test` or `.venv/bin/python -m pytest`
- **Real sandbox tests**: run `make test-piston` explicitly; any failure or skip blocks WP3 acceptance and merge
- **GPU tests**: auto-detected — on a CUDA machine `make test` runs the full suite including the GPU smoke tests; on a CPU-only machine GPU-required tests are skipped with an explicit reason and only CPU tests run. `make test-gpu` targets the GPU smoke subset; any failure on the GPU machine blocks GPU acceptance work
- **Coverage**: Not yet configured

## Commit & Pull Request Guidelines

- **Commit messages**: Follow Conventional Commits (e.g., `feat: add environment recording`, `fix: correct submodule pin validation`)
- **Branch naming**: Feature branches from `main` (e.g., `feat/environment-recording`)
- **PR requirements**: 
  - All `make lint` and `make test` checks must pass
  - WP3 execution, batch, or cache changes also require `make test-piston` with 0 failed and 0 skipped
  - Link related issues in PR description
  - Keep changes minimal and focused on the stated goal
  - Enforce the Implementation Design Principles above: reject compatibility shims, speculative abstractions, duplicated library functionality, cross-layer leakage, and incomplete framework-first changes

## Agent-Specific Instructions

- **Never edit `third_party/open-r1/`** — it's a pinned submodule. Use `open_r1_adapter.py` for integrations.
- **Target hardware split**: development, builds, engineering integration tests, Piston acceptance, and small-model GPU smoke run on the GTX 1660 Ti (6GB VRAM) machine; real optimizer-based SFT/GRPO training and final numerical validation run only on a 24GB GPU (e.g. RTX 4090). Never start real training on the 1660 Ti.
- **Development-first lifecycle**: finish all dependency-ready production code and engineering tests that can be completed on the 1660 Ti before scheduling any 24GB training gate. A lower-numbered WP with only deferred real-training/numerical acceptance remaining does not block later development work such as GRPO control-plane or aggregation/analysis tooling.
- **Development completion**: terminal status requires a Development Completion Inventory covering WP0–WP8, not merely the absence of currently dependency-ready work. Each WP must be backed by finalized evidence or the terminal stage itself; `DEV-CLOSEOUT` is allowed only when all nine WP development deliverables are already finalized. The terminal stage also runs the full closeout suite (`make lint`, `make test`, `make test-gpu`, real `make test-piston` with 0 failed/0 skipped, and no production-critical stub/TODO/fake implementation). Only `stage-lifecycle finalize` may write the valid marker: an exact `## Development Complete Record` heading immediately followed by the required YAML `development_complete_record`; prose mentions never unlock validation.
- **Execution preflight / incomplete stages**: every plan must put checkable external prerequisites (Piston, required imports, model cache/CUDA where relevant) in an Execution preflight that runs before the first business modification/commit. If a later blocker still leaves a stage with commits but no completed E0/review, do not manually delete it; use `stage-lifecycle retire_incomplete` to archive the exact history and then replan.
- **Evidence boundary**: fixture/mock/synthetic data may close a development stage when it exercises the real production contracts, error paths, artifact schemas, checkpoint/resume wiring, and aggregation logic. It may never be recorded as a real checkpoint, completed SFT/GRPO run, B/C/D metric, cost result, or final research acceptance.
- **Persistent validation artifacts**: real training/evaluation artifacts must live outside the stage worktree. Validation routing resolves `artifact_root` from `CODE_VERIFIER_ARTIFACT_ROOT` or defaults to the primary repo `outputs/`; executors set that environment variable for real commands. Never store the only copy of a real checkpoint under `.worktrees/...` because finalize removes the worktree.
- **One-time 1660 Ti → 4090 handoff / validation lifecycle**: terminal finalize reports the exact `development_complete_commit`; stop on the 1660 Ti, sync that exact `main` commit to the 4090, install the pinned training environment there, and restart with `planner-ex` on the 4090. Validation planning/bootstrap is invalid on a <22 GiB GPU. From that point onward the entire Base A → SFT B → Public/Hidden GRPO C/D → final aggregation/analysis track stays on the 4090. `execution-router` still rechecks the >=22 GiB GPU and persistent artifact root before every validation dispatch.
- WP6-a SFT artifacts may carry only the shared visible-only prompt, function name, visible tests, SFT response, and bounded metadata. They must never carry train/eval hidden tests, reference solutions, or starter code; trainer datasets must drop validation payloads after `verify_completion()`.
- `train-sft` must retain exact pinned runtime checks, non-quantized LoRA, `trust_remote_code=False`, local-only reporting, payload-free run metadata, and the pre-model-load 20 GiB hardware guard. Never bypass that guard on the GTX 1660 Ti.
- The WP4-a verifier accepts exactly one caller-selected non-empty test list, never a complete problem or test-layer selector. It must use `extract_python_code()` for parsing and `CodeExecutor` for execution, and sanitized mappings must not store completion, code, tests, function name, or metadata.
- WP4 reward code must flow through `verify_completion()` and therefore through the configured `CodeExecutor`; reward modules must not parse or execute candidate code independently.
- Public and Hidden reward wrappers must share `rewards/common.py`. Public may score only `visible_tests`; Hidden may score only `train_hidden_tests`; `eval_hidden_tests` must never enter either training reward path.
- Reward component records must remain finite, JSON-safe, and free of completion, code, tests, function name, metadata, stdout/stderr, and nested execution results. Do not add WP7 trainer adapters, reward registry changes, GRPO configuration, or persistent experiment logging inside WP4.
- WP5-a evaluation prompts may contain only the problem statement, function signature, and visible examples. Never place `train_hidden_tests`, `eval_hidden_tests`, reference solutions, or SFT responses into generation prompts.
- WP5-a generation must remain frozen deterministic pass@1. Evaluation must not modify checkpoints, invoke training rewards, or add SFT/GRPO behavior. Real Transformers generation requires the full dependency environment; default tests must remain model/GPU independent. Real CUDA generation smoke tests auto-run in the default suite only when a CUDA-capable GPU with the full inference dependencies is detected; on CPU-only machines they are skipped with an explicit reason telling the user a GPU is required.
- WP5-a must verify the same completion in visible → train-hidden → eval-hidden order through `verify_completion()`. The top-level evaluation `execution_status` is the eval-hidden status; test payloads must never be serialized into evaluation rows or run metadata.
- Evaluation resume is exact-prefix only. Keep run/config/model/checkpoint/seed/dataset/prompt/repository/submodule/dependency/hardware identity checks fail-closed, and never regenerate already completed rows after a valid resume.
- Only `samples/results.jsonl` may persist evaluation completion text or extracted code. `run.json`, `environment.json`, `resolved_config.yaml`, `metrics.jsonl`, `stdout.log`, and `stderr.log` must remain free of completion/code/test payloads.
- `model_revision: null` is debug-only. Formal Base evaluation must use `configs/eval/base.yaml` with its immutable 40-hex revision, real loopback Piston, CUDA, and FP16. Aggregation remains problem-level, `public_eval_gap` remains paired, and derived summary/CSV artifacts must never contain completion/code/test payloads.
- `MockExecutor` never executes code. Real candidate code may only be sent to the strict local `PistonExecutor`; do not add host `exec`, `eval`, `compile`, or unrestricted subprocess execution paths.
- Preserve the in-sandbox process boundary: the trusted parent alone owns expected values, comparison, and the final marker; the candidate child may receive only the function name and input, and its result must remain an untrusted claimed return value.
- Preserve cache invalidation: any result-affecting executor, harness, comparison, mapping, or stopping-policy change must increment its version constant. Never remove code hash, problem ID, test layer, tests hash, executor version, function name, timeout, or memory from the cache key.
- Training cache remains disabled unless an experiment explicitly opts in and records the resolved policy. Cache files are sensitive artifacts because results may contain bounded stdout/stderr.
- Real Piston tests must be explicitly enabled. Any failed or skipped verdict-tampering, batch/cache, network, user, filesystem, host-isolation, cleanup, PID, timeout, memory, or output probe blocks merge.
- When adding new modules, update `pyproject.toml` `tool.mypy.files` if needed.
