# WP9-a Review

## R1 — refresh data foundation independent review

```yaml
review_record:
  version: 1
  stage_id: WP9-a
  review_round: 1
  source_execution_id: E0
  reviewed_head_commit: 16660a249fe1d9d849887cccccd9de8da96a773a
  conclusion: needs_repair
```

### Review scope and provenance guard

- Reviewer context is fresh and did not participate in the latest `web_codexpro` execution.
- Stage was explicitly requested as `WP9-a`. The unique matching worktree is `/home/dzy/open-r1-code-verifier/.worktrees/wp9-a`, branch `feat/wp9-a`.
- Sealed plan metadata matches the actual stage: `stage_profile=development`, `control_plane_hardware=GTX 1660 Ti (6GB)`, `target_hardware=GTX 1660 Ti (6GB)`, `evidence_class=engineering`, `development_terminal=false`.
- Sealed plan commit is `72a91b652a38fe4e7e58a396c76bfd77fb46a66b`.
- Latest completed execution record is `E0`, `task_kind=implementation`, `source_plan_commit=72a91b652a38fe4e7e58a396c76bfd77fb46a66b`, `result_code_commit=2deff303a0a7c98a65170fe6661178a57a09dbe3`, `execution_backend=web_codexpro`, `effective_execution_mode=single`, `status=completed`.
- Git history identifies `16660a249fe1d9d849887cccccd9de8da96a773a` as the commit that added `ai-work/executor/WP9-a-executor.md`; review began with `HEAD` exactly at that commit and a clean worktree.
- `git ls-files .ai-bridge` is empty; no tracked transport artifact is present.
- `show_changes` reported no staged or unstaged repository changes before review writing.

### Plan / spec verification

| Area | Independent review result |
|---|---|
| Stage boundary | PASS. Implementation remains a development/control-plane data stage and does not add real B calibration, GRPO training, C2/D2, 400-problem evaluation, reward/trainer semantic changes, or 24GB operator work. |
| Source ingestion | PASS for code shape. Pinned full-SHA resolution, dataset-card license equality, exact DeepCoder parquet projection shape, strict JSON parsing, fixed-output stdio-only mapping, and HumanEvalPlus exclusion-only loading are implemented in `refresh_sources.py`. |
| Three-layer materialization | PASS for producer path. `split_refresh_test_cases()` uses the isolated `wp9a-refresh-tests-v1` namespace; `>=8` tests map to 2 visible / 3 train-hidden / remainder eval-hidden; 4–7 tests preserve all three non-empty layers and producer-side `quality_gate_required=true`. |
| Public/Hidden field isolation | PASS for producer/readback path. Public/Hidden are rebuilt from canonical whitelist records; Public excludes train-hidden and both exclude eval-hidden/reference solution/SFT response/starter code. |
| SFT quota producer path | PASS for the tracked config. `target_size=10000`, overlap `0.075`, hard max `0.15`, and explicit SFT-reuse vs external-new selection are implemented; the committed config has the planned values. |
| Strict overlap readback | **FAIL — R1-M1.** `check_refresh_data()` audits SFT/evaluation overlap using the `fingerprint` objects already stored in `selection.jsonl` (`refresh.py:943-981`) rather than re-deriving fingerprints from the canonical rows that are actually fed to Public/Hidden training. The quality flag is likewise counted from stored selection records without checking it against each canonical problem's real test count (`refresh.py:982-989`). This makes the strict readback unable to independently prove that the actual canonical/training bytes satisfy the overlap and low-test-quality gates. |
| External near dedup semantics | **FAIL — R1-M2.** `_external_duplicate_components()` unions all >=0.90 pairwise edges into a transitive component (`refresh_dedup.py:404-449`) and later reports every rejected member as matched to the retained component representative (`refresh_dedup.py:536-555`). Jaccard near-duplicate is not transitive, so a rejected member can be <0.90 similar to the reported retained representative even though the manifest calls it `near_external_duplicate`. The plan defines accepted-near by final exact Jaccard >=0.90, not by transitive closure. |
| Frozen dedup protocol | **FAIL — R1-M3.** The file-based CLI config path does not enforce the sealed WP9-a `token_ngram_size=5` / `near_jaccard_threshold=0.90` protocol. `_validate_selection_config()` only requires a positive n-gram size and threshold in `(0,1]` (`refresh.py:216-225`), and the CLI directly runs whatever `load_refresh_data_config()` accepts (`cli.py:233-245`). A config with `token_ngram_size=1` and `near_jaccard_threshold=1.0` is accepted under the same `wp9a-refresh-v1` schema, even though `1.0` silently disables all non-exact near matches and violates the sealed plan's fixed near-dedup rule. |

### Reviewer-owned reproduction evidence

1. **Strict-readback quality-flag bypass (R1-M1).** Starting from the repository's own small WP9-a fixture pipeline, reviewer changed one canonical `<8 tests` selection record from `quality_gate_required=true` to `false`, updated the root manifest's self-reported selection hash/count, and left `reports/test_layer_leakage.json` with its old count. `check_refresh_data()` still returned success: `CHECK_PASSED 1 tampered_index 3`. This proves the checker does not independently reconcile the quality gate with canonical test counts or the leakage report.
2. **Strict-readback SFT-overlap bypass (R1-M1).** Reviewer started from the same valid fixture output, replaced one `external_new` canonical problem's statement/signature/tests with a frozen SFT-train problem, regenerated the Public/Hidden views from that tampered canonical file, and updated the root manifest's self-reported artifact hashes while leaving the stored selection fingerprint unchanged. `check_refresh_data()` still returned success: `CHECK_PASSED_WITH_SFT_OVERLAP 0 external-6 8`. Thus an actual training row can be an SFT duplicate while the strict checker certifies zero incidental external-SFT overlap.
3. **Transitive near-dedup counterexample (R1-M2).** With threshold `0.90`, reviewer constructed fingerprints A/B/C such that `J(A,B)=0.9047619`, `J(B,C)=0.9047619`, but `J(A,C)=0.8181818`. `_external_duplicate_components()` returned `{'a': 'a', 'b': 'a', 'c': 'a'}`. Therefore C is rejected against retained representative A despite their similarity being below the accepted-near threshold.
4. **Frozen-policy bypass (R1-M3).** Reviewer created a valid-shape `wp9a-refresh-v1` YAML with `token_ngram_size: 1` and `near_jaccard_threshold: 1.0`. `load_refresh_data_config()` accepted it and printed `1 1.0` rather than rejecting the protocol deviation.

### Independent regression gates

- Planned literal command `uv run pytest ...`: environment-level invocation failure (`Failed to spawn: pytest`); this is not treated as a code finding because the module entry point is available and repository Make targets use it correctly.
- Equivalent focused command `uv run python -m pytest tests/unit/data/test_refresh_sources.py tests/unit/data/test_refresh_dedup.py tests/unit/data/test_refresh.py tests/unit/data/test_split_tests.py tests/unit/data/test_prepare.py tests/unit/test_cli.py tests/integration/test_wp9a_refresh_data_pipeline.py`: PASS — `164 passed`.
- `make lint`: PASS — Ruff check/format and strict mypy, 121 source files.
- `make test`: PASS — `1087 passed, 3 skipped, 0 failed`; skips are the existing real-Piston opt-in tests and WP9-a does not depend on Piston.
- Reviewer attempted to independently reload both pinned DeepCoder projections plus HumanEvalPlus from the default local HF cache to re-compute the execution report's source counts/fingerprints; the command exceeded the reviewer command limit at 180s before producing a result. Therefore the execution report's real-source projection hashes and run9/run10 root-manifest evidence remain **not independently re-verified in this round**; they are not used to override the code-level failures above.

### Findings

#### R1-M1 — `check-refresh-data` trusts stored selection fingerprints/quality flags instead of the canonical training content

**Severity:** Major / actionable.

The core acceptance property is about the actual canonical pool and the Public/Hidden rows derived from it. `check_refresh_data()` reloads those canonical rows, but then computes evaluation/SFT overlap from `selection.jsonl`'s stored `fingerprint` field rather than rebuilding a fingerprint from each canonical problem and comparing that derived value with the stored provenance. It also trusts `quality_gate_required` as a manifest assertion instead of deriving it from the canonical test-layer cardinality. The two reviewer reproductions above show that a self-consistent artifact tree can pass strict readback while the actual training content violates the SFT-overlap gate or while low-test records are mislabelled.

Required repair:

- bind every selection fingerprint to the canonical problem it describes and fail closed on any mismatch; for external stdio rows, preserve/derive the raw-statement identity in a way that can be deterministically checked against canonical wrapper construction rather than trusting an opaque stored fingerprint;
- recompute `quality_gate_required` per canonical problem and compare it with selection/report/root-manifest counts;
- semantically reconcile the relevant report JSON values with recomputed results, not only their self-reported artifact hashes;
- add tests where canonical/training content plus root-manifest hashes are made internally self-consistent but selection fingerprints/quality flags are stale or false; `check-refresh-data` must reject them.

#### R1-M2 — transitive DSU clustering violates the exact-Jaccard accepted-near contract

**Severity:** Major / actionable.

The plan freezes final near-duplicate acceptance at exact Jaccard `>=0.90`. The implementation converts pairwise accepted-near edges into an equivalence relation with DSU, then reports the component's deterministic retained member as the rejected row's `matched_record_id`. Because Jaccard similarity is not transitive, the retained representative may not be an accepted-near match for that rejected row; the reviewer counterexample demonstrates `0.8181818` being collapsed into the same component. This can over-prune the external pool and makes the machine-readable `matched_record_id/similarity` evidence contradict the protocol.

