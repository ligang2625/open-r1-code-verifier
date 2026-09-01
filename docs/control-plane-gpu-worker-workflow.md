# GTX 1660 Ti control plane / RTX 4090 GPU worker workflow

This document is the canonical project-level hardware-routing policy. It supersedes older workflow-location guidance that treated the 4090 as the validation control plane; it does not rewrite historical stage results or formal artifact identities.

## Machine roles

### GTX 1660 Ti: control plane and default development machine

Run planner-ex, reviewer-ex, stage lifecycle, execution routing, ordinary code and workflow changes, lint/unit/CPU/non-4090 integration tests, data preparation/checks, analysis, reports/plots/tables, SFT trajectory prevalidation, Piston work, structural smoke checks and all target-GPU handoff preparation here.

Every stage plan records:

```yaml
stage_profile: development | validation
control_plane_hardware: GTX 1660 Ti (6GB)
target_hardware: GTX 1660 Ti (6GB) | 24GB GPU
```

For validation, `target_hardware` describes what this stage must newly execute, not where its formal source artifacts came from. A validation stage that only aggregates/analyzes existing formal evidence uses `GTX 1660 Ti (6GB)`; a validation stage that performs any new target-GPU execution uses `24GB GPU`. Neither choice moves planner, reviewer or execution-router off the control plane.

### RTX 4090: ephemeral target-GPU worker

Use the 4090 only when a gate intrinsically needs it: target-GPU smoke/acceptance, optimizer-based SFT/GRPO, target numerical validation, or formal model inference/evaluation that cannot reasonably run on the 1660 Ti. The 4090 may be offline while validation is planned, routed, reviewed or analyzed.

## Target-GPU operator gates

Every validation gate that actually needs the 24GB worker uses the same operator boundary, whether it is a short 4090-only smoke or a long formal job. GPT/CodexPro prepares all tracked code/configuration and control-plane checks; it never starts or continuously monitors the target-GPU command.

The control-plane executor creates one immutable, secret-free tracked script at `ai-work/executor/operator/<stage>/<gate>/<checkpoint>/run.sh`. Keep the operator checkpoint commit as narrow as practical (normally the execution report plus that new script), but do not make an ordinary parent/source SHA relationship a state-machine lock. `result_code_commit`, plan/review commits, and checkpoint parents are audit anchors; attributable provenance/docs-only commits do not invalidate the handoff. The workflow does not auto-push.

On the 4090, the user:

1. makes the **actual operator-handoff commit** reachable through Git;
2. checks out or detaches at that handoff commit and confirms the worktree is clean;
3. recomputes the tracked `run.sh` SHA256 and compares it with the checkpoint;
4. runs that tracked script manually in SSH/tmux.

The target script must fail closed on the identities that prove what actually ran: current HEAD equals the handoff commit, stage/gate/checkpoint/script ownership is unambiguous, the tracked script SHA matches, and READY/CUDA/VRAM/model/data/cache/persistent roots/storage/locking/Piston requirements are satisfied. Parent/result/source commit equalities are diagnostic provenance rather than mechanical gates. The script then executes **start preflight → target command → mandatory post-run acceptance**. A target-command return code of zero is not enough: `gate_status=passed` is legal only when `command_rc=0` and `postcheck_rc=0`. Existing `exact_rerun`, `trainer_checkpoint`, latest-valid-checkpoint, atomic status, append-only log and quarantine/no-overwrite semantics remain authoritative.

After each attempt the script emits a versioned secret-free `operator-evidence.json`. Strict identity must cover the actual handoff commit, tracked script path/SHA, target machine/runtime identity, timestamps, command/postcheck rc, gate status, formal run identity, and required artifact inventory/hashes. Plan/review/result/workflow-runtime commits may also be recorded as audit anchors; if they drift on the control plane, resume checks lineage/diff and whether the gate is still semantically applicable instead of requiring field-for-field SHA equality. Sync the evidence plus only the necessary small manifests/metrics/logs byte-for-byte back to the control plane. Resume computes the received evidence SHA256 and records it in the completed execution record. Do not rsync large model checkpoints back by default.

## Cross-machine review

reviewer-ex normally runs on the GTX 1660 Ti regardless of where formal artifacts were produced. For target=24GB stages it independently recomputes the tracked script SHA, received evidence SHA and synced small-artifact hashes, and checks the post-run acceptance result before PASS. For formal-evidence-only validation stages with target=1660 Ti, it reviews source formal identities/hashes and the analysis itself without inventing a new GPU requirement. Reviewer location, artifact source machine and target hardware are independent.

A brief read-only target-machine metadata/artifact check is allowed only when the target-side postcheck/evidence cannot prove a required large-artifact property. Review never reruns or monitors a formal target-GPU command merely to obtain local artifacts.

## Piston

The only project Piston host is `1660ti-wsl`; `home-piston-01` is retired. The pinned Piston service remains on the 1660 Ti WSL host.

A 4090 gate that requires Piston must first ensure the current reverse-forward contract:

```text
1660ti-wsl 127.0.0.1:2000
        |
        | SSH reverse forward over the current provider public SSH endpoint
        v
4090 127.0.0.1:2000
```

