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
    _function_candidate_from_row,
    _lcbv5_function_candidate_from_row,
    _opencoder_candidate_from_row,
    _refresh_stdio_test_fingerprints,
    _resolve_snapshot,
    _stdio_test_payload_sha256,
    _validate_license,
    canonicalize_refresh_candidate,
    load_humanevalplus_references,
    refresh_test_set_fingerprint,
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


def _lcb_spec() -> RefreshSourceSpec:
    return RefreshSourceSpec(
        source_name="deepcoder-lcbv5-train",
        dataset_id="agentica-org/DeepCoder-Preview-Dataset",
        revision="1" * 40,
        config_name="lcbv5",
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


def _prime_function_row(count: int = 8) -> dict[str, object]:
    return {
        "problem": (
            "Return whether two strings are anagrams.\n\n```python\ndef is_anagram(test, original):\n    pass\n```"
        ),
        "solutions": ["```python\ndef is_anagram(test, original):\n    return sorted(test) == sorted(original)\n```"],
        "tests": json.dumps(
            [
                {
                    "type": "function_call",
                    "fn_name": "is_anagram",
                    "input": [f"ab{index}", f"ba{index}"],
                    "output": [True],
                }
                for index in range(count)
            ]
        ),
    }


def _taco_function_row(count: int = 8) -> dict[str, object]:
    return {
        "problem": "Return the sum of the two arguments.",
        "solutions": ["def add_values(left, right):\n    return left + right\n"],
        "tests": json.dumps(
            {
                "fn_name": "add_values",
                "inputs": [[index, index + 1] for index in range(count)],
                "outputs": [[2 * index + 1] for index in range(count)],
            }
        ),
    }


def _lcb_function_row(count: int = 8) -> dict[str, object]:
    return {
        "problem": "Return the sum of two integers.",
        "starter_code": "class Solution:\n    def addValues(self, left: int, right: int) -> int:\n        ",
        "tests": json.dumps(
            [
                {
                    "input": f"{index}\n{index + 1}",
                    "output": str(2 * index + 1),
                    "testtype": "functional",
                }
                for index in range(count)
            ]
        ),
        "metadata": {"func_name": "addValues"},
    }


def _opencoder_function_row(count: int = 8) -> dict[str, object]:
    return {
        "seq_id": 7,
        "instruction": "Return the sum of two integers.",
        "output": "Here is a correct implementation.",
        "code": "def add_values(left, right):\n    return left + right\n",
        "entry_point": "add_values",
        "testcase": [f"assert add_values({index}, {index + 1}) == {2 * index + 1}" for index in range(count)],
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
    assert first.test_fingerprint == refresh_test_set_fingerprint(first.tests, context="test")
    assert first.test_validation_guard is not None


@pytest.mark.parametrize("config_name", ["primeintellect", "taco"])
def test_deepcoder_function_call_rows_map_to_function_candidates(config_name: str) -> None:
    row = _prime_function_row() if config_name == "primeintellect" else _taco_function_row()
    first = _function_candidate_from_row(_spec(config_name), row, row_index=9)
    second = _function_candidate_from_row(_spec(config_name), row, row_index=9)
    assert first is not None
    assert first == second
    assert len(first.tests) == 8
    assert first.category == ("function_call",)
    assert first.test_validation_guard is None
    assert first.test_fingerprint == refresh_test_set_fingerprint(first.tests, context="test")
    if config_name == "primeintellect":
        assert first.function_name == "is_anagram"
        assert first.function_signature == "def is_anagram(test, original):"
        assert first.tests[0].input == ("ab0", "ba0")
        assert first.tests[0].expected is True
    else:
        assert first.function_name == "add_values"
        assert first.function_signature == "def add_values(left, right):"
        assert first.tests[0].input == (0, 1)
        assert first.tests[0].expected == 1


def test_lcbv5_function_call_row_maps_class_method_to_top_level_contract() -> None:
    candidate = _lcbv5_function_candidate_from_row(_lcb_spec(), _lcb_function_row(), row_index=3)
    assert candidate is not None
    assert candidate.function_name == "addValues"
    assert candidate.function_signature == "def addValues(left, right):"
    assert candidate.category == ("function_call", "lcbv5_train")
    assert len(candidate.tests) == 8
    assert candidate.tests[0].input == (0, 1)
    assert candidate.tests[0].expected == 1
    problem, quality_gate_required = canonicalize_refresh_candidate(candidate, seed=42)
    assert quality_gate_required is False
    assert problem.prompt == "Return the sum of two integers."
    assert problem.function_signature == "def addValues(left, right):"


def test_opencoder_assert_rows_map_to_function_candidates_without_executing_tests() -> None:
    candidate = _opencoder_candidate_from_row(
        _opencoder_function_row(),
        row_index=7,
        dataset_id="OpenCoder-LLM/opc-sft-stage2",
        revision="2" * 40,
    )
    assert candidate is not None
    assert candidate.function_name == "add_values"
    assert candidate.function_signature == "def add_values(left, right):"
    assert candidate.category == ("function_call", "opencoder_educational")
    assert candidate.tests[0].input == (0, 1)
    assert candidate.tests[0].expected == 1
    assert candidate.raw_reference_solution_hash is not None

    unsafe = _opencoder_function_row()
    unsafe["testcase"] = ["assert add_values(eval('1'), 2) == 3"] * 8
    assert (
        _opencoder_candidate_from_row(
            unsafe,
            row_index=8,
            dataset_id="OpenCoder-LLM/opc-sft-stage2",
            revision="2" * 40,
        )
        is None
    )


def test_function_call_adapter_fails_closed_on_ambiguous_output_and_incompatible_signature() -> None:
    ambiguous = _taco_function_row()
    tests = json.loads(str(ambiguous["tests"]))
    tests["outputs"][0] = [1, 2]
    ambiguous["tests"] = json.dumps(tests)
    assert _function_candidate_from_row(_spec("taco"), ambiguous, row_index=1) is None

    class_method = _prime_function_row()
    class_method["problem"] = "```python\ndef is_anagram(self, test, original):\n    pass\n```"
    class_method["solutions"] = ["def is_anagram(self, test, original):\n    return True\n"]
    assert _function_candidate_from_row(_spec("primeintellect"), class_method, row_index=2) is None


@pytest.mark.parametrize(
    "row",
    [
        _prime_row(),
        {
            "problem": 'Unicode 雪 and quotes " plus slash \\ and newline\n',
            "solutions": ['return "雪"', "line one\nline two", "\\path\\value"],
            "tests": '{"escaped":"\\u96ea","quote":"\\""}',
        },
    ],
)
def test_deepcoder_fast_raw_hash_matches_generic_canonical_hash(row: dict[str, object]) -> None:
    assert _deepcoder_raw_record_hash(row) == stable_json_hash(row)


def test_combined_stdio_fingerprints_match_independent_helpers() -> None:
    candidate = _candidate_from_row(_spec("primeintellect"), _prime_row(), row_index=2)
    assert candidate is not None
    fingerprint, payload_sha256 = _refresh_stdio_test_fingerprints(candidate.tests, context="fixture")
    assert fingerprint == refresh_test_set_fingerprint(candidate.tests, context="fixture")
    assert payload_sha256 == _stdio_test_payload_sha256(candidate.tests)


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


def test_canonicalize_function_candidate_preserves_function_contract_without_stdio_wrapper() -> None:
    candidate = _function_candidate_from_row(_spec("taco"), _taco_function_row(), row_index=4)
    assert candidate is not None
    problem, quality_gate_required = canonicalize_refresh_candidate(candidate, seed=42)
    assert quality_gate_required is False
    assert problem.function_name == "add_values"
    assert problem.function_signature == "def add_values(left, right):"
    assert problem.prompt == "Return the sum of the two arguments."
    assert "complete stdin text" not in problem.prompt
    assert [len(problem.visible_tests), len(problem.train_hidden_tests), len(problem.eval_hidden_tests)] == [2, 3, 3]


def test_canonicalize_loader_candidate_reuses_validated_hashes_and_rejects_tamper() -> None:
    candidate = _candidate_from_row(_spec("primeintellect"), _prime_row(), row_index=3)
    assert candidate is not None
    assert candidate.test_validation_guard is not None
    problem, quality_gate_required = canonicalize_refresh_candidate(candidate, seed=42)
    assert quality_gate_required is False
    assert len(problem.visible_tests) + len(problem.train_hidden_tests) + len(problem.eval_hidden_tests) == 8

    with pytest.raises(ValueError, match="inconsistent prevalidated tests"):
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
