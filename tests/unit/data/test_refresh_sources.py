"""Tests for pinned refresh-source adapters and stdio canonicalization."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from code_verifier.data.deduplicate import stable_json_hash
from code_verifier.data.refresh_sources import (
    RefreshCandidate,
    RefreshSourceError,
    RefreshSourceSpec,
    _candidate_from_row,
    _deepcoder_raw_record_hash,
    _resolve_snapshot,
    _validate_license,
    canonicalize_refresh_candidate,
    load_humanevalplus_references,
)
from code_verifier.data.schema import TestCase as CodeTestCase


def _spec(config_name: str) -> RefreshSourceSpec:
    return RefreshSourceSpec(
        source_name=f"deepcoder-{config_name}",
        dataset_id="agentica-org/DeepCoder-Preview-Dataset",
        revision="1" * 40,
        config_name=config_name,
        split="train",
        declared_license="MIT",
        adapter="deepcoder",
    )


def _prime_row(count: int = 8) -> dict[str, object]:
    return {
        "problem": "Echo the requested transformation.",
        "solutions": ["reference solution text"],
        "tests": json.dumps(
            [
                {"type": "stdin_stdout", "input": f"input-{index}\n", "output": f"output-{index}\n"}
                for index in range(count)
            ]
        ),
    }


def _taco_row(count: int = 8) -> dict[str, object]:
    return {
        "problem": "Process the complete stdin text.",
        "solutions": ["reference solution text"],
        "tests": json.dumps(
            {
                "inputs": [f"input-{index}\n" for index in range(count)],
                "outputs": [f"output-{index}\n" for index in range(count)],
            }
        ),
    }


@pytest.mark.parametrize("config_name", ["primeintellect", "taco"])
def test_deepcoder_stdio_rows_map_to_stable_candidates(config_name: str) -> None:
    row = _prime_row() if config_name == "primeintellect" else _taco_row()
    first = _candidate_from_row(_spec(config_name), row, row_index=7)
    second = _candidate_from_row(_spec(config_name), row, row_index=7)
    assert first is not None
    assert first == second
    assert len(first.tests) == 8
    assert first.function_name == "solve_io"
    assert first.function_signature == "def solve_io(input_text: str) -> str:"
    assert first.raw_reference_solution_hash is not None
    assert first.test_case_hashes is not None
    assert len(first.test_case_hashes) == 8
    assert first.test_fingerprint == stable_json_hash(sorted(first.test_case_hashes))


def test_deepcoder_fast_raw_hash_matches_generic_canonical_hash() -> None:
    row = _prime_row()
    assert _deepcoder_raw_record_hash(row) == stable_json_hash(row)


def test_deepcoder_rejects_malformed_unsafe_and_low_test_rows() -> None:
    malformed = _prime_row()
    malformed["tests"] = '{"duplicate": 1, "duplicate": 2}'
    assert _candidate_from_row(_spec("primeintellect"), malformed, row_index=0) is None

    interactive = _prime_row()
    tests = json.loads(str(interactive["tests"]))
    tests[0]["type"] = "interactive"
    interactive["tests"] = json.dumps(tests)
    assert _candidate_from_row(_spec("primeintellect"), interactive, row_index=0) is None

    function_call = _taco_row()
    taco_tests = json.loads(str(function_call["tests"]))
    taco_tests["fn_name"] = "solve"
    function_call["tests"] = json.dumps(taco_tests)
    assert _candidate_from_row(_spec("taco"), function_call, row_index=0) is None

    assert _candidate_from_row(_spec("taco"), _taco_row(3), row_index=0) is None


def test_deepcoder_rejects_top_level_schema_drift() -> None:
    row = _prime_row()
    row["unknown"] = True
    with pytest.raises(RefreshSourceError, match="schema"):
        _candidate_from_row(_spec("primeintellect"), row, row_index=0)


def test_canonicalize_refresh_candidate_uses_scalar_stdio_contract_and_quality_flag() -> None:
    candidate = RefreshCandidate(
        candidate_id="candidate-1",
        source_name="deepcoder-primeintellect",
        source_record_id="primeintellect/train/1",
        prompt="Original problem statement.",
        function_name="solve_io",
        function_signature="def solve_io(input_text: str) -> str:",
        tests=tuple(CodeTestCase(input=f"in-{index}", expected=f"out-{index}") for index in range(7)),
        source_url_hash=None,
        raw_reference_solution_hash="f" * 64,
        difficulty="unknown",
        category=("stdio",),
        raw_record_sha256="a" * 64,
    )
    problem, quality_gate_required = canonicalize_refresh_candidate(candidate, seed=42)
    assert quality_gate_required is True
    assert [len(problem.visible_tests), len(problem.train_hidden_tests), len(problem.eval_hidden_tests)] == [2, 2, 3]
    assert problem.function_name == "solve_io"
    assert "complete stdin text" in problem.prompt
    assert problem.reference_solution is None
    assert problem.sft_response is None
    assert problem.starter_code is None
    assert all(isinstance(test.input, str) and isinstance(test.expected, str) for test in candidate.tests)
    for test in candidate.tests:
        assert str(test.input) not in problem.prompt
        assert str(test.expected) not in problem.prompt


def test_canonicalize_loader_candidate_reuses_validated_hashes_and_rejects_tamper() -> None:
    candidate = _candidate_from_row(_spec("primeintellect"), _prime_row(), row_index=3)
    assert candidate is not None
    assert candidate.test_case_hashes is not None
    problem, quality_gate_required = canonicalize_refresh_candidate(candidate, seed=42)
    assert quality_gate_required is False
    assert len(problem.visible_tests) + len(problem.train_hidden_tests) + len(problem.eval_hidden_tests) == 8

    with pytest.raises(ValueError, match="inconsistent prevalidated test hashes"):
        canonicalize_refresh_candidate(replace(candidate, test_fingerprint="0" * 64), seed=42)


def test_license_validation_is_case_and_punctuation_insensitive(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("---\nlicense: mit\n---\n# fixture\n", encoding="utf-8")
    _validate_license(tmp_path, "MIT")
    with pytest.raises(RefreshSourceError, match="license"):
        _validate_license(tmp_path, "Apache-2.0")


def test_revision_validation_requires_full_sha() -> None:
    with pytest.raises(RefreshSourceError, match="40-character"):
        _resolve_snapshot("fixture/repo", "main", cache_dir=None)


def test_humanevalplus_loader_retains_only_exclusion_hashes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "README.md").write_text("---\nlicense: apache-2.0\n---\n# fixture\n", encoding="utf-8")
    row = {
        "task_id": "HumanEval/0",
        "prompt": "def add(a, b):\n    pass\n",
        "canonical_solution": "    return a + b\n",
        "entry_point": "add",
        "test": "assert add(1, 2) == 3",
    }
    (tmp_path / "test.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    monkeypatch.setattr(
        "code_verifier.data.refresh_sources._resolve_snapshot",
        lambda dataset_id, revision, cache_dir: tmp_path,
    )
    snapshot, references = load_humanevalplus_references(
        dataset_id="evalplus/humanevalplus",
        revision="a" * 40,
        cache_dir=None,
    )
    assert snapshot.scanned_rows == snapshot.accepted_rows == 1
    assert snapshot.declared_license == "Apache-2.0"
    assert len(references) == 1
    reference = references[0]
    assert reference.reference_class == "external_eval"
    assert reference.function_signature == "entry_point:add"
    assert reference.reference_solution_hash is not None
    assert reference.test_fingerprint is None
    assert row["canonical_solution"] not in repr(reference)
    assert row["test"] not in repr(reference)