The control plane owns the long-lived outbound SSH session and uses `-R 127.0.0.1:2000:127.0.0.1:2000`. The current provider SSH hostname/port/authentication remain machine-local and untracked. The 4090 must not start the retired Tailscale/local-forward helper while this transport is active; target-GPU preflight checks only that `http://127.0.0.1:2000/api/v2/runtimes` is healthy and reports the exact pinned runtime.

The project endpoint remains `http://127.0.0.1:2000`; never configure a LAN/public Piston endpoint or introduce another host.

## SFT prevalidation

The existing SFT split remains mandatory. `prevalidate-sft` runs on the 1660 Ti/Piston control plane and writes an immutable manifest. `train-sft` on the 4090 consumes `--prevalidation-manifest` and must not contact Piston. Optimizer-based SFT still requires the target-GPU hardware guard.

## Environment interruption

A valid external environment interruption after useful commits is resumable. A committed `execution_checkpoint(interruption_class=environment,resume_allowed=true)` is the preferred recovery anchor, but it is not the only proof that a partial stage can continue. If Git history, report state, diffs, tests, and user intent make completed/remaining scope reliably recoverable, continue from the current state even when the checkpoint is not current HEAD or no formal checkpoint exists. `retire_incomplete` is reserved for explicit abandon or a state that cannot be safely attributed/recovered.

## Normal cases

### Case 1: ordinary development

```text
1660 Ti: planner -> bootstrap_plan -> code -> lint/test -> reviewer -> finalize
4090: off
```

### Case 2: validation + formal SFT

```text
1660 Ti: planner -> bootstrap/code/prevalidate-sft/short tests -> portable 4090 handoff
4090: target preflight -> user runs formal SFT -> formal artifacts + operator evidence
1660 Ti: sync small evidence -> execution-router resume -> analysis -> reviewer
```

The 4090 may be shut down after the formal artifacts/evidence are safely stored.

### Case 3: formal evaluation

```text
1660 Ti: prepare exact evaluation config + target-generation operator handoff
4090: load model -> generate complete frozen bundle -> generation artifacts/evidence -> shut down when safe
1660 Ti: verify frozen completions with local Piston -> aggregate -> bootstrap CI -> failure analysis -> reviewer
```

Do not serialize target-GPU generation with remote Piston verification once the staged evaluation contract is available. The portable generation bundle must bind model/revision/checkpoint, seed, ordered dataset identity, decode settings, Piston-definition SHA, code/Open-R1/dependency identity and record hashes. `generate-eval` runs only the model-generation phase on the target GPU; `verify-eval` then consumes that immutable bundle on the control plane, preserves canonical problem order and exact generated payload, and `aggregate-eval` derives the correctness/statistical outputs. Piston execution timing is fresh runtime telemetry and is not expected to be byte-identical across independent verification attempts.

### Case 4: GRPO

```text
1660 Ti: prepare data/config/Piston validation/operator handoff
4090: user runs formal GRPO optimizer job
1660 Ti: sync evidence -> analysis/review
```

## Active-stage workflow migration and effective contract

A project-level workflow update may land while an already sealed stage has execution/review history. The sealed plan/review remains the default contract and historical provenance, but ordinary `planning_base_commit`, review, result-code, checkpoint-parent, and `workflow_runtime_commit` SHAs are **audit anchors rather than immutable state locks**. Prefer a clean maintenance worktree when that avoids mixing workflow maintenance with business changes, but an advanced primary `main` or a newer workflow runtime does not by itself invalidate the active stage. Inspect lineage/diff and block only when the change alters unreviewed business semantics, makes scope/provenance ambiguous, or conflicts with the stage.

Record the workflow runtime actually used when useful for audit. User-explicit changes to implementation method, scope, ordering, routing, or recovery form an **effective execution contract** without requiring a sealed-plan rewrite. This precedence does not waive project/specification MUST/MUST NOT rules, real-evidence requirements, hidden-test isolation, target-GPU boundaries, experiment identities, or acceptance criteria.

If a repair needs an operator-owned control-plane-only action (for example Piston verification of an already-frozen generation bundle), it may use `operator_handoff_mode: control_plane_manual` when the latest review or explicit user instruction makes that path unambiguous. The tracked script SHA, frozen result-affecting inputs, fresh non-overwriting output, and real command/postcheck evidence remain strict. Ordinary plan/review/workflow-runtime commit equality does not. This mode must never move a real 24GB training/inference gate off the RTX 4090 or become a convenience offload.

Old sealed plans may lack metadata added by later workflow versions. Infer missing metadata only when the current project state and history make the effective profile/hardware/evidence contract reliable; new plans should still write the current explicit metadata. Reclassify preflight by current hardware responsibility: run checks that are necessary for the effective task, keep target-only checks at target start, and do not force irrelevant historical preflight or exact-SHA conditions merely to preserve an old workflow form.

## Backward compatibility

Historical operator checkpoints that predate `operator_handoff_mode: portable_target` may contain absolute target-root paths. They remain auditable under the legacy v1 contract; do not rewrite historical records merely to adopt this workflow. New operator checkpoints use the portable-target contract.
