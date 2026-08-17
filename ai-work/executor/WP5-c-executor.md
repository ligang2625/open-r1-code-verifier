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
