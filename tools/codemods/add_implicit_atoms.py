"""Codemod: add ``-implicit_atoms`` to .clausal files lacking an atom-mode
marker. Throwaway migration tool for the strict-atoms-by-default flip
(Task 3 / Phase 1 of the plan). Idempotent; skips files that already carry
``-strict_atoms`` or ``-implicit_atoms``.

Usage:
    python tools/codemods/add_implicit_atoms.py clausal tests/fixtures
"""
from __future__ import annotations

import re
import sys

_MARKER_RE = re.compile(r"^\s*-\s*(strict_atoms|implicit_atoms)\b")


def add_implicit_atoms(path: str) -> bool:
    """Insert ``-implicit_atoms`` before the first non-comment, non-blank
    line of *path*. Returns True if modified, False if skipped."""
    with open(path, "r") as fh:
        lines = fh.readlines()

    if any(_MARKER_RE.match(line) for line in lines):
        return False

    insert_at = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "" or stripped.startswith("#"):
            continue
        insert_at = i
        break
    else:
        # File is all comments/blank — append at end.
        insert_at = len(lines)

    lines.insert(insert_at, "-implicit_atoms\n")
    with open(path, "w") as fh:
        fh.writelines(lines)
    return True


_SKIP_DIRS = {
    # Golden output snapshots compared against prolog_to_clausal output;
    # arming them would break the round-trip assertion tests.
    "prolog_golden",
}


def _walk(roots: list[str]) -> int:
    import os
    changed = 0
    for root in roots:
        for dirpath, dirnames, files in os.walk(root):
            # Prune skip directories in-place so os.walk won't descend.
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for name in files:
                if name.endswith(".clausal"):
                    full = os.path.join(dirpath, name)
                    # Skip symlinks (e.g. Emacs lock files like .#foo.clausal).
                    if not os.path.isfile(full) or os.path.islink(full):
                        continue
                    if add_implicit_atoms(full):
                        changed += 1
    return changed


if __name__ == "__main__":
    roots = sys.argv[1:] or ["clausal", "tests/fixtures"]
    n = _walk(roots)
    print(f"add_implicit_atoms: modified {n} file(s)")
