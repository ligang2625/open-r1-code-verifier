# Open-R1 CodeVerifier

Open-R1 CodeVerifier is a research scaffold for comparing visible-test and hidden-test rewards in function-level Python RLVR. WP0 project scaffolding through the WP7-a GRPO control-plane integration are implemented.

WP3 includes the stable execution contract, non-executing `MockExecutor`, loopback-only `PistonExecutor`, resource and sandbox acceptance, bounded batch concurrency, versioned SQLite caching, and the `execute-batch` CLI. WP4 adds structured verification results, completion → parser → executor orchestration, a shared reward core, and isolated Public/Hidden reward wrappers. WP5 adds frozen deterministic Transformers generation, three-layer per-problem pass@1 records, strict exact-prefix resume, problem-level metrics/bootstrap, and generated summary/CSV artifacts through the `evaluate` CLI. WP6 adds a visible-only SFT data contract, pinned LoRA/TRL/Open-R1 runtime construction, hardware protection, reproducible run artifacts, strict completed-run checkpoint identity, read-only PEFT reload, and B-group evaluation through the same `evaluate` pipeline. WP7-a adds Public/Hidden GRPO datasets and configs, verifier-backed TRL reward wiring, merged-B policy initialization, sanitized rollout/reward/group logs, strict resume, and the `train-grpo` CLI. Real untrusted code may only be sent to an explicitly configured local Piston service.

## Upstream dependency

`third_party/open-r1` is a read-only Git submodule pinned to:

```text
1416fa0cf21595d2083b399a2a0bbddd7f6e9563
```

Do not edit the submodule. Project integrations with Open-R1 must go through `code_verifier.training.open_r1_adapter`.

## Setup

```bash
git submodule update --init --recursive
make install
```

`make install` creates `.venv`, installs this project and the pinned Open-R1 checkout in editable mode, and installs the minimal WP1 data stack and development tools. The data dependencies are pinned to `PyYAML==6.0.2` and `datasets==3.2.0`; strict Mypy support also uses `types-PyYAML==6.0.12.20241230`.

`make install` intentionally skips Open-R1's large training dependency tree and torch: it is sufficient for lint and the CPU-only unit/default test suite. Real WP5-a Transformers generation requires the GPU environment:

```bash
make install-gpu
```

`make install-gpu` runs `uv sync --extra dev --extra gpu`: it installs the current pinned Open-R1/Transformers inference/GPU dependency stack plus the project-pinned CUDA torch wheel (`torch==2.6.0`, CUDA 12.4 build, from the PyTorch `cu124` index, compatible with Turing/sm_75). `make install-full` is kept as an alias for `make install-gpu`. Neither installation command updates the pinned Open-R1 commit.

Install the full pinned training-capable dependency stack when developing SFT/GRPO integrations or when running on the final training machine:

```bash
make install-train
```

`make install-train` adds the `training` extra and the exact `peft==0.14.0` pin while preserving TRL `0.18.0`, Transformers `4.52.3`, Accelerate `1.4.0`, torch `2.6.0`, and the pinned Open-R1 checkout. It is safe to run on the GTX 1660 Ti for API/import/integration development; installing the dependencies does **not** authorize optimizer-based training. The 20 GiB runtime hardware guard remains the boundary that prevents real SFT on the development GPU.

Development and smoke tests run on a machine with a single NVIDIA GeForce GTX 1660 Ti (6GB VRAM, Turing/sm_75); SFT/GRPO training still runs on the 24GB GPU (e.g. RTX 4090) machine per the project spec. After `make install-gpu`, regenerate `environment.json` with `record-environment` to confirm `cuda_version` / `gpu_name` / `gpu_count` and the added `compute_capability` / `bf16_supported` fields. `bf16_supported` records native hardware support only (torch `is_bf16_supported(including_emulation=False)`): it is `false` on Turing even though torch can create emulated BF16 tensors, and the final RTX 4090 training design keeps BF16. The GPU smoke generator explicitly loads the 0.5B debug model in fp16 and asserts the loaded dtype; `configs/eval/pass1.yaml` uses `generation.dtype: float16` for 1660 Ti debug evaluation. The GPU smoke tests load the model with `local_files_only=True` (offline cached model): they never perform Hugging Face network retries when the model is cached and the network is unreachable, and they fail fast with a clear message if the model is not cached yet. `generation.dtype: auto` keeps the legacy Transformers default loading behavior (no `torch_dtype` override). PEFT remains separate from the inference-only install and is available through `make install-train`; the `train-sft` hardware guard rejects the 1660 Ti before tokenizer/model/trainer loading. DeepSpeed is installed as pinned Open-R1 metadata but its GPU training integration is not validated on the 1660 Ti, so GPU training-stack acceptance is deferred to the RTX 4090. The CPU-only workflow (`make install` + `make test`) remains valid on machines without a GPU, where GPU smoke tests auto-skip with an explicit reason.

