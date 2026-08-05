# Open-R1 CodeVerifier

Open-R1 CodeVerifier is a research scaffold for comparing visible-test and hidden-test rewards in function-level Python RLVR. WP0 project scaffolding is complete, and WP1 now provides the data schema, deterministic three-layer test splitting, deduplication, leakage checks, training-safe views, and a committed 20-problem smoke fixture.

Training, code parsing, untrusted-code execution, reward computation, and model evaluation are not implemented yet. Those capabilities belong to later Work Packages.

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

## Current limitations

WP1 normalization uses deterministic Unicode and whitespace normalization plus SHA-256 hashing. It detects exact normalized prompt/signature, reference-solution, test-set, and matching-signature test-case overlap, but does not claim semantic or AST-level equivalence. The committed fixture is for structural and pipeline validation; its reference solutions are not executed by WP1 and are not evidence of model quality.

Minimal Open-R1 adapter usage remains:

```python
from code_verifier.training.open_r1_adapter import import_open_r1_module

open_r1 = import_open_r1_module()
```
