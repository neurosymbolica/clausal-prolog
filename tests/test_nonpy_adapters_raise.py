"""Non-``py`` library adapters RAISE where they used to fail silently.

Operator rulings 2026-10-02 for adapter predicates:

1. a value of the WRONG TYPE  -> ``error(type_error(Type, Culprit), PI)``;
2. an unbound argument the call needs -> ``error(instantiation_error, PI)``;
3. a right-typed value out of range -> ``error(domain_error(Domain, Culprit), PI)``.

A predicate whose documented meaning is a legitimate "no" (no path, not
connected, an unknown code in the ``currency_code/2`` lookup relation, a
reflection decomposer handed a non-matching node) keeps failing; the
``*_still_fails`` rows below pin those.

Each row asserts the EXACT error term, built with the same constructors the
adapters use, so a drift in type/domain name or context shows up here.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from clausal.logic.atoms import mint
from clausal.logic.cells import chars
from clausal.logic.exceptions import (
    LogicException, domain_error, existence_error, instantiation_error, type_error)
from clausal.logic.solve import _drive_trampoline, call
from clausal.logic.variables import Trail, Var, deref
from clausal.terms import Quantity

from clausal.modules import currency as C
from clausal.modules import graphs as G
from clausal.modules import reflection as R
from clausal.modules import units as U
from clausal.modules.countries.european_union import euro


def _run(pred, *args):
    """Drive a ModulePredicate's dispatch; return the number of solutions."""
    return sum(1 for _ in _drive_trampoline(pred._get_dispatch(), Trail(), *args))


def _term(pred, *args):
    """The error term *pred(args)* raises."""
    with pytest.raises(LogicException) as ei:
        _run(pred, *args)
    return ei.value.term


def _gsols(fn, *args):
    """Drive a trampoline-mode graphs fn directly; count solutions."""
    n = 0
    for parent, _v in fn(None, "P", "F", None, *args, Trail()):
        if parent != "P":
            break
        n += 1
    return n


def _graph_term(fn, *args):
    with pytest.raises(LogicException) as ei:
        _gsols(fn, *args)
    return ei.value.term


# ═════════════════════════════════════════════════════════════════════════════
# graphs
# ═════════════════════════════════════════════════════════════════════════════

_E = [["a", "b"], ["b", "c"]]

# (fn, args with the EDGES slot first, indicator)
_EDGE_PREDICATES = [
    (G._vertices__2, (Var(),), "vertices/2"),
    (G._neighbors__3, ("a", Var()), "neighbors/3"),
    (G._has_edge__3, (Var(), Var()), "has_edge/3"),
    (G._degree__3, ("a", Var()), "degree/3"),
    (G._is_connected__1, (), "is_connected/1"),
    (G._is_isolated__2, (Var(),), "is_isolated/2"),
    (G._breadth_first_nodes__3, ("a", Var()), "breadth_first_nodes/3"),
    (G._depth_first_nodes__3, ("a", Var()), "depth_first_nodes/3"),
    (G._find_path__4, ("a", "c", Var()), "find_path/4"),
    (G._shortest_path__4, ("a", "c", Var()), "shortest_path/4"),
    (G._path_cost__3, (["a", "b"], Var()), "path_cost/3"),
    (G._connected_components__2, (Var(),), "connected_components/2"),
    (G._topological_sort__2, (Var(),), "topological_sort/2"),
    (G._has_cycle__1, (), "has_cycle/1"),
    (G._spanning_tree__2, (Var(),), "spanning_tree/2"),
    (G._min_spanning_tree__3, (Var(), Var()), "min_spanning_tree/3"),
    (G._reverse_edges__2, (Var(),), "reverse_edges/2"),
]


@pytest.mark.parametrize("fn, rest, pi", _EDGE_PREDICATES, ids=[r[2] for r in _EDGE_PREDICATES])
def test_graphs_non_list_edges_is_a_type_error(fn, rest, pi):
    assert _graph_term(fn, mint("not_a_graph"), *rest) == type_error(
        "list", mint("not_a_graph"), pi)


@pytest.mark.parametrize("fn, rest, pi", _EDGE_PREDICATES, ids=[r[2] for r in _EDGE_PREDICATES])
def test_graphs_unbound_edges_is_an_instantiation_error(fn, rest, pi):
    assert _graph_term(fn, Var(), *rest) == instantiation_error(pi)


def test_merge_graphs_checks_both_edge_lists():
    assert _graph_term(G._merge_graphs__3, 5, _E, Var()) == type_error(
        "list", 5, "merge_graphs/3")
    assert _graph_term(G._merge_graphs__3, _E, Var(), Var()) == instantiation_error(
        "merge_graphs/3")


