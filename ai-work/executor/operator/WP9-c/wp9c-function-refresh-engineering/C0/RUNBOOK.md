# WP9-c function-refresh engineering C0

Engineering-only preparation for the OpenCoder `educational_instruct` source.

This is **not** a formal WP9-c operator gate. It must not start calibration retry, training, evaluation, or any RTX4090 workload.

## Frozen source identity

- dataset: `OpenCoder-LLM/opc-sft-stage2`
- revision: `87a3b8da70131b3cf5ef6504c26a51b8c17347a4`
- file: `educational_instruct/train-00000-of-00001.parquet`
- expected size: `53572508` bytes
- expected SHA256: `59cc262e240140ca265655a8d14d2a0f28139164a8e532294308692408095759`
- adapter: `opencoder_assert_literal_v1`

## Manual execution

Run from the user's normal interactive terminal so the proxy exports in `~/.bashrc` are inherited by the download script.

```bash
cd /home/dzy/open-r1-code-verifier/.worktrees/wp9-c
source ~/.bashrc
bash ai-work/executor/operator/WP9-c/wp9c-function-refresh-engineering/C0/01-download-opencoder.sh
bash ai-work/executor/operator/WP9-c/wp9c-function-refresh-engineering/C0/02-stage-opencoder.sh
```

The download script is fail-closed on missing proxy variables, snapshot identity, file size, or SHA256 mismatch.

The stage script switches Hugging Face into offline mode, refuses to overwrite an existing output/log, validates the pinned dataset license through the project loader, applies the conservative AST/literal-only function-call adapter, and verifies the final candidate JSONL count and SHA256 against its manifest.

Expected new engineering artifacts:

- `/home/dzy/wp9c-function-refresh-stage-opencoder-C0/`
- `/home/dzy/wp9c-function-refresh-stage-opencoder-C0.log`

After the stage completes, stop. Do not run calibration generation/retry. The next control-plane step is to inspect `candidate_count` and `quality_safe_ge8_count`, then choose an audited dedup/context strategy before any further long task.

## Open-R1 tested/shuffled audit

The OpenCoder stage yielded only 490 rows with at least eight canonical tests, so it cannot supply the required function-level external-new pool by itself. The next source is therefore audited before any candidate materialization:

- dataset: `open-r1/verifiable-coding-problems-python_decontaminated-tested-shuffled`
- revision: `98191eb6eefd276b7ebb4eb8d25c4a167cc65605`
- file: `data/train-00000-of-00001.parquet`
- expected size: `146139801` bytes
- expected SHA256: `0f4967c744a1ef7acfc9aadcdefcb64be7b5567448e507f80a48d3b3d0bb2686`
- license status: `unresolved_upstream` because this derived dataset card does not declare a license
- adapter status: `audit_only_v1`; no row is admitted to the candidate pool by this step

Run manually:

```bash
cd /home/dzy/open-r1-code-verifier/.worktrees/wp9-c
source ~/.bashrc
bash ai-work/executor/operator/WP9-c/wp9c-function-refresh-engineering/C0/03-download-openr1-tested.sh
bash ai-work/executor/operator/WP9-c/wp9c-function-refresh-engineering/C0/04-audit-openr1-tested.sh
```

The audit is offline after download and never executes source testcase strings. It reports pure function-call inventory, raw and unique test counts, `fn_name` consistency, statically recoverable gold-solution signatures, strict-JSON mappings, safe-`ast.literal_eval` mappings, and a fail-closed arity ambiguity check. Upstream `test_reward == 1` remains informational only and does not replace project Piston reference-solution validation.

Expected audit artifacts:

- `/home/dzy/wp9c-function-refresh-audit-openr1-tested-C0/report.json`
- `/home/dzy/wp9c-function-refresh-audit-openr1-tested-C0/report.sha256`
- `/home/dzy/wp9c-function-refresh-audit-openr1-tested-C0.log`

After the audit completes, stop again. Do not run dedup, Piston, calibration generation, or retry until the report has been reviewed.

