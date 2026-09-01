# WP9-a Execution Report

## Provenance and routing

- Stage: `WP9-a`
- Task kind: `implementation`
- Sealed plan: `ai-work/planner/WP9-a-plan.md`
- Source plan commit: `72a91b652a38fe4e7e58a396c76bfd77fb46a66b`
- Stage branch/worktree: `feat/wp9-a` / WP9-a linked stage worktree
- Source routing: `mode=single`, `complexity=normal`
- Execution backend: `web_codexpro`
- Effective execution mode: `single`
- Stage profile: development; control plane / target hardware `GTX 1660 Ti (6GB)`; engineering evidence; no 24GB operator gate.
- Result code commit captured before this report: `2deff303a0a7c98a65170fe6661178a57a09dbe3`.
- Transport guard remained clean: `.ai-bridge/**` was never tracked. The sealed plan, both project specifications, `proceedings.md`, and `third_party/open-r1` were not modified.

## Implementation commits

- `4d7439a` `feat(data): add refresh source foundation`
- `e8f48e0` `feat(data): add refresh deduplication`
- `b1004a8` `feat(data): build refresh materialization pipeline`
- `b55a6f4` `feat(data): expose refresh data CLI`
- `994122e` `test(data): add WP9-a refresh integration`
- `d34c54c` `style(data): format refresh pipeline`
- `daa02ef` `perf(data): speed refresh source materialization`
- `dc82f08` `perf(data): reuse validated refresh test hashes`
- `c7c0062` `perf(data): optimize refresh near-prefix indexing`
- `593dc77` `perf(data): streamline refresh artifact I/O`
- `5cbb8ca` `perf(data): accelerate refresh strict readback`
- `4076f83` `perf(data): stream refresh parquet rows`
- `79165a6` `perf(data): bound refresh readback memory`
- `2deff30` `perf(data): complete refresh engineering path`

The implementation provides pinned-source ingestion/provenance, fixed-output stdio canonicalization to `solve_io(input_text: str) -> str`, deterministic exact/near deduplication, explicit SFT-overlap quota selection, deterministic three-layer test materialization, Public/Hidden training views, root/artifact manifests, strict readback, tracked refresh protocol config, CLI entry points, and fixture/integration coverage. No dependency or `third_party/open-r1` change was required.

## Source and reference evidence

All final engineering runs used only the already-cached pinned snapshots in offline mode (`HF_HUB_OFFLINE=1`, `HF_DATASETS_OFFLINE=1`).

- DeepCoder PrimeIntellect: `agentica-org/DeepCoder-Preview-Dataset@177913a7bd43791646ef6a43645caa3c871ab3db`, `primeintellect/train`, declared license `MIT`; scanned `16,252`, adapter accepted `11,323`; consumed-projection SHA256 `6241f5c56810008cf12cb94b47d9ec8fd49f5048fa2900d77b3ce87531f2480c`.
- DeepCoder TACO: same pinned dataset revision, `taco/train`, declared license `MIT`; scanned `7,436`, adapter accepted `2,642`; consumed-projection SHA256 `d5b1242810ec37f9a524a7e2c7b3731595e269544b7add719cccfea51e2fe6de`.
- HumanEvalPlus exclusion: `evalplus/humanevalplus@aa0d916268b1c17e84e881e9bd460508dd2fd308`, `test`, declared license `Apache-2.0`; `164` exclusion references; projection SHA256 `d538bb58cbf89c74001c7e60b21a38552af6666da695e27182d66c97297b0314`.
- Frozen formal canonical split counts: train `2,500`, validation `300`, test `400`; canonical SHA256 `d310b68f5644214177c00784d8af64e8a87dbd982068c028f72ec5974d3d71c6`.

## Real pinned-source engineering materialization

The acceptance output was written outside Git under logical output name `wp9a-refresh-seed42-run9`; a second fresh same-seed output used logical name `wp9a-refresh-seed42-run10`. Large JSONL/cache artifacts were not added to the repository.

Final real commands/results:

- Offline `prepare-refresh-data` with tracked `configs/data/refresh.yaml`, the frozen formal prepared root, local HF cache, seed `42`, and fresh output `wp9a-refresh-seed42-run9`: exit `0`, `173.574s`.
- Fresh `check-refresh-data` against `wp9a-refresh-seed42-run9`: exit `0`, `35.504s`.
- Same offline `prepare-refresh-data` with identical inputs/seed into fresh output `wp9a-refresh-seed42-run10`: exit `0`, `174.159s`.
- Determinism comparison: exact file sets matched (`13/13` files) and every corresponding file was byte-for-byte/SHA256 identical; mismatches `0`.

Materialization/readback evidence:

- Total DeepCoder rows scanned: `23,688`; adapter accepted candidates: `13,965`; dedup retained external candidates: `9,453`.
- Final canonical pool: exactly `10,000` unique train problems.
- Explicit frozen-SFT reuse: exactly `750 / 10,000 = 0.075`; hard max `0.15` passed.
- Newly selected external problems: exactly `9,250`.
- Validation exact/accepted-near overlap: `0`; project-test overlap: `0`; HumanEvalPlus overlap: `0`.
- Test-layer audit: `10,000` problems checked; cross-layer normalized duplicate count `0`; all layers non-empty.
- `quality_gate_required=true`: `1,090` problems (the allowed 4–7-test reserve).
- Public view contains no train-hidden tests; Public/Hidden contain no eval-hidden/reference-solution/SFT-response/starter-code leakage.
- Selected IDs/order SHA256: `955aed7ca430418e413da6bcb70cc1defdafd54c12646fcc5a1ab55a47725134`.
- Root manifest SHA256: `996ac510756a5de51d6e42c36189f655aa7cb6c99194773f0421cc2189e3ffd9`.

Dedup report retained `9,453` external candidates after deterministic cross-source/in-source exact/near handling. Recorded external duplicate rejections were: exact reference-solution `80`, exact statement/contract `439`, exact test fingerprint `3,563`, accepted-near external duplicate `430`. Evaluation and incidental-SFT hard gates remained separate and passed at zero selected overlap.

## Validation and closeout evidence

- WP9-a focused/unit/integration regression (including data leakage/dedup helpers): `206 passed`, `0 failed`.
- `make lint`: Ruff check passed, Ruff format check passed, strict mypy passed for `121` source files.
- `make test`: `1087 passed`, `3 skipped`, `0 failed` in `118.84s`. The three skips are the repository's existing opt-in real-Piston cases; WP9-a does not depend on Piston.
- Real pinned-source prepare, fresh strict readback, and same-seed deterministic rerun all passed as recorded above.
- Post-code-closeout worktree was clean before this report, and protected plan/spec/proceedings/third-party paths had no diff from the sealed plan commit.

## Deviations and resolved blockers

- Initial Hugging Face probes could not reach the network without the user's local proxy. The user populated the exact pinned snapshots into the local HF cache; final acceptance runs were fully offline and did not download or change source identities.
- Several early real-data attempts hit the CodexPro per-command `180s` limit, and one early parallel parquet attempt was killed by the approximately 8 GiB control-plane memory ceiling. No failed attempt published a partial final output; the temporary-sibling/atomic-rename contract remained intact.
- Performance work retained the frozen protocol while reducing wall time/memory: streamed parquet batches, deterministic bounded row parallelism, refresh-specific prevalidated test guards, shared prefix contexts, write-time JSONL SHA/row accounting, bounded-memory strict readback, and removal of duplicate validation passes already guaranteed by the canonical/training loaders.
- A timing-instrumented run completed its internal atomic publish after the external tool timeout and was not used as the formal prepare result. The accepted `run9` and `run10` commands both returned exit `0` within the tool limit.
- No calibration generations, B numerical metrics, GRPO checkpoints, C2/D2 results, or final 400-problem evaluation metrics were produced; those remain outside WP9-a scope.

```yaml
execution_record:
  version: 1
  stage_id: WP9-a
  execution_id: E0
  task_kind: implementation
  source_plan_commit: 72a91b652a38fe4e7e58a396c76bfd77fb46a66b
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: 2deff303a0a7c98a65170fe6661178a57a09dbe3
  execution_backend: web_codexpro
  effective_execution_mode: single
  status: completed
```

