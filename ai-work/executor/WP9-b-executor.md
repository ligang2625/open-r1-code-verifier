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

## Review Round 1 repair execution (E1)

### Routing and provenance

- Task kind: `repair` for committed WP9-b Review Round 1 (`a218d7b`).
- Source routing remained `mode=multi` with three review-defined workstreams; Web GPT + CodexPro executed them as `serialized_multi` in the existing `feat/wp9-b` stage worktree.
- Effective repair scope was exactly `R1-M1`, `R1-M2`, `R1-M3`, and `R1-M4`; no plan/review/proceedings/spec/third-party changes and no target-GPU/formal run were introduced.
- Stage profile remained `development`; all evidence below is fixture/mock/CPU/development evidence only.

### Repair commits and issue mapping

- `53f5d42` `fix(wp9-b): stratify calibrated active selection` — R1-M1. Producer and strict checker share deterministic overlap-bucket selection with class priority plus source+difficulty largest-remainder allocation, stable ordering, fail-closed diagnostics, unequal-strata coverage, and selection-tamper rejection.
- `6bd6d8d` `fix(wp9-b): prevalidate concurrent reward batches` — R1-M3. Every aligned completion/test/function/resource contract is prevalidated before executor factory/thread work; a late invalid item proves zero factory/execute side effects.
- `b8744b9` `fix(wp9-b): bind refresh evidence identities` — R1-M2/R1-M4. Refresh binding requires strict active-pool recomputation plus a reconstructable throughput report; eval candidates bind normalized resolved config/problem order and GRPO candidates bind complete portable B config/dependency identity.
- `8c772a6` `style(wp9-b): normalize repair formatting` — Ruff-format-only closeout; no semantic behavior changed.

### Verification evidence

- Calibration selector + production-shadow integration after R1-M1: `14 passed`.
- Concurrent reward unit suite after R1-M3: `38 passed`.
- Shared throughput/binding/GRPO/CLI/integration repair set: `200 passed`.
- Exact sealed-plan focused suite from WP9-b plan section 6.1: `322 passed`.
- Additional review-specific reward/throughput/binding regression set: `49 passed`.
- `make lint`: PASS — Ruff check, Ruff format check, and mypy all passed for `134` source/test files.
- `make test`: PASS — `1162 passed, 3 skipped` in `114.42s`; the three skips are the repository's existing opt-in real-Piston cases requiring `CODE_VERIFIER_RUN_PISTON=1`.
- `git diff --check`: PASS before the final code-format commit and again on the final report diff; the stage working tree was clean before appending this execution record.

### Repair result

- R1-M1 is closed by strict source+difficulty stratified allocation in both overlap buckets and checker recomputation.
- R1-M2 is closed by strict calibration source revalidation plus benchmark-manifest snapshot/reconstruction; shallow self-authored calibration/benchmark documents cannot construct a refresh binding.
- R1-M3 is closed by whole-batch side-effect-free verifier-input prevalidation before concurrent executor creation.
- R1-M4 is closed by strict generation resolved-config/problem-order identity and complete parent-B config/dependency identity for GRPO throughput candidates.
- No formal worker count, active-pool research result, C2/D2 checkpoint, 24GB execution, or 400-problem result is claimed; those remain WP9-c+ validation responsibilities.

```yaml
execution_record:
  version: 1
  stage_id: WP9-b
  execution_id: E1
  task_kind: repair
  source_plan_commit: 23e43b78fd31bfe051b29d38ef9e9d0f43e20590
  source_review_round: 1
  source_review_commit: a218d7b8894b5504c2e750e558e0dcaf83c14cc2
  repair_issue_ids:
    - R1-M1
    - R1-M2
    - R1-M3
    - R1-M4
  result_code_commit: 8c772a6f4cc340be4bd263d6e82c16b03142ebfe
  execution_backend: web_codexpro
  effective_execution_mode: serialized_multi
  status: completed
```

## Review Round 2 repair execution (E2)

### Routing and provenance