## Open-R1 tested/shuffled result

The audit verified all 15,068 rows and found 985,337 testcase records, all with `type=stdin_stdout` and `fn_name=null`. This source therefore contributes zero function-level candidates under the current WP9-c repair goal and is excluded from further function-level preparation.

## BAAI/TACO shard-0 supply audit

The next audit returns to the same upstream family already used by the old SFT canonical dataset. The old canonical TACO examples use top-level function contracts such as `def checkchoose(m, n):` with positional JSON arguments, matching the desired interface.

To avoid downloading the full 2.42 GB train parquet set before establishing supply, only the first of nine `ALL/train` parquet shards is pinned initially:

- dataset: `BAAI/TACO`
- revision: `d593ed0a2becbbc952230bb89be09189bf1056dc`
- shard: `ALL/train-00000-of-00009.parquet`
- size: `286917870` bytes
- SHA256: `bee336c14dda183b1f700d54a149173418c7b3def295666159dd72c32aa8b326`
- declared dataset license: `Apache-2.0`
- provenance note: TACO includes mixed upstream material; source/url and upstream terms must remain auditable before formal admission

Run manually:

```bash
cd /home/dzy/open-r1-code-verifier/.worktrees/wp9-c
source ~/.bashrc
bash ai-work/executor/operator/WP9-c/wp9c-function-refresh-engineering/C0/05-download-taco-shard0.sh
bash ai-work/executor/operator/WP9-c/wp9c-function-refresh-engineering/C0/06-audit-taco-shard0.sh
```

The audit executes no solution or testcase payload. It measures function-call rows, >=8-test rows, normalized test uniqueness, non-empty gold solutions, immediately compatible direct signatures, and class-method-only signatures separately. After it completes, stop for review before downloading the remaining eight shards.

### TACO shard-0 result

Shard 0 contained 2,827 rows, including 360 function-call rows. Of these, 78 had at least eight tests; five failed normalized test uniqueness, leaving 73 unique >=8-test rows. All 73 had a non-empty solution and an immediately compatible direct top-level signature. A naive 9-shard extrapolation is only about 657 such rows before dedup/context/Piston losses, so full TACO is useful as a supplementary source but is not downloaded yet.

## Raw Open-R1 decontaminated sample audit

The previously audited `open-r1/verifiable-coding-problems-python_decontaminated-tested-shuffled` artifact is a post-reward-filter derivative and cannot be used to infer the raw upstream interface inventory. Its upstream `open-r1/verifiable-coding-problems-python_decontaminated` artifact contains 27,839 Python rows and preserves structured verification records with `fn_name`, `input`, `output`, and `type` fields.

Before downloading the full 1.13 GB source, audit the first and last of its six pinned shards to sample both ends of the source ordering:

- revision: `0d251c23dcff7f7e525e7a4e184be5232bf63db6`
- shard 0: `data/train-00000-of-00006.parquet`, 36,295,672 bytes, SHA256 `181d2e480df556e10e49f6dd1c6160a98adf5c1ae77c5e44fb03accc19129c89`
- shard 5: `data/train-00005-of-00006.parquet`, 218,679,740 bytes, SHA256 `f302c5aaa01d126c0dc72a541b3d445d0dd6259577a88a930cdd02c771c903b6`
- license status remains `unresolved_upstream`; this is audit-only until per-source provenance is resolved

Run manually:

```bash
cd /home/dzy/open-r1-code-verifier/.worktrees/wp9-c
source ~/.bashrc
bash ai-work/executor/operator/WP9-c/wp9c-function-refresh-engineering/C0/07-download-openr1-decontaminated-sample.sh
bash ai-work/executor/operator/WP9-c/wp9c-function-refresh-engineering/C0/08-audit-openr1-decontaminated-sample.sh
```

The audit executes no source code. Function-call input is accepted only when it parses explicitly as a positional-argument list; strict JSON is preferred and `ast.literal_eval` is only a non-executing audit fallback. Stop after the report is produced; do not run full-source download, candidate materialization, Piston, calibration, or retry until review.

