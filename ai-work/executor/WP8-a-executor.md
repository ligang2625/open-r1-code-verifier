# WP8-a Execution Report

## Execution summary

- Stage: `WP8-a`
- Task: `implementation`
- Profile: `validation`
- Control-plane hardware: `GTX 1660 Ti (6GB)`
- Target hardware: `GTX 1660 Ti (6GB)`
- Evidence class: `real-training/numerical`
- Development terminal: `false`
- Source plan commit: `ab87fea68ccb727f939887fd60bfb5a7adc86da0`
- Result code commit: `ab87fea68ccb727f939887fd60bfb5a7adc86da0`
- Backend: `web_codexpro`
- Source routing: `single`, `normal`
- Effective execution mode: `single`
- Worktree: `/home/dzy/open-r1-code-verifier/.worktrees/wp8-a`
- Branch: `feat/wp8-a`
- Review/finalization: not performed

WP8-a completed as a zero-code formal validation execution. No production source, test, config, plan, review,
proceedings, or `third_party/open-r1/**` file required modification. Accepted canonical A/B/C/D artifacts were consumed
through production strict loaders on the GTX 1660 Ti control plane; no new 4090 command, generation, training, or
verification run was executed.

## Routing and baseline guards

- `execution_routing.version=1`, `mode=single`, `single_class=normal`, low parallelizability and low multi benefit were
  consumed unchanged from the sealed plan.
- Web GPT + CodexPro selected explicit `backend=web`; source SINGLE therefore remained
  `effective_execution_mode=single`.
- Initial and pre-report stage status was clean.
- Initial `HEAD` equaled the sealed plan commit `ab87fea68ccb727f939887fd60bfb5a7adc86da0`.
- Primary and stage `git ls-files .ai-bridge` both returned no tracked paths.
- Stage-local `code_verifier` and `open_r1` imports resolved inside this WP8-a worktree; `.venv` was not a symlink and
  stage-local Ruff/mypy/pytest were available.

## Execution preflight

All required preflight gates passed before any tracked business modification or commit:

1. Analysis import check: passed (`analysis-import-ok`).
2. Analysis unit suite: `35 passed`.
3. Real loopback Piston acceptance: `9 passed`, `0 selected skipped`, `2 deselected`.
4. Formal source identity:
   - Base / SFT / Public-RLVR / Hidden-RLVR evaluations each loaded with `400` rows and `400` unique problem IDs.
   - Completed B SFT identity loaded successfully.
   - Completed C/D GRPO identities loaded successfully after the synchronized historical `/root/sj-tmp/...` path was
     made readable on the control plane.
   - C reward mode is `public`; D reward mode is `hidden`.
   - C and D both strictly bind the same completed B parent at
     `/root/sj-tmp/open-r1-code-verifier-outputs/sft/B-sft-formal-seed42`.
5. Baseline `make lint`: Ruff check/format and strict mypy passed.

## Formal input freeze

Machine-local persistent input namespace:

`/home/dzy/wp8-analysis/wp8-a-input-ab87fea-e0/`

- `formal-analysis.yaml`: 767 bytes,
  SHA256 `118093d5befbd43bdd0e08527847d23f40626284f8e73b49dbe2df033d1e0da8`.
- `source-inventory.json`: 16,582 bytes,
  SHA256 `b79718d096be441b2d3d0e45b88b4b95ce1d458696617dafd80f1b11cfca18f1`.
- Bootstrap contract: seed `42`, `10000` resamples, confidence level `0.95`, unit `problem`.
- `gpu_hour_cost_usd: null`; no post-hoc USD rate was invented.
- `manual_labels_path: null`.

Accepted evaluation result hashes:

- Base A: `3c512ea6aeb160efa865e7b00c52a7494929f68d9bf10683b8746c6eac2d411b`.
- SFT B: `b53cb533b17ce7ca30e508a01cc484272470c64c1532d5a68810dfa66cd6291f`.
- Public C: `7c5bb7497389872ee55ec67c4cb73cb188b68f0da06750013f1bd7a734cbb913`.
- Hidden D: `004d5655b438244a729acd0b2b1fe33aed8ae5e8758fe462ac7215d1f54d12c5`.

Final completed adapter hashes used by the strict training identities:

- SFT B: `51042ea9c52d2d24976c2ca4e777f1a5f792e3943ff171d03e55b959463a7a67`.
- Public C: `7b6e9ecfcbc95270f53b8d3694594544fc3c84c9209a6d03de9df332ac47de3e`.
- Hidden D: `aa69ba543fe857ad28df6b3c2f282ea99f4ff57f30f8f2a38eab36d663e1c38a`.

The inventory explicitly preserves the WP7-c provenance disclosure: C/D are accepted under the committed A1 post-hoc
operational-equivalence amendment (`ai-work/planner/WP7-c-amendments.md` and
`ai-work/reviewer/WP7-c-review.md`). This execution does not describe C/D as satisfying the original preregistered
exact-code/save-cadence contract without that amendment.

## Formal production analysis

Command:

`.venv/bin/code-verifier analyze-results --manifest /home/dzy/wp8-analysis/wp8-a-input-ab87fea-e0/formal-analysis.yaml --output-dir /home/dzy/wp8-analysis/wp8-a-formal-ab87fea-e0`

Result: exit 0, `analyzed 400 problems`, `candidates=653`, `manual_labels=0`.

The production output contains the complete explicit 10-file `_ANALYSIS_LAYOUT` from the plan. `report_data.json`
records `evidence_class=analysis_source_artifacts`, bootstrap unit `problem`,
`manual_analysis_status=pending`, `manual_label_count=0`, and
`reward_hacking_candidate_status=automated_proxy_not_human_conclusion`.

### A-D main results

| Method | Visible Pass@1 | Train-Hidden Pass@1 | Eval-Hidden Pass@1 |
|---|---:|---:|---:|
| Base A | 0.1225 | 0.1175 | 0.1150 |
| SFT B | 0.3525 | 0.3350 | 0.3775 |
| Public C | 0.3625 | 0.3400 | 0.3750 |
| Hidden D | 0.3625 | 0.3400 | 0.3750 |

All four methods have exactly 400 formal problems and match the finalized proceedings point estimates.

### Problem-paired comparisons

All comparisons use 400 problem-ID pairs and 10,000 problem-level bootstrap resamples.

- Public-RLVR vs SFT: eval-hidden delta `-0.0025`, 95% CI `[-0.0125, 0.0075]`; public-eval-gap delta
  `0.0125`, CI `[0.0, 0.03]`; automated candidate-rate delta `0.0075`, CI `[0.0, 0.0175]`.
- Hidden-RLVR vs SFT: eval-hidden delta `-0.0025`, 95% CI `[-0.0125, 0.0075]`; public-eval-gap delta
  `0.0125`, CI `[0.0, 0.03]`; automated candidate-rate delta `0.0075`, CI `[0.0, 0.0175]`.
- Hidden-RLVR vs Public-RLVR: all three paired deltas are `0.0` with `[0.0, 0.0]` intervals. The C/D row is retained
  despite identical aggregate point estimates.

### Training curves and costs

Production source-to-derived spot checks matched the emitted curve row counts exactly:

- SFT: 2,549 curve rows; GPU-hours `0.5215871774233367`; rollout/token/executor fields unavailable by schema.
- Public-RLVR: 8,115 curve rows; GPU-hours `4.012272991803669`; 2,400 rollouts; 514,360 generated tokens;
  executor-hours `0.0582530611647443`.
- Hidden-RLVR: 8,115 curve rows; GPU-hours `3.5036727118225017`; 2,400 rollouts; 512,918 generated tokens;
  executor-hours `0.06447173045885166`.

All `estimated_cost_usd` fields are null because no auditable GPU-hour USD rate was frozen.

### Failure-analysis preparation

- `failure_candidates.jsonl`: 653 deterministic payload-free candidates.
- `manual_labels_template.csv`: 653 corresponding template rows.
- No manual field is prefilled; formal status remains pending with zero human labels.
- The Hidden-RLVR-only `train_hidden_pass_eval_fail` reason appears zero times on non-Hidden methods.
- Candidate volume is greater than the later 20-case manual-analysis minimum, but this stage does not claim any human
  analysis completion or final positive/negative research conclusion.

## Output hashes and deterministic readback

Canonical formal output directory:

`/home/dzy/wp8-analysis/wp8-a-formal-ab87fea-e0/`

- `auto_error_counts.csv`: 960 bytes, SHA256
  `01d22e2bfa3ec35631f55244a054a56df99eb56a22b841be768871b6970b6d1c`.
