"""Tests for DictTerm and SetTerm compiler integration (Phase 2).

Covers:
  - C-level __unify__ protocol: DictTerm pairwise unification, SetTerm equality
  - Trail undo on failed DictTerm unification
  - NotImplemented return for type mismatch
  - Fixture integration: dict_set_patterns.clausal (13 tests)
  - Backtracking with DictTerm clauses
"""

from __future__ import annotations

import os
import pytest
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.logic.solve import call, solve, _deref_walk
from clausal.import_hook import _load_module
from clausal.terms import DictTerm, SetTerm

_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture():
    return _load_module(
        "dict_set_patterns",
        os.path.join(_FIXTURE_DIR, "dict_set_patterns.clausal"),
    )


# ── C-level __unify__ protocol ───────────────────────────────────────────────

class TestCLevelUnify:
    def test_dictterm_unify_with_vars(self):
        # nv
        t = Trail()
        x, y = Var(), Var()
        d1 = DictTerm({"a": x, "b": 2})
        d2 = DictTerm({"a": 42, "b": y})
        assert unify(d1, d2, t)
        assert deref(x) == 42
        assert deref(y) == 2

    def test_dictterm_unify_fails_different_keys(self):
        # nv
        t = Trail()
        assert not unify(DictTerm({"a": 1}), DictTerm({"b": 1}), t)

    def test_dictterm_unify_fails_value_mismatch(self):
        # nv
        t = Trail()
        assert not unify(DictTerm({"a": 1}), DictTerm({"a": 2}), t)

    def test_dictterm_unify_trail_undo(self):
        """On failure, __unify__ undoes partial bindings."""
        # nv
        t = Trail()
        x = Var()
        d1 = DictTerm({"a": x, "b": 1})
        d2 = DictTerm({"a": 42, "b": 99})  # b mismatch
        assert not unify(d1, d2, t)
        assert not isinstance(deref(x), int)

    def test_setterm_unify_same(self):
        # nv
        t = Trail()
        assert unify(SetTerm([1, 2, 3]), SetTerm([3, 1, 2]), t)

    def test_setterm_unify_different(self):
        # nv
        t = Trail()
        assert not unify(SetTerm([1, 2]), SetTerm([1, 3]), t)

    def test_var_unifies_with_dictterm(self):
        # nv
        t = Trail()
        x = Var()
        d = DictTerm({"k": "v"})
        assert unify(x, d, t)
        assert deref(x) == d

    def test_var_unifies_with_setterm(self):
        # nv
        t = Trail()
        x = Var()
        s = SetTerm([1, 2])
        assert unify(x, s, t)
        assert deref(x) == s

    def test_dictterm_unifies_with_plain_dict(self):
        # nv — DictTerm and plain dict are treated as equivalent under
        # unification. See TestDictTermPlainDictEquality in
        # test_dict_set_builtins.py for the full matrix.
        t = Trail()
        assert unify(DictTerm({"a": 1}), {"a": 1}, t)

    def test_empty_dictterms_unify(self):
        # nv
        t = Trail()
        assert unify(DictTerm({}), DictTerm({}), t)

    def test_nested_dictterm_unify(self):
        # nv
        t = Trail()
        x = Var()
        d1 = DictTerm({"inner": DictTerm({"val": x})})
        d2 = DictTerm({"inner": DictTerm({"val": 99})})
        assert unify(d1, d2, t)
        assert deref(x) == 99

    def test_setterm_unifies_with_plain_set(self):
        # nv — SetTerm and plain set/frozenset are equivalent under
        # unification. Full matrix in TestSetTermPlainSetEquality in
        # test_dict_set_builtins.py.
        t = Trail()
        assert unify(SetTerm([1, 2]), frozenset([1, 2]), t)
        assert unify(SetTerm([1, 2]), {1, 2}, Trail())

    def test_empty_setterms_unify(self):
        # nv
        t = Trail()
        assert unify(SetTerm([]), SetTerm([]), t)


# ── Fixture integration ─────────────────────────────────────────────────────

