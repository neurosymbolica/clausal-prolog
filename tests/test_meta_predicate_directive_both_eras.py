"""``-meta_predicate(p(1, '?'))``: Scryer's meta_predicate/1, in both eras.

Operator ruling 2026-09-25 (ruling 1, "follow Scryer").  Ruling S makes a
predicate name passed as data the plain atom, so a higher-order predicate in
another module looked it up in ITS module and silently answered nothing::

    % hutil:  -module(hutil, [apply_all(G, L)])   apply_all(G, L) <- maplist(G, L),
    % hmain:  -import_from(hutil, [apply_all])    my_pred(1),  go() <- apply_all(my_pred, [1]),

Scryer (verified on the box)::

    ?- apply_all(my_pred,[1]).    % error(existence_error(procedure,my_pred/1),my_pred/1)
    :- meta_predicate(apply_all2(1, ?)).
    ?- apply_all2(my_pred,[1]).   % yes

A ``:``/integer spec position is qualified with the CALLER's module
(``M:G`` -- the runtime cell ``(":", M, G)``) unless already qualified;
``'+'``/``'-'``/``'?'`` positions are untouched; the qualified goal resolves
in the caller through call/N, maplist, phrase and time_goal inside the
callee.  Without the declaration the name resolves in the callee and --
ruling 2 (2026-09-25) -- an unknown procedure RAISES.

Handle era (W4b-2d flip): the load binds imports to the owner's handles
itself, so the era fixtures run ``[handle]`` only and assert the import
binding they depend on; the stand-in ``_bind_imports_as_owner_handles`` is
gone (after the flip it re-bound nothing, and the ``[class]`` arms silently
ran the handle era).
"""
from __future__ import annotations

import sys
import textwrap

import pytest

from clausal.logic.atoms import mangle, mint
from clausal import cell_args, cell_functor
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref, is_var, walk
from tests._suffix import SEAM


def _load(tmp_path, monkeypatch, name, body):
    from clausal.import_hook import _load_module
    monkeypatch.syspath_prepend(str(tmp_path))
    p = tmp_path / f"{name}{SEAM}"
    p.write_text(textwrap.dedent(body).lstrip())
    mod = _load_module(name, str(p))
    assert sys.modules[name] is mod
    return mod


def _assert_import_is_owner_handle(module, name, owner_name, functor=None):
    """Ruling D1, done by the LOAD since the W4b-2d flip: the imported
    *name* is bound to the owner's handle.  Replaces the stand-in
    ``_bind_imports_as_owner_handles``, which re-bound classes the load no
    longer leaves (after the flip it re-bound nothing, so the "handle" arm
    and the "class" arm ran the same code)."""
    got = module.module_dict[name]
    assert got == mangle(owner_name, functor or name), (
        f"the load did not bind {name} to {owner_name}'s handle: {got!r}")


_OWNER = """
    -module(mpu_ERA, [apply_all(G, L), apply_all_raw(G, L), call_it(G, X),
                      parse_with(NT, L), time_it(G), collect(G, L),
                      qual_probe(G, Q), colon_probe(M, Q), data_probe(A, B, C, Q),
                      my_map(G, L), last_goal(G, L, Q)])
    -meta_predicate(apply_all(1, '?'), call_it(1, '?'), parse_with(2, '?'),
                    time_it(0), collect(1, '?'), qual_probe(0, '?'),
                    colon_probe(':', '?'), data_probe('+', '-', '?', '?'),
                    my_map(1, '?'), last_goal(1, '?', '?'))
    apply_all(G, L) <- maplist(G, L),
    apply_all_raw(G, L) <- maplist(G, L),
    call_it(G, X) <- call(G, X),
    parse_with(NT, L) <- phrase(NT, L),
    time_it(G) <- time_goal(G),
    collect(G, L) <- findall(X, call(G, X), L),
    qual_probe(G, Q) <- (Q is G),
    colon_probe(M, Q) <- (Q is M),
    data_probe(A, B, C, Q) <- (Q is [A, B, C]),
    my_map(_G, []),
    my_map(G, [H, *T]) <- (call(G, H), my_map(G, T)),
    last_goal(G, [], Q) <- (Q is G),
    last_goal(G, [_H, *T], Q) <- last_goal(G, T, Q),
"""

_IMPORTER = """
    -double_quotes(atom)
    -module(mpm_ERA, [])
    -hide([secret])
    -import_from(mpu_ERA, [apply_all, apply_all_raw, call_it, parse_with,
                           time_it, collect, qual_probe, colon_probe, data_probe,
                           my_map, last_goal])
    my_pred(1),
    my_pred(2),
    greet >> (["h", "i"])
    go_decl() <- apply_all(my_pred, [1, 2]),
    go_decl_miss() <- apply_all(my_pred, [3]),
    go_raw() <- apply_all_raw(my_pred, [1]),
    go_call(X) <- call_it(my_pred, X),
    go_phrase() <- parse_with(greet, ["h", "i"]),
    go_time() <- time_it(my_pred(1)),
    go_collect(L) <- collect(my_pred, L),
    go_meta_call() <- call(apply_all, my_pred, [1]),
    go_qual(Q) <- qual_probe(my_pred, Q),
    go_colon(Q) <- colon_probe(my_pred, Q),
    go_data(Q) <- data_probe(my_pred, my_pred, my_pred, Q),
    pass_through(G, Q) <- qual_probe(G, Q),
    go_map() <- my_map(my_pred, [1, 2, 1]),
    go_last(Q) <- last_goal(my_pred, [1, 2, 3], Q),
    go_hide(Q) <- qual_probe(secret, Q),
    go_map_partial() <- maplist(apply_all(my_pred), [[1], [2]]),
"""

