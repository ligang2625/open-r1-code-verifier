#!/usr/bin/env python3
"""Freeze the WP9-c reduced calibrated pool from accepted initial+retry scores."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import statistics
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from code_verifier.data.deduplicate import stable_json_hash
from code_verifier.data.leakage_checks import (
    TrainingArtifactKind,
    build_training_record,
    check_training_record,
    load_training_artifact,
)
from code_verifier.data.prepare import load_canonical_jsonl
from code_verifier.data.schema import CodeProblem

SCHEMA = "wp9c-reduced-calibration-v1"
PROTOCOL = "wp9c-reduced-quota-current-viable-v1"
EXPECTED = {
    "c24_checkpoint_sha256": "48ac639cc3fba0c540437bfbba0b65403575f424c06eefd6b8c51d00771313f1",
    "c24_formal_problems_sha256": "d94c5216ef28272fb1e0ee0ec50667c423711d8587227a4feee84687c7509a6f",
    "c25_input_manifest_sha256": "bdccb68febe85f1da381ba01671fb220246dac9e74cdfacb89e4d1da7e334aff",
    "c25_input_records_sha256": "dbb6f18a472e390acbec641daab65db6d3f2cb07d3469f8e46ef2d90bf867d18",
    "c26_score_manifest_sha256": "b7333162acb0e24d7285d8ca9145b220c10636541db09f5fac531de670edd226",
    "c26_score_records_sha256": "b9c7ada9d21a2f3140eeb074248a4b306d49d14b8dcdc90b39e9e3692ffff08e",
    "c26_retry_problem_ids_sha256": "f0c03e55771bc86dd3f9966214ade7d34a9734cff133bdbdd1e6d1d8071c2eb5",
    "c27_generation_run_sha256": "824e92881d63d9d44f2c230f169d649077d21c957f7e02bcf1fdfa61362434d6",
    "c27_generation_records_sha256": "4f3a83f49821cb20952228f976577eab64664e076dc0c94483757e9c144e697d",
    "c28_checkpoint_sha256": "be4d28b0c79b460cc562f813b92e7dfdc49697e0462506900cc03219dd3d8473",
    "c28_score_manifest_sha256": "bcf02cce16217e575b5095c7af4f3ff54c4a689a6925323cb12cef6ab7008b77",
    "c28_score_records_sha256": "76b934b60876500a0a7f27dac48828f72c51cb39c08be57b490064b9cf866cca",
    "retry_problem_order_sha256": "1309b9f7cbbb4e488499a21026a87c3148284becd07a57672131e6f244dea0d3",
}
CLASS_NAMES = ("dual_informative", "public_only", "hidden_only", "dual_uninformative")
COUNT_FIELDS = (
    "parse_failure_count",
    "execution_failure_count",
    "timeout_count",
    "infrastructure_failure_count",
    "truncation_count",
)
REWARD_PREFIXES = ("public_test", "hidden_test", "public_total", "hidden_total")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(value: object, *, pretty: bool = False) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2 if pretty else None,
            separators=None if pretty else (",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode()


def _write_json(path: Path, value: object) -> str:
    content = _json_bytes(value, pretty=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, object]]) -> str:
    content = b"".join(_json_bytes(dict(row)) for row in rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def _load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return cast(dict[str, object], value)


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line:
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"expected JSON object at {path}:{line_number}")
        rows.append(cast(dict[str, object], value))
    return rows


def _require_sha(path: Path, expected: str, *, label: str) -> None:
    if not path.is_file() or _sha256(path) != expected:
        raise ValueError(f"{label} SHA256 drift: {path}")


def _stats(values: Sequence[float]) -> tuple[float, float]:
    if not values or any(not math.isfinite(value) for value in values):
        raise ValueError("calibration reward arrays must be finite and nonempty")
    return statistics.fmean(values), statistics.pstdev(values)


def _float_values(value: object) -> list[float]:
    if not isinstance(value, list):
        raise ValueError("calibration reward field must be an array")
    result: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int | float):
            raise ValueError("calibration rewards must be numeric")
        result.append(float(item))
    return result


def _classification(public_std: float, hidden_std: float) -> str:
    if public_std > 0.0 and hidden_std > 0.0:
        return "dual_informative"
    if public_std > 0.0:
        return "public_only"
    if hidden_std > 0.0:
        return "hidden_only"
    return "dual_uninformative"


def _merge_record(initial: Mapping[str, object], retry: Mapping[str, object] | None) -> dict[str, object]:
    result = dict(initial)
    if retry is not None:
        for prefix in REWARD_PREFIXES:
            field = f"{prefix}_rewards"
            left = initial.get(field)
            right = retry.get(field)
            if not isinstance(left, list) or not isinstance(right, list) or len(left) != 8 or len(right) != 8:
                raise ValueError("initial/retry reward arrays must each have length 8")
            values = [float(value) for value in (*left, *right)]
            mean, std = _stats(values)
            result[field] = values
            result[f"{prefix}_reward_mean"] = mean
            result[f"{prefix}_reward_std"] = std
        result["sample_indices"] = [
            *cast(list[object], initial["sample_indices"]),
            *cast(list[object], retry["sample_indices"]),
        ]
        result["completion_sha256"] = [
            *cast(list[object], initial["completion_sha256"]),
            *cast(list[object], retry["completion_sha256"]),
        ]
        for field in COUNT_FIELDS:
            result[field] = cast(int, initial[field]) + cast(int, retry[field])
        result["completion_token_max"] = max(
            cast(int, initial["completion_token_max"]), cast(int, retry["completion_token_max"])
        )
        result["completion_token_mean"] = statistics.fmean(
            (float(cast(float, initial["completion_token_mean"])), float(cast(float, retry["completion_token_mean"])))
        )

    public = _float_values(result["public_test_rewards"])
    hidden = _float_values(result["hidden_test_rewards"])
    _, public_std = _stats(public)
    _, hidden_std = _stats(hidden)
    result["public_informative"] = public_std > 0.0
    result["hidden_informative"] = hidden_std > 0.0
    result["calibration_class"] = _classification(public_std, hidden_std)
    result["public_all_test_correct"] = all(value == 1.0 for value in public)
    result["hidden_all_test_correct"] = all(value == 1.0 for value in hidden)
    result["public_all_test_zero"] = all(value == 0.0 for value in public)
    result["hidden_all_test_zero"] = all(value == 0.0 for value in hidden)
    result["public_full_pass_count"] = sum(value == 1.0 for value in public)
    result["hidden_full_pass_count"] = sum(value == 1.0 for value in hidden)
    return result


def _validate_merged_record(record: Mapping[str, object], *, retried: bool) -> None:
    sample_indices = record.get("sample_indices")
    expected_indices = list(range(16)) if retried else list(range(8))
    if sample_indices != expected_indices:
        raise ValueError("final calibration sample indices drift")
    completion_hashes = record.get("completion_sha256")
    if not isinstance(completion_hashes, list) or len(completion_hashes) != len(expected_indices):
        raise ValueError("final calibration completion identity length drift")
    for prefix in REWARD_PREFIXES:
        values_raw = record.get(f"{prefix}_rewards")
        if not isinstance(values_raw, list) or len(values_raw) != len(expected_indices):
            raise ValueError("final calibration reward array length drift")
        values = _float_values(values_raw)
        mean, std = _stats(values)
        if not math.isclose(float(cast(float, record[f"{prefix}_reward_mean"])), mean, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("final calibration reward mean drift")
        if not math.isclose(float(cast(float, record[f"{prefix}_reward_std"])), std, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("final calibration reward std drift")
    public = _float_values(record["public_test_rewards"])
    hidden = _float_values(record["hidden_test_rewards"])
    public_std = statistics.pstdev(public)
    hidden_std = statistics.pstdev(hidden)
    if record.get("calibration_class") != _classification(public_std, hidden_std):
        raise ValueError("final calibration class drift")
    if record.get("public_informative") is not (public_std > 0.0) or record.get("hidden_informative") is not (
        hidden_std > 0.0
    ):
        raise ValueError("final calibration informative flags drift")
    if record.get("public_all_test_correct") is not all(value == 1.0 for value in public):
        raise ValueError("final calibration public all-correct flag drift")
    if record.get("hidden_all_test_correct") is not all(value == 1.0 for value in hidden):
        raise ValueError("final calibration hidden all-correct flag drift")
    if record.get("public_all_test_zero") is not all(value == 0.0 for value in public):
        raise ValueError("final calibration public all-zero flag drift")
    if record.get("hidden_all_test_zero") is not all(value == 0.0 for value in hidden):
        raise ValueError("final calibration hidden all-zero flag drift")
    if record.get("public_full_pass_count") != sum(value == 1.0 for value in public):
        raise ValueError("final calibration public pass count drift")
    if record.get("hidden_full_pass_count") != sum(value == 1.0 for value in hidden):
        raise ValueError("final calibration hidden pass count drift")
    if any(not isinstance(record.get(field), int) or cast(int, record[field]) < 0 for field in COUNT_FIELDS):
        raise ValueError("final calibration telemetry count drift")
    if record.get("infrastructure_failure_count") != 0:
        raise ValueError("final calibration may not retain infrastructure failures")


def _disposition(record: Mapping[str, object], *, retried: bool) -> str:
    if record.get("quality_gate_required") is True:
        return "quality_gate_required"
    if record.get("calibration_class") != "dual_uninformative":
        return "eligible"
    if record.get("public_all_test_correct") is True and record.get("hidden_all_test_correct") is True:
        return "dual_saturated"
    if retried:
        return "dual_uninformative_after_16"
    return "dual_uninformative"


def _training_row(
    problem: CodeProblem, calibrated: Mapping[str, object], *, kind: TrainingArtifactKind
) -> dict[str, object]:
    row = cast(dict[str, object], build_training_record(problem, kind=kind))
    metadata = row.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("training metadata is not an object")
    row["metadata"] = {
        **metadata,
        "calibration_class": calibrated["calibration_class"],
        "calibration_record_sha256": calibrated["calibration_record_sha256"],
        "overlap_origin": calibrated["overlap_origin"],
    }
    check_training_record(row, kind=kind)
    return row


def freeze(args: argparse.Namespace) -> Path:
    output_dir = Path(args.output_dir)
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite C29 output: {output_dir}")

    c24_checkpoint = Path(args.c24_checkpoint)
    formal_path = Path(args.formal_problems)
    input_dir = Path(args.input_bundle_dir)
    initial_dir = Path(args.initial_score_dir)
    retry_dir = Path(args.retry_score_dir)
    c27_generation = Path(args.c27_generation_dir)
    c28_checkpoint = Path(args.c28_checkpoint)

    _require_sha(c24_checkpoint, EXPECTED["c24_checkpoint_sha256"], label="C24 checkpoint")
    _require_sha(formal_path, EXPECTED["c24_formal_problems_sha256"], label="C24 formal problems")
    _require_sha(input_dir / "input_manifest.json", EXPECTED["c25_input_manifest_sha256"], label="C25 input manifest")
    _require_sha(input_dir / "inputs.jsonl", EXPECTED["c25_input_records_sha256"], label="C25 input records")
    _require_sha(
        initial_dir / "score_manifest.json", EXPECTED["c26_score_manifest_sha256"], label="C26 score manifest"
    )
    _require_sha(
        initial_dir / "records/scoring.jsonl", EXPECTED["c26_score_records_sha256"], label="C26 score records"
    )
    retry_ids_path = initial_dir / "manifest/retry_problem_ids.jsonl"
    _require_sha(retry_ids_path, EXPECTED["c26_retry_problem_ids_sha256"], label="C26 retry IDs")
    _require_sha(c27_generation / "run.json", EXPECTED["c27_generation_run_sha256"], label="C27 generation run")
    _require_sha(
        c27_generation / "samples/generations.jsonl",
        EXPECTED["c27_generation_records_sha256"],
        label="C27 generation records",
    )
    _require_sha(c28_checkpoint, EXPECTED["c28_checkpoint_sha256"], label="C28 checkpoint")
    _require_sha(retry_dir / "score_manifest.json", EXPECTED["c28_score_manifest_sha256"], label="C28 score manifest")
    _require_sha(retry_dir / "records/scoring.jsonl", EXPECTED["c28_score_records_sha256"], label="C28 score records")

    c24 = _load_json(c24_checkpoint)
    if c24.get("status") != "completed_verified" or c24.get("protocol_amendment") != PROTOCOL:
        raise ValueError("C24 authority drift")
    initial_manifest = _load_json(initial_dir / "score_manifest.json")
    retry_manifest = _load_json(retry_dir / "score_manifest.json")
    if initial_manifest.get("status") != "completed" or initial_manifest.get("block_index") != 0:
        raise ValueError("C26 initial score manifest drift")
    if retry_manifest.get("status") != "completed" or retry_manifest.get("block_index") != 1:
        raise ValueError("C28 retry score manifest drift")
    if initial_manifest.get("sft_checkpoint") != retry_manifest.get("sft_checkpoint"):
        raise ValueError("initial/retry frozen-B identity differs")
    if initial_manifest.get("public_definition_sha256") != retry_manifest.get("public_definition_sha256"):
        raise ValueError("initial/retry Public definition differs")
    if initial_manifest.get("hidden_definition_sha256") != retry_manifest.get("hidden_definition_sha256"):
        raise ValueError("initial/retry Hidden definition differs")
    if retry_manifest.get("problem_count") != 195 or retry_manifest.get("retry_problem_count") != 0:
        raise ValueError("C28 retry scoring population drift")

    input_rows = _load_jsonl(input_dir / "inputs.jsonl")
    initial_rows = _load_jsonl(initial_dir / "records/scoring.jsonl")
    retry_rows = _load_jsonl(retry_dir / "records/scoring.jsonl")
    retry_ids = [cast(str, row["problem_id"]) for row in _load_jsonl(retry_ids_path)]
    formal = load_canonical_jsonl(formal_path)
    if len(input_rows) != len(initial_rows) or len(initial_rows) != len(formal) or len(formal) != 1602:
        raise ValueError("C29 authority population must be exact 1602")
    input_ids = [cast(str, row["problem_id"]) for row in input_rows]
    initial_ids = [cast(str, row["problem_id"]) for row in initial_rows]
    formal_ids = [problem.problem_id for problem in formal]
    if input_ids != initial_ids or initial_ids != formal_ids or len(set(initial_ids)) != 1602:
        raise ValueError("C29 authority problem order drift")
    if len(retry_ids) != 195 or retry_ids != sorted(retry_ids) or len(set(retry_ids)) != 195:
        raise ValueError("C29 retry ID count/order/uniqueness drift")
    if stable_json_hash(retry_ids) != EXPECTED["retry_problem_order_sha256"]:
        raise ValueError("C29 retry order hash drift")
    retry_record_ids = [cast(str, row["problem_id"]) for row in retry_rows]
    if retry_record_ids != retry_ids:
        raise ValueError("C28 score rows do not exactly match the C26 retry IDs")

    input_by_id = {cast(str, row["problem_id"]): row for row in input_rows}
    retry_by_id = {cast(str, row["problem_id"]): row for row in retry_rows}
    formal_by_id = {problem.problem_id: problem for problem in formal}
    final_rows: list[dict[str, object]] = []
    active_rows: list[dict[str, object]] = []
    excluded_rows: list[dict[str, object]] = []
    disposition_counts: Counter[str] = Counter()
    class_counts: Counter[str] = Counter()

    for initial in initial_rows:
        problem_id = cast(str, initial["problem_id"])
        input_row = input_by_id[problem_id]
        if (
            initial.get("source_name") != input_row.get("source_name")
            or initial.get("difficulty") != input_row.get("difficulty")
            or initial.get("overlap_origin") != "external_new"
            or initial.get("quality_gate_required") is not False
        ):
            raise ValueError("C29 initial score identity metadata drift")
        retry = retry_by_id.get(problem_id)
        merged = _merge_record(initial, retry)
        _validate_merged_record(merged, retried=retry is not None)
        disposition = _disposition(merged, retried=retry is not None)
        merged["calibration_record_sha256"] = stable_json_hash(merged)
        class_name = cast(str, merged["calibration_class"])
        class_counts[class_name] += 1
        disposition_counts[disposition] += 1
        final_rows.append(merged)
        if disposition == "eligible":
            active_rows.append(merged)
        else:
            excluded_rows.append(
                {
                    "problem_id": problem_id,
                    "reason": disposition,
                    "retried": retry is not None,
                    "calibration_class": class_name,
                    "calibration_record_sha256": merged["calibration_record_sha256"],
                }
            )

    if set(class_counts) - set(CLASS_NAMES) or sum(class_counts.values()) != 1602:
        raise ValueError("C29 final class accounting drift")
    if any(row["calibration_class"] == "dual_uninformative" for row in active_rows):
        raise ValueError("C29 active population contains dual-uninformative records")
    if any(row["calibration_class"] != "dual_uninformative" for row in final_rows if row not in active_rows):
        raise ValueError("C29 excluded population contains an informative record")
    if len(active_rows) + len(excluded_rows) != 1602:
        raise ValueError("C29 final disposition accounting drift")

    active_ids = [cast(str, row["problem_id"]) for row in active_rows]
    record_by_id = {cast(str, row["problem_id"]): row for row in active_rows}
    public_training = [
        _training_row(formal_by_id[problem_id], record_by_id[problem_id], kind=TrainingArtifactKind.PUBLIC_GRPO)
        for problem_id in active_ids
    ]
    hidden_training = [
        _training_row(formal_by_id[problem_id], record_by_id[problem_id], kind=TrainingArtifactKind.HIDDEN_GRPO)
        for problem_id in active_ids
    ]

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        artifacts: dict[str, str] = {}
        artifacts["records/calibration.jsonl"] = _write_jsonl(temporary / "records/calibration.jsonl", final_rows)
        artifacts["manifest/retry_problem_ids.jsonl"] = _write_jsonl(
            temporary / "manifest/retry_problem_ids.jsonl", [{"problem_id": problem_id} for problem_id in retry_ids]
        )
        selection_rows = [
            {
                "ordinal": ordinal,
                "problem_id": cast(str, row["problem_id"]),
                "calibration_class": row["calibration_class"],
                "calibration_record_sha256": row["calibration_record_sha256"],
                "overlap_origin": row["overlap_origin"],
            }
            for ordinal, row in enumerate(active_rows)
        ]
        artifacts["manifest/active_selection.jsonl"] = _write_jsonl(
            temporary / "manifest/active_selection.jsonl", selection_rows
        )
        artifacts["manifest/problem_order.jsonl"] = _write_jsonl(
            temporary / "manifest/problem_order.jsonl",
            [{"ordinal": ordinal, "problem_id": problem_id} for ordinal, problem_id in enumerate(active_ids)],
        )
        artifacts["manifest/excluded_dual_uninformative.jsonl"] = _write_jsonl(
            temporary / "manifest/excluded_dual_uninformative.jsonl", excluded_rows
        )
        artifacts["training/public_grpo.jsonl"] = _write_jsonl(
            temporary / "training/public_grpo.jsonl", public_training
        )
        artifacts["training/hidden_grpo.jsonl"] = _write_jsonl(
            temporary / "training/hidden_grpo.jsonl", hidden_training
        )
        class_report = {name: class_counts.get(name, 0) for name in CLASS_NAMES}
        disposition_report = dict(sorted(disposition_counts.items()))
        active_class_counts = Counter(cast(str, row["calibration_class"]) for row in active_rows)
        composition = {
            "precalibration_problem_count": 1602,
            "retry_problem_count": len(retry_ids),
            "active_problem_count": len(active_rows),
            "excluded_dual_uninformative_count": len(excluded_rows),
            "class_counts": class_report,
            "active_class_counts": {name: active_class_counts.get(name, 0) for name in CLASS_NAMES},
            "disposition_counts": disposition_report,
            "backfill_performed": False,
            "minimum_pool_count": None,
        }
        artifacts["reports/classification_summary.json"] = _write_json(
            temporary / "reports/classification_summary.json", class_report
        )
        artifacts["reports/disposition_summary.json"] = _write_json(
            temporary / "reports/disposition_summary.json", disposition_report
        )
        artifacts["reports/pool_composition.json"] = _write_json(
            temporary / "reports/pool_composition.json", composition
        )
        manifest = {
            "schema_version": SCHEMA,
            "protocol_amendment": PROTOCOL,
            "status": "completed",
            "evidence_class": "formal_calibration",
            "seed": 42,
            "post_calibration_rule": "report actual class counts; exclude dual_uninformative without backfill",
            "source_expansion_allowed": False,
            "backfill_performed": False,
            "minimum_pool_count": None,
            "precalibration_problem_count": 1602,
            "calibrated_problem_count": 1602,
            "retry_problem_count": len(retry_ids),
            "active_problem_count": len(active_rows),
            "excluded_dual_uninformative_count": len(excluded_rows),
            "calibrated_problem_order_sha256": stable_json_hash(initial_ids),
            "active_order_sha256": stable_json_hash(active_ids),
            "class_counts": class_report,
            "active_class_counts": {name: active_class_counts.get(name, 0) for name in CLASS_NAMES},
            "disposition_counts": disposition_report,
            "sft_checkpoint": initial_manifest["sft_checkpoint"],
            "public_definition_sha256": initial_manifest["public_definition_sha256"],
            "hidden_definition_sha256": initial_manifest["hidden_definition_sha256"],
            "bindings": EXPECTED,
            "artifacts": artifacts,
        }
        _write_json(temporary / "calibration_manifest.json", manifest)
        os.replace(temporary, output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    check(output_dir, formal_path=formal_path)
    return output_dir


def check(pool_dir: Path, *, formal_path: Path) -> dict[str, object]:
    manifest = _load_json(pool_dir / "calibration_manifest.json")
    if (
        manifest.get("schema_version") != SCHEMA
        or manifest.get("protocol_amendment") != PROTOCOL
        or manifest.get("status") != "completed"
        or manifest.get("evidence_class") != "formal_calibration"
        or manifest.get("backfill_performed") is not False
        or manifest.get("minimum_pool_count") is not None
    ):
        raise ValueError("C29 calibration manifest identity drift")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("C29 artifact inventory is invalid")
    expected_files = {Path(relative) for relative in artifacts} | {Path("calibration_manifest.json")}
    actual_files = {path.relative_to(pool_dir) for path in pool_dir.rglob("*") if path.is_file()}
    if actual_files != expected_files:
        raise ValueError("C29 artifact tree differs from exact manifest inventory")
    for relative, expected_sha in artifacts.items():
        if (
            not isinstance(relative, str)
            or not isinstance(expected_sha, str)
            or _sha256(pool_dir / relative) != expected_sha
        ):
            raise ValueError(f"C29 artifact hash drift: {relative}")

    records = _load_jsonl(pool_dir / "records/calibration.jsonl")
    retry_ids = [cast(str, row["problem_id"]) for row in _load_jsonl(pool_dir / "manifest/retry_problem_ids.jsonl")]
    retry_set = set(retry_ids)
    if len(records) != 1602 or len(retry_ids) != 195:
        raise ValueError("C29 record/retry count drift")
    record_ids = [cast(str, row["problem_id"]) for row in records]
    if manifest.get("calibrated_problem_order_sha256") != stable_json_hash(record_ids):
        raise ValueError("C29 calibrated problem order drift")
    for record in records:
        problem_id = cast(str, record["problem_id"])
        record_hash = record.get("calibration_record_sha256")
        raw = dict(record)
        raw.pop("calibration_record_sha256", None)
        if record_hash != stable_json_hash(raw):
            raise ValueError("C29 calibration record hash drift")
        _validate_merged_record(raw, retried=problem_id in retry_set)

    class_counts = Counter(cast(str, record["calibration_class"]) for record in records)
    class_report = _load_json(pool_dir / "reports/classification_summary.json")
    expected_class_report = {name: class_counts.get(name, 0) for name in CLASS_NAMES}
    if class_report != expected_class_report or manifest.get("class_counts") != expected_class_report:
        raise ValueError("C29 classification summary does not recompute")

    active_selection = _load_jsonl(pool_dir / "manifest/active_selection.jsonl")
    active_ids = [cast(str, row["problem_id"]) for row in active_selection]
    expected_active = [
        cast(str, record["problem_id"]) for record in records if record["calibration_class"] != "dual_uninformative"
    ]
    if active_ids != expected_active or manifest.get("active_order_sha256") != stable_json_hash(active_ids):
        raise ValueError("C29 active informative order does not recompute")
    if manifest.get("active_problem_count") != len(active_ids):
        raise ValueError("C29 active count drift")

    excluded = _load_jsonl(pool_dir / "manifest/excluded_dual_uninformative.jsonl")
    expected_excluded = [record for record in records if record["calibration_class"] == "dual_uninformative"]
    if len(excluded) != len(expected_excluded) or manifest.get("excluded_dual_uninformative_count") != len(excluded):
        raise ValueError("C29 excluded dual-uninformative count drift")
    disposition_counts: Counter[str] = Counter()
    for record in records:
        problem_id = cast(str, record["problem_id"])
        disposition_counts[_disposition(record, retried=problem_id in retry_set)] += 1
    disposition_report = _load_json(pool_dir / "reports/disposition_summary.json")
    if (
        disposition_report != dict(sorted(disposition_counts.items()))
        or manifest.get("disposition_counts") != disposition_report
    ):
        raise ValueError("C29 disposition summary does not recompute")

    public = load_training_artifact(pool_dir / "training/public_grpo.jsonl", kind=TrainingArtifactKind.PUBLIC_GRPO)
    hidden = load_training_artifact(pool_dir / "training/hidden_grpo.jsonl", kind=TrainingArtifactKind.HIDDEN_GRPO)
    if [row["problem_id"] for row in public] != active_ids or [row["problem_id"] for row in hidden] != active_ids:
        raise ValueError("C29 Public/Hidden training order differs from active order")
    record_by_id = {cast(str, row["problem_id"]): row for row in records}
    formal_by_id = {problem.problem_id: problem for problem in load_canonical_jsonl(formal_path)}
    for public_row, hidden_row in zip(public, hidden, strict=True):
        problem_id = cast(str, public_row["problem_id"])
        calibrated = record_by_id[problem_id]
        expected_public = _training_row(formal_by_id[problem_id], calibrated, kind=TrainingArtifactKind.PUBLIC_GRPO)
        expected_hidden = _training_row(formal_by_id[problem_id], calibrated, kind=TrainingArtifactKind.HIDDEN_GRPO)
        if public_row != expected_public or hidden_row != expected_hidden:
            raise ValueError("C29 training view does not match canonical formal problem + calibration metadata")

    composition = _load_json(pool_dir / "reports/pool_composition.json")
    if composition.get("active_problem_count") != len(active_ids) or composition.get(
        "excluded_dual_uninformative_count"
    ) != len(excluded):
        raise ValueError("C29 pool composition drift")
    return manifest


def _parser() -> argparse.ArgumentParser:
    root = Path(__file__).resolve().parents[6]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--c24-checkpoint",
        default=str(root / "ai-work/executor/operator/WP9-c/wp9c-final-reduced-pool/C24/checkpoint.json"),
    )
    parser.add_argument(
        "--formal-problems", default="/home/dzy/wp9c-final-reduced-pool-C24/external_formal_problems.jsonl"
    )
    parser.add_argument("--input-bundle-dir", default="/home/dzy/wp9c-fresh-calibration-input-C25")
    parser.add_argument("--initial-score-dir", default="/home/dzy/wp9c-fresh-reduced-calibration-score-C26")
    parser.add_argument("--c27-generation-dir", default="/home/dzy/wp9c-fresh-calibration-retry-generation-C27")
    parser.add_argument(
        "--c28-checkpoint",
        default=str(
            root / "ai-work/executor/operator/WP9-c/wp9c-fresh-reduced-calibration-retry-scoring/C28/checkpoint.json"
        ),
    )
    parser.add_argument("--retry-score-dir", default="/home/dzy/wp9c-fresh-reduced-calibration-retry-score-C28")
    parser.add_argument("--output-dir", default="/home/dzy/wp9c-final-reduced-calibration-C29")
    parser.add_argument("--check-only", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.check_only:
        manifest = check(Path(args.output_dir), formal_path=Path(args.formal_problems))
    else:
        output = freeze(args)
        manifest = check(output, formal_path=Path(args.formal_problems))
    print(
        json.dumps(
            {
                "status": "C29_FINAL_REDUCED_CALIBRATION_OK",
                "active_problem_count": manifest["active_problem_count"],
                "excluded_dual_uninformative_count": manifest["excluded_dual_uninformative_count"],
                "class_counts": manifest["class_counts"],
                "active_class_counts": manifest["active_class_counts"],
                "disposition_counts": manifest["disposition_counts"],
                "active_order_sha256": manifest["active_order_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
