# WP6-d Execution Report

## C0 — Formal SFT B operator handoff

Web GPT + CodexPro completed the routed short-running implementation and validation work for WP6-d, including durable Base A identity readback, formal SFT telemetry/config wiring, the real two-step RTX 4090 SFT smoke, and final executor-owned regression gates. The formal 2,500-example SFT B optimizer run has **not** been started by the executor.

```yaml
execution_checkpoint:
  version: 1
  checkpoint_id: C0
  stage_id: WP6-d
  task_kind: implementation
  source_plan_commit: eb523bc749e9aa4362790c45bbcf4d604ad7e478
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: a6d0b938bac4528a6fe109c23061fe1506a60607
  interruption_class: operator
  resume_allowed: true
  operator_gate_id: sft-b-formal
  operator_restart_policy: trainer_checkpoint
  operator_script: /root/sj-tmp/open-r1-code-verifier-outputs/operator/WP6-d/eb523bc749e9aa4362790c45bbcf4d604ad7e478/sft-b-formal/C0/run.sh
  operator_script_sha256: 0a30e7aee4a4665303dd5f3e3c363df31bc98366839fb65a134fba45f6a23013
  operator_status_file: /root/sj-tmp/open-r1-code-verifier-outputs/operator/WP6-d/eb523bc749e9aa4362790c45bbcf4d604ad7e478/sft-b-formal/C0/status
  operator_log_file: /root/sj-tmp/open-r1-code-verifier-outputs/operator/WP6-d/eb523bc749e9aa4362790c45bbcf4d604ad7e478/sft-b-formal/C0/terminal.log
  expected_artifacts:
    - /root/sj-tmp/open-r1-code-verifier-outputs/sft/B-sft-formal-seed42/run.json
    - /root/sj-tmp/open-r1-code-verifier-outputs/sft/B-sft-formal-seed42/resolved_config.yaml
    - /root/sj-tmp/open-r1-code-verifier-outputs/sft/B-sft-formal-seed42/environment.json
    - /root/sj-tmp/open-r1-code-verifier-outputs/sft/B-sft-formal-seed42/metrics.jsonl
    - /root/sj-tmp/open-r1-code-verifier-outputs/sft/B-sft-formal-seed42/checkpoints/adapter_config.json
    - /root/sj-tmp/open-r1-code-verifier-outputs/sft/B-sft-formal-seed42/checkpoints/adapter_model.safetensors
  completed_scope:
    - "durable Base A identity repair committed in 3c32e15: historical evaluation config identity now uses persisted piston_config_sha256 and no longer depends on a finalized/deleted stage-worktree Piston path; real Base A strict readback succeeds with 400 unique problems"
    - "formal SFT data/run CLI binding, max_seq_length=1536, logging_steps=1, checkpoint/attempt/CUDA/cost telemetry, and validation smoke config committed in 353954c"
    - "plain SFT runtime repair committed in c730fa2: Accelerate's type-only unused DeepSpeed probe is suppressed only for the plain SFT Trainer lifecycle and restored afterward; no third_party or dependency pin changes were made"
    - "tracked engineering smoke fixture makes configs/sft/validation-smoke.yaml independently runnable; exact 1.5B BF16 two-step RTX 4090 smoke completed at /root/sj-tmp/open-r1-code-verifier-outputs/sft/WP6-d-validation-smoke-c730fa2 with git_commit c730fa21ace4abfc31758178b1a85bc639e412a1"
    - "smoke telemetry readback: global_step=2; finite per-step loss/grad_norm/learning_rate/epoch/token scalars; project CUDA peak allocated/reserved bytes; attempt and cumulative GPU-hours; load_training_curve_rows returned 32 rows and build_cost_row succeeded"
    - "smoke checkpoint inventory: checkpoint-1 and checkpoint-2 both contain optimizer.pt, scheduler.pt, rng_state.pth, trainer_state.json, training_args.bin and PEFT adapter state; max complete checkpoint size S=42165517 bytes and max file count F=15"
    - "integration telemetry fixture alignment committed in a6d0b93; final result_code_commit is a6d0b938bac4528a6fe109c23061fe1506a60607"
    - "final executor-owned acceptance: make lint PASS; make test with exact cached 1.5B snapshot PASS 893 passed / 3 expected real-Piston-opt-in skips / 0 failed; make test-gpu PASS 3/3; real make test-piston PASS 9 selected / 0 failed / 0 skipped"
    - "formal data/Base A/storage readback before handoff: SFT train=2500, validation=300, Base A completed with 400 unique problems, persistent artifact free space 113216376832 bytes and 283215512 free inodes"
    - "sft-b-formal C0 immutable operator script generated under persistent artifact_root, chmod 0555, bash syntax checked, SHA256 bound; storage gate derived from smoke is max(20 GiB, 5*S+5 GiB)=20 GiB and max(20000, 5*F+10000)=20000 inodes"
  remaining_scope:
    - "operator runs the exact C0 run.sh in a normal SSH terminal or tmux; Web GPT/CodexPro must not run the formal 2500+300 optimizer command"
    - "if the same canonical formal run is incomplete, the immutable C0 script validates identity and automatically resumes the numerically latest valid same-run Trainer checkpoint; an incomplete run with no valid checkpoint fails closed for quarantine/recovery"
    - "explicit execution-router resume backend=web validates status/log plus real formal SFT artifacts, finite telemetry, complete checkpoint inventory, independent completed adapter reload, analysis curve/cost readiness, and payload safety"
    - "after formal SFT acceptance, executor prepares the separate sft-b-evaluation exact_rerun operator checkpoint; operator then runs the 400-problem B evaluation and resumes again"
    - "only after B evaluation, exact-prefix 400/0 resume, A/B pairing, and all final acceptance gates may completed E0 be appended"
  status: awaiting_operator
```

