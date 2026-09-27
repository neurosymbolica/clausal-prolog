"""P3-3 Task 5 (R11): a CELL is usable as a goal and as an assert/retract argument.

Before this task a cell -- the tagged tuple ``("f", a, b)`` that every data
functor's terms compile to since the P3-2 flip -- was a term the engine could
build and unify but could not *run*: ``solve(("p", X))`` raised
``NotImplementedError`` out of ``terms_to_goalop``, ``call(("p", X))`` failed
silently, and ``assertz(("p", 1))`` was refused outright with a
``permission_error`` whose message described the P3-2 diagnostic rather than a
policy.  R11 makes the cell a first-class spelling of a goal, which is what
these tests pin:

  - ``database.head_key`` reads a cell's ``(functor, arity)``;
  - ``solve._term_to_goal`` lowers a cell goal to the SAME ``Call`` node a
    Compound or class-term goal lowers to, so the three answer alike;
  - the ``call/N`` family resolves a cell (and a bare atom) NAME against the
    calling module's database, folding its own extra arguments on ISO-style;
  - ``assertz``/``asserta``/``retract`` take a cell, gated three ways on the
    target row (dynamic / static / unknown);
  - the query cache keys a cell goal structurally, so equal cell goals share
    one compiled query.

Two cell-goal shapes were DEFERRED by Task 5 with a diagnostic rather than
supported, and each is pinned here so the deferral is visible and its
replacement is a test-visible event.  One of the two has since been replaced:
the module-qualified ``(":", M, G)`` now RESOLVES (P3-3 Task 6 supplied
``resolve_module``; ``cells.resolve_qualified_goal_cell`` kept its name and
gained a return), and the pins below record that change rather than the old
refusal — the semantics themselves belong to
``tests/test_qualified_goals.py``.  The control constructs ``,`` ``;`` ``->``
``\\+`` are still deferred to the ISO-surface phase (see
``cells.refuse_control_construct_cell``).
"""

from __future__ import annotations

import textwrap

import pytest

import clausal.import_hook  # noqa: F401 — installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.atoms import mint
from clausal.logic.database import Database, head_key
from clausal import cell_args, cell_functor
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import call as pcall, solve
from clausal.logic.variables import Var, deref
from clausal.terms import Compound


def _write_module(tmp_path, name: str, source: str):
    path = tmp_path / f"{name}.clausal"
    path.write_text(textwrap.dedent(source).lstrip())
    return _load_module(name, str(path))


def _lm(module):
    return module.__dict__["$module"]


def _error_term(exc: LogicException):
    """``(inner_error_term, indicator, message)`` from a raised LogicException:
    the formal, error/2's second argument (the Name/Arity cell, or the missing
    PI for existence_error(procedure, PI)), and the prose."""
    return cell_args(exc.term)[0], cell_args(exc.term)[1], exc.message


@pytest.fixture
def mod(tmp_path):
    """One module with a dynamic predicate, a static one, a zero-arity one
    and two call/N hosts."""
    return _write_module(tmp_path, "cellgoals", """
        -dynamic(p/1)
        -dynamic(pair/2)
        -dynamic(seen/1)
        -dynamic(seenc/1)

        p(1),
        p(2),

        stat(9),

        z0,

        q(X) <- p(X),

        cg1(G) <- call(G),
        cg2(G, A) <- call(G, A),
        cg3(G, A, B) <- call(G, A, B),
    """)


# ── head_key ───────────────────────────────────────────────────────────────


class TestHeadKeyCellBranch:
    def test_a_cell_reads_its_functor_and_arity(self):
        assert head_key(("p", 1)) == ("p", 1)
        assert head_key(("pair", 1, 2)) == ("pair", 2)

    def test_a_zero_arity_cell_reads_as_arity_zero(self):
        assert head_key("p") == ("p", 0)

    def test_a_tuple_tag_cell_is_data_and_still_raises(self):
        """``(tuple, 1, 2)`` is tuple DATA -- it names no predicate."""
        with pytest.raises(TypeError):
            head_key((tuple, 1, 2))

    def test_a_var_slot0_tuple_is_data_and_still_raises(self):
        with pytest.raises(TypeError):
            head_key((Var(), 1))

    def test_an_empty_tuple_still_raises(self):
        with pytest.raises(TypeError):
            head_key(())


# ── cells as goals ─────────────────────────────────────────────────────────


class TestCellAsGoal:
    def test_var_carrying_cell_goal_enumerates(self, mod):
        X = Var()
        assert [deref(X) for _ in solve(("p", X), _lm(mod))] == [1, 2]

    def test_a_cell_goal_answers_what_the_module_binding_goal_answers(self, mod):
        """The goal built from the module BINDING -- a class term pre-flip,
        the handle-headed cell ``(mod.p, X)`` post-W4b-2d -- answers as the
        plain cell does."""
        X, Y = Var(), Var()
        assert mod.p != "p"                   # the two spellings really differ
        by_binding = [deref(X) for _ in solve((mod.p, X), _lm(mod))]
        by_cell = [deref(Y) for _ in solve(("p", Y), _lm(mod))]
        assert by_cell == by_binding == [1, 2]

    def test_a_ground_cell_goal_succeeds_and_fails_by_value(self, mod):
        assert len(list(solve(("p", 2), _lm(mod)))) == 1
        assert list(solve(("p", 5), _lm(mod))) == []

    def test_a_cell_goal_reaches_a_rule_not_only_facts(self, mod):
        X = Var()
        assert [deref(X) for _ in solve(("q", X), _lm(mod))] == [1, 2]

    def test_a_cell_goal_lowers_to_the_same_node_a_compound_goal_does(self):
        from clausal.logic.solve import _term_to_goal
        v = Var()
        from_cell = _term_to_goal(("p", v))
        from_compound = _term_to_goal(Compound("p", (v,)))
        assert from_cell == from_compound


