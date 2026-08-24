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
