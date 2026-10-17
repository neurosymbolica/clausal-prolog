"""Every ```clausal block in docs/*.md loads as a .clausal module, and its
test/1 and test/2 clauses pass.

Shared check logic lives in ``clausal/tools/doc_snippet_check.py``
(``check_clausal_blocks``).
"""

from pathlib import Path

from clausal.tools.doc_snippet_check import (
    CLAUSAL_PROLOG_FENCE_RE,
    check_clausal_blocks,
)

_DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"

#: Fragments that are not a whole program, keyed by (file, fence line).
#: Allowlist, not aspiration: a block that can load should load.
_KNOWN_DISPLAY_ONLY: set[tuple[str, int]] = set()


def test_clausal_blocks_load_and_pass():
    violations = check_clausal_blocks(
        _DOCS_DIR, known_display_only=_KNOWN_DISPLAY_ONLY)
    assert not violations, (
        f"{len(violations)} ```clausal block(s) fail:\n" + "\n".join(violations))


def test_the_checker_says_no(tmp_path):
    # A gate needs a case that it refuses, and one that it accepts.
    (tmp_path / "page.md").write_text(
        "```clausal\nok(1).\ntest(\"ok\") :- ok(1).\n```\n\n"
        "```clausal\nbad(1).\ntest(\"bad\") :- bad(2).\n```\n\n"
        "```clausal\nnot valid ( syntax\n```\n")
    v = check_clausal_blocks(tmp_path)
    assert len(v) == 2
    assert "page.md:6" in v[0] and "test(s) fail" in v[0]
    assert "page.md:11" in v[1] and "does not load" in v[1]


def test_the_fence_pattern_finds_clausal_but_not_seam_or_prolog():
    text = "```clausal\na.\n```\n```seam\nb\n```\n```prolog\nc.\n```\n"
    assert [m.group(1) for m in CLAUSAL_PROLOG_FENCE_RE.finditer(text)] == ["a.\n"]


def test_an_indented_block_inside_an_admonition_is_checked(tmp_path):
    # Found by docs batch 5: a column-0-only pattern skipped these silently.
    (tmp_path / "page.md").write_text(
        "!!! note\n\n    ```clausal\n    bad(1).\n    test(\"bad\") :- bad(2).\n    ```\n")
    v = check_clausal_blocks(tmp_path)
    assert len(v) == 1 and "page.md:3" in v[0] and "test(s) fail" in v[0]