### Executor-owned evidence before C0

- Routing source: sealed WP6-d `execution_routing`, `mode=single`, `complexity=difficult_serial`; backend `web_codexpro`; effective execution mode `single`.
- Stage worktree: `/root/sj-tmp/open-r1-code-verifier/.worktrees/wp6-d`, branch `feat/wp6-d`; primary planning base remains `a683602f22de7f7b0ba24f01d12a183eea7ddca7`.
- Validation roots: artifact `/root/sj-tmp/open-r1-code-verifier-outputs`, Hugging Face cache `/root/sj-tmp/huggingface`, formal data `/root/sj-tmp/open-r1-code-verifier-data-4090`.
- Validation machine: PyTorch `2.6.0+cu124`, CUDA `12.4`, NVIDIA GeForce RTX 4090, `22683 MiB` total VRAM, native BF16 support.
- Formal dataset checksum and `check-data` preflight passed earlier in this execution: 3,200 total problems, 2,500 train, 300 validation, 400 test; required SFT max sequence length `1536`, measured train+validation maximum `1519` tokens.
- Exact offline model snapshot `Qwen/Qwen2.5-Coder-1.5B-Instruct@2e1fd397ee46e1388853d2af2c993145b0f1098a` loaded locally and was used by the completed two-step BF16 smoke.
- Real tunneled Piston acceptance passed with Python runtime `3.10.0`: 9 selected tests passed, 0 failed/skipped (`2` deselected).
- The initial unqualified `make test` invocation exposed only environment/test-fixture issues: the default uncached 0.5B GPU-smoke model and a fake SFT Trainer lacking the newly required `global_step`. The fixture was corrected; rerunning the suite with the sealed exact cached 1.5B model produced the final passing 893/3/0 result recorded above.
- The SFT runtime smoke also exposed that pinned Open-R1 installs DeepSpeed 0.16.8 as a core dependency while Accelerate 1.4.0 imports DeepSpeed merely for model-unwrapping type detection. On this ordinary GPU container, that unused import probes for a CUDA toolkit/nvcc even though plain LoRA SFT does not enable DeepSpeed. The project-side narrow guard avoids only that unconfigured backend probe and was proven with `setuptools` removed and no `nvcc`/`CUDA_HOME` present; the two-step SFT still completed successfully.
- No formal B SFT run exists at handoff time. The executor did not start the 2,500-example optimizer run and did not modify existing Base A artifacts.

## C1 — Pre-formal robustness re-audit and replacement SFT B operator handoff

At the user's explicit request, Web GPT + CodexPro re-audited WP6-d before any formal optimizer work. C0 was never executed. The audit found one training-interruption provenance defect and two operator-control weaknesses that were important to fix before a long paid-GPU run. The experiment definition, formal data, model revision, optimizer hyperparameters, evaluation definition, and Base A artifacts remain unchanged.

