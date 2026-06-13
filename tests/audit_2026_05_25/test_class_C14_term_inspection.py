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
    """``unpack(["a","b","c"], L)`` follows ISO cons-cell decomposition.

    User decision 2026-06-13: ISO-named inspection predicates follow
    ISO Prolog semantics. ``=..`` on a non-empty list returns the
    cons-cell shape ``[".", head, tail]`` where ``tail`` is the rest
    of the list. Liskov-symmetric on str inputs (tail is a substring).
    """
    L = Var()
    sols = _collect(
        "unpack", 2, ["a", "b", "c"], L, snap=lambda L=L: deref(L)
    )
    assert sols == [[".", "a", ["b", "c"]]], (
        f'unpack(["a","b","c"], L) bound L={sols!r}; expected '
        f'[".", "a", ["b","c"]] under ISO cons-cell.'
    )

    # Liskov symmetry on str input.
    L2 = Var()
    sols2 = _collect(
        "unpack", 2, "abc", L2, snap=lambda L=L2: deref(L)
    )
    assert sols2 == [[".", "a", "bc"]], (
        f'unpack("abc", L) bound L={sols2!r}; expected '
        f'[".", "a", "bc"] — str preserves str type on both head '
        f'(1-char str) and tail (substring).'
    )

    # Empty cases — nil atom.
    L3 = Var()
    sols3 = _collect("unpack", 2, [], L3, snap=lambda L=L3: deref(L))
    assert sols3 == [["[]"]], (
        f'unpack([], L) bound L={sols3!r}; expected ["[]"].'
    )
    L4 = Var()
    sols4 = _collect("unpack", 2, "", L4, snap=lambda L=L4: deref(L))
    assert sols4 == [["[]"]], (
        f'unpack("", L) bound L={sols4!r}; expected ["[]"].'
    )


def test_F089_functor_and_univ_agree_on_str_vs_list():
    """``functor/3`` and ``unpack/2`` (=..) produce Liskov-symmetric
    shapes for str and list inputs under the strings-as-lists contract.

    User decision 2026-06-13: ISO cons-cell across both. The cons-cell
    answer is the same modulo str-vs-list type on head/tail.
    """
    F1, A1 = Var(), Var()
    sols_str = _collect(
        "functor", 3, "abc", F1, A1,
        snap=lambda F=F1, A=A1: (deref(F), deref(A)),
    )
    F2, A2 = Var(), Var()
    sols_lst = _collect(
        "functor", 3, ["a", "b", "c"], F2, A2,
        snap=lambda F=F2, A=A2: (deref(F), deref(A)),
    )
    assert sols_str == [(".", 2)], (
        f'functor("abc", F, A) returned {sols_str!r}; expected '
        f'[(".", 2)] under ISO cons-cell.'
    )
    assert sols_lst == [(".", 2)], (
        f'functor(["a","b","c"], F, A) returned {sols_lst!r}; '
        f'expected [(".", 2)] under ISO cons-cell.'
    )
    assert sols_str == sols_lst, (
        f"functor/3 must give the same (Name, Arity) for str and "
        f"equivalent list inputs under Liskov-symmetric "
        f"strings-as-lists. Got str={sols_str!r}, list={sols_lst!r}."
    )

    # Empty cases — nil atom on both shapes.
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
    assert sols_empty_str == [("[]", 0)], (
        f'functor("", F, A) returned {sols_empty_str!r}; expected '
        f'[("[]", 0)] — the nil atom.'
    )
    assert sols_empty_lst == [("[]", 0)], (
        f'functor([], F, A) returned {sols_empty_lst!r}; expected '
        f'[("[]", 0)] — the nil atom.'
    )


def test_F090_arg_on_str_uses_cons_cell():
    """``arg(N, "abc", X)`` follows ISO cons-cell symmetry on str input.

    User decision 2026-06-13: strings-as-lists Liskov symmetry — str
    decomposes as cons-cell with str-typed head (1-char str) and tail
    (substring).
    """
    # n=1 → head (1-char str).
    X = Var()
    sols = _collect("arg", 3, 1, "abc", X, snap=lambda X=X: deref(X))
    assert sols == ["a"], (
        f'arg(1, "abc", X) bound X={sols!r}; expected ["a"].'
    )
    # n=2 → tail (substring).
    X = Var()
    sols = _collect("arg", 3, 2, "abc", X, snap=lambda X=X: deref(X))
    assert sols == ["bc"], (
        f'arg(2, "abc", X) bound X={sols!r}; expected ["bc"] — '
        f"cons-cell tail preserves str type."
    )
    # n=3 → fail (arity is 2).
    X = Var()
    sols = _collect("arg", 3, 3, "abc", X, snap=lambda X=X: deref(X))
    assert sols == [], (
        f'arg(3, "abc", X) bound X={sols!r}; expected [] '
        f"(cons-cell arity is 2)."
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
        "arg", 3, 1, ["a", "b", "c"], X, snap=lambda X=X: deref(X)
    )
    assert sols == ["a"], (
        f'arg(1, ["a","b","c"], X) bound X={sols!r}; expected ["a"].'
    )
    # n=2 → tail (list of rest).
    X = Var()
    sols = _collect(
        "arg", 3, 2, ["a", "b", "c"], X, snap=lambda X=X: deref(X)
    )
    assert sols == [["b", "c"]], (
        f'arg(2, ["a","b","c"], X) bound X={sols!r}; expected '
        f'[["b", "c"]] — cons-cell tail.'
    )
    # n=3 → fail (arity is 2).
    X = Var()
    sols = _collect(
        "arg", 3, 3, ["a", "b", "c"], X, snap=lambda X=X: deref(X)
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