Required repair:

- choose retained/rejected relationships using direct exact or exact-Jaccard-verified matches at the frozen threshold; do not let a transitive path alone justify rejection;
- if a clustering strategy is retained, its canonical representative must still be directly verified as an accepted duplicate of each rejected member, otherwise retain/reassign the member;
- add a non-transitive A-B-C regression test and assert every `near_external_duplicate` decision has `similarity >= policy.near_jaccard_threshold` to its reported `matched_record_id`.

#### R1-M3 — the CLI accepts protocol configurations that weaken the sealed WP9-a near-dedup rule

**Severity:** Major / actionable.

The committed `configs/data/refresh.yaml` is correct, and the executor says it used that file. However, the production CLI accepts any schema-valid config and the validator does not enforce the plan's frozen `5-gram / 0.90` protocol. In particular, threshold `1.0` is accepted and treats only exact token-set equality as near duplicate, allowing accepted-near leakage that the sealed WP9-a protocol requires to reject. This is a normal production path, not a private test-only API.

Required repair:

- enforce the WP9-a schema's frozen dedup protocol at the file/config boundary used by `prepare-refresh-data` and `check-refresh-data`, or explicitly version any alternate protocol so artifacts cannot claim `wp9a-refresh-v1` while using different n-gram/threshold semantics;
- add config tests rejecting `n != 5` and threshold `!= 0.90` for `wp9a-refresh-v1` (and similarly preserve the tracked 15% hard maximum / planned source identity rules if alternate protocol support is intended later).

### Executor claim audit

- Git/provenance, stage profile, implementation scope, lint, full test suite, and producer-side field isolation are consistent with the execution report.
- The execution report's statement that strict readback proves the final overlap/quality invariants is **not substantiated** because R1-M1 shows the checker can certify canonical bytes that contradict its stored fingerprints/flags.
- The execution report's deterministic external-dedup claim is only partially substantiated because R1-M2 shows the current deterministic algorithm can apply the near threshold transitively rather than to the reported retained/rejected pair.
- The real pinned-source counts/hashes, 10k run9/run10 bytes, and root-manifest SHA were not independently re-read in this reviewer round because the external output path is not available in the committed report/environment and a default-cache source reload exceeded the 180s reviewer command limit.

### Conclusion

**NEEDS REPAIR** for `reviewed_head_commit=16660a249fe1d9d849887cccccd9de8da96a773a`.

The stage has strong producer-side coverage and all repository regression gates pass, but the central data-integrity acceptance is not yet independently enforceable: strict readback can be made self-consistent while actual training content violates overlap/quality semantics, near-dedup can reject below-threshold representatives through transitive closure, and the production config boundary permits weakening the sealed near-dedup protocol.

```yaml
repair_routing:
  version: 1
  required: true
  source_review_round: 1
  mode: single
  complexity: normal
  single_class: normal
  parallelizability: medium
  multi_benefit: low
  independent_workstreams: 1
  repair_issue_ids:
    - R1-M1
    - R1-M2
    - R1-M3
  rationale:
    - "All three findings touch the same refresh data contract and overlapping files/tests (`refresh.py`, `refresh_dedup.py`, CLI/config readback), so independent write scopes would collide and a single repair lane is safer."
    - "The fixes are bounded code/test changes with no GPU or long-running formal job requirement, but they require coordinated provenance/readback semantics and new adversarial regression tests."
  workstream_candidates: []
```

Next lifecycle action: run `stage-lifecycle checkpoint_review` for `WP9-a`; after that, route a repair execution for `R1-M1`, `R1-M2`, and `R1-M3`. Reviewer-ex does not commit, merge, update proceedings, finalize, or clean up the stage.

## R2 — R1 repair independent review

```yaml
review_record:
  version: 1
  stage_id: WP9-a
  review_round: 2
  source_execution_id: E1
  reviewed_head_commit: b57391237dc2bd8ef5b23b258c4d5aebbadded3d
  conclusion: needs_repair
```

### Review scope and provenance guard

- Reviewer did not participate in the latest `E1` repair execution. `WP9-a` was explicitly requested and the exact worktree remains `/home/dzy/open-r1-code-verifier/.worktrees/wp9-a`, branch `feat/wp9-a`.
- The sealed plan remains commit `72a91b652a38fe4e7e58a396c76bfd77fb46a66b` with `stage_profile=development`, `control_plane_hardware=GTX 1660 Ti (6GB)`, `target_hardware=GTX 1660 Ti (6GB)`, `evidence_class=engineering`, `development_terminal=false`.
- R1 was checkpointed at `3ef9a0ee695ea3ee555f03072a3c0433de92c3d4`. The E1 code commit `0e2d65560fb8631614af4441752b1a134179b827` has that review commit as its parent, and the E1 execution-report commit `b57391237dc2bd8ef5b23b258c4d5aebbadded3d` has the code commit as its parent.
- Latest execution record is `E1`, `task_kind=repair`, `source_review_round=1`, `source_review_commit=3ef9a0ee695ea3ee555f03072a3c0433de92c3d4`, `repair_issue_ids=[R1-M1,R1-M2,R1-M3]`, `status=completed`. Review began with `HEAD` exactly at the E1 execution-report commit and a clean worktree.
- `git ls-files .ai-bridge` is empty; no tracked transport state is present.

### R1 issue disposition

| Previous issue | R2 disposition |
|---|---|
| `R1-M1` | **Resolved for the specific selected-side bypasses.** `check_refresh_data()` now recomputes `quality_gate_required` from canonical test-layer counts, rebuilds selected fingerprints from canonical bytes, binds external wrapper stripping to the frozen interface note, and semantically checks the three overlap/leakage reports. The original false-quality and stale-selected-fingerprint attacks are covered by new integration regressions. A separate formal-reference-side trust failure remains and is recorded as new `R2-M1`. |
| `R1-M2` | **Resolved.** External dedup no longer uses transitive DSU components. `_external_duplicate_matches()` only rejects against direct exact or exact-Jaccard-qualified already-retained representatives. Reviewer re-ran a non-transitive A-B-C chain and observed only `b -> a` at `0.9047619`, while C remained retained. |
| `R1-M3` | **Resolved for the frozen near-dedup parameters.** `validate_refresh_dedup_policy()` now rejects n-gram sizes other than 5 and thresholds other than 0.90; reviewer independently confirmed both `n=1` and `threshold=1.0` are rejected. A separate SFT-overlap hard-cap configuration gap is recorded as new `R2-M2`. |

### Reviewer-owned verification

- Focused sealed-plan WP9-a suite: `uv run python -m pytest tests/unit/data/test_refresh_sources.py tests/unit/data/test_refresh_dedup.py tests/unit/data/test_refresh.py tests/unit/data/test_split_tests.py tests/unit/data/test_prepare.py tests/unit/test_cli.py tests/integration/test_wp9a_refresh_data_pipeline.py` → **170 passed**.
- `make lint` → **PASS**: Ruff check, Ruff format check, strict mypy over 121 files.
- `make test` → **1093 passed, 3 skipped, 0 failed**; the three skips are the existing real-Piston opt-in cases and WP9-a does not depend on Piston.
- Reviewer-owned R1-M2 counterexample after repair returned `{'b': ('a', 'near_external_duplicate', 0.9047619047619048)}` and did not reject C, confirming the transitive-collapse bug is closed.
- Reviewer-owned policy probe rejected both `RefreshDedupPolicy(1, 0.90)` and `RefreshDedupPolicy(5, 1.0)` with the frozen WP9-a protocol errors.
- **Formal-reference snapshot adversarial reproduction (`R2-M1`)**: starting from a valid fixture materialization, reviewer changed one selected `external_new` canonical/training row so its raw statement and function contract exactly matched the unchanged formal validation problem; rebuilt that selected fingerprint to match the tampered canonical bytes; then emptied only `manifest/reference_snapshots.json -> fingerprints.validation` and updated all affected root artifact hashes. `check_refresh_data()` still returned success: `CHECK_PASSED_WITH_HIDDEN_VALIDATION_OVERLAP 8 <selected-id> validation-block`. The authoritative `reference_dataset_dir/canonical/problems.jsonl` was not changed.
- **SFT hard-cap adversarial reproduction (`R2-M2`)**: `refresh_data_config_from_mapping()` accepted `version=wp9a-refresh-v1` with `sft_overlap_fraction=0.50` and `sft_overlap_hard_max=0.50`. A fixture `prepare_refresh_data()` followed by `check_refresh_data()` under that policy also succeeded and reported `CHECK_PASSED_50_PERCENT_SFT 4 8 0.5`.

### Findings

#### R2-M1 — strict readback trusts mutable formal-reference fingerprint buckets instead of rebuilding them from the authoritative reference canonical

**Severity:** Major / actionable.

`check_refresh_data()` verifies that `reference_snapshots.json.formal.canonical_sha256` equals the supplied formal canonical file (`refresh.py:1002-1017`), but then obtains all SFT/validation/project-test fingerprints by blindly decoding the snapshot's stored `fingerprints` lists through `_reference_fingerprints_from_snapshot()` (`refresh.py:819-831,1018`). It never rebuilds the formal SFT/validation/project-test references from the already-available authoritative `reference_dataset_dir/canonical/problems.jsonl`, never compares the stored fingerprint buckets to those rebuilt values, and does not reconcile stored formal split counts with actual split counts.

