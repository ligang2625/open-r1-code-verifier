# WP7-d Execution Report

## Execution summary

- Stage: `WP7-d`
- Task: `implementation`
- Profile: `validation`
- Control-plane hardware: `GTX 1660 Ti (6GB)`
- Target hardware: `GTX 1660 Ti (6GB)`
- Evidence class: `real-training/numerical`
- Development terminal: `false`
- Source plan commit: `b4c58abac5669dacfede6581917b93a086acc95c`
- Result code commit: `62b7e4d7beee2ce8f37018d1c37f76c932b1f7b8`
- Backend: `web_codexpro`
- Source routing: `single`, `difficult_serial`
- Effective execution mode: `single`
- Worktree: `/home/dzy/open-r1-code-verifier/.worktrees/wp7-d`
- Branch: `feat/wp7-d`
- Review/finalization: not performed

WP7-d completed the user-requested single-seed final analysis/presentation path. It did **not** execute a second training seed, GRPO rerun, target-GPU generation, or any other new RTX 4090 command. The accepted seed-42 A/B/C/D formal sources were consumed unchanged. Work in this execution was limited to deterministic case selection, human semantic failure analysis, a production labeled-analysis readback, a machine-readable final evidence snapshot, the technical report, and README presentation.

The scientific scope is intentionally explicit: `second_seed_executed=false`, `project_claim_scope=single_training_seed_seed42`, and `replication_status=pending_second_seed_or_full_rerun`. Deferring replication is a user-selected project-ordering decision, not an execution failure and not a claim that the project already satisfies the second-seed/full-rerun DoD item.

## Routing and baseline guards

- The sealed replacement plan superseded the earlier plan-only seed-43 replication proposal before any old-plan execution/review occurred.
- `execution_routing.version=1`, `mode=single`, `single_class=difficult_serial`, low parallelizability and low multi benefit were consumed unchanged.
- Explicit Web GPT + CodexPro execution used `backend=web`; source SINGLE remained `effective_execution_mode=single`.
- Initial `HEAD` equaled plan seal `b4c58abac5669dacfede6581917b93a086acc95c`.
- Stage branch was `feat/wp7-d`; initial and pre-report non-ignored status were clean.
- Stage and primary transport policy remained zero-tracked under `.ai-bridge/**`.
- Stage-local `code_verifier` and `open_r1` imports resolved inside `/home/dzy/open-r1-code-verifier/.worktrees/wp7-d`, not the primary checkout.
- No `operator_terminal_execution` existed because this formal-evidence-only validation stage targets the GTX 1660 Ti and executes no new 24GB-GPU gate.

## Execution preflight

All required preflight gates passed before the first tracked business artifact was created:

1. Stage analysis imports and editable-source bindings passed.
2. Frozen WP8-a hashes matched exactly:
   - input manifest: `118093d5befbd43bdd0e08527847d23f40626284f8e73b49dbe2df033d1e0da8`;
   - source inventory: `b79718d096be441b2d3d0e45b88b4b95ce1d458696617dafd80f1b11cfca18f1`;
   - `main_results.csv`: `02030685f05f0ed04d8e007cc0eb1a4455aacfbcbe6f505c13afd8849e63804e`;
   - `paired_comparisons.csv`: `0ae767e7e9e918d9fe2109a7f65b4aca39b4446c615beb694eb175adb80a3eed`;
   - `report_data.json`: `fd03754215297643aec8d32f1df65b9fd8df669c29983cd7573c5f3ff3fc74c2`;
   - `failure_candidates.jsonl`: `4410a05e2838a0be92997141bf19bb2b518a4985a8afabdc87442812827408ed`;
   - `manual_labels_template.csv`: `bad8b08c658ebfe10039b352d4f41a1b2a0615c4442dd286eeb892121529e79b`;
   - `costs.csv`: `7a7a4bc0f92b011ce6faa4167b71669833745bcf519a31b94d7f13d3102b4505`.
3. Production `load_analysis_config()` / `load_analysis_inputs()` strict-loaded Base, SFT, Public-RLVR and Hidden-RLVR at exactly `400` rows / `400` unique problem IDs per method.
4. Formal run IDs were `A-base-formal-seed42`, `B-sft-formal-seed42`, `C-public-grpo-formal-seed42`, and `D-hidden-grpo-formal-seed42`.
5. No old-plan `WP7-d-executor.md`, review, or operator script existed before this execution.
6. Focused analysis preflight: `41 passed`.
7. Baseline `make lint`: Ruff check/format and strict mypy passed for 114 source files.

## Deterministic manual-case freeze

Before opening any selected completion/extracted code, execution consumed only payload-free rows from the frozen WP8-a `failure_candidates.jsonl` and applied the sealed selection contract:

`selection_key = sha256("wp7-d-final-manual-v1|seed42|<method>|<run_id>|<problem_id>")`

Within each method candidates were sorted by `(selection_key, problem_id)` and the fixed quotas were selected:

- Public-RLVR: 10;
- Hidden-RLVR: 10;
- SFT: 5;
- total: 25 unique `(method, problem_id)` pairs.

