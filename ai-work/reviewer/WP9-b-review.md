# WP9-b Review

## Review Round 1

```yaml
review_record:
  version: 1
  stage_id: WP9-b
  review_round: 1
  source_execution_id: E0
  reviewed_head_commit: 0d61057fb15d8a47f3b50fb4f3dd4b32570997ac
  conclusion: needs_repair
```

### Effective contract / provenance

- Sealed stage contract remains `stage_profile=development`, `control_plane_hardware=GTX 1660 Ti (6GB)`, `target_hardware=GTX 1660 Ti (6GB)`, `evidence_class=engineering`, `development_terminal=false`. No 24GB/formal-calibration/C2-D2/400-eval evidence is required or claimed in this review round.
- Review ran in the plan-declared `feat/wp9-b` worktree `/home/dzy/open-r1-code-verifier/.worktrees/wp9-b`.
- Latest completed execution is `E0`. The Git commit that submits `ai-work/executor/WP9-b-executor.md` is `0d61057fb15d8a47f3b50fb4f3dd4b32570997ac`, equal to the reviewed HEAD; there is no post-report continuation to attribute.
- `git ls-files .ai-bridge` is empty. The stage working tree was clean before review and remained clean after independent tests; executor scope did not modify project specs, proceedings, or `third_party/open-r1`.

### Independent verification

- Exact sealed-plan focused suite: `319 passed`.
- Additional reviewer regression set covering concurrent rewards, runtime telemetry, throughput verification/GRPO, refresh binding, and rolling telemetry: `50 passed`.
- `make lint`: PASS (`ruff check`, `ruff format --check`, `mypy`).
- `make test`: PASS, `1155 passed, 3 skipped`; the three skips are the repository's existing opt-in real-Piston tests.
- Executor's full-suite claim (`1155 passed, 3 skipped`) is independently reproduced. The report's separate `332 passed` expanded focused-suite count is not directly reproducible as an exact command because that expanded file list is not recorded, but all sealed focused tests and the named added regression areas pass independently.

### Findings

#### R1-M1 — Active-pool selection omits the sealed `source+difficulty` stratified allocation

The sealed active-selection protocol requires each overlap/non-overlap quota bucket to apply class priority and then `source+difficulty` strata largest-remainder allocation with stable-hash ordering, preserving the frozen composition while maximizing dual-informative coverage (`ai-work/planner/WP9-b-plan.md:354-358`). `build_calibrated_active_pool()` instead creates only two overlap buckets and globally sorts each bucket by `(calibration_class priority, stable hash)` before slicing the quota (`src/code_verifier/training/calibration.py:1215-1252`). `check_calibrated_active_pool()` recomputes that same unstratified algorithm (`src/code_verifier/training/calibration.py:1582-1624`), so readback cannot detect the protocol omission.

Impact: a source/difficulty stratum can be over- or under-selected solely because of the global stable-hash order even when a valid largest-remainder allocation exists. This changes the frozen active-pool protocol and can alter the scientific composition consumed by C2/D2. The current tests use effectively non-discriminating source strata and do not exercise this boundary.

Required repair: implement the sealed source+difficulty largest-remainder allocation inside both overlap buckets while preserving class priority/caps and stable tie-breaking; make unsatisfiable constraints fail closed with the requested class/source/difficulty/overlap population diagnostics; add regression coverage with multiple unequal source+difficulty strata and checker recomputation/tamper cases.

#### R1-M2 — Refresh training binding accepts shallow, hand-crafted calibration/benchmark documents instead of strict checked artifacts

The sealed plan requires the refresh binding loader to be constructed from `check_calibrated_active_pool()` plus a strict throughput report, not from caller-supplied/trusted digest fields (`ai-work/planner/WP9-b-plan.md:392-411`). `load_grpo_refresh_binding()` never calls `check_calibrated_active_pool()` and has no refresh/reference dataset inputs needed to do so. It accepts any calibration JSON with completed status, an allowed schema/evidence string, `active_order_sha256`, and two training hashes, then checks only those two files (`src/code_verifier/training/grpo.py:1504-1541`). For the benchmark side it accepts any JSON with the version/evidence string and matching `selected_grpo_verification_workers` (`src/code_verifier/training/grpo.py:1542-1558`); it does not verify the benchmark report's required sections/source-artifact lineage or recompute its selection.