The reviewer reproduction demonstrates a core acceptance failure rather than a cosmetic manifest issue: actual canonical training content can exactly overlap the unchanged formal validation split while strict readback certifies zero validation overlap, provided the mutable validation fingerprint bucket is removed and its artifact hash is made self-consistent. This violates the Refresh spec's validation/project-test zero-overlap requirement and the sealed plan's fail-closed strict-readback contract.

Required repair:

- rebuild the formal `sft`, `validation`, and `project_test` `OverlapReference`/fingerprint sets directly from `reference_dataset_dir/canonical/problems.jsonl` during `check_refresh_data()` and use those rebuilt values for overlap auditing;
- compare the stored formal fingerprint buckets byte/semantic-wise to the rebuilt fingerprints and fail closed on missing/extra/changed entries; recompute and verify actual formal split counts and cross-check root `formal_reference_canonical_sha256` as well;
- cross-bind the stored external-eval snapshot identity/count/fingerprint inventory to the root manifest as far as the check-only CLI can independently establish, without weakening the pinned external-eval contract;
- add an adversarial regression matching the reviewer case: a selected canonical row overlaps unchanged formal validation while the stored validation fingerprint list and root hashes are rewritten; strict readback must reject it.

#### R2-M2 — `wp9a-refresh-v1` can raise the SFT-overlap hard maximum above the specification's mandatory 15%

**Severity:** Major / actionable.

The active Refresh spec freezes `hard_max_fraction_of_grpo: 0.15` and requires at least 85% new problems. The sealed WP9-a plan uses an exact 7.5% overlap and 15% hard max. However `_validate_selection_config()` only checks that overlap is within `[0,1]`, hard max is within `[0,1]`, and target overlap does not exceed that caller-provided hard max (`refresh.py:220-229`). `check_refresh_data()` similarly accepts the manifest's own `sft_overlap_hard_max` and only checks the selected fraction against that mutable value (`refresh.py:976-1000,1074-1081`).

Therefore the same production schema can redefine its own safety limit. Reviewer confirmed a `wp9a-refresh-v1` config with 50% target/50% hard max is accepted, and the producer plus strict checker certifies a 50% SFT-overlap fixture. On the real 10k pool, values above 15% such as 20% are also population-feasible with the frozen 2,500-problem SFT train split. This is the same class of production-boundary weakening that R1-M3 fixed for the near-dedup threshold, but it affects the experiment's primary overlap policy.

Required repair:

- enforce the WP9 hard maximum independently of caller input: `sft_overlap_hard_max` must never exceed `0.15` for `wp9a-refresh-v1`, and strict readback must reject both a manifest hard max above 0.15 and any actual selected overlap above 0.15;
- because the sealed WP9-a production protocol is 10,000 / 7.5% / 15%, either freeze those exact production values at the file/config boundary or introduce an explicit test/internal protocol that cannot be mistaken for production `wp9a-refresh-v1` artifacts;
- add config/readback regressions for `0.20`/`0.50` hard-max variants and self-consistent manifests that attempt to authorize >15% overlap.

#### R2-M3 — the repaired dedup implementation has not completed the plan-required fresh real pinned-source materialization and deterministic rerun

**Severity:** Major / actionable acceptance gap.

The E1 repair materially changes the external dedup algorithm. Its own bounded real-source classification reports `9,565` retained external candidates, whereas the pre-repair run9/run10 artifact recorded `9,453`. Therefore the old run9/run10 artifacts cannot be outputs of the repaired producer under the same inputs: at minimum their dedup report/root retained count is stale, and the retained population feeding deterministic 9,250 selection has changed.

E1 explicitly records that two fresh repaired prepares (`wp9a-refresh-seed42-repair-e1/e2`) hit the 180-second command limit and were terminated before atomic publish; neither is counted as a successful materialization. The only completed real-data post-repair checks are bounded classification plus strict readback of the old `run9`. Passing a readback of a pre-repair artifact does not satisfy the sealed plan's `real pinned-source engineering materialization + strict readback` and same-seed byte-identical rerun gates for the code being reviewed, especially because `check_refresh_data()` intentionally does not reload the source snapshots and recompute the producer's dedup/selection decisions.

Required repair:

- complete a fresh real `prepare-refresh-data` using the repaired code, tracked `configs/data/refresh.yaml`, pinned DeepCoder/HumanEvalPlus revisions, frozen formal reference root, and seed 42 into a new logical output; then complete fresh strict readback;
- complete a second fresh same-seed repaired materialization and verify the deterministic artifact set is byte-for-byte identical;
- record the new repaired root-manifest SHA, retained-candidate count, selected/order hash, overlap/quality summaries, commands and exit codes in the E2 execution report; do not reuse E0 run9/run10 as current-code producer acceptance;
- if the control-plane command limit remains a blocker, repair the bounded-memory/performance path or use an allowed execution mechanism that produces a completed, attributable command result rather than counting a timed-out background process.

### Executor claim audit

- E1 provenance, changed-file scope, R1-M2 direct-representative repair, R1-M3 5-gram/0.90 freeze, focused tests, lint, and full regression-suite claims are independently substantiated.
- E1's R1-M1 statement is substantiated for selected canonical fingerprints, quality flags, and the three report values, but it overstates the end-to-end strict-readback guarantee because formal SFT/validation/project-test fingerprints remain mutable snapshot assertions (`R2-M1`).
- The old real run9 strict-readback PASS is reproducible as a checker property, but it is not evidence that the repaired producer can regenerate an accepted real dataset; E1 itself documents that both fresh repaired prepares failed to publish (`R2-M3`).
- The execution report does not claim those failed attempts succeeded, so the issue is an incomplete sealed-plan acceptance gate rather than falsified execution reporting.

### Conclusion

**NEEDS REPAIR** for `reviewed_head_commit=b57391237dc2bd8ef5b23b258c4d5aebbadded3d`.

The three original R1 defects are substantially repaired, and all repository regression gates pass, but WP9-a still cannot be accepted: strict readback can hide a real formal-validation overlap by rewriting its stored formal-reference fingerprint bucket, the production schema can redefine the mandatory 15% SFT-overlap hard cap, and the changed dedup producer has not yet completed the plan-required fresh real 10k materialization plus deterministic rerun.

```yaml
repair_routing:
  version: 1
  required: true
  source_review_round: 2
  mode: single
  complexity: normal
  single_class: normal
  parallelizability: medium
  multi_benefit: low
  independent_workstreams: 1
  repair_issue_ids:
    - R2-M1
    - R2-M2
    - R2-M3
  rationale:
    - "R2-M1 and R2-M2 both require coordinated changes to the same refresh config/readback contract and overlapping tests in refresh.py; the real-data rerun in R2-M3 must happen only after those semantics are fixed."
    - "The code fixes are bounded control-plane work, while the final real materialization is a single dependent acceptance lane; parallel tracked write scopes would add merge/provenance risk without useful independent throughput."
  workstream_candidates: []
```

Next lifecycle action: run `stage-lifecycle checkpoint_review` for `WP9-a`; after checkpointing R2, route a single repair execution for `R2-M1`, `R2-M2`, and `R2-M3`. Reviewer-ex does not commit, merge, update proceedings, finalize, or clean up the stage.

## R3 — R2 repair independent review

```yaml
review_record:
  version: 1
  stage_id: WP9-a
  review_round: 3
  source_execution_id: E2
  reviewed_head_commit: 65b5d74f6561ed7638726c527a35ed7552160f23
  conclusion: needs_repair
```

### Review scope and provenance guard

- Reviewer did not participate in the latest E2 repair execution. The exact stage worktree is `/home/dzy/open-r1-code-verifier/.worktrees/wp9-a`, branch `feat/wp9-a`; review began clean at `HEAD=65b5d74f6561ed7638726c527a35ed7552160f23`.
- The sealed plan remains `72a91b652a38fe4e7e58a396c76bfd77fb46a66b`, with `stage_profile=development`, `control_plane_hardware=GTX 1660 Ti (6GB)`, `target_hardware=GTX 1660 Ti (6GB)`, `evidence_class=engineering`, `development_terminal=false`.
- R2 was checkpointed at `6ce65f8f4855c2a2f5fbbd4838140e6c35508819`. The first E2 code commit `1ed56065ae35e1d41893b5cc7865b190d4bb994c` has that checkpoint as its parent; the final E2 code commit is `bee206c9ed04a5d7a18e308e0b48ffa71e0d704d`; the execution-report commit `65b5d74f6561ed7638726c527a35ed7552160f23` has `bee206c...` as its parent.
- Latest completed execution record is `E2`, `task_kind=repair`, `source_review_round=2`, `source_review_commit=6ce65f8f4855c2a2f5fbbd4838140e6c35508819`, `repair_issue_ids=[R2-M1,R2-M2,R2-M3]`, `status=completed`. `git log` identifies the current HEAD as the commit that added that record.
- `git ls-files .ai-bridge` is empty. E2's long-running second materialization used ignored local `.ai-bridge` runner/status/log files; they remain untracked transport state and are not part of repository history.

### R2 issue disposition

| Previous issue | R3 disposition |
|---|---|
| `R2-M1` | **Partially resolved; remains actionable.** Formal SFT/validation/project-test buckets are now rebuilt from the authoritative formal canonical and compared to the stored snapshot. However the external-eval fingerprint inventory is still only a mutable stored bucket whose dataset/revision/count/projection fields are checked for self-consistency; reviewer reproduced a real external-eval overlap that passes after replacing the HumanEvalPlus fingerprint bucket with an unrelated same-count fingerprint. |
| `R2-M2` | **Resolved for the reported hard-cap/config bypass.** File config now freezes 10,000 / 0.075 / 0.15, runtime validation independently caps the hard max at 0.15, and strict readback rejects configured or actual overlap above 15%. Reviewer found a separate strict-checker production-identity issue recorded as `R3-M2`. |
| `R2-M3` | **Resolved.** Reviewer independently strict-checked both repaired real outputs `final1` and `final4`, then compared all 13 files: exact file sets, zero SHA256 mismatches, and root manifest SHA256 `98a0fb8192661f6358c29819d8a70eb4039397cc2a3ec5444f0581cfbcb81625`. Both outputs report 10,000 selected, 9,565 external retained, 750 SFT reuse, and 1,086 quality-gate-required. |

