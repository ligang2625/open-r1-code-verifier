# WP6-c Review

## R1 — latest completed E0 implementation

```yaml
review_record:
  version: 1
  stage_id: WP6-c
  review_round: 1
  source_execution_id: E0
  reviewed_head_commit: bcf7cfec6a605e934ba8b1379615ba8ef8ae4e41
  conclusion: needs_repair
```

### Provenance and scope

- Sealed plan: `ai-work/planner/WP6-c-plan.md`, source plan commit `09452e78d1d51300e6938768180d6d0decbc5c97`.
- Latest completed execution: `E0`, `task_kind=implementation`, result code commit `18af732f1fad8e54cab64bc40272d029dc0d233b`, execution-report commit / reviewed HEAD `bcf7cfec6a605e934ba8b1379615ba8ef8ae4e41`.
- Stage profile: `development`; evidence class: `engineering`; target hardware: GTX 1660 Ti (6GB); `development_terminal=false`.
- Review workspace was the sealed stage worktree `/home/dzy/open-r1-code-verifier/.worktrees/wp6-c`; it was clean before and after independent verification, and HEAD remained unchanged throughout review.
- This review does not require or treat missing real SFT/B numerical evidence as a failure. Fixture/fake runtime evidence is valid for this development stage, but it must accurately model the pinned runtime contract used by a future real checkpoint.

### Independent verification

- Plan-focused suite:
  - `.venv/bin/python -m pytest tests/unit/training/test_sft.py tests/unit/evaluation/test_generate.py tests/unit/test_cli.py tests/integration/test_wp6c_sft_checkpoint_evaluation.py -q`
  - Result: `124 passed`.
- `make lint`: PASS; Ruff check/format and strict mypy all passed.
- `make test`: PASS; `736 passed, 3 skipped`; the three skips are the existing explicit real-Piston opt-in tests.
- `make test-gpu`: PASS; `3 passed` on the GTX 1660 Ti.
- Pinned-runtime inspection:
  - `trl.get_peft_config(ModelConfig(... model_revision=<40-hex> ...))` returns a `LoraConfig` whose `revision` is `None`.
  - `inspect.getsource(trl.get_peft_config)` confirms the pinned TRL `0.18.0` implementation constructs `LoraConfig` without passing `model_revision`.
  - `inspect.getsource(peft.PeftModel)` for pinned PEFT `0.14.0` shows `save_pretrained()` fills `base_model_name_or_path` when absent, but does not fill the config `revision` from the loaded Transformers model.
  - Formal SFT config `configs/sft/main.yaml` pins non-null `model_revision: 2e1fd397ee46e1388853d2af2c993145b0f1098a`.

### Plan / acceptance coverage

| Area | Result | Review evidence |
|---|---|---|
| Completed-run/checkpoint identity loader | PASS | Strict completed status/layout/direct checkpoint ownership, required identity hashes, adapter files, and payload-free identity are implemented and unit-tested. |
| PEFT inference reload | **FAIL — R1-M1** | Base model identity is checked and inference-only loading is present, but the revision check assumes real PEFT adapters persist the base revision; pinned TRL/PEFT does not. |
| Explicit Base vs SFT CLI model source | PASS | Required mutually exclusive `--model-id` / `--sft-run-dir`; B path binds the completed-run identity and reuses existing evaluator/aggregator. |
| B evaluation resume/checkpoint identity | PASS subject to R1-M1 | Existing evaluator config hash and exact-prefix resume bind the resolved checkpoint path; integration tests cover identity changes. |
| Payload / hidden-test boundary | PASS | Integration tests preserve visible-only prompt construction and keep completion/code/test payloads out of non-sample artifacts. |
| Development evidence boundary | PASS | No optimizer-based SFT/GRPO, no real B checkpoint/metric/cost claim; fixture evidence is explicitly engineering-only. |
| Full engineering regression | PASS | Focused suite, lint, default tests, and GPU smoke independently pass. |

### Actionable findings

#### R1-M1 — Major — Real pinned SFT adapters with a pinned model revision are rejected by `from_peft_checkpoint()`

`src/code_verifier/evaluation/generate.py` currently does:

```python
adapter_revision = getattr(adapter_config, "revision", None)
...
if base_model_revision is not None and adapter_revision != base_model_revision:
    raise GenerationError("PEFT adapter base model revision does not match the selected SFT run")
```

This is incompatible with the project's own pinned SFT path. `configs/sft/main.yaml` pins a non-null 40-hex base revision, but pinned TRL `0.18.0` `get_peft_config()` does not copy `ModelConfig.model_revision` into `LoraConfig`; the resulting PEFT config has `revision=None`. Pinned PEFT `0.14.0` `save_pretrained()` fills `base_model_name_or_path` but does not synthesize that missing revision. Therefore a real adapter produced by `run_sft_training()` will normally have a valid base-model name but no adapter-config revision, and the current B reload path will reject it before model loading.

The current unit/integration fixtures hide this defect by explicitly giving fake adapter configs `revision="revision-1"` / a matching 40-hex revision, which is not the pinned runtime behavior.

Required repair:

1. Keep the SFT run metadata as the source of truth for the pinned base `model_revision`; it is already passed to `AutoTokenizer` / `AutoModelForCausalLM.from_pretrained`, so the actual base weights remain pinned.
2. Keep strict `base_model_name_or_path == checkpoint.model_id` validation.
3. Only enforce adapter-config revision equality when the pinned adapter config actually contains a non-null revision; `revision=None` must be accepted for a completed run with a non-null run-metadata revision. If an adapter revision is present and differs, continue to fail closed.
4. Add a regression test using the realistic pinned case: non-null SFT `model_revision` + adapter config `revision=None` must load; retain a separate non-null mismatched-adapter-revision rejection test.
5. Update the WP6-c integration fake adapter and README wording so the engineering fixture reflects pinned TRL/PEFT behavior rather than asserting that the adapter file always stores the base revision.

This is required before PASS because the central WP6-c deliverable is reloadability of a future real completed SFT checkpoint, not only compatibility with a stronger-than-real fake adapter schema.

### Execution-report verification

The E0 report's reported focused/full lint/test/GPU results were independently reproduced. Its statement that PEFT reload is implemented is structurally true, but the claim that the implementation satisfies the completed real-checkpoint reload contract is incomplete because of `R1-M1`. No evidence was found that fake artifacts were reported as formal B results.

### Conclusion

`needs_repair`. The implementation is otherwise well-scoped and the engineering suite is green, but `R1-M1` blocks the core real-checkpoint reload contract that this development stage is meant to make ready for later 4090 validation.

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
    - "The only required repair is one tightly coupled PEFT revision-contract correction spanning loader behavior, its regression fixtures/tests, and matching documentation."
    - "The correct behavior depends on the pinned TRL/PEFT runtime semantics already reproduced in review; splitting this across multiple lanes would add coordination cost without independent implementation workstreams."
  workstream_candidates: []
```

### Next lifecycle step

Run `$stage-lifecycle checkpoint_review` to commit this R1 review. After checkpointing, run `$execution-router` for the single `R1-M1` repair, then invoke `reviewer-ex` again on the new completed repair execution.