# ── call/N over cells and atoms ────────────────────────────────────────────


class TestCallNOverCells:
    def test_call_1_over_a_cell(self, mod):
        X = Var()
        assert [deref(X) for _ in pcall("cg1", ("p", X), module=_lm(mod))] == [1, 2]

    def test_call_2_folds_its_extra_arg_onto_a_zero_arity_cell(self, mod):
        """ISO: ``call(f, B)`` is the goal ``f(B)``."""
        X = Var()
        assert [deref(X) for _ in pcall("cg2", "p", X, module=_lm(mod))] == [1, 2]

    def test_call_2_folds_its_extra_arg_onto_a_one_arity_cell(self, mod):
        """``call(pair(1), Y)`` is the goal ``pair(1, Y)``."""
        lm = _lm(mod)
        list(pcall("assertz", ("pair", 1, "a"), module=lm))
        list(pcall("assertz", ("pair", 1, "b"), module=lm))
        Y = Var()
        assert [deref(Y) for _ in pcall("cg2", ("pair", 1), Y, module=lm)] == ["a", "b"]

    def test_call_3_folds_both_extra_args(self, mod):
        lm = _lm(mod)
        list(pcall("assertz", ("pair", 3, 4), module=lm))
        assert len(list(pcall("cg3", "pair", 3, 4, module=lm))) == 1
        assert list(pcall("cg3", "pair", 3, 5, module=lm)) == []

    def test_a_bare_atom_goal_resolves_with_the_extra_args(self, mod):
        """``call(p, X)`` is the goal ``p(X)``.  STAGE 2 (atoms-as-str): the
        atom IS the bare ``str``; the two spellings below agree."""
        X = Var()
        assert [deref(X)
                for _ in pcall("cg2", mint("p"), X, module=_lm(mod))] == [1, 2]

    def test_a_bare_str_goal_has_no_procedure(self, mod):
        """STAGE 2 (atoms-as-str, spec §3 Q1): a bare ``str`` IS the atom,
        so ``call("p", X)`` is the goal ``p(X)`` and answers exactly what the
        ``mint("p")`` spelling above answers -- not a refusal.  (Under THE
        FLIP a ``str`` was a STRING and this raised ``existence_error`` for
        ``'.'/3``; a string is the ``chars`` carrier now.)"""
        X = Var()
        assert [deref(X)
                for _ in pcall("cg2", "p", X, module=_lm(mod))] == [1, 2]

    def test_a_non_cell_non_callable_goal_is_a_type_error(self, mod):
        """FLIPPED, operator ruling 2026-09-25 (call-runs-body-terms round 2: follow Scryer): the translator session's
        "section 4.2" silent-failure contract is retired.  Scryer answers
        ``call(42)``, ``call(3.5)`` and ``call([1, 2])`` with
        type_error(callable, G), and so does this engine now."""
        for goal in (42, 3.5):
            with pytest.raises(LogicException) as exc_info:
                list(pcall("cg1", goal, module=_lm(mod)))
            inner, _, _ = _error_term(exc_info.value)
            assert cell_functor(inner) == "type_error"
            assert cell_args(inner) == (mint("callable"), goal)
        # FLIPPED again, operator rule 2026-09-25, ISO first: a non-empty list or string is the callable compound '.'/2, so call/1 of one names the missing procedure '.'/2; Scryer disagrees with itself (literal call([a]) -> existence_error, run-time G = [a], call(G) -> type_error): ``[1, 2]`` is existence_error '.'/2.
        with pytest.raises(LogicException) as exc_info:
            list(pcall("cg1", [1, 2], module=_lm(mod)))
        inner, _, _ = _error_term(exc_info.value)
        assert cell_functor(inner) == "existence_error"
        assert cell_args(inner)[1] == ("/", ".", 2)

    def test_a_tuple_tag_data_cell_goal_is_a_type_error(self, mod):
        """FLIPPED, operator ruling 2026-09-25 (call-runs-body-terms round 2: follow Scryer): tuple DATA is not a goal, and a
        non-goal is type_error(callable, G) rather than a silent failure."""
        for goal in ((tuple, 1, 2), ("()", 1, 2)):
            with pytest.raises(LogicException) as exc_info:
                list(pcall("cg1", goal, module=_lm(mod)))
            assert cell_functor(_error_term(exc_info.value)[0]) == "type_error"

    def test_an_unknown_cell_goal_raises_existence_error(self, mod):
        """FLIPPED 2026-09-25 -- operator ruling 2 ("like Scryer"): a meta-call naming an UNKNOWN procedure raises ISO existence_error(procedure, Name/Arity), catchable; it used to fail silently (the retired §4.2 contract).

        This used to be ``test_an_unknown_cell_goal_fails_silently``."""
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException) as exc:
            list(pcall("cg1", ("no_such_pred", 1), module=_lm(mod)))
        formal = cell_args(exc.value.term)[0]
        assert cell_functor(formal) == "existence_error"
        assert cell_args(formal)[1] == ("/", "no_such_pred", 1)

    def test_call_over_a_predicate_class_is_untouched(self, mod):
        """The pre-existing route — a goal OBJECT answering ``_get_dispatch``
        — is reached before any name resolution and is unchanged."""
        X = Var()
        assert [deref(X) for _ in pcall("cg2", mod.p, X, module=_lm(mod))] == [1, 2]

    def test_a_runtime_built_class_TERM_goal_answers_like_the_cell(self, mod):
        """THE ASYMMETRY IS GONE (P2 Task 3, 2026-09-19).  It was: ``call(G)``
        resolved a cell and an atom by NAME, but ``p(X)`` built at runtime was
        a class-term INSTANCE — neither callable nor ``_get_dispatch``-bearing,
        since that protocol lives on the metaclass — and failed silently, so
        which behaviour a caller got depended on whether the CALLEE had
        clauses.  P2 closed it at the representation instead of at
        ``_resolve_named_goal``: ``p(X)`` from Python IS the cell ``("p", X)``
        now, so both spellings are one term and answer alike.  Closes
        todo/done/call-n-does-not-resolve-a-runtime-built-class-term-goal-2026-09-06.md."""
        # W4b-2d: ``mod.p`` is the predicate's handle; the term built from
        # it at runtime is the handle-headed cell ``(mod.p, X)``.
        X, Y = Var(), Var()
        assert [deref(X) for _ in pcall("cg1", (mod.p, X), module=_lm(mod))] == [1, 2]
        assert ([deref(X) for _ in pcall("cg1", (mod.p, X), module=_lm(mod))]
                == [deref(Y) for _ in pcall("cg1", ("p", Y), module=_lm(mod))])

    def test_an_imported_predicate_answers_call_as_it_answers_solve(
            self, tmp_path):
        """``db.get_dispatch`` is the dispatch table plus the builtin registry
        — it does NOT read the module dict, and an ``-import_from``'d
        predicate lives on the OWNER's row, reachable only through the class
        the import bound here.  So ``solve`` answered and ``call`` failed
        silently, for the same goal.  Fix round 1, F2."""
        _write_module(tmp_path, "cg_lib", """
            -module(cg_lib, [lp(A)])
            -dynamic(lp/1)

            lp(1),
            lp(2),
        """)
        importer = _write_module(tmp_path, "cg_imp", """
            -import_from(cg_lib, [lp])

            host(G) <- call(G),
        """)
        lm = _lm(importer)
        Y, Z = Var(), Var()
        by_solve = [deref(Y) for _ in solve(("lp", Y), lm)]
        by_call = [deref(Z) for _ in pcall("host", ("lp", Z), module=lm)]
        assert by_solve == [1, 2]
        assert by_call == by_solve

    def test_a_zero_argument_control_cell_is_refused_not_silently_failed(
            self, mod):
        """``call((",",))`` used to fall past the arity-guarded refusal and
        fail silently while ``solve((",",), m)`` raised.  Fix round 1, F3.
        FLIPPED, operator ruling 2026-09-25 (call-runs-body-terms round 2: follow Scryer): still raised, now as ISO's
        existence_error(procedure, ','/0) -- ``,`` is a construct of arity 2."""
        with pytest.raises(LogicException) as exc_info:
            list(pcall("cg1", ",", module=_lm(mod)))
        inner, _, _ = _error_term(exc_info.value)
        assert cell_functor(inner) == "existence_error"
        assert cell_args(inner)[1] == ("/", ",", 0)

    def test_the_atom_spelling_of_a_qualified_goal_folds_the_same_way(
            self, mod):
        """``call(":", M, G)`` folds to the same goal as ``call((":", M, G))``
        and must behave identically; it used to bypass the qualified route and
        fall to a ``:``/2 dispatch lookup that found nothing.  Fix round 1, F4.

        P3-3 Task 6 replaced the shared refusal with a shared RESOLUTION, so
        the pin is now that both spellings ANSWER alike (they used to raise
        alike).  ``tests/test_qualified_goals.py`` owns the qualified-goal
        semantics; what stays pinned here is that the fold makes one goal of
        the two spellings."""
        lm = _lm(mod)
        X, Y = Var(), Var()
        by_atom = [deref(X) for _ in pcall(
            "cg3", mint(":"), "cellgoals", ("p", X), module=lm)]
        by_cell = [deref(Y) for _ in pcall(
            "cg1", (":", "cellgoals", ("p", Y)), module=lm)]
        assert by_atom == by_cell == [1, 2]

    def test_both_spellings_of_an_unresolvable_qualified_goal_raise_alike(
            self, mod):
        """The other half of F4's pin: the two spellings share the DIAGNOSTIC
        too, and only the indicator differs (call/3 vs call/1)."""
        lm = _lm(mod)
        errors = []
        for goal_args in ((mint(":"), "nosuchmodule", ("p", 1)),
                          ((":", "nosuchmodule", ("p", 1)),)):
            with pytest.raises(LogicException) as exc_info:
                list(pcall("cg" + str(len(goal_args)), *goal_args, module=lm))
            errors.append(_error_term(exc_info.value))
        assert errors[0][0] == errors[1][0] == (
            "existence_error", mint("module"), "'nosuchmodule'")
        assert errors[0][1] == ("/", "call", 3) and errors[1][1] == ("/", "call", 1)
        assert errors[0][2] == errors[1][2]

    def test_the_atom_spelling_of_a_control_construct_hits_the_same_refusal(
            self, mod):
        """Same folding, the other deferred route.  FLIPPED, operator ruling 2026-09-25 (call-runs-body-terms round 2: follow Scryer):
        the ISO conjunction cell RUNS now, so the pin is that both spellings
        ANSWER alike."""
        lm = _lm(mod)
        a = list(pcall("cg3", mint(","), ("p", 1), ("p", 2), module=lm))
        b = list(pcall("cg1", (",", ("p", 1), ("p", 2)), module=lm))
        assert len(a) == len(b) == 1

    def test_the_call_family_is_registered_db_receiving(self):
        """call/N moved from _BUILTINS to _DB_BUILTINS so it can resolve a
        NAME against the caller's database; the arity set is unchanged."""
        from clausal.logic.builtins._registry import _BUILTINS, _DB_BUILTINS
        for n in range(1, 9):
            assert ("call", n) in _DB_BUILTINS
            assert ("call_goal", n) in _DB_BUILTINS
            assert ("call", n) not in _BUILTINS
            assert ("call_goal", n) not in _BUILTINS

    def test_the_db_less_call_dispatch_still_invokes_a_goal_object(self, mod):
        """``factory(None)`` is call/N's pre-Task-5 self: no name resolution,
        everything else intact.  This is the path ``_BUILTIN_CLASSES`` and a
        ``BuiltinPredicate`` built without a db take."""
        from clausal.logic.builtins._registry import _stateless_dispatch
        from clausal.logic.solve import _drive_trampoline
        from clausal.logic.variables import Trail
        call_2 = _stateless_dispatch("call", 2)
        call_1 = _stateless_dispatch("call", 1)
        assert call_2 is not None and call_1 is not None
        X = Var()
        answers = [deref(X)
                   for _ in _drive_trampoline(call_2, Trail(), mod.p, X)]
        assert answers == [1, 2]
        # ...and with no db there is no name to resolve, so a cell fails.
        Y = Var()
        assert list(_drive_trampoline(call_1, Trail(), ("p", Y))) == []