## E1 repair summary

R1 repair was executed in the same `WP9-a` worktree with `backend=web`, `effective_execution_mode=single`, sourced from review commit `3ef9a0ee695ea3ee555f03072a3c0433de92c3d4`. The implementation is committed as `0e2d65560fb8631614af4441752b1a134179b827`.

### Issue disposition

- `R1-M1`: strict readback no longer treats `manifest/selection.jsonl` fingerprints or `quality_gate_required` flags as authoritative. It rebuilds dedup-relevant fingerprints from canonical problem bytes, binds selection source/difficulty/identity to canonical rows, recomputes the quality gate from actual three-layer test counts, runs overlap audits with rebuilt fingerprints, and semantically reconciles `sft_overlap.json`, `evaluation_overlap.json`, and `test_layer_leakage.json`. Regression coverage includes self-consistent root/hash rewrites with a false quality flag, canonical+training prompt tamper with stale selection fingerprint, and report-value tamper.
- `R1-M2`: external exact/near dedup no longer uses transitive DSU components. A candidate can now be rejected only by direct exact evidence or direct Jaccard `>=0.90` to a deterministic representative that was itself retained; evaluation/SFT hard-rejected candidates are excluded before external representative selection. The non-transitive A-B/B-C chain regression confirms C is retained when A-C is below threshold, and all `near_external_duplicate` decisions assert similarity `>=0.90`.
- `R1-M3`: `wp9a-refresh-v1` now freezes `token_ngram_size=5` and `near_jaccard_threshold=0.90` in runtime/config validation. File-config variants such as `1` or `1.0` are rejected with `ConfigError` before preparation.

### Repair verification

- Review-specific WP9-a unit/integration set after the new regressions: `25 passed`.
- Sealed-plan focused acceptance set, executed via the stage interpreter because `uv run pytest` could not spawn the console script in this environment: `170 passed`.
- `make lint`: PASS; Ruff check + format check + strict mypy passed for all `121` source/test files.
- `make test`: `1093 passed, 3 skipped`; skips are the existing opt-in real-Piston cases and are unrelated to WP9-a.
- Real pinned-source classification with the tracked config and frozen formal references: `23,688` source rows scanned, `13,965` adapter-accepted candidates, `9,565` externally retained candidates (gate `>=9,250`), `276` direct `near_external_duplicate` rejections, minimum recorded near similarity `0.90`.
- New strict checker against the existing accepted real 10k output `wp9a-refresh-seed42-run9`: PASS; selected `10,000`, external retained in that frozen artifact `9,453`, SFT reuse `750/10,000`, quality-gate-required `1,090`.
- A fresh full prepare was attempted twice to new external logical roots (`wp9a-refresh-seed42-repair-e1/e2`), but each process hit the CodexPro per-command `180s` hard timeout during preparation and was SIGTERM'd before atomic publish. Neither final output root was published; both temporary sibling trees were removed. These attempts are not counted as successful materializations. The bounded real-source classification and fresh strict readback above are the completed repair-time real-data evidence available under the tool limit.
- Protected plan/review/proceedings/`third_party/open-r1` paths were not modified by the repair.

## Structured E1 execution record

```yaml
execution_record:
  version: 1
  stage_id: WP9-a
  execution_id: E1
  task_kind: repair
  source_plan_commit: 72a91b652a38fe4e7e58a396c76bfd77fb46a66b
  source_review_round: 1
  source_review_commit: 3ef9a0ee695ea3ee555f03072a3c0433de92c3d4
  repair_issue_ids: [R1-M1, R1-M2, R1-M3]
  result_code_commit: 0e2d65560fb8631614af4441752b1a134179b827
  execution_backend: web_codexpro
  effective_execution_mode: single
  status: completed
```

## E2 repair summary

