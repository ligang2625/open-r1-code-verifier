# WP6-d Review

## R1 — latest completed E0 implementation

```yaml
review_record:
  version: 1
  stage_id: WP6-d
  review_round: 1
  source_execution_id: E0
  reviewed_head_commit: 9a56c35663b97ca04781e38699155f0ebd94bf92
  conclusion: needs_repair
```

### Provenance and evidence boundary

- Sealed plan: `ai-work/planner/WP6-d-plan.md`, source plan commit `eb523bc749e9aa4362790c45bbcf4d604ad7e478`.
- Latest completed execution: `E0`, `task_kind=implementation`, `result_code_commit=c24728249f14a7952d98050210662b506c720884`, execution-report commit / reviewed HEAD `9a56c35663b97ca04781e38699155f0ebd94bf92`.
- Stage profile: `validation`; evidence class: `real-training/numerical`; target hardware: 24GB GPU; `development_terminal=false`.
- Review workspace is `/home/dzy/open-r1-code-verifier-wp6d-verify/.worktrees/wp6-d` on `feat/wp6-d`. It was clean before review, `.ai-bridge` has zero tracked paths, and HEAD remained `9a56c35663b97ca04781e38699155f0ebd94bf92` through all reviewer-owned verification before this review artifact was written.
- Expensive formal SFT / 400-completion generation was not rerun. The review independently checked persisted operator/artifact provenance and only reran short lint/test/GPU/Piston/readback/aggregation gates.

### Independent verification

- `make lint`: PASS. Ruff check/format and strict Mypy all passed.
- `make test`: PASS: `910 passed, 3 skipped, 0 failed`; the three skips are the explicit real-Piston opt-in cases.
- Reviewer-owned GPU smoke: `.venv/bin/python -m pytest -m gpu tests/integration/test_wp5a_gpu_smoke.py -ra`: PASS `3/3`.
- Real local Piston acceptance against `configs/execution/piston-local.yaml`: PASS `9/9`, `0 skipped`, `0 failed` (`2` non-Piston cases deselected).
- `/home/dzy/wp6d-b-export/MANIFEST.sha256` was independently rehashed: `148` entries, `0` missing, `0` mismatches, `239,749,291` bytes, matching E0.
- Existing formal SFT backup strictly loads with `load_completed_sft_checkpoint()` as `B-sft-formal-seed42`, exact Qwen2.5-Coder-1.5B revision `2e1fd397ee46e1388853d2af2c993145b0f1098a`, seed `42`. `load_training_curve_rows(..., method="SFT")` returns `2549` rows and `build_cost_row()` reproduces `0.5215871774233367` RTX 4090 GPU-hours.
- Base A and final B both strictly load through project `_load_evaluation_run()`: each contains `400` completed unique records; problem order is identical; dataset hash, seed, split, device, deterministic generation definition and persisted Piston SHA are identical.
- The transferred generation bundle and final B rows were compared record-by-record. All `400` preserve the same `problem_id`, `prompt_hash`, `completion`, `completion_tokens`, `generation_latency_ms` and `hit_max_new_tokens`.
- Final B aggregation was recomputed in memory from the persisted `results.jsonl` with the saved bootstrap definition (`seed=42`, `10000` resamples, `95%`). Recomputed metrics and confidence intervals exactly equal the saved `summary.json`: visible Pass@1 `0.3525`, train-hidden Pass@1 `0.335`, eval-hidden Pass@1 `0.3775`, eval-hidden CI `[0.33, 0.425]`, public/eval gap `-0.025` modulo floating representation.

### Code / plan coverage

| Area | Result | Review evidence |
|---|---|---|
| Durable finalized-worktree evaluation identity | PASS | Persisted `piston_config_sha256` is used for historical strict hash/readback while active evaluation still requires the live Piston config; real Base A strict-load succeeds without its old worktree. |
| Formal SFT data/model/config binding | PASS | Formal SFT evidence binds 2500/300 data through the manifest, exact model/revision, seed and max length; manifest validation checks dataset/record hashes, model identity, token bounds and Piston definition. |
| Real SFT checkpoint / telemetry / cost | PASS | Real completed adapter, numeric checkpoints and finite analysis-ready curve/cost evidence remain available in the SHA-verified export. |
| Generation / verification decoupling semantics | PASS | The staged implementation binds model/revision/checkpoint/seed/dataset/order/decode/Piston definition and preserves exact generated payload into the canonical evaluation records; unit/full regressions pass. |
| Final B numerical evidence and A/B pairing | PASS | Strict loaders and independent re-aggregation reproduce the saved 400-row B result and its shared Base A evaluation contract. |
| Scope / leakage boundary | PASS | No C/D work was entered; generation bundle stores model outputs but verification remains the phase that consumes the three test layers; non-sample artifact claims are consistent with the tested schema. |
| Formal B operator-terminal provenance | **FAIL — R1-M1** | The sealed plan requires the complete formal B evaluation long gate to be operator-terminal. After C3 was interrupted, C4 operator evidence covers generation only; the subsequent 400-row Piston verification/aggregation completed during the C5→E0 resume without a new immutable operator checkpoint/script/status/log record. |

