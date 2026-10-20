"""Every table that says which arguments of a meta-call are GOALS agrees with
the one table, ``clausal.logic.special_forms``, by ``(name, arity)`` and by
exact position.

Before 2026-10-20 the tables were kept by hand and drifted: catch_error/2
and catch_recover/3 (and some of call_nth/2, count_all/2, call_cleanup/2,
freeze/2, when/2) were missing from the cut-scope scanner's literal
``call/N`` terms, term_expansion's helper reachability and the exporter's
goal walk.  The old
drift test compared ``{name: count}`` only, so neither an arity nor a
position could drift into view.

A table that lists MORE than the special forms (``call/N``, ``\\+``,
``ignore/1``, maplist & co.) is a superset for a stated reason; one that
lists a different spelling (the exported ``.pl`` names) is mapped first.
Goal expansion reads no such table, by decision: see
test_goal_expansion_intentionally_stops_at_a_meta_call.
"""
from __future__ import annotations

import typing

import pytest

from clausal.logic.special_forms import GOAL_POSITIONS, SPECIAL_FORMS
from clausal.logic.variables import Var, deref
from clausal.pythonic_ast import nodes


# ── the compiler is the reference ───────────────────────────────────────────


def _lowered_positions(name: str, arity: int):
    """``(kind, {0-based position: arg key})`` of the goal arguments of the
    MetaCall the compiler makes of ``name(A0, ..., An)``; ``None`` for a
    form lowered to something else (eval_/2 -> ArithEval)."""
    from clausal.logic.compiler.ir import META_GOAL_POSITIONS, MetaCall
    from clausal.logic.compiler.terms_to_goalop import _convert
    probes = [Var() for _ in range(arity)]
    op = _convert(nodes.Call(func=nodes.LoadName(name=name), args=probes,
                             kwargs=[]), None)
    if not isinstance(op, MetaCall):
        return None
    at = {}
    for key in META_GOAL_POSITIONS.get(op.kind, ()):
        if key in op.args:
            hit = [i for i, p in enumerate(probes) if op.args[key] is p]
            assert len(hit) == 1, (name, arity, key)
            at[hit[0]] = key
    return op.kind, at


@pytest.mark.parametrize("key", sorted(SPECIAL_FORMS), ids=lambda k: f"{k[0]}/{k[1]}")
def test_the_goal_positions_are_the_compilers(key):
    """``ir.META_GOAL_POSITIONS`` (key-named) puts each special form's goals
    exactly where :data:`GOAL_POSITIONS` (index-named) says."""
    lowered = _lowered_positions(*key)
    want = GOAL_POSITIONS.get(key, ())
    got = () if lowered is None else tuple(sorted(lowered[1]))
    assert got == want


def test_every_meta_kind_with_a_goal_is_a_special_form_with_one():
    from clausal.logic.compiler.ir import META_GOAL_POSITIONS, MetaKind
    kinds = {k for k in typing.get_args(MetaKind) if META_GOAL_POSITIONS.get(k)}
    assert kinds == {name for name, _ in GOAL_POSITIONS}
    assert set(META_GOAL_POSITIONS) == kinds


def test_the_table_is_not_vacuous():
    assert GOAL_POSITIONS[("catch_error", 2)] == (0,)
    assert GOAL_POSITIONS[("catch_recover", 3)] == (0, 2)
    assert GOAL_POSITIONS[("when", 2)] == (1,)        # W, the condition, is not
    assert ("throw", 1) not in GOAL_POSITIONS
    assert ("eval_", 2) not in GOAL_POSITIONS


# ── tables that ARE the canonical one ──────────────────────────────────────


def test_call_body_uses_the_table():
    from clausal.logic.builtins import call_body
    assert call_body.SPECIAL_FORMS is SPECIAL_FORMS


def test_clause_ops_uses_the_table():
    from clausal.logic.builtins import clause_ops
    assert clause_ops.SPECIAL_FORMS == frozenset(SPECIAL_FORMS)
    assert clause_ops._GOAL_ARGS == GOAL_POSITIONS


def test_the_native_front_end_uses_the_table():
    from clausal.tools import iso_l3
    assert iso_l3._META_GOAL_ARGS == GOAL_POSITIONS


# ── tables derived from it, with their own extras ──────────────────────────