@pytest.mark.parametrize("fn, args, pi", [
    (G._neighbors__3, (_E, Var(), Var()), "neighbors/3"),
    (G._degree__3, (_E, Var(), Var()), "degree/3"),
    (G._breadth_first_nodes__3, (_E, Var(), Var()), "breadth_first_nodes/3"),
    (G._depth_first_nodes__3, (_E, Var(), Var()), "depth_first_nodes/3"),
    (G._find_path__4, (_E, Var(), "c", Var()), "find_path/4"),
    (G._find_path__4, (_E, "a", Var(), Var()), "find_path/4"),
    (G._shortest_path__4, (_E, Var(), "c", Var()), "shortest_path/4"),
    (G._shortest_path__4, (_E, "a", Var(), Var()), "shortest_path/4"),
])
def test_graphs_unbound_needed_node_is_an_instantiation_error(fn, args, pi):
    assert _graph_term(fn, *args) == instantiation_error(pi)


def test_path_cost_path_argument_checked():
    assert _graph_term(G._path_cost__3, _E, Var(), Var()) == instantiation_error("path_cost/3")
    assert _graph_term(G._path_cost__3, _E, mint("a"), Var()) == type_error(
        "list", mint("a"), "path_cost/3")


def test_shortest_path_negative_weight_is_a_domain_error():
    edges = [["a", "b", 1], ["a", "c", 5], ["c", "b", -100]]
    assert _graph_term(G._shortest_path__4, edges, "a", "b", Var()) == domain_error(
        "not_less_than_zero", -100, "shortest_path/4")


def test_graphs_legitimate_no_still_fails():
    # no path, disconnected, cycle, unknown node, path not in the graph
    assert _gsols(G._find_path__4, [["a", "b"], ["c", "d"]], "a", "d", Var()) == 0
    assert _gsols(G._shortest_path__4, [["a", "b"], ["c", "d"]], "a", "d", Var()) == 0
    assert _gsols(G._is_connected__1, [["a", "b"], ["c", "d"]]) == 0
    assert _gsols(G._topological_sort__2, [["a", "b"], ["b", "a"]], Var()) == 0
    assert _gsols(G._spanning_tree__2, [["a", "b"], ["c", "d"]], Var()) == 0
    assert _gsols(G._path_cost__3, _E, ["a", "c"], Var()) == 0
    assert _gsols(G._has_edge__3, _E, "c", "a") == 0


# ═════════════════════════════════════════════════════════════════════════════
# currency
# ═════════════════════════════════════════════════════════════════════════════

_EUR = Quantity(Decimal("7.89"), euro)
_METRES = U.metre(5)


@pytest.mark.parametrize("pred, pi", [(C.money, "money/3"), (C.money_precise, "money_precise/3")])
def test_money_constructors_unbound(pred, pi):
    assert _term(pred, Var(), euro, Var()) == instantiation_error(pi)
    assert _term(pred, chars("1.00"), Var(), Var()) == instantiation_error(pi)


@pytest.mark.parametrize("pred, pi", [(C.money, "money/3"), (C.money_precise, "money_precise/3")])
def test_money_constructors_non_currency_is_a_type_error(pred, pi):
    assert _term(pred, chars("1.00"), U.metre, Var()) == type_error("currency", U.metre, pi)
    assert _term(pred, chars("1.00"), mint("eur"), Var()) == type_error(
        "currency", mint("eur"), pi)


@pytest.mark.parametrize("pred, attr", [
    (C.currency_scale, "scale"), (C.currency_symbol, "symbol"),
    (C.currency_start, "start"), (C.currency_end, "end"),
])
def test_currency_accessor_non_currency_is_a_type_error(pred, attr):
    assert _term(pred, 42, Var()) == type_error("currency", 42, f"currency_{attr}/2")


def test_currency_code_forward_non_currency_is_a_type_error():
    assert _term(C.currency_code, U.metre, Var()) == type_error(
        "currency", U.metre, "currency_code/2")


def test_currency_code_reverse_non_text_code_is_a_type_error():
    assert _term(C.currency_code, Var(), 978) == type_error("text", 978, "currency_code/2")


def test_currency_code_unknown_code_still_fails():
    # a lookup RELATION: an unknown code is an ordinary "no"
    assert _run(C.currency_code, Var(), mint("zzz")) == 0
    assert _run(C.currency_code, Var(), chars("EUR")) == 1


@pytest.mark.parametrize("pred, extra, pi", [
    (C.money_round, (mint("half_up"),), "money_round/3"),
    (C.money_str, (mint("half_up"),), "money_str/3"),
    (C.money_format, (mint("symbol"), mint("half_up")), "money_format/4"),
])
def test_money_amount_checks(pred, extra, pi):
    assert _term(pred, Var(), *extra, Var()) == instantiation_error(pi)
    assert _term(pred, 42, *extra, Var()) == type_error("quantity", 42, pi)
    assert _term(pred, _METRES, *extra, Var()) == domain_error("money", _METRES, pi)


