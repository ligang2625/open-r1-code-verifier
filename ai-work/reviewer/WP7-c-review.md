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