This behavior is codified by `tests/unit/training/test_grpo_refresh_binding.py:21-71`, where a deliberately minimal calibration manifest and minimal three-field benchmark report are sufficient to construct a binding. Such documents would fail the full active-pool checker and do not prove any benchmark run existed.

Impact: on a later 24GB formal run, k=8 GRPO can pass its preflight with a self-authored `formal_calibration` manifest and `formal` benchmark report whose training hashes/worker number are internally consistent but whose calibration composition, quality exclusions, source provenance, or benchmark evidence were never validated. This bypasses the intended formal-evidence gate.

Required repair: make binding construction consume strict checker outputs (or invoke equivalent strict checkers with the necessary source paths), require the full calibrated-pool contract, and add a strict benchmark-report verification/reconstruction path that anchors the selected worker to the actual source benchmark artifacts. Add negative tests showing the current minimal manifests, self-consistent calibration tamper, and hand-crafted formal benchmark recommendation are rejected.

#### R1-M3 — Concurrent reward scoring can start executor side effects before the whole batch's item contracts are validated

The sealed concurrency contract requires all batch alignment/completion/input validation to finish before executor side effects (`ai-work/planner/WP9-b-plan.md:429-452`). `compute_code_rewards_concurrent()` prevalidates batch lengths and completion extraction, but then submits every index immediately. Each worker constructs an executor before calling `verify_completion()` (`src/code_verifier/rewards/common.py:292-322`), while `verify_completion()` validates `function_name`, tests, and metadata only inside that worker just before its own execute call (`src/code_verifier/verification/verifier.py:210-239`). Therefore a valid worker can already call the executor while another worker is only discovering an invalid tests/function/metadata item.

The current regression only proves a length mismatch happens before `executor_factory` (`tests/unit/rewards/test_common.py:571-589`); it does not cover a late invalid per-item contract in an otherwise aligned batch.

Impact: an invalid aligned batch is not fail-before-side-effect as specified. It can cause partial Piston/executor traffic despite the overall reward batch eventually raising, which weakens the intended atomic/fail-closed runtime boundary.

Required repair: pre-normalize/validate every item's selected tests, function name, metadata/resource limits, and completion parse-input contract before submitting any executor work (or expose a side-effect-free verifier prevalidation primitive), while preserving serial semantics/order. Add a regression with a late invalid item that asserts zero factory/execute side effects for the entire batch.

#### R1-M4 — Throughput selection does not fully bind candidates to the required scientific identities

The sealed throughput rules require eval generation candidates to use the same model/checkpoint/dataset/**config**/seed/problem order and GRPO verifier candidates to use the same k=8 scientific config/pool/**B identity**/seed (`ai-work/planner/WP9-b-plan.md:497-505`). The implemented generation parity checks only `model_id`, `model_revision`, `checkpoint`, `dataset_hash`, and `seed`, then compares output rows (`src/code_verifier/throughput.py:176-196`); `_completed_bundle()` does not validate/normalize `resolved_config.yaml`, so a candidate with a different generation configuration can still be eligible when its observed outputs happen to match (`src/code_verifier/throughput.py:163-173`, `406-435`). The fixture explicitly uses fabricated minimal run manifests and never tests config drift (`tests/unit/test_throughput.py:15-85`).

For GRPO, `_grpo_probe()` builds `scientific_identity_sha256` from reward mode, dataset hash, seed, selected parent fields and resolved GRPO config, but omits the parent SFT `config_hash` and `dependency_lock_hash` that are part of the completed B identity (`src/code_verifier/throughput.py:341-382`; compare `src/code_verifier/training/grpo.py:1986-2005`). Thus two runs can compare as the same benchmark identity while referring to different completed-B provenance.

Impact: a formal benchmark can select a faster eval batch/GRPO verifier worker from scientifically non-equivalent source runs, violating the anti-optimization-confounding boundary even if output/reward parity happens to match on the benchmark sample.

