"""The sole project boundary for importing pinned Open-R1 functionality.

Example:
    open_r1 = import_open_r1_module()
"""

from __future__ import annotations

from importlib import import_module, metadata
from types import ModuleType


class OpenR1UnavailableError(ImportError):
    """Raised when the pinned Open-R1 package is not installed."""


def import_open_r1_module(module_name: str = "open_r1") -> ModuleType:
    """Import Open-R1 or one of its submodules through the adapter boundary."""
    if module_name != "open_r1" and not module_name.startswith("open_r1."):
        raise ValueError(f"Expected an open_r1 module name, got {module_name!r}")

    try:
        return import_module(module_name)
    except ModuleNotFoundError as error:
        if error.name == "open_r1":
            raise OpenR1UnavailableError(
                "The pinned Open-R1 checkout is unavailable; run `make install` from the repository root."
            ) from error
        raise


def open_r1_version() -> str:
    """Return the installed Open-R1 distribution version."""
    try:
        return metadata.version("open-r1")
    except metadata.PackageNotFoundError as error:
        raise OpenR1UnavailableError(
            "The pinned Open-R1 checkout is unavailable; run `make install` from the repository root."
        ) from error
