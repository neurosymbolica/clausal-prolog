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
  ``'m\\x1fgd_p'/1``.  Operator ruling 2026-09-25, option (c): a cell built
  from a handle is PLAIN when the namespace binds the plain name to that same
  predicate, MANGLED otherwise (a Python-held handle, a dotted ``lib.p(X)``),
  and the write doors route a mangled cell to its owner.

Arm I (``_refuse_untablable_target``) landed with R6 and is pinned in
``test_class_only_state_moved_both_eras.py``.

The handle era is emulated the way the other both-eras tests do it: ruling D1
(an import binds the OWNER's handle, ``mint_predicate_handle(owner_db,
name)``), either on one binding after load or on every binding during the
load (``flipped_loads``, applied where the dry run applied the flip).
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
from clausal.logic.predicate import PredicateMeta, mint_predicate_handle
from clausal.logic.solve import call
from clausal.terms import Call as TermCall, LoadName

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
ERAS = ["class", "handle"]
_OWNER = "tests.fixtures.gate_dyn_owner"


def _lm(mod):
    return mod.__dict__["$module"]


def _flip_all_bindings(module_dict, db):
    """The dry run's ``_flip_bindings`` in miniature (same as
    ``test_class_only_state_moved_both_eras._flip_all_bindings``)."""
    for key, value in list(module_dict.items()):
        if not isinstance(value, PredicateMeta) or key.startswith("$"):
            continue
        row = value.__dict__.get("_row")
        if row is not None and not row.detached:
            owner, functor = row.db, row.key[0]
        else:
            owner, functor = db, value.__name__
        module_dict[key] = mint_predicate_handle(owner, functor)


@pytest.fixture
def flipped_loads(monkeypatch):
    """Flip every binding after step 4a, before step 4b and step 5 -- where
    the dry run flipped.  An IMPORTER compiled under this sees the owner's
    handle from its import onwards, step 4a included."""
    import clausal.logic.compiler_v2 as cv2
    real = cv2._validate_directive_targets

    def _flip_then_validate(module_items, db, module_dict):
        _flip_all_bindings(module_dict, db)
        return real(module_items, db, module_dict)

    monkeypatch.setattr(cv2, "_validate_directive_targets", _flip_then_validate)


@pytest.fixture
def era_loads(request):
    def use(era):
        if era == "handle":
            request.getfixturevalue("flipped_loads")
    return use


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


@pytest.mark.parametrize("era", ERAS)
def test_an_imported_dynamic_loads_and_asserts_onto_the_owner(gate_dyn, era_loads, era):
    """G: the importer LOADS (no redefinition refusal) and A2: its
    ``assertz(gd_p(X))`` builds the plain ``gd_p`` cell, so the clause lands
    on the OWNER's row and the importer's twin stays empty."""
    era_loads(era)
    owner, user = gate_dyn()
    binding = user.__dict__["gd_p"]
    if era == "handle":
        assert type(binding) is str, "the flip did not happen"
    else:
        assert isinstance(binding, PredicateMeta)
    lm = _lm(user)
    assert list(call("gd_add", 42, module=lm)) != []
    owner_row = _lm(owner).db.row("gd_p", 1)
    heads = [c.head for c in owner_row.clauses]
    assert len(heads) == 2 and heads[1] == ("gd_p", 42), heads
    assert {h[0] for h in heads} == {"gd_p"}
    twin = lm.db.row("gd_p", 1, create=False)
    assert twin is None or twin.clauses == []


@pytest.mark.parametrize("era", ERAS)
def test_step_4a_leaves_an_imported_dynamic_to_its_owner(gate_dyn, era_loads, era):
    """G in isolation: step 4a must not seed the importer's pending entry for
    an imported ``-dynamic``.  The buggy path compiled the importer's OWN
    (empty) dispatch at step 5, which the gate refused as a redefinition; so
    what is G-specific is (1) the load succeeds, (2) the importer's local
    twin row (``mark_dynamic``'s, present in both eras) got NO compiled
    dispatch, and (3) a query through the importer answers the OWNER's
    clause, which an empty local dispatch would answer as ``[]``."""
    from clausal.logic.variables import Var, deref
    era_loads(era)
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