## Development-first workflow

The project deliberately separates **engineering development** from **real training/numerical validation**:

1. On the GTX 1660 Ti, finish all dependency-ready production code first: data/reward contracts, SFT/GRPO adapters and control planes, checkpoint/resume wiring, evaluation, aggregation, reporting, and analysis tooling. Each stage runs its declared **Execution preflight** (Piston/import/model-cache/CUDA checks as applicable) before the first business modification or commit, so common environment mistakes leave the stage retryable at the sealed plan commit.
2. Validate those paths with unit/integration tests, real loopback Piston where applicable, 0.5B FP16 GPU inference smoke, and deterministic fixture/mock/synthetic artifacts. Synthetic evidence is valid only for engineering contracts; it is never a B/C/D checkpoint or research metric.
3. Do not run optimizer-based SFT/GRPO on the 1660 Ti. The pre-model-load 20 GiB guard is intentional: seeing it fail closed on the development machine verifies the hardware boundary rather than blocking development. Installing `make install-train` on the development machine is allowed because dependency availability and real training are separate concerns.
4. A terminal development stage must carry a Development Completion Inventory that accounts for WP0–WP8; the absence of currently dependency-ready work is not enough. `DEV-CLOSEOUT` is valid only when all nine WP development deliverables are already finalized, and it is a SINGLE verification-only stage that may complete with `result_code_commit == plan_commit`. The terminal stage also must pass `make lint`, `make test`, `make test-gpu`, real `make test-piston` with no skips/failures, and the no-critical-stub/TODO/fake check.
5. `stage-lifecycle finalize` is the only writer of the machine-readable completion block: an exact `## Development Complete Record` heading immediately followed by the required YAML record. After the finalization docs commit, lifecycle reports the exact `development_complete_commit` (`main HEAD`). Natural-language mentions of completion do not unlock validation.
6. Perform one machine handoff: stop on the GTX 1660 Ti, sync that exact `main` commit to the RTX 4090, run `make install-train`, verify pinned PyTorch sees a >=22 GiB CUDA GPU, and restart with `planner-ex` on the 4090. Do not bootstrap a validation worktree on the 1660 Ti and copy it across machines.
7. Keep the entire validation track on the 4090: Base A, SFT B, Public/Hidden GRPO C/D, and final A–D aggregation/cost/error analysis. `execution-router` still verifies the 24GB-class GPU and a writable persistent artifact root before every validation execution. Real outputs default to the primary checkout's `outputs/` (outside `.worktrees/`) or to an absolute `CODE_VERIFIER_ARTIFACT_ROOT`; the only copy of a real checkpoint must never live inside a stage worktree.
8. If a later blocker leaves commits but no completed E0/review, use `stage-lifecycle retire_incomplete` to archive the exact branch history and replan; do not manually delete the worktree/branch. If a real 4090 run exposes an implementation bug after E0/review, fix it through the normal validation review/repair loop and rerun the affected gate; do not redesign features or silently change experiment definitions on the training machine.

A missing 24GB GPU, full-scale training data, or real checkpoint is therefore a **validation prerequisite**, not a reason to stop later code development that can be validated on the 1660 Ti.

## Quality checks

```bash
make lint
make test
.venv/bin/python -m code_verifier.cli --help
```

Default `make test` does not contact Piston. Run the real local-sandbox acceptance suite explicitly with:

```bash
make test-piston PISTON_CONFIG=configs/execution/piston-local.yaml
```

The command requires a self-hosted Piston service bound only to loopback with the exact configured Python runtime. See [`docs/piston-local.md`](docs/piston-local.md).