### Actionable findings

#### R1-M1 — Major — The final 400-problem B verification is missing the sealed operator-terminal checkpoint provenance

The persisted B artifacts are internally consistent and their numerical result is independently reproducible from the saved rows, so this is not a finding that B's scores are wrong. The defect is the control-plane/provenance contract for the formal long gate.

The sealed WP6-d plan defines `sft-b-evaluation` as an `operator_terminal_execution` gate and requires the formal B full evaluation to be run by the operator from an immutable, SHA-bound script with checkpoint identity, atomic status and append-only terminal log. The project specification likewise places formal Base/B/C/D full evaluations and other long Piston/GPU gates behind the operator-terminal checkpoint protocol.

The execution changed the evaluation architecture after C3 was interrupted. C4 correctly preserved the 156-row failed attempt and introduced `generate-eval -> verify-eval -> aggregate-eval`, but C4's own report and operator evidence explicitly cover only the 4090 generation command. The exported `sft-b-evaluation` operator namespace contains only `C3` and `C4`; C4 has the successful status/log for generation. E0 then reports that the transferred bundle was verified `400/400` on the 1660 Ti and aggregated, but does not identify a subsequent operator checkpoint, immutable verification script SHA, status file or terminal log for that formal 400-problem Piston operation.

That means the reviewer can establish **artifact correctness** from hashes/strict loaders, but cannot establish **plan-compliant execution provenance** for the second half of the formal B long gate. Reviewer-ex cannot silently relax the sealed operator boundary merely because the GPU-heavy generation was already finished or because the final rows look valid.

Required repair:

1. Preserve the current SHA-verified generation bundle, formal SFT artifacts, Base A, C3 quarantine and final B directory; do not regenerate model completions and do not overwrite/delete historical evidence.
2. Restore plan-compliant operator provenance for the formal verification half of `sft-b-evaluation`. Prefer binding any already-existing durable verification command/log evidence if it can be independently authenticated. If such evidence does not exist, create a new immutable operator-owned verification checkpoint on the 1660 Ti that consumes the frozen generation bundle and exact code/data/Piston identity. Rerun **only** the Piston verification if that is required to obtain genuine operator evidence; never rerun 4090 generation/SFT for this finding.
3. The checkpoint must bind the exact generation records SHA, evaluation contract, verifier project/Open-R1/dependency identity, Piston definition, formal dataset identity and target B namespace, and must persist the same status/log/script-SHA semantics required by the sealed operator protocol.
4. After the operator gate, independently prove 400 unique canonical rows, exact generated-payload preservation, exact-prefix `resumed=400/verified=0`, deterministic aggregate equality, Base A/B shared contract, and the final B manifest/hash identity. Preserve any superseded B directory in quarantine rather than deleting or overwriting it if a fresh verification output is required.
5. Append a repair execution record that makes the resulting operator checkpoint and final artifact provenance reviewer-auditable. Do not enter C/D work.

### Execution-report verification

The E0 report is materially accurate on the real data/model/checkpoint, export manifest, SFT telemetry/cost, final B rows, numerical aggregates, A/B identity, lint/default/GPU/Piston regression results and the absence of C/D work; these claims were independently reproduced from persisted artifacts and current code. The unresolved mismatch is limited to the missing operator-terminal provenance for the formal 400-row verification/aggregation segment after the staged architecture change.

### Conclusion

`needs_repair`. The scientific/numerical B evidence is currently consistent and no rerun of formal SFT or 4090 generation is justified by this review. `R1-M1` nevertheless blocks PASS because the completed E0 does not satisfy the sealed operator-control requirement for the full formal B evaluation gate.

```yaml
repair_routing:
  version: 1
  required: true
  source_review_round: 1
  mode: single
  complexity: normal
  single_class: normal
  parallelizability: low
  multi_benefit: low
  independent_workstreams: 1
  repair_issue_ids:
    - R1-M1
  rationale:
    - "The only required repair is one tightly coupled operator-provenance correction for the already-frozen B verification evidence; the real SFT, generation bundle, numerical result, and code regressions independently passed review."
    - "The repair must coordinate one immutable verification checkpoint with the exact generation/data/code/Piston/final-artifact identity, so splitting it into parallel workstreams would create provenance risk without independent implementation benefit."
  workstream_candidates: []
```

### Next lifecycle step

Run `$stage-lifecycle checkpoint_review` to commit this R1 review. After checkpointing, run `$execution-router` for the single `R1-M1` repair. Once a new completed repair execution is appended, invoke `reviewer-ex` again in a fresh Web conversation/context.

## R2 — latest completed E1 repair

```yaml
review_record:
  version: 1
  stage_id: WP6-d
  review_round: 2
  source_execution_id: E1
  reviewed_head_commit: 60bf54a23f78bde1fe43a462a23efd4d7934c3b4
  conclusion: pass
```

