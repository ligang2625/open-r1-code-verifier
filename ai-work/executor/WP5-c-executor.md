# WP5-c Execution Report

## C0 — Base A formal evaluation operator handoff

The Web GPT + CodexPro executor completed the routed implementation work that may run inside the agent session, revalidated the RTX 4090 validation machine, formal data, exact cached model revision, and tunneled Piston runtime, and prepared the sealed `base-a-formal` operator gate. The 400-problem formal evaluation has **not** been started by the executor.

```yaml
execution_checkpoint:
  version: 1
  checkpoint_id: C0
  stage_id: WP5-c
  task_kind: implementation
  source_plan_commit: 34c37aa0a8d8b432cc920aa9e130e986c7e0e27f
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: ca56d8ec422e2037209cf565b517e119d380b269
  interruption_class: operator
  resume_allowed: true
  operator_gate_id: base-a-formal
  operator_restart_policy: exact_rerun
  operator_script: /root/sj-tmp/open-r1-code-verifier-outputs/operator/WP5-c/34c37aa0a8d8b432cc920aa9e130e986c7e0e27f/base-a-formal/C0/run.sh
  operator_script_sha256: 7d49ac99d3f262b203624e224aa0c5a7c004d4f29039ea643434dd6576345b8e
  operator_status_file: /root/sj-tmp/open-r1-code-verifier-outputs/operator/WP5-c/34c37aa0a8d8b432cc920aa9e130e986c7e0e27f/base-a-formal/C0/status
  operator_log_file: /root/sj-tmp/open-r1-code-verifier-outputs/operator/WP5-c/34c37aa0a8d8b432cc920aa9e130e986c7e0e27f/base-a-formal/C0/terminal.log
  expected_artifacts:
    - /root/sj-tmp/open-r1-code-verifier-outputs/evaluation/A-base-formal-seed42/run.json
    - /root/sj-tmp/open-r1-code-verifier-outputs/evaluation/A-base-formal-seed42/resolved_config.yaml
    - /root/sj-tmp/open-r1-code-verifier-outputs/evaluation/A-base-formal-seed42/environment.json
    - /root/sj-tmp/open-r1-code-verifier-outputs/evaluation/A-base-formal-seed42/samples/results.jsonl
    - /root/sj-tmp/open-r1-code-verifier-outputs/evaluation/A-base-formal-seed42/summary.json
    - /root/sj-tmp/open-r1-code-verifier-outputs/evaluation/A-base-formal-seed42/main_results.csv
  completed_scope:
    - validation router/executor preflight: machine record, persistent roots, RTX 4090 24210 MiB, formal-data checksums and 3200/2500/300/400 split, exact offline 1.5B model load, real Piston 9/9, baseline CLI tests
    - step 1: evaluate --dataset-dir override, stderr override audit line, unit coverage, and README operator workflow committed in ca56d8ec422e2037209cf565b517e119d380b269
    - step 1 validation: tests/unit/test_cli.py 61 passed; make lint passed; exact-revision GPU smoke 3/3 passed
    - base-a-formal C0 immutable operator script generated under persistent artifact_root and SHA256 bound
  remaining_scope:
    - operator runs the exact C0 run.sh in a normal terminal or tmux; executor must not run the 400-problem command
    - explicit execution-router resume backend=web validates status, log, and real Base A persistent artifacts
    - completed-run exact-prefix quick resume must report resumed=400 generated=0 with unchanged result rows
    - final executor-owned make lint, make test, make test-gpu, make test-piston and strict artifact readback
    - append completed E0 only after every formal acceptance gate passes
  status: awaiting_operator
```

### Executor-owned evidence before handoff

