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

The goal-taking callees that are NOT special forms (aggregate_all/3,
time_goal, phrase, maplist & co.; ``\\+``/not/ignore; call/N) are the
second table, ``special_forms.GOAL_BUILTINS`` / ``GOAL_CONTROLS`` /
``CLOSURE_CALLERS``, held to their readers the same way.  And every goal
position of every special form has exactly one cut-scope rule in
``compiler/cut_scope`` (transparent, commits or opaque).
"""
from __future__ import annotations

import typing

import pytest

from clausal.logic.special_forms import (
    BUILTIN_GOAL_POSITIONS, CLOSURE_CALLERS, GOAL_BUILTINS, GOAL_CONTROLS,
    GOAL_FIRST_LIST_BUILTINS, GOAL_POSITIONS, SPECIAL_FORMS,
)
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
    argument at run time.  Extras: the control constructs, and every
    goal-taking callee of the second table."""
    from clausal.logic.compiler.cut_scope import _RUN_TIME_META
    assert {name for name, _ in GOAL_POSITIONS} <= _RUN_TIME_META
    assert CLOSURE_CALLERS <= _RUN_TIME_META
    assert {name for name, _ in GOAL_BUILTINS} <= _RUN_TIME_META
    assert {name for name, _ in GOAL_CONTROLS} <= _RUN_TIME_META


# ── every goal position has one scoping rule ───────────────────────────────


def _cut_scope_sets():
    from clausal.logic.compiler import cut_scope
    return {"transparent": cut_scope._TRANSPARENT_TO_CHOICE_POINTS,
            "commits": cut_scope._COMMITS,
            "opaque": cut_scope._OPAQUE_TO_CHOICE_POINTS}


@pytest.mark.parametrize("key", sorted(GOAL_POSITIONS), ids=lambda k: f"{k[0]}/{k[1]}")
def test_every_goal_position_has_one_cut_scope(key):
    """Each goal of each special form is in EXACTLY ONE of cut_scope's
    sets: its choice points survive the meta-call (transparent), the
    meta-call commits to a solution of it (commits), or it is run to
    exhaustion or first failure and leaves nothing (opaque).  A special
    form added without a rule fails here instead of silently being
    "opaque" by absence (count_all, findall, forall and the Cleanups were,
    before 2026-10-20)."""
    from clausal.logic.compiler.cut_scope import _meta_terms
    kind, at = _meta_terms()[key]
    assert sorted(at) == [i + 1 for i in GOAL_POSITIONS[key]]
    for pos, arg_key in at.items():
        hits = [n for n, rows in _cut_scope_sets().items()
                if (kind, arg_key) in rows]
        assert len(hits) == 1, (key, pos, arg_key, hits)


def test_the_cut_scope_sets_name_only_real_goal_positions():
    from clausal.logic.compiler.ir import META_GOAL_POSITIONS
    real = {(k, a) for k, keys in META_GOAL_POSITIONS.items() for a in keys}
    sets = _cut_scope_sets()
    assert set().union(*sets.values()) == real
    assert sum(map(len, sets.values())) == len(real)          # disjoint


def test_the_cut_scope_classification_is_isos():
    """Spot rows, against ISO 7.8.9 (catch/3 is call/1 of Goal and of
    Recovery), 8.15.2 (once(G) is call((G, !))), 8.10 (findall/bagof/setof
    collect every solution) and forall(C, A) = \\+ (C, \\+ A)."""
    sets = _cut_scope_sets()
    assert ("catch", "inner") in sets["transparent"]
    assert ("catch", "recovery") in sets["transparent"]
    assert ("once", "inner") in sets["commits"]
    assert ("call_nth", "inner") in sets["commits"]
    assert ("setup_call_cleanup", "cleanup") in sets["commits"]
    assert ("findall", "inner") in sets["opaque"]
    assert ("forall", "action") in sets["opaque"]


def test_every_commit_is_a_commit_name():
    """The pre-check (cut_scope._may_commit) spots a commit by NAME: each
    meta-call kind with a committing goal is spelled as its special form,
    and is one of the commit names."""
    from clausal.logic.compiler.cut_scope import (
        _COMMIT_NAMES, _COMMITS, _meta_terms)
    kinds = {kind for kind, _ in _COMMITS}
    names = {name for (name, _a), (kind, _at) in _meta_terms().items()
             if kind in kinds}
    assert names == kinds
    assert _COMMIT_NAMES == {"!", "->"} | kinds


