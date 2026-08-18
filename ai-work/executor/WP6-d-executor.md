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
