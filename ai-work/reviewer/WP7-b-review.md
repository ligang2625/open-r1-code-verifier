# WP7-b Review

## Review round 1

```yaml
review_record:
  version: 1
  stage_id: WP7-b
  review_round: 1
  source_execution_id: E0
  reviewed_head_commit: d894f887c7fb77ce24338b4779655187b572e2d9
  conclusion: pass
```

### Scope and provenance

- Reviewed sealed plan `ai-work/planner/WP7-b-plan.md`, source plan commit `c3b1f7d08ab6aca3a8b1eba715ee0201e92efbd7`.
- Latest completed execution is `E0`, `task_kind=implementation`, with `result_code_commit=3eb54c1c72ac1e6df5c724fcbd559527f71aff6f`.
- The execution report is committed at and uniquely bound to stage HEAD `d894f887c7fb77ce24338b4779655187b572e2d9`; review started with `HEAD` exactly at that commit.
- Stage worktree: `/home/dzy/open-r1-code-verifier/.worktrees/wp7-b`, branch `feat/wp7-b`; worktree was clean before review and `git ls-files .ai-bridge` was empty.
- Stage profile is `development`, target hardware `GTX 1660 Ti (6GB)`, evidence class `engineering`, `development_terminal=false`. Real SFT/GRPO optimizer runs, formal B/C/D checkpoints, research metrics, cost evidence, and 24GB validation are therefore outside this review gate and were not required.
- Business changes from plan seal through `result_code_commit` were limited to the declared WP7-b scope: GRPO checkpoint identity/export, stacked PEFT inference reload, evaluate CLI binding, WP7-b tests/integration, README, and AGENTS. No dependency file, GRPO config, Piston/execution implementation, `third_party/open-r1/**`, plan, proceedings, or prior review artifact was modified.

### Independent review findings

No blocker, major, minor, or other actionable issue was found.

The implementation satisfies the sealed WP7-b development contract:

1. `load_completed_grpo_checkpoint()` requires the strict GRPO run layout and `status=completed`, binds the checkpoint directory directly to the run, rejects missing/symlinked final adapter artifacts, validates GRPO identity fields, and independently reloads the recorded parent SFT run through `load_completed_sft_checkpoint()` before comparing all persisted parent identity fields.
2. The GRPO adapter base-model identity and non-null revision are checked against the completed parent B identity, preventing a C/D run from silently pointing at a different base lineage.
3. `grpo_evaluation_checkpoint_id()` creates a deterministic identity string that includes the resolved C/D checkpoint/run identity, reward mode, GRPO dataset/config/dependency/seed identity, and the completed parent B run/checkpoint/model/config/data/dependency/seed identity. Changing C↔D or parent B changes the evaluation checkpoint identity and therefore invalidates exact-prefix resume.
4. `TransformersCompletionGenerator.from_grpo_checkpoint()` reconstructs inference in the required order: load A, attach B read-only, require and call `merge_and_unload(safe_merge=True)`, then attach C/D read-only. It does not create a trainer or optimizer and preserves the existing deterministic generation initialization path.
5. Existing B evaluation behavior remains on `from_peft_checkpoint()`; C/D adds a separate stacked-loader entry point without creating a second evaluator or aggregator.
6. `code-verifier evaluate` now exposes an exact three-way mutually exclusive model source (`--model-id`, `--sft-run-dir`, `--grpo-run-dir`). For C/D, it loads the completed GRPO identity, derives the base/revision from the revalidated parent B, substitutes only the effective checkpoint/revision in `EvaluationConfig`, and then calls the existing `run_pass1_evaluation()` and `aggregate_evaluation_run()`.
7. The WP7-b integration test uses production checkpoint loaders, production stacked PEFT construction, the real deterministic evaluator, and the existing aggregator. Its fakes are limited to model/runtime execution and explicitly record A → B attach → safe merge → C/D attach, so the test does not bypass the new production control path.
8. Resume evidence covers reuse of the exact same C identity and rejection after C↔D, generation-config, dataset-path, parent-B/GRPO identity, or seed changes.
9. Prompt and artifact boundary checks confirm hidden tests, reference solution, starter code, and SFT response do not enter generation prompts; non-sample evaluation artifacts remain free of completion/code/test payloads. Fixture adapters remain engineering evidence only and are not represented as formal training/checkpoint/cost evidence.
10. No experiment definition, C/D training configuration, reward logic, execution isolation, pinned dependency, or third-party Open-R1 source was changed by this stage.