GPU-required tests are detected automatically: on a machine with a CUDA-capable GPU and the full inference dependencies (`make install-gpu`), `make test` runs the complete suite including the CUDA generation smoke tests. On a machine without a GPU, those tests are skipped with an explicit message telling you they require a GPU, and only the CPU suite runs. To run just the GPU smoke subset:

```bash
make test-gpu
```

`make test-gpu` is also auto-detecting: it runs on a CUDA-capable machine and skips with the same explicit reason on a machine without a GPU. Use `CODE_VERIFIER_GPU_MODEL=<model-id>` to override the smoke model (default `Qwen/Qwen2.5-Coder-0.5B-Instruct`).

Record repository/submodule commits, Python/platform, tracked dependency versions, dependency-lock identity, and optional CUDA/GPU identity with:

```bash
.venv/bin/python -m code_verifier.cli record-environment --output environment.json
```

## WP1 smoke data pipeline

Prepare the committed 20-problem fixture:

```bash
.venv/bin/python -m code_verifier.cli prepare-data \
  --config configs/data/smoke.yaml \
  --seed 42 \
  --output-dir data/processed/wp1-smoke \
  --log-level INFO
```

Revalidate the serialized artifacts:

```bash
.venv/bin/python -m code_verifier.cli check-data \
  --dataset data/processed/wp1-smoke \
  --seed 42 \
  --output-dir outputs/check-data \
  --log-level INFO
```

The generated layout is:

```text
data/processed/wp1-smoke/
├── canonical/
│   └── problems.jsonl
├── hf_dataset/
└── training/
    ├── sft.jsonl
    ├── public_grpo.jsonl
    └── hidden_grpo.jsonl
```

`canonical/problems.jsonl` is the auditable source of truth and contains all 20 problems and all three test layers. The Hugging Face Dataset uses the explicit schema version `wp1-canonical-json-v1`, stored in each row under `code_verifier_schema`. Because Apache Arrow cannot represent arbitrary heterogeneous JSON unions directly, each test uses `input_json` and `expected_json` deterministic JSON strings. Use the public decoder rather than consuming those encoded fields directly:

```python
from pathlib import Path

from code_verifier.data.prepare import load_hf_dataset

problems = load_hf_dataset(Path("data/processed/wp1-smoke/hf_dataset"))
```

`load_hf_dataset()` rejects unsupported schema versions and restores the canonical §7.1 `input` / `expected` values. `check-data` decodes every row and compares it with `canonical/problems.jsonl`.

The `training/` files contain only the 12 train-split problems and are built from explicit field whitelists:

- `sft.jsonl` contains the shared rendered prompt, function name, visible tests, SFT response, and bounded metadata needed for the pre-training quality gate; it contains no hidden tests or reference solution.
- `public_grpo.jsonl` contains visible tests only.
- `hidden_grpo.jsonl` contains visible and train-hidden tests.
- No training artifact contains `eval_hidden_tests`.

Preparation refuses to overwrite a non-empty output directory. Both preparation and checking validate schema completeness, duplicate IDs, independent cross-split prompt/signature, reference-solution and test-overlap signals, test-layer overlap, training-field isolation, row order, exact training-record equivalence to canonical train problems, and HF Dataset round-trip equivalence. Renaming eval-hidden content into an allowed training field therefore fails validation.

## WP2 code parser

Use the deterministic Python API to select the final supported fenced code block and optionally require a module-level target function:

~~~~python
from code_verifier.parsing import extract_python_code

completion = """Reasoning text.
```python
def solve(value):
    return value + 1
```
"""
result = extract_python_code(completion, expected_function_name="solve")
~~~~

Parse a UTF-8 completion file:

```bash
.venv/bin/code-verifier parse-code \
  --completion-file completion.txt \
  --expected-function-name solve
```

Read the completion from stdin:

```bash
printf '%s\n' '```python' 'def solve(x):' '    return x + 1' '```' | \
  .venv/bin/code-verifier parse-code \
    --completion-file - \
    --expected-function-name solve
```

The command prints one JSON object with `success`, `code`, `error_type`, and `num_code_blocks`. Exit code 0 means successful extraction, 1 means a structured parse failure, and 2 means a CLI or input I/O error.