Required repair: derive benchmark scientific identities from strict source artifacts. For eval generation, compare the resolved evaluation contract with only operational fields such as run ID/batch size normalized away. For GRPO, include the complete portable B identity (including parent config/dependency identity) and any other required scientific/runtime anchors while excluding only genuinely operational timing/path fields. Add config-drift and B-identity-drift rejection tests.

### Acceptance status

- Public/Hidden calibration prompt isolation, same-completion dual scoring, retry shape, class recomputation, overlap/class caps, quality-gate reserve, active Public/Hidden row copying/order, bounded worker limits, telemetry synchronization, ordered result assembly, staged v1/v2 loading, and legacy k=4 compatibility all have passing implementation/tests in the reviewed tree.
- The four findings above are uncompleted/incorrect effective-contract items, so the stage cannot PASS despite green lint/test gates.
- No formal 24GB evidence is requested in this development round, and lack of such evidence is not a finding.

```yaml
repair_routing:
  version: 1
  required: true
  source_review_round: 1
  mode: multi
  complexity: difficult_serial
  single_class: null
  parallelizability: high
  multi_benefit: high
  independent_workstreams: 3
  repair_issue_ids:
    - R1-M1
    - R1-M2
    - R1-M3
    - R1-M4
  rationale:
    - "R1-M1 (calibration selector) and R1-M3 (reward prevalidation) are independent of each other and of the benchmark/binding evidence-chain repairs, with disjoint tracked write scopes."
    - "R1-M2 and R1-M4 should stay in one evidence-binding lane because a strict refresh binding should consume the repaired strict throughput identity/report contract rather than creating a second competing validation schema."
    - "Three independent lanes reduce turnaround without splitting shared evidence schemas across agents."
  workstream_candidates:
    - id: calibration-selector
      issue_ids:
        - R1-M1
      write_scope:
        - src/code_verifier/training/calibration.py
        - tests/unit/training/test_calibration.py
        - tests/integration/test_wp9b_refresh_engineering.py
    - id: reward-prevalidation
      issue_ids:
        - R1-M3
      write_scope:
        - src/code_verifier/rewards/common.py
        - tests/unit/rewards/test_common.py
    - id: evidence-binding-throughput
      issue_ids:
        - R1-M2
        - R1-M4
      write_scope:
        - src/code_verifier/throughput.py
        - src/code_verifier/training/grpo.py
        - src/code_verifier/cli.py
        - tests/unit/test_throughput.py
        - tests/unit/test_throughput_grpo.py
        - tests/unit/training/test_grpo_refresh_binding.py
        - tests/unit/test_cli.py
```

### Conclusion

`needs_repair`. The implementation is broadly coherent and all independent gates are green, but the active-pool selection protocol, formal refresh binding provenance, fail-before-side-effect concurrency contract, and benchmark scientific identity checks are not yet strong enough to satisfy the sealed WP9-b contract. Next lifecycle action is `stage-lifecycle checkpoint_review`; only after that checkpoint should the repair execution be routed.

## Review Round 2

```yaml
review_record:
  version: 1
  stage_id: WP9-b
  review_round: 2
  source_execution_id: E1
  reviewed_head_commit: ad47d6b37bae10c842d607f5d7f22458e9982977
  conclusion: needs_repair
```

### Effective contract / provenance

- Effective stage contract remains `stage_profile=development`, `control_plane_hardware=GTX 1660 Ti (6GB)`, `target_hardware=GTX 1660 Ti (6GB)`, `evidence_class=engineering`, `development_terminal=false`. WP9-b still does not require or permit real frozen-B calibration, optimizer C2/D2, 24GB scientific execution, or formal 400-problem refresh results.
- Review ran in the plan-declared `feat/wp9-b` worktree `/home/dzy/open-r1-code-verifier/.worktrees/wp9-b`. Before the review artifact was edited, the worktree was clean and `git ls-files .ai-bridge` was empty.
- Latest completed execution is `E1`. The commit that submits the E1 execution report is `ad47d6b37bae10c842d607f5d7f22458e9982977`, equal to the reviewed HEAD, so there is no unreviewed post-report implementation continuation to attribute.
- The active WP9 requirements were checked against both `PROJECT_SPEC_Open-R1_CodeVerifier.md` and `PROJECT_SPEC_GRPO_Refresh.md`, plus the latest `proceedings.md` routing record. The project remains on WP9-b development; lack of 24GB/formal evidence is not a defect in this round.

