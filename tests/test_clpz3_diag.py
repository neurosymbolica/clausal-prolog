"""Tests for Z3 diagnostics — Phase 8.

Covers: named constraints, unsat cores, model inspection, entailment,
        simplification, assertions dump, solver config, statistics.
"""

from __future__ import annotations
import pytest

z3 = pytest.importorskip("z3")

from clausal.logic.atoms import is_atom, mint
from clausal.logic.cells import chars
from clausal.logic.exceptions import LogicException
from clausal.logic.variables import Var, Trail, deref, is_var
from clausal.logic.clpz3 import (
    in_z3, z3_eq, z3_le, z3_ge, z3_check, label_z3,
    z3_named, z3_unsat_core, z3_minimal_unsat_core,
    z3_is_sat, z3_disentailed, z3_model, z3_simplify,
    z3_assertions, z3_stats, z3_set_option, z3_set_logic,
    z3_declare_datatype, entailed_z3, get_z3_state,
)
from clausal.pythonic_ast.nodes import ArithEq, Lt, LtE, Gt, GtE, Add


# ══════════════════════════════════════════════════════════════════════════════
# Named Constraints & Unsat Core
# ══════════════════════════════════════════════════════════════════════════════

class TestNamedConstraints:
    def test_named_post_succeeds(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        assert z3_named(Gt(left=x, right=5), mint("x_big"), trail)

    def test_named_and_unsat_core(self):
        """x > 5 AND x < 3 is unsat — core includes both."""
        # nv
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        z3_named(Gt(left=x, right=5), mint("x_big"), trail)
        z3_named(Lt(left=x, right=3), mint("x_small"), trail)
        core = Var()
        assert z3_unsat_core(core, trail)
        names = deref(core)
        assert mint("x_big") in names
        assert mint("x_small") in names

    def test_satisfiable_no_core(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        z3_named(Gt(left=x, right=5), mint("x_big"), trail)
        core = Var()
        assert not z3_unsat_core(core, trail)

    def test_named_backtrack(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)

        mark = trail.mark()
        z3_named(Gt(left=x, right=5), mint("x_big"), trail)
        trail.undo(mark)

        state = get_z3_state(trail)
        named = getattr(state, '_named_constraints', {})
        # The registry is keyed by the atom's SPELLING (§6.4): a plain str
        # here is the internal storage key, not a term.
        assert "x_big" not in named

    def test_three_constraints_two_conflict(self):
        """Three named constraints, only two conflict."""
        # nv
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        z3_named(Gt(left=x, right=5), mint("a"), trail)
        z3_named(Lt(left=x, right=3), mint("b"), trail)
        z3_named(GtE(left=x, right=1), mint("c"), trail)  # always true (domain)
        core = Var()
        assert z3_unsat_core(core, trail)
        names = deref(core)
        assert mint("a") in names
        assert mint("b") in names

    def test_no_named_unsat(self):
        """Unsat with no named constraints returns empty core."""
        # nv
        trail = Trail()
        x = Var()
        in_z3(x, 1, 5, trail)
        z3_eq(x, 10, trail)  # contradicts domain
        core = Var()
        assert z3_unsat_core(core, trail)
        assert deref(core) == []


class TestNamedConstraintNamesAreAtoms:
    """THE FLIP (2026-09-06-atoms-as-cells-strings §6.4): a constraint's Name
    is a NAME, so it is an ATOM.  ``z3_named`` coerced anything non-``str``
    with ``str(name)``, which post-flip renders ``("x_big",)`` as the Python
    tuple REPR ``"('x_big',)"`` — the indicator, the ``_named_constraints``
    key and every core answer carried the repr.
    """

    def test_atom_name_is_stored_and_returned_by_spelling(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        assert z3_named(Gt(left=x, right=5), mint("x_big"), trail)
        assert z3_named(Lt(left=x, right=3), mint("x_small"), trail)

        state = get_z3_state(trail)
        assert set(state._named_constraints) == {"x_big", "x_small"}

        core = Var()
        assert z3_unsat_core(core, trail)
        # Atoms in, atoms out (§6.4) — the answer is comparable to what the
        # program wrote, which a repr or a bare spelling would not be.
        assert deref(core) == [mint("x_big"), mint("x_small")]

    def test_minimal_core_answers_atoms_too(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        z3_named(Gt(left=x, right=5), mint("a"), trail)
        z3_named(Lt(left=x, right=3), mint("b"), trail)
        z3_named(GtE(left=x, right=1), mint("c"), trail)  # redundant
        core = Var()
        assert z3_minimal_unsat_core(core, trail)
        assert deref(core) == [mint("a"), mint("b")]

    def test_a_string_name_is_refused(self):
        # nv
        from clausal.logic.exceptions import LogicException

        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        with pytest.raises(LogicException) as exc:
            z3_named(Gt(left=x, right=5), chars("x_big"), trail)
        formal = exc.value.term.args[0]
        assert formal.functor == "type_error"
        assert formal.args[0] == mint("atom")
        assert formal.args[1] == chars("x_big")

    def test_an_unbound_name_fails_rather_than_raising(self):
        """Fix round 1: a variable Name is a MODE signal, not a type fault —
        the term is the right sort and only the binding is missing.  The two
        sibling funnels this task added (``clpfd._op_spelling``,
        ``attributes._storage_key``) both fail for an unbound argument, and
        this one now matches them."""
        # nv
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        assert z3_named(Gt(left=x, right=5), Var(), trail) is False
        state = get_z3_state(trail)
        assert not getattr(state, "_named_constraints", {})


class TestMinimalUnsatCore:
    def test_minimal_core_strips_redundant(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        z3_named(Gt(left=x, right=5), mint("a"), trail)
        z3_named(Lt(left=x, right=3), mint("b"), trail)
        z3_named(GtE(left=x, right=1), mint("c"), trail)  # redundant
        core = Var()
        assert z3_minimal_unsat_core(core, trail)
        names = deref(core)
        assert mint("a") in names
        assert mint("b") in names
        # "c" should NOT be in minimal core
        assert mint("c") not in names

    def test_satisfiable_returns_false(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        z3_named(Gt(left=x, right=5), mint("a"), trail)
        core = Var()
        assert not z3_minimal_unsat_core(core, trail)


# ══════════════════════════════════════════════════════════════════════════════
# Satisfiability Check
# ══════════════════════════════════════════════════════════════════════════════

class TestIsSat:
    def test_sat(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        r = Var()
        assert z3_is_sat(r, trail)
        # Task 12c: a status is a NAME (§6.4), so the answer is the atom.
        assert deref(r) == mint("sat")

    def test_unsat(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3(x, 1, 5, trail)
        z3_eq(x, 10, trail)
        r = Var()
        assert z3_is_sat(r, trail)
        assert deref(r) == mint("unsat")


# ══════════════════════════════════════════════════════════════════════════════
# Entailment & Disentailment
# ══════════════════════════════════════════════════════════════════════════════

class TestEntailment:
    def test_entailed_by_bounds(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3(x, 5, 10, trail)
        assert entailed_z3(GtE(left=x, right=5), trail)
        assert entailed_z3(LtE(left=x, right=10), trail)

    def test_not_entailed(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        assert not entailed_z3(GtE(left=x, right=5), trail)

    def test_entailed_after_equality(self):
        # nv
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 0, 10, trail)
        z3_eq(x, y, trail)
        z3_eq(x, 5, trail)
        assert entailed_z3(ArithEq(left=y, right=5), trail)


class TestDisentailed:
    def test_disentailed(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3(x, 5, 10, trail)
        assert z3_disentailed(Lt(left=x, right=5), trail)

    def test_not_disentailed(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        assert not z3_disentailed(Lt(left=x, right=5), trail)


# ══════════════════════════════════════════════════════════════════════════════
# Model Inspection
# ══════════════════════════════════════════════════════════════════════════════

class TestModel:
    def test_model_without_binding(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3(x, 1, 3, trail)
        vals = Var()
        assert z3_model([x], vals, trail)
        assert is_var(deref(x))  # x still unbound
        model_data = deref(vals)
        assert len(model_data) == 1
        assert model_data[0][1] in [1, 2, 3]

    def test_model_constrained(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        z3_eq(x, 7, trail)
        vals = Var()
        assert z3_model([x], vals, trail)
        assert deref(vals)[0][1] == 7

    def test_model_unsat_fails(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3(x, 1, 5, trail)
        z3_eq(x, 10, trail)
        vals = Var()
        assert not z3_model([x], vals, trail)

    def test_model_multiple_vars(self):
        # nv
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 0, 10, trail)
        z3_eq(x, 3, trail)
        z3_eq(y, 7, trail)
        vals = Var()
        assert z3_model([x, y], vals, trail)
        model_data = deref(vals)
        assert len(model_data) == 2
        values = {pair[1] for pair in model_data}
        assert values == {3, 7}


# ══════════════════════════════════════════════════════════════════════════════
# Simplification
# ══════════════════════════════════════════════════════════════════════════════

class TestSimplify:
    def test_simplify_constant(self):
        # nv
        trail = Trail()
        r = Var()
        assert z3_simplify(Add(left=2, right=3), r, trail)
        assert deref(r) == 5

    def test_simplify_tautology(self):
        # nv
        trail = Trail()
        r = Var()
        assert z3_simplify(ArithEq(left=5, right=5), r, trail)
        # z3_to_python may return True or 1 (bool is subclass of int)
        assert deref(r) in (True, 1)

    def test_simplify_with_variable(self):
        """Simplify expression containing a variable returns string form."""
        # nv
        trail = Trail()
        x = Var()
        in_z3(x, 0, 10, trail)
        r = Var()
        assert z3_simplify(Add(left=x, right=0), r, trail)
        result = deref(r)
        # Z3 simplifies x + 0 → x; result is either the int (if var resolved)
        # or a string representation
        assert result is not None


# ══════════════════════════════════════════════════════════════════════════════
# Assertions Dump
# ══════════════════════════════════════════════════════════════════════════════

class TestAssertions:
    def test_dump_assertions(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        a = Var()
        assert z3_assertions(a, trail)
        a_list = deref(a)
        assert len(a_list) >= 2  # at least x >= 1 and x <= 10
        assert all(isinstance(s, str) for s in a_list)

    def test_empty_assertions(self):
        # nv
        trail = Trail()
        _ = get_z3_state(trail)  # init state
        a = Var()
        assert z3_assertions(a, trail)
        assert deref(a) == []


# ══════════════════════════════════════════════════════════════════════════════
# Solver Statistics
# ══════════════════════════════════════════════════════════════════════════════

class TestStats:
    def test_stats_returns_pairs(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        s = Var()
        assert z3_stats(s, trail)
        stats = deref(s)
        assert isinstance(stats, list)
        # Stats should contain at least some entries after check()
        # Each entry is [key, value]
        for pair in stats:
            assert len(pair) == 2
            assert isinstance(pair[0], str)


# ══════════════════════════════════════════════════════════════════════════════
# Solver Configuration
# ══════════════════════════════════════════════════════════════════════════════

class TestSolverConfig:
    def test_set_timeout(self):
        # nv
        trail = Trail()
        assert z3_set_option(mint("timeout"), 5000, trail)

    def test_set_logic_qf_lia(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        assert z3_set_logic(mint("QF_LIA"), trail)
        assert z3_check(trail)

    def test_set_logic_preserves_constraints(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        z3_eq(x, 5, trail)
        z3_set_logic(mint("QF_LIA"), trail)
        sols = []
        for _ in label_z3([x], trail):
            sols.append(deref(x))
        assert sols == [5]

    def test_set_logic_detects_unsat(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3(x, 1, 5, trail)
        z3_eq(x, 10, trail)
        z3_set_logic(mint("QF_LIA"), trail)
        assert not z3_check(trail)


def _formal_type(exc_info):
    """The TYPE argument of a raised ``error(type_error(Type, X), Context)``."""
    return exc_info.value.term.args[0].args[0]


class TestNamePositionsAreAtoms:
    """Every NAME this module hands to Z3 is an atom (§6.4).

    Each of these positions used to pass the term straight through, so the
    cell a source-written ``"QF_LIA"``/``"timeout"``/``"IntList"`` produces in
    the default ``-double_quotes(atom)`` mode reached the z3 C bindings and
    came back as a bare ``ArgumentError``/``Z3Exception`` — not a logic error
    a program can catch.  A STRING is now the same ``type_error(atom, …)``
    ``z3_named/2`` has always given, and an unbound name fails.
    """

    def test_string_logic_is_a_type_error(self):
        # nv
        trail = Trail()
        with pytest.raises(LogicException) as exc:
            z3_set_logic(chars("QF_LIA"), trail)
        assert _formal_type(exc) == mint("atom")

    def test_string_option_key_is_a_type_error(self):
        # nv
        trail = Trail()
        with pytest.raises(LogicException) as exc:
            z3_set_option(chars("timeout"), 5000, trail)
        assert _formal_type(exc) == mint("atom")

    def test_string_datatype_name_is_a_type_error(self):
        # nv
        trail = Trail()
        with pytest.raises(LogicException) as exc:
            z3_declare_datatype(chars("Shade"), [(mint("pale"), [])], trail)
        assert _formal_type(exc) == mint("atom")

    def test_string_constructor_name_is_a_type_error(self):
        # nv
        trail = Trail()
        with pytest.raises(LogicException) as exc:
            z3_declare_datatype(mint("Shade2"), [(chars("pale2"), [])], trail)
        assert _formal_type(exc) == mint("atom")

    def test_unbound_logic_fails_rather_than_raising(self):
        # nv
        trail = Trail()
        assert z3_set_logic(Var(), trail) is False

    def test_datatype_registers_under_its_spelling(self):
        # nv
        trail = Trail()
        sort = z3_declare_datatype(
            mint("Shade3"), [(mint("pale3"), []), (mint("deep3"), [])], trail)
        assert sort is not None
        # slot 0 stays a plain str, so the registry key is the SPELLING
        assert "Shade3" in get_z3_state(trail).datatypes

    def test_model_answers_atom_names_and_plain_values(self):
        # nv
        trail = Trail()
        x = Var()
        in_z3(x, 1, 3, trail)
        z3_eq(x, 2, trail)
        vals = Var()
        assert z3_model([x], vals, trail)
        name, value = deref(vals)[0]
        assert is_atom(name)      # a Z3 constant NAME is a name position
        assert value == 2         # the VALUE stays a value


# ══════════════════════════════════════════════════════════════════════════════
# Integration: Debug workflow
# ══════════════════════════════════════════════════════════════════════════════

class TestDebugWorkflow:
    def test_find_conflict_with_unsat_core(self):
        """Full workflow: post named constraints, find conflict."""
        # nv
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 1, 10, trail)
        z3_named(Gt(left=x, right=8), mint("x_high"), trail)
        z3_named(Lt(left=y, right=3), mint("y_low"), trail)
        z3_named(ArithEq(left=x, right=y), mint("x_eq_y"), trail)

        # x > 8 AND y < 3 AND x == y is unsat
        core = Var()
        assert z3_unsat_core(core, trail)
        names = deref(core)
        # All three participate in the conflict
        assert len(names) >= 2

    def test_model_then_entailment(self):
        """Inspect model, then verify entailment."""
        # nv
        trail = Trail()
        x = Var()
        in_z3(x, 1, 10, trail)
        z3_eq(x, 5, trail)

        # Model shows x = 5
        vals = Var()
        assert z3_model([x], vals, trail)
        assert deref(vals)[0][1] == 5

        # x == 5 is entailed
        assert entailed_z3(ArithEq(left=x, right=5), trail)

        # x > 5 is disentailed
        assert z3_disentailed(Gt(left=x, right=5), trail)