# ── the two deferred cell-goal forms ───────────────────────────────────────


class TestDeferredCellGoalForms:
    @pytest.mark.parametrize("functor", [",", ";", "->", "*->", "\\+"])
    def test_a_control_construct_cell_goal_is_refused_by_solve(self, mod, functor):
        cell = (functor, ("p", 1), ("p", 2))
        with pytest.raises(LogicException) as exc_info:
            list(solve(cell, _lm(mod)))
        inner, _pi, context = _error_term(exc_info.value)
        assert inner == (
            "type_error", mint("callable_control_construct_unsupported"),
            cell)
        assert f"{functor}/2 is a control construct" in context

    def test_a_control_construct_cell_goal_runs_under_call(self, mod):
        """FLIPPED, operator ruling 2026-09-25 (call-runs-body-terms round 2: follow Scryer): ``(",", A, B)``, ``(";", A, B)`` and
        ``("\\+", G)`` run as bodies; ``->`` stays refused (cut-free, no
        committed choice) -- tests/test_call_runs_body_terms.py owns that.
        ``solve`` still refuses the cell (next test): the ruling was call's."""
        cell = (",", ("p", 1), ("p", 2))
        assert len(list(pcall("cg1", cell, module=_lm(mod)))) == 1
        with pytest.raises(LogicException) as exc_info:
            list(pcall("cg1", ("->", ("p", 1), ("p", 2)), module=_lm(mod)))
        inner, _pi, context = _error_term(exc_info.value)
        assert cell_functor(inner) == "existence_error"
        assert "call/1" in context

    def test_the_refusal_names_the_compile_time_form(self, mod):
        with pytest.raises(LogicException) as exc_info:
            list(solve((",", ("p", 1), ("p", 2)), _lm(mod)))
        _inner, _pi, context = _error_term(exc_info.value)
        assert "And" in context and "clause body" in context

    def test_a_qualified_goal_cell_now_resolves_instead_of_being_refused(
            self, mod):
        """Task 5 deferred ``(":", M, G)`` with an ``existence_error`` naming
        the stub; P3-3 Task 6 supplied the resolver, so a RESOLVABLE module
        answers.  The semantics live in ``tests/test_qualified_goals.py``;
        this is the deferral's replacement made test-visible, as Task 5
        promised it would be."""
        X = Var()
        assert [deref(X)
                for _ in solve((":", "cellgoals", ("p", X)),
                               _lm(mod))] == [1, 2]

    def test_an_unresolvable_qualified_goal_cell_is_an_existence_error(
            self, mod):
        with pytest.raises(LogicException) as exc_info:
            list(solve((":", "nosuchmodule", ("p", 1)), _lm(mod)))
        inner, _pi, context = _error_term(exc_info.value)
        assert inner == (
            "existence_error", mint("module"), "'nosuchmodule'")
        assert "sys.modules" in context

    def test_a_qualified_goal_cell_resolves_through_call_too(self, mod):
        X = Var()
        assert [deref(X) for _ in pcall(
            "cg1", (":", "cellgoals", ("p", X)), module=_lm(mod))] == [1, 2]

    def test_only_colon_slash_2_is_the_qualified_form_on_the_lowering_paths(
            self, mod):
        """``(":", A, B, C)`` is an ordinary ``:``/3 call.  Both LOWERING paths
        must agree on that: ``_term_to_goal``'s guard has always been
        ``len == 3``, and ``_templatize_query_goal``'s was arity-blind.
        Task 5 fix round 1, F5 — still the rule now that ``:``/2 resolves
        rather than being refused.

        SCOPE (narrowed by P3-3 Task 6 fix round 1, ruling R-A): "only ``:``/2"
        is a statement about these two functions, which lower a goal TERM as
        written.  ``call/N`` is not a lowering path — its fold has already
        moved the extras in, so there a folded ``:``/N≥2 is ``M:G`` with N-2
        extras still to place (``call(M:p, X)`` → ``M:p(X)``).  That is Task 5
        F4's rule, not an exception to F5: the two are consistent because
        nothing folds anything here."""
        from clausal.logic.solve import _templatize_query_goal, _term_to_goal
        from clausal.pythonic_ast.nodes import Call as AstCall, LoadName

        goal = (":", 1, 2, 3)
        # the lowering path treats it as an ordinary call...
        assert _term_to_goal(goal) == AstCall(
            func=LoadName(name=":"), args=[1, 2, 3], kwargs=[])
        # ...and so does the templatizer: three ground args, three params.
        template, params = _templatize_query_goal(goal)
        assert len(params) == 3
        assert template[0] == ":" and [v for _pv, v in params] == [1, 2, 3]
        # while :/2 is the qualified form on both: the templatizer leaves it
        # for the strip in _compile_as_query, and the lowering resolves it.
        assert _templatize_query_goal((":", "m", ("g",)))[1] == []
        with pytest.raises(LogicException):
            _term_to_goal((":", "m", ("g",)))  # 'm' names no module

    def test_the_stub_became_the_resolver(self, mod):
        """Named so the hand-off is a symbol, not a grep.  Task 6 replaced the
        body: the same function now returns ``(module, inner_goal)`` and only
        raises when a designator names no module."""
        from clausal.logic import cells
        assert callable(cells.resolve_qualified_goal_cell)
        with pytest.raises(LogicException):
            cells.resolve_qualified_goal_cell((":", "m", ("g",)), "ctx")
        module, inner = cells.resolve_qualified_goal_cell(
            (":", "cellgoals", ("p", 1)), "ctx")
        assert module.name == "cellgoals" and inner == ("p", 1)


