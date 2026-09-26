"""The dumb seam, step (d) (operator GO 2026-09-26): ``++`` UNCONVERTED --
a plain ``str`` is the atom, containers raw (main's meaning, kept) -- and
THE LEAK RULE (an ``atom`` instance never enters term space) applied at the
doors ``wrap_text`` never sees: a seam's bare-name lookup (``seam.build``)
and a Python caller's goal at ``solve``/``once``/``call``.  Each door is
tested with the repro the 2026-09-26 design review found.
"""
import os
import tempfile

from clausal.import_hook import _load_module
from clausal.logic.atoms import atom
from clausal.terms import Var


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
        from clausal.terms import Compound, KWTerm, DictTerm, SetTerm
        class NT(NamedTuple):
            x: object
        a = atom("a")
        return {
            "tuple": ("f", a), "list": [a], "dict": {"k": a}, "dict-key": {a: 1},
            "DictTerm": DictTerm({"k": a}), "Compound": Compound("f", (a,)),
            "KWTerm": KWTerm("k", f=a), "SetTerm": SetTerm({a}), "set": {a},
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

    def test_to_python_converts_through_every_shape(self):
        """No drift: the same list of shapes converts, so a container the
        strip knows is one to_python knows."""
        from clausal.logic.to_python import to_python, TERM_CONTAINER_TYPES
        from clausal.logic.cells import chars
        from clausal.terms import Compound, KWTerm, DictTerm, SetTerm
        c = chars("t")
        samples = {tuple: ("f", c), list: [c], dict: {"k": c}, DictTerm: DictTerm({"k": c}),
                   Compound: Compound("f", (c,)), KWTerm: KWTerm("k", f=c),
                   SetTerm: SetTerm({c}), set: {c}, frozenset: frozenset({c})}
        assert set(samples) == set(TERM_CONTAINER_TYPES)
        for t, sample in samples.items():
            out = to_python(sample)
            flat = repr(out)
            assert "$chars" not in flat, t

    def test_a_dataclass_term_instance_is_walked_too(self):
        from clausal.logic.predicate import is_term_instance
        from clausal.pythonic_ast.nodes import LoadName
        node = LoadName(name=atom("a"))
        assert is_term_instance(node)
        from clausal.logic.to_python import strip_atom_tags, has_atom_tag
        assert has_atom_tag(node)
        out = strip_atom_tags(node)
        assert type(out) is LoadName and type(out.name) is str

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