- Routing source: sealed WP5-c `execution_routing`, `mode=single`, `complexity=normal`; backend `web_codexpro`; effective mode `single`.
- Stage worktree: `/root/sj-tmp/open-r1-code-verifier/.worktrees/wp5-c`, branch `feat/wp5-c`.
- Machine roots: artifact `/root/sj-tmp/open-r1-code-verifier-outputs`, Hugging Face cache `/root/sj-tmp/huggingface`, formal data `/root/sj-tmp/open-r1-code-verifier-data-4090`.
- GPU preflight: PyTorch `2.6.0+cu124`, CUDA `12.4`, NVIDIA GeForce RTX 4090, `24210 MiB` total VRAM.
- Formal data: `sha256sum -c checksums.sha256` passed; `check-data` reported 3200 problems (`train=2500`, `validation=300`, `test=400`).
- Exact model snapshot `Qwen/Qwen2.5-Coder-1.5B-Instruct@2e1fd397ee46e1388853d2af2c993145b0f1098a` loaded offline in FP16 successfully.
- Real tunneled Piston acceptance: 9 passed, 0 failed, 0 skipped (`2 deselected`).
- Baseline CLI preflight before modification: 60 passed. After implementation: CLI suite 61 passed; `make lint` passed; exact-revision `make test-gpu` 3 passed.
- Persistent artifact filesystem probe passed with more than 10 GiB free and more than 100000 free inodes.
- Formal 400-problem evaluation was not executed by Web GPT/CodexPro.

## E0 — Completed implementation after C0 operator resume

The user executed the immutable C0 operator script in a normal terminal. The first manual attempt was interrupted after a small exact-prefix had been persisted; rerunning the same `exact_rerun` script resumed that prefix and completed the formal Base A run. Web GPT + CodexPro then resumed from C0, validated the persistent evidence, performed the required zero-generation exact-prefix check, and ran all executor-owned final acceptance gates.

```yaml
execution_record:
  version: 1
  stage_id: WP5-c
  execution_id: E0
  task_kind: implementation
  source_plan_commit: 34c37aa0a8d8b432cc920aa9e130e986c7e0e27f
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: b9261f4b9343e3e98c78ab0aa3684f11144302b8
  execution_backend: web_codexpro
  effective_execution_mode: single
  resumed_from_checkpoint_id: C0
  resumed_from_checkpoint_commit: b9261f4b9343e3e98c78ab0aa3684f11144302b8
  status: completed
```

### Operator artifact acceptance

- C0 operator status file contained `0`; terminal log ended with `long-command-end rc=0`.
- C0 script SHA256 remained `7d49ac99d3f262b203624e224aa0c5a7c004d4f29039ea643434dd6576345b8e`, exactly matching the committed checkpoint.
- Operator long run reported `evaluated 400 problems (resumed=7, generated=393)` after the interrupted first attempt; this is valid exact-prefix continuation under the sealed `exact_rerun` policy.
- `run.json.status=completed`; model `Qwen/Qwen2.5-Coder-1.5B-Instruct`, revision `2e1fd397ee46e1388853d2af2c993145b0f1098a`, checkpoint `base`, seed `42`.
- `resolved_config.yaml` binds `/root/sj-tmp/open-r1-code-verifier-data-4090/prepared`, `split=test`, `device=cuda`, `do_sample=false`, `temperature=null`, `top_p=null`, `max_new_tokens=512`, `dtype=float16`.
- Strict formal-result readback found exactly 400 records, 400 unique `problem_id` values, and exact order equality with the formal test split.
- Persistent run path: `/root/sj-tmp/open-r1-code-verifier-outputs/evaluation/A-base-formal-seed42`.
- `results.jsonl` SHA256 around the final quick-resume verification remained unchanged at `cca9945d28962bcee241cfc69b38ec0c326862e15d9e74f2b5b0354cb01e277e`.
- Re-running the exact formal command during executor resume returned `evaluated 400 problems (resumed=400, generated=0)`; no sample was regenerated.
- Non-sample payload scan passed for `run.json`, `environment.json`, `resolved_config.yaml`, `metrics.jsonl`, stdout/stderr logs, `summary.json`, and `main_results.csv`.

### Formal Base A numerical evidence

