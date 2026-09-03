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

## C1 — Gate A pre-execution audit and hardened operator handoff

Before any RTX 4090 execution, C0 was re-audited for fatal portability, path-binding, integrity, and restart defects. No C0 target evidence had been accepted. The audit found that the original checkpoint-parent/scope assertion would make a repaired handoff self-reject, that production resume did not accept the zero-record durable prefix, that a completed bundle could be rehashed instead of being strictly reused, and that a rerun could temporarily leave stale canonical success status/evidence visible. C0 is therefore superseded before target execution; it remains immutable history and must not be used for the formal Gate A run.

The production resume implementation was hardened in `eca10bc179d65aa6600500897dd11f82ab7f27c0` (`wp9c: harden calibration generation resume`). New tests cover interruption before the first k=8 group, interruption after one complete k=8 group, idempotent completed reuse, and rejection of a tampered completed bundle. Post-fix verification: calibration unit suite `18 passed`; focused WP9-b/WP9-c suite `23 passed`; `make lint` PASS; full `make test` `1192 passed, 3 skipped` with the same three explicit opt-in real-Piston skips.

C1 contains no `/home/...` or `1660` target path. Target roots are resolved only from the RTX 4090 validation-machine record (or an explicit `CODE_VERIFIER_VALIDATION_MACHINE`). The operator must provide `WP9C_HANDOFF_COMMIT=<exact final C1 handoff SHA>`; C1 proves target `HEAD` equals that SHA, proves the hardened result-code commit and target bootstrap are ancestors, keeps the sealed plan unchanged, requires a clean checkout with `.ai-bridge` untracked, verifies the tracked executable script SHA, checks RTX 4090/BF16/runtime/dependency identity, strict-loads the exact input and formal B, verifies the formal B adapter bytes and pinned base-model weights, enforces storage, and performs strict output classification before generation.

Restart policy is fail-closed: a valid running output must be an exact complete k=8 prefix (including ordered IDs/indices, deterministic sample seeds, exact fields, and finite typed telemetry); a valid completed output is strict-loaded against its original record hash and reused without generation; malformed or identity-mismatched output is preserved under quarantine before a fresh run. Previous canonical C1 status/evidence/postcheck files are moved to attempt-specific history before each attempt so a killed rerun cannot expose a stale success marker.