```yaml
execution_checkpoint:
  version: 1
  checkpoint_id: C1
  stage_id: WP6-d
  task_kind: implementation
  source_plan_commit: eb523bc749e9aa4362790c45bbcf4d604ad7e478
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: acee19768967251fc4aca553fa3283a487b00fc2
  interruption_class: operator
  resume_allowed: true
  operator_gate_id: sft-b-formal
  operator_restart_policy: trainer_checkpoint
  operator_script: /root/sj-tmp/open-r1-code-verifier-outputs/operator/WP6-d/eb523bc749e9aa4362790c45bbcf4d604ad7e478/sft-b-formal/C1/run.sh
  operator_script_sha256: ecbd03559537dedd6fdc1eeb8734ad962b1ce94e5cd405a727fbc2fbd2fa7042
  operator_status_file: /root/sj-tmp/open-r1-code-verifier-outputs/operator/WP6-d/eb523bc749e9aa4362790c45bbcf4d604ad7e478/sft-b-formal/C1/status
  operator_log_file: /root/sj-tmp/open-r1-code-verifier-outputs/operator/WP6-d/eb523bc749e9aa4362790c45bbcf4d604ad7e478/sft-b-formal/C1/terminal.log
  expected_artifacts:
    - /root/sj-tmp/open-r1-code-verifier-outputs/sft/B-sft-formal-seed42/run.json
    - /root/sj-tmp/open-r1-code-verifier-outputs/sft/B-sft-formal-seed42/resolved_config.yaml
    - /root/sj-tmp/open-r1-code-verifier-outputs/sft/B-sft-formal-seed42/environment.json
    - /root/sj-tmp/open-r1-code-verifier-outputs/sft/B-sft-formal-seed42/metrics.jsonl
    - /root/sj-tmp/open-r1-code-verifier-outputs/sft/B-sft-formal-seed42/checkpoints/adapter_config.json
    - /root/sj-tmp/open-r1-code-verifier-outputs/sft/B-sft-formal-seed42/checkpoints/adapter_model.safetensors
  completed_scope:
    - "pre-formal audit confirmed the sealed training definition remains exact: Qwen2.5-Coder-1.5B-Instruct at revision 2e1fd397ee46e1388853d2af2c993145b0f1098a; 2500 train + 300 validation; max_seq_length 1536; 2 epochs; batch 1; gradient accumulation 16; LR 2e-4; warmup 0.05; cosine; BF16; LoRA r16/alpha32/dropout0.05; logging every optimizer step; save/eval every 100 optimizer steps"
    - "audit confirmed B evaluation and WP8 analysis identity/data chains are closed: completed-B-only PEFT reload, base/revision checks, exact checkpoint binding, 400-problem exact-prefix evaluation, persisted completion/code and parse/status/pass-rate/failure/token/latency/hit-max-new-tokens fields, problem-level aggregate/bootstrap, and A/B/C/D shared-contract checks"
    - "critical interruption fix committed in acee19768967251fc4aca553fa3283a487b00fc2: SFT catches BaseException so KeyboardInterrupt closes the current attempt and persists failed status/end_time/attempt GPU-hours/cumulative GPU-hours before re-raising; completed metrics are atomically rebuilt from Trainer state so a resumed completion cannot duplicate a partially written curve"
    - "new unit coverage proves KeyboardInterrupt attempt/cost persistence and resume metrics de-duplication; focused SFT suite 40 passed, focused SFT/CLI/analysis suite 139 passed, Ruff and Mypy passed"
    - "fresh exact-model BF16 two-step RTX 4090 smoke under acee197 completed at /root/sj-tmp/open-r1-code-verifier-outputs/sft/WP6-d-validation-smoke-acee197; run.json binds git_commit acee19768967251fc4aca553fa3283a487b00fc2; WP8 curve loader returned 32 numeric rows and cost loader succeeded"
    - "fresh smoke checkpoint inventory again proves complete Trainer resume state: checkpoint-1 and checkpoint-2 contain optimizer/scheduler/RNG/trainer state/training args/adapter files; measured max checkpoint S=42165518 bytes and F=15 files; final completed adapter strict loader succeeded"
    - "post-fix global acceptance: make lint PASS; exact cached 1.5B make test PASS 894 passed / 3 expected real-Piston opt-in skips / 0 failed; make test-gpu PASS 3/3; tunneled real make test-piston PASS 9 selected / 0 failed / 0 skipped"
    - "C1 supersedes unexecuted C0. C1 adds fail-closed native-BF16 checking, exact runtime API/version checks, live Piston YAML digest equality with persisted Base A piston_config_sha256, full frozen formal-config checks, and status-safe resume-source selection so set -e cannot bypass atomic operator status reporting"
    - "C1 immutable operator script is chmod 0555, bash syntax checked, and SHA256-bound; formal B canonical run still does not exist, so no formal optimizer work has started"
  remaining_scope:
    - "operator runs the exact C1 run.sh in a normal SSH terminal or tmux; Web GPT/CodexPro must not start the formal 2500+300 optimizer command"
    - "if interrupted after a valid Trainer checkpoint, the same immutable C1 script validates canonical-run identity and automatically selects the numerically latest valid same-run checkpoint; if interruption occurs before any valid checkpoint, evidence is preserved and the script fails closed for quarantine/fresh-restart handling rather than deleting or overwriting it"
    - "explicit execution-router resume backend=web validates C1 status/log and real formal SFT artifacts, finite complete metrics, attempt accounting, all numeric checkpoints, final adapter reload, curve/cost readiness, and payload safety"
    - "after SFT B acceptance, executor prepares the separate sft-b-evaluation exact_rerun operator checkpoint; after user execution/resume it validates 400 unique paired B results and a 400-resumed/0-generated exact-prefix rerun before E0"
  status: awaiting_operator
```

### Re-audit conclusions before C1

- **Formal training has still not started.** C0 has no status/log and no canonical `B-sft-formal-seed42` run; the new code commit after C0 also makes the old C0 Git provenance guard reject execution.
- The main correctness defect found by this audit was interruption accounting, not the optimizer definition. `KeyboardInterrupt` is now handled analogously to evaluation's existing `BaseException` fail path, preserving attempt/cost provenance without swallowing the interrupt.
- The downstream evidence inventory is sufficient for the current MVP questions: training curves/eval metrics/token counts/CUDA peak/cost provenance remain available from SFT, and evaluation permanently stores the irrecoverable per-problem model outputs and three-layer verification outcomes needed for aggregate metrics and failure analysis. Formal prepared data remains checksummed and joinable by `problem_id` for difficulty/category/test metadata without model reruns.
- One known efficiency limitation remains non-blocking: SFT constructs its train/validation datasets by re-validating visible-only trajectories through the tunneled Piston service before optimizer work, and a resume repeats that validation. This can leave the paid GPU underutilized during pre-training validation, but it does not change the experiment definition or lose evidence, so it was not optimized inside this validation stage.

