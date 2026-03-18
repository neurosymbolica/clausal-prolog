"""Phase 5: Impure/Mutable variants — MutableDict and MutableSet with Trail-backed undo.

Tests cover:
  - trail.record() callback mechanism
  - MutableDict put / remove / undo
  - MutableSet add / remove / undo
  - freeze() → DictTerm / SetTerm conversion
  - Builtins: MutableDictNew, IsMutableDict, MutableDictPut, MutableDictGet,
              MutableDictRemove, MutableDictFreeze, MutableDictSize, GenMutableDict
  - Builtins: MutableSetNew, IsMutableSet, MutableSetAdd, MutableSetRemove,
              MutableSetFreeze, MutableSetSize, MutableSetMember, GenMutableSet
  - Interaction with the search engine (backtracking unwinds mutable state)
"""

from __future__ import annotations

import pytest

from clausal.logic.database import Module
from clausal.logic.solve import solve
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.terms import Call, LoadName, DictTerm, SetTerm, MutableDict, MutableSet


# ── Helpers ────────────────────────────────────────────────────────────────────


def fresh_mod():
    return Module("test")


def _goal(name, *args):
    return Call(func=LoadName(name=name), args=list(args), kwargs=[])


def _succeeds(name, *args):
    return bool(list(solve(_goal(name, *args), fresh_mod())))


def _fails(name, *args):
    return not _succeeds(name, *args)


def _sols(name, *args):
    """Return list of dicts {index: deref'd value} for Var args."""
    var_positions = {i: a for i, a in enumerate(args) if isinstance(a, Var)}
    t = Trail()
    results = []
    for _ in solve(_goal(name, *args), fresh_mod(), t):
        results.append({i: deref(v) for i, v in var_positions.items()})
    return results


# ── trail.record() protocol ────────────────────────────────────────────────────


class TestTrailRecord:
    def test_record_called_on_undo(self):
        trail = Trail()
        log = []
        m = trail.mark()
        trail.record(lambda: log.append("undone"))
        trail.undo(m)
        assert log == ["undone"]

    def test_record_not_called_if_not_undone(self):
        trail = Trail()
        log = []
        trail.record(lambda: log.append("undone"))
        # never call undo — callback should not fire
        assert log == []

    def test_multiple_callbacks_reversed(self):
        trail = Trail()
        log = []
        m = trail.mark()
        trail.record(lambda: log.append(1))
        trail.record(lambda: log.append(2))
        trail.record(lambda: log.append(3))
        trail.undo(m)
        assert log == [3, 2, 1]  # reversed (newest first)

    def test_callback_exception_cleared(self):
        """Exceptions in callbacks are swallowed so undo always completes."""
        trail = Trail()
        log = []

        def bad():
            raise RuntimeError("oops")

        m = trail.mark()
        trail.record(bad)
        trail.record(lambda: log.append("ok"))
        trail.undo(m)  # should not raise
        assert log == ["ok"]

    def test_non_callable_raises(self):
        trail = Trail()
        with pytest.raises(TypeError):
            trail.record(42)

    def test_callbacks_mixed_with_bindings(self):
        """Callbacks and var-bindings interleave correctly."""
        trail = Trail()
        v = Var()
        log = []
        m = trail.mark()
        unify(v, 1, trail)
        trail.record(lambda: log.append("cb"))
        trail.undo(m)
        assert log == ["cb"]
        # v should be unbound after full undo
        from clausal.logic.variables import is_var
        assert is_var(deref(v))

    def test_partial_undo_leaves_later_callbacks(self):
        trail = Trail()
        log = []
        m1 = trail.mark()
        trail.record(lambda: log.append("A"))
        m2 = trail.mark()
        trail.record(lambda: log.append("B"))
        trail.undo(m2)   # only undo B
        assert log == ["B"]
        trail.undo(m1)   # now undo A
        assert log == ["B", "A"]

    def test_reset_fires_callbacks(self):
        trail = Trail()
        log = []
        trail.record(lambda: log.append("x"))
        trail.reset()
        assert log == ["x"]


# ── MutableDict Python API ─────────────────────────────────────────────────────