_ALIAS_IMPORTER = """
    -module(mpa_ERA, [])
    -import_from(mpu_ERA, [alias(apply_all, aa)])
    my_pred(1),
    my_pred(2),
    go_a() <- aa(my_pred, [1, 2]),
    go_a_call() <- call(aa, my_pred, [1, 2]),
    go_a_map() <- maplist(aa(my_pred), [[1], [2]]),
"""


@pytest.fixture(params=["handle"])   # W4b-2d: the class era is gone
def pair(request, tmp_path, monkeypatch):
    era = request.param
    ow = _load(tmp_path, monkeypatch, f"mpu_{era}", _OWNER.replace("ERA", era))
    O = ow.__dict__["$module"]
    im = _load(tmp_path, monkeypatch, f"mpm_{era}", _IMPORTER.replace("ERA", era))
    I = im.__dict__["$module"]
    al = _load(tmp_path, monkeypatch, f"mpa_{era}",
               _ALIAS_IMPORTER.replace("ERA", era))
    I.alias_importer = al.__dict__["$module"]
    _assert_import_is_owner_handle(I, "apply_all", f"mpu_{era}")
    _assert_import_is_owner_handle(I.alias_importer, "aa", f"mpu_{era}",
                                   "apply_all")
    return era, O, I


def _n(module, goal, *args):
    return len(list(call(goal, *args, module=module)))


def _one(module, goal):
    q = Var()
    out = [walk(q) for _ in call(goal, q, module=module)]
    assert len(out) == 1, out
    return out[0]


def test_the_declaration_is_recorded_on_the_owner_and_read_through_the_import(pair):
    _era, O, I = pair
    assert O.db.meta_predicate_specs("apply_all", 2) == (1, "?")
    assert I.db.meta_predicate_specs("apply_all", 2) == (1, "?")
    assert I.db.meta_predicate_specs("apply_all_raw", 2) is None


def test_undeclared_the_name_resolves_in_the_callee_and_raises(pair):
    """The HIGH as the controller measured it, now loud (ruling 2): the
    callee's maplist looks ``my_pred`` up in the CALLEE's module."""
    _era, _O, I = pair
    with pytest.raises(LogicException) as exc:
        _n(I, "go_raw")
    formal = cell_args(exc.value.term)[0]
    assert cell_functor(formal) == "existence_error"
    assert cell_args(formal) == (mint("procedure"), ("/", mint("my_pred"), 1))


def test_declared_the_meta_argument_resolves_in_the_caller(pair):
    _era, _O, I = pair
    assert _n(I, "go_decl") == 1
    assert _n(I, "go_decl_miss") == 0          # resolved, and simply fails


def test_meta_arguments_reach_call_n_phrase_time_goal_and_findall(pair, capsys):
    _era, _O, I = pair
    x = Var()
    assert sorted(deref(x) for _ in call("go_call", x, module=I)) == [1, 2]
    assert _n(I, "go_phrase") == 1
    assert _n(I, "go_time") == 1
    assert _one(I, "go_collect") == [1, 2]


def test_a_meta_call_of_a_declared_predicate_qualifies_too(pair):
    """``call(apply_all, my_pred, L)`` -- Scryer's expand_call_goal."""
    _era, _O, I = pair
    assert _n(I, "go_meta_call") == 1


def test_a_python_query_qualifies_with_the_query_module(pair):
    _era, _O, I = pair
    assert _n(I, "apply_all", "my_pred", [1]) == 1


@pytest.mark.parametrize("goal, spec", [("go_qual", "0"), ("go_colon", ":")])
def test_each_qualifying_spec_kind_qualifies_with_the_caller(pair, goal, spec):
    era, _O, I = pair
    assert _one(I, goal) == (":", f"mpm_{era}", "my_pred"), spec


def test_plus_minus_and_question_positions_are_untouched(pair):
    _era, _O, I = pair
    assert _one(I, "go_data") == ["my_pred", "my_pred", "my_pred"]


def test_an_already_qualified_argument_is_left_alone(pair):
    era, _O, I = pair
    q = Var()
    already = (":", "somewhere_else", "p")
    assert [walk(q) for _ in call("pass_through", already, q, module=I)] == [already]
    # ... and a plain one bound at run time is qualified.
    q = Var()
    assert [walk(q) for _ in call("pass_through", "p", q, module=I)] == [
        (":", f"mpm_{era}", "p")]


def test_a_malformed_declaration_is_a_load_error(tmp_path, monkeypatch):
    """Scryer's setup_meta_predicate accepts only + - ? : and integers;
    ``^`` and ``//`` are an InvalidMetaPredicateDecl there."""
    for bad in ("p('^')", "p('//')", "p(-1)", "p(x)"):
        with pytest.raises(SyntaxError, match="meta"):
            _load(tmp_path, monkeypatch, "mp_bad",
                  f"-module(mp_bad, [p(A)])\n-meta_predicate({bad})\np(_A),\n")
        sys.modules.pop("mp_bad", None)


def test_a_recursive_meta_predicate_runs_and_never_nests_the_qualification(pair):
    """The owner's own recursive tail call re-qualifies G with the OWNER's
    module at each step -- which leaves an already-qualified G alone, so the
    caller's qualification survives unnested (Scryer: HeadVars)."""
    era, _O, I = pair
    assert _n(I, "go_map") == 1
    assert _one(I, "go_last") == (":", f"mpm_{era}", "my_pred")


