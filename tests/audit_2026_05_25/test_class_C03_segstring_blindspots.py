"""C3 — SegString blind spots vs SegList.

8 findings (5 bug + 3 design-gap). The dispatch sites that branch on
the target's container type have SegList arms but no SegString arms.
A single Phase 2 fix (likely at the _as_items-equivalent layer or per-
site __walk__ shims) could close many of these in one change.

Findings tested here:
- F012 Var bound to SegString in list position not recognised as a char
- F031 _head_list_unify_input never walks SegString (non-ground fails)
- F032 _head_list_unify_input rejects ground SegString too
- F034 _head_list_unify_output never walks SegString star_val
- F040 _body_multi_star_unify rejects ground SegString target
- F041 _body_multi_star_unify has no non-ground SegString branch
- F047 Multi-star head guard ignores SegString (ground and non-ground)
- F075 Every char/atom builtin in chars.py is SegString-blind
"""

import pytest

from clausal.logic.atoms import char_atom, mint
from clausal.logic.cells import chars


def test_F012_bare_str_vs_list_is_retired_segstring_var_binding_still_works():
    """RETIRED by P3-1 Task 5 (\u00a71b): `unify("a", [v])` was a direct bare
    str-vs-list unify (the exact C block cited below, `_variables.c:1149/
    1175`, is now DELETED entirely) -- it fails post-retirement regardless
    of what `v` is bound to, so the original F012 "SegString not
    recognised as a char in a bare-str-vs-list unify" finding is moot: the
    bare-str-vs-list call shape it was about no longer succeeds for ANY
    list element type, str or SegString. The control assertion (binding a
    Var to a SegString) is unaffected and still pinned below.
    """
    from clausal.logic.variables import Trail, Var, unify
    from clausal.terms import SegString

    v = Var()
    t = Trail()
    bound = unify(v, SegString("a"), t)
    assert bound is True, (
        f"control: binding v to SegString('a') should succeed; "
        f"got {bound!r}"
    )

    ok = unify("a", [v], t)
    assert ok is False, (
        f"unify('a', [v]) is a bare str-vs-list unify -- retired by P3-1 "
        f"\u00a71b regardless of what v is bound to; got {ok!r}"
    )


def test_F031_head_list_unify_input_non_ground_segstring():
    """`_head_list_unify_input(SegString([\"a\", VarSeg(X), \"c\"]), [H], T, [], t)`
    should not silently return False.

    The input-mode helper has an explicit ``isinstance(d, SegList)``
    walk branch but no SegString equivalent. A non-ground SegString
    flows past the list/str isinstance check, past the SegList check,
    past the is_var defer, and hits the final ``return False``. The
    head pattern ``foo([H, *T])`` against this SegString is logically
    satisfiable (e.g. H="a", T=SegString([VarSeg(X), "c"])), so the
    silent False drops a real solution.
    """
    from clausal.logic.variables import Var, Trail
    from clausal.terms import SegString, VarSeg
    from clausal.logic.runtime.list_unify import _head_list_unify_input

    X = Var()
    seg = SegString(["a", VarSeg(X), "c"])
    H, T = Var(), Var()
    t = Trail()
    result = _head_list_unify_input(seg, [H], T, [], t)

    # Expected: True (or None for deferred). The bug is silent False.
    assert result is not False, (
        f"_head_list_unify_input(non-ground SegString, [H], T, [], t) "
        f"returned {result!r}; expected True (or None for deferred) — "
        f"the goal is logically satisfiable but list_unify.py:114-117 "
        f"has no SegString-walking branch."
    )


