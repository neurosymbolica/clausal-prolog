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
        n2 = Var()
        assert [n2.value for _ in call("pair", atom("art_6"), n2, module=mod)] == [2]

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
