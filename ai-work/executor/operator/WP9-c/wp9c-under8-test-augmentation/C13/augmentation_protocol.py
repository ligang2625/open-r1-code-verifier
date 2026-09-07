"""Frozen deterministic helpers for WP9-c under8 test augmentation."""

from __future__ import annotations

import ast
import hashlib
import math
from dataclasses import dataclass
from typing import Any

from code_verifier.data.deduplicate import canonical_json, stable_json_hash
from code_verifier.parsing.code_extractor import extract_python_code

REFERENCE_ENTRY = "__wp9c_reference_entry__"
PROPOSAL_PROTOCOL = "wp9c-json-boundary-mutation-v1"


@dataclass(frozen=True)
class SolutionTransform:
    success: bool
    reason: str
    extraction_mode: str | None
    target_kind: str | None
    target_owner: str | None
    raw_solution_sha256: str
    source_code_sha256: str | None
    transformed_code_sha256: str | None
    transformed_code: str | None


def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _extract_source_code(solution: str) -> tuple[str | None, str | None, str | None]:
    if not isinstance(solution, str) or not solution.strip():
        return None, None, "empty_solution"
    if "```" in solution:
        parsed = extract_python_code(solution)
        if not parsed.success:
            return None, None, f"fenced_extract_{parsed.error_type}"
        return parsed.code.rstrip() + "\n", "final_fenced_python", None
    return solution.strip() + "\n", "whole_text", None


def transform_source_solution(solution: str, *, function_name: str) -> SolutionTransform:
    """Transform one accepted source solution into a deterministic module-level callable wrapper."""
    raw_sha = _sha_text(solution)
    code, extraction_mode, error = _extract_source_code(solution)
    if code is None:
        return SolutionTransform(
            False, error or "extract_failed", extraction_mode, None, None, raw_sha, None, None, None
        )
    source_sha = _sha_text(code)
    try:
        module = ast.parse(code)
    except (SyntaxError, ValueError, UnicodeError, MemoryError, RecursionError):
        return SolutionTransform(
            False, "invalid_python_syntax", extraction_mode, None, None, raw_sha, source_sha, None, None
        )

    if any(
        isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == REFERENCE_ENTRY
        for node in module.body
    ):
        return SolutionTransform(
            False, "reserved_wrapper_collision", extraction_mode, None, None, raw_sha, source_sha, None, None
        )

    top_targets = [
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == function_name
    ]
    if any(isinstance(node, ast.AsyncFunctionDef) for node in top_targets):
        return SolutionTransform(
            False, "async_target_not_supported", extraction_mode, None, None, raw_sha, source_sha, None, None
        )
    if len(top_targets) > 1:
        return SolutionTransform(
            False, "ambiguous_top_level_target", extraction_mode, None, None, raw_sha, source_sha, None, None
        )
    if len(top_targets) == 1:
        wrapper = f"\n\ndef {REFERENCE_ENTRY}(*args, **kwargs):\n    return {function_name}(*args, **kwargs)\n"
        transformed = code.rstrip() + wrapper
        return SolutionTransform(
            True,
            "ok",
            extraction_mode,
            "top_level_function",
            None,
            raw_sha,
            source_sha,
            _sha_text(transformed),
            transformed,
        )

    class_targets: list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]] = []
    for node in module.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for child in node.body:
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef) and child.name == function_name:
                class_targets.append((node.name, child))
    if any(isinstance(node, ast.AsyncFunctionDef) for _, node in class_targets):
        return SolutionTransform(
            False, "async_target_not_supported", extraction_mode, None, None, raw_sha, source_sha, None, None
        )
    if len(class_targets) != 1:
        reason = "missing_target_function" if not class_targets else "ambiguous_class_method_target"
        return SolutionTransform(False, reason, extraction_mode, None, None, raw_sha, source_sha, None, None)

    owner, _ = class_targets[0]
    wrapper = f"\n\ndef {REFERENCE_ENTRY}(*args, **kwargs):\n    return {owner}().{function_name}(*args, **kwargs)\n"
    transformed = code.rstrip() + wrapper
    return SolutionTransform(
        True,
        "ok",
        extraction_mode,
        "class_method",
        owner,
        raw_sha,
        source_sha,
        _sha_text(transformed),
        transformed,
    )


