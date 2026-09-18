"""Goal-position ``--``: if/elif/while tests, for iterables and ``not`` run
the goal and export its variables as plain locals (spec:
docs/superpowers/specs/2026-09-08-goal-position-seam-design.md)."""
import os
import tempfile

import pytest

from clausal.import_hook import _load_module
from clausal.logic.cells import chars


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

    def test_a_thunk_over_a_goal_variable_reads_its_bound_value(self):
        # ``++len(IDS)`` is lowered to ``PyThunk(lambda IDS: len(IDS), [IDS])``:
        # the lambda takes the DEREFERENCED value as a parameter of the same
        # name, so only the ``var_objects`` list OUTSIDE the lambda is the
        # seam's variable and only it may be renamed to ``$v_IDS``.  Renaming
        # the body's ``IDS`` too handed ``len()`` the AttVar itself.
        mod = _load_inline("_gp_if8", RULEBASE.format(name="_gp_if8") + (
            "def count(profile):\n"
            "    if --(decide(++profile, verdict(S, IDS)), N is ++len(IDS)):\n"
            "        return S, IDS, N\n"
            "    return None\n"
        ))
        assert mod.count(("small",)) == (
            ("permitted",), [("r1",), ("r2",)], 2)
        assert mod.count(("large",)) == (("prohibited",), [("r1",)], 1)

    def test_an_fstring_over_a_goal_variable_reads_its_bound_value(self):
        # Same shape as the ``++`` thunk above: ``visit_JoinedStr`` builds the
        # same ``PyThunk(lambda S: ..., [S])``, so the same rename rule has to
        # hold for an f-string interpolating a goal variable.
        mod = _load_inline("_gp_if9", RULEBASE.format(name="_gp_if9") + (
            "def label(profile):\n"
            "    if --(decide(++profile, verdict(S, _)), S2 is f\"v={S}\"):\n"
            "        return S, S2\n"
            "    return None\n"
        ))
        assert mod.label(("small",)) == (("permitted",), chars("v=permitted"))

    def test_an_unbound_export_handed_to_an_inner_seam_binds_the_live_object(self):
        # spec §7: "an unbound export handed to an inner seam through ``++``
        # binds there without touching the outer seam".  The outer seam is
        # over by then — what it hands out is the LIVE variable object (an
        # unbound, unattributed export is the variable itself, see
        # ``TestHelpersDirectly.test_export_refuses_an_attributed_unbound_variable``),
        # so the inner seam's binding is visible through the Python name that
        # holds it, and the outer seam's OTHER exports are untouched.  The
        # handle is a lowercase Python local on purpose: an ALL-CAPS name
        # inside ``++`` is a variable of the INNER seam (next test).
        mod = _load_inline("_gp_if10", (
            "-module(_gp_if10, [edge(A, B, C), a, b, seen])\n"
            "-double_quotes(chars)\n"
            "edge(a, _, seen)\n"
            "def probe():\n"
            "    if --edge(a, B, C):\n"
            "        held = B\n"
            "        if --(++held is b):\n"
            "            inner = 'bound'\n"
            "        else:\n"
            "            inner = 'failed'\n"
            "        return held is B, B, C, inner\n"
            "    return None\n"
        ))
        from clausal.logic.variables import deref
        same, B, C, inner = mod.probe()
        assert inner == "bound"
        assert same is True                  # one live object, not a copy
        assert deref(B) == ("b",)            # the inner seam bound it
        assert C == ("seen",)                # the outer seam's other export

    def test_an_all_caps_name_inside_an_inner_seams_escape_is_that_seams_variable(self):
        # spec §4, "no sharing across seams": two ``--`` in one function that
        # both mention ``B`` bind two unrelated fresh variables — including
        # when the second mentions it inside a ``++``.  So ``++B`` in the
        # inner seam reads the INNER ``$v_B``, and the outer seam's export
        # (saved first) is left exactly as it was: unbound, same object.
        mod = _load_inline("_gp_if11", (
            "-module(_gp_if11, [edge(A, B), a, b])\n"
            "-double_quotes(chars)\n"
            "edge(a, _)\n"
            "def probe():\n"
            "    if --edge(a, B):\n"
            "        before = B\n"
            "        if --(++B is b):\n"
            "            inner = 'true'\n"
            "        else:\n"
            "            inner = 'false'\n"
            "        return before, before is B, inner\n"
            "    return None\n"
        ))
        from clausal.logic.variables import deref, is_var
        before, same, inner = mod.probe()
        assert inner == "true"
        assert same is False                 # the inner seam exported its own B
        assert is_var(before) and deref(before) is before   # outer's untouched

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


class TestNot:
    def test_not_is_true_exactly_when_the_goal_fails_and_exports_nothing(self):
        mod = _load_inline("_gp_not1", RULEBASE.format(name="_gp_not1") + (
            "def absent(profile):\n"
            "    if not --decide(++profile, verdict(S, _)):\n"
            "        return 'absent'\n"
            "    return 'present'\n"
            "def leaks(profile):\n"
            "    if not --decide(++profile, verdict(S, _)):\n"
            "        return S\n"
        ))
        assert mod.absent(("tiny",)) == "absent"
        assert mod.absent(("small",)) == "present"
        with pytest.raises(UnboundLocalError):
            mod.leaks(("tiny",))


