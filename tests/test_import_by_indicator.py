"""``-import_from(m, [p/1])`` imports ONE arity of ``p`` (operator ruling D20,
2026-09-29), as Scryer's ``use_module(m, [p/1])`` does.

A bare ``p`` still imports every arity the exporter has, and the two forms
mix in one list.  An indicator the exporter does not have is a load-time
existence error naming the module, the indicator and the line.  A call at an
arity that was NOT imported resolves in the importer, like any other
unqualified call: its own row if it defines one, else the arity refusal.
"""

from __future__ import annotations

import os
import sys
import textwrap

import pytest

from clausal import Var
from clausal.import_hook import _load_module
from clausal.logic.solve import call, imported_atoms
from clausal.logic.variables import deref
from clausal.predicate_diagnostics import PredicateArityMismatchError


LIB = """
    -module(ibi_lib, [g/1, g/2, h/1, k, k/1])
    g(X) <- (X is 1)
    g(X, X),
    h(X) <- (X is 7)
    k(X) <- (X is 9)
"""


@pytest.fixture
def lib_dir(tmp_path):
    _write(tmp_path, "ibi_lib", LIB)
    sys.path.insert(0, str(tmp_path))
    yield tmp_path
    sys.path.remove(str(tmp_path))
    for name in list(sys.modules):
        if name.startswith("ibi_"):
            del sys.modules[name]


def _write(tmp_path, name, text):
    path = os.path.join(tmp_path, name + ".clausal")
    with open(path, "w") as fh:
        fh.write(textwrap.dedent(text).lstrip("\n"))
    return path


def _load(tmp_path, name, text):
    return _load_module(name, _write(tmp_path, name, text))


def _answers(mod, name, *args):
    out = []
    for _ in call(name, *args, module=mod):
        out.append(tuple(deref(a) for a in args))
    return out


class TestOneArity:

    def test_the_imported_arity_answers(self, lib_dir):
        mod = _load(lib_dir, "ibi_one", """
            -import_from(ibi_lib, [g/1])
            one(A) <- g(A)
        """)
        a = Var()
        assert _answers(mod, "one", a) == [(1,)]

    def test_an_unimported_arity_is_refused_like_any_missing_arity(
            self, lib_dir):
        mod = _load(lib_dir, "ibi_other", """
            -import_from(ibi_lib, [g/1])
            two(A) <- g(A, 5)
        """)
        with pytest.raises(PredicateArityMismatchError) as info:
            list(call("two", Var(), module=mod))
        text = " ".join(str(info.value).split())
        assert "g takes 1 argument, but this call passes 2" in text
        assert ("ibi_lib has g/2, but this module's -import_from did not "
                "import it: add g/2 to the -import_from(ibi_lib, [...])"
                in text)
        # the ISO term Scryer gives for an undefined procedure
        assert "existence_error" in repr(info.value.term)

    def test_a_meta_call_at_an_unimported_arity_is_refused(self, lib_dir):
        mod = _load(lib_dir, "ibi_meta", """
            -import_from(ibi_lib, [g/1])
            one(A) <- call(g, A)
            two(A) <- call(g, A, 5)
        """)
        a = Var()
        assert _answers(mod, "one", a) == [(1,)]
        with pytest.raises(PredicateArityMismatchError):
            list(call("two", Var(), module=mod))

    def test_the_unimported_arity_is_free_for_a_local_definition(
            self, lib_dir):
        """ISO: p/1 and p/2 are unrelated procedures, so importing p/1 and
        defining p/2 locally is not a clash."""
        mod = _load(lib_dir, "ibi_local", """
            -import_from(ibi_lib, [g/1])
            g(500, Y),
            both(A, B) <- (g(A), g(B, 5))
        """)
        a, b = Var(), Var()
        assert _answers(mod, "both", a, b) == [(1, 500)]

    def test_a_bare_name_still_imports_every_arity(self, lib_dir):
        mod = _load(lib_dir, "ibi_bare", """
            -import_from(ibi_lib, [g])
            both(A, B) <- (g(A), g(B, 5))
        """)
        a, b = Var(), Var()
        assert _answers(mod, "both", a, b) == [(1, 5)]

    def test_two_indicators_import_both_arities(self, lib_dir):
        mod = _load(lib_dir, "ibi_twoind", """
            -import_from(ibi_lib, [g/1, g/2])
            both(A, B) <- (g(A), g(B, 5))
        """)
        a, b = Var(), Var()
        assert _answers(mod, "both", a, b) == [(1, 5)]

    def test_a_mixed_list(self, lib_dir):
        mod = _load(lib_dir, "ibi_mixed", """
            -import_from(ibi_lib, [g/2, h])
            both(A, B) <- (g(A, 1), h(B))
        """)
        a, b = Var(), Var()
        assert _answers(mod, "both", a, b) == [(1, 7)]

    def test_the_adopted_rows_are_the_imported_arity_only(self, lib_dir):
        mod = _load(lib_dir, "ibi_rows", """
            -import_from(ibi_lib, [g/1])
            one(A) <- g(A)
        """)
        db = mod.__clausal_module__.db
        assert db.adopted_arities("g") == frozenset({1})


