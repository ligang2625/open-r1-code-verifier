# WP7-c Execution Report

## C0 — Paired 20-step GRPO smoke operator handoff

Web GPT + CodexPro completed the routed control-plane implementation and acceptance work for WP7-c through the first target-GPU boundary. No C/D optimizer-based GRPO command has been started by the executor. The next action is the user-owned RTX 4090 paired smoke gate.

```yaml
execution_checkpoint:
  version: 1
  checkpoint_id: C0
  stage_id: WP7-c
  task_kind: implementation
  source_plan_commit: 8464e69691c527c726a2e28e5a7ca81fa2001bbf
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: 66199d9434290394a55c5c15b0262ff8db322549
  interruption_class: operator
  resume_allowed: true
  operator_gate_id: grpo-cd-smoke
  operator_handoff_mode: portable_target
  operator_restart_policy: trainer_checkpoint
  operator_script: ai-work/executor/operator/WP7-c/grpo-cd-smoke/C0/run.sh
  operator_script_sha256: 2aa602e7a8de9417e06f4d78d6750fe76e4e38eccf5c33a079d17e3771197c38
  target_machine_pointer_template: .ai-bridge/validation-machine.json
  target_status_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-smoke/C0/status"
  target_log_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-smoke/C0/terminal.log"
  target_evidence_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-smoke/C0/operator-evidence.json"
  control_plane_evidence_receive_dir: /home/dzy/wp7c-operator-evidence/WP7-c/grpo-cd-smoke/C0
  expected_artifacts:
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/smoke/C-public-grpo-smoke20-seed42/run.json"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/smoke/C-public-grpo-smoke20-seed42/checkpoints/adapter_model.safetensors"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/smoke/D-hidden-grpo-smoke20-seed42/run.json"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/smoke/D-hidden-grpo-smoke20-seed42/checkpoints/adapter_model.safetensors"
  completed_scope:
    - "formal paired CLI binding committed in f2bb73d: one dataset-dir override binds both Public/Hidden artifacts, paired run-name overrides are all-or-none and safe, and overrides occur before reward/Piston/training selection"
    - "paired-definition provenance and GRPO durability committed in 51dc3b3: same-pair SHA binds both resolved configs, both dataset byte identities, seed, strict completed B identity and schema version; resume fails closed on counterpart drift; completed/evaluation checkpoint identities include the pair SHA"
    - "GRPO telemetry committed in 51dc3b3: explicit pinned Trainer telemetry flags, append-only attempts, recomputable cumulative GPU-hours, GPU count/semantics, final global step, CUDA peak allocated/reserved bytes, all-finite Trainer/result metrics, and completed artifacts consumable by curve/cost loaders"
    - "validation smoke/pilot configs committed in 7ec611b: smoke is paired max_steps=20/save_steps=10; pilot is paired max_steps=100/save_steps=50; only phase fields differ from the finalized main GRPO definition"
    - "analysis engineering fixture was upgraded for the new strict GRPO pair identity in 66199d9 without weakening the production completed-checkpoint loader"
    - "final control-plane acceptance from clean result-code HEAD: make lint PASS including Ruff/format/mypy; standalone mypy PASS; make test PASS 926 passed / 3 expected real-Piston opt-in skips / 0 failed; make test-gpu PASS 3/3; real make test-piston PASS 9 selected / 0 failed / 0 skipped"
    - "formal data readback PASS: check-data confirms 3200 total = 2500 train / 300 validation / 400 test; Public/Hidden GRPO each strict-load 2500 rows, pair validator passes, and both byte SHA values match the sealed plan"
    - "formal completed B strict loader PASS against the sealed run/model/revision/data/config/dependency/seed identity; canonical B evaluation remains completed with 400 unique rows and exact sealed dataset/order/Piston/seed identity"
    - "C0 tracked script is chmod 0555, bash syntax checked, all 13 embedded Python heredocs compile, and only the paired 20-step smoke command is reachable; no pilot/formal/generation command is present"
    - "C0 start preflight resolves target-local roots from the ignored validation-machine pointer, validates exact checkpoint parent/report/script provenance, READY records, RTX 4090 >=22528 MiB/native BF16, pinned runtime/API, local-only exact model snapshot, formal data/B/pair, 1660ti-wsl Piston loopback, and >=20 GiB/100000-inode storage"
    - "C0 trainer_checkpoint policy is fail-closed: fresh runs start from B independently; interrupted runs resume only the numerically latest complete same-run Trainer checkpoint after production resume-identity validation; completed runs are strict-read only; invalid incomplete runs require quarantine rather than overwrite"
    - "C0 sealed postcheck requires C/D completed at global_step=20, same completed B and paired-definition SHA, finite/recomputable telemetry, positive CUDA peaks, nonempty real rollout/reward/group evidence with correct reward source, strict adapters, complete checkpoint-10/checkpoint-20 state, curve/cost loader success and payload boundaries before gate_status=passed"
  remaining_scope:
    - "make the exact C0 checkpoint commit reachable on the RTX 4090 through Git, checkout/detach that exact commit, confirm the checkout is clean, recompute the tracked run.sh SHA256 and run it manually in SSH/tmux; Web GPT/CodexPro must not start or monitor the target command"
    - "C0 runs Public smoke then Hidden smoke from the same formal completed B and same paired definition; Hidden never consumes the Public adapter/checkpoint; an interruption may rerun the same immutable C0 script only when its same-run Trainer checkpoint passes the fail-closed resume contract"
    - "after the script exits, sync operator-evidence.json plus status/terminal.log and necessary small training metadata byte-for-byte to the recorded control-plane receive directory, then explicitly invoke execution-router resume backend=web stage_id=WP7-c"
    - "resume must verify C0 evidence/provenance and real target artifacts; only after smoke passes may the executor create the separate grpo-cd-pilot operator checkpoint; C0 never starts pilot automatically"
  status: awaiting_operator
```

### Executor-owned evidence before C0

- Routing source remains the sealed WP7-c single execution route; backend is Web GPT + CodexPro and no Local Codex execution agent was invoked.
- Stage worktree is `/home/dzy/open-r1-code-verifier/.worktrees/wp7-c`, branch `feat/wp7-c`; `.ai-bridge` has zero tracked paths.
- The current control plane is GTX 1660 Ti. Its GPU smoke passes, but the project hardware guard correctly prevents treating this 6GB device as the 24GB GRPO target.
- The canonical project Piston service is `1660ti-wsl`; local real-Piston acceptance passes 9/9. The target script requires the existing 4090 loopback tunnel helper and exact Python 3.10.0 runtime before any GRPO work.
- The operator script derives all target-local artifact/HF/data roots from the machine pointer at runtime; no control-plane formal-data or B archive absolute path is embedded in the target command.
- No real C or D validation metric, reward, loss, cost, checkpoint or research result exists from this execution yet. Smoke output, if produced by C0, remains validation-gating evidence only and is not a formal C/D result.

## C1 — Superseding paired 20-step GRPO smoke operator handoff

A final pre-run audit was requested before any expensive RTX 4090 execution. That audit found C0 should not be run: production resume validation mutated `run.json` before a new attempt actually began, and C0's postcheck would reject a legitimate historical `running` attempt left by a hard interruption. The production durability issue is fixed in result-code commit `9a7843aa96c566a8bcc8886e1f2f2941ea901f8c`; C1 supersedes C0 without rewriting C0 history. No target GRPO command was executed during this audit.

```yaml
execution_checkpoint:
  version: 1
  checkpoint_id: C1
  stage_id: WP7-c
  task_kind: implementation
  source_plan_commit: 8464e69691c527c726a2e28e5a7ca81fa2001bbf
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: 9a7843aa96c566a8bcc8886e1f2f2941ea901f8c
  interruption_class: operator
  resume_allowed: true
  operator_gate_id: grpo-cd-smoke
  operator_handoff_mode: portable_target
  operator_restart_policy: trainer_checkpoint
  operator_script: ai-work/executor/operator/WP7-c/grpo-cd-smoke/C1/run.sh
  operator_script_sha256: ffc66388cf42c084a7a8a2e84fd7a3a9a7ee60e82f4d06882e4ea062219ee860
  target_machine_pointer_template: .ai-bridge/validation-machine.json
  target_status_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-smoke/C1/status"
  target_log_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-smoke/C1/terminal.log"
  target_evidence_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-smoke/C1/operator-evidence.json"
  control_plane_evidence_receive_dir: /home/dzy/wp7c-operator-evidence/WP7-c/grpo-cd-smoke/C1
  supersedes_checkpoint_id: C0
  supersedes_checkpoint_commit: fda5afb7f3a249d59fa9f5f525d4da35802a0067
  expected_artifacts:
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/smoke/C-public-grpo-smoke20-seed42/run.json"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/smoke/C-public-grpo-smoke20-seed42/checkpoints/adapter_model.safetensors"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/smoke/D-hidden-grpo-smoke20-seed42/run.json"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/smoke/D-hidden-grpo-smoke20-seed42/checkpoints/adapter_model.safetensors"
  completed_scope:
    - "all business implementation and control-plane acceptance recorded by C0 remain valid; C0 was never used for target execution and is retained only as immutable audit history"
    - "pre-run audit fixed production GRPO resume validation so identity checking is read-only until _begin_attempt; regression explicitly proves run.json remains byte-for-byte unchanged when execution stops after validation but before attempt begin"
    - "post-fix acceptance is fresh PASS: make lint including Ruff/format/mypy; make test 927 passed / 3 expected real-Piston opt-in skips / 0 failed; make test-gpu 3/3; real make test-piston 9 selected / 0 failed / 0 skipped"
    - "formal Public/Hidden artifacts revalidated at 2500/2500 rows with sealed byte SHA values; formal B strict identity remains exact; paired smoke config revalidation passes and produces one same-pair identity"
    - "C1 target preflight validates checkpoint parent/diff/report/script SHA, READY machine records, persistent roots, RTX 4090 >=22528 MiB/native BF16, current package map against formal B frozen runtime including torch 2.6.0+cu124, sealed dependency/Open-R1/CUDA identity, exact model local-only with HF/Transformers offline mode, formal data/B/pair, canonical Piston tunnel/runtime, and storage"
    - "C1 fixes sibling-root classification so the canonical /root/sj-tmp/open-r1-code-verifier-outputs style artifact root is accepted while true checkout children remain forbidden"
    - "C1 runtime sentinel was directly exercised: noisy runtime initialization plus exactly one WP7C_RUNTIME record parses unambiguously"
    - "C1 trainer-checkpoint selector was dry-run against the real formal pair/B identity: latest complete numeric checkpoint was selected and run.json remained byte-for-byte unchanged"
    - "C1 postcheck was dry-run end-to-end against production schemas using real formal B identity, including a historical running attempt followed by a completed attempt; strict GRPO loader, reward/group schema, curve/cost and checkpoint inventory all passed"
    - "C1 postcheck additionally requires no Piston infrastructure-failure rows, at least one actually executed reward completion per C/D, exact group schema with sample_count=4, positive generated-token count, completed step-10/step-20 Trainer checkpoints, finite telemetry, strict final adapters and payload safety"
    - "C1 is smoke-only: one parameterized train-grpo site schedules Public then Hidden; no validation-pilot, formal-training or generate-eval command is present"
  remaining_scope:
    - "make the exact C1 checkpoint commit reachable on the RTX 4090 through Git, checkout/detach that exact commit, confirm clean checkout, recompute C1 run.sh SHA256 and run it manually in SSH/tmux; do not run C0"
    - "C1 runs Public smoke then Hidden smoke from the same formal completed B and paired definition; Hidden never consumes the Public adapter/checkpoint; reruns use only a same-run latest complete Trainer checkpoint after read-only production identity validation"
    - "after C1 exits, sync operator-evidence.json, status, terminal.log, postcheck-summary.json and required small run metadata byte-for-byte to the C1 control-plane receive directory, then explicitly invoke execution-router resume backend=web stage_id=WP7-c"
    - "resume must verify C1 provenance/evidence and real target artifacts; only after smoke passes may a distinct grpo-cd-pilot checkpoint be generated"
  status: awaiting_operator
```

### Executor-owned evidence before C1

- C0 is superseded and must not be executed. Its commit/report/script remain untouched for provenance.
- Business result-code HEAD for C1 is `9a7843aa96c566a8bcc8886e1f2f2941ea901f8c`; the only business change after C0 is the minimal read-only resume-validation durability fix plus its regression test.
- No RTX 4090 target command was started, monitored, or simulated with a real model. All new audit executions were bounded 1660 Ti/control-plane checks or synthetic metadata-only dry-runs.
- No pilot/formal/generation checkpoint has been created. C1 remains the first outstanding target-GPU gate.

## C2 — Piston identity-label compatibility repair

The operator ran C1 on the exact RTX 4090 checkpoint. C1 failed closed before GPU/model/data/training preflight because its Piston identity validator treated the documentation's minimum value `real_piston_acceptance=PASS` as the only legal spelling. The current validated machine provenance intentionally records the stronger value `PASS_9_OF_9_TUNNELED` together with `local_piston_acceptance=PASS_9_OF_9`. This is an operator-validator defect, not damaged target provenance. The persistent machine record is preserved byte-for-byte; C2 supersedes C1 and changes only the new tracked operator script plus this append-only report.

```yaml
execution_checkpoint:
  version: 1
  checkpoint_id: C2
  stage_id: WP7-c
  task_kind: implementation
  source_plan_commit: 8464e69691c527c726a2e28e5a7ca81fa2001bbf
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: 925181820e86787b7374108d1f6c9ce7b970606b
  interruption_class: operator
  resume_allowed: true
  operator_gate_id: grpo-cd-smoke
  operator_handoff_mode: portable_target
  operator_restart_policy: trainer_checkpoint
  operator_script: ai-work/executor/operator/WP7-c/grpo-cd-smoke/C2/run.sh
  operator_script_sha256: 5c451313fa9fb2f5a0dfb720367e517d042357c853c991392627771a138be848
  target_machine_pointer_template: .ai-bridge/validation-machine.json
  target_status_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-smoke/C2/status"
  target_log_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-smoke/C2/terminal.log"
  target_evidence_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-smoke/C2/operator-evidence.json"
  control_plane_evidence_receive_dir: /home/dzy/wp7c-operator-evidence/WP7-c/grpo-cd-smoke/C2
  supersedes_checkpoint_id: C1
  supersedes_checkpoint_commit: 925181820e86787b7374108d1f6c9ce7b970606b
  failed_c1_operator_evidence_sha256: 70cfb740dc6c1c45113a5b006386de5af3499fb5215a6408f237c0fab51845ca
  failed_c1_status_sha256: a5e45837a2959db847f7e67a915d0ecaddd47f943af2af5fa6453be497faabca
  failed_c1_terminal_log_sha256: 765ce8a7bc1911ff4ccccc9d6767c66a187f0d3ef3527b48ca796e1b0b0755f3
  expected_artifacts:
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/smoke/C-public-grpo-smoke20-seed42/run.json"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/smoke/C-public-grpo-smoke20-seed42/checkpoints/adapter_model.safetensors"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/smoke/D-hidden-grpo-smoke20-seed42/run.json"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/smoke/D-hidden-grpo-smoke20-seed42/checkpoints/adapter_model.safetensors"
  completed_scope:
    - "C1 was run twice and both attempts failed in preflight with command_rc=125/postcheck_rc=125/gate_status=preflight_failed before GPU/model/data/training work; latest target evidence inventories every expected C/D artifact as absent"
    - "target validation-machine.json is internally consistent: endpoint http://127.0.0.1:2000, host 1660ti-wsl, READY record, and the current Piston identity record; target record SHA256 is 19e978bacadea8ff1ac358b3e19efb68f395740200faa460b0f17b706c283d79"
    - "the target Piston record contains deployment_mode=ssh_tunneled_remote, endpoint=http://127.0.0.1:2000, python_runtime=3.10.0, piston_host_id=1660ti-wsl, local_piston_acceptance=PASS_9_OF_9, real_piston_acceptance=PASS_9_OF_9_TUNNELED, pinned source/image identity, and the current tunnel helper reports the loopback tunnel healthy"
    - "C2 keeps exact topology/runtime checks and accepts only either the documented minimum PASS spelling or PASS_9_OF_9_TUNNELED when it is accompanied by local_piston_acceptance=PASS_9_OF_9; unknown acceptance labels and inconsistent detailed provenance remain fail-closed"
    - "the exact proposed C2 acceptance rule was executed read-only against the real 4090 machine record and passed; the exact C2 heredoc also passed a four-case matrix covering legacy PASS, detailed 9/9 PASS, missing local evidence rejection, and unknown-label rejection"
    - "C2 bash syntax passes and all 13 embedded Python heredocs compile; C2 contains no C1 self-reference or old result-code reference and still has one parameterized smoke-only train-grpo invocation with no validation-pilot command"
    - "post-repair control-plane acceptance is fresh PASS: make lint including Ruff/format/mypy; make test 927 passed / 3 expected real-Piston opt-in skips / 0 failed; real make test-piston 9 selected / 0 failed / 0 skipped"
  remaining_scope:
    - "make the exact C2 checkpoint commit reachable on the RTX 4090 through Git, checkout/detach that exact commit, confirm clean checkout, recompute C2 run.sh SHA256 and run it manually in SSH/tmux; do not rerun C0 or C1"
    - "C2 will re-run all original target preflight gates after the corrected Piston identity check, then run Public smoke followed by Hidden smoke from the same formal B/pair; no pilot is started"
    - "after C2 exits, sync operator-evidence.json, status, terminal.log, postcheck-summary.json and required small run metadata byte-for-byte to the C2 control-plane receive directory, then explicitly invoke execution-router resume backend=web stage_id=WP7-c"
    - "only after C2 smoke evidence is accepted may a distinct grpo-cd-pilot checkpoint be generated"
  status: awaiting_operator
```

### C1 failure evidence and C2 repair notes

- C1 target terminal log records two attempts (`2026-08-20T11:52:20Z` and `2026-08-20T12:01:52Z`); both end in phase `preflight` with rc 125 and the same readiness/Piston identity mismatch. No `train-grpo` line was reached.
- Latest C1 evidence binds checkpoint `925181820e86787b7374108d1f6c9ce7b970606b`, script SHA `ffc66388cf42c084a7a8a2e84fd7a3a9a7ee60e82f4d06882e4ea062219ee860`, target machine pointer SHA `b2230476c3d7600477108db5684ba2efbef95b89f746b8d8a1bc83b88ba5cab7`, readiness SHA `5e3a42ac4f99d8312f876bd4f7ac70b35d5b3db27a7ca7c8c96a7196b019e45d`, and Piston identity SHA `19e978bacadea8ff1ac358b3e19efb68f395740200faa460b0f17b706c283d79`.
- The C1 failure produced no Public or Hidden smoke run metadata/checkpoint/log artifact; C2 therefore enters the same smoke namespace as a clean fresh run unless an operator independently creates incompatible files, which the existing fail-closed run-action logic would reject.
- The 4090 machine provenance was not edited. C2 repairs only the tracked interpretation of an already validated, stronger Piston acceptance label.

## C3 — heterogeneous GRPO test-payload repair and exact C2 failure quarantine

The operator ran C2 on the exact RTX 4090 checkpoint. C2 passed its full provenance/machine/GPU/frozen-runtime/offline-model/data/B/pair/Piston/storage preflight and reached the Public `train-grpo` command, but failed while materializing the HuggingFace trainer Dataset, before model/Trainer initialization. The formal test payload permits arbitrary JSON values in `input` and `expected`; PyArrow cannot infer one struct field type when those values mix list/dict/scalar/null shapes. The production repair stores each test case as canonical JSON text inside the trainer Dataset (`list<string>`) and strictly restores the exact `{input, expected}` mapping in the reward callback before verifier/Piston use. Formal JSONL, prompts, verifier inputs, reward math, parent B, pair identity, and all GRPO hyperparameters remain unchanged.

```yaml
execution_checkpoint:
  version: 1
  checkpoint_id: C3
  stage_id: WP7-c
  task_kind: implementation
  source_plan_commit: 8464e69691c527c726a2e28e5a7ca81fa2001bbf
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: 7b47ee0ebb1b4c6ab494944155ff0fbd6ebaa0e0
  interruption_class: operator
  resume_allowed: true
  operator_gate_id: grpo-cd-smoke
  operator_handoff_mode: portable_target
  operator_restart_policy: trainer_checkpoint
  operator_script: ai-work/executor/operator/WP7-c/grpo-cd-smoke/C3/run.sh
  operator_script_sha256: 6ba8009e04f525cb690ed265063fe71059a2bd38fec3b58b01f66f10c4cd2fd3
  target_machine_pointer_template: .ai-bridge/validation-machine.json
  target_status_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-smoke/C3/status"
  target_log_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-smoke/C3/terminal.log"
  target_evidence_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-smoke/C3/operator-evidence.json"
  target_quarantine_manifest_template: "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/quarantine/WP7-c/grpo-cd-smoke/C2/quarantine-manifest.json"
  control_plane_evidence_receive_dir: /home/dzy/wp7c-operator-evidence/WP7-c/grpo-cd-smoke/C3
  supersedes_checkpoint_id: C2
  supersedes_checkpoint_commit: b0d59cf0ccbdd5bd190f678ab1dc727a9112f98c
  failed_c2_operator_evidence_sha256: 0e120f39c52cdb0ac3460f69a3dfd1c2d195412ae28c17c51a999227909f453f
  failed_c2_status_sha256: 4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865
  failed_c2_terminal_log_sha256: 0424ea62147892a4825741bd1063eb9e4db023077d6b73abfc17d3e7753581ed
  failed_c2_public_run_json_sha256: f642703ee635a4eafd02d8f905b34b85dcd1510b734d4288e7415e7047ce67cc
  failed_c2_public_stderr_sha256: fc56b31a1f8c3bd2a166b0f815a68672b2631958f96a393be79049e62e9cd6b9
  expected_artifacts:
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/smoke/C-public-grpo-smoke20-seed42/run.json"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/smoke/C-public-grpo-smoke20-seed42/checkpoints/adapter_model.safetensors"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/smoke/D-hidden-grpo-smoke20-seed42/run.json"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/smoke/D-hidden-grpo-smoke20-seed42/checkpoints/adapter_model.safetensors"
  completed_scope:
    - "C2 target preflight passed, then Public failed in build_grpo_dataset -> datasets.Dataset.from_list with pyarrow ArrowInvalid cannot mix list and non-list, non-null values; C2 evidence has command_rc=1/gate_status=command_failed"
    - "C2 failed Public run has global_step=null, peak CUDA allocated/reserved=0, empty checkpoints, zero-byte metrics/rollouts/rewards/group_metrics/stdout, stderr identity ArrowInvalid, and approximately 0.000157 GPU-hours; Hidden run does not exist"
    - "real formal Public visible_tests Arrow inference fails because input values mix list/dict and expected values mix str/int/list/bool/float/null/dict; real formal Hidden visible_tests and train_hidden_tests exhibit the same Arrow failure"
    - "business result-code 7b47ee0ebb1b4c6ab494944155ff0fbd6ebaa0e0 canonical-JSON encodes each trainer test case into Arrow-stable list<string> and strictly decodes it before reward verification; complex nested JSON values round-trip without changing verifier/Piston semantics"
    - "post-fix targeted WP7 integration/unit suite passes 84/84; make lint including Ruff/format/mypy passes; make test passes 929 / 3 expected real-Piston opt-in skips / 0 failed; GTX1660 GPU smoke passes 3/3; real Piston passes 9/9"
    - "complete formal Public and Hidden artifacts each materialize 2500-row trainer Datasets successfully; Public visible_tests and Hidden visible_tests/train_hidden_tests are Sequence[string]; the exact C3 formal-Dataset preflight heredoc also passes on the control-plane formal data"
    - "C3 only quarantines the known C2 Public failure when run.json SHA, C2 git commit, failed attempt, empty checkpoints/logs, zero peak CUDA, stderr SHA and absent Hidden run all match; a read-only matcher against the real 4090 C2 artifacts passes"
    - "C3 quarantine heredoc dry-run passes first quarantine and idempotent rerun, rejects changed run artifacts, and validates an existing quarantine manifest byte-for-semantics against the quarantined inventory; manifest tampering is rejected"
    - "C3 bash syntax passes and all 15 embedded Python heredocs compile; there is one parameterized smoke-only train-grpo invocation, no validation-pilot command, and pilot appears only in the final evidence note that it was not started"
  remaining_scope:
    - "make the exact C3 checkpoint commit reachable on the RTX 4090 through Git, checkout/detach that exact commit, confirm clean checkout, recompute C3 run.sh SHA256 and run it manually in SSH/tmux; do not rerun C0/C1/C2"
    - "C3 re-runs all target preflight gates including complete formal 2500+2500 trainer Dataset materialization, then quarantines only the exact known C2 pre-Trainer failure and starts a fresh canonical Public smoke; subsequent C3 reruns leave a C3 run untouched and use only strict trainer-checkpoint restart semantics"
    - "C3 runs Public smoke then Hidden smoke from the same formal completed B and paired definition; Hidden never consumes the Public adapter/checkpoint; no pilot is started"
    - "after C3 exits, sync operator-evidence.json, status, terminal.log, postcheck-summary.json, quarantine-manifest.json and required small run metadata byte-for-byte to the C3 control-plane receive directory, then explicitly invoke execution-router resume backend=web stage_id=WP7-c"
    - "only after C3 smoke evidence is accepted may a distinct grpo-cd-pilot checkpoint be generated"
  status: awaiting_operator
```

### C2 failure evidence and C3 repair notes

- C2 terminal log records preflight PASS at `2026-08-20T12:24:23Z`, Public fresh-run dispatch at `12:24:24Z`, and the ArrowInvalid traceback ending at `12:24:31Z`; the exception occurs in `build_grpo_dataset()` / `Dataset.from_list()` before `_load_grpo_runtime()`, tokenizer/model loading, Trainer construction, or `trainer.train()`.
- The real 4090 C2 canonical Public directory still exactly matches C3 quarantine prerequisites and has not been edited by Web GPT/CodexPro. The C3 quarantine check performed on the target was read-only.
- C3 preserves C2 failure evidence rather than deleting it: an exact match is atomically moved under the external artifact-root quarantine namespace and accompanied by a deterministic manifest containing every quarantined file size/SHA. Unknown, changed, partially overlapping, symlinked, or inconsistent states fail closed.
- No RTX 4090 target training command was started or monitored by Web GPT/CodexPro during this repair. All target-side connector work was read-only diagnosis/matching; all executable repair tests were control-plane CPU/1660/Piston or synthetic metadata-only dry-runs.

## C4 — reuse the proven plain-training DeepSpeed guard for GRPO

The operator ran C3 and reported a Public failure after formal Dataset materialization and merged-B model loading, while `GRPOTrainer.__init__` enabled gradient checkpointing. Accelerate 1.4.0 called `is_peft_model()`, which imported the lock-pinned but unconfigured DeepSpeed 0.16.8 backend for model-unwrapping type detection; DeepSpeed's import-time CUDA op compatibility probe reached `torch.utils.cpp_extension`, which imports `setuptools`, but the Python 3.10 locked runtime does not install setuptools as a runtime package. This is not an extraneous-package incident: `uv.lock` pins DeepSpeed 0.16.8 through Open-R1, and an exact frozen/offline `uv sync --dry-run` includes it. WP6-d had already solved the identical plain-LoRA SFT condition with `_without_unconfigured_deepspeed_backend()`. C4 applies that established narrow guard to the GRPO model/Trainer/train/save lifecycle without changing dependencies, model/data identities, DeepSpeed pins, or experiment semantics.

```yaml
execution_checkpoint:
  version: 1
  checkpoint_id: C4
  stage_id: WP7-c
  task_kind: implementation
  source_plan_commit: 8464e69691c527c726a2e28e5a7ca81fa2001bbf
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: 847f7c7f74b6d4d4af37762efe1da6a7370a8110
  interruption_class: operator
  resume_allowed: true
  operator_gate_id: grpo-cd-smoke
  operator_handoff_mode: portable_target
  operator_restart_policy: trainer_checkpoint
  operator_script: ai-work/executor/operator/WP7-c/grpo-cd-smoke/C4/run.sh
  operator_script_sha256: 35b65f89a7f33e46c4b7f44f6a68a539e7c9b795a5ca85dc680b3ec0276b4e85
  target_machine_pointer_template: .ai-bridge/validation-machine.json
  target_status_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-smoke/C4/status"
  target_log_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-smoke/C4/terminal.log"
  target_evidence_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-smoke/C4/operator-evidence.json"
  target_quarantine_manifest_template: "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/quarantine/WP7-c/grpo-cd-smoke/C3/quarantine-manifest.json"
  control_plane_evidence_receive_dir: /home/dzy/wp7c-operator-evidence/WP7-c/grpo-cd-smoke/C4
  supersedes_checkpoint_id: C3
  supersedes_checkpoint_commit: 500b3936dba6b0ef72a3e4a0ad8b703a35d93682
  failed_c3_public_stderr_sha256: cc0e697f76fe85b5ad6186baae92dcb29572e91a63ee09e1e687b25c1ffc21ea
  expected_artifacts:
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/smoke/C-public-grpo-smoke20-seed42/run.json"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/smoke/C-public-grpo-smoke20-seed42/checkpoints/adapter_model.safetensors"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/smoke/D-hidden-grpo-smoke20-seed42/run.json"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/smoke/D-hidden-grpo-smoke20-seed42/checkpoints/adapter_model.safetensors"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/quarantine/WP7-c/grpo-cd-smoke/C3/quarantine-manifest.json"
  completed_scope:
    - "the C3 user-reported traceback reaches GRPOTrainer.__init__ -> gradient-checkpointing -> accelerate.is_peft_model -> extract_model_from_parallel -> import deepspeed -> torch.utils.cpp_extension -> import setuptools and ends with ModuleNotFoundError: No module named setuptools, before trainer.train()"
    - "the same failure was reproduced exactly on the GTX1660 control-plane pinned runtime: deepspeed=0.16.8, accelerate=1.4.0, torch=2.6.0+cu124, trl=0.18.0, peft=0.14.0, setuptools absent"
    - "DeepSpeed is not extraneous: uv.lock contains deepspeed==0.16.8 and setuptools, while the Python 3.10 dependency markers do not install setuptools at runtime; frozen/offline uv sync dry-run includes DeepSpeed 0.16.8"
    - "WP6-d already established _without_unconfigured_deepspeed_backend for plain LoRA SFT; with setuptools absent and DeepSpeed installed, the exact guarded Accelerate is_peft_model probe returns False without importing the unused backend"
    - "business result-code 847f7c7f74b6d4d4af37762efe1da6a7370a8110 wraps the GRPO merged-model/Trainer/train/save lifecycle in the same established guard and adds a lifecycle regression test; pyproject.toml and uv.lock are unchanged"
    - "post-fix acceptance is fresh PASS: GRPO unit 63/63; make lint including Ruff/format/mypy; make test 930 passed / 3 expected real-Piston opt-in skips / 0 failed; GTX1660 GPU smoke 3/3; real Piston 9/9; formal Public/Hidden Dataset materialization 2500+2500 PASS"
    - "C4 target preflight contains an executable guarded Accelerate compatibility probe requiring deepspeed=0.16.8 and proving is_peft_model(object()) returns False inside the guard even when setuptools is absent; the exact heredoc passes on the current control-plane runtime"
    - "C4 inherits the C3 complete-formal Dataset materialization preflight and C2 quarantine handling, and adds semantic C3 quarantine tied to checkpoint 500b3936..., result-code 7b47ee0..., formal pair/data/B/lock identity, one failed non-resume attempt, global_step=null, positive CUDA peak, empty Trainer checkpoints/telemetry, ModuleNotFoundError stderr, absent Hidden run, and matching C3 operator evidence/status/terminal semantics"
    - "the exact C4 C3-quarantine heredoc passes first quarantine, idempotent rerun, manifest-tamper rejection, and future-C4-run non-interference dry-runs; actual C3 run/evidence/status/terminal SHAs are captured into the target quarantine manifest at runtime rather than guessed on the control plane"
    - "C4 bash syntax passes and all 17 embedded Python heredocs compile; there is one actual parameterized smoke train-grpo invocation, no validation-pilot command, and pilot appears only in the final evidence note that it was not started"
  remaining_scope:
    - "make the exact C4 checkpoint commit reachable on the RTX 4090 through Git, checkout/detach that exact commit, confirm clean checkout, recompute C4 run.sh SHA256 and run it manually in SSH/tmux; do not rerun C0/C1/C2/C3"
    - "C4 re-runs all target preflight gates, including formal 2500+2500 Dataset materialization and the guarded Accelerate/DeepSpeed compatibility probe; it then preserves/quarantines only the semantically exact C3 pre-trainer-train failure and starts a fresh canonical Public smoke"
    - "subsequent C4 reruns never quarantine a C4 run; they use only the existing strict trainer-checkpoint restart/completed semantics"
    - "C4 runs Public 20-step smoke then Hidden 20-step smoke from the same formal completed B and paired definition; no pilot is started"
    - "after C4 exits, sync operator-evidence.json, status, terminal.log, postcheck-summary.json, the C3 quarantine manifest, and required small run metadata byte-for-byte to the C4 control-plane receive directory, then explicitly invoke execution-router resume backend=web stage_id=WP7-c"
    - "only after C4 smoke evidence is accepted may a distinct grpo-cd-pilot checkpoint be generated"
  status: awaiting_operator
```