def test_tro_classifies_every_meta_kind():
    """A TRO prefix goal must be proved at-most-one-solution: every
    MetaKind is in exactly one of tro's two sets."""
    from clausal.logic.compiler.ir import MetaKind
    from clausal.logic.compiler.tro import (
        _DETERMINISTIC_META_KINDS, _NONDETERMINISTIC_META_KINDS)
    kinds = set(typing.get_args(MetaKind))
    assert _DETERMINISTIC_META_KINDS | _NONDETERMINISTIC_META_KINDS == kinds
    assert not _DETERMINISTIC_META_KINDS & _NONDETERMINISTIC_META_KINDS


def test_term_expansion_helper_reachability_covers_the_table():
    """Extras: call/N's closure, ``\\+``/not/ignore and every goal-taking
    builtin (``_called_positions``).  The seam body's TERM view
    (``_goal_positions``, ``_seam_body_term``) converts the special forms',
    ``\\+``/not/ignore's and aggregate_all/3's only, as it always has."""
    from clausal.logic.term_expansion import (
        _EXTRA_GOAL_ARGS, _called_positions, _goal_positions)
    for (name, arity), positions in GOAL_POSITIONS.items():
        assert _goal_positions(name, arity) == positions, (name, arity)
        assert _called_positions(name, arity) == positions, (name, arity)
    for key, positions in BUILTIN_GOAL_POSITIONS.items():
        assert _called_positions(*key) == positions, key
    assert _goal_positions("call", 3) == (0,)
    assert _called_positions("call_goal", 2) == (0,)
    assert _goal_positions("\\+", 1) == (0,)
    assert _goal_positions("once", 2) == ()       # another arity is a call
    assert _EXTRA_GOAL_ARGS == {
        **{k: (0,) for k in GOAL_CONTROLS},
        ("aggregate_all", 3): BUILTIN_GOAL_POSITIONS[("aggregate_all", 3)]}


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


#: The goal-taking builtins a ``.pl`` file calls by the same name (ISO,
#: SWI library(apply)/library(aggregate), Scryer): the translator lists
#: these.  The rest of GOAL_BUILTINS (take_while, group_by, tfilter ...) are
#: Clausal's own names, which a ``.pl`` file may define for itself with
#: other arguments, so the translator does not read them as goals.
_PL_GOAL_BUILTIN_NAMES = {"aggregate_all", "time", "phrase", "maplist",
                          "foldl", "include", "exclude", "partition"}
#: The database builtins' CLAUSE argument: a translator-only extra (a goal
#: NAME is collected from it, but it is not called).
_PL_CLAUSE_ARG_NAMES = {"assert", "asserta", "assertz", "retract",
                        "retractall", "clause"}


def test_the_translators_other_goal_names_are_the_second_table():
    """Every non-special-form entry of ``prolog_to_clausal._META_GOAL_ARGS``
    is call/N, a GOAL_CONTROLS name, a ``.pl`` name of GOAL_BUILTINS with
    exactly its positions (at every arity of it the engine has), or a
    database builtin's clause argument -- and every such name is there."""
    from clausal.tools.prolog_to_clausal import _META_GOAL_ARGS, _NIL_GOAL_ARGS
    special = {_pl_name(name) for name, _ in GOAL_POSITIONS}
    builtins: dict = {}
    for (name, arity), positions in BUILTIN_GOAL_POSITIONS.items():
        builtins.setdefault(_pl_name(name), set()).add(positions)
    extras = set(_META_GOAL_ARGS) - special
    assert extras == ({"call"} | {n for n, _ in GOAL_CONTROLS}
                      | _PL_GOAL_BUILTIN_NAMES | _PL_CLAUSE_ARG_NAMES)
    for name in {"call"} | {n for n, _ in GOAL_CONTROLS}:
        assert _META_GOAL_ARGS[name] == (0,), name
    for name in _PL_GOAL_BUILTIN_NAMES:
        assert builtins[name] == {_META_GOAL_ARGS[name]}, name
    # A [] there is the goal []/0 only where the argument is a GOAL, not a
    # closure (C), a DCG body (D) or a clause term.
    not_goal = {_pl_name(name) for (name, _), roles in GOAL_BUILTINS.items()
                if set(roles) & {"C", "D"}}
    assert set(_META_GOAL_ARGS) - set(_NIL_GOAL_ARGS) == (
        (not_goal & set(_META_GOAL_ARGS)) | _PL_CLAUSE_ARG_NAMES)


# ── the second table: goal-taking callees that are not special forms ───────