class TestFor:
    def test_for_yields_every_solution_and_leaves_the_last_values(self):
        mod = _load_inline("_gp_for1", RULEBASE.format(name="_gp_for1") + (
            "def all_ids(profile):\n"
            "    out = []\n"
            "    for S, IDS in --decide(++profile, verdict(S, IDS)):\n"
            "        out.append((S, IDS))\n"
            "    return out, S\n"
        ))
        out, last = mod.all_ids(("large",))
        assert out == [(("prohibited",), [("r1",)]), (("prohibited",), [("r2",)])]
        assert last == ("prohibited",)

    def test_a_single_target_gets_the_bare_value(self):
        mod = _load_inline("_gp_for2", RULEBASE.format(name="_gp_for2") + (
            "def verdicts(profile):\n"
            "    out = []\n"
            "    for V in --decide(++profile, V):\n"
            "        out.append(V)\n"
            "    return out\n"
        ))
        assert mod.verdicts(("small",)) == [("verdict", ("permitted",), [("r1",), ("r2",)])]

    def test_a_goal_variable_that_is_not_a_target_is_not_exported(self):
        mod = _load_inline("_gp_for3", RULEBASE.format(name="_gp_for3") + (
            "def only_status(profile):\n"
            "    for S in --decide(++profile, verdict(S, IDS)):\n"
            "        pass\n"
            "    return IDS\n"
        ))
        with pytest.raises((UnboundLocalError, NameError)):
            mod.only_status(("large",))

    def test_a_target_not_in_the_goal_is_a_load_time_syntax_error(self):
        with pytest.raises(SyntaxError, match="X"):
            _load_inline("_gp_for4", RULEBASE.format(name="_gp_for4") + (
                "def bad(profile):\n"
                "    for S, X in --decide(++profile, verdict(S, _)):\n"
                "        pass\n"
            ))

    def test_a_non_name_target_is_a_load_time_syntax_error(self):
        with pytest.raises(SyntaxError):
            _load_inline("_gp_for5", RULEBASE.format(name="_gp_for5") + (
                "def bad(profile, box):\n"
                "    for box.S in --decide(++profile, verdict(S, _)):\n"
                "        pass\n"
            ))

    def test_values_are_copies_per_solution(self):
        # Two things, and the SECOND is what proves copying: within one run
        # each solution's list starts at its stored length (so the append to
        # solution 1 did not reach solution 2), and a SECOND run over the same
        # loaded module sees the stored lists unmutated (so the append did not
        # reach the clause database either).  Without copying the second run
        # would read 3s.
        mod = _load_inline("_gp_for6", RULEBASE.format(name="_gp_for6") + (
            "def mutate(profile):\n"
            "    out = []\n"
            "    for IDS in --decide(++profile, verdict(_, IDS)):\n"
            "        IDS.append(('x',))\n"
            "        out.append(len(IDS))\n"
            "    return out\n"
        ))
        assert mod.mutate(("large",)) == [2, 2]
        assert mod.mutate(("large",)) == [2, 2]

    def test_break_stops_the_search(self):
        mod = _load_inline("_gp_for7", RULEBASE.format(name="_gp_for7") + (
            "def first(profile):\n"
            "    for IDS in --decide(++profile, verdict(_, IDS)):\n"
            "        break\n"
            "    return IDS\n"
        ))
        assert mod.first(("large",)) == [("r1",)]

    def test_a_statement_nested_seam_may_reuse_a_target_name(self):
        # spec §4: statement-nested seams are independent -- `_seam_bound`
        # only tracks a ``--`` nested inside a ``++`` of the SAME seam
        # expression, which a statement (an inner ``for``'s whole clause) is
        # never part of. Reusing ``S`` as both the outer and inner target is
        # therefore not refused; it is an ordinary Python rebinding, exactly
        # as reusing a loop variable name in nested ``for`` loops always is.
        mod = _load_inline("_gp_for8", RULEBASE.format(name="_gp_for8") + (
            "def nested(profile, profile2):\n"
            "    out = []\n"
            "    outer_ids = []\n"
            "    for S, IDS in --decide(++profile, verdict(S, IDS)):\n"
            "        outer_ids.append(IDS)\n"
            "        for S in --decide(++profile2, verdict(S, _)):\n"
            "            out.append(S)\n"
            "    return out, outer_ids, S\n"
        ))
        out, outer_ids, last = mod.nested(("large",), ("small",))
        assert out == [("permitted",), ("permitted",)]
        assert outer_ids == [[("r1",)], [("r2",)]]
        assert last == ("permitted",)


class TestWhile:
    def test_while_reruns_the_goal_each_iteration(self):
        mod = _load_inline("_gp_while1", (
            "-module(_gp_while1, [next(A, B), a, b, c])\n"
            "-double_quotes(chars)\n"
            "next(a, b),\n"
            "next(b, c),\n"
            "def walk(start):\n"
            "    cur = start\n"
            "    path = [cur]\n"
            "    while --next(++cur, N):\n"
            "        cur = N\n"
            "        path.append(cur)\n"
            "    return path\n"
        ))
        assert mod.walk(("a",)) == [("a",), ("b",), ("c",)]

    def test_while_not_goal_loops_until_the_goal_succeeds(self):
        # `while not --goal` runs the body for as long as the goal FAILS;
        # nothing is exported (the loudness rule for negated tests), so the
        # body advances a plain Python counter/cursor instead.
        mod = _load_inline("_gp_while2", (
            "-module(_gp_while2, [next(A, B), c, z])\n"
            "-double_quotes(chars)\n"
            "next(c, z),\n"
            "def find(seq):\n"
            "    cur = seq[0]\n"
            "    i = 0\n"
            "    while not --next(++cur, N):\n"
            "        i += 1\n"
            "        cur = seq[i]\n"
            "    return cur, i\n"
        ))
        assert mod.find([("a",), ("b",), ("c",)]) == (("c",), 2)

    def test_while_not_goal_does_not_export_the_fresh_variable(self):
        mod = _load_inline("_gp_while3", (
            "-module(_gp_while3, [next(A, B), c, z])\n"
            "-double_quotes(chars)\n"
            "next(c, z),\n"
            "def find(seq):\n"
            "    cur = seq[0]\n"
            "    i = 0\n"
            "    while not --next(++cur, N):\n"
            "        i += 1\n"
            "        cur = seq[i]\n"
            "    return N\n"
        ))
        with pytest.raises((UnboundLocalError, NameError)):
            mod.find([("a",), ("b",), ("c",)])


