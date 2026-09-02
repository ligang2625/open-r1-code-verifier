# WP9-b Execution Report

## Provenance and routing

- Stage: `WP9-b`
- Task kind: `implementation`
- Sealed plan: `ai-work/planner/WP9-b-plan.md`
- Source plan commit: `23e43b78fd31bfe051b29d38ef9e9d0f43e20590`
- Stage branch/worktree: `feat/wp9-b` / `.worktrees/wp9-b`
- Source routing: `mode=single`, difficult serial implementation stage.
- Execution backend completing this run: `web_codexpro`; effective execution mode: `single`.
- Stage profile: `development`; control-plane / target hardware `GTX 1660 Ti (6GB)` plus CPU and fixture/mock executors; evidence class `engineering`.
- This execution was resumed from the existing WP9-b worktree after the prior local agent exhausted its quota. Existing attributable commits, dirty diff, focused tests, and the sealed plan were used to continue rather than restarting completed work.
- Result code commit captured before this report: `f25e3e382d1e31e9475cd14aac5f4989e8360055`.
- Transport guard remained clean: `.ai-bridge/**` is untracked. `PROJECT_SPEC_Open-R1_CodeVerifier.md`, `PROJECT_SPEC_GRPO_Refresh.md`, `proceedings.md`, the sealed plan, and `third_party/open-r1` were not modified by the stage implementation.

## Implementation commits

- `c5674cd` `feat(wp9-b): add batched and sampled generation`
- `ca03e2d` `feat(wp9-b): add calibration artifact pipeline`
- `4ac67a0` `feat(wp9-b): batch staged evaluation`
- `b09b5e6` `feat(wp9-b): add refresh configs and benchmarks`
- `afc786c` `feat(wp9-b): parallelize GRPO reward verification`
- `a2f5afd` `test(wp9-b): enforce atomic reward logs`
- `79ee9ac` `feat(wp9-b): complete refresh engineering closeout`
- `f25e3e3` `fix(wp9-b): harden refresh evidence contracts`

## Implemented engineering contract

### Calibration and active-pool foundation

- Added the tracked refresh calibration protocol and explicit CLI boundaries for Public-safe prompt preparation, frozen-B generation, Public/Hidden scoring of the exact same completion bytes, and deterministic active-pool construction.
- Production calibration config is frozen to `8 + 8` sampling, temperature `0.8`, top-p `0.95`, max-new-tokens `512`, active-pool size `3000`, SFT overlap target `0.075`, hard max `0.15`, dual-informative minimum `0.70`, and `0.15` caps for each single-arm informative class. Test-only small configs remain explicitly separated through the engineering protocol.
- Initial both-zero problems are the only retry-eligible IDs; retry scores must use the exact same frozen-B identity and sample indices `8..15`. Cumulative 16-sample dual-uninformative problems are classified hard; dual-saturated problems are easy; quality-gate-required problems remain excluded with precedence.
- The active-pool producer and strict checker bind current WP9-a root/order/Public/Hidden identities, calibration input, initial/retry score manifests, frozen-B identity, every output artifact SHA, and active ordering.
- Strict readback independently recomputes reward means/stds, informativeness flags, calibration class, full-pass counts, retry disposition, deterministic selection, class caps/minimums, SFT overlap, reserve/hard/easy manifests, Public/Hidden training rows, composition, classification report, and record/order hashes. Reviewer-style self-consistent tampering is rejected even when modified artifact/root hashes are updated together.

### Refresh k=8 GRPO and reward runtime

- Historical `configs/grpo/public.yaml` / `hidden.yaml` remain k=4. New refresh Public/Hidden configs are k=8 and paired on scientific settings other than reward source and dataset path.
- Refresh `train-grpo` requires a calibration manifest, artifact-derived benchmark report, and its selected verification-worker count. Non-k8 legacy runs reject refresh binding arguments and retain serial reward verification.
- Refresh binding is derived from artifact bytes rather than caller-supplied hashes and binds the active Public/Hidden dataset hashes, active order, calibration manifest, benchmark report, and verification workers into the newer paired-definition identity.
- Concurrent GRPO verification is bounded and ordered. Worker-local executor/circuit-breaker state is used while shared retry/transport telemetry remains synchronized. A batch containing an infrastructure failure aborts before optimizer update and before normal reward log append.
- Refresh group evidence adds calibration class, test/total means/stds, all-correct/all-zero/zero-variance signals and verifier time while preserving legacy aliases/schema behavior for historical k=4 runs.
- Bounded rolling telemetry tracks all-correct/all-zero/total-zero-variance fractions, mean/median reward std, effective non-zero-variance group count, and verifier wall time.
- Pinned Trainer runtime instrumentation retains generation/rollout/no-grad protections and adds refresh-only backward and optimizer timing alongside step timing. Missing required pinned hooks fail closed for refresh runs.

