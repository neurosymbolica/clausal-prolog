"""Coverage tests for code blocks in core docs/.

1. No # skip blocks allowed (ratchet at 0).
2. Every seam block (```seam) must be either a --8<-- snippet reference,
   contain at least one Test clause, or compile successfully.

Per-package equivalents live at
``packages/clausal-<pkg>/tests/test_doc_integrity.py``. Shared check
logic lives in ``clausal/tools/doc_snippet_check.py``.
"""

from pathlib import Path

from clausal.tools.doc_snippet_check import (
    check_no_raw_untested_blocks,
    check_no_skip_blocks,
)

_DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"

_HOWTO = (
    "See implementation_plans/docs/DOC_SNIPPET_TESTING.md for the pattern: "
    "create a section in tests/fixtures/docs/<page>_sigs.txt (display) "
    "or tests/fixtures/docs/<page>_examples.seam (executable), "
    "add companion tests in tests/fixtures/docs/<page>_sig_tests.seam, "
    'then reference via --8<-- "tests/fixtures/docs/<file>:<section>" '
    "in the markdown."
)

# Pre-existing display fragments that don't compile standalone — partial
# examples / pseudo-code in guide pages. Allowlist, not aspiration: do not
# grow this set. New blocks should compile or be moved to fixtures.
_KNOWN_UNCOMPILABLE = {
    # import.md: two `# caller.seam` blocks that `-import_from(lib, …)` a
    # fictional library and illustrate cross-module name scoping; the first
    # deliberately documents a runtime failure. Neither is standalone-compilable.
    #
    # These are keyed by fence line, so prose inserted ABOVE them shifts every
    # one; the numbers below match docs/import.md after the adapter-`is` note (2026-10-04).
    ("import.md", 459),
    ("import.md", 501),
    # import.md: one more `# caller.seam` block that `-import_from(lib, …)`
    # a fictional library. Not standalone-compilable.
    ("import.md", 566),
}


def test_no_skip_blocks():
    """No # skip blocks allowed — all doc snippets must be tested."""
    # nv
    violations = check_no_skip_blocks(_DOCS_DIR)
    assert not violations, (
        f"Found {len(violations)} # skip block(s):\n"
        + "\n".join(violations)
        + f"\n\n{_HOWTO}"
    )


def test_no_raw_untested_blocks():
    """New seam blocks (```seam) must be --8<-- references, contain a Test, or
    compile successfully. Blocks that fail to compile and have no Test are
    the gap — they silently rot. This test catches them.
    """
    # nv
    violations = check_no_raw_untested_blocks(
        _DOCS_DIR, known_uncompilable=_KNOWN_UNCOMPILABLE
    )
    assert not violations, (
        f"Found {len(violations)} seam block(s) (```seam) that fail to compile "
        f"and have no Test clause or --8<-- reference:\n"
        + "\n".join(violations)
        + "\n\nEither fix the code, add a Test clause, or move to a "
        + f"tested fixture file.\n{_HOWTO}"
    )