- Total problems: `400`.
- Visible Pass@1: `0.1225`.
- Train-Hidden Pass@1: `0.1175`.
- Eval-Hidden Pass@1: `0.115`.
- Eval-Hidden Pass@1 95% problem-level bootstrap CI: `[0.085, 0.1475]` with 10,000 resamples, seed 42.
- Eval-Hidden average test pass rate: `0.13875` with 95% CI `[0.1075, 0.1725]`.
- Public-eval gap: `0.0075` with 95% CI `[-0.01, 0.025]`.
- Parse success / target-function-found / executable rate: `0.32 / 0.32 / 0.32`.
- Execution status counts: parse_error `272`, passed `46`, runtime_error `13`, timeout `1`, wrong_answer `68`.
- Mean completion tokens: `145.335`; mean generation latency: `3760.4036792676197 ms`; mean execution runtime: `82.11140645750936 ms`.

### Final executor-owned acceptance

- `make lint`: PASS — Ruff check/format and strict Mypy all passed.
- `make test`: PASS — 882 passed, 3 expected real-Piston-disabled skips, 0 failed; CUDA smoke executed inside the default suite.
- `make test-gpu` with the exact cached 1.5B revision: PASS — 3 passed, 0 failed/skipped.
- `make test-piston` against the tunneled loopback service: PASS — 9 selected passed, 0 failed/skipped (`2 deselected`).
- Formal artifact and summary/CSV strict readback: PASS.
- No tracked plan/review/proceedings/third-party files were changed during resume; no formal result/checkpoint was copied into the stage worktree.

## C1 — R1-M1 evaluation timing/cost provenance repair operator handoff

Reviewer round R1 identified one blocking provenance defect: the formal evaluation contract did not persist the specification-required `start_time`, `end_time`, and `gpu_hours`. The repair implements an auditable exact-prefix-safe timing/cost contract, preserves the previous Base A run unchanged because its exact missing timing provenance cannot be reconstructed without fabrication, and prepares a fresh canonical Base A operator run under the repaired code.

```yaml
execution_checkpoint:
  version: 1
  checkpoint_id: C1
  stage_id: WP5-c
  task_kind: repair
  source_plan_commit: 34c37aa0a8d8b432cc920aa9e130e986c7e0e27f
  source_review_round: 1
  source_review_commit: 0355f95085870179e9980fd1be1c303a3c5fa136
  repair_issue_ids:
    - R1-M1
  result_code_commit: 717de9c550f759c3c36e68bbcbf7edefc8bbfbae
  interruption_class: operator
  resume_allowed: true
  operator_gate_id: base-a-formal
  operator_restart_policy: exact_rerun
  operator_script: /root/sj-tmp/open-r1-code-verifier-outputs/operator/WP5-c/34c37aa0a8d8b432cc920aa9e130e986c7e0e27f/base-a-formal/C1/run.sh
  operator_script_sha256: a24e029d39bcdf5a1d7de5a9595c06be316083a480a0af1d59717366e0b6ee81
  operator_status_file: /root/sj-tmp/open-r1-code-verifier-outputs/operator/WP5-c/34c37aa0a8d8b432cc920aa9e130e986c7e0e27f/base-a-formal/C1/status
  operator_log_file: /root/sj-tmp/open-r1-code-verifier-outputs/operator/WP5-c/34c37aa0a8d8b432cc920aa9e130e986c7e0e27f/base-a-formal/C1/terminal.log
  expected_artifacts:
    - /root/sj-tmp/open-r1-code-verifier-outputs/evaluation/A-base-formal-seed42/run.json
    - /root/sj-tmp/open-r1-code-verifier-outputs/evaluation/A-base-formal-seed42/resolved_config.yaml
    - /root/sj-tmp/open-r1-code-verifier-outputs/evaluation/A-base-formal-seed42/environment.json
    - /root/sj-tmp/open-r1-code-verifier-outputs/evaluation/A-base-formal-seed42/samples/results.jsonl
    - /root/sj-tmp/open-r1-code-verifier-outputs/evaluation/A-base-formal-seed42/summary.json
    - /root/sj-tmp/open-r1-code-verifier-outputs/evaluation/A-base-formal-seed42/main_results.csv
  completed_scope:
    - "R1-M1 repair committed in 717de9c550f759c3c36e68bbcbf7edefc8bbfbae: evaluation run.json now records immutable start_time, completion-only end_time, finite non-negative gpu_hours, gpu_count_used, and fixed gpu_hours_semantics derived from persisted generation latency"
    - focused fresh/interrupted/resumed timing tests passed; affected unit set 97 passed; make lint passed; full make test 884 passed with 3 expected Piston-opt-in skips; exact-revision GPU smoke 3/3 passed
    - validation preflight passed on RTX 4090 with formal 3200/2500/300/400 data, exact offline model revision, and real tunneled Piston 9/9; the tunnel was slow but the final full suite completed with no failures/skips
    - pre-repair Base A preserved unchanged at /root/sj-tmp/open-r1-code-verifier-outputs/quarantine/WP5-c/R1-M1/A-base-formal-seed42-pre-timing-provenance-cca9945d with results SHA256 cca9945d28962bcee241cfc69b38ec0c326862e15d9e74f2b5b0354cb01e277e; canonical run path is clear for the repaired fresh run
    - base-a-formal C1 immutable operator script generated under persistent artifact_root, chmod 0555, bash syntax checked, and SHA256 bound
  remaining_scope:
    - operator runs the exact C1 run.sh in a normal terminal or tmux; executor must not run the 400-problem command
    - explicit execution-router resume backend=web validates status/log and repaired Base A artifacts, including start_time/end_time/gpu_hours/gpu_count_used/gpu_hours_semantics against all persisted generation latencies
    - completed-run exact-prefix quick resume must report resumed=400 generated=0 with unchanged results hash and unchanged run.json timing/cost metadata
    - final executor-owned make lint, make test, make test-gpu, make test-piston and strict artifact/payload readback
    - append completed repair E1 only after every R1-M1 and formal acceptance gate passes
  status: awaiting_operator
```

