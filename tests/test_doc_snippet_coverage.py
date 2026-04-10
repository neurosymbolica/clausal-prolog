"""Ratchet test: ensure the number of # skip blocks in docs never increases.

As doc snippets are migrated to --8<-- fixture references, decrease
MAX_ALLOWED_SKIPS to prevent regressions.
"""

import re
from pathlib import Path

_DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
_CLAUSAL_FENCE_RE = re.compile(r"```clausal\n(.*?)```", re.DOTALL)

# Decrease this as migrations proceed.  Current baseline: 810.
# After lists.md pilot migration: 810 -> 808.
# After builtins.md migration (Phase 1): 808 -> 575.
MAX_ALLOWED_SKIPS = 575


def _count_skip_blocks() -> int:
    total = 0
    for md in sorted(_DOCS_DIR.glob("*.md")):
        text = md.read_text()
        for m in _CLAUSAL_FENCE_RE.finditer(text):
            first_line = m.group(1).lstrip().split("\n", 1)[0].strip()
            if first_line in ("# skip", "# clausal: skip"):
                total += 1
    return total


def test_skip_count_not_increasing():
    actual = _count_skip_blocks()
    assert actual <= MAX_ALLOWED_SKIPS, (
        f"# skip block count increased to {actual} "
        f"(max allowed: {MAX_ALLOWED_SKIPS}). "
        f"New doc snippets should use --8<-- fixture references instead."
    )
