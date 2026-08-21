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
