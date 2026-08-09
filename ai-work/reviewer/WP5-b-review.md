# WP5-b Reviewer Report

## R1 — completed E0 review

```yaml
review_record:
  version: 1
  stage_id: WP5-b
  review_round: 1
  source_execution_id: E0
  reviewed_head_commit: 4139f82e7798f1ed98901b289abd89c66d3075bc
  conclusion: needs_repair
```

### Provenance

- Sealed plan: `ai-work/planner/WP5-b-plan.md`, plan commit `c830b4acffd336fd5daf78945e7f6fcc004c002b`.
- Latest completed execution: `E0`, `task_kind=implementation`, `result_code_commit=e84266b`, source plan commit matches the sealed plan.
- The completed execution record is first contained by current stage HEAD `4139f82e7798f1ed98901b289abd89c66d3075bc` (`docs: complete WP5-b execution record`).
- Review started and finished with HEAD unchanged at that commit; tracked worktree was clean before review artifact creation.
- No prior `WP5-b` review record existed, so this is R1.

### Plan and acceptance review

| Area | Result | Reviewer evidence |
|---|---|---|
| Step 1: strict persisted record loader + derived-artifact resume guard | **needs repair** | Ordinary strict-row/resume tests pass, but the loader does not round-trip every UTF-8 record that the repository writer itself can emit; see `R1-M1`. |
| Step 2: deterministic problem-level bootstrap | pass | Implementation uses local `random.Random(seed)`, problem-index resampling, fixed linear percentile interpolation, finite input validation, and paired differences. Unit coverage passes. |
| Step 3: aggregate metrics / error statistics / problem-level CI | pass | Whole-problem pass@1 is separated from average test pass rate; executable/error-rate definitions match the sealed plan; public-eval-gap CI is paired. |
| Step 4: completed-run `summary.json` + one-row `main_results.csv` | pass for ordinary persisted rows | Strict run/record identity checks, finite JSON mapping, stable one-row CSV, atomic per-file replacement, and payload isolation are present. `R1-M1` can prevent aggregation when a valid persisted row contains a Unicode line-separator character. |
| Step 5: existing `evaluate` command aggregation | pass for ordinary persisted rows | Fresh Base run and zero-generation resume both produced results + summary + CSV. Aggregation errors remain sanitized through the CLI path. |
| Step 6: CPU/mock WP5-b integration regression | pass | Included in the default suite; four WP5-b integration tests pass. |
| Step 7: immutable Base config + documentation boundary | pass | `configs/eval/base.yaml` pins `Qwen/Qwen2.5-Coder-1.5B-Instruct` revision `2e1fd397ee46e1388853d2af2c993145b0f1098a`, CUDA, float16, deterministic pass@1; docs keep the four-problem result framed as an engineering gate. |
| Step 8: lint/default/Piston/GPU/Base gates | pass, subject to `R1-M1` | Independent lint/default/Piston/GPU checks pass. A fresh current-HEAD Base run from the immutable local cache reproduced the executor result and resumed with `generated=0`. |

### Independent verification

Reviewer commands were executed from the stage worktree. The worktree has no local `.venv`; therefore the already-installed primary-checkout environment was reused with `VENV=/home/dzy/open-r1-code-verifier/.venv`, and `PYTHONPATH=src` was set for runtime tests so imports resolve to this stage worktree rather than the primary checkout.

- `make lint VENV=/home/dzy/open-r1-code-verifier/.venv`: passed — Ruff check, Ruff format check, strict Mypy, 76 source files.
- `PYTHONPATH=src make test VENV=/home/dzy/open-r1-code-verifier/.venv`: `659 passed, 3 skipped`; all skips are the explicitly gated real-Piston tests.
- `PYTHONPATH=src make test-piston VENV=/home/dzy/open-r1-code-verifier/.venv PISTON_CONFIG=configs/execution/piston-local.yaml`: `9 passed, 0 skipped` (`2 deselected`).
- `PYTHONPATH=src make test-gpu VENV=/home/dzy/open-r1-code-verifier/.venv`: `3 passed` on the available CUDA environment.
- A normal-network fresh reviewer Base invocation encountered an external Hub `ConnectionError`. Repeating the same immutable revision with standard `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` forced use of the already-cached model and completed successfully: `4` problems, `resumed=0`, `generated=4`.
- Reviewer fresh run `outputs/evaluation/reviewer-r1-offline` exactly reproduced the original Base records after excluding only `run_id`, `runtime_ms`, and `generation_latency_ms`: both normalized record sets hash to `03f4168f04155bca9d2a66bed919aa6f5d41004f687e075a862c405165f755b0`; main correctness metrics are identical.
- The reviewer run reports parse/target/executable `1.0`, visible/train-hidden/eval-hidden pass@1 `0.5`, eval-hidden average test pass rate `0.5`, public-eval gap `0.0`, and error categories `passed=2`, `runtime_error=2`.
- Same-run reviewer resume succeeded with `resumed=4`, `generated=0`. Derived files remained byte-stable across resume: `summary.json` SHA-256 `b0d2cb009828f8dd2385ea6cbe5ef2acba473e603353ca1f4263513556d540ae`; `main_results.csv` SHA-256 `c07e05c4715be5b71198b0c0646e5c34913b2192d4044ba0e5266c28e6f44347`.
- Derived-artifact inspection found no completion/code/test/reference-solution/stdout/stderr payload copied into the summary or CSV.

