"""C14 — Term inspection drift.

7 findings (4 bug + 3 design-gap). The inspection predicates
(functor/3, arg/3, =../2, copy_term/2, term_variables/2) disagree
about what the "args" of a list are, fail to copy Seg* containers
correctly, and don't see VarSegs as variables. F092 (copy_term
aliasing) is the most serious — it's a correctness landmine for any
future code that puts Seg* in clauses. F092 and F093 have lock-in
tests in tests/test_term_inspection.py.

Findings tested here (all closed as of 2026-06-13 follow-up):
- F088 (bug) unpack (=..) on a non-empty list now follows ISO cons-cell
- F089 (design-gap) functor/3 and =.. now Liskov-symmetric on str ↔ list
- F090 (bug) arg(N, "abc", X) follows cons-cell symmetry on str
- F091 (bug) arg/3 on non-empty list now uses cons-cell head/tail
- F092 (bug) copy_term aliases Seg* containers (closed Phase 2 Task 10)
- F093 (design-gap) term_variables Seg*-blind (closed Phase 2 Task 10)
- F094 (design-gap) numbervars/3 cannot number Vars inside Seg* containers
"""

from clausal.logic.atoms import char_atom, mint
from clausal.logic.builtins import get_builtin_dispatch
from clausal.logic.trampoline import StepGenerator, solutions
from clausal.logic.variables import Trail, Var, deref
from clausal.terms import SegList, SegString, VarSeg


def _collect(name, arity, *args, snap):
    """Run a builtin and snapshot the result for each solution."""
    disp = get_builtin_dispatch(name, arity, None)
    return solutions(
        StepGenerator(disp, None, None, None, *args, Trail()),
        snapshot=snap,
    )


def test_F088_unpack_on_list_uses_cons_cell():
    """``unpack(["a","b","c"], L)`` follows ISO cons-cell decomposition
    on a LIST (unaffected by P3-1 Task 5).

    User decision 2026-06-13: ISO-named inspection predicates follow
    ISO Prolog semantics. ``=..`` on a non-empty list returns the
    cons-cell shape ``[".", head, tail]`` where ``tail`` is the rest
    of the list.

    THE FLIP (spec §6.4) INVERTS P3-1 Task 5's str-is-atomic reading: a
    ``str`` is the LIST of its char atoms, so ``unpack("abc", L)`` is back
    to the cons-cell shape ``[".", ("a",), "bc"]`` (the tail a ``str``
    SLICE, R-S2).  The ATOM ``("abc",)`` is what decomposes as ``[atom]``.
    """
    L = Var()
    sols = _collect(
        "unpack", 2, [mint("a"), mint("b"), mint("c")], L, snap=lambda L=L: deref(L)
    )
    assert sols == [[mint("."), mint("a"), [mint("b"), mint("c")]]], (
        f'unpack(["a","b","c"], L) bound L={sols!r}; expected '
        f'[".", "a", ["b","c"]] under ISO cons-cell.'
    )

    # THE FLIP: the ATOM decomposes as [self]; the STRING decomposes as the
    # cons cell of the char list it denotes.
    L2 = Var()
    sols2 = _collect(
        "unpack", 2, mint("abc"), L2, snap=lambda L=L2: deref(L)
    )
    assert sols2 == [[mint("abc")]], (
        f'unpack(("abc",), L) bound L={sols2!r}; expected [("abc",)].'
    )
    L2b = Var()
    sols2b = _collect(
        "unpack", 2, "abc", L2b, snap=lambda L=L2b: deref(L)
    )
    assert sols2b == [[mint("."), mint("a"), "bc"]], (
        f'unpack("abc", L) bound L={sols2b!r}; expected '
        f'[".", ("a",), "bc"] -- a STRING is a list (spec §6.4).'
    )

    # Empty cases — nil atom.
    L3 = Var()
    sols3 = _collect("unpack", 2, [], L3, snap=lambda L=L3: deref(L))
    assert sols3 == [[mint("[]")]], (
        f'unpack([], L) bound L={sols3!r}; expected ["[]"].'
    )
    L4 = Var()
    sols4 = _collect("unpack", 2, "", L4, snap=lambda L=L4: deref(L))
    assert sols4 == [[mint("[]")]], (
        f'unpack("", L) bound L={sols4!r}; expected ["[]"].'
    )