# ── the zero-arity control constructs reached by NAME (final review I-3) ───


class TestZeroArityControlConstructsByName:
    """``true``/``fail``/``false``/``!`` are lowered by the compiler, so they
    have no row and no registry entry.  Reached by NAME through ``call/1``
    they resolved to nothing and FAILED SILENTLY — ``call(true)`` yielded zero
    solutions, which is the worst failure mode a Prolog can have.  They are
    answered directly now: not refused (unlike ``,``/``;``/``->``, they need
    no goal-tree interpreter) and not looked up (no database defines them)."""

    @pytest.mark.parametrize("goal", ["true"])
    def test_true_succeeds_exactly_once(self, mod, goal):
        assert len(list(pcall("cg1", goal, module=_lm(mod)))) == 1

    @pytest.mark.parametrize("goal", ["fail", "false"])
    def test_fail_and_false_fail(self, mod, goal):
        assert list(pcall("cg1", goal, module=_lm(mod))) == []

    @pytest.mark.parametrize("goal", ["!"])
    def test_cut_succeeds_once_because_it_is_local_to_the_call(self, mod, goal):
        """ISO 7.8.3: a cut inside ``call/1`` is local to that call, so the
        barrier IS the call and there is nothing left inside it to cut.
        ``call(!)`` is therefore ``call(true)`` — opaque, not a silent change
        to the caller's choice points."""
        assert len(list(pcall("cg1", goal, module=_lm(mod)))) == 1

    def test_the_control_constructs_do_not_consume_the_arity_one_spelling(
            self, mod):
        """``call(true, X)`` is the goal ``true/1`` -- not ``true`` with an
        argument thrown away.  FLIPPED, operator ruling 2026-09-25 (call-runs-body-terms round 2: follow Scryer): Scryer answers
        existence_error(procedure, true/1), and so does this engine (it used
        to fail silently, as an unknown name does)."""
        with pytest.raises(LogicException) as exc_info:
            list(pcall("cg2", mint("true"), 1, module=_lm(mod)))
        inner, _, _ = _error_term(exc_info.value)
        assert cell_functor(inner) == "existence_error"
        assert cell_args(inner)[1] == ("/", "true", 1)

    def test_they_answer_without_a_database_too(self):
        """Decided before the db lookups, like the control-construct refusal,
        so the behaviour never depends on how the builtin was reached."""
        from clausal.logic.builtins.higher_order import _resolve_named_goal
        assert _resolve_named_goal(None, "true", (), "call/1") is not None
        assert _resolve_named_goal(None, "fail", (), "call/1") is not None
        assert _resolve_named_goal(
            None, "no_such_pred", (), "call/1") is None