## C2 — Off-GPU formal prevalidation recovery and fresh manifest-backed SFT B handoff

C1 was manually started and then interrupted after the operator identified that the old implementation was spending paid RTX 4090 time on sequential visible-trajectory Piston validation before Trainer initialization. No optimizer step or Trainer checkpoint was produced. The user explicitly directed a controlled workflow change: perform the exact SFT trajectory validation on the GTX 1660 Ti / local Piston host, bind the result in an immutable manifest, and keep the RTX 4090 path for model load / Trainer / optimizer only. The experiment definition itself remains unchanged.

```yaml
execution_checkpoint:
  version: 1
  checkpoint_id: C2
  stage_id: WP6-d
  task_kind: implementation
  source_plan_commit: eb523bc749e9aa4362790c45bbcf4d604ad7e478
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: 52a1ffffbfd07348483e6981215a39a99581fbf0
  interruption_class: operator
  resume_allowed: true
  operator_gate_id: sft-b-formal
  operator_restart_policy: trainer_checkpoint
  operator_script: /root/sj-tmp/open-r1-code-verifier-outputs/operator/WP6-d/eb523bc749e9aa4362790c45bbcf4d604ad7e478/sft-b-formal/C2/run.sh
  operator_script_sha256: 6d43eb6e18a745f6aea53550d287709b7adc6e14868bb255dc67fbad2addcf0f
  operator_status_file: /root/sj-tmp/open-r1-code-verifier-outputs/operator/WP6-d/eb523bc749e9aa4362790c45bbcf4d604ad7e478/sft-b-formal/C2/status
  operator_log_file: /root/sj-tmp/open-r1-code-verifier-outputs/operator/WP6-d/eb523bc749e9aa4362790c45bbcf4d604ad7e478/sft-b-formal/C2/terminal.log
  operator_prevalidation_manifest: /root/sj-tmp/open-r1-code-verifier-outputs/sft-prevalidation/WP6-d/formal-52a1ffff/WP6-d-formal-sft-prevalidation-52a1ffff.json
  operator_prevalidation_manifest_sha256: 1e6a5a224dbc80374237101b65774bcfd450a80595041631f2239a8b4dba70dc
  quarantine_record: /root/sj-tmp/open-r1-code-verifier-outputs/sft/quarantine/WP6-d/C1-B-sft-formal-seed42-b775102-status130.quarantine.json
  expected_artifacts:
    - /root/sj-tmp/open-r1-code-verifier-outputs/sft/B-sft-formal-seed42/run.json
    - /root/sj-tmp/open-r1-code-verifier-outputs/sft/B-sft-formal-seed42/resolved_config.yaml
    - /root/sj-tmp/open-r1-code-verifier-outputs/sft/B-sft-formal-seed42/environment.json
    - /root/sj-tmp/open-r1-code-verifier-outputs/sft/B-sft-formal-seed42/metrics.jsonl
    - /root/sj-tmp/open-r1-code-verifier-outputs/sft/B-sft-formal-seed42/checkpoints/adapter_config.json
    - /root/sj-tmp/open-r1-code-verifier-outputs/sft/B-sft-formal-seed42/checkpoints/adapter_model.safetensors
  completed_scope:
    - "C1 terminal status is 130. Its failed run closed attempt 1 with gpu_hours=0.3463342955455624 and produced no Trainer checkpoint; the exact old files were SHA256-inventoried and atomically moved to /root/sj-tmp/open-r1-code-verifier-outputs/sft/quarantine/WP6-d/C1-B-sft-formal-seed42-b775102-status130, leaving the canonical B run path free for a fresh C2 run"
    - "result-code commit 52a1ffffbfd07348483e6981215a39a99581fbf0 removes the superseded inline-Piston SFT training path, adds production prevalidate-sft, and makes train-sft require a strictly validated prevalidation manifest; the sealed model/data/hyperparameter definition is unchanged"
    - "formal prevalidation completed on the GTX 1660 Ti at exact validator commit 52a1ffffbfd07348483e6981215a39a99581fbf0 with 2500 train + 300 validation records, all passed, max_token_count=1519 under max_seq_length=1536, Piston config SHA f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e, Python runtime 3.10.0, and pinned package versions matching the 4090 training environment"
    - "the formal manifest was rsynced byte-for-byte from 1660 Ti to the 4090 artifact root; both sides report SHA256 1e6a5a224dbc80374237101b65774bcfd450a80595041631f2239a8b4dba70dc, and the 4090 strict consumer revalidated raw dataset hashes/order/record hashes/model revision/max sequence/Piston definition and returned 2500/300/1519 evidence"
    - "the final result-code commit was proven by a real two-step RTX 4090 manifest-backed SFT smoke at /root/sj-tmp/open-r1-code-verifier-outputs/sft/WP6-d-manifest-smoke-52a1fff; run.json binds git_commit 52a1ffffbfd07348483e6981215a39a99581fbf0, prevalidation_mode=manifest, complete Trainer checkpoint state, finite curve/cost telemetry, and strict completed-adapter reload"
    - "the current project Piston host has been migrated from retired home-piston-01 to 1660ti-wsl. The 1660 Ti local service is the same pinned privileged Piston image/runtime and passes 9/9 acceptance locally; the 4090 reaches it only through SSH local forwarding to 127.0.0.1:2000 using the 1660ti-wsl alias and dedicated SSH key, and a subsequent complete tunneled acceptance passed 9/9. Machine records and validation-machine.json now identify 1660ti-wsl as the current Piston host"
    - "C2 does not contact live Piston during formal SFT preflight or training. It validates the immutable manifest and Piston definition SHA instead, so 4090 optimizer time is not coupled to remote Piston latency. Future Piston-backed evaluation/GRPO operations must use the 1660ti-wsl tunnel"
    - "C2 run.sh is secret-free, bash syntax checked, chmod 0555, SHA256-bound, requires the manifest SHA above, verifies current GPU/BF16/model/data/Base A/quarantine/final smoke/storage and manifest provenance, and preserves trainer_checkpoint resume semantics for any later same-C2 interruption with a valid numeric Trainer checkpoint"
  remaining_scope:
    - "operator runs the exact C2 run.sh in a normal SSH terminal or tmux; Web GPT/CodexPro must not start the formal optimizer command"
    - "after the operator run exits, explicit execution-router resume backend=web validates C2 status/log and the real formal SFT artifacts, including manifest identity, attempts/GPU-hours, finite complete metrics, expected numeric checkpoints near 100/200/300, final adapter reload, curve/cost readiness, and payload safety"
    - "after formal SFT B acceptance, executor prepares the separate sft-b-evaluation exact_rerun operator checkpoint; all future Piston requests for B evaluation and later GRPO/evaluation must terminate at the 1660ti-wsl Piston service"
  status: awaiting_operator
```

