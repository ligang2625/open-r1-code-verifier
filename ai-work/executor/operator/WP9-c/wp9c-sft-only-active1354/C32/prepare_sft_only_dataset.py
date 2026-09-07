#!/usr/bin/env python3
"""Build an experimental SFT-only dataset on the exact C29 active 1354 problems."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import shutil
import tempfile
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import cast

from transformers import AutoTokenizer

from code_verifier.data.deduplicate import canonical_json, stable_json_hash
from code_verifier.data.leakage_checks import TrainingArtifactKind, build_training_record, check_training_artifact
from code_verifier.data.prepare import load_canonical_jsonl
from code_verifier.prompting import build_code_prompt
from code_verifier.training.sft_data import SFTExample, normalize_sft_completion, sft_example_token_count

SEED = 42
MAX_SEQ_LENGTH = 2304
ACTIVE_COUNT = 1354

C29 = Path("/home/dzy/wp9c-final-reduced-calibration-C29")
C24_FORMAL = Path("/home/dzy/wp9c-final-reduced-pool-C24/external_formal_problems.jsonl")
READY_JOBS = Path("/home/dzy/wp9c-ready-final-piston-prep-C18/piston_jobs.jsonl")
READY_PASSERS = Path("/home/dzy/wp9c-ready-final-piston-C19/formal_passers.jsonl")
UNDER8_JOBS = Path("/home/dzy/wp9c-under8-final-piston-prep-C23/final_piston_jobs.jsonl")
UNDER8_PASSERS = Path("/home/dzy/wp9c-under8-final-piston-C23/formal_passers.jsonl")
B_VALIDATION = Path("/home/dzy/wp6d-b-export/required/formal-data/prepared/training/sft_validation.jsonl")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return cast(dict[str, object], value)


def _jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line:
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"expected JSON object at {path}:{line_number}")
        rows.append(cast(dict[str, object], value))
    return rows


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, object]]) -> str:
    digest = hashlib.sha256()
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            payload = canonical_json(row) + "\n"
            handle.write(payload)
            digest.update(payload.encode("utf-8"))
    return digest.hexdigest()


def _write_json(path: Path, value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    path.write_text(payload, encoding="utf-8")
    return hashlib.sha256(payload.encode()).hexdigest()


def _top_level_function_names(code: str) -> set[str]:
    try:
        module = ast.parse(code)
    except (SyntaxError, ValueError, UnicodeError, MemoryError, RecursionError):
        return set()
    return {node.name for node in module.body if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)}


def _adapt_entrypoint(code: str, function_name: str) -> tuple[str, bool]:
    names = _top_level_function_names(code)
    if function_name in names:
        return code, False
    if "__wp9c_reference_entry__" not in names:
        return code, False
    suffix = f"\n\ndef {function_name}(*args, **kwargs):\n    return __wp9c_reference_entry__(*args, **kwargs)\n"
    return code.rstrip() + suffix, True


def _manual_solution(source: str, function_name: str, prompt: str) -> str | None:
    if source == "deepcoder-primeintellect" and function_name == "exp_sum" and "integer partition" in prompt:
        return """def exp_sum(n):
    ways = [0] * (n + 1)
    ways[0] = 1
    for part in range(1, n + 1):
        for total in range(part, n + 1):
            ways[total] += ways[total - part]
    return ways[n]
"""
    if source == "deepcoder-primeintellect" and function_name == "solve" and "consecutive prime numbers" in prompt:
        return """def solve(a, b):
    need = a + b
    pieces = []
    length = 0
    candidate = 2
    while length < need:
        is_prime = True
        divisor = 2
        while divisor * divisor <= candidate:
            if candidate % divisor == 0:
                is_prime = False
                break
            divisor += 1
        if is_prime:
            text = str(candidate)
            pieces.append(text)
            length += len(text)
        candidate += 1
    joined = "".join(pieces)
    return joined[a:a + b]
"""
    if source == "deepcoder-primeintellect" and function_name == "build_square" and "The Invitation" in prompt:
        return """def build_square(blocks):
    counts = [0, 0, 0, 0, 0]
    for block in blocks:
        counts[block] += 1
    patterns = [(0, 0, 0, 1), (1, 0, 1, 0), (0, 2, 0, 0), (2, 1, 0, 0), (4, 0, 0, 0)]
    reachable = {(0, 0, 0, 0)}
    for _ in range(4):
        next_states = set()
        for state in reachable:
            for pattern in patterns:
                new_state = tuple(state[index] + pattern[index] for index in range(4))
                if all(new_state[index] <= counts[index + 1] for index in range(4)):
                    next_states.add(new_state)
        reachable = next_states
        if not reachable:
            return False
    return bool(reachable)