def test_a_db_less_compile_of_a_rule_with_a_body_call_still_works():
    """roborev HIGH (2026-09-25): with ``db=None`` the compiler's ``ctx.db`` is
    ``globals_env._GlobalsDb``, which implements only ``signature_for``; the
    -meta_predicate lookup in terms_to_goalop called
    ``db.meta_predicate_specs`` on it and every body call raised
    ``AttributeError``.  The db-less recipe (``make_predicate``'s hand-built
    globals) is supported.  (W4b-3 slice 6: the recipe's callee is the
    frozen ``_get_dispatch`` protocol on a plain object, and the caller is
    driven through the dispatch the compile returns -- ``make_predicate``,
    which supplied both as classes, was retired.)"""
    from clausal.logic.compiler import compile_predicate_trampoline
    from clausal.logic.database import Clause
    from clausal.terms import Call, LoadName
    from tests.predicate_api_support import (
        ForeignPredicate, dispatch_solutions)

    x = Var()
    base = compile_predicate_trampoline(
        "mp_dbless_base", 1, [Clause(("mp_dbless_base", 1), [])])
    top = compile_predicate_trampoline(
        "mp_dbless_top", 1,
        [Clause(("mp_dbless_top", x),
                [Call(func=LoadName(name="mp_dbless_base"),
                      args=[x], kwargs=[])])],
        globals_={"mp_dbless_base": ForeignPredicate(base)})
    assert dispatch_solutions(top, Var()) == [(1,)]


@pytest.mark.parametrize("goal", ["go_a", "go_a_call", "go_a_map"])
def test_a_meta_predicate_imported_under_an_alias_qualifies(pair, goal):
    """roborev MEDIUM (2026-09-25): under ``alias(apply_all, aa)`` a goal
    built through the alias carries the OWNER's functor, and call/N's
    aliased branch looked the declaration up under that spelling -- but the
    adopted row is keyed by the LOCAL alias, so it missed and never
    qualified.  Direct call, call/N and maplist."""
    _era, _O, I = pair
    A = I.alias_importer
    assert A.db.meta_predicate_specs("aa", 2) == (1, "?")
    assert _n(A, goal) == 1


def test_a_hide_data_atom_is_qualified_not_taken_for_a_handle(pair):
    """roborev LOW (2026-09-25): a ``-hide`` DATA atom is mangled like a
    predicate handle but names no predicate, so it is not "already
    qualified" -- it is qualified with the caller like any other atom."""
    era, _O, I = pair
    secret = mangle(f"mpm_{era}", "secret")
    assert _one(I, "go_hide") == (":", f"mpm_{era}", secret)


def test_a_partial_meta_goal_through_maplist_qualifies_with_the_caller(pair):
    """``maplist(apply_all(my_pred), [[1], [2]])``.  In the handle era the
    cell built through the import carries the OWNER's handle in slot 0, and
    re-entering it as ``M:G`` qualified ``my_pred`` with the owner (found
    while fixing the roborev MEDIUM, 2026-09-25); the caller's own import is
    the caller's reference, as in the class era."""
    _era, _O, I = pair
    assert _n(I, "go_map_partial") == 1


# ── A goal-passing library across modules (2026-09-25) ─────────────────────
#
# Two shapes found FAILING SILENTLY once the library
# declared -meta_predicate.  Scryer (verified on the box) answers both:
#
#     :- meta_predicate(run_all(?, ?, 4, ?)).
#     run_all([R|RS], P, G, [row(R,S,C)|IS]) :- call(G, R, P, S, C), ...
#     qa(CL) :- slib:run_all([k1], ctx, sdom:check, CL).  % [row(k1,yes,1)]
#     qb(R)  :- wrap(s, [k1], ctx, check, R).              % out(s,[row(k1,yes,1)])
#     qc(R)  :- top(check, [k1], R).        % 3-deep     % out(s,[row(k1,yes,1)])
#     catch(slib:run_all([k1], ctx, sdom:nosuch, _), E, true)
#                                   % E = error(existence_error(procedure,nosuch/4),_)
#
# Root cause: a dotted ``m.p`` reference in data position is p's CLASS (a
# goal OBJECT, not a name); ``$meta_qualify`` wrapped it as ``(":", M, Cls)``
# and the qualified arm handed Cls to the NAME resolver, which answers None
# for a non-name -- no solution, no error.

_GLIB = """
    -module(mglib_ERA, [ev1(G, X), ev2(G, X, Y), ev3(G, X, Y, Z),
                        run_all(RS, P, G, IS), wrap(S, KS, P, G, OUT),
                        top(G, KS, R), parse_with(NT, L)])
    -private([row(R, S, C), out(S, CL), s, ctx])
    -meta_predicate(ev1(1, '?'), ev2(2, '?', '?'), ev3(3, '?', '?', '?'),
                    run_all('?', '?', 4, '?'), wrap('?', '?', '?', 4, '?'),
                    top(4, '?', '?'), parse_with(2, '?'))
    ev1(G, X) <- call_goal(G, X),
    ev2(G, X, Y) <- call_goal(G, X, Y),
    ev3(G, X, Y, Z) <- call_goal(G, X, Y, Z),
    run_all([], _, _, []),
    run_all([R, *RS], P, G, [I, *IS]) <- (call_goal(G, R, P, S, C), I is row(R, S, C), run_all(RS, P, G, IS))
    wrap(S, KS, P, G, OUT) <- (run_all(KS, P, G, CL), OUT is out(S, CL))
    top(G, KS, R) <- wrap(s, KS, ctx, G, R)
    parse_with(NT, L) <- phrase(NT, L)
"""

_GRULES = """
    -module(mgrules_ERA, [ext_check(A, B, C, D)])
    -private([k1, ctx, yes])
    ext_check(k1, ctx, yes, 3),
"""

