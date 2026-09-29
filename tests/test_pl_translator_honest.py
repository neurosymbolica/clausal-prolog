"""The ``.pl`` import translator must not answer silently wrong.

Every case here loads a ``.pl`` file through the REAL ``PrologLoader`` and
checks the ANSWERS against what Scryer Prolog gives for the same file (the
expected values were measured with Scryer; see each test).  A construct the
engine cannot run must be a load-time error naming it, never a comment, a
drop or a rename.
"""

from __future__ import annotations

import sys
import textwrap

import pytest

from clausal.import_hook import _load_prolog_module
from clausal.logic.solve import query
from clausal.logic.variables import Var
from clausal.tools.prolog_to_clausal import (
    PrologTranslationError, prolog_to_clausal,
)

_PREFIX = "plhonest_"


@pytest.fixture(autouse=True)
def _on_path(tmp_path):
    sys.path.insert(0, str(tmp_path))
    yield
    sys.path.remove(str(tmp_path))
    for key in list(sys.modules):
        if key.startswith(_PREFIX) or key.startswith("plhpkg"):
            del sys.modules[key]


def _load(tmp_path, name, source):
    path = tmp_path / f"{_PREFIX}{name}.pl"
    path.write_text(textwrap.dedent(source))
    return _load_prolog_module(f"{_PREFIX}{name}", str(path))


def _answers(mod, pred):
    x = Var()
    return [s["X"] for s in query((pred, x), {"X": x}, mod)]


# ── A. bagof/setof keep the existential quantifier ─────────────────────

_SETOF_SRC = """\
    p(1, a).
    p(2, a).
    p(3, b).
    q(1, a, 1).
    q(2, b, 2).
    s(L) :- setof(X, Y^p(X, Y), L).
    b(L) :- bagof(X, Y^p(X, Y), L).
    g(L) :- setof(X, p(X, _Y), L).
    n(L) :- setof(X, A^B^q(X, A, B), L).
    c(L) :- setof(X, Y^(p(X, Y), X > 1), L).
"""


class TestCaretQuantifier:
    """ISO 8.10.2/8.10.3: ``Y^G`` makes Y existential, so the solutions are
    NOT grouped by Y.  Scryer: s -> [[1,2,3]], b -> [[1,2,3]],
    g -> [[1,2],[3]] (no ^, grouped), n -> [[1,2]], c -> [[2,3]]."""

    def test_setof_caret_is_one_answer(self, tmp_path):
        m = _load(tmp_path, "setof", _SETOF_SRC)
        assert _answers(m, "s") == [[1, 2, 3]]

    def test_bagof_caret_is_one_answer(self, tmp_path):
        m = _load(tmp_path, "bagof", _SETOF_SRC)
        assert _answers(m, "b") == [[1, 2, 3]]

    def test_no_caret_still_groups(self, tmp_path):
        m = _load(tmp_path, "group", _SETOF_SRC)
        assert _answers(m, "g") == [[1, 2], [3]]

    def test_nested_caret(self, tmp_path):
        m = _load(tmp_path, "nested", _SETOF_SRC)
        assert _answers(m, "n") == [[1, 2]]

    def test_caret_over_conjunction(self, tmp_path):
        m = _load(tmp_path, "conj", _SETOF_SRC)
        assert _answers(m, "c") == [[2, 3]]

    def test_caret_over_unification_goal(self, tmp_path):
        # member/2 emits the infix `X in L`, and `Y ^ X in L` would read as
        # `(Y ^ X) in L`: the goal is parenthesised.  Scryer: [[1,2]].
        m = _load(tmp_path, "unif", """\
            u(L) :- setof(X, Y^member(X-Y, [2-b, 1-a]), L).
        """)
        assert _answers(m, "u") == [[1, 2]]


# ── B. no rename of a name the program means literally ────────────────