### Independent verification

- Exact sealed-plan focused suite from WP9-b plan §6.1: `322 passed`.
- Additional R1-repair regression set (`rewards/test_common`, refresh binding, GRPO throughput, verification throughput): `49 passed`.
- `make lint`: PASS — Ruff check, Ruff format check, and strict mypy all pass for `134` source/test files.
- `make test`: PASS — `1162 passed, 3 skipped` in `114.56s`; all three skips are the existing opt-in real-Piston cases requiring `CODE_VERIFIER_RUN_PISTON=1`.
- Reviewer mixed-class selector probe: with external population `A/hard=16 dual`, `B/easy=2 public-only + 2 hidden-only` and external quota `18`, `_select_active_records()` selects `A=16, B=2`. Whole-bucket source+difficulty largest-remainder for that population is `A=14, B=4`; this demonstrates that the repaired selector still lets calibration class suppress a valid stratum allocation.
- Reviewer GRPO-source probe: `throughput._grpo_probe()` accepts a bare four-file self-authored benchmark directory built by the unit fixture, while `load_completed_grpo_checkpoint()` rejects the exact same directory with `completed GRPO run does not match the strict artifact layout`. Therefore benchmark report reconstruction is still only as trustworthy as the shallow GRPO probe input contract.

### Execution report declaration verification

- E1 claim that the sealed focused suite is `322 passed`: independently reproduced.
- E1 claim that the review-specific repair regressions are `49 passed`: independently reproduced.
- E1 claims for `make lint` and full `make test` (`1162 passed, 3 skipped`): independently reproduced.
- E1 claim that `R1-M2` is closed by strict calibration checking plus benchmark report reconstruction: verified for the binding layer itself; the loader now invokes `check_calibrated_active_pool()` and `check_refresh_benchmark_report()`, rejects the old minimal manifests, and binds the selected worker to the checked report.
- E1 claim that `R1-M3` is closed by whole-batch verifier-input prevalidation before executor creation: functionally verified by code and regression (`factory=0`, `execute=0` for a late invalid item). The chosen repair introduces a separate layer-boundary defect recorded below as `R2-M1`.
- E1 claim that `R1-M1` is closed: not verified; the selector stratifies separately inside already-separated calibration classes rather than preserving source+difficulty quotas across the whole overlap bucket.
- E1 claim that `R1-M4` is closed: not verified; eval-generation resolved-config identity is repaired and parent B config/dependency fields were added, but GRPO benchmark inputs remain shallow self-declared directories rather than strict source artifacts.

### Previous-round issue verification

| issue_id | R1 severity | status | evidence |
|---|---|---|---|
| `R1-M1` | major | 修复不完整 | `src/code_verifier/training/calibration.py:1305-1373` applies largest-remainder independently to dual/public-only/hidden-only subsets; reviewer mixed-class probe selects external A/B=`16/2` instead of whole-bucket largest-remainder `14/4`. Existing new regression `tests/unit/training/test_calibration.py:257-299` uses only dual-informative rows and cannot expose this interaction. |
| `R1-M2` | major | 已修复 | `src/code_verifier/training/grpo.py:1507-1583` now calls the strict active-pool checker and benchmark-report checker; `tests/unit/training/test_grpo_refresh_binding.py:138-175` rejects the previous unchecked minimal calibration and hand-crafted benchmark recommendation. |
| `R1-M3` | major | 已修复 | `src/code_verifier/rewards/common.py:315-346` completes whole-batch prevalidation before `executor_factory`; `tests/unit/rewards/test_common.py:592-628` proves a late invalid item causes zero factory/execute side effects. The repair's cross-layer parsing is a new issue `R2-M1`. |
| `R1-M4` | major | 修复不完整 | Eval bundle identity is strengthened in `src/code_verifier/throughput.py:173-265`, and parent B config/dependency fields are in `_grpo_probe()` at `422-449`; however `_grpo_probe()` at `367-478` still trusts a minimal `run.json`/`resolved_config.yaml`/reward/group directory. The reviewer probe proves it accepts a directory that the strict completed-GRPO loader (`src/code_verifier/training/grpo.py:391-464`) rejects. |

