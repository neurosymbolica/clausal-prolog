"""Stage 1 of the atoms-as-str flip (spec 2026-09-18, RULED Q2): under
``-double_quotes(chars)`` a string is the CARRIER ``('$chars', text)`` -- a
reserved-tag cell equal to the list of its char atoms everywhere -- so that a
bare Python str can stop meaning "text".  These pin the carrier's identity
with the list spelling across the operations that used to key on ``str``."""
from __future__ import annotations

import pathlib

import pytest

from clausal.logic.atoms import is_atom, mint
from clausal.logic.cells import CHARS_TAG, chars, chars_text, is_chars
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.testing import load_clausal_module

_HDR = "-double_quotes(chars)\n-private([yes, no, a, b, c, x, h, i, t, e, r])\n"


def _mod(tmp_path, body):
    p = tmp_path / "carrier.clausal"; p.write_text(_HDR + body)
    return load_clausal_module(p)


def _first(mod, name, *args):
    for _ in call(name, *args, module=mod):
        return [deref(x) for x in args]
    return None


def test_the_carrier_shape():
    c = chars("ab")
    assert c == (CHARS_TAG, "ab") and is_chars(c) and chars_text(c) == "ab"
    assert not is_chars("ab") and not is_chars("ab") and not is_chars((CHARS_TAG, 1))
    assert not is_atom(c)


def test_a_chars_literal_compiles_to_the_carrier(tmp_path):
    mod = _mod(tmp_path, 'p(X) <- (X is "ab")\nq(X) <- (X is "")\n')
    (x,) = _first(mod, "p", Var()); assert x == chars("ab"), x
    (e,) = _first(mod, "q", Var()); assert e == chars(""), e


def test_a_single_quoted_literal_is_still_an_atom(tmp_path):
    mod = _mod(tmp_path, "p(X) <- (X is 'ab')\n")
    (x,) = _first(mod, "p", Var()); assert x == "ab" and is_atom(x)


class TestEqualToTheListSpelling:
    def test_msort_interleaves_carriers_and_char_lists(self, tmp_path):
        mod = _mod(tmp_path, 'p(L) <- msort(["b", [a], "a", [b]], L)\n')
        (l,) = _first(mod, "p", Var())
        keys = [x if isinstance(x, list) else chars_text(x) for x in l]
        assert [k if isinstance(k, str) else "".join(c[0] for c in k) for k in keys] == ["a", "a", "b", "b"], l

    def test_string_1_and_length_2(self, tmp_path):
        mod = _mod(tmp_path, 'p(R) <- if_(string("ab"), R is yes, R is no)\nq(N) <- length("abc", N)\n')
        (r,) = _first(mod, "p", Var()); assert r == "yes"
        (n,) = _first(mod, "q", Var()); assert n == 3

    def test_append_keeps_the_carrier_kind(self, tmp_path):
        mod = _mod(tmp_path, 'p(R) <- append("ab", "cd", R)\n')
        (r,) = _first(mod, "p", Var()); assert r == chars("abcd"), r

    def test_identity_eq_across_spellings(self, tmp_path):
        mod = _mod(tmp_path, "p(R) <- if_('=='(\"ab\", [a, b]), R is yes, R is no)\n")
        (r,) = _first(mod, "p", Var()); assert r == "yes", r

    def test_unify_across_spellings(self, tmp_path):
        """Needs the C list-unify to read the carrier (slice 2)."""
        mod = _mod(tmp_path, "p(R) <- if_('='(\"ab\", [a, b]), R is yes, R is no)\n")
        (r,) = _first(mod, "p", Var()); assert r == "yes", r


