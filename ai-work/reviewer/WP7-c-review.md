# WP7-c Review

## Review round 1

### Review Record

```yaml
review_record:
  version: 1
  stage_id: WP7-c
  review_round: 1
  source_execution_id: E0
  reviewed_head_commit: 66ce5f498a03a59e6de8d5a8b1b8d77a9fa13d01
  workflow_runtime_commit: 657030c47a29411e343049926de10730858104a8
  conclusion: needs_repair
```

### Scope and provenance

- Reviewed the exact WP7-c worktree `/home/dzy/open-r1-code-verifier/.worktrees/wp7-c`, branch `feat/wp7-c`, at clean pre-review HEAD `66ce5f498a03a59e6de8d5a8b1b8d77a9fa13d01`. `git ls-files .ai-bridge` was empty.
- Reviewed sealed plan `ai-work/planner/WP7-c-plan.md` from `source_plan_commit=8464e69691c527c726a2e28e5a7ca81fa2001bbf` and latest completed execution `E0`. The execution report commit is exactly the reviewed HEAD.
- `E0` is `task_kind=implementation`, `result_code_commit=0e2a894943cfb623610e937380342d148ad8cff0`, `execution_backend=web_codexpro`, and records active-stage workflow runtime `657030c47a29411e343049926de10730858104a8`; that runtime object exists as a Git commit.
- Stage profile is `validation` / `real-training/numerical` targeting the RTX 4090 for optimizer/generation gates and GTX 1660 Ti control-plane Piston verification. Synthetic evidence was not accepted for any real gate.
- C25 formal evidence was independently read from `/home/dzy/wp7c-operator-evidence/WP7-c/grpo-cd-formal/C25`; C27 generation evidence from `/home/dzy/wp7c-operator-evidence/WP7-c/grpo-cd-generate-eval/C27`; final verification/aggregation artifacts from `/home/dzy/wp7c-verified`.

### Plan completion / acceptance disposition

| Item | Status | Evidence | issue_id |
|---|---|---|---|
| Paired CLI/data/B binding and reward-source isolation | PASS | Production pair validation; C uses `visible_tests`, D uses `train_hidden_tests`; C25 postcheck and formal run metadata | — |
| Stable paired-definition provenance | PASS, with limitation noted below | Formal C/D both persist pair SHA `31f5464abf094d14cf86e8ef4dd909b8a1be559c8b4ca8b96473070a9f1daad9`, matching component dataset/config/B identities | — |
| GRPO telemetry/cost/checkpoint durability | PASS | C25 postcheck: each formal run has 300 trainer steps, 2400 rollouts, 2400 reward rows, 600 group rows, finite trainer/reward/timing/GPU telemetry, recovery history, final adapters | — |
| 20-step paired smoke | PASS | C5 evidence accepted by the execution lineage; no contradictory evidence found | — |
| 100-step paired pilot uses sealed cadence | WITH PLAN DEVIATION | Plan fixes pilot `save_steps=50`; tracked `validation-pilot-public.yaml` (and paired hidden config) use `save_steps=10` after execution-time change | `R1-M1` |
| 300-step formal C/D use sealed formal definition | WITH PLAN DEVIATION | Plan fixes formal `save_steps=50` with other formal hyperparameters unchanged; tracked `public.yaml`/`hidden.yaml` use `save_steps=25`, and C25 evidence has checkpoints every 25 steps | `R1-M1` |
| Final formal C/D share the same sealed project/code context | FAIL | Public formal run originates at `a7c3c4da...` and completes under `47c7fb2a...`; Hidden originates at `47c7fb2a...` and completes under `31b99727...`. The sealed plan explicitly forbids splicing an old incomplete formal member with the other member after an identity-changing tracked repair | `R1-B1` |
| Deterministic C/D generation, 400 rows each | PASS as downstream evidence of the produced checkpoints | C27 evidence and synchronized bundle hashes match E0; exact readback is 400 resumed / 0 generated for both | — |
| Real control-plane Piston verification, 400 rows each | PASS as downstream evidence of the produced checkpoints | `/home/dzy/wp7c-verified`: both result streams hash exactly as E0, each has 400 rows, sealed order/data/Piston identity, no sandbox/infrastructure errors | — |
| Aggregation finite and traceable | PASS | Public/Hidden summary and CSV hashes exactly match E0; summaries trace to 400 verification rows | — |
| Reviewer-owned lint/default/GPU/Piston gates | PASS | Independent reruns listed below | — |
| No WP8 final A-D analysis/finalize/merge/push in this stage | PASS | E0 stops at C/D pairing readiness and review boundary | — |

