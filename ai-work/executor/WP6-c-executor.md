# WP6-c Execution Report

## E0 implementation summary

Implemented the sealed WP6-c development plan as one Local Codex SINGLE execution. The stage now has a strict
completed-SFT checkpoint identity loader, pinned PEFT inference reload, explicit B-group CLI binding, and an
engineering integration test through the existing deterministic evaluator and aggregator.

No optimizer-based SFT or GRPO was run. No real or fixture artifact was reported as a B checkpoint, research metric,
loss, or cost result.

### Execution preflight

- Stage-local tools: Ruff `0.9.10`, Mypy `1.15.0`, Pytest `8.3.5`.
- Pinned runtime: PEFT `0.14.0`, Transformers `4.52.3`, torch `2.6.0+cu124`.
- Pinned API: `PeftConfig.from_pretrained` accepts a local adapter path; `PeftModel.from_pretrained` exposes
  `model_id`, `is_trainable`, and adapter inference parameters.
- CUDA/cache baseline: `make test-gpu` passed `3 passed` before implementation.
- Source binding: `code_verifier` and `open_r1` both resolved inside
  `/home/dzy/open-r1-code-verifier/.worktrees/wp6-c`.
- Baseline provenance: clean `feat/wp6-c` at sealed plan commit
  `09452e78d1d51300e6938768180d6d0decbc5c97`; no prior WP6-c execution report or review existed.

### Plan steps and commits

| Step | Result | Commit |
|---|---|---|
| 1. Completed SFT checkpoint identity | Added strict completed-run/layout/identity/adapter validation and payload-free identity return. | `e032a27` |
| 2. PEFT inference reload | Added shared safe base loading plus identity-checked, inference-only PEFT adapter loading. | `796296d` |
| 3. Evaluate CLI binding | Added required mutual exclusion between `--model-id` and `--sft-run-dir`; SFT runs reuse the existing evaluator and aggregator. | `e1138b4` |
| 4. Integration contract | Added fake-runtime engineering coverage for reload, evaluation, aggregation, exact-prefix resume, and payload boundaries. | `d87883d` |
| 5. Documentation/invariants | Documented B evaluation usage and development/validation evidence boundaries in README and AGENTS. | `18af732` |

### Files changed

- Production: `src/code_verifier/training/sft.py`, `src/code_verifier/training/__init__.py`,
  `src/code_verifier/evaluation/generate.py`, `src/code_verifier/cli.py`.
- Tests: `tests/unit/training/test_sft.py`, `tests/unit/evaluation/test_generate.py`,
  `tests/unit/test_cli.py`, `tests/integration/test_wp6c_sft_checkpoint_evaluation.py`.
- Documentation: `README.md`, `AGENTS.md`.

The sealed plan, review area, `proceedings.md`, dependency files, and `third_party/open-r1/` were not modified.

### Verification

- Plan focused suite:
  `.venv/bin/python -m pytest tests/unit/training/test_sft.py tests/unit/evaluation/test_generate.py tests/unit/test_cli.py tests/integration/test_wp6c_sft_checkpoint_evaluation.py -q`
  — `124 passed`.
- `make lint` — PASS: Ruff check, Ruff format check, and strict Mypy; `85 files already formatted`,
  `Success: no issues found in 85 source files`.
- `make test` — `736 passed, 3 skipped`; all skips are the existing explicit real-Piston opt-in tests.
- `make test-gpu` — `3 passed` on the GTX 1660 Ti.
- `.venv/bin/code-verifier evaluate --help` — PASS; displays required
  `(--model-id MODEL_ID | --sft-run-dir SFT_RUN_DIR)`.

### Evidence boundary, deviations, and blockers

- Evidence class remains `engineering`. Integration adapters and model runtimes are explicit fixtures/fakes and are
  not formal B evidence.
- The development stage performed no optimizer step, real training, checkpoint production, numerical B evaluation,
  or cost measurement.