def test_F089_functor_agrees_on_string_vs_char_list_and_diverges_on_the_atom():
    """THE FLIP (spec §6.4): a STRING and its char-atom LIST are one term, so
    ``functor/3`` answers ``(".", 2)`` for both -- symmetric again, INVERTING
    P3-1 Task 5's "str is atomic" divergence.  What diverges now is the ATOM
    ``("abc",)``, which is its own functor at arity 0.
    """
    F1, A1 = Var(), Var()
    sols_atom = _collect(
        "functor", 3, mint("abc"), F1, A1,
        snap=lambda F=F1, A=A1: (deref(F), deref(A)),
    )
    F1b, A1b = Var(), Var()
    sols_str = _collect(
        "functor", 3, "abc", F1b, A1b,
        snap=lambda F=F1b, A=A1b: (deref(F), deref(A)),
    )
    F2, A2 = Var(), Var()
    sols_lst = _collect(
        "functor", 3, [mint("a"), mint("b"), mint("c")], F2, A2,
        snap=lambda F=F2, A=A2: (deref(F), deref(A)),
    )
    assert sols_atom == [(mint("abc"), 0)], (
        f'functor(("abc",), F, A) returned {sols_atom!r}; expected '
        f'[(("abc",), 0)] -- an atom is its own functor at arity 0.'
    )
    assert sols_lst == [(mint("."), 2)], (
        f'functor(["a","b","c"], F, A) returned {sols_lst!r}; '
        f'expected [(".", 2)] under ISO cons-cell.'
    )
    assert sols_str == sols_lst, (
        f"a STRING and its char-atom LIST are one term, so functor/3 must "
        f"AGREE. Got str={sols_str!r}, list={sols_lst!r}."
    )
    assert sols_atom != sols_lst, (
        f"the ATOM diverges from the list. Got atom={sols_atom!r}, "
        f"list={sols_lst!r}."
    )

    # Empty cases — nil atom on both shapes (unaffected: the empty str
    # is the one str value that legitimately reads as the list-shaped
    # nil atom).
    F3, A3 = Var(), Var()
    sols_empty_str = _collect(
        "functor", 3, "", F3, A3,
        snap=lambda F=F3, A=A3: (deref(F), deref(A)),
    )
    F4, A4 = Var(), Var()
    sols_empty_lst = _collect(
        "functor", 3, [], F4, A4,
        snap=lambda F=F4, A=A4: (deref(F), deref(A)),
    )
    assert sols_empty_str == [(mint("[]"), 0)], (
        f'functor("", F, A) returned {sols_empty_str!r}; expected '
        f'[("[]", 0)] — the nil atom.'
    )
    assert sols_empty_lst == [(mint("[]"), 0)], (
        f'functor([], F, A) returned {sols_empty_lst!r}; expected '
        f'[("[]", 0)] — the nil atom.'
    )