The same-pair SHA does not resolve `R1-B1`: `_paired_definition()` deliberately hashes portable scientific config/data/B/seed identity and does not include the per-attempt project commit. The sealed plan separately requires same project/code context and explicitly forbids cross-code splicing.

### Independent tests and evidence checks

- `make lint` → PASS: Ruff check/format and strict Mypy clean.
- `make test` → PASS: `1030 passed, 3 skipped`, with only the expected env-gated real-Piston skips.
- `make test-gpu` → PASS: `3 passed`.
- `make test-piston PISTON_CONFIG=configs/execution/piston-local.yaml` → PASS: `9 passed, 2 deselected`, zero selected skips/failures.
- Tracked C25 formal operator script SHA256 independently recomputed as `cb68ff0c5dfc852810c6e6aff620093f0dd1ea7f4d759e9c5902607126551fae`, matching C25 evidence.
- Tracked C27 generation operator script SHA256 independently recomputed as `e03bae85798260d2e5dfe4fb515bf7f703dc47f09deae57c67a3c8ac6f164926`, matching C27 evidence.
- Received C25 `operator-evidence.json` SHA256 independently recomputed as `0fe7f376fb94918f5e5aee1c28bcc0ac159687fefd9600509efb35773ca2df9e`; C25 postcheck SHA256 is `c41e17a3a22b1e3c54de006c058165e32c0774c2d50581844194906c75b46a63`. Both match E0. C25 records `command_rc=0`, `postcheck_rc=0`, `gate_status=passed`, RTX 4090 / 22683 MiB, formal pair/Piston/B identities, and generation not started.
- Received C27 `operator-evidence.json` SHA256 independently recomputed as `4e2912a57b7fa5f1a3864db3e2bf938026357f4808bc85ae513042dca677a098`; C27 postcheck SHA256 is `dc014c76b6bfb73fb6d30de8ddd13865309f1cd148c3eb8bd03cdab332807745`. Both match E0. C27 records `command_rc=0`, `postcheck_rc=0`, `gate_status=passed`, 400/400 deterministic generation and 400/0 exact readback.
- C27 synchronized Public/Hidden generation run and records hashes independently match E0 exactly: `0d081a3a...` / `a5d841f6...` and `644fbd3a...` / `f84c2ab7...`.
- Control-plane verification and aggregate hashes independently match E0 exactly:
  - Public run `bf777fc6...`, results `7c5bb749...`, summary `6cc3fa7b...`, CSV `c39c7573...`.
  - Hidden run `5d6cc0a8...`, results `004d5655...`, summary `f63a2018...`, CSV `8da04392...`.
- Public and Hidden formal received `run.json` files themselves hash to the values bound by C25 operator evidence, so the code-lineage mismatch in `R1-B1` is present in authenticated preserved evidence rather than being a reporting discrepancy.

### Execution report claim verification

- E0's final lint/default/GPU/Piston pass claims: VERIFIED independently.
- E0's accepted C25/C27 evidence and postcheck hashes: VERIFIED independently.
- E0's C/D generation run/records hashes and control-plane verification/aggregate hashes: VERIFIED independently.
- C25/C27 `command_rc=0`, `postcheck_rc=0`, `gate_status=passed`, target GPU identity, formal data/pair/B/Piston identities, and generation-only vs verification separation: VERIFIED from preserved evidence.
- E0's statement that formal C/D completed and downstream generation/verification succeeded is factually correct. The review failure is instead sealed-plan conformance: those successful artifacts were produced after execution-time changes to code identity and checkpoint cadence that the plan did not authorize.

### Issue list