### C3 failure and C4 repair notes

- This repair deliberately does not install setuptools, remove DeepSpeed, or change the lock. DeepSpeed 0.16.8 is part of the pinned Open-R1 runtime; the experiment is plain LoRA GRPO and has no configured DeepSpeed backend, so suppressing only Accelerate's unused type-detection import is the same narrow backend-selection policy already used by the accepted formal SFT path.
- The C3 failure occurred later than C2: formal Dataset materialization had passed and the merged B model was loaded before `GRPOTrainer.__init__` failed. C4 therefore refuses to treat it as a Trainer resume unless a complete cadence-valid Trainer checkpoint exists; the known no-checkpoint C3 state is instead preserved under a distinct external quarantine namespace.
- The 4090 CodexPro connector became unavailable during this repair, so control-plane code does not invent target C3 run/evidence hashes. C4 validates C3 evidence/status/terminal and run semantics on-target before any move, then records the actual target hashes and every quarantined file hash in its deterministic quarantine manifest. Any mismatch fails closed.
- No RTX4090 target training command was started or monitored by Web GPT/CodexPro during C4 preparation. All executable validation was on the GTX1660 control plane or synthetic metadata-only recovery dry-runs.

## C5 — final GRPO constructor/preflight/recovery certification checkpoint

C5 supersedes C4 without executing any earlier operator script. Business result-code `e1592bfc89c5e3f276c4b42d089597a23ccfe4c2` adds the pinned real `GRPOTrainer` constructor regression plus the established unconfigured-DeepSpeed guard coverage; C5 freezes the final operator preflight/recovery contract around that result. No 20-step smoke or pilot was started while preparing this checkpoint.

```yaml
execution_checkpoint:
  version: 1
  checkpoint_id: C5
  stage_id: WP7-c
  task_kind: implementation
  source_plan_commit: 8464e69691c527c726a2e28e5a7ca81fa2001bbf
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: e1592bfc89c5e3f276c4b42d089597a23ccfe4c2
  interruption_class: operator
  resume_allowed: true
  operator_gate_id: grpo-cd-smoke
  operator_handoff_mode: portable_target
  operator_restart_policy: trainer_checkpoint
  operator_script: ai-work/executor/operator/WP7-c/grpo-cd-smoke/C5/run.sh
  operator_script_sha256: df2f79b3d628825c690b7b450d8d3fa6b497508df86d7406ef136dd9ac595049
  target_machine_pointer_template: .ai-bridge/validation-machine.json
  target_status_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-smoke/C5/status"
  target_log_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-smoke/C5/terminal.log"
  target_evidence_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-smoke/C5/operator-evidence.json"
  target_quarantine_manifest_template: "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/quarantine/WP7-c/grpo-cd-smoke/C3/quarantine-manifest.json"
  control_plane_evidence_receive_dir: /home/dzy/wp7c-operator-evidence/WP7-c/grpo-cd-smoke/C5
  supersedes_checkpoint_id: C4
  supersedes_checkpoint_commit: d5211049e9b3dd9a37a0e768c79b69ac8483ced2
  failed_c3_public_stderr_sha256: cc0e697f76fe85b5ad6186baae92dcb29572e91a63ee09e1e687b25c1ffc21ea
  expected_artifacts:
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/smoke/C-public-grpo-smoke20-seed42/run.json"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/smoke/C-public-grpo-smoke20-seed42/checkpoints/adapter_model.safetensors"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/smoke/D-hidden-grpo-smoke20-seed42/run.json"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/smoke/D-hidden-grpo-smoke20-seed42/checkpoints/adapter_model.safetensors"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/quarantine/WP7-c/grpo-cd-smoke/C2/quarantine-manifest.json"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/quarantine/WP7-c/grpo-cd-smoke/C3/quarantine-manifest.json"
  completed_scope:
    - "business result-code e1592bfc89c5e3f276c4b42d089597a23ccfe4c2 is based directly on C4 checkpoint d5211049e9b3dd9a37a0e768c79b69ac8483ced2 and adds the real pinned TRL 0.18.0 / Accelerate 1.4.0 / Transformers Qwen2 GRPOTrainer constructor regression with gradient_checkpointing=True; trainer.train() is never called"
    - "C5 Git preflight proves checkpoint parent=result-code, result-code parent=C4 checkpoint, sealed plan unchanged, report byte-for-byte append-only, checkpoint diff exactly modified execution report plus newly added executable C5 script, and tracked script SHA equals the checkpoint record"
    - "C5 machine preflight uses exact validation-machine/readiness/Piston schemas and validates READY gates, persistent roots, formal-data counts, exact model identity, deployment ssh_tunneled_remote, host 1660ti-wsl, endpoint http://127.0.0.1:2000, Piston Python 3.10.0, source ref and image digest"
    - "C5 frozen-runtime preflight requires formal-B Python 3.10.21, CUDA 12.4, NVIDIA GeForce RTX 4090, compute capability 8.9, native BF16, exact package map accelerate 1.4.0 / datasets 3.2.0 / open-r1 0.1.0.dev0 / peft 0.14.0 / torch 2.6.0+cu124 / transformers 4.52.3 / trl 0.18.0, and exact dependency-lock identity"
    - "C5 model/B certification binds Qwen/Qwen2.5-Coder-1.5B-Instruct@2e1fd397ee46e1388853d2af2c993145b0f1098a, model.safetensors SHA c1b9b30e907950516ba3c646bdf570d8084c25a6410a0cdca80cf04b11bc13a8, B adapter_model SHA 51042ea9c52d2d24976c2ca4e777f1a5f792e3943ff171d03e55b959463a7a67, and B adapter_config SHA 3738f9ef0ac56f90a48497ab4c0a1f172770864aa61dad56e8d9751050f34344"
    - "formal Public/Hidden GRPO data revalidated at 2500/2500 rows with sealed byte SHAs; trainer materialization PASS and visible_tests/train_hidden_tests are Arrow Sequence[string]"
    - "C2/C3 recovery matrices PASS manifest-first validation, deterministic SHA inventory, tamper fail-closed, idempotent rerun, preservation of future C5 runs, and no movement of unknown failed runs; C3 complete cadence-valid Trainer checkpoints explicitly prohibit quarantine and require strict same-run resume"
    - "C5 shell syntax PASS; all 19 embedded Python heredocs compile; exact C5 GRPO constructor block executes successfully with train_not_called=true"
    - "fresh control-plane acceptance PASS: make lint; make test 931 passed / 3 expected real-Piston opt-in skips / 0 failed; make test-gpu 3/3; real make test-piston 9/9 with 0 skips"
    - "read-only exported 4090 cross-check PASS for exact readiness/Piston identity, formal-B runtime/package map, dependency lock, B adapter SHA pair and base-model weight SHA; target-only absolute-path equality remains intentionally fail-closed and is rechecked only on the 4090"
    - "C5 run.sh is mode 0755 and frozen SHA256 df2f79b3d628825c690b7b450d8d3fa6b497508df86d7406ef136dd9ac595049; no C0/C1/C2/C3/C4 script, 20-step target smoke, pilot, formal training, formal data mutation, formal B mutation, uv.lock change, setuptools install, force-push or failed-artifact deletion occurred"
  remaining_scope:
    - "make the exact C5 checkpoint commit reachable on the RTX 4090 through Git, checkout/detach that exact commit, confirm clean checkout, recompute C5 run.sh SHA256 and run it manually in SSH/tmux; do not execute C0/C1/C2/C3/C4"
    - "C5 target start revalidates exact Git/result/checkpoint provenance, target machine pointer/readiness/Piston identity, RTX4090/BF16/runtime/package lock, offline base-model SHA, formal B adapter SHAs, formal Public/Hidden 2500+2500 materialization, real Piston and storage before recovery or training"
    - "C5 re-inspects the actual C3 run.json/status/attempts/global_step/checkpoints/metrics/rewards/rollouts/group_metrics/stderr plus C3 operator evidence/status/terminal log; only the exact known no-Trainer-checkpoint failure may be atomically quarantined with deterministic manifest, while any complete cadence-valid Trainer checkpoint forbids quarantine and stops for strict same-run resume"
    - "after recovery, C5 runs only the paired Public then Hidden 20-step smoke from the same formal B/pair, using strict same-run trainer-checkpoint resume/completed semantics; no pilot is started"
    - "after C5 exits, sync operator-evidence.json, status, terminal.log, postcheck-summary.json, C2/C3 quarantine manifests and required small run metadata byte-for-byte to the C5 control-plane receive directory, then explicitly invoke execution-router resume backend=web stage_id=WP7-c"
    - "only after C5 smoke evidence is accepted may a distinct grpo-cd-pilot checkpoint be generated"
  status: awaiting_operator
```

### C5 certification and C3 recovery notes

- Historical C3 evidence records a constructor-time failure before `trainer.train()` with `global_step=null`, empty Trainer checkpoints and empty metrics/reward/rollout/group outputs; C5 does not trust that prose alone. The target script revalidates the actual run directory, stderr, operator status/evidence/terminal log and every quarantined file hash before moving anything.
- Existing C2/C3 quarantine manifests are authenticated before canonical-run classification. A tampered manifest therefore cannot be bypassed merely because a later C5 run already occupies the canonical run name. Existing quarantine validation is independent of future Hidden-run presence, so later valid C5 artifacts are neither moved nor misclassified as historical C2/C3 state.
- If the target C3 directory unexpectedly contains a complete cadence-valid Trainer checkpoint, C5 refuses quarantine and stops with a strict same-run resume requirement. Incomplete/unknown checkpoint state also fails closed; it is never converted into a fresh run by deletion or overwrite.
- The C5 constructor probe is real pinned TRL/Transformers code, CPU-only and constructor-only. It exercises the gradient-checkpointing initialization path under `_without_unconfigured_deepspeed_backend()` and deliberately never calls `trainer.train()`.
- No RTX4090 target command was started or monitored while preparing C5. C5 is the final executable smoke checkpoint; C6 was not created.


### C6 — accepted C5 smoke; paired 100-step pilot operator handoff

C5 target evidence has now been received byte-for-byte on the GTX 1660 Ti control plane and accepted before any pilot command is allowed. The accepted evidence SHA256 is `f1e3b350d11a4af13118a2517bbbbfb95df752b6cded126c80492ba40b163a5e`; its postcheck SHA256 is `94b052e9c14f4842b45c35c2ce0d9f108cd6e382ff99e50293544b83039c2b8a`. The accepted smoke pair completed Public/Hidden at global step 20, retained complete checkpoint-10/checkpoint-20 state on the target, and reported a maximum complete Trainer checkpoint footprint of 42184437 bytes / 15 inodes. No pilot or formal command was executed during this resume.

```yaml
execution_checkpoint:
  version: 1
  checkpoint_id: C6
  stage_id: WP7-c
  task_kind: implementation
  source_plan_commit: 8464e69691c527c726a2e28e5a7ca81fa2001bbf
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: ae429f2dc0ed7353d5a3de0adb0d71b58a879a3d
  interruption_class: operator
  resume_allowed: true
  operator_gate_id: grpo-cd-pilot
  operator_handoff_mode: portable_target
  operator_restart_policy: trainer_checkpoint
  operator_script: ai-work/executor/operator/WP7-c/grpo-cd-pilot/C6/run.sh
  operator_script_sha256: 8d37f8c775fe5122988106b5b098f074b3d379ece4776cd47a9370e5b9ebb96e
  target_machine_pointer_template: .ai-bridge/validation-machine.json
  target_status_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-pilot/C6/status"
  target_log_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-pilot/C6/terminal.log"
  target_evidence_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-pilot/C6/operator-evidence.json"
  target_postcheck_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-pilot/C6/postcheck-summary.json"
  control_plane_evidence_receive_dir: /home/dzy/wp7c-operator-evidence/WP7-c/grpo-cd-pilot/C6
  prior_operator_checkpoint_commit: ae429f2dc0ed7353d5a3de0adb0d71b58a879a3d
  accepted_prior_operator_evidence_sha256: f1e3b350d11a4af13118a2517bbbbfb95df752b6cded126c80492ba40b163a5e
  accepted_prior_postcheck_sha256: 94b052e9c14f4842b45c35c2ce0d9f108cd6e382ff99e50293544b83039c2b8a
  pilot_pair_sha256: a82c7521551d8a4520a0126783c3c4c4dd3f36f57a5b3dd43484e59dda7a34b5
  smoke_max_complete_trainer_checkpoint_bytes: 42184437
  smoke_max_complete_trainer_checkpoint_inodes: 15
  target_required_free_bytes: 32212254720
  target_required_free_inodes: 100000
  expected_artifacts:
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/pilot/C-public-grpo-pilot100-seed42/run.json"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/pilot/C-public-grpo-pilot100-seed42/checkpoints/adapter_model.safetensors"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/pilot/D-hidden-grpo-pilot100-seed42/run.json"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/pilot/D-hidden-grpo-pilot100-seed42/checkpoints/adapter_model.safetensors"
  completed_scope:
    - "C5 operator evidence was accepted from /home/dzy/wp7c-operator-evidence/WP7-c/grpo-cd-smoke/C5 with exact checkpoint/result/script identity, status=0, command_rc=0, postcheck_rc=0 and gate_status=passed"
    - "received C5 machine pointer/readiness/Piston records match target evidence SHA256; all 19 expected inventory entries and C2/C3 quarantine manifests/inventories match byte-for-byte, including direct 4090/1660 SHA equality for both smoke rollouts and final LoRA adapters"
    - "control-plane pilot prevalidation reloaded formal Public/Hidden 2500+2500 artifacts and the frozen formal B, validated pair fairness/cadence max_steps=100 save_steps=50, and certified pilot paired_definition_sha256 a82c7521551d8a4520a0126783c3c4c4dd3f36f57a5b3dd43484e59dda7a34b5"
    - "C6 target preflight binds its parent directly to accepted C5, requires report+new-script-only checkpoint scope and byte-for-byte append-only report history, preserves .ai-bridge as untracked machine state, and requires the exact accepted target machine/readiness/Piston hashes"
    - "C6 revalidates exact RTX4090/VRAM/CC8.9/BF16, Python/CUDA/package lock/Open-R1, offline base-model SHA, formal B adapter SHAs, formal data, pilot pair, Piston tunnel/runtime, and accepted C5 target evidence plus complete smoke checkpoint-10/checkpoint-20 before pilot execution"
    - "pilot restart is trainer_checkpoint: absent run starts fresh from formal B; incomplete same-C6 run may resume only its latest complete cadence checkpoint; different-checkpoint/unknown/incomplete-without-valid-checkpoint state fails closed without deletion or quarantine"
    - "pilot postcheck requires completed independent Public/Hidden global_step=100 runs, complete checkpoint-50/checkpoint-100, finite metrics/reward/group/cost data, distinct visible-tests vs train-hidden reward sources, and emits raw spec 12.4 reward/std/KL/loss/completion/parse/execute/timeout/pass/executor-runtime telemetry without inventing numerical stopping thresholds"
    - "C6 shell syntax PASS; all 13 embedded Python heredocs compile; train-grpo has exactly one command site; formal public/hidden configs and historical C2/C3 recovery logic are absent"
    - "fresh control-plane regression PASS after C5 acceptance: pinned GRPOTrainer constructor 1/1; make lint; make test 931 passed / 3 expected real-Piston opt-in skips / 0 failed; make test-gpu 3/3; real make test-piston 9/9 with 0 skips"
    - "C6 run.sh is mode 0755 and frozen SHA256 8d37f8c775fe5122988106b5b098f074b3d379ece4776cd47a9370e5b9ebb96e; no RTX4090 pilot/formal/generation command was started, no formal data/B/dependency mutation occurred, and no push was performed"
  remaining_scope:
    - "make the exact C6 checkpoint commit reachable on the RTX 4090 through ordinary Git transport, checkout/detach that exact commit, verify a clean checkout and the recorded C6 run.sh SHA256, then run only the tracked C6 script manually in SSH/tmux"
    - "C6 target start must pass accepted-C5 provenance, exact target machine/runtime/model/data/B/Piston/storage gates before either Public or Hidden pilot starts; do not manually bypass a failed preflight"
    - "after C6 exits, sync operator-evidence.json, status, terminal.log, postcheck-summary.json, required small pilot metadata/metrics/rewards/group data and final C/D pilot LoRA adapters byte-for-byte to the C6 control-plane receive directory; numeric Trainer checkpoints remain on the 4090 by default"
    - "explicitly invoke execution-router resume backend=web stage_id=WP7-c after C6 evidence is received; executor must inspect the raw spec-12.4 telemetry for an explicit stop signal before any grpo-cd-formal operator checkpoint can be generated"
  status: awaiting_operator
```

### C6 pilot boundary notes

- C6 is a new gate after accepted C5, not a smoke repair. Historical C5 text saying C6 had not yet been created remains true for the C5 checkpoint and is intentionally not rewritten; this section is append-only continuation after C5 evidence acceptance.
- Public and Hidden pilot runs remain independent children of the same formal B. Neither consumes the C5 smoke adapter nor the other pilot branch; C5 artifacts are used only as accepted gate evidence and checkpoint-size input for the pilot storage bound.
- The operator postcheck records the raw spec §12.4 signals available in production artifacts. The project does not currently persist a separate rollout-runtime field, so C6 records `rollout_runtime_seconds_recorded=false` rather than fabricating one; executor resume will interpret only the actually recorded raw evidence and will not invent unsealed numerical thresholds.
- No RTX4090 command was started or monitored while preparing C6. This execution conversation stops at the portable target-GPU operator boundary.

### C7 — GRPO inference optimization + complete pilot timing telemetry

C6 was never executed on the RTX 4090. Before paying for the paired 100-step pilot, the training path was re-audited against the accepted C5 smoke logs. The smoke showed Piston executor time below 1% of train time while CUDA allocated/reserved memory stayed far below the 4090's 24 GB capacity. The actionable bottleneck was instead inference-only work inheriting gradient checkpointing from the training model: regular generation and the beta=0.01 no-grad reference log-prob forward. Result-code commit `8f8e3e0f5040574e6fcca9401a71281e1e9660ad` adds a narrow project-local shim that disables gradient checkpointing only around those inference-only calls, always restores it, leaves the grad-enabled policy forward unchanged, and records generation/rollout/no-grad-logps/optimizer-step wall time into the existing Trainer metric stream. C7 supersedes the unexecuted C6 operator handoff without deleting it.

```yaml
execution_checkpoint:
  version: 1
  checkpoint_id: C7
  stage_id: WP7-c
  task_kind: implementation
  source_plan_commit: 8464e69691c527c726a2e28e5a7ca81fa2001bbf
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: 8f8e3e0f5040574e6fcca9401a71281e1e9660ad
  interruption_class: operator
  resume_allowed: true
  operator_gate_id: grpo-cd-pilot
  operator_handoff_mode: portable_target
  operator_restart_policy: trainer_checkpoint
  operator_script: ai-work/executor/operator/WP7-c/grpo-cd-pilot/C7/run.sh
  operator_script_sha256: 97e2212aec51938d14c322b5a8f54ddf852958ae81edadcdeb8a3c3792b67108
  target_machine_pointer_template: .ai-bridge/validation-machine.json
  target_status_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-pilot/C7/status"
  target_log_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-pilot/C7/terminal.log"
  target_evidence_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-pilot/C7/operator-evidence.json"
  target_postcheck_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-pilot/C7/postcheck-summary.json"
  control_plane_evidence_receive_dir: /home/dzy/wp7c-operator-evidence/WP7-c/grpo-cd-pilot/C7
  prior_operator_checkpoint_commit: ae429f2dc0ed7353d5a3de0adb0d71b58a879a3d
  accepted_prior_operator_evidence_sha256: f1e3b350d11a4af13118a2517bbbbfb95df752b6cded126c80492ba40b163a5e
  accepted_prior_postcheck_sha256: 94b052e9c14f4842b45c35c2ce0d9f108cd6e382ff99e50293544b83039c2b8a
  pilot_pair_sha256: a82c7521551d8a4520a0126783c3c4c4dd3f36f57a5b3dd43484e59dda7a34b5
  supersedes_checkpoint_id: C6
  supersedes_checkpoint_commit: db42c382a6499ca771ae95a7d8b2472c3960a8b8
  smoke_max_complete_trainer_checkpoint_bytes: 42184437
  smoke_max_complete_trainer_checkpoint_inodes: 15
  target_required_free_bytes: 32212254720
  target_required_free_inodes: 100000
  expected_artifacts:
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/pilot/C-public-grpo-pilot100-seed42/run.json"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/pilot/C-public-grpo-pilot100-seed42/metrics.jsonl"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/pilot/C-public-grpo-pilot100-seed42/rollouts.jsonl"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/pilot/C-public-grpo-pilot100-seed42/rewards.jsonl"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/pilot/C-public-grpo-pilot100-seed42/group_metrics.jsonl"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/pilot/C-public-grpo-pilot100-seed42/checkpoints/adapter_model.safetensors"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/pilot/D-hidden-grpo-pilot100-seed42/run.json"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/pilot/D-hidden-grpo-pilot100-seed42/metrics.jsonl"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/pilot/D-hidden-grpo-pilot100-seed42/rollouts.jsonl"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/pilot/D-hidden-grpo-pilot100-seed42/rewards.jsonl"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/pilot/D-hidden-grpo-pilot100-seed42/group_metrics.jsonl"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/pilot/D-hidden-grpo-pilot100-seed42/checkpoints/adapter_model.safetensors"
  completed_scope:
    - "C5 smoke performance evidence was re-audited before pilot: Public train runtime about 1400 s with executor about 12 s, Hidden about 1639 s with executor about 13.4 s; executor share is below 1%, while smoke peak CUDA allocated/reserved remained far below 24 GB, so Piston concurrency and sealed batch hyperparameters were not changed"
    - "result-code 8f8e3e0f5040574e6fcca9401a71281e1e9660ad keeps batch=1, gradient_accumulation_steps=8, gradient_checkpointing=true, LoRA/reward/seed/pair semantics unchanged; it disables gradient checkpointing only for regular generation and torch.no_grad reference log-prob work, restores it in finally blocks, and leaves the grad-enabled policy forward untouched"
    - "the same runtime shim records generation_runtime_seconds, rollout_runtime_seconds, no_grad_logps_runtime_seconds, no_grad_logps_calls and step_runtime_seconds through TRL's existing _metrics/log_history path; artifact tests prove the scalars persist to metrics.jsonl and remain readable by load_training_curve_rows"
    - "real pinned TRL 0.18.0 + tiny Qwen2 + PEFT one-step train PASS under the production DeepSpeed guard: gradient checkpointing is restored after inference-only calls; generation/rollout/no-grad-logps/step timings are finite; beta=0.01 produces one no-grad reference call per micro-batch; the previous generation/cache and no-grad checkpoint warnings are absent"
    - "post-optimization regression PASS: focused GRPO/WP7a/WP7b suite 82/82; make lint/ruff/mypy PASS; full make test 932 passed / 3 expected real-Piston opt-in skips / 0 failed; make test-gpu 3/3; real make test-piston 9/9"
    - "C7 postcheck requires complete steps 1..100 telemetry for reward/reward_std/KL/loss/completion plus generation/rollout/no-grad-logps/step timing; requires no_grad_logps_calls=8 per optimizer step and validates rollout>=generation and step>=rollout+no-grad-logps"
    - "C7 postcheck emits per-step timing series plus mean/p95/max, generation/rollout/no-grad-logps fractions of optimizer-step wall time, executor fraction of train and rollout time, and generated-token throughput; it still records raw metrics only and invents no numerical stopping threshold"
    - "C7 provenance requires checkpoint parent=result-code 8f8e3e0..., result-code parent=superseded C6 checkpoint db42c382..., accepted C5 smoke evidence unchanged, checkpoint scope exactly append-only execution report + new executable C7 script, and tracked script SHA equal to this record"
    - "C7 shell syntax PASS; all 13 Python heredocs compile; only two C6 references remain and both are explicit supersession provenance; train-grpo still has one command site; no RTX4090 pilot/formal command was started while preparing C7"
  remaining_scope:
    - "make the exact C7 checkpoint commit reachable on the RTX 4090 through ordinary Git transport, checkout/detach that exact commit, verify a clean checkout and recorded C7 run.sh SHA256, then run only the tracked C7 script manually in SSH/tmux; do not run C6"
    - "C7 target start must pass checkpoint/result/supersession provenance, accepted-C5 evidence, exact machine/runtime/model/data/B/Piston/storage gates before Public or Hidden pilot starts; do not bypass a failed preflight"
    - "after C7 exits, sync operator-evidence.json, status, terminal.log, postcheck-summary.json and the required small pilot metadata/metrics/reward/group/final-adapter evidence byte-for-byte into the C7 control-plane receive directory; numeric Trainer checkpoints remain on the 4090 by default"
    - "explicitly invoke execution-router resume backend=web stage_id=WP7-c after C7 evidence is received; executor must analyze the newly complete timing + reward/KL/completion/execution telemetry before any formal C/D operator checkpoint is generated"
  status: awaiting_operator
```

### C7 performance/data-analysis notes

- This change intentionally does **not** increase `per_device_train_batch_size`, reduce gradient accumulation, disable training gradient checkpointing, enable vLLM, change LoRA, alter max completion length, or modify reward execution. Those are sealed C/D fairness or semantic choices; the pre-pilot optimization is restricted to inference-only implementation overhead.
- The pilot now leaves enough structured evidence to attribute expensive wall time among generation, whole rollout, no-grad reference/KL log-prob, remaining policy forward/backward+optimizer work, and Piston execution. Together with reward component rows, group variance/all-equal, completion lengths/truncation, parse/execute/timeout/pass status, KL/loss, GPU-hours, peak CUDA memory and checkpoint inventory, this is sufficient for the planned final performance/cost/reward analysis without rerunning merely to recover missing timing fields.
- C6 remains in immutable Git/report history as an unexecuted operator checkpoint. C7 is the only current pilot handoff and supersedes it explicitly.
- No RTX4090 target command was started or monitored while preparing C7.


### C8 — portable GRPO pair identity repair after C7 preflight failure

C7 was executed on the RTX 4090 but failed safely during preflight before either pilot branch was created. Read-only target inspection proved `command_rc=125`, `postcheck_rc=125`, `gate_status=preflight_failed`, no postcheck file, every expected pilot inventory entry `exists=false`, and no Public/Hidden pilot run directory. The failure was traced to paired-definition schema v1 hashing machine-local absolute dataset/Piston/SFT paths. Result-code commit `9e55b4175e5d86804d1ce182e04489e4b5f99a87` fixes the root cause by introducing paired-definition schema v2: single-run config/resume hashes remain unchanged, while only the C/D pair fingerprint replaces dataset/Piston paths with content SHA256 and removes parent-SFT artifact paths from the pair canonical payload.

```yaml
execution_checkpoint:
  version: 1
  checkpoint_id: C8
  stage_id: WP7-c
  task_kind: implementation
  source_plan_commit: 8464e69691c527c726a2e28e5a7ca81fa2001bbf
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: 9e55b4175e5d86804d1ce182e04489e4b5f99a87
  interruption_class: operator
  resume_allowed: true
  operator_gate_id: grpo-cd-pilot
  operator_handoff_mode: portable_target
  operator_restart_policy: trainer_checkpoint
  operator_script: ai-work/executor/operator/WP7-c/grpo-cd-pilot/C8/run.sh
  operator_script_sha256: 18bbbaddbe00a5c0f610a49b65307d583172eea5c32381cd97be7444fbb21c06
  target_machine_pointer_template: .ai-bridge/validation-machine.json
  target_status_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-pilot/C8/status"
  target_log_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-pilot/C8/terminal.log"
  target_evidence_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-pilot/C8/operator-evidence.json"
  target_postcheck_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-pilot/C8/postcheck-summary.json"
  control_plane_evidence_receive_dir: /home/dzy/wp7c-operator-evidence/WP7-c/grpo-cd-pilot/C8
  prior_operator_checkpoint_commit: ae429f2dc0ed7353d5a3de0adb0d71b58a879a3d
  accepted_prior_operator_evidence_sha256: f1e3b350d11a4af13118a2517bbbbfb95df752b6cded126c80492ba40b163a5e
  accepted_prior_postcheck_sha256: 94b052e9c14f4842b45c35c2ce0d9f108cd6e382ff99e50293544b83039c2b8a
  pilot_pair_schema_version: 2
  pilot_pair_sha256: b889cf144b787854c73a6b97c9a26d1a0378dee9ba1e822b965c1ef85c637be2
  pilot_public_config_hash: e288b89419ea0aa2a780cf03b6ed72921d4f6395e4feaf5169e2db2dcb57100c
  pilot_hidden_config_hash: 97ee2444a5a3e6709f9347d606f391d0b6ec3b380d3ce74e230b972631958b07
  supersedes_checkpoint_id: C7
  supersedes_checkpoint_commit: ef89d8898cbc2c6d3da2a5c327afc5b22cb83beb
  superseded_result_code_commit: 8f8e3e0f5040574e6fcca9401a71281e1e9660ad
  superseded_operator_script_sha256: 97e2212aec51938d14c322b5a8f54ddf852958ae81edadcdeb8a3c3792b67108
  superseded_operator_evidence_sha256: 1e3a20e6edff2b9e4949bb38a45d12951fc3d86a4032964b7e2bb2b726f2485a
  superseded_status_sha256: a5e45837a2959db847f7e67a915d0ecaddd47f943af2af5fa6453be497faabca
  superseded_terminal_log_sha256: 19835ff50a5d9cb907b54fb4500278d6c3642a0c011478069c8416c8f113d1eb
  smoke_max_complete_trainer_checkpoint_bytes: 42184437
  smoke_max_complete_trainer_checkpoint_inodes: 15
  target_required_free_bytes: 32212254720
  target_required_free_inodes: 100000
  completed_scope:
    - "C7 target failure was revalidated read-only on the 4090: exact evidence/status/log SHAs, rc=125, preflight_failed, no postcheck, paired_definition_sha256=null, all expected artifact inventory entries absent and both pilot run directories absent"
    - "root cause confirmed: paired-definition schema v1 transitively included absolute dataset_path and piston_config through _config_hash plus parent_sft_run_path/checkpoint_path, so identical semantic experiments differed across 1660ti and 4090"
    - "result-code 9e55b4175e5d86804d1ce182e04489e4b5f99a87 bumps paired-definition schema to v2 and adds a dedicated portable pair config hash using dataset/Piston content SHA256 plus a parent SFT semantic mapping without local artifact paths; single-run _config_hash and resume identity remain unchanged"
    - "new portability regression constructs byte-identical C/D/Piston/B inputs under two different absolute roots: old single-run config hashes remain different while v2 pair components and pair SHA are exactly equal"
    - "formal v2 control-plane certification yields pair SHA b889cf144b787854c73a6b97c9a26d1a0378dee9ba1e822b965c1ef85c637be2, Public pair-config SHA e288b89419ea0aa2a780cf03b6ed72921d4f6395e4feaf5169e2db2dcb57100c and Hidden pair-config SHA 97ee2444a5a3e6709f9347d606f391d0b6ec3b380d3ce74e230b972631958b07"
    - "post-repair verification PASS: focused GRPO/WP7a/WP7b 83/83; make lint/ruff/mypy PASS; full make test 933 passed / 3 expected real-Piston opt-in skips / 0 failed; make test-gpu 3/3; real make test-piston 9/9"
    - "C8 retains C7 timing/performance instrumentation and postcheck, rebinds all fresh/resume/completed semantics to portable v2 pair identity, and validates exact C7 failure evidence before Piston or training"
    - "C8 bash syntax PASS; all 14 Python heredocs compile; stale v1 pair SHA and C6 semantics are absent; train-grpo has exactly one command site"
  remaining_scope:
    - "push the exact C8 checkpoint through ordinary Git, checkout/detach it on the RTX 4090, verify clean checkout and C8 script SHA, then run only C8; do not rerun C7"
    - "C8 must authenticate the preserved C7 preflight failure and zero-pilot-artifact state, then recompute portable pair v2 and match the exact control-plane pair/components before Public training starts"
    - "after C8 exits, sync C8 operator evidence/status/log/postcheck and required small pilot artifacts/final adapters back to the C8 control-plane receive directory, then invoke execution-router resume backend=web stage_id=WP7-c"
  status: awaiting_operator
```

