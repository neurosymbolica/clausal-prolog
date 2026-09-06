"""Tests for Phase 6 — user-facing attributed variable builtins."""

from __future__ import annotations

import pytest

from clausal.logic.atoms import mint
from clausal.logic.variables import (
    Var, Trail, deref, is_var, unify,
    put_attr, get_attr, del_attr, register_attr_hook, unregister_attr_hook,
)

# THE FLIP (spec §6.4): an attribute Key is a NAME, so the four Key-taking
# BUILTINS (put_attr/3, get_attr/3, del_attr/2, put_attrs/2) speak ATOMS.
# The low-level ``clausal.logic.variables`` functions used throughout this
# file take the STORAGE key, which is the atom's spelling — a plain ``str``
# there is deliberate, not a leftover.
from clausal.terms import Compound, DictTerm
from clausal.logic.builtins.attributes import (
    _put_attr__3, _get_attr__3, _del_attr__2,
    _get_attrs__2, _put_attrs__2,
    _is_att_var__1, _term_attributed_variables__2,
)


# ── Helpers ──────────────────────────────────────────────────────────────


def simple(fn, *args):
    """Run a simple-mode builtin and collect solutions."""
    trail = Trail()
    return list(fn(*args, trail, None)), trail


def simple_var(fn, var, *args):
    """Run simple-mode builtin and capture deref'd var per solution."""
    trail = Trail()
    return [deref(var) for _ in fn(*args, trail, None)]


# ── put_attr/3 ────────────────────────────────────────────────────────────


class TestPutAttr:
    def test_basic(self):
        # nv
        v = Var()
        sols, trail = simple(_put_attr__3, v, mint("color"), "red")
        assert len(sols) == 1
        assert get_attr(v, "color") == "red"

    def test_bound_var_fails(self):
        """put_attr on a bound term fails."""
        # nv
        sols, _ = simple(_put_attr__3, 42, mint("key"), "val")
        assert len(sols) == 0

    def test_unbound_key_fails(self):
        # nv
        sols, _ = simple(_put_attr__3, Var(), Var(), "val")
        assert len(sols) == 0

    def test_non_string_key_fails(self):
        # nv
        sols, _ = simple(_put_attr__3, Var(), 123, "val")
        assert len(sols) == 0

    def test_overwrite(self):
        # nv
        v = Var()
        trail = Trail()
        list(_put_attr__3(v, mint("k"), "old", trail, None))
        assert get_attr(v, "k") == "old"
        list(_put_attr__3(v, mint("k"), "new", trail, None))
        assert get_attr(v, "k") == "new"

    def test_backtrack_undoes(self):
        # nv
        v = Var()
        trail = Trail()
        mark = trail.mark()
        list(_put_attr__3(v, mint("k"), 42, trail, None))
        assert get_attr(v, "k") == 42
        trail.undo(mark)
        assert get_attr(v, "k") is None


# ── get_attr/3 ────────────────────────────────────────────────────────────


class TestGetAttr:
    def test_basic(self):
        # nv
        v = Var()
        trail = Trail()
        put_attr(v, "color", "blue", trail)
        val = Var()
        results = [deref(val) for _ in _get_attr__3(v, mint("color"), val, trail, None)]
        assert results == ["blue"]

    def test_missing_key_fails(self):
        # nv
        v = Var()
        sols, _ = simple(_get_attr__3, v, mint("nonexistent"), Var())
        assert len(sols) == 0

    def test_non_var_fails(self):
        # nv
        sols, _ = simple(_get_attr__3, 42, mint("key"), Var())
        assert len(sols) == 0

    def test_unify_check(self):
        """get_attr with pre-bound value checks equality."""
        # nv
        v = Var()
        trail = Trail()
        put_attr(v, "n", 42, trail)
        # Correct value
        sols_ok = list(_get_attr__3(v, mint("n"), 42, trail, None))
        assert len(sols_ok) == 1
        # Wrong value
        sols_bad = list(_get_attr__3(v, mint("n"), 99, trail, None))
        assert len(sols_bad) == 0

    def test_after_delete_fails(self):
        # nv
        v = Var()
        trail = Trail()
        put_attr(v, "k", "val", trail)
        del_attr(v, "k", trail)
        sols = list(_get_attr__3(v, mint("k"), Var(), trail, None))
        assert len(sols) == 0