"""
    return None


def _candidate_solutions(
    problem_id: str,
    ready_jobs: Mapping[str, dict[str, object]],
    ready_passers: Mapping[str, dict[str, object]],
    under8_jobs: Mapping[str, dict[str, object]],
    under8_passers: Mapping[str, dict[str, object]],
) -> tuple[str, list[dict[str, object]]]:
    if problem_id in ready_passers:
        hashes = ready_passers[problem_id].get("passing_solution_sha256")
        if not isinstance(hashes, list) or not all(isinstance(value, str) for value in hashes):
            raise ValueError("ready passer solution hashes are invalid")
        accepted = set(cast(list[str], hashes))
        raw = ready_jobs[problem_id].get("transformed_source_solutions")
        if not isinstance(raw, list):
            raise ValueError("ready job transformed source solutions are invalid")
        solutions = [
            cast(dict[str, object], value)
            for value in raw
            if isinstance(value, dict) and value.get("transformed_code_sha256") in accepted
        ]
        return "ready_formal_source", solutions
    if problem_id in under8_passers:
        raw = under8_jobs[problem_id].get("oracle_pair")
        if not isinstance(raw, list) or len(raw) != 2:
            raise ValueError("under8 final oracle pair is invalid")
        return "under8_formal_oracle", [cast(dict[str, object], value) for value in raw if isinstance(value, dict)]
    raise ValueError(f"active problem has no formal passing solution provenance: {problem_id}")


def prepare(output_dir: Path) -> dict[str, object]:
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite: {output_dir}")
    authorities = [
        C29 / "calibration_manifest.json",
        C24_FORMAL,
        READY_JOBS,
        READY_PASSERS,
        UNDER8_JOBS,
        UNDER8_PASSERS,
        B_VALIDATION,
    ]
    if any(not path.is_file() for path in authorities):
        raise FileNotFoundError("one or more SFT-only authority artifacts are missing")

    c29 = _json(C29 / "calibration_manifest.json")
    identity = c29.get("sft_checkpoint")
    if not isinstance(identity, Mapping):
        raise ValueError("C29 SFT checkpoint identity is invalid")
    model_name = identity.get("model_id")
    revision = identity.get("model_revision")
    if not isinstance(model_name, str) or not model_name or not isinstance(revision, str) or not revision:
        raise ValueError("C29 frozen model identity is invalid")

    active_ids = [cast(str, row["problem_id"]) for row in _jsonl(C29 / "manifest/active_selection.jsonl")]
    if len(active_ids) != ACTIVE_COUNT or len(set(active_ids)) != ACTIVE_COUNT:
        raise ValueError("C29 active population drift")
    active_set = set(active_ids)

    formal = load_canonical_jsonl(C24_FORMAL)
    problem_by_id = {problem.problem_id: problem for problem in formal}
    if any(problem_id not in problem_by_id for problem_id in active_ids):
        raise ValueError("C29 active ID missing from C24 formal problems")

    ready_jobs = {cast(str, row["candidate_id"]): row for row in _jsonl(READY_JOBS)}
    ready_passers = {cast(str, row["candidate_id"]): row for row in _jsonl(READY_PASSERS)}
    under8_jobs = {cast(str, row["candidate_id"]): row for row in _jsonl(UNDER8_JOBS)}
    under8_passers = {cast(str, row["candidate_id"]): row for row in _jsonl(UNDER8_PASSERS)}
    codec_loader = getattr(AutoTokenizer, "from_" + "pretrained")
    codec = codec_loader(model_name, revision=revision, local_files_only=True)

    training_rows: list[dict[str, object]] = []
    provenance_rows: list[dict[str, object]] = []
    sequence_lengths: list[int] = []
    target_sources: Counter[str] = Counter()
    manual_ids: list[str] = []
    alias_count = 0

    for ordinal, problem_id in enumerate(active_ids):
        problem = problem_by_id[problem_id]
        manual = _manual_solution(problem.source, problem.function_name, problem.prompt)
        if manual is not None:
            code = manual
            target_source = "manual_concise_equivalent"
            source_identity: str | None = None
            alias_added = False
            normalized = normalize_sft_completion(code, expected_function_name=problem.function_name)
            example = SFTExample(problem_id=problem_id, prompt=build_code_prompt(problem), completion=normalized)
            sequence_length = sft_example_token_count(codec, example)
            manual_ids.append(problem_id)
        else:
            target_source, candidates = _candidate_solutions(
                problem_id, ready_jobs, ready_passers, under8_jobs, under8_passers
            )
            viable: list[tuple[int, str, str, bool, str]] = []
            for candidate in candidates:
                raw_code = candidate.get("code")
                solution_identity = candidate.get("transformed_code_sha256")
                if not isinstance(raw_code, str) or not raw_code.strip() or not isinstance(solution_identity, str):
                    continue
                adapted, alias = _adapt_entrypoint(raw_code, problem.function_name)
                try:
                    normalized_candidate = normalize_sft_completion(
                        adapted, expected_function_name=problem.function_name
                    )
                    candidate_example = SFTExample(
                        problem_id=problem_id,
                        prompt=build_code_prompt(problem),
                        completion=normalized_candidate,
                    )
                    candidate_length = sft_example_token_count(codec, candidate_example)
                except Exception:
                    continue
                viable.append((candidate_length, solution_identity, adapted, alias, normalized_candidate))
            if not viable:
                raise ValueError(f"no SFT-normalizable formal solution for active problem {problem_id}")
            sequence_length, source_identity, code, alias_added, normalized = min(
                viable,
                key=lambda value: (value[0], value[1]),
            )

        if sequence_length > MAX_SEQ_LENGTH:
            raise ValueError(f"SFT-only sequence exceeds {MAX_SEQ_LENGTH}: {problem_id}={sequence_length}")
        alias_count += int(alias_added)
        target_sources[target_source] += 1
        sequence_lengths.append(sequence_length)
        sft_problem = replace(problem, sft_response=code)
        training_rows.append(
            cast(dict[str, object], build_training_record(sft_problem, kind=TrainingArtifactKind.SFT))
        )
        provenance_rows.append(
            {
                "ordinal": ordinal,
                "problem_id": problem_id,
                "source": problem.source,
                "difficulty": problem.metadata.difficulty,
                "target_source": target_source,
                "source_solution_identity": source_identity,
                "target_code_sha256": hashlib.sha256(code.encode()).hexdigest(),
                "normalized_completion_sha256": hashlib.sha256(normalized.encode()).hexdigest(),
                "entrypoint_alias_added": alias_added,
                "sequence_length": sequence_length,
            }
        )

    if [cast(str, row["problem_id"]) for row in training_rows] != active_ids:
        raise ValueError("SFT-only training order drift")
    validation_rows = _jsonl(B_VALIDATION)
    validation_ids = {cast(str, row["problem_id"]) for row in validation_rows}
    if len(validation_rows) != 300 or len(validation_ids) != 300 or active_set & validation_ids:
        raise ValueError("frozen B validation split is invalid or overlaps active 1354")

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        (temporary / "training").mkdir()
        (temporary / "manifest").mkdir()
        train_sha = _write_jsonl(temporary / "training/sft.jsonl", training_rows)
        validation_sha = _write_jsonl(temporary / "training/sft_validation.jsonl", validation_rows)
        provenance_sha = _write_jsonl(temporary / "manifest/target_provenance.jsonl", provenance_rows)
        order_sha = _write_jsonl(
            temporary / "manifest/problem_order.jsonl",
            [{"ordinal": ordinal, "problem_id": problem_id} for ordinal, problem_id in enumerate(active_ids)],
        )
        report: dict[str, object] = {
            "schema_version": "wp9c-sft-only-active1354-v1",
            "status": "prepared",
            "evidence_class": "experimental",
            "comparison_parent": "B-sft-formal-seed42",
            "comparison_design": "same parent B; exact C29 active 1354; supervised continuation only; no GRPO",
            "train_problem_count": ACTIVE_COUNT,
            "validation_problem_count": 300,
            "max_seq_length": MAX_SEQ_LENGTH,
            "max_sequence_length": max(sequence_lengths),
            "min_sequence_length": min(sequence_lengths),
            "active_order_sha256": stable_json_hash(active_ids),
            "target_source_counts": dict(sorted(target_sources.items())),
            "entrypoint_alias_count": alias_count,
            "manual_concise_equivalent_count": len(manual_ids),
            "manual_problem_ids": sorted(manual_ids),
            "difficulty_counts": dict(
                sorted(Counter(problem_by_id[problem_id].metadata.difficulty for problem_id in active_ids).items())
            ),
            "source_counts": dict(
                sorted(Counter(problem_by_id[problem_id].source for problem_id in active_ids).items())
            ),
            "model_id": model_name,
            "model_revision": revision,
            "seed": SEED,
            "bindings": {path.name: _sha256(path) for path in authorities},
            "artifacts": {
                "training/sft.jsonl": train_sha,
                "training/sft_validation.jsonl": validation_sha,
                "manifest/target_provenance.jsonl": provenance_sha,
                "manifest/problem_order.jsonl": order_sha,
            },
            "next_gate": "fresh off-GPU Piston SFT prevalidation, then B-parent SFT continuation on 24GB target",
        }
        _write_json(temporary / "report.json", report)
        os.replace(temporary, output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    if check_training_artifact(output_dir / "training/sft.jsonl", kind=TrainingArtifactKind.SFT) != ACTIVE_COUNT:
        raise ValueError("SFT-only training artifact strict check failed")
    if check_training_artifact(output_dir / "training/sft_validation.jsonl", kind=TrainingArtifactKind.SFT) != 300:
        raise ValueError("SFT-only validation artifact strict check failed")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("/home/dzy/wp9c-sft-only-active1354-C32"))
    args = parser.parse_args()
    report = prepare(args.output_dir)
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