### Provenance and review boundary

- Latest completed execution is `E1`, `task_kind=repair`, submitted by execution-report commit / reviewed HEAD `60bf54a23f78bde1fe43a462a23efd4d7934c3b4`.
- E1 correctly binds the sealed plan commit `eb523bc749e9aa4362790c45bbcf4d604ad7e478`, previous committed review round `1` at `6f80d545374809693d8a47defe791ee1f881489e`, and the sole repair issue `R1-M1`.
- The stage worktree was clean before review, `.ai-bridge` has no tracked paths, and HEAD remained `60bf54a23f78bde1fe43a462a23efd4d7934c3b4` through reviewer-owned verification before this R2 artifact was appended.
- This is a validation stage. Reviewer did not rerun formal SFT, 4090 generation, or the 400-row Piston operator command; only persisted operator provenance and short readback/regression gates were independently checked.

### Independent verification

- `make lint`: PASS; Ruff check/format and strict Mypy all passed.
- `make test`: PASS `910 passed, 3 skipped, 0 failed`; the three skips are the expected real-Piston opt-in cases.
- `make test-gpu`: PASS `3/3`.
- Real `make test-piston`: PASS `9/9`, `0 skipped`, `0 failed` (`2` deselected).
- C8 tracked operator script SHA256 is `0aade6967bf863da9afabd224eb286314fa86fde1c4254165e1e26010fab7ddd`, matching the checkpoint/evidence binding. Persisted operator evidence SHA256 independently recomputes to `612f02274000881206769a7b92d48a7e8ba85ea4fb338cf89529765f9956317a`; status is `0`; evidence records checkpoint commit `ebf7b0d63c3c56231dc3c68a7e922cd9902c5c54`, workflow runtime `734549fe3282edad76456c69f085e53d9ce39844`, `command_rc=0`, `postcheck_rc=0`, and `gate_status=passed`.
- The append-only C8 terminal log records the actual operator attempt running `verify-eval` over the frozen 400-row generation bundle, producing `resumed=0, verified=400`, followed by a successful strict semantic postcheck and terminal gate completion.
- Reviewer independently reran the exact-prefix C8 verification readback from the frozen verifier checkout; it returned `resumed=400, verified=0`, so no Piston problem row was re-executed.
- Project strict loaders accept both canonical B and fresh C8 B as completed 400-row runs with 400 unique problem IDs in identical order and matching dataset hash, seed, model/revision, persisted Piston definition, generation records SHA, and generation contract SHA.
- Reviewer independently compared all 400 canonical/C8 result rows after excluding only the documented attempt-local `runtime_ms` and path-derived `config_hash`; normalized semantic SHA256 is identical (`ecc946b8a39e939721e02cf7b8da41c1f537e43ef7f5ad503c2a3934ebdf985`) and every normalized row is equal.
- Canonical and C8 aggregate summaries differ only in path-derived `config_hash` and fresh `mean_execution_runtime_ms`; deterministic correctness/status/error/bootstrap/token/generation metrics are unchanged. This is consistent with R1's already independently accepted canonical B scientific evidence.

### R1-M1 resolution

`R1-M1` is resolved. The missing formal verification control-plane provenance now exists as a genuine new operator-owned C8 attempt rather than retrospective synthesis: the frozen generation/data/verifier/Open-R1/dependency/Piston identities are bound before execution; the script is immutable and SHA-bound; status/log/evidence capture the real command and postcheck outcome; the repair writes a fresh namespace without overwriting canonical B; and short reviewer-owned readback proves exact-prefix completion and semantic equality with the previously accepted canonical B result.

The earlier C6/C7 failed attempts remain preserved as audit history and do not weaken C8: C6 failed before verification because of the dependency-lock preflight bug, C7 failed before output creation because of cwd-sensitive config resolution, and C8 superseded those scripts without rewriting their evidence.

### Findings and conclusion

No blocker, major, minor, or actionable issue remains for E1. R1's scientific/numerical acceptance remains valid, and the sole missing operator-terminal verification provenance has been repaired with independently auditable evidence. Conclusion: `pass`.

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
    - "R1-M1 is resolved by the genuine C8 operator verification evidence and independent exact-prefix/semantic/aggregate readback; no further executor action is required."
  workstream_candidates: []
```

### Next lifecycle step

Run `$stage-lifecycle checkpoint_review` to commit this R2 PASS review. If the lifecycle stale/provenance checks pass, run `$stage-lifecycle finalize` for WP6-d.

## Finalization Record

```yaml
finalization_record:
  version: 1
  stage_id: WP6-d
  review_round: 2
  review_commit: 6c0dbb337f990c709342db254d1dca24a4e7e03d
  merge_commit: 5741ccd8432f530edc9edcca914ebba5339dc800
  finalized_at: "2026-08-20T15:15:37+08:00"
  status: finalized
```