def test_F032_head_list_unify_input_ground_segstring():
    """`_head_list_unify_input(SegString([\"abc\"]), [H], T, [], t)` should
    succeed with H='a' and T='bc'.

    A trivially-ground ``SegString(["abc"])`` whose ``__walk__()``
    returns the plain str ``"abc"`` is *still* rejected: the function
    never walks SegString. The unification is unambiguously solvable
    (H='a', T='bc') — silent False is the stronger half of F031.
    """
    from clausal.logic.variables import Var, Trail, deref
    from clausal.terms import SegString
    from clausal.logic.runtime.list_unify import _head_list_unify_input

    ss = SegString(["abc"])
    # Sanity-check the precondition the bug claim depends on.
    assert ss.is_ground() and ss.__walk__() == chars("abc"), (
        f"precondition: SegString(['abc']) should be ground and walk "
        f"to 'abc'; got is_ground={ss.is_ground()}, "
        f"walk={ss.__walk__()!r}"
    )

    H, T = Var(), Var()
    t = Trail()
    result = _head_list_unify_input(ss, [H], T, [], t)

    assert result is True, (
        f"_head_list_unify_input(SegString(['abc']), [H], T, [], t) "
        f"returned {result!r}; expected True with H='a' and T='bc' — "
        f"SegString walks to 'abc' but the helper never invokes "
        f"__walk__ (no SegString branch at list_unify.py:114-117)."
    )
    # THE FLIP (spec §6.2): the head of a string is its CHAR ATOM; the tail
    # stays a ``str`` slice (R-S2).
    assert deref(H) == char_atom("a") and deref(T) == chars("bc"), (
        f"expected H=('a',), T='bc' from destructuring SegString(['abc']); "
        f"got H={deref(H)!r}, T={deref(T)!r}"
    )


def test_F034_head_list_unify_output_walks_segstring_star_val():
    """Output-mode reconstruction should walk a seg_string-bound star_val,
    not append it as a single opaque element.

    The output-mode helper branches `star_val` on ``list`` (extend),
    ``SegList`` (walk-and-extend), and ``Var`` (rebuild with VarSeg).
    It has no seg_string branch — a seg_string-bound star_val falls
    into the catch-all ``else`` and is appended whole. A head
    ``foo([H, *T])`` whose T is bound to ``seg_string(['hello'])``
    therefore produces ``['h', seg_string(['hello'])]`` instead of
    walking the seg_string into chars (as the parallel SegList branch
    would do) or, under "input type wins", into a str.
    """
    from clausal.logic.variables import Var, unify, Trail, deref
    from clausal.terms import SegString
    from clausal.logic.runtime.list_unify import _head_list_unify_output

    target = Var()
    H, T = Var(), Var()
    unify(H, char_atom("h"), Trail())
    unify(T, SegString(["ello"]), Trail())
    _head_list_unify_output(target, [H], T, [], Trail())

    bound = deref(target)
    # The actual current behaviour is ['h', SegString(['ello'])] — a list
    # with an opaque SegString tail element. The expected behaviour
    # (symmetric with the SegList branch) walks the SegString.
    assert bound == [char_atom(c) for c in "hello"] or bound == chars("hello"), (
        f"_head_list_unify_output with T bound to SegString(['ello']) "
        f"should walk the SegString into chars (or, under 'input type "
        f"wins', into the str 'hello'); got {bound!r} "
        f"(type={type(bound).__name__}). The SegString was appended as "
        f"a single opaque element because there is no SegString branch "
        f"at list_unify.py:166-200."
    )


def test_F040_body_multi_star_unify_ground_segstring():
    """`_body_multi_star_unify(SegString(["abc"]), [fixed,star,fixed], t)`
    should yield True (one solution), not silently produce [].

    The dispatch checks ``(list, str)``, then ``SegList``, then
    ``is_var``. A trivially ground ``SegString(['abc'])`` (which walks
    to ``"abc"``) falls through all four branches and hits the
    catch-all ``else: return`` at body_star_unify.py:262. Silent
    zero-solutions on a logically-satisfiable goal — the multi-star
    body twin of F032.
    """
    from clausal.logic.variables import Var, Trail
    from clausal.logic.runtime.body_star_unify import _body_multi_star_unify
    from clausal.terms import SegString

    ss = SegString(["abc"])
    # Precondition: ground SegString walks to plain str.
    assert ss.is_ground() and ss.__walk__() == chars("abc"), (
        f"precondition: SegString(['abc']) ground+walks-to-'abc'; "
        f"got is_ground={ss.is_ground()}, walk={ss.__walk__()!r}"
    )

    H, S, R = Var(), Var(), Var()
    segments = [("fixed", [H]), ("star", S), ("fixed", [R])]
    solutions = list(_body_multi_star_unify(ss, segments, Trail()))

    assert len(solutions) >= 1, (
        f"_body_multi_star_unify(SegString(['abc']), [fixed,star,fixed]) "
        f"yielded {solutions!r}; expected at least one True (analogous "
        f"to the SegList branch which walks then enumerates). "
        f"body_star_unify.py:234-262 has no SegString branch — the "
        f"value falls through to the catch-all 'else: return'."
    )


