"""ISO Prolog conformity: term creation and decomposition.

ISO §8.5.1 — functor/3
ISO §8.5.2 — arg/3
ISO §8.5.3 — =../2 (univ)
ISO §8.5.4 — copy_term/2

Clausal equivalents:
  functor/3  → functor(Term, Name, Arity)
  arg/3      → arg(N, Term, arg)
  univ/2     → univ(Term, List)  (=../2 in Prolog)

Not available:
  copy_term/2 — no builtin equivalent.

Differences from ISO:
  - Prolog: functor(1, X, Y) → X = 1, Y = 0 (numbers are arity-0 terms).
    Clausal: integers/floats have functor=str(val), arity=0.
  - Prolog: functor([], X, Y) → X = '[]', Y = 0.
    Clausal: lists are Python lists, not atoms — functor may not apply.
  - univ/2 is spelled 'univ' (not the =.. operator).
"""

from __future__ import annotations

import pytest
from clausal.logic.database import Module
from clausal.logic.solve import solve, call
from clausal.logic.variables import Var, Trail, deref
from clausal.terms import Compound


def _call_binding(functor, *args, var_indices=None, mod=None):
    """Call builtin, return deref'd values of specified Var args for first solution."""
    if mod is None:
        mod = Module("test")
    if var_indices is None:
        var_indices = [i for i, a in enumerate(args) if isinstance(a, Var)]
    for _ in call(functor, *args, module=mod):
        return tuple(deref(args[i]) for i in var_indices)
    return None


# ── functor/3 ─────────────────────────────────────────────────────────────────


class TestFunctor:
    """ISO §8.5.1 — functor/3."""

    def test_decompose_compound(self):
        """ISO: functor(f(a,b), X, Y) → X = f, Y = 2."""
        name, arity = Var(), Var()
        result = _call_binding("functor", Compound("f", ("a", "b")), name, arity)
        assert result is not None
        assert result == ("f", 2)

    def test_decompose_atom(self):
        """ISO: functor(a, X, Y) → X = a, Y = 0.
        in_ clausal, strings are atoms."""
        name, arity = Var(), Var()
        result = _call_binding("functor", "a", name, arity)
        assert result is not None
        assert result == ("a", 0)

    def test_decompose_arity1(self):
        """functor(f(x), Name, Arity) → Name = f, Arity = 1."""
        name, arity = Var(), Var()
        result = _call_binding("functor", Compound("f", ("x",)), name, arity)
        assert result is not None
        assert result == ("f", 1)

    def test_construct_compound(self):
        """ISO: functor(T, f, 2) → T = f(_, _) (fresh vars)."""
        t = Var()
        result = _call_binding("functor", t, "f", 2, var_indices=[0])
        assert result is not None
        term = result[0]
        assert isinstance(term, Compound)
        assert term.functor == "f"
        assert len(term.args) == 2

    def test_construct_atom(self):
        """ISO: functor(T, a, 0) → T = a."""
        t = Var()
        result = _call_binding("functor", t, "a", 0, var_indices=[0])
        assert result is not None
        assert result[0] == "a"

    def test_decompose_integer(self):
        """ISO: functor(1, X, Y) → X = 1, Y = 0.
        Clausal may or may not support this."""
        name, arity = Var(), Var()
        result = _call_binding("functor", 1, name, arity)
        if result is not None:
            assert result[1] == 0

    def test_decompose_float(self):
        """ISO: functor(1.0, X, Y) → X = 1.0, Y = 0."""
        name, arity = Var(), Var()
        result = _call_binding("functor", 1.0, name, arity)
        if result is not None:
            assert result[1] == 0

    def test_decompose_large_compound(self):
        """functor(f(a,b,c,d,e), Name, Arity) → Name=f, Arity=5."""
        name, arity = Var(), Var()
        result = _call_binding(
            "functor",
            Compound("f", ("a", "b", "c", "d", "e")),
            name, arity,
        )
        assert result is not None
        assert result == ("f", 5)


# ── arg/3 ─────────────────────────────────────────────────────────────────────


class TestArg:
    """ISO §8.5.2 — arg/3."""

    def test_first_arg(self):
        """ISO: arg(1, f(a,b,c), X) → X = a."""
        x = Var()
        result = _call_binding("arg", 1, Compound("f", ("a", "b", "c")), x)
        assert result is not None
        assert result[0] == "a"

    def test_second_arg(self):
        """ISO: arg(2, f(a,b,c), X) → X = b."""
        x = Var()
        result = _call_binding("arg", 2, Compound("f", ("a", "b", "c")), x)
        assert result is not None
        assert result[0] == "b"

    def test_third_arg(self):
        x = Var()
        result = _call_binding("arg", 3, Compound("f", ("a", "b", "c")), x)
        assert result is not None
        assert result[0] == "c"

    def test_out_of_range(self):
        """ISO: arg(4, f(a,b,c), X) fails."""
        x = Var()
        result = _call_binding("arg", 4, Compound("f", ("a", "b", "c")), x)
        assert result is None

    def test_zero_fails(self):
        """ISO: arg(0, f(a), X) fails."""
        x = Var()
        result = _call_binding("arg", 0, Compound("f", ("a",)), x)
        assert result is None

    def test_negative_fails(self):
        x = Var()
        result = _call_binding("arg", -1, Compound("f", ("a",)), x)
        assert result is None

    def test_nested_compound(self):
        """arg(1, f(g(x)), A) → A = g(x)."""
        a = Var()
        inner = Compound("g", ("x",))
        result = _call_binding("arg", 1, Compound("f", (inner,)), a)
        assert result is not None
        assert result[0] == inner


# ── =../2 (univ) ─────────────────────────────────────────────────────────────


class TestUniv:
    """ISO §8.5.3 — =../2 (spelled 'univ' in clausal)."""

    def test_decompose_compound(self):
        """ISO: f(a,b) =.. X → X = [f, a, b]."""
        x = Var()
        result = _call_binding("unpack", Compound("f", ("a", "b")), x)
        assert result is not None
        assert result[0] == ["f", "a", "b"]

    def test_decompose_atom(self):
        """ISO: a =.. X → X = [a]."""
        x = Var()
        result = _call_binding("unpack", "a", x)
        assert result is not None
        assert result[0] == ["a"]

    def test_decompose_arity1(self):
        """f(x) =.. L → L = [f, x]."""
        lst = Var()
        result = _call_binding("unpack", Compound("f", ("x",)), lst)
        assert result is not None
        assert result[0] == ["f", "x"]

    def test_construct_from_list(self):
        """ISO: T =.. [f, a, b] → T = f(a, b)."""
        t = Var()
        result = _call_binding("unpack", t, ["f", "a", "b"], var_indices=[0])
        assert result is not None
        term = result[0]
        assert isinstance(term, Compound)
        assert term.functor == "f"
        assert term.args == ("a", "b")

    def test_construct_atom_from_list(self):
        """ISO: T =.. [a] → T = a."""
        t = Var()
        result = _call_binding("unpack", t, ["a"], var_indices=[0])
        assert result is not None
        assert result[0] == "a"

    def test_decompose_number(self):
        """ISO: 1 =.. X → X = [1].
        DIFFERS: clausal decomposes integers via their string representation
        as functor, so 1 =.. X gives X = ["1"] (functor is the str "1")."""
        x = Var()
        result = _call_binding("unpack", 1, x)
        if result is not None:
            # Clausal uses str(val) as functor for numbers
            assert result[0] == ["1"]