@pytest.mark.parametrize("era", ERAS)
def test_a_cell_built_from_a_predicate_binding_carries_the_plain_functor(gate_dyn, era):
    owner, user = gate_dyn()
    md = user.__dict__
    cls = md["gd_p"]
    assert isinstance(cls, PredicateMeta), "fixture no longer binds a class"
    try:
        if era == "handle":
            md["gd_p"] = mint_predicate_handle(_lm(owner).db, "gd_p")
        term = TermCall(func=LoadName(name="gd_p"), args=[7], kwargs=[])
        assert _lowered_value(md, term) == ("gd_p", 7)
    finally:
        md["gd_p"] = cls


def test_a_hide_data_atom_keeps_its_mangled_functor_spelling():
    """A2 is gated on "is a declared predicate", never on ``is_mangled``: a
    ``-hide`` DATA atom is mangled in the handle's shape and its mangled
    spelling is its identity -- even in its owner, which binds the plain
    name to it (so rule (c) alone would unmangle it)."""
    from clausal.logic.compiler.terms_to_ast import _functor_spelling
    saved = sys.modules.pop("hide_owner", None)
    try:
        mod = _load_module("hide_owner", os.path.join(FIXTURES, "hide_owner.clausal"))
        md = mod.__dict__
        db = _lm(mod).db
        secret = mangle("hide_owner", "hide_secret")
        assert _functor_spelling(secret, "x", namespace=md) == secret
        handle = mint_predicate_handle(db, "holds")
        # Rule (c): the owner binds ``holds`` to this predicate -> plain;
        # a namespace that does not -> mangled.
        assert _functor_spelling(handle, "x", namespace=md, is_predicate=True) == "holds"
        assert _functor_spelling(handle, "x", namespace={}, is_predicate=True) == handle
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


def test_bare_listing_of_a_handle_is_a_predicate_indicator_type_error(
        lister, flipped_loads):
    """SOURCE ``listing(fib)`` in the handle era, and the Python call with
    the handle: Scryer's ``type_error(predicate_indicator, fib)``, naming the
    PLAIN name the source wrote, never ``'m\\x1ffib'``."""
    mod = lister("sa_e_fib", _FIB.format(name="sa_e_fib"))
    handle = mod.__dict__["fib"]
    assert type(handle) is str, "the flip did not happen"
    lm = _lm(mod)
    assert _predicate_indicator_culprit("show", (), lm) == "fib"
    assert _predicate_indicator_culprit("listing", (handle,), lm) == "fib"


def test_bare_listing_of_a_class_binding_is_unchanged(lister, capsys):
    """The CLASS era keeps the Python-API arm: ``listing(<class>)`` lists.
    Source ``listing(fib)`` passes that same class object today, so it lists
    too; only the flip makes the source form Scryer's type_error."""
    mod = lister("sa_e_fibc", _FIB.format(name="sa_e_fibc"))
    assert isinstance(mod.__dict__["fib"], PredicateMeta)
    lm = _lm(mod)
    for goal, args in (("listing", (mod.__dict__["fib"],)), ("show", ())):
        capsys.readouterr()
        assert len(list(call(goal, *args, module=lm))) == 1
        assert capsys.readouterr().out.startswith("% fib/2 — 2 clause(s)\n")


@pytest.mark.parametrize("popped", [False, True])
def test_bare_listing_of_an_imported_handle_names_the_plain_name(lister, popped):
    owner = lister("sa_e_own", """
        -module(sa_e_own, [colour(C)])
        colour(1),
        colour(2),
    """)
    user = lister("sa_e_use", """
        -module(sa_e_use, [])
        -import_from(sa_e_own, [colour])
    """)
    handle = mint_predicate_handle(_lm(owner).db, "colour")
    user.__dict__["colour"] = handle
    if popped:
        sys.modules.pop("sa_e_own", None)
    assert _predicate_indicator_culprit("listing", (handle,), _lm(user)) == "colour"


def test_bare_listing_of_a_hide_data_atom_is_unchanged():
    """A ``-hide`` DATA atom is not a handle: it keeps the atom arm (its
    mangled spelling at arity 0 names no predicate)."""
    saved = sys.modules.pop("hide_owner", None)
    try:
        mod = _load_module("hide_owner", os.path.join(FIXTURES, "hide_owner.clausal"))
        secret = mangle("hide_owner", "hide_secret")
        with pytest.raises(LogicException) as exc:
            list(call("listing", secret, module=_lm(mod)))
        err = exc.value.term.args[0]
        assert err.functor == "existence_error"
        assert err.args[1].args == (secret, 0)
    finally:
        sys.modules.pop("hide_owner", None)
        if saved is not None:
            sys.modules["hide_owner"] = saved


