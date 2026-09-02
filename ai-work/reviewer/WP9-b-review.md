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

## Review Round 3

```yaml
review_record:
  version: 1
  stage_id: WP9-b
  review_round: 3
  source_execution_id: E2
  reviewed_head_commit: da38045c5b9278a17aee9ba54f4a9237539d05d8
  conclusion: needs_repair
```

### Effective contract / provenance

- Effective stage contract remains `stage_profile=development`, `control_plane_hardware=GTX 1660 Ti (6GB)`, `target_hardware=GTX 1660 Ti (6GB)`, `evidence_class=engineering`, `development_terminal=false`. WP9-b is still responsible for target-ready engineering contracts only; real frozen-B calibration, real k=8 pilot/C2/D2, 24GB execution, and formal 400-problem evaluation remain WP9-c+ validation work.
- Review ran in the plan-declared `feat/wp9-b` worktree `/home/dzy/open-r1-code-verifier/.worktrees/wp9-b`. Before this review artifact edit the worktree was clean and `git ls-files .ai-bridge` was empty.
- Latest completed execution is E2. Its execution-report commit is the reviewed HEAD `da38045c5b9278a17aee9ba54f4a9237539d05d8`; the committed R2 review `b0ce11835e3955427d6e4e8e9d3693b2ba4d7625` and E2 result-code commit `a15622eea69aafc6374f60252c2a876b5f70b56b` are both ancestors of that HEAD.
- E2's code commits are scoped to the three R2 repair lanes: calibration selector, Verification/Reward preflight boundary, and GRPO throughput source validation. No sealed plan, project spec, proceedings, dependency lock, or `third_party/open-r1` change is part of the E2 result-code range.

### Independent verification

- Exact sealed-plan focused suite from WP9-b plan §6.1: `324 passed`.
- E2 combined repair regression set (calibration + WP9-b integration + verifier/reward + WP4 integration + refresh binding + GRPO throughput): `103 passed`.
- Supplemental reviewer set (`verification/test_verifier`, `rewards/test_common`, refresh binding, GRPO throughput, verification throughput): `78 passed`.
- `make lint`: PASS — Ruff check, Ruff format check, and strict mypy pass for `134` source/test files.
- `make test`: PASS — `1169 passed, 3 skipped` in `114.03s`; all three skips are the existing opt-in real-Piston tests requiring `CODE_VERIFIER_RUN_PISTON=1`. The default CUDA smoke tests ran and passed.
- `git diff --check`: PASS; `.ai-bridge/**` remains untracked.
- Reviewer k=8 bootstrap probe: both tracked refresh configs load as `num_generations=8`, but calling the production `run_grpo_training(..., refresh_binding=None)` fails before any B artifact access with `GRPOTrainingError: k=8 refresh GRPO requires calibration and benchmark binding`. This independently demonstrates that the current production path cannot generate a pre-selection k=8 verifier sweep without an already completed benchmark report.
- Source inspection of the formal Hidden probe path finds an arm-path error: for a Hidden run `config.dataset_path` is `.../hidden_grpo.jsonl`, but `_strict_grpo_source()` treats that selected-arm path as the Public artifact before deriving `hidden_grpo.jsonl`, so both hashes come from the Hidden file and the Public hash comparison fails for a normal distinct Public/Hidden active-pool pair.

### Execution report declaration verification

- E2's `16 passed`, `77 passed`, `10 passed`, and combined `103 passed` repair-gate claims are independently reproduced by the combined repair suite.
- E2's focused `324 passed`, `make lint` PASS, and full `1169 passed, 3 skipped` claims are independently reproduced.
- E2 claim that `R1-M1` is closed: verified. The selector now computes largest-remainder source+difficulty quotas from each complete overlap bucket before applying dual-first class preference, preserves exact strata quotas, enforces class bounds, and has a correlated mixed-class regression that reproduces the R2 counterexample as `14/4` rather than `16/2`.
- E2 claim that `R2-M1` is closed: verified. Parsing/normalization is owned by Verification through public `prevalidate_verification_input()` / `verify_prevalidated_request()` APIs, while Reward consumes those APIs and no longer imports Parsing or verifier-private helpers. Whole-batch prevalidation still completes before executor-factory side effects.
- E2 claim that `R1-M4` is closed: not verified. The new strict loader is directionally correct and rejects the old shallow engineering fixture as formal evidence, but its formal source path has an incorrect Hidden-arm dataset binding and, more fundamentally, requires the final benchmark binding/report on the very k=8 runs needed to create that report.
- E2 correctly makes no real frozen-B calibration, C2/D2 checkpoint, 4090 throughput, or formal 400-problem scientific claim; the absence of such evidence is not a WP9-b defect.

