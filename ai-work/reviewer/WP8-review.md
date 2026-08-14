# WP8 Review

## Review round 1

```yaml
review_record:
  version: 1
  stage_id: WP8
  review_round: 1
  source_execution_id: E0
  reviewed_head_commit: dc00d8ffe98710dd5b4687abf4bf926054c8e2bf
  conclusion: needs_repair
```

### Scope and provenance

- Reviewed sealed plan `ai-work/planner/WP8-plan.md`, source plan commit `c3b5337efdd43135087ea63a38efef1dc7e31ad2`.
- Latest completed execution is `E0`, `task_kind=implementation`, with `result_code_commit=a61b4995b9a470f8425f1034e60c974c80f0f7b0`.
- The execution report is committed at and uniquely bound to stage HEAD `dc00d8ffe98710dd5b4687abf4bf926054c8e2bf`; review started with `HEAD` exactly at that commit and the stage worktree clean.
- Stage worktree is `/home/dzy/open-r1-code-verifier/.worktrees/wp8`, branch `feat/wp8`; `git ls-files .ai-bridge` was empty.
- Stage profile is `development`, target hardware `GTX 1660 Ti (6GB)`, evidence class `engineering`, and `development_terminal=true`. Real optimizer-based SFT/GRPO, formal B/C/D checkpoints, final A-D numerical conclusions, and 24GB validation were correctly treated as out of scope.
- Business commits from plan seal through `result_code_commit` remained within WP8 scope: reward/SFT scalar logging, the new Analysis Layer, CLI/docs/tests, and fixture support. No dependency file or `third_party/open-r1/**` change was observed in the implementation commit range.

### Independent findings

#### R1-M1 — Evaluation `resolved_config.yaml` is not cryptographically bound back to the completed run `config_hash`

**Severity: major. Action required.**

`src/code_verifier/analysis/experiment.py` loads each evaluation's `run.json`, `resolved_config.yaml`, and `samples/results.jsonl` separately. `_load_evaluation_run()` only checks that the persisted `config_hash` in `run.json` equals the hash string carried by every `EvaluationRecord`; `_validate_shared_evaluation_contract()` then trusts the independently loaded `resolved_config.yaml` for split/device/generation/Piston comparison. It never recomputes the evaluation config identity from the resolved config + model/seed/Piston definition and compares that result with the completed run's `config_hash`.

This means the analysis layer can accept a post-hoc rewritten evaluation definition as long as the same rewritten fields are made consistent across A-D. I independently reproduced this with the repository's existing analysis fixture: after `_fixture()` created four completed evaluation artifacts, I changed all four `resolved_config.yaml` files from their recorded generation definition to `max_new_tokens=999` without changing any `run.json` or `results.jsonl`; `load_analysis_inputs()` still returned successfully (`accepted-tampered-resolved-config`).

That violates the sealed plan's strict source-identity/fail-closed requirement and makes the final same-evaluation-definition assertion non-auditable. Repair must bind each loaded resolved evaluation definition to its persisted completed-run `config_hash` using the production evaluation identity rules, then test post-hoc resolved-config/Piston-definition tampering explicitly.

#### R1-M2 — `report_data.json` drops source code/dependency provenance required by the sealed plan

**Severity: major. Action required.**

The sealed plan requires `report_data.json` to persist each source's run/checkpoint/dataset/config/**provenance** plus the source results hash. Completed evaluation `run.json` already records provenance fields including `project_commit`, `open_r1_commit`, and `dependency_lock_hash` (`src/code_verifier/evaluation/evaluate.py`). However `_build_report_data()` in `src/code_verifier/analysis/report.py` only copies `run_id`, model identity, checkpoint, `dataset_hash`, `config_hash`, results path, and results SHA-256.

As a result, a downstream README/report consumer cannot recover the code/submodule/dependency provenance from the derived WP8 artifact alone, despite those fields being available in the authoritative source run metadata. This is an explicit plan acceptance item, not optional metadata. Repair should validate and retain the relevant completed-run provenance fields in `report_data.json` and add tests that fail if required source provenance is missing or malformed.

#### R1-M3 — Automatic failure-candidate selection misses the required large public→eval gap rule

**Severity: major. Action required.**

Project spec §14.1 requires automatic candidate marking when the visible-vs-eval-hidden gap exceeds `0.5`. `select_failure_candidates()` currently only emits reasons for visible whole-pass/eval failure, train-hidden whole-pass/eval failure, partial eval-hidden failure, parse/runtime/timeout, and truncation. A normal wrong-answer record with `visible_pass_rate=0.75`, `eval_hidden_pass_rate=0.0`, and `error_category_auto="large_public_eval_gap"` therefore produces no candidate at all.