# ── del_attr/2 ────────────────────────────────────────────────────────────


class TestDelAttr:
    def test_basic(self):
        # nv
        v = Var()
        trail = Trail()
        put_attr(v, "k", 1, trail)
        sols = list(_del_attr__2(v, mint("k"), trail, None))
        assert len(sols) == 1
        assert get_attr(v, "k") is None

    def test_nonexistent_succeeds(self):
        """Deleting non-existent attr is a no-op, succeeds."""
        # nv
        v = Var()
        sols, _ = simple(_del_attr__2, v, mint("nope"))
        assert len(sols) == 1

    def test_backtrack_undoes(self):
        # nv
        v = Var()
        trail = Trail()
        put_attr(v, "k", 42, trail)
        mark = trail.mark()
        list(_del_attr__2(v, mint("k"), trail, None))
        assert get_attr(v, "k") is None
        trail.undo(mark)
        assert get_attr(v, "k") == 42


# ── get_attrs/2 ───────────────────────────────────────────────────────────


class TestGetAttrs:
    def test_multiple_attrs(self):
        # nv
        v = Var()
        trail = Trail()
        put_attr(v, "a", 1, trail)
        put_attr(v, "b", 2, trail)
        result = Var()
        results = [deref(result) for _ in _get_attrs__2(v, result, trail, None)]
        assert len(results) == 1
        dt = results[0]
        assert isinstance(dt, DictTerm)
        # The keys come back as ATOMS — the term surface of the spellings
        # they are stored under (§6.4/§6.8).
        assert dt.data[mint("a")] == 1
        assert dt.data[mint("b")] == 2

    def test_no_attrs(self):
        # nv
        v = Var()
        result = Var()
        results = simple_var(_get_attrs__2, result, v, result)
        assert len(results) == 1
        dt = results[0]
        assert isinstance(dt, DictTerm)
        assert dt.data == {}

    def test_non_var_fails(self):
        # nv
        sols, _ = simple(_get_attrs__2, 42, Var())
        assert len(sols) == 0


# ── put_attrs/2 ───────────────────────────────────────────────────────────


class TestPutAttrs:
    def test_dict_term(self):
        # nv
        v = Var()
        dt = DictTerm({mint("x"): 10, mint("y"): 20})
        sols, trail = simple(_put_attrs__2, v, dt)
        assert len(sols) == 1
        assert get_attr(v, "x") == 10
        assert get_attr(v, "y") == 20

    def test_empty_dict(self):
        # nv
        v = Var()
        sols, _ = simple(_put_attrs__2, v, DictTerm({}))
        assert len(sols) == 1

    def test_non_dict_fails(self):
        # nv
        sols, _ = simple(_put_attrs__2, Var(), [["a", 1]])
        assert len(sols) == 0

    def test_non_var_fails(self):
        # nv
        sols, _ = simple(_put_attrs__2, 42, DictTerm({"k": "v"}))
        assert len(sols) == 0


# ── attvar/1 ───────────────────────────────────────────────────────────


class TestIsAttVar:
    def test_var_with_attr(self):
        # nv
        v = Var()
        trail = Trail()
        put_attr(v, "k", 1, trail)
        sols = list(_is_att_var__1(v, trail, None))
        assert len(sols) == 1

    def test_bare_var_fails(self):
        # nv
        sols, _ = simple(_is_att_var__1, Var())
        assert len(sols) == 0

    def test_bound_term_fails(self):
        # nv
        sols, _ = simple(_is_att_var__1, 42)
        assert len(sols) == 0


# ── term_attvars/2 ────────────────────────────────────────────