### Previous-round issue verification

| issue_id | status | evidence |
|---|---|---|
| `R1-M1` | 已修复 | `src/code_verifier/training/calibration.py:1418-1558` allocates whole-bucket source+difficulty strata first, then dual-first/single-arm fallback with global caps; `tests/unit/training/test_calibration.py:301-351` covers the correlated class/stratum counterexample and input-order determinism. |
| `R1-M2` | 已修复 | The refresh binding still comes from strict calibrated-pool and benchmark-report checkers rather than caller-supplied digests; no regression was found in E2. |
| `R1-M3` | 已修复 | Concurrent reward still completes aligned Verification-layer preflight before executor construction, and the zero-side-effect late-invalid regression remains green. |
| `R1-M4` | 修复不完整 | Formal GRPO source validation now uses `load_completed_grpo_checkpoint()`, but `src/code_verifier/throughput.py:696-705` misbinds the Hidden selected-arm path as Public, while `src/code_verifier/training/grpo.py:2470-2477` and `1507-1583` require the already-selected benchmark binding for every k=8 run, creating a bootstrap cycle for the worker/paired benchmark itself. |
| `R2-M1` | 已修复 | `src/code_verifier/verification/verifier.py:120-138,244-302` owns parsing/preflight/execution orchestration; `src/code_verifier/rewards/common.py:84-103,300-347` consumes only public Verification APIs. |

### Findings

#### R1-M4 — Formal GRPO benchmark sources are stricter, but the strict path is not executable for the required pre-freeze sweep

E2 correctly replaced the shallow formal source with `_strict_grpo_identity()` → `load_completed_grpo_checkpoint()` and extensive runtime/config/pool/log recomputation (`src/code_verifier/throughput.py:439-997`). That closes the original "four self-authored files can become formal evidence" hole, but two production-path defects keep the same R1 issue materially open.

First, the strict active-pool path is arm-incorrect. At `src/code_verifier/throughput.py:696-705`, `dataset_path = config.dataset_path` is always hashed as `public_sha`, then `hidden_dataset_path = dataset_path.with_name("hidden_grpo.jsonl")`. For the tracked Hidden refresh config (`configs/grpo/refresh-hidden.yaml:3`), `dataset_path` already is `hidden_grpo.jsonl`, so both variables identify the Hidden file. A legitimate Hidden run whose Public and Hidden training artifacts differ will therefore fail the `active_public_training_sha256` comparison. Existing strict-source tests are only negative (`tests/unit/test_throughput_grpo.py:176-195`); there is no positive strict Public-and-Hidden completed-source test to expose this.

Second, the formal benchmark has a circular bootstrap. `run_grpo_training()` rejects every k=8 run without a `GRPORefreshBinding` (`src/code_verifier/training/grpo.py:2470-2477`), while `load_grpo_refresh_binding()` itself requires a completed benchmark report and requires runtime workers to equal that report's already selected worker (`1507-1583`). `_strict_grpo_source()` also requires refresh metadata including `benchmark_report_sha256` (`src/code_verifier/throughput.py:610-643`). Yet the formal throughput report is supposed to be the artifact that compares k=8 verifier-worker candidates and chooses that worker. The reviewer probe hits this cycle before any external B/checkpoint access. A prior final binding cannot solve the sweep either, because it freezes one worker value and therefore cannot generate the alternative worker candidates being compared.

Impact: WP9-c cannot use the implemented production contracts to create and then strictly validate the formal k=8 verifier/paired benchmark evidence that WP9-b was required to make target-ready. Hidden strict sources are rejected on their own path, and the worker-selection benchmark requires its own result before its candidate runs can exist. This is a code-contract defect in WP9-b development, not a complaint about missing 4090 evidence.

Required repair: introduce an explicit **pre-freeze benchmark-run contract** for real k=8 benchmark candidates. It must bind the completed B identity, formal calibration/active-pool identity, exact k=8 scientific config/seed/runtime, candidate worker count, and completed output artifact hashes, but it must not require the not-yet-created final benchmark report or selected worker. The final C2/D2 training path should continue to require the frozen benchmark report/binding. Derive Public and Hidden active-pool paths explicitly from the calibration root (or branch correctly by reward mode), and add positive strict-source regressions for both arms plus the worker-sweep bootstrap path.