I reproduced this directly against the current code; `select_failure_candidates("Public-RLVR", [record])` returned `()` for that case. This can remove precisely the overfitting/reward-hacking candidates WP8 is supposed to surface and can shrink the validation-time manual-review pool. Repair should add a deterministic scalar-only large-gap candidate reason/rule (without inspecting or copying code payloads) and cover it in unit/integration tests.

#### R1-m1 — `train_hidden_pass_eval_fail` is emitted for every method instead of being a Hidden-RLVR-specific extra reason

**Severity: minor. Action required.**

The sealed plan keeps the reward-hacking proxy method-independent, but states that **Hidden-RLVR** may additionally carry `train_hidden_pass_eval_fail` as a candidate reason because train-hidden is its training verifier. `_candidate_reasons()` has no method input and currently emits this reason for Base, SFT, Public-RLVR, and Hidden-RLVR alike; the current unit test even expects it for `Public-RLVR`.

That makes the candidate taxonomy imply a training-verifier relationship where none exists for Base/SFT/Public-RLVR. Repair should keep the shared visible→eval proxy unchanged while restricting the train-hidden-specific reason to Hidden-RLVR, then update the test accordingly.

#### R1-m2 — Fixture analysis output is not explicitly marked as fixture/synthetic engineering evidence

**Severity: minor. Action required.**

The sealed integration requirement says the fixture/synthetic analysis report must **explicitly** mark itself as engineering evidence and must not merely avoid claiming formal validation. The current `report_data.json` writes `"evidence_class": "analysis_source_artifacts"`, while `test_wp8_fixture_outputs_never_claim_real_training_or_manual_evidence` only checks that formal-validation strings are absent. Absence of a false claim is weaker than the required explicit fixture/synthetic marker.

Repair should make the deterministic WP8 fixture report carry an explicit fixture/synthetic engineering-evidence marker in a way that cannot be confused with validation output, and make the integration assertion positively require that marker. This must not weaken the exact production manifest schema or let synthetic data satisfy validation gates.

### Independent verification evidence

- Lint/type gate:
  - `make lint`
  - Result: Ruff check PASS; Ruff format PASS (`102 files already formatted`); strict mypy PASS (`Success: no issues found in 102 source files`).
- Focused WP8 gate:
  - `.venv/bin/python -m pytest tests/unit/analysis tests/integration/test_wp8_analysis_pipeline.py tests/unit/rewards/test_common.py tests/unit/training/test_sft.py tests/unit/training/test_grpo.py tests/unit/test_cli.py -q`
  - Result: `221 passed`.
- Full default suite:
  - `make test`
  - Result: `875 passed, 3 skipped`; the three skips are the explicit opt-in real-Piston tests and therefore do not substitute for the dedicated Piston gate.
- GPU terminal gate:
  - `make test-gpu`
  - Result: `3 passed`, `0 failed`, `0 skipped` on the development CUDA path.
- Real Piston terminal gate:
  - `make test-piston`
  - Result: `9 passed`, `0 failed`, `0 skipped` (`2 deselected` non-Piston cases).
- Production critical-path scan:
  - Independent searches under `src/code_verifier` found no `TODO`, `FIXME`, `NotImplementedError`, `stub`, or `fake` production implementation markers; no `TODO` was found under `configs`.
- Tamper probe for R1-M1:
  - Rewrote all four fixture evaluation `resolved_config.yaml` generation definitions after run creation while preserving their persisted `run.json` / record `config_hash` values.
  - Current `load_analysis_inputs()` accepted the modified artifacts.
- Candidate probe for R1-M3:
  - Constructed a scalar-only Public-RLVR record with visible pass rate `0.75`, eval-hidden pass rate `0.0`, and `error_category_auto=large_public_eval_gap`.
  - Current `select_failure_candidates()` returned no candidate.
- Review tests/probes left the stage worktree clean; reviewed HEAD remained `dc00d8ffe98710dd5b4687abf4bf926054c8e2bf` through the read/test portion of review.

### Development Completion Inventory disposition

- WP0: finalized evidence present in `proceedings.md`; PASS for inventory purposes.
- WP1: finalized/accepted evidence present in `proceedings.md`; PASS for inventory purposes.
- WP2: finalized/accepted evidence present in `proceedings.md`; PASS for inventory purposes.
- WP3: finalized/accepted evidence present in `proceedings.md`; PASS for inventory purposes.
- WP4: finalized/accepted evidence present in `proceedings.md`; PASS for inventory purposes.
- WP5: WP5-a/WP5-b aggregation is recorded complete in `proceedings.md`; PASS for inventory purposes.
- WP6: WP6-a/WP6-c development aggregation is recorded complete; real SFT remains correctly deferred to validation; PASS for inventory purposes.
- WP7: WP7-a/WP7-b development aggregation is recorded complete; real GRPO remains correctly deferred to validation; PASS for inventory purposes.
- WP8: implementation and terminal test infrastructure are substantially present, but the five actionable analysis-contract findings above mean `covered_by_this_stage` is not yet satisfied.
- Terminal closeout commands themselves (`make lint`, `make test`, `make test-gpu`, `make test-piston`) independently PASS, including GPU/Piston 0 skipped, and no production-critical stub/TODO/fake implementation was found. These gates do not override the unresolved WP8 contract defects.