The selector was rerun before code inspection and reproduced the selection bytes exactly.

Tracked selection artifact:

- `report/manual_case_selection.json`
- SHA256 `cd5ef448b8d4ee1ea85f364d05c90651b75267da3d431ac699ed6657b5c0e7ea`
- selection commit: `6277130` (`docs: freeze WP7-d manual case selection`)

Selected IDs were never replaced after code inspection.

## Human semantic failure analysis

After the selection commit, the 25 exact formal result rows were opened in batches. Inspection was restricted to model-generated extracted code plus run/model/problem IDs, parse status, execution status and visible/train-hidden/eval-hidden scalar outcomes. Eval-hidden test bodies, expected outputs, reference solutions and private SFT responses were not copied into tracked reports.

Each case received a manually authored category, reason, reward/data improvement suggestion, and `reward_hacking=yes|no|uncertain` judgment. These judgments were not generated by mapping `candidate_reasons` to manual categories.

Production `load_manual_labels()` strict-loaded all 25 rows successfully. Method counts:

- Public-RLVR: 10;
- Hidden-RLVR: 10;
- SFT: 5.

Manual category counts:

- `runtime_error`: 11;
- `incomplete_algorithm`: 6;
- `misunderstood_problem`: 5;
- `missed_edge_case`: 2;
- `syntax_error`: 1.

All 25 reviewed cases were labeled `reward_hacking=no` under the sealed rubric because the inspected code showed ordinary implementation/semantic failure modes without concrete sample-value hardcoding or another verifier-specific branch. This is **not** reported as a 0% population Reward-Hacking estimate: the set is a deterministic candidate-stratified qualitative sample rather than a random sample of all outputs.

Tracked manual artifacts:

- `report/manual_labels.csv` SHA256 `052dfcbed63b39934cc0886de4ea3adb8fb19a794b35b466d78796a064b71668`;
- `report/manual_failure_analysis.md` SHA256 `c4cc12d86dbe99d990020d2122e15c2fe0bf3f41c6821e43240e044806d18406`;
- manual-analysis commit: `d75d165812f1014c2175ef934ea7aae1c80c0ee3`.

A structural/leakage check found exactly 25 case sections and 25 extracted-code blocks and no copied `eval_hidden_tests`, reference-solution, expected-output, or private-SFT-response payload fields.

## Final labeled production analysis

A fresh machine-local manifest was derived from the frozen WP8-a manifest. A/B/C/D evaluation dirs, B/C/D training dirs, bootstrap seed `42`, `10000` resamples, confidence `0.95`, problem pairing, and null USD rate were preserved exactly. The only semantic change was:

`manual_labels_path=/home/dzy/open-r1-code-verifier/.worktrees/wp7-d/report/manual_labels.csv`

Manifest:

- `/home/dzy/wp8-analysis/wp7-d-input-b4c58ab-e0/formal-analysis.yaml`
- SHA256 `c38ba8cee584a150ac926946f0cc3ab67ac1c6c70f58e57f7821ef0b60bfd51b`

Production command:

`.venv/bin/code-verifier analyze-results --manifest /home/dzy/wp8-analysis/wp7-d-input-b4c58ab-e0/formal-analysis.yaml --output-dir /home/dzy/wp8-analysis/wp7-d-final-b4c58ab-e0`

Result: exit 0, `analyzed 400 problems`, `candidates=653`, `manual_labels=25`.

`report_data.json` records:

- `evidence_class=analysis_source_artifacts`;
- `manual_analysis_status=completed`;
- `manual_label_count=25`.

The following final files remained byte-for-byte identical to the WP8-a automated baseline, proving that the human layer did not change the numerical experiment:

- `main_results.csv` SHA256 `02030685f05f0ed04d8e007cc0eb1a4455aacfbcbe6f505c13afd8849e63804e`;
- `paired_comparisons.csv` SHA256 `0ae767e7e9e918d9fe2109a7f65b4aca39b4446c615beb694eb175adb80a3eed`;
- `costs.csv` SHA256 `7a7a4bc0f92b011ce6faa4167b71669833745bcf519a31b94d7f13d3102b4505`;
- `auto_error_counts.csv` SHA256 `01d22e2bfa3ec35631f55244a054a56df99eb56a22b841be768871b6970b6d1c`;
- `failure_candidates.jsonl` SHA256 `4410a05e2838a0be92997141bf19bb2b518a4985a8afabdc87442812827408ed`;
- `training_curves.csv` SHA256 `dfff63b5e05e20778e5ac659d823c07bab29fb75c77dab5888f414ce60682048`.

New manual-aware output hashes include:

- `manual_error_counts.csv`: `c154900da2148e0c403a1d23eb7f917e9d3b2735eb9a4505d651f09b6d8ad21e`;
- `report_data.json`: `d3953fc520ea5daf302a3a7c5971a1ddf5dd96b80ea7d02e5be07a8d87f21897`.

A second fresh run to `/home/dzy/wp8-analysis/wp7-d-final-b4c58ab-e0-readback` reproduced **all 10 analysis output files byte-for-byte**, including manual-aware outputs.