#### R3-M1 — The throughput harness still omits the mandatory legacy k=4 versus k=8 benchmark comparison

The frozen plan requires the benchmark manifest to carry a legacy k=4 reference and k=8 candidates, and explicitly says `k4 vs k8` is a benchmark comparison (`ai-work/planner/WP9-b-plan.md:497-504`). The active Refresh specification likewise requires, before formal C2/D2, a legacy `num_generations=4` small reference and a `num_generations=8` candidate (`PROJECT_SPEC_GRPO_Refresh.md:758-768`).

The implemented report schema has no such section. `summarize_refresh_benchmarks()` accepts only `eval_generation`, optional eval verification, `grpo_verification`, and `paired_grpo` sections (`src/code_verifier/throughput.py:1444-1495`). In the entire throughput module, the only explicit `num_generations` validation for GRPO requires `== 8` (`src/code_verifier/throughput.py:588-591`), so the strict formal source path cannot represent a legacy k=4 reference. The engineering integration manifest likewise contains only eval-generation and k=8 GRPO worker fixtures (`tests/integration/test_wp9b_refresh_engineering.py:283-326`).

This also leaves the GRPO side of the §12 record incomplete: the current GRPO report derives group throughput, memory, verifier timing and artifact hashes, but does not expose artifact-derived generated-token count / tokens-per-second for the k4/k8 comparison even though §12 requires generated tokens and tokens/s for each benchmark (`PROJECT_SPEC_GRPO_Refresh.md:770-784`).

Impact: a future formal report can satisfy the implemented schema while omitting one of the specification's mandatory comparisons, and therefore cannot demonstrate that k=8 throughput was evaluated without changing scientific work/budget relative to the legacy k=4 reference.

Required repair: add a formal k4-vs-k8 benchmark section/source contract that accepts strict actual artifacts for both protocols, independently proves the same B/pool/seed/scientific budget except for the intended generation-group-size difference, rejects confounds such as fewer steps/shorter completion/different reward or dataset, and derives the required token/time/resource/error telemetry from artifacts. Formal report checking must reject omission of this comparison. Add positive k4/k8 parity/identity tests and negative confound tests.

### Acceptance status

- `R1-M1`, `R1-M2`, `R1-M3`, and `R2-M1` are closed under independent code/test review.
- `R1-M4` remains materially incomplete because the new strict formal GRPO path cannot validate a normal Hidden source and cannot bootstrap the k=8 worker/paired sweep without an already-frozen benchmark result.
- New `R3-M1` records the still-missing mandatory k4-vs-k8 benchmark contract and required artifact-derived telemetry coverage.
- All independent lint/test gates are green, but current tests do not contain a positive strict formal Public+Hidden source or a formal k4-vs-k8 report, so they do not exercise the failing target-ready contract above.
- WP9-b still does not require actual 24GB/4090 execution or scientific results. The failure is that the development implementation cannot support the specified future formal evidence flow as written.

### Repair Routing

```yaml
repair_routing:
  version: 1
  required: true
  source_review_round: 3
  mode: single
  complexity: normal
  single_class: normal
  parallelizability: low
  multi_benefit: low
  independent_workstreams: 1
  repair_issue_ids:
    - R1-M4
    - R3-M1
  rationale:
    - "Both remaining findings are one formal GRPO benchmark-bootstrap/source-contract problem spanning the pre-freeze run identity and the final throughput report; splitting them would risk two incompatible evidence schemas."
    - "The repair should define one pre-freeze actual-run contract that supports k4/k8 and worker/paired candidates, then let the final report freeze choices consumed by formal C2/D2."
  workstream_candidates: []
```

### Conclusion

`needs_repair`. E2 closes the active-pool stratification and Verification/Reward boundary defects and independently reproduces all reported test/lint gates. Its strict-source repair is a substantial improvement, but `R1-M4` is still open because the formal Hidden source binding is arm-incorrect and the k=8 benchmark path depends on its own not-yet-created final report. The throughput harness also still omits the specification-mandated k4-versus-k8 comparison (`R3-M1`). Next lifecycle action is `stage-lifecycle checkpoint_review`; after that checkpoint, route the single integrated benchmark-contract repair.

## Review Round 4