```yaml
execution_checkpoint:
  version: 1
  stage_id: WP9-c
  checkpoint_id: C1
  task_kind: implementation
  source_plan_commit: 5a1f083af6bfdf2e1333bd70e95e9257b4e66b48
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: eca10bc179d65aa6600500897dd11f82ab7f27c0
  execution_backend: web_codexpro
  effective_execution_mode: single
  interruption_class: operator
  operator_gate_id: wp9c-calibration-initial-generation
  operator_handoff_mode: portable_target
  operator_restart_policy: exact_prefix_or_strict_completed_reuse
  operator_commit_binding: runtime_WP9C_HANDOFF_COMMIT_must_equal_target_HEAD
  operator_script: ai-work/executor/operator/WP9-c/wp9c-calibration-initial-generation/C1/run.sh
  operator_script_sha256: 8f52b0419a171227a6ff3b5ddcc60d65c17d33f1a7d19dc879921c23f6631c52
  calibration_config_sha256: 4f658443d0296fbc9da206e9f75ece07c4ceb544d66a3e93eacedf89722fab0e
  control_plane_input_bundle: /home/dzy/wp9c-calibration-input-e929e51
  target_input_bundle: $CODE_VERIFIER_DATA_ROOT/wp9c/calibration-input
  input_manifest_sha256: 3eeee5ffea63904e3bd714d275147cd9df438aa3332f49bfd99d7398d71571d3
  input_records_sha256: 86f385a03836d731aa5d03b268f3880ad1e2ac9dccc7c391a8b97d6a9668b682
  input_problem_order_sha256: 355cfec302a38c3c05e4237be178c5f34207cabb432d2b65f1b4a027cf42d001
  wp9a_manifest_sha256: 98a0fb8192661f6358c29819d8a70eb4039397cc2a3ec5444f0581cfbcb81625
  wp9a_selected_order_sha256: 355cfec302a38c3c05e4237be178c5f34207cabb432d2b65f1b4a027cf42d001
  formal_b_run_name: B-sft-formal-seed42
  formal_b_adapter_model_sha256: 51042ea9c52d2d24976c2ca4e777f1a5f792e3943ff171d03e55b959463a7a67
  formal_b_adapter_config_sha256: 3738f9ef0ac56f90a48497ab4c0a1f172770864aa61dad56e8d9751050f34344
  expected_target_output: $CODE_VERIFIER_ARTIFACT_ROOT/wp9c/calibration/initial
  expected_artifacts:
    - $CODE_VERIFIER_ARTIFACT_ROOT/wp9c/calibration/initial/run.json
    - $CODE_VERIFIER_ARTIFACT_ROOT/wp9c/calibration/initial/samples/generations.jsonl
    - $CODE_VERIFIER_ARTIFACT_ROOT/operator/WP9-c/5a1f083af6bfdf2e1333bd70e95e9257b4e66b48/wp9c-calibration-initial-generation/C1/operator-evidence.json
    - $CODE_VERIFIER_ARTIFACT_ROOT/operator/WP9-c/5a1f083af6bfdf2e1333bd70e95e9257b4e66b48/wp9c-calibration-initial-generation/C1/postcheck-summary.json
  control_plane_evidence_receive_dir: /home/dzy/wp9c-operator-evidence/WP9-c/wp9c-calibration-initial-generation/C1
  completed_scope:
    - bounded WP9-c validation configs and static contract tests
    - hardened calibration exact-prefix/completed reuse semantics and regression tests
    - focused/lint/full control-plane acceptance after resume hardening
    - strict WP9-a formal-data and Public-safe 10,000-record input readback
    - C1 portable operator pre-execution audit and hardening
  remaining_scope:
    - accept C1 Gate A operator evidence and sync the complete immutable generation bundle to the control plane
    - run initial dual-verifier Piston scoring at workers=8 and derive retry manifest
    - conditionally execute retry generation/scoring and freeze the 3,000-problem active pool
    - run evaluation generation/verification benchmark sweep
    - run GRPO throughput benchmark and freeze benchmark report
    - run k=8 Public/Hidden pilot and zero-variance gate
    - complete WP9-c execution inventory and ready_for_wp9d decision
  blocker: manual RTX 4090 C1 Gate A execution and evidence/artifact return are required
  status: awaiting_operator
```

## C2 — Gate A streaming/batched generation hardening

Before any RTX 4090 Gate A execution, C1 was superseded by a second pre-execution engineering audit. No C1 target evidence or formal generation bundle has been accepted. The audit found two scale hazards in the production path: each completed k=8 problem group rewrote the entire growing `generations.jsonl` (quadratic cumulative serialization/write cost), and the 10,000 problems were issued as 10,000 serial `model.generate()` calls. It also found two correctness defects that would affect formal calibration telemetry/protocol: the exact Qwen revision carries generation defaults `top_k=20` and `repetition_penalty=1.1`, which were not part of the WP9 calibration protocol, and padded k=8 output width could overstate per-completion token/truncation telemetry.

Production commit `972dc7e47479da4f01aebc6143a9d67d993f76da` (`wp9c: batch and stream calibration generation`) fixes those defects before formal generation. Running generation now appends only newly completed problem batches, `fsync`s the JSONL bytes, and then atomically advances `samples/progress.json` with the committed record/byte boundary. Resume truncates only an uncommitted append tail and validates the committed exact prefix. Completed bundles strict-load both the original record hash and the final progress marker. Formal C2 fixes `problem_batch_size=4`: four prompts are generated in one model call, each retaining its own deterministic per-problem RNG stream and ordered k=8 rows. The batched sampler applies exactly the configured `temperature=0.8` and `top_p=0.95` while explicitly neutralizing the model revision's undeclared `top_k` and repetition penalty. Sampled completion telemetry is counted per sequence through its first EOS rather than from padded group width.

