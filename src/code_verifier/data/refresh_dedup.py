"""Deterministic exact and high-threshold near deduplication for WP9-a refresh data."""

from __future__ import annotations

import hashlib
import heapq
import math
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from code_verifier.data.deduplicate import normalize_text, stable_json_hash
from code_verifier.data.refresh_sources import OverlapReference, RefreshCandidate, refresh_test_set_fingerprint

RecordClass = Literal["candidate", "sft", "validation", "project_test", "external_eval"]

WP9A_TOKEN_NGRAM_SIZE = 5
WP9A_NEAR_JACCARD_THRESHOLD = 0.90


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
    """Reject policies that differ from the sealed WP9-a token/Jaccard protocol."""
    if isinstance(policy.token_ngram_size, bool) or policy.token_ngram_size <= 0:
        raise ValueError("token_ngram_size must be a positive integer")
    if not math.isfinite(policy.near_jaccard_threshold) or not 0.0 < policy.near_jaccard_threshold <= 1.0:
        raise ValueError("near_jaccard_threshold must be finite and in (0, 1]")
    if policy.token_ngram_size != WP9A_TOKEN_NGRAM_SIZE:
        raise ValueError(f"wp9a-refresh-v1 freezes token_ngram_size={WP9A_TOKEN_NGRAM_SIZE}")
    if policy.near_jaccard_threshold != WP9A_NEAR_JACCARD_THRESHOLD:
        raise ValueError(f"wp9a-refresh-v1 freezes near_jaccard_threshold={WP9A_NEAR_JACCARD_THRESHOLD:.2f}")


def _tokens(text: str) -> tuple[str, ...]:
    normalized = normalize_text(text).casefold()
    return tuple(re.findall(r"\w+|[^\w\s]", normalized, flags=re.UNICODE))


def _ngram_hash(gram: str) -> str:
    return hashlib.sha256(gram.encode("utf-8")).hexdigest()


def _token_ngrams(statement: str, contract: str | None, *, n: int) -> tuple[str, ...]:
    tokens = _tokens(statement)
    if contract is not None:
        tokens += ("<contract>", *_tokens(contract))
    if not tokens:
        return ()
    if len(tokens) < n:
        return (_ngram_hash("\x1f".join(tokens)),)
    hashed_grams: dict[str, None] = {}
    for index in range(len(tokens) - n + 1):
        gram_hash = _ngram_hash("\x1f".join(tokens[index : index + n]))
        hashed_grams.setdefault(gram_hash, None)
    return tuple(hashed_grams)


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
    """Build stable exact signals and deterministic token n-grams from raw task text plus contract."""
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
    test_fingerprint = candidate.test_fingerprint
    if test_fingerprint is None:
        test_fingerprint = refresh_test_set_fingerprint(
            candidate.tests,
            context=f"candidate {candidate.candidate_id}",
        )
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


