"""W4b-2d task 7, the "small arms": four places that must answer the same
whether a module-dict predicate binding is still the ``PredicateMeta`` CLASS
or already the owner's mangled HANDLE, so the flip itself is only the binding
change.  Each was found by the flip dry run
(``implementation_plans/w4b2d-flip-dry-run-2026-09-24.md`` §1, §2):

* E (R7): ``listing(p)``, the bare form, on a handle fell into the atom arm
  and raised ``existence_error(procedure, 'm\\x1fp'/0)``;
* C (R8): ``analyze_mi(mi_module.solve)``, the direct Python API, raised
  ``'str' object has no attribute 'key'``;
* G (R5): step 4a read ``pred_cls._row``, so an imported ``-dynamic`` HANDLE
  was compiled locally and the gate refused ``gate_dyn_user`` as a
  redefinition;
* A2 (R3): a cell built from a handle carried the MANGLED functor, so the
  importer's ``assertz(gd_p(X))`` raised existence_error for
  ``'m\\x1fgd_p'/1``.

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
    """G in isolation: step 4a must not seed the importer's own dispatch for
    an imported ``-dynamic`` -- the owner's row keeps its one dispatch."""
    era_loads(era)
    owner, user = gate_dyn()
    twin = _lm(user).db.row("gd_p", 1, create=False)
    assert twin is None or twin.dispatch_fn is None or twin.clauses == []
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
    spelling is its identity."""
    from clausal.logic.compiler.terms_to_ast import _functor_spelling
    saved = sys.modules.pop("hide_owner", None)
    try:
        mod = _load_module("hide_owner", os.path.join(FIXTURES, "hide_owner.clausal"))
        db = _lm(mod).db
        secret = mangle("hide_owner", "hide_secret")
        assert _functor_spelling(secret, "x", db=db) == secret
        handle = mint_predicate_handle(db, "holds")
        assert _functor_spelling(handle, "x", db=db) == "holds"
        # The seam's flag keeps the W4-pinned qualified spelling (open
        # operator question, flip dry run §3.5).
        assert _functor_spelling(handle, "x", db=db, qualified_handle=True) == handle
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


def _out(goal, args, lm, capsys):
    capsys.readouterr()
    answers = list(call(goal, *args, module=lm))
    return len(answers), capsys.readouterr().out


@pytest.mark.parametrize("era", ERAS)
def test_bare_listing_of_the_binding_lists_the_predicate(lister, era_loads, era, capsys):
    """Both the Python call ``listing(<binding>)`` and a compiled
    ``listing(fib)`` (whose bare ``fib`` is a runtime load of the binding)."""
    era_loads(era)
    mod = lister("sa_e_fib", _FIB.format(name="sa_e_fib"))
    binding = mod.__dict__["fib"]
    assert (type(binding) is str) == (era == "handle"), "the flip did not happen"
    lm = _lm(mod)
    for goal, args in (("listing", (binding,)), ("show", ())):
        n, out = _out(goal, args, lm, capsys)
        assert n == 1, goal
        assert out.startswith("% fib/2 — 2 clause(s)\n"), (goal, out)
        assert out.count("fib(") == 2, (goal, out)


@pytest.mark.parametrize("era", ERAS)
def test_bare_listing_of_an_imported_binding_lists_the_owner(lister, era, capsys):
    """An ``-import_from``'d name lists the OWNER's clauses, with the owner
    loaded and with it popped from ``sys.modules`` (the Q0 registry)."""
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
    assert isinstance(md["colour"], PredicateMeta)
    if era == "handle":
        md["colour"] = mint_predicate_handle(_lm(owner).db, "colour")
    lm = _lm(user)
    for popped in (False, True):
        if popped:
            sys.modules.pop("sa_e_own", None)
        n, out = _out("listing", (md["colour"],), lm, capsys)
        assert n == 1 and out.startswith("% colour/1 — 2 clause(s)\n"), (popped, out)


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


def test_bare_listing_of_a_multi_arity_handle_lists_every_arity(lister, capsys):
    """A class names one bound arity; a handle names none, so every defined
    arity is listed, in arity order, rather than one being picked."""
    mod = _multi_arity(lister, "sa_e_multi")
    handle = mint_predicate_handle(_lm(mod).db, "p")
    n, out = _out("listing", (handle,), _lm(mod), capsys)
    assert n == 1
    lines = [ln for ln in out.splitlines() if ln.startswith("%")]
    assert lines == ["% p/1 — 1 clause(s)", "% p/2 — 1 clause(s)"]


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
