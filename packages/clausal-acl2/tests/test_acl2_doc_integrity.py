"""Doc-snippet integrity + coverage checks for clausal-acl2's own docs/.

Mirrors core's tests/test_doc_snippet_*.py against this package's docs.
Shared check logic lives in clausal/tools/doc_snippet_check.py (in core).
"""

from pathlib import Path

from clausal.tools.doc_snippet_check import (
    check_clausal_fixtures_have_tests,
    check_files_exist,
    check_no_raw_untested_blocks,
    check_no_skip_blocks,
    check_sections_exist,
    collect_snippet_refs,
)

_PKG_ROOT = Path(__file__).resolve().parent.parent
_DOCS_DIR = _PKG_ROOT / "docs"


def test_all_snippet_files_exist():
    refs = collect_snippet_refs(_DOCS_DIR)
    missing = check_files_exist(refs, _PKG_ROOT)
    assert not missing, (
        "Snippet references point to missing files:\n" + "\n".join(missing)
    )


def test_all_snippet_sections_exist():
    refs = collect_snippet_refs(_DOCS_DIR)
    missing = check_sections_exist(refs, _PKG_ROOT)
    assert not missing, (
        "Snippet references point to missing sections:\n" + "\n".join(missing)
    )


def test_clausal_fixtures_have_tests():
    refs = collect_snippet_refs(_DOCS_DIR)
    untested = check_clausal_fixtures_have_tests(refs, _PKG_ROOT)
    assert not untested, (
        "Referenced .clausal fixture files have no Test clauses:\n"
        + "\n".join(untested)
    )


def test_no_skip_blocks():
    violations = check_no_skip_blocks(_DOCS_DIR)
    assert not violations, (
        f"Found {len(violations)} # skip block(s):\n" + "\n".join(violations)
    )


def test_no_raw_untested_blocks():
    violations = check_no_raw_untested_blocks(_DOCS_DIR)
    assert not violations, (
        f"Found {len(violations)} ```seam block(s) that fail to compile "
        f"and have no Test clause or --8<-- reference:\n"
        + "\n".join(violations)
    )