The parser selects the last Python fenced block, or the last unmarked fenced block when no Python block exists. It does not treat the complete completion as code by default. It does not execute code, assess semantic correctness, repair output, or apply security checks.

## WP3-a execution contract

WP3-a defines the stable structured result types and a deterministic `MockExecutor` for offline tests. The mock validates requests, records defensive copies of calls, and returns preconfigured results in FIFO order. It does not execute code.

```python
from code_verifier.execution import (
    CodeExecutor,
    ExecutionResult,
    ExecutionStatus,
    MockExecutor,
    TestCaseResult,
)

configured = ExecutionResult(
    status=ExecutionStatus.PASSED,
    passed_tests=1,
    total_tests=1,
    pass_rate=1.0,
    runtime_ms=0.5,
    test_results=[
        TestCaseResult(
            status=ExecutionStatus.PASSED,
            passed=True,
            runtime_ms=0.5,
            stdout="",
            stderr="",
        )
    ],
)
executor: CodeExecutor = MockExecutor([configured])
result = executor.execute(
    code="def solve(value):\n    return value + 1\n",
    function_name="solve",
    tests=[{"input": 1, "expected": 2}],
    timeout_seconds=1.0,
    memory_limit_mb=64,
)
```

Do not use `MockExecutor` as evidence that untrusted code can be run safely.

## WP3-b local Piston executor

WP3-b adds a synchronous `PistonExecutor` that accepts the same `CodeExecutor` request shape and sends each test to a separate job on a self-hosted loopback Piston service. The host process never imports, compiles, evaluates, or executes candidate code.

```python
import json
from pathlib import Path

from code_verifier.execution import (
    PistonExecutor,
    execution_result_to_mapping,
    load_piston_executor_config,
)

config = load_piston_executor_config(Path("configs/execution/piston-local.yaml"))
executor = PistonExecutor(config)
assert executor.validate_runtime() == config.version

result = executor.execute(
    code="def solve(value):\n    return value + 1\n",
    function_name="solve",
    tests=[{"input": 1, "expected": 2}],
    timeout_seconds=1.0,
    memory_limit_mb=64,
)
print(json.dumps(execution_result_to_mapping(result), allow_nan=False))
```

Configuration rejects non-loopback URLs, redirects, proxies, runtime selectors, unknown fields, and unbounded responses. The real acceptance suite verifies result mapping, time, memory and output limits, disabled networking, non-root execution, filesystem isolation, host-file invisibility, per-job cleanup, PID containment, and service recovery.

Do not configure a public Piston endpoint or place API credentials in project configuration. Deployment, runtime installation, fixed image metadata, health checks, and shutdown instructions are in [`docs/piston-local.md`](docs/piston-local.md).

## WP3-c batch execution and cache

`BatchExecutor` validates every request before cache or worker side effects, creates an independent executor for each cache miss, caps concurrency at 64, and restores input order after futures complete. Evaluation workloads may use an optional versioned SQLite cache; training workloads reject cache use unless `allow_training_cache` is explicitly enabled and recorded.

```python
from pathlib import Path

from code_verifier.execution import (
    BatchExecutionRequest,
    BatchExecutor,
    BatchExecutorConfig,
    ExecutionCacheMode,
    ExecutionTestLayer,
    PistonExecutor,
    SQLiteExecutionCache,
    load_batch_execution_config,
    piston_executor_version,
)

config = load_batch_execution_config(Path("configs/execution/batch-local.yaml"))
request = BatchExecutionRequest(
    request_id="example-1",
    problem_id="problem-1",
    test_layer=ExecutionTestLayer.VISIBLE,
    code="def solve(value):\n    return value + 1\n",
    function_name="solve",
    tests=[{"input": 1, "expected": 2}],
    timeout_seconds=1.0,
    memory_limit_mb=64,
)

with SQLiteExecutionCache(Path("outputs/execution-cache.sqlite3")) as cache:
    batch = BatchExecutor(
        lambda: PistonExecutor(config.piston),
        executor_version=piston_executor_version(config.piston),
        config=BatchExecutorConfig(
            max_concurrency=4,
            cache_mode=ExecutionCacheMode.READ_WRITE,
            allow_training_cache=False,
        ),
        cache=cache,
    )
    result = batch.execute_batch([request])
```

