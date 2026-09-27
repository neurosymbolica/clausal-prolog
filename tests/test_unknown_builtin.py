"""Tests for the Kleene ``Undefined`` builtin (piece 1 of
todo/kleene-unknown-builtin-and-stdlib.md) and the ``tri_get/3`` builtin.

Covers the acceptance criteria:
  - the ``Undefined`` singleton: repr, bool() raises, copy/deepcopy/pickle
    identity, ground-constant unification;
  - resolution in any .clausal module including ``-strict_atoms`` with no
    declaration/import/export, and process-wide identity across two separately
    loaded modules;
  - a bare ``Undefined`` in goal position → compile-time error naming the
    offending predicate;
  - outbound ``clausal_to_prolog`` maps ``Undefined`` → atom ``unknown``;
    inbound ``prolog_to_clausal`` leaves atom ``unknown`` unchanged;
  - ``tri_get/3``: present key → stored value; absent key → ``Undefined``;
    checking mode; and edge cases mirroring ``get/3`` (soft, never throws).
"""

from __future__ import annotations

import copy
import os
import pickle
import tempfile

import pytest

from clausal.terms import Undefined, DictTerm, Call, LoadName
from clausal.logic.database import Module
from clausal.logic.solve import solve
from clausal.logic.variables import Var, Trail, deref, unify


# ── Singleton behaviour ───────────────────────────────────────────────────────


class TestUnknownSingleton:
    def test_repr_and_str(self):
        assert repr(Undefined) == "Undefined"
        assert str(Undefined) == "Undefined"

    def test_bool_raises(self):
        with pytest.raises(TypeError):
            bool(Undefined)

    def test_hashable(self):
        # Clause indexing needs a stable hash; identity hash is fine.
        assert hash(Undefined) == hash(Undefined)
        d = {Undefined: 1}
        assert d[Undefined] == 1

    def test_copy_deepcopy_pickle_identity(self):
        assert copy.copy(Undefined) is Undefined
        assert copy.deepcopy(Undefined) is Undefined
        assert pickle.loads(pickle.dumps(Undefined)) is Undefined

    def test_direct_construction_returns_singleton(self):
        # Even a direct call to the type yields the one instance.
        from clausal.terms import _UndefinedType
        assert _UndefinedType() is Undefined

    def test_distinct_from_none_and_bools(self):
        assert Undefined is not None
        assert Undefined is not True
        assert Undefined is not False


# ── Unification (step 3): ordinary ground constant, identity equality ─────────


class TestUnknownUnification:
    def test_var_binds_to_unknown(self):
        t = Trail()
        v = Var()
        assert bool(unify(v, Undefined, t))
        assert deref(v) is Undefined

    def test_unknown_unifies_with_itself(self):
        t = Trail()
        assert bool(unify(Undefined, Undefined, t))

    def test_unknown_does_not_unify_with_true_false_none(self):
        for other in (True, False, None, "unknown", 0):
            t = Trail()
            assert not bool(unify(Undefined, other, t)), other


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
    _SRC = "-module({mod}, [p(A)])\np(Undefined),\n"
    _SRC_STRICT = "-module({mod}, [p(A)])\n-strict_atoms\np(Undefined),\n"

    def test_resolves_no_declaration(self):
        mod = _load_src("_ub_plain", self._SRC.format(mod="_ub_plain"))
        assert _query_p(mod, None) == [Undefined]

    def test_resolves_under_strict_atoms(self):
        mod = _load_src("_ub_strict", self._SRC_STRICT.format(mod="_ub_strict"))
        # -strict_atoms would reject an undeclared bare atom; Undefined is a real
        # binding, so it resolves anyway.
        assert _query_p(mod, None) == [Undefined]

    def test_process_wide_identity_across_two_modules(self):
        m1 = _load_src("_ub_id1", self._SRC.format(mod="_ub_id1"))
        m2 = _load_src("_ub_id2", self._SRC.format(mod="_ub_id2"))
        [u1] = _query_p(m1, None)
        [u2] = _query_p(m2, None)
        assert u1 is Undefined
        assert u2 is Undefined
        assert u1 is u2


# ── Goal-position guard (step 4) ──────────────────────────────────────────────


class TestUnknownGoalPosition:
    def test_bare_unknown_in_body_is_compile_error(self):
        from clausal.logic.compiler.terms_to_goalop import BareGoalUndefinedError
        src = "-module(_ub_goal, [q(A)])\nq(_x) <- (\n    Undefined\n)\n"
        with pytest.raises(BareGoalUndefinedError) as exc:
            _load_src("_ub_goal", src)
        # The offending predicate is named in the message.
        assert "q/1" in str(exc.value)
        assert "Undefined" in str(exc.value)