### C2 recovery conclusions

- C1 evidence was preserved rather than deleted or overwritten. Its 0.3463342955455624 GPU-hours remain attributable to the failed pre-optimizer attempt.
- Formal SFT trajectory validation is now an off-GPU prerequisite. `train-sft` cannot silently fall back to inline Piston validation and cannot start without the exact manifest.
- The synced formal manifest is immutable on the 4090 (`0444`) and is bound by SHA256 in both C2 report and C2 operator script.
- `home-piston-01` is retired for current/future project operations. Historical bootstrap/machine records were archived before current machine provenance was switched to `1660ti-wsl`.
- The 4090-to-1660 Ti Tailscale path currently uses DERP and is slower than the old host. One initial tunneled batch acceptance experienced a transient transport failure; the targeted batch rerun passed and the subsequent complete 9-test tunneled suite passed. This does not affect C2 SFT because C2 is manifest-only, but later Piston-heavy evaluation/GRPO should retain fail-closed transport handling and operator-visible logs.

## C3 — Formal SFT B acceptance and B evaluation operator handoff

The operator completed C2 successfully. Web GPT + CodexPro resumed only on the RTX 4090 machine, verified the immutable C2 operator identity and the real formal SFT artifacts, and did not access or modify the GTX 1660 Ti code repository. Formal SFT B is accepted; the next long-running gate is the separate 400-problem B evaluation and remains operator-owned.