def _jaccard(left: tuple[str, ...], right: tuple[str, ...]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set and not right_set:
        return 1.0
    union_size = len(left_set | right_set)
    return 0.0 if union_size == 0 else len(left_set & right_set) / union_size


def _global_token_frequency(fingerprints: Sequence[RefreshFingerprint]) -> Counter[str]:
    frequency: Counter[str] = Counter()
    for fingerprint in fingerprints:
        frequency.update(fingerprint.token_ngrams)
    return frequency


def _fingerprint_key(fingerprint: RefreshFingerprint) -> tuple[RecordClass, str]:
    return fingerprint.record_class, fingerprint.record_id


def _prefix_length(size: int, threshold: float) -> int:
    if size == 0:
        return 0
    return max(1, size - math.ceil(threshold * size) + 1)


@dataclass(frozen=True)
class _NearIndexContext:
    prefixes: Mapping[tuple[RecordClass, str], tuple[str, ...]]


def _build_near_index_context(
    fingerprints: Sequence[RefreshFingerprint],
    *,
    threshold: float,
) -> _NearIndexContext:
    unique: dict[tuple[RecordClass, str], RefreshFingerprint] = {}
    for fingerprint in fingerprints:
        key = _fingerprint_key(fingerprint)
        previous = unique.get(key)
        if previous is not None and previous != fingerprint:
            raise ValueError(f"duplicate fingerprint identity {key}")
        unique[key] = fingerprint
    frequency = _global_token_frequency(list(unique.values()))
    prefixes: dict[tuple[RecordClass, str], tuple[str, ...]] = {}
    for key, fingerprint in unique.items():
        prefix_length = _prefix_length(len(fingerprint.token_ngrams), threshold)
        prefixes[key] = tuple(
            heapq.nsmallest(
                prefix_length,
                fingerprint.token_ngrams,
                key=lambda token: (frequency[token], token),
            )
        )
    return _NearIndexContext(prefixes=prefixes)


def _candidate_pairs(
    queries: Sequence[RefreshFingerprint],
    references: Sequence[RefreshFingerprint],
    *,
    policy: RefreshDedupPolicy,
    context: _NearIndexContext | None = None,
) -> set[tuple[int, int]]:
    """Generate deterministic high-threshold candidate pairs through a shared rare-token prefix index."""
    if context is None:
        context = _build_near_index_context(
            [*queries, *references],
            threshold=policy.near_jaccard_threshold,
        )
    index: dict[str, list[int]] = defaultdict(list)
    reference_sizes = [len(reference.token_ngrams) for reference in references]
    for ref_index, reference in enumerate(references):
        for token in context.prefixes[_fingerprint_key(reference)]:
            index[token].append(ref_index)

    result: set[tuple[int, int]] = set()
    for query_index, query in enumerate(queries):
        query_size = len(query.token_ngrams)
        if query_size == 0:
            continue
        minimum_size = math.ceil(policy.near_jaccard_threshold * query_size)
        maximum_size = math.floor(query_size / policy.near_jaccard_threshold)
        for token in context.prefixes[_fingerprint_key(query)]:
            for ref_index in index.get(token, ()):
                if minimum_size <= reference_sizes[ref_index] <= maximum_size:
                    result.add((query_index, ref_index))
    return result


def find_exact_duplicate_matches(
    queries: Sequence[RefreshFingerprint],
    references: Sequence[RefreshFingerprint],
) -> dict[str, tuple[str, str]]:
    """Return the deterministic best exact-signal match for each query using exact indexes."""
    indexes: dict[str, dict[object, str]] = {
        "statement_contract": {},
        "source_url": {},
        "reference_solution": {},
        "test_fingerprint": {},
    }
    for reference in sorted(references, key=lambda item: item.record_id):
        values: tuple[tuple[str, object | None], ...] = (
            (
                "statement_contract",
                (reference.normalized_statement_hash, reference.contract_hash),
            ),
            ("source_url", reference.source_url_hash),
            ("reference_solution", reference.reference_solution_hash),
            ("test_fingerprint", reference.test_fingerprint),
        )
        for signal, value in values:
            if value is not None:
                indexes[signal].setdefault(value, reference.record_id)

    matches: dict[str, tuple[str, str]] = {}
    for query in queries:
        candidates: list[tuple[str, str]] = []
        values = (
            ("statement_contract", (query.normalized_statement_hash, query.contract_hash)),
            ("source_url", query.source_url_hash),
            ("reference_solution", query.reference_solution_hash),
            ("test_fingerprint", query.test_fingerprint),
        )
        for signal, value in values:
            if value is None:
                continue
            matched_id = indexes[signal].get(value)
            if matched_id is not None:
                candidates.append((matched_id, signal))
        if candidates:
            matches[query.record_id] = min(candidates)
    return matches


def find_near_duplicate_matches(
    queries: Sequence[RefreshFingerprint],
    references: Sequence[RefreshFingerprint],
    *,
    policy: RefreshDedupPolicy,
    context: _NearIndexContext | None = None,
) -> dict[str, tuple[str, float]]:
    """Return the best accepted-near match per query after prefix pruning and exact Jaccard verification."""
    validate_refresh_dedup_policy(policy)
    best: dict[str, tuple[str, float]] = {}
    for query_index, ref_index in sorted(_candidate_pairs(queries, references, policy=policy, context=context)):
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


def _reference_match_map(
    queries: Sequence[RefreshFingerprint],
    references: Sequence[RefreshFingerprint],
    *,
    policy: RefreshDedupPolicy,
    context: _NearIndexContext | None = None,
) -> dict[str, tuple[str, str, float | None]]:
    """Match one reference class in bulk so exact and prefix indexes are constructed only once."""
    if not queries or not references:
        return {}
    reference_by_id = {reference.record_id: reference for reference in references}
    if len(reference_by_id) != len(references):
        raise ValueError("overlap references must have unique reference_id values within a class")

    exact_indexes: dict[str, dict[object, str]] = {
        "statement_contract": {},
        "source_url": {},
        "reference_solution": {},
        "test_fingerprint": {},
    }
    for reference in sorted(references, key=lambda item: item.record_id):
        values: tuple[tuple[str, object | None], ...] = (
            (
                "statement_contract",
                (reference.normalized_statement_hash, reference.contract_hash),
            ),
            ("source_url", reference.source_url_hash),
            ("reference_solution", reference.reference_solution_hash),
            ("test_fingerprint", reference.test_fingerprint),
        )
        for signal, value in values:
            if value is not None:
                exact_indexes[signal].setdefault(value, reference.record_id)

    result: dict[str, tuple[str, str, float | None]] = {}
    for query in queries:
        values = (
            ("statement_contract", (query.normalized_statement_hash, query.contract_hash)),
            ("source_url", query.source_url_hash),
            ("reference_solution", query.reference_solution_hash),
            ("test_fingerprint", query.test_fingerprint),
        )
        exact: list[tuple[str, str]] = []
        for signal, value in values:
            if value is None:
                continue
            matched_id = exact_indexes[signal].get(value)
            if matched_id is not None:
                exact.append((matched_id, signal))
        if exact:
            matched_id, signal = min(exact)
            matched_class = reference_by_id[matched_id].record_class
            result[query.record_id] = (matched_id, f"exact_{matched_class}_{signal}", 1.0)

    near_matches = find_near_duplicate_matches(queries, references, policy=policy, context=context)
    for query_id, (matched_id, similarity) in near_matches.items():
        if query_id in result:
            continue
        matched_class = reference_by_id[matched_id].record_class
        result[query_id] = (matched_id, f"near_{matched_class}", similarity)
    return result


def _external_duplicate_matches(
    candidates: Sequence[RefreshCandidate],
    fingerprints: Sequence[RefreshFingerprint],
    *,
    policy: RefreshDedupPolicy,
    context: _NearIndexContext | None = None,
) -> dict[str, tuple[str, str, float]]:
    """Return direct duplicate evidence against deterministic retained representatives only."""
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    fingerprint_by_id = {fingerprint.record_id: fingerprint for fingerprint in fingerprints}
    if len(by_id) != len(candidates) or set(fingerprint_by_id) != set(by_id):
        raise ValueError("external duplicate candidates/fingerprints must have identical unique IDs")

    near_neighbors: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for left_index, right_index in sorted(
        _candidate_pairs(fingerprints, fingerprints, policy=policy, context=context)
    ):
        if left_index >= right_index:
            continue
        left = fingerprints[left_index]
        right = fingerprints[right_index]
        similarity = _jaccard(left.token_ngrams, right.token_ngrams)
        if similarity < policy.near_jaccard_threshold:
            continue
        near_neighbors[left.record_id].append((right.record_id, similarity))
        near_neighbors[right.record_id].append((left.record_id, similarity))

    exact_indexes: dict[str, dict[object, str]] = {
        "statement_contract": {},
        "source_url": {},
        "reference_solution": {},
        "test_fingerprint": {},
    }
    retained_ids: set[str] = set()
    duplicate_matches: dict[str, tuple[str, str, float]] = {}
    for candidate in sorted(candidates, key=lambda item: (item.source_name, item.candidate_id)):
        fingerprint = fingerprint_by_id[candidate.candidate_id]
        exact_values: tuple[tuple[str, object | None], ...] = (
            (
                "statement_contract",
                (fingerprint.normalized_statement_hash, fingerprint.contract_hash),
            ),
            ("source_url", fingerprint.source_url_hash),
            ("reference_solution", fingerprint.reference_solution_hash),
            ("test_fingerprint", fingerprint.test_fingerprint),
        )
        exact_matches: list[tuple[str, str]] = []
        for signal, value in exact_values:
            if value is None:
                continue
            matched_id = exact_indexes[signal].get(value)
            if matched_id is not None:
                exact_matches.append((matched_id, signal))
        if exact_matches:
            matched_id, signal = min(exact_matches)
            duplicate_matches[candidate.candidate_id] = (matched_id, f"exact_external_{signal}", 1.0)
            continue

        direct_near_matches = [
            (matched_id, similarity)
            for matched_id, similarity in near_neighbors.get(candidate.candidate_id, ())
            if matched_id in retained_ids
        ]
        if direct_near_matches:
            matched_id, similarity = min(direct_near_matches, key=lambda item: (-item[1], item[0]))
            duplicate_matches[candidate.candidate_id] = (matched_id, "near_external_duplicate", similarity)
            continue

        retained_ids.add(candidate.candidate_id)
        for signal, value in exact_values:
            if value is not None:
                exact_indexes[signal].setdefault(value, candidate.candidate_id)
    return duplicate_matches


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

    validation_fingerprints = [reference_fingerprint(item, policy=policy) for item in validation_references]
    project_test_fingerprints = [reference_fingerprint(item, policy=policy) for item in project_test_references]
    external_eval_fingerprints = [reference_fingerprint(item, policy=policy) for item in external_eval_references]
    sft_fingerprints = [reference_fingerprint(item, policy=policy) for item in sft_references]
    evaluation_groups = [validation_fingerprints, project_test_fingerprints, external_eval_fingerprints]
    near_context = _build_near_index_context(
        [
            *candidate_fingerprints,
            *validation_fingerprints,
            *project_test_fingerprints,
            *external_eval_fingerprints,
            *sft_fingerprints,
        ],
        threshold=policy.near_jaccard_threshold,
    )
    evaluation_matches = [
        _reference_match_map(candidate_fingerprints, references, policy=policy, context=near_context)
        for references in evaluation_groups
    ]
    sft_matches = _reference_match_map(
        candidate_fingerprints,
        sft_fingerprints,
        policy=policy,
        context=near_context,
    )
    excluded_ids = {candidate_id for matches in [*evaluation_matches, sft_matches] for candidate_id in matches}
    external_candidates = [candidate for candidate in candidates if candidate.candidate_id not in excluded_ids]
    external_fingerprints = [
        fingerprint for fingerprint in candidate_fingerprints if fingerprint.record_id not in excluded_ids
    ]
    external_matches = _external_duplicate_matches(
        external_candidates,
        external_fingerprints,
        policy=policy,
        context=near_context,
    )

    decisions: list[RefreshDedupDecision] = []
    for candidate in sorted(candidates, key=lambda item: item.candidate_id):
        hard_match = next(
            (matches[candidate.candidate_id] for matches in evaluation_matches if candidate.candidate_id in matches),
            None,
        )
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

        sft_match = sft_matches.get(candidate.candidate_id)
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

        external_match = external_matches.get(candidate.candidate_id)
        if external_match is not None:
            representative, reason, similarity = external_match
            decisions.append(
                RefreshDedupDecision(
                    candidate_id=candidate.candidate_id,
                    retained=False,
                    rejection_reason=reason,
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
