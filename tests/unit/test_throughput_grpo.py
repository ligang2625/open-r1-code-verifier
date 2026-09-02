from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from code_verifier import throughput
from tests.unit.throughput_fixture import write_grpo_probe


def test_grpo_verification_worker_selection_uses_reward_group_parity(tmp_path: Path) -> None:
    start = datetime(2026, 9, 2, 0, 0, tzinfo=timezone.utc)
    baseline = write_grpo_probe(
        tmp_path,
        name="grpo-base",
        reward_mode="public",
        workers=8,
        start=start,
        duration_seconds=10.0,
    )
    worker16 = write_grpo_probe(
        tmp_path,
        name="grpo-16",
        reward_mode="public",
        workers=16,
        start=start,
        duration_seconds=4.0,
    )
    worker32_bad = write_grpo_probe(
        tmp_path,
        name="grpo-32-bad",
        reward_mode="public",
        workers=32,
        start=start,
        duration_seconds=1.0,
        reward_drift=True,
    )
    worker64 = write_grpo_probe(
        tmp_path,
        name="grpo-64",
        reward_mode="public",
        workers=64,
        start=start,
        duration_seconds=6.0,
    )

    selected, report = throughput._select_grpo_verification(
        {"baseline": str(baseline), "candidates": [str(worker16), str(worker32_bad), str(worker64)]}
    )

    assert selected == 16
    candidates = report["candidates"]
    assert isinstance(candidates, list)
    assert candidates[1]["rejection"] == "reward_parity_mismatch"


def test_paired_grpo_recommendation_uses_fifteen_percent_threshold(tmp_path: Path) -> None:
    start = datetime(2026, 9, 2, 0, 0, tzinfo=timezone.utc)
    seq_public = write_grpo_probe(
        tmp_path,
        name="seq-public",
        reward_mode="public",
        workers=16,
        start=start,
        duration_seconds=10.0,
    )
    seq_hidden = write_grpo_probe(
        tmp_path,
        name="seq-hidden",
        reward_mode="hidden",
        workers=16,
        start=start,
        duration_seconds=10.0,
    )

    for suffix, concurrent_seconds, expected in (
        ("gain14", 17.2, "sequential"),
        ("gain15", 17.0, "concurrent"),
    ):
        con_public = write_grpo_probe(
            tmp_path,
            name=f"{suffix}-public",
            reward_mode="public",
            workers=16,
            start=start,
            duration_seconds=concurrent_seconds,
        )
        con_hidden = write_grpo_probe(
            tmp_path,
            name=f"{suffix}-hidden",
            reward_mode="hidden",
            workers=16,
            start=start,
            duration_seconds=concurrent_seconds,
        )
        recommendation, report = throughput._paired_grpo_decision(
            {
                "sequential": {"public": str(seq_public), "hidden": str(seq_hidden)},
                "concurrent": {"public": str(con_public), "hidden": str(con_hidden)},
            }
        )
        assert recommendation == expected
        assert report["stable"] is True