### Independent verification evidence

- Focused WP7-b suite:
  - `.venv/bin/python -m pytest tests/unit/training/test_grpo.py tests/unit/evaluation/test_generate.py tests/unit/test_cli.py tests/integration/test_wp7b_grpo_checkpoint_evaluation.py -q`
  - Result: `160 passed`.
- Lint/type gate:
  - `make lint`
  - Result: Ruff check PASS, Ruff format PASS (`91 files already formatted`), strict Mypy PASS (`Success: no issues found in 91 source files`).
- Full default suite:
  - `make test`
  - Result: `833 passed, 3 skipped`; all three skips are the existing explicit real-Piston opt-in tests. GPU smoke tests executed and passed in this suite.
- GPU engineering gate:
  - `make test-gpu`
  - Result: `3 passed` on the development GPU.
- Real loopback Piston prerequisite:
  - project `PistonExecutor.validate_runtime()` against `configs/execution/piston-local.yaml`
  - Result: runtime `3.10.0`.
- CLI contract:
  - `.venv/bin/code-verifier evaluate --help`
  - Result: exit `0`; help shows required `(--model-id ... | --sft-run-dir ... | --grpo-run-dir ...)` source selection.
- Stage-local runtime/source binding:
  - `code_verifier.__file__` resolves under `.worktrees/wp7-b/src/code_verifier`.
  - `open_r1.__file__` resolves under `.worktrees/wp7-b/third_party/open-r1/src/open_r1`.
  - Independently observed pinned runtime versions: PEFT `0.14.0`, Transformers `4.52.3`, torch `2.6.0+cu124`.
- Test execution left the stage worktree clean; reviewed HEAD remained `d894f887c7fb77ce24338b4779655187b572e2d9` throughout the read/test portion of review.

### Plan acceptance disposition

- Completed GRPO run/checkpoint identity and strict run/layout validation: PASS.
- Parent completed-SFT B revalidation and exact identity binding: PASS.
- Stable C/D evaluation checkpoint identity including parent B: PASS.
- A → read-only B → `safe_merge=True` → read-only C/D inference reconstruction: PASS.
- Base/B evaluation regression and C/D explicit CLI source: PASS.
- Reuse of existing deterministic evaluator/aggregator: PASS.
- Exact-prefix resume binding to C/D and parent B identity: PASS.
- Public/Hidden evaluation parity; no reward-mode-specific evaluator branch: PASS.
- Prompt/non-sample artifact payload boundaries: PASS.
- Fixture/fake evidence correctly limited to engineering evidence: PASS.
- `make lint` / `make test` / `make test-gpu`: PASS.
- Piston runtime prerequisite: PASS.
- No `third_party/open-r1/**`, dependency, or experiment-definition change: PASS.
- No real optimizer training or fabricated B/C/D checkpoint/metric/cost evidence: PASS.
- `development_terminal=false` correctly retained; WP8 remains outside this stage: PASS.

```yaml
repair_routing:
  version: 1
  required: false
  source_review_round: 1
  mode: null
  complexity: null
  single_class: null
  parallelizability: null
  multi_benefit: null
  independent_workstreams: 0
  repair_issue_ids: []
  rationale:
    - "WP7-b E0 independently satisfies the sealed development plan for completed C/D identity, parent-B binding, stacked reload, and unified evaluation."
    - "Focused, full, lint/type, GPU, Piston, CLI, source-binding, resume, and payload-boundary checks passed; no actionable repair remains."
  workstream_candidates: []
```

### Conclusion

**PASS.** The reviewed state at `d894f887c7fb77ce24338b4779655187b572e2d9` is acceptable as WP7-b development evidence. The next lifecycle operation is `$stage-lifecycle checkpoint_review`. After that review checkpoint is committed and remains current, the stage may proceed to `$stage-lifecycle finalize`.

## Finalization Record

```yaml
finalization_record:
  review_round: 1
  review_commit: 95189360692bfee282f77cdac9a7a4c2b2b338eb
  merge_commit: adc0490f72d28e78b87f7cde9ae6bcb62e3d589e
  finalized_at: 2026-08-14T17:58:14+08:00
  status: finalized
```