```yaml
review_record:
  version: 1
  stage_id: WP9-b
  review_round: 4
  source_execution_id: E2
  reviewed_head_commit: c4cf62701c84ac2edbf32842dd85a2ffadb2b06a
  conclusion: needs_repair
```

### User-authorized effective-contract override

- This round is an attributable user-authorized contract continuation rather than a new execution. No source/test/config change occurred after the committed R3 checkpoint; `c4cf62701c84ac2edbf32842dd85a2ffadb2b06a` differs from the E2 reviewed code only by the append-only R3 review artifact.
- The user explicitly accepts **k=8 as the primary Refresh GRPO protocol**. WP9-b/WP9-c no longer need a co-equal formal model-selection framework whose purpose is to decide between k=4 and k=8 before the project may proceed.
- A **small controlled legacy k=4 reference is retained as a diagnostic baseline only**. Its purpose is to determine whether active-pool calibration already makes k=4 sufficiently informative, quantify the marginal systems cost/benefit of k=8, and detect nonlinear k=8 instability. It is not a second C2/D2 arm and does not require a k=4 worker sweep, k=4 Public/Hidden paired scheduling trial, or a separate k=4 formal training campaign.
- The controlled reference should use the same completed B identity, same calibrated active pool (or the same explicitly frozen small benchmark subset), same seed/reward arm/runtime/sampling protocol, and the same problem order as its k=8 comparison, with `num_generations` as the intended protocol difference. The report must preserve raw work/cost differences rather than normalize them away.
- The default project decision remains k=8. The k=4 diagnostic should trigger an explicit reconsideration warning only when it exposes a material reason to do so, for example: k=4 already reaches roughly <=20% zero-variance while k=8 improves by <5 percentage points; k=8 is >=15% worse in useful non-zero-variance groups/GPU-hour; k=8 causes persistent OOM/retry/verifier-starvation/step-jitter degradation; or a later fair pilot shows no learning advantage while k=4 is materially cheaper. These are diagnostic/research decision signals, not new WP9-b development evidence requirements.
- All other WP9-b boundaries are unchanged: this remains a `development` / `engineering` stage on GTX 1660 Ti. Real frozen-B calibration, real k=4/k=8 measurements, 24GB execution, C2/D2, and held-out learning conclusions remain WP9-c+ validation work.

### Scope change relative to R3

- `R1-M4` is unchanged and remains mandatory. The production formal/pre-freeze GRPO benchmark path must be executable before a final benchmark report exists, and Public/Hidden active-pool identities must be derived correctly for both arms.
- `R3-M1` remains open but is **materially narrowed**. The R3 requirement for a full formal k4-versus-k8 selection framework is superseded by the user decision above. The only remaining requirement is support for one strict, small, controlled k=4 diagnostic reference alongside the primary k=8 benchmark evidence.
- In particular, WP9-b no longer needs to make k=4 a peer candidate in final configuration selection, prove that k=8 must beat k=4 before continuing, run k=4 through every GRPO worker candidate, or implement k=4 same-GPU paired scheduling logic.

### Current-code check under the overridden contract

- The new contract is still not fully satisfied by the current code. `src/code_verifier/throughput.py:588-591` rejects every strict GRPO benchmark source whose `num_generations != 8`, so a real controlled k=4 diagnostic artifact cannot use the strict actual-run identity path.
- `summarize_refresh_benchmarks()` still has no manifest/report slot for the diagnostic k=4 reference (`src/code_verifier/throughput.py:1450-1466`). Therefore the current formal report cannot carry even the reduced baseline or derive its cost/informativeness metrics.
- The narrower implementation does not need a large new subsystem. The preferred repair is to make the same **pre-freeze actual-run contract** support roles such as `k4_diagnostic` and `k8_candidate`, while the final frozen refresh binding remains k=8-only for C2/D2.
- The k=4 diagnostic report only needs enough artifact-derived evidence to support the intended sanity decision: completed B/pool/config/seed/runtime identity, problem/group/sample count, wall-clock, generated tokens/tokens-per-second, verifier request/time, OOM/retry/error counts, zero-variance/informative-group counts, and useful non-zero-variance groups/GPU-hour. It does not need optimizer-quality claims or to become a final-training selection gate.

### Verification evidence for this contract-only round

