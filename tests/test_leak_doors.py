"""The dumb seam, step (d) (operator GO 2026-09-26): ``++`` UNCONVERTED --
a plain ``str`` is the atom, containers raw (main's meaning, kept) -- and
THE LEAK RULE (an ``atom`` instance never enters term space) applied at the
doors ``wrap_text`` never sees: a seam's bare-name lookup (``seam.build``)
and a Python caller's goal at ``solve``/``once``/``call``.  Each door is
tested with the repro the 2026-09-26 design review found.
"""
import os
import tempfile

import pytest

from clausal.import_hook import _load_module
from clausal.logic.atoms import atom
from clausal.terms import Var

# The deprecated boundary class (dumb seam step (f), 2026-09-27): this file
# constructs ``atom`` ON PURPOSE -- it pins the class / the leak strips that
# must keep working through 1.x -- so its deprecation warning is expected
# here and is asserted in tests/test_atom_class_deprecation.py.
pytestmark = pytest.mark.filterwarnings(
    "ignore::clausal.lint_warnings.ClausalAtomClassDeprecationWarning")


def _load(name, source):
    d = tempfile.mkdtemp()
    p = os.path.join(d, f"{name}.seam")
    with open(p, "w") as fh:
        fh.write(source)
    return _load_module(name, p)


RB = (
    "-module({name}, [sp(X), pair(K, N), color(C)])\n"
    "-double_quotes(chars)\n"
    "-private([permitted, art_6, red, blue])\n"
    "sp(permitted),\n"
    "pair(permitted, 1),\n"
    "pair(art_6, 2),\n"
    "color(red),\n"
    "color(blue),\n"
)


def _rb(name, body):
    return _load(name, RB.format(name=name) + body)


class TestLeakDoors:
    def test_a_bare_name_bound_to_an_atom_instance_enters_as_a_plain_str(self):
        m = _rb("_ld_a", (
            "from clausal.logic.atoms import atom\n"
            "tagged = atom('red')\n"
            "def build():\n"
            "    return --color(tagged)\n"
            "def query():\n"
            "    if --color(tagged):\n"
            "        return 'matched'\n"
            "    return 'no'\n"
        ))
        cell = m.build()
        assert cell == ("color", "red") and type(cell[1]) is str, cell
        assert m.query() == "matched"

    def test_a_python_callers_goal_is_stripped_at_solve_once_and_call(self):
        from clausal.logic.solve import solve, once, call
        m = _rb("_ld_b", "")
        mod = m.__dict__["$module"]
        n = Var()
        assert [n.value for _ in solve(("pair", atom("permitted"), n), mod)] == [1]
        assert once(("sp", atom("permitted")), mod) is not None
        assert once(("sp", [atom("permitted")]), mod) is None      # a list is not the atom: fails, no crash
        # call(): the argument reaches term space stripped -- bind an OUTPUT
        # variable to it and look at the type (roborev 243: the old test
        # passed on str-subclass equality alone)
        x = Var()
        assert [type(x.value).__name__ for _ in call("=", x, atom("a"), module=mod)] == ["str"]
        y = Var()
        assert [type(y.value[1]).__name__ for _ in call("=", y, ("f", [atom("a")]), module=mod)] == ["list"]
        for _ in call("=", y, ("f", [atom("a")]), module=mod):
            assert type(y.value[1][0]) is str

    def test_the_strip_reaches_into_a_nested_goal_argument(self):
        from clausal.logic.solve import solve
        m = _rb("_ld_c", "")
        mod = m.__dict__["$module"]
        v = Var()
        got = [v.value for _ in solve(("=", v, ("f", [atom("a")], {"k": atom("b")})), mod)]
        assert got == [("f", ["a"], {"k": "b"})]
        assert type(got[0][1][0]) is str and type(got[0][2]["k"]) is str

    def test_strip_atom_tags_returns_the_same_object_when_nothing_changes(self):
        from clausal.logic.to_python import strip_atom_tags
        t = ("f", ["a"], {"k": ("g", 1)})
        assert strip_atom_tags(t) is t
        assert strip_atom_tags(("f", atom("a"))) == ("f", "a")
        assert type(strip_atom_tags(("f", atom("a")))[1]) is str

    def test_a_shared_tagged_subterm_is_rebuilt_once_and_stays_shared(self):
        """A tagged DAG with nested sharing: t(i+1) = (t(i), t(i)).  Without
        a memo the rebuild visits 2**40 paths; with it, each node once."""
        import time
        from clausal.logic.to_python import strip_atom_tags
        t = ("leaf", atom("a"))
        for _ in range(40):
            t = ("node", t, t)
        start = time.perf_counter()
        out = strip_atom_tags(t)
        assert time.perf_counter() - start < 1.0
        assert out[1] is out[2]                 # sharing kept
        leaf = out
        while leaf[0] == "node":
            leaf = leaf[1]
        assert leaf == ("leaf", "a") and type(leaf[1]) is str

    def test_an_atom_instance_handed_to_a_seams_bare_name_enters_as_a_str(self):
        m = _rb("_ld_h", (
            "from clausal.logic.atoms import atom\n"
            "tagged = atom('permitted')\n"
            "def go():\n"
            "    for N in --pair(tagged, N):\n"
            "        return N\n"
        ))
        assert m.go() == 1