class TestSoundnessThroughTheRewriter:
    def test_a_conditional_answer_raises_in_an_if(self):
        from clausal.logic.seam import UndefinedAnswer
        mod = _load_inline("_gp_s1", (
            "-module(_gp_s1, [move(A, B), wins(X), a, b, c])\n"
            "-double_quotes(chars)\n"
            "-table(wins/1)\n"
            "move(a, b),\n"
            "move(b, c),\n"
            "move(c, a),\n"
            "wins(X) <- (move(X, Y), not wins(Y))\n"
            "def check():\n"
            "    if --wins(a):\n"
            "        return True\n"
            "    return False\n"
        ))
        with pytest.raises(UndefinedAnswer):
            mod.check()

    def test_a_conditional_answer_is_judged_through_a_conjunction_and_a_wrapper(self):
        """WFS strictness reaches EVERY goal shape, not only a bare tabled
        call: a conjunction and an untabled wrapper over a tabled predicate
        both raise on the conditional answer (throwaway-leader judgement,
        2026-09-08 — the pin that used to record the opposite is gone)."""
        from clausal.logic.seam import UndefinedAnswer
        mod = _load_inline("_gp_s3", (
            "-module(_gp_s3, [move(A, B), wins(X), p(X), a, b, c])\n"
            "-double_quotes(chars)\n"
            "-table(wins/1)\n"
            "move(a, b),\n"
            "move(b, c),\n"
            "move(c, a),\n"
            "wins(X) <- (move(X, Y), not wins(Y))\n"
            "p(X) <- wins(X)\n"
            "def conjunction():\n"
            "    if --(X is a, wins(X)):\n"
            "        return 'true'\n"
            "    return 'false'\n"
            "def wrapper():\n"
            "    if --p(a):\n"
            "        return 'true'\n"
            "    return 'false'\n"
            "def bare():\n"
            "    if --wins(a):\n"
            "        return 'true'\n"
            "    return 'false'\n"
        ))
        with pytest.raises(UndefinedAnswer):
            mod.conjunction()
        with pytest.raises(UndefinedAnswer):
            mod.wrapper()
        with pytest.raises(UndefinedAnswer):
            mod.bare()

    def test_mixed_conditional_and_unconditional_answers_from_one_tabled_goal(self):
        """One tabled predicate, one DEFINITE answer and three conditional
        ones, judged ANSWER BY ANSWER — and the call need not be ground.

        The observed answer order is ``d, a, b, c``: ``for X in --wins(X):``
        yields the definite ``d`` and then RAISES when it reaches ``a``, the
        first conditional one (it raises on reaching it, not before yielding
        anything — the assertion below records the partial sequence).  The
        same open call under ``if`` is once-semantics, so it stops at the
        first answer, which is the definite one, and is simply true.
        """
        from clausal.logic.seam import UndefinedAnswer
        src = (
            "-module({n}, [move(A, B), wins(X), a, b, c, d, e])\n"
            "-double_quotes(chars)\n"
            "-table(wins/1)\n"
            "move(a, b),\n"
            "move(b, c),\n"
            "move(c, a),\n"
            "move(d, e),\n"            # d wins outright: e has no move
            "wins(X) <- (move(X, Y), not wins(Y))\n"
            "def definite():\n"
            "    if --wins(d):\n"
            "        return 'true'\n"
            "    return 'false'\n"
            "def conditional():\n"
            "    if --wins(a):\n"
            "        return 'true'\n"
            "    return 'false'\n"
            "def every(out):\n"
            "    for X in --wins(X):\n"
            "        out.append(X)\n"
            "    return out\n"
            "def any_win():\n"
            "    if --wins(X):\n"
            "        return X\n"
            "    return None\n"
        )
        mod = _load_inline("_gp_s4", src.format(n="_gp_s4"))
        assert mod.definite() == "true"          # empty delay set: exported
        with pytest.raises(UndefinedAnswer):     # non-empty delay set: refused
            mod.conditional()
        # The open call, in a fresh module so the two do not share a table.
        mod2 = _load_inline("_gp_s5", src.format(n="_gp_s5"))
        out = []
        with pytest.raises(UndefinedAnswer):
            mod2.every(out)
        assert out == [("d",)]                   # the definite one, yielded
        # Once-semantics stops at the first answer, which is definite.
        mod3 = _load_inline("_gp_s6", src.format(n="_gp_s6"))
        assert mod3.any_win() == ("d",)

    def test_a_non_ground_tabled_call_is_judged_too(self):
        """A tabled call with an UNBOUND argument is judged like a ground one.

        The entry is stored under the subgoal key of the call as WRITTEN, so
        ``_definite_answers`` snapshots that key before ``solve()`` runs; a key
        derived at the first answer would name the answer's own bindings
        (``wins(a)``) and miss the open call's table entirely.  Here every
        answer is conditional, so the very first one raises.
        """
        from clausal.logic.seam import UndefinedAnswer
        mod = _load_inline("_gp_s7", (
            "-module(_gp_s7, [move(A, B), wins(X), a, b, c])\n"
            "-double_quotes(chars)\n"
            "-table(wins/1)\n"
            "move(a, b),\n"
            "move(b, c),\n"
            "move(c, a),\n"
            "wins(X) <- (move(X, Y), not wins(Y))\n"
            "def any_win():\n"
            "    if --wins(X):\n"
            "        return X\n"
            "    return None\n"
            "def every(out):\n"
            "    for X in --wins(X):\n"
            "        out.append(X)\n"
            "    return out\n"
        ))
        with pytest.raises(UndefinedAnswer):
            mod.any_win()
        out = []
        with pytest.raises(UndefinedAnswer):
            mod.every(out)
        assert out == []

    def test_an_attributed_unbound_export_raises_in_a_for(self):
        from clausal.logic.seam import ResidualConstraints
        mod = _load_inline("_gp_s2", (
            "-module(_gp_s2, [constrain(X)])\n"
            "-double_quotes(chars)\n"
            "constrain(X) <- dif(X, 1)\n"
            "def get():\n"
            "    for X in --constrain(X):\n"
            "        return X\n"
        ))
        with pytest.raises(ResidualConstraints):
            mod.get()


