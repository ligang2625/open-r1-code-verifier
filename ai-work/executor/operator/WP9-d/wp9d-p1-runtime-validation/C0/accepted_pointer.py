#!/usr/bin/env python3
"""Atomically record the currently accepted successful artifact for one WP9-d P1 phase."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--detail", required=True)
    parser.add_argument("--retry-tag", default="")
    parser.add_argument("--handoff-commit", required=True)
    parser.add_argument("--primary-artifact", type=Path, required=True)
    parser.add_argument("--phase-meta", type=Path, default=None)
    parser.add_argument("--operator-evidence", type=Path, required=True)
    args = parser.parse_args()

    if re.fullmatch(r"[0-9a-f]{40}", args.handoff_commit) is None:
        raise SystemExit("accepted P1 pointer requires exact handoff commit")
    primary = args.primary_artifact.resolve(strict=True)
    evidence = args.operator_evidence.resolve(strict=True)
    phase_meta = args.phase_meta.resolve(strict=True) if args.phase_meta is not None else None
    evidence_value = json.loads(evidence.read_text(encoding="utf-8"))
    if not isinstance(evidence_value, dict) or evidence_value.get("gate_status") != "passed":
        raise SystemExit("accepted P1 pointer requires passed operator evidence")
    if evidence_value.get("handoff_commit") != args.handoff_commit:
        raise SystemExit("accepted P1 pointer evidence commit mismatch")

    value = {
        "schema_version": "wp9d-p1-accepted-v1",
        "phase": args.phase,
        "detail": args.detail,
        "retry_tag": args.retry_tag or None,
        "handoff_commit": args.handoff_commit,
        "primary_artifact": str(primary),
        "phase_meta": str(phase_meta) if phase_meta is not None else None,
        "operator_evidence": str(evidence),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=args.output.parent,
            prefix=f".{args.output.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(value, handle, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, args.output)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink(missing_ok=True)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