The cache key stores hashes and execution metadata, not raw code or tests. Cached results can still contain bounded model stdout/stderr, so the SQLite file is created with user-only permissions and must be managed as a sensitive experiment artifact. Cache corruption or schema/version mismatch is a hard infrastructure error, not a cache miss.

Run the committed batch fixture through the CLI:

```bash
.venv/bin/code-verifier execute-batch \
  --config configs/execution/batch-local.yaml \
  --requests tests/fixtures/wp3c/batch_requests.jsonl \
  --workload-mode evaluation \
  --output-dir outputs/wp3c-batch \
  --log-level INFO
```

The output directory is published atomically and contains only:

```text
outputs/wp3c-batch/
├── results.jsonl
└── summary.json
```

`results.jsonl` contains ordered structured results without code or tests. `summary.json` records counts, cache hits, concurrency, executor version, workload/cache mode, and wall-clock runtime.

## WP4-a unified verification

`verify_completion()` accepts exactly one caller-selected test list, validates its shape and resource limits, extracts code through the WP2 parser, and delegates execution through the supplied `CodeExecutor`. It does not receive a complete problem record or a test-layer selector, so it cannot choose visible, train-hidden, or eval-hidden tests on its own.

```python
from code_verifier.verification import verification_result_to_mapping, verify_completion

result = verify_completion(
    completion="""```python
def solve(value):
    return value + 1
```""",
    tests=[{"input": 1, "expected": 2}],
    function_name="solve",
    metadata={"time_limit_seconds": 1.0, "memory_limit_mb": 64},
    executor=executor,
)
summary = verification_result_to_mapping(result)
```

Input validation is fail-closed: an empty test list is a `VerificationContractError`, and malformed function names, tests, or resource limits fail before parser or executor side effects. A parse failure returns structured `PARSE_ERROR` data and never calls the executor. Candidate code is still executed only by the configured `CodeExecutor`; the verifier contains no host execution path.

The sanitized summary records status, parse/execution flags, pass counts, pass rate, parser taxonomy, failure counts, and an optional validated execution result. It does not contain the completion, extracted code, selected tests, function name, or metadata. Reward calculation remains outside the Verification Layer.

## WP4-b reward layer

`code_verifier.rewards` exposes the shared `compute_code_rewards()` core plus the specification-level `public_code_reward()` and `hidden_code_reward()` wrappers. Public scoring receives `visible_tests` as its only test source. Hidden scoring receives `train_hidden_tests` as its only scoring source and may ignore a separately supplied `visible_tests` dataset column. Public rejects both `train_hidden_tests` and `eval_hidden_tests` in callback kwargs; Hidden rejects `eval_hidden_tests`. Neither training reward path may use eval-hidden tests.

```python
from code_verifier.rewards import compute_code_rewards, hidden_code_reward, public_code_reward

public_rewards = public_code_reward(
    completions,
    visible_tests,
    function_names,
    metadata_batch,
    executor=executor,
)
hidden_rewards = hidden_code_reward(
    completions,
    train_hidden_tests,
    function_names,
    metadata_batch,
    executor=executor,
    visible_tests=visible_tests,
)

rewards, component_records = compute_code_rewards(
    completions,
    visible_tests,
    function_names,
    metadata_batch,
    executor,
    mode="public",
)
```

The shared formula is `test_reward + executable_reward + timeout_penalty + invalid_format_penalty`: the selected-test pass rate is the main component, parsed/executed non-infrastructure results receive `+0.1`, timeout receives `-0.2`, and parser invalid-format/missing-target failures receive `-0.1`. Infrastructure sandbox failures do not receive the executable bonus. The core rejects batch-length mismatches instead of silently truncating them and returns exactly one finite reward and one sanitized component record per completion.

Reward callback completion items may be raw strings or the currently pinned Open-R1 chat-style message sequence; for chat payloads, the final message's exact string `content` is sent to the existing verifier. The wrappers require a caller-bound `CodeExecutor`. They do not create executors, register themselves with Open-R1, persist reward logs, or add GRPO commands/configuration. Formal trainer/Open-R1 adapter integration and experiment logging remain WP7 work.