### Evaluation and throughput engineering

- Deterministic staged generation supports batch sizes `{1,2,4,8,16}` with v2 batch provenance, exact-prefix resume, partial final batches, and backward-compatible completed v1 bundle loading.
- `verify-eval` supports workers through `64` while preserving ordered result append and generation provenance binding.
- Artifact-derived throughput selection covers deterministic generation parity, evaluation verification worker candidates, GRPO verification worker candidates, and the optional same-GPU Public/Hidden schedule decision. Generation/output drift, verification result drift, reward/group drift, or infrastructure instability disqualifies candidates.
- Same-GPU concurrent C2/D2 scheduling is recommended only when measured concurrent wall time is `<= 0.85 * sequential_wall` (at least 15% gain) and scientific/reward/group parity plus infrastructure stability all hold; otherwise recommendation is sequential.
- Production generation and refresh GRPO persist injectable periodic GPU utilization/memory evidence using `nvidia-smi`. Sampling failures are recorded as `unavailable`, never fabricated as zero. Formal generation/GRPO throughput selection fails closed when required GPU utilization evidence is missing or unavailable.
- Evaluation verification persists real host CPU/max-RSS evidence without pretending a verifier host has GPU utilization. Throughput reports derive mean/P95 verifier latency and validate host resource telemetry for formal verification-worker selection.

## Production-shadow engineering evidence

`tests/integration/test_wp9b_refresh_engineering.py` reuses the WP9-a production-shadow fixture and exercises an engineering-only end-to-end path:

1. WP9-a Public/Hidden views -> Public-safe calibration input bundle with hidden/reference payload exclusion.
2. Deterministic fake frozen-B k=8 completions -> same completion bytes scored by concurrent Public/Hidden verifier paths.
3. Calibrated active pool -> strict readback, class/order/hash and Public/Hidden isolation checks.
4. Artifact-derived generation and GRPO worker benchmark report -> refresh binding.
5. Legacy k4 and refresh k8 config identities are checked together.
6. Root/hash-only tamper plus self-consistent derived-stat, training-view, and composition tampering are all rejected by independent recomputation.

Additional unit regressions cover retry/hard/easy/quality disposition, delayed concurrent reward parity and infra abort, rolling/backward/optimizer timing, runtime-utilization available/unavailable semantics, formal telemetry rejection, evaluation worker-64 parity with mean/P95 latency, GRPO worker parity, and the 14% vs 15% same-GPU recommendation boundary.

All fixture/mock/synthetic results above are engineering evidence only. They are not model-quality measurements and are not valid formal WP9-c runtime recommendations.

## Validation and closeout evidence

- Final sealed-plan focused unit/integration suite (including the additional telemetry/binding regressions): `332 passed`, `0 failed`.
- `make lint`: PASS. Ruff check passed, Ruff format check passed, strict mypy passed for `134` source/test files.
- `make test`: PASS — `1155 passed, 3 skipped`, `0 failed` in `114.11s`. The three skips are the repository's existing opt-in real-Piston cases requiring `CODE_VERIFIER_RUN_PISTON=1`.
- The repository GPU smoke tests ran as part of `make test` and passed on the development machine.
- Real Piston was not required as a WP9-b development hard gate by the sealed plan; no skipped Piston check is reported as a fabricated PASS.
- `git diff --check` passed before the result-code commit.
- Final scope audit from the plan seal showed no modifications to project specifications, `proceedings.md`, the sealed planner artifact, or `third_party/open-r1`.

## Known limitations and validation boundary

- No real frozen-B calibration generation was executed in WP9-b.
- No optimizer-based SFT/GRPO training, C2/D2 checkpoint, or 4090 scientific run was executed.
- No formal worker count, evaluation batch size, paired same-GPU scheduling mode, real zero-variance rate, throughput value, GPU utilization value, or research metric is claimed from the engineering fixtures.
- No formal 400-problem refresh evaluation was run.
- These real numerical/target-GPU gates remain WP9-c+ validation work under the portable operator boundary and must consume the exact committed code/protocol rather than modifying experimental definitions during validation.

```yaml
execution_record:
  version: 1
  stage_id: WP9-b
  execution_id: E0
  task_kind: implementation
  source_plan_commit: 23e43b78fd31bfe051b29d38ef9e9d0f43e20590
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: f25e3e382d1e31e9475cd14aac5f4989e8360055
  execution_backend: web_codexpro
  effective_execution_mode: single
  status: completed
```