```yaml
execution_checkpoint:
  version: 1
  checkpoint_id: C3
  stage_id: WP6-d
  task_kind: implementation
  source_plan_commit: eb523bc749e9aa4362790c45bbcf4d604ad7e478
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: 60f4d95cf4624ae2114a7f0188d8b0b43541542c
  interruption_class: operator
  resume_allowed: true
  operator_gate_id: sft-b-evaluation
  operator_restart_policy: exact_rerun
  operator_script: /root/sj-tmp/open-r1-code-verifier-outputs/operator/WP6-d/eb523bc749e9aa4362790c45bbcf4d604ad7e478/sft-b-evaluation/C3/run.sh
  operator_script_sha256: 96c08ed47c36ca4d83fd6b933bd1588a8cf337edbb6ec83d3c22dcbafc354957
  operator_status_file: /root/sj-tmp/open-r1-code-verifier-outputs/operator/WP6-d/eb523bc749e9aa4362790c45bbcf4d604ad7e478/sft-b-evaluation/C3/status
  operator_log_file: /root/sj-tmp/open-r1-code-verifier-outputs/operator/WP6-d/eb523bc749e9aa4362790c45bbcf4d604ad7e478/sft-b-evaluation/C3/terminal.log
  expected_artifacts:
    - /root/sj-tmp/open-r1-code-verifier-outputs/evaluation/B-sft-formal-seed42/run.json
    - /root/sj-tmp/open-r1-code-verifier-outputs/evaluation/B-sft-formal-seed42/resolved_config.yaml
    - /root/sj-tmp/open-r1-code-verifier-outputs/evaluation/B-sft-formal-seed42/environment.json
    - /root/sj-tmp/open-r1-code-verifier-outputs/evaluation/B-sft-formal-seed42/samples/results.jsonl
    - /root/sj-tmp/open-r1-code-verifier-outputs/evaluation/B-sft-formal-seed42/summary.json
    - /root/sj-tmp/open-r1-code-verifier-outputs/evaluation/B-sft-formal-seed42/main_results.csv
  completed_scope:
    - "C2 immutable operator identity verified: run.sh SHA256 6d43eb6e18a745f6aea53550d287709b7adc6e14868bb255dc67fbad2addcf0f, terminal status 0, and terminal.log records all short preflights PASS followed by long-command-end rc=0"
    - "formal B run /root/sj-tmp/open-r1-code-verifier-outputs/sft/B-sft-formal-seed42 is completed and binds git_commit 60f4d95cf4624ae2114a7f0188d8b0b43541542c, exact Qwen/Qwen2.5-Coder-1.5B-Instruct revision, seed 42, manifest-only prevalidation SHA 1e6a5a224dbc80374237101b65774bcfd450a80595041631f2239a8b4dba70dc, validator commit 52a1ffffbfd07348483e6981215a39a99581fbf0, and exact Piston config/executor identities"
    - "Trainer completed global_step=314 at epoch 2.0; metrics.jsonl has 319 finite records including summary, train_loss=0.21536325907726198, peak CUDA allocated=20068083200 bytes, peak CUDA reserved=24620564480 bytes, and C2 gpu_hours=0.5215871774233367"
    - "all numeric Trainer checkpoints are preserved: checkpoint-100, checkpoint-200, checkpoint-300, and checkpoint-314 each contain optimizer.pt, scheduler.pt, rng_state.pth, trainer_state.json, training_args.bin, adapter_config.json, and adapter_model.safetensors with trainer global_step matching the numeric suffix"
    - "formal completed-B strict loader passed; load_training_curve_rows returned 2549 long-form finite scalar rows; build_cost_row succeeded; an independent offline exact-revision BF16 PEFT reload succeeded on cuda:0"
    - "project-owned formal SFT metadata/log artifacts passed payload-safety scanning for hidden-test/reference-solution/problem/completion payload fields and obvious API-token material"
    - "C1 failed pre-optimizer evidence remains preserved unchanged in quarantine with status 130, zero Trainer checkpoints, and gpu_hours=0.3463342955455624; C2 cost is separately attributable and does not overwrite the failed-attempt cost"
    - "C3 B-evaluation target is currently fresh; exact formal evaluation preparation resolves 400/400 unique test problems and the completed B adapter checkpoint without creating the canonical B evaluation run"
    - "C3 immutable exact_rerun script is secret-free, chmod 0555, bash syntax checked, and SHA256-bound. Its start preflight validates the current RTX 4090, completed B/Base A identities, storage, and uses the 4090-side ensure-piston-1660ti-tunnel.sh plus loopback Piston runtime validation; it does not access the 1660 Ti code repository"
  remaining_scope:
    - "operator runs the exact C3 run.sh in a normal SSH terminal or tmux; Web GPT/CodexPro must not start the 400-problem B evaluation"
    - "C3 exact_rerun uses the project's strict initialize_or_resume_run contract for any existing B evaluation prefix; an environment/transport interruption may reuse the same immutable script without changing checkpoint HEAD, while identity drift fails closed"
    - "after the operator run exits, explicit execution-router resume backend=web validates status/log, 400 unique B results with the exact Base A problem set and evaluation/Piston/seed/checkpoint identities, required per-sample payload fields and non-sample payload safety, finite summary/main results, then runs only the short 400-resumed/0-generated exact-prefix readback and A/B analysis pairing gates"
    - "only after B evaluation acceptance and all final executor-owned WP6-d acceptance gates may completed E0 be appended; do not enter C/D work in this stage"
  status: awaiting_operator
```

### C3 acceptance conclusions

- C2 formal SFT B is accepted as a real RTX 4090 training result. The actual Trainer schedule resolved to 314 optimizer steps; the earlier planning estimate of approximately 313 was not treated as a hard identity field.
- No production code/config/test change was required during this resume. `result_code_commit` for C3 is therefore the committed C2 checkpoint HEAD `60f4d95cf4624ae2114a7f0188d8b0b43541542c`; C3 itself is a docs-only operator checkpoint.
- The formal B evaluation remains unstarted. Its canonical path does not exist at C3 creation time, so this checkpoint does not pre-create or contaminate evaluation evidence.
- All future Piston-backed work in this stage remains bound to the current `1660ti-wsl` service through the 4090 loopback tunnel. The 1660 Ti project repository was not accessed or modified during this resume.

## C4 — Interrupted C3 quarantine and generation/verification decoupling