- Stage worktree was clean before this append; `git ls-files .ai-bridge` is empty.
- Current reviewed HEAD is the committed R3 review checkpoint `c4cf62701c84ac2edbf32842dd85a2ffadb2b06a`; there are no intervening code/config/test commits after E2.
- Because the executable tree is unchanged from R3, the independently reproduced R3 gates remain applicable: focused `324 passed`, `make lint` PASS, and full `1169 passed, 3 skipped`.
- A fresh targeted sanity rerun for the affected benchmark/binding surface passed: `tests/unit/test_throughput_grpo.py`, `tests/unit/test_throughput.py`, and `tests/unit/training/test_grpo_refresh_binding.py` -> `15 passed`.
- These green tests do not close the remaining findings because the current test matrix still has no positive strict actual k=4 diagnostic source and does not exercise pre-freeze k=8 worker-sweep bootstrap.

### Remaining actionable findings

#### R1-M4 — Pre-freeze formal GRPO benchmark runs still cannot bootstrap correctly

Status: **open, unchanged**.

Required repair remains:

- add an explicit pre-freeze actual-run identity for benchmark candidates that binds completed B, formal calibration/active-pool identity, exact config/seed/runtime, candidate worker count and output artifacts without requiring the not-yet-created final benchmark report or already-selected worker;
- fix Public/Hidden active-pool path derivation so a normal Hidden run validates the distinct Public and Hidden training artifacts correctly;
- keep final C2/D2 k=8 training strict: once the benchmark is frozen, it must consume the final benchmark report/binding and selected worker;
- add positive strict Public and Hidden source regressions plus a k=8 worker-sweep bootstrap regression.

#### R3-M1 — Retain only a small controlled k=4 diagnostic reference

Status: **open with superseded/narrowed repair scope**.

Required repair is now limited to:

- permit one strict actual legacy k=4 benchmark source under an explicit diagnostic role without weakening the k=8-only final C2/D2 binding;
- place that reference in the throughput manifest/report next to the primary k=8 benchmark evidence;
- prove the k=4 and k=8 diagnostic comparison shares the frozen B/pool/subset/order/seed/reward/runtime/sampling identity except for the intended group-size difference and directly attributable work-count differences;
- derive the minimal diagnostic telemetry listed above, including zero-variance/informative groups and useful non-zero-variance groups/GPU-hour;
- add a positive controlled k4/k8 diagnostic regression and negative identity/confound regressions.

Explicitly **not required** by this issue anymore:

- a formal algorithm that chooses k=4 versus k=8 as peer primary protocols;
- a k=4 verifier-worker sweep;
- a k=4 paired Public/Hidden scheduling benchmark;
- a k=4 C2/D2 training run;
- proof during WP9-b that k=8 has superior held-out model quality.

### Acceptance status

- `R1-M1`, `R1-M2`, `R1-M3`, and `R2-M1` remain closed.
- `R1-M4` remains the principal blocking production-contract defect.
- `R3-M1` is retained only as a small implementation addition needed to make the user-requested controlled k=4 diagnostic auditable; its former heavyweight k4-versus-k8 selection scope is superseded.
- The two remaining items should be implemented together because one parameterized pre-freeze benchmark-run contract can support both the k=8 worker candidates and the k=4 diagnostic reference without duplicating evidence schemas.

### Repair Routing

```yaml
repair_routing:
  version: 1
  required: true
  source_review_round: 4
  mode: single
  complexity: normal
  single_class: normal
  parallelizability: low
  multi_benefit: low
  independent_workstreams: 1
  repair_issue_ids:
    - R1-M4
    - R3-M1
  rationale:
    - "The user has made k=8 the primary protocol and reduced k=4 to one controlled diagnostic reference, so the previous heavyweight peer-selection requirement is superseded."
    - "Both remaining tasks are best solved by one pre-freeze actual-run contract parameterized for a k8 primary candidate or k4 diagnostic role, while preserving a k8-only final frozen C2/D2 binding."
  workstream_candidates: []
```

### Conclusion

`needs_repair`. The user override substantially reduces the remaining WP9-b scope: k=8 is now the primary Refresh protocol, and k=4 is only a small controlled diagnostic baseline. The current implementation still needs `R1-M4` so formal k=8 candidate runs can bootstrap before the final benchmark report and Hidden source identity is correct, plus the narrowed `R3-M1` so one strict k=4 diagnostic reference can be represented and compared on artifact-derived informativeness/cost metrics. After this append, the next lifecycle action is `stage-lifecycle checkpoint_review`; only then should execution-router perform the single integrated repair.