class TestNoStaleRenames:
    """A Prolog name crosses unchanged unless the engine spells the SAME
    predicate differently.  ``profile_get/3`` was renamed to Clausal's
    ``get/3`` (an export-direction mapping for a downstream helper library,
    run backwards), so a program's own ``profile_get`` vanished."""

    def test_undefined_profile_get_is_an_existence_error(self, tmp_path):
        # Scryer: error(existence_error(procedure, profile_get/3), _)
        m = _load(tmp_path, "pg_undef", """\
            t(V) :- X = foo, profile_get(X, k, V).
        """)
        with pytest.raises(Exception, match="profile_get"):
            _answers(m, "t")

    def test_own_profile_get_is_called(self, tmp_path):
        m = _load(tmp_path, "pg_own", """\
            profile_get(foo, k, 1).
            t(V) :- profile_get(foo, k, V).
        """)
        assert _answers(m, "t") == [1]
        x = Var()
        assert [s["X"] for s in query(("profile_get", "foo", "k", x),
                                      {"X": x}, m)] == [1]

    def test_imported_profile_get_is_called(self, tmp_path):
        (tmp_path / f"{_PREFIX}pg_lib.pl").write_text(textwrap.dedent(f"""\
            :- module({_PREFIX}pg_lib, [profile_get/3]).
            profile_get(foo, k, 2).
        """))
        m = _load(tmp_path, "pg_user", f"""\
            :- use_module({_PREFIX}pg_lib, [profile_get/3]).
            t(V) :- profile_get(foo, k, V).
        """)
        assert _answers(m, "t") == [2]

    def test_atomic_is_the_iso_type_test(self, tmp_path):
        # was renamed to is_atomic/1, which does not exist
        m = _load(tmp_path, "atomic", """\
            t(X) :- atomic(foo), X = 1.
            t(X) :- atomic(f(a)), X = 2.
        """)
        assert _answers(m, "t") == [1]

    def test_a_program_defining_a_renamed_name_keeps_it(self, tmp_path):
        # time/1 maps to Clausal's time_goal/1 -- but not when the program
        # defines its own time/1
        m = _load(tmp_path, "owntime", """\
            time(7).
            t(X) :- time(X).
        """)
        assert _answers(m, "t") == [7]
        # ... and it is time/1 under its own name, as the program wrote it
        assert _answers(m, "time") == [7]


# ── D. ISO evaluables keep their names ────────────────────────────────


class TestEvaluableNames:
    """max/min/abs (and every ISO evaluable) are in the engine's evaluable
    table, so ``X is max(3, 5)`` crosses as ``max``, not ``max_`` (which
    raised type_error(evaluable, max_/2)).  Scryer: mx 5, mn 3, ab 4,
    fl 3.0, tr 3, fl_test [1], dat max(1,2)."""

    _SRC = """\
        mx(X) :- X is max(3, 5).
        mn(X) :- X is min(3, 5).
        ab(X) :- X is abs(-4).
        fl(X) :- X is float(3).
        tr(X) :- X is truncate(3.7) + ceiling(0.5) - floor(0.5).
        sq(X) :- X is sqrt(16) + sin(0) + cos(0) + exp(0) + log(1).
        fl_test(X) :- float(1.0), X = 1.
        fl_test(X) :- float(1), X = 2.
        dat(X) :- X = max(1, 2).
    """

    @pytest.mark.parametrize("pred,expected", [
        ("mx", [5]), ("mn", [3]), ("ab", [4]), ("fl", [3.0]), ("tr", [4]),
        ("sq", [6.0]), ("fl_test", [1]),
    ])
    def test_evaluable(self, tmp_path, pred, expected):
        m = _load(tmp_path, f"ev_{pred}", self._SRC)
        assert _answers(m, pred) == expected

    def test_evaluable_name_as_data(self, tmp_path):
        m = _load(tmp_path, "ev_dat", self._SRC)
        assert _answers(m, "dat") == [("max", 1, 2)]


