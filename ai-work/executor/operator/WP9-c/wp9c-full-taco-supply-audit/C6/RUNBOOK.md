# WP9-c C6 full-TACO supply audit runbook

This sidecar implements only the control-plane supply audit authorized by `wp9c-active-pool-2500-amendment-v1`. It does **not** run Piston, candidate solutions, generated tests, calibration generation/scoring/retry, GRPO, or any RTX4090 operator.

## Frozen target

- active pool exact: 2500
- SFT reuse exact: 225
- external-new exact: 2275
- dual-informative >=1750
- public-only <=375
- hidden-only <=375
- dual-uninformative =0
- desired pre-Piston external-new candidate buffer: approximately 2600–2800

Historical aggregate evidence remains `/home/dzy/wp9c-function-supply-aggregate-audit-C0/report.json` with its published digest and historically reported 1278 ready / 1126 APPS-under8 values; do not rerun or overwrite it. The reviewed correction artifact is `/home/dzy/wp9c-function-supply-context-correction-C6-r1/report.json` with SHA256 `dfcf62177d0e8b3d643db2a528ea5c8915a16351e1e7ef75b0e1a37d21f8b953`. It establishes 1276 corrected current-ready Exact-B context survivors and 1119 APPS-under8 pre-augmentation planning/proxy survivors. The APPS-under8 formal context-eligible count remains unresolved/null until augmentation and final context recheck.

**Current gate is unblocked for the audited TACO supply run only.** The C6 checkpoint is re-frozen against the correction report. Calibration, Piston, GRPO, APPS augmentation, and RTX4090 remain frozen.

The first manual Step 2 attempt stopped during static JSON parsing because one upstream TACO `input_output` field contained a 9131-digit integer and Python's configured integer-string conversion limit rejected it. No audit report or candidate stage was published. The failed log is preserved at `/home/dzy/wp9c-taco-full-supply-audit-C6.log`. The pinned Step 1 download is valid and must be reused; do **not** rerun Step 1. The strict JSON loader now normalizes this parser-level `ValueError` into `StrictJsonError`, so the existing source-adapter policy records such a row as invalid and skips it without relaxing the interpreter limit or accepting the oversized integer.

Both C6 runners read `checkpoint.json` before doing work and fail closed unless the amended protocol/frozen flags and bound config/script SHA256 values match the current worktree bytes.

## Why full TACO is worth running now

Shard0 yielded 73 conservative >=8-test direct-signature function candidates before aggregate dedup/context/Piston. `73 * 9 = 657` is only a planning extrapolation. Starting from the corrected zero-attrition planning potential 2395, at least 205 incremental TACO survivors would reach 2600 and 405 would reach 2800 **before accounting for any TACO overlap that removes APPS-under8 planning rows**. The audit therefore recomputes the APPS-under8 planning count after TACO dedup instead of treating 205/405 as guaranteed sufficiency thresholds.

## Step 1 — pinned download (networked, manual)

Run from the WP9-c worktree:

```bash
cd /home/dzy/open-r1-code-verifier/.worktrees/wp9-c
source ~/.bashrc
bash ai-work/executor/operator/WP9-c/wp9c-full-taco-supply-audit/C6/01-download-full-taco.sh
```

The script resolves **only** `BAAI/TACO` revision `d593ed0a2becbbc952230bb89be09189bf1056dc`, requires exactly nine `ALL/train-xxxxx-of-00009.parquet` files, freezes each Hugging Face LFS SHA256 + size before/with download, rehashes local bytes, and writes `/home/dzy/wp9c-taco-full-download-C6/manifest.json` plus `manifest.sha256`. It refuses overwrite.

## Step 2 — offline static stage/audit (manual)

Step 1 is already complete for the current operator attempt. Re-run only Step 2:

```bash
cd /home/dzy/open-r1-code-verifier/.worktrees/wp9-c
bash ai-work/executor/operator/WP9-c/wp9c-full-taco-supply-audit/C6/02-audit-full-taco.sh
```

Do **not** source `~/.bashrc` for this offline step. The runner forces `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`.

The audit:

1. verifies the download manifest and all nine shard SHA256/size identities;
2. preserves only native TACO function-call rows with >=8 unique normalized tests, nonempty accepted source solutions, and a conservative direct top-level function signature;
3. keeps dedup identity as the raw TACO question plus the separately recovered function contract, matching the frozen refresh fingerprint policy;
4. deduplicates against the same frozen formal SFT/validation/project-test/HumanEvalPlus identities and the corrected 1276 current-ready candidates; the shared classifier also applies deterministic candidate-candidate dedup within TACO;
5. only after dedup, applies production `canonicalize_refresh_candidate(seed=42) -> build_code_prompt` to each intact >=8-test TACO candidate, then the exact cached Formal-B tokenizer/chat-template context cap <=2048;
6. reconstructs the corrected 1119 APPS-under8 pre-augmentation planning/proxy survivors and re-deduplicates them against retained TACO survivors under priority `current-ready -> TACO natural >=8 -> APPS-under8`; this adjusted APPS count remains planning-only and still requires post-augmentation context recheck;
7. emits candidate payloads including dataset revision, shard SHA256, row index, upstream source, prompt/hash protocol, native tests, and accepted source solutions for later reference-solution transformation/Piston work;
8. emits `formal_eligible=false`; no solution/test execution occurs.

Expected outputs:

- `/home/dzy/wp9c-taco-full-supply-audit-C6-r1/report.json`
- `/home/dzy/wp9c-taco-full-supply-audit-C6-r1/report.sha256`
- `/home/dzy/wp9c-taco-full-supply-audit-C6-r1/candidates.jsonl`
- `/home/dzy/wp9c-taco-full-supply-audit-C6-r1/apps_under8_after_taco_decisions.jsonl`
- `/home/dzy/wp9c-taco-full-supply-audit-C6-r1.log`

When both steps finish, reply only `执行完毕`. The control plane should read these artifacts directly and recompute how much APPS-under8 augmentation is still needed. Do not copy/paste logs.

## Frozen boundaries after audit

Even if TACO supply is large enough, do not immediately start calibration. Natural TACO survivors still need source/provenance review, a frozen reference-solution transformation policy, and project-required Piston validation. APPS augmentation, if still needed, gets its own audited checkpoint. Old C5 calibration, old retry sidecars, and RTX4090 remain frozen until the new function-level formal candidate protocol closes.