The operator interrupted C3 after the real B evaluation exposed a throughput defect in the execution architecture rather than a model or verifier failure. The old evaluator serialized GPU generation with remote Piston verification, leaving the RTX 4090 idle for most wall-clock time. The partial C3 run was preserved as failed evidence, then the evaluation control plane was minimally repaired so formal generation can complete on the 4090 before any Piston work is performed. The evaluation problem set, model/checkpoint, deterministic decoding, three test layers, Piston definition, per-problem verdict schema, metrics, and bootstrap definitions are unchanged.

```yaml
execution_checkpoint:
  version: 1
  checkpoint_id: C4
  stage_id: WP6-d
  task_kind: implementation
  source_plan_commit: eb523bc749e9aa4362790c45bbcf4d604ad7e478
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: 5107f03d58380e0260671142c062604accf80ff6
  interruption_class: operator
  resume_allowed: true
  operator_gate_id: sft-b-evaluation
  operator_restart_policy: exact_rerun
  operator_script: /root/sj-tmp/open-r1-code-verifier-outputs/operator/WP6-d/eb523bc749e9aa4362790c45bbcf4d604ad7e478/sft-b-evaluation/C4/run.sh
  operator_script_sha256: 3ce22292c7e9b8d759516f1c870088733f9d7035c48f7edcb9e23d5f5e68291d
  operator_status_file: /root/sj-tmp/open-r1-code-verifier-outputs/operator/WP6-d/eb523bc749e9aa4362790c45bbcf4d604ad7e478/sft-b-evaluation/C4/status
  operator_log_file: /root/sj-tmp/open-r1-code-verifier-outputs/operator/WP6-d/eb523bc749e9aa4362790c45bbcf4d604ad7e478/sft-b-evaluation/C4/terminal.log
  quarantine_record: /root/sj-tmp/open-r1-code-verifier-outputs/evaluation/quarantine/WP6-d/C3-B-sft-formal-seed42-interrupted-156rows.quarantine.json
  quarantine_record_sha256: 7a2934cf13d402be36c2397ce08c3fd649afd0a5f8304fb064769eb988448d68
  expected_artifacts:
    - /root/sj-tmp/open-r1-code-verifier-outputs/generation/B-sft-formal-seed42/run.json
    - /root/sj-tmp/open-r1-code-verifier-outputs/generation/B-sft-formal-seed42/resolved_config.yaml
    - /root/sj-tmp/open-r1-code-verifier-outputs/generation/B-sft-formal-seed42/environment.json
    - /root/sj-tmp/open-r1-code-verifier-outputs/generation/B-sft-formal-seed42/metrics.jsonl
    - /root/sj-tmp/open-r1-code-verifier-outputs/generation/B-sft-formal-seed42/stdout.log
    - /root/sj-tmp/open-r1-code-verifier-outputs/generation/B-sft-formal-seed42/stderr.log
    - /root/sj-tmp/open-r1-code-verifier-outputs/generation/B-sft-formal-seed42/samples/generations.jsonl
  completed_scope:
    - "C3 was interrupted by the operator after 156/400 durable evaluation rows. The old run closed with run.json status=failed and gpu_hours=0.3259985226868755; its rows SHA256 is ee6d93a9917921e502d14c21c6b79192a1d06f6cc74aaf1e34d9697117a4d622. Because Ctrl+C terminated the old outer script before its final write, C3 has no operator status file; terminal.log remains preserved"
    - "the exact partial C3 evaluation directory was atomically moved out of the canonical B path to /root/sj-tmp/open-r1-code-verifier-outputs/evaluation/quarantine/WP6-d/C3-B-sft-formal-seed42-interrupted-156rows and is indexed by the immutable quarantine record above; no partial row or prior GPU cost was deleted or reused as new formal B evidence"
    - "result-code commit 5107f03d58380e0260671142c062604accf80ff6 introduces generate-eval -> verify-eval -> aggregate-eval. generate-eval persists exact-prefix deterministic completions without constructing/contacting Piston; verify-eval reuses the existing evaluate_completion/verify_completion contracts with bounded local-Piston workers while preserving canonical problem order; aggregate-eval remains the existing deterministic aggregator"
    - "the transferable generation contract is path-independent but content-strict: model/revision/checkpoint, seed, split, decode settings, ordered dataset identity, Piston YAML SHA, generation rows SHA, and source code/dependency provenance are bound. Different absolute dataset/Piston paths on a later verification machine are allowed only when their semantic/content identities match"
    - "staged-vs-one-process equivalence, exact-prefix generation/verification resume, crash-accounting reconciliation, transfer-path portability, tamper rejection, bounded worker concurrency with ordered persistence, payload safety, and code/dependency drift fail-closed behavior are covered by the new staged tests"
    - "final repair regression is green on the 4090: make lint passed; the full suite passed 908 tests with only 3 expected real-Piston skips when run against the exact cached 1.5B snapshot; make test-gpu passed 3/3; and the explicit real current 1660ti-wsl Piston acceptance passed 9/9"
    - "C4 run.sh is chmod 0555, bash -n clean, SHA256-bound, and statically contains no ensure-piston, runtime API, curl, or ssh invocation. It validates only the pinned Piston YAML SHA as part of the future verification definition; the long command is generation-only"
  remaining_scope:
    - "operator runs the exact C4 run.sh in a normal SSH terminal or tmux. Web GPT/CodexPro must not start the 400-problem formal generation command"
    - "C4 exact_rerun validates any existing generation prefix and resumes only missing durable generation rows; the EXIT/INT/TERM handling also atomically writes operator status on interruption"
    - "after C4 exits, explicit execution-router resume backend=web must validate status/log plus 400 unique completed generation rows, exact model/revision/checkpoint/seed/dataset/order/decode/Piston-definition identities, finite generation latency/token telemetry, bundle/environment hashes, GPU-hours accounting, payload safety, and a short 400-resumed/0-generated no-op readback"
    - "only after the 4090 generation bundle is accepted should the exact code/dependency commit, formal data, and bundle be transferred to the 1660 Ti for local-Piston verify-eval and aggregate-eval. This execution conversation must not access or modify the 1660 Ti code repository while its separate workflow refactor is active"
    - "after verified B artifacts are synced back and strict A/B pairing acceptance passes, WP6-d may close E0; do not enter C/D work in this stage"
  status: awaiting_operator
```

