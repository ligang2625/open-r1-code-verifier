"""Deterministic exact and high-threshold near deduplication for WP9-a refresh data."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

from code_verifier.data.deduplicate import normalize_text, stable_json_hash, test_case_hash
from code_verifier.data.refresh_sources import OverlapReference, RefreshCandidate

RecordClass = Literal["candidate", "sft", "validation", "project_test", "external_eval"]


@dataclass(frozen=True)
class RefreshDedupPolicy:
    """Frozen tokenization and accepted-near threshold for refresh deduplication."""

    token_ngram_size: int
    near_jaccard_threshold: float


@dataclass(frozen=True)
class RefreshFingerprint:
    """Content-only duplicate signals for one candidate or exclusion reference."""

    record_id: str
    record_class: RecordClass
    normalized_statement_hash: str
    contract_hash: str | None
    source_url_hash: str | None
    reference_solution_hash: str | None
    test_fingerprint: str | None
    token_ngrams: tuple[str, ...]


@dataclass(frozen=True)
class RefreshDedupDecision:
    """Auditable retention or rejection decision for one external candidate."""

    candidate_id: str
    retained: bool
    rejection_reason: str | None
    overlap_class: str
    matched_record_id: str | None
    similarity: float | None


def validate_refresh_dedup_policy(policy: RefreshDedupPolicy) -> None:
    """Reject thresholds that would weaken the sealed WP9-a high-threshold protocol."""
    if isinstance(policy.token_ngram_size, bool) or policy.token_ngram_size <= 0:
        raise ValueError("token_ngram_size must be a positive integer")
    if not math.isfinite(policy.near_jaccard_threshold) or not 0.0 < policy.near_jaccard_threshold <= 1.0:
        raise ValueError("near_jaccard_threshold must be finite and in (0, 1]")


def _tokens(text: str) -> tuple[str, ...]:
    normalized = normalize_text(text).casefold()
    return tuple(re.findall(r"\w+|[^\w\s]", normalized, flags=re.UNICODE))


def _token_ngrams(statement: str, contract: str | None, *, n: int) -> tuple[str, ...]:
    tokens = _tokens(statement)
    if contract is not None:
        tokens += ("<contract>", *_tokens(contract))
    if not tokens:
        return ()
    if len(tokens) < n:
        return ("\x1f".join(tokens),)
    return tuple(sorted({"\x1f".join(tokens[index : index + n]) for index in range(len(tokens) - n + 1)}))


def build_refresh_fingerprint(
    *,
    record_id: str,
    record_class: RecordClass,
    prompt: str,
    function_signature: str | None,
    source_url_hash: str | None,
    reference_solution_hash: str | None,
    test_fingerprint: str | None,
    policy: RefreshDedupPolicy,
) -> RefreshFingerprint:
    """Build stable exact signals and sorted token n-grams from raw task text plus contract."""
    validate_refresh_dedup_policy(policy)
    statement = normalize_text(prompt)
    if not statement:
        raise ValueError(f"record {record_id} has an empty normalized prompt")
    contract = None if function_signature is None else normalize_text(function_signature)
    contract = contract or None
    return RefreshFingerprint(
        record_id=record_id,
        record_class=record_class,
        normalized_statement_hash=stable_json_hash(statement),
        contract_hash=None if contract is None else stable_json_hash(contract),
        source_url_hash=source_url_hash,
        reference_solution_hash=reference_solution_hash,
        test_fingerprint=test_fingerprint,
        token_ngrams=_token_ngrams(statement, contract, n=policy.token_ngram_size),
    )


def candidate_fingerprint(candidate: RefreshCandidate, *, policy: RefreshDedupPolicy) -> RefreshFingerprint:
    """Build one candidate fingerprint without the stdio wrapper boilerplate added at materialization time."""
    test_fingerprint = stable_json_hash(sorted(test_case_hash(test) for test in candidate.tests))
    return build_refresh_fingerprint(
        record_id=candidate.candidate_id,
        record_class="candidate",
        prompt=candidate.prompt,
        function_signature=candidate.function_signature,
        source_url_hash=candidate.source_url_hash,
        reference_solution_hash=candidate.raw_reference_solution_hash,
        test_fingerprint=test_fingerprint,
        policy=policy,
    )


def reference_fingerprint(reference: OverlapReference, *, policy: RefreshDedupPolicy) -> RefreshFingerprint:
    """Build one reference fingerprint from its minimal exclusion-only fields."""
    return build_refresh_fingerprint(
        record_id=reference.reference_id,
        record_class=reference.reference_class,
        prompt=reference.prompt,
        function_signature=reference.function_signature,
        source_url_hash=reference.source_url_hash,
        reference_solution_hash=reference.reference_solution_hash,
        test_fingerprint=reference.test_fingerprint,
        policy=policy,
    )


def _exact_signal(left: RefreshFingerprint, right: RefreshFingerprint) -> str | None:
    if (
        left.normalized_statement_hash == right.normalized_statement_hash
        and left.contract_hash == right.contract_hash
    ):
        return "statement_contract"
    for name in ("source_url_hash", "reference_solution_hash", "test_fingerprint"):
        left_value = getattr(left, name)
        right_value = getattr(right, name)
        if left_value is not None and left_value == right_value:
            return name.removesuffix("_hash")
    return None


def _jaccard(left: tuple[str, ...], right: tuple[str, ...]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set and not right_set:
        return 1.0
    union_size = len(left_set | right_set)
    return 0.0 if union_size == 0 else len(left_set & right_set) / union_size


def _global_token_order(
    queries: Sequence[RefreshFingerprint], references: Sequence[RefreshFingerprint]
) -> dict[str, int]:
    frequency: Counter[str] = Counter()
    for fingerprint in (*queries, *references):
        frequency.update(fingerprint.token_ngrams)
    ordered = sorted(frequency, key=lambda token: (frequency[token], token))
    return {token: index for index, token in enumerate(ordered)}


def _ordered_ngrams(fingerprint: RefreshFingerprint, order: dict[str, int]) -> tuple[str, ...]:
    return tuple(sorted(fingerprint.token_ngrams, key=lambda token: (order[token], token)))


def _prefix_length(size: int, threshold: float) -> int:
    if size == 0:
        return 0
    return max(1, size - math.ceil(threshold * size) + 1)


def _candidate_pairs(
    queries: Sequence[RefreshFingerprint],
    references: Sequence[RefreshFingerprint],
    *,
    policy: RefreshDedupPolicy,
) -> set[tuple[int, int]]:
    """Generate deterministic high-threshold candidate pairs through a global-order prefix index."""
    order = _global_token_order(queries, references)
    index: dict[str, list[int]] = defaultdict(list)
    reference_sizes = [len(set(reference.token_ngrams)) for reference in references]
    for ref_index, reference in enumerate(references):
        ordered = _ordered_ngrams(reference, order)
        for token in ordered[: _prefix_length(len(ordered), policy.near_jaccard_threshold)]:
            index[token].append(ref_index)

    result: set[tuple[int, int]] = set()
    for query_index, query in enumerate(queries):
        query_size = len(set(query.token_ngrams))
        if query_size == 0:
            continue
        minimum_size = math.ceil(policy.near_jaccard_threshold * query_size)
        maximum_size = math.floor(query_size / policy.near_jaccard_threshold)
        ordered = _ordered_ngrams(query, order)
        for token in ordered[: _prefix_length(len(ordered), policy.near_jaccard_threshold)]:
            for ref_index in index.get(token, ()):
                if minimum_size <= reference_sizes[ref_index] <= maximum_size:
                    result.add((query_index, ref_index))
    return result


def find_near_duplicate_matches(
    queries: Sequence[RefreshFingerprint],
    references: Sequence[RefreshFingerprint],
    *,
    policy: RefreshDedupPolicy,
) -> dict[str, tuple[str, float]]:
    """Return the best accepted-near match per query after prefix pruning and exact Jaccard verification."""
    validate_refresh_dedup_policy(policy)
    best: dict[str, tuple[str, float]] = {}
    for query_index, ref_index in sorted(_candidate_pairs(queries, references, policy=policy)):
        query = queries[query_index]
        reference = references[ref_index]
        if query.record_id == reference.record_id and query.record_class == reference.record_class:
            continue
        similarity = _jaccard(query.token_ngrams, reference.token_ngrams)
        if similarity < policy.near_jaccard_threshold:
            continue
        previous = best.get(query.record_id)
        candidate = (reference.record_id, similarity)
        if previous is None or (-candidate[1], candidate[0]) < (-previous[1], previous[0]):
            best[query.record_id] = candidate
    return best


def _best_exact_match(
    query: RefreshFingerprint,
    references: Sequence[RefreshFingerprint],
) -> tuple[RefreshFingerprint, str] | None:
    matches: list[tuple[RefreshFingerprint, str]] = []
    for reference in references:
        signal = _exact_signal(query, reference)
        if signal is not None:
            matches.append((reference, signal))
    if not matches:
        return None
    return min(matches, key=lambda item: (item[0].record_id, item[1]))


def _reference_decision(
    query: RefreshFingerprint,
    references: Sequence[RefreshFingerprint],
    *,
    policy: RefreshDedupPolicy,
) -> tuple[str, str, float | None] | None:
    exact = _best_exact_match(query, references)
    if exact is not None:
        reference, signal = exact
        return reference.record_id, f"exact_{reference.record_class}_{signal}", 1.0
    near = find_near_duplicate_matches([query], references, policy=policy).get(query.record_id)
    if near is None:
        return None
    matched_id, similarity = near
    matched_class = next(reference.record_class for reference in references if reference.record_id == matched_id)
    return matched_id, f"near_{matched_class}", similarity


class _DisjointSet:
    def __init__(self, ids: Iterable[str]) -> None:
        self._parent = {record_id: record_id for record_id in ids}

    def find(self, record_id: str) -> str:
        parent = self._parent[record_id]
        if parent != record_id:
            parent = self.find(parent)
            self._parent[record_id] = parent
        return parent

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        first, second = sorted((left_root, right_root))
        self._parent[second] = first


def _external_duplicate_components(
    candidates: Sequence[RefreshCandidate],
    fingerprints: Sequence[RefreshFingerprint],
    *,
    policy: RefreshDedupPolicy,
) -> dict[str, str]:
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    dsu = _DisjointSet(by_id)
    exact_indexes: dict[tuple[str, str], str] = {}
    for fingerprint in sorted(fingerprints, key=lambda item: item.record_id):
        exact_values = [
            ("statement_contract", f"{fingerprint.normalized_statement_hash}:{fingerprint.contract_hash}"),
            ("source_url", fingerprint.source_url_hash),
            ("reference_solution", fingerprint.reference_solution_hash),
            ("test_fingerprint", fingerprint.test_fingerprint),
        ]
        for signal, value in exact_values:
            if value is None:
                continue
            key = (signal, value)
            previous = exact_indexes.get(key)
            if previous is not None:
                dsu.union(previous, fingerprint.record_id)
            else:
                exact_indexes[key] = fingerprint.record_id

    for left_index, right_index in sorted(_candidate_pairs(fingerprints, fingerprints, policy=policy)):
        if left_index >= right_index:
            continue
        left = fingerprints[left_index]
        right = fingerprints[right_index]
        if _jaccard(left.token_ngrams, right.token_ngrams) >= policy.near_jaccard_threshold:
            dsu.union(left.record_id, right.record_id)

    components: dict[str, list[str]] = defaultdict(list)
    for candidate_id in by_id:
        components[dsu.find(candidate_id)].append(candidate_id)
    representative: dict[str, str] = {}
    for members in components.values():
        retained = min(members, key=lambda item: (by_id[item].source_name, item))
        for member in members:
            representative[member] = retained
    return representative


def classify_refresh_candidates(
    candidates: Sequence[RefreshCandidate],
    *,
    sft_references: Sequence[OverlapReference],
    validation_references: Sequence[OverlapReference],
    project_test_references: Sequence[OverlapReference],
    external_eval_references: Sequence[OverlapReference],
    policy: RefreshDedupPolicy,
) -> list[RefreshDedupDecision]:
    """Apply hard evaluation exclusion, incidental-SFT exclusion, then deterministic external dedup."""
    validate_refresh_dedup_policy(policy)
    candidate_fingerprints = [candidate_fingerprint(candidate, policy=policy) for candidate in candidates]
    fingerprint_by_id = {fingerprint.record_id: fingerprint for fingerprint in candidate_fingerprints}
    if len(fingerprint_by_id) != len(candidates):
        raise ValueError("refresh candidates must have unique candidate_id values")

    evaluation_groups = [
        ("validation", [reference_fingerprint(item, policy=policy) for item in validation_references]),
        ("project_test", [reference_fingerprint(item, policy=policy) for item in project_test_references]),
        ("external_eval", [reference_fingerprint(item, policy=policy) for item in external_eval_references]),
    ]
    sft_fingerprints = [reference_fingerprint(item, policy=policy) for item in sft_references]
    representatives = _external_duplicate_components(candidates, candidate_fingerprints, policy=policy)

    decisions: list[RefreshDedupDecision] = []
    for candidate in sorted(candidates, key=lambda item: item.candidate_id):
        query = fingerprint_by_id[candidate.candidate_id]
        hard_match: tuple[str, str, float | None] | None = None
        for _class_name, references in evaluation_groups:
            hard_match = _reference_decision(query, references, policy=policy)
            if hard_match is not None:
                break
        if hard_match is not None:
            matched_id, reason, similarity = hard_match
            decisions.append(
                RefreshDedupDecision(
                    candidate_id=candidate.candidate_id,
                    retained=False,
                    rejection_reason=reason,
                    overlap_class="evaluation_overlap",
                    matched_record_id=matched_id,
                    similarity=similarity,
                )
            )
            continue

        sft_match = _reference_decision(query, sft_fingerprints, policy=policy)
        if sft_match is not None:
            matched_id, reason, similarity = sft_match
            decisions.append(
                RefreshDedupDecision(
                    candidate_id=candidate.candidate_id,
                    retained=False,
                    rejection_reason=reason,
                    overlap_class="incidental_sft_overlap",
                    matched_record_id=matched_id,
                    similarity=similarity,
                )
            )
            continue

        representative = representatives[candidate.candidate_id]
        if representative != candidate.candidate_id:
            representative_fingerprint = fingerprint_by_id[representative]
            exact_signal = _exact_signal(query, representative_fingerprint)
            similarity = 1.0 if exact_signal is not None else _jaccard(
                query.token_ngrams, representative_fingerprint.token_ngrams
            )
            decisions.append(
                RefreshDedupDecision(
                    candidate_id=candidate.candidate_id,
                    retained=False,
                    rejection_reason=(
                        f"exact_external_{exact_signal}" if exact_signal is not None else "near_external_duplicate"
                    ),
                    overlap_class="cross_source_duplicate",
                    matched_record_id=representative,
                    similarity=similarity,
                )
            )
            continue

        decisions.append(
            RefreshDedupDecision(
                candidate_id=candidate.candidate_id,
                retained=True,
                rejection_reason=None,
                overlap_class="none",
                matched_record_id=None,
                similarity=None,
            )
        )
    return decisions
