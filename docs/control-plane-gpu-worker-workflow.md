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

`target_hardware: 24GB GPU` never implies that planner, reviewer or execution-router must run on the 4090.

### RTX 4090: ephemeral target-GPU worker

Use the 4090 only when a gate intrinsically needs it: target-GPU smoke/acceptance, optimizer-based SFT/GRPO, target numerical validation, or formal model inference/evaluation that cannot reasonably run on the 1660 Ti. The 4090 may be offline while validation is planned, routed, reviewed or analyzed.

## Long target-GPU jobs

GPT/CodexPro prepares all tracked code/configuration, control-plane preflight, short tests and a secret-free portable `run.sh`. It does not start or continuously monitor formal long jobs.

The control-plane executor writes the immutable script under ignored `.ai-bridge/operator-handoffs/<stage>/<plan>/<gate>/<checkpoint>/`, records its SHA256 and target artifact/evidence contract in an append-only operator checkpoint, and stops with operator action required.

On the 4090, the user:

1. fetches/checks out the exact operator-checkpoint commit;
2. copies the exact `run.sh` and verifies its SHA256;
3. runs it manually in SSH/tmux.

The target script resolves the 4090 checkout and target-local machine record at runtime. Before the formal command it fail-closes on Git/report provenance, READY identity, CUDA/VRAM, model/data/cache, persistent artifact/HF/data roots, storage capacity, locking and Piston when applicable. Existing `exact_rerun`, `trainer_checkpoint`, latest-valid-checkpoint, atomic status, append-only log and quarantine/no-overwrite semantics remain authoritative.

After each target attempt the script emits a small secret-free `operator-evidence.json` binding the operator checkpoint, script hash, target machine/GPU identity, resolved roots, Piston identity when applicable, status/log, formal run identity and checkpoint/artifact inventory/hashes/summaries. Sync that evidence plus only the necessary small manifests/metrics/logs back to the control plane. Do not rsync large model checkpoints back by default.

## Cross-machine review

reviewer-ex normally runs on the GTX 1660 Ti regardless of where formal artifacts were produced. It reviews Git/result provenance, operator checkpoint, target machine identity, evidence manifest, metrics/logs, checkpoint inventory/hashes/summaries and repeatable control-plane readback/aggregation tests. Reviewer location, artifact source machine and target hardware are independent.

A brief read-only target-machine metadata/artifact check is allowed only when the synced evidence is insufficient. Review never reruns or monitors the formal long job merely to obtain local artifacts.

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
