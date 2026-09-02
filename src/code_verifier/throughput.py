"""Artifact-derived WP9 refresh throughput and deterministic parity reports."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml

from code_verifier.data.json_strict import StrictJsonError, loads_strict
from code_verifier.evaluation.staged import load_generation_bundle_records

_BENCHMARK_VERSION = "wp9b-refresh-benchmark-v1"


class ThroughputError(RuntimeError):
    """Raised when benchmark source artifacts do not prove a valid comparison."""


@dataclass(frozen=True)
class GenerationParity:
    exact: bool
    reason: str | None
    problem_count: int


@dataclass(frozen=True)
class RefreshBenchmarkSummary:
    report_dir: Path
    report_path: Path
    selected_eval_generation_batch_size: int
    evidence_class: str


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise ThroughputError(f"benchmark artifact is unreadable: {path.name}") from error


def _json(path: Path) -> dict[str, object]:
    try:
        value = loads_strict(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, StrictJsonError) as error:
        raise ThroughputError(f"benchmark artifact is invalid: {path.name}") from error
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ThroughputError(f"benchmark artifact must contain an object: {path.name}")
    return cast(dict[str, object], value)


def _completed_bundle(run_dir: Path) -> tuple[dict[str, object], Path]:
    metadata = _json(run_dir / "run.json")
    records_path = run_dir / "samples" / "generations.jsonl"
    if metadata.get("status") != "completed" or metadata.get("artifact_type") != "evaluation_generation_bundle":
        raise ThroughputError("benchmark generation bundle must be completed")
    if metadata.get("records_sha256") != _sha256(records_path):
        raise ThroughputError("benchmark generation bundle records hash mismatch")
    records = load_generation_bundle_records(records_path)
    if metadata.get("completed_records") != len(records) or metadata.get("total_problems") != len(records):
        raise ThroughputError("benchmark generation bundle is incomplete")
    return metadata, records_path


def compare_generation_bundle_parity(baseline_run_dir: Path, candidate_run_dir: Path) -> GenerationParity:
    """Compare exact deterministic outputs while ignoring operational run/batch identity."""
    baseline_meta, baseline_path = _completed_bundle(baseline_run_dir)
    candidate_meta, candidate_path = _completed_bundle(candidate_run_dir)
    identity_fields = ("model_id", "model_revision", "checkpoint", "dataset_hash", "seed")
    if any(baseline_meta.get(field) != candidate_meta.get(field) for field in identity_fields):
        return GenerationParity(False, "source_identity_mismatch", 0)
    baseline = load_generation_bundle_records(baseline_path)
    candidate = load_generation_bundle_records(candidate_path)
    if len(baseline) != len(candidate):
        return GenerationParity(False, "problem_count_mismatch", min(len(baseline), len(candidate)))
    for left, right in zip(baseline, candidate, strict=True):
        if left.problem_id != right.problem_id or left.prompt_hash != right.prompt_hash:
            return GenerationParity(False, "problem_order_mismatch", len(baseline))
        if (
            left.completion != right.completion
            or left.completion_tokens != right.completion_tokens
            or left.hit_max_new_tokens != right.hit_max_new_tokens
        ):
            return GenerationParity(False, "generation_output_mismatch", len(baseline))
    return GenerationParity(True, None, len(baseline))


def _bundle_metrics(run_dir: Path) -> dict[str, object]:
    metadata, records_path = _completed_bundle(run_dir)
    records = load_generation_bundle_records(records_path)
    batch_size = metadata.get("batch_size", 1)
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size not in {1, 2, 4, 8, 16}:
        raise ThroughputError("benchmark bundle batch_size is invalid")
    latency_seconds = sum(record.generation_latency_ms for record in records) / 1000.0
    tokens = sum(record.completion_tokens for record in records)
    if latency_seconds <= 0 or tokens < 0:
        raise ThroughputError("benchmark bundle has invalid persisted timing/token accounting")
    tokens_per_second = tokens / latency_seconds
    if not math.isfinite(tokens_per_second):
        raise ThroughputError("benchmark bundle throughput is non-finite")
    return {
        "batch_size": batch_size,
        "problem_count": len(records),
        "completion_tokens": tokens,
        "generation_wall_seconds": latency_seconds,
        "tokens_per_second": tokens_per_second,
        "run_manifest_sha256": _sha256(run_dir / "run.json"),
        "records_sha256": _sha256(records_path),
    }


def summarize_refresh_benchmarks(manifest_path: Path, *, output_dir: Path) -> RefreshBenchmarkSummary:
    """Select an exact-parity eval batch using only strict completed bundle artifacts."""
    try:
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ThroughputError("benchmark manifest is unreadable") from error
    if not isinstance(raw, dict) or set(raw) != {"version", "evidence_class", "eval_generation"}:
        raise ThroughputError("benchmark manifest fields are invalid")
    if raw.get("version") != _BENCHMARK_VERSION or raw.get("evidence_class") not in {"engineering", "formal"}:
        raise ThroughputError("benchmark manifest identity is invalid")
    generation = raw.get("eval_generation")
    if not isinstance(generation, dict) or set(generation) != {"baseline", "candidates"}:
        raise ThroughputError("eval generation benchmark declaration is invalid")
    baseline_raw = generation.get("baseline")
    candidates_raw = generation.get("candidates")
    if not isinstance(baseline_raw, str) or not isinstance(candidates_raw, list) or not candidates_raw:
        raise ThroughputError("eval generation benchmark paths are invalid")
    if any(not isinstance(item, str) for item in candidates_raw):
        raise ThroughputError("eval generation benchmark candidate paths are invalid")
    baseline = Path(baseline_raw)
    baseline_metrics = _bundle_metrics(baseline)
    if baseline_metrics["batch_size"] != 1:
        raise ThroughputError("eval generation baseline must use batch_size=1")
    candidates: list[dict[str, object]] = []
    for raw_path in cast(list[str], candidates_raw):
        path = Path(raw_path)
        metrics = _bundle_metrics(path)
        parity = compare_generation_bundle_parity(baseline, path)
        candidates.append({"path": raw_path, **metrics, "exact_parity": parity.exact, "rejection": parity.reason})
    baseline_rate = cast(float, baseline_metrics["tokens_per_second"])
    eligible = [
        item
        for item in candidates
        if item["exact_parity"] is True and cast(float, item["tokens_per_second"]) >= baseline_rate
    ]
    selected = (
        min(
            eligible,
            key=lambda item: (-cast(float, item["tokens_per_second"]), cast(int, item["batch_size"])),
        )
        if eligible
        else {"batch_size": 1, **baseline_metrics}
    )
    report = {
        "version": _BENCHMARK_VERSION,
        "evidence_class": raw["evidence_class"],
        "source_manifest_sha256": _sha256(manifest_path),
        "baseline": {"path": baseline_raw, **baseline_metrics},
        "candidates": candidates,
        "selected_eval_generation_batch_size": selected["batch_size"],
    }
    if output_dir.exists():
        raise ThroughputError("benchmark output directory must not already exist")
    output_dir.mkdir(parents=True)
    report_path = output_dir / "refresh_benchmark_report.json"
    encoded = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output_dir, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, report_path)
    return RefreshBenchmarkSummary(
        report_dir=output_dir,
        report_path=report_path,
        selected_eval_generation_batch_size=cast(int, selected["batch_size"]),
        evidence_class=cast(str, raw["evidence_class"]),
    )
