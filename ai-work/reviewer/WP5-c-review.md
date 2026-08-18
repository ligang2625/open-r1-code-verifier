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

## R2 — R1-M1 timing/cost provenance repair review

```yaml
review_record:
  version: 1
  stage_id: WP5-c
  review_round: 2
  source_execution_id: E1
  reviewed_head_commit: 498cfc887e530026dda013bcc1a74e188f38b4dc
  conclusion: pass
```

### Review scope and repair provenance

- Reviewed the new completed repair `E1`, which is correctly bound to committed R1 through `source_review_round=1`, `source_review_commit=0355f95085870179e9980fd1be1c303a3c5fa136`, and `repair_issue_ids=[R1-M1]`.
- Repair history is auditable: `717de9c550f759c3c36e68bbcbf7edefc8bbfbae` implements evaluation timing/cost provenance; C1 was sealed at `a35205a7aa3d47e4102a232ab52741e91e0c4bf4`; `a7033238a0a202084abc2308940955c73fffae90` adds generation-time analysis-readiness provenance without changing the experiment definition; C2 was sealed at `5bdff18b4b88f9a507331ba2e303042a447ca684`; completed E1 is reported by current HEAD `498cfc887e530026dda013bcc1a74e188f38b4dc`.
- Current HEAD changes only `ai-work/executor/WP5-c-executor.md`; the stage was clean at review start and remained at the same HEAD during all reviewer checks.
- This review did not rerun the 400-problem long gate. It independently inspected C2 status/log/script provenance, persistent artifacts and quarantines, and ran only short validation/tests.

### R1-M1 closure

- Fresh evaluation runs now persist immutable timezone-aware `start_time`, completion-only `end_time`, finite non-negative `gpu_hours`, `gpu_count_used`, and explicit `gpu_hours_semantics=persisted_generation_latency_ms_x_gpu_count_used`.
- `created_at == start_time`; completed runs require `end_time >= start_time` and full split completion; incomplete/failed runs require `end_time=null`.
- `gpu_hours` is recomputed from durable result rows, so interrupted work is never guessed. `run_pass1_evaluation()` catches `BaseException`; a real/simulated `KeyboardInterrupt` therefore records the durable prefix as failed before propagating the interrupt.
- Focused tests explicitly cover fresh completion, `KeyboardInterrupt` after one persisted row, exact-prefix resume, immutable start time, cumulative durable-row GPU-hours, and completed zero-generation resume that leaves timing metadata byte-identical.
- The pre-repair formal A run was not edited or backfilled. It remains intact at `/root/sj-tmp/open-r1-code-verifier-outputs/quarantine/WP5-c/R1-M1/A-base-formal-seed42-pre-timing-provenance-cca9945d/`; reviewer independently verified its result SHA256 as `cca9945d28962bcee241cfc69b38ec0c326862e15d9e74f2b5b0354cb01e277e`.
- C1 was intentionally interrupted after seven durable rows and was likewise preserved intact at `/root/sj-tmp/open-r1-code-verifier-outputs/quarantine/WP5-c/R1-M1/C1-pre-analysis-readiness-86d9f030/`; its result SHA256 is `86d9f030c9bcf06bd774d1fd74ace5a1f44b742a632f4d51563261271cc13ae1`. Its `run.json` independently verifies `status=failed`, `end_time=null`, retained `start_time`, `gpu_count_used=1`, and non-fabricated prefix `gpu_hours`.
- The new canonical C2 Base A run was therefore produced fresh under the repaired contract rather than reconstructed from unauditable timing estimates.

### Canonical Base A and analysis-readiness evidence

