"""The TitleCase gate, measured: no Clausal source in this repository — the
engine's own ``.clausal`` files, every fixture under ``tests/`` and every
optional package under ``packages/`` — carries a TitleCase identifier in a
FUNCTOR position, except the deprecation-window witness that exists to
assert the error.

Since 2026-09-10 the lint is functor-only (a capital initial in term
position is a logic variable), so this census measures functor positions.
That is the census that matters: a TitleCase term is now ordinary code.

The count is taken by the lint itself (``_parse_clausal_source`` under the
warning severity, so one load reports every offending name), not by a grep:
a file that imports a TitleCase Python class through its import list is
clean, a file that spells one bare is not.  The package fixtures' own suites
need optional dependencies this environment may lack; this check needs only
the transformer, so it runs everywhere.
"""
from __future__ import annotations

import pathlib
import re
import warnings

import pytest

from clausal.import_hook import _parse_clausal_source
from clausal.templating import term_rewriting
from clausal.templating.term_rewriting import ClausalTitleCaseIdentifierWarning
from tests._suffix import SEAM, seam_glob

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_ROOTS = ("clausal", "tests", "packages")
_SKIP_PARTS = {".git", "__pycache__", ".claude", "node_modules"}

#: The deprecation-window witnesses: kept on the retired spelling ON PURPOSE,
#: each asserted by the test that owns it.
#: The unit witness dropped off this list on 2026-09-10: its ``5.0(Metre)``
#: puts the retired spelling in a unit-annotation ARGUMENT, which is a term
#: position, so it reads as a logic variable and the lint -- now functor-only
#: -- says nothing about it.  The file is clean by this census's measure; what
#: it witnesses now is asserted by tests/test_units_lowercase_names.py.
_WITNESSES = {
    "tests/fixtures/titlecase_test_spelling_witness.seam": {"Test"},
}


def _clausal_files():
    for root in _ROOTS:
        for p in seam_glob(_ROOT / root, recursive=True):
            # Repo-relative parts: the checkout itself may live under a
            # directory named like one of the skips.
            if _SKIP_PARTS & set(p.relative_to(_ROOT).parts):
                continue
            yield p


_NAMED = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)` is TitleCase")

#: Fixtures kept on ANOTHER deliberate load error (each asserted by its own
#: test); the transformer stops there, and the lint had already read every
#: clause before the failing one.  Anything else that fails to parse is
#: re-raised — a silently truncated census would prove nothing.
_OTHER_LOAD_ERROR_WITNESSES = {
    "tests/fixtures/lambda_in_term_position_witness.seam",
}


def _titlecase_names(path: pathlib.Path) -> set[str]:
    """Every TitleCase identifier the lint reports for *path*.

    Any SyntaxError that is NOT the lint's own is re-raised: a file the
    transformer stops on part-way would truncate the census silently.
    """
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        try:
            _parse_clausal_source(path.read_text(), str(path))
        except SyntaxError as exc:
            rel = path.relative_to(_ROOT).as_posix() if _ROOT in path.parents else ""
            if not _NAMED.search(str(exc)) and rel not in _OTHER_LOAD_ERROR_WITNESSES:
                raise
    names = set()
    for w in rec:
        if issubclass(w.category, ClausalTitleCaseIdentifierWarning):
            m = _NAMED.search(str(w.message))
            assert m, str(w.message)
            names.add(m.group(1))
    return names


@pytest.fixture(autouse=True)
def _lint_as_warning(monkeypatch):
    monkeypatch.setattr(
        term_rewriting, "TITLECASE_IDENTIFIER_SEVERITY", "warn")


def test_the_tree_has_clausal_files_to_check():
    """Positive control on the walk: an empty census would prove nothing."""
    files = list(_clausal_files())
    assert len(files) > 300, len(files)
    assert any("packages" in p.parts for p in files)


@pytest.mark.parametrize("text, names", [
    ("Foo(1),\n", {"Foo"}),
    ("baz(1),\ngo(X) <- (Qux(X))\n", {"Qux"}),
    # ...and the matching NEGATIVE control.  A single-quoted functor is an
    # ATOM, which ISO lets name anything, so the census must stay silent
    # about it — otherwise this instrument would report the whole tree as
    # offending the moment a file spells a capitalised predicate the one
    # unambiguous way (see test_quoted_atom_functor.py).
    ("'Bar'(1),\n", set()),
    ("baz(1),\ngo(X) <- ('Qux'(X))\n", set()),
])
def test_the_lint_still_sees_a_titlecase_head(tmp_path, text, names):
    """Positive control on the instrument: the census is the lint."""
    p = tmp_path / f"probe{SEAM}"
    p.write_text(text)
    assert _titlecase_names(p) == names


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