### Findings

#### R1-M1 — Active selector still stratifies inside calibration classes instead of the whole overlap bucket

The sealed selector contract requires overlap/non-overlap quotas, class priority, and then source+difficulty largest-remainder allocation, with single-arm rows used when dual rows cannot fill the applicable strata/target (`ai-work/planner/WP9-b-plan.md:354-358`). The repair first takes `dual_count=min(quota, len(dual))` across the whole overlap bucket and performs source+difficulty allocation only within the dual subset (`src/code_verifier/training/calibration.py:1305-1318`). It later performs separate largest-remainder allocations inside the public-only and hidden-only subsets (`1348-1373`). That is not equivalent when class and stratum are correlated: a source+difficulty stratum with no dual rows can be starved even though a valid constrained allocation exists using permitted single-arm rows.

The independent mixed-class probe demonstrates the defect with a valid 20-problem test configuration: the external bucket has 16 dual rows in stratum A and four single-arm rows in stratum B, quota 18. A whole-bucket largest-remainder allocation reserves 14 A + 4 B, satisfying the >=70% dual and both <=15% single-arm caps; current code instead maximizes dual globally and returns 16 A + 2 B. The added unequal-strata unit regression does not catch this because every row in that test is `dual_informative` (`tests/unit/training/test_calibration.py:257-295`).

Impact: active-pool source/difficulty composition can still drift as a function of Public/Hidden informativeness class rather than the frozen stratification protocol. This affects the scientific dataset definition consumed by C2/D2 and leaves the original R1 finding materially open.

Required repair: compute source+difficulty quota targets from the entire eligible population of each overlap bucket first (or implement an equivalent constrained allocator), then fill each stratum with dual rows preferentially and use public/hidden single-arm rows only as needed while enforcing the global class caps/minimum. Producer and checker must share/recompute that algorithm. Add mixed-class/unequal-stratum regressions where some strata contain only single-arm rows and prove deterministic selection plus tamper rejection.

#### R1-M4 — GRPO throughput candidates are still not derived from strict source artifacts

The R1 repair added `parent_sft_config_hash` and `parent_sft_dependency_lock_hash` to the GRPO scientific identity (`src/code_verifier/throughput.py:422-449`), which closes the narrow missing-field bug. But `_grpo_probe()` still treats `run.json`, `resolved_config.yaml`, `rewards.jsonl`, and `group_metrics.jsonl` as sufficient proof of a completed GRPO benchmark (`367-478`). It does not revalidate a completed GRPO/checkpoint/parent chain, recompute the parent B identity from the actual completed SFT artifact, verify current-run config/dependency/runtime-package identity, or bind the dataset/pool/calibration artifacts from an independently checked source contract.

This is directly observable in the repository's own benchmark fixture: `tests/unit/throughput_fixture.py:10-99` writes only four shallow files and is accepted by `_grpo_probe()`. The reviewer independently passed the same directory to `load_completed_grpo_checkpoint()`, which correctly rejected it because it does not match the strict completed-GRPO artifact layout. `check_refresh_benchmark_report()` rebuilds the report from the source manifest, but reconstruction through the same shallow probe cannot turn self-authored source metadata into strict evidence. Refresh addendum §12 also requires each formal benchmark to record and preserve model/checkpoint, runtime/package, config, count, timing/resource/error and selection evidence (`PROJECT_SPEC_GRPO_Refresh.md:758-784`).

Impact: a later formal benchmark report can be internally reconstructable while still being grounded in fabricated or scientifically incomplete GRPO source directories. The selected verifier worker could therefore be admitted to the formal refresh binding without proving the actual k=8 pool/B/runtime identity required by the experiment.

Required repair: make GRPO throughput source loading strict. Reuse `load_completed_grpo_checkpoint()` where benchmark candidates are completed GRPO runs, or define an equally strict benchmark-run artifact checker that independently recomputes the current GRPO config/dependency/runtime identity, parent B identity, pool/calibration binding, relevant dataset hashes, paired definition, counts and reward/group artifact hashes. Keep an explicitly engineering-only fixture path if needed, but formal report reconstruction must reject the current bare fixture contract. Add a negative regression showing self-consistent forged parent/config/runtime fields cannot become a formal benchmark source.

