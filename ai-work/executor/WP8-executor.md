# WP8 Execution Report

## Execution summary

- Stage: `WP8`
- Task: `implementation`
- Profile: `development`
- Hardware: `GTX 1660 Ti (6GB)`
- Evidence class: `engineering`
- Development terminal: `true`
- Source plan commit: `c3b5337efdd43135087ea63a38efef1dc7e31ad2`
- Result code commit: `a61b4995b9a470f8425f1034e60c974c80f0f7b0`
- Backend: `local_codex`
- Effective mode: `single`
- Subagents: none
- Review/finalization: not performed

WP8 development implementation is complete. The stage adds strict A-D source identity validation, problem-paired
bootstrap comparisons, traceable report inputs, deterministic automatic failure candidates, human-label validation,
training curves, auditable costs, and the `analyze-results` CLI. It also completes the terminal development closeout
without starting optimizer-based SFT/GRPO or claiming fixture output as formal research evidence.

## Baseline and protocol checks

- Worktree: `/home/dzy/open-r1-code-verifier/.worktrees/wp8`
- Branch: `feat/wp8`
- Initial HEAD equaled the sealed plan commit.
- `ai-work/planner/WP8-plan.md` matched the file sealed at the plan commit.
- No prior `WP8` completed E0 existed.
- `git ls-files .ai-bridge` returned no paths before implementation and before report commit.
- The initial worktree was clean.
- Plan metadata matched router inputs: development / GTX 1660 Ti / engineering / terminal true.
- No `.codegraph/` index existed, so the repository CodeGraph fast path was not applicable.

## Execution preflight

All preflight commands ran before the first business modification or business commit.

1. `.venv/bin/python -c "import torch, peft, trl, transformers, accelerate, yaml; print(torch.__version__)"`
   - Passed; reported `2.6.0+cu124`.
2. `make test-gpu`
   - Passed: `3 passed`, `0 failed`, `0 skipped`.
3. `make test-piston`
   - Passed: `9 passed`, `0 failed`, `0 skipped` (`2 deselected` non-Piston cases).
4. `make lint`
   - Ruff check passed, Ruff format check passed, strict mypy passed for the baseline 91 source files.
5. `.venv/bin/python -m pytest tests/unit/evaluation/test_bootstrap.py -q`
   - Passed: `16 passed`.

## Implemented plan steps

### Step 1: project-owned scalar logging

- Added finite non-negative `executor_runtime_ms` to sanitized reward component records without changing reward
  calculation.
- Added SFT Trainer `state.log_history` normalization matching the existing GRPO finite numeric scalar contract.
- SFT and GRPO `metrics.jsonl` now distinguish `record_type: trainer` and `record_type: summary`.
- Updated unit and integration fixtures for the current metrics schema.
- Initial focused validation: `127 passed`.
- Commit: `0258f013d7e1801db010b54e2dfaa94126ef3804`.
- Regression fixture correction: `799210ddcbd6008f5f939a2ac93a2d8e8028008f`.

### Step 2: strict analysis manifest and A-D identities

- Added `code_verifier.analysis.experiment` with exact manifest schema and sanitized `AnalysisError` failures.
- Requires completed non-empty evaluation runs with unique problem IDs and matching row/run identities.
- Requires one A-D problem set, dataset hash, seed, split, device, deterministic generation definition, and Piston
  definition.
- Reloads completed B/C/D identities through the existing strict SFT/GRPO loaders.
- Requires Base to match B's base identity, B evaluation to bind the completed SFT adapter, C/D canonical evaluation
  checkpoint IDs, ordered public/hidden reward modes, and the same completed B parent.
- Validation: `7 passed`.
- Commit: `b8d59ad64e8f67a70f8b4cc3d515c1a829fd6a26`.

### Step 3: paired comparison and failure candidates

- Added strict `problem_id` pairing independent of source row order.
- Added problem-level paired bootstrap intervals for eval-hidden delta, public-eval-gap delta, and the shared automated
  candidate-rate delta.
- Kept the automated reward-hacking proxy definition method-independent: visible whole-pass with eval-hidden not
  whole-pass.
- Added deterministic payload-free candidate reasons derived only from available strict record fields.
- Validation: `6 passed`; aggregate analysis unit suite at that point: `13 passed`.
- Commit: `040bbd50a178713c184bee3b2b635c674ac5f34c`.

### Step 4: curve, cost, and manual-label contracts

