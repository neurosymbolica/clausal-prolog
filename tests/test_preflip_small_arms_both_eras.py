"""W4b-2d task 7, the "small arms": four places that must answer the same
whether a module-dict predicate binding is still the ``PredicateMeta`` CLASS
or already the owner's mangled HANDLE, so the flip itself is only the binding
change.  Each was found by the flip dry run
(``implementation_plans/w4b2d-flip-dry-run-2026-09-24.md`` §1, §2):

* E (R7): ``listing(p)``, the bare form, on a handle fell into the atom arm
  and raised ``existence_error(procedure, 'm\\x1fp'/0)``.  It now raises
  Scryer's ``type_error(predicate_indicator, p)`` with the PLAIN name
  (operator ruling 2026-09-25, "do what Scryer does");
* C (R8): ``analyze_mi(mi_module.solve)``, the direct Python API, raised
  ``'str' object has no attribute 'key'``;
* G (R5): step 4a read ``pred_cls._row``, so an imported ``-dynamic`` HANDLE
  was compiled locally and the gate refused ``gate_dyn_user`` as a
  redefinition;
* A2 (R3): a cell built from a handle carried the MANGLED functor, so the
  importer's ``assertz(gd_p(X))`` raised existence_error for
  ``'m\\x1fgd_p'/1``.  Operator ruling 2026-09-25, option (a) (superseding
  option (c)): a cell built from a handle is ALWAYS PLAIN in data, term and
  head position -- ISO functors are never module-qualified; qualification
  lives only on goals (``M:G``) -- and a plain cell writes through the
  caller's namespace only.
* the handle head path (ruling (b), same day): an importer's clause for an
  imported predicate DEFERS to the load gate's refusal instead of raising
  ClausalTermConstructionError against the owner's field names.

Arm I (``_refuse_untablable_target``) landed with R6 and is pinned in
``test_class_only_state_moved_both_eras.py``.

Handle era (W4b-2d flip): the LOAD binds every handle now (ruling D1 for an
import), so the class arms and the stand-in ``flipped_loads`` /
``era_loads`` / ``_flip_all_bindings`` load-time flip are gone -- after the
flip they found no class and flipped nothing.  Tests assert the handle
binding they depend on.  ``_bindings_seen_before_step_4`` (it was the
last stand-in flip) now only OBSERVES the module dict before step 4, so the
step-4a test can assert the local handle was already there.
"""

from __future__ import annotations

import ast
import os
import sys
import textwrap

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.atoms import mangle
from clausal.logic.exceptions import LogicException
from clausal.logic.predicate import mint_predicate_handle
from clausal.logic.solve import call
from clausal.terms import Call as TermCall, LoadName

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
_OWNER = "tests.fixtures.gate_dyn_owner"


def _lm(mod):
    return mod.__dict__["$module"]


# ── G + A2: an imported -dynamic, asserted through the importer ─────────────


@pytest.fixture
def gate_dyn():
    names = (_OWNER, "_small_arms_gate_dyn_user")
    saved = {n: sys.modules.pop(n, None) for n in names}

    def load():
        owner = _load_module(_OWNER, os.path.join(FIXTURES, "gate_dyn_owner.clausal"))
        user = _load_module(names[1], os.path.join(FIXTURES, "gate_dyn_user.clausal"))
        return owner, user

    yield load
    for n in names:
        sys.modules.pop(n, None)
        if saved[n] is not None:
            sys.modules[n] = saved[n]


def test_an_imported_dynamic_loads_and_asserts_onto_the_owner(gate_dyn):
    """G: the importer LOADS (no redefinition refusal) and A2: its
    ``assertz(gd_p(X))`` builds the plain ``gd_p`` cell, so the clause lands
    on the OWNER's row and the importer's twin stays empty."""
    owner, user = gate_dyn()
    binding = user.__dict__["gd_p"]
    assert binding == mint_predicate_handle(_lm(owner).db, "gd_p"), (
        "the load did not bind the owner's handle")
    lm = _lm(user)
    assert list(call("gd_add", 42, module=lm)) != []
    owner_row = _lm(owner).db.row("gd_p", 1)
    heads = [c.head for c in owner_row.clauses]
    assert len(heads) == 2 and heads[1] == ("gd_p", 42), heads
    assert {h[0] for h in heads} == {"gd_p"}
    twin = lm.db.row("gd_p", 1, create=False)
    assert twin is None or twin.clauses == []


