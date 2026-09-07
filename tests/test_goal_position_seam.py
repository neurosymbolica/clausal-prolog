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
        mod = _load_inline("_gp_for6", RULEBASE.format(name="_gp_for6") + (
            "def mutate(profile):\n"
            "    out = []\n"
            "    for IDS in --decide(++profile, verdict(_, IDS)):\n"
            "        IDS.append(('x',))\n"
            "        out.append(len(IDS))\n"
            "    return out\n"
        ))
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