- Added long-form finite Trainer scalar rows for SFT/Public-RLVR/Hidden-RLVR.
- Added completed-run cost rows from recorded GPU-hours, GRPO rollout/token counts, and executor-reported runtime.
- Preserved SFT rollout/generated-token/executor fields as unavailable rather than inventing values.
- Estimated USD cost remains null unless a finite non-negative hourly rate is explicit in the manifest.
- Added exact human-label CSV schema, category validation, unique candidate binding, and candidate metadata checks.
- Completed human analysis requires at least 20 unique candidate labels.
- Validation: initially `7 passed`; final report unit suite `15 passed`.
- Commit: `06b86fff0025e00cb0691c9d06144726a660ad30`.
- Final contract correction: `a61b4995b9a470f8425f1034e60c974c80f0f7b0`.

### Step 5: traceable report artifacts

- Added atomic generation into a new output directory with the exact 10-file layout from the plan.
- Generates four-row A-D main results with distinct public and train-verifier gap semantics.
- Generates the three required paired comparisons with point estimates and confidence intervals.
- Generates training curves, automatic error counts, failure candidates, blank human-label template, optional human
  counts, costs, resolved manifest, and structured report data.
- `report_data.json` records source run/checkpoint/config/dataset identities and SHA-256 of each source
  `samples/results.jsonl` without copying completion/code/test payloads.
- Existing outputs fail closed and temporary output is removed on failure.
- Commit: `513958d59e0d69969a5381249459252a63a6e8d8`.

### Step 6: CLI and documentation

- Added `code-verifier analyze-results --manifest ... [--output-dir ...]`.
- Default output follows `CODE_VERIFIER_ARTIFACT_ROOT/analysis` or `outputs/analysis`.
- Analysis errors use the existing sanitized exit code 2 path.
- Added README manifest/layout/evidence-boundary documentation and the WP8 repository contract in `AGENTS.md`.
- Validation: CLI plus analysis suite `86 passed`; command help passed; targeted mypy passed.
- Commit: `643c9f3256f366cb6034eb12670c26930444c7ed`.

### Step 7: deterministic WP8 integration fixture

- Added synthetic A/B/C/D completed artifact fixtures exercising the real production loaders and report generator.
- Verified four main rows, source hashes, problem-level bootstrap metadata, and automated-vs-human status.
- Reversed C/D source row order and reproduced the same paired comparison.
- Verified problem-set, dataset, and checkpoint drift fail atomically.
- Verified outputs do not claim formal training/manual evidence or copy private completion/code sentinels.
- Validation: `6 passed`.
- Commit: `1690e6e825022ac5fb1348e83ec4b1edacdd9727`.

Test packaging support commits were `d66eb5d56e317d28634e724e1aa4e8bbb289e66e` and
`31ee1c5437e57db29cea3f0018ed08f1908c6b41`; they make shared WP8 fixtures unambiguous to strict mypy.

## Validation and closeout evidence

- Focused WP8 gate:
  - Command: `.venv/bin/python -m pytest tests/unit/analysis tests/integration/test_wp8_analysis_pipeline.py tests/unit/rewards/test_common.py tests/unit/training/test_sft.py tests/unit/training/test_grpo.py tests/unit/test_cli.py -q`
  - Result: `219 passed`.
- First full `make test` exposed a non-environment regression in the WP6-a fake Trainer, which lacked the newly
  required `state.log_history`; the fixture was updated and committed, then all gates were rerun.
- Final `make lint`:
  - Ruff check passed.
  - Ruff format check passed for 102 files.
  - Strict mypy passed for 102 source files.
- Final `make test`:
  - `875 passed`, `3 skipped`, `0 failed`.
  - The three skips are the expected opt-in Piston cases in the default suite and are replaced by the explicit real
    Piston gate below.
- Final `make test-gpu`:
  - `3 passed`, `0 failed`, `0 skipped` on the GTX 1660 Ti CUDA path.
- Final `make test-piston`:
  - `9 passed`, `0 failed`, `0 skipped` (`2 deselected` non-Piston cases).
- Production critical-path scan:
  - `rg -n -i "TODO|FIXME|NotImplementedError|\bstub\b|\bfake\b" src/code_verifier configs`
  - No matches.
- `third_party/open-r1/**`: unchanged.
- Plan/review/proceedings/`.ai-bridge`: unchanged.
- No real optimizer-based SFT/GRPO was started.
- No fixture output was recorded as a real B/C/D checkpoint, formal A-D metric, cost result, or human conclusion.

## Development Completion Inventory disposition

- WP0-WP7 retain the finalized evidence listed in the sealed plan inventory.
- WP8 is covered by the implementations and engineering evidence above.
- The executor records terminal development acceptance only; it does not write a Development Complete Record,
  review the changes, finalize the stage, merge, or begin validation.

## Deviations and blockers

- No unresolved blocker remains.
- No execution checkpoint was needed.
- One full-suite regression was found and fixed in-scope; all final gates were rerun after the final code commit.
- No dependency files changed, so no stage-local full environment rebuild was required.