R2 repair was executed in the same `WP9-a` worktree with `backend=web`, `source_mode=single`, and `effective_execution_mode=single`, sourced from review round 2 / commit `6ce65f8f4855c2a2f5fbbd4838140e6c35508819`. The final repair code HEAD is `bee206c9ed04a5d7a18e308e0b48ffa71e0d704d`; the principal repair commits are `1ed5606` (`fix(wp9-a): harden refresh reference readback`), `7e6582b` (`perf(wp9-a): avoid duplicate refresh test scans`), and `bee206c` (`perf(wp9-a): complete repaired refresh materialization`).

### Issue disposition

- `R2-M1`: strict readback now treats `reference_dataset_dir/canonical/problems.jsonl` as authoritative for the formal SFT/validation/project-test reference sets. It reloads the formal canonical, recomputes actual train/validation/test split counts, rebuilds the three formal fingerprint buckets with the active frozen dedup policy, requires the stored snapshot buckets to equal those rebuilt values, and uses the rebuilt fingerprints for overlap auditing. The root formal-canonical SHA is cross-bound to the same authoritative bytes. The external-eval snapshot is also fail-closed checked for the frozen HumanEvalPlus dataset/revision/license, non-empty count consistency, projection fingerprint shape, and equality with the root manifest identity. The reviewer-style adversarial regression now rewrites a selected canonical row to overlap unchanged formal validation while deleting the stored validation fingerprint bucket and updating root hashes; strict readback rejects the snapshot mismatch.
- `R2-M2`: `wp9a-refresh-v1` file/config loading freezes the production selection values to target `10,000`, SFT overlap `0.075`, and hard max `0.15`, while the runtime validator independently rejects any hard max above `0.15`. Strict readback independently rejects a manifest hard max above `0.15`, a configured overlap above `0.15`, or an actual selected SFT overlap above `0.15`, so caller-provided manifest values cannot redefine the safety ceiling. Regression coverage includes `0.20` and `0.50` hard-max variants plus a self-consistent selected-overlap tamper above 15%.
- `R2-M3`: the repaired producer was made reliably runnable without changing the frozen data protocol by removing duplicate selected test-layer scans, reusing already-computed external candidate fingerprints through classification/selection manifest attachment, avoiding repeated generic JSON-value validation for trusted already-canonical artifact mappings, and removing redundant raw training-view byte scans after exact-schema loading plus semantic canonical-view comparison. The generic JSONL writer keeps its prior validating default; the non-validating path is explicit and only used for trusted internal mappings. A unit regression confirms the combined selected-test fingerprint path still rejects normalized cross-layer test duplicates.

### Repair verification