_GDOM = """
    -double_quotes(atom)
    -module(mgdom_ERA, [check(A, B, C, D), g1a(X), g2a(X, Y), g3a(X, Y, Z),
                        greet/2])
    -import_module(mglib_ERA)
    -import_module(mgdom_ERA)
    -import_from(mglib_ERA, [ev1, ev2, ev3, run_all, wrap, top, parse_with])
    -import_from(mgrules_ERA, [ext_check])
    -private([ctx, k1, s, yes])
    check(k1, ctx, yes, 1),
    g1a(1),
    g2a(1, 2),
    g3a(1, 2, 3),
    a_dotted(CL) <- mglib_ERA.run_all([k1], ctx, mgdom_ERA.check, CL)
    a_imported(CL) <- run_all([k1], ctx, mgdom_ERA.check, CL)
    a_bare(CL) <- run_all([k1], ctx, check, CL)
    a_other_module(CL) <- run_all([k1], ctx, ext_check, CL)
    b_bare(R) <- wrap(s, [k1], ctx, check, R)
    b_dotted(R) <- wrap(s, [k1], ctx, mgdom_ERA.check, R)
    b_other_module(R) <- wrap(s, [k1], ctx, ext_check, R)
    greet >> (["h", "i"])
    p_bare() <- parse_with(greet, ["h", "i"]),
    p_dotted() <- parse_with(mgdom_ERA.greet, ["h", "i"]),
    c_three_deep(R) <- top(check, [k1], R)
    c_three_deep_dotted(R) <- top(mgdom_ERA.check, [k1], R)
    pass4(G, CL) <- run_all([k1], ctx, G, CL)
    x1(X) <- ev1(g1a, X)
    x2(Y) <- ev2(g2a, 1, Y)
    x3(Z) <- ev3(g3a, 1, 2, Z)
    x1_dotted(X) <- ev1(mgdom_ERA.g1a, X)
    x2_dotted(Y) <- ev2(mgdom_ERA.g2a, 1, Y)
    x3_dotted(Z) <- ev3(mgdom_ERA.g3a, 1, 2, Z)
"""

_ROW1 = [("row", "k1", "yes", 1)]


@pytest.fixture(params=["handle"])   # W4b-2d: the class era is gone
def glib(request, tmp_path, monkeypatch):
    era = request.param
    _load(tmp_path, monkeypatch, f"mglib_{era}", _GLIB.replace("ERA", era))
    _load(tmp_path, monkeypatch, f"mgrules_{era}", _GRULES.replace("ERA", era))
    dom = _load(tmp_path, monkeypatch, f"mgdom_{era}", _GDOM.replace("ERA", era))
    D = dom.__dict__["$module"]
    _assert_import_is_owner_handle(D, "run_all", f"mglib_{era}")
    return era, D


@pytest.mark.parametrize("goal, want", [
    ("a_dotted", _ROW1),                       # shape (a), as reported
    ("a_imported", _ROW1),
    ("a_bare", _ROW1),
    ("a_other_module", [("row", "k1", "yes", 3)]),
    ("b_bare", ("out", "s", _ROW1)),           # shape (b), as reported
    ("b_dotted", ("out", "s", _ROW1)),
    ("b_other_module", ("out", "s", [("row", "k1", "yes", 3)])),
    ("c_three_deep", ("out", "s", _ROW1)),
    ("c_three_deep_dotted", ("out", "s", _ROW1)),
])
def test_a_goal_passed_across_modules_through_meta_arguments(glib, goal, want):
    _era, D = glib
    assert _one(D, goal) == want


@pytest.mark.parametrize("goal, want", [
    ("x1", 1), ("x2", 2), ("x3", 3),
    ("x1_dotted", 1), ("x2_dotted", 2), ("x3_dotted", 3),
])
def test_extra_argument_counts_one_to_three(glib, goal, want):
    """call_goal/N with 1..3 extras onto a bare and a dotted meta-argument
    (4 extras is run_all above)."""
    _era, D = glib
    assert _one(D, goal) == want


def test_bare_vs_m_colon_g_vs_class_goal_handed_in_at_run_time(glib):
    era, D = glib
    cls_or_handle = D.module_dict["check"]
    for g in ("check", (":", f"mgdom_{era}", "check"), cls_or_handle,
              (":", f"mgdom_{era}", cls_or_handle)):
        assert _one_with(D, "pass4", g) == _ROW1, g


def test_a_qualified_goal_naming_a_missing_predicate_raises(glib):
    """Ruling 2: never a silent failure."""
    era, D = glib
    with pytest.raises(LogicException) as exc:
        _one_with(D, "pass4", (":", f"mgdom_{era}", "nosuch"))
    formal = cell_args(exc.value.term)[0]
    assert cell_functor(formal) == "existence_error"
    assert cell_args(formal)[1] == ("/", mint("nosuch"), 4)


def _one_with(module, goal, arg):
    q = Var()
    out = [walk(q) for _ in call(goal, arg, q, module=module)]
    assert len(out) == 1, out
    return out[0]


@pytest.mark.parametrize("goal", ["p_bare", "p_dotted"])
def test_a_nonterminal_passed_across_modules_to_phrase(glib, goal):
    _era, D = glib
    assert _n(D, goal) == 1


def test_phrase_resolves_m_colon_a_nonterminal_class(glib):
    """``M:NT`` whose NT is a goal OBJECT (the class) -- phrase's qualified
    arm handed it to the name resolver, which answered None."""
    era, D = glib
    nt = D.module_dict["greet"]
    for g in ("greet", (":", f"mgdom_{era}", "greet"), nt,
              (":", f"mgdom_{era}", nt)):
        assert _n(D, "parse_with", g, ["h", "i"]) == 1, g


# ── A lambda as a meta-argument (2026-09-25) ───────────────────────────────
#
# Found in a trial: an inline lambda handed to a meta-declared argument raised
# ``NameError: name 'U' is not defined`` (a Python error, not a logic one).
# Root cause: the lambda-hoisting walk (``control_constructs.
# _hoist_lambdas_in_term``) did not descend into the ``MetaArg`` marker, so
# the lambda reached ``term_to_ast_expr`` as a raw ``Lambda`` node and its
# parameter names were referenced in the CALLER's scope.  A lambda literal is
# now not wrapped at all (a closure compiled in its defining module, whose
# body's names resolve there -- Scryer qualifies a yall lambda with its
# defining module), and the walk hoists inside the marker for a lambda nested
# in a compound.

