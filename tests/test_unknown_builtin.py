"""Tests for the Kleene ``Unknown`` builtin (piece 1 of
todo/kleene-unknown-builtin-and-stdlib.md) and the ``tri_get/3`` builtin.

Covers the acceptance criteria:
  - the ``Unknown`` singleton: repr, bool() raises, copy/deepcopy/pickle
    identity, ground-constant unification;
  - resolution in any .clausal module including ``-strict_atoms`` with no
    declaration/import/export, and process-wide identity across two separately
    loaded modules;
  - a bare ``Unknown`` in goal position → compile-time error naming the
    offending predicate;
  - outbound ``clausal_to_prolog`` maps ``Unknown`` → atom ``unknown``;
    inbound ``prolog_to_clausal`` leaves atom ``unknown`` unchanged;
  - ``tri_get/3``: present key → stored value; absent key → ``Unknown``;
    checking mode; and edge cases mirroring ``get/3`` (soft, never throws).
"""

from __future__ import annotations

import copy
import os
import pickle
import tempfile

import pytest

from clausal.terms import Unknown, DictTerm, Call, LoadName
from clausal.logic.database import Module
from clausal.logic.solve import solve
from clausal.logic.variables import Var, Trail, deref, unify


# ── Singleton behaviour ───────────────────────────────────────────────────────


class TestUnknownSingleton:
    def test_repr_and_str(self):
        assert repr(Unknown) == "Unknown"
        assert str(Unknown) == "Unknown"

    def test_bool_raises(self):
        with pytest.raises(TypeError):
            bool(Unknown)

    def test_hashable(self):
        # Clause indexing needs a stable hash; identity hash is fine.
        assert hash(Unknown) == hash(Unknown)
        d = {Unknown: 1}
        assert d[Unknown] == 1

    def test_copy_deepcopy_pickle_identity(self):
        assert copy.copy(Unknown) is Unknown
        assert copy.deepcopy(Unknown) is Unknown
        assert pickle.loads(pickle.dumps(Unknown)) is Unknown

    def test_direct_construction_returns_singleton(self):
        # Even a direct call to the type yields the one instance.
        from clausal.terms import _UnknownType
        assert _UnknownType() is Unknown

    def test_distinct_from_none_and_bools(self):
        assert Unknown is not None
        assert Unknown is not True
        assert Unknown is not False


# ── Unification (step 3): ordinary ground constant, identity equality ─────────


class TestUnknownUnification:
    def test_var_binds_to_unknown(self):
        t = Trail()
        v = Var()
        assert bool(unify(v, Unknown, t))
        assert deref(v) is Unknown

    def test_unknown_unifies_with_itself(self):
        t = Trail()
        assert bool(unify(Unknown, Unknown, t))

    def test_unknown_does_not_unify_with_true_false_none(self):
        for other in (True, False, None, "unknown", 0):
            t = Trail()
            assert not bool(unify(Unknown, other, t)), other


# ── Resolution in .clausal modules (step 2) ───────────────────────────────────


def _load_src(name: str, src: str):
    from clausal.import_hook import _load_module
    d = tempfile.mkdtemp()
    path = os.path.join(d, f"{name}.clausal")
    with open(path, "w") as f:
        f.write(src)
    return _load_module(name, path)


def _query_p(mod, argvar):
    """Run p(X) over a loaded module, returning the single bound value."""
    from clausal.logic.solve import query
    lm = mod.__dict__["$module"]
    v = Var()
    goal = Call(func=LoadName(name="p"), args=[v], kwargs=[])
    rows = list(query(goal, {"x": v}, lm))
    return [r["x"] for r in rows]


class TestUnknownResolvesInModules:
    _SRC = "-module({mod}, [p(A)])\np(Unknown),\n"
    _SRC_STRICT = "-module({mod}, [p(A)])\n-strict_atoms\np(Unknown),\n"

    def test_resolves_no_declaration(self):
        mod = _load_src("_ub_plain", self._SRC.format(mod="_ub_plain"))
        assert _query_p(mod, None) == [Unknown]

    def test_resolves_under_strict_atoms(self):
        mod = _load_src("_ub_strict", self._SRC_STRICT.format(mod="_ub_strict"))
        # -strict_atoms would reject an undeclared bare atom; Unknown is a real
        # binding, so it resolves anyway.
        assert _query_p(mod, None) == [Unknown]

    def test_process_wide_identity_across_two_modules(self):
        m1 = _load_src("_ub_id1", self._SRC.format(mod="_ub_id1"))
        m2 = _load_src("_ub_id2", self._SRC.format(mod="_ub_id2"))
        [u1] = _query_p(m1, None)
        [u2] = _query_p(m2, None)
        assert u1 is Unknown
        assert u2 is Unknown
        assert u1 is u2