class TestBoundaries:
    def test_repl_cell_form(self):
        # ClausalConsole itself has no `$define_predicate` wired into its
        # namespace (only IPython's `$assert_fact`, which nothing emits any
        # more — the compiler routes every fact through `$define_predicate`),
        # so a bare `fact(1),` typed at the console cannot declare a new
        # predicate today; no existing REPL test declares one either. What
        # this pins instead — goal position running through the SAME
        # ClausalConsole.runsource() transform path a file uses — is real:
        # load a predicate the normal way, hand the console its `$module`
        # and predicate binding, and confirm `for X in --fact(X):` inside an
        # "exec"-mode multi-line cell drives `$each`/`$once_bind` exactly as
        # a file does.
        from clausal.python_repl import ClausalConsole
        mod = _load_inline("_gp_repl1", (
            "-module(_gp_repl1, [fact(X)])\n"
            "-double_quotes(chars)\n"
            "fact(1),\n"
            "fact(2),\n"
        ))
        console = ClausalConsole(filename="<test>")
        console.locals["$module"] = mod.__dict__["$module"]
        console.locals["fact"] = mod.fact
        console.runsource("out = [X for X in [1]]", "<test>", "single")
        console.runsource(
            "got = []\nfor X in --fact(X):\n    got.append(X)\n",
            "<test>", "exec")
        assert console.locals.get("got") == [1, 2]

    def test_reflection_models_python_code_by_position_only(self):
        from clausal.reflection import reify_source
        src = RULEBASE.format(name="_gp_r") + "def f():\n    if --decide(small, V):\n        return V\n"
        dumped = "\n".join(repr(vars(i)) if hasattr(i, "__dict__") else repr(i) for i in reify_source(src))
        assert "PythonCode(kind='function', name='f'" in dumped and "$once_bind" not in dumped


class TestQueryCache:
    """A goal-position seam inside a loop compiles its query ONCE.

    The node handed to ``solve()`` is rebuilt on every execution — fresh
    ``Var`` objects, a fresh ``PyThunk`` closing over this iteration's Python
    values — so nothing about the OBJECTS is stable.  What is stable is the
    node's SHAPE, and that is what ``_goal_cache_key`` keys on (Task 7).
    """

    def _compile_count(self, fn):
        """How many query compiles *fn()* triggers (instrumented, not timed)."""
        import clausal.logic.compiler as comp
        import clausal.logic.solve as solve_mod
        calls = []
        real = comp.compile_predicate_trampoline

        def counting(*a, **k):
            calls.append(1)
            return real(*a, **k)

        comp.compile_predicate_trampoline = counting
        solve_mod._query_cache.clear()
        try:
            fn()
        finally:
            comp.compile_predicate_trampoline = real
        return len(calls)

    def test_a_goal_seam_in_a_loop_compiles_once(self):
        mod = _load_inline("_gp_c1", RULEBASE.format(name="_gp_c1") + (
            "def hits(profiles):\n"
            "    n = 0\n"
            "    for p in profiles:\n"
            "        if --decide(++p, verdict(S, IDS)):\n"
            "            n += 1\n"
            "    return n\n"
        ))
        profiles = [("small",), ("large",), ("tiny",)] * 10
        assert self._compile_count(lambda: mod.hits(profiles)) == 1
        assert mod.hits(profiles) == 20

    def test_a_thunk_is_re_evaluated_per_execution_not_captured(self):
        mod = _load_inline("_gp_c2", RULEBASE.format(name="_gp_c2") + (
            "def status(p):\n"
            "    if --decide(++p, verdict(S, _)):\n"
            "        return S\n"
            "    return None\n"
        ))
        assert mod.status(("small",)) == ("permitted",)
        assert mod.status(("large",)) == ("prohibited",)
        assert mod.status(("small",)) == ("permitted",)

    def test_a_unification_pattern_seam_compiles_once(self):
        mod = _load_inline("_gp_c3", RULEBASE.format(name="_gp_c3") + (
            "def parts(answers):\n"
            "    out = []\n"
            "    for a in answers:\n"
            "        if --(verdict(S, IDS) is ++a):\n"
            "            out.append(S)\n"
            "    return out\n"
        ))
        answers = [("verdict", ("permitted",), []), ("verdict", ("prohibited",), [])] * 5
        assert self._compile_count(lambda: mod.parts(answers)) == 1
        assert mod.parts(answers) == [("permitted",), ("prohibited",)] * 5

    def test_a_thunk_over_a_goal_variable_is_correct_but_uncached(self):
        """A ``++`` over a GOAL variable still reads the bound value, and the
        goal holding it is refused the cache today.

        ``_structural_key`` refuses a ``PyThunk`` with ``var_objects``
        (``_collect_vars`` never reaches them, so a cache hit could not rebind
        them), so this goal recompiles once per execution — the measured cost
        of the refusal recorded in
        ``todo/goal-position-seam-thunk-var-objects-cache-2026-09-08.md``.
        The same goal WITHOUT the var-taking thunk compiles once, so the
        refusal is what separates the two, not the shape of the seam.
        """
        mod = _load_inline("_gp_c5", RULEBASE.format(name="_gp_c5") + (
            "def sized(profiles):\n"
            "    out = []\n"
            "    for p in profiles:\n"
            "        if --(decide(++p, verdict(S, IDS)), N is ++len(IDS)):\n"
            "            out.append((S, N))\n"
            "    return out\n"
            "def plain(profiles):\n"
            "    out = []\n"
            "    for p in profiles:\n"
            "        if --decide(++p, verdict(S, IDS)):\n"
            "            out.append((S, len(IDS)))\n"
            "    return out\n"
        ))
        profiles = [("small",), ("large",)] * 5
        expected = [(("permitted",), 2), (("prohibited",), 1)] * 5
        assert mod.sized(profiles) == expected
        assert self._compile_count(lambda: mod.sized(profiles)) == len(profiles)
        # The cacheable twin: same loop, no var-taking thunk, one compile.
        assert mod.plain(profiles) == expected
        assert self._compile_count(lambda: mod.plain(profiles)) == 1

    def test_a_reentrant_seam_site_keeps_each_execution_its_own_thunks(self):
        """The SAME seam site, running again while its own generator is
        suspended, must not have its cached query hijacked by the inner run.

        The `for` holds a live generator over `edge(++node, N)`; the body
        recurses and drives the same site with a different `node`/`tag`.  Both
        executions share one compiled query, so the only thing keeping them
        apart is that each gets its own globals copy with its own thunks — and
        `lab(N, ++tag)` re-evaluates its thunk on every backtrack, i.e. after
        the inner execution has been and gone."""
        mod = _load_inline("_gp_c4", (
            "-module(_gp_c4, [edge(A, B), lab(N, L), a, b, c, d, e, x, y])\n"
            "-double_quotes(chars)\n"
            "edge(a, b)\n"
            "edge(a, c)\n"
            "edge(b, d)\n"
            "edge(c, e)\n"
            "lab(b, x)\n"
            "lab(c, x)\n"
            "lab(d, y)\n"
            "lab(e, y)\n"
            "def walk(node, tag, out, depth):\n"
            "    for N in --(edge(++node, N), lab(N, ++tag)):\n"
            "        out.append((depth, tag, node, N))\n"
            "        if depth < 1:\n"
            "            walk(N, ('y',), out, depth + 1)\n"
            "    return out\n"
        ))
        got = []
        assert self._compile_count(lambda: mod.walk(("a",), ("x",), got, 0)) == 1
        # The outer execution resumes with ITS tag and sees both of a's edges,
        # interleaved with the inner executions it spawned.
        assert got == [
            (0, ("x",), ("a",), ("b",)),
            (1, ("y",), ("b",), ("d",)),
            (0, ("x",), ("a",), ("c",)),
            (1, ("y",), ("c",), ("e",)),
        ]