@pytest.mark.parametrize("key", sorted(GOAL_POSITIONS), ids=lambda k: f"{k[0]}/{k[1]}")
def test_the_cut_scope_scanner_reads_a_literal_term_like_the_compiler(key):
    """call/N's LITERAL goal term (a cell, not a clause-body node) becomes the
    MetaCall the compiler would make of the same goal: same kind, and each
    goal argument under the same key, so the scan descends into it."""
    from clausal.logic.compiler.cut_scope import _body_term_ir
    from clausal.logic.compiler.ir import MetaCall, SubCall
    name, arity = key
    op = _body_term_ir((name, *(f"arg{i}" for i in range(arity))))
    kind, at = _lowered_positions(name, arity)
    assert isinstance(op, MetaCall) and op.kind == kind
    assert {k: v for k, v in op.args.items()} == {
        k: SubCall(fname=f"arg{i}", arity=0, args=[]) for i, k in at.items()}


def test_the_cut_scope_run_time_meta_names_cover_the_table():
    """A goal reached as an ordinary call to one of these names runs a goal
    argument at run time.  Extras: call/N, control constructs and the
    goal-taking builtins that are not special forms."""
    from clausal.logic.compiler.cut_scope import _RUN_TIME_META
    assert {name for name, _ in GOAL_POSITIONS} <= _RUN_TIME_META


def test_term_expansion_helper_reachability_covers_the_table():
    """Extras: call/N's closure, ``\\+``/not/ignore and aggregate_all/3,
    goal-taking builtins that are not special forms."""
    from clausal.logic.term_expansion import _goal_positions
    for (name, arity), positions in GOAL_POSITIONS.items():
        assert _goal_positions(name, arity) == positions, (name, arity)
    assert _goal_positions("call", 3) == (0,)
    assert _goal_positions("\\+", 1) == (0,)
    assert _goal_positions("once", 2) == ()       # another arity is a call


def _pl_name(name: str) -> str:
    """The spelling the exporter writes a seam builtin with (catch_error/2
    is ``catch/2``)."""
    from clausal.tools.prolog_dialect import BUILTIN_NAME_MAP
    return BUILTIN_NAME_MAP.get(name, {}).get("iso", name)


def test_the_exporters_goal_walk_covers_the_table():
    """``clausal_to_prolog.GOAL_TRANSPARENT`` is keyed by the EXPORTED
    spelling.  Extras: the control constructs, call/1, ``\\+``/not/ignore,
    aggregate_all/3 and bagof/setof's ``^``."""
    from clausal.tools.clausal_to_prolog import GOAL_TRANSPARENT
    for (name, arity), positions in GOAL_POSITIONS.items():
        assert GOAL_TRANSPARENT.get((_pl_name(name), arity)) == positions, (
            name, arity)


@pytest.mark.parametrize("src,want", [
    ("t(X) <- once(q({n: X}))\n",
     "once((dict_pairs(Dict__1, [n - X]), q(Dict__1)))"),
    ("t(X) <- catch_error(q({n: X}), _)\n",
     "catch((dict_pairs(Dict__1, [n - X]), q(Dict__1)), _)"),
], ids=["once", "catch_error"])
def test_the_exporters_dict_literal_hoist_builds_inside_a_goal_argument(src, want):
    """The plain layout's dict-literal hoist (D6) walks the same goal
    positions as the meta-mode walk: a literal in a goal argument is built
    INSIDE that goal, as findall's and forall's always were.  Before, its
    own short table missed once/1 and catch/2 and built it in front."""
    from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
    out = clausal_source_to_prolog(src, module_path="m", module_specs="plain")
    assert want in out


def test_the_translators_goal_names_cover_the_table():
    """``prolog_to_clausal._META_GOAL_ARGS`` is keyed by ``.pl`` NAME only,
    across arities (so ``catch``'s ``(0, 2)`` also serves catch/2): it must
    give each special form exactly its positions within its arity.  Extras:
    call/N, ``\\+``/not/ignore, time/1, phrase, the goal-first list
    builtins, aggregate_all/3, and the database builtins' clause argument."""
    from clausal.tools.prolog_to_clausal import _META_GOAL_ARGS
    for (name, arity), positions in GOAL_POSITIONS.items():
        listed = _META_GOAL_ARGS.get(_pl_name(name), ())
        assert tuple(i for i in listed if i < arity) == positions, (name, arity)