def test_step_4a_leaves_an_imported_dynamic_to_its_owner(gate_dyn):
    """G in isolation: step 4a must not seed the importer's pending entry for
    an imported ``-dynamic``.  The buggy path compiled the importer's OWN
    (empty) dispatch at step 5, which the gate refused as a redefinition; so
    what is G-specific is (1) the load succeeds, (2) the importer's local
    twin row (``mark_dynamic``'s, present in both eras) got NO compiled
    dispatch, and (3) a query through the importer answers the OWNER's
    clause, which an empty local dispatch would answer as ``[]``."""
    from clausal.logic.variables import Var, deref
    owner, user = gate_dyn()
    lm = _lm(user)
    twin = lm.db.row("gd_p", 1, create=False)
    assert twin is not None and twin.db is lm.db, "no local twin: nothing to leave"
    assert twin.dispatch_fn is None, "step 5 compiled the importer's own gd_p/1"
    X = Var()
    assert [deref(X) for _ in call("gd_p", X, module=lm)] == [1]
    assert _lm(owner).db.row("gd_p", 1).clauses != []


# ── A2: the cell functor a handle builds ─────────────────────────────────────


def _lowered_value(module_dict, term):
    from clausal.logic.compiler.terms_to_ast import lowering_scope, term_to_ast_expr
    with lowering_scope(module_dict):
        expr = term_to_ast_expr(term, {})
    return eval(compile(ast.fix_missing_locations(ast.Expression(expr)),
                        "<t>", "eval"), dict(module_dict))


def test_a_cell_built_from_a_predicate_binding_carries_the_plain_functor(gate_dyn):
    owner, user = gate_dyn()
    md = user.__dict__
    assert md["gd_p"] == mint_predicate_handle(_lm(owner).db, "gd_p"), (
        "the load did not bind the owner's handle")
    term = TermCall(func=LoadName(name="gd_p"), args=[7], kwargs=[])
    assert _lowered_value(md, term) == ("gd_p", 7)


def test_a_hide_data_atom_keeps_its_mangled_functor_spelling():
    """A2 is gated on "is a declared predicate", never on ``is_mangled``: a
    ``-hide`` DATA atom is mangled in the handle's shape and its mangled
    spelling is its identity.  ``is_predicate`` (the caller's
    ``is_declared_predicate_name`` answer) is what separates the two."""
    from clausal.logic.compiler.terms_to_ast import _functor_spelling
    saved = sys.modules.pop("hide_owner", None)
    try:
        mod = _load_module("hide_owner", os.path.join(FIXTURES, "hide_owner.clausal"))
        db = _lm(mod).db
        secret = mangle("hide_owner", "hide_secret")
        assert _functor_spelling(secret, "x") == secret
        handle = mint_predicate_handle(db, "holds")
        # Ruling (a): a predicate handle is PLAIN (no namespace consulted).
        assert _functor_spelling(handle, "x", is_predicate=True) == "holds"
    finally:
        sys.modules.pop("hide_owner", None)
        if saved is not None:
            sys.modules["hide_owner"] = saved


# ── E: listing(p), the bare form ─────────────────────────────────────────────