- `make test-piston` was not run because WP6-c did not modify execution/Piston behavior and the sealed plan does not
  require that non-terminal gate; the default suite contains only the three expected opt-in Piston skips.
- Deviations: none.
- Blockers: none.

## Structured E0 execution record

```yaml
execution_record:
  version: 1
  stage_id: WP6-c
  execution_id: E0
  task_kind: implementation
  source_plan_commit: 09452e78d1d51300e6938768180d6d0decbc5c97
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: 18af732f1fad8e54cab64bc40272d029dc0d233b
  execution_backend: local_codex
  effective_execution_mode: single
  status: completed
```

## E1 repair summary

Repaired `R1-M1` as one Local Codex SINGLE repair. Pinned TRL 0.18.0 / PEFT 0.14.0 adapters whose config leaves
`revision=None` now load against the non-empty completed-run `model_revision`; an adapter config that explicitly
contains a different revision still fails closed. The strict adapter `base_model_name_or_path == checkpoint.model_id`
validation is unchanged.

### Execution preflight

- Stage-local tools: Ruff `0.9.10`, Mypy `1.15.0`, Pytest `8.3.5`.
- Pinned runtime: PEFT `0.14.0`, Transformers `4.52.3`, torch `2.6.0+cu124`; required PEFT loader APIs exist.
- CUDA/cache baseline: `make test-gpu` passed `3 passed` before repair.
- Source binding: `code_verifier` and `open_r1` both resolved inside
  `/home/dzy/open-r1-code-verifier/.worktrees/wp6-c`.
- Baseline provenance: clean `feat/wp6-c` at committed review
  `a61af3a4956cf205f48d6c6fee707ac73f5241a8`.

### R1-M1 changes

- Updated `TransformersCompletionGenerator.from_peft_checkpoint()` to compare revisions only when the adapter config
  supplies one, while retaining the completed-run revision for base tokenizer/model loading.
- Added a realistic non-empty run-revision plus `adapter_revision=None` regression and retained explicit mismatch and
  base-model identity rejection coverage.
- Updated the WP6-c integration fake adapter/config fixture and README to reflect pinned TRL/PEFT semantics.
- Code/test/documentation commit: `29be612ca4176761962ebbd67839f4c3e96181f7`.

### Verification

- Affected tests:
  `.venv/bin/python -m pytest tests/unit/evaluation/test_generate.py tests/integration/test_wp6c_sft_checkpoint_evaluation.py -q`
  — `41 passed`.
- Plan focused suite:
  `.venv/bin/python -m pytest tests/unit/training/test_sft.py tests/unit/evaluation/test_generate.py tests/unit/test_cli.py tests/integration/test_wp6c_sft_checkpoint_evaluation.py -q`
  — `125 passed`.
- `make lint` — PASS: Ruff check/format and strict Mypy.
- `make test` — `737 passed, 3 skipped`; all skips are the existing explicit real-Piston opt-in tests.
- `make test-gpu` — `3 passed` on the GTX 1660 Ti.
- `.venv/bin/code-verifier evaluate --help` — PASS; required Base/SFT model-source exclusivity is displayed.

### Evidence boundary, deviations, and blockers

- Evidence remains engineering-only. No optimizer-based SFT/GRPO, real B checkpoint, numerical metric, or cost was
  produced or claimed.
- Scope was limited to `R1-M1`; plan, review, `proceedings.md`, dependency files, and `third_party/open-r1/` were not
  modified.
- Deviations: none.
- Blockers: none.

## Structured E1 execution record

```yaml
execution_record:
  version: 1
  stage_id: WP6-c
  execution_id: E1
  task_kind: repair
  source_plan_commit: 09452e78d1d51300e6938768180d6d0decbc5c97
  source_review_round: 1
  source_review_commit: a61af3a4956cf205f48d6c6fee707ac73f5241a8
  repair_issue_ids: [R1-M1]
  result_code_commit: 29be612ca4176761962ebbd67839f4c3e96181f7
  execution_backend: local_codex
  effective_execution_mode: single
  status: completed
```