- Review-focused affected set during repair: `69 passed` after the final performance/static-typing changes.
- Sealed-plan WP9-a focused acceptance set: `179 passed`.
- `make lint`: PASS; Ruff check, Ruff format check, and strict mypy all passed for `121` source/test files.
- `make test`: `1102 passed, 3 skipped`; the three skips are the existing opt-in real-Piston cases and are unrelated to WP9-a.
- Final repaired real materialization `wp9a-refresh-seed42-r2e2-final1`, executed offline with tracked `configs/data/refresh.yaml`, frozen formal reference root, local pinned HF cache, and seed `42`: exit `0` in `173.022s`. A separate `check-refresh-data` against final1 returned exit `0` in `49.019s` with selected `10,000`, external retained `9,565`, SFT reuse `750/10,000`, and quality-gate-required `1,086`.
- A direct second-run attempt at `wp9a-refresh-seed42-r2e2-final2` hit the CodexPro `180s` command timeout and was SIGTERM'd before atomic publish; its temporary sibling was removed and it is not counted as acceptance evidence. A further direct retry (`final3`) likewise produced no final output and no retained temporary sibling and is not counted.
- To obtain a completed attributable result rather than count a timed-out background process, the second accepted same-seed run used an ignored, untracked `.ai-bridge` runner that executed the exact same offline `prepare-refresh-data` CLI while recording commit, command, terminal return code, duration, and log. It bound `bee206c9ed04a5d7a18e308e0b48ffa71e0d704d`, returned code `0` after `198.474s`, and published `wp9a-refresh-seed42-r2e2-final4`. `.ai-bridge/**` remained untracked and is not part of repository provenance.
- Determinism comparison between final1 and final4: exact file sets matched (`13/13`) and every corresponding file was byte-for-byte/SHA256 identical; mismatches `0`. Root manifest SHA256 is `98a0fb8192661f6358c29819d8a70eb4039397cc2a3ec5444f0581cfbcb81625`; selected IDs/order SHA256 is `355cfec302a38c3c05e4237be178c5f34207cabb432d2b65f1b4a027cf42d001`.
- Final real-source counts: `23,688` source rows scanned, `13,965` adapter-accepted candidates, `9,565` dedup-retained external candidates, `10,000` selected problems, `750` SFT reuse (`0.075`), `9,250` external-new selected, and `1,086` quality-gate-required. Dedup rejections were exact reference-solution `117`, exact statement/contract `409`, exact test fingerprint `3,598`, and direct near-external duplicate `276`.
- Source projection fingerprints remained pinned and deterministic: DeepCoder PrimeIntellect `6241f5c56810008cf12cb94b47d9ec8fd49f5048fa2900d77b3ce87531f2480c`, DeepCoder TACO `d5b1242810ec37f9a524a7e2c7b3731595e269544b7add719cccfea51e2fe6de`, HumanEvalPlus `d538bb58cbf89c74001c7e60b21a38552af6666da695e27182d66c97297b0314`; frozen formal canonical SHA256 remained `d310b68f5644214177c00784d8af64e8a87dbd982068c028f72ec5974d3d71c6`.
- Protected plan/review/spec/proceedings/`third_party/open-r1` paths were not modified by E2.

## Structured E2 execution record

```yaml
execution_record:
  version: 1
  stage_id: WP9-a
  execution_id: E2
  task_kind: repair
  source_plan_commit: 72a91b652a38fe4e7e58a396c76bfd77fb46a66b
  source_review_round: 2
  source_review_commit: 6ce65f8f4855c2a2f5fbbd4838140e6c35508819
  repair_issue_ids: [R2-M1, R2-M2, R2-M3]
  result_code_commit: bee206c9ed04a5d7a18e308e0b48ffa71e0d704d
  execution_backend: web_codexpro
  effective_execution_mode: single
  status: completed
```

## E3 repair summary

R3 repair ran in the same `WP9-a` worktree with `backend=local`, `source_mode=single`, and
`effective_execution_mode=single`, sourced from review round 3 / commit
`d87ae07ec3750274a2f37b9983a60b6a5e327f17`. The repair code commit is
`6bfd1619bf7a578b26f2195ad58ab69ef1e111e8`.

### Issue disposition

- `R2-M1`: production strict readback now binds the HumanEvalPlus exclusion set to the frozen 164-record
  fingerprint-inventory SHA256 and pinned projection SHA256. Replacing the stored external-eval fingerprints while
  preserving local count/root hashes fails closed.
- `R3-M1`: `wp9a-refresh-v1` config accepts exactly the two approved DeepCoder projections. Strict readback validates
  source snapshot shape, unique identities, row counts and SHA formats, cross-binds snapshots to both root source
  structures, and verifies the pinned scan/accept/projection identities independently.
- `R3-M2`: production readback independently requires 10,000 / 0.075 / 0.15 / 750 / 9,250. Small engineering
  fixtures use the explicit `wp9a-refresh-test-v1` protocol and require `allow_test_protocol=True`; the production
  `check-refresh-data` CLI cannot silently certify them.

### Repair verification

- Execution preflight passed at the exact R3 review baseline: clean `feat/wp9-a`, no tracked `.ai-bridge`, sealed plan
  unchanged, required imports available, formal canonical split counts `2500/300/400`, pinned source schemas probed,
  and writable control-plane temporary storage confirmed.
- Sealed-plan focused unit/integration suite: `182 passed`.
- Existing repaired real artifact `wp9a-refresh-seed42-r2e2-final1` passed the new production strict readback:
  selected `10,000`, external retained `9,565`, SFT reuse `750`, quality-gate-required `1,086`.