### Repair evidence before C1 handoff

- Routing source: committed R1 `repair_routing`, `mode=single`, `complexity=normal`, issue `R1-M1`; backend `web_codexpro`, effective mode `single`.
- `gpu_hours` semantics are deliberately limited to auditable model-generation device time: sum of persisted per-problem `generation_latency_ms` multiplied by the evaluation GPU count used, divided by 3,600,000. Piston/CPU work, model loading, and interrupted generations that never yielded a durable result row are not guessed into this value.
- Interrupted/resumed runs retain the original `start_time`, use `end_time: null` until full completion, and recompute derived GPU-hours from the durable prefix. A fully completed zero-generation exact-prefix resume returns without rewriting the timing/cost metadata.
- The previous Base A results were not edited or backfilled. Because its first manual attempt was interrupted without a reliable terminal end marker, exact missing timing provenance could not be established without fabrication; the entire prior run was moved intact to the recorded quarantine path before creating C1.
- The formal 400-problem evaluation has **not** been executed by Web GPT/CodexPro for C1.

## C2 — Pre-formal analysis-readiness audit and replacement operator handoff

The user intentionally interrupted C1 after a small prefix and requested a final pre-formal audit focused on preventing later A/B/C/D analysis from discovering irrecoverable missing data. The audit kept the sealed Base A experiment definition unchanged, quarantined the seven-row C1 prefix before changing the strict per-problem schema, and added only WP5 evaluation-side provenance that must be captured at generation time.