### C8 repair notes

- C7 failure evidence remains immutable on the 4090; C8 neither deletes nor rewrites it.
- The fix changes only experiment identity portability. It does not change GRPO batch size, gradient accumulation, optimization hyperparameters, LoRA, reward math, dataset bytes, formal B, Piston definition or timing instrumentation.
- No C8 target command was started while preparing this checkpoint.

## C9 — Piston infrastructure fail-closed repair + 10-step pilot checkpoints

The executed C8 pilot is preserved as infrastructure-invalid evidence rather than reused. C8 Public reached trainer step 100, but reward telemetry proves the Piston transport began failing at optimizer step 36: 495/800 reward rows are infrastructure failures, the last fully healthy optimizer step is 35, and no pre-failure Trainer checkpoint exists because the C8 cadence was 50. C8 Hidden never created a run directory. The retry therefore must start Public and Hidden independently from the same formal B under new run names.

```yaml
execution_checkpoint:
  checkpoint_id: C9
  source_plan_commit: 8464e69691c527c726a2e28e5a7ca81fa2001bbf
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: 78d4aebd36d916db3c8d160dcfa89f5425affc22
  fail_closed_result_code_commit: b58667f4ff1e34e1e1e13e2f78fef21cb118fdf9
  interruption_class: operator
  resume_allowed: true
  operator_gate_id: grpo-cd-pilot
  operator_handoff_mode: portable_target
  operator_restart_policy: trainer_checkpoint
  operator_script: ai-work/executor/operator/WP7-c/grpo-cd-pilot/C9/run.sh
  operator_script_sha256: bae1e5ec8f0b4c29b86401e547ced8fc818b1b90af6c7d0d6b4bde708d15dcfa
  target_machine_pointer_template: .ai-bridge/validation-machine.json
  target_status_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-pilot/C9/status"
  target_log_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-pilot/C9/terminal.log"
  target_evidence_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-pilot/C9/operator-evidence.json"
  target_postcheck_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-pilot/C9/postcheck-summary.json"
  control_plane_evidence_receive_dir: /home/dzy/wp7c-operator-evidence/WP7-c/grpo-cd-pilot/C9
  prior_operator_checkpoint_commit: ae429f2dc0ed7353d5a3de0adb0d71b58a879a3d
  accepted_prior_operator_evidence_sha256: f1e3b350d11a4af13118a2517bbbbfb95df752b6cded126c80492ba40b163a5e
  accepted_prior_postcheck_sha256: 94b052e9c14f4842b45c35c2ce0d9f108cd6e382ff99e50293544b83039c2b8a
  pilot_pair_schema_version: 2
  pilot_pair_sha256: bb8a733b2f6b9519d6e9c9de087461a975ba830f6c132a8f06120881576b512f
  pilot_public_config_hash: da543a9ac2719076fd81696dbcb98f1df9c9254adc9e9f519569b3b0d2e09dac
  pilot_hidden_config_hash: 5036e0aa8be941f145f52e08269e808948f091c80d5d0972ef50326417934658
  pilot_public_run_name: C-public-grpo-pilot100-retry1-seed42
  pilot_hidden_run_name: D-hidden-grpo-pilot100-retry1-seed42
  pilot_max_steps: 100
  pilot_save_steps: 10
  expected_trainer_checkpoints: [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
  supersedes_checkpoint_id: C8
  supersedes_checkpoint_commit: 32ab2697b33c9a211c37c78f0871808de069b658
  superseded_result_code_commit: 9e55b4175e5d86804d1ce182e04489e4b5f99a87
  superseded_operator_script_sha256: 18bbbaddbe00a5c0f610a49b65307d583172eea5c32381cd97be7444fbb21c06
  superseded_operator_evidence_sha256: def49dcb2d838e8ff8a740250ad392a3dee34c54774d808c3c4b82630451b594
  superseded_status_sha256: 53c234e5e8472b6ac51c1ae1cab3fe06fad053beb8ebfd8977b010655bfdd3c3
  superseded_terminal_log_sha256: b9052153a341093732d8dee9d312bb3437cfe8a12ccafeb3537200fccc4e0b90
  superseded_public_run_json_sha256: 557f880a199ef6ddcfa5127d85d8cb1e98a68c00fe982423dc79c0f0c260d59e
  superseded_public_rewards_sha256: 4a3dba109be0dfa51949e61383ef35e2f59f4bc084580b80b5e84142f7e22226
  superseded_public_final_adapter_sha256: 41d01287ef7c21494bfb0e13910f7238a45802068c658631b68ef80dcd89b32b
  superseded_public_first_infrastructure_failure_step: 36
  superseded_public_infrastructure_failure_rows: 495
  smoke_max_complete_trainer_checkpoint_bytes: 42184437
  smoke_max_complete_trainer_checkpoint_inodes: 15
  target_required_free_bytes: 32212254720
  target_required_free_inodes: 100000
  completed_scope:
    - "C8 target failure was diagnosed read-only: Public command rc=0 but became infrastructure-invalid from optimizer step 36; 495/800 reward rows report infrastructure_failure/sandbox_error; Hidden failed before run creation when the Piston tunnel endpoint was refused"
    - "C8 operator evidence/status/log are preserved byte-for-byte and C9 preflight authenticates their exact SHAs plus the preserved invalid Public run signatures; C9 does not delete, rename or resume the C8 Public run"
    - "b58667f4ff1e34e1e1e13e2f78fef21cb118fdf9 changes only the GRPO training callback path so infrastructure-failure reward batches are fsync-logged and then raise GRPOTrainingError before rewards return to Trainer/optimizer; reward formula/evaluation representation remains unchanged"
    - "the fail-closed regression proves a sandbox/infrastructure failure writes sanitized reward/rollout/group evidence and aborts instead of returning zero reward to training"
    - "78d4aebd36d916db3c8d160dcfa89f5425affc22 changes both validation pilot configs from save_steps=50 to save_steps=10 and locks the cadence in unit/integration tests; batch, gradient accumulation, learning rate, reward source, LoRA, seed and max_steps remain unchanged"
    - "C9 retry run names are new, so invalid C8 checkpoints cannot be selected; normal resume chooses the highest complete checkpoint whose step is a multiple of config.save_steps, now 10"
    - "C9 reruns the target Piston tunnel helper immediately before each Public/Hidden train-grpo invocation; if transport later fails during reward execution, training now fails closed on the first affected reward batch"
    - "C9 postcheck requires complete checkpoint-10/20/30/40/50/60/70/80/90/100 for both retry runs, in addition to the existing 100-step timing/reward/rollout/cost telemetry checks"
    - "formal retry pair v2 certification yields pair SHA bb8a733b2f6b9519d6e9c9de087461a975ba830f6c132a8f06120881576b512f, Public pair-config SHA da543a9ac2719076fd81696dbcb98f1df9c9254adc9e9f519569b3b0d2e09dac and Hidden pair-config SHA 5036e0aa8be941f145f52e08269e808948f091c80d5d0972ef50326417934658"
    - "verification PASS after the combined repair: focused GRPO/WP7a/WP7b 85/85; make lint/ruff/mypy PASS; full make test 935 passed / 3 expected real-Piston opt-in skips / 0 failed; make test-gpu 3/3; real make test-piston 9/9"
    - "C9 bash syntax PASS; all 15 Python heredocs compile; actual train-grpo command site count=1; old retry pair SHA absent; C8 run-name/pair references are restricted to superseded-history validation"
  remaining_scope:
    - "push the exact C9 checkpoint through ordinary Git, checkout/detach it on the RTX 4090, verify clean checkout and C9 script SHA, then run only C9; do not rerun C8"
    - "C9 must authenticate the preserved C8 infrastructure-invalid evidence, recompute retry pair v2, ensure the Piston tunnel before each branch and start new Public/Hidden retry runs independently from formal B"
    - "if C9 is interrupted after any complete 10-step Trainer checkpoint, rerunning the exact C9 script may resume from the highest complete valid checkpoint; never manually edit or replace run artifacts"
    - "after C9 exits successfully, sync C9 operator evidence/status/log/postcheck and required small retry pilot artifacts/final adapters back to the C9 control-plane receive directory, then invoke execution-router resume backend=web stage_id=WP7-c"
  status: awaiting_operator
```

### C9 repair notes

- C8 remains immutable history. Its Public run is intentionally preserved as infrastructure-invalid evidence and is not a parent or resume source for C9.
- The user-requested 10-step checkpoint cadence is an operational recoverability change only; C/D receive the same cadence and all model/reward optimization semantics remain paired.
- Numeric Trainer checkpoints remain on the RTX 4090 by default; only required small evidence and final LoRA adapters are synced back after a successful run.
- No C9 target training command was started while preparing this checkpoint.

## C10 — pre-push GRPO recovery audit hardening

C9 was not executed by the operator. A pre-push audit found a remaining resume-evidence flaw: a failed attempt after a valid Trainer checkpoint could append reward/rollout/group rows beyond that checkpoint; resuming the model from the checkpoint without restoring the canonical JSONL boundary would mix failed-attempt rows with the replayed canonical trajectory. C10 supersedes the unexecuted C9 and retains the same retry1 C/D pair and 10-step checkpoint cadence.

```yaml
execution_checkpoint:
  checkpoint_id: C10
  source_plan_commit: 8464e69691c527c726a2e28e5a7ca81fa2001bbf
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: 24685d7e9587fdd9e072fa871d0a66f22bff9caf
  interruption_class: operator
  resume_allowed: true
  operator_gate_id: grpo-cd-pilot
  operator_handoff_mode: portable_target
  operator_restart_policy: trainer_checkpoint
  operator_script: ai-work/executor/operator/WP7-c/grpo-cd-pilot/C10/run.sh
  operator_script_sha256: 06499d2b00b0799f4b277b130d095e498ec1fafe5753eb862c33824735739b49
  target_machine_pointer_template: .ai-bridge/validation-machine.json
  target_status_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-pilot/C10/status"
  target_log_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-pilot/C10/terminal.log"
  target_evidence_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-pilot/C10/operator-evidence.json"
  target_postcheck_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-pilot/C10/postcheck-summary.json"
  control_plane_evidence_receive_dir: /home/dzy/wp7c-operator-evidence/WP7-c/grpo-cd-pilot/C10
  prior_operator_checkpoint_commit: ae429f2dc0ed7353d5a3de0adb0d71b58a879a3d
  accepted_prior_operator_evidence_sha256: f1e3b350d11a4af13118a2517bbbbfb95df752b6cded126c80492ba40b163a5e
  accepted_prior_postcheck_sha256: 94b052e9c14f4842b45c35c2ce0d9f108cd6e382ff99e50293544b83039c2b8a
  pilot_pair_schema_version: 2
  pilot_pair_sha256: bb8a733b2f6b9519d6e9c9de087461a975ba830f6c132a8f06120881576b512f
  pilot_public_config_hash: da543a9ac2719076fd81696dbcb98f1df9c9254adc9e9f519569b3b0d2e09dac
  pilot_hidden_config_hash: 5036e0aa8be941f145f52e08269e808948f091c80d5d0972ef50326417934658
  pilot_public_run_name: C-public-grpo-pilot100-retry1-seed42
  pilot_hidden_run_name: D-hidden-grpo-pilot100-retry1-seed42
  pilot_max_steps: 100
  pilot_save_steps: 10
  expected_trainer_checkpoints: [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
  checkpoint_log_state_file: code_verifier_log_state.json
  recovery_history_dir: checkpoints/recovery-history
  supersedes_checkpoint_id: C9
  supersedes_checkpoint_commit: 792f637f34ccabebbc61fde61bd861f20887f217
  superseded_result_code_commit: 78d4aebd36d916db3c8d160dcfa89f5425affc22
  superseded_operator_script_sha256: bae1e5ec8f0b4c29b86401e547ced8fc818b1b90af6c7d0d6b4bde708d15dcfa
  superseded_execution_state: unexecuted_by_operator
  preserved_invalid_c8_checkpoint_commit: 32ab2697b33c9a211c37c78f0871808de069b658
  preserved_invalid_c8_operator_evidence_sha256: def49dcb2d838e8ff8a740250ad392a3dee34c54774d808c3c4b82630451b594
  smoke_max_complete_trainer_checkpoint_bytes: 42184437
  smoke_max_complete_trainer_checkpoint_inodes: 15
  target_required_free_bytes: 32212254720
  target_required_free_inodes: 100000
  completed_scope:
    - "pre-push audit found and repaired canonical streaming-log contamination on resume: Trainer model state could roll back to checkpoint-N while rewards.jsonl/rollouts.jsonl/group_metrics.jsonl still contained rows from the failed suffix after N"
    - "each newly saved Trainer checkpoint now receives code_verifier_log_state.json after upstream _save_checkpoint returns; the sidecar records exact byte size, line count and SHA256 for the three canonical streaming JSONL files at that checkpoint boundary"
    - "resume validation is read-only before attempt begin and requires the selected checkpoint sidecar plus exact prefix identities; a missing sidecar makes that checkpoint ineligible, while a present-but-mismatched sidecar/prefix fails closed"
    - "after a resume attempt is recorded, the complete pre-rollback streaming logs are fsync-copied into checkpoints/recovery-history/before-attempt-N-resume-checkpoint-S with a manifest, then canonical logs are atomically restored to the selected checkpoint boundary before Trainer model loading/train resumes"
    - "recovery-history lives under checkpoints so the strict top-level GRPO run layout remains unchanged; repeated recovery from the same checkpoint is covered and preserves a distinct archive for each attempt"
    - "the training executor now has an attempt-local circuit breaker: after the first executor exception or sandbox_error, subsequent completions in that reward batch fail locally rather than repeatedly waiting on the unavailable remote Piston transport; the full batch is still sanitized/logged and GRPOTrainingError is raised before rewards return to Trainer"
    - "real pinned TRL 0.18 tiny-Qwen CPU regression PASS: production timing hook and checkpoint-log hook compose on a real GRPOTrainer.train(), checkpoint-1 receives a matching sidecar, and gradient checkpointing remains restored"
    - "real pinned TRL failure regression PASS: a reward exception during rollout leaves trainer global_step=0, creates no checkpoint-1 and leaves every model parameter unchanged, directly proving the failure propagates before optimizer update"
    - "focused GRPO/WP7a/WP7b regression PASS 90/90; make lint/ruff/mypy PASS; full make test 940 passed / 3 expected real-Piston opt-in skips / 0 failed; make test-gpu 3/3; real make test-piston 9/9"
    - "C10 retains C9 retry1 run names, pair v2 SHA and save_steps=10 because the recovery-hardening result-code commit changes no pilot config/data/B/pair-definition inputs"
    - "C10 resume selects only complete cadence checkpoints with the required Trainer files and a valid canonical-log sidecar; postcheck requires and validates sidecars for checkpoint-10 through checkpoint-100 for both Public and Hidden"
    - "C10 target preflight requires the C9 operator root to be absent, consistent with the operator statement that no C9 operation was executed; preserved C8 infrastructure-invalid evidence remains independently authenticated"
    - "C10 bash syntax PASS; all 15 Python heredocs compile; actual train-grpo command site count=1; C11 is absent"
  remaining_scope:
    - "push the exact C10 checkpoint through ordinary Git, checkout/detach it on the RTX 4090, verify clean checkout and C10 script SHA, then run only C10; do not run C9 or rerun C8"
    - "C10 must authenticate C9 as unexecuted, authenticate preserved C8 infrastructure-invalid evidence, recompute the unchanged retry pair v2, ensure the Piston tunnel before each branch and start/continue only the C10 retry1 runs"
    - "if C10 is interrupted, rerunning the exact C10 script resumes only from the highest complete 10-step checkpoint with a valid canonical-log sidecar; failed-attempt log suffixes remain in recovery-history and are excluded from canonical analysis"
    - "after C10 exits successfully, sync C10 operator evidence/status/log/postcheck and required small retry pilot artifacts/final adapters back to the C10 control-plane receive directory, then invoke execution-router resume backend=web stage_id=WP7-c"
  status: awaiting_operator
```

### C10 audit notes

- C9 remains immutable and unexecuted; C10 supersedes it before any target training or evidence was produced.
- C8 remains immutable infrastructure-invalid history and is never a parent or resume source for retry1.
- The audit hardening changes recovery/evidence semantics and executor failure handling only. It does not change batch size, gradient accumulation, learning rate, reward formula/source, LoRA, seed, max steps, data bytes, formal B or the paired experiment definition.
- No C10 target command was started while preparing this checkpoint.

## C11 — stale-running recovery guard handoff

C9 and C10 were not executed. The final pre-push recovery audit added one conservative business guard after C10: a GRPO run left as `status=running` by a hard interruption is not automatically resumable, because its attempt cost/end-state was never durably finalized. Only a run that the training process has gracefully closed to `status=failed` may resume from a validated Trainer checkpoint. C11 supersedes the unexecuted C10 and retains the same retry1 C/D pair, fail-closed Piston behavior, canonical-log sidecars, and 10-step checkpoint cadence.

```yaml
execution_checkpoint:
  checkpoint_id: C11
  source_plan_commit: 8464e69691c527c726a2e28e5a7ca81fa2001bbf
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: e6622a40c0449477079710e0fe875e216278e13c
  recovery_hardening_commit: 24685d7e9587fdd9e072fa871d0a66f22bff9caf
  interruption_class: operator
  resume_allowed: true
  operator_gate_id: grpo-cd-pilot
  operator_handoff_mode: portable_target
  operator_restart_policy: trainer_checkpoint
  operator_script: ai-work/executor/operator/WP7-c/grpo-cd-pilot/C11/run.sh
  operator_script_sha256: d390dcd95c0f48702dbb14014b4efb6c3d848634d2c258fa74d30c1a6503af84
  target_machine_pointer_template: .ai-bridge/validation-machine.json
  target_status_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-pilot/C11/status"
  target_log_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-pilot/C11/terminal.log"
  target_evidence_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-pilot/C11/operator-evidence.json"
  target_postcheck_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-pilot/C11/postcheck-summary.json"
  control_plane_evidence_receive_dir: /home/dzy/wp7c-operator-evidence/WP7-c/grpo-cd-pilot/C11
  prior_operator_checkpoint_commit: ae429f2dc0ed7353d5a3de0adb0d71b58a879a3d
  accepted_prior_operator_evidence_sha256: f1e3b350d11a4af13118a2517bbbbfb95df752b6cded126c80492ba40b163a5e
  accepted_prior_postcheck_sha256: 94b052e9c14f4842b45c35c2ce0d9f108cd6e382ff99e50293544b83039c2b8a
  pilot_pair_schema_version: 2
  pilot_pair_sha256: bb8a733b2f6b9519d6e9c9de087461a975ba830f6c132a8f06120881576b512f
  pilot_public_config_hash: da543a9ac2719076fd81696dbcb98f1df9c9254adc9e9f519569b3b0d2e09dac
  pilot_hidden_config_hash: 5036e0aa8be941f145f52e08269e808948f091c80d5d0972ef50326417934658
  pilot_public_run_name: C-public-grpo-pilot100-retry1-seed42
  pilot_hidden_run_name: D-hidden-grpo-pilot100-retry1-seed42
  pilot_max_steps: 100
  pilot_save_steps: 10
  expected_trainer_checkpoints: [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
  checkpoint_log_state_file: code_verifier_log_state.json
  recovery_history_dir: checkpoints/recovery-history
  supersedes_checkpoint_id: C10
  supersedes_checkpoint_commit: d9af548d49cc8f781984f31ea70817e4afa9f1b1
  superseded_result_code_commit: 24685d7e9587fdd9e072fa871d0a66f22bff9caf
  superseded_operator_script_sha256: 06499d2b00b0799f4b277b130d095e498ec1fafe5753eb862c33824735739b49
  superseded_execution_state: unexecuted_by_operator
  unexecuted_c9_checkpoint_commit: 792f637f34ccabebbc61fde61bd861f20887f217
  unexecuted_c9_operator_script_sha256: bae1e5ec8f0b4c29b86401e547ced8fc818b1b90af6c7d0d6b4bde708d15dcfa
  preserved_invalid_c8_checkpoint_commit: 32ab2697b33c9a211c37c78f0871808de069b658
  preserved_invalid_c8_operator_evidence_sha256: def49dcb2d838e8ff8a740250ad392a3dee34c54774d808c3c4b82630451b594
  smoke_max_complete_trainer_checkpoint_bytes: 42184437
  smoke_max_complete_trainer_checkpoint_inodes: 15
  target_required_free_bytes: 32212254720
  target_required_free_inodes: 100000
  completed_scope:
    - "result-code e6622a40c0449477079710e0fe875e216278e13c is a narrow post-C10 business guard: its diff is exactly src/code_verifier/training/grpo.py plus tests/unit/training/test_grpo.py"
    - "resume metadata validation now accepts only status=failed; stale status=running from hard power/process loss fails closed instead of appending a new attempt with unverifiable prior cost/end state"
    - "test_grpo_resume_rejects_stale_running_attempt_after_hard_interruption locks that behavior; intentional Ctrl-C/KeyboardInterrupt still passes through the existing BaseException finalizer, which writes status=failed and cumulative attempt gpu_hours before re-raising"
    - "the preceding recovery-hardening commit remains unchanged: each Trainer checkpoint carries code_verifier_log_state.json, failed-attempt stream suffixes are archived under checkpoints/recovery-history, and canonical reward/rollout/group logs are restored to the selected checkpoint prefix before resume"
    - "the attempt-local Piston circuit breaker and fail-closed reward callback remain unchanged: the first infrastructure failure stops repeated remote calls and the failed reward batch is logged then raises before optimizer update"
    - "real pinned TRL regressions remain present: timing/checkpoint hooks compose on real GRPOTrainer; reward exception leaves global_step=0, no checkpoint, and all model parameters unchanged"
    - "current result-code verification PASS: focused GRPO/WP7a/WP7b 91/91; make lint/ruff/mypy PASS; full make test 941 passed / 3 expected real-Piston opt-in skips / 0 failed; make test-gpu 3/3; real make test-piston 9/9"
    - "C11 changes no training execution logic relative to C10 after result-code preflight: from resolve_run_action through train-grpo and postcheck, the scripts are byte-identical after checkpoint-id normalization"
    - "C11 resume still selects only the highest complete 10-step checkpoint with a valid canonical-log sidecar; postcheck requires sidecars on checkpoint-10 through checkpoint-100 for both Public and Hidden"
    - "C11 target preflight requires both C10 and C9 operator roots to be absent, matching the operator statement that neither was executed; preserved C8 infrastructure-invalid evidence remains independently authenticated"
    - "C11 bash syntax PASS; all 15 Python heredocs compile; actual train-grpo command site count=1"
  remaining_scope:
    - "push only the exact C11 checkpoint through ordinary Git, checkout/detach it on the RTX 4090, verify clean checkout and C11 script SHA, then run only C11; do not run C9/C10 or rerun C8"
    - "C11 must authenticate C10 and C9 as unexecuted, authenticate preserved C8 infrastructure-invalid evidence, recompute the unchanged retry pair v2, ensure the Piston tunnel before each branch and start/continue only the retry1 runs"
    - "for intentional pauses use Ctrl-C/TERM and wait for the process to finish writing status=failed before powering off; a stale status=running is intentionally not auto-resumable"
    - "after C11 exits successfully, sync C11 operator evidence/status/log/postcheck and required small retry pilot artifacts/final adapters back to the C11 control-plane receive directory, then invoke execution-router resume backend=web stage_id=WP7-c"
  status: awaiting_operator
```

### C11 audit notes

- C10 and C9 remain immutable and unexecuted; C11 supersedes them before target execution.
- C8 remains immutable infrastructure-invalid history and is never a parent or resume source for retry1.
- C11 preserves batch size, gradient accumulation, learning rate, reward formula/source, LoRA, seed, max steps, data bytes, formal B, pair identity and save_steps=10.
- No C11 target command was started while preparing this checkpoint.


## C12 — hard-interruption recoverable GRPO pilot handoff

C10 was executed once on the RTX 4090, but it failed during preflight before either retry1 training run was created. The failure was caused by an operator provenance assertion that conflated two distinct C8 statistics: 498 reward rows are infrastructure-affected, while 495 rows have aggregate `status=sandbox_error`. C11 was generated locally afterward but was never pushed or executed; its conservative stale-`running` guard would also have blocked recovery after a real hard power/process interruption. C12 supersedes C11, preserves the executed-preflight C10 evidence, corrects the C8 historical signature, and restores fail-closed trainer-checkpoint recovery for coherent hard interruptions.

```yaml
execution_checkpoint:
  checkpoint_id: C12
  source_plan_commit: 8464e69691c527c726a2e28e5a7ca81fa2001bbf
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: dfbeafaf5b449b0884c065495db8059815cfd80f
  recovery_hardening_commit: 24685d7e9587fdd9e072fa871d0a66f22bff9caf
  superseded_stale_running_guard_commit: e6622a40c0449477079710e0fe875e216278e13c
  interruption_class: operator
  resume_allowed: true
  operator_gate_id: grpo-cd-pilot
  operator_handoff_mode: portable_target
  operator_restart_policy: trainer_checkpoint
  operator_script: ai-work/executor/operator/WP7-c/grpo-cd-pilot/C12/run.sh
  operator_script_sha256: ba838037596a3e0ba9a0d1102075174de36998156d0b3766df62c3b7550afd44
  target_machine_pointer_template: .ai-bridge/validation-machine.json
  target_status_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-pilot/C12/status"
  target_log_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-pilot/C12/terminal.log"
  target_evidence_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-pilot/C12/operator-evidence.json"
  target_postcheck_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-pilot/C12/postcheck-summary.json"
  control_plane_evidence_receive_dir: /home/dzy/wp7c-operator-evidence/WP7-c/grpo-cd-pilot/C12
  prior_operator_checkpoint_commit: ae429f2dc0ed7353d5a3de0adb0d71b58a879a3d
  accepted_prior_operator_evidence_sha256: f1e3b350d11a4af13118a2517bbbbfb95df752b6cded126c80492ba40b163a5e
  accepted_prior_postcheck_sha256: 94b052e9c14f4842b45c35c2ce0d9f108cd6e382ff99e50293544b83039c2b8a
  pilot_pair_schema_version: 2
  pilot_pair_sha256: bb8a733b2f6b9519d6e9c9de087461a975ba830f6c132a8f06120881576b512f
  pilot_public_config_hash: da543a9ac2719076fd81696dbcb98f1df9c9254adc9e9f519569b3b0d2e09dac
  pilot_hidden_config_hash: 5036e0aa8be941f145f52e08269e808948f091c80d5d0972ef50326417934658
  pilot_public_run_name: C-public-grpo-pilot100-retry1-seed42
  pilot_hidden_run_name: D-hidden-grpo-pilot100-retry1-seed42
  pilot_max_steps: 100
  pilot_save_steps: 10
  expected_trainer_checkpoints: [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
  checkpoint_log_state_file: code_verifier_log_state.json
  recovery_history_dir: checkpoints/recovery-history
  supersedes_checkpoint_id: C11
  supersedes_checkpoint_commit: 418cc1138b9c748726876ae6c53822773578151b
  superseded_result_code_commit: e6622a40c0449477079710e0fe875e216278e13c
  superseded_operator_script_sha256: d390dcd95c0f48702dbb14014b4efb6c3d848634d2c258fa74d30c1a6503af84
  superseded_execution_state: unexecuted_by_operator
  failed_c10_checkpoint_commit: d9af548d49cc8f781984f31ea70817e4afa9f1b1
  failed_c10_result_code_commit: 24685d7e9587fdd9e072fa871d0a66f22bff9caf
  failed_c10_operator_script_sha256: 06499d2b00b0799f4b277b130d095e498ec1fafe5753eb862c33824735739b49
  failed_c10_operator_evidence_sha256: 13a612f0d7fa6c8d471065dd7fe890570acc08483708e7933d5cb30875086396
  failed_c10_status_sha256: a5e45837a2959db847f7e67a915d0ecaddd47f943af2af5fa6453be497faabca
  failed_c10_terminal_log_sha256: 4e2e12af753f1da6f220a145df7c43d8464b8295123ede2ff837d3d97abf9c33
  failed_c10_command_rc: 125
  failed_c10_postcheck_rc: 125
  failed_c10_gate_status: preflight_failed
  failed_c10_retry1_runs_created: false
  unexecuted_c9_checkpoint_commit: 792f637f34ccabebbc61fde61bd861f20887f217
  unexecuted_c9_operator_script_sha256: bae1e5ec8f0b4c29b86401e547ced8fc818b1b90af6c7d0d6b4bde708d15dcfa
  preserved_invalid_c8_checkpoint_commit: 32ab2697b33c9a211c37c78f0871808de069b658
  preserved_invalid_c8_operator_evidence_sha256: def49dcb2d838e8ff8a740250ad392a3dee34c54774d808c3c4b82630451b594
  preserved_invalid_c8_reward_rows: 800
  preserved_invalid_c8_infrastructure_failure_rows: 498
  preserved_invalid_c8_sandbox_error_status_rows: 495
  preserved_invalid_c8_first_infrastructure_failure_step: 36
  preserved_invalid_c8_healthy_prefix_steps: 35
  preserved_invalid_c8_hidden_run_absent: true
  smoke_max_complete_trainer_checkpoint_bytes: 42184437
  smoke_max_complete_trainer_checkpoint_inodes: 15
  target_required_free_bytes: 32212254720
  target_required_free_inodes: 100000
  completed_scope:
    - "C10 target execution is preserved as a preflight-only failure, not mislabeled as unexecuted: its exact evidence/status/terminal-log hashes are authenticated and neither retry1 run existed after the failure"
    - "C8 historical validation now distinguishes the actual immutable statistics: 498/800 reward rows are infrastructure_failure=true, 495 have aggregate status=sandbox_error, the first infrastructure-affected row is in optimizer step 36, and steps 1..35 are healthy"
    - "the three C8 rows that are infrastructure-affected without aggregate sandbox_error retain sandbox_error in failure_counts; C12 validates that semantic evidence instead of equating infrastructure_failure with the aggregate status field"
    - "C11 remains immutable and unexecuted; C12 supersedes its stale-running guard because refusing status=running would make a complete Trainer+sidecar checkpoint unusable after hard power/process loss"
    - "result-code dfbeafaf5b449b0884c065495db8059815cfd80f accepts only coherent interrupted status=running state: the latest attempt must also be running, interrupted attempt gpu_hours remains 0 because exact elapsed time was not durably finalized, and interrupted attempt/run end_time remains null"
    - "resume checkpoint selection is centralized in production _latest_valid_resume_checkpoint: only cadence checkpoints with every required Trainer file, exact trainer_state global_step, and a valid code_verifier_log_state.json prefix boundary are eligible; a newer Trainer-complete checkpoint without its sidecar is skipped in favor of the highest lower valid checkpoint"
    - "repeated hard-interruption recovery is covered end-to-end: two separate resumes from the same checkpoint preserve distinct recovery-history archives and remove each failed suffix from canonical rollouts/rewards/group_metrics before replay"
    - "recovery remains viable if a previous recovery itself was hard-interrupted: recognized .incomplete-* archive staging and .resume-*.tmp rollback staging are preserved as bounded production recovery evidence rather than making the next valid resume impossible"
    - "checkpoint and recovery-history symlink boundaries fail closed; recovery-history stays under checkpoints and canonical analysis continues to read only the run-root streaming JSONL files"
    - "C12 postcheck validates checkpoint-10 through checkpoint-100 with the production sidecar validator and additionally requires checkpoint-100 sidecar state to equal each complete final canonical streaming-log state"
    - "C12 postcheck accepts and audits recognized hard-interruption recovery staging while rejecting symlinks, unknown recovery-history entries, malformed manifests, unsafe future-checkpoint entries, and unexpected archive files"
    - "Public and Hidden remain independently restartable under the same C12 script: an already completed Public run is skipped on a later invocation while Hidden can continue from its own highest valid 10-step Trainer+sidecar checkpoint"
    - "training definitions are unchanged: max_steps=100 and save_steps=10 for each of Public and Hidden; batch size, gradient accumulation, num_generations, beta, learning rate, temperature, max_completion_length, LoRA, seed, gradient checkpointing, vLLM setting, formal data and formal B are unchanged"
    - "portable pair v2 identity remains bb8a733b2f6b9519d6e9c9de087461a975ba830f6c132a8f06120881576b512f with unchanged Public/Hidden portable config hashes"
    - "fail-closed reward semantics, same-batch Piston circuit breaker, per-checkpoint canonical log sidecars, failed-attempt archive/rollback, and the real pinned TRL save-hook/fail-before-optimizer regressions remain in place"
    - "verification PASS: focused GRPO/WP7a/WP7b 95/95; make lint PASS; full make test 945 passed / 3 expected real-Piston opt-in skips / 0 failed; make test-gpu 3/3; real make test-piston 9/9 with 2 deselected"
    - "C12 bash syntax PASS; all 16 embedded Python heredocs compile; exactly one real train-grpo command site; no numerical stopping threshold is introduced"
  remaining_scope:
    - "push only the exact C12 checkpoint through ordinary Git, checkout/detach that exact commit on the RTX 4090, verify clean checkout and C12 script SHA, then run only C12; do not rerun C8, C9, C10 or C11"
    - "C12 must authenticate C11/C9 as unexecuted, authenticate the exact C10 preflight-only failure, authenticate preserved C8 infrastructure-invalid history, recompute the unchanged pair v2, and ensure the Piston tunnel immediately before each Public/Hidden train-grpo invocation"
    - "C12 may be rerun after intentional or hard interruption; it selects only the highest complete valid 10-step Trainer+sidecar checkpoint, preserves failed/recovery-interrupted evidence under recovery-history, rolls canonical streams back to the selected boundary, and continues from there"
    - "after C12 exits successfully, sync C12 operator evidence/status/log/postcheck and required small retry pilot artifacts/final adapters back to the C12 control-plane receive directory, then resume the WP7-c lifecycle on the control plane"
  status: awaiting_operator
```