def test_F090_arg_on_str_is_retired_str_is_atomic():
    """P3-1 Task 5 (\u00a71b/R2): ``arg(N, "abc", X)`` no longer follows
    ISO cons-cell symmetry -- a str is atomic (arity 0), so EVERY index
    fails, including n=1 and n=2 (formerly asserted to bind the head
    char / tail substring under the retired cons rule).
    """
    # n=1 → no longer the head; str is atomic (arity 0), so this fails.
    X = Var()
    sols = _collect("arg", 3, 1, mint("abc"), X, snap=lambda X=X: deref(X))
    assert sols == [], (
        f'arg(1, "abc", X) bound X={sols!r}; expected [] -- a str is '
        f'atomic under the retired cons rule (\u00a71b/R2), so it has '
        f'no arguments.'
    )
    # n=2 → likewise no longer the tail.
    X = Var()
    sols = _collect("arg", 3, 2, mint("abc"), X, snap=lambda X=X: deref(X))
    assert sols == [], (
        f'arg(2, "abc", X) bound X={sols!r}; expected [] -- same '
        f'rationale as n=1.'
    )
    # n=3 → still fails (was already out of range; still is).
    X = Var()
    sols = _collect("arg", 3, 3, mint("abc"), X, snap=lambda X=X: deref(X))
    assert sols == [], (
        f'arg(3, "abc", X) bound X={sols!r}; expected [] '
        f"(str is arity 0, unchanged conclusion)."
    )


def test_F091_arg_on_list_uses_cons_cell():
    """``arg/3`` on a non-empty list follows ISO cons-cell head/tail.

    User decision 2026-06-13: ``arg(1, [a,b,c], X)`` binds ``X = a``
    (head); ``arg(2, [a,b,c], X)`` binds ``X = [b,c]`` (tail);
    ``arg(3, [a,b,c], _)`` fails (arity is 2).
    """
    # n=1 → head.
    X = Var()
    sols = _collect(
        "arg", 3, 1, [mint("a"), mint("b"), mint("c")], X, snap=lambda X=X: deref(X)
    )
    assert sols == [mint("a")], (
        f'arg(1, ["a","b","c"], X) bound X={sols!r}; expected ["a"].'
    )
    # n=2 → tail (list of rest).
    X = Var()
    sols = _collect(
        "arg", 3, 2, [mint("a"), mint("b"), mint("c")], X, snap=lambda X=X: deref(X)
    )
    assert sols == [[mint("b"), mint("c")]], (
        f'arg(2, ["a","b","c"], X) bound X={sols!r}; expected '
        f'[["b", "c"]] — cons-cell tail.'
    )
    # n=3 → fail (arity is 2).
    X = Var()
    sols = _collect(
        "arg", 3, 3, [mint("a"), mint("b"), mint("c")], X, snap=lambda X=X: deref(X)
    )
    assert sols == [], (
        f'arg(3, ["a","b","c"], X) bound X={sols!r}; expected [] '
        f"(cons-cell arity is 2)."
    )


def test_F092_copy_term_aliases_segstring_binding_propagates():
    """``copy_term(SegString([..., VarSeg(V)]), X)`` must produce a
    FRESH container whose inner ``VarSeg`` references a FRESH ``Var``.

    Today the copy IS the original (``copy is original``) — neither
    the Python fallback (inspection.py:21-47) nor the C twin
    (_variables.c:2403-2579) has a Seg* branch; both reach the final
    ``return term``. The Vars inside the "copy" are aliased to the
    Vars inside the source. ``copy_term`` is the spine of clause
    renaming during resolution, so any clause containing a Seg* term
    breaks the per-call fresh-Var guarantee.

    This test demonstrates the aliasing by binding the original's Var
    AFTER the copy and asserting the copy's Var is still unbound — a
    real copy would be independent.
    """
    V = Var()
    ss = SegString(["x", VarSeg(V)])

    # Take a copy via copy_term/2.
    X = Var()
    sols = _collect(
        "copy_term", 2, ss, X, snap=lambda X=X: deref(X)
    )
    assert len(sols) == 1, (
        f"copy_term(SegString, X) should yield exactly one solution; "
        f"got {sols!r}"
    )
    copy = sols[0]

    # Bind the ORIGINAL's Var. If copy_term produced a true independent
    # copy, the copy's VarSeg.var (a fresh Var) would still be unbound.
    from clausal.logic.variables import unify

    t = Trail()
    bound = unify(V, "Z", t)
    assert bound is True, (
        f"setup: binding the original's Var V to 'Z' should succeed; "
        f"got {bound!r}"
    )

    # The copy's inner VarSeg.var is supposed to be a fresh Var, so
    # dereffing it should still be unbound (a Var). Today it derefs to
    # the binding "Z" because the inner Var is the SAME object as V.
    copy_inner = copy.segments[1].var
    copy_inner_val = deref(copy_inner)
    assert isinstance(copy_inner_val, Var), (
        f"copy_term(SegString([..., VarSeg(V)])) produced a copy whose "
        f"inner VarSeg.var derefs to {copy_inner_val!r} after binding "
        f"the ORIGINAL's V — expected the copy to be independent, so "
        f"its inner Var should still be unbound. Today the 'copy' is "
        f"the same object as the original (copy is original: "
        f"{copy is ss}) and the inner Var is shared, so binding the "
        f"original propagates to the copy. This breaks per-call "
        f"fresh-Var renaming for any clause containing a Seg* term. "
        f"Fix: add Seg* branches to inspection.py:21-47 and "
        f"_variables.c:2403-2579 that allocate fresh Seg* with fresh "
        f"Vars via var_map."
    )