### Reviewer-owned verification

- Focused sealed-plan suite: `uv run python -m pytest tests/unit/data/test_refresh_sources.py tests/unit/data/test_refresh_dedup.py tests/unit/data/test_refresh.py tests/unit/data/test_split_tests.py tests/unit/data/test_prepare.py tests/unit/test_cli.py tests/integration/test_wp9a_refresh_data_pipeline.py` → **179 passed**.
- `make lint` → **PASS**: Ruff check, Ruff format check, strict mypy over 121 files.
- `make test` → **1102 passed, 3 skipped, 0 failed**; the three skips are the repository's existing real-Piston opt-in cases and are unrelated to WP9-a.
- Fresh reviewer readback of `/home/dzy/wp9a-refresh-seed42-r2e2-final1` → exit 0, selected 10,000, retained external 9,565, SFT overlap 750/10,000, quality-gate-required 1,086.
- Fresh reviewer readback of `/home/dzy/wp9a-refresh-seed42-r2e2-final4` → the same counts and exit 0. Independent file comparison reported `13/13` identical files, `0` mismatches, root SHA `98a0fb8192661f6358c29819d8a70eb4039397cc2a3ec5444f0581cfbcb81625`.
- Reviewer independently read final1's source evidence: PrimeIntellect 16,252 scanned / 11,323 accepted / projection `6241f5c56810008cf12cb94b47d9ec8fd49f5048fa2900d77b3ce87531f2480c`; TACO 7,436 / 2,642 / `d5b1242810ec37f9a524a7e2c7b3731595e269544b7add719cccfea51e2fe6de`; HumanEvalPlus count 164 / projection `d538bb58cbf89c74001c7e60b21a38552af6666da695e27182d66c97297b0314`; formal split counts 2,500/300/400 and canonical SHA `d310b68f5644214177c00784d8af64e8a87dbd982068c028f72ec5974d3d71c6`.
- **External-eval inventory bypass (`R2-M1`)**: reviewer changed one selected external canonical/training row so its raw statement and contract exactly matched the unchanged pinned HumanEvalPlus fixture reference; rebuilt the selected fingerprint; replaced only `reference_snapshots.json.fingerprints.external_eval` with an unrelated same-count external-eval fingerprint while leaving the pinned dataset/revision/license/count/projection fingerprint and root external-eval identity unchanged; updated affected artifact hashes. `check_refresh_data()` returned success: `EXTERNAL_SNAPSHOT_BYPASS_PASSED 7 <selected-id> humanevalplus:HumanEval/fixture-0`.
- **Source provenance bypass (`R3-M1`)**: `refresh_data_config_from_mapping()` accepted `wp9a-refresh-v1` with an arbitrary DeepCoder-style source identity (`some/other-deepcoder@111...`) while the production selection/external-eval fields were frozen. Separately, reviewer rewrote a valid artifact's `manifest/source_snapshots.json` and root `sources/source_projection_fingerprints` to `evil/replacement@ffff...`, license `UNKNOWN`, projection `eeee...`, updated the source-snapshot artifact hash, and strict readback still returned success: `SOURCE_PROVENANCE_TAMPER_PASSED 7 evil/replacement ffff...`.
- **Non-production protocol certification (`R3-M2`)**: the same public `check_refresh_data()` used by `check-refresh-data` successfully certified a `wp9a-refresh-v1` fixture artifact with only 7 selected problems and SFT overlap `1/7 = 0.142857...`: `NONPROD_SCHEMA_CHECK_PASSED 7 0.142857... 7 0.142857...`. The prepare CLI's YAML loader freezes 10,000/0.075/0.15, but the checker receives no config and does not enforce those exact production values.

### Findings

#### R2-M1 — external-eval fingerprints remain a mutable trust root, so HumanEvalPlus overlap can still be hidden

**Severity:** Major / actionable; previous issue remains open in narrowed form.

The formal-reference portion of R2-M1 is fixed: `check_refresh_data()` reloads `reference_dataset_dir/canonical/problems.jsonl`, recomputes split counts and formal fingerprints, compares stored formal buckets, and uses rebuilt values (`refresh.py:1066-1104`). The external-eval path is different. It decodes `reference_snapshots.json.fingerprints.external_eval`, then only verifies that the adjacent snapshot claims the frozen HumanEvalPlus identity/license, that `scanned_rows == accepted_rows == len(stored_fingerprints) > 0`, that `projection_fingerprint_sha256` merely has a 64-hex shape, and that the root manifest repeats the same projection string (`refresh.py:1106-1152`). It never establishes that the stored fingerprint inventory was actually derived from the pinned HumanEvalPlus projection.

The reviewer reproduction preserves every check currently implemented—including pinned dataset/revision/license, count, projection field, and root equality—but substitutes an unrelated same-count fingerprint inventory. Because overlap auditing then uses that substituted bucket, actual canonical/training content exactly matching the unchanged external evaluation reference is certified as zero overlap. This violates Refresh §6.3's hard requirement that HumanEvalPlus exact/accepted-near overlap be zero and the sealed plan's strict-readback fail-closed requirement.

Required repair:

- independently anchor the exact HumanEvalPlus fingerprint inventory for the frozen revision. Acceptable designs include reloading/rebuilding the pinned source during `check-refresh-data` (with an explicit cache/source input) or comparing the stored inventory to a tracked immutable expected inventory hash/count derived from the frozen source; root↔snapshot self-consistency alone is not sufficient;
- enforce the known pinned reference count/inventory identity rather than merely `count > 0`, and fail closed if any stored external-eval fingerprint is removed/replaced/reordered contrary to the frozen inventory contract;
- add the reviewer adversarial regression: selected canonical content overlaps the real external-eval reference while the stored same-count fingerprint bucket is replaced and all local hashes remain self-consistent; checker must reject it.

#### R3-M1 — candidate-source provenance is neither frozen at the production config boundary nor semantically checked during strict readback

**Severity:** Major / actionable.

The sealed plan fixes the enabled source projection to the two DeepCoder configs at revision `177913a7bd43791646ef6a43645caa3c871ab3db`, MIT, and requires source revision/license/provenance/projection fingerprints to be auditable. Refresh §6.4 likewise requires each source revision, license/provenance, fingerprint and schema mapping to be frozen before formal materialization. Yet `refresh_data_config_from_mapping()` currently freezes the selection and HumanEvalPlus identity but accepts arbitrary `adapter=deepcoder` source dataset/revision/config/license values (`refresh.py:167-197,217-243`). On readback, `manifest/source_snapshots.json` is only covered by generic byte hash/row accounting; `check_refresh_data()` never loads it semantically, never validates root `sources`, and never cross-checks root `source_projection_fingerprints` against source snapshots.

The reviewer demonstrated both sides: an arbitrary source config is accepted under `wp9a-refresh-v1`, and a fully prepared artifact can have its source dataset/revision/license/projection provenance rewritten in both source snapshot and root manifest while `check-refresh-data` still passes. The actual E2 final1/final4 happen to contain the correct pinned identities and hashes, but strict readback cannot prove that property and can certify falsified provenance.

Required repair:

- freeze the exact WP9-a production source specifications at the file/config boundary: exactly the approved DeepCoder PrimeIntellect/TACO source names, dataset id, full revision, config names, split, MIT license and adapter unless a new schema/spec amendment explicitly authorizes another source;
- make strict readback parse `manifest/source_snapshots.json`, validate exact shape/unique source identities/count types/fingerprint format, and cross-bind every snapshot to root `sources` and `source_projection_fingerprints`;
- provide an independent anchor for the pinned projection fingerprints (tracked expected projection hashes or source reload) so rewriting both mutable copies cannot falsify consumed-projection provenance;
- add config and self-consistent artifact-tamper regressions matching the reviewer probes.

#### R3-M2 — the production `check-refresh-data` CLI can certify non-production pools under `wp9a-refresh-v1`

**Severity:** Major / actionable.

E2 correctly freezes file-based preparation configs to `target_size=10000`, `sft_overlap_fraction=0.075`, and `sft_overlap_hard_max=0.15`. However `check-refresh-data` does not load that config (`cli.py:250-255`), and `check_refresh_data()` only requires `target_size > 0`, protocol arithmetic consistency, and overlap values at or below 15% (`refresh.py:1010-1059,1185-1194`). It does not require the sealed production values 10,000 / 0.075 / 0.15 / 750 / 9,250.

This is observable on the repository's own internal fixture path: a 7-problem, 1/7-overlap artifact carries `schema_version=wp9a-refresh-v1` and is accepted by the same public strict checker used by the production CLI. That contradicts the sealed plan's strict-readback statement that SFT reuse is exactly 750 / 7.5% and the tracked production protocol is 10,000 / 0.075 / 0.15. A user can therefore present a self-consistent non-production artifact to `check-refresh-data` and receive a successful certification under the production schema.

Required repair:

- for `wp9a-refresh-v1`, strict readback must independently require `target_size=10000`, `sft_overlap_fraction=0.075`, `sft_overlap_hard_max=0.15`, `sft_overlap_count=750`, and `external_new_count=9250`, in addition to recomputing actual counts;
- preserve small fixture coverage via a clearly separate internal/test protocol or an explicit non-production checker mode that the production `check-refresh-data` CLI cannot silently invoke; do not let test artifacts claim the production schema while relaxing its frozen pool identity;
- add a regression that a small/self-consistent `wp9a-refresh-v1` artifact is rejected by the production checker.

### Executor claim audit

- E2 provenance, changed-file scope, formal-reference rebuilding, 15% hard-cap enforcement, regression counts, lint and full-suite claims are independently substantiated.
- E2's real-data materialization/determinism claims are independently substantiated at the artifact level: both final1/final4 strict readbacks pass and all 13 files are byte-identical with the reported root SHA.
- E2's statement that R2-M1 is fully repaired is **not substantiated** for external evaluation: the HumanEvalPlus fingerprint inventory remains replaceable without detection.
- E2's production source/protocol artifacts are correct in the two accepted real outputs, but the checker does not independently enforce those source/protocol identities, so successful readback currently proves less than the execution report and sealed plan claim.

### Conclusion

**NEEDS REPAIR** for `reviewed_head_commit=65b5d74f6561ed7638726c527a35ed7552160f23`.

E2 closes the real-materialization gate and the concrete 15% hard-cap bypass, and all repository tests pass. WP9-a nevertheless cannot PASS while the production checker can (1) hide a true HumanEvalPlus overlap by replacing the external-eval fingerprint inventory, (2) certify falsified candidate-source provenance, and (3) certify non-production pool sizes/overlap fractions under the production `wp9a-refresh-v1` schema.

```yaml
repair_routing:
  version: 1
  required: true
  source_review_round: 3
  mode: single
  complexity: normal
  single_class: normal
  parallelizability: medium
  multi_benefit: low
  independent_workstreams: 1
  repair_issue_ids:
    - R2-M1
    - R3-M1
    - R3-M2
  rationale:
    - "All remaining findings are the same strict-readback/config provenance boundary in refresh.py and overlapping unit/integration tests; splitting tracked writes would create conflicts and inconsistent schema decisions."
    - "The repair is bounded control-plane code plus adversarial regressions; after semantics are fixed, existing real outputs can be rechecked or regenerated if the artifact schema changes, so one serial lane is the safest provenance-preserving route."
  workstream_candidates: []
```

Next lifecycle action: run `stage-lifecycle checkpoint_review` for `WP9-a`; after checkpointing R3, route one repair execution for `R2-M1`, `R3-M1`, and `R3-M2`. Reviewer-ex does not commit, merge, update proceedings, finalize, or clean up the stage.

## R4 — R3 repair independent review

```yaml
review_record:
  version: 1
  stage_id: WP9-a
  review_round: 4
  source_execution_id: E3
  reviewed_head_commit: d25ec3c704ad7dd08bbea9dac209e07d9de08ff7
  conclusion: needs_repair
```

### Review scope and provenance guard

- Reviewer did not participate in the latest E3 repair execution. The exact stage worktree is `/home/dzy/open-r1-code-verifier/.worktrees/wp9-a`, branch `feat/wp9-a`; review began clean at `HEAD=d25ec3c704ad7dd08bbea9dac209e07d9de08ff7`.
- The sealed plan remains `72a91b652a38fe4e7e58a396c76bfd77fb46a66b`, with `stage_profile=development`, `control_plane_hardware=GTX 1660 Ti (6GB)`, `target_hardware=GTX 1660 Ti (6GB)`, `evidence_class=engineering`, `development_terminal=false`.
- R3 was checkpointed at `d87ae07ec3750274a2f37b9983a60b6a5e327f17`. E3 code commit `6bfd1619bf7a578b26f2195ad58ab69ef1e111e8` has that review commit as its parent, and the E3 execution-report commit `d25ec3c704ad7dd08bbea9dac209e07d9de08ff7` has the code commit as its parent.
- Latest completed execution record is `E3`, `task_kind=repair`, `source_review_round=3`, `source_review_commit=d87ae07ec3750274a2f37b9983a60b6a5e327f17`, `repair_issue_ids=[R2-M1,R3-M1,R3-M2]`, `status=completed`.
- `git ls-files .ai-bridge` is empty and the tracked stage remained clean throughout reviewer verification.

### R3 issue disposition

| Previous issue | R4 disposition |
|---|---|
| `R2-M1` | **Resolved.** Production readback now freezes HumanEvalPlus count/projection and an exact fingerprint-inventory SHA. Reviewer independently rebuilt the pinned 164-reference inventory from the local pinned cache and obtained projection `d538bb58cbf89c74001c7e60b21a38552af6666da695e27182d66c97297b0314` and inventory SHA `b9cf681ddf22f2195ff1a74added578b0dd58108031d93fd4c9a560fd58f5dac`, exactly matching the tracked anchors. A same-count fingerprint replacement with updated artifact hash is rejected. |
| `R3-M1` | **Resolved for the reported source-config/source-snapshot trust roots.** `wp9a-refresh-v1` now freezes the exact two DeepCoder specs and production readback requires the exact pinned scan/accepted/projection snapshots; reviewer confirmed arbitrary source config and self-consistent root+source-snapshot replacement are rejected. A different downstream provenance gap—selected rows are not bound to retained dedup decisions/raw identities—is recorded as new `R4-M1`. |
| `R3-M2` | **Resolved.** Production readback independently freezes 10,000 / 0.075 / 0.15 / 750 / 9,250. Small fixtures now emit `wp9a-refresh-test-v1` and require explicit `allow_test_protocol=True`; the production CLI path does not enable it. |

### Reviewer-owned verification

- Focused sealed-plan suite: `uv run python -m pytest tests/unit/data/test_refresh_sources.py tests/unit/data/test_refresh_dedup.py tests/unit/data/test_refresh.py tests/unit/data/test_split_tests.py tests/unit/data/test_prepare.py tests/unit/test_cli.py tests/integration/test_wp9a_refresh_data_pipeline.py` → **182 passed**.
- `make lint` → **PASS**: Ruff check, Ruff format check, strict mypy over 121 files.
- `make test` → **1105 passed, 3 skipped, 0 failed**; the three skips are the existing real-Piston opt-in cases and WP9-a does not depend on Piston.
- Fresh strict readback of `/home/dzy/wp9a-refresh-seed42-r2e2-final1` under E3 → exit 0: selected 10,000, external retained 9,565, SFT overlap 750/10,000, quality-gate-required 1,086.
- Pinned HumanEvalPlus source reload from `/home/dzy/.cache/huggingface` independently produced 164 references and exactly matched both E3 frozen projection/inventory hashes. A production artifact with one external-eval fingerprint replaced and the reference-snapshot artifact hash updated failed closed with `external-eval fingerprints do not match the frozen inventory`.
- An arbitrary production config source (`some/other-deepcoder@111...`) failed with `ConfigError ... freezes the two approved DeepCoder projections`. A self-consistent production source snapshot/root rewrite to `evil/replacement@ffff...` failed closed with `source snapshots do not match the frozen WP9-a production projections`.
- A direct reviewer reload of both full DeepCoder projections from the local cache exceeded the CodexPro 180-second command limit and was terminated; it is not counted as successful evidence. This does not invalidate the repaired checker gate: the existing real output carries the previously audited pinned snapshots, current strict readback enforces those exact tracked anchors, and E3 did not modify `refresh_sources.py`.
- Existing real artifact consistency is good: reviewer cross-joined all 9,250 `external_new` selection rows against the 13,965 dedup decisions and observed **0 mismatches** for candidate ID, `retained=true`, source name, source-record ID, and raw-record SHA.
- **Selected raw-provenance tamper (`R4-M1`)**: on a production-shadow tree of final1, reviewer changed one external selection row's real `source_record_id/raw_record_sha256` from `primeintellect/train/5509` / `ec22cd...eb4` to `forged-source-record` / `ffff...`, updated only the selection artifact SHA in the root manifest, and `check_refresh_data()` still returned success: `SELECTED_PROVENANCE_TAMPER_PASSED 10000 ...`.
- **Retained-decision contradiction (`R4-M1`)**: reviewer changed the same kind of selected external candidate's dedup decision from `(retained=true, rejection_reason=null, overlap_class=none)` to `(retained=false, forged_rejection, evaluation_overlap)` and updated only the dedup-decisions artifact SHA. Production strict readback still returned success: `SELECTED_REJECTED_DECISION_TAMPER_PASSED 10000 <candidate-id> ...`.

### Finding

#### R4-M1 — strict readback does not bind selected external rows to frozen raw-candidate provenance and retained dedup decisions

**Severity:** Major / actionable.

E3 correctly anchors the source-level identities: `refresh.py:1041-1136` parses `source_snapshots.json`, cross-binds root source specs/projection fields, and for production requires exact tracked DeepCoder snapshot values. However the selected-row provenance chain is still unchecked. `_canonical_selection_fingerprint()` (`refresh.py:543-590`) validates the stored fingerprint against canonical bytes plus `source`/`difficulty`/`overlap_origin`, but it never validates the selection record's `schema_version`, `source_record_id`, or `raw_record_sha256`. `SELECTION_SCHEMA_VERSION` is only used when writing records. More importantly, `check_refresh_data()` never reads `manifest/dedup_decisions.jsonl` at all, so it never proves that an `external_new` selection came from a candidate that the frozen-source classifier actually marked retained.