Component records contain only mode, reward components, sanitized verification status/flags/counts, parser taxonomy, and failure counts. They do not contain completion text, extracted code, tests, function names, metadata, stdout/stderr, or nested execution results.

## WP5 deterministic pass@1 evaluation and aggregation

WP5-a evaluates a frozen model checkpoint one problem at a time using the fixed project prompt. The prompt contains only the problem statement, function signature, and visible examples. Generation is deterministic pass@1 (`do_sample: false`, `temperature: null`, `top_p: null`) and uses the tokenizer's configured chat template. Evaluation then sends the same parsed completion through the existing verifier three times, in visible → train-hidden → eval-hidden order. The top-level `execution_status` is always the eval-hidden status.

Prepare a validated WP1 artifact first, start the loopback Piston service described in [`docs/piston-local.md`](docs/piston-local.md), and install the full inference dependencies before a real model run:

```bash
make install-gpu
.venv/bin/code-verifier evaluate \
  --config configs/eval/pass1.yaml \
  --model-id <model-or-checkpoint-id> \
  --run-name base-debug \
  --seed 42 \
  --output-dir outputs
```

`configs/eval/pass1.yaml` sets `device: auto` and `generation.dtype: float16`; on the 1660 Ti development machine the frozen generator runs on CUDA when torch reports it available, loads the 0.5B debug model in FP16, and the run's `environment.json` records the CUDA/GPU identity so resume fails closed on hardware drift.

`configs/eval/pass1.yaml` retains `model_revision: null` for local/debug workflows. Formal Base evaluation uses the immutable 1.5B revision, CUDA, FP16, and real Piston configuration:

```bash
.venv/bin/code-verifier evaluate \
  --config configs/eval/base.yaml \
  --model-id Qwen/Qwen2.5-Coder-1.5B-Instruct \
  --run-name base-main-r1 \
  --seed 42 \
  --output-dir outputs
```

Each run is stored under `outputs/evaluation/<run-name>/`:

```text
outputs/evaluation/<run-name>/
├── resolved_config.yaml
├── environment.json
├── run.json
├── metrics.jsonl
├── stdout.log
├── stderr.log
├── summary.json
├── main_results.csv
└── samples/
    └── results.jsonl
```

Only `samples/results.jsonl` may persist completion text and extracted code. The manifest, environment record, progress metrics, logs, summary, and CSV are payload-bounded and do not store tests, reference solutions, completion text, or extracted code. `results.jsonl` stores per-problem status/rate summaries for all three test layers, but never stores the test payloads themselves.

`summary.json` uses schema version 1 and records run/model/dataset/config identities, bootstrap parameters, metrics, confidence intervals, and error/status counts. `main_results.csv` contains exactly one stable row for the run. Pass@1 means the fraction of problems whose layer pass rate is exactly 1.0; `eval_hidden_average_test_pass_rate` separately averages per-problem test pass rates. Error rates and bootstrap samples are problem-level. `public_eval_gap` is visible pass@1 minus eval-hidden pass@1, with a paired bootstrap interval that preserves problem pairing.

The committed 20-problem smoke fixture currently has four test-split problems. Its Base result is an auditable engineering/pipeline gate, not a final 300–500 problem research benchmark or evidence for broad model-quality claims.

Reusing the same run name performs strict prefix resume rather than overwrite or best-effort matching. Resume succeeds only when the resolved config, model/checkpoint identity, seed, dataset hash, prompt hashes/order, repository/submodule identity, dependency identity, and CUDA/GPU identity match the existing run. Already completed rows are not generated again. Corrupt, reordered, duplicated, non-finite, or identity-drifted rows cause a hard error.

The evaluation path is read-only with respect to training: it does not modify the frozen checkpoint, invoke Public/Hidden training rewards, write eval-hidden tests into training artifacts, or add SFT/GRPO behavior. Those boundaries must remain intact during WP6+ work.

## WP6-a LoRA SFT control plane

WP6-a normalizes every accepted SFT target to exactly one closed Python fenced block, parses the expected top-level function, verifies it only against the artifact's visible tests through `verify_completion()` and the configured `CodeExecutor`, and rejects failed, truncated, duplicate, repetitive, or over-length trajectories. After validation, the TRL dataset contains only conversational `prompt` and `completion` columns; tests, function names, and metadata are dropped before trainer construction.

