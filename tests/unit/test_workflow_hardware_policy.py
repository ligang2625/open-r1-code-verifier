from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_validation_control_plane_is_separate_from_target_hardware() -> None:
    planner = _text("skills/planner-ex/SKILL.md")
    lifecycle = _text("skills/stage-lifecycle/SKILL.md")
    router = _text("skills/execution-router/SKILL.md")
    reviewer = _text("skills/reviewer-ex/SKILL.md")
    template = _text("skills/planner-ex/references/plan-template.md")

    for document in (planner, lifecycle, router, reviewer, template):
        assert "control_plane_hardware" in document
        assert "target_hardware" in document
        assert "GTX 1660 Ti" in document
        assert "24GB" in document

    assert "不得为了规划而实时连接或探测 4090" in planner
    assert "bootstrap 不读取本机 `.ai-bridge/validation-machine.json`" in lifecycle
    assert "Router 默认只调度 **control-plane execution**" in router
    assert "reviewer location 与 target hardware 分离" in reviewer


def test_new_operator_handoff_is_portable_and_real_execution_identity_is_strict() -> None:
    lifecycle = _text("skills/stage-lifecycle/SKILL.md")
    router = _text("skills/execution-router/SKILL.md")
    executor_local = _text("skills/executor-ex/SKILL.md")
    executor_web = _text("skills/executor-web/SKILL.md")
    workflow = _text("docs/control-plane-gpu-worker-workflow.md")

    for document in (lifecycle, router, executor_local, executor_web):
        assert "portable_target" in document

    assert "ai-work/executor/operator/" in executor_local
    assert ".ai-bridge/operator-handoffs" not in executor_local
    assert "operator-evidence.json" in executor_local
    assert "postcheck_rc" in executor_local
    assert "gate_status=passed" in executor_local
    assert "operator_evidence_sha256" in executor_local
    assert "operator_evidence_sha256" in router
    assert "actual operator-handoff commit" in workflow
    assert "tracked script SHA" in workflow
    assert "legacy" in router.lower()


def test_validation_evidence_profile_does_not_force_4090_execution() -> None:
    planner = _text("skills/planner-ex/SKILL.md")
    lifecycle = _text("skills/stage-lifecycle/SKILL.md")
    router = _text("skills/execution-router/SKILL.md")
    reviewer = _text("skills/reviewer-ex/SKILL.md")

    for document in (planner, lifecycle, router, reviewer):
        assert "formal-evidence" in document or "formal evidence" in document
        assert "GTX 1660 Ti" in document
        assert "24GB" in document

    assert "全部 24GB acceptance gates" in lifecycle
    assert "不存在 router 直接把 executor 切到 4090 的第二路径" in router
    assert "target=24GB" in reviewer


def test_target_gpu_success_requires_post_run_acceptance_and_evidence_hash() -> None:
    planner = _text("skills/planner-ex/SKILL.md")
    lifecycle = _text("skills/stage-lifecycle/SKILL.md")
    router = _text("skills/execution-router/SKILL.md")
    reviewer = _text("skills/reviewer-ex/SKILL.md")

    for document in (planner, lifecycle, router, reviewer):
        assert "postcheck_rc" in document
        assert "gate_status" in document

    assert "operator_evidence_sha256" in router
    assert "operator_evidence_sha256" in reviewer
    assert "tracked operator script" in reviewer


def test_canonical_piston_host_and_sft_prevalidation_policy_are_preserved() -> None:
    agents = _text("AGENTS.md")
    readme = _text("README.md")
    piston_doc = _text("docs/piston-local.md")
    workflow = _text("docs/control-plane-gpu-worker-workflow.md")
    template = _text("skills/planner-ex/references/plan-template.md")
    piston_config = _text("configs/execution/piston-local.yaml")

    for document in (agents, readme, piston_doc):
        assert "1660ti-wsl" in document
        assert "home-piston-01" in document

    assert "reverse forward" in agents
    assert "-R 127.0.0.1:2000:127.0.0.1:2000" in agents
    assert "-R 127.0.0.1:2000:127.0.0.1:2000" in piston_doc
    assert "reverse-forward" in workflow
    assert "canonical transport" in template
    assert "base_url: http://127.0.0.1:2000" in piston_config
    assert "ensure-piston-1660ti-tunnel.sh" not in piston_doc
    assert "prevalidate-sft" in agents
    assert "train-sft" in agents
    assert "must not contact Piston" in agents