class TestDictSetFixture:
    """Integration tests via dict_set_patterns.clausal fixture."""

    @pytest.fixture(scope="class")
    def mod(self):
        return _load_fixture()

    @pytest.fixture(scope="class")
    def logic_mod(self, mod):
        return mod.__dict__["$module"]

    def _query_test(self, mod, logic_mod, test_name):
        result = Var()
        sols = [deref(result) for _ in call("Test", test_name, module=logic_mod)]
        return sols

    def test_origin(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "origin")

    def test_x_axis(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "x_axis")

    def test_get_x(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "get_x")

    def test_get_y(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "get_y")

    def test_nested_city(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "nested city")

    def test_make_point(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "make_point")

    def test_dict_unify(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "dict unify")

    def test_dict_key_mismatch(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "dict key mismatch fails")

    def test_set_match(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "set match")

    def test_set_primary(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "set primary")

    def test_set_mismatch(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "set mismatch fails")

    def test_var_binds_dict(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "var binds dict")

    def test_empty_dict(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "empty dict")

    # ── Dict subscript read: V is P[key] (dict-native-profile-api item 1) ──

    def test_subscript_str_key_a(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "subscript str key a")

    def test_subscript_str_key_b(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "subscript str key b")

    def test_subscript_int_key(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "subscript int key")

    def test_subscript_via_var(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "subscript via var")

    def test_subscript_value_var(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "subscript value var")

    def test_subscript_missing_throws(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "subscript missing throws")

    def test_subscript_nonground_errors(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "subscript nonground errors")

    # ── item 2: KEY in P key membership ──

    def test_in_present_key(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "in present key")

    def test_in_absent_key_fails(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "in absent key fails")

    def test_in_is_key_not_value(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "in is key not value")

    def test_in_enumerates_keys(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "in enumerates keys")

    def test_in_pair_mode(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "in pair mode")

    # ── item 3: get/3, get/4 ──

    def test_get_present(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "get present")

    def test_get_absent_fails(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "get absent fails")

    def test_get_value_var(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "get value var")

    def test_get4_present(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "get4 present")

    def test_get4_default(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "get4 default")

    # ── item 4: splat/merge ──

    def test_merge_override(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "merge override")

    def test_merge_default_order(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "merge default order")

    def test_merge_addkey(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "merge addkey")

    def test_merge_value_var(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "merge value var")

    def test_merge_multi_splat(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "merge multi splat")

    # ── item 5: delete/3 ──

    def test_delete_removes_key(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "delete removes key")

    def test_delete_keeps_original(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "delete keeps original")

    def test_delete_absent_throws(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "delete absent throws")

    # ── hardening: object/source type guards ──

    def test_subscript_nondict_object_errors(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "subscript nondict object errors")

    def test_get_nondict_fails(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "get nondict fails")

    def test_splat_unbound_source_errors(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "splat unbound source errors")

    def test_splat_nondict_source_errors(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "splat nondict source errors")

    def test_get_unhashable_key_fails(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "get unhashable key fails")

    def test_get4_unhashable_key_fails(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "get4 unhashable key fails")

    def test_delete_unhashable_key_throws(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "delete unhashable key throws")

    # ── atom-key dict literals ──

    def test_atom_key_subscript(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "atom key subscript")

    def test_atom_key_subscript_bar(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "atom key subscript bar")

    def test_atom_key_get(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "atom key get")

    def test_atom_key_in(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "atom key in")

    def test_atom_key_unify(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "atom key unify")

    def test_atom_key_merge(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "atom key merge")

    def test_atom_key_delete(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "atom key delete")

    def test_atom_key_same_as_string(self, mod, logic_mod):
        # nv
        # P3-1 atom pivot (§1b/R2): atom(X) collapses onto every str, so an
        # atom key `foo` and a string key "foo" are the SAME key. Inverted
        # from the pre-pivot "distinct" pin; see
        # phase3-decomposition-and-p31-atom-pivot.md Task 7 work item 2.
        # The broader dict/set-vs-atom audit stays Phase 4 scope.
        assert self._query_test(mod, logic_mod, "atom key same as string")

    # ── dot attribute-access sugar: P.key ≡ P[key] ──

    @pytest.mark.parametrize("name", [
        "dot atom key",
        "dot equals bracket",
        "dot variable key",
        "dot chained",
        "dot chained equals bracket",
        "dot in argument position",
        "dot in comparison",
        "dot under not",
        "dot value var aliases",
        "dot missing key throws",
        "dot nondict throws",
        "dot unbound base throws",
        "bracket unbound base throws",
        "dot has no dot functor",
        "dot does not unify with a dot compound",
        "dot inside findall",
    ])
    def test_dot_attribute_access(self, mod, logic_mod, name):
        # nv
        assert self._query_test(mod, logic_mod, name)