# ── a bare str goal IS the atom (stage 2, atoms-as-str) ────────────────────


class TestBareStrGoalInSolve:
    """STAGE 2 (atoms-as-str, spec §3 Q1): a bare ``str`` IS the atom, so
    ``solve("z0", m)`` is the call of ``z0/0`` -- the same goal the
    ``Compound("z0", ())`` spelling lowers to.  (THE FLIP had made a ``str``
    a STRING, with ``solve("z0", m)`` an ``existence_error(procedure,
    '.'/2)``; a string is the ``chars`` carrier now, and the old 1-tuple cell
    spelling is refused by the engine.)"""

    def test_a_bare_str_goal_has_no_procedure(self, mod):
        lm = _lm(mod)
        assert len(list(solve("z0", lm))) == 1
        assert len(list(solve(Compound("z0", ()), lm))) == 1

    def test_the_lowering_path_refuses_a_bare_str_goal(self):
        from clausal.logic.solve import _term_to_goal
        assert _term_to_goal("z0") == _term_to_goal(Compound("z0", ()))

    def test_an_unknown_cell_goal_still_reports_the_missing_predicate(
            self, mod):
        from clausal.predicate_diagnostics import PredicateNotFoundError
        lm = _lm(mod)
        with pytest.raises(PredicateNotFoundError):
            list(solve("no_such_pred", lm))