### Lifecycle Reconciliation Record

This record repairs lifecycle provenance only; it does **not** retroactively claim that Review Round 4 was checkpointed before E3, and it does not revalidate R4 against the post-E3 code tree.

```yaml
review_reconciliation:
  version: 1
  stage_id: WP9-b
  reconciled_review_round: 4
  original_draft_sha256: 7299e32d9e1cba1a1c9e4f0a752b0c51f7a771ac8a9bc0a38bb8c5a37f638bf1
  original_reviewed_head_commit: c4cf62701c84ac2edbf32842dd85a2ffadb2b06a
  consumed_by_execution_id: E3
  source_review_commit_at_execution: null
  e3_result_code_commit: e3f9b97aa331714f11ff6f96b2065bc68a7da7f1
  reconciliation_head_before_commit: 271e51a6cb5fa37a02ad80e054d8c075f0291b2b
  status: historical_uncheckpointed_input_reconciled
  next_review_round: 5
```

- R4 was authored and consumed as a user-authorized **uncommitted review draft**. E3 already records that exceptional provenance explicitly, including `source_review_round: 4` and `source_review_commit: null`; those fields remain correct and are not rewritten.
- The R4 findings/routing are preserved verbatim above as the historical contract input that E3 repaired. This reconciliation commit is a provenance repair, not a normal `checkpoint_review` of the current post-E3 HEAD.
- The authoritative next independent review is therefore **R5**, which must review E3 and the current actual code tree. Normal `stage-lifecycle checkpoint_review` semantics resume with that R5 record.

## Review Round 5

```yaml
review_record:
  version: 1
  stage_id: WP9-b
  review_round: 5
  source_execution_id: E3
  reviewed_head_commit: 719964a
  conclusion: needs_repair
```

### Effective contract / provenance

- This is the first independent review after E3. R4 is treated only as the historical uncheckpointed repair input reconciled above.
- E3 result-code commit `e3f9b97aa331714f11ff6f96b2065bc68a7da7f1` is the implementation provenance anchor.
- The current code tree includes E3 plus the lifecycle provenance reconciliation commit; no business-code change occurred in the reconciliation step.

### Independent verification

- Targeted benchmark/binding regression set: `28 passed`.
- `make lint`: PASS.
- `make test`: PASS, `1184 passed, 3 skipped`.
- `.ai-bridge` tracked paths: none.

### Findings

#### R5-M1 — Final refresh binding does not cryptographically couple benchmark report identity to calibration/active-pool identity

Status: **open, major**.

The E3 repair correctly introduced `GRPOBenchmarkBinding` for pre-freeze candidates and strict k4/k8 diagnostic roles. However, the final `load_grpo_refresh_binding()` path still only checks that the benchmark report validates and that the selected worker count matches. It does not require the benchmark report's source manifest to carry the same calibration manifest hash, active order hash, and Public/Hidden training artifact identities as the calibration manifest supplied to the final refresh run.

Impact: two individually valid formal artifacts from different active pools can be combined into one refresh binding if their worker selection agrees. The final C2/D2 run would then consume a calibration identity different from the benchmark evidence that justified the runtime choice.

Required repair:

- add canonical benchmark source identity fields covering calibration manifest SHA, active order SHA, Public training SHA, and Hidden training SHA;
- require `load_grpo_refresh_binding()` to compare benchmark identity with calibration identity before producing `GRPORefreshBinding`;
- add negative regression using two valid but different calibration/benchmark artifact sets with the same worker selection.

### Acceptance status

- E3 closes the previous `R1-M4` bootstrap-cycle and narrowed `R3-M1` implementation gaps.
- R5-M1 remains the blocking evidence-lineage defect.

### Repair Routing

```yaml
repair_routing:
  version: 1
  required: true
  source_review_round: 5
  mode: single
  complexity: normal
  single_class: normal
  parallelizability: low
  multi_benefit: low
  independent_workstreams: 1
  repair_issue_ids:
    - R5-M1
  rationale:
    - "The remaining defect is one evidence identity contract spanning benchmark report reconstruction and final refresh binding."
  workstream_candidates: []
```

### Conclusion

`needs_repair`. E3 is a substantial repair and passes the executable verification gates, but final benchmark evidence is not yet guaranteed to describe the same calibration/active-pool identity consumed by refresh training. Next lifecycle action is `stage-lifecycle checkpoint_review`.