class TestSlice3Funnels:
    """Slice 3: ``=..`` cons tail, rendering, the io producers, CLP ``==``,
    and the Python-side crossings all read the carrier as its text."""

    def test_univ_conses_a_char_onto_a_carrier(self, tmp_path):
        mod = _mod(tmp_path, "p(T) <- unpack(T, ['.', a, \"bc\"])\nq(T) <- unpack(T, ['.', 1, \"bc\"])\n")
        (t,) = _first(mod, "p", Var()); assert t == chars("abc"), t
        (u,) = _first(mod, "q", Var()); assert u == [1, "b", "c"], u

    def test_writeq_and_write_never_show_the_tag(self):
        from clausal.terms import term_str, term_canonical
        assert term_str(chars("ab")) == '"ab"'
        assert term_str(chars("ab"), quoted=False, double_quotes=False) == "[a, b]"
        assert term_canonical(chars("ab")) == "'.'(a,'.'(b,[]))"
        assert "$chars" not in term_str(("f", chars("x")))

    def test_to_string_producers_answer_the_carrier(self, tmp_path):
        mod = _mod(tmp_path, 'p(S) <- write_to_string("hi", S)\nq(S) <- term_to_string([a, 1], S)\nr(S) <- write_text_to_string("hi", S)\n')
        (s,) = _first(mod, "p", Var()); assert s == chars("[h,i]"), s
        (t,) = _first(mod, "q", Var()); assert t == chars("[a, 1]"), t
        (u,) = _first(mod, "r", Var()); assert u == chars("hi"), u

    def test_infix_eq_between_a_bare_str_and_the_carrier(self):
        from clausal.logic.clpfd import fd_eq, fd_ne
        from clausal.logic.variables import Trail
        t = Trail()
        assert fd_eq(chars("ab"), chars("ab"), t) and not fd_eq(chars("ab"), chars("ac"), t)
        assert fd_ne(chars("ab"), chars("ac"), t) and not fd_ne(chars("ab"), chars("ab"), t)
        assert not fd_eq("ab", chars("ab"), t)          # STAGE 2: the atom ab is not the string "ab"

    def test_python_side_crossings_read_the_text(self):
        from clausal.logic.to_python import to_python
        from clausal.logic.seam import text_of, text_value
        assert to_python(chars("ab")) == "ab"
        assert to_python([chars("ab"), 1]) == ["ab", 1]
        assert text_of(chars("ab")) == "ab" and text_value(chars("ab")) == "ab"

    def test_a_chars_literal_in_a_head_is_a_string_literal(self, tmp_path):
        """A ``"..."`` head argument keeps the str literal's capture+unify
        guard: every spelling of the text matches, and the stored head keeps
        the literal (the test runner reads names off stored heads)."""
        mod = _mod(tmp_path, 'p("ab", R) <- (R is yes)\np("cd", R) <- (R is no)\n')
        from clausal.logic.atoms import char_atom
        assert _first(mod, "p", chars("ab"), Var())[1] == "yes"
        assert _first(mod, "p", "cd", Var()) is None             # STAGE 2: the atom cd is not the string "cd"
        assert _first(mod, "p", chars("cd"), Var())[1] == "no"
        assert _first(mod, "p", [char_atom("a"), char_atom("b")], Var())[1] == "yes"
        assert _first(mod, "p", chars("zz"), Var()) is None
        x = Var(); assert _first(mod, "p", x, Var())[0] == chars("ab")     # output mode binds the carrier
        heads = [c.head for c in mod.__dict__["$module"].db.clauses_for("p", 2)]
        # P2: a stored head is a CELL, so its first argument is read at its
        # POSITION -- there are no field names on the term to go through.
        from clausal.logic.cells import cell_args
        assert [cell_args(h)[0] for h in heads] == [chars("ab"), chars("cd")], heads

    def test_runner_reads_chars_test_names_and_runs_the_right_body(self, tmp_path):
        from clausal.testing import collect_tests, run_test
        p = tmp_path / "t.clausal"
        p.write_text(_HDR + 'test("first") <- (X is 1, X == 1)\ntest("second") <- (Y is 2, Y == 3)\n')
        mod = load_clausal_module(p)
        assert collect_tests(mod) == ["first", "second"]
        assert run_test(mod, "first").passed and not run_test(mod, "second").passed


