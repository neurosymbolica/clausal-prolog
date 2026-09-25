"""W4b-2b: the era-agnostic binding resolver.

Design authority: ``implementation_plans/w4b2-open-questions-2026-09-23.md``
(Question 2's family table and the controller's W4b-2 decomposition) and
``implementation_plans/w4b1-site-classification-2026-09-22.md`` (the 49
IDENTITY rows, families F1/F2).

Today a module-dict binding for a predicate is a ``PredicateMeta`` CLASS.
At W4b-2d it becomes a module-qualified mangled atom (a ``str``,
``"module\\x1fname"``).  49 call sites ask ``isinstance(x, PredicateMeta)``
to answer one of two questions:

  * F1 (23 rows) -- "give me the live ``PredRow``" (``._row``, ``.clauses``,
    ``.dispatch_fn``, ``.locked``, ``_lock()``, or a value handed to
    ``_install``/``analyze_mi``/a mutation gate's ``through=``).
  * F2 (15 rows) -- "is this specifically a predicate, not data?" at an
    EXACT arity (the predicate-name-as-atom coercion, plus
    ``-table``/``-discontiguous``/``-shallow`` directive-target typo
    guards).

Two functions answer them, both era-agnostic (correct whether *binding* is
still a ``PredicateMeta`` class or already a mangled atom) and both taking
*arity* as a REQUIRED keyword-only argument -- never guessed, per hazard 3:
a data atom misused in goal position arrives at a different arity than it
was declared at, so the resolver must never search ``arities_for`` or
otherwise infer one; the caller's own call site already knows the arity of
whatever term/clause/directive it is processing, in both eras alike.

``resolve_predicate_row`` (F1) returns the ``PredRow`` or ``None``.
``is_declared_predicate`` (F2) returns a strict ``bool``.  Two functions,
not one with a mode flag: the return SHAPES differ (an identity object vs.
a boolean) and forcing them through one signature would need exactly the
kind of flag argument that makes call sites harder to read, for no shared
control flow beyond "demangle, then ask the db" -- which is what the
private ``_resolve_mangled_owner`` helper factors out instead.

TDD note: written and run red before ``resolve_predicate_row`` /
``is_declared_predicate`` existed in ``clausal.logic.predicate`` -- see the
W4b-2b report for the observed ImportError.
"""
from __future__ import annotations

import dataclasses
import os

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.atoms import mangle
from clausal.logic.predicate import (
    is_declared_predicate, resolve_predicate_row,
)
from tests.predicate_api_support import class_arm_predicate


def _fixture_path(name: str) -> str:
    return os.path.join(os.path.dirname(__file__), "fixtures", name)


def _load_hide_owner():
    """Load the REAL ``-hide`` fixture under sys.modules key ``"hide_owner"``
    -- matching the module name ``mangle("hide_owner", ...)`` uses -- so
    ``_db_for_module_name("hide_owner")`` finds it for real.  No monkeypatch
    anywhere in this file (hazard 4): every mangled-atom test below either
    exercises an unloaded/foreign module (hazard 1c/1d) through the REAL
    ``_db_for_module_name``, or resolves through this REAL loaded module."""
    return _load_module("hide_owner", _fixture_path("hide_owner.clausal"))


# ── Hazard 1: six shapes, each with its own test, for BOTH functions ────────
#
# "A bare string that happens to spell something must not resolve" is the
# sharp one (1b below): W4b-1's accessor widened past its intended
# population by accepting any ``@dataclass``/bare string; this suite checks
# every one of the six shapes the brief names explicitly.

@dataclasses.dataclass
class Point:
    x: int
    y: int


# 1a. a @dataclass class

def test_1a_row_dataclass_class_does_not_resolve():
    assert resolve_predicate_row(Point, arity=2) is None


def test_1a_kind_dataclass_class_is_not_a_predicate():
    assert is_declared_predicate(Point, arity=2) is False


# 1b. a plain non-mangled str

def test_1b_row_plain_nonmangled_string_does_not_resolve():
    assert resolve_predicate_row("holds", arity=1) is None