This is a direct acceptance-contract break, not merely cosmetic provenance. The sealed plan requires every accepted candidate to carry a stable candidate identity and raw-record hash (`plan:159`), requires the 9,250 new selections to come **only** from `classify_refresh_candidates` retained external candidates (`plan:331`), and says strict readback must fail closed on self-consistent tamper (`plan:381-386`). Refresh §6.4 requires frozen source provenance/fingerprints and §6.6 requires a machine-readable candidate dedup manifest with candidate/source identity and retained/rejected status. The two reviewer attacks show the current checker can certify mutually contradictory claims: the selected artifact can claim a forged raw source record, and the dedup manifest can simultaneously say that an actually selected candidate was rejected for evaluation overlap.

The real final1 artifact itself is internally correct—9,250/9,250 selected external rows currently match retained decisions and raw provenance—so this is a checker/provenance-binding defect rather than evidence that E2's real materialization selected bad data.

Required repair:

- add exact-schema strict parsers for `selection.jsonl` and `dedup_decisions.jsonl`; require `selection.schema_version=wp9a-selection-v1`, reject unknown/missing fields and type drift, require external `source_record_id` non-empty plus `raw_record_sha256` valid 64-hex, and require SFT-reuse provenance fields to have their defined null form;
- during production readback, require one unique dedup decision for every accepted source candidate and cross-bind every selected `external_new` record to the decision with the same candidate/problem ID, `retained=true`, no rejection, `overlap_class=none`, and exact `source_name/source_record_id/raw_record_sha256` equality;
- do not stop at cross-binding two mutable files. Independently anchor the accepted-candidate provenance inventory for each frozen source (for example a tracked per-source SHA over deterministic `(candidate_id, source_record_id, raw_record_sha256)` tuples produced from the pinned source) or explicitly reload the source projection during check. This must make a self-consistent selection+decision rewrite fail closed;
- recompute and exact-check `reports/dedup_summary.json` plus root `total_candidates_scanned` / `external_candidates_retained` from the frozen source snapshots and parsed dedup decisions so the candidate/dedup evidence chain is one coherent contract;
- add production-mode adversarial regressions matching both reviewer reproductions: forged selected raw provenance with updated hashes, and a selected external candidate changed to a rejected dedup decision with updated hashes. Both must be rejected;
- if the repair only adds readback validation/anchors and does not change artifact bytes, re-run strict checks on existing final1/final4; if it changes production artifact schema or bytes, regenerate the same-seed deterministic real pair before claiming acceptance.

### Executor claim audit

- E3 provenance and changed-file scope are valid; the code commit is directly parented by the R3 review and the execution-report commit is directly parented by the E3 code commit.
- E3's `R2-M1` claim is independently substantiated, including a fresh pinned-source recomputation of the HumanEvalPlus inventory anchor.
- E3's `R3-M2` claim is substantiated by code inspection plus the focused suite: production exact pool values are independently enforced and test artifacts are on a distinct opt-in schema.
- E3's `R3-M1` claim is substantiated at the source-config/source-snapshot level, but it overstates end-to-end candidate provenance: source-level anchors are not connected to per-selection raw provenance or retained dedup decisions (`R4-M1`).
- E3's reported host-side full-suite result is independently reproduced: **1105 passed, 3 skipped**. The reviewer's attempted full DeepCoder source reload timed out under the same 180-second tool bound and is not treated as a pass or a new blocker.

### Conclusion

**NEEDS REPAIR** for `reviewed_head_commit=d25ec3c704ad7dd08bbea9dac209e07d9de08ff7`.

E3 closes the three specific R3 trust-boundary attacks and all repository regression gates pass. WP9-a still cannot PASS because strict readback can certify an external selection whose raw source provenance has been forged and can certify a dataset where the dedup manifest explicitly says that a selected external candidate was rejected. The real final1 data is internally consistent; the remaining defect is the fail-closed provenance binding required to prove that fact during readback.

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
    - R4-M1
  rationale:
    - "The remaining defect is one coherent readback/provenance chain in refresh.py: selection schema, dedup-decision parsing, source-inventory anchoring, and dedup-summary/root reconciliation must agree atomically."
    - "The tests and production-shadow adversarial cases touch the same checker contract, so multiple tracked write lanes would add collision risk without independent throughput benefit."
  workstream_candidates: []
```

Next lifecycle action: run `stage-lifecycle checkpoint_review` for `WP9-a`; after checkpointing R4, route one repair execution for `R4-M1`. Reviewer-ex does not commit, merge, update proceedings, finalize, or clean up the stage.

## R5 — R4 repair independent review

```yaml
review_record:
  version: 1
  stage_id: WP9-a
  review_round: 5
  source_execution_id: E4
  reviewed_head_commit: 453fbd423a871ff3b9e0e652c1cee1a58e81afdc
  conclusion: needs_repair