### Findings

#### R1-M1 — JSONL loader breaks valid UTF-8 records containing Unicode line separators

**Severity:** major  
**Actionable:** yes

`append_evaluation_record()` serializes records using `json.dumps(..., ensure_ascii=False)` and therefore may persist legal Unicode characters such as U+2028 LINE SEPARATOR or U+2029 PARAGRAPH SEPARATOR directly inside JSON string values such as `completion` or `extracted_code`. `load_evaluation_records()` then reads the entire file and calls `str.splitlines()`. Python `splitlines()` treats U+2028/U+2029 (and other Unicode line-boundary characters) as record separators even though the JSONL format here is delimited by physical LF (`\n`) written by `_append_jsonl()`.

A reviewer probe used an existing strict Base `EvaluationRecord`, replaced only its completion with `before<U+2028>after`, wrote it through the repository's own `append_evaluation_record()`, and immediately loaded it through `load_evaluation_records()`. The writer produced one LF-terminated JSON object, but the loader split the JSON string at U+2028 and failed with:

`EvaluationError: results JSONL row 1 is invalid: StrictJsonError`

This is not merely a malformed-input case: it is a writer/reader round-trip failure for a valid UTF-8 model completion accepted by the `EvaluationRecord` contract. In a real evaluation, such a completion can be durably appended, after which end-of-run aggregation (`aggregate_evaluation_run()`) and future exact-prefix resume both become impossible. That violates sealed-plan Step 1's strict-row round-trip requirement and WP5's resumability/aggregation acceptance.

**Required repair:** make `load_evaluation_records()` split only on the repository's actual JSONL delimiter LF, while continuing to reject genuine blank LF-delimited rows and invalid/truncated JSON. Add regression coverage proving repository-written strict records containing at least U+2028 and U+2029 round-trip successfully without weakening duplicate-key/unknown-field/UTF-8 guards.

### Conclusion

The statistical definitions, aggregation outputs, immutable Base configuration, real Piston/GPU gates, formal Base correctness result, deterministic rerun, payload isolation, and zero-generation resume are independently supported by reviewer evidence. However, `R1-M1` is a core persisted-record/resume contract defect and is actionable; under the reviewer-ex acceptance rules this round cannot PASS until it is repaired and a new completed repair execution is reviewed.

```yaml
repair_routing:
  version: 1
  required: true
  source_review_round: 1
  mode: single
  complexity: very_simple
  single_class: very_simple
  parallelizability: low
  multi_benefit: low
  independent_workstreams: 1
  repair_issue_ids:
    - R1-M1
  rationale:
    - "The only required repair is localized to strict JSONL record splitting/round-trip behavior plus focused regression coverage; it does not require changes to metrics, bootstrap, Base configuration, executor semantics, or model evaluation logic."
    - "One executor can safely repair and retest this single contract without coordination overhead; parallel repair lanes would add no useful benefit."
  workstream_candidates: []
```

### Required next lifecycle action

Run `$stage-lifecycle checkpoint_review` to provenance-check and commit this R1 review. After that checkpoint, run `$execution-router` for the `R1-M1` repair. Do not finalize WP5-b from this review round.

## R2 — completed E1 repair review

```yaml
review_record:
  version: 1
  stage_id: WP5-b
  review_round: 2
  source_execution_id: E1
  reviewed_head_commit: 82acf24ba0d00a74cb1d43393c02645d763bd02a
  conclusion: pass
```

### Provenance