def test_1b_kind_plain_nonmangled_string_is_not_a_predicate():
    assert is_declared_predicate("holds", arity=1) is False


# 1c. a mangled str whose module is not loaded

def test_1c_row_mangled_atom_unloaded_module_does_not_resolve():
    ghost = mangle("w4b2b_no_such_module_ever_loaded", "p")
    assert resolve_predicate_row(ghost, arity=1) is None


def test_1c_kind_mangled_atom_unloaded_module_is_not_a_predicate():
    ghost = mangle("w4b2b_no_such_module_ever_loaded", "p")
    assert is_declared_predicate(ghost, arity=1) is False


# 1d. a mangled str naming a real PYTHON module (not a Clausal one)

def test_1d_row_mangled_atom_naming_a_real_python_module_does_not_resolve():
    import json  # noqa: F401 -- make sure it is actually loaded
    handle = mangle("json", "loads")
    assert resolve_predicate_row(handle, arity=1) is None


def test_1d_kind_mangled_atom_naming_a_real_python_module_is_not_a_predicate():
    import json  # noqa: F401
    handle = mangle("json", "loads")
    assert is_declared_predicate(handle, arity=1) is False


# 1e. None

def test_1e_row_none_does_not_resolve():
    assert resolve_predicate_row(None, arity=0) is None


def test_1e_kind_none_is_not_a_predicate():
    assert is_declared_predicate(None, arity=0) is False


# 1f. an arbitrary object

def test_1f_row_arbitrary_object_does_not_resolve():
    assert resolve_predicate_row(object(), arity=0) is None
    assert resolve_predicate_row(42, arity=0) is None
    assert resolve_predicate_row(("not", "a", "binding"), arity=0) is None


def test_1f_kind_arbitrary_object_is_not_a_predicate():
    assert is_declared_predicate(object(), arity=0) is False
    assert is_declared_predicate(42, arity=0) is False
    assert is_declared_predicate(("not", "a", "binding"), arity=0) is False


# ── Class arm: today's era, a PredicateMeta binding ─────────────────────────

def test_row_unbound_predicate_class_has_no_row_yet():
    """``cls._row`` is None until first use (``__init__``) -- the resolver
    must read it directly, not mint one via ``_state_row()``, or every F1
    call site that today tests ``cls._row is not None`` as a bailout would
    silently start seeing a row that was never really there."""
    P = class_arm_predicate("W4b2bUnbound", ["a", "b"])
    assert resolve_predicate_row(P, arity=2) is None


def test_row_bound_predicate_class_returns_the_live_row_object():
    P = class_arm_predicate("W4b2bBound", ["a", "b"])
    row = P._state_row()
    assert resolve_predicate_row(P, arity=2) is row


def test_kind_predicate_class_is_a_predicate_regardless_of_row_binding():
    """F2's question is identity (a PredicateMeta class IS a predicate by
    construction), not row state -- matches today's bare ``isinstance``,
    at the class's OWN (matching) arity."""
    P = class_arm_predicate("W4b2bKind", ["a"])
    assert is_declared_predicate(P, arity=1) is True
    P._state_row()
    assert is_declared_predicate(P, arity=1) is True


def test_kind_predicate_class_is_arity_strict_in_both_eras():
    """RULED 2026-09-23 (review round): the class arm is arity-STRICT, same
    as the mangled-atom arm -- not arity-blind like today's bare
    ``isinstance(x, PredicateMeta)``.

    F2's own question is "is this a predicate AT THIS EXACT ARITY"; a
    migrated call site that kept arity-blind behaviour today would have
    silently turned arity-strict the moment the SAME site met a mangled
    atom instead of a class (arm 2 already requires an exact match) -- a
    behaviour change landing at the one moment no gate covers it.  Ruling
    it strict in both eras up front means any site that actually depended
    on arity-blindness fails the full suite NOW, not at the flip."""
    P = class_arm_predicate("W4b2bArityStrict", ["a", "b"])
    assert is_declared_predicate(P, arity=2) is True
    assert is_declared_predicate(P, arity=99) is False
    assert is_declared_predicate(P, arity=0) is False