### C12 recovery notes

- The two 100-step runs do not need to finish in one machine session. Public and Hidden have independent run directories and independent 10-step Trainer checkpoints; rerunning the exact C12 checkpoint can skip an already completed branch and resume the unfinished branch from its highest valid Trainer+sidecar checkpoint.
- A hard interruption may leave the latest attempt recorded as `running`. C12 treats that as recoverable only when the persisted metadata is internally coherent and relies on checkpoint/sidecar/log-prefix evidence rather than pretending the interrupted attempt duration was durably known.
- C8 remains immutable infrastructure-invalid history. C10 remains immutable preflight-failure history. C11 remains immutable unexecuted history. No target training command was started while preparing C12 on the GTX 1660 Ti control plane.

## C13 — C12 Hidden checkpoint-90 cross-commit recovery handoff

C12 was executed on the RTX 4090. Public completed all 100 optimizer steps, while Hidden failed closed after checkpoint-90 when the Piston-backed reward path reported infrastructure failure near the end of the run. The failed reward batch was aborted before its optimizer update. C12 cannot be safely rerun verbatim because its historical C10 preflight check incorrectly requires the retry1 namespace to remain absent even after C12 itself created it. C13 therefore preserves C12 and its artifacts immutably, adds an explicit cross-commit resume lineage contract, and permits only the unfinished Hidden branch to recover from checkpoint-90 or a later valid C13-created checkpoint.

```yaml
execution_checkpoint:
  checkpoint_id: C13
  source_plan_commit: 8464e69691c527c726a2e28e5a7ca81fa2001bbf
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: 7342b323fb550fd5ebae2ddcd614c2c63c054cbc
  interruption_class: operator
  resume_allowed: true
  operator_gate_id: grpo-cd-pilot
  operator_handoff_mode: portable_target
  operator_restart_policy: trainer_checkpoint
  operator_script: ai-work/executor/operator/WP7-c/grpo-cd-pilot/C13/run.sh
  operator_script_sha256: dd49ee0b21af0e309803bd3b3d2e0ebfc0b419bcdb01da56ebcab24cd3adfe58
  target_machine_pointer_template: .ai-bridge/validation-machine.json
  target_status_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-pilot/C13/status"
  target_log_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-pilot/C13/terminal.log"
  target_evidence_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-pilot/C13/operator-evidence.json"
  target_postcheck_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-pilot/C13/postcheck-summary.json"
  control_plane_evidence_receive_dir: /home/dzy/wp7c-operator-evidence/WP7-c/grpo-cd-pilot/C13
  recovery_origin_checkpoint_id: C12
  recovery_origin_checkpoint_commit: 355486ccccff3a1325614e18e8f8d4a85b8789ba
  recovery_origin_operator_script_sha256: ba838037596a3e0ba9a0d1102075174de36998156d0b3766df62c3b7550afd44
  recovery_origin_public_state: completed_100
  recovery_origin_hidden_state: failed_after_checkpoint_90
  recovery_origin_hidden_first_resume_checkpoint: 90
  pilot_pair_schema_version: 2
  pilot_pair_sha256: bb8a733b2f6b9519d6e9c9de087461a975ba830f6c132a8f06120881576b512f
  pilot_public_config_hash: da543a9ac2719076fd81696dbcb98f1df9c9254adc9e9f519569b3b0d2e09dac
  pilot_hidden_config_hash: 5036e0aa8be941f145f52e08269e808948f091c80d5d0972ef50326417934658
  pilot_public_run_name: C-public-grpo-pilot100-retry1-seed42
  pilot_hidden_run_name: D-hidden-grpo-pilot100-retry1-seed42
  pilot_max_steps: 100
  pilot_save_steps: 10
  checkpoint_log_state_file: code_verifier_log_state.json
  recovery_history_dir: checkpoints/recovery-history
  completed_scope:
    - "production train-grpo now accepts cross-commit recovery only when --resume-run-git-commit explicitly matches the preserved run.json git_commit; omission, mismatch, malformed commit, or use without --resume-from-checkpoint fails closed"
    - "run.json.git_commit remains the immutable origin commit C12; every new attempt records code_commit so the recovery execution commit is separately auditable without rewriting the historical run origin"
    - "legacy C12 attempt records without code_commit remain valid; new attempt code_commit values are strict lowercase 40-character Git commit identities"
    - "C13 preflight requires its result-code commit to be directly parented by C12 and requires the C12-to-result diff to be exactly src/code_verifier/cli.py, src/code_verifier/training/grpo.py, tests/unit/test_cli.py, and tests/unit/training/test_grpo_resume_lineage.py"
    - "C13 authenticates the executed C12 terminal state as status=2, command_rc=2, postcheck_rc=125, gate_status=command_failed, note=hidden pilot train-grpo exited nonzero, with exact C12 checkpoint/script provenance; the exact C12 evidence SHA is recomputed on target and recorded in C13 operator evidence"
    - "Public is strict-loader validated as the untouched C12 100-step completed run and C13 has no Public train-grpo command"
    - "on the first C13 invocation Hidden must be owned by C12, attempt-1 must be the C12 failed attempt, and production _latest_valid_resume_checkpoint must select exactly checkpoint-90; no fresh fallback is present"
    - "C13 invokes exactly one real train-grpo site with reward-mode hidden, explicit --resume-from-checkpoint, and --resume-run-git-commit bound to C12; production recovery archives the failed suffix and restores canonical rollouts/rewards/group_metrics to the checkpoint sidecar boundary before Trainer resumes"
    - "if C13 itself is interrupted, the same exact C13 script may select only a highest complete valid cadence checkpoint at step >=90; it never falls back below checkpoint-90 or to fresh training"
    - "postcheck strict-loads both completed C/D adapters, requires Public attempt_count=1, requires Hidden to have a C13 attempt lineage, validates checkpoint-10..100 sidecars and final checkpoint-100 canonical stream equality, and requires at least one completed C13 checkpoint-90 recovery archive so a prior C13 hard interruption before archive finalization remains recoverable"
    - "scientific definitions remain unchanged: pair SHA, Public/Hidden portable config hashes, formal datasets, formal B, Piston definition/runtime/topology, batch size, gradient accumulation, num_generations, reward formula/source, LoRA, seed, max_steps and save_steps are unchanged"
    - "business verification PASS before handoff: focused GRPO/CLI 149/149; make lint PASS; full make test 948 passed / 3 expected real-Piston opt-in skips / 0 failed; make test-gpu 3/3; real make test-piston 9/9 with 2 deselected"
    - "C13 bash syntax PASS and all 12 embedded Python heredocs compile; C13 parses its own report block and fail-closes if result_code_commit/script SHA/handoff/restart/status metadata differ from the tracked checkpoint; C13 contains no --reward-mode public command and exactly one Hidden recovery train-grpo command site"
  remaining_scope:
    - "commit the four-file cross-commit resume repair as the direct child of C12, substitute that exact result-code SHA into this C13 report block, mark C13/run.sh executable, then commit only this append-only report plus the new C13 script as the operator checkpoint"
    - "make the exact C13 checkpoint reachable on the RTX 4090, checkout/detach it, verify a clean checkout and the exact C13 script SHA, then manually run only C13; do not rerun C12 or invoke train-grpo directly"
    - "C13 must preflight the existing C12 Public/Hidden artifacts and will start only Hidden from checkpoint-90 on its first invocation"
    - "after C13 exits, preserve/sync C13 evidence/status/log/postcheck and required small pilot artifacts for review; do not proceed to formal GRPO before the C12/C13 pilot review is complete"
  status: awaiting_operator
```

### C13 recovery notes

- C13 is a recovery-only handoff. It has no fresh training path and no Public training path.
- The cross-commit permission is intentionally narrow: the preserved run origin commit must be exactly C12, all scientific/run identities must still match, and the current recovery execution is recorded per attempt as `code_commit`.
- The current Piston topology remains the sealed 4090 loopback SSH-forward to `1660ti-wsl`; the planned transport-reliability hardening remains deferred until this pilot and its review are complete.

## C14 — C13 pilot evidence review (control plane)

Review performed read-only from the 1660 Ti synchronized evidence root `/home/dzy/wp7c-operator-evidence/WP7-c/grpo-cd-pilot`; synchronized evidence remains outside Git. No C12/C13 target artifact or checkpoint was modified.

### Authenticity, provenance, and synchronized inventory

- Git lineage independently revalidated as `355486ccccff3a1325614e18e8f8d4a85b8789ba` (C12) -> `7342b323fb550fd5ebae2ddcd614c2c63c054cbc` (C13 business repair result-code commit) -> `945764a99e3a1bed53afbff830fddc84181e215f` (C13 operator checkpoint).
- C12 synchronized operator bytes: `status` SHA256 `53c234e5e8472b6ac51c1ae1cab3fe06fad053beb8ebfd8977b010655bfdd3c3`, `terminal.log` `541e5e0312027b50c2753ffc7943f7a7080f35b3544caf0adaaafded742185e5`, `operator-evidence.json` `9426f68b5ccd755f31fccc419b7f779227609009a8e5c5a0e9b76ffc65d44418`; status is `2`, command failed closed while Hidden was at 97 completed optimizer steps and the failed 8/8 infrastructure batch aborted before its optimizer update.
- C13 synchronized operator bytes: `status` SHA256 `9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa`, `terminal.log` `98e5f0740b80d55bed544ae050394d1bbe23ef6154944c2169224742d14359f8`, `operator-evidence.json` `91647fa09354f1dbaf486b7d94960934391467470665401022493ad5fb87d50b`, `postcheck-summary.json` `91d4825b86a325a8f9765bfb9d99ab51345051c046c9847cfe335aadad487b2f`; status/command/postcheck are all `0` and gate status is `passed`.
- C13 operator inventory was remapped to the synchronized pilot/operator tree and independently hash/size checked: 23/23 expected files are present with no mismatch.
- Final Public adapter SHA256 is `55e1860b2cdd5a3e6b497724f2519b5cf0ee5825273545f8042f039d916c19e9`; final Hidden adapter SHA256 is `29afca9c80537d712c2c388dfdcd8eef822a91d772381367389c5d18d57805d3`.
- Hidden recovery manifest SHA256 is `efc8c4d570550376e294f20f388ae1e354ba9a01ff88f37faae333391c92ecd8`. The archived failed streams independently match the manifest/C12 terminal bytes: rewards `dc1b3c6509bacc68d5afee212f5e6d6cd2156142d9b0cf44bf946796471b9698`, rollouts `8dfb8b865c18ef26a741f74c4ee5e603bd35298b98cb0d60f85707aec388f0bb`, groups `7ecf47d9d251561632235c664f5d6a9ec474f1f19bcd9cbc6ada70bf62039924`.

### Strict pilot identity and recovery correctness

- Public is `C-public-grpo-pilot100-retry1-seed42`, completed at global step 100 in exactly one attempt, fresh from B with `resume_from_checkpoint=null`; C13 did not retrain Public.
- Hidden is `D-hidden-grpo-pilot100-retry1-seed42`, completed at global step 100 with two attempts: C12 attempt 1 failed; C13 attempt 2 records code commit `945764a99e3a1bed53afbff830fddc84181e215f`, resumed only `checkpoints/checkpoint-90`, and completed.
- Both runs bind the same parent `B-sft-formal-seed42`, seed 42, paired-definition SHA256 `bb8a733b2f6b9519d6e9c9de087461a975ba830f6c132a8f06120881576b512f`, Public portable config SHA256 `da543a9ac2719076fd81696dbcb98f1df9c9254adc9e9f519569b3b0d2e09dac`, Hidden portable config SHA256 `5036e0aa8be941f145f52e08269e808948f091c80d5d0972ef50326417934658`, Public dataset SHA256 `94ef48888d2b2edaa0080b9b412c274ada692c9546fe135572d48ab20fd49223`, Hidden dataset SHA256 `79af3c2a3742e0cda8d02901a07241afce12a54c0b6d334e3012bcd0b69f77f7`, exact formal B/data/config/dependency/Open-R1/Qwen identities, and differ scientifically only in the paired dataset/reward source plus run name: Public `visible_tests`, Hidden `train_hidden_tests`.
- Hidden checkpoint-90 sidecar records 720 rewards, 720 rollouts, 180 groups. The C12 failed state archived before recovery records 784/784/196. Every archived stream begins with the exact checkpoint-90 byte prefix, and every restored canonical stream also begins with that exact checkpoint-90 prefix.
- Hidden checkpoint-100 sidecar records 800 rewards, 800 rollouts, 200 groups and its size/SHA/line-count state exactly equals each final canonical stream. Final Public and Hidden canonical rewards/rollouts/groups contain zero exact duplicate rows. Trainer telemetry covers steps 1..100 exactly once for each run, with no missing or duplicate step.
- Canonical reward rows contain zero `infrastructure_failure=true` and zero `status=sandbox_error`. The failed suffix remains only under `checkpoints/recovery-history/before-attempt-2-resume-checkpoint-90/` and is not part of final canonical reward/rollout/group streams.

### §12.4 raw pilot telemetry review

No numerical stop threshold is invented; the following are raw evidence statistics used only for the spec-defined qualitative review.

| Metric | Public | Hidden |
| --- | ---: | ---: |
| trainer reward mean | 0.4537500189 | 0.4501250179 |
| trainer reward-std mean | 0.2260171307 | 0.2179937651 |
| group std mean | 0.1957365761 | 0.1887881369 |
| group all-equal rate | 0.415 | 0.415 |
| KL mean / max | 0.0001310794 / 0.0002448273 | 0.0001256360 / 0.0002903884 |
| loss mean | 0.0 | 0.0 |
| completion mean tokens | 216.2975 | 214.3775 |
| truncation rate | 0.0125 | 0.00875 |
| parse rate | 0.97125 | 0.9825 |
| executed rate | 0.97125 | 0.9825 |
| timeout rate | 0.015 | 0.01125 |
| pass rate | 0.3075 | 0.30125 |
| generation sec mean / p95 / max | 36.6508 / 62.8305 / 63.5203 | 35.9684 / 63.4112 / 64.5314 |
| rollout sec mean / p95 / max | 74.0522 / 97.7825 / 106.5992 | 86.0732 / 115.5506 / 157.6113 |
| no-grad sec mean / p95 / max | 0.77149 / 0.81213 / 0.84066 | 0.76593 / 0.80407 / 0.80928 |
| total step sec mean / p95 / max | 78.3432 / 102.0233 / 110.9500 | 90.3358 / 119.8840 / 161.9703 |
| executor runtime mean / total ms | 90.0992 / 72079.38 | 97.4686 / 77974.86 |
| GPU hours | 2.1831925225 | 2.8170487867 cumulative (2.6525675642 failed attempt + 0.1644812225 recovery) |
| peak CUDA allocated bytes | 4521147392 | 4154825728 |
| peak CUDA reserved bytes | 10114564096 | 5932843008 |

Public status counts: `passed=246`, `wrong_answer=384`, `runtime_error=134`, `parse_error=23`, `timeout=12`, `memory_limit=1`. Public failure counts: `wrong_answer=690`, `runtime_error=258`, `parse_error=46`, `timeout=24`, `memory_limit=2`.

Hidden status counts: `passed=241`, `wrong_answer=381`, `runtime_error=152`, `parse_error=14`, `timeout=9`, `memory_limit=3`. Hidden failure counts: `wrong_answer=677`, `runtime_error=296`, `parse_error=28`, `timeout=22`, `memory_limit=6`.

All parsed numerical values in final metrics/rewards/rollouts/group telemetry are finite. Both runs have no missing/duplicate trainer step, no canonical infrastructure failure, no canonical sandbox error, and the expected eight no-grad reference-logprob calls at every optimizer step. Hidden canonical per-step timing intentionally combines the preserved checkpoint-90 lineage with replayed steps 91..100; the final metrics summary `train_runtime` is recovery-attempt runtime and therefore is not used as a cumulative two-attempt wall-clock substitute. Cumulative Hidden GPU hours remain the authoritative full-attempt cost record.

### Pilot review conclusion

**B. no spec-defined hard stop signal.** The pilot has authenticated complete C/D 100-step canonical trajectories, valid checkpoint-90 recovery, finite telemetry, exact step coverage, distinct sealed reward sources, and no canonical infrastructure/sandbox failure. §12.4 does not seal numerical thresholds for qualitative terms such as “obvious decline”, “too high”, or “abnormal growth”, so this review does not manufacture one. The lifecycle may proceed to the formal-precondition Piston transport-reliability hardening gate; formal 300-step C/D remains blocked until that engineering gate and the subsequent formal-readiness review pass.

## C15 — formal readiness review and 300-step C/D operator handoff

Phase-2 transport reliability is accepted as a completed predecessor gate per the user-provided cross-conversation handoff. This review does not invent missing soak counters: destructive restart/long-soak raw numbers are not restated from the synchronized C13 evidence tree. The current tracked Phase-2 transport documentation explicitly amends the deployed topology to the 1660 Ti initiated reverse-SSH loopback forward and defers destructive tunnel restart experiments unless an operator explicitly chooses them while no formal target-GPU run is active. The formal operator therefore validates the existing reverse-forward live but never starts, kills, or rewrites tunnel state.

### Formal-readiness revalidation on the 1660 Ti control plane

- Current accepted result-code commit: `ed3eaea93ba897c38e3b3ff7b95903d31f7e76d2`; C13 checkpoint `945764a99e3a1bed53afbff830fddc84181e215f` remains an immutable ancestor. Reverse-SSH workflow transport commit `b4ac6acb95530f5359566e6f140f77ad6a4da78f` is also in the accepted result-code lineage.
- Git blob comparison from C13 to the accepted result-code commit is identical for `configs/execution/piston-local.yaml`, `configs/grpo/public.yaml`, `configs/grpo/hidden.yaml`, and the entire `src/code_verifier/rewards` tree. Therefore scientific Piston semantics, formal hyperparameters, and reward math are unchanged by Phase 2.
- `.ai-bridge/**` tracked-path check: zero tracked paths. No synchronized C12/C13 evidence is added to Git. The only intended handoff change set is this append-only executor report plus the new C15 operator script; the eventual target checkout must be clean and C15 preflight enforces that condition.
- Formal pair was independently recomputed with production `_paired_definition()` against exact formal B and exact formal data: pair SHA256 `7924be4e115b20bc3e40207256d67d2e8591c973dbd9de7bfcb0b4bf39b08df3`; Public portable config component `1ec25400fd1f6d6ec46d636ac84db9098de6559fa327fd63d3e8f7364f650271`; Hidden `330ce6ce4a8ba3743927bd3f38bd4692a3616483bd8cd2fe1727c455c55a9f71`; Public/Hidden data remain `94ef48888d2b2edaa0080b9b412c274ada692c9546fe135572d48ab20fd49223` / `79af3c2a3742e0cda8d02901a07241afce12a54c0b6d334e3012bcd0b69f77f7`.
- Scientific Piston definition remains SHA256 `f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e`. Transport resilience is separate: normalized policy identity SHA256 `d7e7b3a3a2f6492cf6040c08a64086fba3aa7a9c4f5209752a0ba2917ef81c85`; implementation identities are `piston-transport-retry-v2`, `httpclient-loopback-classifier-v3`, `httpclient-single-keepalive-v1`, and legacy-supervisor implementation identity `piston-tunnel-supervisor-v3` (the legacy local-forward supervisor is not deployed by C15).
- Phase-2 real reverse-forward acceptance recorded on 2026-08-27: 4090 runtime probe exact Python `3.10.0`; fresh `/api/v2/runtimes` 30-call mean `97.56 ms`, p50 `98.759 ms`, p95 `104.156 ms`; trusted `print(1)` fresh 10-call mean `134.31 ms`; real reverse-tunnel `make test-piston` `9 passed, 0 skipped, 0 failed`.
- Current focused transport/recovery fault suite re-run: `95 passed`. Coverage includes safe pre-connect retry/recovery and exhaustion, no retry for read timeout/reset/HTTP/invalid JSON/oversized response/application verdicts, exact request reuse, bounded attempts/backoff, ownership/locking, durable sidecar telemetry, same-run GRPO recovery, and unrecovered infrastructure abort before optimizer update.
- Current full regression re-run: `make lint` PASS; `make test` `997 passed, 3 skipped`; `make test-gpu` `3 passed`; real `make test-piston PISTON_CONFIG=configs/execution/piston-local.yaml` `9 passed, 2 deselected`, with zero skipped/failed Piston tests.
- Current real-Piston semantic-equivalence probe compared the baseline scientific executor against the resilience-policy executor on fixed `passed`, `wrong_answer`, `runtime_error`, and `parse_error` cases. Both resolved runtime `3.10.0`; `status`, `passed_tests`, `total_tests`, `pass_rate`, and `failure_counts` had `0` mismatches.
- Destructive tunnel-fault/long-soak acceptance is inherited from the user-confirmed completed Phase-2 gate rather than re-executed here. No new 4090 destructive fault, generation, SFT, GRPO, or operator command was launched by this formal-readiness review.

### C15 operator contract

- Gate is `grpo-cd-formal`: Public C and Hidden D are each exactly 300 steps with save cadence 50, seed 42, and the formal pair identity above.
- Each member independently initializes fresh from the same completed `B-sft-formal-seed42` on its first attempt. Pilot adapters are authenticated only as prior-gate evidence and are never accepted as formal parents. C cannot initialize D and D cannot initialize C.
- Rerun action is resolved separately for each member: absent -> fresh; completed exact identity -> skip; incomplete exact same-operator run -> only the highest production-validated same-run 50-step Trainer checkpoint plus canonical log sidecar; no valid checkpoint -> fail closed. Cross-member and cross-operator resume are rejected.
- C15 authenticates immutable C13 status/log/evidence/postcheck bytes and final pilot adapters, verifies the accepted checkpoint-90 recovery lineage, but never modifies or deletes C12/C13 artifacts/checkpoints.
- Target preflight requires the exact model/B/data/dependencies, RTX 4090 + native BF16, offline model availability, exact scientific Piston SHA, exact transport-policy SHA/implementation identity, and a live loopback runtime probe equal to Python 3.10.0. It never invokes the retired target-side tunnel helper.
- Storage is recomputed on target from the actual complete pilot Trainer checkpoints using the sealed formula `max(40 GiB, 14*P + 10 GiB)` and `max(100000, 14*Fp + 20000)` before either formal member starts.
- The production transport sidecar is required for every existing formal run and is bound to both scientific Piston SHA and transport-policy SHA. Historical safe retries, retry exhaustion, or ambiguous failures remain visible rather than erased; ambiguous/current-request failures are never transparently replayed.
- Final postcheck requires both exact completed 300-step identities, attempts rooted fresh from B, same-operator same-run recovery only, checkpoints 50..300 with canonical log sidecars, trainer steps 1..300 exactly once, canonical 2400 rewards / 2400 rollouts / 600 groups, finite telemetry, zero canonical `infrastructure_failure` / `sandbox_error`, correct reward-source isolation, safe payload schema, cost/curve availability, transport telemetry consistency, and complete recovery-history validation.
- C15 stops after formal C/D postcheck. It does not start generation or formal evaluation.

```yaml
execution_checkpoint:
  checkpoint_id: C15
  source_plan_commit: 8464e69691c527c726a2e28e5a7ca81fa2001bbf
  result_code_commit: ed3eaea93ba897c38e3b3ff7b95903d31f7e76d2
  workflow_transport_commit: b4ac6acb95530f5359566e6f140f77ad6a4da78f
  operator_gate_id: grpo-cd-formal
  operator_handoff_mode: portable_target
  operator_restart_policy: trainer_checkpoint
  operator_script: ai-work/executor/operator/WP7-c/grpo-cd-formal/C15/run.sh
  operator_script_sha256: f53972ff6bed4f59ef0e925ffc96c18c063bfe195bdac0be99f9692f41266375
  formal_pair_sha256: 7924be4e115b20bc3e40207256d67d2e8591c973dbd9de7bfcb0b4bf39b08df3
  transport_policy_sha256: d7e7b3a3a2f6492cf6040c08a64086fba3aa7a9c4f5209752a0ba2917ef81c85
  piston_definition_sha256: f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e
  accepted_c13_operator_evidence_sha256: 91647fa09354f1dbaf486b7d94960934391467470665401022493ad5fb87d50b
  accepted_c13_postcheck_sha256: 91d4825b86a325a8f9765bfb9d99ab51345051c046c9847cfe335aadad487b2f
  target_status_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C15/status"
  target_log_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C15/terminal.log"
  target_evidence_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C15/operator-evidence.json"
  target_postcheck_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C15/postcheck-summary.json"
  target_gpu: NVIDIA GeForce RTX 4090
  target_precision: bf16
  formal_public_run: C-public-grpo-formal-seed42
  formal_hidden_run: D-hidden-grpo-formal-seed42
  status: awaiting_operator
```

C15 is the lifecycle stop point for this control-plane task. The formal target operator has not been executed. Do not push automatically and do not start 4090 formal GRPO from the control plane.

## C16 — C15 initialization repair and superseding formal operator handoff

The user manually invoked the exact C15 checkpoint on the RTX 4090 and the shell terminated immediately with `line 99: STAGE_ID: unbound variable`. Independent control-plane inspection confirms that immutable C15 omitted the three shell constants `STAGE_ID`, `GATE_ID`, and `CHECKPOINT_ID` before their first use in the `OP_ROOT` assignment. With `set -u`, this is a tracked operator-wrapper bug rather than a target environment or scientific failure.

By C15 control flow, the reported failure occurs before `OP_ROOT` is assigned, before `mkdir -p "$OP_ROOT"`, before the operator lock/attempt log is created, before GPU/Piston/formal-pair/storage preflight, and hundreds of lines before either `train-grpo` call. Therefore that invocation cannot have started Public or Hidden formal training and cannot have created a formal GRPO run or transport sidecar through C15. Because the failure precedes the evidence root itself, no valid C15 `operator-evidence.json` is expected from this attempt; the terminal shell error is the applicable failure observation.

C15 checkpoint commit `178f77b406b90bebb2eb6b5b572b79ebd849f935` and C15 script SHA256 `f53972ff6bed4f59ef0e925ffc96c18c063bfe195bdac0be99f9692f41266375` remain immutable. C16 is copied from C15 and changes only operator identity/provenance plus the missing shell constants; scientific configs, reward code, formal pair, Piston definition, transport policy, B/data/model identities, run names, 300-step/50-save cadence, checkpoint/recovery semantics, postcheck, and Public/Hidden isolation are unchanged.

C16 additionally verifies on target that its direct parent is the immutable C15 checkpoint, that the historical C15 script bytes still match the certified SHA, and that its own checkpoint diff is exactly append-only executor report plus the new executable C16 script. C16 supersedes C15; do not inject the missing variables into C15 through the environment and do not rerun C15.

C16 control-plane static validation before handoff:

- `bash -n ai-work/executor/operator/WP7-c/grpo-cd-formal/C16/run.sh`: PASS.
- All 14 embedded Python heredocs compile: PASS.
- `set -u` uppercase-variable source audit: PASS, with `CODE_VERIFIER_VALIDATION_MACHINE` the only intentionally optional external variable; `STAGE_ID`, `GATE_ID`, and `CHECKPOINT_ID` are now explicit immutable constants at the top of C16.
- Immutable C15 SHA recheck: PASS (`f53972ff6bed4f59ef0e925ffc96c18c063bfe195bdac0be99f9692f41266375`).
- Non-training `/tmp` dry preflight: C16 passed the former unbound-variable point, created atomic C16 status/evidence, then intentionally failed closed at the injected wrong machine-pointer SHA with `rc=125`, `status=125`, `checkpoint_id=C16`, `gate_status=preflight_failed`, and note `validation machine pointer SHA changed`. No GPU/Piston/GRPO path was reached.
- C16 script SHA256: `9e752f8b60204874dcce8c779acaca478a4749da3f94de36316406b964e4ac3e`.