# ── rule (c): a handle the module does NOT bind by its plain name ────────────
#
# roborev (Medium) on c0df2aeb: pin the COMPILED-body behaviour.  ``h`` is a
# handle held in Python; ``sa_clib.dfact(X)`` is a dotted reference in term
# position.  Neither binds ``dfact`` in the host, so under (c) the cell is
# MANGLED, and call/N and assertz/retract route it to the owner.


_CLIB = """
    -module(sa_clib, [dfact/1])
    -dynamic(dfact/1)
    dfact(0),
"""

_CHOST = """
    -module(sa_chost, [cell_h(C), cell_d(C), add_h(X), add_d(X), get_h(X),
                       get_d(X), del_h(X)])
    -import_module(sa_clib)
    from clausal.logic.atoms import mangle
    h = mangle("sa_clib", "dfact")
    same(X, X),
    cell_h(C) <- same(C, h(1))
    cell_d(C) <- same(C, sa_clib.dfact(1))
    add_h(X) <- assertz(h(X))
    add_d(X) <- assertz(sa_clib.dfact(X))
    del_h(X) <- retract(h(X))
    get_h(X) <- call(h(X))
    get_d(X) <- call(sa_clib.dfact(X))
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


@pytest.mark.parametrize("era", ERAS)
def test_a_handle_not_bound_by_its_plain_name_builds_the_mangled_cell(
        lister, era_loads, era):
    era_loads(era)
    lib = lister("sa_clib", _CLIB)
    host = lister("sa_chost", _CHOST)
    assert (type(lib.__dict__["dfact"]) is str) == (era == "handle")
    assert "dfact" not in host.__dict__, "the host must not bind the plain name"
    lm = _lm(host)
    qualified = mangle("sa_clib", "dfact")
    # Python-held: mangled in both eras (it is a handle in both).
    assert _one("cell_h", lm) == (qualified, 1)
    # Dotted: the CLASS era is unchanged (a class spells its own name); the
    # handle is not bound as ``dfact`` here, so (c) keeps the module.
    assert _one("cell_d", lm) == (("dfact", 1) if era == "class" else (qualified, 1))


@pytest.mark.parametrize("era", ERAS)
def test_a_mangled_cell_is_called_and_written_on_its_owner(lister, era_loads, era):
    era_loads(era)
    lib = lister("sa_clib", _CLIB)
    host = lister("sa_chost", _CHOST)
    lm, owner_db = _lm(host), _lm(lib).db
    assert list(call("add_h", 11, module=lm)) != []
    if era == "handle":
        # The dotted cell is mangled only in the handle era; in the class era
        # it is the PLAIN ``dfact`` cell, which this host does not know
        # (existence_error, as on main -- class era unchanged).
        assert list(call("add_d", 12, module=lm)) != []
    heads = [c.head[1] for c in owner_db.row("dfact", 1).clauses]
    assert heads[1:] == ([11, 12] if era == "handle" else [11])
    assert _lm(host).db.row("dfact", 1, create=False) is None, "written locally"
    expected = [0, 11, 12] if era == "handle" else [0, 11]
    assert _all("get_h", lm) == expected
    assert _all("get_d", lm) == expected
    assert list(call("del_h", 11, module=lm)) != []
    assert _all("get_h", lm) == [x for x in expected if x != 11]


@pytest.mark.parametrize("era", ERAS)
def test_the_seam_follows_the_same_rule(lister, era_loads, era):
    """The ``--`` seam applies the same rule.  The rule is about the
    NAMESPACE, not about how the handle was obtained: a Python-held handle
    to a predicate this module imports by name is PLAIN, and one to a
    predicate it does not import (``other``) is MANGLED."""
    era_loads(era)
    lister("sa_slib", """
        -module(sa_slib, [spred(A), other(A)])
        spred(1),
        other(1),
    """)
    host = lister("sa_shost", """
        -module(sa_shost, [])
        -import_from(sa_slib, [spred])
        from clausal.logic.atoms import mangle
        held = mangle("sa_slib", "spred")
        held_other = mangle("sa_slib", "other")
        via_import = spred
        def build_import():
            return --spred(X)
        def build_alias():
            return --via_import(X)
        def build_held():
            return --held(X)
        def build_held_other():
            return --held_other(X)
    """)
    assert (type(host.__dict__["spred"]) is str) == (era == "handle")
    assert host.build_import()[0] == "spred"
    assert host.build_alias()[0] == "spred"
    assert host.build_held()[0] == "spred"
    assert "other" not in host.__dict__
    assert host.build_held_other()[0] == mangle("sa_slib", "other")


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


@pytest.mark.parametrize("era", ERAS)
def test_analyze_mi_accepts_the_module_attribute(era):
    import clausal.examples.metainterpreters as mi
    from clausal.logic.specialization import analyze_mi
    cls = mi.solve
    assert isinstance(cls, PredicateMeta), "fixture no longer binds a class"
    expected = _pattern_key(analyze_mi(cls))
    binding = cls if era == "class" else mint_predicate_handle(_lm(mi).db, "solve")
    assert _pattern_key(analyze_mi(binding)) == expected
    assert expected[:2] == ("solve", 2)


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


# ── the handle head path ─────────────────────────────────────────────────────
#
# Found under the flip emulation, NOT fixed here (not contained): an importer
# that writes a clause for an imported predicate spells the head with field
# names derived from ITS OWN head (``gv_owned(teal),`` -> ``arg_0=teal``).  In
# the class era the importer's body re-mints a local class with those names,
# the head builds, and the mutation gate refuses the load.  A HANDLE builds
# against the OWNER's names (``gv_owned(NAME)``), so the head raises
# ClausalTermConstructionError first and the gate's refusal is never seen.


@pytest.mark.parametrize("era", [
    "class",
    pytest.param("handle", marks=pytest.mark.xfail(
        strict=True, raises=Exception,
        reason="the handle head path raises ClausalTermConstructionError "
               "before the gate refuses (importer-derived head field names)")),
])
def test_a_clobbering_import_head_is_refused_by_the_gate(era_loads, era):
    era_loads(era)
    names = ("tests.fixtures.gate_vocab", "tests.fixtures.gate_rival")
    saved = {n: sys.modules.pop(n, None) for n in names}
    try:
        vocab = _load_module(names[0], os.path.join(FIXTURES, "gate_vocab.clausal"))
        with pytest.raises(SyntaxError) as exc:
            _load_module(names[1], os.path.join(FIXTURES, "gate_rival.clausal"))
        assert "may not write gv_owned/1" in str(exc.value)
        assert len(_lm(vocab).db.row("gv_owned", 1).clauses) == 1
    finally:
        for n in names:
            sys.modules.pop(n, None)
            if saved[n] is not None:
                sys.modules[n] = saved[n]


def test_a_handle_head_construction_error_names_the_declaration_site():
    """The stale "no Database home yet" comment: the site IS on the owner's
    row (``PredRow.declared_at``), so a handle's head error names it rather
    than ``registered by: <unknown>``."""
    from clausal.logic.predicate import ClausalTermConstructionError, head_cell
    saved = sys.modules.pop("tests.fixtures.gate_vocab", None)
    try:
        vocab = _load_module("tests.fixtures.gate_vocab",
                             os.path.join(FIXTURES, "gate_vocab.clausal"))
        handle = mint_predicate_handle(_lm(vocab).db, "gv_owned")
        assert head_cell(handle, NAME="teal") == ("gv_owned", "teal")
        with pytest.raises(ClausalTermConstructionError) as exc:
            head_cell(handle, arg_0="teal")
        assert "gate_vocab.clausal:" in str(exc.value)
        assert "<unknown>" not in str(exc.value)
    finally:
        sys.modules.pop("tests.fixtures.gate_vocab", None)
        if saved is not None:
            sys.modules["tests.fixtures.gate_vocab"] = saved


@pytest.mark.parametrize("era", ERAS)
@pytest.mark.parametrize("by_name", [False, True])
def test_a_head_pattern_follows_the_same_rule(lister, era_loads, era, by_name):
    """``head_match``'s cell pattern for a dotted ``sa_hlib.hf(X)`` in a
    clause head: PLAIN when the host also imports ``hf`` by name (or in the
    class era, where a class spells its own name), MANGLED otherwise."""
    era_loads(era)
    lister("sa_hlib", """
        -module(sa_hlib, [hf(A)])
        hf(1),
    """)
    host = lister("sa_hhost", f"""
        -module(sa_hhost, [patq(T, X)])
        {"-import_from(sa_hlib, [hf])" if by_name else ""}
        -import_module(sa_hlib)
        patq(sa_hlib.hf(X), X) <- true
    """)
    lm = _lm(host)
    from clausal.logic.variables import Var, deref
    plain = by_name or era == "class"
    for functor in ("hf", mangle("sa_hlib", "hf")):
        X = Var()
        got = [deref(X) for _ in call("patq", (functor, 5), X, module=lm)]
        assert got == ([5] if (functor == "hf") == plain else []), functor
