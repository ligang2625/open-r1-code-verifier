# WP7-b Execution Report

## E0 implementation summary

Implemented the sealed WP7-b development plan as one Local Codex SINGLE execution. The stage now validates completed
GRPO C/D checkpoint identity against its unique completed SFT B parent, reconstructs inference as A → safe-merged B
→ read-only C/D, and evaluates C/D through the existing deterministic evaluator and aggregator.

No optimizer-based SFT or GRPO was run. No fixture artifact was reported as a real B/C/D checkpoint, research
metric, loss, cost, or validation result.

### Execution preflight

- Baseline provenance: clean `feat/wp7-b` at sealed plan commit
  `c3b1f7d08ab6aca3a8b1eba715ee0201e92efbd7`; the checked-out plan was byte-identical to the plan in that commit,
  no prior WP7-b completed E0 existed, and `git ls-files .ai-bridge` was empty.
- Stage-local tools: Ruff `0.9.10`, Mypy `1.15.0`, pytest `8.3.5`.
- Pinned runtime: PEFT `0.14.0`, Transformers `4.52.3`, torch `2.6.0+cu124`, matching the lockfile.
- Pinned API: `PeftModel.from_pretrained` exposes `is_trainable=False`; PEFT 0.14 delegates
  `merge_and_unload` from `PeftModel` instances to `LoraModel`, whose signature exposes `safe_merge=False` and
  therefore supports the required `safe_merge=True` call.
- CUDA/model-cache baseline: pre-implementation `make test-gpu` passed `3 passed` on the GTX 1660 Ti.
- Piston prerequisite: `PistonExecutor.validate_runtime()` against the resolved
  `configs/execution/piston-local.yaml` returned Python runtime `3.10.0`.
- Source binding: `code_verifier` and `open_r1` both resolved inside
  `/home/dzy/open-r1-code-verifier/.worktrees/wp7-b`, including its pinned `third_party/open-r1` checkout.

### Plan steps and commits

| Step | Result | Commit |
|---|---|---|
| 1. Completed GRPO identity | Added strict completed-run/layout/adapter validation, parent-B revalidation, and stable non-sensitive evaluation identity. | `e67a99a` |
| 2. Stacked inference reload | Added read-only A → B attach → safe merge → C/D attach construction while retaining the B reload contract. | `5b81547` |
| 3. Evaluate CLI binding | Added explicit Base/SFT/GRPO three-way model-source selection and reused the existing evaluator/aggregator. | `f295d31` |
| 4. Integration contract | Added Public C and Hidden D engineering fixtures covering production reload order, resume identity, schemas, and payload boundaries. | `3bbb96f` |
| 5. Documentation/invariants | Documented WP7-b usage, reconstruction order, parent binding, and fixture evidence limits. | `a9fd87c` |
| Acceptance cleanup | Applied Ruff formatting and strict-Mypy test typing corrections found by the global lint gate. | `3eb54c1` |

### Files changed

- Production: `src/code_verifier/training/grpo.py`, `src/code_verifier/training/__init__.py`,
  `src/code_verifier/evaluation/generate.py`, `src/code_verifier/cli.py`.
- Tests: `tests/unit/training/test_grpo.py`, `tests/unit/evaluation/test_generate.py`, `tests/unit/test_cli.py`,
  `tests/integration/test_wp7b_grpo_checkpoint_evaluation.py`.
- Documentation: `README.md`, `AGENTS.md`.

The sealed plan, review area, `proceedings.md`, dependency files, configs, and `third_party/open-r1/` were not
modified. `.ai-bridge/**` remained ignored/untracked and was never staged.

### Verification

- Plan focused suite:
  `.venv/bin/python -m pytest tests/unit/training/test_grpo.py tests/unit/evaluation/test_generate.py tests/unit/test_cli.py tests/integration/test_wp7b_grpo_checkpoint_evaluation.py -q`
  — `160 passed`.
- `make lint` — PASS: Ruff check, Ruff format check, and strict Mypy; `91 files already formatted`,
  `Success: no issues found in 91 source files`.
- `make test` — `833 passed, 3 skipped`; all three skips are the existing explicit real-Piston opt-in tests. The
  CUDA smoke tests ran and passed inside the default suite.
- `make test-gpu` — `3 passed` on the GTX 1660 Ti after implementation.
- Final non-destructive Piston probe — PASS; configured runtime `3.10.0`.
- `.venv/bin/code-verifier evaluate --help` — PASS; displays required
  `(--model-id MODEL_ID | --sft-run-dir SFT_RUN_DIR | --grpo-run-dir GRPO_RUN_DIR)`.

### Evidence boundary, deviations, and blockers

- Stage profile remained `development` on the GTX 1660 Ti with `engineering` evidence and
  `development_terminal: false`.
- Public/Hidden integration adapters and Transformers/PEFT runtimes are explicit fixtures/fakes. They exercise the
  production identity/reload/evaluation contracts but are not formal C/D evidence.
- `make test-piston` was not run because WP7-b does not modify execution/Piston isolation and the sealed non-terminal
  plan requires only a runtime probe; the three default-suite skips are the expected real-Piston opt-in tests.
- The first preflight shell wrapper escaped newlines incorrectly and did not execute its intended checks. It made no
  repository changes; every preflight item was immediately rerun with direct commands and passed before the first
  business modification.
- The global lint gate initially found one Ruff formatting difference and strict-Mypy typing errors in new tests.
  These tracked code issues were fixed in the same execution, committed, and all affected/global gates were rerun.
- Final deviations from the sealed functional scope: none. Blockers: none.

## Structured E0 execution record

```yaml
execution_record:
  version: 1
  stage_id: WP7-b
  execution_id: E0
  task_kind: implementation
  source_plan_commit: c3b1f7d08ab6aca3a8b1eba715ee0201e92efbd7
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: 3eb54c1c72ac1e6df5c724fcbd559527f71aff6f
  execution_backend: local_codex
  effective_execution_mode: single
  status: completed
```
