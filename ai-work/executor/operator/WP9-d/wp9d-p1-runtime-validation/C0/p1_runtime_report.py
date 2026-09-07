#!/usr/bin/env python3
"""Build a strict WP9-d P1 runtime summary from accepted bounded target artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

CONCURRENT_SPEEDUP_MIN = 1.15
SAFE_HEADROOM_MIB = 1024.0
_ACCEPTED_SCHEMA = "wp9d-p1-accepted-v1"
_REPORT_SCHEMA = "wp9d-p1-runtime-report-v1"
_QKVO_TARGETS = {"q_proj", "k_proj", "v_proj", "o_proj"}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SystemExit(f"unreadable JSON artifact: {path}: {type(error).__name__}") from None
    if not isinstance(value, dict):
        raise SystemExit(f"JSON artifact must be an object: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise SystemExit(f"unreadable JSONL artifact: {path}: {type(error).__name__}") from None
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(lines, 1):
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            raise SystemExit(f"invalid JSONL row {index}: {path}") from None
        if not isinstance(row, dict):
            raise SystemExit(f"JSONL row {index} must be an object: {path}")
        rows.append(row)
    return rows


def _number(value: object, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise SystemExit(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise SystemExit(f"{field} must be finite and non-negative")
    return result


def _optional_number(value: object, *, field: str) -> float | None:
    if value is None:
        return None
    return _number(value, field=field)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _accepted(
    p1_root: Path,
    key: str,
    *,
    phase: str,
    detail: str,
) -> dict[str, Any]:
    pointer_path = p1_root / f"accepted/{key}.json"
    pointer = _read_json(pointer_path)
    if pointer.get("schema_version") != _ACCEPTED_SCHEMA:
        raise SystemExit(f"accepted pointer schema drift: {pointer_path}")
    if pointer.get("phase") != phase or pointer.get("detail") != detail:
        raise SystemExit(f"accepted pointer phase/detail drift: {pointer_path}")
    commit = pointer.get("handoff_commit")
    if not isinstance(commit, str) or len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit):
        raise SystemExit(f"accepted pointer handoff commit is invalid: {pointer_path}")
    primary_raw = pointer.get("primary_artifact")
    evidence_raw = pointer.get("operator_evidence")
    phase_meta_raw = pointer.get("phase_meta")
    if not isinstance(primary_raw, str) or not isinstance(evidence_raw, str):
        raise SystemExit(f"accepted pointer paths are invalid: {pointer_path}")
    primary = Path(primary_raw)
    evidence_path = Path(evidence_raw)
    if not primary.exists() or not evidence_path.is_file():
        raise SystemExit(f"accepted pointer target is unavailable: {pointer_path}")
    evidence = _read_json(evidence_path)
    if evidence.get("gate_status") != "passed" or evidence.get("command_rc") != 0 or evidence.get("postcheck_rc") != 0:
        raise SystemExit(f"accepted pointer does not reference passed operator evidence: {pointer_path}")
    if evidence.get("handoff_commit") != commit or evidence.get("phase") != phase or evidence.get("detail") != detail:
        raise SystemExit(f"accepted pointer operator evidence identity drift: {pointer_path}")
    phase_meta: Path | None = None
    if phase_meta_raw is not None:
        if not isinstance(phase_meta_raw, str):
            raise SystemExit(f"accepted pointer phase_meta is invalid: {pointer_path}")
        phase_meta = Path(phase_meta_raw)
        if not phase_meta.is_file():
            raise SystemExit(f"accepted pointer phase_meta is unavailable: {pointer_path}")
    return {
        **pointer,
        "pointer_path": str(pointer_path),
        "primary_path": primary,
        "phase_meta_path": phase_meta,
        "operator_evidence_path": evidence_path,
    }


def _metric_row(run_dir: Path) -> dict[str, Any]:
    rows = _read_jsonl(run_dir / "metrics.jsonl")
    candidates = [row for row in rows if "step_runtime_seconds" in row]
    if len(candidates) != 1:
        raise SystemExit(f"expected exactly one one-step trainer timing row: {run_dir}")
    return candidates[0]


def _phase_wall(path: Path | None) -> float:
    if path is None:
        raise SystemExit("phase wall metadata is required for this P1 artifact")
    value = _read_json(path)
    if value.get("return_code") != 0:
        raise SystemExit(f"phase did not complete successfully: {path}")
    return _number(value.get("wall_seconds"), field=f"{path} wall_seconds")


def _arm_summary(run_dir: Path, *, handoff_commit: str, phase_wall: float | None = None) -> dict[str, Any]:
    meta = _read_json(run_dir / "run.json")
    if meta.get("status") != "completed" or meta.get("global_step") != 1:
        raise SystemExit(f"GRPO P1 arm is not exactly one completed optimizer step: {run_dir}")
    if meta.get("git_commit") != handoff_commit:
        raise SystemExit(f"GRPO P1 run commit differs from its accepted handoff: {run_dir}")
    metrics = _metric_row(run_dir)
    group_rows = _read_jsonl(run_dir / "group_metrics.jsonl")
    if len(group_rows) != 1 or group_rows[0].get("sample_count") != 8:
        raise SystemExit(f"GRPO P1 arm must persist exactly one 8-sample problem group: {run_dir}")
    util = meta.get("runtime_utilization")
    if not isinstance(util, dict) or util.get("status") != "available":
        raise SystemExit(f"GRPO P1 runtime utilization unavailable: {run_dir}")
    checkpoint = run_dir / "checkpoints/checkpoint-1"
    required = (
        "adapter_config.json",
        "adapter_model.safetensors",
        "optimizer.pt",
        "scheduler.pt",
        "rng_state.pth",
        "trainer_state.json",
        "training_args.bin",
    )
    if not checkpoint.is_dir() or not all((checkpoint / name).is_file() for name in required):
        raise SystemExit(f"GRPO P1 checkpoint-1 is incomplete: {checkpoint}")
    adapter = _read_json(checkpoint / "adapter_config.json")
    targets = adapter.get("target_modules")
    if not isinstance(targets, list) or set(targets) != _QKVO_TARGETS:
        raise SystemExit(f"GRPO P1 checkpoint is not qkvo: {checkpoint}")
    attempts = meta.get("attempts")
    if not isinstance(attempts, list) or len(attempts) != 1 or not isinstance(attempts[0], dict):
        raise SystemExit(f"GRPO P1 must have one fresh attempt: {run_dir}")
    attempt_wall = _number(attempts[0].get("gpu_hours"), field="attempt gpu_hours") * 3600.0
    return {
        "run_dir": str(run_dir),
        "handoff_commit": handoff_commit,
        "reward_mode": meta.get("reward_mode"),
        "total_wall_seconds": phase_wall if phase_wall is not None else attempt_wall,
        "attempt_wall_seconds": attempt_wall,
        "step_runtime_seconds": _number(metrics.get("step_runtime_seconds"), field="step_runtime_seconds"),
        "generation_runtime_seconds": _number(
            metrics.get("vllm_generation_runtime_seconds"), field="vllm_generation_runtime_seconds"
        ),
        "rollout_runtime_seconds": _optional_number(
            metrics.get("rollout_runtime_seconds"), field="rollout_runtime_seconds"
        ),
        "reward_verification_wall_seconds": _number(
            group_rows[0].get("verifier_batch_wall_seconds"), field="verifier batch wall"
        ),
        "backward_runtime_seconds": _number(
            metrics.get("backward_runtime_total_seconds"), field="backward_runtime_total_seconds"
        ),
        "backward_calls": _number(metrics.get("backward_calls"), field="backward_calls"),
        "optimizer_runtime_seconds": _optional_number(
            metrics.get("optimizer_runtime_seconds"), field="optimizer_runtime_seconds"
        ),
        "gpu_utilization_mean_percent": _number(
            util.get("gpu_utilization_mean_percent"), field="gpu utilization mean"
        ),
        "gpu_utilization_p95_percent": _number(util.get("gpu_utilization_p95_percent"), field="gpu utilization p95"),
        "gpu_memory_used_mean_mib": _number(util.get("gpu_memory_used_mean_mib"), field="gpu memory mean"),
        "gpu_memory_used_max_mib": _number(util.get("gpu_memory_used_max_mib"), field="gpu memory max"),
        "torch_peak_allocated_mib": _number(meta.get("peak_cuda_memory_allocated_bytes"), field="peak allocated bytes")
        / (1024.0 * 1024.0),
        "torch_peak_reserved_mib": _number(meta.get("peak_cuda_memory_reserved_bytes"), field="peak reserved bytes")
        / (1024.0 * 1024.0),
        "oom": False,
        "vllm_weight_sync_error": False,
        "checkpoint_success": True,
    }


def _eval_summary(pointer: dict[str, Any], expected_ids: list[str], *, expected_parallel: int) -> dict[str, Any]:
    run_dir = pointer["primary_path"]
    assert isinstance(run_dir, Path)
    phase_meta = pointer["phase_meta_path"]
    assert phase_meta is None or isinstance(phase_meta, Path)
    handoff_commit = pointer["handoff_commit"]
    assert isinstance(handoff_commit, str)
    meta = _read_json(run_dir / "run.json")
    if meta.get("status") != "completed" or meta.get("total_problems") != 8 or meta.get("completed_records") != 8:
        raise SystemExit(f"eval P1 bundle is not exactly 8 completed problems: {run_dir}")
    if meta.get("batch_size") != 4 or meta.get("parallel_generators") != expected_parallel:
        raise SystemExit(f"eval P1 topology drift: {run_dir}")
    environment = _read_json(run_dir / "environment.json")
    if environment.get("project_commit") != handoff_commit:
        raise SystemExit(f"eval P1 commit differs from accepted handoff: {run_dir}")
    rows = _read_jsonl(run_dir / "samples/generations.jsonl")
    ids = [row.get("problem_id") for row in rows]
    if ids != expected_ids:
        raise SystemExit(f"eval P1 persisted order differs from canonical eval8: {run_dir}")
    util = meta.get("runtime_utilization")
    if not isinstance(util, dict) or util.get("status") != "available":
        raise SystemExit(f"eval P1 utilization unavailable: {run_dir}")
    generation_wall = _number(
        meta.get("invocation_generation_wall_seconds"), field="invocation_generation_wall_seconds"
    )
    return {
        "run_dir": str(run_dir),
        "handoff_commit": handoff_commit,
        "batch_size": 4,
        "parallel_generators": expected_parallel,
        "dedicated_cuda_streams": expected_parallel == 2,
        "total_wall_seconds": _phase_wall(phase_meta),
        "invocation_generation_wall_seconds": generation_wall,
        "problems_per_second": 8.0 / generation_wall if generation_wall > 0.0 else None,
        "gpu_utilization_mean_percent": _number(
            util.get("gpu_utilization_mean_percent"), field="eval gpu utilization mean"
        ),
        "gpu_utilization_p95_percent": _number(
            util.get("gpu_utilization_p95_percent"), field="eval gpu utilization p95"
        ),
        "gpu_memory_used_mean_mib": _number(util.get("gpu_memory_used_mean_mib"), field="eval gpu memory mean"),
        "gpu_memory_used_max_mib": _number(util.get("gpu_memory_used_max_mib"), field="eval gpu memory max"),
        "order_integrity": True,
        "completion_count": 8,
        "oom": False,
        "generation_error": False,
    }


def _only_run(root: Path, *, label: str) -> Path:
    if not root.is_dir():
        raise SystemExit(f"accepted concurrent {label} root is unavailable: {root}")
    candidates = sorted(path for path in root.iterdir() if path.is_dir())
    if len(candidates) != 1:
        raise SystemExit(f"accepted concurrent {label} root must contain exactly one run: {root}")
    return candidates[0]


def _concurrent_completed(
    p1_root: Path,
    tag: str,
    latest: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    pointer = _accepted(
        p1_root, f"concurrent-{tag}", phase="concurrent", detail={"m040": "0.40", "m030": "0.30", "m025": "0.25"}[tag]
    )
    root = pointer["primary_path"]
    assert isinstance(root, Path)
    result_path_raw = latest.get("result_path")
    if not isinstance(result_path_raw, str):
        raise SystemExit(f"latest concurrent {tag} result lacks result_path")
    result_path = Path(result_path_raw)
    if result_path.parent != root or _read_json(result_path) != latest:
        raise SystemExit(f"accepted concurrent {tag} result differs from latest measured result")
    if latest.get("handoff_commit") != pointer.get("handoff_commit"):
        raise SystemExit(f"accepted concurrent {tag} handoff commit differs from latest result")
    handoff_commit = pointer["handoff_commit"]
    assert isinstance(handoff_commit, str)
    public = _arm_summary(
        _only_run(root / "public/grpo", label="Public"),
        handoff_commit=handoff_commit,
    )
    hidden = _arm_summary(
        _only_run(root / "hidden/grpo", label="Hidden"),
        handoff_commit=handoff_commit,
    )
    return pointer, public, hidden


def _collect_commits(*values: object) -> list[str]:
    commits: set[str] = set()
    for value in values:
        if isinstance(value, dict):
            commit = value.get("handoff_commit")
            if isinstance(commit, str):
                commits.add(commit)
            commits.update(_collect_commits(*value.values()))
        elif isinstance(value, list):
            commits.update(_collect_commits(*value))
    return sorted(commits)


def build_report(p1_root: Path, eval8_dir: Path) -> dict[str, Any]:
    manifest_path = eval8_dir / "wp9d_p1_eval8_manifest.json"
    manifest = _read_json(manifest_path)
    ids = manifest.get("problem_ids")
    if (
        manifest.get("problem_count") != 8
        or not isinstance(ids, list)
        or len(ids) != 8
        or not all(isinstance(problem_id, str) for problem_id in ids)
    ):
        raise SystemExit("invalid eval8 systems manifest")

    public_pointer = _accepted(p1_root, "single-public", phase="single", detail="public")
    hidden_pointer = _accepted(p1_root, "single-hidden", phase="single", detail="hidden")
    public = _arm_summary(
        public_pointer["primary_path"],
        handoff_commit=public_pointer["handoff_commit"],
        phase_wall=_phase_wall(public_pointer["phase_meta_path"]),
    )
    hidden = _arm_summary(
        hidden_pointer["primary_path"],
        handoff_commit=hidden_pointer["handoff_commit"],
        phase_wall=_phase_wall(hidden_pointer["phase_meta_path"]),
    )
    sequential_estimate = public["total_wall_seconds"] + hidden["total_wall_seconds"]

    concurrent_attempts: list[dict[str, Any]] = []
    selected_concurrent: dict[str, Any] | None = None
    for tag in ("m040", "m030", "m025"):
        latest_path = p1_root / f"latest/concurrent-{tag}.json"
        if not latest_path.is_file():
            continue
        raw = _read_json(latest_path)
        latest_commit = raw.get("handoff_commit")
        if (
            not isinstance(latest_commit, str)
            or len(latest_commit) != 40
            or any(char not in "0123456789abcdef" for char in latest_commit)
        ):
            raise SystemExit(f"latest concurrent {tag} handoff commit is invalid")
        item: dict[str, Any] = {"tag": tag, **raw}
        if raw.get("reason_class") == "completed" and raw.get("public_rc") == 0 and raw.get("hidden_rc") == 0:
            pointer, pub_arm, hid_arm = _concurrent_completed(p1_root, tag, raw)
            wall = _number(raw.get("wall_seconds"), field="concurrent wall")
            speedup = sequential_estimate / wall if wall > 0.0 else 0.0
            headroom = _optional_number(raw.get("headroom_mib"), field="concurrent headroom")
            item.update(
                {
                    "handoff_commit": pointer["handoff_commit"],
                    "speedup": speedup,
                    "public": pub_arm,
                    "hidden": hid_arm,
                    "safe_headroom": headroom is not None and headroom >= SAFE_HEADROOM_MIB,
                    "material_speedup": speedup >= CONCURRENT_SPEEDUP_MIN,
                }
            )
            if selected_concurrent is None and item["safe_headroom"] and item["material_speedup"]:
                selected_concurrent = item
        concurrent_attempts.append(item)
    if not concurrent_attempts or concurrent_attempts[0]["tag"] != "m040":
        raise SystemExit("P1 requires a 0.40 concurrent attempt before runtime freeze")

    by_tag = {item["tag"]: item for item in concurrent_attempts}
    for current_tag, next_tag in (("m040", "m030"), ("m030", "m025")):
        current = by_tag.get(current_tag)
        if current is None:
            continue
        reason = current.get("reason_class")
        headroom = current.get("headroom_mib")
        needs_lower = reason == "memory_pressure" or (
            reason == "completed"
            and isinstance(headroom, int | float)
            and not isinstance(headroom, bool)
            and float(headroom) < SAFE_HEADROOM_MIB
        )
        if needs_lower and next_tag not in by_tag:
            raise SystemExit(
                f"{current_tag} requires the bounded next memory fraction {next_tag} before runtime freeze"
            )
        if reason == "other_failure":
            raise SystemExit(f"{current_tag} has unresolved non-memory failure; repair/retry before runtime freeze")
    last = by_tag.get("m025")
    if last is not None and last.get("reason_class") == "other_failure":
        raise SystemExit("m025 has unresolved non-memory failure; repair/retry before runtime freeze")

    if selected_concurrent is not None:
        grpo_execution = "concurrent"
        grpo_fraction = float(selected_concurrent["fraction"])
        concurrent_decision = "concurrent"
    else:
        grpo_execution = "sequential"
        grpo_fraction = 0.4
        concurrent_decision = "sequential"

    eval_single_pointer = _accepted(p1_root, "eval-single", phase="eval", detail="single")
    eval_dual_pointer = _accepted(p1_root, "eval-dual", phase="eval", detail="dual")
    eval_single = _eval_summary(eval_single_pointer, ids, expected_parallel=1)
    eval_dual = _eval_summary(eval_dual_pointer, ids, expected_parallel=2)
    eval_speedup = eval_single["total_wall_seconds"] / eval_dual["total_wall_seconds"]
    eval_generation_speedup = (
        eval_single["invocation_generation_wall_seconds"] / eval_dual["invocation_generation_wall_seconds"]
    )
    eval_decision = "dual" if eval_speedup > 1.0 else "single"

    report_core: dict[str, Any] = {
        "schema_version": _REPORT_SCHEMA,
        "evidence_class": "systems_validation_only",
        "single_arm": {"public": public, "hidden": hidden},
        "concurrent": {
            "sequential_estimate_seconds": sequential_estimate,
            "speedup_threshold": CONCURRENT_SPEEDUP_MIN,
            "safe_headroom_threshold_mib": SAFE_HEADROOM_MIB,
            "attempts": concurrent_attempts,
            "decision": concurrent_decision,
            "selected_memory_fraction": grpo_fraction,
        },
        "dual_b4": {
            "single": eval_single,
            "dual": eval_dual,
            "total_wall_speedup": eval_speedup,
            "generation_only_speedup": eval_generation_speedup,
            "order_integrity": True,
            "decision": eval_decision,
        },
        "runtime_freeze_candidate": {
            "GRPO": {
                "use_vllm": True,
                "vllm_mode": "colocate",
                "vllm_gpu_memory_utilization": grpo_fraction,
                "public_hidden_execution": grpo_execution,
                "num_generations": 8,
                "train_batch": 1,
                "grad_accum": 8,
                "lora_target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
                "lora_r": 16,
                "lora_alpha": 32,
                "lora_dropout": 0.05,
                "reward_workers": 8,
            },
            "Eval": {
                "batch_size": 4,
                "parallel_generators": 2 if eval_decision == "dual" else 1,
                "dedicated_cuda_streams": eval_decision == "dual",
                "verification_workers": 64,
            },
        },
        "key_config_sha256": {
            "wp9d-runtime-smoke-public.yaml": "6105bb2706460ee7460393205a10770a2004a93c53d2566197281138f0157723",
            "wp9d-runtime-smoke-hidden.yaml": "0e1b9efa674ef2fd10773f2aeeb34aa04579fd0f48de7d847c6785d00df5d4a8",
            "eval8_manifest": _sha256(manifest_path),
        },
        "eval8_order_sha256": manifest.get("ordered_problem_ids_sha256"),
        "stop_condition": "P1 complete; do not start B eval400 refresh or Recipe A in this invocation",
    }
    commits = _collect_commits(report_core)
    report_core["evidence_handoff_commits"] = commits
    report_core["all_evidence_same_handoff_commit"] = len(commits) == 1
    return report_core


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink(missing_ok=True)


def _persist_report(out: Path, report: dict[str, Any]) -> None:
    content = json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n"
    if out.exists():
        existing = out.read_text(encoding="utf-8")
        if existing == content:
            return
        history = out.parent / "history"
        history.mkdir(parents=True, exist_ok=True)
        old_sha = hashlib.sha256(existing.encode("utf-8")).hexdigest()
        archive = history / f"p1-runtime-report-{old_sha}.json"
        if archive.exists() and archive.read_text(encoding="utf-8") != existing:
            raise SystemExit("P1 report history hash collision")
        if not archive.exists():
            shutil.copy2(out, archive)
    _atomic_write(out, content)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--p1-root", type=Path, required=True)
    parser.add_argument("--eval8-dir", type=Path, required=True)
    args = parser.parse_args()
    report = build_report(args.p1_root, args.eval8_dir)
    out = args.p1_root / "report/p1-runtime-report.json"
    _persist_report(out, report)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
