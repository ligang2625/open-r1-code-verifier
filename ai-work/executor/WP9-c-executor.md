# WP9-c Execution Report

## Execution context

- Stage: `WP9-c`
- Task kind: `implementation`
- Source plan commit: `5a1f083af6bfdf2e1333bd70e95e9257b4e66b48`
- Branch/worktree: `feat/wp9-c` / `/home/dzy/open-r1-code-verifier/.worktrees/wp9-c`
- Backend: `web_codexpro`
- Source routing: `single / difficult_serial`
- Effective execution mode: `single`
- Stage profile: `validation`
- Control plane: GTX 1660 Ti (6GB)
- Target hardware: 24GB GPU / RTX 4090 operator boundary

## Control-plane implementation and preflight

The execution started from the sealed plan baseline `5a1f083af6bfdf2e1333bd70e95e9257b4e66b48`. Primary and stage `.ai-bridge/**` tracked sets were empty; the stage `.venv` resolved both `code_verifier` and `open_r1` into the WP9-c worktree and provided ruff, mypy, and pytest.

WP9-c step 1 added six bounded validation configs plus static contract coverage. k=8 benchmark configs use `num_generations=8`, `max_steps=20`; the controlled k=4 diagnostic uses the same bounded scientific/runtime settings except `num_generations=4` and run identity; k=8 pilot configs use `max_steps=100`. Legacy k=4 and formal k=8/300-step configs remain unchanged.

Code/config commits before the first operator gate:

- `59b8c08` — `wp9c: add bounded refresh validation configs`
- `e929e51` — `wp9c: type validation config helper`

Verification before target handoff:

- WP9-c focused suite: `98 passed`.
- `make lint`: PASS after adding the missing test helper return annotation; ruff check/format and strict mypy all pass over 136 files.
- `make test`: `1189 passed, 3 skipped`; skips are only the existing opt-in real-Piston tests.
- Production `check-refresh-data` against `/home/dzy/wp9a-refresh-seed42-r2e2-final4` and `/home/dzy/wp6d-b-export/required/formal-data/prepared`: PASS with selected `10000`, external retained `9565`, SFT overlap `750/10000`, quality-gate-required `1086`.

## Formal calibration input

A first materialization attempt under `/home/dzy/wp9c-control/...` failed before publication because the requested atomic temporary-sibling parent did not exist. No calibration artifact was published by that attempt. A fresh run used the existing external parent `/home/dzy` and successfully published:

`/home/dzy/wp9c-calibration-input-e929e51`

Strict `_load_input_bundle()` readback confirms:

- schema: `wp9b-calibration-v1`
- evidence class: `formal_input`
- seed: `42`
- record count: `10000`
- input manifest SHA256: `3eeee5ffea63904e3bd714d275147cd9df438aa3332f49bfd99d7398d71571d3`
- inputs JSONL SHA256: `86f385a03836d731aa5d03b268f3880ad1e2ac9dccc7c391a8b97d6a9668b682`
- problem/order SHA256: `355cfec302a38c3c05e4237be178c5f34207cabb432d2b65f1b4a027cf42d001`
- WP9-a root manifest SHA256: `98a0fb8192661f6358c29819d8a70eb4039397cc2a3ec5444f0581cfbcb81625`
- WP9-a selected IDs/order SHA256: `355cfec302a38c3c05e4237be178c5f34207cabb432d2b65f1b4a027cf42d001`

Formal B was independently strict-loaded from the control-plane backup before constructing the handoff. Frozen identity: run `B-sft-formal-seed42`, model `Qwen/Qwen2.5-Coder-1.5B-Instruct`, revision `2e1fd397ee46e1388853d2af2c993145b0f1098a`, dataset hash `4b90cf95de2d8f12bdc98decbfb712b8eacf5987b02b02b868075ed9ca69eb0c`, config hash `250fbc15ececb040d2b90d3cb1606e412d1256e10ab9063c073c4ad2b1fb5244`, dependency-lock hash `59e6292f72bdc6f7f9d889d1969d87715c83ccb09ed95766a50f81d9d762d560`, seed `42`.

## C0 — Gate A operator handoff