```yaml
execution_checkpoint:
  checkpoint_id: C16
  source_plan_commit: 8464e69691c527c726a2e28e5a7ca81fa2001bbf
  result_code_commit: 178f77b406b90bebb2eb6b5b572b79ebd849f935
  workflow_transport_commit: b4ac6acb95530f5359566e6f140f77ad6a4da78f
  operator_gate_id: grpo-cd-formal
  operator_handoff_mode: portable_target
  operator_restart_policy: trainer_checkpoint
  operator_script: ai-work/executor/operator/WP7-c/grpo-cd-formal/C16/run.sh
  operator_script_sha256: 9e752f8b60204874dcce8c779acaca478a4749da3f94de36316406b964e4ac3e
  formal_pair_sha256: 7924be4e115b20bc3e40207256d67d2e8591c973dbd9de7bfcb0b4bf39b08df3
  transport_policy_sha256: d7e7b3a3a2f6492cf6040c08a64086fba3aa7a9c4f5209752a0ba2917ef81c85
  piston_definition_sha256: f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e
  accepted_c13_operator_evidence_sha256: 91647fa09354f1dbaf486b7d94960934391467470665401022493ad5fb87d50b
  accepted_c13_postcheck_sha256: 91d4825b86a325a8f9765bfb9d99ab51345051c046c9847cfe335aadad487b2f
  supersedes_checkpoint_id: C15
  supersedes_checkpoint_commit: 178f77b406b90bebb2eb6b5b572b79ebd849f935
  superseded_operator_script_sha256: f53972ff6bed4f59ef0e925ffc96c18c063bfe195bdac0be99f9692f41266375
  supersession_reason: C15 omitted STAGE_ID/GATE_ID/CHECKPOINT_ID and failed under set -u before operator-root creation
  target_status_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C16/status"
  target_log_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C16/terminal.log"
  target_evidence_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C16/operator-evidence.json"
  target_postcheck_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C16/postcheck-summary.json"
  target_gpu: NVIDIA GeForce RTX 4090
  target_precision: bf16
  formal_public_run: C-public-grpo-formal-seed42
  formal_hidden_run: D-hidden-grpo-formal-seed42
  status: awaiting_operator
```

C16 replaces C15 as the only formal operator handoff. No 4090 command is run by the control plane; after committing C16, make that exact checkpoint commit reachable on the 4090, checkout it cleanly, verify the new script SHA, and run only C16.

## C17 — C16 transport-provenance repair and superseding formal operator handoff

The user manually invoked the exact C16 checkpoint on the RTX 4090 and preflight terminated at the reverse-SSH workflow ancestry check with `fatal: Not a valid commit name b4ac6acb95530f5359566e6f140f77ad6a4da78f`. Git inspection confirms that this 40-hex value is not an object in the repository. The intended transport amendment is the existing commit `b4ac6acab60703c288a2e2e82e84398a11320177` (`chore: switch Piston tunnel to reverse SSH`), which is an ancestor of both C15 and C16. C15 introduced the malformed full SHA and C16 inherited it unchanged.

The failure occurs in C16 preflight before persistent-root, GPU, formal-pair, storage, or training checks and before either `train-grpo` call. It therefore cannot have started Public or Hidden formal training. C16 status/log/evidence produced before the fail-closed exit remain immutable failed-attempt evidence under the C16 operator root.

C16 checkpoint commit `03be8f6d084b75ebf39d04cafb499d9127390955` and C16 script SHA256 `9e752f8b60204874dcce8c779acaca478a4749da3f94de36316406b964e4ac3e` remain immutable. C17 is copied from C16 and changes only operator identity/provenance: it binds the real transport commit, uses C16 as its direct parent and superseded checkpoint, authenticates the immutable C16 script, and writes into a distinct C17 operator root. Scientific configs, reward code, formal pair, Piston definition, transport policy, B/data/model identities, run names, 300-step/50-save cadence, checkpoint/recovery semantics, postcheck, and Public/Hidden isolation are unchanged.

C17 control-plane validation before handoff:

- `git cat-file -t b4ac6acab60703c288a2e2e82e84398a11320177`: PASS (`commit`).
- Correct transport commit ancestry to C16: PASS.
- `bash -n ai-work/executor/operator/WP7-c/grpo-cd-formal/C17/run.sh`: PASS.
- Immutable C16 SHA recheck: PASS (`9e752f8b60204874dcce8c779acaca478a4749da3f94de36316406b964e4ac3e`).
- C17 script SHA256: `155f5b138e5a8db052f235b9966b5044312d5556d480c513649f8430d8b44d2a`.

```yaml
execution_checkpoint:
  checkpoint_id: C17
  source_plan_commit: 8464e69691c527c726a2e28e5a7ca81fa2001bbf
  result_code_commit: 03be8f6d084b75ebf39d04cafb499d9127390955
  workflow_transport_commit: b4ac6acab60703c288a2e2e82e84398a11320177
  operator_gate_id: grpo-cd-formal
  operator_handoff_mode: portable_target
  operator_restart_policy: trainer_checkpoint
  operator_script: ai-work/executor/operator/WP7-c/grpo-cd-formal/C17/run.sh
  operator_script_sha256: 155f5b138e5a8db052f235b9966b5044312d5556d480c513649f8430d8b44d2a
  formal_pair_sha256: 7924be4e115b20bc3e40207256d67d2e8591c973dbd9de7bfcb0b4bf39b08df3
  transport_policy_sha256: d7e7b3a3a2f6492cf6040c08a64086fba3aa7a9c4f5209752a0ba2917ef81c85
  piston_definition_sha256: f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e
  accepted_c13_operator_evidence_sha256: 91647fa09354f1dbaf486b7d94960934391467470665401022493ad5fb87d50b
  accepted_c13_postcheck_sha256: 91d4825b86a325a8f9765bfb9d99ab51345051c046c9847cfe335aadad487b2f
  supersedes_checkpoint_id: C16
  supersedes_checkpoint_commit: 03be8f6d084b75ebf39d04cafb499d9127390955
  superseded_operator_script_sha256: 9e752f8b60204874dcce8c779acaca478a4749da3f94de36316406b964e4ac3e
  supersession_reason: C16 inherited a nonexistent workflow transport commit SHA and failed closed during ancestry preflight
  target_status_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C17/status"
  target_log_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C17/terminal.log"
  target_evidence_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C17/operator-evidence.json"
  target_postcheck_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C17/postcheck-summary.json"
  target_gpu: NVIDIA GeForce RTX 4090
  target_precision: bf16
  formal_public_run: C-public-grpo-formal-seed42
  formal_hidden_run: D-hidden-grpo-formal-seed42
  status: awaiting_operator
```

C17 replaces C16 as the only formal operator handoff. Do not edit or rerun C16. After committing C17, make that exact checkpoint commit reachable on the 4090, checkout it cleanly, verify the C17 script SHA, and run only C17.

## C18 — stale Piston keep-alive repair and fresh formal restart handoff

The user manually invoked the exact C17 checkpoint `0bc5c2a8251f41b6265ba1a43a064ca04ea48ba9` on the RTX 4090. C17 passed operator preflight and entered Public GRPO, but the first reward batch stopped with `GRPO reward execution infrastructure failure in 8/8 completions; aborting before optimizer update` at 0/300. This is materially different from C15/C16 wrapper/preflight failures: C17 reached the production reward executor, but the explicit GRPO infrastructure circuit breaker prevented the first optimizer update.

Control-plane diagnosis reproduced the failure deterministically with the production `PistonExecutor`. The Piston Express endpoint advertises `Keep-Alive: timeout=5`; connection implementation v1 reused the same HTTP/1.1 socket from the pre-training `/api/v2/runtimes` validation across model loading/first generation. After a 6-second idle, a known-correct `target(1) == 1` request reproduced `sandbox_error` with transport telemetry `transport_requests=1`, `transport_ambiguous_failures=1`, and no connect failure/retry. Because `_TrainingExecutorCircuitBreaker` trips after that first infrastructure result, the remaining seven reward items become fail-closed infrastructure failures without seven additional real Piston requests. This explains the observed 8/8 error without weakening the no-ambiguous-replay contract.

The stale-connection repair is commit `da2a8a353efb6bd8dff7071e6e21cf13c703497c`, whose direct parent is C17. Its scope is exactly `docs/piston-transport-resilience.md`, `src/code_verifier/execution/piston.py`, `src/code_verifier/execution/piston_resilience.py`, and `tests/unit/execution/test_piston.py`. Before reusing an idle real socket, the client now performs a zero-time readiness/error check and discards peer-closed/exceptional sockets before any new request bytes are sent. Ambiguous candidate POSTs remain non-replayable. The connection implementation identity is bumped from `httpclient-single-keepalive-v1` to `httpclient-single-keepalive-v2`; the normalized transport policy identity is therefore `0e0b85e0331840c9825cc6d4cb357e4d129e4906d945b85f80d532adecf655f3`. The scientific Piston definition remains unchanged at `f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e`; datasets, reward mathematics, B/model identity, max_steps=300, and all non-checkpoint-cadence hyperparameters remain unchanged. Before sealing C18, the paired formal configs are intentionally changed together from `save_steps=50` to `save_steps=25` in result-code commit `3b63a13e38d31f2182183d2c0d42f9f0478fae5c` to support shorter multi-session recovery windows; this changes only the paired config/pair provenance, not reward or optimizer mathematics.

Control-plane validation of the repair and C18 handoff:

- Focused transport/recovery suite after the repair: 79 passed.
- `make lint`: PASS.
- `make test`: 999 passed, 3 skipped.
- real `make test-piston PISTON_CONFIG=configs/execution/piston-local.yaml`: 9 passed, 2 deselected, no Piston failure/skip.
- `make test-gpu`: 3 passed.
- Exact production idle reproduction after the repair: `validate_runtime()` -> 6-second idle -> trusted passing execute returned `passed 1/1`, with `transport_requests=1` and `transport_ambiguous_failures=0`.
- C18 `bash -n`: PASS; all 16 embedded Python heredocs compile; `set -u` uppercase-variable source audit reports no unresolved variable.
- Synthetic C17 failure-quarantine fixture: first invocation returned `quarantined`, second invocation returned idempotent `already_quarantined`, with the canonical Public path absent and archive/manifest present.
- C18 script SHA256: `183173fa4ae0fed2f33f8566e868f0248129f5d448fa225cdedcaa1f7cf07269`.

C18 does not resume the C17 run across a code commit. Before a fresh C18 Public run is allowed, target preflight must authenticate the C17 operator status/log/evidence and the exact failed Public signature: C17 commit/script/old transport identity; command rc=2 / `command_failed`; the exact 8/8 pre-optimizer error in terminal log; `run.json.status=failed`; `global_step=null`; exactly one fresh failed attempt at C17; empty Trainer checkpoint directory; empty `metrics.jsonl`; canonical row counts 8 rollouts / 8 rewards / 2 groups; all eight rewards `sandbox_error` infrastructure failures with exactly one `executed=true`; and old transport telemetry exactly one request / one ambiguous failure / zero safe retry/connect failure. Hidden formal run/sidecar must still be absent on the first quarantine. C18 then moves the C17 Public run and sidecar byte-for-byte into `$CODE_VERIFIER_ARTIFACT_ROOT/grpo-failed-history/C17-stale-keepalive/`, verifies pre/post SHA inventories, writes an atomic manifest binding C17 operator/status/log/evidence hashes, and only then releases the canonical Public namespace for a fresh run from formal B. A rerun of C18 validates the existing archive manifest rather than overwriting it.

C18 additionally performs the 6-second production idle-reuse Piston probe on target before any formal command. Current C18 runs may resume only from same-C18 valid 25-step Trainer+canonical-log checkpoints; C17 is never used as a Trainer resume source. Public remains first and flows directly into Hidden when Public succeeds or is already completed under the same C18 checkpoint; there is no operator pause inserted between the pair members, and no generation/evaluation is started by this gate.

```yaml
execution_checkpoint:
  checkpoint_id: C18
  source_plan_commit: 8464e69691c527c726a2e28e5a7ca81fa2001bbf
  result_code_commit: 3b63a13e38d31f2182183d2c0d42f9f0478fae5c
  transport_repair_commit: da2a8a353efb6bd8dff7071e6e21cf13c703497c
  workflow_transport_commit: b4ac6acab60703c288a2e2e82e84398a11320177
  operator_gate_id: grpo-cd-formal
  operator_handoff_mode: portable_target
  operator_restart_policy: trainer_checkpoint
  operator_script: ai-work/executor/operator/WP7-c/grpo-cd-formal/C18/run.sh
  operator_script_sha256: 183173fa4ae0fed2f33f8566e868f0248129f5d448fa225cdedcaa1f7cf07269
  formal_pair_sha256: 31f5464abf094d14cf86e8ef4dd909b8a1be559c8b4ca8b96473070a9f1daad9
  formal_public_config_sha256: e7353aecf28cf496def0a03f64a7ee8c739dc914e8df22a23e008bb72ef0e1e2
  formal_hidden_config_sha256: 951bef7fcd17694bac9d52e180290bcbb46b69f3756810c9402075b1d422a129
  formal_save_steps: 25
  transport_policy_sha256: 0e0b85e0331840c9825cc6d4cb357e4d129e4906d945b85f80d532adecf655f3
  transport_connection_implementation: httpclient-single-keepalive-v2
  piston_definition_sha256: f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e
  accepted_c13_operator_evidence_sha256: 91647fa09354f1dbaf486b7d94960934391467470665401022493ad5fb87d50b
  accepted_c13_postcheck_sha256: 91d4825b86a325a8f9765bfb9d99ab51345051c046c9847cfe335aadad487b2f
  supersedes_checkpoint_id: C17
  supersedes_checkpoint_commit: 0bc5c2a8251f41b6265ba1a43a064ca04ea48ba9
  superseded_operator_script_sha256: 155f5b138e5a8db052f235b9966b5044312d5556d480c513649f8430d8b44d2a
  superseded_transport_policy_sha256: d7e7b3a3a2f6492cf6040c08a64086fba3aa7a9c4f5209752a0ba2917ef81c85
  supersession_reason: C17 hit the reproducible stale persistent-HTTP socket after Piston's 5-second keep-alive timeout before the first optimizer update
  c17_failed_history_template: "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-failed-history/C17-stale-keepalive"
  target_status_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C18/status"
  target_log_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C18/terminal.log"
  target_evidence_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C18/operator-evidence.json"
  target_postcheck_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C18/postcheck-summary.json"
  target_gpu: NVIDIA GeForce RTX 4090
  target_precision: bf16
  formal_public_run: C-public-grpo-formal-seed42
  formal_hidden_run: D-hidden-grpo-formal-seed42
  status: awaiting_operator
```

C18 supersedes C17 as the only formal operator handoff. C17 failed artifacts must remain preserved and are consumed only by C18's authenticated quarantine step; do not manually delete, rename, or edit them. The control plane does not execute C18 on the 4090 and does not push automatically.

### C18 pre-formal checkpoint/resume and analysis-readiness audit

Before authorizing formal target execution, the C18 wrapper and production GRPO recovery path were re-audited specifically for multi-session training. Formal cadence is `max_steps=300`, `save_steps=25` for both Public and Hidden; the paired save cadence is the only intentional formal config change in C18, so the portable config components and paired-definition SHA are re-certified above. Resume remains same-run and same-C18-checkpoint only. `_latest_valid_resume_checkpoint()` selects the highest cadence checkpoint only when all pinned Trainer resume files are non-empty, `trainer_state.json.global_step` matches the directory step, and the project-owned canonical GRPO log-state sidecar validates against the current streaming-log prefix. A newer partial checkpoint is skipped rather than trusted. Before a resumed attempt starts, any canonical log suffix after the selected boundary and any later checkpoint directories are preserved under `checkpoints/recovery-history/`, then the canonical rollout/reward/group streams are atomically restored to the selected boundary.

Recovery-focused control-plane verification was rerun after the transport repair: 13 targeted tests passed, covering failed-suffix archive/restore, incomplete-newer-checkpoint fallback, repeated hard interruption recovery, same-run resume binding, read-only validation before attempt begin, cross-commit rejection, and durable cumulative transport-sidecar restore. Two additional training/analysis-loader checks passed, confirming the completed GRPO artifacts remain directly consumable by `load_training_curve_rows()` and `build_cost_row()`.

C18 now logs the session policy and traps `HUP` in addition to `INT`/`TERM`. For planned multi-session operation, the preferred boundary is any fully written 25-step checkpoint (`25, 50, 75, ..., 275`), followed by foreground `Ctrl-C` and waiting for the operator to exit before the target is released. That path lets Python's `BaseException` cleanup close the attempt with end time and measured attempt GPU-hours. An abrupt target loss / `kill -9` is still recoverable from the last complete checkpoint, including when `run.json` is left `running`, but the hard-killed attempt cannot have exact end/GPU-hours reconstructed without fabrication. Final C18 postcheck therefore reports `hard_interrupted_attempt_count` and `gpu_hours_complete_for_all_attempts`; later cost analysis must treat a false completeness flag as an operational telemetry limitation rather than silently assuming zero cost. Final postcheck also requires one recovery-history archive for every resumed attempt, with the archive checkpoint encoded by that attempt's `resume_from_checkpoint`. There is deliberately no pause or scheduling branch between Public and Hidden: after Public completes, the same C18 invocation proceeds directly to Hidden.

Analysis coverage was checked against PROJECT_SPEC §12.3. A completed Public or Hidden formal run retains: exact 300-step Trainer numeric telemetry including loss, reward/reward_std, KL, generation/rollout/no-grad/step timing, completion mean length and clipped ratio; 2400 completion rollouts with text/token-count/truncation/reward; 2400 reward-component rows with parse/execution/infrastructure status, component rewards, pass/total tests, failure counts and executor runtime; 600 group mean/std/all-equal records; peak CUDA allocation/reservation; cumulative attempt/GPU-hours lineage; transport request/retry/ambiguity telemetry; twelve full Trainer checkpoints at steps 25..300; and preserved failed-attempt suffix archives. Streaming reward evidence is fsynced as it is appended, transport telemetry is durably snapshotted per mutation, and every Trainer checkpoint receives a canonical log-state snapshot after the Trainer save.

To make later step-wise analysis unambiguous even across multiple resumes, C18 final postcheck now validates the canonical raw-log ordering as exactly 300 blocks of 8 rollout rows + 8 aligned reward rows + 2 group rows, with item/group/problem/reward alignment inside every block. `postcheck-summary.json` records this `analysis_layout`, so optimizer step `n` maps deterministically to rollout/reward rows `[(n-1)*8:n*8]` and group rows `[(n-1)*2:n*2]`. Canonical streams contain only successful final-prefix training data; discarded/interrupted suffixes remain separately preserved in recovery-history for operational analysis and are never mixed into the scientific final curves.

Audit conclusion: C18 is suitable for deliberate multi-session execution provided planned stops are made after a verified complete 25-step checkpoint. Arbitrary interruption may replay work since the previous 25-step checkpoint but does not corrupt canonical evidence; hard process/machine loss preserves recoverability but may make the interrupted attempt's GPU-hours incomplete. No formal 4090 training was executed during this audit.

## C19 — C18 resume-preflight signature repair with preserved C18 training provenance

After a real C18 target session had already created resumable formal artifacts, the user re-ran the exact C18 operator and observed `accepted_c13_pilot=PASS` followed by `TypeError: _validate_resume_run() missing 1 required keyword-only argument: 'resume_run_git_commit'`. The failing call is inside C18 `resolve_run_action()` after a valid existing run/checkpoint has been selected and before the next `train-grpo` command is launched. Production `_validate_resume_run()` requires the keyword-only argument, while the C18 wrapper omitted it. This is an operator-wrapper defect, not a reward, optimizer, checkpoint-content, Piston, or GPU failure; the failed resume-preflight invocation is read-only with respect to the formal run.

C18 is now immutable because it has been executed on target and its operator evidence/formal run metadata bind checkpoint commit `a7c3c4da77b6cb6af387a74667e42d33bc9f7e6b` and script SHA256 `183173fa4ae0fed2f33f8566e868f0248129f5d448fa225cdedcaa1f7cf07269`. Therefore the repair is a new operator checkpoint C19 rather than an in-place rewrite of C18. C19 makes no production `src/`, formal config, reward, optimizer, transport-policy, dataset, B/model, or checkpoint-cadence change. The formal pair remains `31f5464abf094d14cf86e8ef4dd909b8a1be559c8b4ca8b96473070a9f1daad9`, with `save_steps=25` and no Public→Hidden scheduling pause.

To preserve the existing C18 Trainer checkpoint without permitting a cross-Git-commit Trainer resume, C19 materializes a temporary detached Git worktree at the exact preserved C18 commit `a7c3c4da77b6cb6af387a74667e42d33bc9f7e6b`. Resume-state validation and every actual `train-grpo` invocation load `code_verifier` from that temporary C18 worktree via `PYTHONPATH`; control-plane verification confirmed `collect_environment()['project_commit']` then resolves exactly to the C18 commit. C19 calls `_validate_resume_run(..., resume_run_git_commit=None)` under that same C18 source identity and deliberately does not pass `--resume-run-git-commit` to training. Thus existing and future attempts for the current formal pair continue to record the original C18 training Git provenance, while C19 separately records the repaired operator-wrapper checkpoint. The main target checkout remains at C19; the temporary C18 training worktree is removed on operator exit and stale registrations are pruned before recreation.

Control-plane C19 verification before handoff:

- C19 shell syntax: PASS.
- All 17 embedded Python heredocs compile.
- `set -u` uppercase-variable audit: no unresolved variables.
- Detached C18 source execution probe: `code_verifier` loads from the C18 worktree and reports project commit `a7c3c4da77b6cb6af387a74667e42d33bc9f7e6b`.
- `python -m code_verifier.cli train-grpo --help` succeeds from the detached C18 source using the stage virtualenv.
- C19 does not pass `--resume-run-git-commit`; its explicit `_validate_resume_run` call uses `resume_run_git_commit=None` under the same preserved C18 source commit.
- C19 operator script SHA256: `9a762a5ec6484b5ae374e2e79230f212e76551588df170fbe75c754c8afc0dbb`.

```yaml
execution_checkpoint:
  checkpoint_id: C19
  source_plan_commit: 8464e69691c527c726a2e28e5a7ca81fa2001bbf
  result_code_commit: a7c3c4da77b6cb6af387a74667e42d33bc9f7e6b
  training_code_commit: a7c3c4da77b6cb6af387a74667e42d33bc9f7e6b
  workflow_transport_commit: b4ac6acab60703c288a2e2e82e84398a11320177
  operator_gate_id: grpo-cd-formal
  operator_handoff_mode: portable_target
  operator_restart_policy: trainer_checkpoint
  operator_script: ai-work/executor/operator/WP7-c/grpo-cd-formal/C19/run.sh
  operator_script_sha256: 9a762a5ec6484b5ae374e2e79230f212e76551588df170fbe75c754c8afc0dbb
  formal_pair_sha256: 31f5464abf094d14cf86e8ef4dd909b8a1be559c8b4ca8b96473070a9f1daad9
  formal_public_config_sha256: e7353aecf28cf496def0a03f64a7ee8c739dc914e8df22a23e008bb72ef0e1e2
  formal_hidden_config_sha256: 951bef7fcd17694bac9d52e180290bcbb46b69f3756810c9402075b1d422a129
  formal_save_steps: 25
  transport_policy_sha256: 0e0b85e0331840c9825cc6d4cb357e4d129e4906d945b85f80d532adecf655f3
  transport_connection_implementation: httpclient-single-keepalive-v2
  piston_definition_sha256: f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e
  accepted_c13_operator_evidence_sha256: 91647fa09354f1dbaf486b7d94960934391467470665401022493ad5fb87d50b
  accepted_c13_postcheck_sha256: 91d4825b86a325a8f9765bfb9d99ab51345051c046c9847cfe335aadad487b2f
  supersedes_checkpoint_id: C18
  supersedes_checkpoint_commit: a7c3c4da77b6cb6af387a74667e42d33bc9f7e6b
  superseded_operator_script_sha256: 183173fa4ae0fed2f33f8566e868f0248129f5d448fa225cdedcaa1f7cf07269
  supersession_reason: C18 resume preflight omitted required _validate_resume_run resume_run_git_commit keyword before train-grpo launch
  target_status_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C19/status"
  target_log_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C19/terminal.log"
  target_evidence_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C19/operator-evidence.json"
  target_postcheck_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C19/postcheck-summary.json"
  target_gpu: NVIDIA GeForce RTX 4090
  target_precision: bf16
  formal_public_run: C-public-grpo-formal-seed42
  formal_hidden_run: D-hidden-grpo-formal-seed42
  status: awaiting_operator
```

C19 supersedes C18 only at the operator-wrapper layer. Existing C18 formal run/checkpoint/transport artifacts must not be deleted, renamed, rewritten, or manually migrated; C19 is designed to consume them in place while preserving their C18 training Git identity. The control plane does not execute C19 on the 4090 and does not push automatically.

## C20 — preserve C18 source identity without changing path-sensitive GRPO config identity

The real C19 target invocation progressed beyond the repaired wrapper-side `_validate_resume_run()` signature and then failed with `existing GRPO run identity does not match the requested resume`. Control-plane source audit identified the mismatch deterministically. GRPO config loading resolves relative paths against `Path.cwd()`: `_path()` converts `piston_config: configs/execution/piston-local.yaml` into an absolute path, and `_config_hash()` persists that absolute path. The existing C18 run was launched from the canonical target checkout. C19 correctly loaded C18 Python code from a temporary detached C18 worktree, but its actual `train-grpo` subshell also changed cwd into that `/tmp/...` worktree. Consequently the resumed config's absolute `piston_config` path, and therefore `config_hash`, differed from the existing C18 run even though the file bytes and scientific settings were unchanged.

C20 is an operator-wrapper-only correction. It still loads all training Python code from the exact C18 commit `a7c3c4da77b6cb6af387a74667e42d33bc9f7e6b`, so `collect_environment()['project_commit']` remains C18 and there is no cross-commit Trainer resume. However, C20 canonicalizes cwd to the main target checkout and does not `cd` into the temporary C18 worktree for `train-grpo`. Therefore relative config paths resolve exactly as they did when the existing C18 run was created. No production source, formal config, pair identity, reward, optimizer, dataset, B/model, Piston policy, or checkpoint bytes are changed.

Control-plane reproduction confirmed the bug and repair: with the same C18 source and the same synthetic formal dataset path, loading the config from canonical cwd resolved `piston_config` to the canonical checkout and produced one config hash; changing only cwd to the temporary C18 worktree resolved `piston_config` under `/tmp/...` and produced a different config hash. C20 keeps C18 module/project provenance while restoring the canonical cwd/path identity. Shell syntax and all 17 embedded Python heredocs pass, and 85 targeted GRPO resume/lineage/transport-sidecar tests pass.

```yaml
execution_checkpoint:
  checkpoint_id: C20
  source_plan_commit: 8464e69691c527c726a2e28e5a7ca81fa2001bbf
  result_code_commit: 71f1ce0194089a47fb2e23c7cce1ea589a8d562d
  training_code_commit: a7c3c4da77b6cb6af387a74667e42d33bc9f7e6b
  workflow_transport_commit: b4ac6acab60703c288a2e2e82e84398a11320177
  operator_gate_id: grpo-cd-formal
  operator_handoff_mode: portable_target
  operator_restart_policy: trainer_checkpoint
  operator_script: ai-work/executor/operator/WP7-c/grpo-cd-formal/C20/run.sh
  operator_script_sha256: 049c28c1f9b5fbd5a823a50ec6b10105ecc5ea09ff19c308110ebb601292e25c
  formal_pair_sha256: 31f5464abf094d14cf86e8ef4dd909b8a1be559c8b4ca8b96473070a9f1daad9
  formal_public_config_sha256: e7353aecf28cf496def0a03f64a7ee8c739dc914e8df22a23e008bb72ef0e1e2
  formal_hidden_config_sha256: 951bef7fcd17694bac9d52e180290bcbb46b69f3756810c9402075b1d422a129
  formal_save_steps: 25
  transport_policy_sha256: 0e0b85e0331840c9825cc6d4cb357e4d129e4906d945b85f80d532adecf655f3
  transport_connection_implementation: httpclient-single-keepalive-v2
  piston_definition_sha256: f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e
  accepted_c13_operator_evidence_sha256: 91647fa09354f1dbaf486b7d94960934391467470665401022493ad5fb87d50b
  accepted_c13_postcheck_sha256: 91d4825b86a325a8f9765bfb9d99ab51345051c046c9847cfe335aadad487b2f
  supersedes_checkpoint_id: C19
  supersedes_checkpoint_commit: 71f1ce0194089a47fb2e23c7cce1ea589a8d562d
  superseded_operator_script_sha256: 9a762a5ec6484b5ae374e2e79230f212e76551588df170fbe75c754c8afc0dbb
  supersession_reason: C19 changed train-grpo cwd to the temporary C18 worktree, changing the absolute piston_config path embedded in config_hash
  target_status_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C20/status"
  target_log_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C20/terminal.log"
  target_evidence_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C20/operator-evidence.json"
  target_postcheck_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C20/postcheck-summary.json"
  target_gpu: NVIDIA GeForce RTX 4090
  target_precision: bf16
  formal_public_run: C-public-grpo-formal-seed42
  formal_hidden_run: D-hidden-grpo-formal-seed42
  status: awaiting_operator
```

C20 supersedes C19 at the operator-wrapper layer only. Preserve all existing C18/C19 operator evidence and all formal run/checkpoint/transport artifacts in place; C20 consumes the existing C18 Trainer checkpoint without rewriting its training Git or scientific identity.

## C21 — bounded automatic recovery for transient Piston reward infrastructure failures

A second real C20 target invocation resumed Public from checkpoint-175 and again failed during reward execution, this time after step 198. The terminal log recorded `GRPO reward execution infrastructure failure in 6/8 completions; aborting before optimizer update`. Target-side forensic readback showed the same transport signature as the earlier step-196 failure: cumulative `transport_ambiguous_failures` increased from 1 to 2 while connect-failure/safe-retry counters remained zero; the final failed reward batch contained one genuinely executed infrastructure failure followed by circuit-breaker fanout rows with `executed=false`. Production `_latest_valid_resume_checkpoint()` still selected checkpoint-175. This establishes a repeated transient/ambiguous Piston transport failure rather than a model, CUDA, identity, or checkpoint failure.

C21 remains an operator-wrapper-only repair because the existing formal run is permanently bound to training Git commit `a7c3c4da77b6cb6af387a74667e42d33bc9f7e6b`. Changing reward/Piston production source would require an impermissible cross-Git-commit Trainer resume. C21 therefore continues loading the exact C18 training source and keeps the canonical checkout cwd, but wraps each Public/Hidden `train-grpo` process in bounded infrastructure recovery. A nonzero command is automatically retried only when all of the following are true: rc is exactly 2; run metadata and latest attempt are failed; production latest-valid-checkpoint selection succeeds; reward rows after that checkpoint form complete 8-row batches; the final batch contains at least one `infrastructure_failure=true` row; every such row has zero total reward; and at least one infrastructure-failure row was actually executed against Piston. Other errors remain fail-closed.

