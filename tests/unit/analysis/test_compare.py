"""Tests for problem-paired comparisons and automatic failure candidates."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from code_verifier.analysis.compare import compare_evaluation_records, select_failure_candidates
from code_verifier.analysis.experiment import AnalysisError
from code_verifier.evaluation.evaluate import EvaluationRecord


def _record(
    problem_id: str,
    *,
    visible: float = 1.0,
    train_hidden: float = 1.0,
    eval_hidden: float = 1.0,
) -> EvaluationRecord:
    passed = eval_hidden == 1.0
    return EvaluationRecord(
        run_id="run",
        model_id="model",
        checkpoint="checkpoint",
        dataset_hash="d" * 64,
        config_hash="c" * 64,
        problem_id=problem_id,
        prompt_hash="p" * 64,
        completion="PRIVATE_COMPLETION",
        extracted_code="PRIVATE_CODE",
        parse_success=True,
        target_function_found=True,
        visible_pass_rate=visible,
        train_hidden_pass_rate=train_hidden,
        eval_hidden_pass_rate=eval_hidden,
        execution_status="passed" if passed else "wrong_answer",
        visible_execution_status="passed" if visible == 1.0 else "wrong_answer",
        train_hidden_execution_status="passed" if train_hidden == 1.0 else "wrong_answer",
        eval_hidden_execution_status="passed" if passed else "wrong_answer",
        visible_failure_counts={} if visible == 1.0 else {"wrong_answer": 1},
        train_hidden_failure_counts={} if train_hidden == 1.0 else {"wrong_answer": 1},
        eval_hidden_failure_counts={} if passed else {"wrong_answer": 1},
        parse_error_type=None,
        runtime_ms=1.0,
        generation_latency_ms=1.0,
        completion_tokens=4,
        error_category_auto="passed" if passed else "visible_only_success",
    )


def _compare(left: list[EvaluationRecord], right: list[EvaluationRecord]):  # type: ignore[no-untyped-def]
    return compare_evaluation_records(
        "left",
        left,
        "right",
        right,
        bootstrap_seed=7,
        bootstrap_resamples=100,
        confidence_level=0.95,
    )


def test_compare_evaluation_records_pairs_by_problem_id_not_row_order() -> None:
    left = [_record("p1", eval_hidden=1.0), _record("p2", eval_hidden=0.0)]
    right = [_record("p2", eval_hidden=1.0), _record("p1", eval_hidden=0.0)]

    result = _compare(left, right)

    assert result.total_problems == 2
    assert result.eval_hidden_delta == 0.0


def test_compare_evaluation_records_bootstraps_eval_and_gap_deltas() -> None:
    left = [_record("p1", eval_hidden=1.0), _record("p2", eval_hidden=1.0)]
    right = [_record("p1", eval_hidden=0.0), _record("p2", eval_hidden=1.0)]

    result = _compare(left, right)

    assert result.eval_hidden_delta == 0.5
    assert result.public_eval_gap_delta == -0.5
    assert result.reward_hacking_candidate_rate_delta == -0.5
    assert result.eval_hidden_delta_ci.estimate == result.eval_hidden_delta


def test_compare_evaluation_records_rejects_unpaired_inputs() -> None:
    with pytest.raises(AnalysisError, match="same problem_id"):
        _compare([_record("p1")], [_record("p2")])


def test_select_failure_candidates_is_deterministic_and_payload_free() -> None:
    records = [
        _record("p2", visible=1.0, train_hidden=1.0, eval_hidden=0.5),
        _record("p1", visible=0.0, train_hidden=0.0, eval_hidden=1.0),
    ]

    candidates = select_failure_candidates("Public-RLVR", records)
    serialized = json.dumps([candidate.__dict__ for candidate in candidates])

    assert [candidate.problem_id for candidate in candidates] == ["p2"]
    assert candidates[0].candidate_reasons == (
        "visible_pass_eval_fail",
        "partial_eval_hidden_failure",
    )
    assert "PRIVATE_COMPLETION" not in serialized
    assert "PRIVATE_CODE" not in serialized


def test_reward_hacking_candidate_proxy_uses_one_definition_for_all_methods() -> None:
    public = [_record("p1", visible=1.0, train_hidden=0.0, eval_hidden=0.0)]
    hidden = [_record("p1", visible=1.0, train_hidden=1.0, eval_hidden=0.0)]

    result = _compare(hidden, public)

    assert result.reward_hacking_candidate_rate_delta == 0.0


def test_select_failure_candidates_marks_large_public_eval_gap_and_hidden_train_reason() -> None:
    large_gap = replace(
        _record("p1", visible=0.75, train_hidden=0.0, eval_hidden=0.0),
        error_category_auto="large_public_eval_gap",
    )
    hidden = _record("p2", visible=0.0, train_hidden=1.0, eval_hidden=0.0)

    assert select_failure_candidates("Public-RLVR", [large_gap])[0].candidate_reasons == ("large_public_eval_gap",)
    assert select_failure_candidates("Hidden-RLVR", [hidden])[0].candidate_reasons == ("train_hidden_pass_eval_fail",)


def test_select_failure_candidates_maps_strict_status_and_parse_reasons() -> None:
    record = replace(
        _record("p1", visible=0.0, train_hidden=0.0, eval_hidden=0.0),
        parse_success=False,
        target_function_found=False,
        parse_error_type="missing_target_function",
        execution_status="parse_error",
        eval_hidden_execution_status="parse_error",
        eval_hidden_failure_counts={"parse_error": 1},
        error_category_auto="parse_error:missing_target_function",
    )

    candidate = select_failure_candidates("SFT", [record])[0]

    assert candidate.candidate_reasons == ("wrong_signature_or_parse",)
