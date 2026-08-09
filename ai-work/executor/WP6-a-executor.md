# WP6-a Executor Report

## Human-readable summary

WP6-a implementation is complete under the sealed single-agent implementation route. The stage now has one shared visible-only §7.2 prompt builder, a stricter SFT artifact contract, deterministic trajectory normalization and visible-test verification, exact PEFT/runtime pins, strict LoRA configuration and hardware protection, payload-free training run artifacts, `train-sft` CLI/resume plumbing, and CPU/mock integration coverage.

No real SFT training was started. A real `train-sft` invocation on the current GTX 1660 Ti validated Piston first and then failed closed before tokenizer/model/trainer loading because the configured minimum is 20 GiB and the device exposes 6.0 GiB. Real checkpoint, reload, B-group evaluation, 50-example smoke, and cost acceptance remain WP6-b gates.

## Step and commit mapping

| Plan step | Result | Commit |
|---|---|---|
| 1. Shared prompt builder | Byte-compatible visible-only builder shared by WP5 and SFT | `42ffaa4` |
| 2. SFT artifact contract | Rendered prompt, function name, visible tests, response, bounded metadata; hidden/reference/starter keys rejected | `6c784ef` |
| 3. Trajectory quality gate | Single fenced target normalization, visible-only verifier path, repetition/length fail-closed rules, minimal TRL dataset | `7e8d485` |
| 4. Training dependency/runtime | `peft==0.14.0`, `install-train`, lock entry, pinned runtime/import probes | `717cd5a` |
| 5. LoRA control plane | Strict YAML, runtime mapping, 20 GiB/native-BF16 guard, resume identity, payload-free run artifacts | `72a1647` |
| 6. CLI and integration | `train-sft`, resume option, sanitized exit 2, fake-runtime end-to-end coverage | `ebfaa10` |
| 7. Documentation/handoff | Setup, hardware split, artifacts, WP6-b external gates | `c854fcb` |
| Bridge status | Final files/checks/blockers handoff | `a6f16ab` |

## Verification evidence

- Shared prompt focus: `34 passed`.
- WP1 data/leakage focus: `117 passed`.
- SFT data focus: `13 passed`; Ruff and strict Mypy passed.
- SFT control-plane focus: `31 passed`; Ruff and strict Mypy passed.
- CLI/training/integration focus: `78 passed`.
- Pinned no-training conversational dataset probe: TRL `0.18.0` accepted `prompt`/`completion` conversational rows.
- Pinned no-training trainer-construction probe: `ModelConfig`, Open-R1 `SFTConfig`, and PEFT `LoraConfig` constructed; project `max_seq_length` mapped only to TRL `max_length`.
- Exact installed versions: Open-R1 `0.1.0.dev0`, TRL `0.18.0`, Transformers `4.52.3`, Accelerate `1.4.0`, PEFT `0.14.0`.
- `PYTHONPATH=src make lint VENV=/home/dzy/open-r1-code-verifier/.venv`: passed; Ruff check, Ruff format check, and strict Mypy all green across 84 source files.
- `PYTHONPATH=src make test VENV=/home/dzy/open-r1-code-verifier/.venv`: `701 passed, 3 skipped`; only the three explicitly enabled real-Piston cases skipped by default.
- `PYTHONPATH=src make test-gpu VENV=/home/dzy/open-r1-code-verifier/.venv`: `3 passed` on the real GTX 1660 Ti; existing CUDA identity, FP16 generation, and autograd smoke ran without SFT.
- `code-verifier --help` and `code-verifier train-sft --help`: both returned 0.
- Real guarded CLI probe: returned 2 with `SFT training requires at least 20 GiB CUDA memory; detected 6.0 GiB`; no output run directory was created.
- `third_party/open-r1/**`, the sealed plan, reviewer artifacts, and `proceedings.md`: no diff.

## Files changed

- Shared/data: `src/code_verifier/prompting.py`, `src/code_verifier/evaluation/generate.py`, `src/code_verifier/data/leakage_checks.py` and related tests.
- Training: `src/code_verifier/training/sft_data.py`, `src/code_verifier/training/sft.py`, `src/code_verifier/training/__init__.py`, adapter contract test, training unit/integration tests.
- Runtime/config/CLI: `pyproject.toml`, `uv.lock`, `Makefile`, `configs/sft/debug.yaml`, `configs/sft/main.yaml`, `src/code_verifier/cli.py` and CLI tests.
- Documentation/handoff: `README.md`, `AGENTS.md`, `.ai-bridge/agent-status.md`, `.ai-bridge/execution-log.jsonl`.

## Deviations and blockers

- Blockers: none.
- Linked-worktree installation detail: this stage worktree intentionally had an empty, uninitialized submodule directory. To preserve the prohibition on modifying `third_party/open-r1`, the PEFT lock delta was resolved in an isolated temporary project against the existing pinned read-only checkout, normalized back to the repository-relative source, and verified byte-for-byte. PEFT `0.14.0` was then installed into the existing project virtual environment for runtime tests. The committed `make install-train` target remains the canonical command for a normal initialized checkout/training machine.
- `configs/sft/main.yaml` keeps `eval_strategy: no` because the current SFT artifact contains only canonical train rows and WP6-a does not invent or reuse a validation split. The other §11.3 LoRA/hyperparameter defaults and frozen model revision are preserved; formal validation/evaluation remains WP6-b work.
- `.ai-bridge/implementation-diff.patch` was not duplicated because the staged seven-commit implementation history is the exact canonical review input; use `git diff 0d17934e101c142d5117c6ec5c05bdf8c938921d..a6f16ab43c4c5c2ed73097064269ba08fd5d9df4`.

## Structured execution record

```yaml
execution_record:
  version: 1
  stage_id: WP6-a
  execution_id: E0
  task_kind: implementation
  source_plan_commit: 0d17934e101c142d5117c6ec5c05bdf8c938921d
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: a6f16ab43c4c5c2ed73097064269ba08fd5d9df4
  status: completed
```