| ID | Severity | Location | Issue | Basis | Required repair | Next round must fix |
|---|---|---|---|---|---|---|
| `R1-B1` | blocker | `ai-work/planner/WP7-c-plan.md:156-158,297-299,357-358`; received C25 formal `run.json` files | The final formal C/D pair is spliced across different tracked project/code identities, violating the sealed fairness and resume contract. Public's preserved run has root `git_commit=a7c3c4da77b6cb6af387a74667e42d33bc9f7e6b` and completes on attempt 4 under `47c7fb2a55b91e471aeca5ededf6e0233f4f93f9`; Hidden has root `git_commit=47c7fb2a...` and completes on attempt 3 under `31b997279ff4e908165b93187fc898922a059de4`. | The plan requires completed formal C/D to share the same project context and explicitly says that after an identity-changing tracked repair, an old incomplete formal member cannot be combined with the other member under new code. The commit changes were substantive production changes: `47c7fb2a...` modifies GRPO/Piston/CLI retry behavior; `31b99727...` changes candidate-result overflow classification from retryable harness infrastructure failure to output-limit semantics. A `scientific_change=false` migration label cannot override the sealed plan or independently establish equivalence. | Produce the formal pair under one exact tracked code identity. With the repaired code chosen, run both C and D independently from the same formal B under that same identity (no cross-commit splice), then regenerate both 400-row bundles and repeat control-plane verification/aggregation so all downstream artifacts bind the repaired pair. If a different protocol is desired, it must be replanned before execution rather than retroactively accepted. | yes |
| `R1-M1` | major | `ai-work/planner/WP7-c-plan.md:130-142,334-343`; `configs/grpo/validation-pilot-public.yaml:12-25`; `configs/grpo/public.yaml:12-25`; `configs/grpo/hidden.yaml:12-25` | Pilot/formal checkpoint cadence was changed after plan seal: pilot `save_steps=50` → `10`, formal `save_steps=50` → `25`. | The plan calls pilot cadence fixed at 50, formal cadence 50 with other formal hyperparameters unchanged, and final acceptance requires the 20/100/300-step phases to be completed per spec without formal-hyperparameter changes. Reviewer-ex for validation stages forbids accepting an unplanned experimental-definition change merely because later evidence is green. | Restore the sealed cadence and rerun the affected real pilot/formal/downstream gates, or obtain a new sealed plan that explicitly authorizes the changed cadence before re-execution. Because `R1-B1` already requires a fresh single-code formal pair, the repair should resolve the cadence contract before spending that GPU budget. | yes |

### Additional observations

- No independent source-level defect was found in the current recovery implementation beyond the protocol/conformance issues above. Current GRPO log-boundary snapshots, recovery-history archival, structured Piston failure classification, fail-closed ambiguous-POST handling, payload boundaries, and paired data/B identity checks are defensive and are covered by passing tests.
- Formal telemetry is rich and internally consistent: both runs reached 300 steps with the expected 2400 completion/reward rows and 600 group rows, finite timing/reward/GPU metrics, completed adapters, and real downstream 400-row evaluation. These positives do not waive the sealed-pair identity requirement.
- The same scientific pair SHA across attempts is useful evidence that config/data/B/seed stayed stable, but it intentionally omits code commit; therefore it cannot be used as a substitute for the separate same-project-context acceptance criterion.

### Repair Routing

```yaml
repair_routing:
  version: 1
  required: true
  source_review_round: 1
  mode: single
  complexity: difficult_serial
  single_class: difficult_serial
  parallelizability: low
  multi_benefit: low
  independent_workstreams: 1
  repair_issue_ids:
    - R1-B1
    - R1-M1
  rationale:
    - "Both issues affect one tightly coupled C/D validation protocol: the cadence contract must be resolved before spending GPU time, then C and D must be produced under one exact repaired code identity before generation and control-plane verification can be repeated."
    - "The repair is inherently serial because paired fairness, one target RTX 4090, checkpoint provenance, generation, and verification each consume the immediately preceding authenticated artifacts; splitting into parallel lanes would increase pair drift risk rather than reduce work."
  workstream_candidates: []
```

### Conclusion

**NEEDS_REPAIR.** The implementation/tests and preserved portable-target evidence are technically strong and independently reproducible at the hash level, but the final formal experiment does not conform to the sealed WP7-c validation contract. `R1-B1` is a blocker because C/D were finalized across different tracked code identities despite an explicit no-splice rule. `R1-M1` is a major plan deviation because pilot/formal checkpoint cadence was changed after seal.

Next lifecycle operation: `$stage-lifecycle checkpoint_review`. Reviewer-ex stops here: do not commit, merge, finalize, update proceedings, or start repair execution from this review invocation.

## Review round 2

### Review Record

```yaml
review_record:
  version: 1
  stage_id: WP7-c
  review_round: 2
  source_execution_id: E1
  reviewed_head_commit: 7885d502077660d87ec48c17bd0e6db24c6fd1e2
  workflow_runtime_commit: c18925ae7b953e0f7022bb7c2a15c0a630258b83
  conclusion: pass
```

### Scope and provenance