- R1 review was checkpointed at `14f365a217782a5a2b5245a568cc87b55a3406fe` with `conclusion=needs_repair` and sole repair issue `R1-M1`.
- Latest completed execution is `E1`, `task_kind=repair`, `source_review_round=1`, `source_review_commit=14f365a217782a5a2b5245a568cc87b55a3406fe`, `repair_issue_ids=[R1-M1]`, and `result_code_commit=30964b2c6af9bf0dbc8b76f59e99b2ca8ba0b218`.
- The E1 execution record is contained by current stage HEAD `82acf24ba0d00a74cb1d43393c02645d763bd02a` (`docs(executor): record WP5-b repair`).
- Review started and finished with HEAD unchanged at that commit; tracked worktree was clean before this R2 artifact append.

### R1 issue closure

#### R1-M1 — resolved

`load_evaluation_records()` now splits persisted JSONL only on the repository's physical LF delimiter (`"\n"`) instead of `str.splitlines()`. It removes only the synthetic final empty fragment produced by a terminal LF; empty files remain valid, while genuine blank LF-delimited rows still reach the existing strict rejection path.

The added regression `test_load_evaluation_records_round_trips_writer_unicode_line_separators` writes a strict record through `append_evaluation_record()` containing both U+2028 LINE SEPARATOR and U+2029 PARAGRAPH SEPARATOR, confirms the raw UTF-8 bytes are persisted, and verifies exact loader round-trip. Existing invalid JSON, duplicate-key, unknown-field, invalid UTF-8, finite-value, and blank-row guards remain covered.

Reviewer independently replayed the original failure mode against current HEAD: writer→loader round-trip with `before<U+2028>middle<U+2029>after` succeeded, while a physical blank LF row was still rejected with `EvaluationError`.

### Independent verification

Reviewer commands were executed from the WP5-b stage worktree. As in R1, the primary checkout's installed virtual environment was reused while `PYTHONPATH=src` forced imports to resolve to the stage worktree source.

- Affected strict-record/resume suite: `34 passed`.
- `make lint VENV=/home/dzy/open-r1-code-verifier/.venv`: Ruff check/format and strict Mypy passed for 76 files.
- `PYTHONPATH=src make test VENV=/home/dzy/open-r1-code-verifier/.venv`: `660 passed, 3 skipped`; all three skips are the explicitly gated real-Piston cases.
- `PYTHONPATH=src make test-piston VENV=/home/dzy/open-r1-code-verifier/.venv PISTON_CONFIG=configs/execution/piston-local.yaml`: `9 passed`, `0 skipped` (`2 deselected`).
- `PYTHONPATH=src make test-gpu VENV=/home/dzy/open-r1-code-verifier/.venv`: `3 passed`.
- Current-HEAD formal Base reviewer run using the already-cached immutable model (`HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`) completed 4 problems with `resumed=0`, `generated=4`.
- Re-running the same reviewer run produced `resumed=4`, `generated=0`, confirming no-op resume after the repair.
- Comparing `base-main-r1-repair` with `reviewer-r2-offline` while excluding only `run_id`, `runtime_ms`, and `generation_latency_ms` produced identical ordered normalized records. Under the reviewer's canonical sorted compact JSON encoding, both normalized sets hash to `03f4168f04155bca9d2a66bed919aa6f5d41004f687e075a862c405165f755b0`.
- Core metrics matched: parse/target/executable rates `1.0`; visible/train-hidden/eval-hidden pass@1 `0.5`; eval-hidden average test pass rate `0.5`; public-eval gap `0.0`.
- Full regression coverage, including WP5-b summary/CSV payload-isolation checks, passed after the repair.

### Findings

No new blocker, major, minor, or other actionable findings were identified. `R1-M1` is closed.

### Conclusion

E1 fixes the only R1 defect without weakening the strict persisted-record guards or changing the statistical, Base configuration, execution, or payload-isolation contracts. All required independent tests and the current-HEAD Base/resume acceptance pass. WP5-b therefore passes R2 for reviewed HEAD `82acf24ba0d00a74cb1d43393c02645d763bd02a`.

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
    - "R1-M1 is resolved and no new actionable findings remain; no repair execution is required after R2."
  workstream_candidates: []
```

### Required next lifecycle action

Run `$stage-lifecycle checkpoint_review` to provenance-check and commit this R2 PASS review. After that checkpoint succeeds, run `$stage-lifecycle finalize` for WP5-b. Do not run `$execution-router` again unless the review becomes stale or new code changes are introduced.