### C4 repair conclusions

- The C3 interruption is treated as a preserved formal attempt, not as reusable B evidence. New formal B generation starts from 0/400 under the repaired staged architecture.
- The expensive/non-reproducible model output is now durably captured before CPU/Piston verification. This removes remote Piston latency from paid 4090 wall time without changing any verifier result semantics.
- The generation bundle does not carry hidden-test payloads. Verification remains the only phase that reads the three test layers, and only the verification machine needs the live Piston service.
- The current C4 generation target is fresh. No generation bundle exists at checkpoint creation time.
- No 1660 Ti project repository was accessed or modified during this repair; only its already-configured Piston service was used for the explicit 9/9 sandbox regression.

## C5 — Accepted staged B generation; verification transfer deferred

C4 was executed by the operator and accepted from its real persistent artifacts. The expensive 4090 generation phase is complete. The remaining B work is CPU/Piston verification plus aggregation on the 1660 Ti side, but this 4090 execution context is explicitly isolated from the 1660 Ti project repository while its independent workflow/infrastructure refactor is active. No transfer or verification command was attempted against that repository.

```yaml
execution_checkpoint:
  version: 1
  checkpoint_id: C5
  stage_id: WP6-d
  task_kind: implementation
  source_plan_commit: eb523bc749e9aa4362790c45bbcf4d604ad7e478
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: 41abf31618372445ba2233f386c08417b4407436
  interruption_class: environment
  resume_allowed: true
  failed_command: "not executed: transfer generation bundle/code identity to the protected 1660 Ti project environment and run verify-eval"
  blocker: "the 1660 Ti project repository is under an independent workflow/infrastructure refactor and must not be read, modified, or synchronized from this 4090 execution conversation until that isolation is released"
  completed_scope:
    - "C4 operator status is 0; terminal.log records all short preflights passing, generated 400 evaluation prompts with resumed=0/generated=400, and long-command-end rc=0"
    - "completed generation run /root/sj-tmp/open-r1-code-verifier-outputs/generation/B-sft-formal-seed42 has status=completed, completed_records=400, total_problems=400, model Qwen/Qwen2.5-Coder-1.5B-Instruct revision 2e1fd397ee46e1388853d2af2c993145b0f1098a, formal B checkpoint binding, seed 42, and pinned Piston-definition SHA f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e"
    - "strict project loader accepted all 400 generation rows; IDs are unique and exactly match the formal test problem order and Base A problem order; records SHA256=24cdd44976e7c8ff50934cb636ff7128497799c84f7b3739be89314fe477adfc and evaluation-contract SHA256=119fe22ee3983394ecae036b9ddc6a741766b07f3f09244765aa510679322a72"
    - "generation telemetry is complete and finite: 400 metrics rows, cumulative generation latency 2738824.847012933 ms, 80456 completion tokens, hit_max_new_tokens count 0, and persisted generation GPU-hours 0.7607846797258146"
    - "non-sample generation artifacts are completion-payload safe, and a strict completed-bundle no-op readback returned resumed=400/generated=0 without model generation"
  remaining_scope:
    - "after the 1660 Ti repository isolation is released, transfer the exact generation bundle plus the exact code/dependency identity and formal prepared data required by the cross-machine contract; do not regenerate any B completion"
    - "on the 1660 Ti verification environment, run verify-eval for B-sft-formal-seed42 through the local loopback Piston service with bounded workers, preserving exact-prefix resume and canonical result ordering"
    - "run aggregate-eval after 400/400 verification rows complete, then sync the completed B evaluation artifacts back for strict run/result/summary/payload/GPU-hours/provenance acceptance and A/B pairing readiness"
    - "after final B acceptance, run any remaining short closeout gates required by the sealed plan, append completed E0, and stop before reviewer-ex; do not enter C/D in WP6-d"
  status: interrupted
```