- Reviewed the exact WP7-c worktree `/home/dzy/open-r1-code-verifier/.worktrees/wp7-c`, branch `feat/wp7-c`, at clean pre-review HEAD `7885d502077660d87ec48c17bd0e6db24c6fd1e2`; `git ls-files .ai-bridge` remained empty.
- The latest completed execution is `E1`, `task_kind=repair`, with `source_review_round=1`, `source_review_commit=deebfa0f02097a0593674aaa88d1f673427ab19e`, and `repair_issue_ids=[R1-B1,R1-M1]`. Git history shows that `7885d502...` is exactly the commit that appended E1, with parent `72e12971...`; therefore the execution report commit is the reviewed HEAD and there are no later commits or uncommitted changes.
- R1 is committed at `deebfa0f02097a0593674aaa88d1f673427ab19e`. Amendment A1 is committed at `72e12971a277f186663e102338096e14db55f6b1`, has SHA256 `aeb5f660af1662b961994276b10fa3f75b194d2b5c82b478915fa5e68bd7f3d5`, and is the latest committed validation amendment consumed by E1.
- A1 provenance is valid: its `source_plan_commit`, R1 round/commit, affected issue IDs, `post_hoc=true`, `user_authorized=true`, and `workflow_runtime_commit=c18925ae...` are internally consistent. Its `source_head_commit` is C28 commit `f6336c7f...`; Git shows A1 is the direct child of C28 and the A1 commit changes only `ai-work/planner/WP7-c-amendments.md`.
- The workflow-maintenance worktree is clean at exact runtime commit `c18925ae7b953e0f7022bb7c2a15c0a630258b83`; that commit is not an ancestor of the WP7-c stage HEAD, satisfying the independent maintenance-runtime requirement.
- C28 remains historical rather than passed: tracked script SHA256 recomputes to `ce55751b0c67800a18db4cc15fcebf6ace1d3a73455709641d50367ce811f749`, its recorded receive directory still does not exist, and no C28 target evidence is present. This is consistent with A1/E1 disposition `abandoned_unexecuted` and does not rewrite the checkpoint.
- This review applies the effective contract `sealed plan + A1`. PASS below is explicitly post-hoc operational-equivalence acceptance; it is not a claim that the original exact-code-identity or `save_steps=50` requirements were historically followed.

### Plan completion / amended acceptance disposition

| Item | Status | Independent evidence | issue_id |
|---|---|---|---|
| A1 amendment provenance / forbidden-waiver boundary | PASS | Direct C28→A1→E1 Git chain; amendment-only A1 commit; exact maintenance runtime; original plan/R1/C28 retained; no target failure reclassified as PASS | — |
| `R1-M1`: historical pilot/formal checkpoint cadence | RESOLVED UNDER A1 | C13 Public/Hidden are real completed 100-step runs with historical `save_steps=10`, 800 reward + 800 rollout + 200 group rows each; C25 Public/Hidden are completed 300-step runs with historical `save_steps=25`; current future-run configs are restored to 50. Other scientific fields remain paired/invariant except intended reward/data/run identity dimensions. | — |
| `R1-B1`: cross-commit formal C/D lineage | RESOLVED UNDER A1 | Preserved run metadata identifies every attempt/code transition and legal same-run resume points; canonical C/D streams are complete and clean; source recovery code fail-closes infrastructure batches before optimizer update and restores canonical streams to checkpoint boundaries; actual-path output-limit behavior is bounded as described below. | — |
| Formal C/D common scientific definition and reward isolation | PASS | Same completed B, seed 42, model/revision, dependency/Open-R1 identity and `paired_definition_sha256=31f5464a...`; Public uses visible tests and Hidden uses train-hidden tests; both reach global step 300. | — |
| Formal telemetry/authenticity | PASS | Both arms: 2400 rewards, 2400 rollouts, 600 groups, finite scanned numerics, no canonical infrastructure or sandbox rows, authenticated run/config/stream hashes, completed adapters/checkpoint inventories in C25 evidence. | — |
| C27 deterministic generation | PASS | Public/Hidden each rehash to 400 unique generation rows; dataset/order/formal-pair/model/B/Piston identities are bound by C27 evidence; strict readback remains 400 resumed / 0 generated. | — |
| Real control-plane Piston verification + aggregation | PASS | `/home/dzy/wp7c-verified` Public/Hidden each have 400 unique ordered results, zero sandbox/infrastructure rows, generation-to-verification order equality, matching result/summary hashes, and finite summary numerics. | — |
| Reviewer-owned lint/default/focused/GPU/Piston gates | PASS | Independent reruns listed below all pass. | — |
| Post-hoc disclosure requirement | PASS | A1 and E1 explicitly disclose retrospective operational-equivalence acceptance and preserve the original R1 nonconformance record. | — |