The Web executor does not run the 24GB command. C0 is a tracked portable-target checkpoint. The target script resolves the target machine record at runtime, validates the exact checkpoint commit and script SHA, clean checkout, stage provenance, RTX 4090 >=22528 MiB and BF16, stage-local runtime identity, persistent roots, local-only formal model revision/weights, strict formal B, the exact synced Public-safe calibration input, and the 30 GiB / 100000-inode storage gate. It then runs production `generate-refresh-calibration --block initial` and performs a strict 10,000-problem / 80,000-record postcheck before writing operator evidence.

For a matching interrupted output, production exact-prefix resume is permitted. An incompatible or malformed pre-existing output is preserved under the target quarantine root before a fresh attempt; it is never silently overwritten.

```yaml
execution_checkpoint:
  version: 1
  stage_id: WP9-c
  checkpoint_id: C0
  task_kind: implementation
  source_plan_commit: 5a1f083af6bfdf2e1333bd70e95e9257b4e66b48
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: e929e515d25c43c15193058d24fc2a3d6670c3da
  execution_backend: web_codexpro
  effective_execution_mode: single
  interruption_class: operator
  operator_gate_id: wp9c-calibration-initial-generation
  operator_handoff_mode: portable_target
  operator_restart_policy: exact_rerun
  operator_script: ai-work/executor/operator/WP9-c/wp9c-calibration-initial-generation/C0/run.sh
  operator_script_sha256: a992dd71807ce131dbca7f5625aa10beedcdd584a1bcb1d556561b9033f844ed
  calibration_config_sha256: 4f658443d0296fbc9da206e9f75ece07c4ceb544d66a3e93eacedf89722fab0e
  control_plane_input_bundle: /home/dzy/wp9c-calibration-input-e929e51
  target_input_bundle: $CODE_VERIFIER_DATA_ROOT/wp9c/calibration-input
  input_manifest_sha256: 3eeee5ffea63904e3bd714d275147cd9df438aa3332f49bfd99d7398d71571d3
  input_records_sha256: 86f385a03836d731aa5d03b268f3880ad1e2ac9dccc7c391a8b97d6a9668b682
  input_problem_order_sha256: 355cfec302a38c3c05e4237be178c5f34207cabb432d2b65f1b4a027cf42d001
  wp9a_manifest_sha256: 98a0fb8192661f6358c29819d8a70eb4039397cc2a3ec5444f0581cfbcb81625
  wp9a_selected_order_sha256: 355cfec302a38c3c05e4237be178c5f34207cabb432d2b65f1b4a027cf42d001
  formal_b_run_name: B-sft-formal-seed42
  expected_target_output: $CODE_VERIFIER_ARTIFACT_ROOT/wp9c/calibration/initial
  expected_artifacts:
    - $CODE_VERIFIER_ARTIFACT_ROOT/wp9c/calibration/initial/run.json
    - $CODE_VERIFIER_ARTIFACT_ROOT/wp9c/calibration/initial/samples/generations.jsonl
    - $CODE_VERIFIER_ARTIFACT_ROOT/operator/WP9-c/5a1f083af6bfdf2e1333bd70e95e9257b4e66b48/wp9c-calibration-initial-generation/C0/operator-evidence.json
    - $CODE_VERIFIER_ARTIFACT_ROOT/operator/WP9-c/5a1f083af6bfdf2e1333bd70e95e9257b4e66b48/wp9c-calibration-initial-generation/C0/postcheck-summary.json
  control_plane_evidence_receive_dir: /home/dzy/wp9c-operator-evidence/WP9-c/wp9c-calibration-initial-generation/C0
  completed_scope:
    - bounded WP9-c validation configs and static contract tests
    - focused/lint/full control-plane acceptance
    - strict WP9-a formal-data readback
    - frozen Public-safe 10,000-record calibration input bundle
    - Gate A portable operator script preparation
  remaining_scope:
    - accept Gate A operator evidence and sync the complete immutable generation bundle to the control plane
    - run initial dual-verifier Piston scoring at workers=8 and derive retry manifest
    - conditionally execute retry generation/scoring and freeze the 3,000-problem active pool
    - run evaluation generation/verification benchmark sweep
    - run GRPO throughput benchmark and freeze benchmark report
    - run k=8 Public/Hidden pilot and zero-variance gate
    - complete WP9-c execution inventory and ready_for_wp9d decision
  blocker: manual RTX 4090 Gate A execution and evidence/artifact return are required
  status: awaiting_operator
```