class TestMissingIndicator:

    def test_an_arity_the_exporter_lacks_is_a_load_error(self, lib_dir):
        with pytest.raises(ImportError) as info:
            _load(lib_dir, "ibi_missing", """
                # a comment line so the directive is on line 2
                -import_from(ibi_lib, [g/3])
            """)
        text = " ".join(str(info.value).split())
        assert "ibi_lib" in text
        assert "g/3" in text
        assert "existence_error(procedure, g/3)" in text
        assert "line 2" in text
        # says what the exporter does have for g
        assert "g/1" in text and "g/2" in text

    def test_a_python_module_has_no_indicators(self, lib_dir):
        with pytest.raises(ImportError) as info:
            _load(lib_dir, "ibi_py", """
                -import_from(py.json, [parse/2])
            """)
        text = " ".join(str(info.value).split())
        assert "parse/2" in text
        assert "not a Clausal module" in text


class TestAliasByIndicator:

    def test_alias_of_one_arity(self, lib_dir):
        mod = _load(lib_dir, "ibi_alias", """
            -import_from(ibi_lib, [alias(g/1, gg)])
            one(A) <- gg(A)
            two(A) <- gg(A, 5)
        """)
        a = Var()
        assert _answers(mod, "one", a) == [(1,)]
        with pytest.raises(PredicateArityMismatchError) as info:
            list(call("two", Var(), module=mod))
        assert "add alias(g/2, gg) to the" in " ".join(
            str(info.value).split())

    def test_alias_of_a_missing_arity_is_a_load_error(self, lib_dir):
        with pytest.raises(ImportError, match="g/4"):
            _load(lib_dir, "ibi_alias_missing", """
                -import_from(ibi_lib, [alias(g/4, gg)])
            """)


class TestImportedAtoms:

    def test_an_indicator_entry_names_a_predicate_not_an_atom(self, lib_dir):
        mod = _load(lib_dir, "ibi_atoms_ind", """
            -import_from(ibi_lib, [k/1])
            one(A) <- k(A)
        """)
        assert "k" not in imported_atoms(mod)
        a = Var()
        assert _answers(mod, "one", a) == [(9,)]

    def test_a_bare_entry_still_names_the_atom(self, lib_dir):
        mod = _load(lib_dir, "ibi_atoms_bare", """
            -import_from(ibi_lib, [k])
            one(A) <- k(A)
        """)
        assert imported_atoms(mod) == {"k": "ibi_lib"}


class TestSelectionsMerge:
    """roborev round 1: a selection is the UNION of the entries and
    directives that name it, and a bare entry means every arity."""

    def test_two_directives_import_two_arities(self, lib_dir):
        mod = _load(lib_dir, "ibi_two_dirs", """
            -import_from(ibi_lib, [g/1])
            -import_from(ibi_lib, [g/2])
            both(A, B) <- (g(A), g(B, 5))
        """)
        assert mod.__clausal_module__.db.adopted_arities("g") == {1, 2}
        a, b = Var(), Var()
        assert _answers(mod, "both", a, b) == [(1, 5)]

    def test_two_directives_refuse_a_local_clause_at_either_arity(
            self, lib_dir):
        with pytest.raises(SyntaxError, match="g/1"):
            _load(lib_dir, "ibi_two_dirs_clash", """
                -import_from(ibi_lib, [g/1])
                -import_from(ibi_lib, [g/2])
                g(7),
            """)

    def test_a_later_bare_import_widens_an_earlier_selection(self, lib_dir):
        with pytest.raises(SyntaxError, match="g/2"):
            _load(lib_dir, "ibi_then_bare", """
                -import_from(ibi_lib, [g/1])
                -import_from(ibi_lib, [g])
                g(7, 8),
            """)

    def test_an_earlier_bare_import_is_not_narrowed(self, lib_dir):
        with pytest.raises(SyntaxError, match="g/2"):
            _load(lib_dir, "ibi_bare_then", """
                -import_from(ibi_lib, [g])
                -import_from(ibi_lib, [g/1])
                g(7, 8),
            """)

    def test_one_predicate_under_two_names_at_different_arities(
            self, lib_dir):
        """``[g/1, alias(g/2, gg)]`` is refused: both spellings share ONE
        remapped reference, which cannot tell ``g(A, 5)`` from ``gg(A, 5)``
        (the review-round-5 residual), so either the alias would fail or
        the name would leak the other arity."""
        with pytest.raises(SyntaxError) as info:
            _load(lib_dir, "ibi_name_alias", """
                -import_from(ibi_lib, [g/1, alias(g/2, gg)])
            """)
        text = " ".join(str(info.value).split())
        assert "`g`" in text and "`gg`" in text

    def test_a_nonterminal_indicator(self, tmp_path):
        _write(tmp_path, "ibi_dcg_lib", """
            -module(ibi_dcg_lib, [greeting//0, greeting//1])
            greeting >> [1]
            greeting(N) >> [1, N]
        """)
        sys.path.insert(0, str(tmp_path))
        try:
            mod = _load(tmp_path, "ibi_dcg_use", """
                -import_from(ibi_dcg_lib, [greeting//1])
                one(N) <- phrase(greeting(N), [1, 2])
            """)
            assert mod.__clausal_module__.db.adopted_arities(
                "greeting") == {3}
            n = Var()
            assert _answers(mod, "one", n) == [(2,)]
        finally:
            sys.path.remove(str(tmp_path))
            for name in ("ibi_dcg_lib", "ibi_dcg_use"):
                sys.modules.pop(name, None)
