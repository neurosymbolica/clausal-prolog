"""C14 — Term inspection drift.

7 findings (4 bug + 3 design-gap). The inspection predicates
(functor/3, arg/3, =../2, copy_term/2, term_variables/2) disagree
about what the "args" of a list are, fail to copy Seg* containers
correctly, and don't see VarSegs as variables. F092 (copy_term
aliasing) is the most serious — it's a correctness landmine for any
future code that puts Seg* in clauses. F092 and F093 have lock-in
tests in tests/test_term_inspection.py.

Findings tested here:
- F088 (bug) unpack (=..) on a non-empty list yields ["."] with no args
- F089 (design-gap) functor/3 and =.. give different shapes for str vs list
- F090 (bug) arg(N, "abc", X) silently fails for every N
- F091 (bug) arg/3 on non-empty list uses Python-list indexing, not cons-cell
- F092 (bug) copy_term aliases Seg* containers
- F093 (design-gap) term_variables Seg*-blind
- F094 (design-gap) numbervars/3 cannot number Vars inside Seg* containers
"""

import pytest

from clausal.logic.builtins import get_builtin_dispatch
from clausal.logic.trampoline import StepGenerator, solutions
from clausal.logic.variables import Trail, Var, deref
from clausal.terms import Compound, SegList, SegString, VarSeg


def _collect(name, arity, *args, snap):
    """Run a builtin and snapshot the result for each solution."""
    disp = get_builtin_dispatch(name, arity, None)
    return solutions(
        StepGenerator(disp, None, None, None, *args, Trail()),
        snapshot=snap,
    )


@pytest.mark.xfail(
    strict=True,
    reason='ledger F088: unpack (=..) on a non-empty list yields ["."] with no args',
)
def test_F088_unpack_on_list_drops_args():
    """``unpack(["a","b","c"], L)`` should not bind ``L`` to ``["."]`` only.

    The implementation calls ``_functor_name`` (returns ``"."`` for any
    Python list) and concatenates with ``_args_list``, but ``_args_list``
    has no isinstance branch for ``list`` — it falls through to ``[]``
    in both the Python fallback (_helpers.py:75-83) and the C twin
    (_variables.c:2362-2363). Result: ``L = ["."]`` — functor name only,
    args dropped. ``functor/3`` on the same input reports arity 2, so
    the inspection family is internally inconsistent. The expected
    behaviour is either cons-cell decomposition
    (``[".", "a", ["b", "c"]]``) or strings-as-lists element-shape
    (``["a", "b", "c"]``) — either is defensible; ``["."]`` is neither.
    """
    L = Var()
    sols = _collect(
        "unpack", 2, ["a", "b", "c"], L, snap=lambda L=L: deref(L)
    )
    assert sols and sols[0] != ["."], (
        f"unpack(['a','b','c'], L) bound L={sols!r}; expected either "
        f'cons-cell decomposition (e.g. [".", "a", ["b", "c"]]) or '
        f"strings-as-lists shape (['a', 'b', 'c']) — got the functor "
        f"name with no args, which contradicts functor/3 reporting "
        f"arity 2 for the same input. See _helpers.py:75-83 and "
        f"_variables.c:2362-2363 (missing isinstance(term, list) branch)."
    )


@pytest.mark.xfail(
    strict=True,
    reason="ledger F089: functor/3 and =.. give different shapes for str vs list",
)
def test_F089_functor_and_univ_disagree_on_str_vs_list():
    """``functor/3`` and ``unpack/2`` (=..) should produce compatible
    shapes for str and list inputs under the strings-as-lists contract.

    Today ``"abc"`` decomposes as atom-univ (``("abc", 0)`` /
    ``["abc"]``) while ``["a","b","c"]`` decomposes as a cons-cell
    (``(".", 2)`` / ``["."]`` per F088). The two equivalent
    representations land in two unrelated worlds. The audit anchor for
    C14 — the bug cluster F088/F090/F091 is independent of which
    contract is chosen, but choosing one is what closes F089.
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
    assert sols_str == sols_lst, (
        f'functor/3 of "abc" returned {sols_str!r} but functor/3 of '
        f"['a','b','c'] returned {sols_lst!r}; under strings-as-lists "
        f"these inputs are interchangeable and must decompose to the "
        f"same (Name, Arity) shape. Today: str → atom-univ ('abc', 0); "
        f"list → cons-cell ('.', 2). C14 anchor finding."
    )


@pytest.mark.xfail(
    strict=True,
    reason='ledger F090: arg(N, "abc", X) silently fails for every N',
)
def test_F090_arg_on_str_silently_fails():
    """``arg(1, "abc", X)`` should not silently fail.

    ``_nth_arg`` raises ``IndexError`` on any str (no isinstance branch);
    ``_arg__3`` catches and ``return``s. Caller sees clean failure rather
    than ``type_error(compound, "abc")``. Asymmetric with
    ``arg(1, ["a","b","c"], X)`` which binds ``X = "a"`` — the two
    equivalent inputs disagree, and the error path is silent (ISO
    ``arg/3`` is a type-error predicate, not a failure predicate).
    """
    X = Var()
    sols = _collect(
        "arg", 3, 1, "abc", X, snap=lambda X=X: deref(X)
    )
    # Expected: under strings-as-lists, X="a". Under strict ISO, a
    # type_error would have raised before solutions ran. Either way,
    # silent zero-solutions is wrong.
    assert sols, (
        f'arg(1, "abc", X) yielded {sols!r}; expected one solution '
        f"binding X='a' under strings-as-lists, OR a "
        f'type_error(compound, "abc") under strict ISO. Silent failure '
        f"is incorrect either way. _nth_arg raises IndexError on str "
        f"(no isinstance branch) and _arg__3 swallows it at "
        f"inspection.py:151-152."
    )


@pytest.mark.xfail(
    strict=True,
    reason="ledger F091: arg/3 on non-empty list uses Python-list indexing, not cons-cell",
)
def test_F091_arg_on_list_uses_python_indexing_not_cons_cell():
    """``arg/3`` on a non-empty list should not use Python-list indexing
    while ``functor/3`` reports cons-cell arity 2.

    Today ``arg(3, ["a","b","c"], X)`` binds ``X = "c"`` — but
    ``functor(["a","b","c"], F, A)`` reports ``A = 2``, so an
    ISO-conformant ``arg/3`` would fail for N > 2. The list branch in
    ``_nth_arg`` (``_helpers.py:70-71``) returns ``term[n-1]`` for any
    ``N ≤ len(term)``, ignoring the cons-cell arity that ``functor``
    advertises. Either both should use cons-cell semantics
    (``arg(1)`` = head, ``arg(2)`` = tail, ``arg(3)`` raises) or both
    should use Python-list indexing (``functor`` reports arity
    ``len(list)``).
    """
    # The mismatch: arg(3, [a,b,c], X) succeeds with "c" even though
    # functor/3 reports arity 2 for the same term. Under any consistent
    # cons-cell contract, arg(3, ...) should fail (or raise).
    X = Var()
    sols = _collect(
        "arg", 3, 3, ["a", "b", "c"], X, snap=lambda X=X: deref(X)
    )
    assert sols == [], (
        f"arg(3, ['a','b','c'], X) yielded {sols!r}; expected [] "
        f"because functor/3 reports arity 2 for the same list "
        f"(cons-cell view). Today _nth_arg uses Python-list indexing "
        f"(_helpers.py:70-71) and silently returns term[2]='c', "
        f"contradicting functor/3."
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