# ── assertz / asserta / retract with a cell ────────────────────────────────


class TestCellAssertRetract:
    def test_a_cell_asserted_into_a_dynamic_predicate_is_queryable_both_ways(
            self, mod):
        lm = _lm(mod)
        list(pcall("assertz", ("p", 7), module=lm))
        X = Var()
        by_cell = [deref(X) for _ in solve(("p", X), lm)]
        Y = Var()
        by_binding = [deref(Y) for _ in solve((mod.p, Y), lm)]  # handle-headed
        Z = Var()
        by_call_node = [deref(Z) for _ in pcall("p", Z, module=lm)]
        assert by_cell == by_binding == by_call_node == [1, 2, 7]

    def test_asserta_puts_the_cell_first(self, mod):
        lm = _lm(mod)
        list(pcall("asserta", ("p", 0), module=lm))
        X = Var()
        assert [deref(X) for _ in solve(("p", X), lm)] == [0, 1, 2]

    def test_the_asserted_clause_has_the_shape_the_source_clauses_have(self, mod):
        """A cell is a SPELLING of the term, so it must not leave a foreign
        clause shape behind.  Since the P2 head flip (2026-09-19) the shape a
        source clause leaves IS the cell, so this now pins that the two
        spellings agree rather than that the cell is converted away."""
        lm = _lm(mod)
        list(pcall("assertz", ("p", 7), module=lm))
        heads = [c.head for c in lm.db.clauses_for("p", 1)]
        assert heads[-1] == ("p", 7)
        assert all(type(h) is tuple for h in heads), "source clauses too"

    def test_collect_by_assert_over_a_cell_stores_one_clause_per_solution(
            self, mod):
        """The collect-by-assert idiom: drive a goal, assert one fact per
        solution.  The stored head must hold the VALUE the variable had at
        assert time, not the variable — otherwise every clause reads back as
        whatever it was bound to last.  Fix round 1, F1."""
        lm = _lm(mod)
        X = Var()
        for _ in solve(("p", X), lm):
            list(pcall("assertz", ("seen", X), module=lm))
        Y = Var()
        assert [deref(Y) for _ in solve(("seen", Y), lm)] == [1, 2]

    def test_the_cell_spelling_agrees_with_the_compound_spelling(self, mod):
        """The Compound path has always frozen (``_normalize_fact_clause``
        rebuilds a bound argument as a fresh Var + Unify); the cell path now
        agrees with it, which is the point of the fix."""
        lm = _lm(mod)
        X = Var()
        for _ in solve(("p", X), lm):
            list(pcall("assertz", Compound("seenc", (X,)), module=lm))
        Z = Var()
        for _ in solve(("p", Z), lm):
            list(pcall("assertz", ("seen", Z), module=lm))
        Y, W = Var(), Var()
        by_compound = [deref(Y) for _ in solve(("seenc", Y), lm)]
        by_cell = [deref(W) for _ in solve(("seen", W), lm)]
        assert by_cell == by_compound == [1, 2]

    def test_the_freeze_is_on_the_assert_path_only(self, mod):
        """``retract`` must keep SHARING the caller's variables — binding them
        is how a retracted clause's values escape with the solution — so the
        freeze lives in ``_build_clause``, not in the shared gate."""
        lm = _lm(mod)
        X = Var()
        assert len(list(pcall("retract", ("p", X), module=lm))) == 1
        assert deref(X) == 1

    def test_a_cell_retract_removes_a_cell_asserted_clause(self, mod):
        lm = _lm(mod)
        list(pcall("assertz", ("p", 7), module=lm))
        assert len(list(pcall("retract", ("p", 7), module=lm))) == 1
        X = Var()
        assert [deref(X) for _ in solve(("p", X), lm)] == [1, 2]

    def test_a_cell_retract_removes_a_clause_loaded_from_source(self, mod):
        """The cross-representation case: the clause head is a class term and
        the pattern is a cell.  It matches because the cell normalizes to that
        class's instance before the search."""
        lm = _lm(mod)
        assert len(list(pcall("retract", ("p", 1), module=lm))) == 1
        X = Var()
        assert [deref(X) for _ in solve(("p", X), lm)] == [2]

    def test_a_cell_retract_binds_the_patterns_variables(self, mod):
        lm = _lm(mod)
        X = Var()
        assert len(list(pcall("retract", ("p", X), module=lm))) == 1
        assert deref(X) == 1

    def test_a_cell_retract_that_matches_nothing_fails_without_writing(self, mod):
        lm = _lm(mod)
        before = list(lm.db.clauses_for("p", 1))
        assert list(pcall("retract", ("p", 99), module=lm)) == []
        assert lm.db.clauses_for("p", 1) == before

    def test_a_cell_assert_against_a_static_predicate_is_a_permission_error(
            self, mod):
        with pytest.raises(LogicException) as exc_info:
            list(pcall("assertz", ("stat", 3), module=_lm(mod)))
        inner, pi, context = _error_term(exc_info.value)
        assert inner == (
            "permission_error",
            mint("modify"), mint("static_procedure"), ("/", "stat", 1))
        assert pi == ("/", "assertz", 1) and "-dynamic(stat/1)" in context

    def test_a_cell_assert_against_an_unknown_predicate_is_an_existence_error(
            self, mod):
        """Not assertz's usual "create the predicate": a cell is
        indistinguishable from a str-headed data tuple, so an undeclared
        target must not silently become state."""
        with pytest.raises(LogicException) as exc_info:
            list(pcall("assertz", ("nope", 3), module=_lm(mod)))
        inner, _pi, context = _error_term(exc_info.value)
        assert inner == (
            "existence_error", mint("procedure"), ("/", "nope", 1))
        assert "does not create one" in context

    def test_a_cell_assert_against_a_declared_data_functor_is_a_permission_error(
            self, tmp_path):
        """A data functor -- declared with fields, given no clauses -- has no
        Database ROW at all, so the row lookup alone would call it unknown.
        The declaration is what puts it on the static side of the line, and
        the P3-2 diagnostic (which names ``-dynamic`` as the remedy) is what
        it gets.  Also pinned from the .clausal surface by
        tests/test_exceptions.py::TestAssertzAgainstADataFunctor."""
        m = _write_module(tmp_path, "cellgoals_data", """
            -module(cellgoals_data, [d(A), go(X)])

            go(X) <- assertz(d(X)),
        """)
        with pytest.raises(LogicException) as exc_info:
            list(pcall("go", 7, module=_lm(m)))
        inner, _pi, context = _error_term(exc_info.value)
        assert inner == (
            "permission_error",
            mint("modify"), mint("static_procedure"), ("/", "d", 1))
        assert "data functor" in context and "-dynamic(d/1)" in context

    def test_the_declaration_check_is_arity_checked(self, tmp_path):
        """``d`` is declared at arity 1; a runtime-built cell naming ``d/2``
        is not that declaration, so it is genuinely unknown.  (The cell is
        built here rather than written as ``d(X, Y)`` in source, which the
        compiler rejects at load with its own arity SyntaxError.)"""
        m = _write_module(tmp_path, "cellgoals_data2", """
            -module(cellgoals_data2, [d(A), go(X)])

            go(X) <- assertz(d(X)),
        """)
        with pytest.raises(LogicException) as exc_info:
            list(pcall("assertz", ("d", 7, 8), module=_lm(m)))
        inner, _pi, _context = _error_term(exc_info.value)
        assert inner == (
            "existence_error", mint("procedure"), ("/", "d", 2))
        # ...while arity 1, the declared one, is the permission_error.
        with pytest.raises(LogicException) as exc_info:
            list(pcall("assertz", ("d", 7), module=_lm(m)))
        assert cell_functor(_error_term(exc_info.value)[0]) == "permission_error"

    def test_a_cell_retract_follows_the_same_gate(self, mod):
        lm = _lm(mod)
        with pytest.raises(LogicException) as exc_info:
            list(pcall("retract", ("stat", 9), module=lm))
        inner, pi, _context = _error_term(exc_info.value)
        assert cell_functor(inner) == "permission_error"
        assert pi == ("/", "retract", 1)
        with pytest.raises(LogicException) as exc_info:
            list(pcall("retract", ("nope", 3), module=lm))
        assert cell_functor(_error_term(exc_info.value)[0]) == "existence_error"

    def test_a_non_cell_assert_is_untouched_by_the_gate(self, mod):
        """A Compound assert still creates its predicate, as it always has."""
        lm = _lm(mod)
        list(pcall("assertz", Compound("fresh", (1,)), module=lm))
        X = Var()
        assert [deref(X) for _ in pcall("fresh", X, module=lm)] == [1]

    def test_a_cell_assert_into_a_classless_dynamic_row_uses_a_compound_head(self):
        """No class in scope (a bare Database) — the head is the Compound
        ``assertz(Compound(...))`` would have built."""
        db = Database()
        db.mark_dynamic("r", 1)
        from clausal.logic.builtins import get_builtin_dispatch
        from clausal.logic.solve import _drive_trampoline
        from clausal.logic.variables import Trail
        dispatch = get_builtin_dispatch("assertz", 1, db)
        list(_drive_trampoline(dispatch, Trail(), ("r", 5)))
        head = db.clauses_for("r", 1)[-1].head
        assert isinstance(head, Compound) and head.functor == "r"


