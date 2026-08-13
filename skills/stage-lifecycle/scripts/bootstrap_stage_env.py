#!/usr/bin/env python3
"""Create a worktree-local Python environment without binding execution to main sources."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path


class StageEnvError(RuntimeError):
    pass


def _run(command: list[str], *, cwd: Path | None = None) -> None:
    try:
        subprocess.run(command, cwd=cwd, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise StageEnvError(f"command failed: {command[0]}") from exc


def _capture(command: list[str]) -> str:
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise StageEnvError(f"command failed: {command[0]}") from exc
    return result.stdout.strip()


def _site_packages(python: Path) -> Path:
    output = _capture(
        [
            str(python),
            "-c",
            "import site; print(site.getsitepackages()[0])",
        ]
    )
    path = Path(output).resolve()
    if not path.is_dir():
        raise StageEnvError("site-packages directory is unavailable")
    return path


def _package_version(python: Path, package: str) -> str:
    return _capture(
        [
            str(python),
            "-c",
            (f"import importlib.metadata as metadata; print(metadata.version({package!r}))"),
        ]
    )


def _verify_overlay_tools(stage_python: Path, stage_venv: Path) -> dict[str, str]:
    ruff_bin = stage_venv / "bin" / "ruff"
    if not ruff_bin.is_file():
        raise StageEnvError("stage-local ruff executable is unavailable")
    checks = {
        "ruff": [str(stage_python), "-m", "ruff", "--version"],
        "mypy": [str(stage_python), "-m", "mypy", "--version"],
        "pytest": [str(stage_python), "-m", "pytest", "--version"],
    }
    return {name: _capture(command) for name, command in checks.items()}


def _verify_sources(stage_python: Path, stage_root: Path) -> dict[str, str]:
    output = _capture(
        [
            str(stage_python),
            "-c",
            (
                "import json,sys,code_verifier,open_r1; "
                "print(json.dumps({'python': sys.version.split()[0], "
                "'code_verifier': code_verifier.__file__, 'open_r1': open_r1.__file__}))"
            ),
        ]
    )
    payload = json.loads(output)
    for key in ("code_verifier", "open_r1"):
        source = Path(payload[key]).resolve()
        try:
            source.relative_to(stage_root)
        except ValueError as exc:
            raise StageEnvError(f"{key} is not bound to the stage worktree") from exc
    return payload


def bootstrap(primary_root: Path, stage_worktree: Path, mode: str) -> dict[str, str]:
    primary_root = primary_root.resolve()
    stage_worktree = stage_worktree.resolve()
    worktrees_root = (primary_root / ".worktrees").resolve()
    try:
        stage_worktree.relative_to(worktrees_root)
    except ValueError as exc:
        raise StageEnvError("stage worktree must be under primary .worktrees/") from exc

    primary_python = primary_root / ".venv" / "bin" / "python"
    if not primary_python.is_file():
        raise StageEnvError("primary .venv/bin/python is unavailable")
    uv = shutil.which("uv")
    if uv is None:
        raise StageEnvError("uv is unavailable")

    submodule_command = [
        "git",
        "-C",
        str(stage_worktree),
        "submodule",
        "update",
        "--init",
        "--recursive",
    ]
    primary_open_r1 = primary_root / "third_party" / "open-r1"
    if primary_open_r1.is_dir():
        submodule_command.extend(["--reference", str(primary_open_r1)])
    submodule_command.append("third_party/open-r1")
    _run(submodule_command)

    stage_venv = stage_worktree / ".venv"
    _run([uv, "venv", "--clear", "--python", str(primary_python), str(stage_venv)])
    stage_python = stage_venv / "bin" / "python"

    if mode == "overlay":
        primary_site = _site_packages(primary_python)
        stage_site = _site_packages(stage_python)
        (stage_site / "_primary_runtime_deps.pth").write_text(f"{primary_site}\n", encoding="utf-8")
        ruff_version = _package_version(primary_python, "ruff")
        _run(
            [
                uv,
                "pip",
                "install",
                "--python",
                str(stage_python),
                "--no-deps",
                f"ruff=={ruff_version}",
            ]
        )
        _run(
            [
                uv,
                "pip",
                "install",
                "--python",
                str(stage_python),
                "--no-deps",
                "--editable",
                str(stage_worktree / "third_party" / "open-r1"),
                "--editable",
                str(stage_worktree),
            ]
        )
    elif mode == "full":
        _run(
            [
                uv,
                "sync",
                "--extra",
                "dev",
                "--extra",
                "gpu",
                "--extra",
                "training",
            ],
            cwd=stage_worktree,
        )
    else:
        raise StageEnvError(f"unsupported mode: {mode}")

    payload = _verify_sources(stage_python, stage_worktree)
    if mode == "overlay":
        payload["tools"] = _verify_overlay_tools(stage_python, stage_venv)
    payload["mode"] = mode
    payload["stage_python"] = str(stage_python)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--primary-root", required=True, type=Path)
    parser.add_argument("--stage-worktree", required=True, type=Path)
    parser.add_argument("--mode", choices=("overlay", "full"), default="overlay")
    args = parser.parse_args()
    try:
        result = bootstrap(args.primary_root, args.stage_worktree, args.mode)
    except StageEnvError as exc:
        print(f"STAGE_ENV_BOOTSTRAP_FAILED: {exc}")
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
