"""Slice 4 on the native ``.pl`` front end, construct by construct (plan
native-iso-reader-step2 §4 Slice 4; operator rulings 2026-09-30):

* D13: ``\\+``, once/1, forall/2, memberchk/2, the ``findall(_, G, [])``
  backdoor and make_quantity/3 are ACCEPTED and COUNTED (goal positions
  only), never refused.
* D35: a DATA-position ``true``/``false``/``undefined`` is the truth value
  (Python ``True``/``False``, ``Undefined``), exactly as the seam folds it;
  so ``memberd_t(b, [a, b], true)`` succeeds (it FAILED: a silent wrong
  answer).
* D40: a user-defined true/N and false/N (N >= 1) loads and answers, on the
  native path AND the seam; true/0 and false/0 stay reserved.
* library(reif): if_/3 with Scryer's meaning, only when imported; its
  tfilter/3 and tpartition/4 replace the engine's committed-choice
  builtins, and a file's own definition of one of them wins without losing
  the rest of the library.
* maplist/4..9 and findall/4 (Scryer's lists and builtins).
"""
from __future__ import annotations

import logging
import textwrap

import pytest


def _load(native, name, text, **kw):
    return native.load(name, textwrap.dedent(text), **kw)


def _plain(t):
    """A walked answer with the chars carrier read back as its list (the
    walk shows a list of one-char atoms as the carrier)."""
    if type(t) is tuple and len(t) == 2 and t[0] == "$chars":
        return list(t[1])
    if type(t) is tuple:
        return tuple(_plain(a) for a in t)
    if type(t) is list:
        return [_plain(a) for a in t]
    return t


# ── D13: the transition-construct lint ──


def test_every_key_is_present_and_a_clean_file_counts_zero(native, caplog):
    caplog.set_level(logging.INFO, logger="clausal.pl_frontend")
    mod = _load(native, "s4_clean", "p(X) :- member(X, [1, 2]).\n")
    assert mod.__loader__.l3_stats["transition_constructs"] == {
        "\\+/1": 0, "once/1": 0, "forall/2": 0, "memberchk/2": 0,
        "findall/3_empty": 0, "make_quantity/3": 0}
    assert not [r for r in caplog.records
                if "transition constructs" in r.getMessage()]


def test_goal_positions_are_counted_data_positions_are_not(native):
    mod = _load(native, "s4_lint", """\
        :- use_module(library(lists)).
        a(X) :- \\+ \\+ X = 1.
        b(X) :- findall(Y, (member(Y, X), \\+ Y = 2), _).
        c(X) :- catch(once(X), _, true), forall(true, once(true)).
        d(X) :- lists:memberchk(X, [1]).
        e(G) :- G = (\\+ fail), H = once(true), call(G), call(H).
        f(L) :- maplist(memberchk(1), L).
        g :- findall(_, fail, []), findall(_, fail, _), findall(_, fail, [x]).
        h(Q) :- make_quantity(1, meter, Q).
        """)
    assert mod.__loader__.l3_stats["transition_constructs"] == {
        "\\+/1": 3, "once/1": 2, "forall/2": 1, "memberchk/2": 1,
        "findall/3_empty": 1, "make_quantity/3": 1}


def test_the_counted_constructs_still_run(native, ans):
    mod = _load(native, "s4_run", """\
        a(X) :- member(X, [1, 2, 3]), \\+ X = 2.
        b(X) :- once(member(X, [p, q])).
        c(ok) :- forall(member(X, [1, 2]), X > 0).
        d(X) :- memberchk(X, [p, q]).
        e(X) :- member(X, [1, 2]), findall(_, X > 1, []).
        """)
    assert ans(mod, "a") == [1, 3]
    assert ans(mod, "b") == ["p"]
    assert ans(mod, "c") == ["ok"]
    assert ans(mod, "d") == ["p"]
    assert ans(mod, "e") == [1]


# ── D35: data-position truth values ──


