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
