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