# ── what the agreement changes ─────────────────────────────────────────────


_REGEX_IMPORT = ('-double_quotes(chars)\n'
                 '-import_from(py.re, [match])\n')


def _load_seam(tmp_path, name, src):
    from clausal.import_hook import _load_module
    from tests._suffix import SEAM
    p = tmp_path / f"{name}{SEAM}"
    p.write_text(src)
    return _load_module(name, str(p))


# THE ONE INTENDED EXCEPTION: goal expansion (regex auto-binding, arrow
# patterns) does NOT descend into any meta-call's goal argument.  Decided in
# b9d79200 (2026-10-20, CHANGELOG "a group ... inside a meta-argument binds
# nothing"; docs/regex.md, Auto-Binding): each meta-predicate scopes its
# bindings differently (findall/forall/\+ must not leak them, catch/once
# must), so descending needs a per-predicate rule, not this table.  The
# .clausal singleton lint matches it, and does read this table, so a group
# inside catch_error/2 is reported like one inside catch/3
# (tests/iso_l3/test_l3_regex_named_groups.py, catch_error_group).
@pytest.mark.parametrize("body", [
    'catch_error(match(r"(?P<YEAR>\\d{4})", S), _E)',
    'catch_recover(throw(42), _E, match(r"(?P<YEAR>\\d{4})", S))',
    'catch(match(r"(?P<YEAR>\\d{4})", S), _E, fail)',
    'once(match(r"(?P<YEAR>\\d{4})", S))',
], ids=["catch_error", "catch_recover_recovery", "catch", "once"])
def test_goal_expansion_intentionally_stops_at_a_meta_call(tmp_path, body):
    """A regex group inside a meta-call's goal binds nothing, the same for
    the engine's catch_error/catch_recover as for catch/once."""
    from clausal.logic.cells import chars
    from clausal.logic.solve import call
    from clausal.logic.variables import is_var
    mod = _load_seam(tmp_path, "ge_meta_" + body.split("(")[0],
                     _REGEX_IMPORT + "-allow_singletons\n"
                     f"year(S, YEAR) <- {body}\n")
    y = Var()
    got = [deref(y) for _ in call("year", chars("2026"), y,
                                  module=mod.__dict__["$module"])]
    assert len(got) == 1 and is_var(got[0])


def test_a_term_expansion_helper_called_only_inside_catch_error_is_compiled(tmp_path):
    """term_expansion/4's body reaches its helper through catch_error/2's
    goal: the helper is compiled into the expansion module, so the file
    loads and expands.  Before, it was not reached and the load failed."""
    from clausal.logic.solve import call
    m = _load_seam(tmp_path, "te_helper_catch_error", (
        "-private([fact(_), logged_fact(_)])\n"
        "term_expansion(I, O, S, S) <- catch_error(step(I, O), _E)\n"
        "step(fact(X), [fact(X), logged_fact(X)]),\n"
        "fact(1),\n"
        "fact(2),\n"))
    x = Var()
    assert [deref(x) for _ in call("logged_fact", x,
                                   module=m.__dict__["$module"])] == [1, 2]


# The cut-scope scan's half is tests/iso_l3/test_l3_cut_tabling.py
# (test_the_scan_descends_into_a_literal_call_goals_meta_call).


@pytest.mark.parametrize("src,mode", [
    ("p(D) <- catch_error(call_goal(D, x), _)\n", {0: 1}),
    ("p(D) <- catch_recover(true, _, call_goal(D, x))\n", {0: 1}),
    ("p(D, V) <- freeze(V, call_goal(D, x))\n", {0: 1}),
    ("p(D) <- call_cleanup(true, call_goal(D, x))\n", {0: 1}),
], ids=["catch_error", "catch_recover", "freeze", "call_cleanup"])
def test_the_exporter_infers_a_meta_argument_through_the_engines_forms(src, mode):
    """The exported ``:- meta_predicate`` sees a goal argument passed on
    through catch_error/2 (written ``catch/2``) and its kin."""
    from clausal.tools.clausal_to_prolog import (
        clausal_source_to_prolog_ast, collect_local_meta_modes)
    modes = collect_local_meta_modes(clausal_source_to_prolog_ast(src, strict=True))
    assert list(modes.values()) == [mode]
