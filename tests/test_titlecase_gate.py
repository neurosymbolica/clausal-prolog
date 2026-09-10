"""The TitleCase gate, measured: no Clausal source in this repository — the
engine's own ``.clausal`` files, every fixture under ``tests/`` and every
optional package under ``packages/`` — carries a TitleCase identifier in a
Clausal position, except the two deprecation-window witnesses that exist to
assert the error.

The count is taken by the lint itself (``_parse_clausal_source`` under the
warning severity, so one load reports every offending name), not by a grep:
a file that imports a TitleCase Python class through its import list is
clean, a file that spells one bare is not.  The package fixtures' own suites
need optional dependencies this environment may lack; this check needs only
the transformer, so it runs everywhere.
"""
from __future__ import annotations

import pathlib
import warnings

import pytest

from clausal.import_hook import _parse_clausal_source
from clausal.templating import term_rewriting
from clausal.templating.term_rewriting import ClausalTitleCaseIdentifierWarning

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_ROOTS = ("clausal", "tests", "packages")
_SKIP_PARTS = {".git", "__pycache__", ".claude", "node_modules"}

#: The deprecation-window witnesses: kept on the retired spelling ON PURPOSE,
#: each asserted by the test that owns it.
_WITNESSES = {
    "tests/fixtures/titlecase_test_spelling_witness.clausal": {"Test"},
    "tests/fixtures/titlecase_unit_spelling_witness.clausal": {"Metre"},
}


def _clausal_files():
    for root in _ROOTS:
        for p in sorted((_ROOT / root).rglob("*.clausal")):
            # Repo-relative parts: the checkout itself may live under a
            # directory named like one of the skips.
            if _SKIP_PARTS & set(p.relative_to(_ROOT).parts):
                continue
            yield p


def _titlecase_names(path: pathlib.Path) -> set[str]:
    """Every TitleCase identifier the lint reports for *path*."""
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        try:
            _parse_clausal_source(path.read_text(), str(path))
        except SyntaxError:
            # A file that does not parse for another reason is somebody
            # else's test; the lint still ran up to the failure.
            pass
    return {str(w.message).split("`")[1] for w in rec
            if issubclass(w.category, ClausalTitleCaseIdentifierWarning)}


@pytest.fixture(autouse=True)
def _lint_as_warning(monkeypatch):
    monkeypatch.setattr(
        term_rewriting, "TITLECASE_IDENTIFIER_SEVERITY", "warn")


def test_the_tree_has_clausal_files_to_check():
    """Positive control on the walk: an empty census would prove nothing."""
    files = list(_clausal_files())
    assert len(files) > 300, len(files)
    assert any("packages" in p.parts for p in files)


def test_the_lint_still_sees_a_titlecase_head(tmp_path):
    """Positive control on the instrument: the census is the lint."""
    p = tmp_path / "probe.clausal"
    p.write_text("Foo(1),\n")
    assert _titlecase_names(p) == {"Foo"}


def test_no_titlecase_identifier_in_any_clausal_position():
    offenders = {}
    for p in _clausal_files():
        names = _titlecase_names(p)
        rel = p.relative_to(_ROOT).as_posix()
        if rel in _WITNESSES:
            assert names == _WITNESSES[rel], (rel, names)
            continue
        if names:
            offenders[rel] = sorted(names)
    assert offenders == {}, (
        f"{len(offenders)} file(s) spell a TitleCase identifier in a "
        f"Clausal position (rename to snake_case, or reach a Python class "
        f"as `++Name` / through the import list): {offenders}"
    )
