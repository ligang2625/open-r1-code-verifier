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