### Raw Open-R1 sample result

The first/last shard sample covered 9,279 rows. Only 73 rows were pure function-call tasks, all from TACO in shard 5, and those rows had only 1-2 tests each (mean 1.726). Therefore the sampled raw source contributed zero >=8-test function-call tasks. The remaining four shards are not downloaded for WP9-c function-level repair.

## Native APPS + LeetCode supply audit

The next audit combines two comparatively small native/function-oriented sources in one round and runs the frozen overlap classifier immediately, avoiding another single-source download/review cycle.

Pinned sources:

- `codeparrot/apps`, revision `21e74ddf8de1a21436da12e3e653065c5213e9d1`, `train.jsonl`, 107,101,272 bytes, SHA256 `45e82ef22ed8e7c0c04d881a21b923e9dd233157896b0b8d5b3493e887499cae`, declared MIT.
- `tkeskin/leetcode-solutions`, revision `ac62251a3fa13388bf4dd348160adb1e0f95bbaf`, `leetcode-solutions.parquet`, SHA256 `48f49b9967f4bb059d7d55080f208f74c1ef957e380fcdd0ea08f0eeb1b560ea`. Solution provenance is recorded as walkccc/LeetCode (MIT) and metadata/tests as newfacade/LeetCodeDataset (Apache-2.0); statement provenance remains separately noted rather than treated as a blanket license grant.

Audit policy:

- APPS: native `fn_name` only, >=8 unique tests, existing strict function-call parser, non-empty solutions, directly recoverable function signature.
- LeetCode: `Solution().method` only; literal/strict-JSON arguments and outputs only; test keyword names must exactly match method parameters; linked-list/tree/node annotation contracts fail closed; >=8 unique tests required.
- Both sources are classified jointly against frozen SFT, validation, project-test, and HumanEvalPlus references with the existing 5-gram/Jaccard 0.90 policy.
- This round produces only an audit report. Exact-B context filtering, reference-solution transformation/materialization, and Piston execution remain later gates.

Run manually:

```bash
cd /home/dzy/open-r1-code-verifier/.worktrees/wp9-c
source ~/.bashrc
bash ai-work/executor/operator/WP9-c/wp9c-function-refresh-engineering/C0/09-download-native-function-supply.sh
bash ai-work/executor/operator/WP9-c/wp9c-function-refresh-engineering/C0/10-audit-native-function-supply.sh
```

Expected audit artifacts:

- `/home/dzy/wp9c-native-function-supply-audit-C0/report.json`
- `/home/dzy/wp9c-native-function-supply-audit-C0/report.sha256`
- `/home/dzy/wp9c-native-function-supply-audit-C0.log`

Stop after the report. Do not start context materialization, Piston validation, calibration generation/retry, or RTX4090 work until the report is reviewed.

### Native supply C0 transport failure and recovery

The first native-supply attempt failed before candidate audit because the APPS source downloaded and verified successfully, but the pinned `tkeskin/leetcode-solutions` snapshot never entered the local HF cache. The C0 log records `LocalEntryNotFoundError` when the offline audit looked for revision `ac62251a3fa13388bf4dd348160adb1e0f95bbaf`. The pinned revision, filename, and SHA256 were rechecked; the parquet is Xet-backed, while this environment has `hf_xet` enabled. The recovery therefore preserves APPS and the failed C0 log, disables Xet explicitly, and downloads only the missing LeetCode parquet through regular Hub HTTP.

Run the recovery manually:

```bash
cd /home/dzy/open-r1-code-verifier/.worktrees/wp9-c
source ~/.bashrc
bash ai-work/executor/operator/WP9-c/wp9c-function-refresh-engineering/C0/11-recover-download-leetcode-http.sh
bash ai-work/executor/operator/WP9-c/wp9c-function-refresh-engineering/C0/12-audit-native-function-supply-C1.sh
```

Recovery outputs use `C1` so the failed C0 evidence is never overwritten:

- `/home/dzy/wp9c-native-function-supply-audit-C0.log` — preserved transport failure
- `/home/dzy/wp9c-native-function-supply-audit-C1/report.json`
- `/home/dzy/wp9c-native-function-supply-audit-C1/report.sha256`
- `/home/dzy/wp9c-native-function-supply-audit-C1.log`

Stop after C1 report production for review.

### Native supply C1 provenance-hash failure and C2 recovery

The LeetCode HTTP recovery succeeded and the C1 audit reached candidate parsing. It then failed only while hashing the raw PyArrow row because `estimated_date` is `timestamp[ms]` and therefore becomes a Python `datetime`, which the project's strict JSON hash correctly rejects. A complete schema/type scan of all 3,563 LeetCode rows found no other non-JSON Arrow scalar type; `estimated_date` was the only one. C2 therefore changes only the audit-only raw provenance hash: Arrow timestamps are tagged as `timestamp_ms` and serialized as ISO-8601 milliseconds before hashing. Candidate tests, function contracts, overlap classification, and all formal gates are unchanged.

A full local LeetCode parser check after the fix completed successfully: 3,563 total rows, 2,869 rows with metadata/tests, 2,867 with >=8 raw tests, and 976 structurally safe unique >=8-test candidates after fail-closed contract/test parsing and test-fingerprint uniqueness. This is pre-dedup and pre-context/Piston evidence only.

Run only the C2 audit; both source downloads are already cached and pinned:

```bash
cd /home/dzy/open-r1-code-verifier/.worktrees/wp9-c
source ~/.bashrc
bash ai-work/executor/operator/WP9-c/wp9c-function-refresh-engineering/C0/13-audit-native-function-supply-C2.sh
```

C2 preserves both prior failure logs and writes `/home/dzy/wp9c-native-function-supply-audit-C2/`. Stop after C2 report production for review.

### Native supply C2 report-field failure and C3 recovery

C2 completed source parsing, HumanEvalPlus loading, and joint overlap classification, then failed only while building the final report projection because the audit sidecar referenced a non-existent `RefreshDedupDecision.matched_reference_id` attribute. The project dataclass field is `matched_record_id`. To prevent future field-name drift, C3 no longer hand-copies the decision fields: it serializes each frozen dataclass with `dataclasses.asdict()` and adds only source metadata.

C3 also writes `source_candidates_built` and `dedup_completed` summaries to the log before final report serialization, so expensive data results remain recoverable even if a later report-only failure occurs. A fail-fast preflight verifies the exact `RefreshDedupDecision` dataclass schema and canonical-JSON serializability before running the audit.

Run only the offline C3 audit; no source download is required:

```bash
cd /home/dzy/open-r1-code-verifier/.worktrees/wp9-c
bash ai-work/executor/operator/WP9-c/wp9c-function-refresh-engineering/C0/14-audit-native-function-supply-C3.sh
```

C3 preserves C0/C1/C2 failure logs and writes `/home/dzy/wp9c-native-function-supply-audit-C3/`. Stop after C3 report production for review.

### Native supply C3 result and APPS schema correction

C3 completed successfully and its report digest verified. Its LeetCode path produced 976 structurally safe >=8-test candidates, of which only 200 were retained external-new after the frozen joint overlap classifier: 588 were near SFT, 105 near project test, 78 near validation, 4 near external-eval, and 1 exact external reference-solution overlap. With the existing 654 structural external-new bundle, that leaves 1,921 still missing before context/Piston.

C3's APPS result is not a valid zero-supply conclusion: all 5,000 APPS rows were rejected by the audit sidecar's incorrect top-level schema assumption (`problem_id`). The pinned `codeparrot/apps` train JSONL actually uses `id`, plus `question`, `solutions`, `input_output`, `difficulty`, `url`, and `starter_code`. A read-only inventory found 3,062 native `fn_name` rows, 757 with at least eight raw tests, and one oversized JSON-integer row that Python correctly rejects under its integer-conversion safety limit.