For an authenticated infrastructure failure, C21 permits at most three recoveries per Public/Hidden member. Each recovery records a visible `C21 RECOVERY` line, applies a bounded 5/10/15-second backoff, rechecks exact Piston runtime health, re-runs the normal strict `resolve_run_action()` validation, verifies the selected checkpoint is unchanged between failure authentication and resume resolution, and starts a fresh C18 `train-grpo` process from that checkpoint. Existing GRPO recovery logic archives the discarded suffix and restores canonical streams before the next attempt; the failed reward batch is therefore never used for an optimizer update or final scientific stream. Exhaustion or any non-authenticated failure prints an explicit terminal failure and writes normal operator evidence. Operator evidence additionally records Public/Hidden bounded-recovery counts.

Control-plane/target-readback verification before handoff:

- C20 second failure signature: 6/8 reward infrastructure failures at the post-step-198 batch; transport ambiguous-failure counter incremented to 2, with zero connect failures/safe retries.
- Target read-only classifier reproduction: retryable, checkpoint `checkpoint-175`, infrastructure rows `6`, suffix rows `192`.
- C21 shell syntax: PASS.
- All embedded Python blocks compile after adding the infrastructure classifier.
- Targeted GRPO resume/lineage/transport-sidecar tests: 85 passed.
- No target training was started by the control plane while preparing C21.

```yaml
execution_checkpoint:
  checkpoint_id: C21
  source_plan_commit: 8464e69691c527c726a2e28e5a7ca81fa2001bbf
  result_code_commit: 720a48cc9edb281ccb91b8f59080c65c118bde65
  training_code_commit: a7c3c4da77b6cb6af387a74667e42d33bc9f7e6b
  workflow_transport_commit: b4ac6acab60703c288a2e2e82e84398a11320177
  operator_gate_id: grpo-cd-formal
  operator_handoff_mode: portable_target
  operator_restart_policy: trainer_checkpoint
  operator_script: ai-work/executor/operator/WP7-c/grpo-cd-formal/C21/run.sh
  operator_script_sha256: 51873cbc7a7c35a021b48296d934043a4f8218ae31278ef1931637d77f0f13f4
  formal_pair_sha256: 31f5464abf094d14cf86e8ef4dd909b8a1be559c8b4ca8b96473070a9f1daad9
  formal_public_config_sha256: e7353aecf28cf496def0a03f64a7ee8c739dc914e8df22a23e008bb72ef0e1e2
  formal_hidden_config_sha256: 951bef7fcd17694bac9d52e180290bcbb46b69f3756810c9402075b1d422a129
  formal_save_steps: 25
  bounded_infrastructure_recoveries_per_mode: 3
  transport_policy_sha256: 0e0b85e0331840c9825cc6d4cb357e4d129e4906d945b85f80d532adecf655f3
  transport_connection_implementation: httpclient-single-keepalive-v2
  piston_definition_sha256: f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e
  accepted_c13_operator_evidence_sha256: 91647fa09354f1dbaf486b7d94960934391467470665401022493ad5fb87d50b
  accepted_c13_postcheck_sha256: 91d4825b86a325a8f9765bfb9d99ab51345051c046c9847cfe335aadad487b2f
  supersedes_checkpoint_id: C20
  supersedes_checkpoint_commit: 720a48cc9edb281ccb91b8f59080c65c118bde65
  superseded_operator_script_sha256: 049c28c1f9b5fbd5a823a50ec6b10105ecc5ea09ff19c308110ebb601292e25c
  supersession_reason: repeated transient ambiguous Piston reward failures aborted long GRPO despite valid recoverable checkpoints
  target_status_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C21/status"
  target_log_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C21/terminal.log"
  target_evidence_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C21/operator-evidence.json"
  target_postcheck_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C21/postcheck-summary.json"
  target_gpu: NVIDIA GeForce RTX 4090
  target_precision: bf16
  formal_public_run: C-public-grpo-formal-seed42
  formal_hidden_run: D-hidden-grpo-formal-seed42
  status: awaiting_operator
```

C21 supersedes C20 only at the operator-wrapper layer. Preserve all existing C18/C19/C20 operator evidence and all formal run/checkpoint/transport/recovery-history artifacts in place. C21 is designed to consume the existing C18 run and checkpoint lineage without changing its training Git identity or scientific configuration.

## C22 — in-process reward transport recovery and explicit checkpoint code migration

C20 reached Public GRPO progress beyond checkpoint-175 twice, then failed at approximately steps 196 and 198 with transient ambiguous Piston transport failures. The second failure produced six infrastructure-failure reward rows in the final eight-completion batch, while target transport telemetry reached two ambiguous failures with zero connect failures and zero safe transport retries. The production reward circuit breaker correctly aborted before optimizer update, but process exit forced later work back to checkpoint-175.

C21 added bounded shell-level Trainer process recovery without changing the C18 training source. It is preserved as immutable history but was not adopted as the final recovery design. C22 supersedes that wrapper-level approach with production training commit `47c7fb2a55b91e471aeca5ededf6e0233f4f93f9`: the reward callback retries only the exact sanitized Piston transport-failure signature, rebuilds and health-checks the exact Python 3.10.0 connection before each retry, then re-executes the identical code/function/tests/timeout/memory request after 1/2/4-second bounded backoff. It does not regenerate completions, change RNG, roll back model state, or enter optimizer update before reward success. Successful transient failures produce only the final successful scientific reward row; payload-free retry events and counters remain operational telemetry. Exhaustion after three retries remains fail-closed before optimizer update.

This repair intentionally changes training code while preserving scientific identity. Public `run.json.git_commit` remains the C18 origin `a7c3c4da77b6cb6af387a74667e42d33bc9f7e6b`; each new attempt records the actual repair code commit. The first resume from legacy C18 checkpoint-175 requires `operational_reward_resilience_v1` and records C18-to-repair migration with `scientific_change=false`. Trainer checkpoint sidecars now use v2 and persist the actual 40-hex training code commit. Existing C18 v1 sidecars remain readable only by strict derivation from the preserved run origin. Later resumes from a v2 repair checkpoint are same-code resumes and must not record a false migration.

Formal Public/Hidden YAML, max_steps=300, save_steps=25, seed=42, reward formula, model, LoRA, optimizer, scheduler, datasets, completed B parent, Piston scientific definition, and transport policy are unchanged. The formal pair remains `31f5464abf094d14cf86e8ef4dd909b8a1be559c8b4ca8b96473070a9f1daad9`; Piston definition remains `f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e`; transport policy remains `0e0b85e0331840c9825cc6d4cb357e4d129e4906d945b85f80d532adecf655f3`.

C22 keeps the proven C20 path-identity boundary: it creates a temporary detached worktree at the exact repair commit, loads `code_verifier` through that worktree's `src`, and runs `train-grpo` from the canonical target checkout so relative `piston_config` resolution and config hash remain unchanged. Public uses production latest-valid checkpoint selection and explicit preserved-origin/migration arguments. Hidden starts fresh from formal B when absent. Each pair member launches at most one Trainer process per C22 invocation; C22 contains no shell process-retry loop. Final postcheck accepts Public's C18 origin plus C18/repair attempt lineage, requires migration exactly when selected checkpoint code differs, rejects false same-code migrations, requires Hidden origin/attempt code at the repair commit, rejects canonical infrastructure/sandbox reward failures, and aggregates retry counters into postcheck/evidence.

Control-plane validation before handoff:

- Focused required suite: 238 passed.
- `make lint`: PASS; Ruff check/format and strict mypy all passed.
- `make test`: 1009 passed, 3 skipped; GPU smoke tests ran on the GTX 1660 Ti.
- real `make test-piston PISTON_CONFIG=configs/execution/piston-local.yaml`: 9 passed, 2 deselected, zero failures/skips among selected Piston tests.
- explicit `make test-gpu`: 3 passed.
- C22 `bash -n`: PASS; all 17 embedded Python blocks compile; uppercase `set -u` source audit has no unresolved variable except the intentionally optional external machine-pointer override.
- C22 script SHA256: `6baf5e898b735796e7b396e53ba3254ef00208d19035a4b9e69008f2c8e3cd7f`.
- No C22 operator command or RTX 4090 workload was started by the control plane.

```yaml
execution_checkpoint:
  version: 1
  checkpoint_id: C22
  stage_id: WP7-c
  task_kind: repair
  source_plan_commit: 8464e69691c527c726a2e28e5a7ca81fa2001bbf
  result_code_commit: 47c7fb2a55b91e471aeca5ededf6e0233f4f93f9
  training_code_commit: 47c7fb2a55b91e471aeca5ededf6e0233f4f93f9
  workflow_transport_commit: b4ac6acab60703c288a2e2e82e84398a11320177
  operator_gate_id: grpo-cd-formal
  operator_handoff_mode: portable_target
  operator_restart_policy: trainer_checkpoint
  operator_script: ai-work/executor/operator/WP7-c/grpo-cd-formal/C22/run.sh
  operator_script_sha256: 6baf5e898b735796e7b396e53ba3254ef00208d19035a4b9e69008f2c8e3cd7f
  formal_pair_sha256: 31f5464abf094d14cf86e8ef4dd909b8a1be559c8b4ca8b96473070a9f1daad9
  formal_public_config_sha256: e7353aecf28cf496def0a03f64a7ee8c739dc914e8df22a23e008bb72ef0e1e2
  formal_hidden_config_sha256: 951bef7fcd17694bac9d52e180290bcbb46b69f3756810c9402075b1d422a129
  formal_save_steps: 25
  piston_definition_sha256: f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e
  transport_policy_sha256: 0e0b85e0331840c9825cc6d4cb357e4d129e4906d945b85f80d532adecf655f3
  code_migration_class: operational_reward_resilience_v1
  reward_retry_policy_version: grpo-reward-infra-retry-v1
  reward_retry_max_retries: 3
  reward_retry_backoff_seconds: [1.0, 2.0, 4.0]
  public_run_origin_commit: a7c3c4da77b6cb6af387a74667e42d33bc9f7e6b
  public_initial_expected_checkpoint: production_latest_valid_expected_checkpoint-175
  checkpoint_log_state_write_version: 2
  checkpoint_log_state_legacy_read_version: 1
  accepted_c13_operator_evidence_sha256: 91647fa09354f1dbaf486b7d94960934391467470665401022493ad5fb87d50b
  accepted_c13_postcheck_sha256: 91d4825b86a325a8f9765bfb9d99ab51345051c046c9847cfe335aadad487b2f
  supersedes_checkpoint_id: C21
  supersedes_checkpoint_commit: 107d08dc115bdeea0a417702f453d4b2c048b0c0
  superseded_operator_script_sha256: 51873cbc7a7c35a021b48296d934043a4f8218ae31278ef1931637d77f0f13f4
  superseded_c20_checkpoint_commit: 720a48cc9edb281ccb91b8f59080c65c118bde65
  superseded_c20_operator_script_sha256: 049c28c1f9b5fbd5a823a50ec6b10105ecc5ea09ff19c308110ebb601292e25c
  supersession_reason: C21 wrapper-level Trainer process recovery is superseded by bounded in-process retry of the identical reward execution request
  target_status_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C22/status"
  target_log_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C22/terminal.log"
  target_evidence_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C22/operator-evidence.json"
  target_postcheck_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C22/postcheck-summary.json"
  expected_artifacts:
    - completed Public run with origin C18, accurate per-attempt code provenance, and global_step 300
    - completed Hidden run with repair-code origin and global_step 300
    - canonical reward streams without infrastructure_failure or sandbox_error rows
    - payload-free retry telemetry and versioned operator-evidence.json
  completed_scope:
    - control-plane production repair and engineering verification
    - immutable portable C22 operator handoff
  remaining_scope:
    - manual target execution and post-run evidence sync
  resume_allowed: true
  interruption_class: operator
  target_gpu: NVIDIA GeForce RTX 4090
  target_precision: bf16
  formal_public_run: C-public-grpo-formal-seed42
  formal_hidden_run: D-hidden-grpo-formal-seed42
  status: awaiting_operator
```

C22 supersedes C21 as the only formal operator handoff. Preserve C18/C19/C20/C21 scripts, evidence, and formal run/checkpoint/recovery history unchanged. Make the exact C22 checkpoint commit reachable on the RTX 4090, checkout it cleanly, verify the tracked script SHA256, then run only C22 manually. The control plane does not push or execute C22.

## C23 — operator-wrapper provenance constant repair

C22 was executed twice on the real RTX 4090 target and both invocations exited immediately during preflight with `immutable C21 operator script SHA changed`. Neither invocation reached GRPO training. Read-only verification proved that C21 was not modified: its committed script still has SHA256 `51873cbc7a7c35a021b48296d934043a4f8218ae31278ef1931637d77f0f13f4`, and the C21-to-C22 history contains no C21 script diff. The failure was a C22 wrapper provenance typo: adjacent string fragments assembled a 63-character expected C21 SHA (`...78ef193637...`) instead of the correct `...78ef1931637...` value.

C23 is wrapper-only. It preserves training code commit `47c7fb2a55b91e471aeca5ededf6e0233f4f93f9`, the in-process `grpo-reward-infra-retry-v1` policy, `operational_reward_resilience_v1` checkpoint migration, production latest-valid-checkpoint selection, detached repair-code worktree, canonical training cwd, and one Trainer process invocation per Public/Hidden member. It adds shared preflight guards requiring every hard-coded Git commit/revision to be exact 40-character lowercase hex and every hard-coded SHA256 to be exact 64-character lowercase hex before filesystem hash comparisons. It also validates the immutable C17–C22 scripts against their independently computed SHA256 values. C23 supersedes only the faulty C22 operator wrapper; no scientific config, reward, model, optimizer, dataset, seed, pair, Piston definition, or transport-policy identity changes.

```yaml
execution_checkpoint:
  version: 1
  checkpoint_id: C23
  stage_id: WP7-c
  task_kind: repair
  source_plan_commit: 8464e69691c527c726a2e28e5a7ca81fa2001bbf
  result_code_commit: 47c7fb2a55b91e471aeca5ededf6e0233f4f93f9
  training_code_commit: 47c7fb2a55b91e471aeca5ededf6e0233f4f93f9
  workflow_transport_commit: b4ac6acab60703c288a2e2e82e84398a11320177
  operator_gate_id: grpo-cd-formal
  operator_handoff_mode: portable_target
  operator_restart_policy: trainer_checkpoint
  operator_script: ai-work/executor/operator/WP7-c/grpo-cd-formal/C23/run.sh
  operator_script_sha256: b9761d58fadb68f515a3b4972b5c90bd633ed123c037255d02a8dd2cf14456ca
  formal_pair_sha256: 31f5464abf094d14cf86e8ef4dd909b8a1be559c8b4ca8b96473070a9f1daad9
  formal_public_config_sha256: e7353aecf28cf496def0a03f64a7ee8c739dc914e8df22a23e008bb72ef0e1e2
  formal_hidden_config_sha256: 951bef7fcd17694bac9d52e180290bcbb46b69f3756810c9402075b1d422a129
  formal_save_steps: 25
  piston_definition_sha256: f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e
  transport_policy_sha256: 0e0b85e0331840c9825cc6d4cb357e4d129e4906d945b85f80d532adecf655f3
  code_migration_class: operational_reward_resilience_v1
  reward_retry_policy_version: grpo-reward-infra-retry-v1
  reward_retry_max_retries: 3
  reward_retry_backoff_seconds: [1.0, 2.0, 4.0]
  provenance_constant_format_guards: git_commit_40_lowercase_hex_and_sha256_64_lowercase_hex
  c21_actual_operator_script_sha256: 51873cbc7a7c35a021b48296d934043a4f8218ae31278ef1931637d77f0f13f4
  accepted_c13_operator_evidence_sha256: 91647fa09354f1dbaf486b7d94960934391467470665401022493ad5fb87d50b
  accepted_c13_postcheck_sha256: 91d4825b86a325a8f9765bfb9d99ab51345051c046c9847cfe335aadad487b2f
  supersedes_checkpoint_id: C22
  supersedes_checkpoint_commit: 32d18869f929dacf464ef132f8d6d17177a4f834
  superseded_operator_script_sha256: 6baf5e898b735796e7b396e53ba3254ef00208d19035a4b9e69008f2c8e3cd7f
  supersession_reason: C22 carried a 63-character typo in the expected immutable C21 script SHA and failed before GRPO startup
  c22_target_invocations: 2
  c22_grpo_started: false
  target_status_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C23/status"
  target_log_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C23/terminal.log"
  target_evidence_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C23/operator-evidence.json"
  target_postcheck_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C23/postcheck-summary.json"
  resume_allowed: true
  interruption_class: operator
  target_gpu: NVIDIA GeForce RTX 4090
  target_precision: bf16
  formal_public_run: C-public-grpo-formal-seed42
  formal_hidden_run: D-hidden-grpo-formal-seed42
  status: awaiting_operator
```

C23 supersedes C22 only at the operator-wrapper layer. Preserve all C17–C22 scripts, target evidence, formal runs, checkpoints, transport telemetry, and recovery history unchanged. The control plane does not push, execute C23, or start any RTX 4090 workload.

## C24 — structured non-transport reward infrastructure recovery

C23 completed Public formal GRPO at global step 300, but Hidden failed after checkpoint-125 with four infrastructure-failure completions in one eight-completion reward batch. The first failure was a real executed Piston request; later rows were circuit-breaker fanout. Transport telemetry recorded no ambiguous, connect, safe-retry, or retry-exhaustion event. Root cause was therefore not HTTP transport replay: reward/verification correctly recognized `sandbox_error` as infrastructure failure, while retry-v1 classified retryability only through the transport-specific signature and did not recover structured non-transport Piston or harness failures.

Structured recovery source commit `3675bf55c339dbfe0d1c0c248418c6efdd0da170` preserves the consolidated subtype model: `piston_transport`, `piston_response_protocol`, `harness_protocol`, and `piston_internal` are payload-free retryable infrastructure classes. Invalid/malformed Piston responses, invalid harness reports/protocol failures, and supported Piston `XX` internal failures use those classes. Candidate `wrong_answer`, `syntax_error`, `runtime_error`, `timeout`, `memory_limit`, `output_limit`, `parse_error`, ordinary failed tests, non-`XX` compile-stage failures, and unclassified `sandbox_error` remain non-retryable. GRPO retry-v2 never classifies stderr text. It performs at most three semantic-layer retries of the identical code/function/tests/timeout/memory request after connection discard, exact Python 3.10.0 health validation, and 1/2/4-second backoff. It does not replay ambiguous POSTs in the HTTP transport, regenerate completion text, change RNG, enter optimizer update early, or use a wrapper restart loop.

The consolidated baseline already implemented retry-v2, v1/v2 attempt-history compatibility, structured canonical reward fields, operational `failure_kind`, and analysis compatibility. Final audit found two remaining source gaps. First, with `stop_on_first_failure=false`, a prior candidate failure could mask a later structured infrastructure failure in aggregate execution status, preventing GRPO retry. The final repair gives any per-test `sandbox_error` aggregate precedence while preserving ordinary candidate-failure ordering. Second, result-affecting Piston classification changed without a cache implementation-version bump; the final repair advances `PISTON_EXECUTOR_IMPLEMENTATION_VERSION` to `piston-executor-v2`. Scientific YAML, reward mathematics, model, optimizer, scheduler, dataset, seed, completed B parent, paired definition, Piston definition, and transport-policy identity remain unchanged.

C24 treats Public as immutable completed evidence. It performs strict identity/postcheck verification, records before/after artifact snapshots, and contains no Public `train-grpo` invocation. Hidden must already exist and is resumed only through production `_latest_valid_resume_checkpoint()` selection. At the current target state this is expected to select checkpoint-125 and validate canonical sidecar boundaries of 1000 `rollouts.jsonl`, 1000 `rewards.jsonl`, and 250 `group_metrics.jsonl` rows; selection is not hard-coded to step 125. Existing production resume logic archives the failed suffix and restores the selected sidecar boundary. Hidden resume explicitly preserves origin commit `47c7fb2a55b91e471aeca5ededf6e0233f4f93f9`, records an `operational_reward_resilience_v1` migration to the final repair source with `scientific_change=false`, and writes retry policy `grpo-reward-infra-retry-v2`. Historical v1 attempts remain unchanged and readable; the new attempt writes v2 metadata.

C24 creates a detached temporary worktree at the exact repair source commit, imports Python from that worktree, and keeps the formal command working directory at `/root/sj-tmp/open-r1-code-verifier`. It verifies immutable C17–C23 scripts, including C23 commit `d9829755dd1e7b2554fb9fcbc9f8268936f50d87` and script SHA256 `b9761d58fadb68f515a3b4972b5c90bd633ed123c037255d02a8dd2cf14456ca`. Target preflight remains fail-closed for Git lineage, script/report provenance, machine record, RTX 4090 VRAM, persistent roots, exact Piston runtime, storage, datasets, model/B identity, formal pair, and transport policy. Operator evidence remains secret-free and records real command/postcheck return codes; only both zero may produce `gate_status=passed`.

Control-plane validation before handoff:

- Focused structured recovery suite: 349 passed.
- Real Piston acceptance: 9 passed, 2 deselected, with zero failures/skips among selected tests.
- `make lint`: PASS; Ruff check/format and strict mypy passed.
- Full pytest: 1027 passed, 3 skipped.
- C24 `bash -n`: PASS; all 18 embedded Python heredocs compile; static provenance/source checks pass.
- C23 immutable commit and script SHA checks: PASS.
- C24 script SHA256: `8a6d0b37d037081390833f7fac4981501cff8d4ab9cbca2ae81d49a2abc33afb`.
- No C24 operator command or RTX 4090 workload was started by the control plane.

```yaml
execution_checkpoint:
  version: 1
  checkpoint_id: C24
  stage_id: WP7-c
  task_kind: repair
  source_plan_commit: 8464e69691c527c726a2e28e5a7ca81fa2001bbf
  result_code_commit: 3675bf55c339dbfe0d1c0c248418c6efdd0da170
  training_code_commit: 3675bf55c339dbfe0d1c0c248418c6efdd0da170
  checkpoint_code_commit: 47c7fb2a55b91e471aeca5ededf6e0233f4f93f9
  consolidated_baseline_commit: 1781a738ee8f9c6215a68b551350bf1df11e8172
  workflow_transport_commit: b4ac6acab60703c288a2e2e82e84398a11320177
  operator_gate_id: grpo-cd-formal
  operator_handoff_mode: portable_target
  operator_restart_policy: trainer_checkpoint
  operator_script: ai-work/executor/operator/WP7-c/grpo-cd-formal/C24/run.sh
  operator_script_sha256: 8a6d0b37d037081390833f7fac4981501cff8d4ab9cbca2ae81d49a2abc33afb
  formal_pair_sha256: 31f5464abf094d14cf86e8ef4dd909b8a1be559c8b4ca8b96473070a9f1daad9
  formal_public_config_sha256: e7353aecf28cf496def0a03f64a7ee8c739dc914e8df22a23e008bb72ef0e1e2
  formal_hidden_config_sha256: 951bef7fcd17694bac9d52e180290bcbb46b69f3756810c9402075b1d422a129
  formal_save_steps: 25
  piston_definition_sha256: f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e
  transport_policy_sha256: 0e0b85e0331840c9825cc6d4cb357e4d129e4906d945b85f80d532adecf655f3
  code_migration_class: operational_reward_resilience_v1
  reward_retry_policy_version: grpo-reward-infra-retry-v2
  reward_retry_max_retries: 3
  reward_retry_backoff_seconds: [1.0, 2.0, 4.0]
  public_action: strict_completed_verify_only
  hidden_action: production_latest_valid_checkpoint_resume
  hidden_expected_initial_checkpoint: production_latest_valid_expected_checkpoint-125
  hidden_checkpoint_125_expected_rewards: 1000
  hidden_checkpoint_125_expected_rollouts: 1000
  hidden_checkpoint_125_expected_group_metrics: 250
  accepted_historical_retry_policy_versions: [grpo-reward-infra-retry-v1, grpo-reward-infra-retry-v2]
  accepted_c13_operator_evidence_sha256: 91647fa09354f1dbaf486b7d94960934391467470665401022493ad5fb87d50b
  accepted_c13_postcheck_sha256: 91d4825b86a325a8f9765bfb9d99ab51345051c046c9847cfe335aadad487b2f
  supersedes_checkpoint_id: C23
  supersedes_checkpoint_commit: d9829755dd1e7b2554fb9fcbc9f8268936f50d87
  superseded_operator_script_sha256: b9761d58fadb68f515a3b4972b5c90bd633ed123c037255d02a8dd2cf14456ca
  supersession_reason: retry-v1 did not recover structured non-transport Piston and harness infrastructure failures
  target_status_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C24/status"
  target_log_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C24/terminal.log"
  target_evidence_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C24/operator-evidence.json"
  target_postcheck_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C24/postcheck-summary.json"
  expected_artifacts:
    - unchanged completed Public run verified at global_step 300 without Public training
    - completed Hidden run resumed from production-selected latest valid checkpoint to global_step 300
    - Hidden new attempt and migration bound to repair-v2 source and preserved repair-v1 origin
    - mixed historical v1/new v2 attempt metadata accepted without history rewrite
    - canonical reward streams without infrastructure_failure or sandbox_error rows
    - structured new reward rows with null infrastructure_failure_kind on normal outcomes
    - payload-free operational retry telemetry and versioned operator-evidence.json
  completed_scope:
    - control-plane structured recovery source repair and verification
    - immutable portable C24 operator handoff
  remaining_scope:
    - manual target execution and post-run evidence sync
  resume_allowed: true
  interruption_class: operator
  target_gpu: NVIDIA GeForce RTX 4090
  target_precision: bf16
  formal_public_run: C-public-grpo-formal-seed42
  formal_hidden_run: D-hidden-grpo-formal-seed42
  status: awaiting_operator
```

C24 supersedes C23 for formal operator execution. Preserve C17–C23 scripts, target evidence, Public completed artifacts, Hidden checkpoints, transport telemetry, and recovery history unchanged. Make the exact C24 checkpoint commit reachable on the RTX 4090, checkout it cleanly, verify the tracked script SHA256, then run C24 only by explicit human decision. The control plane does not push or execute C24.

## C25 — candidate result output-limit classification recovery

C24 was executed on the RTX 4090 from checkpoint commit `5230da43318a632b1c6b05140782db7a8b82472a` and failed while resuming Hidden from production-selected checkpoint-125. The target evidence is preserved exactly: status SHA256 `53c234e5e8472b6ac51c1ae1cab3fe06fad053beb8ebfd8977b010655bfdd3c3`, terminal log SHA256 `879ddd37660038bbaf9bffedb7e1e06f676c9fe8656e5f2e916b3042b9204be6`, and operator-evidence SHA256 `c5864659cf3751ddbf7b1de8162059232cca458dfc0afd7cb7fd518a41b812fa`. C24 recorded `command_rc=2`, `postcheck_rc=125`, `gate_status=command_failed`, no postcheck file, Public `verify-only`, and Hidden resume from checkpoint-125. Retry-v2 ran three bounded 1/2/4-second semantic retries for `kind=harness_protocol` and exhausted; transport telemetry still recorded zero connect failure, ambiguous failure, safe retry, transport retry exhaustion, or tunnel outage.

Target forensics showed that the real executed failure was completion item 4 for `leetcode-all-paths-from-source-to-target`; items 5–7 were circuit-breaker fanout with `executed=false`. The generated DFS duplicated every returned path by its path length. On the first Hidden test graph that deterministic bug expands to 714,066 paths containing about 6,652,872 integer slots, producing a compact JSON result of roughly 14.7 MB. The trusted child-result channel is bounded at 8 MiB. Before C25, exceeding that result-channel bound was mapped to `harness_error`, then to structured retryable `harness_protocol`, so the same deterministic candidate failure was retried three times and aborted the reward batch. This is not a Piston transport failure and not a malformed trusted harness protocol.

Source repair commit `31b997279ff4e908165b93187fc898922a059de4` directly follows immutable C24 checkpoint `5230da43318a632b1c6b05140782db7a8b82472a`. It changes only `src/code_verifier/execution/harness.py` plus three focused test files. Oversized candidate result packets now map to existing candidate-side `output_limit`; malformed/invalid child protocol remains `harness_error`, and genuine Piston/harness infrastructure failures retain structured retry-v2 handling. `PYTHON_HARNESS_PROTOCOL_VERSION` advances from `trusted-parent-v1` to `trusted-parent-v2`, so result-affecting executor/cache identity changes deterministically. Reward mathematics, scientific YAML, model, optimizer, scheduler, dataset, seed, formal pair, Piston definition, transport policy, and completed Public artifacts are unchanged.

Control-plane validation for the C25 source repair:

- Focused harness/Piston/GRPO retry suite: 109 passed.
- Real Piston acceptance: 9 passed, 2 deselected, with all selected tests passing.
- `make lint`: PASS; Ruff check/format and strict mypy passed.
- Full pytest: 1030 passed, 3 skipped; the skipped tests are the normal env-gated Piston cases already exercised explicitly above.
- `make test-gpu`: 3 passed on the control-plane GTX 1660 Ti smoke suite.
- C25 `bash -n`: PASS; all 19 embedded Python heredocs compile.
- C25 script SHA256: `cb68ff0c5dfc852810c6e6aff620093f0dd1ea7f4d759e9c5902607126551fae`.
- No C25 operator command, Hidden Trainer process, or RTX 4090 workload was started by the control plane.

C25 authenticates the failed C24 target artifacts by exact SHA before any new training action, requires the C24 postcheck to remain absent, and validates its failed run actions and retry-v2 identity. Public remains strict verify-only. Hidden must already exist and is resumed only through production `_latest_valid_resume_checkpoint()` selection; the current target state is expected to select checkpoint-125 without hard-coding that selection. Production resume archives the failed C24 suffix as the next recovery-history entry and restores the checkpoint canonical boundaries before attempt 3. The new attempt keeps top-level Hidden origin `47c7fb2a55b91e471aeca5ededf6e0233f4f93f9`, uses migration class `operational_reward_resilience_v1`, imports exact training code from a detached `31b997279ff4e908165b93187fc898922a059de4` worktree through `PYTHONPATH`, and starts one Trainer process. Postcheck accepts the historical v1 origin attempt, exactly one failed C24 retry-v2 attempt at `3675bf55c339dbfe0d1c0c248418c6efdd0da170` with counters 3 retry attempts / 0 successes / 1 exhaustion / 0 prepare failures, and the final C25 retry-v2 attempt; it requires canonical completed reward streams to contain no infrastructure or sandbox failures while allowing ordinary candidate `output_limit` results.