- Task kind: `repair` for committed WP9-b Review Round 2 (`b0ce11835e3955427d6e4e8e9d3693b2ba4d7625`).
- Source/effective routing was `mode=multi`: three local Codex workers owned the review-defined, mutually disjoint calibration-strata, strict-GRPO-benchmark-source, and verification-preflight-boundary lanes. Workers did not commit; the coordinator integrated, corrected, tested, and committed each lane separately.
- Effective repair scope was exactly `R1-M1`, `R1-M4`, and `R2-M1`. There was no user scope override or routing deviation. Stage profile remained `development`, control-plane and target hardware remained `GTX 1660 Ti (6GB)`, and all evidence remained `engineering`.
- No real frozen-B calibration, optimizer-based SFT/GRPO, C2/D2, 24GB/4090 command, or formal 400-problem evaluation was run or claimed.
- Result code commit captured before this report: `a15622eea69aafc6374f60252c2a876b5f70b56b`.

### Repair commits and issue mapping

- `d08d332` `fix(wp9-b): allocate whole-bucket strata` — `R1-M1`. Each overlap/non-overlap bucket now computes source+difficulty largest-remainder targets from its complete eligible population before calibration-class preference. Each stratum selects dual-informative rows first and uses deterministic Public/Hidden single-arm fallback only within the global minimum/caps. Producer and strict checker share the allocator; correlated mixed-class strata, input-order determinism, unsatisfiable diagnostics, and checker tamper rejection are covered.
- `aa348c8` `fix(wp9-b): centralize verifier preflight` — `R2-M1`. Verification now exposes one public, side-effect-free normalized request preflight consumed by both `verify_completion()` and concurrent rewards. Reward no longer imports Parsing or verifier-private helpers and never parses code itself. The late-invalid-item regression still proves zero executor-factory and execute side effects for the entire batch.
- `a15622e` `fix(wp9-b): validate formal GRPO sources` — `R1-M4`. Formal GRPO throughput reconstruction now uses the canonical strict completed-GRPO loader and completed-B parent chain, then revalidates current k=8 config/dependency/runtime identity, refresh calibration/pool/binding, reward/group/rollout counts and cross-record identities, and source artifact hashes. Shallow sources are legal only when explicitly marked `engineering_fixture`; they cannot enter a formal report. The coordinator additionally corrected selected-arm Public/Hidden binding and allowed bounded benchmark subsets while retaining exact eight-sample group consistency.

### Verification evidence

- Calibration selector + production-shadow integration: `16 passed`.
- Verification/reward unit and WP4 integration regression: `77 passed`.
- Throughput/GRPO source regression: `10 passed`.
- Combined review-repair regression set: `103 passed`.
- Exact sealed-plan focused file list, including the two new tests: `324 passed`.
- `make lint`: PASS — Ruff check, Ruff format check, and strict mypy passed for `134` source/test files.
- `make test`: PASS — `1169 passed, 3 skipped` in `32.26s`; all three skips are the existing opt-in real-Piston tests requiring `CODE_VERIFIER_RUN_PISTON=1`. GPU smoke tests ran and passed.
- `git diff --check`: PASS. Explicit staging contained only the intended lane files; `.ai-bridge/**` remained untracked and unstaged.
- Diagnostic note: `rtk`-wrapped pytest processes could not initialize CUDA/NVML and made existing fake-GRPO tests fail at `gpu_count=0`; direct stage `.venv`/Makefile commands, which are the sealed acceptance authority, saw the GTX 1660 Ti and produced the passing results above. No repository change or test weakening was made for this wrapper behavior.

### Repair result and boundary

- `R1-M1` is closed by whole-bucket source+difficulty allocation followed by constrained class preference/fallback, with deterministic checker recomputation and correlated-strata regressions.
- `R1-M4` is closed by a strict formal completed-GRPO/B/calibration/runtime/artifact source path plus an explicitly non-formal engineering fixture path and forged-source rejection.
- `R2-M1` is closed by restoring Parsing ownership to Verification and sharing one public side-effect-free preflight with Reward concurrency.
- No formal active-pool composition, runtime worker recommendation, throughput number, zero-variance result, C2/D2 checkpoint, or research metric is claimed. Those remain WP9-c+ validation responsibilities.