- `costs.csv`: 389 bytes, SHA256 `7a7a4bc0f92b011ce6faa4167b71669833745bcf519a31b94d7f13d3102b4505`.
- `failure_candidates.jsonl`: 205,367 bytes, SHA256
  `4410a05e2838a0be92997141bf19bb2b518a4985a8afabdc87442812827408ed`.
- `main_results.csv`: 1,168 bytes, SHA256 `02030685f05f0ed04d8e007cc0eb1a4455aacfbcbe6f505c13afd8849e63804e`.
- `manual_error_counts.csv`: 29 bytes, SHA256
  `50294642a74a02e7775ba183d1e53c1d4c79312fc58ffc03441a3f99165b3701`.
- `manual_labels_template.csv`: 133,549 bytes, SHA256
  `bad8b08c658ebfe10039b352d4f41a1b2a0615c4442dd286eeb892121529e79b`.
- `paired_comparisons.csv`: 504 bytes, SHA256
  `0ae767e7e9e918d9fe2109a7f65b4aca39b4446c615beb694eb175adb80a3eed`.
- `report_data.json`: 4,498,405 bytes, SHA256
  `fd03754215297643aec8d32f1df65b9fd8df669c29983cd7573c5f3ff3fc74c2`.
- `resolved_analysis.yaml`: 767 bytes, SHA256
  `5ea3944fa0487cf4b089ebbd5d5ce69475ccf3ac84af8ac0d3c3bd00c2b22e29`.
- `training_curves.csv`: 1,605,105 bytes, SHA256
  `dfff63b5e05e20778e5ac659d823c07bab29fb75c77dab5888f414ce60682048`.

A second fresh production run using the identical manifest wrote
`/home/dzy/wp8-analysis/wp8-a-formal-ab87fea-e0-readback/`. All 10 files were byte-for-byte identical to the canonical
run; every SHA256 above matched, proving deterministic numerical tables, paired bootstrap outputs, candidate ordering,
and structured report data for this frozen input.

## Validation and closeout evidence

- `.venv/bin/python -m pytest tests/unit/analysis/test_experiment.py -q`: `13 passed`.
- Real manifest `load_analysis_inputs()`: four methods × `400` records; strict B/C/D identities passed.
- `.venv/bin/python -m pytest tests/unit/analysis tests/integration/test_wp8_analysis_pipeline.py -q`: `41 passed`.
- Formal numerical assertion command: passed all point-estimate, paired-row, CI, evidence-class, manual-status, and cost
  assertions.
- Curve/cost production source-to-derived spot check: passed for SFT/Public/Hidden.
- Final `make lint`: Ruff check passed, Ruff format check passed, strict mypy passed for 114 source files.
- Final `make test`: `1030 passed`, `3 skipped`, `0 failed`. The three skips are the project's explicit opt-in real
  Piston cases in the default suite and are covered by the explicit Piston gate below.
- Final `make test-gpu`: `3 passed`, `0 failed`, `0 skipped` on GTX 1660 Ti.
- Final `make test-piston PISTON_CONFIG=configs/execution/piston-local.yaml`: `9 passed`, `0 selected skipped`,
  `2 deselected`.
- Post-regression strict readback again loaded Base/SFT/Public/Hidden with 400 records each and retained the same source
  hashes.

## Deviations and blockers

- The initial execution attempt before this completed run was blocked because the synchronized C/D training metadata
  referenced its immutable historical parent SFT path under `/root/sj-tmp/...`, while the 1660 Ti user could not traverse
  that path. The user synchronized the accepted canonical artifacts and restored local path accessibility; no formal
  source JSON was edited and no 4090 regeneration was performed.
- During this completed execution there were no production defects, tracked business modifications, execution
  checkpoints, or remaining environment blockers.
- The manual 20-case analysis and final narrative/report conclusion remain intentionally out of scope for WP8-a and must
  be handled by the subsequent stage using these sealed output hashes.

```yaml
execution_record:
  version: 1
  stage_id: WP8-a
  execution_id: E0
  task_kind: implementation
  source_plan_commit: ab87fea68ccb727f939887fd60bfb5a7adc86da0
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: ab87fea68ccb727f939887fd60bfb5a7adc86da0
  execution_backend: web_codexpro
  effective_execution_mode: single
  status: completed
```