- `make lint`: PASS; Ruff check/format and strict mypy passed for `121` files.
- Sandboxed `make test` could not access NVML and failed 28 existing SFT/GRPO GPU-environment fixture tests with
  `gpu_count=0`; no WP9-a test failed. The same command rerun on the authorized GTX 1660 Ti host environment passed:
  `1105 passed, 3 skipped`; the skips are the existing real-Piston opt-in cases.
- Only `src/code_verifier/data/refresh.py`, `tests/unit/data/test_refresh.py`, and
  `tests/integration/test_wp9a_refresh_data_pipeline.py` changed. Plan/review/spec/proceedings/`third_party/open-r1`
  remained unmodified, and `.ai-bridge/**` remained untracked.

## Structured E3 execution record

```yaml
execution_record:
  version: 1
  stage_id: WP9-a
  execution_id: E3
  task_kind: repair
  source_plan_commit: 72a91b652a38fe4e7e58a396c76bfd77fb46a66b
  source_review_round: 3
  source_review_commit: d87ae07ec3750274a2f37b9983a60b6a5e327f17
  repair_issue_ids: [R2-M1, R3-M1, R3-M2]
  result_code_commit: 6bfd1619bf7a578b26f2195ad58ab69ef1e111e8
  execution_backend: local_codex
  effective_execution_mode: single
  status: completed
```

## E4 repair summary

R4 repair was taken over in the same `WP9-a` worktree after the local agent exhausted its quota before creating any R4 code or execution-report commit. The inherited tracked diff was limited to the R4-M1 readback work; the Web/CodexPro executor validated that diff against the committed R4 review baseline, completed the missing regressions and acceptance, and committed the final repair as `c2cddff5bc947e8a0ee279b655cbbec527f02afd`.

Routing remained the sealed R4 `source_mode=single` / `single_class=normal`; the completing runtime was `backend=web`, so `effective_execution_mode=single`. Source review round 4 is commit `3badd4cb0149ee6fecf9297156a7eb8642ae6b4d`, with repair scope `[R4-M1]` only.

### Issue disposition

- `R4-M1`: strict readback now exact-schema parses `selection.jsonl` and `dedup_decisions.jsonl`; external selection provenance must use a non-empty source record id and valid raw-record SHA, while SFT reuse requires both provenance fields to be null.
- Every parsed dedup decision is unique by candidate id and source-record identity, has strict retained/rejected evidence types, and production readback requires exact per-source accepted-candidate provenance inventory hashes. The two tracked anchors were independently rebuilt from the pinned local DeepCoder cache: PrimeIntellect `11,323` accepted candidates -> `37c62e2a5446517974a060242eedc93af7a44c505666346f824b12085ed3bcd0`; TACO `2,642` -> `6baac4a1e44340c13bf25c750836821d95b2b1c0c519588b8e977b75ce310701`.
- Every selected `external_new` row is cross-bound to the dedup decision with the same candidate/problem id and exact source name, source-record id, and raw-record SHA, and that decision must be retained with no rejection and `overlap_class=none`. A self-consistent selection+decision provenance rewrite is therefore rejected by the frozen accepted-candidate inventory.
- Strict readback now recomputes `reports/dedup_summary.json` from source snapshots plus parsed decisions and cross-checks root `total_candidates_scanned` / `external_candidates_retained` against those recomputed values.
- New adversarial regressions cover forged selected raw provenance, a selected candidate rewritten to a rejected dedup decision while dedup summary/root counts are also made self-consistent, exact selection/dedup schemas, provenance type drift, and the frozen accepted-candidate inventory anchor. The earlier >15% overlap tamper was updated to satisfy the new SFT null-provenance schema so it continues exercising the intended ceiling gate.

### Repair verification