```yaml
execution_checkpoint:
  version: 1
  checkpoint_id: C2
  stage_id: WP5-c
  task_kind: repair
  source_plan_commit: 34c37aa0a8d8b432cc920aa9e130e986c7e0e27f
  source_review_round: 1
  source_review_commit: 0355f95085870179e9980fd1be1c303a3c5fa136
  repair_issue_ids:
    - R1-M1
  result_code_commit: a7033238a0a202084abc2308940955c73fffae90
  interruption_class: operator
  resume_allowed: true
  operator_gate_id: base-a-formal
  operator_restart_policy: exact_rerun
  operator_script: /root/sj-tmp/open-r1-code-verifier-outputs/operator/WP5-c/34c37aa0a8d8b432cc920aa9e130e986c7e0e27f/base-a-formal/C2/run.sh
  operator_script_sha256: 1c561a7f8d23b5a0c14955a8010f924648291a12eee279b58265f0dc50072d2f
  operator_status_file: /root/sj-tmp/open-r1-code-verifier-outputs/operator/WP5-c/34c37aa0a8d8b432cc920aa9e130e986c7e0e27f/base-a-formal/C2/status
  operator_log_file: /root/sj-tmp/open-r1-code-verifier-outputs/operator/WP5-c/34c37aa0a8d8b432cc920aa9e130e986c7e0e27f/base-a-formal/C2/terminal.log
  expected_artifacts:
    - /root/sj-tmp/open-r1-code-verifier-outputs/evaluation/A-base-formal-seed42/run.json
    - /root/sj-tmp/open-r1-code-verifier-outputs/evaluation/A-base-formal-seed42/resolved_config.yaml
    - /root/sj-tmp/open-r1-code-verifier-outputs/evaluation/A-base-formal-seed42/environment.json
    - /root/sj-tmp/open-r1-code-verifier-outputs/evaluation/A-base-formal-seed42/samples/results.jsonl
    - /root/sj-tmp/open-r1-code-verifier-outputs/evaluation/A-base-formal-seed42/summary.json
    - /root/sj-tmp/open-r1-code-verifier-outputs/evaluation/A-base-formal-seed42/main_results.csv
  completed_scope:
    - "C1 was intentionally interrupted by the user after 7 durable rows; the entire partial run was preserved at /root/sj-tmp/open-r1-code-verifier-outputs/quarantine/WP5-c/R1-M1/C1-pre-analysis-readiness-86d9f030 with results SHA256 86d9f030c9bcf06bd774d1fd74ace5a1f44b742a632f4d51563261271cc13ae1"
    - "real interruption metadata was verified before quarantine: status=failed, end_time=null, start_time retained, gpu_count_used=1, and gpu_hours exactly matched the 7 persisted rows' generation latency"
    - "analysis-readiness repair committed in a7033238a0a202084abc2308940955c73fffae90: each evaluation row now persists hit_max_new_tokens and run.json persists piston_config_sha256; exact-prefix resume rejects Piston-definition drift"
    - "the experiment definition is unchanged: formal 400-test split, Base model/revision, seed 42, CUDA FP16, deterministic do_sample=false, temperature=null, top_p=null, max_new_tokens=512, and real loopback Piston remain fixed"
    - "scope was explicitly constrained to WP5 evaluation code/tests/README; temporary WP8 analysis-side audit edits were removed before commit so this validation repair does not modify analysis/SFT/GRPO business logic"
    - "validation passed after final scope reduction: focused evaluation tests 84 passed; make lint passed; make test 887 passed with 3 expected Piston-opt-in skips; exact-revision make test-gpu 3/3 passed; real make test-piston 9/9 passed with 0 skipped"
    - "base-a-formal C2 immutable operator script was generated under persistent artifact_root, verifies both prior quarantines plus the new analysis provenance schema, passed bash syntax validation, is chmod 0555, and is SHA256 bound"
  remaining_scope:
    - operator runs the exact C2 run.sh in a normal terminal or tmux; executor must not run the 400-problem command
    - explicit execution-router resume backend=web validates status/log and repaired Base A artifacts, including timing/cost metadata, piston_config_sha256, and hit_max_new_tokens on all 400 strict rows
    - completed-run exact-prefix quick resume must report resumed=400 generated=0 with unchanged results hash and unchanged completed timing/cost metadata
    - final executor-owned make lint, make test, make test-gpu, make test-piston and strict artifact/payload/readiness readback
    - append completed repair E1 only after every R1-M1/formal/data-readiness acceptance gate passes
  status: awaiting_operator
```

### Data-readiness audit conclusions before C2