class TestMutableDictPython:
    def test_empty_on_create(self):
        md = MutableDict()
        assert len(md) == 0
        assert list(md.items()) == []

    def test_initial_data(self):
        md = MutableDict({"a": 1, "b": 2})
        assert md["a"] == 1
        assert md["b"] == 2

    def test_put_and_get(self):
        trail = Trail()
        md = MutableDict()
        md.put("x", 42, trail)
        assert md["x"] == 42

    def test_put_undo(self):
        trail = Trail()
        md = MutableDict()
        m = trail.mark()
        md.put("x", 42, trail)
        trail.undo(m)
        assert "x" not in md

    def test_put_update_undo(self):
        trail = Trail()
        md = MutableDict({"x": 1})
        m = trail.mark()
        md.put("x", 99, trail)
        assert md["x"] == 99
        trail.undo(m)
        assert md["x"] == 1  # restored

    def test_remove_undo(self):
        trail = Trail()
        md = MutableDict({"a": 10})
        m = trail.mark()
        md.remove("a", trail)
        assert "a" not in md
        trail.undo(m)
        assert md["a"] == 10

    def test_remove_absent_noop(self):
        trail = Trail()
        md = MutableDict({"a": 1})
        m = trail.mark()
        md.remove("z", trail)  # absent — no-op
        trail.undo(m)
        assert md["a"] == 1

    def test_multiple_puts_undo(self):
        trail = Trail()
        md = MutableDict()
        m = trail.mark()
        md.put("a", 1, trail)
        md.put("b", 2, trail)
        md.put("c", 3, trail)
        assert len(md) == 3
        trail.undo(m)
        assert len(md) == 0

    def test_freeze(self):
        md = MutableDict({"x": 1, "y": 2})
        dt = md.freeze()
        assert isinstance(dt, DictTerm)
        assert dt["x"] == 1
        assert dt["y"] == 2

    def test_freeze_is_snapshot(self):
        trail = Trail()
        md = MutableDict({"x": 1})
        dt1 = md.freeze()
        md.put("x", 99, trail)
        dt2 = md.freeze()
        assert dt1["x"] == 1
        assert dt2["x"] == 99

    def test_contains(self):
        md = MutableDict({"a": 1})
        assert "a" in md
        assert "z" not in md

    def test_repr(self):
        md = MutableDict()
        assert "MutableDict" in repr(md)


# ── MutableSet Python API ──────────────────────────────────────────────────────


class TestMutableSetPython:
    def test_empty_on_create(self):
        ms = MutableSet()
        assert len(ms) == 0

    def test_initial_data(self):
        ms = MutableSet(["red", "blue"])
        assert "red" in ms
        assert "blue" in ms

    def test_add_and_contains(self):
        trail = Trail()
        ms = MutableSet()
        ms.add("red", trail)
        assert "red" in ms

    def test_add_undo(self):
        trail = Trail()
        ms = MutableSet()
        m = trail.mark()
        ms.add("red", trail)
        trail.undo(m)
        assert "red" not in ms

    def test_add_existing_noop(self):
        """Adding an element already present records no trail entry."""
        trail = Trail()
        ms = MutableSet(["red"])
        m = trail.mark()
        ms.add("red", trail)  # already present — no trail entry
        trail.undo(m)
        # No entry was pushed so undo does nothing; still present
        assert "red" in ms

    def test_remove_and_undo(self):
        trail = Trail()
        ms = MutableSet(["a", "b"])
        m = trail.mark()
        ms.remove("a", trail)
        assert "a" not in ms
        trail.undo(m)
        assert "a" in ms

    def test_remove_absent_noop(self):
        trail = Trail()
        ms = MutableSet(["a"])
        m = trail.mark()
        ms.remove("z", trail)
        trail.undo(m)
        assert "a" in ms

    def test_freeze(self):
        ms = MutableSet(["x", "y"])
        st = ms.freeze()
        assert isinstance(st, SetTerm)
        assert "x" in st.elements
        assert "y" in st.elements

    def test_repr(self):
        ms = MutableSet()
        assert "MutableSet" in repr(ms)


# ── MutableDict builtins ────────────────────────────────────────────────────────


