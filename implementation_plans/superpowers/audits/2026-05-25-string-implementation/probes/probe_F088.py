"""Probe F088 — term inspection (functor/3, arg/3, =..|unpack/2,
copy_term/2, term_variables/2, numbervars/3) over the str / list / Seg*
row-set.

Drives every inspection predicate in
``clausal/logic/builtins/inspection.py`` against the audit row-set and
pins down the contracts that disagree between str-shaped and list-shaped
inputs (and between the inspection predicates themselves).

Source for findings F088–F094:
  - F088  ``unpack`` (=..) on a non-empty list yields ``["."]`` — the
          functor name with NO args.  Contradicts ``functor/3`` reporting
          arity 2 for the same list, and breaks ``=..``'s standard
          round-trip property.
  - F089  ``functor/3`` and ``unpack/2`` give different shapes for str
          (atom-univ, ``["abc"]`` arity 0) and list (cons-cell, ``"."``
          arity 2).  Inputs that are equivalent under strings-as-lists
          decompose to two different worlds.
  - F090  ``arg(N, "abc", X)`` silently fails for every N — the
          ``_nth_arg`` helper raises ``IndexError`` for any str, which
          ``_arg__3`` swallows.  Asymmetric vs ``arg(N, ["a","b","c"], X)``
          which binds the N-th element.
  - F091  ``arg/3`` on a non-empty list returns the N-th *element* (not
          cons-cell head/tail) — directly inconsistent with ``functor/3``
          reporting arity 2.  Either both inspect Python-list indexing
          (and ``functor`` is wrong) or both inspect cons-cells (and
          ``arg`` is wrong); right now they disagree.
  - F092  ``copy_term/2`` does not recurse into ``SegList`` / ``SegString``
          — the result *is the same object* (``copy is original``), so
          inner VarSegs are still bound to the same Vars as the source.
          Aliasing bug under backtracking.
  - F093  ``term_variables/2`` does not see Vars inside ``VarSeg``s of
          ``Seg*`` containers — sibling of the C3 Seg*-blind cluster
          ([[F083]] for ``ground/1``).
  - F094  ``numbervars/3`` walks the same blind ``_collect_vars_impl``
          helper, so it can't number Vars buried inside ``Seg*``
          containers either.  Cross-listed with F093.
"""
from __future__ import annotations

from clausal.logic.builtins import get_builtin_dispatch
from clausal.logic.variables import Var, Trail, deref
from clausal.logic.trampoline import StepGenerator, solutions
from clausal.terms import Compound, SegList, SegString, VarSeg


def _collect(name, arity, *args, snap):
    disp = get_builtin_dispatch(name, arity, None)
    return solutions(StepGenerator(disp, None, None, None, *args, Trail()),
                     snapshot=snap)


def _row(label, value):
    return (label, value)


