# WP8-a Review

## R1 — formal automated analysis validation

```yaml
review_record:
  version: 1
  stage_id: WP8-a
  review_round: 1
  source_execution_id: E0
  reviewed_head_commit: 61cfe3dd68e214ce354e70795f8db197dc079501
  conclusion: pass
```

### Review scope and provenance guard

- Reviewer context is fresh and did not participate in the latest `web_codexpro` execution.
- Resolved stage is explicitly `WP8-a`; review workspace is `/home/dzy/open-r1-code-verifier/.worktrees/wp8-a`, branch `feat/wp8-a`.
- Sealed plan metadata matches the actual stage: `stage_profile=validation`, `control_plane_hardware=GTX 1660 Ti (6GB)`, `target_hardware=GTX 1660 Ti (6GB)`, `evidence_class=real-training/numerical`, `development_terminal=false`.
- Sealed plan commit is `ab87fea68ccb727f939887fd60bfb5a7adc86da0`.
- Latest completed execution record is `E0`, `task_kind=implementation`, `source_plan_commit=ab87fea68ccb727f939887fd60bfb5a7adc86da0`, `result_code_commit=ab87fea68ccb727f939887fd60bfb5a7adc86da0`, `execution_backend=web_codexpro`, `effective_execution_mode=single`, `status=completed`.
- Git history identifies `61cfe3dd68e214ce354e70795f8db197dc079501` as the commit that added `ai-work/executor/WP8-a-executor.md`; review began with `HEAD` exactly at that commit and a clean worktree.
- `git ls-files .ai-bridge` is empty; no tracked transport artifact is present.
- The execution-report commit changed only `ai-work/executor/WP8-a-executor.md`; no unknown post-execution commit or uncommitted tracked change was present.

### Plan and acceptance verification

| Area | Independent review result |
|---|---|
| Formal source binding | PASS. Production `load_analysis_inputs()` independently reloads Base/SFT/Public/Hidden with 400 records and 400 unique problem IDs each. Completed B/C/D identities load; C is `public`, D is `hidden`, and both bind the same completed B parent. |
| Source artifact integrity | PASS. Reviewer recursively re-hashed all 37 `path`/`size_bytes`/`sha256` entries recorded in `/home/dzy/wp8-analysis/wp8-a-input-ab87fea-e0/source-inventory.json`; 37/37 matched current bytes. Input manifest SHA256 is `118093d5befbd43bdd0e08527847d23f40626284f8e73b49dbe2df033d1e0da8`; source inventory SHA256 is `b79718d096be441b2d3d0e45b88b4b95ce1d458696617dafd80f1b11cfca18f1`. |
| A1 disclosure | PASS. The source inventory explicitly records `accepted_under_a1_post_hoc_operational_equivalence=true` and references the committed WP7-c amendment/review. `proceedings.md` likewise states that accepted C/D do not satisfy the original exact-code/save-cadence contract without A1. |
| Formal output layout | PASS. Canonical output contains exactly the 10 planned files: `auto_error_counts.csv`, `costs.csv`, `failure_candidates.jsonl`, `main_results.csv`, `manual_error_counts.csv`, `manual_labels_template.csv`, `paired_comparisons.csv`, `report_data.json`, `resolved_analysis.yaml`, `training_curves.csv`. |
| Deterministic readback | PASS. Reviewer re-hashed canonical and readback directories; all 10 corresponding files are byte-for-byte identical. All SHA256 values match the execution report. |
| Main A–D results | PASS. Direct stdlib recomputation from the four raw `results.jsonl` files gives Base `0.1225 / 0.1175 / 0.115`, SFT `0.3525 / 0.335 / 0.3775`, Public `0.3625 / 0.34 / 0.375`, Hidden `0.3625 / 0.34 / 0.375`, each over 400 unique problems. These match `main_results.csv` and finalized proceedings. |
| Bootstrap / paired statistics | PASS. Reviewer independently recomputed the 10,000-resample problem-level percentile bootstrap contract with seed 42. Eval-hidden 95% CIs are Base `[0.085, 0.1475]`, SFT `[0.33, 0.425]`, Public `[0.3275, 0.4225]`, Hidden `[0.3275, 0.4225]`; Public-vs-SFT paired eval delta is `-0.0025` with CI `[-0.0125, 0.0075]`, matching the formal output. All three comparison rows contain 400 paired problem IDs. |
| C/D paired interpretation | PASS. C and D have six problems where partial visible/train/eval pass-rate tuples differ, but their pre-defined whole-pass eval-hidden, public-eval-gap, and automated-candidate proxy differences are all zero problem-by-problem; therefore the formal C-vs-D row of `0.0` with `[0.0, 0.0]` intervals is legitimate and not an omitted nonzero paired effect under the sealed metric contract. |
| Curves and costs | PASS. Direct source-log recomputation gives curve rows SFT `2549`, Public `8115`, Hidden `8115`; GPU-hours `0.5215871774233367`, `4.012272991803669`, `3.5036727118225017`; Public/Hidden rollouts `2400/2400`, generated tokens `514360/512918`, executor-hours `0.0582530611647443/0.06447173045885166`. These match `training_curves.csv` and `costs.csv`. No USD rate is fabricated. |
| Failure-analysis preparation | PASS. Formal output contains 653 deterministic candidates and 653 template rows; manual fields are empty, non-Hidden rows never contain `train_hidden_pass_eval_fail`, `manual_analysis_status=pending`, `manual_label_count=0`, and the automated proxy is explicitly not presented as a human conclusion. Candidate volume is sufficient for the later 20-case human stage. |
| Evidence boundary | PASS. This stage only consumed finalized formal evidence on the GTX 1660 Ti control plane; no new 24GB GPU gate or synthetic fixture was used as validation evidence. The still-pending ≥20-case human analysis and final narrative are explicitly out of scope for WP8-a and are not falsely claimed complete. |