class TestTheLowLevelDoorTakesACellHead:
    """A clause head IS the functor-first cell (P2 head flip, 2026-09-19), so
    the low-level store door takes one and answers from it.

    It used to REFUSE, and the refusal was right at the time: no lowering path
    read a cell as a head, so a cell-headed clause compiled to a predicate
    that answered with its arguments UNBOUND — a silent wrong answer, which is
    worse than the ``TypeError`` the door gave before ``head_key`` learned
    about cells.  Every one of those readers takes a cell now, so what these
    tests pin is the other half of that same contract: it stores, it answers
    BOUND, and retract by a cell pattern removes the clause it matched.
    """

    def test_database_assertz_takes_a_cell_head(self):
        from clausal.logic.database import Clause
        db = Database()
        db.assertz(Clause(head=("p", 1), body=[]))
        assert len(db.clauses_for("p", 1)) == 1

    def test_database_asserta_takes_a_cell_head(self):
        from clausal.logic.database import Clause
        db = Database()
        db.assertz(Clause(head=("p", 2), body=[]))
        db.asserta(Clause(head=("p", 1), body=[]))
        assert [c.head for c in db.clauses_for("p", 1)] == [("p", 1), ("p", 2)]

    def test_a_cell_headed_clause_answers_BOUND(self, mod):
        """The defect the refusal existed to prevent, asserted as fixed.

        Through the LOW-LEVEL door (``Database.assertz``, not the assertz/1
        builtin that used to normalise the cell away), against a predicate
        with a compiled dispatch — which is the shape that answered UNBOUND
        before the flip."""
        from clausal.logic.database import Clause
        lm = _lm(mod)
        lm.db.assertz(Clause(head=("p", 7), body=[]))
        X = Var()
        assert 7 in [deref(X) for _ in solve(("p", X), lm)]

    def test_database_retract_takes_a_cell_head(self):
        from clausal.logic.database import Clause
        db = Database()
        db.assertz(Clause(head=("p", 1), body=[]))
        assert db.retract(("p", 1)) is not False
        assert db.clauses_for("p", 1) == [], "and it removed the clause"

    def test_a_tuple_tag_head_keeps_the_old_typeerror(self):
        from clausal.logic.database import Clause
        db = Database()
        with pytest.raises(TypeError):
            db.assertz(Clause(head=(tuple, 1), body=[]))

    def test_the_builtin_door_is_the_one_that_works(self, mod):
        """The refusal points somewhere real: the same cell through
        ``assertz/1`` lands, because that door normalizes it first."""
        lm = _lm(mod)
        list(pcall("assertz", ("p", 7), module=lm))
        X = Var()
        assert 7 in [deref(X) for _ in solve(("p", X), lm)]


