"""Dumb seam step (f), 2026-09-27: the boundary class
``clausal.logic.atoms.atom`` is DEPRECATED (removed in 2.0).

An atom IS the plain ``str``, and after step (c) nothing in the engine
constructs an ``atom`` instance -- only user code can.  So constructing one
warns (``ClausalAtomClassDeprecationWarning``, once per call site), while the
class itself, its equality/hashing/interning/pickling, and the engine's leak
strips that test for it keep working, silently, through 1.x.

Every construction below sits on its OWN line on purpose: the guard is once
per (file, line), so a second construction on a line that already warned is
silent by design.
"""
import pickle
import runpy
import warnings
from pathlib import Path

import pytest

from clausal.lint_warnings import ClausalAtomClassDeprecationWarning
from clausal.logic.atoms import atom, is_atom

REPO = Path(__file__).resolve().parents[1]


def _recorded(fn):
    """Run *fn* and return the ClausalAtomClassDeprecationWarnings it emitted."""
    with warnings.catch_warnings(record=True) as got:
        warnings.simplefilter("always")
        fn()
    return [w for w in got if issubclass(w.category, ClausalAtomClassDeprecationWarning)]


class TestConstructionWarns:
    def test_it_is_a_deprecation_warning(self):
        assert issubclass(ClausalAtomClassDeprecationWarning, DeprecationWarning)

    def test_constructing_warns_and_says_what_to_use_instead(self):
        got = _recorded(lambda: atom("permitted"))
        assert len(got) == 1
        msg = str(got[0].message)
        assert "deprecated" in msg and "2.0" in msg
        assert "plain str" in msg
        assert "type(v) is str" in msg and "is_atom" in msg
        assert "to_python" in msg

    def test_attributed_to_the_constructing_code_not_the_engine(self):
        got = _recorded(lambda: atom("attributed"))
        assert len(got) == 1 and got[0].filename == __file__

    def test_once_per_call_site(self):
        def many():
            for _ in range(5):
                atom("loop")                                    # one site, five calls
        assert len(_recorded(many)) == 1
        assert _recorded(many) == [], "the site already warned"

    def test_two_sites_warn_twice(self):
        def two():
            atom("first")
            atom("second")
        got = _recorded(two)
        assert len(got) == 2 and got[0].lineno != got[1].lineno
        assert _recorded(two) == []
        got = _recorded(lambda: (atom("third"), atom("fourth")))   # one LINE: one site
        assert len(got) == 1

    def test_distinct_lines_are_distinct_sites(self):
        def a():
            return atom("line_a")
        def b():
            return atom("line_b")
        assert len(_recorded(a)) == 1
        assert len(_recorded(b)) == 1


class TestTheClassIsUnchanged:
    """Deprecated, not altered: equality, hashing, interning, repr, pickling."""

    def _make(self):
        with pytest.warns(ClausalAtomClassDeprecationWarning):
            return atom("same")

    def test_semantics(self):
        a = self._make()
        assert a == "same" and hash(a) == hash("same") and repr(a) == "atom('same')"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ClausalAtomClassDeprecationWarning)
            assert atom("same") is a                  # still interned
        assert isinstance(a, atom) and isinstance(a, str) and type(a) is atom
        assert is_atom(a) is False and is_atom("same") is True

    def test_pickle_round_trip_keeps_the_interned_instance(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ClausalAtomClassDeprecationWarning)
            a = atom("pickled")
            back = pickle.loads(pickle.dumps(a))
        assert back is a and type(back) is atom


class TestTheEngineNeverWarns:
    """The leak strips TEST for the class; they never construct it, so a
    value that already holds an instance passes every Python entry without
    a single further warning."""

    def test_the_leak_strips_and_entries_are_silent(self):
        from clausal.logic.to_python import (
            strip_atom_tags, has_atom_tag, wrap_text, to_python)
        from clausal.logic.solve import _python_entry
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ClausalAtomClassDeprecationWarning)
            tagged = atom("tagged")
        goal = ("=", ("f", [tagged], {"k": tagged}), ("f", ["tagged"], {"k": "tagged"}))

        def engine():
            assert has_atom_tag(goal)
            out = strip_atom_tags(goal)
            assert type(out[1][1][0]) is str and not has_atom_tag(out)
            assert type(wrap_text(tagged)) is str
            assert to_python(tagged) is tagged
            assert not has_atom_tag(_python_entry(goal))
        assert _recorded(engine) == []

    def test_the_builtin_atom_1_is_not_the_class(self):
        import clausal
        assert clausal.atom is not atom
        built = []
        assert _recorded(lambda: built.append(clausal.atom("x"))) == []   # the atom/1 GOAL, not the class
        assert type(built[0]) is not atom


class TestTheCensusTool:
    """tools/atom_class_census: the controls pass, and the engine's own tree
    has ZERO constructions -- the step (c) guarantee as a permanent gate."""

    def _census(self):
        return runpy.run_path(str(REPO / "tools" / "atom_class_census" / "census.py"))

    def test_self_test_passes(self, capsys):
        assert self._census()["self_test"]() == 0

    def test_the_engine_constructs_none(self):
        mod = self._census()
        reex = mod["find_reexporters"](REPO / "clausal")
        rep = mod["census"]([REPO / "clausal"], reex)
        assert rep["files_found"] > 100 and rep["files_unparsed"] == 0, rep["files_found"]
        assert rep["totals"]["construction"] == 0, rep["files"]
        # the only engine uses are the leak strips' type tests
        assert set(rep["files"]) == {str(REPO / "clausal" / "logic" / "to_python.py")}, set(rep["files"])
        assert rep["totals"]["type_test"] >= 1