### Independent reviewer-owned regression gates

- `make lint`: PASS — Ruff check/format and strict mypy, 114 source files.
- `make test`: PASS — `1030 passed, 3 skipped, 0 failed`; all three skips are the explicit default-suite real-Piston opt-in cases.
- `make test-gpu`: PASS — `3 passed, 0 failed, 0 skipped` on GTX 1660 Ti.
- `make test-piston PISTON_CONFIG=configs/execution/piston-local.yaml`: PASS — `9 passed, 2 deselected`, with no selected skip/failure.
- Production strict formal loader readback: PASS — four methods × 400 records, completed B/C/D identity and parent/reward-mode checks all pass.

### Executor claim audit

The material claims in `ai-work/executor/WP8-a-executor.md` were independently checked against Git state, formal source bytes, production strict loaders, raw result/log recomputation, generated outputs, and reviewer-owned tests. No substantive discrepancy was found.

### Findings

No blocker, major, minor, or actionable acceptance finding is open for this reviewed head. No repair issue ID is required.

### Conclusion

**PASS** for `reviewed_head_commit=61cfe3dd68e214ce354e70795f8db197dc079501`.

WP8-a correctly closes only the formal automated-analysis layer: immutable accepted A/B/C/D source binding, A–D aggregates, problem-paired bootstrap comparisons, curve/cost derivation, deterministic failure-candidate preparation, output hashing/readback, and regression evidence. It does not claim the later human 20-case analysis or final report conclusion.

```yaml
repair_routing:
  version: 1
  required: false
  source_review_round: 1
  mode: null
  complexity: null
  single_class: null
  parallelizability: null
  multi_benefit: null
  independent_workstreams: 0
  repair_issue_ids: []
  rationale:
    - "All WP8-a planned automated formal-analysis gates and reviewer-owned regression/provenance checks pass at the reviewed execution-report HEAD."
    - "No executor action is required; the remaining human 20-case analysis and final narrative belong to a subsequent stage by the sealed plan."
  workstream_candidates: []
```

Next lifecycle action: run `stage-lifecycle checkpoint_review` for `WP8-a`. Reviewer-ex does not commit, merge, update proceedings, finalize, or clean up the stage.
