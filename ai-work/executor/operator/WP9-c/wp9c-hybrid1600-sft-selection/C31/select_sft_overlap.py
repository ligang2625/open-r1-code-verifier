#!/usr/bin/env python3
"""Select a deterministic 246-problem SFT-overlap extension for a 1600-problem experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import tempfile
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import cast

from code_verifier.data.deduplicate import canonical_json, stable_json_hash

SEED = 42
NAMESPACE = "wp9c-hybrid1600-sft-overlap-v1"
BASE_COUNT = 1354
ADD_COUNT = 246
FINAL_COUNT = 1600
SFT_REUSE_COUNT = 750

C29 = Path("/home/dzy/wp9c-final-reduced-calibration-C29")
C24 = Path("/home/dzy/wp9c-final-reduced-pool-C24")
WP9A = Path("/home/dzy/wp9a-refresh-seed42-e2-final-run4")
FORMAL_SFT = Path("/home/dzy/wp6d-b-export/required/formal-data/prepared/training/sft.jsonl")

EXPECTED = {
    "c29_manifest_sha256": "5593fe90c19a096678f19e45ca6736e0fc97d242e4f27f92f0b10bb303077d5b",
    "c24_sft_reuse_audit_sha256": "c24a9909e3ce06f4db95ff7639254e1a083b8a447d0f565a466d921f28fc5f6c",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _rank(problem_id: str) -> str:
    return hashlib.sha256(f"{NAMESPACE}|{SEED}|{problem_id}".encode()).hexdigest()


def _stratum_rank(source: str, difficulty: str) -> str:
    return hashlib.sha256(f"{NAMESPACE}|stratum|{SEED}|{source}|{difficulty}".encode()).hexdigest()


def _allocations(populations: Mapping[tuple[str, str], int], count: int) -> dict[tuple[str, str], int]:
    total = sum(populations.values())
    if total < count:
        raise ValueError("selection population is too small")
    exact = {key: count * value / total for key, value in populations.items()}
    allocated = {key: math.floor(value) for key, value in exact.items()}
    remaining = count - sum(allocated.values())
    order = sorted(
        populations,
        key=lambda key: (-(exact[key] - allocated[key]), _stratum_rank(*key)),
    )
    for key in order[:remaining]:
        allocated[key] += 1
    if sum(allocated.values()) != count:
        raise ValueError("largest-remainder allocation failed")
    return allocated


def select(output_dir: Path) -> dict[str, object]:
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite: {output_dir}")
    if _sha256(C29 / "calibration_manifest.json") != EXPECTED["c29_manifest_sha256"]:
        raise ValueError("C29 manifest identity drift")
    if _sha256(C24 / "sft_reuse_audit.jsonl") != EXPECTED["c24_sft_reuse_audit_sha256"]:
        raise ValueError("C24 SFT reuse audit identity drift")

    active_rows = _jsonl(C29 / "manifest/active_selection.jsonl")
    active_ids = [cast(str, row["problem_id"]) for row in active_rows]
    if len(active_ids) != BASE_COUNT or len(set(active_ids)) != BASE_COUNT:
        raise ValueError("C29 active population drift")

    sft_rows = _jsonl(FORMAL_SFT)
    formal_sft_ids = {cast(str, row["problem_id"]) for row in sft_rows}
    if len(sft_rows) != 2500 or len(formal_sft_ids) != 2500:
        raise ValueError("frozen formal SFT dataset count drift")
    if set(active_ids) & formal_sft_ids:
        raise ValueError("C29 active pool unexpectedly overlaps frozen formal SFT")

    wp9a_selection = _jsonl(WP9A / "manifest/selection.jsonl")
    candidates = [row for row in wp9a_selection if row.get("overlap_origin") == "sft_reuse"]
    if len(candidates) != SFT_REUSE_COUNT:
        raise ValueError("WP9-a SFT reuse population drift")
    candidate_ids = [cast(str, row["problem_id"]) for row in candidates]
    if len(set(candidate_ids)) != SFT_REUSE_COUNT or any(
        problem_id not in formal_sft_ids for problem_id in candidate_ids
    ):
        raise ValueError("SFT-reuse candidates are not an exact unique subset of formal SFT")

    groups: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in candidates:
        source = row.get("source")
        difficulty = row.get("difficulty")
        if not isinstance(source, str) or not source or not isinstance(difficulty, str) or not difficulty:
            raise ValueError("SFT-reuse candidate identity metadata is invalid")
        groups[(source, difficulty)].append(row)
    populations = {key: len(rows) for key, rows in groups.items()}
    allocations = _allocations(populations, ADD_COUNT)

    selected: list[dict[str, object]] = []
    reserve: list[dict[str, object]] = []
    for key in sorted(groups):
        rows = sorted(groups[key], key=lambda row: (_rank(cast(str, row["problem_id"])), cast(str, row["problem_id"])))
        take = allocations[key]
        selected.extend(rows[:take])
        reserve.extend(rows[take:])
    selected.sort(key=lambda row: (_rank(cast(str, row["problem_id"])), cast(str, row["problem_id"])))
    reserve.sort(key=lambda row: (_rank(cast(str, row["problem_id"])), cast(str, row["problem_id"])))

    selected_ids = [cast(str, row["problem_id"]) for row in selected]
    reserve_ids = [cast(str, row["problem_id"]) for row in reserve]
    if len(selected_ids) != ADD_COUNT or len(reserve_ids) != SFT_REUSE_COUNT - ADD_COUNT:
        raise ValueError("selected/reserve count drift")
    if set(selected_ids) & set(active_ids) or set(reserve_ids) & set(active_ids):
        raise ValueError("SFT extension overlaps C29 active pool")
    if set(selected_ids) & set(reserve_ids) or set(selected_ids) | set(reserve_ids) != set(candidate_ids):
        raise ValueError("selected/reserve partition drift")

    hybrid_ids = [*active_ids, *selected_ids]
    if len(hybrid_ids) != FINAL_COUNT or len(set(hybrid_ids)) != FINAL_COUNT:
        raise ValueError("hybrid 1600 identity drift")

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        selected_out = [
            {
                "ordinal": ordinal,
                "problem_id": cast(str, row["problem_id"]),
                "source": cast(str, row["source"]),
                "difficulty": cast(str, row["difficulty"]),
                "overlap_origin": "sft_reuse",
                "selection_rank_sha256": _rank(cast(str, row["problem_id"])),
            }
            for ordinal, row in enumerate(selected)
        ]
        reserve_out = [
            {
                "ordinal": ordinal,
                "problem_id": cast(str, row["problem_id"]),
                "source": cast(str, row["source"]),
                "difficulty": cast(str, row["difficulty"]),
                "overlap_origin": "sft_reuse",
                "selection_rank_sha256": _rank(cast(str, row["problem_id"])),
            }
            for ordinal, row in enumerate(reserve)
        ]
        selected_sha = _write_jsonl(temporary / "selected_sft_overlap.jsonl", selected_out)
        reserve_sha = _write_jsonl(temporary / "reserve_sft_overlap.jsonl", reserve_out)
        hybrid_sha = _write_jsonl(
            temporary / "hybrid_problem_order.jsonl",
            [
                {
                    "ordinal": ordinal,
                    "problem_id": problem_id,
                    "overlap_origin": "external_new" if ordinal < BASE_COUNT else "sft_reuse",
                }
                for ordinal, problem_id in enumerate(hybrid_ids)
            ],
        )
        selected_source = Counter(cast(str, row["source"]) for row in selected_out)
        selected_difficulty = Counter(cast(str, row["difficulty"]) for row in selected_out)
        population_source = Counter(cast(str, row["source"]) for row in candidates)
        population_difficulty = Counter(cast(str, row["difficulty"]) for row in candidates)
        report: dict[str, object] = {
            "schema_version": "wp9c-hybrid1600-sft-overlap-selection-v1",
            "status": "completed",
            "evidence_class": "experimental",
            "seed": SEED,
            "selection_namespace": NAMESPACE,
            "base_c29_count": BASE_COUNT,
            "sft_reuse_population_count": SFT_REUSE_COUNT,
            "selected_sft_overlap_count": ADD_COUNT,
            "reserve_sft_overlap_count": SFT_REUSE_COUNT - ADD_COUNT,
            "hybrid_problem_count": FINAL_COUNT,
            "sft_overlap_fraction": ADD_COUNT / FINAL_COUNT,
            "selected_source_counts": dict(sorted(selected_source.items())),
            "selected_difficulty_counts": dict(sorted(selected_difficulty.items())),
            "candidate_source_counts": dict(sorted(population_source.items())),
            "candidate_difficulty_counts": dict(sorted(population_difficulty.items())),
            "stratum_populations": {
                f"{source}|{difficulty}": populations[(source, difficulty)]
                for source, difficulty in sorted(populations)
            },
            "stratum_allocations": {
                f"{source}|{difficulty}": allocations[(source, difficulty)]
                for source, difficulty in sorted(allocations)
            },
            "base_active_order_sha256": stable_json_hash(active_ids),
            "selected_sft_order_sha256": stable_json_hash(selected_ids),
            "reserve_sft_order_sha256": stable_json_hash(reserve_ids),
            "hybrid_order_sha256": stable_json_hash(hybrid_ids),
            "bindings": {
                **EXPECTED,
                "wp9a_selection_sha256": _sha256(WP9A / "manifest/selection.jsonl"),
                "formal_sft_sha256": _sha256(FORMAL_SFT),
            },
            "artifacts": {
                "selected_sft_overlap.jsonl": selected_sha,
                "reserve_sft_overlap.jsonl": reserve_sha,
                "hybrid_problem_order.jsonl": hybrid_sha,
            },
            "notes": {
                "mutates_c29": False,
                "formal_pool_claim": False,
                "fresh_calibration_required_before_production_grpo": True,
                "reason": "the 246 additions were seen during B SFT and have no accepted current calibration class",
            },
        }
        _write_json(temporary / "report.json", report)
        os.replace(temporary, output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("/home/dzy/wp9c-hybrid1600-sft-selection-C31"))
    args = parser.parse_args()
    report = select(args.output_dir)
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