class TestIsoEvaluableOperators:
    """The ISO arithmetic operators Python spells differently cross as the
    quoted ISO evaluable.  Expected values are Scryer's (2026-09-29)."""

    @pytest.mark.parametrize("expr,expected", [
        ("-7 // 2", -3), ("-7 mod 2", 1), ("-7 rem 2", -1),
        ("7 div -2", -4), ("2 ^ 3", 8), ("2 ** 3", 8.0), ("2.0 ^ 2", 4.0),
        ("1 << 3", 8), ("16 >> 2", 4), ("5 /\\ 3", 1), ("5 \\/ 3", 7),
        ("\\ 5", -6), ("2 ^ 3 ^ 2", 512), ("(2 ^ 3) ^ 2", 64),
        ("1 + 2 * 3 - 4 / 2", 5.0),
    ])
    def test_value(self, tmp_path, expr, expected):
        m = _load(tmp_path, "iso_op", f"t(X) :- X is {expr}.\n")
        got = _answers(m, "t")
        assert got == [expected] and type(got[0]) is type(expected)

    def test_int_caret_negative_is_a_type_error(self, tmp_path):
        # Scryer: error(type_error(float, 2), (^)/2); was 0.5
        m = _load(tmp_path, "iso_caret", "t(X) :- X is 2 ^ -1.\n")
        with pytest.raises(Exception, match="type_error"):
            _answers(m, "t")

    def test_in_comparison(self, tmp_path):
        m = _load(tmp_path, "iso_cmp", """\
            t(1) :- 2 ^ 3 > 7, 1 << 2 =:= 4, -7 // 2 =:= -3.
        """)
        assert _answers(m, "t") == [1]

    def test_as_data(self, tmp_path):
        # a data term keeps its ISO functor, (^)/2 -- not Python's **
        m = _load(tmp_path, "iso_data", """\
            t(X) :- T = 2 ^ 3, T =.. [X|_].
        """)
        assert _answers(m, "t") == ["^"]


# ── C. module paths in use_module ─────────────────────────────────────


def _pkg(tmp_path):
    """plhpkg/{lib1.pl, sub/{lib2.pl}} on sys.path (tmp_path)."""
    root = tmp_path / "plhpkg"
    (root / "sub").mkdir(parents=True)
    (root / "__init__.py").write_text("")
    (root / "sub" / "__init__.py").write_text("")
    (root / "lib1.pl").write_text(
        ":- module(lib1, [v/1]).\nv(1).\n")
    (root / "sub" / "lib2.pl").write_text(
        ":- module(lib2, [v/1]).\nv(2).\n")
    return root


def _pkg_mod(tmp_path, rel, source):
    root = _pkg(tmp_path)
    path = root / rel
    path.write_text(textwrap.dedent(source))
    name = "plhpkg." + rel[:-3].replace("/", ".")
    return _load_prolog_module(name, str(path))


class TestModulePaths:
    """ISO leaves source-sink resolution to the implementation; Scryer
    resolves a relative path against the LOADING FILE's directory
    (measured 2026-09-29: sub/m2.pl with use_module('../lib1') loads
    lib1.pl, and m3.pl with use_module(sub/lib2) loads sub/lib2.pl).  The
    translator maps the resolved file to its dotted module name; a path it
    cannot map is a load error naming the directive, never a comment."""

    def test_unquoted_slash_path(self, tmp_path):
        m = _pkg_mod(tmp_path, "m3.pl", """\
            :- use_module(sub/lib2).
            w(X) :- v(X).
        """)
        assert _answers(m, "w") == [2]

    def test_quoted_slash_path(self, tmp_path):
        m = _pkg_mod(tmp_path, "m3.pl", """\
            :- use_module('sub/lib2').
            w(X) :- v(X).
        """)
        assert _answers(m, "w") == [2]

    def test_quoted_slash_path_with_import_list(self, tmp_path):
        m = _pkg_mod(tmp_path, "m3.pl", """\
            :- use_module('sub/lib2', [v/1]).
            w(X) :- v(X).
        """)
        assert _answers(m, "w") == [2]

    def test_unquoted_slash_path_with_import_list(self, tmp_path):
        m = _pkg_mod(tmp_path, "m3.pl", """\
            :- use_module(sub/lib2, [v/1]).
            w(X) :- v(X).
        """)
        assert _answers(m, "w") == [2]

    def test_relative_parent_path(self, tmp_path):
        m = _pkg_mod(tmp_path, "sub/m2.pl", """\
            :- use_module('../lib1', [v/1]).
            w(X) :- v(X).
        """)
        assert _answers(m, "w") == [1]

    def test_dotted_sys_path_fallback(self, tmp_path):
        # no plhpkg/sub/plhpkg/lib1.pl beside the file: the path is read as
        # the dotted module plhpkg.lib1 on sys.path, as a bare name is
        m = _pkg_mod(tmp_path, "sub/m4.pl", """\
            :- use_module(plhpkg/lib1).
            w(X) :- v(X).
        """)
        assert _answers(m, "w") == [1]

    def test_pl_suffix(self, tmp_path):
        m = _pkg_mod(tmp_path, "m3.pl", """\
            :- use_module('sub/lib2.pl').
            w(X) :- v(X).
        """)
        assert _answers(m, "w") == [2]

    def test_unresolvable_path_names_directive_and_line(self, tmp_path):
        with pytest.raises(SyntaxError,
                           match=r"line 2.*use_module.*\.\./\.\./nowhere"):
            _pkg_mod(tmp_path, "m5.pl", """\
                w(1).
                :- use_module('../../nowhere').
            """)

    def test_variable_path_is_refused(self, tmp_path):
        with pytest.raises(SyntaxError, match=r"line 1.*use_module"):
            _load(tmp_path, "varpath", ":- use_module(M).\n")