- C2 operator script SHA256 independently matches checkpoint evidence: `1c561a7f8d23b5a0c14955a8010f924648291a12eee279b58265f0dc50072d2f`; status is `0`; terminal log ends with `evaluated 400 problems (resumed=0, generated=400)` and `long-command-end rc=0`.
- Canonical `run.json` is completed and records `start_time=2026-08-18T05:59:25.773910+00:00`, `end_time=2026-08-18T06:53:54.534608+00:00`, `gpu_count_used=1`, and `gpu_hours=0.4206591900355286`.
- Reviewer independently recomputed `gpu_hours` from all 400 persisted `generation_latency_ms` values and obtained exactly `0.4206591900355286` within the contract's `1e-12` absolute tolerance.
- The canonical run additionally persists `piston_config_sha256=f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e`, independently matching the current sealed Piston YAML. This preserves execution-definition provenance after the stage worktree is removed.
- Every strict result row now contains boolean `hit_max_new_tokens`; all 400 rows pass the strict loader and six rows reached the configured 512-token limit. This is additive telemetry only and does not change decoding.
- The formal experiment definition remains unchanged: same 400 test problems/order, Base model/revision, checkpoint `base`, seed 42, CUDA FP16, greedy decoding, max_new_tokens 512, and loopback Piston.
- Comparing the quarantined pre-repair A with the new canonical A shows zero drift in all prior semantic result fields. All 400 rows differ only in naturally variable `generation_latency_ms` and `runtime_ms`; completion/code/parser/test outcomes/statuses/error categories are identical.
- Strict readback passes for 400 rows and the one-row main CSV. Numerical evidence remains unchanged and finite: Eval-Hidden Pass@1 `0.115`, 95% problem-level bootstrap CI `[0.085, 0.1475]`, visible/train-hidden Pass@1 `0.1225/0.1175`, eval-hidden average test pass rate `0.13875`, and public-eval gap `0.0075`.

### Independent reviewer checks

- `make lint`: PASS — Ruff check/format and strict Mypy passed.
- `make test` with the exact cached 1.5B snapshot: PASS — 887 passed, 3 expected real-Piston opt-in skips, 0 failed.
- `make test-gpu` with the exact cached revision: PASS — 3 passed, 0 failed/skipped.
- First reviewer `make test-piston` attempt produced one transient TIMEOUT for a trivial wrong-answer case while the other eight selected checks passed. Immediate targeted rerun of the same case passed, and a subsequent complete `make test-piston` passed 9/9 with 0 failed/skipped (`2 deselected`). This is consistent with the already-recorded slow SSH-tunnel observation rather than a reproducible source defect.
- Strict result loader / summary / CSV finite-metric readback: PASS.
- Quarantine preservation and recorded hashes: PASS.
- Piston config SHA binding: PASS.

### Non-blocking observations

- Evaluation `gpu_hours` deliberately means persisted model-generation device time, while the existing SFT/GRPO training runners currently accumulate trainer-attempt wall time. Because evaluation stores `gpu_hours_semantics` plus `start_time/end_time`, the evidence is unambiguous and R1-M1 is satisfied; future cross-stage cost analysis must respect these distinct semantics rather than silently treating the raw values as identical accounting definitions.
- The SSH-tunneled Piston service showed one transient timeout during reviewer testing before passing both targeted and complete retries. Future validation stages should continue the existing strict preflight/real-Piston acceptance and should not reinterpret isolated infrastructure latency as candidate behavior without corroborating evidence.
- The repeated Transformers warning about sampling flags remains log noise only; deterministic resolved config and semantic output reproducibility are unaffected.

### Conclusion

R1-M1 is fully resolved without fabricated metadata or loss of prior evidence. The repaired implementation, interruption/resume tests, quarantined history, fresh canonical Base A artifacts, and numerical results satisfy the sealed WP5-c validation acceptance. No actionable blocker/major/minor finding remains for E1.

```yaml
repair_routing:
  version: 1
  required: false
  source_review_round: 2
  mode: null
  complexity: null
  single_class: null
  parallelizability: null
  multi_benefit: null
  independent_workstreams: 0
  repair_issue_ids: []
  rationale:
    - "R1-M1 is closed by auditable timing/cost provenance, explicit interruption semantics, preserved quarantines, and a fresh canonical Base A run with unchanged research outcomes."
    - "No further repair execution is required for the reviewed E1 head."
  workstream_candidates: []
```

## Finalization Record

```yaml
finalization_record:
  version: 1
  stage_id: WP5-c
  review_round: 2
  review_commit: d8f1259bd6684bfe3fa6887a48a99659882d8e26
  merge_commit: 3850416e0cc5b383ad8c5b111c0aa4f9ef106367
  finalized_at: "2026-08-18T15:20:00+08:00"
  status: finalized
```
