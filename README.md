# Open-R1 CodeVerifier

Open-R1 CodeVerifier is a research scaffold for comparing visible-test and hidden-test rewards in function-level Python RLVR. WP0 project scaffolding, the WP1 data layer, the WP2 deterministic code parser, the WP3-a execution contract/mock foundation, and the WP3-b loopback-only single-request Piston executor are implemented.

WP3 remains partially complete: batch concurrency, caching, and the execution debugging CLI are reserved for WP3-c. Reward computation, training, and model evaluation are also not implemented. `MockExecutor` remains a non-executing test double; real untrusted code may only be sent to an explicitly configured local Piston service.

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

The command intentionally skips Open-R1's large training dependency tree. Use `make install-full` only when a later Work Package requires the complete training stack. Neither installation command updates the pinned Open-R1 commit.

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

Record repository, submodule, Python, and dependency versions with:

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

- `sft.jsonl` contains no test fields or reference solutions.
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

## Current limitations

WP1 normalization uses deterministic Unicode and whitespace normalization plus SHA-256 hashing. It detects exact normalized prompt/signature, reference-solution, test-set, and matching-signature test-case overlap, but does not claim semantic or AST-level equivalence. The committed fixture is for structural and pipeline validation; its reference solutions are not executed by WP1 and are not evidence of model quality.

WP3-b performs one Piston job per test and does not yet provide WP3-c batch requests, bounded concurrency, caching, or an execution CLI. The trusted harness and candidate share one Python interpreter inside a sandbox job; the randomized marker and strict schema reduce ordinary spoofing but are not a complete defense against advanced interpreter-level tampering.

Minimal Open-R1 adapter usage remains:

```python
from code_verifier.training.open_r1_adapter import import_open_r1_module

open_r1 = import_open_r1_module()
```