def main() -> None:
    print("Probe F088 — term inspection over str / list / Seg* row-set")
    print()

    # ── functor/3 over the row-set ──────────────────────────────────────
    print("functor(Term, Name, Arity):")
    rows = [
        _row('"abc"',                    "abc"),
        _row('["a","b","c"]',            ["a", "b", "c"]),
        _row('""',                       ""),
        _row('[]',                       []),
        _row('Compound("f",(1,2))',      Compound("f", (1, 2))),
        _row('42',                       42),
    ]
    for label, val in rows:
        F, A = Var(), Var()
        sols = _collect("functor", 3, val, F, A,
                        snap=lambda F=F, A=A: (deref(F), deref(A)))
        print(f"  {label:30s} -> {sols}")
    print()

    # F089 — str-vs-list shape disagreement under functor/3.
    F, A = Var(), Var()
    sols_str = _collect("functor", 3, "abc", F, A,
                        snap=lambda F=F, A=A: (deref(F), deref(A)))
    F, A = Var(), Var()
    sols_lst = _collect("functor", 3, ["a", "b", "c"], F, A,
                        snap=lambda F=F, A=A: (deref(F), deref(A)))
    assert sols_str == [("abc", 0)], sols_str
    assert sols_lst == [(".", 2)], sols_lst

    # ── arg/3 over the row-set ──────────────────────────────────────────
    print("arg(1, Term, X):")
    for label, val in rows:
        X = Var()
        sols = _collect("arg", 3, 1, val, X, snap=lambda X=X: deref(X))
        print(f"  {label:30s} -> {sols}")
    print()

    # F090 — arg(N, str, X) silently fails for every N.
    for N in (1, 2, 3, 4):
        X = Var()
        sols = _collect("arg", 3, N, "abc", X, snap=lambda X=X: deref(X))
        assert sols == [], (N, sols)

    # F091 — arg on a non-empty list returns Python-list-indexed N-th
    # element, not cons-cell head/tail.
    X = Var()
    sols = _collect("arg", 3, 1, ["a", "b", "c"], X, snap=lambda X=X: deref(X))
    assert sols == ["a"], sols
    X = Var()
    sols = _collect("arg", 3, 2, ["a", "b", "c"], X, snap=lambda X=X: deref(X))
    # If this were a real cons-cell decomposition, X would be ["b","c"].
    assert sols == ["b"], sols
    # arity is 2 per functor/3 — so arg/3 says 3 in a 2-arg term?
    X = Var()
    sols = _collect("arg", 3, 3, ["a", "b", "c"], X, snap=lambda X=X: deref(X))
    assert sols == ["c"], sols

    # ── unpack (=..) over the row-set ──────────────────────────────────
    print("unpack(Term, L):")
    for label, val in rows:
        L = Var()
        sols = _collect("unpack", 2, val, L, snap=lambda L=L: deref(L))
        print(f"  {label:30s} -> {sols}")
    print()

    # F088 — unpack on a non-empty list yields ["."] (no args).
    L = Var()
    sols = _collect("unpack", 2, ["a", "b", "c"], L, snap=lambda L=L: deref(L))
    assert sols == [["."]], (
        "expected unpack to either expose the cons-cell args "
        "(['.','a',['b','c']]) or honour strings-as-lists "
        "(['a','b','c'] / atom-univ); got %r" % (sols,)
    )

    # F088/F089 — round-trip is destructive for lists.
    L = Var()
    sols = _collect("unpack", 2, ["a", "b", "c"], L, snap=lambda L=L: deref(L))
    T = Var()
    rt = _collect("unpack", 2, T, sols[0], snap=lambda T=T: deref(T))
    # Round-trip drops every element — list ["a","b","c"] becomes atom ".".
    assert rt == ["."], rt

    # F089 — atom-univ round-trip on strings is non-destructive (sanity).
    L = Var()
    sols = _collect("unpack", 2, "abc", L, snap=lambda L=L: deref(L))
    assert sols == [["abc"]], sols
    T = Var()
    rt = _collect("unpack", 2, T, sols[0], snap=lambda T=T: deref(T))
    assert rt == ["abc"], rt

    # Sanity: Compound decomposes and reconstructs cleanly.
    L = Var()
    sols = _collect("unpack", 2, Compound("f", (1, 2)), L,
                    snap=lambda L=L: deref(L))
    assert sols == [["f", 1, 2]], sols
    T = Var()
    rt = _collect("unpack", 2, T, ["f", 1, 2], snap=lambda T=T: deref(T))
    assert rt == [Compound("f", (1, 2))], rt

    # ── copy_term/2 ─────────────────────────────────────────────────────
    print("copy_term(Term, X):")
    # Strings (immutable) — sharing is fine.
    s = "hello"
    X = Var()
    sols = _collect("copy_term", 2, s, X, snap=lambda X=X: deref(X) is s)
    assert sols == [True], sols
    print(f"  str shares identity (OK): {sols}")

    # Lists — properly deep-copied (NOT same object).
    lst = ["a", "b", Var()]
    X = Var()
    sols = _collect("copy_term", 2, lst, X, snap=lambda X=X: deref(X) is lst)
    assert sols == [False], sols
    print(f"  list is deep-copied (OK): {sols}")

    # F092 — SegString / SegList are NOT copied; result is original.
    V = Var()
    ss = SegString(["x", VarSeg(V)])
    X = Var()
    sols = _collect("copy_term", 2, ss, X, snap=lambda X=X: deref(X) is ss)
    assert sols == [True], (
        "expected copy_term(SegString) to return a fresh container "
        "with a fresh VarSeg; got the original object back: %r" % (sols,)
    )
    print(f"  SegString aliased (BUG): {sols}")

    V = Var()
    sl = SegList(["a", VarSeg(V)])
    X = Var()
    sols = _collect("copy_term", 2, sl, X, snap=lambda X=X: deref(X) is sl)
    assert sols == [True], sols
    print(f"  SegList aliased (BUG):   {sols}")

    # Confirm aliasing: bind through the "copy", original mutates too.
    # (We do this with a fresh SegString whose VarSeg holds a fresh Var
    # so the binding doesn't bleed across cases.)
    V = Var()
    ss = SegString(["x", VarSeg(V)])
    X = Var()
    sols = _collect("copy_term", 2, ss, X, snap=lambda X=X: deref(X))
    copy = sols[0]
    # The "copy" shares VarSeg(V) — its var IS V.
    assert copy is ss
    assert copy.segments[1].var is V

    # ── term_variables/2 ────────────────────────────────────────────────
    print()
    print("term_variables(Term, Vs):")
    # Baseline — Compound with a Var arg.
    V = Var()
    Vs = Var()
    sols = _collect("term_variables", 2, Compound("f", (V,)), Vs,
                    snap=lambda Vs=Vs: [v is V for v in deref(Vs)])
    assert sols == [[True]], sols
    print(f"  Compound((V,)) finds V (OK): {sols}")

    # F093 — Vars inside SegString/SegList VarSegs are invisible.
    V = Var()
    ss = SegString(["x", VarSeg(V)])
    Vs = Var()
    sols = _collect("term_variables", 2, ss, Vs, snap=lambda Vs=Vs: deref(Vs))
    assert sols == [[]], sols
    print(f"  SegString hides VarSeg.var (BUG): {sols}")

    V = Var()
    sl = SegList(["a", VarSeg(V)])
    Vs = Var()
    sols = _collect("term_variables", 2, sl, Vs, snap=lambda Vs=Vs: deref(Vs))
    assert sols == [[]], sols
    print(f"  SegList   hides VarSeg.var (BUG): {sols}")

    # str / list are properly ground per the walker.
    Vs = Var()
    sols = _collect("term_variables", 2, "abc", Vs, snap=lambda Vs=Vs: deref(Vs))
    assert sols == [[]], sols
    Vs = Var()
    sols = _collect("term_variables", 2, ["a", "b", "c"], Vs,
                    snap=lambda Vs=Vs: deref(Vs))
    assert sols == [[]], sols

    # ── numbervars/3 ────────────────────────────────────────────────────
    print()
    print("numbervars(Term, 0, End):")
    # Baseline — Compound with a Var arg gets numbered.
    V = Var()
    End = Var()
    sols = _collect("numbervars", 3, Compound("f", (V,)), 0, End,
                    snap=lambda End=End, V=V: (deref(End), deref(V)))
    # End == 1 means exactly 1 var was numbered; V is bound to $VAR(0).
    assert sols and sols[0][0] == 1, sols
    print(f"  Compound((V,)) -> End=1, V={sols[0][1]} (OK)")

    # F094 — SegString/SegList VarSegs are invisible to numbervars.
    V = Var()
    ss = SegString(["x", VarSeg(V)])
    End = Var()
    sols = _collect("numbervars", 3, ss, 0, End,
                    snap=lambda End=End, V=V: (deref(End), deref(V) is V))
    # End comes back as 0 (no vars numbered) and V is still unbound.
    assert sols == [(0, True)], sols
    print(f"  SegString    -> End=0, V still unbound (BUG): {sols}")

    V = Var()
    sl = SegList(["a", VarSeg(V)])
    End = Var()
    sols = _collect("numbervars", 3, sl, 0, End,
                    snap=lambda End=End, V=V: (deref(End), deref(V) is V))
    assert sols == [(0, True)], sols
    print(f"  SegList      -> End=0, V still unbound (BUG): {sols}")

    print()
    print("All matrix-row assertions passed (findings F088–F094 confirmed).")


if __name__ == "__main__":
    main()