### Independent amendment-equivalence evidence

- **Historical cadence (`R1-M1`)**: C13 operator evidence/postcheck independently rehash to `91647fa09354f1dbaf486b7d94960934391467470665401022493ad5fb87d50b` / `91d4825b86a325a8f9765bfb9d99ab51345051c046c9847cfe335aadad487b2f`. Both pilot arms are `status=completed`, `global_step=100`, seed 42, paired SHA `bb8a733b...`, with historical `save_steps=10`. C25 resolved configs independently rehash to Public `01c33353...` / Hidden `8e65daa0...`; both preserve max_steps 300, seed 42, beta 0.01, LR 5e-6, cosine scheduler, warmup 0.05, grad accumulation 8, num_generations 4, LoRA 16/32/0.05, BF16 and generation limits while retaining historical `save_steps=25`. The accepted deviation is therefore checkpoint persistence cadence, not a rewritten claim of original-plan compliance.
- **Formal evidence authenticity (`R1-B1`)**: C25 tracked script SHA recomputes to `cb68ff0c5dfc852810c6e6aff620093f0dd1ea7f4d759e9c5902607126551fae`; received operator evidence/postcheck rehash to `0fe7f376fb94918f5e5aee1c28bcc0ac159687fefd9600509efb35773ca2df9e` / `c41e17a3a22b1e3c54de006c058165e32c0774c2d50581844194906c75b46a63`. Evidence records `command_rc=0`, `postcheck_rc=0`, `gate_status=passed`, RTX 4090 / 22683 MiB, expected roots/runtime/Piston identities and the complete formal inventory.
- **Attempt and resume lineage**: Public `run.json` rehashes to `5dcd27af...` and preserves attempts under `a7c3c4da...` followed by completed migration to `47c7fb2a...` from same-run checkpoint-175. Hidden `run.json` rehashes to `911044d6...` and preserves `47c7fb2a...` → failed `3675bf55...` → completed `31b99727...`, both later attempts resuming from same-run checkpoint-125. C25 postcheck records the corresponding recovery-history archives rather than rewriting failed suffixes.
- **No failed-batch optimizer contamination**: current production GRPO reward handling raises on any `infrastructure_failure=true` with the explicit fail-closed message `aborting before optimizer update`; cross-attempt recovery validates the same-run checkpoint, archives failed streaming suffixes/future checkpoints, then restores rollout/reward/group files exactly to the checkpoint boundary before trainer continuation. The focused independent suite covering this behavior passes 67/67.
- **Result-affecting output-limit path**: direct parsing of authenticated canonical C25 rewards shows Public has zero output-limit rows. For `leetcode-all-paths-from-source-to-target`, Public's four accepted completions are three `wrong_answer` plus one `runtime_error`, all non-infrastructure. Hidden has exactly one accepted `status=output_limit` row at canonical reward line 1005, with `infrastructure_failure=false`, `infrastructure_failure_kind=null`, `failure_counts.output_limit=2`, and the other three group items ordinary `wrong_answer`. Thus the changed classification is observed on Hidden while the Public canonical path does not exercise it.
- **Canonical stream integrity**: independently parsed C25 Public/Hidden streams each contain exactly 2400 reward rows, 2400 rollout rows and 600 group rows. No canonical reward row has `infrastructure_failure=true` or sandbox status, and numeric scanning of rewards/rollouts/groups/metrics found no NaN/Inf. Stream hashes exactly match C25 inventory/E1.
- **Generation binding**: C27 tracked script SHA recomputes to `e03bae85798260d2e5dfe4fb515bf7f703dc47f09deae57c67a3c8ac6f164926`; received operator evidence/postcheck/terminal rehash to `4e2912a5...` / `dc014c76...` / `e80c71e4...`. C27 binds formal checkpoint identities `628abb90...` / `1d661a8b...`, dataset `770b772c...`, ordered IDs `2d811d62...`, formal pair `31f5464a...`, model/revision/B/Piston/seed identities and 400/0 strict readback. Public/Hidden generation records independently rehash to `a5d841f6...` / `f84c2ab7...`, each exactly 400 unique rows.
- **Verification/aggregation binding**: `/home/dzy/wp7c-verified` Public results/summary/main CSV rehash to `7c5bb749...` / `6cc3fa7b...` / `c39c7573...`; Hidden to `004d5655...` / `f63a2018...` / `8da04392...`. Both result files contain 400 unique problem IDs with no sandbox/infrastructure row; Public/Hidden verification order is identical and exactly matches the corresponding C27 generation order; summary numerics are finite.