def test_memberd_t_with_a_written_true_succeeds(native, ans):
    mod = _load(native, "s4_d35", """\
        :- use_module(library(reif)).
        yes(ok) :- memberd_t(b, [a, b], true).
        no(ok) :- memberd_t(c, [a, b], false).
        t(T) :- memberd_t(b, [a, b], T), T == true.
        """)
    assert ans(mod, "yes") == ["ok"]
    assert ans(mod, "no") == ["ok"]
    assert ans(mod, "t") == [True]


def test_true_false_undefined_in_data_are_the_truth_values(native, ans):
    from clausal.terms import Undefined
    mod = _load(native, "s4_truth", """\
        v(X) :- X = [true, false, undefined].
        h(true). h(false).
        g(ok) :- true, \\+ false.
        """)
    [row] = ans(mod, "v")
    assert row[0] is True and row[1] is False and row[2] is Undefined
    assert ans(mod, "h") == [True, False]
    assert ans(mod, "g") == ["ok"]
    # a truth value is not an atom the file declares
    assert mod.__loader__.l3_stats["auto_declared"]["atoms"] == 1   # ok


def test_capitalised_true_is_a_variable(native, ans):
    mod = _load(native, "s4_tvar", "v(True) :- True = 1.\n")
    assert ans(mod, "v") == [1]


# ── D40: user-defined true/N and false/N ──


D40_PL = """\
    true(X) :- X = 1.
    false(X, Y) :- Y is X + 1.
    q(Y) :- true(Y).
    r(Y) :- false(1, Y).
    c(Y) :- call(true, Y).
    e(E) :- catch(call(true, 1, 2), error(E, _), true).
    """


def test_d40_native(native, ans):
    mod = _load(native, "s4_d40", D40_PL)
    assert ans(mod, "q") == [1]
    assert ans(mod, "r") == [2]
    assert ans(mod, "c") == [1]
    # the indicator's name is the atom ``true`` -- whose object is ``True``
    # (D35 closed): ``mint("true")`` IS ``True``, so ``true/2`` walks as
    # ``('/', True, 2)``; the str spelling still unifies with it.
    assert ans(mod, "e") == [("existence_error", "procedure",
                              ("/", True, 2))]


def test_d40_seam(native, ans):
    mod = _load(native, "s4_d40s", """\
        true(X) <- (X is 1)
        false(X, Y) <- (Y == X + 1)
        q(Y) <- true(Y)
        r(Y) <- false(1, Y)
        c(Y) <- call(true, Y)
        """, suffix=".seam", frontend=None)
    assert ans(mod, "q") == [1]
    assert ans(mod, "r") == [2]
    assert ans(mod, "c") == [1]


def test_true_0_is_still_reserved_on_the_seam(native):
    with pytest.raises(NameError, match="reserved truth value"):
        _load(native, "s4_d40r", "true <- (1 is 1)\n", suffix=".seam",
              frontend=None)


def test_true_0_is_still_the_control_construct_natively(native):
    with pytest.raises(SyntaxError, match="control construct true/0"):
        _load(native, "s4_d40n", "true :- fail.\n")


def test_call_true_with_extras_and_no_definition_is_existence_error(native,
                                                                    ans):
    mod = _load(native, "s4_d40e",
                "e(E) :- catch(call(true, 1), error(E, _), true).\n")
    assert ans(mod, "e") == [("existence_error", "procedure",
                              ("/", "true", 1))]


# ── library(reif) ──


def test_if_is_reifs_only_when_imported(native, ans):
    mod = _load(native, "s4_noreif",
                "i(E) :- catch(if_(1 = 1, true, true), error(E, _), true).\n")
    [err] = ans(mod, "i")
    assert err[0] == "existence_error" and err[2] == ("/", "if_", 3)


def test_an_import_list_without_if_leaves_it_a_plain_call(native, ans):
    mod = _load(native, "s4_reiflist", """\
        :- use_module(library(reif), [memberd_t/3]).
        i(E) :- catch(if_(1 = 1, true, true), error(E, _), true).
        m(T) :- memberd_t(a, [a], T).
        """)
    assert ans(mod, "i")[0][2] == ("/", "if_", 3)
    assert ans(mod, "m") == [True]