```yaml
execution_checkpoint:
  version: 1
  checkpoint_id: C25
  stage_id: WP7-c
  task_kind: repair
  source_plan_commit: 8464e69691c527c726a2e28e5a7ca81fa2001bbf
  result_code_commit: 31b997279ff4e908165b93187fc898922a059de4
  training_code_commit: 31b997279ff4e908165b93187fc898922a059de4
  checkpoint_code_commit: 47c7fb2a55b91e471aeca5ededf6e0233f4f93f9
  historical_repair_code_commit: 3675bf55c339dbfe0d1c0c248418c6efdd0da170
  consolidated_baseline_commit: 1781a738ee8f9c6215a68b551350bf1df11e8172
  workflow_transport_commit: b4ac6acab60703c288a2e2e82e84398a11320177
  operator_gate_id: grpo-cd-formal
  operator_handoff_mode: portable_target
  operator_restart_policy: trainer_checkpoint
  operator_script: ai-work/executor/operator/WP7-c/grpo-cd-formal/C25/run.sh
  operator_script_sha256: cb68ff0c5dfc852810c6e6aff620093f0dd1ea7f4d759e9c5902607126551fae
  formal_pair_sha256: 31f5464abf094d14cf86e8ef4dd909b8a1be559c8b4ca8b96473070a9f1daad9
  formal_public_config_sha256: e7353aecf28cf496def0a03f64a7ee8c739dc914e8df22a23e008bb72ef0e1e2
  formal_hidden_config_sha256: 951bef7fcd17694bac9d52e180290bcbb46b69f3756810c9402075b1d422a129
  formal_save_steps: 25
  piston_definition_sha256: f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e
  transport_policy_sha256: 0e0b85e0331840c9825cc6d4cb357e4d129e4906d945b85f80d532adecf655f3
  harness_protocol_version: trusted-parent-v2
  code_migration_class: operational_reward_resilience_v1
  reward_retry_policy_version: grpo-reward-infra-retry-v2
  reward_retry_max_retries: 3
  reward_retry_backoff_seconds: [1.0, 2.0, 4.0]
  public_action: strict_completed_verify_only
  hidden_action: production_latest_valid_checkpoint_resume
  hidden_expected_initial_checkpoint: production_latest_valid_expected_checkpoint-125
  hidden_checkpoint_125_expected_rewards: 1000
  hidden_checkpoint_125_expected_rollouts: 1000
  hidden_checkpoint_125_expected_group_metrics: 250
  accepted_historical_retry_policy_versions: [grpo-reward-infra-retry-v1, grpo-reward-infra-retry-v2]
  accepted_c13_operator_evidence_sha256: 91647fa09354f1dbaf486b7d94960934391467470665401022493ad5fb87d50b
  accepted_c13_postcheck_sha256: 91d4825b86a325a8f9765bfb9d99ab51345051c046c9847cfe335aadad487b2f
  accepted_c24_status_sha256: 53c234e5e8472b6ac51c1ae1cab3fe06fad053beb8ebfd8977b010655bfdd3c3
  accepted_c24_terminal_log_sha256: 879ddd37660038bbaf9bffedb7e1e06f676c9fe8656e5f2e916b3042b9204be6
  accepted_c24_operator_evidence_sha256: c5864659cf3751ddbf7b1de8162059232cca458dfc0afd7cb7fd518a41b812fa
  accepted_c24_postcheck: absent
  supersedes_checkpoint_id: C24
  supersedes_checkpoint_commit: 5230da43318a632b1c6b05140782db7a8b82472a
  superseded_operator_script_sha256: 8a6d0b37d037081390833f7fac4981501cff8d4ab9cbca2ae81d49a2abc33afb
  supersession_reason: deterministic oversized candidate return was misclassified as retryable harness_protocol instead of candidate output_limit
  target_status_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C25/status"
  target_log_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C25/terminal.log"
  target_evidence_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C25/operator-evidence.json"
  target_postcheck_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-formal/C25/postcheck-summary.json"
  expected_artifacts:
    - unchanged completed Public run verified at global_step 300 without Public training
    - completed Hidden run resumed from production-selected latest valid checkpoint to global_step 300
    - preserved failed C24 attempt/evidence plus append-only C25 attempt and recovery-history archive
    - mixed historical retry-v1 and retry-v2 attempt metadata accepted without history rewrite
    - canonical reward streams without infrastructure_failure or sandbox_error rows
    - oversized candidate results represented as non-infrastructure output_limit when encountered
    - structured new reward rows with null infrastructure_failure_kind on ordinary candidate outcomes
    - payload-free operational retry telemetry and versioned operator-evidence.json
  completed_scope:
    - control-plane candidate result output-limit source repair and verification
    - immutable portable C25 operator handoff
  remaining_scope:
    - manual target execution and post-run evidence sync
  resume_allowed: true
  interruption_class: operator
  target_gpu: NVIDIA GeForce RTX 4090
  target_precision: bf16
  formal_public_run: C-public-grpo-formal-seed42
  formal_hidden_run: D-hidden-grpo-formal-seed42
  status: awaiting_operator
```

C25 supersedes C24 only for the next formal operator execution. Preserve C17–C24 scripts, target evidence, Public completed artifacts, Hidden checkpoints, C24 failed attempt/recovery evidence, transport telemetry, and recovery history unchanged. The control plane does not push or execute C25.

## C26 — reconciled C25 acceptance and deterministic C/D generation handoff

The user completed C25 manually on the RTX 4090 and pulled the resulting evidence back to the GTX 1660 Ti. The explicit control-plane receive root is `/home/dzy/wp7c-operator-evidence/WP7-c/grpo-cd-formal/C25`. The four authoritative operator files were recomputed byte-for-byte on the control plane and match the target evidence exactly: status SHA256 `9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa`, terminal log SHA256 `b08930b7c7a984816cb9ccb69fbfb031aa88d07768852f5fd9914297e5aa4234`, operator-evidence SHA256 `0fe7f376fb94918f5e5aee1c28bcc0ac159687fefd9600509efb35773ca2df9e`, and postcheck SHA256 `c41e17a3a22b1e3c54de006c058165e32c0774c2d50581844194906c75b46a63`. The synced Public/Hidden top-level formal metadata/telemetry files were also rehashed against the C25 evidence inventory; all 14 checked files matched their target hashes.

C25 records `command_rc=0`, `postcheck_rc=0`, `gate_status=passed`, RTX 4090 with 22683 MiB VRAM, Public strict verify-only with an unchanged before/after snapshot and no Public `train-grpo` invocation, Hidden production resume from checkpoint-125 to completed global step 300, and `generation_started=false`. The completed Public/Hidden runs retain formal pair SHA256 `31f5464abf094d14cf86e8ef4dd909b8a1be559c8b4ca8b96473070a9f1daad9`; the final Hidden canonical reward stream contains no infrastructure/sandbox rows, while the previously fatal `leetcode-all-paths-from-source-to-target` oversized candidate is represented as ordinary non-infrastructure `output_limit`. No C/D optimizer rerun is justified or permitted by this handoff.

The raw C25 checkpoint predates the current strict operator-checkpoint source-provenance schema: it records `task_kind=repair` although WP7-c has no committed review, omits `source_review_round/source_review_commit/repair_issue_ids`, and omits `control_plane_evidence_receive_dir`. The historical checkpoint is not rewritten. Instead, workflow-maintenance commit `657030c47a29411e343049926de10730858104a8` adds `operator_checkpoint_reconciliation.version=1`, restricted to an already-executed current-HEAD portable-target checkpoint whose only defects are those schema-migration fields and whose successful target evidence can be independently authenticated. Under that contract C25 raw task kind `repair` is effective implementation provenance with `source_review_round=null`, `source_review_commit=null`, and `repair_issue_ids=[]`; the explicit receive root above and the exact C25 evidence SHA remain reviewable audit fields. The maintenance runtime is separate from the WP7-c branch and is not merged into this stage.

Control-plane acceptance before C26 creation also revalidated the stage-local environment and zero-tracked `.ai-bridge`, ran the staged generation/evaluation-focused suite (`14 passed`), and recomputed the formal test split as exactly 400 rows with dataset SHA256 `770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae` and ordered problem-IDs SHA256 `2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9`. The new C26 script is generation-only: it authenticates C25 and the completed C/D sources, binds the exact Base evaluation/Piston definition/model/Open-R1/dependency identities, allows exact-prefix resume, quarantines only incompatible incomplete generation bundles, fails closed on any mismatched completed bundle, generates C then D, strictly postchecks two 400-row bundles, and finally performs a `resumed=400, generated=0` readback for each. Static validation passed `bash -n`, all 13 embedded Python heredocs compile, `make lint` passed Ruff check/format plus strict mypy, and the script contains no `train-grpo`, `PistonExecutor`, SSH/tunnel, or curl invocation. The control plane did not start C26 or any RTX 4090 workload.

```yaml
execution_checkpoint:
  version: 1
  checkpoint_id: C26
  stage_id: WP7-c
  task_kind: implementation
  source_plan_commit: 8464e69691c527c726a2e28e5a7ca81fa2001bbf
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: e0ec354790d42753c8170625adea4d5e28fe4325
  workflow_runtime_commit: 657030c47a29411e343049926de10730858104a8
  operator_checkpoint_reconciliation_version: 1
  reconciled_checkpoint_id: C25
  reconciled_checkpoint_commit: e0ec354790d42753c8170625adea4d5e28fe4325
  reconciled_checkpoint_task_kind_raw: repair
  reconciled_checkpoint_task_kind_effective: implementation
  reconciled_control_plane_evidence_receive_dir: /home/dzy/wp7c-operator-evidence/WP7-c/grpo-cd-formal/C25
  accepted_c25_status_sha256: 9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa
  accepted_c25_terminal_log_sha256: b08930b7c7a984816cb9ccb69fbfb031aa88d07768852f5fd9914297e5aa4234
  accepted_c25_operator_evidence_sha256: 0fe7f376fb94918f5e5aee1c28bcc0ac159687fefd9600509efb35773ca2df9e
  accepted_c25_postcheck_sha256: c41e17a3a22b1e3c54de006c058165e32c0774c2d50581844194906c75b46a63
  operator_gate_id: grpo-cd-generate-eval
  operator_handoff_mode: portable_target
  operator_restart_policy: exact_rerun
  operator_script: ai-work/executor/operator/WP7-c/grpo-cd-generate-eval/C26/run.sh
  operator_script_sha256: f1fb281c0aef9ca237584b99374033a58a68fa75adc26ffbf1cdc111ae3f1565
  control_plane_evidence_receive_dir: /home/dzy/wp7c-operator-evidence/WP7-c/grpo-cd-generate-eval/C26
  target_status_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-generate-eval/C26/status"
  target_log_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-generate-eval/C26/terminal.log"
  target_evidence_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-generate-eval/C26/operator-evidence.json"
  target_postcheck_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-generate-eval/C26/postcheck-summary.json"
  formal_pair_sha256: 31f5464abf094d14cf86e8ef4dd909b8a1be559c8b4ca8b96473070a9f1daad9
  evaluation_dataset_sha256: 770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae
  ordered_problem_ids_sha256: 2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9
  piston_definition_sha256: f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e
  base_eval_config_sha256: 3fa1b8f0dbc6853c894ac9f02b6820afd838ff68ca9f090ecbbef4ae495dbac3
  public_generation_run: C-public-grpo-formal-seed42
  hidden_generation_run: D-hidden-grpo-formal-seed42
  expected_artifacts:
    - completed C-public-grpo-formal-seed42 generation bundle with exactly 400 unique ordered rows
    - completed D-hidden-grpo-formal-seed42 generation bundle with exactly 400 unique ordered rows
    - exact dataset/order/seed/deterministic-decode/Piston-definition/model/GRPO-checkpoint/pair/project/Open-R1/dependency identities
    - strict C and D quick readback with resumed=400 and generated=0 without bundle mutation
    - generation-only execution with no Piston verification and no GRPO training
    - versioned operator-evidence.json and postcheck-summary.json with full generation artifact inventory
  completed_scope:
    - C25 formal gate accepted through reconciliation v1 using exact synced target evidence; no C/D retraining
    - control-plane staged-evaluation regression and formal 400-row dataset/order identity revalidation
    - immutable portable C26 generation operator handoff
  remaining_scope:
    - user manually runs C26 on the RTX 4090; C and D generation only
    - sync complete C/D generation bundles plus C26 evidence byte-for-byte to the recorded 1660 Ti receive directory
    - run real local Piston verify-eval and aggregate-eval for C/D, 400 rows each, on the GTX 1660 Ti
    - write the completed WP7-c implementation execution record E0 and stop for a fresh independent reviewer conversation
  resume_allowed: true
  interruption_class: operator
  target_gpu: NVIDIA GeForce RTX 4090
  target_precision: fp16
  status: awaiting_operator
```

C26 is the only next target-GPU gate. It consumes the already-completed C/D formal adapters and must not rerun Public or Hidden GRPO. Make the exact C26 checkpoint commit reachable on the RTX 4090, checkout it cleanly, verify the tracked script SHA256, and run C26 only by explicit human decision. The control plane does not push, start, or monitor C26.

## C27 — supersede pre-generation C26 shell-local failure

The operator started C26 manually on the RTX 4090. Read-only target inspection shows the attempt reached the completed source/preparation preflight and recorded `generation actions public=fresh hidden=fresh`, then exited at C26 `run.sh` line 688 before the first `code-verifier generate-eval` invocation because `set -u` expanded `$label` inside the same `local` declaration that was assigning `label`. C26 terminal log SHA256 is `28b31446fee864dab14ed9dd73d83831b1679d86c8117b93e01a3570bdab0c80`. The C26 operator directory contains only `run.lock` and `terminal.log`; there is no `status`, `operator-evidence.json`, or `postcheck-summary.json`. At diagnosis time the target generation root contained only the prior B bundle and no C/D generation directories, so no C/D generation row had been created or overwritten by C26.

C27 preserves C26 unchanged and fixes both instances of the same shell bug: `run_generate()` and `readback_one()` now assign `run_name/grpo_run/label` first and derive `out_file` in a separate `local` statement. C27 additionally authenticates the immutable C26 failure log/script before generation. `bash -n` passes, all 14 embedded Python heredocs compile, and a `bash -u` focused declaration check resolves `/tmp/public.generate.stdout` without an unbound variable. C27 remains generation-only and does not add GRPO training or live Piston execution.

```yaml
execution_checkpoint:
  version: 1
  checkpoint_id: C27
  stage_id: WP7-c
  task_kind: implementation
  source_plan_commit: 8464e69691c527c726a2e28e5a7ca81fa2001bbf
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: d53a18cd951a3cab7e5571f95b3b508b61878b2d
  workflow_runtime_commit: 657030c47a29411e343049926de10730858104a8
  operator_checkpoint_reconciliation_version: 1
  reconciled_checkpoint_id: C25
  reconciled_checkpoint_commit: e0ec354790d42753c8170625adea4d5e28fe4325
  reconciled_checkpoint_task_kind_raw: repair
  reconciled_checkpoint_task_kind_effective: implementation
  reconciled_control_plane_evidence_receive_dir: /home/dzy/wp7c-operator-evidence/WP7-c/grpo-cd-formal/C25
  accepted_c25_operator_evidence_sha256: 0fe7f376fb94918f5e5aee1c28bcc0ac159687fefd9600509efb35773ca2df9e
  accepted_c25_postcheck_sha256: c41e17a3a22b1e3c54de006c058165e32c0774c2d50581844194906c75b46a63
  operator_gate_id: grpo-cd-generate-eval
  operator_handoff_mode: portable_target
  operator_restart_policy: exact_rerun
  operator_script: ai-work/executor/operator/WP7-c/grpo-cd-generate-eval/C27/run.sh
  operator_script_sha256: e03bae85798260d2e5dfe4fb515bf7f703dc47f09deae57c67a3c8ac6f164926
  control_plane_evidence_receive_dir: /home/dzy/wp7c-operator-evidence/WP7-c/grpo-cd-generate-eval/C27
  supersedes_checkpoint_commit: d53a18cd951a3cab7e5571f95b3b508b61878b2d
  superseded_operator_script_sha256: f1fb281c0aef9ca237584b99374033a58a68fa75adc26ffbf1cdc111ae3f1565
  superseded_terminal_log_sha256: 28b31446fee864dab14ed9dd73d83831b1679d86c8117b93e01a3570bdab0c80
  supersession_reason: C26 same-local-declaration expansion of label failed under set -u before generation dispatch
  target_status_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-generate-eval/C27/status"
  target_log_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-generate-eval/C27/terminal.log"
  target_evidence_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-generate-eval/C27/operator-evidence.json"
  target_postcheck_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-generate-eval/C27/postcheck-summary.json"
  formal_pair_sha256: 31f5464abf094d14cf86e8ef4dd909b8a1be559c8b4ca8b96473070a9f1daad9
  evaluation_dataset_sha256: 770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae
  ordered_problem_ids_sha256: 2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9
  piston_definition_sha256: f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e
  expected_artifacts:
    - completed C-public-grpo-formal-seed42 generation bundle with exactly 400 unique ordered rows
    - completed D-hidden-grpo-formal-seed42 generation bundle with exactly 400 unique ordered rows
    - strict C and D quick readback with resumed=400 and generated=0 without bundle mutation
    - generation-only execution with no Piston verification and no GRPO training
    - versioned C27 operator-evidence.json and postcheck-summary.json
  completed_scope:
    - C25 formal gate remains accepted through reconciliation v1; no C/D retraining
    - C26 pre-generation shell failure authenticated and preserved without generation output
    - both same-declaration label expansion defects fixed in immutable C27 operator script
    - immutable portable C27 generation operator handoff
  remaining_scope:
    - user manually runs C27 on the RTX 4090; C and D generation only
    - sync complete C/D generation bundles plus C27 evidence byte-for-byte to the recorded 1660 Ti receive directory
    - run real local Piston verify-eval and aggregate-eval for C/D, 400 rows each, on the GTX 1660 Ti
    - write the completed WP7-c implementation execution record E0 and stop for a fresh independent reviewer conversation
  resume_allowed: true
  interruption_class: operator
  target_gpu: NVIDIA GeForce RTX 4090
  target_precision: fp16
  status: awaiting_operator
```

C27 supersedes C26 only for the generation gate. C26 remains immutable failed historical evidence. The control plane does not push, start, or monitor C27.

## E0 — completed WP7-c implementation after C27 generation resume

The C27 target generation evidence and both synchronized 400-row generation bundles were independently revalidated byte-for-byte on the GTX 1660 Ti control plane before any verification was started. The received C27 operator evidence SHA256 is `4e2912a57b7fa5f1a3864db3e2bf938026357f4808bc85ae513042dca677a098`; postcheck SHA256 is `dc014c76b6bfb73fb6d30de8ddd13865309f1cd148c3eb8bd03cdab332807745`; terminal log SHA256 is `e80c71e40dca99aa79b6bab01ab8e8c84a331fa2d55d07e38d649dfc1fe11732`. Evidence binds checkpoint `0e2a894943cfb623610e937380342d148ad8cff0`, result code `d53a18cd951a3cab7e5571f95b3b508b61878b2d`, workflow runtime `657030c47a29411e343049926de10730858104a8`, and tracked script SHA256 `e03bae85798260d2e5dfe4fb515bf7f703dc47f09deae57c67a3c8ac6f164926`, with `command_rc=0`, `postcheck_rc=0`, `gate_status=passed`, generation-only execution, no target Piston verification, and strict C/D 400-row generation readback at `resumed=400, generated=0`.

Every C27 expected generation artifact was rehashed against `operator-evidence.json`. Public generation records SHA256 is `a5d841f625fe1d3126e858f8c12081babb7a7739c84667a715e175bfbef07357`; Hidden generation records SHA256 is `f84c2ab7037c3ec297b1786171c0272f782f98b22ca1d8a81e6bb02eb384bfd0`. Both generation bundles are completed at 400 rows, bind `project_commit=0e2a894943cfb623610e937380342d148ad8cff0`, evaluation dataset SHA256 `770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae`, ordered problem IDs SHA256 `2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9`, formal pair SHA256 `31f5464abf094d14cf86e8ef4dd909b8a1be559c8b4ca8b96473070a9f1daad9`, Piston definition SHA256 `f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e`, seed 42, the exact frozen model/Open-R1/dependency identities, and their respective independent formal GRPO checkpoint identities.

A fresh external control-plane result root `/home/dzy/wp7c-verified` was used for real local-Piston evaluation; no verification artifact was written into the stage worktree. `configs/execution/piston-local.yaml` rehashed to the sealed Piston definition and real runtime acceptance passed 9 selected tests with zero selected skips/failures. Public and Hidden `verify-eval` each processed all 400 generated completions through local Piston with four workers (`resumed=0, verified=400`), followed by strict readback (`resumed=400, verified=0`). Both result streams have 400 unique problem IDs in the exact sealed order, zero `sandbox_error` rows, zero sandbox-error failure counts, and no infrastructure-failure field occurrence. Public verification results SHA256 is `7c5bb7497389872ee55ec67c4cb73cb188b68f0da06750013f1bd7a734cbb913`; Hidden is `004d5655b438244a729acd0b2b1fe33aed8ae5e8758fe462ac7215d1f54d12c5`.

`aggregate-eval` then completed independently for both 400-row runs. Public summary SHA256 is `6cc3fa7b785f01aef55e6a13e082266385ea01a77950a36ffaf1e7285e25480c` and `main_results.csv` SHA256 is `c39c75737cf9e4befd43e782d1bfe1f59e1aa8b8a932cb4d5bb341d39fafafc8`; Hidden summary SHA256 is `f63a20181f2f560ffdf1b6bdcb385f6dbbf83f1a05b5592013315ff401a2273d` and `main_results.csv` SHA256 is `8da0439242fdb15274b4300fb17ebc813eb692cdbc220f3ebc70c5919cff0dcf`. Public aggregate metrics include visible pass@1 `0.3625`, train-hidden pass@1 `0.34`, eval-hidden pass@1 `0.375`, and eval-hidden average test pass rate `0.44875`; Hidden records the same three pass@1 values and eval-hidden average test pass rate `0.45125`. All persisted aggregate numeric values are finite and each summary traces to 400 rows, the exact C/D checkpoint, project commit, dataset, dependency, model and seed identities.

Final executor-owned acceptance on the current stage HEAD passed: `make lint`; `make test` with 1030 passed / 3 expected env-gated Piston skips / 0 failed; `make test-gpu` with 3/3 passed; and real `make test-piston PISTON_CONFIG=configs/execution/piston-local.yaml` with 9 selected passed / 2 deselected / 0 selected skipped or failed. `.ai-bridge/**` remains untracked, no C/D training or 4090 generation was repeated, no historical C25/C26/C27 checkpoint was modified, and no push/review/finalize/merge was performed.

```yaml
execution_record:
  version: 1
  stage_id: WP7-c
  execution_id: E0
  task_kind: implementation
  source_plan_commit: 8464e69691c527c726a2e28e5a7ca81fa2001bbf
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: 0e2a894943cfb623610e937380342d148ad8cff0
  execution_backend: web_codexpro
  effective_execution_mode: single
  workflow_runtime_commit: 657030c47a29411e343049926de10730858104a8
  operator_checkpoint_reconciliation_version: 1
  reconciled_checkpoint_id: C25
  reconciled_checkpoint_commit: e0ec354790d42753c8170625adea4d5e28fe4325
  reconciled_checkpoint_task_kind_raw: repair
  reconciled_checkpoint_task_kind_effective: implementation
  reconciled_control_plane_evidence_receive_dir: /home/dzy/wp7c-operator-evidence/WP7-c/grpo-cd-formal/C25
  accepted_c25_operator_evidence_sha256: 0fe7f376fb94918f5e5aee1c28bcc0ac159687fefd9600509efb35773ca2df9e
  accepted_c25_postcheck_sha256: c41e17a3a22b1e3c54de006c058165e32c0774c2d50581844194906c75b46a63
  resumed_from_checkpoint_id: C27
  resumed_from_checkpoint_commit: 0e2a894943cfb623610e937380342d148ad8cff0
  operator_gate_id: grpo-cd-generate-eval
  operator_handoff_mode: portable_target
  operator_restart_policy: exact_rerun
  operator_evidence_sha256: 4e2912a57b7fa5f1a3864db3e2bf938026357f4808bc85ae513042dca677a098
  operator_postcheck_sha256: dc014c76b6bfb73fb6d30de8ddd13865309f1cd148c3eb8bd03cdab332807745
  operator_terminal_log_sha256: e80c71e40dca99aa79b6bab01ab8e8c84a331fa2d55d07e38d649dfc1fe11732
  superseded_checkpoint_id: C26
  superseded_checkpoint_commit: d53a18cd951a3cab7e5571f95b3b508b61878b2d
  superseded_operator_script_sha256: f1fb281c0aef9ca237584b99374033a58a68fa75adc26ffbf1cdc111ae3f1565
  superseded_terminal_log_sha256: 28b31446fee864dab14ed9dd73d83831b1679d86c8117b93e01a3570bdab0c80
  superseded_generation_started: false
  evaluation_dataset_sha256: 770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae
  ordered_problem_ids_sha256: 2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9
  formal_pair_sha256: 31f5464abf094d14cf86e8ef4dd909b8a1be559c8b4ca8b96473070a9f1daad9
  piston_definition_sha256: f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e
  public_generation_run_sha256: 0d081a3aded9eda7c3f12f40536f31016d2b9255054f9c5d4f4f8ab998e2f623
  public_generation_records_sha256: a5d841f625fe1d3126e858f8c12081babb7a7739c84667a715e175bfbef07357
  hidden_generation_run_sha256: 644fbd3abac1ff58884d1820feb93079e81cde0df542f64d5139a966a8ab3d27
  hidden_generation_records_sha256: f84c2ab7037c3ec297b1786171c0272f782f98b22ca1d8a81e6bb02eb384bfd0
  control_plane_verification_root: /home/dzy/wp7c-verified
  public_verification_run_sha256: bf777fc62d40249c86b4a17c92e39a06fe784688238a336faf109dfbc2b82bb2
  public_verification_results_sha256: 7c5bb7497389872ee55ec67c4cb73cb188b68f0da06750013f1bd7a734cbb913
  public_verification_rows: 400
  public_verification_readback_resumed: 400
  public_verification_readback_verified: 0
  public_sandbox_error_rows: 0
  public_infrastructure_failure_rows: 0
  hidden_verification_run_sha256: 5d6cc0a8a08efaf1f8cea927190531a3a5ff0decdc4531cd49e7d1f6375d03ba
  hidden_verification_results_sha256: 004d5655b438244a729acd0b2b1fe33aed8ae5e8758fe462ac7215d1f54d12c5
  hidden_verification_rows: 400
  hidden_verification_readback_resumed: 400
  hidden_verification_readback_verified: 0
  hidden_sandbox_error_rows: 0
  hidden_infrastructure_failure_rows: 0
  public_aggregate_summary_sha256: 6cc3fa7b785f01aef55e6a13e082266385ea01a77950a36ffaf1e7285e25480c
  public_aggregate_main_results_sha256: c39c75737cf9e4befd43e782d1bfe1f59e1aa8b8a932cb4d5bb341d39fafafc8
  hidden_aggregate_summary_sha256: f63a20181f2f560ffdf1b6bdcb385f6dbbf83f1a05b5592013315ff401a2273d
  hidden_aggregate_main_results_sha256: 8da0439242fdb15274b4300fb17ebc813eb692cdbc220f3ebc70c5919cff0dcf
  evidence_class: real-training/numerical
  status: completed
```

E0 closes only routed execution. Independent review remains a separate lifecycle boundary and is not performed in this execution conversation.

## C28 — review-r1 sealed-cadence pilot repair handoff

Review round 1 dispatches `R1-B1` and `R1-M1` as one difficult-serial repair. Repair code commit `f84556e801415374bf85f57bb65c1e09ddf9a5dc` restores only the sealed pilot/formal `save_steps=50` cadence plus matching test assertions. Model, optimizer, scheduler, reward mathematics, datasets, formal B, seed, Piston definition, Open-R1 and dependency identities are unchanged. Control-plane acceptance passed: focused baseline 176 tests, repaired-cadence 91 tests, `make lint`, full pytest 1030 passed / 3 expected skips, GPU 3/3, and real Piston 9 selected passed.

C28 preserves historical target artifacts. The repaired pilot keeps the sealed run names but writes under fresh namespace `$CODE_VERIFIER_ARTIFACT_ROOT/repair/WP7-c/R1/grpo-validation/pilot`; existing historical pilot/formal runs are neither overwritten nor accepted as this repair. The certified repaired pilot pair SHA256 is `b889cf144b787854c73a6b97c9a26d1a0378dee9ba1e822b965c1ef85c637be2`, with Public/Hidden paired-config SHA256 `e288b89419ea0aa2a780cf03b6ed72921d4f6395e4feaf5169e2db2dcb57100c` / `97ee2444a5a3e6709f9347d606f391d0b6ec3b380d3ce74e230b972631958b07`. The target script validates the existing reverse-forward Piston endpoint but does not start the legacy 4090-side tunnel helper.

```yaml
execution_checkpoint:
  version: 1
  checkpoint_id: C28
  stage_id: WP7-c
  task_kind: repair
  source_plan_commit: 8464e69691c527c726a2e28e5a7ca81fa2001bbf
  source_review_round: 1
  source_review_commit: deebfa0f02097a0593674aaa88d1f673427ab19e
  repair_issue_ids: [R1-B1, R1-M1]
  result_code_commit: f84556e801415374bf85f57bb65c1e09ddf9a5dc
  workflow_runtime_commit: 657030c47a29411e343049926de10730858104a8
  execution_backend: web_codexpro
  effective_execution_mode: single
  operator_gate_id: grpo-cd-pilot
  operator_handoff_mode: portable_target
  operator_restart_policy: trainer_checkpoint
  operator_script: ai-work/executor/operator/WP7-c/grpo-cd-pilot/C28/run.sh
  operator_script_sha256: ce55751b0c67800a18db4cc15fcebf6ace1d3a73455709641d50367ce811f749
  control_plane_evidence_receive_dir: /home/dzy/wp7c-operator-evidence/WP7-c/grpo-cd-pilot/C28
  target_status_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-pilot/C28/status"
  target_log_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-pilot/C28/terminal.log"
  target_evidence_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-pilot/C28/operator-evidence.json"
  target_postcheck_file_template: "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-pilot/C28/postcheck-summary.json"
  repair_artifact_namespace_template: "$CODE_VERIFIER_ARTIFACT_ROOT/repair/WP7-c/R1"
  prior_operator_checkpoint_id: C5
  prior_operator_checkpoint_commit: ae429f2dc0ed7353d5a3de0adb0d71b58a879a3d
  accepted_prior_operator_evidence_sha256: f1e3b350d11a4af13118a2517bbbbfb95df752b6cded126c80492ba40b163a5e
  accepted_prior_postcheck_sha256: 94b052e9c14f4842b45c35c2ce0d9f108cd6e382ff99e50293544b83039c2b8a
  accepted_prior_pair_sha256: b0aa34f56a3453687301edfc327fd26e5f1318839d77c8f4a5a8e508b435f49d
  repaired_pilot_pair_sha256: b889cf144b787854c73a6b97c9a26d1a0378dee9ba1e822b965c1ef85c637be2
  repaired_pilot_public_config_sha256: e288b89419ea0aa2a780cf03b6ed72921d4f6395e4feaf5169e2db2dcb57100c
  repaired_pilot_hidden_config_sha256: 97ee2444a5a3e6709f9347d606f391d0b6ec3b380d3ce74e230b972631958b07
  piston_definition_sha256: f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e
  expected_artifacts:
    - "$CODE_VERIFIER_ARTIFACT_ROOT/repair/WP7-c/R1/grpo-validation/pilot/C-public-grpo-pilot100-seed42/run.json"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/repair/WP7-c/R1/grpo-validation/pilot/C-public-grpo-pilot100-seed42/checkpoints/checkpoint-50/trainer_state.json"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/repair/WP7-c/R1/grpo-validation/pilot/C-public-grpo-pilot100-seed42/checkpoints/checkpoint-100/trainer_state.json"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/repair/WP7-c/R1/grpo-validation/pilot/C-public-grpo-pilot100-seed42/checkpoints/adapter_model.safetensors"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/repair/WP7-c/R1/grpo-validation/pilot/D-hidden-grpo-pilot100-seed42/run.json"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/repair/WP7-c/R1/grpo-validation/pilot/D-hidden-grpo-pilot100-seed42/checkpoints/checkpoint-50/trainer_state.json"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/repair/WP7-c/R1/grpo-validation/pilot/D-hidden-grpo-pilot100-seed42/checkpoints/checkpoint-100/trainer_state.json"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/repair/WP7-c/R1/grpo-validation/pilot/D-hidden-grpo-pilot100-seed42/checkpoints/adapter_model.safetensors"
    - "$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP7-c/8464e69691c527c726a2e28e5a7ca81fa2001bbf/grpo-cd-pilot/C28/postcheck-summary.json"
  completed_scope:
    - R1-M1 control-plane repair restored sealed pilot/formal save_steps=50 and passed focused/global acceptance
    - R1-B1 repair protocol requires a fresh final C/D pair under one exact tracked code identity; historical formal evidence remains immutable
    - fresh non-overwriting repair target namespace selected
    - immutable portable C28 paired-pilot handoff prepared
  remaining_scope:
    - user manually runs C28 on RTX 4090; paired 100-step C/D pilot only in the repair namespace
    - sync C28 evidence/postcheck and required pilot metadata byte-for-byte to the recorded 1660 Ti receive directory
    - resume through execution-router backend=web and validate pilot identities/telemetry and hard stop conditions
    - create and manually execute fresh 300-step formal C/D under one exact tracked checkpoint commit with save_steps=50
    - regenerate both 400-row bundles, rerun real 1660 Ti Piston verification/aggregation, then write completed repair E1
  resume_allowed: true
  interruption_class: operator
  target_gpu: NVIDIA GeForce RTX 4090
  target_precision: bf16
  status: awaiting_operator
```