class TestJudgementThroughLoweredArguments:
    """A tabled call is judged whatever SHAPE its arguments are written in.

    The table entry is stored under the key of the call as the compiled query
    makes it — cells, atoms, ``++`` values.  ``_definite_answers`` used to take
    its key from the reified NODE's arguments instead, so a compound
    (``wins(pair(a))``), a ``++`` value (``wins(++x)``) or a ``++`` inside a
    compound never matched an entry and the conditional answer passed as
    true.  Now the arguments are lowered through the seam's own builder first
    (``seam_term``), so the key is the one the entry is under.  Fixes cause
    (3) of ``todo/wfs-delays-through-composite-goals-in-goal-position-2026-09-08.md``
    and the compound-argument gap found alongside it.
    """

    SRC = (
        "-module({n}, [move(A, B), wins(X), beats(A, B), pair(A), a, b, c, d, e])\n"
        "-double_quotes(chars)\n"
        "-table(wins/1)\n"
        "-table(beats/2)\n"
        "move(pair(a), pair(b)),\n"
        "move(pair(b), pair(c)),\n"
        "move(pair(c), pair(a)),\n"
        "move(pair(d), pair(e)),\n"          # pair(d) wins outright
        "wins(X) <- (move(X, Y), not wins(Y))\n"
        "beats(X, Y) <- (move(X, Y), not wins(Y))\n"
        "ground_a = ('pair', ('a',))\n"
        "ground_d = ('pair', ('d',))\n"
        "def compound_conditional():\n"
        "    if --wins(pair(a)):\n"
        "        return 'true'\n"
        "    return 'false'\n"
        "def compound_definite():\n"
        "    if --wins(pair(d)):\n"
        "        return 'true'\n"
        "    return 'false'\n"
        "def thunk_conditional():\n"
        "    if --wins(++ground_a):\n"
        "        return 'true'\n"
        "    return 'false'\n"
        "def thunk_definite():\n"
        "    if --wins(++ground_d):\n"
        "        return 'true'\n"
        "    return 'false'\n"
        "def nested_thunk_conditional():\n"
        "    x = ('a',)\n"
        "    if --wins(pair(++x)):\n"
        "        return 'true'\n"
        "    return 'false'\n"
        "def nested_thunk_definite():\n"
        "    x = ('d',)\n"
        "    if --wins(pair(++x)):\n"
        "        return 'true'\n"
        "    return 'false'\n"
        "def every_thunk(out, start):\n"
        "    for Y in --beats(++start, Y):\n"
        "        out.append(Y)\n"
        "    return out\n"
        "def var_thunk():\n"
        "    if --wins(++len(X)):\n"
        "        return 'true'\n"
        "    return 'false'\n"
    )

    def _mod(self, n):
        return _load_inline(n, self.SRC.format(n=n))

    def test_a_compound_argument_is_judged(self):
        from clausal.logic.seam import UndefinedAnswer
        mod = self._mod("_gp_l1")
        assert mod.compound_definite() == "true"
        with pytest.raises(UndefinedAnswer):
            mod.compound_conditional()

    def test_a_thunk_argument_is_judged(self):
        from clausal.logic.seam import UndefinedAnswer
        mod = self._mod("_gp_l2")
        assert mod.thunk_definite() == "true"
        with pytest.raises(UndefinedAnswer):
            mod.thunk_conditional()

    def test_a_thunk_inside_a_compound_is_judged(self):
        from clausal.logic.seam import UndefinedAnswer
        mod = self._mod("_gp_l3")
        assert mod.nested_thunk_definite() == "true"
        with pytest.raises(UndefinedAnswer):
            mod.nested_thunk_conditional()

    def test_for_over_a_thunk_argument_judges_each_answer(self):
        from clausal.logic.seam import UndefinedAnswer
        mod = self._mod("_gp_l4")
        # pair(d) beats pair(e) outright: wins(pair(e)) is false, so the
        # negation is definite and the answer is exported.
        assert mod.every_thunk([], ("pair", ("d",))) == [("pair", ("e",))]
        # pair(a) beats pair(b) only if wins(pair(b)) is false, which is
        # undefined in the 3-cycle: the one answer is conditional.
        out = []
        with pytest.raises(UndefinedAnswer):
            mod.every_thunk(out, ("pair", ("a",)))
        assert out == []

    def test_a_thunk_over_a_goal_variable_in_a_tabled_call_is_refused_loudly(self):
        """``wins(++len(X))`` with ``X`` a variable of the same goal has no
        value to key on before the search, and the compiled query would hand
        the lambda an unbound Var anyway.  It is refused with a clear message
        rather than silently unjudged."""
        mod = self._mod("_gp_l5")
        with pytest.raises(SyntaxError, match=r"\+\+ over a goal variable"):
            mod.var_thunk()