_LLIB = """
    -module(mllib_ERA, [e0(G), e1(G, X), e2(G, X, Y), e3(G, X, Y, Z),
                        h1(X, G, V), h2(X, G, V), h3(X, G, V), cprobe(M, Q),
                        decide(B, V)])
    -meta_predicate(e0(0), e1(1, '?'), e2(2, '?', '?'), e3(3, '?', '?', '?'),
                    h1('?', 2, '?'), h2('?', 2, '?'), h3('?', 2, '?'),
                    cprobe(':', '?'))
    -private([lib_version])
    e0(G) <- call_goal(G),
    e1(G, X) <- call_goal(G, X),
    e2(G, X, Y) <- call_goal(G, X, Y),
    e3(G, X, Y, Z) <- call_goal(G, X, Y, Z),
    h1(X, G, V) <- call_goal(G, X, V),
    h2(X, G, V) <- h1(X, G, V),
    h3(X, G, V) <- h2(X, G, V),
    cprobe(M, Q) <- (Q is M),
    decide(_B, lib_version),
"""

_LDOM = """
    -module(mldom_ERA, [mark(X)])
    -import_module(mldom_ERA)
    -import_module(mllib_ERA)
    -import_from(mllib_ERA, [e0, e1, e2, e3, h1, h2, h3, cprobe])
    -private([box(X), seen])
    decide(B, V) <- (V is B),
    mark(seen),
    z0() <- e0((() <- mark(seen))),
    z1(X) <- e1((A <- (A is 1)), X),
    z2(Y) <- e2(((A, B) <- eval_(A + 1, B)), 1, Y),
    z3(Z) <- e3(((A, B, C) <- eval_(A + B, C)), 1, 2, Z),
    hop1(V) <- (K is 1000, h1(2, ((U, W) <- (eval_(U * K, B), decide(B, W))), V)),
    hop2(V) <- (K is 1000, h2(2, ((U, W) <- (eval_(U * K, B), decide(B, W))), V)),
    hop3(V) <- (K is 1000, h3(2, ((U, W) <- (eval_(U * K, B), decide(B, W))), V)),
    nested(T) <- cprobe(box((A <- (A is 7))), T),
    colon_lambda(T) <- cprobe((A <- (A is 7)), T),
    colon_class(T) <- cprobe(mldom_ERA.mark, T),
    colon_foreign(T) <- cprobe(mllib_ERA.decide, T),
    colon_pass(G, T) <- cprobe(G, T),
"""


@pytest.fixture(params=["handle"])   # W4b-2d: the class era is gone
def llib(request, tmp_path, monkeypatch):
    era = request.param
    _load(tmp_path, monkeypatch, f"mllib_{era}", _LLIB.replace("ERA", era))
    dom = _load(tmp_path, monkeypatch, f"mldom_{era}", _LDOM.replace("ERA", era))
    D = dom.__dict__["$module"]
    _assert_import_is_owner_handle(D, "cprobe", f"mllib_{era}")
    return era, D


def test_a_lambda_with_zero_extras(llib):
    _era, D = llib
    assert _n(D, "z0") == 1


@pytest.mark.parametrize("goal, want", [("z1", 1), ("z2", 2), ("z3", 3)])
def test_a_lambda_with_one_to_three_extras(llib, goal, want):
    _era, D = llib
    assert _one(D, goal) == want


@pytest.mark.parametrize("goal", ["hop1", "hop2", "hop3"])
def test_a_lambda_through_one_to_three_meta_hops_with_a_captured_variable(llib, goal):
    """K is captured from the enclosing clause; the body's bare ``decide``
    is the DOMAIN's (the library exports a ``decide`` too, answering
    ``lib_version``): a lambda resolves in its defining module."""
    _era, D = llib
    assert _one(D, goal) == 2000


def test_a_lambda_nested_in_a_compound_in_a_colon_position(llib):
    """The hoisting walk descends into the meta-argument marker: the compound
    arrives qualified, with a callable closure inside, not a raw node."""
    era, D = llib
    q = _one(D, "nested")
    assert q[:2] == (":", f"mldom_{era}")
    functor, closure = q[2]
    assert functor == "box" and callable(closure)


# ── A Python-written closure as a meta-argument (2026-09-25) ───────────────
#
# A plain Python simple-mode goal function ``fn(*args, trail, k)``, built in
# Python and handed into a query, is a goal OBJECT: a meta-declared position
# leaves it unwrapped and call_goal runs it, exactly as without the
# declaration.  Pinned through one and two meta hops, both eras, through the
# ``call`` Python entry, through a clause that passes it on, and (since
# 2026-09-30) inside a ``solve`` CELL goal -- which the query compiler used to
# refuse (``term_to_ast_expr: unsupported term type function``; todo/done/
# solve-cell-goal-with-a-raw-python-function-is-refused-2026-09-25.md).

_CLIB = """
    -module(mclib_ERA, [c1(LO, G, OUT), c2(LO, G, OUT)])
    -meta_predicate(c1('?', 2, '?'), c2('?', 2, '?'))
    c1(LO, G, OUT) <- call_goal(G, LO, OUT),
    c2(LO, G, OUT) <- c1(LO, G, OUT),
"""

_CDOM = """
    -module(mcdom_ERA, [])
    -import_from(mclib_ERA, [c1, c2])
    via1(G, OUT) <- c1(2, G, OUT),
    via2(G, OUT) <- c2(2, G, OUT),
"""


def _python_probe(x, status, trail, k):
    from clausal.logic.variables import unify
    if unify(status, deref(x) * 10, trail):
        yield None


@pytest.fixture(params=["handle"])   # W4b-2d: the class era is gone
def clib(request, tmp_path, monkeypatch):
    era = request.param
    lib = _load(tmp_path, monkeypatch, f"mclib_{era}", _CLIB.replace("ERA", era))
    L = lib.__dict__["$module"]
    dom = _load(tmp_path, monkeypatch, f"mcdom_{era}", _CDOM.replace("ERA", era))
    D = dom.__dict__["$module"]
    _assert_import_is_owner_handle(D, "c1", f"mclib_{era}")
    return L, D