def _unique(values: list[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for value in values:
        try:
            digest = stable_json_hash(value)
        except (TypeError, ValueError, RecursionError):
            continue
        if digest in seen:
            continue
        seen.add(digest)
        result.append(value)
    return result


def _mutations(value: Any, *, depth: int = 0) -> list[Any]:
    if depth > 3:
        return []
    if isinstance(value, bool):
        return [not value]
    if isinstance(value, int):
        int_candidates = [0, 1, -1, value - 1, value + 1, -value, value * 2]
        return _unique([item for item in int_candidates if abs(item) <= 10**12])
    if isinstance(value, float):
        if not math.isfinite(value):
            return []
        float_candidates = [0.0, 1.0, -1.0, value - 1.0, value + 1.0, -value, value * 2.0]
        return _unique([item for item in float_candidates if math.isfinite(item) and abs(item) <= 10**12])
    if isinstance(value, str):
        string_candidates = [
            "",
            value[:1],
            value[-1:] if value else "",
            value[::-1],
            value[: len(value) // 2],
            value + value[:1],
            value.lower(),
            value.upper(),
        ]
        return _unique(string_candidates)
    if value is None:
        return []
    if isinstance(value, list):
        list_candidates: list[Any] = [[], value[:1], value[-1:] if value else [], list(reversed(value))]
        if value:
            list_candidates.extend([value[1:], value[:-1], [value[0], *value]])
        for index, item in enumerate(value[:8]):
            for mutated in _mutations(item, depth=depth + 1)[:8]:
                copy = list(value)
                copy[index] = mutated
                list_candidates.append(copy)
        return _unique(list_candidates)
    if isinstance(value, dict):
        dict_candidates: list[Any] = []
        for key in sorted(value)[:8]:
            for mutated in _mutations(value[key], depth=depth + 1)[:8]:
                dict_copy = dict(value)
                dict_copy[key] = mutated
                dict_candidates.append(dict_copy)
        return _unique(dict_candidates)
    return []


def generate_input_proposals(
    *,
    candidate_id: str,
    existing_inputs: list[Any],
    maximum: int,
) -> list[dict[str, object]]:
    """Generate reward-independent deterministic input-only proposals from frozen existing inputs."""
    if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum <= 0:
        raise ValueError("maximum must be a positive integer")
    existing_hashes = {stable_json_hash(value) for value in existing_inputs}
    proposal_by_hash: dict[str, Any] = {}
    for input_value in existing_inputs:
        if isinstance(input_value, list):
            for arg_index, arg in enumerate(input_value):
                for mutated in _mutations(arg):
                    list_proposal = list(input_value)
                    list_proposal[arg_index] = mutated
                    digest = stable_json_hash(list_proposal)
                    if digest not in existing_hashes:
                        proposal_by_hash.setdefault(digest, list_proposal)
        elif isinstance(input_value, dict):
            for key in sorted(input_value):
                for mutated in _mutations(input_value[key]):
                    dict_proposal = dict(input_value)
                    dict_proposal[key] = mutated
                    digest = stable_json_hash(dict_proposal)
                    if digest not in existing_hashes:
                        proposal_by_hash.setdefault(digest, dict_proposal)
        else:
            for scalar_proposal in _mutations(input_value):
                digest = stable_json_hash(scalar_proposal)
                if digest not in existing_hashes:
                    proposal_by_hash.setdefault(digest, scalar_proposal)

    ranked: list[tuple[str, str, Any]] = []
    for digest, input_value in proposal_by_hash.items():
        rank = hashlib.sha256(f"{PROPOSAL_PROTOCOL}|{candidate_id}|{canonical_json(input_value)}".encode()).hexdigest()
        ranked.append((rank, digest, input_value))
    ranked.sort()
    return [
        {
            "proposal_id": hashlib.sha256(f"{PROPOSAL_PROTOCOL}|{candidate_id}|{digest}".encode()).hexdigest(),
            "proposal_rank_sha256": rank,
            "input": input_value,
        }
        for rank, digest, input_value in ranked[:maximum]
    ]
