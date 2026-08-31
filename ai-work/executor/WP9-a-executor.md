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
