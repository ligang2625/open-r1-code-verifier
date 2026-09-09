# WP9-d C2 — Hidden300 stability adjudication

C2 is a one-shot third full-400 verification of `wp9d-A-hidden-step300-eval400-b4-p1-seed42`. It is created after C0 was rejected for two Piston `sandbox_error` rows and C1 eliminated those infrastructure failures but exposed one timeout/pass instability at row 5 (`apps-4392`). C2 does not weaken either prior gate and does not patch individual rows.

## Predeclared decision rule

Before C2 is run, the acceptance rule is frozen as follows:

- run the entire 400-problem Hidden300 verification again in a new namespace;
- require zero `sandbox_error` statuses/failure counts;
- require exact frozen generation payload preservation for all 400 rows;
- require C2 verifier semantics to equal C1 for all 400 rows, excluding only fresh `runtime_ms` telemetry;
- therefore row 5 `apps-4392` must reproduce C1's `eval_hidden_execution_status=passed` and `eval_hidden_pass_rate=1.0`;
- if C2 reproduces C1 exactly, classify the earlier C0 `apps-4392` timeout as transient and accept C2 as the final Hidden300 run;
- if `apps-4392` returns to timeout, or any other semantic row differs, preserve C2 and fail the gate. Do not create a final accepted manifest.

This rule is fixed before observing C2 and is intentionally stricter than simply accepting any zero-sandbox run.

## Frozen lineage

- C0 operator commit: `8717f6032c27117facbd996b7bce3ba8ec328143`
- C0 evidence SHA256: `92966897f3b705b11d95736ae47262d7be1ad6a44387342e4d6cd5a876e183e1`
- C0 terminal log SHA256: `c7b1c8c55ba057cee2085e1178ba325b7fe67ff5243f4539949c0a9b756409ee`
- C0 Hidden300 results SHA256: `a1f5d2b2dbd726edf48a435388b74eef463fb10ab85e1f6c999c80099704663f`
- C0 sandbox rows: 55 and 59
- C1 operator commit: `8f54a0873c34a75c8140e3f0ddad9d1ff3f6291c`
- C1 evidence SHA256: `778b18c4f4e797598159609f79ca6444747347a48cc91feb5d0d451720fc6852`
- C1 terminal log SHA256: `f133b41e87ccafb35afd7edac50ed8cd627fb3e800d5a9e9295ba0488041af0e`
- C1 Hidden300 run SHA256: `bc8bfbfd806e7f372456262429719ab2e30f477155017b6398e872414ec491d5`
- C1 Hidden300 results SHA256: `60883c2b8a25c13ac6d92229fab9a74edbac95fc48241f07d48dd073bd82772e`
- C1 Hidden300 summary SHA256: `9bebd5a148c4c6a790b4c2d630d2dc3017f5d5a0b9b944082913e238b454bf28`
- C1 Hidden300 main-results SHA256: `7a4fc952e05e895d9d79cb8b1f9689bc8a56baafcb9c9882945b41e342426ffb`
- C1 sandbox rows: 0
- C0→C1 non-sandbox semantic drift: exactly row 5 `apps-4392`, timeout → passed

The original Hidden300 generation remains frozen:

- run.json SHA256: `e2de319a2c629730bc1b0a6f2b15ee29d17868522e2e060b3c7d0a8c0fa9c120`
- generations SHA256: `8acc2d875b493db09b886293e5eaba1ed64a94c800e37e79545d65472a652d5c`
- verifier project commit: `f17b4f607daa3bb03b08682bbbd841118d36c4af`
- Open-R1: `1416fa0cf21595d2083b399a2a0bbddd7f6e9563`
- dependency lock: `4cd4ee4e9dacbaf6531c346e4c032485ffa7d22b7714538bd8bf4a5beace3acf`
- eval400 dataset: `770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae`
- ordered problem IDs: `2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9`
- Piston definition: `f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e`
- seed 42, verification workers 64

## Output isolation

C2 uses a new immutable namespace:

- verification output: `/home/dzy/wp9d-eval400-stability-c2`
- operator evidence: `/home/dzy/wp9d-eval400-operator/WP9-d/wp9d-eval400-unified-verify/C2`
- stability report: `/home/dzy/wp9d-eval400-stability-c2/stability-report.json`
- final manifest, only if accepted: `/home/dzy/wp9d-eval400-stability-c2/final-verification-manifest.json`

The script refuses to start if the C2 output namespace already exists. C0 and C1 are never overwritten.

## Manual execution

After C2 is committed, export its exact commit and script SHA256 from the clean WP9-d worktree:

```bash
export WP9D_C2_HANDOFF_COMMIT=<exact C2 commit>
export WP9D_C2_SCRIPT_SHA256=<exact C2 run.sh SHA256>
C2=ai-work/executor/operator/WP9-d/wp9d-eval400-unified-verify/C2
```

Run preflight first:

```bash
bash "$C2/run.sh" preflight
```

Then manually run the third full-400 adjudication:

```bash
bash "$C2/run.sh" adjudicate
```

Follow progress with:

```bash
tail -F /home/dzy/wp9d-eval400-operator/WP9-d/wp9d-eval400-unified-verify/C2/terminal.log
```

If C2 reproduces C1, final success ends with:

```text
formal_c2_postcheck=PASS bundles=9 records=3600 repaired_run=hidden-step300 c1_c2_semantic_drift=0 apps4392=passed_twice sandbox_errors=0 aggregation=PASS
```

C2 performs no generation, loads no model weights, and does not require an RTX 4090.