def test_if_named_in_an_import_list(native, ans):
    mod = _load(native, "s4_reifif", """\
        :- use_module(library(reif), [if_/3, (=)/3, (',')/3, (;)/3]).
        i(R) :- if_((a = b ; 1 = 1), R = y, R = n).
        """)
    assert ans(mod, "i") == ["y"]


def test_if_condition_errors_are_scryers(native, ans):
    mod = _load(native, "s4_iferr", """\
        :- use_module(library(reif)).
        u(_).
        w(maybe).
        e(E) :- member(G, [u, w]), catch(if_(G, true, true), error(E, _), true).
        """)
    assert ans(mod, "e") == ["instantiation_error",
                             ("type_error", "boolean", "maybe")]


def test_a_local_tfilter_wins_and_the_rest_of_reif_stays(native, ans):
    mod = _load(native, "s4_local", """\
        :- use_module(library(reif)).
        tfilter(_, L, L).
        t(L) :- tfilter(=(a), [a, b], L).
        m(T) :- memberd_t(b, [a, b], T).
        p(Ts) :- tpartition(=(a), [a, b], Ts, _).
        """)
    assert _plain(ans(mod, "t")) == [["a", "b"]]
    assert ans(mod, "m") == [True]
    assert _plain(ans(mod, "p")) == [["a"]]


def test_reif_tfilter_gives_every_answer_the_builtin_commits(native, ans):
    reif = _load(native, "s4_tf_reif", """\
        :- use_module(library(reif)).
        t(X-Fs) :- tfilter(=(a), [X], Fs).
        """)
    builtin = _load(native, "s4_tf_builtin", """\
        t(X-Fs) :- tfilter(=(a), [X], Fs).
        """)
    got = _plain(ans(reif, "t"))
    assert len(got) == 2 and got[0] == ("-", "a", ["a"]) and got[1][2] == []
    assert len(ans(builtin, "t")) == 1


def test_reif_closures_resolve_in_the_callers_module(native, ans):
    mod = _load(native, "s4_closure", """\
        :- use_module(library(reif)).
        small_t(X, T) :- ( X < 3, T = true ; X >= 3, T = false ).
        t(L) :- tfilter(small_t, [1, 5, 2, 7], L).
        m(ok) :- tmember(small_t, [5, 2]).
        """)
    assert ans(mod, "t") == [[1, 2]]
    assert ans(mod, "m") == ["ok"]


# ── maplist/4..9, findall/4 ──


def test_maplist_4_to_9(native, ans):
    mod = _load(native, "s4_maplist", """\
        s(A, B, C, D) :- D is A + B + C.
        s(A, B, C, D, E, F, G, H) :- H is A + B + C + D + E + F + G.
        m4(L) :- maplist(s, [1, 2], [10, 20], [100, 200], L).
        m8(L) :- maplist(s, [1], [1], [1], [1], [1], [1], [1], L).
        len(E) :- catch(maplist(s, [1], [1, 2], [1], _), E, true).
        pr(A, B, C, A-B-C).
        open(L) :- maplist(pr, [x|T], [1, 2], [a, b], L), T = [y].
        """)
    assert ans(mod, "m4") == [[111, 222]]
    assert ans(mod, "m8") == [[7]]
    assert ans(mod, "len") == []            # different lengths: no answer
    assert ans(mod, "open") == [[("-", ("-", "x", 1), "a"),
                                 ("-", ("-", "y", 2), "b")]]


