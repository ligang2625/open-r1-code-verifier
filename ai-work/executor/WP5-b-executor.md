# WP5-b Executor Report

## E0 implementation attempt — blocked

- `stage_id`: `WP5-b`
- `task_kind`: `implementation`
- `source_plan_commit`: `c830b4acffd336fd5daf78945e7f6fcc004c002b`
- attempted code HEAD: `e84266b`
- status: **blocked; no completed E0 execution record was written**

### Implemented plan steps

1. Added strict persisted `EvaluationRecord` loading and completed-run derived-artifact resume guards.
2. Added deterministic standard-library problem-level and paired bootstrap intervals.
3. Added record-only WP5 metrics, error/status counts, and problem-level confidence intervals.
4. Added completed-run `summary.json` and one-row `main_results.csv` atomic aggregation.
5. Integrated aggregation into the existing `evaluate` command, including no-op resume reaggregation.
6. Added a CPU/mock WP5-b end-to-end aggregation regression.
7. Added formal Base config with Hub-resolved immutable revision
   `2e1fd397ee46e1388853d2af2c993145b0f1098a` and updated the WP5 documentation boundary.

Code/test commits, in order:

- `69c5f83` — `feat: extend evaluation resume artifacts`
- `947e88b` — `feat: add deterministic bootstrap intervals`
- `6eaa38a` — `feat: aggregate evaluation metrics`
- `22645a9` — `feat: write evaluation summary artifacts`
- `06d4e8b` — `feat: aggregate completed evaluation runs`
- `9c3dcf7` — `test: cover WP5-b metrics pipeline`
- `e84266b` — `feat: add immutable Base evaluation config`

### Verification evidence

- WP5-a strict records/resume: `32 passed`.
- Bootstrap unit tests: `16 passed`.
- Bootstrap + metrics unit tests: `30 passed`.
- Metrics/run aggregation unit tests: `19 passed`.
- CLI unit tests: `43 passed`; `code-verifier evaluate --help` returned 0.
- WP5-b integration tests: `4 passed`.
- `make lint`: Ruff check, Ruff format check, and strict Mypy passed for 76 files.
- `make test`: `659 passed, 3 skipped`; the three skips are the expected explicitly gated real-Piston tests.
- `make test-gpu`: `3 passed, 0 skipped` on NVIDIA GeForce GTX 1660 Ti, CUDA 12.4.
- Git scope audit: no changes to the sealed plan, reviewer artifacts, `proceedings.md`, or
  `third_party/open-r1/**`.

### Blocking acceptance evidence

`make test-piston PISTON_CONFIG=configs/execution/piston-local.yaml` could not connect to
`http://127.0.0.1:2000`: all seven WP3-b fixtures errored with `PistonTransportError: piston transport failed`,
and both WP3-c real-Piston tests failed for the same unavailable runtime (`2 failed, 7 errors, 0 skipped`).

No process is listening on loopback port 2000. Docker and Podman are not installed, so the repository's documented
pinned privileged Piston container cannot be started in this environment. Consequently the mandatory real 1.5B Base
run, same-run no-op resume, and independent deterministic rerun were not attempted because the CLI validates Piston
before loading/generating with the model.

The plan requires all of those gates before `status: completed`. This report therefore deliberately omits the
structured completed E0 `execution_record`; no Base metrics or successful completion status are fabricated.

## E0 acceptance continuation — completed

The prior external blockers were resolved without changing implementation code: Docker became available, the pinned
Piston container/runtime was restored, and the immutable Base model snapshot was fully cached. The same E0 then
completed all remaining sealed-plan gates.

### Completed acceptance evidence

- Piston identity: pinned image
  `ghcr.io/engineer-man/piston@sha256:2f66b7456189c4d713aa986d98eccd0b6ee16d26c7ec5f21b30e942756fd127a`,
  privileged container with only named volume `piston_wp3b:/piston`, published only at `127.0.0.1:2000`, runtime
  Python `3.10.0`.
- `make test-piston PISTON_CONFIG=configs/execution/piston-local.yaml`: `9 passed`, `0 failed`, `0 skipped`
  (`2 deselected` non-Piston cases).
- Formal Base run `outputs/evaluation/base-main-r1`: 4 test problems, `resumed=0`, `generated=4`; immutable model
  revision `2e1fd397ee46e1388853d2af2c993145b0f1098a`; dataset hash
  `3bfd5db68c39b8868df6a9bf6e1bdfa5745fef80516fb995d0f3159d26183380`.
- Same-run resume: `resumed=4`, `generated=0`; derived hashes remained byte-identical:
  `summary.json=0e76c83b719313c44da860da9bb5996a64aecfe3599c4723c913d1e448091762`,
  `main_results.csv=8c8ea4321631d8f32b4e6d0ccf7c3895f002763c328f4478a4c4ea5195f5651f`.
- Independent run `outputs/evaluation/base-main-repro`: 4 test problems, `resumed=0`, `generated=4`. Ignoring only
  `run_id`, `runtime_ms`, and `generation_latency_ms`, both ordered record sets had identical normalized SHA-256
  `03f4168f04155bca9d2a66bed919aa6f5d41004f687e075a862c405165f755b0`; all correctness metrics matched.
- Formal engineering-gate metrics on the four-problem smoke test split: parse/target/executable rates `1.0`;
  visible/train-hidden/eval-hidden pass@1 `0.5`; eval-hidden average test pass rate `0.5`; public-eval gap `0.0`;
  eval-hidden pass@1 95% problem bootstrap CI `[0.0, 1.0]`; public-eval-gap paired 95% CI `[0.0, 0.0]`;
  error categories `passed=2`, `runtime_error=2`.
- Derived-artifact audit: each run has 4 strict result rows, one CSV data row, finite metrics, error/status counts
  summing to 4, and no completion/code/test/reference-solution payload sentinel in summary or CSV.
- Final `make lint`: Ruff check/format and strict Mypy passed for 76 files.
- Final `make test-gpu`: `3 passed`, `0 failed`, `0 skipped` on the GTX 1660 Ti CUDA environment.
- Previously completed default regression remains `659 passed, 3 skipped`; all three skips were the explicitly gated
  Piston tests subsequently covered by the passing real-Piston command above.
- Final scope audit: no changes to plan, review, `proceedings.md`, or `third_party/open-r1/**`; no implementation
  changes after `result_code_commit`.

The four-problem Base result above is an engineering/pipeline acceptance baseline only, not a final research benchmark.

```yaml
execution_record:
  version: 1
  stage_id: WP5-b
  execution_id: E0
  task_kind: implementation
  source_plan_commit: c830b4acffd336fd5daf78945e7f6fcc004c002b
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: e84266b
  status: completed
```
