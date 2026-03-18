"""Phase 5: Trail callback protocol (trail.record()).

MutableDict/MutableSet were considered but removed — mutable accumulation is
better served by the existing ``++()`` Python escape (plain Python dicts/sets)
or by DictTerm functional updates.  The trail.record() mechanism is kept as a
clean extension point for any future custom backtrackable mutable state.
"""

import pytest

from clausal.logic.variables import Trail, Var, unify, deref, is_var


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
        assert log == []

    def test_multiple_callbacks_reversed(self):
        """Callbacks fire newest-first, matching the trail's LIFO order."""
        trail = Trail()
        log = []
        m = trail.mark()
        trail.record(lambda: log.append(1))
        trail.record(lambda: log.append(2))
        trail.record(lambda: log.append(3))
        trail.undo(m)
        assert log == [3, 2, 1]

    def test_callback_exception_cleared(self):
        """Exceptions in callbacks are swallowed so undo always completes."""
        trail = Trail()
        log = []

        def bad():
            raise RuntimeError("oops")

        m = trail.mark()
        trail.record(bad)
        trail.record(lambda: log.append("ok"))
        trail.undo(m)  # must not raise
        assert log == ["ok"]

    def test_non_callable_raises(self):
        trail = Trail()
        with pytest.raises(TypeError):
            trail.record(42)

    def test_callbacks_mixed_with_var_bindings(self):
        """Callbacks and var-bindings interleave correctly in LIFO order."""
        trail = Trail()
        v = Var()
        log = []
        m = trail.mark()
        unify(v, 1, trail)
        trail.record(lambda: log.append("cb"))
        trail.undo(m)
        assert log == ["cb"]
        assert is_var(deref(v))

    def test_partial_undo_respects_mark(self):
        trail = Trail()
        log = []
        m1 = trail.mark()
        trail.record(lambda: log.append("A"))
        m2 = trail.mark()
        trail.record(lambda: log.append("B"))
        trail.undo(m2)
        assert log == ["B"]
        trail.undo(m1)
        assert log == ["B", "A"]

    def test_reset_fires_all_callbacks(self):
        trail = Trail()
        log = []
        trail.record(lambda: log.append("x"))
        trail.record(lambda: log.append("y"))
        trail.reset()
        assert log == ["y", "x"]

    def test_plain_dict_with_trail_record(self):
        """Demonstrate the idiomatic pattern: use trail.record() + plain dict."""
        trail = Trail()
        d = {}
        _ABSENT = object()

        def trailed_put(key, value):
            old = d.get(key, _ABSENT)
            def undo():
                if old is _ABSENT:
                    d.pop(key, None)
                else:
                    d[key] = old
            trail.record(undo)
            d[key] = value

        m = trail.mark()
        trailed_put("x", 1)
        trailed_put("y", 2)
        assert d == {"x": 1, "y": 2}
        trail.undo(m)
        assert d == {}

    def test_plain_set_with_trail_record(self):
        """Demonstrate the idiomatic pattern: use trail.record() + plain set."""
        trail = Trail()
        s = set()

        def trailed_add(elem):
            if elem in s:
                return
            trail.record(lambda e=elem: s.discard(e))
            s.add(elem)

        m = trail.mark()
        trailed_add("red")
        trailed_add("blue")
        assert s == {"red", "blue"}
        trail.undo(m)
        assert s == set()