def test_findall_4(native, ans):
    mod = _load(native, "s4_fa4", """\
        f(L) :- findall(X, member(X, [1, 2]), L, [3]).
        g(L-T) :- findall(X, member(X, [1, 2]), L, T).
        h(E) :- catch(findall(X, member(X, [1]), _, foo), error(E, _), true).
        k(L) :- G = findall(X, member(X, [a]), L, []), call(G).
        """)
    assert ans(mod, "f") == [[1, 2, 3]]
    [(lst, tail)] = [(r[1], r[2]) for r in ans(mod, "g")]
    assert list(lst)[:2] == [1, 2]
    assert ans(mod, "h") == [("type_error", "list", "foo")]
    assert ans(mod, "k") == [["a"]]


def test_eq3_and_dif3_answer_orders_are_scryers(native, ans):
    mod = _load(native, "s4_eqdif", """\
        e(T) :- =(_, a, T).
        d(T) :- dif(_, a, T).
        g(T1-T2) :- =(a, a, T1), dif(a, b, T2).
        """)
    assert ans(mod, "e") == [True, False]
    assert ans(mod, "d") == [False, True]
    assert ans(mod, "g") == [("-", True, True)]


# ── D26b: a listless use_module/1 of a SEAM module ──


D26B_LIB = """\
    -module(s4seamlib, [check_true, not_member, area/2, red])

    check_true(X) <- (X is 1)
    not_member(_, []),
    not_member(X, [Y, *T]) <- (dif(X, Y), not_member(X, T))
    area(W, A) <- (A == W * W)
    """


def _seam_module(native, name, text):
    (native.tmp / f"{name}.seam").write_text(textwrap.dedent(text),
                                            encoding="utf-8")
    native._names.append(name)


def test_listless_use_module_of_a_seam_module_imports_its_exports(native,
                                                                  ans):
    """D26b: the bare names of the seam module's -module list (predicates
    at every arity, atoms) are imported, like its name/N entries."""
    import warnings
    _seam_module(native, "s4seamlib", D26B_LIB)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")   # the lib's own atom-export lint
        mod = _load(native, "s4_d26b", """\
            :- use_module(s4seamlib).
            a(X) :- check_true(X).
            b(ok) :- not_member(a, [b]).
            c(A) :- area(3, A).
            q(ok) :- s4seamlib:not_member(a, [b]).
            """)
    assert ans(mod, "a") == [1]
    assert ans(mod, "b") == ["ok"]
    assert ans(mod, "c") == [9]
    assert ans(mod, "q") == ["ok"]


def test_listless_use_module_of_a_module_exporting_nothing_loads_it(native,
                                                                   ans):
    _seam_module(native, "s4seamnone", """\
        -module(s4seamnone, [])

        hidden(7),
        """)
    mod = _load(native, "s4_d26b0", """\
        :- use_module(s4seamnone).
        q(X) :- s4seamnone:hidden(X).
        """)
    assert ans(mod, "q") == [7]


# ── D35's cost, CLOSED: the truth values ARE atoms to the engine ──
#
# A data ``true`` IS Python ``True`` (the ruling), and the engine reads the
# object as the atom ``true`` (``clausal.logic.atoms.is_truth_atom``): atom/1,
# the atom builtins, functor/3, unification and the standard order all answer
# as Scryer does.  These were strict-xfail while the cost was open; the wider
# table is tests/iso_l3/test_l3_truth_atoms.py.

_ISO_ATOM_TRUE = """\
    a1(ok) :- atom(true).
    a2(N) :- atom_length(false, N).
    a3(F) :- functor(F, true, 1), F = true(x).
    a4(ok) :- atom_chars(X, [t, r, u, e]), X == true.
    a5(ok) :- true \\= 1.
    a6(O) :- compare(O, true, a).
    """


@pytest.mark.parametrize("name, scryer", [
    ("a1", ["ok"]),
    ("a2", [5]),
    ("a3", [("true", "x")]),
    ("a4", ["ok"]),
    ("a5", ["ok"]),
    ("a6", [">"]),
])
def test_d35_truth_values_behave_as_scryers_atoms(native, ans, name, scryer):
    mod = _load(native, "s4_d35_iso", _ISO_ATOM_TRUE)
    assert ans(mod, name) == scryer