The custom batched sampling processor was checked against Transformers 4.52.3's own temperature/top-p warpers, and independent per-problem RNG streams are covered by regression tests. A real `Qwen2ForCausalLM` tiny-model `GenerationMixin` smoke also exercised two batched prompts / 16 sampled rows through the production generator: repeated batched runs reproduced identical completion/token/truncation outputs, and each batched problem group was exactly equal to a separate serial `generate_group` call with the same per-problem seed. Persistence tests cover append-only generation, exact ordering under multi-problem batches, committed progress-marker integrity, and recovery that discards only an uncommitted tail. Verification after the complete repair: focused sampling/calibration suite `75 passed`; broader WP9-b/calibration/generation/CLI suite `160 passed`; `make lint` PASS; full `make test` `1199 passed, 3 skipped`, with the same three explicit opt-in real-Piston skips.

C2 retains the C1 portability/integrity gates and strengthens output handling for the new persistence contract. A valid running output is recovered through production's progress-marker loader before exact-prefix validation; an old C1-format or otherwise identity-incompatible output is quarantined rather than resumed. A completed output must strict-load the progress marker and immutable record hash before reuse. The final script audit additionally rejects duplicate-key/ambiguous validation-machine JSON and TSV-breaking control characters, requires the referenced readiness record itself to be strict JSON containing `READY_FOR_VALIDATION_PLANNER`, and holds both a gate-wide lock and the superseded C0/C1 lock files so an old checkpoint cannot run concurrently against the same output. The exact local-only model snapshot is now byte-bound beyond `model.safetensors`: `config.json`, `generation_config.json`, `tokenizer.json`, `tokenizer_config.json`, `vocab.json`, and `merges.txt` are all SHA256-checked before generation, closing tokenizer/chat-template/config cache drift. The final postcheck requires the exact 10,000-problem/80,000-record flat order, k=8 indices/seeds, exact record fields, `problem_batch_size=4`, per-sequence token counts in `[0, 512]`, truncation consistency, finite latency, and final progress marker `version=1 / record_count=80000 / byte_count=<generation file size>`. `samples/progress.json` is therefore a required returned artifact.