C28 is the only next target-GPU action for review round 1. The Web executor does not push, execute, or monitor C28.

## E1 — post-hoc A1 preserved-evidence equivalence repair

The user explicitly declined a new RTX 4090 C/D rerun and authorized validation protocol amendment A1. A1 is committed at `72e12971a277f186663e102338096e14db55f6b1`, directly after the unexecuted C28 checkpoint `f6336c7fa22c74a94955ea529f5333a89bc1d8ee`, and is implemented by clean workflow runtime `c18925ae7b953e0f7022bb7c2a15c0a630258b83`. The original sealed plan and R1 review remain byte-for-byte historical artifacts: A1 is explicitly `post_hoc: true`, does not claim original-plan compliance, and only replaces R1-B1/R1-M1's exact-whole-run-code-identity and checkpoint-save-cadence rerun requirements with preserved-evidence operational-equivalence acceptance. A1 SHA256 is `aeb5f660af1662b961994276b10fa3f75b194d2b5c82b478915fa5e68bd7f3d5`. C28 remains immutable and was not executed: its recorded control-plane receive directory `/home/dzy/wp7c-operator-evidence/WP7-c/grpo-cd-pilot/C28` did not exist at amendment/execution preflight, and its script remains SHA256 `ce55751b0c67800a18db4cc15fcebf6ace1d3a73455709641d50367ce811f749`.

### R1-M1 — checkpoint cadence accepted as operational persistence

The historical C13 pilot evidence was independently reopened rather than inferred from E0 prose. C13 operator evidence/postcheck rehash to `91647fa09354f1dbaf486b7d94960934391467470665401022493ad5fb87d50b` / `91d4825b86a325a8f9765bfb9d99ab51345051c046c9847cfe335aadad487b2f`. Public/Hidden pilot run metadata rehash to `921be22bd58ea17377404e286e872acd24a125cde36790026d9291401fc58fe1` / `4b491b482b8d268403eef96cd4d2c78e085d67bf3754e43cb23ad774a01f46d4`; both are real completed step-100 runs with seed 42, 800 canonical reward rows, 200 group rows, zero canonical infrastructure/sandbox rows and the same pilot paired-definition SHA256 `bb8a733b2f6b9519d6e9c9de087461a975ba830f6c132a8f06120881576b512f`. Their resolved historical cadence is preserved as `save_steps=10`; it is not rewritten to 50.

The C25 formal Public/Hidden resolved configs rehash to `01c333536fe7984c7c67edcd744da64c901800a3850627ee060c00db14d898fe` / `8e65daa05d2d5a4e7297730c1c7ab535632aeb1d0359e8d620f4c7f9943bd178`. They both preserve `max_steps=300`, seed 42, beta 0.01, learning rate 5e-6, cosine scheduler, warmup 0.05, gradient accumulation 8, num_generations 4, the same LoRA 16/32/0.05 settings, generation limits and BF16 policy; the historical cadence is `save_steps=25`. Public/Hidden differ only in the intended data/reward-mode/run identity dimensions. Current tracked future-run configs remain restored to `save_steps=50`; A1 accepts the already-completed 10/25 cadence only as persistence/recovery frequency and does not retroactively assert it matched the sealed plan.

### R1-B1 — actual-path code-migration equivalence

The C25 target evidence rehashes exactly to operator evidence `0fe7f376fb94918f5e5aee1c28bcc0ac159687fefd9600509efb35773ca2df9e` and postcheck `c41e17a3a22b1e3c54de006c058165e32c0774c2d50581844194906c75b46a63`. Every synchronized formal metadata/telemetry file checked byte-for-byte against C25's expected-artifact inventory: Public `run.json`/metrics/rollouts/rewards/groups are respectively `5dcd27af74589c1329d8717fc0f03a4726ffc428a26e9ff380ecaab74e5442b5`, `4463e420162368411421b220ff94d9708588296fd64662d65193dd635a3baf7e`, `d09d0b5c048ffd891f486232fbcfad7993dc3cb83ff9ae8777cc98184ae699cc`, `d709ecac0ab2c1c5849201f3d80883f8eaaddf54025857bcfa95a547671b29b7`, `cca167986ca2e39061b19cc261a40eb9c1146c4de4be5139a2af6d9cd78628b3`; Hidden equivalents are `911044d6b460d8ce9e958254fa6d75fb2fd1c77a2a82431752ea9b04548ca526`, `7cd0de7f9fa2a1ef3b4bbcf985f4fefac6d27bc76f5d41e2316bc9e187dc5f70`, `08cb1485b89e8d39f5863c3a891af2f4b676d035a8f33c36b8369b2ae5022995`, `0b85089404c8f970aa199821e4b8ba5aeb0101c63cc8f339a72f31dcc88782ed`, `915d45c6bb72463e970773372584fce55a3ada8a5c1e7f3078fba17c3eba66dc`.

Public preserves four attempts: three under `a7c3c4da77b6cb6af387a74667e42d33bc9f7e6b`, then a completed attempt under `47c7fb2a55b91e471aeca5ededf6e0233f4f93f9` from validated same-run `checkpoint-175`. Hidden preserves three attempts: origin `47c7fb2a55b91e471aeca5ededf6e0233f4f93f9`, a failed retry-v2 attempt under `3675bf55c339dbfe0d1c0c248418c6efdd0da170` from `checkpoint-125`, then the completed attempt under `31b997279ff4e908165b93187fc898922a059de4` from that same validated `checkpoint-125`. C25 postcheck preserves recovery archives `before-attempt-2-resume-checkpoint-125` and `before-attempt-3-resume-checkpoint-125` for Hidden, and corresponding Public checkpoint-boundary archives at 150/175. Production GRPO reward handling still fail-closes an infrastructure-affected reward batch with `aborting before optimizer update`; resume recovery archives failed streaming suffixes/future checkpoints and restores the canonical rollout/reward/group streams exactly to the selected checkpoint boundary before continuing.

The completed canonical streams provide the result-affecting actual-path check that R1 lacked. Both formal runs are `status=completed`, `global_step=300`, descendants of the same `B-sft-formal-seed42`, with seed 42, identical B model/revision/config/data/dependency identities and formal paired-definition SHA256 `31f5464abf094d14cf86e8ef4dd909b8a1be559c8b4ca8b96473070a9f1daad9`. Each has exactly 2400 canonical rewards, 2400 rollouts and 600 groups; all numeric metric values inspected are finite; neither canonical reward stream contains `infrastructure_failure=true` or `sandbox_error`. Public's accepted `leetcode-all-paths-from-source-to-target` rows are ordinary `wrong_answer/runtime_error` outcomes and never exercise the C25 output-limit classification. Hidden's accepted rows contain exactly the formerly fatal oversized candidate as non-infrastructure `status=output_limit` with `failure_counts.output_limit=2`; the remaining group items are ordinary candidate outcomes. Thus the C25 result-affecting classification change is evidenced on Hidden while the accepted Public canonical path does not exercise that changed behavior.

### Downstream preserved evidence

C27 generation evidence/postcheck rehash to `4e2912a57b7fa5f1a3864db3e2bf938026357f4808bc85ae513042dca677a098` / `dc014c76b6bfb73fb6d30de8ddd13865309f1cd148c3eb8bd03cdab332807745`. Public/Hidden generation `run.json` hashes remain `0d081a3aded9eda7c3f12f40536f31016d2b9255054f9c5d4f4f8ab998e2f623` / `644fbd3abac1ff58884d1820feb93079e81cde0df542f64d5139a966a8ab3d27`; the generation streams remain exactly 400 rows with hashes `a5d841f625fe1d3126e858f8c12081babb7a7739c84667a715e175bfbef07357` / `f84c2ab7037c3ec297b1786171c0272f782f98b22ca1d8a81e6bb02eb384bfd0`. C27 postcheck independently binds formal checkpoint identities `628abb90a1fe57d32f7bcbba1b58ace1aed2c35fb5501871f7ce35dd8a4d05d7` / `1d661a8b5f7f591da6591bed1647cdaab3f54b881996e1913bd079fb6bfcf11d`, dataset SHA256 `770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae`, ordered IDs `2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9`, the same formal pair/Piston/model/revision/B/seed identities, and strict readback `resumed=400, generated=0` for both arms.

The existing `/home/dzy/wp7c-verified` real-Piston results also revalidate without regeneration. Public/Hidden each contain 400 rows and 400 unique problem IDs, zero sandbox rows and zero true infrastructure markers. Public results/summary/main-results hashes are `7c5bb7497389872ee55ec67c4cb73cb188b68f0da06750013f1bd7a734cbb913` / `6cc3fa7b785f01aef55e6a13e082266385ea01a77950a36ffaf1e7285e25480c` / `c39c75737cf9e4befd43e782d1bfe1f59e1aa8b8a932cb4d5bb341d39fafafc8`; Hidden equivalents are `004d5655b438244a729acd0b2b1fe33aed8ae5e8758fe462ac7215d1f54d12c5` / `f63a20181f2f560ffdf1b6bdcb385f6dbbf83f1a05b5592013315ff401a2273d` / `8da0439242fdb15274b4300fb17ebc813eb692cdbc220f3ebc70c5919cff0dcf`. Both evaluation `run.json` files bind the exact generation records hash, formal checkpoint identity, dataset/order, model/revision, dependency lock, Piston definition and project commit; aggregate numeric values inspected are finite.

### Control-plane regression after A1

No target-GPU command was launched. The exact current stage remained clean throughout the evidence audit. Focused GRPO/cadence regression passed `91` tests; `make lint` passed Ruff check/format and strict mypy; `make test` passed `1030` with `3` expected environment-gated Piston skips and zero failures; real `make test-piston PISTON_CONFIG=configs/execution/piston-local.yaml` passed all `9` selected tests with `2` deselected; `make test-gpu` passed `3/3` on the GTX 1660 Ti control plane. Primary and stage `.ai-bridge/**` remain zero-tracked.

Under the effective `sealed plan + A1` contract, executor-owned evidence for R1-B1 and R1-M1 is complete without a new 4090 run. This is explicitly a retrospective operational-equivalence disposition, not a claim that historical C/D strictly followed the original exact-code-identity or save-steps=50 requirements. Independent R2 review remains required to decide PASS.

```yaml
execution_record:
  version: 1
  stage_id: WP7-c
  execution_id: E1
  task_kind: repair
  source_plan_commit: 8464e69691c527c726a2e28e5a7ca81fa2001bbf
  source_plan_amendment_id: A1
  source_plan_amendment_commit: 72e12971a277f186663e102338096e14db55f6b1
  source_plan_amendment_sha256: aeb5f660af1662b961994276b10fa3f75b194d2b5c82b478915fa5e68bd7f3d5
  protocol_amendment_post_hoc: true
  source_review_round: 1
  source_review_commit: deebfa0f02097a0593674aaa88d1f673427ab19e
  repair_issue_ids: [R1-B1, R1-M1]
  result_code_commit: 72e12971a277f186663e102338096e14db55f6b1
  workflow_runtime_commit: c18925ae7b953e0f7022bb7c2a15c0a630258b83
  execution_backend: web_codexpro
  effective_execution_mode: single
  evidence_reuse_mode: preserved_formal_operational_equivalence
  target_gpu_rerun_performed: false
  superseded_operator_checkpoint_id: C28
  superseded_operator_checkpoint_commit: f6336c7fa22c74a94955ea529f5333a89bc1d8ee
  superseded_operator_gate_id: grpo-cd-pilot
  superseded_operator_script_sha256: ce55751b0c67800a18db4cc15fcebf6ace1d3a73455709641d50367ce811f749
  operator_checkpoint_disposition: abandoned_unexecuted
  c28_operator_execution_observed: false
  c28_control_plane_evidence_receive_dir_existed: false
  accepted_pilot_checkpoint_id: C13
  accepted_pilot_operator_evidence_sha256: 91647fa09354f1dbaf486b7d94960934391467470665401022493ad5fb87d50b
  accepted_pilot_postcheck_sha256: 91d4825b86a325a8f9765bfb9d99ab51345051c046c9847cfe335aadad487b2f
  historical_pilot_save_steps: 10
  pilot_public_global_step: 100
  pilot_hidden_global_step: 100
  accepted_formal_checkpoint_id: C25
  accepted_formal_operator_evidence_sha256: 0fe7f376fb94918f5e5aee1c28bcc0ac159687fefd9600509efb35773ca2df9e
  accepted_formal_postcheck_sha256: c41e17a3a22b1e3c54de006c058165e32c0774c2d50581844194906c75b46a63
  historical_formal_save_steps: 25
  formal_pair_sha256: 31f5464abf094d14cf86e8ef4dd909b8a1be559c8b4ca8b96473070a9f1daad9
  public_formal_run_sha256: 5dcd27af74589c1329d8717fc0f03a4726ffc428a26e9ff380ecaab74e5442b5
  hidden_formal_run_sha256: 911044d6b460d8ce9e958254fa6d75fb2fd1c77a2a82431752ea9b04548ca526
  public_formal_final_code_commit: 47c7fb2a55b91e471aeca5ededf6e0233f4f93f9
  hidden_formal_final_code_commit: 31b997279ff4e908165b93187fc898922a059de4
  public_formal_final_resume_checkpoint: checkpoints/checkpoint-175
  hidden_formal_final_resume_checkpoint: checkpoints/checkpoint-125
  public_formal_reward_rows: 2400
  hidden_formal_reward_rows: 2400
  public_formal_group_rows: 600
  hidden_formal_group_rows: 600
  public_formal_canonical_infrastructure_rows: 0
  hidden_formal_canonical_infrastructure_rows: 0
  public_formal_canonical_sandbox_rows: 0
  hidden_formal_canonical_sandbox_rows: 0
  public_c25_output_limit_path_exercised: false
  hidden_c25_output_limit_path_exercised: true
  accepted_generation_checkpoint_id: C27
  accepted_generation_operator_evidence_sha256: 4e2912a57b7fa5f1a3864db3e2bf938026357f4808bc85ae513042dca677a098
  accepted_generation_postcheck_sha256: dc014c76b6bfb73fb6d30de8ddd13865309f1cd148c3eb8bd03cdab332807745
  public_generation_records_sha256: a5d841f625fe1d3126e858f8c12081babb7a7739c84667a715e175bfbef07357
  hidden_generation_records_sha256: f84c2ab7037c3ec297b1786171c0272f782f98b22ca1d8a81e6bb02eb384bfd0
  public_verification_results_sha256: 7c5bb7497389872ee55ec67c4cb73cb188b68f0da06750013f1bd7a734cbb913
  hidden_verification_results_sha256: 004d5655b438244a729acd0b2b1fe33aed8ae5e8758fe462ac7215d1f54d12c5
  public_aggregate_summary_sha256: 6cc3fa7b785f01aef55e6a13e082266385ea01a77950a36ffaf1e7285e25480c
  hidden_aggregate_summary_sha256: f63a20181f2f560ffdf1b6bdcb385f6dbbf83f1a05b5592013315ff401a2273d
  control_plane_verification_root: /home/dzy/wp7c-verified
  evidence_class: real-training/numerical
  reporting_disclosure_required: true
  status: completed
```

E1 closes only the amendment-backed routed repair execution. R1 history, A1, C28 and all existing target artifacts remain immutable. The next action is a fresh independent reviewer-ex conversation for review round 2; this execution conversation does not self-review, checkpoint a review, finalize, merge or push.

### E1 supplemental preserved-evidence audit

The user explicitly rejected a fresh C28/pilot/formal rerun and authorized reuse of the already-completed real evidence. The immutable sealed plan and R1 review remain unchanged. Workflow-maintenance commit `c18925ae7b953e0f7022bb7c2a15c0a630258b83` adds the restricted `validation-protocol-amendment-v1` control path, and stage amendment A1 is committed at `72e12971a277f186663e102338096e14db55f6b1` with SHA256 `aeb5f660af1662b961994276b10fa3f75b194d2b5c82b478915fa5e68bd7f3d5`. A1 is explicitly `post_hoc: true`, binds review round 1 issues `R1-B1/R1-M1`, and replaces only the exact-save-cadence and exact-whole-run-code-identity rerun requirements with preserved-evidence operational-equivalence acceptance. It does not waive real training, hidden isolation, reward-source separation, sandbox/safety, completed-step, finite-telemetry, hash/provenance, or real-Piston requirements.

A1 supersedes C28 as an action, not as history. C28 checkpoint commit `f6336c7fa22c74a94955ea529f5333a89bc1d8ee` and tracked script SHA256 `ce55751b0c67800a18db4cc15fcebf6ace1d3a73455709641d50367ce811f749` remain immutable. At amendment time `/home/dzy/wp7c-operator-evidence/WP7-c/grpo-cd-pilot/C28` did not exist, and this Web executor never launched or monitored C28, so its disposition is `abandoned_unexecuted`; C28 is not reported as passed.

`R1-M1` is resolved under A1 as a persistence-cadence deviation rather than a scientific-definition failure. The preserved C13 pilot operator evidence/postcheck rehash to `91647fa09354f1dbaf486b7d94960934391467470665401022493ad5fb87d50b` / `91d4825b86a325a8f9765bfb9d99ab51345051c046c9847cfe335aadad487b2f`. Both Public and Hidden C13 pilot runs are real completed 100-step runs with historical `save_steps=10`, 800 reward rows, 800 rollout rows, and 200 group rows each. The preserved C25 formal configs are paired at `max_steps=300, save_steps=25`; excluding the intended dataset/reward-mode/run-name differences, Public/Hidden resolved configs match exactly, including beta, gradient accumulation, learning rate, LoRA parameters, cosine scheduler, generation lengths/count, batch size, seed, temperature/top-p, and warmup. Both formal runs complete 300 optimizer steps. The current tracked pilot/formal configs remain restored to `save_steps=50` for future execution, so A1 accepts historical evidence without claiming that the historical cadence complied with the original sealed value.

`R1-B1` is resolved under A1 by an actual-path code-migration audit. C25 operator evidence/postcheck independently rehash to `0fe7f376fb94918f5e5aee1c28bcc0ac159687fefd9600509efb35773ca2df9e` / `c41e17a3a22b1e3c54de006c058165e32c0774c2d50581844194906c75b46a63`. Public run metadata SHA256 is `5dcd27af74589c1329d8717fc0f03a4726ffc428a26e9ff380ecaab74e5442b5`; its attempts are `a7c3c4da77b6cb6af387a74667e42d33bc9f7e6b` fresh, then same-code checkpoint-150, same-code checkpoint-175, then migration to `47c7fb2a55b91e471aeca5ededf6e0233f4f93f9` from checkpoint-175 with `scientific_change=false`, finishing global step 300. Hidden run metadata SHA256 is `911044d6b460d8ce9e958254fa6d75fb2fd1c77a2a82431752ea9b04548ca526`; its attempts are `47c7fb2a...` fresh, migration to `3675bf55c339dbfe0d1c0c248418c6efdd0da170` from checkpoint-125 with retry-v2 and a failed suffix, then migration to `31b997279ff4e908165b93187fc898922a059de4` from the same checkpoint-125 and completion at step 300. Hidden postcheck preserves both `before-attempt-2-resume-checkpoint-125` and `before-attempt-3-resume-checkpoint-125` recovery archives, so the failed suffix is not silently rewritten into the canonical stream.

The accepted Public/Hidden formal runs retain the same completed `B-sft-formal-seed42`, seed 42, model/revision, dependency lock, Open-R1 identity, and `paired_definition_sha256=31f5464abf094d14cf86e8ef4dd909b8a1be559c8b4ca8b96473070a9f1daad9`. Each canonical run contains exactly 2400 reward rows, 2400 rollout rows, and 600 group rows with finite persisted telemetry and no canonical `infrastructure_failure` or `sandbox_error` reward rows. The result-affecting trusted-harness repair is bounded by observed path behavior: Public canonical rewards contain zero `output_limit` rows and its retry telemetry has zero operational events; Hidden canonical rewards contain exactly one ordinary non-infrastructure `output_limit` row after the C25 repair and zero infrastructure/sandbox rows. The focused current-source recovery/classification suite (`test_grpo_resume_lineage`, `test_grpo_transport_failure`, `test_harness`, `test_piston_resilience`) passes 67/67 and covers fail-closed reward infrastructure handling before optimizer update, same-run checkpoint/recovery lineage, and candidate output-limit classification. Together with the preserved same-checkpoint restart/recovery archives, this satisfies A1's no-canonical-contamination requirement without asserting literal whole-run commit identity.

The downstream artifacts were reused only after byte-level and content-level revalidation. C27 operator evidence/postcheck/terminal log rehash to `4e2912a57b7fa5f1a3864db3e2bf938026357f4808bc85ae513042dca677a098` / `dc014c76b6bfb73fb6d30de8ddd13865309f1cd148c3eb8bd03cdab332807745` / `e80c71e40dca99aa79b6bab01ab8e8c84a331fa2d55d07e38d649dfc1fe11732`. Public generation run/records rehash to `0d081a3aded9eda7c3f12f40536f31016d2b9255054f9c5d4f4f8ab998e2f623` / `a5d841f625fe1d3126e858f8c12081babb7a7739c84667a715e175bfbef07357`; Hidden to `644fbd3abac1ff58884d1820feb93079e81cde0df542f64d5139a966a8ab3d27` / `f84c2ab7037c3ec297b1786171c0272f782f98b22ca1d8a81e6bb02eb384bfd0`. Both bundles remain completed, exactly 400 unique rows, dataset SHA256 `770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae`, ordered-ID SHA256 `2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9`, seed 42, and generation project commit `0e2a894943cfb623610e937380342d148ad8cff0`; C27 evidence binds the accepted formal pair SHA above.

The existing real-Piston results under `/home/dzy/wp7c-verified` were also rehashed and parsed rather than regenerated. Public verification run/results are `bf777fc62d40249c86b4a17c92e39a06fe784688238a336faf109dfbc2b82bb2` / `7c5bb7497389872ee55ec67c4cb73cb188b68f0da06750013f1bd7a734cbb913`; Hidden are `5d6cc0a8a08efaf1f8cea927190531a3a5ff0decdc4531cd49e7d1f6375d03ba` / `004d5655b438244a729acd0b2b1fe33aed8ae5e8758fe462ac7215d1f54d12c5`. Both contain exactly 400 unique results, bind the same dataset/order and Piston definition `f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e`, and have no sandbox execution status or infrastructure-failure field occurrence. Public aggregate summary/main-results hashes remain `6cc3fa7b785f01aef55e6a13e082266385ea01a77950a36ffaf1e7285e25480c` / `c39c75737cf9e4befd43e782d1bfe1f59e1aa8b8a932cb4d5bb341d39fafafc8`; Hidden remain `f63a20181f2f560ffdf1b6bdcb385f6dbbf83f1a05b5592013315ff401a2273d` / `8da0439242fdb15274b4300fb17ebc813eb692cdbc220f3ebc70c5919cff0dcf`.

Current control-plane acceptance on A1 HEAD is green: `make lint` passed Ruff check/format plus strict mypy; `make test` passed 1030 with 3 expected environment-gated Piston skips; `make test-gpu` passed 3/3 on the GTX 1660 Ti; real `make test-piston PISTON_CONFIG=configs/execution/piston-local.yaml` passed all 9 selected tests with 2 deselected; and the focused recovery/classification suite passed 67/67. No target-GPU training or generation was started, no existing formal/generation/evaluation artifact was mutated, no sealed plan/review/checkpoint history was rewritten, and no push/review/finalize/merge was performed.

```yaml
supplemental_evidence_record:
  version: 1
  stage_id: WP7-c
  supports_execution_id: E1
  task_kind: repair
  source_plan_commit: 8464e69691c527c726a2e28e5a7ca81fa2001bbf
  source_review_round: 1
  source_review_commit: deebfa0f02097a0593674aaa88d1f673427ab19e
  repair_issue_ids: [R1-B1, R1-M1]
  source_plan_amendment_id: A1
  source_plan_amendment_commit: 72e12971a277f186663e102338096e14db55f6b1
  source_plan_amendment_sha256: aeb5f660af1662b961994276b10fa3f75b194d2b5c82b478915fa5e68bd7f3d5
  protocol_amendment_post_hoc: true
  workflow_runtime_commit: c18925ae7b953e0f7022bb7c2a15c0a630258b83
  result_code_commit: 72e12971a277f186663e102338096e14db55f6b1
  execution_backend: web_codexpro
  effective_execution_mode: single
  superseded_operator_checkpoint_id: C28
  superseded_operator_checkpoint_commit: f6336c7fa22c74a94955ea529f5333a89bc1d8ee
  superseded_operator_script_sha256: ce55751b0c67800a18db4cc15fcebf6ace1d3a73455709641d50367ce811f749
  operator_checkpoint_disposition: abandoned_unexecuted
  superseded_operator_receive_dir: /home/dzy/wp7c-operator-evidence/WP7-c/grpo-cd-pilot/C28
  superseded_operator_receive_dir_existed_at_amendment: false
  historical_pilot_checkpoint_id: C13
  historical_pilot_operator_evidence_sha256: 91647fa09354f1dbaf486b7d94960934391467470665401022493ad5fb87d50b
  historical_pilot_postcheck_sha256: 91d4825b86a325a8f9765bfb9d99ab51345051c046c9847cfe335aadad487b2f
  historical_pilot_max_steps: 100
  historical_pilot_save_steps: 10
  historical_pilot_public_reward_rows: 800
  historical_pilot_public_rollout_rows: 800
  historical_pilot_public_group_rows: 200
  historical_pilot_hidden_reward_rows: 800
  historical_pilot_hidden_rollout_rows: 800
  historical_pilot_hidden_group_rows: 200
  historical_formal_max_steps: 300
  historical_formal_save_steps: 25
  current_future_pilot_save_steps: 50
  current_future_formal_save_steps: 50
  accepted_c25_operator_evidence_sha256: 0fe7f376fb94918f5e5aee1c28bcc0ac159687fefd9600509efb35773ca2df9e
  accepted_c25_postcheck_sha256: c41e17a3a22b1e3c54de006c058165e32c0774c2d50581844194906c75b46a63
  accepted_public_formal_run_sha256: 5dcd27af74589c1329d8717fc0f03a4726ffc428a26e9ff380ecaab74e5442b5
  accepted_hidden_formal_run_sha256: 911044d6b460d8ce9e958254fa6d75fb2fd1c77a2a82431752ea9b04548ca526
  accepted_formal_pair_sha256: 31f5464abf094d14cf86e8ef4dd909b8a1be559c8b4ca8b96473070a9f1daad9
  public_formal_attempt_code_commits: [a7c3c4da77b6cb6af387a74667e42d33bc9f7e6b, a7c3c4da77b6cb6af387a74667e42d33bc9f7e6b, a7c3c4da77b6cb6af387a74667e42d33bc9f7e6b, 47c7fb2a55b91e471aeca5ededf6e0233f4f93f9]
  public_formal_attempt_resumes: [null, checkpoints/checkpoint-150, checkpoints/checkpoint-175, checkpoints/checkpoint-175]
  hidden_formal_attempt_code_commits: [47c7fb2a55b91e471aeca5ededf6e0233f4f93f9, 3675bf55c339dbfe0d1c0c248418c6efdd0da170, 31b997279ff4e908165b93187fc898922a059de4]
  hidden_formal_attempt_resumes: [null, checkpoints/checkpoint-125, checkpoints/checkpoint-125]
  public_formal_global_step: 300
  hidden_formal_global_step: 300
  public_formal_reward_rows: 2400
  public_formal_rollout_rows: 2400
  public_formal_group_rows: 600
  hidden_formal_reward_rows: 2400
  hidden_formal_rollout_rows: 2400
  hidden_formal_group_rows: 600
  public_canonical_output_limit_reward_rows: 0
  hidden_canonical_output_limit_reward_rows: 1
  public_canonical_infrastructure_reward_rows: 0
  hidden_canonical_infrastructure_reward_rows: 0
  public_canonical_sandbox_reward_rows: 0
  hidden_canonical_sandbox_reward_rows: 0
  public_reward_retry_operational_events: 0
  hidden_recovery_archives: [before-attempt-2-resume-checkpoint-125, before-attempt-3-resume-checkpoint-125]
  accepted_c27_operator_evidence_sha256: 4e2912a57b7fa5f1a3864db3e2bf938026357f4808bc85ae513042dca677a098
  accepted_c27_postcheck_sha256: dc014c76b6bfb73fb6d30de8ddd13865309f1cd148c3eb8bd03cdab332807745
  accepted_c27_terminal_log_sha256: e80c71e40dca99aa79b6bab01ab8e8c84a331fa2d55d07e38d649dfc1fe11732
  public_generation_run_sha256: 0d081a3aded9eda7c3f12f40536f31016d2b9255054f9c5d4f4f8ab998e2f623
  public_generation_records_sha256: a5d841f625fe1d3126e858f8c12081babb7a7739c84667a715e175bfbef07357
  hidden_generation_run_sha256: 644fbd3abac1ff58884d1820feb93079e81cde0df542f64d5139a966a8ab3d27
  hidden_generation_records_sha256: f84c2ab7037c3ec297b1786171c0272f782f98b22ca1d8a81e6bb02eb384bfd0
  generation_rows_each: 400
  evaluation_dataset_sha256: 770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae
  ordered_problem_ids_sha256: 2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9
  piston_definition_sha256: f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e
  public_verification_run_sha256: bf777fc62d40249c86b4a17c92e39a06fe784688238a336faf109dfbc2b82bb2
  public_verification_results_sha256: 7c5bb7497389872ee55ec67c4cb73cb188b68f0da06750013f1bd7a734cbb913
  hidden_verification_run_sha256: 5d6cc0a8a08efaf1f8cea927190531a3a5ff0decdc4531cd49e7d1f6375d03ba
  hidden_verification_results_sha256: 004d5655b438244a729acd0b2b1fe33aed8ae5e8758fe462ac7215d1f54d12c5
  verification_rows_each: 400
  verification_sandbox_error_rows: 0
  verification_infrastructure_failure_rows: 0
  public_aggregate_summary_sha256: 6cc3fa7b785f01aef55e6a13e082266385ea01a77950a36ffaf1e7285e25480c
  public_aggregate_main_results_sha256: c39c75737cf9e4befd43e782d1bfe1f59e1aa8b8a932cb4d5bb341d39fafafc8
  hidden_aggregate_summary_sha256: f63a20181f2f560ffdf1b6bdcb385f6dbbf83f1a05b5592013315ff401a2273d
  hidden_aggregate_main_results_sha256: 8da0439242fdb15274b4300fb17ebc813eb692cdbc220f3ebc70c5919cff0dcf
  focused_equivalence_tests_passed: 67
  full_tests_passed: 1030
  full_tests_expected_skipped: 3
  gpu_tests_passed: 3
  piston_selected_tests_passed: 9
  piston_deselected_tests: 2
  evidence_class: real-training/numerical
  audit_status: completed
```

This supplemental audit supports the authoritative E1 record above and is not a second execution record. Independent review remains a fresh-conversation boundary.