The APPS adapter is therefore corrected under a new v2 audit config rather than mutating the C3-bound config. The v2 adapter keeps the integer guard fail-closed, binds `source_record_id` to the native integer `id`, restores `source_url_hash` as SHA256 of raw UTF-8 URL bytes (matching the old canonical APPS convention), and conservatively supports `class Solution.method(self, ...)` contract extraction without executing code. A local full APPS structural scan after the correction produced 731 structurally safe candidates: 756 >=8-test rows, 25 duplicate-normalized-test rejections, and 731 unique/signature-safe survivors.

The v2 config is `configs/data/wp9c-native-function-supply-audit-v2.yaml`, SHA256 `892b3544bb46ca34f397cf3a602c67c15e7e61fffe4a8047a0669e281063ae04`. The corrected joint raw structural pool is therefore 1,707 candidates before overlap classification: 731 APPS plus 976 LeetCode.

Run only the offline C4 audit; no source download is required:

```bash
cd /home/dzy/open-r1-code-verifier/.worktrees/wp9-c
bash ai-work/executor/operator/WP9-c/wp9c-function-refresh-engineering/C0/15-audit-native-function-supply-C4.sh
```

C4 preserves C0-C3 logs and writes `/home/dzy/wp9c-native-function-supply-audit-C4/`. Stop after C4 report production for review. Calibration retry and RTX4090 remain frozen.

### Native supply C4 result and under-tested APPS decision audit

C4 completed successfully and its report digest verified at `fa33d4a0bbd2433537c0a3465aa6009a1855a93bdb6a5868b0dd32f471ba0431`. The corrected native >=8-test pool contained 1,707 structural candidates (731 APPS + 976 LeetCode), but the frozen overlap classifier retained only 260 external-new: 60 APPS and 200 LeetCode. The dominant APPS losses were exact source-URL overlaps with SFT/validation/project-test references. Together with the pre-existing 654 structural external-new bundle, the current audited pre-context/pre-Piston supply is 914, leaving a gap of 1,861 to the required 2,775.

OpenCoder's 490 raw >=8-test maximum plus the full-TACO naive extrapolation of about 657 cannot close this gap even under a zero-attrition assumption: `914 + 490 + 657 = 2,061`, still 714 short before joint dedup, exact-B context filtering, and Piston validation. Do not download the remaining TACO shards merely to chase this bound.

A safer next protocol candidate is test augmentation for APPS tasks that already have native function-call interfaces but only 1-7 source tests. The threshold is not relaxed. A static inventory found 1,954 such APPS rows; after requiring unique existing tests, at least two non-empty accepted source solutions, and a recoverable static signature, 1,930 remain structurally augmentable. This route preserves the native interface and could later use multi-source-solution consensus plus project Piston to validate generated tests, but augmentation is not yet authorized or implemented.

Before designing any generator, run a static overlap audit on those 1,930 candidates. It executes no source code, generates no tests, and only measures how many are truly external-new after the frozen SFT/validation/project-test/HumanEvalPlus exclusions. The frozen audit config is `configs/data/wp9c-apps-under8-augmentability-audit.yaml`, SHA256 `0389ea01bd8e295db1870148feed2eae00bea20ef832e888c15439a2855cd547`; the audit script SHA256 is `229ebc4dc916c0af1bc58e6c4b27b6132ca534ef85cc965c316221c1262fcd22`.

Run manually:

```bash
cd /home/dzy/open-r1-code-verifier/.worktrees/wp9-c
bash ai-work/executor/operator/WP9-c/wp9c-function-refresh-engineering/C0/16-audit-apps-under8-augmentable.sh
```

The result will be `/home/dzy/wp9c-apps-under8-augmentability-audit-C0/report.json`. Stop after the report for review. Do not generate augmented tests, run Piston, restart calibration retry, or use RTX4090 yet.

### Under8 result and aggregate cross-source audit