```yaml
execution_checkpoint:
  version: 1
  stage_id: WP9-c
  checkpoint_id: C2
  task_kind: implementation
  source_plan_commit: 5a1f083af6bfdf2e1333bd70e95e9257b4e66b48
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: 972dc7e47479da4f01aebc6143a9d67d993f76da
  execution_backend: web_codexpro
  effective_execution_mode: single
  interruption_class: operator
  operator_gate_id: wp9c-calibration-initial-generation
  operator_handoff_mode: portable_target
  operator_restart_policy: exact_prefix_or_strict_completed_reuse
  operator_commit_binding: runtime_WP9C_HANDOFF_COMMIT_must_equal_target_HEAD
  operator_script: ai-work/executor/operator/WP9-c/wp9c-calibration-initial-generation/C2/run.sh
  operator_script_sha256: 8ec34db2b4cdce28eb994244b35c462e6d3ac421d162804b8c124297d0d092c2
  calibration_config_sha256: 4f658443d0296fbc9da206e9f75ece07c4ceb544d66a3e93eacedf89722fab0e
  problem_batch_size: 4
  control_plane_input_bundle: /home/dzy/wp9c-calibration-input-e929e51
  target_input_bundle: $CODE_VERIFIER_DATA_ROOT/wp9c/calibration-input
  input_manifest_sha256: 3eeee5ffea63904e3bd714d275147cd9df438aa3332f49bfd99d7398d71571d3
  input_records_sha256: 86f385a03836d731aa5d03b268f3880ad1e2ac9dccc7c391a8b97d6a9668b682
  input_problem_order_sha256: 355cfec302a38c3c05e4237be178c5f34207cabb432d2b65f1b4a027cf42d001
  wp9a_manifest_sha256: 98a0fb8192661f6358c29819d8a70eb4039397cc2a3ec5444f0581cfbcb81625
  wp9a_selected_order_sha256: 355cfec302a38c3c05e4237be178c5f34207cabb432d2b65f1b4a027cf42d001
  formal_b_run_name: B-sft-formal-seed42
  formal_b_adapter_model_sha256: 51042ea9c52d2d24976c2ca4e777f1a5f792e3943ff171d03e55b959463a7a67
  formal_b_adapter_config_sha256: 3738f9ef0ac56f90a48497ab4c0a1f172770864aa61dad56e8d9751050f34344
  base_model_weights_sha256: c1b9b30e907950516ba3c646bdf570d8084c25a6410a0cdca80cf04b11bc13a8
  base_model_config_sha256: 88f9a17863c05fb313515d2ff74b1098e0c35579f99068e32beda00618508ae0
  base_model_generation_config_sha256: 1a628a5775bc69cde01c6749a531150ca4d3189652c618a174f7077923acf3b1
  base_model_tokenizer_sha256: c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539
  base_model_tokenizer_config_sha256: 959e7f1d9a1b7641a6d6ce05ca97b75c7894fcb66cbe5a040406458fb1128ee4
  base_model_vocab_sha256: ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910
  base_model_merges_sha256: 599bab54075088774b1733fde865d5bd747cbcc7a547c5bc12610e874e26f5e3
  expected_target_output: $CODE_VERIFIER_ARTIFACT_ROOT/wp9c/calibration/initial
  expected_artifacts:
    - $CODE_VERIFIER_ARTIFACT_ROOT/wp9c/calibration/initial/run.json
    - $CODE_VERIFIER_ARTIFACT_ROOT/wp9c/calibration/initial/samples/generations.jsonl
    - $CODE_VERIFIER_ARTIFACT_ROOT/wp9c/calibration/initial/samples/progress.json
    - $CODE_VERIFIER_ARTIFACT_ROOT/operator/WP9-c/5a1f083af6bfdf2e1333bd70e95e9257b4e66b48/wp9c-calibration-initial-generation/C2/operator-evidence.json
    - $CODE_VERIFIER_ARTIFACT_ROOT/operator/WP9-c/5a1f083af6bfdf2e1333bd70e95e9257b4e66b48/wp9c-calibration-initial-generation/C2/postcheck-summary.json
  control_plane_evidence_receive_dir: /home/dzy/wp9c-operator-evidence/WP9-c/wp9c-calibration-initial-generation/C2
  control_plane_generation_receive_dir: /home/dzy/wp9c-calibration-initial-C2
  completed_scope:
    - bounded WP9-c validation configs and static contract tests
    - hardened exact-prefix/completed-reuse semantics from C1
    - append-only crash-safe calibration generation with atomic committed progress marker
    - four-problem batched k8 generation with independent deterministic problem RNG streams
    - neutralized undeclared Qwen sampling defaults and corrected per-sequence token/truncation telemetry
    - focused/broader/lint/full control-plane acceptance after C2 production hardening
    - strict WP9-a formal-data and Public-safe 10,000-record input readback
    - strict validation-machine/readiness parsing, cross-checkpoint locking, and complete runtime model/tokenizer snapshot byte binding
    - C2 portable operator pre-execution audit and hardening
  remaining_scope:
    - accept C2 Gate A operator evidence and sync the complete immutable generation bundle to the control plane
    - run initial dual-verifier Piston scoring at workers=8 and derive retry manifest
    - conditionally execute retry generation/scoring and freeze the 3,000-problem active pool
    - run evaluation generation/verification benchmark sweep
    - run GRPO throughput benchmark and freeze benchmark report
    - run k=8 Public/Hidden pilot and zero-variance gate
    - complete WP9-c execution inventory and ready_for_wp9d decision
  blocker: manual RTX 4090 C2 Gate A execution and evidence/artifact return are required
  status: awaiting_operator
```


## C2 target failure and user-directed repair continuation

C2 was executed manually on the certified RTX 4090 target at detached handoff `e3c952fc9780138fa8d1332cc374da9d07ee347b`; this target execution is now accepted as failure evidence, not as a successful Gate A artifact. The C2 preflight passed the exact handoff, formal 10,000-record input, strict formal B, pinned Qwen snapshot bytes, RTX 4090/CUDA/BF16, and dependency identity gates. Generation then started with `problem_batch_size=4`, k=8, and `max_new_tokens=512` and crash-safely committed 96 records for 12 complete problems before the next batch failed with `OutOfMemoryError`.