### Execution-report claim disposition

- Preflight and final lint/default/GPU/Piston results: independently verified and consistent with the report.
- No real optimizer training / no formal A-D research evidence: consistent with reviewed scope.
- `third_party/open-r1/**` unchanged: consistent with implementation commit scope.
- "strict A-D source identity validation" and fully traceable report provenance: **not fully verified; contradicted by R1-M1 and R1-M2**.
- failure-candidate/error-analysis completion: **not fully verified; contradicted by R1-M3/R1-m1**.
- fixture evidence boundary: mostly respected, but the explicit positive engineering-evidence marker required by the sealed plan is missing (R1-m2).

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
  independent_workstreams: 2
  repair_issue_ids:
    - R1-M1
    - R1-M2
    - R1-M3
    - R1-m1
    - R1-m2
  rationale:
    - "The remaining defects are concentrated in the WP8 Analysis Layer and its tests: evaluation identity/provenance and candidate/evidence semantics are somewhat separable, but they converge on the same strict schemas and integration fixture."
    - "A single repair execution is lower risk than multi-agent coordination because source identity, report provenance, candidate taxonomy, and fixture evidence markers must remain mutually consistent and then rerun the terminal closeout gates."
  workstream_candidates: []
```

### Conclusion

**NEEDS REPAIR.** The reviewed state at `dc00d8ffe98710dd5b4687abf4bf926054c8e2bf` passes the terminal environment/test gates but does not yet satisfy the sealed WP8 analysis and traceability contract. In particular, resolved evaluation definitions are not bound back to the completed config identity, source provenance is incomplete in the derived report, and the failure-candidate/evidence semantics have uncovered gaps.

The next lifecycle operation is `$stage-lifecycle checkpoint_review`. After that review checkpoint is committed, route a SINGLE repair execution for exactly `R1-M1`, `R1-M2`, `R1-M3`, `R1-m1`, and `R1-m2`, then run reviewer-ex again on the new completed repair execution.

## Review round 2

```yaml
review_record:
  version: 1
  stage_id: WP8
  review_round: 2
  source_execution_id: E1
  reviewed_head_commit: defc6d40dffbd60cc65d878319ffaa3d25a7f83e
  conclusion: pass