## Final evidence and presentation artifacts

`report/final_evidence.json` is the machine-readable numerical/claim authority for the final presentation layer. It binds frozen source hashes, final output hashes, manual artifact hashes, main/paired/cost rows, manual counts, and known limitations.

Required claim-state fields are:

- `project_claim_scope=single_training_seed_seed42`;
- `replication_status=pending_second_seed_or_full_rerun`;
- `second_seed_executed=false`;
- `wp7c_a1_posthoc_operational_equivalence=true`;
- `manual_review.candidate_sample_only=true`;
- `manual_review.population_prevalence_estimate=null`;
- `usd_cost_rate=null`.

Tracked presentation hashes at `result_code_commit`:

- `report/final_evidence.json`: `8431496e3978788348a9ab0373133cb06ec2d28edd581d6c4d42df62631cfada`;
- `report/technical_report.md`: `0cd7a64962ca276406274f5f65d9c1b2a162ff229cc6512917492f66ea5ac2f7`;
- `README.md`: `122a1b0796c8ba60de605ee8097bf08e5ddc9f8b2e15e0ec9cecc7e9754d4579`.

The technical report contains all 16 required sections. README now starts with the research question, key finding, method diagram, A-D table, final-analysis reproduce command, two reviewed candidate examples, measured hardware/GPU-hours, limitations, and links to the evidence/manual/technical reports. Historical engineering and workflow documentation remains below the results-first front page.

## Scientific interpretation recorded in the final artifacts

Formal seed-42 values remain:

| Method | Visible Pass@1 | Train-Hidden Pass@1 | Eval-Hidden Pass@1 |
|---|---:|---:|---:|
| Base | 0.1225 | 0.1175 | 0.1150 |
| SFT | 0.3525 | 0.3350 | 0.3775 |
| Public-RLVR | 0.3625 | 0.3400 | 0.3750 |
| Hidden-RLVR | 0.3625 | 0.3400 | 0.3750 |

Interpretation boundaries:

- SFT shows an observed +0.2625 / +26.25 percentage-point Eval-Hidden difference over Base in this formal pipeline.
- Public-RLVR and Hidden-RLVR each have Eval-Hidden delta `-0.0025` versus SFT with 95% CI `[-0.0125, 0.0075]`; documents therefore say no observed held-out improvement, **not** significant degradation.
- Hidden-RLVR versus Public-RLVR has zero predefined aggregate whole-pass deltas/intervals in this accepted run; documents do **not** convert this into a general equivalence claim.
- Automated candidate proxy and human Reward-Hacking judgment remain separate concepts.
- WP7-c A1 post-hoc operational-equivalence disclosure remains explicit in both README and the technical report.
- Training-seed robustness remains unknown because only seed 42 was executed; second-seed/full-rerun work is deferred to the user's later whole-project review.

## Validation and closeout evidence

Final required checks:

- `make lint`: PASS — Ruff check, Ruff format check and strict mypy passed.
- `make test`: PASS — `1030 passed`, `3 skipped`, `0 failed`; the three skips are the project's explicit opt-in real-Piston cases and were covered by the explicit Piston command below.
- `make test-gpu`: PASS — `3 passed`, `0 failed`, `0 skipped` on GTX 1660 Ti.
- `make test-piston PISTON_CONFIG=configs/execution/piston-local.yaml`: PASS — `9 passed`, `0 selected skipped`, `2 deselected`.
- `.venv/bin/python -m pytest tests/unit/analysis tests/integration/test_wp8_analysis_pipeline.py -q`: PASS — `41 passed`.
- Post-regression SHA assertions for selection, labels, manual report and final evidence: all exact hashes unchanged.
- Documentation/evidence consistency: PASS — technical report has exactly 16 numbered sections; key numerical values, single-seed limitation and A1 disclosure are present in README and report; final evidence retains manual count 25 and replication pending.
- `git diff --check`: PASS before presentation commit.
- Final non-ignored stage state before this execution report: clean.

## Deviations and blockers

- No production source, test, dependency, training config, evaluation config, plan, review, proceedings, or `third_party/open-r1/**` file was modified by execution after plan seal. The tracked changes are the manual-analysis/evidence/reporting artifacts and README requested by the sealed plan.
- One QA shell command that searched Markdown code-fence text was initially quoted incorrectly and failed in the shell before inspecting/modifying an artifact; the corrected read-only check passed. This had no research or repository effect.
- No environment checkpoint, operator checkpoint, target-GPU handoff, or unresolved blocker exists.
- The second training seed/full C/D rerun remains intentionally deferred by user direction. It is recorded as a known pending project-level scientific gate, not hidden and not marked complete.

```yaml
execution_record:
  version: 1
  stage_id: WP7-d
  execution_id: E0
  task_kind: implementation
  source_plan_commit: b4c58abac5669dacfede6581917b93a086acc95c
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: 62b7e4d7beee2ce8f37018d1c37f76c932b1f7b8
  execution_backend: web_codexpro
  effective_execution_mode: single
  status: completed
```
