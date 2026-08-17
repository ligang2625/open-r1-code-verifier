# WP5-c Review

## R1 — Formal Base A validation review

```yaml
review_record:
  version: 1
  stage_id: WP5-c
  review_round: 1
  source_execution_id: E0
  reviewed_head_commit: c1b1355a7be217f0afa3ac173b32a458c9348f71
  conclusion: needs_repair
```

### Review scope and provenance

- Reviewed sealed plan: `ai-work/planner/WP5-c-plan.md`, source plan commit `34c37aa0a8d8b432cc920aa9e130e986c7e0e27f`.
- Reviewed latest completed execution: `E0` in `ai-work/executor/WP5-c-executor.md`.
- Git history is coherent: implementation commit `ca56d8ec422e2037209cf565b517e119d380b269` → operator checkpoint docs commit `b9261f4b9343e3e98c78ab0aa3684f11144302b8` → completed E0 report commit `c1b1355a7be217f0afa3ac173b32a458c9348f71`.
- `c1b1355...` changes only `ai-work/executor/WP5-c-executor.md`; the stage was clean when review started and remained at the same HEAD throughout review.
- `.ai-bridge/**` remains ignored/untracked in the stage.
- This review did not rerun the 400-problem operator gate; it inspected the committed checkpoint and persistent artifacts and ran only short reviewer-owned checks.

### Implementation and plan conformance

- `evaluate --dataset-dir PATH` is implemented as the planned minimal explicit override. `_evaluate()` applies it immediately after loading the evaluation config and before Piston/generator/evaluation setup; default behavior is unchanged when the argument is absent.
- The CLI prints `override: dataset_dir: <old> -> <new>` to stderr, satisfying the explicit CLI override audit requirement.
- Unit coverage includes parser acceptance/default behavior and handler propagation before `run_pass1_evaluation()`.
- The tracked implementation scope is limited to `src/code_verifier/cli.py`, `tests/unit/test_cli.py`, and `README.md`, matching the sealed plan.

### Operator checkpoint and persistent evidence

- C0 checkpoint uses `restart_policy=exact_rerun`, persistent operator namespace, immutable script SHA256 `7d49ac99d3f262b203624e224aa0c5a7c004d4f29039ea643434dd6576345b8e`, exclusive `flock`, Git/report self-provenance checks, GPU/Piston/data/model/storage start preflight, append-only terminal log, and atomic status writes.
- Operator status is `0`; terminal log contains two `attempt-start` records. The first attempt was interrupted without a terminal long-command-end marker, and the second attempt completed with `long-command-end rc=0`, which is consistent with the sealed exact-rerun recovery contract.
- The completed long run reports `resumed=7, generated=393`. The subsequent exact-prefix verification records `resumed=400, generated=0` without changing `samples/results.jsonl`.
- Persistent Base A path is `/root/sj-tmp/open-r1-code-verifier-outputs/evaluation/A-base-formal-seed42`, outside the stage worktree.
- `run.json.status=completed`; model/revision/checkpoint/seed match the sealed Base A definition.
- `resolved_config.yaml` binds `/root/sj-tmp/open-r1-code-verifier-data-4090/prepared`, `split=test`, CUDA/FP16, deterministic generation, `max_new_tokens=512`, `temperature=null`, `top_p=null`.
- Independent readback confirmed exactly 400 result rows, 400 unique `problem_id` values, and exact order equality with the formal test split.
- `results.jsonl` SHA256 is `cca9945d28962bcee241cfc69b38ec0c326862e15d9e74f2b5b0354cb01e277e`, matching E0.
- Independent non-sample payload scan passed for `run.json`, `environment.json`, `resolved_config.yaml`, `metrics.jsonl`, `stdout.log`, `stderr.log`, `summary.json`, and `main_results.csv`.
- Main numerical evidence independently read back as finite and internally consistent: Eval-Hidden Pass@1 `0.115`, 95% problem-level bootstrap CI `[0.085, 0.1475]`, visible/train-hidden Pass@1 `0.1225/0.1175`, public-eval gap `0.0075`, with 10,000 bootstrap resamples and seed 42.
- Actual cached `model.safetensors` SHA256 remains `c1b9b30e907950516ba3c646bdf570d8084c25a6410a0cdca80cf04b11bc13a8`, matching the 4090 readiness record.

### Independent reviewer checks

- `make lint`: PASS — Ruff check/format and strict Mypy passed.
- `make test` with the readiness exact 1.5B snapshot: PASS — 882 passed, 3 expected real-Piston opt-in skips, 0 failed.
- `make test-gpu` with the exact cached revision: PASS — 3 passed, 0 failed/skipped.
- `make test-piston`: PASS — 9 selected passed, 0 failed/skipped (`2 deselected`).
- Persistent artifact identity/order/finite-metric check: PASS.
- Non-sample payload scan: PASS.

### Findings

#### R1-M1 — Formal Base A run is missing mandatory per-run timing/cost provenance

`PROJECT_SPEC_Open-R1_CodeVerifier.md` §18.1 states that every run must save, among other provenance, `start_time`, `end_time`, and `gpu_hours`. The formal Base A artifact currently records `created_at` and environment/model/dataset/config identities but does not persist those three required fields in `run.json` or another canonical per-run metadata record. The independent check of `run.json + environment.json` confirms `start_time`, `end_time`, and `gpu_hours` are absent.

This is material for a real validation run rather than a cosmetic schema difference: Base A actually experienced an interrupted first operator attempt and an exact-prefix second attempt, so later cost/runtime audit cannot reconstruct exact active-GPU time from `run.json` alone. The operator terminal log provides useful attempt timestamps but the interrupted first attempt has no terminal end marker; therefore missing values must not be invented or silently inferred with an undocumented approximation.

Required repair acceptance:

1. Define and implement the formal evaluation run metadata contract so fresh/resumed Base/B/C/D evaluation records preserve non-sensitive `start_time`, `end_time`, and finite non-negative `gpu_hours` with explicit semantics that remain correct across interrupted/exact-prefix attempts.
2. Add focused tests covering fresh completion and interrupted/resumed evaluation metadata behavior without weakening the existing exact-prefix identity contract or payload boundary.
3. Reconcile the already-produced Base A formal evidence using only auditable existing evidence. Preserve the current 400 result rows and their hash if exact required metadata can be established without fabrication. If exact values cannot be established under the chosen contract, do not fabricate them: preserve/quarantine the existing formal run and use the operator workflow to produce a new canonical Base A run under the repaired metadata contract.
4. Update the execution report with the resulting provenance and rerun the short acceptance/readback gates. The reviewer must not accept a manual metadata edit whose derivation is not auditable.

### Non-blocking observation

The operator terminal log contains repeated Transformers warnings that sampling-only generation flags may be ignored while the resolved project config is deterministic (`do_sample=false`, `temperature=null`, `top_p=null`). The final artifacts and deterministic identity checks remain valid, so this is not a repair issue for R1. It is worth suppressing or normalizing in a future maintenance change because the warning volume is confusing during long manual runs.

```yaml
repair_routing:
  version: 1
  required: true
  source_review_round: 1
  mode: single
  complexity: normal
  single_class: normal
  parallelizability: low
  multi_benefit: low
  independent_workstreams: 1
  repair_issue_ids:
    - R1-M1
  rationale:
    - "The only blocking issue is one coupled evaluation-provenance contract: implementation, resume semantics, tests, and reconciliation of the existing Base A artifact must be handled together."
    - "Parallel lanes would increase risk around run identity and persistent artifact reconciliation without shortening any expensive operator task."
  workstream_candidates: []
```