```

### Scope and provenance

- Reviewed the new completed `E1` repair execution. Its execution record is committed at stage HEAD `defc6d40dffbd60cc65d878319ffaa3d25a7f83e`; `result_code_commit=a55c36b0325254c2166836e7fbde8dd29027ccaa`.
- E1 is correctly bound to committed R1 via `source_review_round=1` and `source_review_commit=2d447adfc079afc75ab6a7305fe8a3f41c5789a1`, and its `repair_issue_ids` exactly cover `R1-M1`, `R1-M2`, `R1-M3`, `R1-m1`, and `R1-m2`.
- Review started with the stage worktree clean, branch `feat/wp8`, and `HEAD` exactly equal to the execution-report commit. `git ls-files .ai-bridge` remained empty.
- The sealed profile remains `development` / `GTX 1660 Ti (6GB)` / `engineering` / `development_terminal=true`; no real optimizer training, formal A-D numerical evidence, or 24GB validation was required or accepted for this review.

### R1 issue disposition

- **R1-M1 — RESOLVED.** `resolved_evaluation_config_hash()` now re-parses the persisted resolved evaluation definition through the production `EvaluationConfig` schema and recomputes the canonical `evaluation_config_hash`, including the exact Piston YAML digest, model identity, and seed. `_load_evaluation_run()` requires this recomputed identity to equal the persisted completed-run `config_hash`. The original reviewer tamper scenario was independently repeated by rewriting all four fixture generation definitions after run creation; current code rejected the artifacts (`REJECTED_TAMPER`). Unit tests also cover resolved-config and Piston-definition tampering.
- **R1-M2 — RESOLVED.** Analysis source loading now requires the persisted evaluation provenance fields and `report_data.json` retains `project_commit`, `open_r1_commit`, and `dependency_lock_hash` for every A-D source alongside run/model/checkpoint/dataset/config identity and source-results SHA-256. Tests verify malformed/missing provenance rejection and positive provenance retention.
- **R1-M3 — RESOLVED.** Candidate selection now adds the scalar-only `large_public_eval_gap` reason when `visible_pass_rate - eval_hidden_pass_rate > 0.5`. The original `0.75 -> 0.0` probe now returns exactly that reason.
- **R1-m1 — RESOLVED.** `train_hidden_pass_eval_fail` is now gated on `method == "Hidden-RLVR"`; an otherwise identical Public-RLVR sample yields no train-hidden-specific candidate while Hidden-RLVR yields the intended reason. The method-independent visible→eval reward-hacking proxy remains unchanged.
- **R1-m2 — RESOLVED.** Fixture integration calls explicitly generate `report_data.json` with `evidence_class="engineering_fixture_synthetic"` and positively assert that marker. The production/default `analyze_experiment()` path remains `analysis_source_artifacts`, and the exact analysis manifest schema was not expanded or weakened.

### Independent verification evidence

- Repair-focused Analysis suite:
  - `.venv/bin/python -m pytest tests/unit/analysis tests/integration/test_wp8_analysis_pipeline.py -q`
  - Result: `40 passed`.
- Exact WP8 focused gate:
  - `.venv/bin/python -m pytest tests/unit/analysis tests/integration/test_wp8_analysis_pipeline.py tests/unit/rewards/test_common.py tests/unit/training/test_sft.py tests/unit/training/test_grpo.py tests/unit/test_cli.py -q`
  - Result: `227 passed`.
- Lint/type terminal gate:
  - `make lint`
  - Result: Ruff check PASS, Ruff format PASS (`102 files already formatted`), strict mypy PASS (`Success: no issues found in 102 source files`).
- Full default terminal gate:
  - `make test`
  - Result: `881 passed, 3 skipped`; all three skips are the expected explicit Piston opt-in cases and are replaced by the dedicated real-Piston gate below.
- GPU terminal gate:
  - `make test-gpu`
  - Result: `3 passed`, `0 failed`, `0 skipped`.
- Real Piston terminal gate:
  - `make test-piston`
  - Result: `9 passed`, `0 failed`, `0 skipped` (`2 deselected` non-Piston cases).
- Production critical-path review found no `TODO`, `FIXME`, `NotImplementedError`, `stub`, or `fake` production implementation marker under `src/code_verifier`; no `TODO` was found under `configs`.
- Review commands and probes left the stage code state clean; `HEAD` remained `defc6d40dffbd60cc65d878319ffaa3d25a7f83e` throughout the read/test portion of R2.

### Development Completion Inventory disposition

- WP0, WP1, WP2, WP3, and WP4 remain recorded as completed/accepted in `proceedings.md` and match the sealed inventory.
- WP5 remains covered by finalized WP5-a/WP5-b development evidence.
- WP6 remains covered by finalized WP6-a/WP6-c development evidence; real SFT training correctly remains validation-only.
- WP7 remains covered by finalized WP7-a/WP7-b development evidence; real GRPO training correctly remains validation-only.
- WP8 is now covered by this stage: the Analysis Layer, strict A-D identity/provenance validation, paired comparison, candidate/manual tooling, training curves/costs, report generation, CLI/docs, deterministic integration fixture, and terminal engineering gates are all present and independently verified.
- Therefore the sealed WP0-WP8 Development Completion Inventory is fully satisfied for this terminal development stage. This review does not itself write a `Development Complete Record`; that remains exclusively the responsibility of `stage-lifecycle finalize` after this PASS review is checkpointed.

### Findings

No blocker, major, minor, or other actionable issue remains in the reviewed E1 state. No new repair issue ID is required.

```yaml
repair_routing:
  version: 1
  required: false
  source_review_round: 2
  mode: null
  complexity: null
  single_class: null
  parallelizability: null
  multi_benefit: null
  independent_workstreams: 0
  repair_issue_ids: []
  rationale:
    - "All five R1 repair issues are independently verified as resolved without weakening the sealed WP8 schemas, evidence boundary, or terminal acceptance criteria."
    - "Focused, full, lint/type, GPU, real-Piston, tamper, candidate-taxonomy, provenance, fixture-evidence, and Development Completion Inventory checks pass; no actionable repair remains."
  workstream_candidates: []
```

### Conclusion

**PASS.** The reviewed state at `defc6d40dffbd60cc65d878319ffaa3d25a7f83e` satisfies the sealed WP8 terminal-development plan and resolves all R1 findings. The next lifecycle operation is `$stage-lifecycle checkpoint_review`; if that checkpoint remains current, proceed with `$stage-lifecycle finalize` so lifecycle can merge WP8, write the terminal `Development Complete Record`, and report the exact `development_complete_commit` for the subsequent 1660 Ti → 4090 handoff.