- The canonical evaluation row now permanently preserves the model output and all irrecoverable generation-time facts needed by the current research design: `completion`, `extracted_code`, parser status/error, three-layer pass rates/status/failure counts, generation latency, completion-token count, `hit_max_new_tokens`, total verification runtime, automatic error category, and run/model/checkpoint/dataset/config/problem/prompt identities.
- Run-level persistent provenance includes resolved config, environment/package/GPU/CUDA identity, project/Open-R1/dependency identity, immutable `start_time`, completion-only `end_time`, exact-prefix-safe `gpu_hours`, `gpu_count_used`, `gpu_hours_semantics`, and `piston_config_sha256`. The latter is important because `resolved_config.yaml` contains the stage-worktree-local Piston path, while the SHA remains usable after stage finalization removes that worktree.
- Data that is intentionally not duplicated in result rows remains recoverable without model reruns: difficulty/category and exact visible/hidden test payloads remain in the checksummed formal prepared dataset and can be joined by `problem_id`; prompt text is deterministic from that dataset and the pinned prompt builder; tokenizer/model generation configuration is traceable to the exact pinned model revision. Per-test forensic replay, if ever needed, requires only Piston re-execution of the already-persisted candidate code, not model generation or training.
- The local Qwen snapshot carries inherited generation defaults including `repetition_penalty=1.1`; the project explicitly fixes greedy decoding and the same pinned base revision is used for A and for the base underlying B/C/D PEFT evaluation. No decode parameter was changed in this audit, avoiding an unplanned experiment-definition change.

### Forward validation-readiness notes — must be resolved before formal SFT/GRPO

These observations are deliberately **not modified in WP5-c** because SFT/GRPO are outside this stage plan, but they are persisted here so they cannot be lost when the next validation stages are planned:

- Formal SFT/GRPO operator stages must re-audit manual interruption accounting before the first optimizer run. The current training runners catch ordinary `Exception`; a terminal `KeyboardInterrupt`/SIGINT path should be explicitly tested so interrupted attempts cannot lose timing/GPU-hour provenance across trainer-checkpoint resume.
- Before formal GRPO, verify the §12.3 telemetry inventory against real pinned TRL logs and custom artifacts: loss/reward and reward components, group mean/std/all-equal rate, completion length/truncation, parse/executable/timeout rates, verifier pass rates, KL, step/rollout/executor timing, peak GPU memory, and cumulative GPU-hours. Any telemetry that TRL does not guarantee must be persisted before C/D are allowed to run formally.
- WP8 final analysis should be updated to consume the evaluation run's stored `piston_config_sha256` rather than reopening the ephemeral absolute Piston-config path from `resolved_config.yaml`. This is a future analysis-code change only; the necessary immutable data is now captured by C2, so it will not require rerunning A/B/C/D.

- The formal 400-problem evaluation has **not** been executed by Web GPT/CodexPro for C2.

## E1 — Completed R1-M1 repair after C2 operator resume

```yaml
execution_record:
  version: 1
  stage_id: WP5-c
  execution_id: E1
  task_kind: repair
  source_plan_commit: 34c37aa0a8d8b432cc920aa9e130e986c7e0e27f
  source_review_round: 1
  source_review_commit: 0355f95085870179e9980fd1be1c303a3c5fa136
  repair_issue_ids:
    - R1-M1
  result_code_commit: 5bdff18b4b88f9a507331ba2e303042a447ca684
  execution_backend: web_codexpro
  effective_execution_mode: single
  resumed_from_checkpoint_id: C2
  resumed_from_checkpoint_commit: 5bdff18b4b88f9a507331ba2e303042a447ca684
  status: completed
```

### Completed repair evidence