class TestNativeLibraries:
    """A library the engine provides natively is a no-op import (Scryer's
    library(dif) is dif/2, which is an engine builtin)."""

    def test_library_dif(self, tmp_path):
        m = _load(tmp_path, "libdif", """\
            :- use_module(library(dif)).
            t(X) :- dif(X, 1), X = 2.
        """)
        assert _answers(m, "t") == [2]

    def test_library_dif_with_list(self, tmp_path):
        m = _load(tmp_path, "libdif2", """\
            :- use_module(library(dif), [dif/2]).
            t(X) :- dif(X, 1), X = 2.
        """)
        assert _answers(m, "t") == [2]

    def test_library_between(self, tmp_path):
        m = _load(tmp_path, "libbetween", """\
            :- use_module(library(between), [between/3]).
            t(X) :- between(1, 2, X).
        """)
        assert _answers(m, "t") == [1, 2]

    def test_use_module_1_imports_the_exports(self, tmp_path):
        # use_module/1 imports every exported predicate, unqualified (it was
        # -import_module alone, which gives only qualified access)
        (tmp_path / f"{_PREFIX}um_lib.pl").write_text(
            f":- module({_PREFIX}um_lib, [v/1]).\nv(3).\n")
        m = _load(tmp_path, "um_user", f"""\
            :- use_module({_PREFIX}um_lib).
            w(X) :- v(X).
        """)
        assert _answers(m, "w") == [3]


# ── E. the double_quotes flag governs the "..." below it ──────────────


class TestDoubleQuotesFlag:
    """``:- set_prolog_flag(double_quotes, M)`` changes how every later
    ``"..."`` in the file reads (ISO 7.11.2.5).  Scryer, for the file below:
    d0 = [a,b], d1 = [97,98], d2 = ab, d3 = [a,b]."""

    _SRC = """\
        d0("ab").
        :- set_prolog_flag(double_quotes, codes).
        d1("ab").
        :- set_prolog_flag(double_quotes, atom).
        d2("ab").
        :- set_prolog_flag(double_quotes, chars).
        d3("ab").
        t(0) :- d0([a, b]).
        t(1) :- d1([97, 98]).
        t(2) :- d2(ab).
        t(3) :- d3([a, b]).
    """

    def test_each_mode_reads_as_scryer_does(self, tmp_path):
        m = _load(tmp_path, "dq", self._SRC)
        assert _answers(m, "t") == [0, 1, 2, 3]

    def test_codes_answer(self, tmp_path):
        m = _load(tmp_path, "dq_codes", self._SRC)
        assert _answers(m, "d1") == [[97, 98]]

    def test_atom_answer(self, tmp_path):
        m = _load(tmp_path, "dq_atom", self._SRC)
        assert _answers(m, "d2") == ["ab"]

    def test_short_directive_spelling(self, tmp_path):
        m = _load(tmp_path, "dq_short", """\
            :- set_prolog_flag(double_quotes, codes).
            t(X) :- X = "a".
        """)
        assert _answers(m, "t") == [[97]]

    def test_unknown_mode_is_refused(self, tmp_path):
        with pytest.raises(SyntaxError, match=r"line 1.*double_quotes"):
            _load(tmp_path, "dq_bad", """\
                :- set_prolog_flag(double_quotes, string).
                t("a").
            """)
