# WP7-a Execution Report

## E0 — legacy recovery implementation

This execution rebuilds WP7-a on the workflow-fixed baseline without inheriting the old stage provenance. The former stage remains read-only at `archive/wp7-a-legacy-20260814-160709` (`2a96f157b5f28258614c973f36599e87806ee593`). Its old plan, execution records, and R1/R2 reviews are historical evidence only.

### Recovery provenance

- New planning base: `0e836995eb2bb05c6cec78aa8e6d056573c9589c` (`fix(workflow): keep agent transport state untracked`).
- New plan seal: `f81f6172913292c8ec06926cc41f229322330fbe`.
- The old business implementation commits were mechanically replayed onto the new stage while deliberately excluding the old `.ai-bridge/**` transport commit, old execution report commits, and old review commits.
- Replayed business tree under `src/`, `configs/`, `tests/`, and `README.md` is byte-identical to the archived final reviewed business tree. `AGENTS.md` additionally retains the new main-line transport-state invariant.
- `.ai-bridge/**` is ignored/local-only and `git ls-files .ai-bridge` is empty in the recovered stage.
- Legacy-recovery ordering note: the archived business commits were mechanically replayed after the new worktree/environment and plan seal were established, then the full Execution preflight and acceptance suite were rerun on that exact recovered tree before this completed E0 was written. No new business logic was authored during the replay.

### Execution preflight

- Stage-local tooling: Ruff `0.9.10`, Mypy `1.15.0`, pytest `8.3.5`.
- Source binding: both `code_verifier` and `open_r1` resolve inside `/home/dzy/open-r1-code-verifier/.worktrees/wp7-a`.
- Pinned runtime: TRL `0.18.0`, Transformers `4.52.3`, Accelerate `1.4.0`, PEFT `0.14.0`, torch `2.6.0+cu124`; bounded signature inspection matched the expected GRPO/PEFT interfaces.
- Real loopback Piston runtime validation returned `3.10.0`.
- Development GPU baseline: `make test-gpu` → `3 passed` on the GTX 1660 Ti.

### Acceptance and legacy-recovery checks

- Focused WP7-a suite: `117 passed`.
- `.venv/bin/code-verifier train-grpo --help`: exit `0`; CLI requires Public/Hidden configs, Public/Hidden completed-SFT B definitions, and explicit `--reward-mode`.
- `make lint`: PASS; Ruff check/format and strict Mypy all green across 90 source files.
- `make test`: `803 passed, 3 skipped`; all three skips are the pre-existing explicit real-Piston opt-in tests.
- `make test-gpu`: `3 passed`.
- Archived business-tree comparison: no diff for `src`, `configs`, `tests`, or `README.md`.
- R1-M1 contract recheck: with the same completed SFT B but an intentionally drifted Hidden artifact prompt, production `run_grpo_training()` raises `GRPOTrainingError` before output creation (`output_exists=False`).
- R1-M2 contract recheck: `num_generations=3` is rejected at the project config boundary; the checked-in valid `num_generations=4` constructs pinned TRL with `generation_batch_size=8` and `steps_per_generation=8`.
- Real development hardware guard: GRPO training rejects the detected `6.0 GiB` GPU against the `20 GiB` minimum before model loading.
- No optimizer-based GRPO, real C/D checkpoint, research metric, loss, or cost evidence was produced.

### Recovered implementation commits

- `ddad44c` — GRPO dataset mapping
- `2ec4c77` — GRPO config contracts
- `4539dc6` — reward artifact logging
- `9b3b6a2` — merged-SFT policy construction
- `acefe3a` — GRPO run lifecycle
- `275ea53` — GRPO CLI
- `e97dc5f` — integration/docs coverage
- `c93770e` — formatting cleanup
- `603475c` — paired GRPO preflight and pinned-TRL fail-closed repair

```yaml
execution_record:
  version: 1
  stage_id: WP7-a
  execution_id: E0
  task_kind: implementation
  source_plan_commit: f81f6172913292c8ec06926cc41f229322330fbe
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: 603475c3d256b9f659d84e6a0d3e93e4126276b2
  execution_backend: web_codexpro
  effective_execution_mode: single
  status: completed
```