# ── Goal-position guard (step 4) ──────────────────────────────────────────────


class TestUnknownGoalPosition:
    def test_bare_unknown_in_body_is_compile_error(self):
        from clausal.logic.compiler.terms_to_goalop import BareGoalUnknownError
        src = "-module(_ub_goal, [q(A)])\nq(_x) <- (\n    Unknown\n)\n"
        with pytest.raises(BareGoalUnknownError) as exc:
            _load_src("_ub_goal", src)
        # The offending predicate is named in the message.
        assert "q/1" in str(exc.value)
        assert "Unknown" in str(exc.value)


# ── Outbound Prolog mapping (step 5) ──────────────────────────────────────────


class TestPrologRoundTrip:
    def test_outbound_unknown_becomes_atom(self):
        from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
        src = "-module(k, [t(A)])\nt(Unknown),\nt(True),\nt(False),\n"
        out = clausal_source_to_prolog(src)
        assert "t(unknown)." in out
        assert "t(true)." in out
        assert "t(false)." in out

    def test_inbound_unknown_atom_unchanged(self):
        # Decision 4: prolog_to_clausal is NOT rewired — atom `unknown` stays a
        # plain atom (does NOT become the builtin), preserving import identity
        # semantics.  It resolves to a zero-arity PredicateMeta atom, not the
        # Unknown singleton.
        from clausal.tools.prolog_to_clausal import prolog_to_clausal
        out = prolog_to_clausal("t(unknown).")
        assert "unknown" in out
        # The translated source references the atom `unknown`, not `Unknown`.
        assert "Unknown" not in out


# ── tri_get/3 builtin (step 7) ────────────────────────────────────────────────


def _goal(name, *args):
    return Call(func=LoadName(name=name), args=list(args), kwargs=[])


def _sols(name, *args):
    var_positions = {i: a for i, a in enumerate(args) if isinstance(a, Var)}
    t = Trail()
    results = []
    for _ in solve(_goal(name, *args), Module("test"), t):
        results.append({i: deref(v) for i, v in var_positions.items()})
    return results


def _succeeds(name, *args):
    return bool(list(solve(_goal(name, *args), Module("test"))))


class TestTriGet:
    def test_present_key_binds_value(self):
        d = DictTerm({"a": True})
        v = Var()
        sols = _sols("tri_get", d, "a", v)
        assert len(sols) == 1
        assert sols[0][2] is True

    def test_absent_key_binds_unknown(self):
        d = DictTerm({"a": True})
        v = Var()
        sols = _sols("tri_get", d, "b", v)
        assert len(sols) == 1
        assert sols[0][2] is Unknown

    def test_checking_mode_absent_key(self):
        # tri_get(P, K, Unknown) with b absent succeeds (checking mode).
        d = DictTerm({"a": True})
        assert _succeeds("tri_get", d, "b", Unknown)

    def test_checking_mode_present_key(self):
        d = DictTerm({"a": True})
        assert _succeeds("tri_get", d, "a", True)
        assert not _succeeds("tri_get", d, "a", False)
        # present key does NOT match Unknown
        assert not _succeeds("tri_get", d, "a", Unknown)

    def test_deterministic_single_solution(self):
        d = DictTerm({"a": 1, "b": 2})
        v = Var()
        assert len(_sols("tri_get", d, "a", v)) == 1
        assert len(_sols("tri_get", d, "zzz", v)) == 1

    def test_soft_on_non_dict(self):
        # Mirrors get/3: non-dict Dict fails softly (never throws).
        v = Var()
        assert not _succeeds("tri_get", 42, "a", v)
        assert not _succeeds("tri_get", Var(), "a", v)

    def test_soft_on_unbound_key(self):
        d = DictTerm({"a": 1})
        v = Var()
        assert not _succeeds("tri_get", d, Var(), v)

    def test_matches_get3_present_key(self):
        # tri_get and get/3 agree on the present-key path.
        d = DictTerm({"a": 99})
        v1, v2 = Var(), Var()
        s_tri = _sols("tri_get", d, "a", v1)
        s_get = _sols("get", d, "a", v2)
        assert s_tri[0][2] == s_get[0][2] == 99
