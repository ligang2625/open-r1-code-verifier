# WP7-d Review

## Review round 1

```yaml
review_record:
  version: 1
  stage_id: WP7-d
  review_round: 1
  source_execution_id: E0
  reviewed_head_commit: 786dd13f5d425eb3b8d9f164e0e8a43ea77e7ab6
  conclusion: pass
```

### Provenance guard

- Fresh reviewer context: this conversation did not implement or repair WP7-d E0.
- Stage worktree: `/home/dzy/open-r1-code-verifier/.worktrees/wp7-d`, branch `feat/wp7-d`, matching the sealed plan metadata.
- Sealed plan commit: `b4c58abac5669dacfede6581917b93a086acc95c`.
- Latest completed execution: `E0`, `task_kind=implementation`, `status=completed`.
- Execution report commit: `786dd13f5d425eb3b8d9f164e0e8a43ea77e7ab6`; review started with and remained at this exact HEAD.
- Result code commit recorded by E0: `62b7e4d7beee2ce8f37018d1c37f76c932b1f7b8`.
- Worktree was clean before review artifact creation.
- `git ls-files .ai-bridge` returned empty; no transport file is tracked.
- Stage profile/evidence boundary verified as `validation`, control plane `GTX 1660 Ti (6GB)`, target `GTX 1660 Ti (6GB)`, evidence class `real-training/numerical`, `development_terminal=false`. This review therefore consumed existing finalized formal evidence and did not require or rerun a 24GB-GPU gate.

### Independent plan/spec review

The committed WP7-d artifacts satisfy the sealed plan and the relevant project-spec boundaries:

- Deterministic manual selection is frozen from the canonical WP8-a candidate file using namespace `wp7-d-final-manual-v1|seed42`; an independent recomputation reproduced the exact 25 selected `(method, run_id, problem_id, selection_key)` tuples with Public-RLVR 10, Hidden-RLVR 10, SFT 5 and 25 unique `(method, problem_id)` pairs.
- The canonical WP8-a manifest, source inventory, main results, paired comparisons, report data, failure candidates, manual-label template, and costs all independently rehashed to the exact plan-recorded SHA256 values.
- `report/manual_labels.csv` contains exactly 25 labels with the production schema, allowed manual categories, stable `reward_hacking/reason/improvement` notes, and the required 10/10/5 method split. A fresh production `analyze-results` run consumed these labels successfully, which independently exercises the strict manual-label loader.
- `report/manual_failure_analysis.md` contains 25 case sections with run/model identity, candidate/auto label, visible/train-hidden/eval-hidden scalar outcomes, execution status, manual category, Reward-Hacking judgment, rationale, improvement suggestion, and model-generated extracted-code block (with an explicit no-extracted-code placeholder for the parser-rejected syntax-error case).
- Five reviewer-owned source spot checks were performed directly against accepted formal `results.jsonl` records: Public-RLVR `taco-4842`, Public-RLVR `taco-17884`, Hidden-RLVR `taco-4537`, Hidden-RLVR `leetcode-disconnect-path-in-a-binary-matrix-by-at-most-one-flip`, and SFT `leetcode-minimum-value-to-get-positive-step-by-step-sum`. For all five, the tracked report matched source run/model identity, scalar outcomes, execution statuses, and extracted code exactly.
- The manual report contains no copied eval-hidden test bodies, expected outputs, reference solutions, or private SFT responses in the reviewed material; model-generated code is used only for the intended qualitative case analysis.
- A fresh reviewer-owned production analysis to `/home/dzy/wp8-analysis/wp7-d-review-r1` completed with 400 problems, 653 candidates, and 25 manual labels. All 10 output files independently matched the SHA256 values recorded in `report/final_evidence.json`, including byte-identical `main_results.csv`, `paired_comparisons.csv`, `costs.csv`, `failure_candidates.jsonl`, and the manual-aware outputs.
- `report/final_evidence.json` correctly preserves `project_claim_scope=single_training_seed_seed42`, `replication_status=pending_second_seed_or_full_rerun`, `second_seed_executed=false`, `wp7c_a1_posthoc_operational_equivalence=true`, `candidate_sample_only=true`, `population_prevalence_estimate=null`, and `usd_cost_rate=null`.
- README satisfies the project-spec first-screen requirements: one-sentence problem definition, method diagram, core result table, key finding, reproduce command, training hardware/cost evidence, two reviewed cases, and explicit limitations before the long setup section.
- `report/technical_report.md` contains all 16 required sections and keeps observed facts, supported conclusions, limitations, and future hypotheses appropriately separated.
- Scientific claims remain within evidence: the `-0.0025` GRPO-vs-SFT point estimate is not called a significant degradation; zero Hidden/Public aggregate differences are not generalized to method equivalence; the 25-case candidate sample is not presented as a population Reward-Hacking prevalence estimate; WP7-c A1 remains disclosed; and second-seed/full-rerun replication remains explicitly pending as required by the replan.

### Reviewer-owned verification

- `make lint`: PASS — Ruff check/format and strict mypy passed for 114 source files.
- `make test`: PASS — `1030 passed, 3 skipped`; all three skips are the explicit opt-in real-Piston tests.
- `make test-gpu`: PASS — `3 passed`, no skips/failures on the GTX 1660 Ti.
- `make test-piston PISTON_CONFIG=configs/execution/piston-local.yaml`: PASS — `9 passed, 2 deselected`, no selected skips/failures.
- `.venv/bin/python -m pytest tests/unit/analysis tests/integration/test_wp8_analysis_pipeline.py -q`: PASS — `41 passed`.
- Frozen WP8-a SHA256 gate: PASS for all eight required files.
- Deterministic selection recomputation: PASS, exact 25-row identity.
- Fresh production final-analysis readback: PASS, all 10 output hashes exact.
- Five formal-source manual-case spot checks: PASS.
- One initial helper command for the spot-check failed only because shell quoting interpreted Markdown backticks; it performed no repository/artifact mutation. The corrected read-only verifier then passed all five cases.

### Findings

No blocker, major, minor, or actionable acceptance finding was identified for reviewed HEAD `786dd13f5d425eb3b8d9f164e0e8a43ea77e7ab6`.

The project-level second-seed/full-rerun requirement remains pending by explicit user decision and sealed WP7-d scope. It is a disclosed future scientific gate, not an execution defect in this stage and therefore is not a repair issue.

### Conclusion

**PASS.** WP7-d E0 is consistent with the sealed plan, accepted formal evidence, relevant spec requirements, and independent reviewer-owned tests/readbacks. No repair execution is required for this reviewed HEAD.

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
    - "All sealed WP7-d acceptance items reviewed for E0 passed on the exact reviewed HEAD, including independent regression, formal-source hash verification, deterministic selection recomputation, fresh production analysis readback, five source-level manual-case spot checks, and claims/provenance review."
    - "The explicitly deferred second-seed/full-rerun requirement remains a disclosed project-level future gate and is outside this stage's repair scope."
  workstream_candidates: []
```

Next lifecycle action: run `stage-lifecycle checkpoint_review` for WP7-d. After that committed checkpoint passes its stale/provenance guards, WP7-d is eligible for `stage-lifecycle finalize`.
