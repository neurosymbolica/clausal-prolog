"""Native ``.pl``: a bare name in a use_module/2 import list imports EXACTLY
the arities the module exports that name at (operator ruling 2026-10-01),
as the translator's ``use_module(m, [p])`` and the seam's
``-import_from(m, [p])`` already did.  The native front end imported
NOTHING for it (D11(a) read every bare entry as an atom), so ``p(X)``
through the import raised existence_error(procedure, p/1).

A name the module does not export stays a bare atom (D11(a): imports
nothing, one counted warning).  Scryer itself refuses a bare name in an
import list (syntax_error(invalid_module_declaration)); the ruling, not
Scryer, decides here."""
from __future__ import annotations

import textwrap
import warnings

LIB = """\
:- module(l3bare_lib, [p/1, word//1]).
p(1).
p(1, 2).
word(W) --> [W].
"""


def _load(native, name, imports, body):
    (native.tmp / "l3bare_lib.pl").write_text(LIB, encoding="utf-8")
    with warnings.catch_warnings(record=True) as got:
        warnings.simplefilter("always")
        mod = native.load(name, f":- use_module(l3bare_lib, {imports}).\n"
                          + textwrap.dedent(body))
    return mod, got


def test_a_bare_name_imports_the_exported_arity_only(native, ans):
    mod, _ = _load(native, "l3_bare_p", "[p]", """\
        t(R) :- catch((p(X), R = X), error(E, _), R = E).
        t2(R) :- catch((p(X, Y), R = X-Y), error(E, _), R = E).
        """)
    assert ans(mod, "t") == [1]
    assert ans(mod, "t2") == [("existence_error", "procedure",
                               ("/", "p", 2))]


def test_a_bare_name_imports_an_exported_nonterminal(native, ans):
    mod, _ = _load(native, "l3_bare_word", "[word]", """\
        t(R) :- findall(X, phrase(word(X), [a]), R).
        """)
    assert ans(mod, "t") == [["a"]]


def test_the_importer_may_define_the_unexported_arity(native, ans):
    mod, _ = _load(native, "l3_bare_own", "[p]", """\
        p(own, 2).
        t(R) :- findall(X, p(X), R).
        t2(R) :- findall(X-Y, p(X, Y), R).
        """)
    assert ans(mod, "t") == [[1]]
    assert ans(mod, "t2") == [[("-", "own", 2)]]


def test_only_a_bare_name_the_module_does_not_export_warns(native, ans):
    from clausal.lint_warnings import ClausalBareAtomImportWarning
    mod, got = _load(native, "l3_bare_warn", "[p, l3bare_atom]", """\
        t(R) :- findall(X, p(X), R).
        """)
    ours = [str(w.message) for w in got
            if w.category is ClausalBareAtomImportWarning]
    assert len(ours) == 1 and "1 bare atom entry" in ours[0], ours
    assert "(l3bare_atom)" in ours[0], ours
    assert ans(mod, "t") == [[1]]