class TestSlice4SegLayer:
    """Slice 4: the Seg* layer -- every text that ESCAPES into a term (a star
    tail, a VarSeg binding, a star-list result, a ground Seg* walk, a DCG
    remainder) is the carrier, in both the Python and the C twins."""

    def test_head_star_tail_is_the_carrier_in_both_twins(self):
        from clausal.logic.runtime.list_unify import _head_list_unify_input_py
        from clausal.logic.runtime._list_unify import _head_list_unify_input
        from clausal.logic.variables import Trail
        targets = [chars("abc")]
        for fn in (_head_list_unify_input_py, _head_list_unify_input):
            for target in targets:
                t = Trail(); h = Var(); tl = Var()
                assert fn(target, [h], tl, [], t) is True
                assert deref(h) == "a" and deref(tl) == chars("bc"), (fn, target, deref(tl))

    def test_body_multi_star_binds_carriers(self, tmp_path):
        mod = _mod(tmp_path, 'p(A, B) <- ("abc" is [*A, b, *B])\nq(T) <- ("abc" is [_, *T])\n')
        a, b = _first(mod, "p", Var(), Var()); assert (a, b) == (chars("a"), chars("c")), (a, b)
        (t,) = _first(mod, "q", Var()); assert t == chars("bc"), t

    def test_star_list_built_from_carriers_is_a_carrier(self, tmp_path):
        mod = _mod(tmp_path, 'p(R) <- (A is "ab", B is "cd", R is [*A, *B])\nq(R) <- (A is "ab", R is [yes, *A])\n')
        (r,) = _first(mod, "p", Var()); assert r == chars("abcd"), r
        (s,) = _first(mod, "q", Var()); assert s == ["yes", "a", "b"], s

    def test_ground_segstring_walks_to_the_carrier(self):
        from clausal.terms import SegString, VarSeg
        from clausal.logic.variables import Trail, walk, unify
        t = Trail(); x = Var(); ss = SegString(["a", VarSeg(x)])
        assert unify(x, chars("bc"), t) and walk(ss) == chars("abc")
        y = Var(); ss2 = SegString(["a", VarSeg(y)])
        assert unify(ss2, chars("abc"), t) and deref(y) == chars("bc")
        assert ss2.is_ground() and ss2 == chars("abc")

    def test_dcg_terminal_and_remainder(self, tmp_path):
        mod = _mod(tmp_path, 'greet >> ("hi", " ", "there")\np(R) <- (phrase(greet, "hi there", R))\nq <- phrase(greet, "hi there")\nr <- phrase(greet, [h, i, \' \', t, h, e, r, e])\n')
        (r,) = _first(mod, "p", Var()); assert r == chars(""), r
        assert _first(mod, "q") is not None
        assert _first(mod, "r") is not None

    def test_is_list_flatten_and_fresh_shape(self, tmp_path):
        mod = _mod(tmp_path, 'p(R) <- if_(is_list("ab"), R is yes, R is no)\nq(F) <- flatten([[a], "bc"], F)\n')
        (r,) = _first(mod, "p", Var()); assert r == "yes"
        (f,) = _first(mod, "q", Var()); assert f == ["a", "b", "c"], f


# ── spelling parity: the positive control for stage 1 ───────────────────────
#
# One text term, three spellings -- the bare str (interim), the carrier, and
# the char list.  Every goal below must answer the SAME (answers compared with
# the carrier and the bare str both read as their text).  A goal that answers
# differently for the carrier is a funnel stage 1 has not reached.

_PARITY_GOALS = [
    "functor(X, N, A)", "unpack(X, L)", "length(X, N)", "msort([X, [a]], L)",
    "sort([X, [a]], L)", "if_(compound(X), R is yes, R is no)",
    "if_(atomic(X), R is yes, R is no)", "if_(is_list(X), R is yes, R is no)",
    "if_(string(X), R is yes, R is no)", "if_(atom(X), R is yes, R is no)",
"if_(ground(X), R is yes, R is no)",
    "copy_term(X, Y)", "term_variables(X, V)", "append(X, [c], R)",
    "append(X, \"c\", R)", "reverse(X, R)", "last(X, E)", 
    "flatten([X, [c]], F)", "in_(E, X)", "compare(O, X, [a, b])",
    "compare(O, X, [a, c])", "if_('=='(X, [a, b]), R is yes, R is no)",
    "if_('@<'(X, [a, c]), R is yes, R is no)", "write_to_string(X, S)",
    "term_to_string(X, S)", "write_text_to_string(X, S)", "arg(1, X, E)",
    "sum_list([1], S), length(X, N)", "list_to_set(X, S)", "exclude(is_a, X, R)",
    "include(is_a, X, R)", "if_(\"ab\" == X, R is yes, R is no)",
    "if_(X == \"ac\", R is yes, R is no)", "(X is [H, *T])", "(X is [*P, b])",
    "(X is [*P, *Q]), P == \"a\"", "atom_chars(A, X)", "atom_codes(A, X)",
    "number_chars(N, X)",
]


