# WP7-c Validation Protocol Amendments

The original sealed plan at `ai-work/planner/WP7-c-plan.md` remains immutable. This file is append-only and records user-authorized protocol changes that supplement, rather than rewrite, that sealed history.

## A1 — accept preserved C/D formal evidence under operational-equivalence criteria

The user explicitly chose not to rerun the RTX 4090 C/D training solely to reproduce the original checkpoint-save cadence or a single exact Git identity. This amendment is deliberately post-hoc: the formal results and review round 1 were already observed. It therefore does **not** claim that the original sealed protocol was followed exactly. It replaces only the two review-round-1 conformance requirements listed below with stricter preserved-evidence equivalence checks, while all real-training, isolation, safety, data, model, reward, completed-step, and artifact-authenticity requirements remain in force.

```yaml
plan_amendment_record:
  version: 1
  amendment_id: A1
  stage_id: WP7-c
  source_plan_commit: 8464e69691c527c726a2e28e5a7ca81fa2001bbf
  source_review_round: 1
  source_review_commit: deebfa0f02097a0593674aaa88d1f673427ab19e
  source_head_commit: f6336c7fa22c74a94955ea529f5333a89bc1d8ee
  workflow_runtime_commit: c18925ae7b953e0f7022bb7c2a15c0a630258b83
  amendment_kind: validation_protocol
  post_hoc: true
  user_authorized: true
  affected_issue_ids: [R1-B1, R1-M1]
  superseded_requirements:
    - "R1-B1/original-plan strictness that the accepted final C and D formal runs must have one identical exact tracked project/code identity across their full training lineage, with any identity-changing operational repair forcing both arms to be rerun fresh."
    - "R1-M1/original-plan treatment of pilot save_steps=50 and formal save_steps=50 as acceptance-critical cadence whose historical deviations (pilot 10, formal 25) require rerunning otherwise completed real training."
    - "The C28 repair path that would rerun a fresh paired 100-step pilot, then fresh 300-step C/D, regenerate both evaluation bundles, and repeat control-plane verification solely to restore those two strict conformance properties."
  replacement_acceptance:
    - "Accept cross-commit formal C/D only if preserved attempt/checkpoint evidence proves one unchanged scientific definition (model/revision, formal data, parent B, seed, LoRA, optimizer, scheduler, max_steps, reward formula/source and paired definition) and every code transition is attributable."
    - "A result-affecting operational/runtime repair may cross a Git identity boundary only when the failed or infrastructure-affected reward batch did not enter optimizer update, resume starts from a validated same-run trainer checkpoint with canonical telemetry boundaries restored, and failed suffix/history remains archived rather than rewritten."
    - "For a repair whose behavior differs between commits, the accepted evidence must show that the other arm did not exercise the changed behavior or otherwise establish observational equivalence from preserved execution telemetry."
    - "Treat checkpoint save_steps as operational persistence/recovery cadence rather than a scientific hyperparameter for the already-completed historical pilot/formal runs, provided optimizer/scheduler/update count, data-order semantics, seed, model/reward definition and completed step count are unchanged. Current tracked configs may remain restored to save_steps=50 for future runs without retroactively rerunning old data."
    - "Reuse the already-authenticated C25 completed formal C/D artifacts and C27 400-row generation bundles plus E0 real-Piston verification/aggregation only after independent hash/provenance revalidation under this amendment."
  required_equivalence_evidence:
    - "Formal C and D remain independent descendants of the same completed B-sft-formal-seed42 and bind the same formal data, seed 42, model/revision, LoRA, optimizer, scheduler, max_steps=300, reward definitions, Piston scientific definition, dependency/Open-R1 context and paired_definition_sha256=31f5464abf094d14cf86e8ef4dd909b8a1be559c8b4ca8b96473070a9f1daad9, except the explicitly amended save_steps cadence."
    - "Public and Hidden run/attempt provenance identifies every training code transition. Public's historical origin/repair lineage and Hidden's later repair lineage must remain preserved; no migration label alone is sufficient without actual-path evidence."
    - "Any transport/harness infrastructure failure that caused a repair/recovery occurred before optimizer update for its affected reward batch; production resume selected a valid same-run trainer checkpoint and restored canonical rollout/reward/group boundaries while archiving failed suffix/history."
    - "The C25 candidate-result overflow classification change is shown not to affect the accepted Public canonical path, while Hidden's previously fatal oversized candidate is represented after repair as ordinary non-infrastructure output_limit rather than a retryable infrastructure failure."
    - "Both accepted formal runs are status completed at global_step=300 with 2400 rollout rows, 2400 reward rows, 600 group rows, finite required telemetry, strict-loadable final adapters, no canonical infrastructure_failure/sandbox_error reward rows, and correct public-vs-hidden reward source isolation."
    - "Historical save_steps differences changed only checkpoint persistence cadence: there is no evidence of changed optimizer/scheduler mathematics, update count, data-order semantics, seed, model/reward definition or max_steps; final completed step is 300 for both formal arms."
    - "The C27 generation evidence and both 400-row bundles rehash to the E0 authenticated identities, including evaluation dataset/order, formal-pair, Piston, checkpoint, model, dependency and project provenance; strict readback remains 400 resumed / 0 generated."
    - "Existing GTX 1660 Ti real-Piston verify-eval and aggregate-eval artifacts rehash to the E0 recorded Public/Hidden 400-row result and summary identities, with zero sandbox/infrastructure rows and finite aggregates."
  forbidden_waivers:
    - "No synthetic/mock/fake artifact may satisfy a formal gate."
    - "No hidden-data leakage, reward-source mixing, sandbox/safety failure, missing real execution, missing completed steps, or artifact-authenticity failure may be waived."
    - "No failed reward batch that entered optimizer update may be silently accepted under operational equivalence."
    - "No missing telemetry, checkpoint, generation/evaluation row, hash, or provenance may be invented or inferred from prose alone."
    - "Historical plan/review/execution/operator evidence must remain immutable; amendment A1 cannot rewrite the old record or claim original strict conformance."
  operator_checkpoint_disposition:
    checkpoint_id: C28
    checkpoint_commit: f6336c7fa22c74a94955ea529f5333a89bc1d8ee
    operator_gate_id: grpo-cd-pilot
    operator_script: ai-work/executor/operator/WP7-c/grpo-cd-pilot/C28/run.sh
    operator_script_sha256: ce55751b0c67800a18db4cc15fcebf6ace1d3a73455709641d50367ce811f749
    status: abandoned_unexecuted
    operator_execution_observed: false
    control_plane_evidence_receive_dir: /home/dzy/wp7c-operator-evidence/WP7-c/grpo-cd-pilot/C28
    control_plane_evidence_receive_dir_existed_at_amendment: false
  reporting_disclosure: "WP7-c formal C/D are accepted, if the A1 equivalence audit passes, under a post-hoc protocol amendment. They do not strictly conform to the original same-exact-code-identity and save_steps=50 requirements; any final claim must describe this as retrospective validation under evidence-based operational equivalence rather than strict original-plan/preregistered conformance."
```

### A1 interpretation notes

- `save_steps` is not being rewritten to 50 in historical evidence. The observed pilot/formal cadence remains part of the audit record; A1 only changes whether that operational cadence deviation invalidates otherwise completed training.
- A1 does not assert that different Git commits are automatically equivalent. The next repair execution must prove the actual code-migration path against the preserved formal telemetry, checkpoint/recovery history, and downstream hashes.
- C28 remains an immutable historical operator checkpoint. It was not executed and is not considered passed; A1 supersedes the need to execute it.
- A1 does not itself close R1-B1/R1-M1. A new completed repair execution must perform the equivalence audit, after which a fresh independent reviewer must decide whether the amended acceptance is satisfied.
