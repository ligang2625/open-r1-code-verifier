from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path("ai-work/executor/operator/WP9-d/wp9d-p1-runtime-validation/C0/p1_runtime_report.py")


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("wp9d_p1_runtime_report", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _phase(path: Path, wall: float) -> None:
    _write_json(path, {"return_code": 0, "wall_seconds": wall})


def _accepted(
    root: Path,
    key: str,
    *,
    phase: str,
    detail: str,
    commit: str,
    primary: Path,
    phase_meta: Path | None = None,
) -> None:
    evidence = root / f"operator/{key}/operator-evidence.json"
    _write_json(
        evidence,
        {
            "gate_status": "passed",
            "command_rc": 0,
            "postcheck_rc": 0,
            "handoff_commit": commit,
            "phase": phase,
            "detail": detail,
        },
    )
    _write_json(
        root / f"accepted/{key}.json",
        {
            "schema_version": "wp9d-p1-accepted-v1",
            "phase": phase,
            "detail": detail,
            "retry_tag": None,
            "handoff_commit": commit,
            "primary_artifact": str(primary),
            "phase_meta": str(phase_meta) if phase_meta is not None else None,
            "operator_evidence": str(evidence),
        },
    )


def _grpo_run(path: Path, *, mode: str, commit: str, attempt_wall: float = 9.0) -> None:
    util = {
        "status": "available",
        "gpu_utilization_mean_percent": 55.0,
        "gpu_utilization_p95_percent": 80.0,
        "gpu_memory_used_mean_mib": 9000.0,
        "gpu_memory_used_max_mib": 10000.0,
    }
    _write_json(
        path / "run.json",
        {
            "status": "completed",
            "global_step": 1,
            "git_commit": commit,
            "reward_mode": mode,
            "runtime_utilization": util,
            "peak_cuda_memory_allocated_bytes": 2 * 1024 * 1024 * 1024,
            "peak_cuda_memory_reserved_bytes": 3 * 1024 * 1024 * 1024,
            "attempts": [{"gpu_hours": attempt_wall / 3600.0}],
        },
    )
    _write_jsonl(
        path / "metrics.jsonl",
        [
            {
                "step": 1,
                "step_runtime_seconds": 5.0,
                "vllm_generation_runtime_seconds": 3.0,
                "generation_runtime_seconds": 3.0,
                "rollout_runtime_seconds": 4.0,
                "backward_runtime_seconds": 0.2,
                "backward_runtime_total_seconds": 1.6,
                "backward_calls": 8.0,
                "optimizer_runtime_seconds": 0.1,
            }
        ],
    )
    _write_jsonl(path / "group_metrics.jsonl", [{"sample_count": 8, "verifier_batch_wall_seconds": 0.4}])
    checkpoint = path / "checkpoints/checkpoint-1"
    checkpoint.mkdir(parents=True)
    for name in (
        "adapter_config.json",
        "adapter_model.safetensors",
        "optimizer.pt",
        "scheduler.pt",
        "rng_state.pth",
        "trainer_state.json",
        "training_args.bin",
    ):
        (checkpoint / name).write_bytes(b"x")


def _eval_run(path: Path, *, commit: str, ids: list[str], parallel: int, generation_wall: float) -> None:
    _write_json(
        path / "run.json",
        {
            "status": "completed",
            "total_problems": 8,
            "completed_records": 8,
            "batch_size": 4,
            "parallel_generators": parallel,
            "invocation_generation_wall_seconds": generation_wall,
            "runtime_utilization": {
                "status": "available",
                "gpu_utilization_mean_percent": 60.0,
                "gpu_utilization_p95_percent": 90.0,
                "gpu_memory_used_mean_mib": 7000.0,
                "gpu_memory_used_max_mib": 8000.0,
            },
        },
    )
    _write_json(path / "environment.json", {"project_commit": commit})
    _write_jsonl(path / "samples/generations.jsonl", [{"problem_id": problem_id} for problem_id in ids])


def _base_fixture(tmp_path: Path, *, hidden_commit: str | None = None) -> tuple[Path, Path, str, list[str]]:
    root = tmp_path / "p1"
    eval8 = tmp_path / "eval8"
    commit = "a" * 40
    hidden_commit = hidden_commit or commit
    ids = [f"p{index}" for index in range(8)]
    _write_json(
        eval8 / "wp9d_p1_eval8_manifest.json",
        {"problem_count": 8, "problem_ids": ids, "ordered_problem_ids_sha256": "e" * 64},
    )

    public_phase = root / "single/public/phase-meta.json"
    hidden_phase = root / "single/hidden-r1/phase-meta.json"
    public_run = root / "single/public/grpo/wp9d-P1-public-vllm-smoke-seed42"
    hidden_run = root / "single/hidden-r1/grpo/wp9d-P1-hidden-vllm-smoke-seed42-r1"
    _phase(public_phase, 10.0)
    _phase(hidden_phase, 12.0)
    _grpo_run(public_run, mode="public", commit=commit)
    _grpo_run(hidden_run, mode="hidden", commit=hidden_commit)
    _accepted(
        root,
        "single-public",
        phase="single",
        detail="public",
        commit=commit,
        primary=public_run,
        phase_meta=public_phase,
    )
    _accepted(
        root,
        "single-hidden",
        phase="single",
        detail="hidden",
        commit=hidden_commit,
        primary=hidden_run,
        phase_meta=hidden_phase,
    )
    return root, eval8, commit, ids


def _write_eval_pair(root: Path, commit: str, ids: list[str]) -> None:
    single_phase = root / "eval/single/phase-meta.json"
    dual_phase = root / "eval/dual/phase-meta.json"
    single_run = root / "eval/single/generation/wp9d-P1-b-eval8-b4-p1-seed42"
    dual_run = root / "eval/dual/generation/wp9d-P1-b-eval8-b4-p2-seed42"
    _phase(single_phase, 10.0)
    _phase(dual_phase, 6.0)
    _eval_run(single_run, commit=commit, ids=ids, parallel=1, generation_wall=8.0)
    _eval_run(dual_run, commit=commit, ids=ids, parallel=2, generation_wall=4.0)
    _accepted(
        root,
        "eval-single",
        phase="eval",
        detail="single",
        commit=commit,
        primary=single_run,
        phase_meta=single_phase,
    )
    _accepted(
        root,
        "eval-dual",
        phase="eval",
        detail="dual",
        commit=commit,
        primary=dual_run,
        phase_meta=dual_phase,
    )


def _write_concurrent_success(
    root: Path, *, tag: str, fraction: float, commit: str, wall: float, headroom: float
) -> None:
    concurrent = root / f"concurrent/{tag}-r1"
    result = {
        "result_path": str(concurrent / "concurrent-result.json"),
        "fraction": fraction,
        "handoff_commit": commit,
        "reason_class": "completed",
        "public_rc": 0,
        "hidden_rc": 0,
        "wall_seconds": wall,
        "headroom_mib": headroom,
        "gpu_utilization_mean_percent": 75.0,
        "gpu_utilization_p95_percent": 95.0,
        "gpu_memory_used_peak_mib": 19000.0,
        "gpu_total_mib": 24564.0,
    }
    _write_json(concurrent / "concurrent-result.json", result)
    _write_json(root / f"latest/concurrent-{tag}.json", result)
    public_run = concurrent / f"public/grpo/wp9d-P1-public-concurrent-{tag}-seed42-r1"
    hidden_run = concurrent / f"hidden/grpo/wp9d-P1-hidden-concurrent-{tag}-seed42-r1"
    _grpo_run(public_run, mode="public", commit=commit)
    _grpo_run(hidden_run, mode="hidden", commit=commit)
    detail = {"m040": "0.40", "m030": "0.30", "m025": "0.25"}[tag]
    _accepted(
        root,
        f"concurrent-{tag}",
        phase="concurrent",
        detail=detail,
        commit=commit,
        primary=concurrent,
    )


def test_report_selects_safe_material_concurrent_and_dual_b4(tmp_path: Path) -> None:
    module = _load_module()
    root, eval8, commit, ids = _base_fixture(tmp_path)
    _write_concurrent_success(root, tag="m040", fraction=0.4, commit=commit, wall=12.0, headroom=4096.0)
    _write_eval_pair(root, commit, ids)

    report = module.build_report(root, eval8)

    assert report["concurrent"]["decision"] == "concurrent"
    assert report["concurrent"]["selected_memory_fraction"] == 0.4
    assert report["concurrent"]["attempts"][0]["speedup"] == pytest.approx(22.0 / 12.0)
    assert report["dual_b4"]["decision"] == "dual"
    assert report["dual_b4"]["total_wall_speedup"] == pytest.approx(10.0 / 6.0)
    assert report["runtime_freeze_candidate"]["GRPO"]["public_hidden_execution"] == "concurrent"
    assert report["runtime_freeze_candidate"]["Eval"]["parallel_generators"] == 2
    assert report["single_arm"]["hidden"]["run_dir"].endswith("-r1")


def test_report_requires_next_bounded_fraction_after_memory_pressure(tmp_path: Path) -> None:
    module = _load_module()
    root, eval8, _, _ = _base_fixture(tmp_path)
    _write_json(
        root / "latest/concurrent-m040.json",
        {
            "fraction": 0.4,
            "handoff_commit": "a" * 40,
            "reason_class": "memory_pressure",
            "public_rc": 2,
            "hidden_rc": 2,
            "wall_seconds": 2.0,
            "headroom_mib": None,
        },
    )

    with pytest.raises(SystemExit, match="m030"):
        module.build_report(root, eval8)


def test_report_falls_back_to_sequential_when_pair_speedup_is_small(tmp_path: Path) -> None:
    module = _load_module()
    root, eval8, commit, ids = _base_fixture(tmp_path)
    _write_concurrent_success(root, tag="m040", fraction=0.4, commit=commit, wall=20.0, headroom=4096.0)
    _write_eval_pair(root, commit, ids)

    report = module.build_report(root, eval8)

    assert 1.0 < report["concurrent"]["attempts"][0]["speedup"] < 1.15
    assert report["concurrent"]["decision"] == "sequential"
    assert report["runtime_freeze_candidate"]["GRPO"]["vllm_gpu_memory_utilization"] == 0.4


def test_report_allows_unaffected_accepted_evidence_from_prior_handoff(tmp_path: Path) -> None:
    module = _load_module()
    prior = "b" * 40
    root, eval8, commit, ids = _base_fixture(tmp_path, hidden_commit=prior)
    _write_concurrent_success(root, tag="m040", fraction=0.4, commit=commit, wall=12.0, headroom=4096.0)
    _write_eval_pair(root, commit, ids)

    report = module.build_report(root, eval8)

    assert report["all_evidence_same_handoff_commit"] is False
    assert report["evidence_handoff_commits"] == [commit, prior]
