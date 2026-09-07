# WP9-c Research Closeout — GRPO Refresh / active1354

**Closeout date:** 2026-09-07
**Status:** user-directed research closeout
**Scope:** freeze the completed WP9-c numerical evidence and stop further recipe changes inside WP9-c.
**Next stage:** WP9-d GRPO optimization, governed by `PROJECT_SPEC_GRPO_Refresh_WP9D.md`.

## 1. Stage boundary

WP9-c is closed as the stage that established the reduced active pool, completed the formal seed-42 GRPO comparison, completed the SFT-only active1354 control, and produced the frozen eval400 analysis used to diagnose the next optimization direction.

This closeout is a **project routing decision**, not a retroactive claim that every historical WP9-c action followed the original sealed `WP9-c-plan.md` route literally. The effective WP9-c route evolved through explicit user decisions and audited operator handoffs. Existing historical plan/executor/operator evidence remains immutable.

From this closeout onward:

- no new GRPO/SFT training recipe is executed under `WP9-c`;
- no second seed is started automatically for an unchanged WP9-c recipe;
- the completed B/C/D/SFT1354 artifacts and analyses below are frozen reference evidence;
- any optimizer/scheduler/LR/beta/LoRA change is a **new WP9-d experiment identity**;
- by explicit user decision, the same frozen eval400 definition becomes the canonical WP9-d tuning/evaluation benchmark and MAY be used to choose hyperparameters and checkpoints; future selected results must be described as reused-benchmark/eval400-selected evidence rather than untouched held-out estimates.

## 2. Frozen scientific result

Formal eval400 identity remains:

- dataset SHA256: `770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae`
- ordered problem IDs SHA256: `2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9`
- Piston config SHA256: `f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e`
- eval config SHA256: `3fa1b8f0dbc6853c894ac9f02b6820afd838ff68ca9f090ecbbef4ae495dbac3`
- seed: `42`
- deterministic pass@1
- generation batch: `4`
- control-plane verification workers: `64`

### B/C/D

| Method | Visible Pass@1 | Train-hidden Pass@1 | Eval-hidden Pass@1 | Eval-hidden average-test pass rate |
|---|---:|---:|---:|---:|
| B | 0.3550 | 0.3350 | **0.3750 (150/400)** | 0.4500 |
| C / Public GRPO | 0.3600 | 0.3400 | **0.3750 (150/400)** | 0.45125 |
| D / Hidden GRPO | 0.3600 | 0.3475 | **0.3750 (150/400)** | 0.4500 |

Primary paired held-out result:

- C - B eval-hidden Pass@1 delta: `0.0000`, 95% CI `[-0.0100, +0.0100]`;
- D - B eval-hidden Pass@1 delta: `0.0000`, 95% CI `[-0.0100, +0.0100]`;
- D - B train-hidden Pass@1: `+0.0125`, 95% CI `[+0.0025, +0.0250]`.

Interpretation: Hidden reward produced measurable reward-source-local adaptation, but neither Public nor Hidden GRPO transferred that change to the frozen eval-hidden endpoint.

Authoritative analysis:

- `/home/dzy/wp9c-formal-sync/analysis/wp9c-eval400-bcd/final_report.md`
  - SHA256 `cc9bbc3d0f6c641c70f9862b0edb4ba0fed29378cd2b80a987bb97579856d9ed`
- `/home/dzy/wp9c-formal-sync/analysis/wp9c-eval400-bcd/paired_report.json`
  - SHA256 `3ce026c9a601909b53f2ac8108b71c3c657d71bbdf5c5015eb08d4bdaed15f8a`
- `/home/dzy/wp9c-formal-sync/analysis/wp9c-eval400-bcd/training_dynamics.json`
  - SHA256 `8bb59a72ae62a6e5088bffe288ac687630e8e74726c615e8af6cddebf5371e83`

### Supplemental SFT-only control

The later SFT-only active1354 continuation is retained as a negative control rather than as the next optimization target:

- eval-hidden Pass@1: `0.3425 = 137/400`;
- SFT1354 - B paired delta: `-0.0325`, 95% CI `[-0.0825, +0.0175]`;
- parse/executable stability regressed and runtime-error rate increased.

Authoritative comparative analysis:

- `/home/dzy/wp9c-formal-sync/analysis/wp9c-eval400-bcd-sft1354/final_report.md`
  - SHA256 `aa3ecf474806112a36e968e2b6fd85416a8a86e8a9f13a3c3170f87f0fdaa544`
- `/home/dzy/wp9c-formal-sync/analysis/wp9c-eval400-bcd-sft1354/paired_report.json`
  - SHA256 `ed9f40c709edf450b0e1abdbf0a72ed816ae94d94ff8e5259a59715731d6d20e`
- `/home/dzy/wp9c-formal-sync/analysis/wp9c-eval400-bcd-sft1354/checksums.sha256`
  - SHA256 `1ff3b4f3f73a585dcb3eacccbf8241f5a5d291b64815d42e9ed00c29cdfafcd1`

## 3. GRPO diagnosis carried into WP9-d

The completed C/D runs show healthy reward variance and no obvious collapse, but insufficient effective policy movement:

- each arm completed `300` optimizer steps / `2400` rollouts;
- trainer-reported data coverage ended at approximately `0.2216 epoch`;
- cosine LR nevertheless decayed from peak `5e-6` to approximately zero by step 300;
- C mean KL: approximately `1.227e-4`;
- D mean KL: approximately `1.255e-4`;
- PPO clip-region mean: `0` in both arms;
- completion clipped ratio remained below `0.75%`;
- reward signal retained substantial group variance.

The highest-confidence optimization hypothesis is therefore **coverage/scheduler/update-budget mismatch**, not reward collapse. WP9-d must test this hypothesis before changing multiple independent scientific knobs.

## 4. Immutable artifacts and handling rules

Primary local authority:

- artifact root: `/home/dzy/wp9c-formal-sync/outputs`
- B/C/D analysis: `/home/dzy/wp9c-formal-sync/analysis/wp9c-eval400-bcd`
- B/C/D/SFT comparative analysis: `/home/dzy/wp9c-formal-sync/analysis/wp9c-eval400-bcd-sft1354`

Historical 4090 artifacts may be archived or the worker may remain offline after successful synchronization. The control-plane copies above are the retained analysis authority for future planning.

Git consolidation/archive anchors:

- full pre-cleanup WP9-c working-tree snapshot: commit `98ce5a6b07064593db06d10f99404f6ff5fbe225`, tag `archive/wp9c-working-tree-20260907`;
- C32 final SFT handoff actually used for the completed run: commit `d59943855e2aab6b786cd5ec5796530a8f486206`, tag `archive/wp9c-c32-final-handoff`;
- C36 SFT-continuation generation handoff actually used for eval400 generation: commit `094c571636d2f9c342e70b9ef404eb59597b8302`, tag `archive/wp9c-c36-generation-handoff`;
- original closeout/spec transition lineage: commit `67dc3d1073c8b03316c5e2d3c7be7b505af29aa4`, tag `archive/wp9c-stage-transition-20260907`.

The historical WP9-c feature checkout and detached handoff worktrees were removed only after those commits were retained and their effective contents were integrated into `main`. The local `feat/wp9-c` branch was deleted after integration. WP9-d planning/implementation MUST start from the cleaned integrated `main`, not from a historical feature branch, detached handoff commit, or archival tag.

## 5. Closeout decision

WP9-c result: **valid negative result / no held-out GRPO improvement under the frozen 300-step recipe.**

The next research question is no longer “does the existing 300-step GRPO recipe beat B?” That question has been answered negatively. The next question is:

> Does a schedule that provides approximately one epoch of active1354 coverage and sustained nonzero learning rate produce meaningful policy movement and improved canonical eval400 performance without destabilizing code generation?

That question belongs to WP9-d and is specified separately.