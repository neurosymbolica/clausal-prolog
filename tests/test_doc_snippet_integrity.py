"""Verify that all --8<-- snippet references in core docs/ point to valid targets.

Each extracted package runs the same checks against its own docs/; see
``packages/clausal-<pkg>/tests/test_doc_integrity.py``. Shared logic lives
in ``clausal/tools/doc_snippet_check.py``.
"""

from pathlib import Path

from clausal.tools.doc_snippet_check import (
    check_clausal_fixtures_have_tests,
    check_files_exist,
    check_sections_exist,
    collect_snippet_refs,
)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DOCS_DIR = _PROJECT_ROOT / "docs"


def test_all_snippet_files_exist():
    # nv
    refs = collect_snippet_refs(_DOCS_DIR)
    missing = check_files_exist(refs, _PROJECT_ROOT)
    assert not missing, (
        "Snippet references point to missing files:\n" + "\n".join(missing)
    )


def test_all_snippet_sections_exist():
    # nv
    refs = collect_snippet_refs(_DOCS_DIR)
    missing = check_sections_exist(refs, _PROJECT_ROOT)
    assert not missing, (
        "Snippet references point to missing sections:\n" + "\n".join(missing)
    )


def test_clausal_fixtures_have_tests():
    """Every .clausal file referenced from docs should have Test clauses."""
    # nv
    refs = collect_snippet_refs(_DOCS_DIR)
    untested = check_clausal_fixtures_have_tests(refs, _PROJECT_ROOT)
    assert not untested, (
        "Referenced .clausal fixture files have no Test clauses:\n"
        + "\n".join(untested)
    )
