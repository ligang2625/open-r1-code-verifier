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