def test_F041_body_multi_star_unify_non_ground_segstring():
    """`_body_multi_star_unify(SegString(["a", VarSeg(X), "c"]), …)` should
    not silently yield [].

    The non-list/str dispatch has an ``isinstance(d, SegList)`` branch
    (body_star_unify.py:235-248) but no parallel ``isinstance(d,
    SegString)`` branch. A non-ground SegString-bound target hits the
    catch-all ``else: return`` and silently drops the goal. (The
    SegList branch is itself currently blocked on F030's deferred
    SegList-vs-SegList unification — but F041 is the *structural*
    absence of the SegString branch.)
    """
    from clausal.logic.variables import Var, Trail
    from clausal.logic.runtime.body_star_unify import _body_multi_star_unify
    from clausal.terms import SegString, VarSeg

    X = Var()
    ss = SegString(["a", VarSeg(X), "c"])
    assert not ss.is_ground(), (
        f"precondition: SegString(['a', VarSeg(X), 'c']) should be "
        f"non-ground; got is_ground={ss.is_ground()}"
    )

    H, S, R = Var(), Var(), Var()
    segments = [("fixed", [H]), ("star", S), ("fixed", [R])]
    solutions = list(_body_multi_star_unify(ss, segments, Trail()))

    # Expected: at least one yield (a structural SegString branch
    # symmetric to body_star_unify.py:235-248). Today: silent [].
    assert len(solutions) >= 1, (
        f"_body_multi_star_unify(non-ground SegString, "
        f"[fixed,star,fixed]) yielded {solutions!r}; expected at "
        f"least one yield from a structural SegString branch "
        f"(symmetric to the SegList branch at body_star_unify.py:"
        f"235-248). Today: no SegString branch → silent 'else: return'."
    )


def test_F047_multi_star_head_guard_segstring():
    """Multi-star head pattern ``bracket([*A, X, Y, *B], X, Y, A, B)``
    invoked with a SegString target should yield the same solutions as
    the str/list controls — not silently zero.

    The multi-star head guard at head_match.py:857-872 normalises
    SegList before the ``(list, str)`` isinstance arm but has no
    SegString normalisation. A SegString target (ground or non-ground)
    walks past SegList normalise, past Var defer, fails the
    ``(list, str)`` isinstance test, the multi-star arm is skipped,
    and the caller silently gets zero solutions.
    """
    from clausal.logic.solve import call
    from clausal.logic.variables import Var
    from clausal.terms import SegString, VarSeg
    from tests.audit_2026_05_25._helpers import load_inline_clausal

    src = "bracket([*A, X, Y, *B], X, Y, A, B),\n"
    mod = load_inline_clausal("c03_f047_bracket", src).__dict__["$module"]

    # Control 1: ground str — walks via (list, str) isinstance arm.
    X1, Y1, A1, B1 = Var(), Var(), Var(), Var()
    n_str = sum(1 for _ in call("bracket", "abc", X1, Y1, A1, B1, module=mod))
    assert n_str > 0, (
        f"control: bracket(\"abc\") should yield >0 solutions; "
        f"got {n_str}. If this fails, the fixture is broken."
    )

    # Control 2: ground list — symmetric.
    X2, Y2, A2, B2 = Var(), Var(), Var(), Var()
    n_list = sum(
        1 for _ in call("bracket", ["a", "b", "c"], X2, Y2, A2, B2, module=mod)
    )
    assert n_list > 0, (
        f"control: bracket(['a','b','c']) should yield >0 solutions; "
        f"got {n_list}. If this fails, the fixture is broken."
    )

    # Probe 1: ground SegString — walks to "abc"; should equal str control.
    ss_ground = SegString(["abc"])
    assert ss_ground.is_ground() and ss_ground.__walk__() == chars("abc")
    X3, Y3, A3, B3 = Var(), Var(), Var(), Var()
    n_ss_ground = sum(
        1 for _ in call("bracket", ss_ground, X3, Y3, A3, B3, module=mod)
    )

    # Probe 2: non-ground SegString — semantically "a" + ?X + "c";
    # multi-star pattern [*A, X, Y, *B] is logically satisfiable.
    XV = Var()
    ss_partial = SegString(["a", VarSeg(XV), "c"])
    X4, Y4, A4, B4 = Var(), Var(), Var(), Var()
    n_ss_partial = sum(
        1 for _ in call("bracket", ss_partial, X4, Y4, A4, B4, module=mod)
    )

    assert n_ss_ground == n_str, (
        f"bracket(SegString(['abc'])) yielded {n_ss_ground} solutions; "
        f"expected the same count as the str control ({n_str}) since "
        f"the SegString walks to 'abc'. The multi-star head guard at "
        f"head_match.py:857-872 has no SegString normalisation, so the "
        f"target falls through and the multi-star arm is skipped."
    )
    assert n_ss_partial > 0, (
        f"bracket(SegString(['a', VarSeg(X), 'c'])) yielded "
        f"{n_ss_partial} solutions; expected >0 since the goal is "
        f"logically satisfiable. The multi-star head guard silently "
        f"drops the SegString."
    )


