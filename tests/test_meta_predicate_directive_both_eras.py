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
"""
from __future__ import annotations

import sys
import textwrap

import pytest

from clausal.logic.atoms import mangle, mint
from clausal.logic.exceptions import LogicException
from clausal.logic.predicate import PredicateMeta
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref, walk
from clausal.terms import Compound


def _load(tmp_path, monkeypatch, name, body):
    from clausal.import_hook import _load_module
    monkeypatch.syspath_prepend(str(tmp_path))
    p = tmp_path / f"{name}.clausal"
    p.write_text(textwrap.dedent(body).lstrip())
    mod = _load_module(name, str(p))
    assert sys.modules[name] is mod
    return mod


def _bind_imports_as_owner_handles(monkeypatch, owner):
    """The handle era for ``-import_from`` (D1: an import binds the OWNER's
    handle) -- the emulation test_arity_mismatch_is_iso_existence_error_both_eras
    uses."""
    import clausal.logic.compiler_v2 as cv
    orig = cv._process_imports
    seen = []

    def flipped(items, module_dict, db=None):
        orig(items, module_dict, db)
        for k, v in list(module_dict.items()):
            if (isinstance(v, PredicateMeta) and v._row is not None
                    and v._row._db is owner.db):
                module_dict[k] = mangle(owner.name, v._row._key[0])
                seen.append(k)

    monkeypatch.setattr(cv, "_process_imports", flipped)
    return seen


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


@pytest.fixture(params=["class", "handle"])
def pair(request, tmp_path, monkeypatch):
    era = request.param
    ow = _load(tmp_path, monkeypatch, f"mpu_{era}", _OWNER.replace("ERA", era))
    O = ow.__dict__["$module"]
    seen = (_bind_imports_as_owner_handles(monkeypatch, O)
            if era == "handle" else None)
    im = _load(tmp_path, monkeypatch, f"mpm_{era}", _IMPORTER.replace("ERA", era))
    I = im.__dict__["$module"]
    al = _load(tmp_path, monkeypatch, f"mpa_{era}",
               _ALIAS_IMPORTER.replace("ERA", era))
    I.alias_importer = al.__dict__["$module"]
    if era == "handle":
        assert "apply_all" in seen, "the handle era must really be exercised"
        assert I.module_dict["apply_all"] == mangle(f"mpu_{era}", "apply_all")
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
    formal = exc.value.term.args[0]
    assert formal.functor == "existence_error"
    assert formal.args == (mint("procedure"), Compound("/", (mint("my_pred"), 1)))


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
    globals) is supported."""
    from clausal.logic.compiler import compile_predicate_trampoline
    from clausal.logic.database import Clause
    from clausal.logic.predicate import make_predicate
    from clausal.terms import Call, LoadName

    base = make_predicate("mp_dbless_base", ["x"])
    top = make_predicate("mp_dbless_top", ["x"])
    x = Var()
    compile_predicate_trampoline(
        "mp_dbless_base", 1, [Clause(base(1), [])], pred_cls=base)
    compile_predicate_trampoline(
        "mp_dbless_top", 1,
        [Clause(top(x), [Call(func=LoadName(name="mp_dbless_base"),
                              args=[x], kwargs=[])])],
        pred_cls=top, globals_={"mp_dbless_base": base})
    y = Var()
    assert [deref(y) for _ in call(top, y)] == [1]


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


@pytest.fixture(params=["class", "handle"])
def glib(request, tmp_path, monkeypatch):
    era = request.param
    lib = _load(tmp_path, monkeypatch, f"mglib_{era}", _GLIB.replace("ERA", era))
    _load(tmp_path, monkeypatch, f"mgrules_{era}", _GRULES.replace("ERA", era))
    if era == "handle":
        _bind_imports_as_owner_handles(monkeypatch, lib.__dict__["$module"])
    dom = _load(tmp_path, monkeypatch, f"mgdom_{era}", _GDOM.replace("ERA", era))
    return era, dom.__dict__["$module"]


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
    formal = exc.value.term.args[0]
    assert formal.functor == "existence_error"
    assert formal.args[1] == Compound("/", (mint("nosuch"), 4))


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