# ── Bare-query globals carry injected builtins (query-globals gap) ────────────
#
# Regression for todo/query-globals-injected-builtins-gap.md: the bare-query
# compilation path derives its compiled globals only from ``module.module_dict``,
# which need not carry the ``predicate_builtins`` injections.  A name that
# ``term_to_ast_expr`` emits as a bare ``Name`` (Var/Compound/DictTerm/SetTerm/
# KWTerm/Undefined, plus the $-prefixed engine helpers) must therefore resolve from
# the compiler-seeded base_globals, not the module dict.  The generic fix seeds
# every predicate's base_globals from ``INJECTED_RUNTIME_BUILTINS`` (single source
# of truth shared with import_hook.predicate_builtins).


class TestQueryGlobalsInjectedBuiltins:
    def test_unknown_resolves_in_bare_query_with_empty_module_dict(self):
        # The exact gap: a Module whose module_dict lacks the injections.  Before
        # the generic fix this raised NameError('Undefined') during query compile.
        from clausal.pythonic_ast.nodes import Unify
        mod = Module("_qg_empty", module_dict={})
        v = Var()
        t = Trail()
        bound = []
        for _ in solve(Unify(left=v, right=Undefined), mod, t):
            # Read the binding inside the loop — backtracking unwinds the trail
            # once the generator is exhausted.
            bound.append(deref(v))
        assert len(bound) == 1
        # Process-wide identity is preserved through query compilation.
        assert bound[0] is Undefined

    def test_all_injected_public_builtins_present_in_query_globals(self):
        # Generic guard: every public (non-$-prefixed) injected runtime binding
        # must land in a compiled bare-query's globals, so a *future* injection
        # cannot silently regress the query path (which is what happened with
        # Undefined).  $-prefixed engine internals are intentionally excluded (they
        # are referenced only under the $ name; see A12-F004).
        from clausal.logic.compiler.predicate import INJECTED_RUNTIME_BUILTINS
        from clausal.logic.solve import _compile_as_query

        mod = Module("_qg_globals", module_dict={})
        # A trivial always-true goal is enough to force query compilation.
        goal = ("=", Var(), Var())
        # _compile_as_query returns (dispatch_fn, param_pairs); the dispatch fn's
        # __globals__ are the seeded base_globals (+ module dict, empty here).
        dispatch_fn, _ = _compile_as_query(goal, mod)
        g = dispatch_fn.__globals__
        public = {n: v for n, v in INJECTED_RUNTIME_BUILTINS.items()
                  if not n.startswith("$")}
        missing = [n for n in public if n not in g]
        assert not missing, f"injected builtins missing from query globals: {missing}"
        # The bindings are the SAME objects (identity), not shadowed copies.
        assert g["Undefined"] is Undefined
        assert all(g[n] is public[n] for n in public)


# ── Outbound Prolog mapping (step 5) ──────────────────────────────────────────


class TestPrologRoundTrip:
    def test_outbound_undefined_becomes_atom(self):
        """The three truth values go out as the three ISO/XSB atoms.  The third
        one is ``undefined``, matching XSB and SWI — it was ``unknown`` before
        the builtin was renamed, and the atom moved with the name."""
        from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
        src = "-module(k, [t(A)])\nt(Undefined),\nt(True),\nt(False),\n"
        out = clausal_source_to_prolog(src)
        assert "t(undefined)." in out
        assert "t(true)." in out
        assert "t(false)." in out

    def test_outbound_lowercase_aliases_match_canonical(self):
        """The aliases are resolved before the Prolog writer sees them, so the
        two spellings produce byte-identical output."""
        from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
        canonical = clausal_source_to_prolog(
            "-module(k, [t(A)])\nt(Undefined),\nt(True),\nt(False),\n"
        )
        aliased = clausal_source_to_prolog(
            "-module(k, [t(A)])\nt(undefined),\nt(true),\nt(false),\n"
        )
        assert aliased == canonical

    def test_inbound_unknown_atom_unchanged(self):
        # Decision 4: prolog_to_clausal is NOT rewired — atom `unknown` stays a
        # plain atom (does NOT become the builtin), preserving import identity
        # semantics.  It resolves to a zero-arity PredicateMeta atom, not the
        # Undefined singleton.
        from clausal.tools.prolog_to_clausal import prolog_to_clausal
        out = prolog_to_clausal("t(unknown).")
        assert "unknown" in out
        # The translated source references the atom `unknown`, not `Undefined`.
        assert "Undefined" not in out


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
        assert sols[0][2] is Undefined

    def test_checking_mode_absent_key(self):
        # tri_get(P, K, Undefined) with b absent succeeds (checking mode).
        d = DictTerm({"a": True})
        assert _succeeds("tri_get", d, "b", Undefined)

    def test_checking_mode_present_key(self):
        d = DictTerm({"a": True})
        assert _succeeds("tri_get", d, "a", True)
        assert not _succeeds("tri_get", d, "a", False)
        # present key does NOT match Undefined
        assert not _succeeds("tri_get", d, "a", Undefined)

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