def test_partial_execution_is_continuation_first_not_sha_locked() -> None:
    agents = _text("AGENTS.md")
    spec = _text("PROJECT_SPEC_Open-R1_CodeVerifier.md")
    workflow = _text("docs/control-plane-gpu-worker-workflow.md")
    lifecycle = _text("skills/stage-lifecycle/SKILL.md")
    router = _text("skills/execution-router/SKILL.md")

    assert "preferred recovery anchor" in agents
    assert "没有 exact current-head checkpoint 也可继续" in spec
    assert "not the only proof" in workflow
    assert "INCOMPLETE_UNKNOWN" in lifecycle
    assert "continuation assessment" in router
    assert "retire_incomplete" in lifecycle


def test_canonical_workflow_documents_all_four_machine_routing_cases() -> None:
    workflow = _text("docs/control-plane-gpu-worker-workflow.md")

    assert "Case 1: ordinary development" in workflow
    assert "Case 2: validation + formal SFT" in workflow
    assert "Case 3: formal evaluation" in workflow
    assert "Case 4: GRPO" in workflow
    assert "4090: off" in workflow
    assert "Do not rsync large model checkpoints back by default" in workflow
    assert "generate complete frozen bundle" in workflow
    assert "verify frozen completions with local Piston" in workflow


def test_formal_evaluation_does_not_serialize_4090_generation_with_piston() -> None:
    agents = _text("AGENTS.md")
    spec = _text("PROJECT_SPEC_Open-R1_CodeVerifier.md")
    planner = _text("skills/planner-ex/SKILL.md")
    workflow = _text("docs/control-plane-gpu-worker-workflow.md")

    for document in (agents, spec, planner, workflow):
        assert "generate-eval" in document
        assert "verify-eval" in document
        assert "aggregate-eval" in document
    assert "不得让 4090 在每题 generation 之间等待 Piston" in spec
    assert "不默认把整条 evaluation 留在 4090" in planner
    assert "Piston execution timing is fresh runtime telemetry" in workflow
    assert "control_plane_manual" in spec


def test_active_stage_workflow_migration_uses_audit_anchors_not_sha_state_locks() -> None:
    agents = _text("AGENTS.md")
    workflow = _text("docs/control-plane-gpu-worker-workflow.md")
    lifecycle = _text("skills/stage-lifecycle/SKILL.md")
    router = _text("skills/execution-router/SKILL.md")
    executor_local = _text("skills/executor-ex/SKILL.md")
    executor_multi = _text("skills/executor/SKILL.md")
    executor_web = _text("skills/executor-web/SKILL.md")
    reviewer = _text("skills/reviewer-ex/SKILL.md")

    for document in (agents, workflow, lifecycle, router, executor_local, executor_multi, executor_web, reviewer):
        assert "workflow_runtime_commit" in document

    assert "audit anchors rather than immutable state locks" in workflow
    assert "workflow_runtime_commit 变化不再因 SHA guard 自动破坏 stage" in lifecycle
    assert "不要求与旧 plan/review 逐项精确匹配" in router
    assert "Ordinary parent/source/result-code SHA relationships are audit anchors" in agents
    assert "control_plane_manual" in workflow
    assert "control_plane_manual" in reviewer
    assert "不得绕过真正 target-GPU gate" in reviewer


def test_user_override_changes_execution_method_not_scientific_requirements() -> None:
    agents = _text("AGENTS.md")
    spec = _text("PROJECT_SPEC_Open-R1_CodeVerifier.md")
    refresh = _text("PROJECT_SPEC_GRPO_Refresh.md")
    proceedings = _text("proceedings.md")

    assert (
        "Explicit user changes to implementation method, scope, ordering, routing, or recovery "
        "define the effective execution contract" in agents
    )
    assert "active addendum 的 MUST/MUST NOT" in spec
    assert "workflow 灵活性不改变本规格的 MUST/MUST NOT" in refresh
    assert "workflow override 降低这些规范性 acceptance" in proceedings


def test_wp9_next_dependency_ready_stage_remains_wp9_b() -> None:
    refresh = _text("PROJECT_SPEC_GRPO_Refresh.md")
    proceedings = _text("proceedings.md")

    assert "## 17.2 WP9-b — Calibration / k=8 / throughput engineering" in refresh
    assert "只用 engineering evidence 关闭" in refresh
    assert "Next dependency-ready stage 是 `WP9-b`" in proceedings
    assert "下一 dependency-ready stage 仍为 `WP9-b` development" in proceedings