class TestEveryContainerIsWalked:
    """The strip walks every shape to_python converts: one list
    (TERM_CONTAINER_TYPES) drives has_atom_tag, map_term and the to_python
    arms, and this test pins each entry against all three so they cannot
    drift (roborev 243)."""

    def _shapes(self):
        from typing import NamedTuple
        from clausal.terms import DictTerm, SetTerm
        class NT(NamedTuple):
            x: object
        a = atom("a")
        return {
            "tuple": ("f", a), "list": [a], "dict": {"k": a}, "dict-key": {a: 1},
            "DictTerm": DictTerm({"k": a}),
            "SetTerm": SetTerm({a}), "set": {a},
            "frozenset": frozenset({a}), "NamedTuple": NT(a), "nested": ("f", [{"k": (a,)}]),
        }

    def test_has_atom_tag_sees_every_shape(self):
        from clausal.logic.to_python import has_atom_tag
        for name, shape in self._shapes().items():
            assert has_atom_tag(shape), name
        assert not has_atom_tag(("f", ["a", {"k": ("g", 1)}]))

    def test_strip_removes_the_tag_from_every_shape_and_keeps_the_shape(self):
        from clausal.logic.to_python import strip_atom_tags, has_atom_tag
        for name, shape in self._shapes().items():
            out = strip_atom_tags(shape)
            assert not has_atom_tag(out), name
            assert type(out) is type(shape), name
        clean = ("f", ["a", {"k": ("g", 1)}])
        assert strip_atom_tags(clean) is clean

    def test_dict_and_list_subclasses_keep_their_type(self):
        import collections
        from clausal.logic.to_python import strip_atom_tags
        od = collections.OrderedDict([("k", atom("a"))])
        out = strip_atom_tags(od)
        assert type(out) is collections.OrderedDict and out["k"] == "a" and type(out["k"]) is str
        class L(list):
            pass
        out = strip_atom_tags(L([atom("a")]))
        assert type(out) is L and type(out[0]) is str
        # a constructor that reads a pair list differently must not be used
        c = collections.Counter({"k": atom("a")})
        out = strip_atom_tags(c)
        assert type(out) is collections.Counter and out == {"k": "a"} and type(out["k"]) is str
        dd = collections.defaultdict(list, {"k": atom("a")})
        out = strip_atom_tags(dd)
        assert type(out) is collections.defaultdict and out.default_factory is list and out["k"] == "a"

    def test_to_python_converts_through_every_shape(self):
        """No drift: the same list of shapes converts, so a container the
        strip knows is one to_python knows."""
        from clausal.logic.to_python import to_python, TERM_CONTAINER_TYPES
        from clausal.logic.cells import chars
        from clausal.terms import DictTerm, SetTerm
        c = chars("t")
        samples = {tuple: ("f", c), list: [c], dict: {"k": c}, DictTerm: DictTerm({"k": c}),
                   SetTerm: SetTerm({c}), set: {c}, frozenset: frozenset({c})}
        assert set(samples) == set(TERM_CONTAINER_TYPES)
        for t, sample in samples.items():
            out = to_python(sample)
            flat = repr(out)
            assert "$chars" not in flat, t

    def test_a_dataclass_term_instance_is_walked_too(self):
        """A caller's own dataclass term (is_term_instance) is a container;
        a pythonic_ast Node is NOT entered -- it is code (see TestCyclicTerms)."""
        import dataclasses
        from clausal.logic.predicate import is_term_instance
        @dataclasses.dataclass
        class P:
            x: object
            y: object = 1
        inst = P(atom("a"))
        assert is_term_instance(inst)
        from clausal.logic.to_python import strip_atom_tags, has_atom_tag
        assert has_atom_tag(inst)
        out = strip_atom_tags(inst)
        assert type(out) is P and type(out.x) is str and out.y == 1

    def test_the_door_does_not_recurse_on_a_deep_goal(self):
        """The scan is iterative; a cons-like goal thousands of levels deep
        passes the door by identity.  (The compiler's own handling of such
        a constant is its business, and predates this door.)"""
        from clausal.logic.solve import _python_entry
        from clausal.logic.to_python import has_atom_tag
        deep = []
        for i in range(3000):
            deep = ["c", deep]
        assert not has_atom_tag(deep)
        assert _python_entry(deep) is deep
        assert _python_entry(("=", Var(), deep))[2] is deep