```

### Review scope and provenance guard

- Reviewer did not participate in the latest E4 repair execution. The exact stage worktree is `/home/dzy/open-r1-code-verifier/.worktrees/wp9-a`, branch `feat/wp9-a`; review began clean at `HEAD=453fbd423a871ff3b9e0e652c1cee1a58e81afdc` and that HEAD remained unchanged throughout review.
- The sealed plan remains `72a91b652a38fe4e7e58a396c76bfd77fb46a66b`, with `stage_profile=development`, `control_plane_hardware=GTX 1660 Ti (6GB)`, `target_hardware=GTX 1660 Ti (6GB)`, `evidence_class=engineering`, `development_terminal=false`.
- R4 was checkpointed at `3badd4cb0149ee6fecf9297156a7eb8642ae6b4d`. E4 code commit `c2cddff5bc947e8a0ee279b655cbbec527f02afd` has that review commit as its parent, and the E4 execution-report commit/current HEAD `453fbd423a871ff3b9e0e652c1cee1a58e81afdc` has the code commit as its parent.
- Latest completed execution record is `E4`, `task_kind=repair`, `source_review_round=4`, `source_review_commit=3badd4cb0149ee6fecf9297156a7eb8642ae6b4d`, `repair_issue_ids=[R4-M1]`, `status=completed`.
- `git ls-files .ai-bridge` is empty. E4 code scope is exactly `src/code_verifier/data/refresh.py`, `tests/unit/data/test_refresh.py`, and `tests/integration/test_wp9a_refresh_data_pipeline.py`; plan/review/spec/proceedings and `third_party/open-r1` were not modified by the repair.

### R4 issue disposition

| Previous issue | R5 disposition |
|---|---|
| `R4-M1` | **Resolved.** Strict readback now exact-schema parses selection and dedup-decision records, freezes per-source accepted-candidate provenance inventories, cross-binds every selected external row to its retained dedup decision, and recomputes dedup summary/root counts. Reviewer independently replayed both R4 production attacks plus a stronger self-consistent selection+decision provenance rewrite; all fail closed. |

### Reviewer-owned verification

- Focused sealed-plan suite: `uv run python -m pytest tests/unit/data/test_refresh_sources.py tests/unit/data/test_refresh_dedup.py tests/unit/data/test_refresh.py tests/unit/data/test_split_tests.py tests/unit/data/test_prepare.py tests/unit/test_cli.py tests/integration/test_wp9a_refresh_data_pipeline.py` → **186 passed**.
- `make lint` → **PASS**: Ruff check, Ruff format check, strict mypy over 121 source/test files.
- `make test` → **1109 passed, 3 skipped, 0 failed**; the three skips are the existing real-Piston opt-in cases and WP9-a does not depend on Piston.
- Production strict readback of `/home/dzy/wp9a-refresh-seed42-r2e2-final1` under E4 → exit 0: selected 10,000, external retained 9,565, SFT overlap 750/10,000, quality-gate-required 1,086.
- Production strict readback of `/home/dzy/wp9a-refresh-seed42-r2e2-final4` under E4 → the same counts and exit 0.
- Independent deterministic comparison of final1/final4 found exactly 13/13 files in both trees, identical file sets, **0 SHA256 mismatches**, and root manifest SHA256 `98a0fb8192661f6358c29819d8a70eb4039397cc2a3ec5444f0581cfbcb81625`.
- **R4 selected raw-provenance replay:** reviewer changed one production `external_new` selection row to `source_record_id=forged-source-record`, `raw_record_sha256=ffff...`, updated the selection artifact hash, and production strict readback rejected it with `selected external provenance does not match its retained dedup decision`.
- **Stronger paired provenance replay:** reviewer changed the same source-record/raw-SHA fields in both selection and its retained dedup decision and updated both artifact hashes. Production strict readback rejected it earlier at the independent PrimeIntellect accepted-candidate inventory anchor: `deepcoder-primeintellect accepted-candidate provenance does not match frozen inventory`.
- **R4 retained-decision replay:** reviewer changed an actually selected external candidate to `retained=false / forged_rejection / evaluation_overlap`, also made `dedup_summary.json` and root retained counts self-consistent and updated affected hashes. Production strict readback still rejected it with `selected external provenance does not match its retained dedup decision`.
- **Dedup row-order tamper (`R5-M1`)**: reviewer swapped only the first two rows of the real production `manifest/dedup_decisions.jsonl`, updated that artifact SHA in the root manifest, and changed no semantic decision fields or other artifacts. Production strict readback still returned success: `DEDUP_REORDER_PASSED 10000 9565`. The valid final1 file itself is in canonical ascending `candidate_id` order across all 13,965 decisions, exactly matching `classify_refresh_candidates()` generation order.
- TACO anchor was independently rebuilt through the repository source loader from the pinned local cache: 7,436 scanned / 2,642 accepted, projection `d5b1242810ec37f9a524a7e2c7b3731595e269544b7add719cccfea51e2fe6de`, accepted-candidate inventory `6baac4a1e44340c13bf25c750836821d95b2b1c0c519588b8e977b75ce310701`; both match the E4 frozen identities.
- PrimeIntellect's initial single-command loader attempts exceeded the CodexPro 180-second ceiling and are not counted as evidence. Reviewer then reran the exact pinned parquet/raw-hash/`_candidate_from_row` contract with an 8-process fork pool: all 16,252 source rows were traversed, 11,323 were independently accepted, projection SHA `6241f5c56810008cf12cb94b47d9ec8fd49f5048fa2900d77b3ce87531f2480c` matched the frozen source snapshot, and accepted-candidate inventory SHA `37c62e2a5446517974a060242eedc93af7a44c505666346f824b12085ed3bcd0` matched the E4 anchor. This is counted as successful independent source evidence; the earlier timed-out attempts are not.

### Code and contract audit

- `_parse_selection_records()` requires the exact `wp9a-selection-v1` field set and version, validates field types, requires external source-record/raw-SHA provenance, and requires SFT-reuse provenance fields to be null.
- `_parse_dedup_decisions()` requires an exact decision schema, unique candidate IDs and source-record identities, exact per-source accepted-row coverage, coherent retained/rejected evidence, and production inventory hashes over deterministic `(candidate_id, source_record_id, raw_record_sha256)` tuples.
- `check_refresh_data()` now loads the dedup manifest before overlap checking, recomputes `dedup_summary.json`, binds root scan/retained counts to parsed evidence, and for every selected external problem requires a matching retained/no-rejection/`overlap_class=none` decision with identical source name, source-record ID and raw SHA.
- The repair is readback-only for production artifacts; existing final1/final4 bytes remain valid and deterministic, so the sealed plan's conditional regeneration rule does not require another materialization.
- No new feature, experiment definition, training behavior, reward semantics, evaluation semantics, dependency contract, or Open-R1 gitlink change was introduced.

### Finding

#### R5-M1 — dedup decision row order is not fail-closed during strict readback

**Severity:** Major / actionable.

E4 closes R4-M1's selected-provenance trust gap, but the strengthened parser still treats `manifest/dedup_decisions.jsonl` as an order-insensitive set. `classify_refresh_candidates()` emits decisions in canonical ascending `candidate_id` order (`refresh_dedup.py:517-577`), and the valid final1 artifact has all 13,965 decision IDs in exactly that order. `_parse_dedup_decisions()` (`refresh.py:743-823`) checks exact fields, uniqueness, source coverage and provenance inventories, but stores records in a dict and deliberately sorts each source inventory before hashing; it never requires the input JSONL sequence itself to equal the generator's canonical order. No later `check_refresh_data()` step restores that order invariant.

The reviewer swapped only the first two decision rows in a production-shadow copy of final1, updated the dedup-decisions artifact SHA in `refresh_manifest.json`, and changed no semantic decision fields, counts, reports, selection or canonical bytes. `check_refresh_data()` returned success: `DEDUP_REORDER_PASSED 10000 9565`. This violates the sealed plan's strict-readback requirement that any `row reorder` fail closed (`WP9-a-plan.md:381-386`) and weakens the byte-deterministic artifact contract: a non-canonical decision sequence can currently be re-hashed and certified as valid.

The real final1/final4 artifacts are not affected: both remain byte-identical, their dedup decision IDs are already canonical ascending `candidate_id`, and both pass the current checker. The defect is limited to readback's ability to prove the deterministic row-order invariant.

Required repair:

- make strict parsing require the dedup decision input sequence to be exactly ascending by unique `candidate_id`, matching `classify_refresh_candidates()` generation order; do not silently sort the input for this check;
- retain the existing per-source accepted-candidate provenance inventory anchors, which serve a different purpose and may remain order-normalized internally after the independent JSONL-order check;
- add a production-shadow regression that swaps two valid dedup-decision rows, updates the root artifact SHA, and requires `check_refresh_data()` to reject the artifact specifically for non-canonical decision order;
- re-run focused/lint/full-suite and strict-check both existing final1/final4 after the repair. Because this is readback-only and valid production bytes are already in canonical order, no rematerialization is required unless the implementation changes artifact bytes.

### Executor claim audit

- E4 Git provenance and changed-file scope are substantiated.
- E4's exact-schema, selection↔dedup cross-binding, dedup-summary/root reconciliation, accepted-candidate inventory anchors, and all three R4 provenance attack-rejection claims are independently reproduced.
- Both source-derived accepted-candidate anchors are independently reproduced from the pinned cache: TACO 7,436/2,642 with inventory `6baac4a1e44340c13bf25c750836821d95b2b1c0c519588b8e977b75ce310701`; PrimeIntellect 16,252/11,323 with projection `6241f5c56810008cf12cb94b47d9ec8fd49f5048fa2900d77b3ce87531f2480c` and inventory `37c62e2a5446517974a060242eedc93af7a44c505666346f824b12085ed3bcd0`.
- E4's focused/lint/full-suite, real strict-readback, and deterministic-pair claims are independently reproduced.
- E4 did not claim a dedup JSONL row-order guard; reviewer found that remaining sealed-plan strict-readback gap as new `R5-M1`.

### Conclusion

**NEEDS REPAIR** for `reviewed_head_commit=453fbd423a871ff3b9e0e652c1cee1a58e81afdc`.

R4-M1 is closed and the real data/evidence remain correct, but WP9-a cannot PASS while strict readback certifies a self-consistently re-hashed row-reordered `dedup_decisions.jsonl`, contrary to the sealed plan's explicit fail-closed row-order requirement. The remaining repair is narrow and readback-only.

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
    - "The only remaining actionable defect is a single strict-readback order invariant in the dedup decision parser plus one production-shadow regression."
    - "The code and test changes touch the same refresh.py/readback contract, so splitting tracked writes has no useful parallel benefit."
  workstream_candidates: []
```

Next lifecycle action: run `stage-lifecycle checkpoint_review` for `WP9-a`; after checkpointing R5, route one repair execution for `R5-M1`. Reviewer-ex does not commit, merge, update proceedings, finalize, or clean up the stage.

## R6 — R5 repair independent review

```yaml
review_record:
  version: 1
  stage_id: WP9-a
  review_round: 6
  source_execution_id: E5
  reviewed_head_commit: 0d0a00c2f0de51142404ce88c8072494c3f89a6d
  conclusion: needs_repair
```

### Review scope and provenance guard

- Reviewer did not participate in the latest E5 repair execution. The exact stage worktree is `/home/dzy/open-r1-code-verifier/.worktrees/wp9-a`, branch `feat/wp9-a`; review began clean at `HEAD=0d0a00c2f0de51142404ce88c8072494c3f89a6d`.
- The sealed plan remains `72a91b652a38fe4e7e58a396c76bfd77fb46a66b`, with `stage_profile=development`, `control_plane_hardware=GTX 1660 Ti (6GB)`, `target_hardware=GTX 1660 Ti (6GB)`, `evidence_class=engineering`, `development_terminal=false`.
- R5 was checkpointed at `afe5e0866494d22a99612b3b9439e550f34ca4ec`. E5 repair commit `27d9999f41f77a3e48cb6252b167cabdbe3108d3` has that review commit as its parent, and the E5 execution-report commit/current reviewed HEAD `0d0a00c2f0de51142404ce88c8072494c3f89a6d` has the repair commit as its parent.
- Latest completed execution record is `E5`, `task_kind=repair`, `source_review_round=5`, `source_review_commit=afe5e0866494d22a99612b3b9439e550f34ca4ec`, `repair_issue_ids=[R5-M1]`, `status=completed`.
- `git ls-files .ai-bridge` remains empty and the stage had no tracked/staged/untracked repository changes before this review append.

### R5 issue disposition

| Previous issue | R6 disposition |
|---|---|
| `R5-M1` | **Code defect resolved, acceptance incomplete.** `_parse_dedup_decisions()` now rejects any input sequence that is not strictly ascending by unique `candidate_id`, matching the producer's canonical decision order. The new parser unit test verifies an ordered two-row input passes and the reversed order fails. However R5 explicitly required a tracked production-shadow end-to-end regression that swaps two valid `dedup_decisions.jsonl` rows, rewrites the root artifact SHA, and proves public `check_refresh_data()` rejects the self-consistent tamper. E5 changed only `src/code_verifier/data/refresh.py` and `tests/unit/data/test_refresh.py`; no such integration regression was added. |

### Reviewer-owned verification

- Code inspection confirms `_parse_dedup_decisions()` maintains `previous_candidate_id` and raises `RefreshDataError("dedup decisions are not in canonical candidate_id order")` when the JSONL input order is non-increasing; the later accepted-candidate inventory sorting remains separate and does not bypass this input-order guard.
- Focused sealed-plan WP9-a suite: `uv run python -m pytest tests/unit/data/test_refresh_sources.py tests/unit/data/test_refresh_dedup.py tests/unit/data/test_refresh.py tests/unit/data/test_split_tests.py tests/unit/data/test_prepare.py tests/unit/test_cli.py tests/integration/test_wp9a_refresh_data_pipeline.py` → **186 passed**.
- `make lint` → **PASS**: Ruff check, Ruff format check, strict mypy over 121 source/test files.
- `make test` → **1109 passed, 3 skipped, 0 failed**; the three skips are the existing opt-in real-Piston cases and WP9-a does not depend on Piston.
- Production strict readback of `/home/dzy/wp9a-refresh-seed42-r2e2-final1` under E5 → exit 0: selected 10,000, external retained 9,565, SFT overlap 750/10,000, quality-gate-required 1,086.
- Production strict readback of `/home/dzy/wp9a-refresh-seed42-r2e2-final4` under E5 → the same counts and exit 0.
- Frozen formal reference canonical independently resolves to SHA256 `d310b68f5644214177c00784d8af64e8a87dbd982068c028f72ec5974d3d71c6`, matching the accepted real artifacts' reference identity.
- `git show --name-only` for E5 repair commit `27d9999...` contains only `src/code_verifier/data/refresh.py` and `tests/unit/data/test_refresh.py`; `tests/integration/test_wp9a_refresh_data_pipeline.py` is unchanged. The existing integration suite contains provenance/hard-cap tamper cases but no dedup-decision row-reorder tamper case.

