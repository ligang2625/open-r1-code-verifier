"""End-to-end acceptance tests for the committed WP1 smoke dataset."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest

from code_verifier.cli import main
from code_verifier.data.prepare import load_hf_dataset

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SMOKE_CONFIG = REPOSITORY_ROOT / "configs" / "data" / "smoke.yaml"


def _prepare(output_dir: Path, monkeypatch: pytest.MonkeyPatch, *, seed: int = 42) -> None:
    monkeypatch.chdir(REPOSITORY_ROOT)
    exit_code = main(
        [
            "prepare-data",
            "--config",
            str(SMOKE_CONFIG),
            "--seed",
            str(seed),
            "--output-dir",
            str(output_dir),
            "--log-level",
            "INFO",
        ]
    )
    assert exit_code == 0


def _check(output_dir: Path, monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.chdir(REPOSITORY_ROOT)
    return main(
        [
            "check-data",
            "--dataset",
            str(output_dir),
            "--seed",
            "42",
            "--output-dir",
            str(output_dir.parent / "check-output"),
            "--log-level",
            "INFO",
        ]
    )


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value: object = json.loads(line)
        assert isinstance(value, dict)
        assert all(isinstance(key, str) for key in value)
        records.append(cast(dict[str, object], value))
    return records


def _contains_key(value: object, forbidden: str) -> bool:
    if isinstance(value, Mapping):
        return any(key == forbidden or _contains_key(nested, forbidden) for key, nested in value.items())
    if isinstance(value, list):
        return any(_contains_key(item, forbidden) for item in value)
    return False


def test_wp1_smoke_pipeline_exports_twenty_problems(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run prepare-data and check-data over the committed 20-problem fixture."""
    from datasets import load_from_disk  # type: ignore[import-untyped]

    output_dir = tmp_path / "prepared"
    _prepare(output_dir, monkeypatch)

    assert _check(output_dir, monkeypatch) == 0
    canonical_records = _read_jsonl(output_dir / "canonical" / "problems.jsonl")
    assert len(canonical_records) == 20
    assert Counter(cast(str, record["split"]) for record in canonical_records) == Counter(
        {"train": 12, "validation": 4, "test": 4}
    )
    assert len(load_from_disk(str(output_dir / "hf_dataset"))) == 20
    assert len(load_hf_dataset(output_dir / "hf_dataset")) == 20

    for record in canonical_records:
        all_tests: list[object] = []
        for layer in ("visible_tests", "train_hidden_tests", "eval_hidden_tests"):
            tests = cast(list[object], record[layer])
            assert len(tests) == 2
            all_tests.extend(tests)
        normalized = {json.dumps(test, ensure_ascii=False, sort_keys=True) for test in all_tests}
        assert len(normalized) == 6

    for artifact_name in ("sft.jsonl", "public_grpo.jsonl", "hidden_grpo.jsonl"):
        assert len(_read_jsonl(output_dir / "training" / artifact_name)) == 12