@pytest.mark.parametrize("hop", ["c1", "c2"])
@pytest.mark.parametrize("where", ["library", "importer"])
def test_a_python_written_closure_runs_through_meta_hops(clib, hop, where):
    L, D = clib
    module = L if where == "library" else D
    out = Var()
    assert [walk(out) for _ in call(hop, 3, _python_probe, out, module=module)] == [30]


@pytest.mark.parametrize("via", ["via1", "via2"])
def test_a_python_written_closure_passed_on_by_a_clause(clib, via):
    _L, D = clib
    out = Var()
    assert [walk(out) for _ in call(via, _python_probe, out, module=D)] == [20]


class _ProbeHolder:
    def probe(self, x, status, trail, k):
        yield from _python_probe(x, status, trail, k)


def _closures():
    import functools
    return {"function": _python_probe,
            "bound method": _ProbeHolder().probe,
            "partial": functools.partial(_python_probe)}


@pytest.mark.parametrize("kind", ["function", "bound method", "partial"])
@pytest.mark.parametrize("hop", ["c1", "c2"])
@pytest.mark.parametrize("where", ["library", "importer"])
def test_a_python_written_closure_in_a_solve_cell_goal(clib, hop, where, kind):
    from clausal.logic.solve import solve
    L, D = clib
    module = L if where == "library" else D
    out = Var()
    fn = _closures()[kind]
    assert [walk(out) for _ in solve((hop, 3, fn, out), module)] == [30]


def test_a_function_in_goal_position_is_not_parameterized():
    """Only ARGUMENT positions pass a function by reference: the goal itself
    and a conjunct of a conjunction tuple are left as written."""
    from clausal.logic.solve import _parameterize_opaque
    params = []
    assert _parameterize_opaque(_python_probe, params) is _python_probe
    conj = (_python_probe, ("q", 1))
    assert _parameterize_opaque(conj, params) is conj
    assert params == []
    nested = ("p", (_python_probe, 1))
    out = _parameterize_opaque(nested, params)
    assert len(params) == 1 and params[0][1] is _python_probe
    assert out[1][0] is params[0][0]


# ── A lambda NODE built in Python and handed to a query (2026-09-25) ───────
#
# Found in a trial: a ``Lambda`` node built from Python and passed in a
# ``solve`` goal to a meta-declared argument raised ISO
# ``type_error(callable, "lambda X, Y: ...")`` where the undeclared
# library runs it.  The same cause as the source-lambda NameError above: the
# lambda was not hoisted out of the ``MetaArg`` marker, and one whose body
# names nothing the lowering must bind reached run time as the raw node, which
# ``_ensure_trampoline_dispatch`` refuses.  Pinned as "declared answers exactly
# what undeclared answers", through 1..3 hops.

_PLIB = """
    -module(mplib_DECL, [p1(LO, G, OUT), p2(LO, G, OUT), p3(LO, G, OUT),
                         tprobe(D, X, S)])
    META
    p1(LO, G, OUT) <- call_goal(G, LO, OUT),
    p2(LO, G, OUT) <- p1(LO, G, OUT),
    p3(LO, G, OUT) <- p2(LO, G, OUT),
    tprobe(_, X, S) <- eval_(X * 10, S),
"""


def _python_lambdas():
    """Two well-formed Python-built lambdas: one whose body refers to its
    parameters by name (it was a NameError), one whose body names nothing
    the lowering must bind (it reached run time as the raw node: the
    type_error(callable, "lambda X, Y: ...") of the trial)."""
    from clausal.terms import Call, DictTerm, LoadName
    import clausal.pythonic_ast.nodes as sa

    def params(*names):
        return sa.Params(params=[sa.PosOrKwParam(name=n) for n in names])

    by_name = sa.Lambda(
        params=params("X", "Y"),
        body=Call(func=LoadName(name="tprobe"),
                  args=[DictTerm({"k": 1}), LoadName(name="X"), LoadName(name="Y")],
                  kwargs=[]))
    no_names = sa.Lambda(
        params=params("X", "Y"),
        body=Call(func=LoadName(name="tprobe"),
                  args=[DictTerm({"k": 1}), 1, 10], kwargs=[]))
    return [("by_name", by_name, [20]), ("no_names", no_names, None)]


_PDOM = """
    -module(mpdom_ERA, [])
    -import_from(mplib_declared_ERA, [p1, p2, p3, tprobe])
"""


@pytest.mark.parametrize("hop", ["p1", "p2", "p3"])
@pytest.mark.parametrize("where", ["declared", "undeclared", "handle"])
def test_a_python_built_lambda_node_in_a_query(tmp_path, monkeypatch, hop, where):
    """declared / undeclared: the query runs in the library itself (the
    trial's shape).  handle: it runs in a module importing the declared
    library, whose imports the load bound to the library's handles (the
    class arm is gone with the class era)."""
    from clausal.logic.solve import solve
    decl = "undeclared" if where == "undeclared" else "declared"
    meta = ("-meta_predicate(p1('?', 2, '?'), p2('?', 2, '?'), p3('?', 2, '?'))"
            if decl == "declared" else "")
    tag = f"{decl}_{where}"
    lib = _load(tmp_path, monkeypatch, f"mplib_{tag}",
                _PLIB.replace("DECL", tag).replace("META", meta))
    L = lib.__dict__["$module"]
    if where == "handle":
        dom = _load(tmp_path, monkeypatch, f"mpdom_{where}",
                    _PDOM.replace("ERA", where))
        L = dom.__dict__["$module"]
        _assert_import_is_owner_handle(L, hop, f"mplib_{tag}")
    ref = _load(tmp_path, monkeypatch, f"mplib_ref_{where}",
                _PLIB.replace("DECL", f"ref_{where}").replace("META", ""))
    R = ref.__dict__["$module"]

    def answers(module, lam):
        out = Var()
        return [("unbound" if is_var(v) else v)
                for v in (walk(out) for _ in solve((hop, 2, lam, out), module))]

    for label, lam, want in _python_lambdas():
        got = answers(L, lam)
        # Exactly what an UNDECLARED library answers for the same lambda.
        assert got == answers(R, lam), (label, got)
        if want is not None:
            assert got == want, (label, got)
        else:
            assert got == ["unbound"], (label, got)


