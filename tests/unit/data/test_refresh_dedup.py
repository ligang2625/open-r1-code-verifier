"""Tests for deterministic exact/near refresh deduplication."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from code_verifier.data.refresh_dedup import (
    RefreshDedupPolicy,
    build_refresh_fingerprint,
    classify_refresh_candidates,
    find_near_duplicate_matches,
)
from code_verifier.data.refresh_sources import OverlapReference, RefreshCandidate
from code_verifier.data.schema import TestCase as CodeTestCase

POLICY = RefreshDedupPolicy(token_ngram_size=5, near_jaccard_threshold=0.90)


def _candidate(candidate_id: str, prompt: str, *, source: str = "source-a") -> RefreshCandidate:
    return RefreshCandidate(
        candidate_id=candidate_id,
        source_name=source,
        source_record_id=f"{source}/{candidate_id}",
        prompt=prompt,
        function_name="solve_io",
        function_signature="def solve_io(input_text: str) -> str:",
        tests=tuple(
            CodeTestCase(input=f"in-{candidate_id}-{i}", expected=f"out-{candidate_id}-{i}") for i in range(8)
        ),
        source_url_hash=None,
        raw_reference_solution_hash=None,
        difficulty="unknown",
        category=("stdio",),
        raw_record_sha256=(candidate_id[0] if candidate_id else "a") * 64,
    )


def _reference(reference_id: str, reference_class: str, prompt: str) -> OverlapReference:
    assert reference_class in {"sft", "validation", "project_test", "external_eval"}
    return OverlapReference(
        reference_id=reference_id,
        reference_class=reference_class,  # type: ignore[arg-type]
        prompt=prompt,
        function_signature="def solve_io(input_text: str) -> str:",
        source_url_hash=None,
        reference_solution_hash=None,
        test_fingerprint=None,
    )


def _long_prompt(token: str, *, count: int = 60) -> str:
    return " ".join(f"{token}{index}" for index in range(count))


def test_exact_evaluation_overlap_is_hard_rejected_before_sft() -> None:
    prompt = _long_prompt("same")
    candidate = _candidate("c1", prompt)
    decisions = classify_refresh_candidates(
        [candidate],
        sft_references=[_reference("sft-1", "sft", prompt)],
        validation_references=[_reference("validation-1", "validation", prompt)],
        project_test_references=[],
        external_eval_references=[],
        policy=POLICY,
    )
    assert decisions[0].retained is False
    assert decisions[0].overlap_class == "evaluation_overlap"
    assert decisions[0].matched_record_id == "validation-1"
    assert decisions[0].rejection_reason is not None and decisions[0].rejection_reason.startswith("exact_validation")


def test_incidental_sft_overlap_is_rejected() -> None:
    prompt = _long_prompt("sft")
    decision = classify_refresh_candidates(
        [_candidate("c1", prompt)],
        sft_references=[_reference("sft-1", "sft", prompt)],
        validation_references=[],
        project_test_references=[],
        external_eval_references=[],
        policy=POLICY,
    )[0]
    assert decision.retained is False
    assert decision.overlap_class == "incidental_sft_overlap"


def test_accepted_near_match_uses_exact_jaccard() -> None:
    base = _long_prompt("near")
    tokens = base.split()
    near = " ".join([*tokens[:-1], "replacement-token"])
    query = build_refresh_fingerprint(
        record_id="query",
        record_class="candidate",
        prompt=base,
        function_signature=None,
        source_url_hash=None,
        reference_solution_hash=None,
        test_fingerprint=None,
        policy=POLICY,
    )
    reference = build_refresh_fingerprint(
        record_id="reference",
        record_class="validation",
        prompt=near,
        function_signature=None,
        source_url_hash=None,
        reference_solution_hash=None,
        test_fingerprint=None,
        policy=POLICY,
    )
    match = find_near_duplicate_matches([query], [reference], policy=POLICY)
    assert match["query"][0] == "reference"
    assert POLICY.near_jaccard_threshold <= match["query"][1] < 1.0


def test_external_duplicate_representation_is_permutation_invariant() -> None:
    duplicate_prompt = _long_prompt("duplicate")
    candidates = [
        _candidate("z-candidate", duplicate_prompt, source="source-z"),
        _candidate("a-candidate", duplicate_prompt, source="source-a"),
        _candidate("unique", _long_prompt("unique"), source="source-z"),
    ]

    def classify(values: list[RefreshCandidate]) -> list[tuple[str, bool, str | None]]:
        decisions = classify_refresh_candidates(
            values,
            sft_references=[],
            validation_references=[],
            project_test_references=[],
            external_eval_references=[],
            policy=POLICY,
        )
        return [(item.candidate_id, item.retained, item.matched_record_id) for item in decisions]

    first = classify(candidates)
    second = classify(list(reversed(candidates)))
    assert first == second
    assert ("a-candidate", True, None) in first
    assert ("z-candidate", False, "a-candidate") in first
    assert ("unique", True, None) in first


def test_prefix_index_avoids_all_pairs_exact_jaccard(monkeypatch: pytest.MonkeyPatch) -> None:
    import code_verifier.data.refresh_dedup as module

    query = build_refresh_fingerprint(
        record_id="query",
        record_class="candidate",
        prompt=_long_prompt("query"),
        function_signature=None,
        source_url_hash=None,
        reference_solution_hash=None,
        test_fingerprint=None,
        policy=POLICY,
    )
    references = [
        build_refresh_fingerprint(
            record_id=f"ref-{index}",
            record_class="external_eval",
            prompt=_long_prompt(f"unrelated{index}"),
            function_signature=None,
            source_url_hash=None,
            reference_solution_hash=None,
            test_fingerprint=None,
            policy=POLICY,
        )
        for index in range(100)
    ]
    original: Callable[[tuple[str, ...], tuple[str, ...]], float] = module._jaccard
    calls = 0

    def counted(left: tuple[str, ...], right: tuple[str, ...]) -> float:
        nonlocal calls
        calls += 1
        return original(left, right)

    monkeypatch.setattr(module, "_jaccard", counted)
    assert find_near_duplicate_matches([query], references, policy=POLICY) == {}
    assert calls < len(references)


def test_policy_rejects_invalid_thresholds() -> None:
    with pytest.raises(ValueError):
        build_refresh_fingerprint(
            record_id="x",
            record_class="candidate",
            prompt="non-empty",
            function_signature=None,
            source_url_hash=None,
            reference_solution_hash=None,
            test_fingerprint=None,
            policy=RefreshDedupPolicy(token_ngram_size=0, near_jaccard_threshold=0.90),
        )
