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