Read-only target audit of the preserved canonical C2 output `/root/sj-tmp/open-r1-code-verifier-outputs/wp9c/calibration/initial` found `run.json` status `running`, C2 identity `problem_batch_size=4`, old input manifest SHA `3eeee5ffea63904e3bd714d275147cd9df438aa3332f49bfd99d7398d71571d3`, old records SHA `86f385a03836d731aa5d03b268f3880ad1e2ac9dccc7c391a8b97d6a9668b682`, and old problem-order SHA `355cfec302a38c3c05e4237be178c5f34207cabb432d2b65f1b4a027cf42d001`. `samples/progress.json` is `{version: 1, record_count: 96, byte_count: 110037}`; `generations.jsonl` is 110037 bytes with SHA256 `b218d3437ceb495c31a89cbaf36a5ee30224bb2ef00e55d0def6e8d9edb8cfad`; `run.json` SHA256 is `823a8d6a738ddf3e905d43c2d390da3f9b449b07404f2d76cf60bb7b5db07b0f`; and `progress.json` SHA256 is `a81f8e46efe27cde3fd00aea48bdb325cae45051b4620a0e8899c2aa19c98e5b`. The target checkout remained clean after the failed attempt.

C2 operator evidence records `command_rc=2`, `postcheck_rc=125`, and `gate_status=internal_error`, but the terminal log proves the actual command failure was `model sampled batch generation failed: OutOfMemoryError`. The mismatch is an operator-classification defect: the C2 `ERR` trap fires for the nonzero generation command before the intended explicit `COMMAND_RC` handling. C3 therefore places the generation command in a shell conditional so an expected nonzero CLI result is captured and finalized as `gate_status=command_failed`; unexpected shell errors and INT/TERM signals remain fail-closed through the existing traps. The postcheck command uses the same conditional form so a postcheck failure is classified as `postcheck_failed` rather than `internal_error`.

The observed OOM is not only a batch-size issue. Exact Qwen tokenizer plus the production chat template showed an extreme long-tail in the immutable WP9-a 10,000-problem authority, including a prompt near 32,358 tokens at the failure neighborhood and prompts far beyond the model context limit. The user explicitly overrides the sealed plan wording that required the WP9-c initial calibration input itself to remain exactly 10,000 problems: the WP9-a 10,000-record authority/provenance remains immutable, while WP9-c calibration may deterministically exclude prompts whose exact rendered prompt exceeds 2,048 tokens. This user override controls this continuation and does not modify the sealed plan.

Production repair commit `9cd10261f4fd3b47135c65154c7a8aca930c29ac` (`wp9c: filter oversized calibration prompts`) adds the frozen tracked `max_prompt_tokens: 2048` protocol, exact formal-B tokenizer/revision chat-template counting, deterministic survivor-order preservation, `excluded_context.jsonl`, context-filter manifest metadata, and strict filtered-bundle validation while continuing to require the formal WP9-a source to contain exactly 10,000 problems. The tracked calibration config SHA256 is `97b2706808e1d4d2fa9088be018617c3e1459633767d3505de138fc5f48c68b0`. Raw `uv.lock` SHA256 remains `f0ef5dc5645e18c9a625057a8b12d3d1c666e9f0cb3539f0e776ba8b26655e80`; the project dependency identity remains the separately defined `59e6292f72bdc6f7f9d889d1969d87715c83ccb09ed95766a50f81d9d762d560`.

The regenerated formal filtered input `/home/dzy/wp9c-calibration-input-9cd1026-context2048` was strict-read back under `9cd10261`: source count 10,000, eligible count 9,621, excluded count 379, prompt cap 2,048, completion cap 512, manifest SHA256 `0ac247e0eae6244148a117a350284dd7088c6822a2eab68382eb22cfd1a2b6c6`, `inputs.jsonl` SHA256 `22675dcbe31c663079c244175f6557d4b65b2206d96ef644c66677b97dd40140`, `excluded_context.jsonl` SHA256 `83219a69b08ffe5348f15e3078389dece3f94e28a8964ac9604ee9d80cf21e1f`, filtered problem-order SHA256 `4de0fa55f04ee02bdd5c4668f97cca9eeb254273c25c354df3c66bc89be9b197`, WP9-a root manifest SHA256 `98a0fb8192661f6358c29819d8a70eb4039397cc2a3ec5444f0581cfbcb81625`, and original WP9-a selected-order SHA256 `355cfec302a38c3c05e4237be178c5f34207cabb432d2b65f1b4a027cf42d001`. The filter policy is `chat_template_prompt_cap_v1`, tokenizer model is `Qwen/Qwen2.5-Coder-1.5B-Instruct`, and exact tokenizer/model revision is `2e1fd397ee46e1388853d2af2c993145b0f1098a`.