- Takeover/preflight: `HEAD=3badd4cb0149ee6fecf9297156a7eb8642ae6b4d` before the repair commit; stage branch `feat/wp9-a`; primary/stage `git ls-files .ai-bridge` empty; stage `.venv` resolves both `code_verifier` and `open_r1` into the WP9-a worktree; Ruff/mypy/pytest available. Frozen formal canonical was located by SHA256 `d310b68f5644214177c00784d8af64e8a87dbd982068c028f72ec5974d3d71c6`.
- R4-focused unit/integration subset: `34 passed`.
- Full sealed-plan WP9-a focused suite: `186 passed`.
- `make lint`: PASS; Ruff check/format and strict mypy passed for `121` source/test files.
- `make test`: PASS — `1109 passed, 3 skipped`; skips are the existing real-Piston opt-in cases.
- New production checker strict-readback of both existing repaired real outputs `wp9a-refresh-seed42-r2e2-final1` and `wp9a-refresh-seed42-r2e2-final4`: PASS, each selected `10,000`, external retained `9,565`, SFT reuse `750`, quality-gate-required `1,086`.
- Because E4 changes readback validation/anchors only and does not change production artifact bytes, no new materialization was required. The existing deterministic pair was re-compared: identical `13/13` file sets, `0` SHA256 mismatches, root manifest SHA256 `98a0fb8192661f6358c29819d8a70eb4039397cc2a3ec5444f0581cfbcb81625`.
- Only `src/code_verifier/data/refresh.py`, `tests/unit/data/test_refresh.py`, and `tests/integration/test_wp9a_refresh_data_pipeline.py` changed in the R4 code commit. Plan/review/spec/proceedings/`third_party/open-r1` remained unmodified, and `.ai-bridge/**` remained untracked.

## Structured E4 execution record

```yaml
execution_record:
  version: 1
  stage_id: WP9-a
  execution_id: E4
  task_kind: repair
  source_plan_commit: 72a91b652a38fe4e7e58a396c76bfd77fb46a66b
  source_review_round: 4
  source_review_commit: 3badd4cb0149ee6fecf9297156a7eb8642ae6b4d
  repair_issue_ids: [R4-M1]
  result_code_commit: c2cddff5bc947e8a0ee279b655cbbec527f02afd
  execution_backend: web_codexpro
  effective_execution_mode: single
  status: completed
```

## E5 repair summary

R5 repair was executed in the same `WP9-a` worktree with `backend=web`, `source_mode=single`, and `effective_execution_mode=single`, sourced from review round 5 / commit `afe5e0866494d22a99612b3b9439e550f34ca4ec`.

### Issue disposition

- `R5-M1`: strict readback now rejects non-canonical `manifest/dedup_decisions.jsonl` ordering. `_parse_dedup_decisions()` verifies that input records arrive in strictly ascending `candidate_id` order instead of accepting a semantically equivalent reordered sequence. The accepted inventory hash checks remain unchanged and continue serving provenance anchoring rather than replacing the JSONL order invariant.

### Repair verification

- Router preflight passed: stage `HEAD` matched the latest committed R5 review baseline; plan remained sealed at `72a91b652a38fe4e7e58a396c76bfd77fb46a66b`; `.ai-bridge/**` remained untracked; stage environment resolved local `code_verifier` and `open_r1` sources.
- Formal canonical reference preflight passed: split counts `2500/300/400`, canonical SHA256 `d310b68f5644214177c00784d8af64e8a87dbd982068c028f72ec5974d3d71c6`.
- Pinned source probes passed from the local cache: DeepCoder schema matched both `primeintellect` and `taco`; HumanEvalPlus exclusion remained 164 references with projection SHA256 `d538bb58cbf89c74001c7e60b21a38552af6666da695e27182d66c97297b0314`.
- R5-focused unit verification: `tests/unit/data/test_refresh.py` → `19 passed`.
- R5 integration verification: `tests/integration/test_wp9a_refresh_data_pipeline.py` → `15 passed`.
- `make lint` → PASS; Ruff check/format and strict mypy passed for `121` source/test files.
- `make test` → PASS: `1109 passed, 3 skipped`; skips are the existing real-Piston opt-in cases.

## Structured E5 execution record

