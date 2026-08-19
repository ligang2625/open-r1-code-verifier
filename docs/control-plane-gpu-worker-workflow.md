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

The control-plane executor creates one immutable, secret-free tracked script at `ai-work/executor/operator/<stage>/<gate>/<checkpoint>/run.sh`. The operator checkpoint commit contains exactly the execution report plus that new script and has `result_code_commit` as its parent. The workflow does not auto-push.

On the 4090, the user:

1. makes the exact operator-checkpoint commit reachable through Git;
2. checks out or detaches at that exact commit and confirms the worktree is clean;
3. recomputes the tracked `run.sh` SHA256 and compares it with the checkpoint;
4. runs that tracked script manually in SSH/tmux.

The target script resolves the target-local machine record and fails closed on Git/checkpoint/script provenance, READY identity, CUDA/VRAM, model/data/cache, persistent artifact/HF/data roots, storage, locking and Piston when applicable. It then executes **start preflight → target command → mandatory post-run acceptance**. A target-command return code of zero is not enough: `gate_status=passed` is legal only when `command_rc=0` and `postcheck_rc=0`. Existing `exact_rerun`, `trainer_checkpoint`, latest-valid-checkpoint, atomic status, append-only log and quarantine/no-overwrite semantics remain authoritative.

After each attempt the script emits a versioned secret-free `operator-evidence.json` binding stage/plan/operator-checkpoint/result-code/checkpoint/gate identity, tracked script path/SHA, target machine-record SHA, GPU identity/VRAM, resolved roots, Piston identity when applicable, timestamps, command/postcheck rc, gate status, formal run identity and expected-artifact inventory. Sync that evidence plus only the necessary small manifests/metrics/logs byte-for-byte back to the control plane. Resume computes the received evidence SHA256 and records it in the completed execution record. Do not rsync large model checkpoints back by default.

## Cross-machine review

reviewer-ex normally runs on the GTX 1660 Ti regardless of where formal artifacts were produced. For target=24GB stages it independently recomputes the tracked script SHA, received evidence SHA and synced small-artifact hashes, and checks the post-run acceptance result before PASS. For formal-evidence-only validation stages with target=1660 Ti, it reviews source formal identities/hashes and the analysis itself without inventing a new GPU requirement. Reviewer location, artifact source machine and target hardware are independent.

A brief read-only target-machine metadata/artifact check is allowed only when the target-side postcheck/evidence cannot prove a required large-artifact property. Review never reruns or monitors a formal target-GPU command merely to obtain local artifacts.

## Piston

The only project Piston host is `1660ti-wsl`; `home-piston-01` is retired. The pinned Piston service remains on the 1660 Ti WSL host.

A 4090 gate that requires Piston must first ensure:

```text
4090 127.0.0.1:2000 -> 1660ti-wsl 127.0.0.1:2000
```

using:

```bash
/root/sj-tmp/open-r1-code-verifier-outputs/machine/ensure-piston-1660ti-tunnel.sh
```

The project endpoint remains `http://127.0.0.1:2000`; never configure a LAN/public Piston endpoint or introduce another host.

## SFT prevalidation

The existing SFT split remains mandatory. `prevalidate-sft` runs on the 1660 Ti/Piston control plane and writes an immutable manifest. `train-sft` on the 4090 consumes `--prevalidation-manifest` and must not contact Piston. Optimizer-based SFT still requires the target-GPU hardware guard.

## Environment interruption

A valid external environment interruption after useful commits is resumable. Preserve the committed `execution_checkpoint(interruption_class=environment,resume_allowed=true)`, repair the environment and explicitly resume. `retire_incomplete` is an explicit abandon path, not the default recovery path.

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
1660 Ti: prepare exact evaluation config/operator handoff
4090: load model -> ensure 1660ti-wsl Piston tunnel -> formal inference/evaluation -> artifacts/evidence
1660 Ti: aggregate -> bootstrap CI -> failure analysis -> reviewer
```

### Case 4: GRPO

```text
1660 Ti: prepare data/config/Piston validation/operator handoff
4090: user runs formal GRPO optimizer job
1660 Ti: sync evidence -> analysis/review
```

## Backward compatibility

Historical operator checkpoints that predate `operator_handoff_mode: portable_target` may contain absolute target-root paths. They remain auditable under the legacy v1 contract; do not rewrite historical records merely to adopt this workflow. New operator checkpoints use the portable-target contract.
