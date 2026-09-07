"""Goal-position ``--``: if/elif/while tests, for iterables and ``not`` run
the goal and export its variables as plain locals (spec:
docs/superpowers/specs/2026-09-08-goal-position-seam-design.md)."""
import os
import tempfile

import pytest

from clausal.import_hook import _load_module


def _load_inline(name: str, source: str):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, f"{name}.clausal")
        with open(path, "w") as fh:
            fh.write(source)
        return _load_module(name, path)


RULEBASE = (
    "-module({name}, [decide(P, V), verdict(S, IDS), small, large, permitted, prohibited, r1, r2])\n"
    "-double_quotes(chars)\n"
    "decide(small, verdict(permitted, [r1, r2]))\n"
    "decide(large, verdict(prohibited, [r1]))\n"
    "decide(large, verdict(prohibited, [r2]))\n"
)


class TestHelpersDirectly:
    def test_once_bind_binds_the_first_answer_and_export_copies_it(self):
        from clausal import Var
        from clausal.logic.seam import once_bind, export
        mod = _load_inline("_gp_h1", RULEBASE.format(name="_gp_h1"))
        S, IDS = Var(), Var()
        goal = ("decide", ("large",), ("verdict", S, IDS))
        assert once_bind(goal, mod.__dict__) is True
        assert export(S) == ("prohibited",) and export(IDS) == [("r1",)]

    def test_once_bind_is_false_on_failure(self):
        from clausal import Var
        from clausal.logic.seam import once_bind
        mod = _load_inline("_gp_h2", RULEBASE.format(name="_gp_h2"))
        assert once_bind(("decide", ("tiny",), Var()), mod.__dict__) is False

    def test_each_yields_every_answer_as_a_tuple_or_a_bare_value(self):
        from clausal import Var
        from clausal.logic.seam import each
        mod = _load_inline("_gp_h3", RULEBASE.format(name="_gp_h3"))
        S, IDS = Var(), Var()
        goal = ("decide", ("large",), ("verdict", S, IDS))
        assert list(each(goal, (S, IDS), mod.__dict__)) == [
            (("prohibited",), [("r1",)]), (("prohibited",), [("r2",)])]
        V = Var()
        assert list(each(("decide", ("small",), V), (V,), mod.__dict__)) == [
            ("verdict", ("permitted",), [("r1",), ("r2",)])]

    def test_export_refuses_an_attributed_unbound_variable(self):
        from clausal import Var, Trail
        from clausal.logic.variables import put_attr
        from clausal.logic.seam import export, ResidualConstraints
        x = Var()
        put_attr(x, "dom", (1, 3), Trail())
        with pytest.raises(ResidualConstraints):
            export(x)
        y = Var()
        assert export(y) is y          # free and unattributed: the variable itself

    def test_a_conditional_answer_raises_undefined_answer(self):
        from clausal import Var
        from clausal.logic.seam import each, once_bind, UndefinedAnswer
        mod = _load_inline("_gp_h5", (
            "-module(_gp_h5, [move(A, B), wins(X), a, b, c])\n"
            "-double_quotes(chars)\n"
            "-table(wins/1)\n"
            "move(a, b),\n"
            "move(b, c),\n"
            "move(c, a),\n"
            "wins(X) <- (move(X, Y), not wins(Y))\n"
        ))
        with pytest.raises(UndefinedAnswer):
            list(each(("wins", ("a",)), (), mod.__dict__))
        with pytest.raises(UndefinedAnswer):
            once_bind(("wins", ("a",)), mod.__dict__)


class TestIf:
    def test_if_binds_locals_on_success_and_they_survive_the_block(self):
        mod = _load_inline("_gp_if1", RULEBASE.format(name="_gp_if1") + (
            "def first(profile):\n"
            "    if --decide(++profile, verdict(S, IDS)):\n"
            "        seen = True\n"
            "    return S, IDS\n"
        ))
        assert mod.first(("large",)) == (("prohibited",), [("r1",)])

    def test_if_assigns_nothing_on_failure(self):
        mod = _load_inline("_gp_if2", RULEBASE.format(name="_gp_if2") + (
            "def first(profile):\n"
            "    if --decide(++profile, verdict(S, IDS)):\n"
            "        return S\n"
            "    return S\n"
        ))
        with pytest.raises(UnboundLocalError):
            mod.first(("tiny",))

    def test_if_with_a_unification_pattern(self):
        mod = _load_inline("_gp_if3", RULEBASE.format(name="_gp_if3") + (
            "def parts(answer):\n"
            "    if --(verdict(S, IDS) is ++answer):\n"
            "        return S, IDS\n"
            "    return None\n"
        ))
        assert mod.parts(("verdict", ("permitted",), [])) == (("permitted",), [])
        assert mod.parts(("other", 1)) is None

    def test_elif_and_a_conjunction(self):
        mod = _load_inline("_gp_if4", RULEBASE.format(name="_gp_if4") + (
            "def which(profile):\n"
            "    if --decide(++profile, verdict(permitted, IDS)):\n"
            "        return ('yes', IDS)\n"
            "    elif --(decide(++profile, V), V is verdict(prohibited, IDS)):\n"
            "        return ('no', IDS)\n"
            "    return 'none'\n"
        ))
        assert mod.which(("small",)) == ("yes", [("r1",), ("r2",)])
        assert mod.which(("large",)) == ("no", [("r1",)])
        assert mod.which(("tiny",)) == "none"

    def test_term_positions_are_unchanged(self):
        mod = _load_inline("_gp_if5", RULEBASE.format(name="_gp_if5") + (
            "def term():\n"
            "    x = --decide(small, V)\n"
            "    return x[0], x[1]\n"
        ))
        assert mod.term()[0] == "decide" and mod.term()[1] == ("small",)

    def test_a_goal_seam_if_nested_in_a_goal_seam_if_body(self):
        mod = _load_inline("_gp_if6", RULEBASE.format(name="_gp_if6") + (
            "def both(profile1, profile2):\n"
            "    if --decide(++profile1, verdict(S, IDS)):\n"
            "        if --decide(++profile2, verdict(S2, IDS2)):\n"
            "            return S, IDS, S2, IDS2\n"
            "    return None\n"
        ))
        assert mod.both(("small",), ("large",)) == (
            ("permitted",), [("r1",), ("r2",)], ("prohibited",), [("r1",)])

    def test_a_goal_seam_if_nested_in_a_goal_seam_if_else(self):
        mod = _load_inline("_gp_if7", RULEBASE.format(name="_gp_if7") + (
            "def either(profile1, profile2):\n"
            "    if --decide(++profile1, verdict(prohibited, IDS0)):\n"
            "        return 'first'\n"
            "    else:\n"
            "        if --decide(++profile2, verdict(S, IDS)):\n"
            "            return S, IDS\n"
            "    return None\n"
        ))
        assert mod.either(("small",), ("large",)) == (("prohibited",), [("r1",)])