```yaml
execution_record:
  version: 1
  stage_id: WP9-b
  execution_id: E2
  task_kind: repair
  source_plan_commit: 23e43b78fd31bfe051b29d38ef9e9d0f43e20590
  source_review_round: 2
  source_review_commit: b0ce11835e3955427d6e4e8e9d3693b2ba4d7625
  repair_issue_ids:
    - R1-M1
    - R1-M4
    - R2-M1
  result_code_commit: a15622eea69aafc6374f60252c2a876b5f70b56b
  execution_backend: local_codex
  effective_execution_mode: multi
  status: completed
```

## Review Round 4 repair execution (E3)

### Routing and provenance

- Task kind: `repair` for WP9-b Review Round 4, consumed as an attributable **uncommitted review draft** because the user explicitly requested execution against the latest review report. The draft identifies `source_execution_id=E2`, `reviewed_head_commit=c4cf62701c84ac2edbf32842dd85a2ffadb2b06a`, and `conclusion=needs_repair`; it is not represented as a committed review provenance anchor.
- Effective repair scope is exactly `R1-M4` plus the user-narrowed `R3-M1`. Source routing is `mode=single`, and Web GPT + CodexPro executed the integrated repair as `effective_execution_mode=single` in the existing `feat/wp9-b` worktree.
- The stage remains `development` / `engineering` on the GTX 1660 Ti control plane. No real frozen-B calibration, real k4/k8 measurement, 24GB/4090 training, C2/D2, or formal 400-problem evaluation was run or claimed.
- Result code commit captured before this report: `e3f9b97aa331714f11ff6f96b2065bc68a7da7f1`.

### Repair result

- `R1-M4` is closed by a separate pre-freeze `GRPOBenchmarkBinding` that binds completed-B/calibration/active-pool/runtime identity without consuming the not-yet-created final benchmark report. Public and Hidden strict-source reconstruction now derive and hash the distinct Public/Hidden active-pool paths correctly, while final refresh/C2-D2 binding remains k=8-only and still requires the final benchmark report plus selected worker.
- Formal k=8 verifier worker candidates now use explicit `k8_candidate` benchmark identity and support the frozen `[8,16,32,64]` worker sweep without binding scientific identity to the candidate worker being compared. The CLI exposes `--benchmark-role` and proves a pre-freeze k=8 candidate can bootstrap without `--benchmark-report`; ordinary final k=8 still fails closed when that report is missing.
- Narrowed `R3-M1` is closed by an explicit strict `k4_diagnostic` role beside primary k=8 evidence. The diagnostic requires the same B/pool/order/seed/reward/runtime/sampling identity except for group size and directly attributable work counts, derives artifact-backed wall-clock/token/verifier/OOM/retry/error/zero-variance/informative-group/GPU-hour metrics, and emits reconsideration warnings without selecting k=4 as the primary protocol.
- Positive strict-source regressions cover actual fixture-backed Public k8, Hidden k8, and k4 diagnostic runs; negative regressions reject reward-arm, worker/runtime, scientific-identity, active-order, and problem-order confounds.

### Verification evidence

- Focused affected regression set including CLI/bootstrap, strict-source, throughput, refresh binding, and GRPO runtime: `112 passed`.
- Sealed-plan focused unit/integration list plus the new R4 contract regressions: `349 passed`.
- `make lint`: PASS — Ruff check, Ruff format check, and strict mypy passed for `135` source/test files.
- `make test`: PASS — `1184 passed, 3 skipped` in `114.15s`; all three skips are the existing opt-in real-Piston tests requiring `CODE_VERIFIER_RUN_PISTON=1`.
- Both primary and stage transport guards reported no tracked `.ai-bridge` paths. The code commit explicitly staged only the eight implementation/test files; the pre-existing Review Round 4 draft remained unstaged and unmodified by the executor.
- Sealed plan, both project specifications, `proceedings.md`, and `third_party/open-r1` were not modified.

```yaml
execution_record:
  version: 1
  stage_id: WP9-b
  execution_id: E3
  task_kind: repair
  source_plan_commit: 23e43b78fd31bfe051b29d38ef9e9d0f43e20590
  source_review_round: 4
  source_review_commit: null
  repair_issue_ids:
    - R1-M4
    - R3-M1
  result_code_commit: e3f9b97aa331714f11ff6f96b2065bc68a7da7f1
  execution_backend: web_codexpro
  effective_execution_mode: single
  status: completed
```