def test_a_colon_position_always_qualifies_even_a_goal_object(llib):
    """roborev MEDIUM (2026-09-25): ``:`` is module-sensitive DATA, and
    Scryer always hands it over as M:X -- a yall lambda there arrives as
    ``cd:[X]>>true`` (verified on the box).  The goal-object and
    lambda-literal exemptions are for GOAL (integer) positions only: a bare
    lambda, a bare class and a Python function in cprobe's ``:`` position
    arrive qualified."""
    era, D = llib
    q = _one(D, "colon_lambda")
    assert q[:2] == (":", f"mldom_{era}") and callable(q[2])
    # A WRITTEN dotted name ``mldom.mark`` is the qualified goal
    # ``mldom:mark`` (operator ruling 2026-09-25, see
    # test_meta_arg_dotted_is_qualified_goal) -- not the class object.
    q = _one(D, "colon_class")
    # A predicate HANDLE (``mldom_ERA.mark``) is spelled M:X with the
    # handle's OWNER as M and the PLAIN name as X (operator ruling
    # 2026-09-25, the always-plain ruling: data never carries a mangled
    # name).  It used to arrive bare, as the mangled handle itself.
    assert D.module_dict["mark"] == mangle(f"mldom_{era}", "mark")
    assert q == (":", f"mldom_{era}", "mark")
    t = Var()
    assert [walk(t) for _ in call("cprobe", _python_probe, t, module=D)] == [
        (":", f"mldom_{era}", _python_probe)]


def test_a_handle_in_a_colon_position_is_qualified_with_its_owner(llib):
    """Operator ruling 2026-09-25: M is the handle's OWNER, not the caller.
    ``mldom_ERA`` (the caller) passes ``mllib_ERA.decide`` -- a handle
    owned by ``mllib_ERA`` -- to ``cprobe``'s ``:`` position, both from a
    compiled body call and from the Python ``call`` entry."""
    from clausal.logic.predicate import mint_predicate_handle
    era, D = llib
    lib = sys.modules[f"mllib_{era}"].__dict__["$module"]
    want = (":", f"mllib_{era}", "decide")
    assert _one(D, "colon_foreign") == want
    t = Var()
    handle = mint_predicate_handle(lib.db, "decide")
    assert [walk(t) for _ in call("cprobe", handle, t, module=D)] == [want]
    # a GOAL (integer) position passes the same handle as it is: it is a
    # goal object that already resolves to its owner
    from clausal.logic.meta_predicate import qualify
    assert qualify(f"mldom_{era}", handle, 1, D.db) == handle
    assert qualify(f"mldom_{era}", handle, ":", D.db) == want


def test_a_handle_functored_cell_in_a_colon_position_is_owner_and_plain(llib):
    """Coordinator relay of the standing rulings, 2026-09-25: a CELL whose
    functor is a declared predicate handle, ``(handle, X, ...)``, in a
    ``:`` position is ``(":", <owner designator>, (plain_name, X, ...))``
    -- the designator ``cells.qualify_mangled_goal`` uses.  It used to be
    wrapped with the CALLER's module around the still-mangled cell.  The
    caller is ``mldom_ERA``, the owner ``mllib_ERA``."""
    from clausal.logic.meta_predicate import qualify
    from clausal.logic.predicate import mint_predicate_handle
    era, D = llib
    lib = sys.modules[f"mllib_{era}"].__dict__["$module"]
    handle = mint_predicate_handle(lib.db, "decide")
    want = (":", f"mllib_{era}", ("decide", 1, "seen"))
    t = Var()
    # compiled call site (``$meta_qualify`` at run time: the cell arrives
    # through a variable, the way a handle-functored cell reaches one)
    assert [walk(t) for _ in call("colon_pass", (handle, 1, "seen"), t,
                                  module=D)] == [want]
    t = Var()
    assert [walk(t) for _ in call("cprobe", (handle, 1, "seen"), t,
                                  module=D)] == [want]    # Python entry
    x = Var()
    got = qualify(f"mldom_{era}", (handle, x), ":", D.db)
    assert got[:2] == (":", f"mllib_{era}") and got[2][0] == "decide"
    assert got[2][1] is x                                 # args kept as-is
    # a GOAL (integer) position is unchanged by this ruling
    assert qualify(f"mldom_{era}", (handle, x), 1, D.db) == (
        ":", f"mldom_{era}", (handle, x))


def test_a_unit_quantity_in_a_goal_position_is_qualified_then_refused(llib):
    """roborev LOW (2026-09-25): ``callable()`` was the goal-object test, and
    a unit Quantity is callable (``byte(4)``), so it skipped qualification.
    It is qualified now, and ``M:Quantity`` is ISO type_error(callable, Q)
    -- Scryer's answer for ``call(lists:5)`` -- where the name resolver used
    to answer nothing."""
    from clausal.logic.meta_predicate import is_goal_object, qualify
    from clausal.modules.units import byte
    era, D = llib
    assert not is_goal_object(byte)
    assert qualify("m", byte, 1) == (":", "m", byte)
    with pytest.raises(LogicException) as exc:
        list(call("e1", byte, Var(), module=D))
    formal = cell_args(exc.value.term)[0]
    assert cell_functor(formal) == "type_error" and cell_args(formal)[0] == "callable"
    assert cell_args(formal)[1] is byte