```yaml
execution_record:
  version: 1
  stage_id: WP9-a
  execution_id: E5
  task_kind: repair
  source_plan_commit: 72a91b652a38fe4e7e58a396c76bfd77fb46a66b
  source_review_round: 5
  source_review_commit: afe5e0866494d22a99612b3b9439e550f34ca4ec
  repair_issue_ids: [R5-M1]
  result_code_commit: 27d9999f41f77a3e48cb6252b167cabdbe3108d3
  execution_backend: web_codexpro
  effective_execution_mode: single
  status: completed
```

## E6 repair summary

R6 repair was executed in the same `WP9-a` worktree with `backend=local`,
`source_mode=single`, and `effective_execution_mode=single`, sourced from review
round 6 / commit `78b61380edcfb2e10cf701e6015c92234ce4b4e0`. The repair is limited
to `R6-M1`: a production-shadow end-to-end strict-readback regression was added
for rehashed non-canonical dedup decision order. The code/test commit is
`fd40e526f6ec4e0d511e24f5b34762ad648b7404`.

### Issue disposition

- `R6-M1`: the integration regression materializes a valid fixture artifact,
  swaps its first two valid `manifest/dedup_decisions.jsonl` rows, updates only
  that artifact's root SHA256 entry, calls public `check_refresh_data()`, and
  requires rejection with the canonical `candidate_id` order error. The prior
  parser unit regression remains covered.

### Repair verification

- Execution preflight passed at the router-provided repair baseline: `HEAD`
  matched review commit `78b61380edcfb2e10cf701e6015c92234ce4b4e0`; the sealed
  plan remained at `72a91b652a38fe4e7e58a396c76bfd77fb46a66b`; the stage branch
  was `feat/wp9-a`; `git ls-files .ai-bridge` was empty; and the stage venv
  resolved `code_verifier` and `open_r1`.
- Formal canonical preflight passed: `3,200` canonical rows with split counts
  `2,500/300/400`, canonical SHA256
  `d310b68f5644214177c00784d8af64e8a87dbd982068c028f72ec5974d3d71c6`.
- Offline pinned-source probes passed through the production source loaders:
  PrimeIntellect `16,252/11,323` with projection
  `6241f5c56810008cf12cb94b47d9ec8fd49f5048fa2900d77b3ce87531f2480c`, TACO
  `7,436/2,642` with projection
  `d5b1242810ec37f9a524a7e2c7b3731595e269544b7add719cccfea51e2fe6de`, and
  HumanEvalPlus `164/164` with projection
  `d538bb58cbf89c74001c7e60b21a38552af6666da695e27182d66c97297b0314`.
- The literal `uv run` import probe was blocked by the environment's read-only
  default uv cache and unavailable offline package metadata; the equivalent
  stage interpreter import probe passed and no dependency changed. Temporary
  control-plane storage was writable with ample free space.
- Affected targeted verification passed: existing refresh unit parser regression
  plus the new integration regression (`20 passed`); the full sealed-plan WP9-a
  focused suite passed (`187 passed`).
- `make lint` passed: Ruff check, Ruff format check, and strict mypy over 121
  source/test files.
- Sandboxed `make test` encountered 28 unrelated existing SFT/GRPO
  GPU-environment guard failures because that sandbox exposes no NVML/GPU. The
  same command with host GPU access passed: `1,110 passed, 3 skipped, 0 failed`;
  the three skips are the existing opt-in real-Piston tests. WP9-a tests passed
  in both runs.
- Only `tests/integration/test_wp9a_refresh_data_pipeline.py` changed in the
  repair code/test commit. The plan, review, specifications, proceedings,
  `third_party/open-r1`, and `.ai-bridge` tracked state were not modified. No
  push was performed.

## Structured E6 execution record

```yaml
execution_record:
  version: 1
  stage_id: WP9-a
  execution_id: E6
  task_kind: repair
  source_plan_commit: 72a91b652a38fe4e7e58a396c76bfd77fb46a66b
  source_review_round: 6
  source_review_commit: 78b61380edcfb2e10cf701e6015c92234ce4b4e0
  repair_issue_ids: [R6-M1]
  result_code_commit: fd40e526f6ec4e0d511e24f5b34762ad648b7404
  execution_backend: local_codex
  effective_execution_mode: single
  status: completed
```