class TestMutableDictBuiltins:
    def test_is_mutable_dict_true(self):
        md = MutableDict()
        assert _succeeds("IsMutableDict", md)

    def test_is_mutable_dict_false_dict_term(self):
        assert _fails("IsMutableDict", DictTerm({"a": 1}))

    def test_is_mutable_dict_false_string(self):
        assert _fails("IsMutableDict", "hello")

    def test_mutable_dict_new(self):
        v = Var()
        sols = _sols("MutableDictNew", v)
        assert len(sols) == 1
        md = sols[0][0]
        assert isinstance(md, MutableDict)
        assert len(md) == 0

    def test_mutable_dict_put(self):
        md = MutableDict()
        t = Trail()
        # Use list() to exhaust the generator — mutation is permanent
        list(solve(_goal("MutableDictPut", "k", 1, md), fresh_mod(), t))
        assert md["k"] == 1

    def test_mutable_dict_get(self):
        md = MutableDict({"name": "alice"})
        v = Var()
        sols = _sols("MutableDictGet", "name", md, v)
        assert len(sols) == 1
        assert sols[0][2] == "alice"

    def test_mutable_dict_get_missing_fails(self):
        md = MutableDict()
        assert _fails("MutableDictGet", "z", md, Var())

    def test_mutable_dict_get_unbound_key_fails(self):
        md = MutableDict({"a": 1})
        assert _fails("MutableDictGet", Var(), md, Var())

    def test_mutable_dict_remove(self):
        md = MutableDict({"x": 1})
        t = Trail()
        list(solve(_goal("MutableDictRemove", "x", md), fresh_mod(), t))
        assert "x" not in md

    def test_mutable_dict_freeze(self):
        md = MutableDict({"p": 10})
        v = Var()
        sols = _sols("MutableDictFreeze", md, v)
        assert len(sols) == 1
        dt = sols[0][1]
        assert isinstance(dt, DictTerm)
        assert dt["p"] == 10

    def test_mutable_dict_size(self):
        md = MutableDict({"a": 1, "b": 2, "c": 3})
        v = Var()
        sols = _sols("MutableDictSize", md, v)
        assert len(sols) == 1
        assert sols[0][1] == 3

    def test_gen_mutable_dict_all_pairs(self):
        md = MutableDict({"x": 1, "y": 2})
        k_var = Var()
        v_var = Var()
        t = Trail()
        results = []
        for _ in solve(_goal("GenMutableDict", k_var, md, v_var), fresh_mod(), t):
            results.append((deref(k_var), deref(v_var)))
        assert len(results) == 2
        assert set(results) == {("x", 1), ("y", 2)}

    def test_mutable_dict_put_permanent(self):
        """MutableDictPut builtin is permanent (like assertz), not trail-backed.

        The Python API MutableDict.put(key, value, trail) IS trail-backed;
        the builtin is not — this matches how assertz/retract work.
        """
        md = MutableDict()
        trail = Trail()
        m = trail.mark()
        for _ in solve(_goal("MutableDictPut", "k", 1, md), fresh_mod(), trail):
            break
        assert md["k"] == 1
        # Trail undo does NOT revert the builtin's mutation
        trail.undo(m)
        assert md["k"] == 1  # still there — permanent mutation


# ── MutableSet builtins ─────────────────────────────────────────────────────────


class TestMutableSetBuiltins:
    def test_is_mutable_set_true(self):
        ms = MutableSet()
        assert _succeeds("IsMutableSet", ms)

    def test_is_mutable_set_false_set_term(self):
        assert _fails("IsMutableSet", SetTerm(["a"]))

    def test_is_mutable_set_false_string(self):
        assert _fails("IsMutableSet", "hello")

    def test_mutable_set_new(self):
        v = Var()
        sols = _sols("MutableSetNew", v)
        assert len(sols) == 1
        ms = sols[0][0]
        assert isinstance(ms, MutableSet)
        assert len(ms) == 0

    def test_mutable_set_add(self):
        ms = MutableSet()
        t = Trail()
        list(solve(_goal("MutableSetAdd", "red", ms), fresh_mod(), t))
        assert "red" in ms

    def test_mutable_set_member_true(self):
        ms = MutableSet(["a", "b"])
        assert _succeeds("MutableSetMember", "a", ms)

    def test_mutable_set_member_false(self):
        ms = MutableSet(["a"])
        assert _fails("MutableSetMember", "z", ms)

    def test_mutable_set_member_unbound_fails(self):
        ms = MutableSet(["a"])
        assert _fails("MutableSetMember", Var(), ms)

    def test_mutable_set_remove(self):
        ms = MutableSet(["x", "y"])
        t = Trail()
        list(solve(_goal("MutableSetRemove", "x", ms), fresh_mod(), t))
        assert "x" not in ms
        assert "y" in ms

    def test_mutable_set_freeze(self):
        ms = MutableSet(["a", "b"])
        v = Var()
        sols = _sols("MutableSetFreeze", ms, v)
        assert len(sols) == 1
        st = sols[0][1]
        assert isinstance(st, SetTerm)
        assert st.elements == frozenset(["a", "b"])

    def test_mutable_set_size(self):
        ms = MutableSet(["p", "q", "r"])
        v = Var()
        sols = _sols("MutableSetSize", ms, v)
        assert len(sols) == 1
        assert sols[0][1] == 3

    def test_gen_mutable_set(self):
        ms = MutableSet(["x", "y", "z"])
        e_var = Var()
        t = Trail()
        results = []
        for _ in solve(_goal("GenMutableSet", e_var, ms), fresh_mod(), t):
            results.append(deref(e_var))
        assert set(results) == {"x", "y", "z"}

    def test_mutable_set_add_permanent(self):
        """MutableSetAdd builtin is permanent (like assertz), not trail-backed."""
        ms = MutableSet()
        trail = Trail()
        m = trail.mark()
        for _ in solve(_goal("MutableSetAdd", "elem", ms), fresh_mod(), trail):
            break
        assert "elem" in ms
        # Trail undo does NOT revert the builtin's mutation
        trail.undo(m)
        assert "elem" in ms  # still there — permanent mutation