# ── the query cache ────────────────────────────────────────────────────────


class TestCellGoalQueryCache:
    def test_two_structurally_equal_cell_goals_share_compiled_code(self, mod):
        from clausal.logic.solve import _query_cache
        lm = _lm(mod)
        X = Var()
        list(solve(("p", X), lm))
        size = len(_query_cache)
        assert size > 0, "a cell goal must be cacheable at all"
        Y = Var()
        list(solve(("p", Y), lm))
        assert len(_query_cache) == size

    def test_distinct_ground_cell_goals_share_one_compiled_query(self, mod):
        """``_templatize_query_goal`` parameterizes a cell's ground args, so
        the compiled query is value-independent."""
        from clausal.logic.solve import _query_cache
        lm = _lm(mod)
        list(solve(("p", 11), lm))
        size = len(_query_cache)
        for value in (12, 13, 14):
            list(solve(("p", value), lm))
        assert len(_query_cache) == size

    def test_a_cell_goal_keys_under_its_own_tag_not_the_sequence_tag(self):
        from clausal.logic.solve import _structural_key
        assert _structural_key(("p", 1), {})[0] == "cell"
        assert _structural_key([1, 2], {})[0] == "seq"
        assert _structural_key((tuple, 1, 2), {})[0] == "seq"

    def test_different_cell_functors_do_not_share_a_key(self):
        from clausal.logic.solve import _structural_key
        assert _structural_key(("p", 1), {}) != _structural_key(("q", 1), {})

    def test_an_unhashable_arg_still_disables_caching(self, mod):
        from clausal.logic.solve import _goal_cache_key
        assert _goal_cache_key(("p", {1: 2}), _lm(mod)) is None