### Independent tests

- `make lint` → PASS: Ruff check/format and strict Mypy clean.
- `.venv/bin/python -m pytest -q tests/unit/training/test_grpo_resume_lineage.py tests/unit/training/test_grpo_transport_failure.py tests/unit/execution/test_harness.py tests/unit/execution/test_piston_resilience.py` → PASS: `67 passed`.
- `make test` → PASS: `1030 passed, 3 skipped`; skips are the expected environment-gated real-Piston cases exercised separately below.
- `make test-gpu` → PASS: `3 passed` on the GTX 1660 Ti control plane.
- `make test-piston PISTON_CONFIG=configs/execution/piston-local.yaml` → PASS: `9 passed, 2 deselected`, zero selected skips/failures.
- No target-GPU gate was rerun by this reviewer.

### Execution report claim verification

- E1 repair provenance, amendment binding, result-code/report commit shape, C28 disposition and exact workflow runtime: **VERIFIED**.
- E1 C13/C25 historical cadence statements and current restored `save_steps=50` configs: **VERIFIED**; acceptance is post-hoc under A1, not original-plan conformance.
- E1 C25 formal hashes, attempt lineage, canonical row counts, no canonical infra/sandbox contamination and actual-path output-limit asymmetry: **VERIFIED independently from synchronized bytes and current source/tests**.
- E1 C27 generation hashes/400-row identities and strict readback: **VERIFIED**.
- E1 `/home/dzy/wp7c-verified` result/aggregate hashes, 400-row uniqueness/order and zero sandbox/infrastructure rows: **VERIFIED**.
- E1 control-plane regression claims: **VERIFIED independently**.

### Previous-round issue verification

| issue_id | R1 severity | R2 status | Evidence |
|---|---|---|---|
| `R1-B1` | blocker | **RESOLVED UNDER A1** | Original same-exact-code requirement remains historically violated, but A1 validly supersedes only that acceptance rule. Preserved attempt/resume/canonical evidence satisfies the required code-migration/operational-equivalence checks, including no failed-batch optimizer contamination and bounded output-limit behavior. |
| `R1-M1` | major | **RESOLVED UNDER A1** | Historical pilot/formal cadence remains 10/25 and is explicitly disclosed. A1 reclassifies only persistence cadence; preserved paired configs/steps/seed/model/reward/optimizer-scheduler semantics support that replacement acceptance, while current future configs are restored to 50. |

### Issue list

No actionable blocker, major, minor, failed acceptance item, or independent-test failure remains for R2. No new repair issue ID is created.

### Repair Routing

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
    - "R1-B1 and R1-M1 are independently resolved under the committed post-hoc A1 replacement acceptance; no actionable R2 finding remains."
    - "All reviewer-owned control-plane gates and preserved evidence/hash/provenance checks passed, so no repair execution is required."
  workstream_candidates: []
```

### Conclusion

**PASS.** WP7-c at reviewed HEAD `7885d502077660d87ec48c17bd0e6db24c6fd1e2` satisfies the effective validation contract `sealed plan + committed amendment A1` and all unaffected real-training, isolation, safety, completed-step, artifact-authenticity, generation, real-Piston and aggregation requirements. This PASS is explicitly **post-hoc operational-equivalence acceptance**: the historical C/D artifacts do not strictly conform to the original whole-run exact-code-identity or `save_steps=50` requirements, and final reporting/proceedings must preserve that disclosure rather than describe the result as strictly preregistered/original-plan compliant.

Next lifecycle operation: `$stage-lifecycle checkpoint_review`. Reviewer-ex stops here: do not commit, merge, finalize, update proceedings, or start another execution from this review invocation.

## Finalization Record

```yaml
finalization_record:
  version: 1
  stage_id: WP7-c
  review_round: 2
  review_commit: d9c53c08798009128d502e94bb113dbea23aec4d
  merge_commit: 6ca8ba9de04303c32a027af439881afd96e9ae67
  finalized_at: "2026-08-30T10:19:08+02:00"
  status: finalized
```