class TestCyclicTerms:
    """The door's scan must terminate on a CYCLIC goal: the engine builds
    one on purpose (unify without the occurs check), and the adversarial
    suite hands such goals to solve().  The first cut grew its stack without
    bound and the gate was OOM-killed at exactly that test, twice."""

    def test_has_atom_tag_terminates_on_a_cycle(self):
        from clausal.logic.to_python import has_atom_tag
        cyc = ["c"]; cyc.append(cyc)
        assert has_atom_tag(cyc) is False
        tagged = ["c", atom("a")]; tagged.append(tagged)
        assert has_atom_tag(tagged) is True

    def test_the_probe_terminates_on_a_cycle(self):
        from clausal.logic.seam import _probe_var_free
        cyc = ["c"]; cyc.append(cyc)
        assert _probe_var_free(cyc) is True        # no Var reachable, walked once
        cycv = ["c", Var()]; cycv.append(cycv)
        assert _probe_var_free(cycv) is False

    def test_a_cyclic_goal_passes_the_door(self):
        from clausal.logic.solve import _python_entry
        cyc = ["c"]; cyc.append(cyc)
        assert _python_entry(("=", Var(), cyc))[2] is cyc
        d = {"k": 1}; d["self"] = d                     # a dict self-cycle
        assert _python_entry(("=", Var(), d))[2] is d
        inner = []
        c = ("f", inner); inner.append(c)                # a cell whose arg holds it
        assert _python_entry(("=", Var(), c))[2] is c

    def test_a_tag_beside_an_untagged_cycle_is_fine(self):
        """Only a subtree that HOLDS a tag is rebuilt; an unrelated cyclic
        term beside it (a cyclic answer from unify without the occurs check)
        is handed back by identity, not entered (roborev 257)."""
        from clausal.logic.solve import _python_entry
        cyc = ["c"]; cyc.append(cyc)
        goal = _python_entry(("=", Var(), (atom("a"), cyc)))
        assert type(goal[2][0]) is str and goal[2][0] == "a"
        assert goal[2][1] is cyc
        # the same with the untagged cycle as a sibling argument, and deep
        big = [("row", i) for i in range(50)]
        goal = _python_entry(("f", cyc, big, [atom("b")]))
        assert goal[1] is cyc and goal[2] is big and goal[3] == ["b"] and type(goal[3][0]) is str

    def test_a_tagged_cycle_is_refused_loudly(self):
        """The rebuild after the scan cannot reproduce an immutable cycle;
        a cyclic goal holding a boundary tag is refused with a clear error
        rather than recursing until the stack gives out (roborev 254)."""
        import pytest
        from clausal.logic.solve import _python_entry
        tagged = ["c", atom("a")]; tagged.append(tagged)
        with pytest.raises(TypeError, match="CYCLIC"):
            _python_entry(("=", Var(), tagged))

    def test_a_dag_is_certified_within_budget_and_a_shared_node_entered_once(self):
        """The budget counts pops (each reference to the shared node is one
        pop), the visited table stops it being ENTERED again: 100 references
        = 1 + 100 + 100 pops, under the budget, and the shared node's own
        child is pushed once."""
        from clausal.logic.seam import _probe_var_free
        shared = ("s", ("t", 1))
        dag = tuple((shared,) for _ in range(100))
        assert _probe_var_free(dag, budget=512)
        assert not _probe_var_free(dag, budget=150), "and the budget is honest: pops are counted"

    def test_a_rewriter_goal_is_a_leaf_for_the_scan(self):
        from clausal.logic.to_python import has_atom_tag
        from clausal.pythonic_ast.nodes import LoadName, Call
        node = Call(func=LoadName(name="g"), args=[LoadName(name=atom("x"))], kwargs=[])
        assert not has_atom_tag(node), "a Node is code: not entered"
        assert not has_atom_tag((":", None, node))