def test_the_second_table_is_well_formed():
    for table in (SPECIAL_FORMS, GOAL_BUILTINS, GOAL_CONTROLS):
        for (name, arity), roles in table.items():
            assert len(roles) == arity, (name, arity)
    assert not set(GOAL_BUILTINS) & set(SPECIAL_FORMS)
    assert not set(GOAL_CONTROLS) & set(SPECIAL_FORMS)
    assert not set(GOAL_BUILTINS) & set(GOAL_CONTROLS)
    assert not CLOSURE_CALLERS & {name for name, _ in SPECIAL_FORMS}
    assert all(BUILTIN_GOAL_POSITIONS.values())


def test_every_goal_builtin_is_an_engine_builtin():
    import clausal.logic.builtins  # noqa: F401 - registers them
    from clausal.logic.builtins._registry import _BUILTINS, _DB_BUILTINS
    missing = [k for k in GOAL_BUILTINS
               if k not in _BUILTINS and k not in _DB_BUILTINS]
    assert missing == []


def test_the_list_builtins_are_the_tables_closure_rows():
    from clausal.logic.builtins import higher_order
    assert higher_order._GOAL_FIRST_LIST_BUILTINS is GOAL_FIRST_LIST_BUILTINS
    assert len(GOAL_FIRST_LIST_BUILTINS) == 25
    assert all(BUILTIN_GOAL_POSITIONS[k] == (0,) for k in GOAL_FIRST_LIST_BUILTINS)


@pytest.mark.parametrize("key", sorted(GOAL_BUILTINS), ids=lambda k: f"{k[0]}/{k[1]}")
def test_clause_2s_goal_positions_are_the_tables(key):
    """clause/2's goal-thunk refusal reads every goal-taking builtin
    (aggregate_all/3's goal was missing until 2026-10-20)."""
    from clausal.logic.builtins import clause_ops
    assert clause_ops._BUILTIN_GOAL_ARGS is BUILTIN_GOAL_POSITIONS
    assert clause_ops._goal_positions(*key, None) == BUILTIN_GOAL_POSITIONS[key]


@pytest.mark.parametrize("key", sorted(GOAL_BUILTINS), ids=lambda k: f"{k[0]}/{k[1]}")
def test_a_dotted_goal_argument_of_every_goal_builtin_is_qualified(key):
    """meta_predicate.builtin_goal_positions marks exactly the table's goal
    positions ``:`` (a dotted ``lib.p`` there is the goal ``lib:p``)."""
    from clausal.logic.meta_predicate import QUALIFIED, builtin_goal_positions
    name, arity = key
    want = tuple(QUALIFIED if i in BUILTIN_GOAL_POSITIONS[key] else "?"
                 for i in range(arity))
    assert builtin_goal_positions(None, name, arity) == want
    assert builtin_goal_positions(None, "call", 3) == (QUALIFIED, "?", "?")
    assert builtin_goal_positions(None, "not_a_goal_builtin", 1) is None


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


@pytest.mark.parametrize("ext", [".pl", ".clausal"])
@pytest.mark.parametrize("body", [
    "maplist(step, [I], [O])",
    "phrase(step2(I, O), [], [])",
    "aggregate_all(count, step(I, O), 1), step(I, O)",
    "call(step, I, O)",
], ids=["maplist", "phrase", "aggregate_all", "call3"])
def test_a_term_expansion_helper_reached_through_a_goal_builtin_is_compiled(
        tmp_path, body, ext):
    """Helper reachability reads every goal-taking builtin of
    ``special_forms.GOAL_BUILTINS``: step/2 reached only as maplist's
    closure, or step2//2 only through phrase/3, is compiled into the
    expansion module.  Before (2026-10-20) its own short table listed
    aggregate_all/3 but not maplist & co. or phrase, and the load failed
    (``step does not accept 2 arguments``; ``no procedure step2/4``)."""
    from clausal.import_hook import _load_module
    from clausal.logic.solve import call
    name = f"te_goal_builtin_{body.split('(')[0]}_{ext[1:]}"
    p = tmp_path / f"{name}{ext}"
    p.write_text(f"term_expansion(I, O, S, S) :- {body}.\n"
                 "step(fact(X), [fact(X), logged_fact(X)]).\n"
                 "step2(I, O) --> [], {step(I, O)}.\n"
                 "fact(1).\nfact(2).\n")
    m = _load_module(name, str(p))
    x = Var()
    assert [deref(x) for _ in call("logged_fact", x, module=m)] == [1, 2]


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


def test_call_body_reads_the_closure_arities_from_the_table():
    from clausal.logic import special_forms
    from clausal.logic.builtins import call_body
    assert call_body._SPECIAL_FORM_MAX_ARITY is special_forms.SPECIAL_FORM_MAX_ARITY
    assert special_forms.SPECIAL_FORM_MAX_ARITY["findall"] == 4