```yaml
execution_record:
  version: 1
  stage_id: WP8
  execution_id: E0
  task_kind: implementation
  source_plan_commit: c3b5337efdd43135087ea63a38efef1dc7e31ad2
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: a61b4995b9a470f8425f1034e60c974c80f0f7b0
  execution_backend: local_codex
  effective_execution_mode: single
  status: completed
```

## Repair execution E1

- Task: `repair`
- Source review: round 1 at `2d447adfc079afc75ab6a7305fe8a3f41c5789a1`
- Routed issues: `R1-M1`, `R1-M2`, `R1-M3`, `R1-m1`, `R1-m2`
- Result code commit: `a55c36b0325254c2166836e7fbde8dd29027ccaa`
- Backend/mode: `local_codex` / `single`
- Subagents: none
- Review/finalization: not performed

### E1 baseline and preflight

- Repair began with `HEAD` exactly equal to the routed review commit, branch `feat/wp8`, a clean worktree, and no
  tracked `.ai-bridge` paths.
- The sealed plan and committed review matched their routed commits; plan metadata matched development / GTX 1660 Ti
  (6GB) / engineering / terminal true.
- Before the first business modification, the complete plan preflight passed:
  - pinned imports passed with torch `2.6.0+cu124`;
  - `make test-gpu`: `3 passed`, 0 failed, 0 skipped;
  - `make test-piston`: `9 passed`, 0 failed, 0 skipped (`2 deselected`);
  - `make lint`: Ruff check/format and strict mypy passed;
  - evaluation bootstrap smoke: `16 passed`.

### E1 issue disposition

- `R1-M1`: added canonical recomputation of persisted resolved evaluation config identity through the production
  evaluation parser/hash rules; Analysis now rejects resolved config or Piston definition tampering. Added both tamper
  tests.
- `R1-M2`: completed evaluation sources now require valid `project_commit`, `open_r1_commit`, and
  `dependency_lock_hash` provenance, and `report_data.json` retains all three per source. Added malformed/missing and
  report-retention tests.
- `R1-M3`: added the deterministic scalar-only `large_public_eval_gap` reason when
  `visible_pass_rate - eval_hidden_pass_rate > 0.5`.
- `R1-m1`: restricted `train_hidden_pass_eval_fail` to `Hidden-RLVR`; the shared visible-to-eval automated proxy is
  unchanged.
- `R1-m2`: fixture integration output now explicitly records `evidence_class: engineering_fixture_synthetic`; the
  production CLI default remains `analysis_source_artifacts`, and the exact analysis manifest schema is unchanged.

Changed production/test files:

- `src/code_verifier/evaluation/evaluate.py`
- `src/code_verifier/analysis/experiment.py`
- `src/code_verifier/analysis/compare.py`
- `src/code_verifier/analysis/report.py`
- `tests/unit/analysis/test_experiment.py`
- `tests/unit/analysis/test_compare.py`
- `tests/unit/analysis/test_report.py`
- `tests/integration/test_wp8_analysis_pipeline.py`

### E1 validation and closeout

- Initial routed focused tests: `40 passed`.
- Plan focused WP8 gate: `227 passed`.
- The first global lint run found one non-environment strict-mypy narrowing error. It was fixed in scope and committed;
  no environment checkpoint was used.
- Final `make lint`: Ruff check/format and strict mypy passed for 102 source files.
- Final `make test`: `881 passed`, `3 skipped`, 0 failed. The skips were the expected opt-in Piston tests and were
  replaced by the dedicated gate.
- Final `make test-gpu`: `3 passed`, 0 failed, 0 skipped.
- Final `make test-piston`: `9 passed`, 0 failed, 0 skipped (`2 deselected`).
- Production critical-path scan found no `TODO`, `FIXME`, `NotImplementedError`, `stub`, or `fake` matches under
  `src/code_verifier` or `configs`.
- Plan/review/proceedings/`third_party/open-r1`/`.ai-bridge` remained unchanged; no dependency file changed, no real
  optimizer-based training ran, and no fixture output was represented as validation evidence.
- No unresolved blocker or deviation remains.

```yaml
execution_record:
  version: 1
  stage_id: WP8
  execution_id: E1
  task_kind: repair
  source_plan_commit: c3b5337efdd43135087ea63a38efef1dc7e31ad2
  source_review_round: 1
  source_review_commit: 2d447adfc079afc75ab6a7305fe8a3f41c5789a1
  repair_issue_ids: [R1-M1, R1-M2, R1-M3, R1-m1, R1-m2]
  result_code_commit: a55c36b0325254c2166836e7fbde8dd29027ccaa
  execution_backend: local_codex
  effective_execution_mode: single
  status: completed
```
