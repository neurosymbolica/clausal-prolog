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

from clausal.logic.database import Module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
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
        # nv
        name, arity = Var(), Var()
        result = _call_binding("functor", Compound("f", ("a", "b")), name, arity)
        assert result is not None
        assert result == ("f", 2)

    def test_decompose_str_cons_cell(self):
        """ISO cons-cell on str: functor("a", F, A) → F = '.', A = 2.

        F089 (audit 2026-06-13): user decision — ISO-named inspection
        predicates follow ISO cons-cell semantics; str ↔ list Liskov
        symmetry applies. A non-empty str decomposes as a cons-cell
        with head and tail args.
        """
        # nv
        name, arity = Var(), Var()
        result = _call_binding("functor", "a", name, arity)
        assert result is not None
        assert result == (".", 2)

    def test_decompose_arity1(self):
        """functor(f(x), Name, Arity) → Name = f, Arity = 1."""
        # nv
        name, arity = Var(), Var()
        result = _call_binding("functor", Compound("f", ("x",)), name, arity)
        assert result is not None
        assert result == ("f", 1)

    def test_construct_compound(self):
        """ISO: functor(T, f, 2) → T = f(_, _) (fresh vars)."""
        # nv
        t = Var()
        result = _call_binding("functor", t, "f", 2, var_indices=[0])
        assert result is not None
        term = result[0]
        assert isinstance(term, Compound)
        assert term.functor == "f"
        assert len(term.args) == 2

    def test_construct_atom(self):
        """ISO: functor(T, a, 0) → T = a."""
        # nv
        t = Var()
        result = _call_binding("functor", t, "a", 0, var_indices=[0])
        assert result is not None
        assert result[0] == "a"

    # Numeric-literal decomposition migrated to iso_term_manipulation.clausal.

    def test_decompose_large_compound(self):
        """functor(f(a,b,c,d,e), Name, Arity) → Name=f, Arity=5."""
        # nv
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
        # nv
        x = Var()
        result = _call_binding("arg", 1, Compound("f", ("a", "b", "c")), x)
        assert result is not None
        assert result[0] == "a"

    def test_second_arg(self):
        """ISO: arg(2, f(a,b,c), X) → X = b."""
        # nv
        x = Var()
        result = _call_binding("arg", 2, Compound("f", ("a", "b", "c")), x)
        assert result is not None
        assert result[0] == "b"

    def test_third_arg(self):
        # nv
        x = Var()
        result = _call_binding("arg", 3, Compound("f", ("a", "b", "c")), x)
        assert result is not None
        assert result[0] == "c"

    def test_out_of_range(self):
        """ISO: arg(4, f(a,b,c), X) fails."""
        # nv
        x = Var()
        result = _call_binding("arg", 4, Compound("f", ("a", "b", "c")), x)
        assert result is None

    def test_zero_fails(self):
        """ISO: arg(0, f(a), X) fails."""
        # nv
        x = Var()
        result = _call_binding("arg", 0, Compound("f", ("a",)), x)
        assert result is None

    def test_negative_fails(self):
        # nv
        x = Var()
        result = _call_binding("arg", -1, Compound("f", ("a",)), x)
        assert result is None

    def test_nested_compound(self):
        """arg(1, f(g(x)), A) → A = g(x)."""
        # nv
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
        # nv
        x = Var()
        result = _call_binding("unpack", Compound("f", ("a", "b")), x)
        assert result is not None
        assert result[0] == ["f", "a", "b"]

    def test_decompose_str_cons_cell(self):
        """ISO cons-cell on str: "a" =.. X → X = ['.', 'a', ''].

        F088/F089/F090 (audit 2026-06-13): under ISO cons-cell, a
        non-empty str decomposes as the cons-cell `[".", head, tail]`
        where head is the 1-char str and tail is the substring rest.
        """
        # nv
        x = Var()
        result = _call_binding("unpack", "a", x)
        assert result is not None
        assert result[0] == [".", "a", ""]

    def test_decompose_arity1(self):
        """f(x) =.. L → L = [f, x]."""
        # nv
        lst = Var()
        result = _call_binding("unpack", Compound("f", ("x",)), lst)
        assert result is not None
        assert result[0] == ["f", "x"]

    def test_construct_from_list(self):
        """ISO: T =.. [f, a, b] → T = f(a, b)."""
        # nv
        t = Var()
        result = _call_binding("unpack", t, ["f", "a", "b"], var_indices=[0])
        assert result is not None
        term = result[0]
        assert isinstance(term, Compound)
        assert term.functor == "f"
        assert term.args == ("a", "b")

    def test_construct_atom_from_list(self):
        """ISO: T =.. [a] → T = a."""
        # nv
        t = Var()
        result = _call_binding("unpack", t, ["a"], var_indices=[0])
        assert result is not None
        assert result[0] == "a"

    # Numeric-literal decomposition migrated to iso_term_manipulation.clausal.
