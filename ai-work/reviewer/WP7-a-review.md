# WP7-a Review

## Review round 1

```yaml
review_record:
  version: 1
  stage_id: WP7-a
  review_round: 1
  source_execution_id: E0
  reviewed_head_commit: d2d621740f89d4f89555e20b24c9be8c79041c7f
  conclusion: pass
```

### Scope and provenance

- Reviewed the recovered WP7-a development execution sealed by plan commit `f81f6172913292c8ec06926cc41f229322330fbe`.
- Latest completed execution record is `E0`, `task_kind=implementation`, with `result_code_commit=603475c3d256b9f659d84e6a0d3e93e4126276b2` and execution-report commit/HEAD `d2d621740f89d4f89555e20b24c9be8c79041c7f`.
- Review started from a clean stage worktree at `/home/dzy/open-r1-code-verifier/.worktrees/wp7-a`; `.ai-bridge/**` is not tracked and `git ls-files .ai-bridge` is empty.
- `stage_profile=development`, `target_hardware=GTX 1660 Ti (6GB)`, `evidence_class=engineering`, `development_terminal=false`. No real optimizer-based GRPO, C/D checkpoint, numerical metric, or cost evidence is required or accepted for this stage.
- HEAD remained `d2d621740f89d4f89555e20b24c9be8c79041c7f` throughout the read/test portion of the review.

### Independent review findings

No blocker, major, minor, or actionable issue was found.

The implementation satisfies the WP7-a plan and the recovered-stage tightening contracts:

1. Shared prompt and GRPO dataset construction reuse the existing §7.2 prompt helper, keep Public rows visible-only, and add only `train_hidden_tests` for Hidden rows. `eval_hidden_tests` and other forbidden training payloads are rejected.
2. Public/Hidden GRPO configs use an exact schema and pair validation; checked-in C/D hyperparameters match except the explicitly allowed identity/reward-source fields.
3. Reward wiring follows the pinned TRL 0.18.0 keyword callback contract, selects only visible tests for Public and train-hidden tests for Hidden, reuses `compute_code_rewards()`, rejects batch/schema mismatch, and writes sanitized rollout/reward/group artifacts.
4. Runtime construction enforces the pinned dependency versions and the required `base A -> load completed B adapter read-only -> safe merge B -> new GRPO LoRA` sequence, preserving B as the reference policy rather than accidentally falling back to A.
5. Production GRPO orchestration validates the C/D config pair, the two completed-SFT B definitions, and the ordered Public/Hidden artifact pair before creating a selected run or loading trainer runtime. The 20 GiB guard runs before model loading and correctly fails closed on the development GTX 1660 Ti.
6. Run metadata/layout and resume checks bind the selected run to parent SFT identity, dataset/config hash, dependency/environment identity, seed, reward mode, and an in-run `checkpoint-N` path. Failure logging records only sanitized exception type information.
7. `train-grpo` exposes the required Public/Hidden configs, Public/Hidden completed-SFT definitions, explicit reward mode, resume path, seed override, and persistent artifact-root output semantics.
8. The two recovered-stage contracts are directly covered: fairness drift is rejected before output creation, and pinned TRL cross-field constraints reject `num_generations=1`/incompatible `3`, accept `4`, and normalize constructor `ValueError` to `GRPOTrainingError`.

### Independent verification evidence

- Focused WP7-a suite:
  - `.venv/bin/python -m pytest tests/unit/test_prompting.py tests/unit/training/test_grpo_data.py tests/unit/training/test_grpo.py tests/unit/test_cli.py tests/integration/test_wp7a_grpo_integration.py -q`
  - Result: `117 passed`.
- Direct recovered-contract checks:
  - fairness-drift integration parametrization + `num_generations` fail-closed/valid-4 + constructor normalization
  - Result: `7 passed`.
- CLI contract:
  - `.venv/bin/code-verifier train-grpo --help`
  - Result: exit `0`; required paired CLI surface present.
- Lint/type gate:
  - `make lint`
  - Result: Ruff check PASS, Ruff format PASS, strict Mypy PASS across 90 source files.
- Full default suite:
  - `make test`
  - Result: `803 passed, 3 skipped`; all three skips are existing explicit real-Piston opt-in tests.
- GPU engineering gate:
  - `make test-gpu`
  - Result: `3 passed` on the development GPU.
- Stage-local source/runtime binding:
  - `code_verifier` and `open_r1` both resolve inside `.worktrees/wp7-a`.
  - Pinned versions independently observed: TRL `0.18.0`, Transformers `4.52.3`, Accelerate `1.4.0`, PEFT `0.14.0`.
- Real loopback Piston prerequisite:
  - project `PistonExecutor.validate_runtime()` returned `3.10.0`.
- Pinned TRL source introspection independently confirms custom reward functions are called with `prompts=...`, `completions=...`, `completion_ids=...`, and dataset-column kwargs, matching the implemented callback contract.

### Plan acceptance disposition

- §7.2 shared prompt reuse: PASS.
- Public/Hidden dataset and leakage boundary: PASS.
- C/D config fairness and artifact-pair drift guard: PASS.
- Pinned TRL reward callback/batch alignment: PASS.
- Completed B identity + safe merge before new GRPO LoRA: PASS.
- Sanitized/recomputable rollout, reward, and group metrics artifacts: PASS.
- Strict run/resume identity: PASS.
- `train-grpo` persistent artifact-root semantics: PASS.
- GTX 1660 Ti fail-closed-before-model-load boundary: PASS.
- `make lint` / `make test` / `make test-gpu`: PASS.
- No `third_party/open-r1/**` modification or pinned dependency upgrade observed in the recovered business change set: PASS.
- No fabricated C/D checkpoint, research result, or cost evidence: PASS.

```yaml
repair_routing:
  version: 1
  required: false
  source_review_round: 1
  mode: null
  complexity: null
  single_class: null
  parallelizability: null
  multi_benefit: null
  independent_workstreams: 0
  repair_issue_ids: []
  rationale:
    - "WP7-a E0 independently satisfies the sealed development plan and recovered-stage tightening contracts."
    - "Focused, full, lint/type, GPU, Piston, source-binding, and pinned-runtime checks passed; no actionable repair remains."
  workstream_candidates: []
```

### Conclusion

**PASS.** The reviewed state at `d2d621740f89d4f89555e20b24c9be8c79041c7f` is acceptable for WP7-a development evidence. The next lifecycle operation is `stage-lifecycle checkpoint_review`; after that checkpoint is committed and remains current, the stage may proceed to `stage-lifecycle finalize`.
