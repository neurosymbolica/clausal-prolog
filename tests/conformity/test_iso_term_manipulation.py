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

from clausal.logic.atoms import char_atom, mint
from clausal.logic.database import Module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


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
        result = _call_binding("functor", ("f", char_atom("a"), char_atom("b")), name, arity)
        assert result is not None
        assert result == (char_atom("f"), 2)

    def test_decompose_str_is_its_own_atom_functor(self):
        """P3-1 Task 5 (\u00a71b/R2): the cons rule is retired -- functor("a", F, A)
        -> F = "a", A = 0 (a str is its own atom functor, arity 0), NOT the
        ISO cons-cell ('.', 2) reading this test pinned pre-pivot (formerly
        ``test_decompose_str_cons_cell``).
        """
        # nv
        name, arity = Var(), Var()
        result = _call_binding("functor", mint("a"), name, arity)
        assert result is not None
        assert result == (char_atom("a"), 0)

    def test_decompose_arity1(self):
        """functor(f(x), Name, Arity) → Name = f, Arity = 1."""
        # nv
        name, arity = Var(), Var()
        result = _call_binding("functor", ("f", char_atom("x")), name, arity)
        assert result is not None
        assert result == (char_atom("f"), 1)

    def test_construct_compound(self):
        """ISO: functor(T, f, 2) → T = f(_, _) (fresh vars)."""
        # nv
        t = Var()
        result = _call_binding("functor", t, mint("f"), 2, var_indices=[0])
        assert result is not None
        term = result[0]
        # The name position CONSTRUCTS CELLS (atoms-as-cells design §6.4):
        # ``f(_, _)`` is the cell ``("f", _, _)``, the engine's own compound
        # representation, not the legacy ``Compound`` wrapper.
        assert type(term) is tuple
        assert term[0] == "f"
        assert len(term) - 1 == 2

    def test_construct_atom(self):
        """ISO: functor(T, a, 0) → T = a."""
        # nv
        t = Var()
        result = _call_binding("functor", t, mint("a"), 0, var_indices=[0])
        assert result is not None
        assert result[0] == mint("a")

    # Numeric-literal decomposition migrated to iso_term_manipulation.clausal.

    def test_decompose_large_compound(self):
        """functor(f(a,b,c,d,e), Name, Arity) → Name=f, Arity=5."""
        # nv
        name, arity = Var(), Var()
        result = _call_binding(
            "functor",
            ("f", char_atom("a"), char_atom("b"), char_atom("c"), char_atom("d"), char_atom("e")),
            name, arity,
        )
        assert result is not None
        assert result == (char_atom("f"), 5)


# ── arg/3 ─────────────────────────────────────────────────────────────────────


class TestArg:
    """ISO §8.5.2 — arg/3."""

    def test_first_arg(self):
        """ISO: arg(1, f(a,b,c), X) → X = a."""
        # nv
        x = Var()
        result = _call_binding("arg", 1, ("f", char_atom("a"), char_atom("b"), char_atom("c")), x)
        assert result is not None
        assert result[0] == mint("a")

    def test_second_arg(self):
        """ISO: arg(2, f(a,b,c), X) → X = b."""
        # nv
        x = Var()
        result = _call_binding("arg", 2, ("f", char_atom("a"), char_atom("b"), char_atom("c")), x)
        assert result is not None
        assert result[0] == mint("b")

    def test_third_arg(self):
        # nv
        x = Var()
        result = _call_binding("arg", 3, ("f", char_atom("a"), char_atom("b"), char_atom("c")), x)
        assert result is not None
        assert result[0] == mint("c")

    def test_out_of_range(self):
        """ISO: arg(4, f(a,b,c), X) fails."""
        # nv
        x = Var()
        result = _call_binding("arg", 4, ("f", char_atom("a"), char_atom("b"), char_atom("c")), x)
        assert result is None

    def test_zero_fails(self):
        """ISO: arg(0, f(a), X) fails."""
        # nv
        x = Var()
        result = _call_binding("arg", 0, ("f", char_atom("a")), x)
        assert result is None

    def test_negative_fails(self):
        # nv
        x = Var()
        result = _call_binding("arg", -1, ("f", char_atom("a")), x)
        assert result is None

    def test_nested_compound(self):
        """arg(1, f(g(x)), A) → A = g(x)."""
        # nv
        a = Var()
        inner = ("g", char_atom("x"))
        result = _call_binding("arg", 1, ("f", inner), a)
        assert result is not None
        assert result[0] == inner


# ── =../2 (univ) ─────────────────────────────────────────────────────────────


class TestUniv:
    """ISO §8.5.3 — =../2 (spelled 'univ' in clausal)."""

    def test_decompose_compound(self):
        """ISO: f(a,b) =.. X → X = [f, a, b]."""
        # nv
        x = Var()
        result = _call_binding("unpack", ("f", char_atom("a"), char_atom("b")), x)
        assert result is not None
        assert result[0] == [char_atom("f"), char_atom("a"), char_atom("b")]

    def test_decompose_str_is_its_own_atom_functor(self):
        """P3-1 Task 5 (\u00a71b/R2): the cons rule is retired -- "a" =.. X ->
        X = ["a"] (a str is its own atom, univ gives [atom]), NOT the ISO
        cons-cell [".", "a", ""] reading this test pinned pre-pivot
        (formerly ``test_decompose_str_cons_cell``).
        """
        # nv
        x = Var()
        result = _call_binding("unpack", mint("a"), x)
        assert result is not None
        assert result[0] == [char_atom("a")]

    def test_decompose_arity1(self):
        """f(x) =.. L → L = [f, x]."""
        # nv
        lst = Var()
        result = _call_binding("unpack", ("f", char_atom("x")), lst)
        assert result is not None
        assert result[0] == [char_atom("f"), char_atom("x")]

    def test_construct_from_list(self):
        """ISO: T =.. [f, a, b] → T = f(a, b)."""
        # nv
        t = Var()
        result = _call_binding("unpack", t, [char_atom("f"), char_atom("a"), char_atom("b")], var_indices=[0])
        assert result is not None
        term = result[0]
        # ``=..`` constructs a CELL (atoms-as-cells design §6.4) — see
        # ``TestFunctor::test_construct_compound``.
        assert term == ("f", char_atom("a"), char_atom("b"))

    def test_construct_atom_from_list(self):
        """ISO: T =.. [a] → T = a."""
        # nv
        t = Var()
        result = _call_binding("unpack", t, [char_atom("a")], var_indices=[0])
        assert result is not None
        assert result[0] == mint("a")

    # Numeric-literal decomposition migrated to iso_term_manipulation.clausal.