def test_wp1_training_artifacts_never_contain_eval_hidden_tests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scan serialized training bytes and structured records for forbidden eval fields."""
    output_dir = tmp_path / "prepared"
    _prepare(output_dir, monkeypatch)

    training_dir = output_dir / "training"
    for path in training_dir.glob("*.jsonl"):
        assert b"eval_hidden_tests" not in path.read_bytes()
        assert all(not _contains_key(record, "eval_hidden_tests") for record in _read_jsonl(path))

    public_records = _read_jsonl(training_dir / "public_grpo.jsonl")
    assert all("train_hidden_tests" not in record for record in public_records)
    sft_records = _read_jsonl(training_dir / "sft.jsonl")
    assert all("visible_tests" in record for record in sft_records)
    assert all("Function signature:" in cast(str, record["prompt"]) for record in sft_records)
    assert all("Visible examples:" in cast(str, record["prompt"]) for record in sft_records)
    assert all(
        not any(field in record for field in ("train_hidden_tests", "eval_hidden_tests", "reference_solution"))
        for record in sft_records
    )


def test_wp1_tampered_training_artifacts_fail_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Require check-data to reject structural and content-level training artifact tampering."""
    deleted_dir = tmp_path / "deleted-field"
    mixed_dir = tmp_path / "mixed-field"
    renamed_dir = tmp_path / "renamed-eval-content"
    _prepare(deleted_dir, monkeypatch)
    _prepare(mixed_dir, monkeypatch)
    _prepare(renamed_dir, monkeypatch)

    sft_path = deleted_dir / "training" / "sft.jsonl"
    sft_records = _read_jsonl(sft_path)
    del sft_records[0]["prompt"]
    sft_path.write_text("".join(f"{json.dumps(record)}\n" for record in sft_records), encoding="utf-8")
    assert _check(deleted_dir, monkeypatch) == 2

    hidden_path = mixed_dir / "training" / "hidden_grpo.jsonl"
    hidden_records = _read_jsonl(hidden_path)
    hidden_records[0]["eval_hidden_tests"] = []
    hidden_path.write_text("".join(f"{json.dumps(record)}\n" for record in hidden_records), encoding="utf-8")
    assert _check(mixed_dir, monkeypatch) == 2

    canonical_records = _read_jsonl(renamed_dir / "canonical" / "problems.jsonl")
    canonical_by_id = {cast(str, record["problem_id"]): record for record in canonical_records}
    public_path = renamed_dir / "training" / "public_grpo.jsonl"
    public_records = _read_jsonl(public_path)
    first_problem_id = cast(str, public_records[0]["problem_id"])
    public_records[0]["visible_tests"] = canonical_by_id[first_problem_id]["eval_hidden_tests"]
    public_path.write_text("".join(f"{json.dumps(record)}\n" for record in public_records), encoding="utf-8")
    assert _check(renamed_dir, monkeypatch) == 2


def test_wp1_duplicate_key_cannot_hide_eval_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Require check-data to reject duplicate JSON keys that could hide eval content."""
    output_dir = tmp_path / "prepared"
    _prepare(output_dir, monkeypatch)

    artifact = output_dir / "training" / "public_grpo.jsonl"
    lines = artifact.read_text(encoding="utf-8").splitlines()
    canonical_records = _read_jsonl(output_dir / "canonical" / "problems.jsonl")
    canonical_by_id = {cast(str, record["problem_id"]): record for record in canonical_records}
    first = json.loads(lines[0])
    eval_layer = json.dumps(canonical_by_id[cast(str, first["problem_id"])]["eval_hidden_tests"])
    marker = '"visible_tests":'
    index = lines[0].index(marker)
    lines[0] = lines[0][:index] + marker + eval_layer + "," + lines[0][index:]
    artifact.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")

    assert _check(output_dir, monkeypatch) == 2
    captured = capsys.readouterr()
    assert "duplicate JSON key" in captured.err
    assert "eval_hidden_tests" not in captured.err


def test_wp1_json_number_type_drift_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Require check-data to reject int/float type drift in training records."""
    output_dir = tmp_path / "prepared"
    _prepare(output_dir, monkeypatch)

    artifact = output_dir / "training" / "public_grpo.jsonl"
    records = _read_jsonl(artifact)
    metadata = cast(dict[str, object], records[0]["metadata"])
    metadata["memory_limit_mb"] = float(cast(int, metadata["memory_limit_mb"]))
    artifact.write_text("".join(f"{json.dumps(record)}\n" for record in records), encoding="utf-8")

    assert _check(output_dir, monkeypatch) == 2


def test_wp1_same_seed_is_reproducible(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Require two end-to-end exports to have identical canonical JSONL digests."""
    first = tmp_path / "first"
    second = tmp_path / "second"
    _prepare(first, monkeypatch)
    _prepare(second, monkeypatch)

    first_digest = hashlib.sha256((first / "canonical" / "problems.jsonl").read_bytes()).digest()
    second_digest = hashlib.sha256((second / "canonical" / "problems.jsonl").read_bytes()).digest()
    assert first_digest == second_digest