On the 24GB training machine, prepare the WP1 data, start the loopback Piston service, install the training extra, and use a **persistent artifact root outside the stage worktree**. Routed validation automatically uses the primary checkout's `outputs/`; for a separate disk or mount, set an absolute override:

```bash
export CODE_VERIFIER_ARTIFACT_ROOT=/absolute/persistent/path/open-r1-code-verifier-outputs
make install-train
.venv/bin/code-verifier train-sft \
  --config configs/sft/debug.yaml \
  --seed 42 \
  --log-level INFO
```

When `CODE_VERIFIER_ARTIFACT_ROOT` is set, the default SFT output becomes `$CODE_VERIFIER_ARTIFACT_ROOT/sft`; the default evaluation output becomes `$CODE_VERIFIER_ARTIFACT_ROOT`. An explicit `--output-dir` still overrides the CLI default, but validation workflow rules forbid pointing it back inside `.worktrees/...`.

Resume is explicit:

```bash
.venv/bin/code-verifier train-sft \
  --config configs/sft/debug.yaml \
  --seed 42 \
  --resume-from-checkpoint "$CODE_VERIFIER_ARTIFACT_ROOT/sft/debug/checkpoints/checkpoint-1"
```

Resume accepts only a concrete `checkpoint-*` directory inside the already-existing run. The existing run's
model, effective config/seed, train and validation datasets, repository/Open-R1 commits, dependency lock, and
recorded cost must match; external or cross-run checkpoints are rejected. GPU-hours accumulate across attempts.
If `--seed` is omitted, `train-sft` uses the YAML seed. An explicit different CLI seed is printed as an override
and becomes the resolved run identity.

Each run uses `<artifact-root>/sft/<run-name>/` (default local path `outputs/sft/<run-name>/` when no artifact root is supplied) with `resolved_config.yaml`, `environment.json`, `run.json`, `metrics.jsonl`, bounded stdout/stderr logs, and `checkpoints/`. These metadata artifacts never store prompts, completions, code, tests, function names, or sample metadata. `configs/sft/debug.yaml` is a short 0.5B/fp16 path with evaluation disabled. `configs/sft/main.yaml` is the frozen 1.5B/bf16 LoRA configuration and evaluates every 100 steps against the independent visible-only `training/sft_validation.jsonl` artifact. Both enforce a non-lowerable project minimum of 20 GiB CUDA memory, so the GTX 1660 Ti fails closed before model loading.

WP6-a does not claim a real SFT checkpoint or B-group result. The final SFT validation still requires a 24GB GPU with at least 50 validated SFT examples and must complete the real 1–2 step smoke, finite-loss check, checkpoint reload, unified deterministic pass@1 evaluation, and cost recording; that validation does not block later dependency-ready code development.

## WP6-c completed SFT checkpoint evaluation

`evaluate` accepts exactly one explicit model source. `--model-id` keeps the Base path. `--sft-run-dir` loads only a strict SFT artifact with `run.json` status `completed`, a complete pinned PEFT adapter under its direct `checkpoints/` directory, and valid non-sensitive run identity. The adapter config's base model must exactly match the completed run. Pinned TRL 0.18.0 / PEFT 0.14.0 normally leaves the adapter config revision unset, so the completed run's non-empty `model_revision` remains the source of truth for loading the base weights; if an adapter config does contain a revision, it must match that run metadata.

After a real SFT run has completed on the 4090 validation machine, evaluate B with the same evaluation config, Piston executor, pass@1 evaluator, and aggregator used for Base:

```bash
.venv/bin/code-verifier evaluate \
  --config configs/eval/base.yaml \
  --sft-run-dir "$CODE_VERIFIER_ARTIFACT_ROOT/sft/<completed-run>" \
  --run-name sft-b-main-r1 \
  --seed 42
```

The effective evaluation identity records the SFT run's base `model_id` and `model_revision` plus the resolved adapter `checkpoints/` path. Existing config hashing and exact-prefix resume therefore reject a different SFT run or checkpoint. The SFT path does not introduce a second evaluator, result schema, or metric definition.

