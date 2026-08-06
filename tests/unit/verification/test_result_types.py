"""Tests for structured verification results and safe serialization."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, cast

import pytest

from code_verifier.execution.base import ExecutionResult, ExecutionStatus
from code_verifier.execution.base import TestCaseResult as ExecutionTestCaseResult
from code_verifier.verification.result_types import (
    VerificationContractError,
    VerificationResult,
    validate_verification_result,
    verification_result_to_mapping,
)


def _test_result(
    status: ExecutionStatus = ExecutionStatus.PASSED,
    *,
    stdout: str = "",
    stderr: str = "",
) -> ExecutionTestCaseResult:
    return ExecutionTestCaseResult(
        status=status,
        passed=status is ExecutionStatus.PASSED,
        runtime_ms=1.0,
        stdout=stdout,
        stderr=stderr,
    )


def _execution_result(
    *,
    status: ExecutionStatus = ExecutionStatus.PASSED,
    passed_tests: int = 1,
    total_tests: int = 1,
    test_results: list[ExecutionTestCaseResult] | None = None,
) -> ExecutionResult:
    return ExecutionResult(
        status=status,
        passed_tests=passed_tests,
        total_tests=total_tests,
        pass_rate=passed_tests / total_tests,
        runtime_ms=1.0,
        test_results=[_test_result()] if test_results is None else test_results,
    )


def _executed_verification(execution_result: ExecutionResult | None = None) -> VerificationResult:
    resolved = _execution_result() if execution_result is None else execution_result
    failure_counts = tuple(
        sorted(
            {
                result.status.value: sum(item.status is result.status for item in resolved.test_results)
                for result in resolved.test_results
                if result.status is not ExecutionStatus.PASSED
            }.items()
        )
    )
    missing = resolved.total_tests - len(resolved.test_results)
    if missing:
        counts = dict(failure_counts)
        counts[resolved.status.value] = counts.get(resolved.status.value, 0) + missing
        failure_counts = tuple(sorted(counts.items()))
    return VerificationResult(
        status=resolved.status,
        parsed=True,
        executed=True,
        infrastructure_failure=resolved.status is ExecutionStatus.SANDBOX_ERROR,
        passed_tests=resolved.passed_tests,
        total_tests=resolved.total_tests,
        pass_rate=resolved.pass_rate,
        parse_error_type=None,
        num_code_blocks=1,
        failure_counts=failure_counts,
        execution_result=resolved,
    )


def _parse_failure() -> VerificationResult:
    return VerificationResult(
        status=ExecutionStatus.PARSE_ERROR,
        parsed=False,
        executed=False,
        infrastructure_failure=False,
        passed_tests=0,
        total_tests=2,
        pass_rate=0.0,
        parse_error_type="missing_target_function",
        num_code_blocks=1,
        failure_counts=(("parse_error", 2),),
        execution_result=None,
    )


def test_valid_parse_failure_result_maps_without_code_or_tests() -> None:
    result = _parse_failure()

    validate_verification_result(result)
    mapping = verification_result_to_mapping(result)

    assert mapping == {
        "status": "parse_error",
        "parsed": False,
        "executed": False,
        "infrastructure_failure": False,
        "passed_tests": 0,
        "total_tests": 2,
        "pass_rate": 0.0,
        "parse_error_type": "missing_target_function",
        "num_code_blocks": 1,
        "failure_counts": {"parse_error": 2},
        "execution_result": None,
    }
    serialized = json.dumps(mapping, allow_nan=False)
    for forbidden in ("completion", "code", "tests", "metadata"):
        assert forbidden not in mapping
    assert "PRIVATE_PAYLOAD_SENTINEL" not in serialized


def test_valid_executed_result_matches_execution_contract() -> None:
    results = [
        _execution_result(),
        _execution_result(
            status=ExecutionStatus.WRONG_ANSWER,
            passed_tests=1,
            total_tests=2,
            test_results=[_test_result(), _test_result(ExecutionStatus.WRONG_ANSWER)],
        ),
        _execution_result(
            status=ExecutionStatus.TIMEOUT,
            passed_tests=1,
            total_tests=3,
            test_results=[_test_result(), _test_result(ExecutionStatus.TIMEOUT)],
        ),
        _execution_result(
            status=ExecutionStatus.SANDBOX_ERROR,
            passed_tests=0,
            total_tests=2,
            test_results=[_test_result(ExecutionStatus.SANDBOX_ERROR)],
        ),
    ]

    for execution_result in results:
        result = _executed_verification(execution_result)
        validate_verification_result(result)
        mapping = verification_result_to_mapping(result)
        assert mapping["status"] == execution_result.status.value
        assert mapping["passed_tests"] == execution_result.passed_tests
        assert mapping["total_tests"] == execution_result.total_tests
        assert mapping["pass_rate"] == execution_result.pass_rate
        json.dumps(mapping, allow_nan=False)


def test_validation_rejects_zero_tests_non_finite_rate_and_bad_counts() -> None:
    valid = _parse_failure()
    invalid_results = [
        replace(valid, total_tests=0, failure_counts=()),
        replace(valid, pass_rate=float("nan")),
        replace(valid, pass_rate=float("inf")),
        replace(valid, passed_tests=cast(int, True)),
        replace(valid, total_tests=cast(int, True)),
        replace(valid, passed_tests=3),
        replace(valid, num_code_blocks=cast(int, True)),
    ]

    for result in invalid_results:
        with pytest.raises(VerificationContractError):
            validate_verification_result(result)


def test_validation_rejects_unsorted_duplicate_unknown_or_zero_failure_counts() -> None:
    valid = replace(
        _parse_failure(),
        total_tests=2,
        failure_counts=(("parse_error", 1), ("timeout", 1)),
    )
    invalid_counts = [
        (("timeout", 1), ("parse_error", 1)),
        (("parse_error", 1), ("parse_error", 1)),
        (("passed", 1), ("parse_error", 1)),
        (("unknown", 1), ("parse_error", 1)),
        (("parse_error", 0), ("timeout", 2)),
        cast(tuple[tuple[str, int], ...], [("parse_error", 2)]),
    ]

    for failure_counts in invalid_counts:
        with pytest.raises(VerificationContractError):
            validate_verification_result(replace(valid, failure_counts=failure_counts))


def test_validation_rejects_parse_execution_and_infrastructure_invariant_mismatches() -> None:
    parse_failure = _parse_failure()
    executed = _executed_verification()
    sandbox = _executed_verification(
        _execution_result(
            status=ExecutionStatus.SANDBOX_ERROR,
            passed_tests=0,
            total_tests=1,
            test_results=[_test_result(ExecutionStatus.SANDBOX_ERROR)],
        )
    )
    invalid_results = [
        replace(parse_failure, status=ExecutionStatus.WRONG_ANSWER, failure_counts=(("wrong_answer", 2),)),
        replace(parse_failure, executed=True),
        replace(parse_failure, infrastructure_failure=True),
        replace(parse_failure, parse_error_type=None),
        replace(parse_failure, execution_result=_execution_result()),
        replace(executed, parse_error_type="sentinel"),
        replace(executed, execution_result=None),
        replace(executed, passed_tests=0, pass_rate=0.0, failure_counts=(("wrong_answer", 1),)),
        replace(sandbox, infrastructure_failure=False),
        replace(executed, infrastructure_failure=True),
        VerificationResult(
            status=ExecutionStatus.SANDBOX_ERROR,
            parsed=True,
            executed=False,
            infrastructure_failure=True,
            passed_tests=1,
            total_tests=1,
            pass_rate=1.0,
            parse_error_type=None,
            num_code_blocks=1,
            failure_counts=(),
            execution_result=None,
        ),
    ]

    for result in invalid_results:
        with pytest.raises(VerificationContractError):
            validate_verification_result(result)


def test_mapping_returns_independent_nested_containers() -> None:
    execution_result = _execution_result(
        status=ExecutionStatus.WRONG_ANSWER,
        passed_tests=0,
        total_tests=1,
        test_results=[_test_result(ExecutionStatus.WRONG_ANSWER, stdout="bounded")],
    )
    result = _executed_verification(execution_result)

    mapping = verification_result_to_mapping(result)
    cast(dict[str, int], mapping["failure_counts"]).clear()
    nested = cast(dict[str, object], mapping["execution_result"])
    cast(list[dict[str, object]], nested["test_results"]).clear()

    assert result.failure_counts == (("wrong_answer", 1),)
    assert result.execution_result is not None
    assert len(result.execution_result.test_results) == 1
    assert verification_result_to_mapping(result)["failure_counts"] == {"wrong_answer": 1}


def test_contract_errors_do_not_echo_sentinel_payloads() -> None:
    sentinel = "PRIVATE_EXECUTION_PAYLOAD_SENTINEL"
    malformed_execution = _execution_result(
        status=ExecutionStatus.WRONG_ANSWER,
        passed_tests=0,
        total_tests=1,
        test_results=[_test_result(ExecutionStatus.WRONG_ANSWER, stdout=sentinel)],
    )
    malformed_execution.test_results[0] = replace(malformed_execution.test_results[0], passed=True)
    result = _executed_verification(
        _execution_result(
            status=ExecutionStatus.WRONG_ANSWER,
            passed_tests=0,
            total_tests=1,
            test_results=[_test_result(ExecutionStatus.WRONG_ANSWER)],
        )
    )
    result = replace(result, execution_result=malformed_execution)

    with pytest.raises(VerificationContractError) as exc_info:
        validate_verification_result(result)

    assert sentinel not in str(exc_info.value)


def test_wrong_runtime_types_are_rejected_without_bool_coercion() -> None:
    result = _executed_verification()
    malformed = replace(cast(ExecutionResult, result.execution_result), pass_rate=cast(float, True))

    with pytest.raises(VerificationContractError):
        validate_verification_result(replace(result, execution_result=malformed))


def test_mapping_has_exact_public_fields() -> None:
    mapping = verification_result_to_mapping(_parse_failure())
    assert set(mapping) == {
        "status",
        "parsed",
        "executed",
        "infrastructure_failure",
        "passed_tests",
        "total_tests",
        "pass_rate",
        "parse_error_type",
        "num_code_blocks",
        "failure_counts",
        "execution_result",
    }
    assert isinstance(cast(Any, mapping), dict)