def test_F075_chars_builtins_refuse_a_segstring_as_an_atom():
    """THE FLIP (spec §6.1/§6.6) INVERTS this pin: a ground ``SegString``
    walks to a ``str``, and a ``str`` is a STRING, not an atom.
    ``_atom_to_str`` is the funnel for "read an ATOM's spelling", so the
    ``str``/``SegString`` arms are gone and ``atom_length/2`` answers
    ``type_error(atom, …)`` -- exactly as it does for the plain ``str``
    ``"hi"``.  The C25 question the original test asked (does the
    SegString reach the same code path as its walked form?) is still
    answered here, just with the post-flip answer.
    """
    from clausal.logic.builtins import get_builtin_dispatch
    from clausal.logic.variables import Var, Trail, deref
    from clausal.logic.trampoline import StepGenerator, solutions
    from clausal.logic.exceptions import LogicException
    from clausal.terms import SegString

    seg = SegString(["hi"])
    # Precondition: this SegString walks to the plain str "hi".
    assert seg.is_ground() and seg.__walk__() == chars("hi"), (
        f"precondition: SegString(['hi']) should be ground and walk "
        f"to 'hi'; got is_ground={seg.is_ground()}, "
        f"walk={seg.__walk__()!r}"
    )

    # atom_length(SegString(["hi"]), N) should bind N=2 (same as the
    # walked str "hi") — currently raises type_error("atom", ...).
    # Use ``snapshot=lambda: deref(N)`` so we capture the binding while
    # it is live (the trampoline undoes bindings on the way out, mirroring
    # the way real callers see solutions one at a time).
    N = Var()
    disp = get_builtin_dispatch("atom_length", 2, None)
    with pytest.raises(LogicException) as exc:
        solutions(
            StepGenerator(disp, None, None, None, seg, N, Trail()),
            snapshot=lambda: deref(N),
        )
    assert "type_error" in str(exc.value) and "atom" in str(exc.value)
    # ...and the plain ``str`` it walks to gets the identical answer, which
    # is the parity the original test was really asking about.
    N2 = Var()
    with pytest.raises(LogicException):
        solutions(
            StepGenerator(disp, None, None, None, chars("hi"), N2, Trail()),
            snapshot=lambda: deref(N2),
        )
    # The ATOM of that spelling is what has a length.
    N3 = Var()
    sols = solutions(
        StepGenerator(disp, None, None, None, mint("hi"), N3, Trail()),
        snapshot=lambda: deref(N3),
    )
    assert sols == [2]

    # char_type/2 takes a CHAR (an atom of length 1) and a Type ATOM.  A
    # single-char SegString walks to the ``str`` "a", which is a
    # one-element STRING and not a char, so it yields nothing -- the same
    # answer the plain ``str`` gets.  The char atom is what succeeds.
    seg1 = SegString(["a"])
    assert seg1.is_ground() and seg1.__walk__() == chars("a")
    disp_ct = get_builtin_dispatch("char_type", 2, None)
    assert len(solutions(StepGenerator(
        disp_ct, None, None, None, seg1, mint("alpha"), Trail()))) == 0
    assert len(solutions(StepGenerator(
        disp_ct, None, None, None, chars("a"), mint("alpha"), Trail()))) == 0
    assert len(solutions(StepGenerator(
        disp_ct, None, None, None, char_atom("a"), mint("alpha"),
        Trail()))) >= 1