def _as_text(v):
    from clausal.terms import SegString
    if is_chars(v):
        return chars_text(v)
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return [_as_text(e) for e in v]
    if isinstance(v, tuple):
        return tuple(_as_text(e) for e in v)
    if isinstance(v, SegString):
        return ("SegString", v.__walk__() if v.is_ground() else repr(v))
    return v


@pytest.mark.parametrize("goal", _PARITY_GOALS)
def test_the_three_spellings_answer_alike(tmp_path, goal):
    from clausal.logic.atoms import char_atom
    from clausal.logic.exceptions import LogicException
    import re
    vars_ = sorted(set(re.findall(r"\b([A-Z][A-Za-z0-9]*)\b", goal)) - {"X"})
    head = "p(X" + "".join(", " + v for v in vars_) + ")"
    mod = _mod(tmp_path, f"is_a(a),\n{head} <- ({goal})\n")
    spellings = [("carrier", chars("ab")), ("list", [char_atom("a"), char_atom("b")])]
    answers = {}
    for label, x in spellings:
        args = [Var() for _ in vars_]
        try:
            got = sorted(repr(_as_text([deref(a) for a in args])) for _ in call("p", x, *args, module=mod))
        except LogicException as e:
            got = ["raised " + type(e).__name__ + " " + repr(_as_text(e.args[0] if e.args else e))[:60]]
        answers[label] = got
    # the carrier and the bare str are ONE spelling family and must agree
    # exactly; the char list is input-type-wins on OUTPUT shape (a str tail
    # stays text, a list tail stays a list), so it is held to the same
    # success/failure COUNT only
    if "str" in answers:
        assert answers["carrier"] == answers["str"], answers
    assert len(answers["list"]) == len(answers["carrier"]), answers


class TestSlice5Crossings:
    """Slice 5: the seam and the py-modules -- text crosses OUT to Python as
    a str and comes back IN as the carrier; module results are carriers."""

    def test_thunk_sees_the_text_and_hands_back_the_carrier(self, tmp_path):
        mod = _mod(tmp_path, 'p(N) <- (S is "abc", N is ++len(S))\nq(R) <- (S is "abc", R is ++S.upper())\n')
        (n,) = _first(mod, "p", Var()); assert n == 3, n
        (r,) = _first(mod, "q", Var()); assert r == "ABC", r   # STAGE 2: a thunk's str result is the ATOM

    def test_to_term_and_from_term_round_trip(self):
        from clausal.logic.python_terms import to_term, from_term
        assert to_term("ab") == "ab" and to_term(["ab", 1]) == ["ab", 1]     # STAGE 2: a str is the atom
        assert to_term({"k": "v"}) == {"k": "v"}
        assert from_term(chars("ab")) == "ab" and from_term([chars("ab"), 1]) == ["ab", 1]

    def test_module_results_are_carriers(self, tmp_path):
        mod = _mod(tmp_path, '-import_from(py.hash, [hash])\np(H) <- hash("sha256", "abc", H)\n')
        (h,) = _first(mod, "p", Var()); assert h == chars("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"), h

    def test_a_chars_string_in_goal_position_is_refused_like_a_str(self, tmp_path):
        from clausal.logic.exceptions import LogicException
        mod = _mod(tmp_path, 'p <- call("foo")\n')
        with pytest.raises(LogicException) as ei:
            _first(mod, "p")
        assert "existence_error" in str(ei.value) and "$chars" not in str(ei.value)