# ── Dot attribute-access sugar: load-time behaviour ──────────────────────────

class TestDotAttributeAccessLoad:
    """``P.key`` is sugar for ``P[key]`` — same resolution, same load errors.

    See docs/superpowers/specs/2026-07-29-dot-attribute-access-design.md.
    """

    def _load_src(self, tmp_path, src, name):
        path = tmp_path / f"{name}.clausal"
        path.write_text(src)
        return _load_module(name, str(path))

    def test_undeclared_key_is_load_time_name_error(self, tmp_path):
        """Strict atoms: an undeclared bare key fails at load, not at run."""
        # nv
        src = (
            "-private([declared])\n"
            "chk(PROF) <- (V is PROF.undeclared_key, V is 1)\n"
        )
        with pytest.raises(NameError, match="undeclared atom"):
            self._load_src(tmp_path, src, "dotstrict_undeclared")

    def test_declared_key_loads(self, tmp_path):
        """The same clause with the key declared loads and runs."""
        # nv
        src = (
            "-private([declared])\n"
            "chk(PROF) <- (V is PROF.declared, V is 1)\n"
        )
        mod = self._load_src(tmp_path, src, "dotstrict_declared")
        logic_mod = mod.__dict__["$module"]
        declared = mod.__dict__["declared"]
        assert list(call("chk", DictTerm({declared: 1}), module=logic_mod))

    def test_method_call_form_still_rejected(self, tmp_path):
        """``P.foo(A)`` stays a SyntaxError — the shape is reserved."""
        # nv
        src = (
            "-private([foo])\n"
            "chk(PROF, X) <- PROF.foo(X)\n"
        )
        with pytest.raises(SyntaxError, match="[Mm]ethod-call"):
            self._load_src(tmp_path, src, "dotcall_rejected")


# ── Read-once lowering ───────────────────────────────────────────────────────