@pytest.mark.parametrize("goal", [(":", "somewhere", Var()), (":", "somewhere", 5)])
def test_a_qualified_non_goal_raises_like_scryer(llib, goal):
    """``M:_`` is instantiation_error, ``M:5`` type_error(callable, 5) --
    Scryer's answers; this arm used to fail silently."""
    era, D = llib
    goal = (":", f"mldom_{era}", goal[2])
    with pytest.raises(LogicException) as exc:
        list(call("e0", goal, module=D))
    formal = cell_args(exc.value.term)[0]
    if is_var(goal[2]):
        assert formal == "instantiation_error"
    else:
        assert cell_functor(formal) == "type_error" and cell_args(formal) == ("callable", 5)


# ── An aliased import passed as data: the WRITTEN name (2026-09-25) ────────
#
# roborev MEDIUM: a bare predicate name in data position used to become the
# atom of the binding's OWN (owner's) name.  Under ``alias(p, q)`` in a module
# that defines its own ``p``, that ran the LOCAL p (or raised
# PredicateArityMismatchError when the local p has another arity).  Scryer
# passes ``q`` and resolves it through the import.  In clause source the
# import rewrite already spelled the reference as the dotted binding; the
# owner-name atom came from the ruling-S LoadName arm (a query built with
# ``LoadName``) and the query-parameter path (a Python-held binding).

_AOWNER = """
    -module(maow_ERA, [p(X), ap(G, L)])
    -private([owner])
    -meta_predicate(ap(1, '?'))
    p(owner),
    ap(G, L) <- maplist(G, L),
"""

_AUSER_SAME = """
    -module(mau_same_ERA, [])
    -import_from(maow_ERA, [alias(p, q), ap])
    -private([local, owner])
    p(local),
    m1(L) <- maplist(q, L),
    c1(X) <- call(q, X),
    a1(L) <- ap(q, L),
"""

_AUSER_OTHER = """
    -module(mau_other_ERA, [])
    -import_from(maow_ERA, [alias(p, q), ap])
    -private([local, owner])
    p(local, local),
    m1(L) <- maplist(q, L),
    c1(X) <- call(q, X),
    a1(L) <- ap(q, L),
"""


@pytest.fixture(params=[(e, k) for e in ("handle",) for k in ("same", "other")],
                ids=lambda p: f"{p[0]}-{p[1]}-arity")
def aliased(request, tmp_path, monkeypatch):
    era, kind = request.param
    _load(tmp_path, monkeypatch, f"maow_{era}", _AOWNER.replace("ERA", era))
    src = (_AUSER_SAME if kind == "same" else _AUSER_OTHER).replace("ERA", era)
    us = _load(tmp_path, monkeypatch, f"mau_{kind}_{era}", src)
    U = us.__dict__["$module"]
    _assert_import_is_owner_handle(U, "q", f"maow_{era}", "p")
    return U


def test_an_aliased_name_in_source_resolves_through_the_import(aliased):
    U = aliased
    assert _n(U, "m1", ["owner"]) == 1 and _n(U, "m1", ["local"]) == 0
    x = Var()
    assert [walk(x) for _ in call("c1", x, module=U)] == ["owner"]
    assert _n(U, "a1", ["owner"]) == 1       # and as a -meta_predicate argument


def test_an_aliased_binding_in_a_python_query_is_the_written_name(aliased):
    from clausal.logic.solve import solve
    from clausal.terms import Call, LoadName
    U = aliased
    binding = U.module_dict["q"]
    by_binding = ("maplist", binding, ["owner"])
    by_loadname = Call(func=LoadName(name="maplist"),
                       args=[LoadName(name="q"), ["owner"]], kwargs=[])
    for goal in (by_binding, by_loadname, ("maplist", "q", ["owner"])):
        assert len(list(solve(goal, U))) == 1, goal


# ── TRO through a -meta_predicate self-call (2026-09-25) ───────────────────

def test_tro_sees_a_meta_argument_passed_through_a_self_call():
    """roborev LOW: every qualifying argument of a SELF-call is a MetaArg,
    and the pass-through check read it as a non-variable -- with no prefix
    goals that made the clause TRO-ineligible.  The qualification is
    idempotent (entry already qualified), so the head variable passed on
    unchanged is a pass-through for TRO."""
    from clausal.logic.compiler.tro import _tro_args_safe_ir
    from clausal.logic.meta_predicate import MetaArg
    g, n, m = Var(), Var(), Var()
    head = ("loop", g, n)
    assert _tro_args_safe_ir(head, [], [MetaArg(g, 0), n], 2) == (True, frozenset())
    assert _tro_args_safe_ir(head, [], [g, n], 2) == (True, frozenset())
    assert _tro_args_safe_ir(head, [], [MetaArg(m, 0), n], 2)[0] is False


_TROLIB = """
    -module(mtro_DECL, [loop(G, N), run(N)])
    META
    loop(_, 0),
    loop(G, N) <- (N > 0, eval_(N - 1, M), loop(G, M)),
    okl(),
    run(N) <- loop(okl, N),
"""


@pytest.mark.parametrize("decl", ["declared", "undeclared"])
def test_a_meta_declared_recursive_walker_over_100k_steps(tmp_path, monkeypatch, decl):
    import clausal.logic.compiler.optimisations.tro as tro
    plans = []
    orig = tro.analyse

    def spy(ir, head, functor, arity, *a, **k):
        r = orig(ir, head, functor, arity, *a, **k)
        if functor == "loop":
            plans.append(r.eligible)
        return r
    monkeypatch.setattr(tro, "analyse", spy)
    meta = "-meta_predicate(loop(0, '?'))" if decl == "declared" else ""
    m = _load(tmp_path, monkeypatch, f"mtro_{decl}",
              _TROLIB.replace("DECL", decl).replace("META", meta))
    assert any(plans), plans                   # TRO-eligible, declared or not
    assert _n(m.__dict__["$module"], "run", 100_000) == 1