The under8 audit completed successfully. Its report SHA256 is `38e0c6f172edbc81bbdbb2f225c73e11908436aa005c32da318445ddf49bb27b`. Of 1,930 structurally augmentable APPS tasks, 1,130 survived the frozen formal-reference overlap classifier. Their existing-test histogram is 119/119/225/214/433/14/6 for 1 through 7 tests, requiring at least 4,861 additional unique test slots to bring all survivors to the unchanged >=8-test threshold. No tests were generated and no source code was executed.

The earlier arithmetic `654 + 260` and `914 + 1,130` is not a valid final supply count because those groups were audited separately and were not cross-deduplicated against each other. The same applies to OpenCoder's 490 raw >=8-test candidates, which have not yet been deduplicated or exact-B context filtered. The next audit therefore uses a fixed priority order: preserve the existing 654 >=8-test exact-B-context incumbents; then classify native/OpenCoder ready >=8-test candidates against formal references plus those incumbents and apply exact-B context; finally classify under8 APPS against formal references plus all ready survivors and apply exact-B context. Under8 candidates can never displace already-ready tasks.

The aggregate audit is static-only. It executes no solution/test payload, generates no tests, performs no Piston work, and does not touch calibration or RTX4090. Its config is `configs/data/wp9c-function-supply-aggregate-audit.yaml`; the runner freezes the current config and audit-script digests before starting. It also closes the 654 provenance chain through the primary 554 exact-B context report and the LCB 100 context/canonical summaries.

Run manually:

```bash
cd /home/dzy/open-r1-code-verifier/.worktrees/wp9-c
bash ai-work/executor/operator/WP9-c/wp9c-function-refresh-engineering/C0/17-audit-function-supply-aggregate.sh
```

Expected result: `/home/dzy/wp9c-function-supply-aggregate-audit-C0/report.json`. Stop after this report. Its key outputs are ready context-eligible supply, augmentable context-eligible supply, the zero-attrition potential after aggregate cross-source dedup, and the remaining gap to 2,775. Calibration retry, test augmentation, Piston, full-TACO download, and RTX4090 remain frozen until that report is reviewed.

### Aggregate result

The aggregate audit completed successfully. `report.json` SHA256 is `f6ff5a9cb688fb60d433f7f9e973d3273e5d18f04e3088855a1a43a06c2cdfd5`, matching `report.sha256`. All 654 incumbents survived the exact Formal-B tokenizer/context recheck. Of 2,197 new ready >=8-test candidates (1,707 native APPS/LeetCode plus 490 OpenCoder), 625 survived aggregate overlap classification and 624 survived exact-B context. Their source split is 6 native APPS, 198 native LeetCode, and 420 OpenCoder. Together with the incumbents, ready context-qualified supply is therefore 1,278.

For APPS under8, 1,130 of 1,930 survived the frozen formal-reference classifier and 1,126 survived exact-B context. None displaced or overlapped the already-retained ready set under the fixed priority policy. These 1,126 still require at least 4,843 additional unique test slots before they can meet the unchanged >=8-test threshold.

The aggregate zero-attrition potential is therefore only `1,278 + 1,126 = 2,404`, leaving a hard gap of 371 to the required 2,775 even under the unrealistic assumption that every under8 survivor is successfully augmented and all future Piston gates pass. Consequently, under8 augmentation alone cannot close WP9-c. Full-TACO's previous naive ~657 raw >=8-test extrapolation is at most a supplementary source and does not provide robust headroom once aggregate dedup/context/Piston and augmentation attrition are considered. Do not restart calibration retry or RTX4090 work. The next data decision must add a new supply protocol/source family with meaningful headroom rather than relying on threshold relaxation.


## 2026-09-04 C6 active-pool amendment pointer

The aggregate result above remains immutable engineering evidence for the historical 3000-target audit. A later user-authorized amendment changes the WP9-c formal active pool to exact 2500 / SFT 225 / external-new 2275 without rewriting this C0 evidence. Continue at `ai-work/executor/operator/WP9-c/wp9c-full-taco-supply-audit/C6/RUNBOOK.md`; old calibration retry and RTX4090 calibration remain frozen.
