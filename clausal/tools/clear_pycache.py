"""clear_pycache — remove __pycache__ dirs to avoid stale .pyc bytecode.

Usage:
    python -m clausal.tools.clear_pycache          # clear project tree
    python -m clausal.tools.clear_pycache /some/dir # clear specific root

Programmatic:
    from clausal.tools.clear_pycache import clear_pycache
    removed = clear_pycache()                       # returns list of removed dirs
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def clear_pycache(root: str | Path | None = None) -> list[Path]:
    """Remove all ``__pycache__`` directories under *root*.

    Parameters
    ----------
    root : path, optional
        Directory tree to scan.  Defaults to the project root
        (parent of the ``clausal`` package directory).

    Returns
    -------
    list[Path]
        Paths that were removed.
    """
    if root is None:
        root = Path(__file__).resolve().parent.parent.parent
    root = Path(root)

    # Skip directories that shouldn't be touched (virtualenvs, .git, etc.)
    _SKIP = {"venv", ".venv", "env", ".env", ".git", "node_modules", ".tox"}

    removed: list[Path] = []
    for dirpath, dirnames, _ in os.walk(root):
        # Prune skipped subtrees in-place.
        dirnames[:] = [d for d in dirnames if d not in _SKIP]

        if "__pycache__" in dirnames:
            target = Path(dirpath) / "__pycache__"
            shutil.rmtree(target, ignore_errors=True)
            removed.append(target)
            dirnames.remove("__pycache__")
    return removed


# ── CLI entry point ──────────────────────────────────────────────────────────

def main() -> None:
    root = sys.argv[1] if len(sys.argv) > 1 else None
    removed = clear_pycache(root)
    if removed:
        for p in removed:
            print(f"removed {p}")
        print(f"\n{len(removed)} __pycache__ dir(s) cleared.")
    else:
        print("No __pycache__ directories found.")


if __name__ == "__main__":
    main()