#### R2-M1 — Concurrent reward prevalidation now parses candidate code inside the Reward layer

The side-effect ordering repair imports verifier-private `_normalize_tests`, `_resource_limits_from_metadata`, `_validate_function_name` plus `extract_python_code` directly into `rewards/common.py` (`src/code_verifier/rewards/common.py:11-23`) and calls the parser itself during `_prevalidate_verification_inputs()` (`87-101`). This does achieve fail-before-executor behavior, but it violates the repository's layer contract: `AGENTS.md:160` requires Parsing, Verification, and Reward responsibilities to stay separated; `AGENTS.md:164` explicitly tells reviewers to treat cross-layer responsibility leakage as a design defect; and `AGENTS.md:216` requires reward code to flow through `verify_completion()` rather than parse candidate code independently.

Impact: verification input semantics are now duplicated across Reward and Verification. A future parser/verifier contract change can diverge between prevalidation and the actual `verify_completion()` call, and Reward has acquired direct knowledge of parser internals solely to make concurrency atomic.

Required repair: expose a side-effect-free verification-layer preflight primitive (for example a public `prevalidate_verification_input()` or normalized request builder) and have both concurrent reward prevalidation and `verify_completion()` use that single implementation. Reward should depend on the verification API, not on parsing or verifier-private helpers. Preserve the R1-M3 regression proving all items are prevalidated before any executor factory/execute side effect.

### Acceptance status

- `R1-M2` and the original fail-before-side-effect behavior of `R1-M3` are closed and independently verified.
- `R1-M1` remains materially incomplete, `R1-M4` remains materially incomplete on the GRPO source-artifact side, and the R1-M3 repair introduces the new cross-layer defect `R2-M1`.
- All independent test/lint gates are green, but those gates do not cover the mixed-class stratification or strict-GRPO-source counterexamples above. Green tests therefore do not satisfy the effective contract by themselves.
- No real frozen-B/4090/C2-D2/400-eval evidence is required in WP9-b development, and its absence is not a finding.

### Repair Routing

```yaml
repair_routing:
  version: 1
  required: true
  source_review_round: 2
  mode: multi
  complexity: normal
  single_class: null
  parallelizability: high
  multi_benefit: high
  independent_workstreams: 3
  repair_issue_ids:
    - R1-M1
    - R1-M4
    - R2-M1
  rationale:
    - "The remaining selector, strict-throughput-source, and verification-layer-preflight defects have disjoint production ownership and can be repaired independently without sharing a new schema."
    - "Parallel repair has high benefit because each lane has a focused regression target; final integration only needs the existing WP9-b focused/full gates plus cross-checking the strict evidence chain."
  workstream_candidates:
    - id: calibration-strata
      issue_ids:
        - R1-M1
      write_scope:
        - src/code_verifier/training/calibration.py
        - tests/unit/training/test_calibration.py
        - tests/integration/test_wp9b_refresh_engineering.py
    - id: strict-grpo-benchmark-source
      issue_ids:
        - R1-M4
      write_scope:
        - src/code_verifier/throughput.py
        - tests/unit/test_throughput.py
        - tests/unit/test_throughput_grpo.py
        - tests/unit/throughput_fixture.py
    - id: verification-preflight-boundary
      issue_ids:
        - R2-M1
      write_scope:
        - src/code_verifier/verification/verifier.py
        - src/code_verifier/verification/__init__.py
        - src/code_verifier/rewards/common.py
        - tests/unit/verification/test_verifier.py
        - tests/unit/rewards/test_common.py
```

### Conclusion

`needs_repair`. E1 successfully closes the strict binding-layer issue (`R1-M2`) and the original concurrent fail-before-side-effect issue (`R1-M3`), and its reported test/lint evidence is independently reproducible. However, the active-pool repair still loses source+difficulty strata when class and stratum are correlated (`R1-M1`), GRPO throughput evidence still trusts shallow self-declared source directories rather than strict artifacts (`R1-M4`), and the concurrency repair introduces Reward→Parsing/Verifier-internal responsibility leakage (`R2-M1`). Next lifecycle action is `stage-lifecycle checkpoint_review`; only after that checkpoint should the three repair lanes be routed.