C3 supersedes C2. It binds the target input to `$CODE_VERIFIER_DATA_ROOT/wp9c/calibration-input-context2048`, sets `problem_batch_size=1`, preserves k=8 / temperature 0.8 / top-p 0.95 / max-new-tokens 512 and the existing deterministic per-problem seed namespace, and requires a final exact 9,621-problem / 76,968-record stream. In addition to production strict loading and exact bytes/provenance checks, C3 re-tokenizes every survivor with the pinned local-only Qwen tokenizer and the production chat template and fails if any rendered prompt exceeds 2,048 tokens. An existing canonical output with a non-C3 identity, including the preserved C2 running 96-record prefix, is moved as a whole into `wp9c/quarantine/calibration/initial/before-C3-*`; a sidecar quarantine manifest records the old run/progress identity, run/generation/progress hashes, generation byte size, and C2 operator-evidence hash before a fresh C3-compatible output is created. A valid later C3 prefix may still exact-prefix resume, and a strict completed C3 bundle may be reused.

## C3 — context-capped Gate A repair handoff

```yaml
execution_checkpoint:
  version: 1
  stage_id: WP9-c
  checkpoint_id: C3
  task_kind: repair
  source_plan_commit: 5a1f083af6bfdf2e1333bd70e95e9257b4e66b48
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  repair_basis: user_directed_c2_target_failure_repair
  result_code_commit: 9cd10261f4fd3b47135c65154c7a8aca930c29ac
  execution_backend: web_codexpro
  effective_execution_mode: single
  interruption_class: operator
  operator_gate_id: wp9c-calibration-initial-generation
  operator_handoff_mode: portable_target
  operator_restart_policy: exact_prefix_or_strict_completed_reuse_after_identity_quarantine
  supersedes_checkpoint: C2
  operator_commit_binding: runtime_WP9C_HANDOFF_COMMIT_must_equal_target_HEAD
  operator_script: ai-work/executor/operator/WP9-c/wp9c-calibration-initial-generation/C3/run.sh
  operator_script_sha256: 07760259a06f60b2ce068a52f31d7ae6630e49fec5f7cf90467f295d5d605224
  calibration_config_sha256: 97b2706808e1d4d2fa9088be018617c3e1459633767d3505de138fc5f48c68b0
  problem_batch_size: 1
  control_plane_input_bundle: /home/dzy/wp9c-calibration-input-9cd1026-context2048
  target_input_bundle: $CODE_VERIFIER_DATA_ROOT/wp9c/calibration-input-context2048
  input_manifest_sha256: 0ac247e0eae6244148a117a350284dd7088c6822a2eab68382eb22cfd1a2b6c6
  input_records_sha256: 22675dcbe31c663079c244175f6557d4b65b2206d96ef644c66677b97dd40140
  input_problem_order_sha256: 4de0fa55f04ee02bdd5c4668f97cca9eeb254273c25c354df3c66bc89be9b197
  excluded_context_sha256: 83219a69b08ffe5348f15e3078389dece3f94e28a8964ac9604ee9d80cf21e1f
  context_filter_policy: chat_template_prompt_cap_v1
  source_record_count: 10000
  eligible_record_count: 9621
  excluded_record_count: 379
  max_prompt_tokens: 2048
  max_new_tokens: 512
  expected_problem_count: 9621
  expected_record_count: 76968
  wp9a_manifest_sha256: 98a0fb8192661f6358c29819d8a70eb4039397cc2a3ec5444f0581cfbcb81625
  wp9a_selected_order_sha256: 355cfec302a38c3c05e4237be178c5f34207cabb432d2b65f1b4a027cf42d001
  formal_b_run_name: B-sft-formal-seed42
  formal_b_model_id: Qwen/Qwen2.5-Coder-1.5B-Instruct
  formal_b_model_revision: 2e1fd397ee46e1388853d2af2c993145b0f1098a
  formal_b_adapter_model_sha256: 51042ea9c52d2d24976c2ca4e777f1a5f792e3943ff171d03e55b959463a7a67
  formal_b_adapter_config_sha256: 3738f9ef0ac56f90a48497ab4c0a1f172770864aa61dad56e8d9751050f34344
  base_model_weights_sha256: c1b9b30e907950516ba3c646bdf570d8084c25a6410a0cdca80cf04b11bc13a8
  base_model_config_sha256: 88f9a17863c05fb313515d2ff74b1098e0c35579f99068e32beda00618508ae0
  base_model_generation_config_sha256: 1a628a5775bc69cde01c6749a531150ca4d3189652c618a174f7077923acf3b1
  base_model_tokenizer_sha256: c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539
  base_model_tokenizer_config_sha256: 959e7f1d9a1b7641a6d6ce05ca97b75c7894fcb66cbe5a040406458fb1128ee4
  base_model_vocab_sha256: ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910
  base_model_merges_sha256: 599bab54075088774b1733fde865d5bd747cbcc7a547c5bc12610e874e26f5e3
  superseded_c2_target_head: e3c952fc9780138fa8d1332cc374da9d07ee347b
  superseded_c2_partial_record_count: 96
  superseded_c2_partial_byte_count: 110037
  superseded_c2_generation_sha256: b218d3437ceb495c31a89cbaf36a5ee30224bb2ef00e55d0def6e8d9edb8cfad
  superseded_c2_run_sha256: 823a8d6a738ddf3e905d43c2d390da3f9b449b07404f2d76cf60bb7b5db07b0f
  superseded_c2_progress_sha256: a81f8e46efe27cde3fd00aea48bdb325cae45051b4620a0e8899c2aa19c98e5b
  expected_target_output: $CODE_VERIFIER_ARTIFACT_ROOT/wp9c/calibration/initial
  expected_artifacts:
    - $CODE_VERIFIER_ARTIFACT_ROOT/wp9c/calibration/initial/run.json
    - $CODE_VERIFIER_ARTIFACT_ROOT/wp9c/calibration/initial/samples/generations.jsonl
    - $CODE_VERIFIER_ARTIFACT_ROOT/wp9c/calibration/initial/samples/progress.json
    - $CODE_VERIFIER_ARTIFACT_ROOT/operator/WP9-c/5a1f083af6bfdf2e1333bd70e95e9257b4e66b48/wp9c-calibration-initial-generation/C3/operator-evidence.json
    - $CODE_VERIFIER_ARTIFACT_ROOT/operator/WP9-c/5a1f083af6bfdf2e1333bd70e95e9257b4e66b48/wp9c-calibration-initial-generation/C3/postcheck-summary.json
  quarantine_root: $CODE_VERIFIER_ARTIFACT_ROOT/wp9c/quarantine/calibration/initial
  control_plane_evidence_receive_dir: /home/dzy/wp9c-operator-evidence/WP9-c/wp9c-calibration-initial-generation/C3
  control_plane_generation_receive_dir: /home/dzy/wp9c-calibration-initial-C3
  completed_scope:
    - accepted and recorded the real C2 target OOM as target failure evidence
    - recorded the user override permitting deterministic context filtering while preserving WP9-a 10k authority
    - strict-read back the 9,621-record context-capped formal calibration input
    - retained the production repair commit 9cd10261 without reworking it
    - prepared C3 portable target preflight, C2 quarantine, batch-1 generation, corrected command classification, and 76,968-record postcheck
  remaining_scope:
    - manually execute C3 Gate A on the RTX 4090 and return operator evidence plus the completed immutable generation bundle
    - run initial dual-verifier Piston scoring at workers=8 and derive retry manifest
    - conditionally execute retry generation/scoring and freeze the 3,000-problem active pool
    - run evaluation generation/verification benchmark sweep
    - run GRPO throughput benchmark and freeze benchmark report
    - run k=8 Public/Hidden pilot and zero-variance gate
    - complete WP9-c execution inventory and ready_for_wp9d decision
  blocker: manual RTX 4090 C3 Gate A execution and evidence/artifact return are required
  status: awaiting_operator
```