@pytest.fixture
def lister(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    loaded = []

    def load(name, body):
        (tmp_path / f"{name}.clausal").write_text(textwrap.dedent(body).lstrip())
        sys.modules.pop(name, None)
        loaded.append(name)
        return _load_module(name, str(tmp_path / f"{name}.clausal"))

    yield load
    for name in loaded:
        sys.modules.pop(name, None)


_FIB = """
    -module({name}, [fib(N, F), show])
    fib(0, 0),
    fib(1, 1),
    show <- listing(fib)
"""


def _predicate_indicator_culprit(goal, args, lm):
    with pytest.raises(LogicException) as exc:
        list(call(goal, *args, module=lm))
    err = exc.value.term.args[0]
    assert err.functor == "type_error", err
    assert err.args[0] == "predicate_indicator", err
    return err.args[1]


def _listed(goal, args, lm, capsys):
    capsys.readouterr()
    assert len(list(call(goal, *args, module=lm))) == 1
    return capsys.readouterr().out


def test_source_listing_of_a_bare_name_is_a_predicate_indicator_type_error(
        lister):
    """SOURCE ``listing(fib)``: ruling S lowers the bare name to its plain
    atom in both eras, so it is Scryer's ``type_error(predicate_indicator,
    fib)``, never naming ``'m\\x1ffib'``."""
    mod = lister("sa_e_fib", _FIB.format(name="sa_e_fib"))
    assert type(mod.__dict__["fib"]) is str
    assert _predicate_indicator_culprit("show", (), _lm(mod)) == "fib"


def test_the_python_api_lists_the_binding_it_is_handed(
        lister, capsys):
    """Operator ruling 2026-09-25: ``listing(mod.fib)`` from PYTHON lists
    the handle's predicate.

    FLIPPED 2026-09-25: the handle arm used to raise
    ``type_error(predicate_indicator, fib)`` (the class arm listed), which
    roborev flagged as the two eras disagreeing on one call."""
    mod = lister("sa_e_api", _FIB.format(name="sa_e_api"))
    binding = mod.__dict__["fib"]
    assert type(binding) is str, "the flip did not happen"
    out = _listed("listing", (binding,), _lm(mod), capsys)
    assert out.startswith("% fib/2 — 2 clause(s)\n"), out
    assert out.count("fib(") == 2


def test_the_python_api_lists_every_arity_of_a_handle(lister, capsys):
    """A handle names no arity: a name that is a predicate at SEVERAL lists
    each, in arity order.  (The class era's one-arity listing of a class is
    gone with the class; the module attribute IS the handle now.)"""
    mod = _multi_arity(lister, "sa_e_multi")
    lm = _lm(mod)
    handle = mint_predicate_handle(lm.db, "p")
    assert mod.__dict__["p"] == handle
    out = _listed("listing", (handle,), lm, capsys)
    assert [ln for ln in out.splitlines() if ln.startswith("%")] == [
        "% p/1 — 1 clause(s)", "% p/2 — 1 clause(s)"]


@pytest.mark.parametrize("popped", [False, True])
def test_the_python_api_lists_an_imported_binding_from_the_owner(
        lister, popped, capsys):
    """FLIPPED 2026-09-25 (was ``..._names_the_plain_name``, a type_error):
    an ``-import_from``'d binding handed to listing/1 from Python lists the
    OWNER's clauses, with the owner loaded or popped from ``sys.modules``."""
    owner = lister("sa_e_own", """
        -module(sa_e_own, [colour(C)])
        colour(1),
        colour(2),
    """)
    user = lister("sa_e_use", """
        -module(sa_e_use, [])
        -import_from(sa_e_own, [colour])
    """)
    md = user.__dict__
    assert md["colour"] == mint_predicate_handle(_lm(owner).db, "colour"), (
        "the load did not bind the owner's handle")
    if popped:
        sys.modules.pop("sa_e_own", None)
    out = _listed("listing", (md["colour"],), _lm(user), capsys)
    assert out.startswith("% colour/1 — 2 clause(s)\n"), out


def test_bare_listing_of_a_hide_data_atom_keeps_its_own_spelling():
    """A ``-hide`` DATA atom is not a handle: Scryer's refusal of a bare
    atom names it by its own (mangled) spelling, not demangled."""
    saved = sys.modules.pop("hide_owner", None)
    try:
        mod = _load_module("hide_owner", os.path.join(FIXTURES, "hide_owner.clausal"))
        secret = mangle("hide_owner", "hide_secret")
        with pytest.raises(LogicException) as exc:
            list(call("listing", secret, module=_lm(mod)))
        err = exc.value.term.args[0]
        assert err.functor == "type_error"
        assert err.args == ("predicate_indicator", secret)
    finally:
        sys.modules.pop("hide_owner", None)
        if saved is not None:
            sys.modules["hide_owner"] = saved


# ── ruling (a): a cell built from a handle is ALWAYS plain ───────────────────
#
# Operator ruling 2026-09-25, option (a), superseding option (c).  ``h`` is a
# handle held in Python; ``sa_clib.dfact(X)`` is a dotted reference in TERM
# position.  Neither binds ``dfact`` in the host.  Under (c) their cells were
# MANGLED and the write doors routed them to the owner; under (a) they are the
# PLAIN ``dfact`` cell, a plain cell writes through the CALLER's namespace
# only (so the host cannot write the owner's -dynamic through one), and a cell
# that must RUN in the owner is called as ``(":", lib, G)`` or
# ``solve(cell, lib)``.  A dotted ``sa_clib.dfact(X)`` in GOAL position is
# still the qualified goal.


_CLIB = """
    -module(sa_clib, [dfact/1, make(T)])
    -dynamic(dfact/1)
    dfact(0),
    make(dfact(7)),
"""

_CHOST = """
    -module(sa_chost, [cell_h(C), cell_d(C), add_h(X), add_d(X), get_h(X),
                       goal_d(X), made(X), run(G)])
    -import_module(sa_clib)
    from clausal.logic.atoms import mangle
    h = mangle("sa_clib", "dfact")
    same(X, X),
    cell_h(C) <- same(C, h(1))
    cell_d(C) <- same(C, sa_clib.dfact(1))
    add_h(X) <- assertz(h(X))
    add_d(X) <- assertz(sa_clib.dfact(X))
    get_h(X) <- call(h(X))
    goal_d(X) <- sa_clib.dfact(X)
    run(G) <- call(G)
    made(X) <- (sa_clib.make(T), same(T, sa_clib.dfact(X)))
"""


def _one(goal, lm):
    from clausal.logic.solve import _deref_walk
    from clausal.logic.variables import Var
    C = Var()
    got = [_deref_walk(C) for _ in call(goal, C, module=lm)]
    assert len(got) == 1, got
    return got[0]


def _all(goal, lm):
    from clausal.logic.variables import Var, deref
    X = Var()
    return sorted(deref(X) for _ in call(goal, X, module=lm))


def _existence_culprit(goal, arg, lm):
    with pytest.raises(LogicException) as exc:
        list(call(goal, arg, module=lm))
    err = exc.value.term.args[0]
    assert err.functor == "existence_error", err
    return err.args[1]


@pytest.fixture
def clib_pair(lister):
    def load():
        lib = lister("sa_clib", _CLIB)
        host = lister("sa_chost", _CHOST)
        assert type(lib.__dict__["dfact"]) is str
        return lib, host
    return load


def test_a_cell_built_from_any_handle_is_plain(clib_pair):
    _lib, host = clib_pair()
    lm = _lm(host)
    assert _one("cell_h", lm) == ("dfact", 1)      # a Python-held handle
    assert _one("cell_d", lm) == ("dfact", 1)      # dotted, term position


def test_an_owner_built_term_unifies_with_the_dotted_spelling(clib_pair):
    """roborev's interop case: ``lib.make(T), T = lib.hf(X)`` -- one logical
    term, one spelling -- which failed in the handle era under (c)."""
    _lib, host = clib_pair()
    assert _all("made", _lm(host)) == [7]


def test_a_plain_cell_writes_only_through_the_caller_s_namespace(clib_pair):
    """The host does not bind ``dfact``, so neither spelling may write the
    owner's -dynamic: ISO routes a write by the caller's namespace (or an
    explicit ``M:G``), never by a qualified functor."""
    lib, host = clib_pair()
    lm, owner_row = _lm(host), _lm(lib).db.row("dfact", 1)
    before = list(owner_row.clauses)
    for goal in ("add_h", "add_d"):
        culprit = _existence_culprit(goal, 11, lm)
        assert culprit.args == ("dfact", 1), (goal, culprit)
    assert owner_row.clauses == before
    assert lm.db.row("dfact", 1, create=False) is None, "written locally"


def test_a_plain_cell_runs_in_the_owner_only_when_qualified(clib_pair, lister):
    from clausal.logic.solve import solve
    from clausal.logic.variables import deref
    lib, host = clib_pair()
    lm = _lm(host)
    from clausal.logic.variables import Var
    # A plain cell VALUE, called, runs in the CALLER.  A caller that knows
    # no dfact/1 never reaches the owner's clauses.  (A separate host:
    # sa_chost binds the Python-held handle ``h = mangle("sa_clib", "dfact")``,
    # which ``predicate._import_index`` indexes as an import, so a meta-call
    # of the plain ``dfact`` there DOES answer the owner's clause -- see
    # todo/plain-cell-reads-route-to-owner-when-host-has-dotted-goals-2026-09-25.md.)
    bare = lister("sa_crun", """
        -module(sa_crun, [run(G)])
        -import_module(sa_clib)
        run(G) <- call(G)
    """)
    # ISO since main ae1a456d: an unknown procedure is existence_error.
    assert _existence_culprit("run", ("dfact", Var()), _lm(bare)).args == ("dfact", 1)
    # Qualified, it runs in the owner: M:G, or solve(cell, M).
    X = Var()
    assert [deref(X) for _ in solve((":", "sa_clib", ("dfact", X)))] == [0]
    Y = Var()
    assert [deref(Y) for _ in solve(("dfact", Y), lib)] == [0]
    # ``call(h(X))`` names the handle in the meta-call's GOAL argument, which
    # is goal position: the qualified goal, as a body goal ``h(X)`` is.
    assert _all("get_h", lm) == [0]
    # A dotted reference in GOAL position is still the qualified goal.
    assert _all("goal_d", lm) == [0]


@pytest.mark.parametrize("atom_pool_seeded", [False, True])
def test_the_seam_builds_the_plain_cell(lister, atom_pool_seeded):
    """The ``--`` seam, the same rule: an imported name, a Python-held handle
    to an imported predicate, and one to a predicate the host does NOT
    import all build the PLAIN cell.  ``atom_pool_seeded`` keeps the
    full-suite pollution (an earlier module exporting the global atom
    ``sa_s_other``, pre-seeded into every module dict) in-file."""
    if atom_pool_seeded:
        lister("sa_spool", """
            -module(sa_spool, [sa_s_other])
        """)
    lister("sa_slib", """
        -module(sa_slib, [spred(A), sa_s_other(A)])
        spred(1),
        sa_s_other(1),
    """)
    host = lister("sa_shost", """
        -module(sa_shost, [])
        -import_from(sa_slib, [spred])
        from clausal.logic.atoms import mangle
        held = mangle("sa_slib", "spred")
        held_other = mangle("sa_slib", "sa_s_other")
        via_import = spred
        def build_import():
            return --spred(X)
        def build_alias():
            return --via_import(X)
        def build_held():
            return --held(X)
        def build_held_other():
            return --held_other(X)
        def build_held_wide():
            return --held(X, Y)
    """)
    assert type(host.__dict__["spred"]) is str
    assert host.build_import()[0] == "spred"
    assert host.build_alias()[0] == "spred"
    assert host.build_held()[0] == "spred"
    assert host.build_held_other()[0] == "sa_s_other"
    # At an arity the predicate is not defined at, no signature answers and
    # the seam's own handle branch builds the cell -- plain there too.
    wide = host.build_held_wide()
    assert wide[0] == "spred" and len(wide) == 3


def _multi_arity(lister, name):
    """``p/1`` and ``p/2`` both defined in one module -- only a ``-dynamic``
    pair can be, a clause head fixes a functor's arity in the file."""
    mod = lister(name, f"""
        -module({name}, [])
        -dynamic(p/1)
        -dynamic(p/2)
    """)
    lm = _lm(mod)
    for cell in (("p", 1), ("p", 1, 2)):
        assert list(call("assertz", cell, module=lm)) != []
    return mod


# ── C: analyze_mi through the direct Python API ──────────────────────────────


def _pattern_key(p):
    return (p.name, p.arity, tuple(p.fields), p.program_arg, p.goal_arg,
            tuple(p.extra_args), len(p.base_clause.body or []),
            len(p.recursive_clause.body or []))


def test_analyze_mi_accepts_the_module_attribute():
    import clausal.examples.metainterpreters as mi
    from clausal.logic.specialization import analyze_mi
    binding = mi.solve
    assert binding == mint_predicate_handle(_lm(mi).db, "solve"), (
        "the load did not bind the handle")
    # What analyze_mi answered for the CLASS (CLAUSAL_NO_FLIP=1, 9e6c2633).
    expected = ("solve", 2, ("GOALS", "PROGRAM"), 1, 0, (), 1, 3)
    assert _pattern_key(analyze_mi(binding)) == expected


def test_analyze_mi_refuses_a_string_that_is_not_a_predicate_handle():
    from clausal.logic.specialization import CannotSpecialize, analyze_mi
    for s in ("solve", mangle("no_such_module_small_arms", "solve")):
        with pytest.raises(CannotSpecialize, match="not a predicate handle"):
            analyze_mi(s)


def test_analyze_mi_refuses_a_handle_defined_at_several_arities(lister):
    from clausal.logic.specialization import CannotSpecialize, analyze_mi
    mod = _multi_arity(lister, "sa_c_multi")
    with pytest.raises(CannotSpecialize, match=r"several arities \[1, 2\]"):
        analyze_mi(mint_predicate_handle(_lm(mod).db, "p"))


_POPMI = """
    -module({name}, [solve(GOALS, PROGRAM), match_clause(GOAL, BODY, PROGRAM)])
    match_clause(GOAL, FRESH_BODY, PROGRAM) <- (
        CLAUSE in PROGRAM,
        copy_term(CLAUSE, [FRESH_HEAD, FRESH_BODY]),
        GOAL is FRESH_HEAD,
    )
    solve([], _PROGRAM_UNUSED),
    solve([GOAL, *GOALS], PROGRAM) <- (
        match_clause(GOAL, BODY, PROGRAM),
        append(BODY, GOALS, ALL_GOALS),
        solve(ALL_GOALS, PROGRAM),
    )
"""


def test_analyze_mi_resolves_a_local_handle_through_the_db_hint(lister):
    """roborev Low: a LOCAL handle whose module was popped from
    ``sys.modules`` resolves through the caller's ``db=`` (ruling Q0)."""
    from clausal.logic.specialization import CannotSpecialize, analyze_mi
    mod = lister("sa_c_popmi", _POPMI.format(name="sa_c_popmi"))
    db = _lm(mod).db
    handle = mint_predicate_handle(db, "solve")
    expected = _pattern_key(analyze_mi(handle))
    sys.modules.pop("sa_c_popmi", None)
    # A second live load under the SAME module name (the ``.clausal`` runner
    # reloads fixtures): the handle-owner registry now holds two candidate
    # dbs, so without the hint the handle names no one predicate.
    twin = lister("sa_c_popmi", _POPMI.format(name="sa_c_popmi"))
    sys.modules.pop("sa_c_popmi", None)
    assert _lm(twin).db is not db
    with pytest.raises(CannotSpecialize):
        analyze_mi(handle)
    assert _pattern_key(analyze_mi(handle, db=db)) == expected


# ── the handle head path defers to the load gate (ruling (b)) ────────────────
#
# Found under the flip emulation: an importer that writes a clause for an
# imported predicate spells the head with field names derived from ITS OWN
# head (``gv_owned(teal),`` -> ``arg_0=teal``, ``gv_owned(COLOUR)`` ->
# ``colour=COLOUR``).  In the class era the importer's body re-mints a local
# class with those names and the gate refuses the load; a HANDLE built against
# the OWNER's names (``gv_owned(NAME)``) raised ClausalTermConstructionError
# first, and the gate's refusal was never seen.  Operator ruling 2026-09-25
# (b): the handle head path defers to the gate.


@pytest.fixture
def vocab_rival():
    names = ("tests.fixtures.gate_vocab", "tests.fixtures.gate_rival", "_sa_hv")
    saved = {n: sys.modules.pop(n, None) for n in names}
    yield names
    for n in names:
        sys.modules.pop(n, None)
        if saved[n] is not None:
            sys.modules[n] = saved[n]


def test_a_clobbering_import_head_is_refused_by_the_gate(vocab_rival):
    vocab = _load_module(vocab_rival[0], os.path.join(FIXTURES, "gate_vocab.clausal"))
    with pytest.raises(SyntaxError) as exc:
        _load_module(vocab_rival[1], os.path.join(FIXTURES, "gate_rival.clausal"))
    assert "may not write gv_owned/1" in str(exc.value)
    assert len(_lm(vocab).db.row("gv_owned", 1).clauses) == 1


def test_a_variable_head_for_an_import_is_refused_by_the_gate(
        vocab_rival, tmp_path):
    """The derived name is a VARIABLE's (``colour``), not a placeholder."""
    _load_module(vocab_rival[0], os.path.join(FIXTURES, "gate_vocab.clausal"))
    src = tmp_path / "sa_hv.clausal"
    src.write_text("-module(sa_hv, [])\n"
                   "-import_from(tests.fixtures.gate_vocab, [gv_owned])\n"
                   "gv_owned(COLOUR) <- true\n")
    with pytest.raises(SyntaxError) as exc:
        _load_module(vocab_rival[2], str(src))
    assert "defines a clause for gv_owned/1" in str(exc.value)


def test_the_owner_s_own_head_keeps_its_construction_error(vocab_rival):
    """Deferral is for ANOTHER module's head only: called with no module to
    tell (this test's namespace has no ``$module``), a handle's head keeps
    the error, and it names the SITE the owner row records
    (``declared_at``), not ``<unknown>``."""
    from clausal.logic.predicate import ClausalTermConstructionError, head_cell
    vocab = _load_module(vocab_rival[0], os.path.join(FIXTURES, "gate_vocab.clausal"))
    handle = mint_predicate_handle(_lm(vocab).db, "gv_owned")
    assert head_cell(handle, NAME="teal") == ("gv_owned", "teal")
    with pytest.raises(ClausalTermConstructionError) as exc:
        head_cell(handle, arg_0="teal")
    assert "gate_vocab.clausal:" in str(exc.value)
    assert "<unknown>" not in str(exc.value)


@pytest.mark.parametrize("by_name", [False, True])
def test_a_host_head_pattern_matches_an_owner_built_term(
        lister, by_name):
    """roborev's interop case, head side: ``patq(sa_hlib.hf(X), X)`` in the
    HOST matches the ``hf`` term the OWNER builds (``sa_hlib.make``), with or
    without an import by name, in both eras -- and never a mangled one."""
    lister("sa_hlib", """
        -module(sa_hlib, [hf(A), make(T)])
        hf(1),
        make(hf(5)),
    """)
    host = lister("sa_hhost", f"""
        -module(sa_hhost, [patq(T, X), owner_built(X)])
        {"-import_from(sa_hlib, [hf])" if by_name else ""}
        -import_module(sa_hlib)
        patq(sa_hlib.hf(X), X) <- true
        owner_built(X) <- (sa_hlib.make(T), patq(T, X))
    """)
    lm = _lm(host)
    from clausal.logic.variables import Var, deref
    assert _all("owner_built", lm) == [5]
    for functor, expected in (("hf", [5]), (mangle("sa_hlib", "hf"), [])):
        X = Var()
        got = [deref(X) for _ in call("patq", (functor, 5), X, module=lm)]
        assert got == expected, functor


# ── review Lows on 176584ec ──────────────────────────────────────────────────


def _bindings_seen_before_step_4(monkeypatch):
    """OBSERVE the module dict at step 3d, BEFORE steps 4 and 4a, and return
    ``{key: value}`` for every key already bound to its own module's handle.

    Nothing is rebound: since W4b-3 slice 5 the module body binds this
    module's own HANDLE (``$declare_head``), so step 4a meets a LOCAL handle
    on a real load.  (This helper used to REBIND classes to handles here --
    the flip ran after step 4a -- until W4b-3 deleted the class.)  The test
    asserts on what it saw, so a load that reached step 4a with anything
    but the handle fails rather than passing under the handle test's name."""
    import clausal.logic.compiler_v2 as cv2
    real = cv2._refuse_foreign_writes
    seen = {}

    def _observe_then_gate(db, predicate_nodes, module_dict, *rest):
        for key, value in list(module_dict.items()):
            if key.startswith("$"):
                continue
            if type(value) is str and value == mint_predicate_handle(db, key):
                seen[key] = value
        return real(db, predicate_nodes, module_dict, *rest)

    monkeypatch.setattr(cv2, "_refuse_foreign_writes", _observe_then_gate)
    return seen


def test_step_4a_a_local_dynamic_handle_is_compiled_from_its_own_row(
        lister, monkeypatch):
    """compiler_v2 step 4a, a LOCAL clause-less ``-dynamic`` whose binding
    is a handle: explicitly ``pending[key] = None`` (no class to bind; its
    row is this db's), the entry a clause-less class gets -- not the class
    test answering None for a str by accident."""
    from clausal.logic.variables import Var, deref
    seen = _bindings_seen_before_step_4(monkeypatch)
    mod = lister("sa_ld", """
        -module(sa_ld, [sa_ld_p/1, add(X)])
        -dynamic(sa_ld_p/1)
        add(X) <- assertz(sa_ld_p(X))
    """)
    binding = mod.__dict__["sa_ld_p"]
    assert seen, "the step-3d observer never ran"
    assert seen.get("sa_ld_p") == binding, (
        f"step 4a did not meet sa_ld_p as its handle: {seen}")
    assert type(binding) is str
    lm = _lm(mod)
    row = lm.db.row("sa_ld_p", 1, create=False)
    assert row is not None and row.db is lm.db and row.dynamic
    assert row.clauses == []
    X = Var()
    assert [deref(X) for _ in call("sa_ld_p", X, module=lm)] == []
    assert list(call("add", 3, module=lm)) != []
    assert [deref(X) for _ in call("sa_ld_p", X, module=lm)] == [3]
    assert [c.head for c in lm.db.row("sa_ld_p", 1).clauses] == [("sa_ld_p", 3)]


def test_the_seam_s_handle_branch_passes_the_q0_hint(lister):
    """seam.py's own handle branch (an arity no signature answers) asks
    ``is_declared_predicate_name`` with the module's db, as
    ``cell_signature_for_name`` does: a LOCAL handle stays a predicate --
    and so PLAIN -- after its module is popped, even when a second live load
    under the same name makes the handle-owner registry ambiguous."""
    src = """
        -module(sa_sq, [sa_sq_p(A)])
        from clausal.logic.atoms import mangle
        held = mangle("sa_sq", "sa_sq_p")
        sa_sq_p(1),
        def build_wide():
            return --held(X, Y)
    """
    first = lister("sa_sq", src)
    sys.modules.pop("sa_sq", None)
    twin = lister("sa_sq", src)
    sys.modules.pop("sa_sq", None)
    assert _lm(twin).db is not _lm(first).db
    wide = first.build_wide()
    assert wide[0] == "sa_sq_p" and len(wide) == 3


@pytest.mark.parametrize("home_is_owner", [True, False])
def test_deferral_compares_the_owner_by_database_identity(vocab_rival, home_is_owner):
    """``_defers_to_the_gate``: the owner is the Q0-resolved DATABASE, not a
    module-name string."""
    from clausal.logic.predicate import _defers_to_the_gate
    vocab = _load_module(vocab_rival[0], os.path.join(FIXTURES, "gate_vocab.clausal"))
    handle = mint_predicate_handle(_lm(vocab).db, "gv_owned")
    if home_is_owner:
        home = vocab.__dict__
    else:
        from clausal.logic.database import Module
        home = {"$module": Module("sa_defer_home", module_dict={"__name__": "sa_defer_home"})}
    assert _defers_to_the_gate(handle, home, 1) is (not home_is_owner)
    from clausal.logic.predicate import ClausalTermConstructionError, _handle_head_cell
    if home_is_owner:
        with pytest.raises(ClausalTermConstructionError):
            _handle_head_cell(handle, (), {"arg_0": "teal"}, home=home)
        assert "$deferred_heads" not in home
    else:
        # Deferred: built at the written arity, and RECORDED for the
        # compile-time invariant check.
        assert _handle_head_cell(handle, (), {"arg_0": "teal"}, home=home) == (
            "gv_owned", "teal")
        assert home["$deferred_heads"] == {("gv_owned", 1)}
    # never at an arity the owner does not know, nor with no module to tell
    assert _defers_to_the_gate(handle, home, 2) is False
    assert _defers_to_the_gate(handle, {}, 1) is False


def test_a_deferred_head_the_gate_permits_is_refused():
    """The invariant: a head built positionally for the gate to refuse never
    reaches a row."""
    from clausal.logic.compiler_v2 import _refuse_unrefused_deferred_heads

    class _Node:
        def __init__(self, head):
            self.head = head

    md = {"$deferred_heads": {("gv_owned", 1)}}
    with pytest.raises(SyntaxError, match="gv_owned/1"):
        _refuse_unrefused_deferred_heads([_Node(("gv_owned", "teal"))], md, "m")
    md = {"$deferred_heads": {("gv_owned", 1)}}
    _refuse_unrefused_deferred_heads([_Node(("other", 1))], md, "m")
    assert "$deferred_heads" not in md


def test_a_head_through_a_python_held_handle_never_reaches_a_row(vocab_rival, tmp_path):
    """The invariant from SOURCE: a Python-held handle is not an
    -import_from, so step 3d does not refuse its head; the deferred head is
    refused by the compile-time check instead of being stored positionally
    on this module's own gv_owned/1 row."""
    _load_module(vocab_rival[0], os.path.join(FIXTURES, "gate_vocab.clausal"))
    src = tmp_path / "sa_hh.clausal"
    src.write_text("-module(sa_hh, [])\n"
                   "-allow_singletons\n"
                   "from clausal.logic.atoms import mangle\n"
                   "h = mangle('tests.fixtures.gate_vocab', 'gv_owned')\n"
                   "h(COLOUR) <- true\n")
    with pytest.raises(SyntaxError, match="written through a handle"):
        _load_module(vocab_rival[2], str(src))