class TestJudgementAtTheSeamQueryBoundary:
    """Where the seam's term-position rules and the compiled query's
    goal-argument rules disagree, judgement must stay SOUND and the goal's
    compilation must not depend on whether the callee is tabled.  Found by
    the review of the argument-lowering fix."""

    SRC = (
        "-module({n}, [move(A, B), wins(X), num(N), pair(A, B), a, b, c, d, e, z])\n"
        "-double_quotes(chars)\n"
        "-table(wins/1)\n"
        "-table(num/1)\n"
        "move(pair(a, z), pair(b, z)),\n"
        "move(pair(b, z), pair(c, z)),\n"
        "move(pair(c, z), pair(a, z)),\n"
        "move(pair(d, z), pair(e, z)),\n"
        "wins(X) <- (move(X, Y), not wins(Y))\n"
        "num(3),\n"
        "def partial_conditional():\n"
        "    if --wins(pair(a)):\n"          # slot B omitted: the query fills a Var
        "        return 'true'\n"
        "    return 'false'\n"
        "def partial_definite():\n"
        "    if --wins(pair(d)):\n"
        "        return 'true'\n"
        "    return 'false'\n"
        "def arith_over_var():\n"
        "    if --num(N + 1):\n"
        "        return 'true'\n"
        "    return 'false'\n"
    )

    def _mod(self, n):
        return _load_inline(n, self.SRC.format(n=n))

    def test_an_omitted_signature_slot_is_judged_conservatively(self):
        """The omitted slot is filled by the query with its own Var; the
        answer is judged by the delays its derivation incurred, not by a key,
        so it is exact: the definite one exports, the conditional one raises."""
        from clausal.logic.seam import UndefinedAnswer
        mod = self._mod("_gp_b1")
        assert mod.partial_definite() == "true"
        with pytest.raises(UndefinedAnswer):
            mod.partial_conditional()

    def test_an_argument_the_seam_cannot_build_still_runs_and_is_judged(self):
        """``num(N + 1)`` is arithmetic over an unbound variable: the compiled
        query accepts the goal (structurally; it simply fails).  Judgement no
        longer depends on lowering the arguments to a key, so nothing here
        warns or refuses: the call runs and is judged like any other."""
        import warnings
        mod = self._mod("_gp_b2")
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert mod.arith_over_var() == "false"


class TestJudgementThroughCompositeGoals:
    """Every goal shape is judged: the derivation reports its delays to a
    throwaway leader pushed for the whole goal-position solve, so a
    conjunction, an untabled wrapper, a ``++``-fed call through a wrapper —
    the oracle shape — and nested predicates are all covered.  Conditional
    answers are delivered LAST (after global resolution), as a tabled root
    already delivers them; definite ones stream as they are found."""

    SRC = (
        "-module({n}, [move(A, B), wins(X), decide(P, V), verdict(S, X), "
        "beats(A, B), p(X), a, b, c, d, e, ok, start])\n"
        "-double_quotes(chars)\n"
        "-table(wins/1)\n"
        "move(a, b),\n"
        "move(b, c),\n"
        "move(c, a),\n"
        "move(d, e),\n"
        "wins(X) <- (move(X, Y), not wins(Y))\n"
        "p(X) <- wins(X)\n"
        "beats(X, Y) <- (move(X, Y), not wins(Y))\n"
        "decide(P, verdict(ok, X)) <- (X is P, wins(X))\n"
        "def decide_definite():\n"
        "    profile = d\n"
        "    if --decide(++profile, verdict(S, X)):\n"
        "        return (S, X)\n"
        "    return None\n"
        "def decide_conditional():\n"
        "    profile = a\n"
        "    if --decide(++profile, verdict(S, X)):\n"
        "        return (S, X)\n"
        "    return None\n"
        "def every_beats(out, first):\n"
        "    for Y in --beats(++first, Y):\n"
        "        out.append(Y)\n"
        "    return out\n"
        "def every_wrapped(out):\n"
        "    for X in --p(X):\n"
        "        out.append(X)\n"
        "    return out\n"
        "def first_wrapped():\n"
        "    for X in --p(X):\n"
        "        return X\n"
        "    return None\n"
        "def nested(out):\n"
        "    for X in --p(X):\n"
        "        if --wins(d):\n"
        "            out.append((X, 'd-wins'))\n"
        "    return out\n"
        "def body_raises():\n"
        "    for X in --p(X):\n"
        "        raise RuntimeError('body')\n"
    )

    def _mod(self, n):
        return _load_inline(n, self.SRC.format(n=n))

    def _stack(self):
        from clausal.logic.tabling import _leader_ctx
        return list(_leader_ctx.stack)

    def test_the_oracle_shape_profile_through_a_wrapper(self):
        from clausal.logic.seam import UndefinedAnswer
        mod = self._mod("_gp_c1")
        assert mod.decide_definite() == (("ok",), ("d",))
        with pytest.raises(UndefinedAnswer):
            mod.decide_conditional()
        assert self._stack() == []

    def test_negation_inside_an_untabled_body_is_judged(self):
        from clausal.logic.seam import UndefinedAnswer
        mod = self._mod("_gp_c2")
        assert mod.every_beats([], ("d",)) == [("e",)]
        out = []
        with pytest.raises(UndefinedAnswer):
            mod.every_beats(out, ("a",))
        assert out == []

    def test_definite_answers_stream_first_then_the_conditional_raises(self):
        """The open wrapped call has one definite answer (d) and three
        conditional ones (a, b, c): the definite one is exported as it is
        found; the conditional ones are deferred to the end and the first of
        them raises."""
        from clausal.logic.seam import UndefinedAnswer
        mod = self._mod("_gp_c3")
        out = []
        with pytest.raises(UndefinedAnswer):
            mod.every_wrapped(out)
        assert out == [("d",)]

    def test_break_after_the_first_answer_leaves_no_leader_behind(self):
        mod = self._mod("_gp_c4")
        assert mod.first_wrapped() == ("d",)
        assert self._stack() == []
        assert mod.first_wrapped() == ("d",)

    def test_a_body_exception_leaves_no_leader_behind(self):
        mod = self._mod("_gp_c5")
        with pytest.raises(RuntimeError, match="body"):
            mod.body_raises()
        assert self._stack() == []

    def test_a_nested_seam_inside_a_judged_body(self):
        from clausal.logic.seam import UndefinedAnswer
        mod = self._mod("_gp_c6")
        out = []
        with pytest.raises(UndefinedAnswer):
            mod.nested(out)
        assert out == [(("d",), "d-wins")]
        assert self._stack() == []