def test_kind_bare_predicate_class_with_no_fields_of_its_own_does_not_raise():
    """A bare ``class X(metaclass=PredicateMeta): pass`` never gets
    ``cls._fields`` set as a class attribute unless its own body declares
    it (row 5 of the site-classification table verifies this with
    ``X._fields`` raising ``AttributeError``) -- the arity-strict class arm
    must answer ``False`` gracefully for it, not crash the 15 F2 call
    sites this accessor now serves."""
    from clausal.logic.predicate import PredicateMeta
    bare = PredicateMeta("W4b2bBareNoFields", (), {})
    assert not hasattr(bare, "_fields")
    # getattr(..., "_fields", ()) -> (), so arity 0 matches -- and,
    # critically, arity 3 does NOT raise, it answers False.
    assert is_declared_predicate(bare, arity=0) is True
    assert is_declared_predicate(bare, arity=3) is False


# ── Positive control: the fixture declares what this suite assumes ─────────

def test_positive_control_hide_owner_declares_holds_at_arity_1():
    """Guards against a false-negative "both None because nothing loaded"
    read of the tests below (see project memory on instruments that fail
    open) -- confirms the fixture's OWN database, independent of the
    resolver under test, actually knows what these tests assume it does."""
    mod = _load_hide_owner()
    db = mod.__dict__["$module"].db
    assert db.declared_kind("holds", 1) == "predicate"
    assert 1 in db.arities_for("holds")
    # and the hidden atom is NOT registered anywhere in the db (Fact B,
    # w4b2-open-questions-2026-09-23.md Q1.1) -- both None, not "data".
    assert db.declared_kind("hide_secret", 0) is None


# ── Hazard 4: a REAL loaded module, no monkeypatch anywhere ─────────────────

def test_row_mangled_predicate_resolves_through_a_real_loaded_module():
    _load_hide_owner()
    row = resolve_predicate_row(mangle("hide_owner", "holds"), arity=1)
    assert row is not None
    assert row.clauses  # holds(hide_secret) -- one real clause


def test_row_mangled_predicate_same_arity_2_resolves_too():
    _load_hide_owner()
    row = resolve_predicate_row(mangle("hide_owner", "same"), arity=2)
    assert row is not None
    assert row.clauses


def test_kind_mangled_predicate_is_a_predicate_through_a_real_loaded_module():
    _load_hide_owner()
    assert is_declared_predicate(mangle("hide_owner", "holds"), arity=1) is True
    assert is_declared_predicate(mangle("hide_owner", "label"), arity=1) is True
    assert is_declared_predicate(mangle("hide_owner", "same"), arity=2) is True


def test_row_mangled_hide_data_atom_does_not_resolve_as_a_row():
    """-hide never calls declare_functor/mark_predicate_export (Fact B in
    the open-questions doc) -- there is no row for a hidden atom, ever, and
    the resolver must not manufacture one."""
    _load_hide_owner()
    assert resolve_predicate_row(mangle("hide_owner", "hide_secret"), arity=0) is None


def test_kind_mangled_hide_data_atom_is_not_a_predicate():
    _load_hide_owner()
    assert is_declared_predicate(mangle("hide_owner", "hide_secret"), arity=0) is False


# ── Hazard 3: the arity comes from the call site, never guessed ────────────

def test_row_wrong_arity_does_not_resolve_even_though_the_name_is_declared():
    """holds/1 is declared; holds/0 is not.  The resolver must not search
    ``arities_for`` (or anything else) to find a nearby arity that DOES
    work -- a data atom misused in goal position must fail exactly this
    way, not be silently rescued at the wrong arity."""
    _load_hide_owner()
    assert resolve_predicate_row(mangle("hide_owner", "holds"), arity=0) is None


def test_kind_wrong_arity_is_not_a_predicate_even_though_the_name_is_declared():
    _load_hide_owner()
    assert is_declared_predicate(mangle("hide_owner", "holds"), arity=0) is False