class TestDictReadOnceLowering:
    """A dict read is a goal at its first-occurrence position, read once.

    Repeated ``P.k`` / ``P[k]`` in one scope share one read; the read
    re-executes on redo; and it is never lifted out of a disjunction arm, a
    negation, or an if-then-else branch.  See
    docs/superpowers/specs/2026-07-29-dot-attribute-access-design.md.
    """

    def _load_counting(self, tmp_path, monkeypatch, src, name):
        """Load *src*, counting every ``$subscript`` the compiled code runs."""
        from clausal.logic.runtime import dict_ops
        reads = []

        def counting_subscript(obj, key):
            reads.append(key)
            return dict_ops._subscript(obj, key)

        monkeypatch.setattr(
            "clausal.logic.compiler.predicate._subscript", counting_subscript)
        path = tmp_path / f"{name}.clausal"
        path.write_text(src)
        mod = _load_module(name, str(path))
        return mod, mod.__dict__["$module"], reads

    def test_repeated_dot_reads_once(self, tmp_path, monkeypatch):
        """``bar(P.k), baz(P.k, 1)`` performs one read, not two."""
        # nv
        src = (
            "-private([kee])\n"
            "bar(1),\n"
            "baz(1, 1),\n"
            "chk(PROF) <- (bar(PROF.kee), baz(PROF.kee, 1))\n"
        )
        mod, logic_mod, reads = self._load_counting(
            tmp_path, monkeypatch, src, "readonce_dot")
        kee = mod.__dict__["kee"]
        assert list(call("chk", DictTerm({kee: 1}), module=logic_mod))
        assert len(reads) == 1

    def test_repeated_bracket_reads_once(self, tmp_path, monkeypatch):
        """``P[k]`` gets the same single-evaluation guarantee as ``P.k``."""
        # nv
        src = (
            "-private([kee])\n"
            "bar(1),\n"
            "baz(1, 1),\n"
            "chk(PROF) <- (bar(PROF[kee]), baz(PROF[kee], 1))\n"
        )
        mod, logic_mod, reads = self._load_counting(
            tmp_path, monkeypatch, src, "readonce_bracket")
        kee = mod.__dict__["kee"]
        assert list(call("chk", DictTerm({kee: 1}), module=logic_mod))
        assert len(reads) == 1

    def test_read_re_executes_on_redo(self, tmp_path, monkeypatch):
        """The read is a goal at the first-occurrence position, not a cache.

        It sits *after* ``prc/1``, so redo re-executes it against the new
        binding of ``PROF``.  Hoisted to clause entry it would read an unbound
        ``PROF`` (instantiation_error); cached in a Python local it would go
        stale and report the first dict's value twice.
        """
        # nv
        src = (
            "-private([kee])\n"
            "prc({kee: 1}),\n"
            "prc({kee: 2}),\n"
            "seen(1),\n"
            "seen(2),\n"
            "pick(V) <- (prc(PROF), seen(PROF.kee), V is PROF.kee)\n"
        )
        mod, logic_mod, reads = self._load_counting(
            tmp_path, monkeypatch, src, "readonce_redo")
        out = Var()
        got = [deref(out) for _ in call("pick", out, module=logic_mod)]
        assert got == [1, 2]
        assert len(reads) == 2

    def test_read_stays_inside_disjunction_arm(self, tmp_path, monkeypatch):
        """A missing key in one arm must not sink a succeeding other arm."""
        # nv
        src = (
            "-private([kee, absent])\n"
            "yes(1),\n"
            "chk(PROF) <- (yes(PROF.kee) or yes(PROF.absent))\n"
        )
        mod, logic_mod, reads = self._load_counting(
            tmp_path, monkeypatch, src, "readonce_or")
        kee = mod.__dict__["kee"]
        # The first arm succeeds; a read lifted ahead of the disjunction would
        # throw existence_error(dict_key, absent) before it ever ran.
        solutions = call("chk", DictTerm({kee: 1}), module=logic_mod)
        assert next(iter(solutions), "no solution") != "no solution"
        assert len(reads) == 1

    def test_read_stays_inside_negation(self, tmp_path, monkeypatch):
        """The read sits inside ``not (...)``, and happens once."""
        # nv
        src = (
            "-private([kee])\n"
            "chk(PROF) <- (not (PROF.kee is 2), PROF.kee is 1)\n"
        )
        mod, logic_mod, reads = self._load_counting(
            tmp_path, monkeypatch, src, "readonce_not")
        kee = mod.__dict__["kee"]
        assert list(call("chk", DictTerm({kee: 1}), module=logic_mod))
        # One read inside the negation's scope, one in the outer scope —
        # sharing deliberately does not cross the construct boundary.
        assert len(reads) == 2

    def test_read_stays_inside_if_then_else_branch(self, tmp_path, monkeypatch):
        """An untaken branch's read never runs, so a missing key cannot throw."""
        # nv
        src = (
            "-private([kee])\n"
            "yes({kee: 1}),\n"
            "prc(PROF, R) <- if_(yes(PROF), R is PROF.kee, R is 0)\n"
        )
        mod, logic_mod, reads = self._load_counting(
            tmp_path, monkeypatch, src, "readonce_ite")
        out = Var()
        # The dict has no `kee`, so the condition fails and the else-branch
        # runs; a read hoisted ahead of the if_ would throw instead.
        got = [deref(out) for _ in
               call("prc", DictTerm({}), out, module=logic_mod)]
        assert got == [0]
        assert reads == []

    def test_sharing_does_not_cross_an_arm_boundary(self, tmp_path, monkeypatch):
        """A later occurrence outside the construct reads again — by design."""
        # nv
        src = (
            "-private([kee])\n"
            "yes(1),\n"
            "nope(0),\n"
            "chk(PROF) <- ((yes(PROF.kee) or nope(PROF.kee)), yes(PROF.kee))\n"
        )
        mod, logic_mod, reads = self._load_counting(
            tmp_path, monkeypatch, src, "readonce_arm_boundary")
        kee = mod.__dict__["kee"]
        # First solution only, so the second arm never runs: one read inside
        # the taken arm, one for the occurrence after the disjunction.  A read
        # shared out of the arm would show 1.
        solutions = call("chk", DictTerm({kee: 1}), module=logic_mod)
        assert next(iter(solutions), "no solution") != "no solution"
        assert len(reads) == 2