class TestDelaysAreChargedToTheRightAnswer:
    """Review of the throwaway leader (2026-09-08).  The leader's in-progress
    delay set is ONE mutable bucket, so a delay a branch incurred before it
    FAILED — or one a DIFFERENT judged goal incurred while running above this
    one — was charged to whatever answer arrived next.  And a delay-free
    re-derivation of an already-deferred answer never rescued it, neither
    through the table's own row (tabled) nor through a definite clause
    (untabled).  Every case turns a WFS-TRUE answer into a raised
    ``UndefinedAnswer``: the direction a caller cannot work around.
    """

    SRC = (
        "-module({n}, [move(A, B), wins(X), ok(X), both(X), p(X), r(X), t(X), "
        "u(X), f(X), g(X), beats(A, B), agg(L), cnt(N), start, "
        "allwins(L), sorted_wins(L), bagged(L), twoway(X), impossible(X), "
        "coldcnt(N), tb(X), zz(X), pair_bag(L), naf_bag(L), nest(X), "
        "ok, none, "
        "a, b, c, d, e, one, two])\n"
        "-double_quotes(chars)\n"
        "-table(wins/1)\n"
        "-table(t/1)\n"
        "-table(u/1)\n"
        "move(a, b),\n"
        "move(b, c),\n"
        "move(c, a),\n"
        "move(d, e),\n"
        "wins(X) <- (move(X, Y), not wins(Y))\n"
        "ok(d),\n"
        "both(X) <- (wins(X), ok(X))\n"
        "p(X) <- wins(X)\n"
        "u(X) <- (not u(X))\n"
        "t(a) <- (not u(a))\n"
        "t(a),\n"
        "r(a) <- wins(a)\n"
        "r(a),\n"
        "f(one),\n"
        "f(two),\n"
        "g(start),\n"
        "g(X) <- (move(X, Y), not wins(Y))\n"
        "beats(X, Y) <- (move(X, Y), not wins(Y))\n"
        "agg(L) <- (findall(Y, beats(a, Y), L))\n"
        "cnt(N) <- (count_all(beats(a, Y), N))\n"
        "allwins(L) <- (findall(X, wins(X), L))\n"
        "sorted_wins(L) <- (setof(X, wins(X), L))\n"
        "bagged(L) <- (bagof(X, wins(X), L))\n"
        "impossible(none),\n"
        "twoway(X) <- (findall(Y, wins(Y), L), impossible(L))\n"
        "twoway(ok),\n"
        "coldcnt(N) <- (count_all(wins(X), N))\n"
        "-table(tb/1)\n"
        "-table(zz/1)\n"
        "tb(X) <- (move(X, Y), not tb(Y))\n"
        "zz(X) <- (not zz(X))\n"
        "pair_bag(L) <- (findall(X, (wins(X), tb(X)), L))\n"
        "naf_bag(L) <- (findall(X, (wins(X), not zz(X)), L))\n"
        "-table(nest/1)\n"
        "nest(one),\n"
        "nest(two),\n"
        "def both_answers(out):\n"
        "    for X in --both(X):\n"
        "        out.append(X)\n"
        "    return out\n"
        "def t_is_true():\n"
        "    if --t(a):\n"
        "        return 'true'\n"
        "    return 'false'\n"
        "def r_answers(out):\n"
        "    for X in --r(X):\n"
        "        out.append(X)\n"
        "    return out\n"
        "def stream_f():\n"
        "    for X in --f(X):\n"
        "        yield X\n"
        "def stream_g():\n"
        "    for X in --g(X):\n"
        "        yield X\n"
        "def warm(out):\n"
        "    for Y in --beats(d, Y):\n"
        "        out.append(Y)\n"
        "    return out\n"
        "def bag():\n"
        "    if --agg(L):\n"
        "        return ('true', L)\n"
        "    return 'false'\n"
        "def counted():\n"
        "    if --cnt(N):\n"
        "        return ('true', N)\n"
        "    return 'false'\n"
        "def cold_bag():\n"
        "    if --allwins(L):\n"
        "        return ('true', L)\n"
        "    return 'false'\n"
        "def cold_set():\n"
        "    if --sorted_wins(L):\n"
        "        return ('true', L)\n"
        "    return 'false'\n"
        "def cold_bagof():\n"
        "    if --bagged(L):\n"
        "        return ('true', L)\n"
        "    return 'false'\n"
        "def nested_same_table(out):\n"
        "    for X in --nest(X):\n"
        "        inner = []\n"
        "        for Y in --nest(Y):\n"
        "            inner.append(Y)\n"
        "        out.append((X, inner))\n"
        "    return out\n"
        "def cold_counted():\n"
        "    if --coldcnt(N):\n"
        "        return ('true', N)\n"
        "    return 'false'\n"
        "def two_tables():\n"
        "    if --pair_bag(L):\n"
        "        return ('true', L)\n"
        "    return 'false'\n"
        "def naf_after_stream():\n"
        "    if --naf_bag(L):\n"
        "        return ('true', L)\n"
        "    return 'false'\n"
        "def after_the_bag():\n"
        "    if --twoway(X):\n"
        "        return X\n"
        "    return None\n"
    )

    def _mod(self, n):
        return _load_inline(n, self.SRC.format(n=n))

    def _stack(self):
        from clausal.logic.tabling import _leader_ctx
        return list(_leader_ctx.stack)

    def test_a_failed_branch_does_not_charge_its_delays_to_the_next_answer(self):
        """``both(X) <- (wins(X), ok(X))`` with ``ok(d)`` the only fact: the
        a/b/c branches each delay ``not wins(...)`` and then FAIL at ``ok``,
        so their delays belong to no answer at all.  ``d``, derived
        delay-free, is WFS-true and must export."""
        mod = self._mod("_gp_d1")
        assert mod.both_answers([]) == [("d",)]
        assert self._stack() == []

    def test_a_tabled_answer_rederived_without_delays_is_true(self):
        """``t(a) <- not u(a)`` (u(a) is undefined) and the fact ``t(a)``:
        the table's own row ends UNCONDITIONAL — a disjunction of derivations
        with one delay-free disjunct is True — so the goal is true."""
        mod = self._mod("_gp_d2")
        assert mod.t_is_true() == "true"
        assert self._stack() == []

    def test_a_definite_clause_rescues_a_deferred_answer_from_a_wrapper(self):
        """Untabled ``r``: the first clause derives ``r(a)`` conditionally
        through ``wins(a)``, the second is the FACT ``r(a)``.  One WFS-true
        answer, exported once — not exported and then raised on."""
        mod = self._mod("_gp_d3")
        assert mod.r_answers([]) == [("a",)]
        assert self._stack() == []

    def test_a_second_judged_goal_does_not_inherit_the_first_s_delays(self):
        """Two judged generators alive at once.  ``g`` yields its fact
        (``start``), then
        ``f`` (two facts, NO negation anywhere) starts and yields, then ``g``
        resumes and delays inside its untabled body: those delays are ``g``'s,
        and ``f`` must still deliver both of its answers."""
        mod = self._mod("_gp_d4")
        gg, gf = mod.stream_g(), mod.stream_f()
        try:
            assert next(gg) == ("start",)   # g's own fact, no conditions
            assert next(gf) == ("one",)
            # g resumes and DELAYS on the a/b/c branches before reaching its
            # second definite answer -- a distinct atom, so this pins that the
            # delaying branches really ran.
            assert next(gg) == ("d",)
            assert next(gf) == ("two",)
        finally:
            gg.close()
            gf.close()
        assert self._stack() == []

    def test_a_collected_bag_keeps_the_conditions_its_rows_stand_on(self):
        """``findall``/``count_all`` collect over a private trail mark and
        unwind it; the BAG survives that unwind, so the conditions its rows
        were derived under have to survive with it.  Trailing the conditions
        (defect 1 above) would otherwise retract them on the way out and
        report a bag built from undefined answers as definitely true."""
        from clausal.logic.seam import UndefinedAnswer
        mod = self._mod("_gp_d5")
        assert mod.warm([]) == [("e",)]     # drives wins/1 to completion
        with pytest.raises(UndefinedAnswer):
            mod.bag()
        with pytest.raises(UndefinedAnswer):
            mod.counted()
        assert self._stack() == []

    def test_a_bag_collected_off_a_LIVE_drive_keeps_its_conditions_too(self):
        """The pin above warms ``wins/1`` first, so it only covers the
        COMPLETE-table path.  On a cold table the answers arrive by STREAMING,
        and there the top of the leader stack is the table's own entry -- the
        conditions are credited to the leader BELOW it.  A harvest that read
        the stack top would collect nothing and the bag would come back
        unconditionally true.

        The bag here is also a MIXED one -- ``wins/1`` gives the definite
        ``d`` alongside the undefined ``a``/``b``/``c`` -- so it pins that one
        undefined row is enough to make the whole bag's reader undefined."""
        from clausal.logic.seam import UndefinedAnswer
        mod = self._mod("_gp_d6")          # NOTHING drives wins/1 first
        with pytest.raises(UndefinedAnswer):
            mod.cold_bag()
        assert self._stack() == []

    def test_setof_and_bagof_keep_their_conditions(self):
        """``setof``/``bagof`` reorder the statements around the charge
        (sort/dedup, fail-on-empty); they carry conditions like ``findall``."""
        from clausal.logic.seam import UndefinedAnswer
        mod = self._mod("_gp_d7")
        with pytest.raises(UndefinedAnswer):
            mod.cold_set()
        assert self._stack() == []
        mod = self._mod("_gp_d8")
        with pytest.raises(UndefinedAnswer):
            mod.cold_bagof()
        assert self._stack() == []

    def test_backtracking_over_a_bag_retracts_the_conditions_it_charged(self):
        """The charge lands AT the construct's own mark, so failing PAST the
        whole ``findall`` retracts it: the next clause's answer is a plain
        fact and must be exported as definitely true, not raised on."""
        mod = self._mod("_gp_d9")
        assert mod.after_the_bag() == ("ok",)
        assert self._stack() == []

    def test_count_all_keeps_its_conditions_off_a_live_drive_too(self):
        """``count_all``'s lowering changed identically to ``findall``'s, but
        the warm pin above reaches its delays through ``_delay_negation``
        behind an untabled goal -- not through the STREAMING credit path this
        repaired.  Cold, over a tabled goal directly, it does."""
        from clausal.logic.seam import UndefinedAnswer
        mod = self._mod("_gp_e1")
        with pytest.raises(UndefinedAnswer):
            mod.cold_counted()
        assert self._stack() == []

    def test_a_bag_over_two_tabled_goals_keeps_their_conditions(self):
        """The collecting leader is bound at the construct's ENTRY, while the
        credit for a conditional row is stack-RELATIVE (the leader below the
        streaming table).  With a second table parked between them the two
        rules address different frames, and the condition reaches the bag
        only because the inner table folds it into its own answers, which
        credit the leader below on streaming.  Measured, both before and
        after the entry-time binding -- this pins the transitive path."""
        from clausal.logic.seam import UndefinedAnswer
        mod = self._mod("_gp_e2")
        with pytest.raises(UndefinedAnswer):
            mod.two_tables()
        assert self._stack() == []

    def test_a_negation_after_a_streaming_tabled_goal_in_a_bag(self):
        """``not zz(X)`` charges the stack TOP, which during ``wins``'s stream
        is ``wins``'s own entry, not the collecting leader.  The condition
        still reaches the bag; this pins that it does."""
        from clausal.logic.seam import UndefinedAnswer
        mod = self._mod("_gp_e3")
        with pytest.raises(UndefinedAnswer):
            mod.naf_after_stream()
        assert self._stack() == []

    def test_a_nested_judged_goal_on_the_SAME_table_keeps_the_outer_answers(self):
        """A ``--`` loop whose body runs another ``--`` over the SAME tabled
        predicate.  The outer loop must still deliver every answer.

        Detaching the judging leader's frames across a yield (which is what
        stops two judged goals charging each other) hid the outer's table from
        the inner call, so the inner re-LED it, drove it to completion, and the
        outer's own answers were deduped away as already-known when it resumed
        -- silently losing solutions, with no error.  The inner loop sees the
        answers known when it runs, exactly as a tabled consumer does."""
        mod = self._mod("_gp_e4")
        out = mod.nested_same_table([])
        assert [x for x, _inner in out] == [("one",), ("two",)]
        assert self._stack() == []