On the GTX 1660 Ti, fixture adapters and fake Transformers/PEFT runtimes validate this loader, CLI, resume, artifact, and aggregation contract without optimizer steps or model downloads. Those fixtures are engineering evidence only: they are not real B checkpoints, B metrics, loss, or cost evidence. A formal B result exists only after the 4090 validation track produces a real completed SFT run and evaluates it through the command above.

## WP7-a GRPO control plane

Public and Hidden GRPO use `configs/grpo/public.yaml` and `configs/grpo/hidden.yaml`. Their experiment settings are identical except `run_name`, `reward_mode`, and `dataset_path`; the paired datasets must keep problem order, prompt inputs, visible tests, and metadata identical. Public reward reads only `visible_tests`. Hidden reward reads only `train_hidden_tests`. Neither training path can load `eval_hidden_tests`.

Every run consumes the complete ordered C/D definition pair before training. The preflight requires matching
Public/Hidden configs and artifacts plus the same strict completed SFT B identity, then executes the selected reward
mode:

```bash
export CODE_VERIFIER_ARTIFACT_ROOT=/absolute/persistent/path/open-r1-code-verifier-outputs

.venv/bin/code-verifier train-grpo \
  --public-config configs/grpo/public.yaml \
  --hidden-config configs/grpo/hidden.yaml \
  --public-sft-run-dir "$CODE_VERIFIER_ARTIFACT_ROOT/sft/<completed-b-run>" \
  --hidden-sft-run-dir "$CODE_VERIFIER_ARTIFACT_ROOT/sft/<completed-b-run>" \
  --reward-mode public

.venv/bin/code-verifier train-grpo \
  --public-config configs/grpo/public.yaml \
  --hidden-config configs/grpo/hidden.yaml \
  --public-sft-run-dir "$CODE_VERIFIER_ARTIFACT_ROOT/sft/<completed-b-run>" \
  --hidden-sft-run-dir "$CODE_VERIFIER_ARTIFACT_ROOT/sft/<completed-b-run>" \
  --reward-mode hidden
```

The default output is `$CODE_VERIFIER_ARTIFACT_ROOT/grpo` or `outputs/grpo`. Resume requires a direct `<run>/checkpoints/checkpoint-N` child and exact parent-SFT, dataset, config, dependency, environment, seed, and reward-mode identity. Each run stores `rollouts.jsonl`, sanitized `rewards.jsonl`, `group_metrics.jsonl`, trainer metrics, and non-sensitive run metadata. Only rollout records contain completion text; reward/group/run/config/environment/stdout/stderr artifacts never contain test payloads.

Policy construction is fixed: load base A, load completed B adapter read-only, validate its base/revision identity, safe-merge B into base weights, then let `GRPOTrainer` create a new trainable GRPO LoRA. Disabling the GRPO adapter therefore returns to B, not A. Quantization, remote code, vLLM, Hub push, and remote reporting remain disabled.

The GTX 1660 Ti exercises production contracts through fake trainer/runtime integration and fails the non-lowerable 20 GiB guard before tokenizer/model loading. WP7-a produces no formal C/D checkpoint, metric, loss, or cost result. Real optimizer-based C/D training remains locked to the post-Development-Complete 24GB validation track; completed C/D reload and unified evaluation remain a later WP7 development stage.

## Current limitations

WP1 normalization uses deterministic Unicode and whitespace normalization plus SHA-256 hashing. It detects exact normalized prompt/signature, reference-solution, test-set, and matching-signature test-case overlap, but does not claim semantic or AST-level equivalence. The committed fixture is for structural and pipeline validation; its reference solutions are not executed by WP1 and are not evidence of model quality.

WP3 remains a single-machine design: one bounded local thread pool, one local SQLite cache, and one Piston job per test. It does not claim distributed execution, shared network storage, or cluster-scale throughput. Inside each job, a trusted parent process retains the expected value, comparator, and final marker while an isolated child interpreter receives only the function name and input. The child result channel is treated as an untrusted claimed return value and is compared only by the parent. This still relies on the Piston/Linux process and sandbox boundary rather than a separately deployed verifier service.

Minimal Open-R1 adapter usage remains:

```python
from code_verifier.training.open_r1_adapter import import_open_r1_module

open_r1 = import_open_r1_module()
```