# ── Subscript read: direct runtime behaviour ─────────────────────────────────

class TestDictSubscriptRead:
    """V is P[K] over a DictTerm, driven from Python via subscript_get/3."""

    @pytest.fixture(scope="class")
    def mod(self):
        return _load_fixture()

    @pytest.fixture(scope="class")
    def logic_mod(self, mod):
        return mod.__dict__["$module"]

    def _first_binding(self, logic_mod, obj, key, out):
        """Read the binding of *out* inside the first solution — bindings are
        undone once the generator backtracks past the last solution."""
        for _ in call("subscript_get", obj, key, out, module=logic_mod):
            return deref(out)
        return None

    def test_reads_present_string_key(self, mod, logic_mod):
        # nv
        assert self._first_binding(
            logic_mod, DictTerm({"a": 1, "b": 2}), "a", Var()) == 1

    def test_reads_present_int_key(self, mod, logic_mod):
        # nv
        assert self._first_binding(
            logic_mod, DictTerm({1: "one"}), 1, Var()) == "one"

    def test_reads_atom_key(self, mod, logic_mod):
        """The read path works for atom (PredicateMeta) keys, even though
        atom-key dict *literals* are a separate parser gap — here the dict is
        built in Python and the key is passed as a runtime value."""
        # nv
        foo = mod.__dict__["colors"]  # any interned atom-like global would do
        d = DictTerm({foo: 99})
        assert self._first_binding(logic_mod, d, foo, Var()) == 99

    def test_missing_key_raises_existence_error(self, mod, logic_mod):
        # nv
        from clausal.logic.exceptions import LogicException
        v = Var()
        with pytest.raises(LogicException) as exc:
            list(call("subscript_get", DictTerm({"a": 1}), "z", v,
                      module=logic_mod))
        term = exc.value.term
        # error(existence_error(_, "z"), _)
        assert term.functor == "error"
        assert term.args[0].functor == "existence_error"
        assert term.args[0].args[1] == "z"

    def test_nonground_key_raises_instantiation_error(self, mod, logic_mod):
        # nv
        from clausal.logic.exceptions import LogicException
        v = Var()
        with pytest.raises(LogicException) as exc:
            list(call("subscript_get", DictTerm({"a": 1}), Var(), v,
                      module=logic_mod))
        term = exc.value.term
        assert term.functor == "error"
        assert term.args[0] == "instantiation_error"

    def test_unbound_object_raises_instantiation_error(self, mod, logic_mod):
        """An unbound base is under-instantiated, not wrong-typed — it used to
        report ``type_error(dict, _)``."""
        # nv
        from clausal.logic.exceptions import LogicException
        v = Var()
        with pytest.raises(LogicException) as exc:
            list(call("subscript_get", Var(), "a", v, module=logic_mod))
        term = exc.value.term
        assert term.functor == "error"
        assert term.args[0] == "instantiation_error"


# ── Backtracking tests ──────────────────────────────────────────────────────

class TestDictBacktracking:
    """Test that DictTerm unification backtracks correctly."""

    @pytest.fixture(scope="class")
    def mod(self):
        return _load_fixture()

    @pytest.fixture(scope="class")
    def logic_mod(self, mod):
        return mod.__dict__["$module"]

    def test_multiple_dict_clauses(self, mod, logic_mod):
        """point_type has 3 clauses; querying with Var should yield all 3."""
        # nv
        r = list(call("point_type", Var(), Var(), module=logic_mod))
        assert len(r) == 3

    def test_get_x_different_inputs(self, mod, logic_mod):
        """get_x extracts correct X from different dicts."""
        # nv
        x = Var()
        for trail in call("get_x", DictTerm({"x": 10, "y": 20}), x, module=logic_mod):
            assert deref(x) == 10
            break

    def test_get_x_another_input(self, mod, logic_mod):
        # nv
        x = Var()
        for trail in call("get_x", DictTerm({"x": 77, "y": 88}), x, module=logic_mod):
            assert deref(x) == 77
            break