@pytest.mark.parametrize("pred, pi", [(C.money_round, "money_round/3"), (C.money_str, "money_str/3")])
def test_money_rounding_mode_checks(pred, pi):
    assert _term(pred, _EUR, Var(), Var()) == instantiation_error(pi)
    assert _term(pred, _EUR, 3, Var()) == type_error("text", 3, pi)
    assert _term(pred, _EUR, mint("sideways"), Var()) == domain_error(
        "rounding_mode", mint("sideways"), pi)


def test_money_format_style_and_mode_checks():
    pi = "money_format/4"
    assert _term(C.money_format, _EUR, Var(), mint("half_up"), Var()) == instantiation_error(pi)
    assert _term(C.money_format, _EUR, mint("fancy"), mint("half_up"), Var()) == domain_error(
        "money_style", mint("fancy"), pi)
    assert _term(C.money_format, _EUR, mint("symbol"), mint("sideways"), Var()) == domain_error(
        "rounding_mode", mint("sideways"), pi)
    # the happy path still answers
    assert _run(C.money_format, _EUR, mint("code"), mint("half_up"), Var()) == 1


# ═════════════════════════════════════════════════════════════════════════════
# units
# ═════════════════════════════════════════════════════════════════════════════


def test_strip_units_checks():
    assert _term(U.strip_units, Var(), Var()) == instantiation_error("strip_units/2")
    # A bare number is dimensionless (RULED 2026-10-02); an atom is not a quantity.
    assert _term(U.strip_units, "abc", Var()) == type_error("quantity", "abc", "strip_units/2")


def test_dimension_of_checks():
    assert _term(U.dimension_of, Var(), Var()) == instantiation_error("dimension_of/2")
    assert _term(U.dimension_of, "abc", Var()) == type_error("quantity", "abc", "dimension_of/2")


def test_make_quantity_checks():
    from clausal.terms import DictTerm
    assert _term(U.make_quantity, Var(), DictTerm({"metre": 1}), Var()) == instantiation_error(
        "make_quantity/3")
    assert _term(U.make_quantity, 5, Var(), Var()) == instantiation_error("make_quantity/3")
    assert _term(U.make_quantity, 5, [1, 2], Var()) == type_error(
        "dict", [1, 2], "make_quantity/3")


# ═════════════════════════════════════════════════════════════════════════════
# reflection
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("pred, pi", [
    (R.reified_item, "reified_item/2"),
    (R.reified_clause, "reified_clause/2"),
    (R.reified_file_item, "reified_file_item/2"),
])
def test_reflection_non_text_source_is_a_type_error(pred, pi):
    with pytest.raises(LogicException) as ei:
        list(call(pred, 42, Var()))
    assert ei.value.term == type_error("text", 42, pi)


def test_reified_file_item_missing_file_is_an_existence_error(tmp_path):
    missing = chars(str(tmp_path / "no_such_file.clausal"))
    with pytest.raises(LogicException) as ei:
        list(call(R.reified_file_item, missing, Var()))
    assert ei.value.term == existence_error("source_sink", missing, "reified_file_item/2")


def test_reflection_decomposers_still_fail_on_a_non_matching_node():
    # filter idiom: reified_subterm(C, SUB), op_node(SUB, ...) walks EVERY
    # subterm, so a non-operator (or unbound) subterm must be a "no"
    assert list(call(R.op_node, 42, Var(), Var())) == []
    assert list(call(R.goal_functor, 42, Var(), Var())) == []
    assert list(call(R.clause_head, 42, Var())) == []


# ═════════════════════════════════════════════════════════════════════════════
# catchable from Clausal source, by the ISO pattern
# ═════════════════════════════════════════════════════════════════════════════


def test_catchable_by_iso_pattern_from_source(tmp_path):
    from clausal.import_hook import _load_module
    from tests._suffix import SEAM
    p = tmp_path / f"nonpy_raise_catch{SEAM}"
    p.write_text(
        "-private([nope, abc])\n"
        "-import_from(units, [strip_units])\n"
        "-import_from(graphs, [vertices])\n"
        "t1(T) <- catch(strip_units(abc, _), error(type_error(T, abc), _), true)\n"
        "t2(D) <- catch(vertices(nope, _), error(type_error(D, nope), _), true)\n"
    )
    mod = _load_module("nonpy_raise_catch", str(p)).__dict__["$module"]
    out = Var()
    got = [deref(out) for _ in call("t1", out, module=mod)]
    assert got == [mint("quantity")]
    out = Var()
    got = [deref(out) for _ in call("t2", out, module=mod)]
    assert got == [mint("list")]
