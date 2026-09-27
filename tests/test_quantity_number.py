"""quantity_number/2 -- the EXPLICIT conversion between a quantity's transfer
term and the object (spec 2026-09-16-quantity-transfer-form-design.md §4).

Driven through the engine, not through Python calls: every test loads a
.clausal module and runs a goal with call().
"""
import pytest

from clausal import Var, cell_args, cell_functor
from clausal.import_hook import _load_module
from clausal.logic.atoms import mint
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import call
from clausal.logic.variables import deref
from clausal.modules import units
from clausal.predicate_diagnostics import PredicateNotFoundError
from clausal.terms import Quantity


def _load(tmp_path, src, name):
    p = tmp_path / f"{name}.clausal"
    p.write_text(src)
    return _load_module(name, str(p)).__dict__["$module"]


PRELUDE = (
    "-import_from(py.units, [kilometre, percent, basis_point, quantity_number])\n"
    "-private([quantity(A, B), unit(A, B), units(A, B), dimensions(A), metre(A), dimensionless, decimal(A, B)])\n"
)
# `units(A, B)` (plural, distinct from `unit(A, B)`) is declared ONLY so
# test_a_malformed_term_RAISES_a_type_error_rather_than_failing_quietly can
# build its deliberately-malformed term at all: an undeclared compound
# functor is not "in scope as a term class" (NameError at the call site,
# before quantity_number/2 ever runs) -- see the report for what was
# MEASURED here on 2026-09-16.
# MEASURED 2026-09-16 (controller probe, this tree): with these declarations
# `X is quantity(5, unit(1000, dimensions(metre(1))))` binds X to the tuple
# ('quantity', 5, ('unit', 1000, ('dimensions', ('metre', 1)))), `dimensionless`
# arrives as ('dimensionless',), and a bound R inlines. `is` is unification in
# .clausal source (`=` is Python syntax, `==` is arithmetic equality). `metre` is
# NOT imported here on purpose: an imported unit name in argument position builds
# a Quantity, not the dimension pair metre(1). Each functor arity needs its own
# declaration, so multi-dimension terms in source are out; Task 3 covers them.


def _solutions(mod, functor, *args):
    return [tuple(deref(a) for a in args) for _ in call(functor, *args, module=mod)]


def test_object_to_term_emits_ratio_one(tmp_path):
    mod = _load(tmp_path, PRELUDE +
        "emit(T) <- (eval_(5(kilometre), Q), quantity_number(T, Q))\n", "qn_emit")
    t = Var()
    sols = _solutions(mod, "emit", t)
    assert sols == [(("quantity", 5000, ("unit", 1, ("dimensions", ("metre", 1)))),)]


def test_term_to_object_multiplies_the_ratio_through(tmp_path):
    mod = _load(tmp_path, PRELUDE +
        "read(Q) <- quantity_number(quantity(5, unit(1000, dimensions(metre(1)))), Q)\n",
        "qn_read")
    q = Var()
    sols = _solutions(mod, "read", q)
    assert len(sols) == 1 and sols[0][0] == Quantity(5, units.kilometre)


def test_both_bound_compares_by_VALUE(tmp_path):
    mod = _load(tmp_path, PRELUDE +
        "same <- (eval_(5(kilometre), Q), quantity_number(quantity(5, unit(1000, dimensions(metre(1)))), Q))\n"
        "pct <- (eval_(300(basis_point), Q), quantity_number(quantity(3, unit(decimal(1, 2), dimensionless)), Q))\n"
        "diff <- (eval_(6(kilometre), Q), quantity_number(quantity(5, unit(1000, dimensions(metre(1)))), Q))\n",
        "qn_both")
    assert _solutions(mod, "same") == [()]
    assert _solutions(mod, "pct") == [()]
    assert _solutions(mod, "diff") == []


def test_both_unbound_is_an_instantiation_error(tmp_path):
    mod = _load(tmp_path, PRELUDE + "bad(T, Q) <- quantity_number(T, Q)\n", "qn_inst")
    with pytest.raises(LogicException) as ei:
        list(call("bad", Var(), Var(), module=mod))
    assert cell_args(ei.value.term)[0] == mint("instantiation_error")


def test_a_malformed_term_RAISES_a_type_error_rather_than_failing_quietly(tmp_path):
    mod = _load(tmp_path, PRELUDE +
        "bad(Q) <- quantity_number(quantity(5, units(1, dimensionless)), Q)\n", "qn_type")
    with pytest.raises(LogicException) as ei:
        list(call("bad", Var(), module=mod))
    inner = cell_args(ei.value.term)[0]
    assert cell_functor(inner) == "type_error" and cell_args(inner)[0] == mint("quantity")
    assert cell_args(inner)[1] == ("quantity", 5, ("units", 1, "dimensionless"))


def test_a_term_slot_holding_a_bound_variable_still_reads(tmp_path):
    # the term is walked (deep deref) before it is read
    mod = _load(tmp_path, PRELUDE +
        "read(Q) <- (R is 1000, quantity_number(quantity(5, unit(R, dimensions(metre(1)))), Q))\n",
        "qn_deref")
    q = Var()
    sols = _solutions(mod, "read", q)
    assert len(sols) == 1 and sols[0][0] == Quantity(5, units.kilometre)


def test_a_term_slot_holding_an_UNBOUND_variable_is_an_instantiation_error(tmp_path):
    mod = _load(tmp_path, PRELUDE +
        "partial(Q) <- quantity_number(quantity(5, unit(R, dimensions(metre(1)))), Q)\n",
        "qn_partial")
    with pytest.raises(LogicException) as ei:
        list(call("partial", Var(), module=mod))
    assert cell_args(ei.value.term)[0] == mint("instantiation_error")


def test_the_object_on_the_term_side_is_taken_as_itself(tmp_path):
    mod = _load(tmp_path, PRELUDE +
        "same <- (eval_(5(kilometre), Q), quantity_number(Q, Q))\n", "qn_obj")
    assert _solutions(mod, "same") == [()]


def test_a_non_quantity_on_the_object_side_just_fails(tmp_path):
    mod = _load(tmp_path, PRELUDE + "nope(T) <- quantity_number(T, 7)\n", "qn_fail")
    assert _solutions(mod, "nope", Var()) == []


def test_a_bound_term_against_a_non_quantity_object_just_fails(tmp_path):
    mod = _load(tmp_path, PRELUDE +
        "nope <- quantity_number(quantity(5, unit(1000, dimensions(metre(1)))), 7)\n", "qn_fail2")
    assert _solutions(mod, "nope") == []


def test_the_relation_is_reachable_by_import_only(tmp_path):
    # no import: the name is not a builtin
    #
    # MEASURED 2026-09-16: the engine raises PredicateNotFoundError (a
    # KeyError subclass, see clausal/predicate_diagnostics.py), not
    # LogicException, and it does so at CALL time (dispatch lookup inside
    # `call()`), not at `_load` time. Both are deviations from the brief's
    # anticipated shapes; per the brief's note on this test, the point
    # pinned here is only that the name is not global.
    mod = _load(tmp_path, "-import_from(py.units, [metre])\n"
                          "emit(T) <- (eval_(5(metre), Q), quantity_number(T, Q))\n", "qn_noimp")
    with pytest.raises(PredicateNotFoundError):
        list(call("emit", Var(), module=mod))
