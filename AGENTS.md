@~/.codex/AGENTS.md
## Repository Guidelines
project instructions are in `PROJECT_SPEC_Open-R1_CodeVerifier.md`
project proceedings are in `proceedings.md`
use `uv` to manage virtual environment and python packages
For long-running asynchronous work:
- Empty `write_stdin` polls MUST use `yield_time_ms >= 180000`; prefer `300000` when intermediate output is not needed.
- `functions.wait` MUST use `yield_time_ms >= 180000`.
- `functions.exec` MUST set its outer `@exec yield_time_ms` at least 30000 ms longer than the longest nested tool wait, so the outer code cell does not yield first.
- Do not apply the long wait to non-empty `write_stdin` calls that send interactive input.
- These tools return early when the process or cell completes. Do not wake the model merely to report that work is still running.

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
│           ├── grpo_data.py          # WP7-a payload-minimal GRPO dataset mapping
│           ├── grpo.py               # WP7 GRPO runtime/artifacts/checkpoint identity
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
│   │   ├── test_wp6a_sft_integration.py
│   │   ├── test_wp7a_grpo_integration.py
│   │   └── test_wp7b_grpo_checkpoint_evaluation.py
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
│       │   ├── test_grpo_data.py
│       │   ├── test_grpo.py
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
│   ├── sft/
│       ├── debug.yaml                 # WP6-a short 0.5B/fp16 config
│       └── main.yaml                  # WP6-a frozen 1.5B/bf16 LoRA config
│   └── grpo/
│       ├── public.yaml                # WP7-a Public-RLVR config
│       └── hidden.yaml                # WP7-a Hidden-RLVR config
├── docs/
│   ├── piston-local.md                # Loopback Piston deployment and safety runbook
│   └── 4090-remote-piston-handoff-amendment.md  # 4090 ordinary-container migration amendment
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
| `make test-piston` | Runs the real loopback Piston safety acceptance suite; the loopback endpoint may terminate at a local service or an SSH tunnel to the pinned remote Piston host |
| `make test-gpu` | Runs only the CUDA generation smoke tests; auto-skips with an explicit reason on machines without a CUDA-capable GPU |
| `make record-environment` | Records repo/submodule/Python/dependency versions to environment.json |
| `.venv/bin/code-verifier --help` | Shows CLI help |
| `.venv/bin/code-verifier evaluate --help` | Shows deterministic evaluation and aggregation options |
| `.venv/bin/code-verifier train-sft --help` | Shows strict LoRA SFT and resume options |
| `.venv/bin/code-verifier train-grpo --help` | Shows strict completed-B GRPO and resume options |

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
- **Agent transport state is never a repository artifact.** `.ai-bridge/**` is local, gitignored Web/Local handoff/runtime state only. It must have zero tracked paths and must never be staged or committed by planner, router, executor, reviewer, or lifecycle operations. Authoritative stage provenance lives under `ai-work/planner/`, `ai-work/executor/`, and `ai-work/reviewer/`; new portable target-GPU `run.sh` files are immutable, secret-free execution provenance and therefore live under tracked `ai-work/executor/operator/...`, not `.ai-bridge`. On the 4090, the migration bootstrap writes the local machine pointer `.ai-bridge/validation-machine.json`; it remains ignored target-machine state rather than stage provenance. If `git ls-files .ai-bridge` is non-empty, stop and repair the workflow state before continuing a stage.
- **Control-plane / GPU-worker split**: GTX 1660 Ti (6GB VRAM) is the project control plane and default development machine. Planner/reviewer/lifecycle/routing, ordinary code edits, workflow/docs/skills, lint/unit/CPU/non-4090 integration tests, data preparation/inspection/analysis, report/figure/table generation, Piston work, SFT visible-trajectory prevalidation, operator-handoff preparation, and all other work that does not intrinsically need a 24GB GPU run here. RTX 4090 is an ephemeral execution worker used only for target-GPU smoke/acceptance, optimizer-based SFT/GRPO, numerical validation, and formal inference/evaluation that truly requires the target GPU. `stage_profile=validation` and `target_hardware=24GB GPU` therefore do **not** mean planner/reviewer/router must run on the 4090. Every new plan records `control_plane_hardware: GTX 1660 Ti (6GB)` separately from `target_hardware`.
- **SFT prevalidation split remains authoritative**: `prevalidate-sft` is non-training control-plane work. It runs visible tests through Piston, checks the exact tokenizer/max-sequence contract, and writes an immutable payload-minimal manifest. `train-sft` consumes that manifest and must not contact Piston. Never bypass its >=20 GiB training guard or start optimizer-based SFT/GRPO on the GTX 1660 Ti.
- **Development-first lifecycle**: finish all dependency-ready production code and engineering tests that can be completed on the 1660 Ti before scheduling any 24GB training gate. A lower-numbered WP with only deferred real-training/numerical acceptance remaining does not block later development work such as GRPO control-plane or aggregation/analysis tooling.
- **Development completion**: terminal status requires a Development Completion Inventory covering WP0–WP8, not merely the absence of currently dependency-ready work. Each WP must be backed by finalized evidence or the terminal stage itself; `DEV-CLOSEOUT` is allowed only when all nine WP development deliverables are already finalized. The terminal stage also runs the full closeout suite (`make lint`, `make test`, `make test-gpu`, real `make test-piston` with 0 failed/0 skipped, and no production-critical stub/TODO/fake implementation). Only `stage-lifecycle finalize` may write the valid marker: an exact `## Development Complete Record` heading immediately followed by the required YAML `development_complete_record`; prose mentions never unlock validation.
- **Execution preflight / incomplete stages**: every plan must put checkable control-plane prerequisites (Piston, required imports, local data/cache where relevant) in an Execution preflight that runs before the first business modification/commit. Target-GPU-only prerequisites belong in the operator/target-GPU start preflight, not in planner/bootstrap. If an external environment interruption happens after valid commits, preserve the existing resumable `execution_checkpoint(interruption_class=environment)` path and resume after repair; do **not** force `retire_incomplete`. `retire_incomplete` is only for an explicit decision to abandon a non-resumable/incomplete stage within its existing guardrails.
- **Evidence boundary**: fixture/mock/synthetic data may close a development stage when it exercises the real production contracts, error paths, artifact schemas, checkpoint/resume wiring, and aggregation logic. It may never be recorded as a real checkpoint, completed SFT/GRPO run, B/C/D metric, cost result, or final research acceptance.
- **Persistent target-machine state/artifacts**: the completed 4090 bootstrap still owns machine-local `.ai-bridge/validation-machine.json`, persistent absolute `artifact_root`, `hf_home`, `formal_data_root`, READY identity and Piston identity. Formal target-GPU commands must fail closed rather than fall back to repo-local `outputs/`. These target-machine records are checked on the 4090 at operator/target-GPU start, not required merely to plan/bootstrap/review a validation stage on the control plane. Never store the only copy of a real checkpoint under `.worktrees/...`; large checkpoints remain on the 4090 persistent root. Small manifests/logs/metrics/summaries may be synced back to the control plane as review evidence.
- **Operator target-GPU runs**: every validation gate that intrinsically requires the 24GB target GPU—short smoke/acceptance, optimizer SFT/GRPO, and the **model-loading/generation portion** of formal Base/B/C/D evaluation—uses the same operator handoff boundary; this keeps the router/control plane off the 4090 and avoids a second hidden dispatch path. Formal evaluation must not keep the 4090 blocked on Piston once a frozen generation bundle can be transferred: use target-GPU `generate-eval` first, then run `verify-eval` + `aggregate-eval` on the GTX 1660 Ti/local Piston control plane. The sealed plan marks each target-GPU gate with `restart_policy=exact_rerun|trainer_checkpoint`; SFT/GRPO always use `trainer_checkpoint`. The control-plane executor finishes code/config/control-plane preflight/tests, creates one immutable secret-free portable `run.sh` under tracked `ai-work/executor/operator/{stage_id}/{gate_id}/{checkpoint_id}/run.sh`, records its SHA256/expected artifact contract in the append-only operator checkpoint, commits the execution report plus exactly that new script, then stops with `EXECUTION_OPERATOR_ACTION_REQUIRED`. Because the script is in Git provenance, the user only needs to make the exact checkpoint commit reachable on the 4090 (for example push/fetch), checkout that exact commit, verify the script SHA256, and run it manually in SSH/tmux; no out-of-band script copy is authoritative. The script resolves target-local roots at runtime, validates Git/checkpoint/script SHA plus the 4090 READY/GPU/roots/model/data/cache/Piston/storage contract, acquires an exclusive lock, and performs gate-specific preflight. After the target command it must run the sealed short **post-run acceptance** (strict completed-run/checkpoint loader, required metrics/schema/artifact identity checks as applicable) before declaring success. `command_rc=0` alone is insufficient. Status remains atomic, logs append-only, `exact_rerun`/`trainer_checkpoint` resume and quarantine semantics remain unchanged. GPT/CodexPro never starts or continuously monitors a formal target-GPU command.
- **Validation lifecycle stays control-plane-first**: terminal development finalize reports the exact `development_complete_commit`, but planner-ex, validation bootstrap, routing, review, aggregation, CI/error analysis and reporting continue on the GTX 1660 Ti. A validation stage may therefore be planned and sealed while the 4090 is offline. The 4090 receives only an exact Git commit plus a target-GPU operator handoff when a gate requires it; after the formal job and target evidence are saved, it may be shut down while review/analysis continue on the control plane. If a real target-GPU run exposes a tracked bug, repair happens through the same stage provenance loop on the control plane, then only the affected GPU gate is re-run.
- **Cross-machine artifact evidence**: reviewer-ex normally runs on the GTX 1660 Ti even when the formal artifact source machine is the 4090. Every new portable gate emits a versioned secret-free `operator-evidence.json` and syncs it byte-for-byte to the control plane. At minimum it binds `stage_id`, `source_plan_commit`, `operator_checkpoint_commit`, `result_code_commit`, `checkpoint_id`, `operator_gate_id`, tracked script path/SHA256, target machine-record SHA256 and GPU identity/VRAM, resolved persistent roots, Piston identity when required, attempt timestamps, `command_rc`, `postcheck_rc`, final `gate_status`, formal run identity, and an expected-artifact inventory with sizes plus SHA256 for identity/metadata artifacts. `gate_status=passed` is legal only when both the target command and sealed post-run acceptance pass. Resume must verify that schema/provenance and record the received evidence SHA256 in the completed execution report. Reviewer independently recomputes the tracked script SHA, evidence SHA, and synced small-artifact hashes; large checkpoints are not rsynced back by default. If evidence/postcheck cannot prove a required large-artifact property, perform a brief read-only target check before PASS; reviewer location still never has to equal artifact source machine.
- **Canonical Piston topology**: the only project Piston host is `1660ti-wsl`, running the pinned local Piston service. `home-piston-01` is retired and must not be reintroduced. The current low-latency transport is a loopback-only SSH **reverse forward initiated from the GTX 1660 Ti control plane to the current 4090 provider public SSH endpoint**: `-R 127.0.0.1:2000:127.0.0.1:2000`. The 4090 still sees only `http://127.0.0.1:2000`; the provider SSH hostname/port/authentication are machine-local operator state and must not be committed. The former 4090-side `ensure-piston-1660ti-tunnel.sh` / Tailscale local-forward path is no longer canonical and must not be started while the reverse-forward transport is in use. Piston-dependent target-GPU preflight only health-checks the 4090 loopback endpoint and exact Python runtime; if a formal target-GPU run is already active, do not restart or perturb the SSH transport.
- **Active-stage workflow migration**: if a project-level workflow update arrives after an active stage already has completed execution/review history, do not advance that clone's primary `main` and do not commit workflow files onto the active stage merely to consume the new runtime; doing either breaks the sealed `planning_base_commit`/review-HEAD guards. Fetch the exact workflow-maintenance commit into a dedicated clean maintenance branch/worktree in the same repository, load router/executor/reviewer/lifecycle from there, keep all business writes in the original stage worktree, and record the exact `workflow_runtime_commit` in every new execution/review created under that migrated runtime. A pre-migration sealed plan missing `control_plane_hardware` may infer GTX 1660 Ti only when the same plan already has a committed completed execution or committed review; pure PLANNED stages must replan. If the latest committed reviewer explicitly requires restoring operator-owned provenance for a pre-migration gate whose remaining command is genuinely control-plane-only, a repair may use `operator_handoff_mode=control_plane_manual`: it remains manual, script-hash/evidence bound, non-overwriting, and may never be used to move a real 24GB training/inference gate onto the GTX 1660 Ti. After the active stage finalizes, integrate the verified workflow-maintenance commits into that clone's `main` before planning the next stage.
- WP6-a SFT artifacts may carry only the shared visible-only prompt, function name, visible tests, SFT response, and bounded metadata. They must never carry train/eval hidden tests, reference solutions, or starter code; trainer datasets must drop validation payloads after `verify_completion()`.
- `train-sft` must retain exact pinned runtime checks, non-quantized LoRA, `trust_remote_code=False`, local-only reporting, payload-free run metadata, and the pre-model-load 20 GiB hardware guard. Never bypass that guard on the GTX 1660 Ti.
- B evaluation must obtain its adapter identity through `load_completed_sft_checkpoint()` from an SFT run whose `run.json` status is `completed`; never accept an arbitrary adapter/checkpoint path or infer the model source from a directory.
- PEFT evaluation reload must fail closed when the adapter base-model identity or pinned revision differs from the completed SFT run, remain inference-only, and reuse the existing deterministic evaluator and aggregator.
- Fixture/fake SFT adapters may verify the development reload, resume, and artifact contracts, but must never be recorded as a real B checkpoint, metric, loss, cost, or validation result.
- `train-grpo` must preflight both ordered Public/Hidden definitions before either run, reuse the config/artifact pair validators, bind both definitions to the same identity loaded through `load_completed_sft_checkpoint()`, and retain the pre-model-load 20 GiB guard. Never accept arbitrary adapter paths or bypass the guard on the GTX 1660 Ti.
- GRPO policy construction is fixed: base A → completed B adapter loaded read-only → `merge_and_unload(safe_merge=True)` → new trainable GRPO LoRA. Never pass the unmerged B adapter as the active `GRPOTrainer` PEFT adapter; its disabled-adapter reference would incorrectly become A.
- Completed C/D evaluation must obtain its identity through `load_completed_grpo_checkpoint()`. That loader must revalidate the unique parent B through `load_completed_sft_checkpoint()` and fail closed on copied parent metadata, path, base-model, revision, or adapter drift.
- C/D evaluation must rebuild base A → completed B read-only → `merge_and_unload(safe_merge=True)` → C/D read-only, then reuse the existing deterministic evaluator and aggregator. Never accept an arbitrary C/D adapter path, attach C/D directly to A, or branch evaluation behavior on reward mode.
- Fixture/fake C/D adapters may verify development identity, stacked reload, resume, artifact, and payload contracts, but must never be recorded as a real C/D checkpoint, metric, loss, cost, or validation result.
- Public GRPO trainer rows contain visible tests only. Hidden rows add only train-hidden tests. `eval_hidden_tests`, reference solutions, starter code, and SFT responses must never enter GRPO datasets, callbacks, or logs.
- GRPO `rewards.jsonl`, `group_metrics.jsonl`, trainer metrics, run/config/environment/stdout/stderr artifacts must remain finite, JSON-safe, and payload-free. Only `rollouts.jsonl` may contain completion text. Fixture/fake runs are engineering evidence, never formal C/D checkpoints, metrics, loss, or cost.
- WP8 analysis must reload strict A/B/C/D source identities, require one problem set and evaluation definition, pair C/D comparisons by `problem_id`, and bootstrap at problem level. Derived report artifacts may contain only aggregate/provenance scalars and source pointers/hashes, never copied completion/code/test/reference/starter/SFT-response payloads. Automated failure candidates are not human conclusions, GPU-hour price must be explicit, and fixture/synthetic outputs are engineering evidence only.
- The WP4-a verifier accepts exactly one caller-selected non-empty test list, never a complete problem or test-layer selector. It must use `extract_python_code()` for parsing and `CodeExecutor` for execution, and sanitized mappings must not store completion, code, tests, function name, or metadata.
- WP4 reward code must flow through `verify_completion()` and therefore through the configured `CodeExecutor`; reward modules must not parse or execute candidate code independently.
- Public and Hidden reward wrappers must share `rewards/common.py`. Public may score only `visible_tests`; Hidden may score only `train_hidden_tests`; `eval_hidden_tests` must never enter either training reward path.
- Reward component records must remain finite, JSON-safe, and free of completion, code, tests, function name, metadata, stdout/stderr, and nested execution results. Do not add WP7 trainer adapters, reward registry changes, GRPO configuration, or persistent experiment logging inside WP4.
- WP5-a evaluation prompts may contain only the problem statement, function signature, and visible examples. Never place `train_hidden_tests`, `eval_hidden_tests`, reference solutions, or SFT responses into generation prompts.
- WP5-a generation must remain frozen deterministic pass@1. Evaluation must not modify checkpoints, invoke training rewards, or add SFT/GRPO behavior. Real Transformers generation requires the full dependency environment; default tests must remain model/GPU independent. Real CUDA generation smoke tests auto-run in the default suite only when a CUDA-capable GPU with the full inference dependencies is detected; on CPU-only machines they are skipped with an explicit reason telling the user a GPU is required.
- WP5-a must verify the same completion in visible → train-hidden → eval-hidden order through `verify_completion()`. The top-level evaluation `execution_status` is the eval-hidden status; test payloads must never be serialized into evaluation rows or run metadata.
- Evaluation resume is exact-prefix only. Keep run/config/model/checkpoint/seed/dataset/prompt/repository/submodule/dependency/hardware identity checks fail-closed, and never regenerate already completed rows after a valid resume.
- Only `samples/results.jsonl` may persist evaluation completion text or extracted code. `run.json`, `environment.json`, `resolved_config.yaml`, `metrics.jsonl`, `stdout.log`, and `stderr.log` must remain free of completion/code/test payloads.
- `model_revision: null` is debug-only. Formal Base evaluation must use `configs/eval/base.yaml` with its immutable 40-hex revision, real loopback Piston, CUDA, and FP16. The loopback endpoint may be a local Piston service or an SSH tunnel to the pinned dedicated Piston host; public/non-loopback Piston endpoints remain forbidden. Aggregation remains problem-level, `public_eval_gap` remains paired, and derived summary/CSV artifacts must never contain completion/code/test payloads.
- `MockExecutor` never executes code. Real candidate code may only be sent to the strict loopback-only `PistonExecutor`; the backend may be the pinned local service or the pinned remote Piston host reached through loopback-only SSH forwarding. Do not add host `exec`, `eval`, `compile`, or unrestricted subprocess execution paths.
- Preserve the in-sandbox process boundary: the trusted parent alone owns expected values, comparison, and the final marker; the candidate child may receive only the function name and input, and its result must remain an untrusted claimed return value.
- Preserve cache invalidation: any result-affecting executor, harness, comparison, mapping, or stopping-policy change must increment its version constant. Never remove code hash, problem ID, test layer, tests hash, executor version, function name, timeout, or memory from the cache key.
- Training cache remains disabled unless an experiment explicitly opts in and records the resolved policy. Cache files are sensitive artifacts because results may contain bounded stdout/stderr.
- Real Piston tests must be explicitly enabled. Any failed or skipped verdict-tampering, batch/cache, network, user, filesystem, host-isolation, cleanup, PID, timeout, memory, or output probe blocks merge.
- When adding new modules, update `pyproject.toml` `tool.mypy.files` if needed.