class TestTermAttributedVariables:
    def test_single_attvar(self):
        # nv
        v = Var()
        trail = Trail()
        put_attr(v, "k", 1, trail)
        result = Var()
        results = [deref(result)
                   for _ in _term_attributed_variables__2(v, result, trail, None)]
        assert len(results) == 1
        assert len(results[0]) == 1
        assert results[0][0] is v

    def test_list_with_mix(self):
        # nv
        v1, v2, v3 = Var(), Var(), Var()
        trail = Trail()
        put_attr(v1, "a", 1, trail)
        put_attr(v3, "b", 2, trail)
        # v2 has no attrs
        result = Var()
        results = [deref(result)
                   for _ in _term_attributed_variables__2([v1, v2, v3], result, trail, None)]
        assert len(results) == 1
        attvars = results[0]
        assert len(attvars) == 2
        assert v1 in attvars
        assert v3 in attvars
        assert v2 not in attvars

    def test_no_attvars(self):
        # nv
        result = Var()
        results = simple_var(_term_attributed_variables__2, result, [1, 2, "hello"], result)
        assert results == [[]]

    def test_compound_term(self):
        # nv
        v = Var()
        trail = Trail()
        put_attr(v, "k", 1, trail)
        term = Compound("f", (v, 42))
        result = Var()
        results = [deref(result)
                   for _ in _term_attributed_variables__2(term, result, trail, None)]
        assert len(results) == 1
        assert results[0] == [v]

    def test_duplicate_var_listed_once(self):
        # nv
        v = Var()
        trail = Trail()
        put_attr(v, "k", 1, trail)
        result = Var()
        results = [deref(result)
                   for _ in _term_attributed_variables__2([v, v, v], result, trail, None)]
        assert len(results) == 1
        assert len(results[0]) == 1


# ── Integration ──────────────────────────────────────────────────────────


class TestIntegration:
    def test_coexist_with_clpfd(self):
        """User attr and CLP(FD) attr coexist on the same variable."""
        # nv
        from clausal.logic.clpfd import in_domain
        v = Var()
        trail = Trail()
        in_domain(v, 1, 10, trail)
        # Now add a user attr
        list(_put_attr__3(v, mint("my_tag"), "hello", trail, None))
        # Both should be present
        assert get_attr(v, "fd") is not None
        assert get_attr(v, "my_tag") == "hello"

    def test_custom_hook_rejects_unification(self):
        """A custom hook can reject unification by returning False."""
        # nv
        hook_key = "_test_reject_hook"
        rejected = []

        def reject_hook(attr_val, bound_to, trail):
            rejected.append((attr_val, deref(bound_to)))
            return False  # reject

        register_attr_hook(hook_key, reject_hook)
        try:
            v = Var()
            trail = Trail()
            put_attr(v, hook_key, "guard", trail)
            # Unification should fail because hook rejects
            result = unify(v, 42, trail)
            assert result is False
            assert len(rejected) == 1
            assert rejected[0][0] == "guard"
        finally:
            unregister_attr_hook(hook_key)

    def test_custom_hook_accepts_unification(self):
        """A custom hook that returns True allows unification."""
        # nv
        hook_key = "_test_accept_hook"
        accepted = []

        def accept_hook(attr_val, bound_to, trail):
            accepted.append(attr_val)
            return True

        register_attr_hook(hook_key, accept_hook)
        try:
            v = Var()
            trail = Trail()
            put_attr(v, hook_key, "ok", trail)
            result = unify(v, 42, trail)
            assert result is True
            assert deref(v) == 42
            assert accepted == ["ok"]
        finally:
            unregister_attr_hook(hook_key)

    def test_round_trip_put_get_attrs(self):
        """put_attrs then get_attrs round-trips through DictTerm."""
        # nv
        v = Var()
        trail = Trail()
        dt_in = DictTerm({mint("x"): 10, mint("y"): "hello"})
        list(_put_attrs__2(v, dt_in, trail, None))
        dt_out = Var()
        results = [deref(dt_out) for _ in _get_attrs__2(v, dt_out, trail, None)]
        assert len(results) == 1
        assert isinstance(results[0], DictTerm)
        assert results[0].data[mint("x")] == 10
        assert results[0].data[mint("y")] == "hello"
        # The round trip closes: what came out goes straight back in.
        assert list(_put_attrs__2(Var(), results[0], trail, None)) == [None]