### Finding

#### R6-M1 — E5 omitted the required end-to-end strict-readback row-order regression

**Severity:** Major / actionable acceptance gap.

R5-M1 was not only a parser implementation request. Its required repair explicitly called for a production-shadow regression that mutates a valid materialized artifact by swapping two `manifest/dedup_decisions.jsonl` rows, updates the corresponding root artifact SHA, and then asserts that `check_refresh_data()` fails specifically because the decision sequence is non-canonical. This test matters because the original defect existed at the public strict-readback boundary: a self-consistently re-hashed artifact was incorrectly certified.

E5 correctly adds the parser guard and a direct unit test of `_parse_dedup_decisions()`, so the underlying implementation appears repaired. But it does not add the required public-boundary regression: the repair commit does not touch `tests/integration/test_wp9a_refresh_data_pipeline.py`, and the existing integration tests do not exercise a re-hashed row-order tamper. Under reviewer-ex's actionable issue coverage rule, an explicit required regression from the previous review remains an incomplete acceptance item and prevents PASS even when manual/code-level evidence indicates the implementation is likely correct.

Required repair:

- add the exact production-shadow integration regression requested by R5: materialize or shadow a valid WP9-a artifact, swap two valid dedup-decision rows without changing their semantic fields, update only the root artifact SHA for `manifest/dedup_decisions.jsonl`, and assert `check_refresh_data()` rejects it for non-canonical candidate order;
- keep the new unit parser regression; it complements rather than replaces the end-to-end public-checker regression;
- rerun the focused WP9-a suite, `make lint`, and `make test`; because the code fix is readback-only and existing final1/final4 already have canonical decision order, no new real materialization is required unless the repair changes production artifact bytes.

### Executor claim audit

- E5 provenance is valid and its implementation claim that the parser now enforces canonical decision order is substantiated by code inspection and the unit regression.
- E5's focused/lint/full-suite verification claims are independently reproduced, and both accepted real outputs still pass production strict readback.
- The repair execution is incomplete against the exact R5 required-repair test contract: passing the unchanged integration suite does not substitute for adding the requested production-shadow regression.

### Conclusion

**NEEDS REPAIR** for `reviewed_head_commit=0d0a00c2f0de51142404ce88c8072494c3f89a6d`.

The row-order implementation defect itself is closed, all repository gates are green, and accepted real artifacts remain valid. WP9-a nevertheless cannot PASS until the required end-to-end strict-readback regression is committed, because that regression is part of the prior review's explicit acceptance contract and protects the public checker path where the defect was originally demonstrated.

```yaml
repair_routing:
  version: 1
  required: true
  source_review_round: 6
  mode: single
  complexity: very_simple
  single_class: very_simple
  parallelizability: low
  multi_benefit: low
  independent_workstreams: 1
  repair_issue_ids:
    - R6-M1
  rationale:
    - "The implementation guard is already present; the only remaining actionable work is one bounded end-to-end integration regression for the public strict-readback boundary."
    - "The repair touches a single existing integration-test file and has no independent parallel workstream or production-data regeneration requirement."
  workstream_candidates: []
```

Next lifecycle action: run `stage-lifecycle checkpoint_review` for `WP9-a`; after checkpointing R6, route the single very-simple repair `R6-M1`. `stage-lifecycle finalize` is not permitted until a later fresh reviewer-ex round records `conclusion=pass` with `repair_routing.required=false`.

## R7 — R6 repair independent review

```yaml
review_record:
  version: 1
  stage_id: WP9-a
  review_round: 7
  source_execution_id: E6
  reviewed_head_commit: ea5ae771cee06ef0e1f626377c0dd65e1f0cca9e
  conclusion: pass
```

### Review scope and provenance guard

- Reviewer did not participate in the latest E6 repair execution. Review was performed in the exact stage worktree `/home/dzy/open-r1-code-verifier/.worktrees/wp9-a` on branch `feat/wp9-a`; the worktree was clean before the review append and `.ai-bridge/**` has zero tracked paths.
- The sealed plan remains `72a91b652a38fe4e7e58a396c76bfd77fb46a66b`, with `stage_profile=development`, `control_plane_hardware=GTX 1660 Ti (6GB)`, `target_hardware=GTX 1660 Ti (6GB)`, `evidence_class=engineering`, and `development_terminal=false`.
- R6 was checkpointed at `78b61380edcfb2e10cf701e6015c92234ce4b4e0`. E6 code/test commit `fd40e526f6ec4e0d511e24f5b34762ad648b7404` has that review commit as its parent, and the E6 execution-report commit/current reviewed HEAD `ea5ae771cee06ef0e1f626377c0dd65e1f0cca9e` has the code/test commit as its parent.
- Latest completed execution record is `E6`, `task_kind=repair`, `source_review_round=6`, `source_review_commit=78b61380edcfb2e10cf701e6015c92234ce4b4e0`, `repair_issue_ids=[R6-M1]`, `status=completed`.
- E6's code/test commit changes exactly `tests/integration/test_wp9a_refresh_data_pipeline.py`; production source, plan, specs, proceedings, and `third_party/open-r1` are unchanged by E6.

### R6 issue disposition

| Previous issue | R7 disposition |
|---|---|
| `R6-M1` | **Resolved.** E6 adds the exact missing public-boundary production-shadow regression: it materializes a valid refresh artifact, swaps the first two valid dedup-decision rows, rewrites only the root SHA256 entry for `manifest/dedup_decisions.jsonl`, and asserts public `check_refresh_data()` rejects the self-consistently re-hashed artifact for non-canonical `candidate_id` order. The prior parser unit regression remains in place. |

### Code and contract audit

- The sealed plan requires strict readback to fail closed on any artifact `row reorder` (`WP9-a-plan.md:381-386`). The new integration test exercises that contract through the public checker rather than only the private parser.
- `_parse_dedup_decisions()` still enforces strictly ascending unique `candidate_id` input using `previous_candidate_id` and raises `RefreshDataError("dedup decisions are not in canonical candidate_id order")` on non-increasing order.
- The producer continues to emit decisions in canonical ascending `candidate_id` order. E6 did not alter producer/readback implementation semantics; it only closes the previously missing integration-test acceptance gap.
- The active Refresh specification keeps WP9-a within development/data-foundation scope, including deterministic dedup, overlap controls, canonical materialization, Public/Hidden views, manifests, and leakage checks. No calibration/GRPO/C2/D2/evaluation scope was added.

### Reviewer-owned verification

- Exact new regression: `uv run python -m pytest tests/integration/test_wp9a_refresh_data_pipeline.py::test_wp9a_strict_readback_rejects_rehashed_noncanonical_dedup_order -q` → **1 passed**.
- Full sealed-plan WP9-a focused suite → **187 passed**.
- `make lint` → **PASS**: Ruff check, Ruff format check, strict mypy over 121 source/test files.
- `make test` → **1110 passed, 3 skipped, 0 failed**; the three skips are the existing opt-in real-Piston tests and are unrelated to WP9-a.
- Production strict readback of `/home/dzy/wp9a-refresh-seed42-r2e2-final1` under reviewed HEAD → exit 0: selected 10,000, external retained 9,565, SFT overlap 750/10,000, quality-gate-required 1,086.
- Production strict readback of `/home/dzy/wp9a-refresh-seed42-r2e2-final4` under reviewed HEAD → exit 0 with the same counts.
- After all reviewer-owned verification, stage HEAD remained exactly `ea5ae771cee06ef0e1f626377c0dd65e1f0cca9e` and the worktree remained clean before this append.

### Executor claim audit

- E6 Git provenance, source review binding, repair issue scope, and changed-file scope are substantiated.
- The claimed production-shadow regression exists and matches the exact R6 required-repair contract.
- E6's focused/lint/full-suite claims are independently reproduced; reviewer additionally revalidated both accepted real production outputs under the reviewed HEAD.
- No remaining actionable plan, spec, safety, leakage, test, or execution-report discrepancy was found.

### Conclusion

**PASS** for `reviewed_head_commit=ea5ae771cee06ef0e1f626377c0dd65e1f0cca9e`.

R6-M1 is fully closed. WP9-a's current completed execution satisfies the sealed row-order fail-closed acceptance contract, all reviewer-owned repository gates are green, and the accepted real refresh outputs remain valid under strict readback. No repair is required.

```yaml
repair_routing:
  version: 1
  required: false
  source_review_round: 7
  mode: null
  complexity: null
  single_class: null
  parallelizability: null
  multi_benefit: null
  independent_workstreams: 0
  repair_issue_ids: []
  rationale:
    - "R6-M1 is resolved by the exact required end-to-end public strict-readback regression, and all independent reviewer verification passed."
  workstream_candidates: []
```

Next lifecycle action: run `stage-lifecycle checkpoint_review` for `WP9-a`; after the PASS review is checkpointed, run `stage-lifecycle finalize`. Reviewer-ex does not commit, merge, update proceedings, finalize, or clean up the stage.