- Routing source remained the committed R1 `repair_routing`: `mode=single`, `complexity=normal`, issue `R1-M1`; Web runtime therefore used `effective_execution_mode=single` without modifying the sealed review routing.
- Resume provenance is exact: current checkpoint commit `5bdff18b4b88f9a507331ba2e303042a447ca684` has parent `a7033238a0a202084abc2308940955c73fffae90`, changes only `ai-work/executor/WP5-c-executor.md`, and C2 script SHA256 remained `1c561a7f8d23b5a0c14955a8010f924648291a12eee279b58265f0dc50072d2f`.
- C2 operator terminal status is `0`. Its append-only log records `evaluated 400 problems (resumed=0, generated=400)` and `2026-08-18T06:54:13Z long-command-end rc=0`; Web GPT/CodexPro did not run that long command.
- Router/stage validation preflight passed on the recorded RTX 4090 machine: PyTorch `2.6.0+cu124`, CUDA `12.4`, NVIDIA GeForce RTX 4090, 22683 MiB reported total VRAM; persistent roots remained `/root/sj-tmp/open-r1-code-verifier-outputs`, `/root/sj-tmp/huggingface`, and `/root/sj-tmp/open-r1-code-verifier-data-4090` outside the stage worktree.
- Canonical Base A run is `/root/sj-tmp/open-r1-code-verifier-outputs/evaluation/A-base-formal-seed42`. `run.json.status=completed`, start/end are `2026-08-18T05:59:25.773910+00:00` / `2026-08-18T06:53:54.534608+00:00`, `gpu_count_used=1`, and `gpu_hours=0.4206591900355286` exactly equals the sum of all persisted per-problem generation latencies divided by 3,600,000.
- Run identities are fixed and accepted: dataset hash `770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae`; config hash `fd1aaebe1b076c9a062826eae32bb94e2e0caf20b876ac7ddd3911bb65ab7d32`; model `Qwen/Qwen2.5-Coder-1.5B-Instruct@2e1fd397ee46e1388853d2af2c993145b0f1098a`; checkpoint `base`; seed `42`; Open-R1 commit `1416fa0cf21595d2083b399a2a0bbddd7f6e9563`; dependency lock hash `59e6292f72bdc6f7f9d889d1969d87715c83ccb09ed95766a50f81d9d762d560`; Piston config SHA256 `f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e`.
- Strict result readback passed: exactly 400 rows, 400 unique problem IDs, exact order equality with the formal test split, and all rows satisfy the new `hit_max_new_tokens` boolean contract. Six of 400 completions reached the configured 512-token generation limit.
- Formal result SHA256 is `3c512ea6aeb160efa865e7b00c52a7494929f68d9bf10683b8746c6eac2d411b`. Pre-resume `run.json`, `summary.json`, and `main_results.csv` SHA256 values were `68a11f5d53f36c007bf246d1817e3dec334cca504685c6d5ea280bcadd90678a`, `46b882aedad073692ec67b80c1350f1848c6dcb74fa79c17398d2e3f871edf3a`, and `8b432dc133197c7e0e0db293a932ffbadf32aec86a2d5dc6a26bbf0c7c4f99f6`.
- Executor-owned exact-prefix verification used the same env/config/dataset/model/run-name/seed and returned `evaluated 400 problems (resumed=400, generated=0)`. The result/run/summary/CSV SHA256 values above were unchanged after this zero-generation verification.
- Formal numerical evidence remains finite and consistent: Eval-Hidden Pass@1 `0.115` with 95% problem-level bootstrap CI `[0.085, 0.1475]`; visible/train-hidden Pass@1 `0.1225/0.1175`; eval-hidden average test pass rate `0.13875`; public-eval gap `0.0075`; bootstrap uses 10,000 problem-level resamples with seed 42.
- Non-sample payload scan passed across run/environment/resolved-config/metrics/stdout/stderr/summary/main-results artifacts; completion/code/hidden-test/reference/starter/SFT-response payload fields remain confined to the intended sample/result or source-data boundaries.
- Final executor-owned acceptance after operator resume: `make lint` PASS; `make test` PASS with 887 passed, 3 expected real-Piston opt-in skips, 0 failed; exact-revision `make test-gpu` PASS with 3/3; real loopback `make test-piston` PASS with 9/9 selected passed, 0 failed/skipped (`2 deselected`).
- R1-M1 is therefore completed without fabricating old timing data: the old formal evidence and the intentionally interrupted C1 prefix remain quarantined with their recorded hashes, while the new canonical C2 run supplies the required timing/cost and analysis-readiness provenance.