def test_F093_term_variables_blind_to_segstring_varseg():
    """``term_variables(SegString([..., VarSeg(V)]), Vs)`` should bind
    ``Vs`` to a list containing ``V`` (and similarly for SegList).

    The walker (Python fallback inspection.py:50-79 / C twin
    _collect_vars_impl) treats Seg* containers as leaves — Seg* is not
    registered with ``_register_term_types`` and the Python branch has
    no isinstance arm for it. Both fall through to "no Vars found".

    Same root cause as F083 (ground/1 blind) and F092 (copy_term
    blind) — single fix registers Seg* with the walker.
    """
    V = Var()
    ss = SegString(["x", VarSeg(V)])
    Vs = Var()
    sols = _collect(
        "term_variables", 2, ss, Vs, snap=lambda Vs=Vs: deref(Vs)
    )
    assert len(sols) == 1, (
        f"term_variables/2 should yield one solution; got {sols!r}"
    )
    found = sols[0]
    assert any(v is V for v in found), (
        f"term_variables(SegString(['x', VarSeg(V)]), Vs) bound "
        f"Vs={found!r}; expected the list to contain V (the unbound "
        f"Var inside the VarSeg). Today the walker (inspection.py:"
        f"50-79 / _collect_vars_impl) has no Seg* branch and treats "
        f"the container as a leaf — Vs comes back empty. Same blind "
        f"spot as F083 (ground) and F092 (copy_term)."
    )


def test_F094_numbervars_misses_varsegs_in_segstring():
    """``numbervars(SegString([..., VarSeg(V)]), 0, End)`` should
    advance ``End`` to ``1`` and bind ``V`` to ``$VAR(0)``.

    ``numbervars`` walks ``_collect_vars_impl`` (the same blind walker
    behind F093), finds no Vars inside Seg* containers, and silently
    returns ``End = 0`` with ``V`` unbound. Downstream pretty-printers
    that depend on ``numbervars`` having reached every variable emit
    a fresh ``_42``-style name instead of the canonical ``$VAR(N)``
    form, breaking "textually-identical clauses print identically".
    """
    V = Var()
    ss = SegString(["x", VarSeg(V)])
    End = Var()
    sols = _collect(
        "numbervars", 3, ss, 0, End,
        snap=lambda End=End: deref(End),
    )
    assert len(sols) == 1, (
        f"numbervars/3 should yield one solution; got {sols!r}"
    )
    end_val = sols[0]
    assert end_val == 1, (
        f"numbervars(SegString(['x', VarSeg(V)]), 0, End) bound "
        f"End={end_val!r}; expected End=1 (one Var numbered). Today "
        f"the walker is Seg*-blind (inspection.py:224-253 drives "
        f"_collect_vars_impl which has no Seg* branch) — End comes "
        f"back as 0 and V is left unbound. Same root cause as F093."
    )
