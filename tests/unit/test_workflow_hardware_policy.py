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
        assert "GTX 1660 Ti" in document

    assert "不得为了规划而实时连接或探测 4090" in planner
    assert "bootstrap 不读取本机 `.ai-bridge/validation-machine.json`" in lifecycle
    assert "Router 默认只调度 **control-plane execution**" in router
    assert "reviewer location、artifact source machine" in reviewer


def test_new_operator_handoff_is_portable_and_legacy_records_remain_readable() -> None:
    lifecycle = _text("skills/stage-lifecycle/SKILL.md")
    router = _text("skills/execution-router/SKILL.md")
    executor_local = _text("skills/executor-ex/SKILL.md")
    executor_web = _text("skills/executor-web/SKILL.md")

    for document in (lifecycle, router, executor_local, executor_web):
        assert "portable_target" in document

    assert ".ai-bridge/operator-handoffs" in executor_local
    assert "operator-evidence.json" in executor_local
    assert "旧版" in lifecycle
    assert "legacy" in router.lower()


def test_canonical_piston_host_and_sft_prevalidation_policy_are_preserved() -> None:
    agents = _text("AGENTS.md")
    readme = _text("README.md")
    piston_doc = _text("docs/piston-local.md")

    for document in (agents, readme, piston_doc):
        assert "1660ti-wsl" in document
        assert "home-piston-01" in document

    assert "ensure-piston-1660ti-tunnel.sh" in agents
    assert "ensure-piston-1660ti-tunnel.sh" in piston_doc
    assert "prevalidate-sft" in agents
    assert "train-sft" in agents
    assert "must not contact Piston" in agents


def test_environment_interruptions_resume_instead_of_forcing_retirement() -> None:
    agents = _text("AGENTS.md")
    spec = _text("PROJECT_SPEC_Open-R1_CodeVerifier.md")
    lifecycle = _text("skills/stage-lifecycle/SKILL.md")

    assert "do **not** force `retire_incomplete`" in agents
    assert "interruption_class=environment,resume_allowed=true" in spec
    assert "resume" in lifecycle.lower()
    assert "retire_incomplete" in lifecycle


def test_canonical_workflow_documents_all_four_machine_routing_cases() -> None:
    workflow = _text("docs/control-plane-gpu-worker-workflow.md")

    assert "Case 1: ordinary development" in workflow
    assert "Case 2: validation + formal SFT" in workflow
    assert "Case 3: formal evaluation" in workflow
    assert "Case 4: GRPO" in workflow
    assert "4090: off" in workflow
    assert "Do not rsync large model checkpoints back by default" in workflow
