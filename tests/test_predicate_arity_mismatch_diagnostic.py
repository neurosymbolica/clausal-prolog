"""Calling a *visible* predicate at the wrong arity must say so.

See ``todo/arity-mismatch-reports-a-missing-trail-argument.md``.  When the
called name is out of scope the lookup fails and
``clausal.predicate_diagnostics`` already reports it well.  But when the name
IS bound — defined in this file, or imported — the compiler injects the
predicate class directly, the wrong-arity call reaches the generated dispatch
function, and it fails as a raw Python ``TypeError``::

    citation__3() missing 1 required positional argument: 'trail'

which leaks the mangled internal name, blames an argument the author never
wrote and cannot supply, and never says the word *arity* — the entire content
of the fault.  The in-module case is the common one, so the common fault had
the worse message.

The second half of this file is the false-positive guard.  A ``Call`` node in
a clause body is not necessarily a *goal*: partial-kwargs term construction
(``vec(x=1)``) and a DCG nonterminal passed to ``phrase/3``
(``phrase(count_leaves(T), ...)``) both look like arity mismatches at the name
level, and both must keep working.
"""

from __future__ import annotations

import os
import textwrap

import pytest

from clausal.logic.database import Clause
from clausal.logic.predicate import make_predicate
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref, walk
from clausal.predicate_diagnostics import (
    PredicateArityMismatchError,
    describe_arity_mismatch,
)
from clausal.testing import load_clausal_module, main


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def write(tmp_path, name, src):
    p = tmp_path / name
    p.write_text(textwrap.dedent(src).lstrip())
    return p


CITATIONS = """
    -private([art_1_2, meta])

    citation(art_1_2, "Reg-Z Article 1(2)", meta),
    cite(art_1_2),

    Test("citation record resolves") <- (
        cite(REF),
        citation(REF, METADATA)
    ),
"""


def _report(tmp_path, src, name="t.clausal"):
    """Run *src* as a .clausal test file and return the printed report."""
    path = write(tmp_path, name, src)
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        main([str(path)])
    return buf.getvalue()


# ── the reported message ─────────────────────────────────────────────────────


class TestTheMessage:

    def test_does_not_blame_trail(self, tmp_path):
        out = _report(tmp_path, CITATIONS)
        assert "positional argument" not in out
        assert "'trail'" not in out

    def test_does_not_leak_the_mangled_name(self, tmp_path):
        assert "citation__3" not in _report(tmp_path, CITATIONS)

    @pytest.mark.parametrize("call_args, passes", [
        ("REF, METADATA", 2),
        ("REF", 1),
        ("REF, LABEL, META, EXTRA", 4),
    ])
    def test_names_both_arities(self, tmp_path, call_args, passes):
        """Both numbers, and the passed one is *read off the call*.

        Asserting ``"2" in out`` was vacuous — every report contains a 2 (``goal
        2 of 2``, a line number), so a message that hard-coded the number, or
        printed the defined arity twice, passed.  Three call shapes against the
        same /3 predicate cannot all be satisfied by a constant.
        """
        out = _report(tmp_path, f"""
            -private([art_1_2, meta])

            citation(art_1_2, "Reg-Z Article 1(2)", meta),

            Test("both arities") <- citation({call_args}),
        """, name=f"argboth{passes}.clausal")
        assert f"citation takes 3 arguments, but this call passes {passes}" in out

    def test_states_the_fault_on_the_first_line(self, tmp_path):
        """The summary line is one line; the fault has to fit on it."""
        out = _report(tmp_path, CITATIONS)
        summary = next(ln for ln in out.splitlines()
                       if "citation record resolves" in ln)
        assert "takes 3 arguments" in summary
        assert "passes 2" in summary

    def test_points_at_the_definition(self, tmp_path):
        out = _report(tmp_path, CITATIONS)
        assert "t.clausal:3" in out

    def test_offers_a_remedy(self, tmp_path):
        out = _report(tmp_path, CITATIONS)
        assert "->" in out
        assert "pass 3 arguments to citation" in out

    def test_the_remedy_is_advice_that_works(self, tmp_path):
        """It must not say "define citation/2 as a predicate of its own".

        That was the first wording, and a reader who followed it in the same
        file had the clause padded to /3 and absorbed, then got this same
        message again — see ``test_following_the_remedy_literally``.
        """
        # The remedy is wrapped and hanging-indented, so match on the collapsed
        # text — asserting a raw substring pins the wrap width, not the advice.
        flat = " ".join(_report(tmp_path, CITATIONS).split())
        assert "define citation/2 as a predicate of its own" not in flat
        assert "give the 2-argument predicate a different name" in flat
        # Since same-name-two-arities-silently-merge.md the second head is a
        # load error, and the sentence says so instead of describing the old
        # silent absorption.
        assert "refused at load" in flat
        assert "absorbed" not in flat


class TestForwardReference:
    """A call written *above* the definition resolves the same way."""

    def test_still_diagnosed(self, tmp_path):
        out = _report(tmp_path, """
            -private([art_1_2, meta])

            Test("forward") <- citation(REF, META),

            citation(art_1_2, "Reg-Z Article 1(2)", meta),
        """)
        assert "takes 3 arguments" in out
        assert "positional argument" not in out


class TestOtherGoalPositions:
    """Every position that turns a name into a dispatch function reports it.

    ``_get_dispatch`` is that one place, which is why negation, ``findall/3``
    and ``call/N`` all arrive at the same message without three separate fixes.
    """

    def _out(self, tmp_path, goal, name):
        return _report(tmp_path, f"""
            -private([art_1_2, meta])

            citation(art_1_2, "Reg-Z Article 1(2)", meta),

            Test("g") <- {goal},
        """, name=name)

    def test_inside_negation(self, tmp_path):
        out = self._out(tmp_path, "(not citation(REF, META))", "argneg.clausal")
        assert "takes 3 arguments" in out

    def test_inside_findall(self, tmp_path):
        out = self._out(tmp_path, "findall(R, citation(R, M), L)",
                        "argfa.clausal")
        assert "takes 3 arguments" in out

    def test_via_call_n(self, tmp_path):
        """``call/N`` resolves the goal at runtime, inside the builtin."""
        out = self._out(tmp_path, "call(citation, REF, META)",
                        "argcall.clausal")
        assert "takes 3 arguments" in out
        assert "positional argument" not in out


class TestHigherOrderFamily:
    """The ``higher_order.py`` meta-call family names the arity it calls at.

    See ``todo/done/higher-order-meta-call-wrong-arity.md``.  Unlike ``call/N``,
    where the source spells the argument count, each of these builtins has its
    own contract for how many arguments the goal receives — the element alone,
    element plus an output/key/truth slot, or element plus both accumulators —
    so each site passes its *own* count, and these tests pin every count
    against the same /3 predicate (or a /2 one where 3 is the count under
    test).  A wrong count here would refuse working code, which is what the
    correct-arity guards below are for.
    """

    def _out(self, tmp_path, goal, name):
        return _report(tmp_path, f"""
            -private([art_1_2, meta])

            citation(art_1_2, "Reg-Z Article 1(2)", meta),
            citepair(art_1_2, meta),

            Test("g") <- {goal},
        """, name=name)

    # The goal receives the element and nothing else.
    @pytest.mark.parametrize("goal", [
        "maplist(citation, [art_1_2])",
        "include(citation, [art_1_2], KEPT)",
        "exclude(citation, [art_1_2], KEPT)",
        "partition(citation, [art_1_2], YES, NO)",
        "take_while(citation, [art_1_2], PREFIX)",
        "drop_while(citation, [art_1_2], SUFFIX)",
        "span(citation, [art_1_2], YES, NO)",
    ])
    def test_element_only_family_passes_1(self, tmp_path, goal):
        out = self._out(tmp_path, goal, f"argho1_{goal.split('(')[0]}.clausal")
        assert "citation takes 3 arguments, but this call passes 1" in out
        assert "positional argument" not in out
        assert "citation__3" not in out

    # The goal receives the element plus one output/key/truth-value slot.
    @pytest.mark.parametrize("goal", [
        "maplist(citation, [art_1_2], YS)",
        "group_by(citation, [art_1_2], GROUPS)",
        "sort_by(citation, [art_1_2], SORTED)",
        "max_by(citation, [art_1_2], MAX)",
        "min_by(citation, [art_1_2], MIN)",
        "filter_map(citation, [art_1_2], OUT)",
        "tfilter(citation, [art_1_2], KEPT)",
        "tpartition(citation, [art_1_2], YES, NO)",
    ])
    def test_element_and_slot_family_passes_2(self, tmp_path, goal):
        out = self._out(tmp_path, goal, f"argho2_{goal.split('(')[0]}.clausal")
        assert "citation takes 3 arguments, but this call passes 2" in out
        assert "positional argument" not in out
        assert "citation__3" not in out

    def test_foldl_passes_3(self, tmp_path):
        """Element plus both accumulators — /3 agrees, so a /2 callee pins it."""
        out = self._out(tmp_path, "foldl(citepair, [art_1_2], V0, V)",
                        "argho3_foldl.clausal")
        assert "citepair takes 2 arguments, but this call passes 3" in out
        assert "positional argument" not in out

    # ── correct-arity guards: one per count, since a wrong count refuses ──

    def test_element_only_at_its_arity_still_runs(self, tmp_path):
        # cite_one/1 is not in the shared preamble; run a dedicated source.
        out = _report(tmp_path, """
            -private([art_1_2])

            cite_one(art_1_2),

            Test("ok1") <- maplist(cite_one, [art_1_2]),
        """, name="arghook1.clausal")
        assert "PASSED" in out

    def test_element_and_slot_at_its_arity_still_runs(self, tmp_path):
        out = self._out(tmp_path, "sort_by(citepair, [art_1_2], SORTED)",
                        "arghook2.clausal")
        assert "PASSED" in out

    def test_foldl_at_its_arity_still_runs(self, tmp_path):
        out = self._out(tmp_path, "foldl(citation, [art_1_2], LABEL, V)",
                        "arghook3.clausal")
        assert "PASSED" in out


class TestImportedPredicate:
    """-import_from binds the exporter's class, so the name IS in scope."""

    def _error(self):
        from clausal.import_hook import _load_module
        from clausal.logic.solve import call
        from clausal.logic.variables import Var
        mod = _load_module("_arimp_use",
                           os.path.join(FIXTURES, "arimp_use.clausal"))
        # The CLASS is pinned, not just TypeError: a plain TypeError here is
        # exactly what the bug was.
        with pytest.raises(PredicateArityMismatchError) as exc:
            list(call("arimp_uses", Var(), module=mod.__dict__["$module"]))
        return str(exc.value)

    def test_names_the_arity(self):
        assert "arimp_pair takes 2 arguments" in self._error()

    def test_points_across_the_module_boundary(self):
        assert "arimp_lib.clausal:" in self._error()


# ── the unit-level message builder ───────────────────────────────────────────


class TestDescribe:

    def test_never_raises_on_junk(self):
        # A diagnostic that fails must degrade, not replace one failure with
        # another.  (This one leaves by the not-an-int early return, above the
        # try — the fallback itself is covered below.)
        assert describe_arity_mismatch("f", 2, None, object())

    def test_falls_back_to_the_head_line_when_the_site_will_not_render(self):
        """The ``except Exception`` fallback, actually exercised.

        Reachable, so kept: *site* is whatever ``_registered_at`` holds, it is
        interpolated into the site sentence, and interpolation runs the object's
        ``__str__``.  A 2-tuple whose elements raise there loses the site line
        and keeps the sentence that carries the fault.
        """
        class Unrenderable:
            def __str__(self):
                raise RuntimeError("a diagnostic must survive this")
            __repr__ = __str__

        msg = describe_arity_mismatch("citation", 2, 3, (Unrenderable(), 14))
        assert msg == "citation takes 3 arguments, but this call passes 2"

    def test_mentions_the_site_when_known(self):
        msg = describe_arity_mismatch("citation", 2, 3, ("t.clausal", 3))
        assert "t.clausal:3" in msg

    def test_omits_the_site_when_unknown(self):
        msg = describe_arity_mismatch("citation", 2, 3, None)
        assert "<unknown>" not in msg
        assert "takes 3 arguments" in msg

    def test_singular_argument(self):
        assert "1 argument," in describe_arity_mismatch("f", 3, 1)


class TestExceptionType:

    def test_is_a_type_error(self):
        """It was a TypeError before; anything catching that keeps working."""
        assert issubclass(PredicateArityMismatchError, TypeError)

    def test_the_raise_is_that_class(self):
        """A static ``issubclass`` pins nothing about what is raised.

        With only that assertion, making ``predicate_arity_mismatch`` return a
        plain ``TypeError(msg)`` — the failure this fix exists to replace —
        passed the whole file.
        """
        pair = make_predicate("arcm_typed", ["k", "v"])
        pair._clauses.append(Clause(head=pair(1, 2), body=[]))
        with pytest.raises(PredicateArityMismatchError):
            pair._get_dispatch(1)

    def test_caught_as_a_type_error_at_the_raise_site(self):
        pair = make_predicate("arcm_typed_te", ["k", "v"])
        pair._clauses.append(Clause(head=pair(1, 2), body=[]))
        with pytest.raises(TypeError):
            pair._get_dispatch(3)


# ── false positives: a Call in a body is not necessarily a goal ──────────────


class TestTermConstructionUnaffected:

    def test_partial_kwargs_functor(self):
        """``vec(x=1)`` builds a *term* — arity 1 against a /2 class."""
        assert main([os.path.join(FIXTURES, "builtins_keywords.clausal")]) == 0

    def test_partial_term_in_argument_position(self, tmp_path):
        """``citation(REF)`` as an *argument* — arity 1 against a /3 predicate.

        This is the shape a DCG nonterminal handed to ``phrase/3`` takes after
        translation (``phrase(count_leaves(T), [0], [N])`` names a /3
        nonterminal at /1); ``tests/test_dcg.py`` covers that instance.
        """
        out = _report(tmp_path, """
            -private([art_1_2, meta])

            citation(art_1_2, "Reg-Z Article 1(2)", meta),
            arcm_shape(REF, N) <- functor(citation(REF), N, _),

            Test("partial term") <- (arcm_shape(art_1_2, N), N == "citation"),
        """)
        assert "PASSED" in out

    def test_atom_vocabulary_then_predicate_local_name_call(self):
        """A 0-arity imported atom re-minted as a /2 predicate (Phenomenon A).

        P3-1 Task 2 fix round 1 (controller ruling, 2026-09-04): atoms are
        plain strs post-pivot (§1b/R2), so there is no shared CLASS object
        any more whose stale ``_arity``/live ``_clause_arity()`` the old
        ``_get_dispatch`` confirmation reconciled — that mechanism was
        class-identity machinery this pivot retires.  What survives: the
        re-defined predicate is fully registered and callable by its bare
        LOCAL name.  See ``tests/test_functor_import_ordering.py``'s
        ``TestZeroArityAtomThenPredicate`` for the matching (a)/(b) split and
        the dotted-owner-path clean-error half.
        """
        use = load_clausal_module(
            os.path.join(FIXTURES, "impord_atom_then_pred.clausal"))
        lm = use.__dict__["$module"]
        k, v = Var(), Var()
        results = sorted(
            (walk(deref(k)), walk(deref(v)))
            for _ in call("impord_qd", k, v, module=lm)
        )
        assert results == [("a", 1), ("b", 2)]

    def test_atom_vocabulary_then_predicate_applied_form_answers(self):
        """(b) half of the same shape: ``impord_atp_lookup``'s body applies
        ``impord_qd`` at arity 2.

        P3-3 Task 5b (controller ruling, 2026-09-06) SUPERSEDES the P3-1 Task
        2 half this used to pin (a clean ``existence_error`` on the owner's
        str atom).  Resolution is keyed on ``(name, arity)``: the imported
        atom has no arity-2 meaning, this file defines ``impord_qd/2``, so
        the applied form is the LOCAL predicate and the goal answers.  The
        deferred "routing to the local predicate is P3-3's job" that ruling
        recorded is this.
        """
        use = load_clausal_module(
            os.path.join(FIXTURES, "impord_atom_then_pred.clausal"))
        lm = use.__dict__["$module"]
        k, v = Var(), Var()
        results = sorted(
            (walk(deref(k)), walk(deref(v)))
            for _ in call("impord_atp_lookup", k, v, module=lm)
        )
        assert results == [("a", 1), ("b", 2)]


class TestCorrectCallsUnaffected:

    def test_right_arity_still_runs(self, tmp_path):
        out = _report(tmp_path, """
            -private([art_1_2, meta])

            citation(art_1_2, "Reg-Z Article 1(2)", meta),

            Test("ok") <- citation(REF, LABEL, META),
        """)
        assert "PASSED" in out


# ── the protocol the diagnostic is not allowed to widen ──────────────────────


class TestForeignSingleArgumentImplementor:
    """``_get_dispatch()`` is duck-typed, and it stays single-argument.

    Roughly two dozen implementors live outside this tree, in ``packages/``.
    ``clausal-scipy``'s ``_LookupPredicate``, ``clausal-spacy``'s
    ``_SpacyPredicate`` and ``clausal-provenance``'s ``_RegistrationGoal``
    inherit from *nothing*: they are plain classes whose whole contract is
    ``def _get_dispatch(self)``.  The first version of this diagnostic taught
    the goal emitters to write ``fname._get_dispatch(N)``, and every one of
    those packages then died on a *correct*-arity call with

        TypeError: _get_dispatch() takes 1 positional argument but 2 were given

    Nothing in the suite noticed, because nothing in the suite called a foreign
    implementor from a compiled goal.  These tests are that missing coverage.
    """

    def test_callable_at_its_correct_arity_from_a_clause_body(self):
        """The end-to-end shape: a .clausal goal calling a plain-class goal."""
        from clausal.import_hook import _load_module
        from clausal.logic.solve import call
        from clausal.logic.variables import Var, deref
        mod = _load_module("_fordisp_use",
                           os.path.join(FIXTURES, "foreign_dispatch_use.clausal"))
        v = Var()
        # Bindings are live on the yielded trail, not after it is undone.
        bound = [deref(v) for _ in call("fordisp_lookup", "b", v,
                                       module=mod.__dict__["$module"])]
        assert bound == [2], (
            "a correct-arity call to a foreign implementor must succeed; "
            f"got {bound!r}"
        )

    def test_the_emitters_do_not_pass_it_an_arity(self):
        """Pin the protocol directly, not just one caller's use of it.

        A class that accepts *no* second argument at all — no ``arity=None``
        escape hatch — has to remain a usable goal target.  If a future change
        re-widens the protocol this fails with the exact ecosystem-breaking
        ``TypeError`` rather than with something vaguer.
        """
        from clausal.logic.compiler import compile_predicate_trampoline
        from clausal.logic.database import Database
        from clausal.logic.trampoline import DONE, StepGenerator
        from clausal.logic.variables import Trail, Var, deref
        from clausal.terms import Call as TCall, Compound, LoadName
        from tests.fixtures.foreign_dispatch_impl import foreign_pair

        # No inherited _get_dispatch anywhere on the MRO to soften the blow.
        assert type(foreign_pair)._get_dispatch.__code__.co_argcount == 1

        k, v = Var(), Var()
        clauses = [Clause(
            head=Compound("fordisp_body", (k, v)),
            body=[TCall(func=LoadName(name="foreign_pair"),
                        args=[k, v], kwargs=[])],
        )]
        fn = compile_predicate_trampoline(
            "fordisp_body", 2, clauses, db=Database(),
            globals_={"foreign_pair": foreign_pair},
        )
        trail = Trail()
        out = Var()
        sg = StepGenerator(fn, None, None, None, "a", out, trail)
        gen, value = sg.send(None)
        while gen is not None:
            gen, value = gen.send(value)
        assert value is not DONE, "the foreign goal must have produced a solution"
        assert deref(out) == 1

    def test_dispatch_at_routes_by_type_not_by_hasattr(self):
        """``_dispatch_at`` is the only place that knows which protocol to use."""
        from clausal.logic.predicate import _dispatch_at
        from tests.fixtures.foreign_dispatch_impl import (
            _foreign_pair_dispatch, foreign_pair,
        )
        # A foreign implementor: the arity is dropped, never forwarded.
        assert _dispatch_at(foreign_pair, 2) is _foreign_pair_dispatch
        assert _dispatch_at(foreign_pair, 99) is _foreign_pair_dispatch
        # A PredicateMeta: the arity is forwarded and a disagreement refused.
        pair = make_predicate("arcm_routed", ["k", "v"])
        pair._clauses.append(Clause(head=pair(1, 2), body=[]))
        with pair._mutate("test", "recompile"):    # the gate, P3-3 Task 3
            pair._dispatch_fn = lambda *a: None
        assert _dispatch_at(pair, 2) is pair._dispatch_fn
        with pytest.raises(PredicateArityMismatchError):
            _dispatch_at(pair, 3)

    def test_only_predicate_meta_takes_an_arity(self):
        """No second implementor may quietly grow an ``arity`` parameter.

        The accept-and-ignore ``arity=None`` signatures the first version added
        to four in-tree adapters were what made the widened protocol look
        official.  One arity-aware implementor, and it is the one with clause
        heads to check against.
        """
        import inspect
        from clausal.logic.builtins._registry import (
            BuiltinPredicate, MultiArityBuiltin,
        )
        from clausal.logic.compiler.globals_env import _DbDispatchAdapter
        from clausal.modules.py import ModulePredicate

        for cls in (BuiltinPredicate, MultiArityBuiltin,
                    _DbDispatchAdapter, ModulePredicate):
            params = inspect.signature(cls._get_dispatch).parameters
            assert list(params) == ["self"], (
                f"{cls.__name__}._get_dispatch must stay single-argument; "
                "the arity belongs in _dispatch_at"
            )


# ── a -dynamic declaration is an arity source clause heads cannot be ─────────


class TestDynamicDeclaredArity:
    """A clause-free ``-dynamic`` predicate refuses on its *declared* arity.

    See ``todo/done/dynamic-declared-arity-not-used-by-the-arity-diagnostic.md``.
    ``_clause_arity`` deliberately distrusts ``_fields`` (stale on the
    re-minted vocabulary atom), but a ``-dynamic(dfact/3)`` directive is a
    *declaration* — it cannot be a stale inference — so it is stamped on the
    class (``_dynamic_arities``) at load and consulted only when the clause
    list is EMPTY: never when the first head already agreed with the call,
    and never on the clause-carrying shapes ``_clause_arity`` was built for.
    """

    def test_clause_free_dynamic_names_the_declared_arity(self, tmp_path):
        """The todo's repro, verbatim in spirit."""
        out = _report(tmp_path, """
            -dynamic(dfact/3)

            Test("dyn wrong arity") <- dfact(_A, _B),
        """, name="argdyn.clausal")
        assert "dfact takes 3 arguments, but this call passes 2" in out
        assert "positional argument" not in out
        assert "dfact__3" not in out

    def test_correct_arity_still_fails_cleanly_with_no_clauses(self, tmp_path):
        """Declare-then-assertz: a pre-assertz call at /3 is 0 solutions."""
        out = _report(tmp_path, """
            -dynamic(dfact/3)

            Test("dyn empty") <- dfact(_A, _B, _C),
        """, name="argdynok.clausal")
        assert "TypeError" not in out
        assert "takes 3 arguments" not in out     # failed, not refused
        assert "1 failed" in out

    def test_clauses_outrank_the_declaration(self, tmp_path):
        """With a clause asserted the head walk answers, same as before."""
        out = _report(tmp_path, """
            -dynamic(dfact/3)

            Test("dyn assertz") <- (assertz(dfact(1, 2, 3)), dfact(_A, _B)),
        """, name="argdynz.clausal")
        assert "dfact takes 3 arguments, but this call passes 2" in out
        assert "positional argument" not in out

    def test_higher_order_position_reports_it_too(self, tmp_path):
        """The meta-call family funnels into the same refusal."""
        out = _report(tmp_path, """
            -dynamic(dfact/3)

            Test("dyn maplist") <- maplist(dfact, [1]),
        """, name="argdynho.clausal")
        assert "dfact takes 3 arguments, but this call passes 1" in out
        assert "positional argument" not in out

    def test_retracting_back_to_empty_keeps_the_declaration(self):
        """assertz → retract → the declared arity still refuses."""
        pair = make_predicate("arcm_dynpair", ["k", "v", "w"])
        moving = make_predicate("arcm_dyndecl", ["a", "b", "c"])
        moving._dynamic_arities = {3}
        with pytest.raises(PredicateArityMismatchError):
            moving._refuse_call_at(2)
        moving._assertz(Clause(head=pair(1, 2, 3), body=[]))
        with pytest.raises(PredicateArityMismatchError):
            moving._refuse_call_at(2)            # via the heads now
        assert moving._retract(pair(1, 2, 3)) is True
        with pytest.raises(PredicateArityMismatchError) as exc:
            moving._refuse_call_at(2)            # via the declaration again
        assert "takes 3 arguments, but this call passes 2" in str(exc.value)

    def test_two_declared_arities_decline(self):
        """One number in the message means one declared arity, or nothing.

        The multi-arity ``-dynamic`` name has its own dispatch tangle; a
        refusal that guessed which declared arity to blame would be wrong
        half the time, so the fallback declines exactly like an unreadable
        head shape does.
        """
        both = make_predicate("arcm_dynboth", ["a", "b", "c"])
        both._dynamic_arities = {2, 3}
        both._refuse_call_at(4)                  # must not raise
        both._refuse_call_at(1)

    def test_a_declared_arity_is_never_itself_refused(self):
        one = make_predicate("arcm_dynself", ["a", "b", "c"])
        one._dynamic_arities = {2}               # declaration disagrees with
        one._refuse_call_at(2)                   # _fields: the call wins

    def test_a_declaration_for_a_differently_shaped_class_declines(self):
        """The stamp can land on a same-named class of another arity.

        ``-dynamic(f/3)`` in a module that imported a 0-arity vocabulary
        atom ``f`` stamps {3} onto a class whose authored shape is /0.  Two
        authored sources disagree, so refusing with either number would be
        confidently wrong half the time — the fallback declines instead
        (roborev job 9).  ``_fields`` acts only as a VETO here, never as
        the arity source, so the stale-``_fields`` hazard cannot return.
        """
        atom = make_predicate("arcm_dynatom", [])         # authored at /0
        atom._dynamic_arities = {3}              # declared at /3
        atom._refuse_call_at(1)                  # must not raise
        pair = make_predicate("arcm_dynpair2", ["k", "v"])
        pair._dynamic_arities = {3}              # /2 class, /3 declaration
        pair._refuse_call_at(1)                  # must not raise

    def test_undeclared_stays_declined(self):
        """The default is ``None`` — every pre-existing decline is untouched."""
        plain = make_predicate("arcm_dynnone", ["a", "b", "c"])
        assert plain._dynamic_arities is None
        plain._refuse_call_at(2)                 # must not raise


# ── the two runtime funnels that know their own arity ────────────────────────


class TestRuntimeFunnels:
    """``time_goal/1`` and ``phrase/2,3`` resolve their goal at runtime.

    Both were still printing the old ``citation__3() missing 3 required
    positional arguments`` after the compiled goal positions were fixed, and
    both know exactly how many arguments they are about to supply — unlike the
    ``higher_order.py`` family, which was filed separately in
    ``todo/done/higher-order-meta-call-wrong-arity.md`` (now fixed — see
    ``TestHigherOrderFamily``) precisely because it does not.
    """

    def test_time_goal_names_the_arity(self, tmp_path):
        """``time_goal(citation)`` calls the goal with no arguments at all."""
        out = _report(tmp_path, """
            -private([art_1_2, meta])

            citation(art_1_2, "Reg-Z Article 1(2)", meta),

            Test("timed") <- time_goal(citation),
        """, "arcmtime.clausal")
        assert "citation takes 3 arguments" in out
        assert "passes 0" in out
        assert "positional argument" not in out

    def test_phrase_counts_the_difference_list_pair(self, tmp_path):
        """A nonterminal's arity is its written arity *plus* S0 and S.

        ``phrase(nt, L)`` calls ``nt`` at 2, so a /5 name refused here has to
        be told it passed 2 — not 0, which is what the source says.
        """
        out = _report(tmp_path, """
            arcmp_five(A, B, C, S0, S) <- (S0 == S),

            Test("phrased") <- phrase(arcmp_five, [], []),
        """, "arcmphrase.clausal")
        assert "arcmp_five takes 5 arguments" in out
        assert "passes 2" in out
        assert "positional argument" not in out

    def test_a_real_nonterminal_still_runs(self, tmp_path):
        """The guard: ``phrase`` on a genuine DCG rule is untouched.

        ``greeting//0`` is written at 0 and called at 2; counting the pair is
        the whole reason that is not reported as a mismatch.
        """
        out = _report(tmp_path, """
            greeting >> (["hello", "world"])

            Test("greets") <- phrase(greeting, ["hello", "world"]),
        """, "arcmdcg.clausal")
        assert "PASSED" in out


# ── the cost of the clause walk ──────────────────────────────────────────────


class _CountingClause:
    """A clause that records how many times its ``head`` was read."""

    __slots__ = ("_head", "reads")

    def __init__(self, head):
        self._head = head
        self.reads = 0

    @property
    def head(self):
        self.reads += 1
        return self._head


def _stale_predicate(name, n_clauses):
    """A predicate shaped the way a downstream rulebase's are: ``_arity`` 0,
    heads at /2.

    Real code gets here by importing a 0-arity vocabulary atom and then
    defining a same-named predicate; ``TestTermConstructionUnaffected.
    test_atom_vocabulary_then_predicate_local_name_call`` (and its dotted-path
    sibling ``..._dotted_path_raises_cleanly``) pin that
    ``tests/fixtures/impord_atom_then_pred.clausal`` really is that shape
    (split in two by the P3-1 Task 2 fix round 1 ruling -- see
    ``task-2-report.md``; this helper's hand-built stale-arity shape is
    orthogonal to that ruling, since it builds a live ``PredicateMeta`` atom
    directly via ``make_predicate(name, [])``, never a str).
    Built by hand here so the clause count can be a fact table's, and so no
    shared fixture class is mutated.
    """
    pair = make_predicate(name + "_pair", ["k", "v"])
    stale = make_predicate(name, [])
    stale._clauses.extend(_CountingClause(pair(i, i)) for i in range(n_clauses))
    assert stale._arity == 0          # stale, permanently
    return stale


class TestTheWalkIsNotPerCall:
    """``arity != len(_fields)`` is permanent for those, so the walk cannot be.

    ``_refuse_call_at`` read every clause head on every invocation of a
    stale-``_arity`` predicate and never refused: 108 µs per call on a 2000-fact
    one against 0.10 µs for an honest ``_arity``, i.e. the whole cost of the
    diagnostic fell on exactly the predicates that made the clause walk
    necessary.  One head is enough — if the first head has the call's arity then
    either all of them do or they disagree, and both answers decline.
    """

    def test_an_agreeing_call_reads_one_head(self):
        stale = _stale_predicate("arcm_hot", 2000)
        stale._refuse_call_at(2)        # the call the corpus makes, every time
        assert sum(c.reads for c in stale._clauses) == 1

    def test_the_cost_does_not_grow_with_the_clause_list(self):
        small = _stale_predicate("arcm_small", 2)
        big = _stale_predicate("arcm_big", 2000)
        small._refuse_call_at(2)
        big._refuse_call_at(2)
        assert (sum(c.reads for c in small._clauses)
                == sum(c.reads for c in big._clauses) == 1)

    def test_a_real_mismatch_is_still_refused(self):
        """The short-circuit must not cost the refusal it is guarding."""
        stale = _stale_predicate("arcm_refused", 50)
        with pytest.raises(PredicateArityMismatchError) as exc:
            stale._refuse_call_at(1)
        assert "takes 2 arguments, but this call passes 1" in str(exc.value)


class TestClauseListChangesAreObeyed:
    """Re-derived, not memoised, so ``assertz``/``retract`` land immediately.

    A cached "2 is acceptable" that outlived its clause list would refuse a call
    that had become correct, or — worse — stay silent about one that had become
    wrong.  ``_clauses`` is mutated in place by ``_assertz``/``_retract`` and
    replaced wholesale by three load-time paths, so the answer is read off the
    heads at every call instead of being remembered.
    """

    def test_assertz_of_another_arity_flips_the_decision(self):
        pair = make_predicate("arcm_dyn_pair", ["k", "v"])
        one = make_predicate("arcm_dyn_one", ["k"])
        moving = make_predicate("arcm_dyn", [])

        moving._assertz(Clause(head=pair(1, 2), body=[]))
        moving._refuse_call_at(2)                    # /2 heads: accepted
        with pytest.raises(PredicateArityMismatchError):
            moving._refuse_call_at(1)

        assert moving._retract(pair(1, 2)) is True
        moving._assertz(Clause(head=one(1), body=[]))
        moving._refuse_call_at(1)                    # /1 heads now: accepted
        with pytest.raises(PredicateArityMismatchError):
            moving._refuse_call_at(2)

    def test_retracting_the_last_clause_stops_refusing(self):
        pair = make_predicate("arcm_empty_pair", ["k", "v"])
        moving = make_predicate("arcm_empty", [])
        moving._assertz(Clause(head=pair(1, 2), body=[]))
        with pytest.raises(PredicateArityMismatchError):
            moving._refuse_call_at(1)
        assert moving._retract(pair(1, 2)) is True
        moving._refuse_call_at(1)   # no clauses: nothing known, nothing refused


# ── head shapes: a diagnostic that can crash is worse than no diagnostic ─────


class TestZeroArityFactAtomHead:
    """``myflag,`` stores the CLASS itself as its clause head.

    ``term_field_names`` raises ``TypeError: must be called with a dataclass
    type or instance`` on a class, so reading the heads crashed with that — on
    one of the exact fault classes this diagnostic exists to describe, and with
    a sentence that names neither arity nor the predicate.
    """

    def test_the_head_is_read_not_crashed(self, tmp_path):
        mod = load_clausal_module(str(write(tmp_path, "arcmflag.clausal", """
            -module(arcmflag, [arcm_flag])

            arcm_flag,
        """)))
        flag = mod.arcm_flag
        assert flag._clauses                    # the bare fact IS a clause
        assert flag._clause_arity() == 0        # used to raise TypeError

    def test_calling_an_atom_fact_at_arity_one(self, tmp_path, monkeypatch):
        """End to end, through the import that makes the name a goal.

        ``arcm_flag(X)`` written in the *same* file as ``arcm_flag,`` is refused
        by the body compiler ("goal shape not yet supported"), so the reachable
        route is the imported one — which is also the corpus's shape for
        vocabulary atoms.
        """
        from clausal.import_hook import _load_module
        from clausal.logic.solve import call
        from clausal.logic.variables import Var

        monkeypatch.syspath_prepend(str(tmp_path))
        write(tmp_path, "arcmflaglib.clausal", """
            -module(arcmflaglib, [arcm_flag])

            arcm_flag,
        """)
        use = write(tmp_path, "arcmflaguse.clausal", """
            -import_from(arcmflaglib, [arcm_flag])

            arcm_flag_use(X) <- arcm_flag(X)
        """)
        mod = _load_module("_arcmflaguse", str(use))
        with pytest.raises(PredicateArityMismatchError) as exc:
            list(call("arcm_flag_use", Var(), module=mod.__dict__["$module"]))
        assert "arcm_flag takes 0 arguments, but this call passes 1" in str(exc.value)
        assert "dataclass" not in str(exc.value)

    def test_calling_a_pure_atom_as_a_goal_across_modules_raises_cleanly(
        self, tmp_path, monkeypatch,
    ):
        """Cross-module analogue of the ``impord_atom_then_pred`` split
        (P3-1 Task 2 fix round 1, controller ruling, 2026-09-04): an atom
        that is declared but NEVER defined as a predicate anywhere (no
        bodyless fact, no clauses -- unlike ``arcm_flag`` above, which
        re-mints into a real predicate class via its own same-file fact) is
        imported into another module and called there as a goal.
        ``_dispatch_at`` (``clausal/logic/predicate.py``) now receives the
        plain str atom directly and must raise a clean, positioned
        ``LogicException``/``existence_error("procedure", ...)`` -- never the
        raw ``AttributeError: 'str' object has no attribute '_get_dispatch'``
        this used to be before the fix.
        """
        from clausal.import_hook import _load_module
        from clausal.logic.exceptions import LogicException
        from clausal.logic.solve import call
        from clausal.logic.variables import Var

        monkeypatch.syspath_prepend(str(tmp_path))
        write(tmp_path, "arcmpurelib.clausal", """
            -module(arcmpurelib, [arcm_pure_tag])

            arcm_pure_marker(arcm_pure_tag),
        """)
        use = write(tmp_path, "arcmpureuse.clausal", """
            -import_from(arcmpurelib, [arcm_pure_tag])

            arcm_pure_use(X) <- arcm_pure_tag(X)
        """)
        mod = _load_module("_arcmpureuse", str(use))
        with pytest.raises(LogicException) as exc_info:
            list(call("arcm_pure_use", Var(), module=mod.__dict__["$module"]))
        term = exc_info.value.term
        indicator = term.args[0].args[1]
        assert str(term.args[0].args[0]) == "procedure"
        assert indicator.functor == "/"
        assert indicator.args == ("arcm_pure_tag", 1)
        assert "not callable at arity 1" in term.args[1]
        assert "AttributeError" not in term.args[1]


class TestCompoundHead:
    """A head with an ``args`` sequence, which is read from ``args``.

    Pinned because reading the class's ``_fields`` first — the fix for the
    0-arity fact atom — put a second branch in front of this one, and because a
    ``Compound`` whose functor is a ``Var`` still has a countable arity even
    though ``database.head_key`` refuses to name it.
    """

    def test_str_functor(self):
        from clausal.terms import Compound
        pred = make_predicate("arcm_compound", [])
        pred._clauses.append(Clause(head=Compound("arcm_compound", (1, 2)),
                                    body=[]))
        assert pred._clause_arity() == 2
        with pytest.raises(PredicateArityMismatchError) as exc:
            pred._refuse_call_at(1)
        assert "takes 2 arguments, but this call passes 1" in str(exc.value)

    def test_var_functor(self):
        from clausal.logic.variables import Var
        from clausal.terms import Compound
        pred = make_predicate("arcm_compound_var", [])
        pred._clauses.append(Clause(head=Compound(Var(), (1, 2, 3)), body=[]))
        assert pred._clause_arity() == 3
        pred._refuse_call_at(3)          # agrees: nothing refused


class TestAHeadShapeNobodyAnticipated:
    """Undefined arity means *nothing is refused*, never *something is raised*."""

    def test_an_unreadable_head_refuses_nothing(self):
        junk = make_predicate("arcm_junk", [])
        junk._clauses.append(Clause(head=object(), body=[]))
        assert junk._clause_arity() is None
        junk._refuse_call_at(3)          # must not raise at all

    def test_one_unreadable_head_makes_the_whole_arity_unknown(self):
        pair = make_predicate("arcm_mixed_pair", ["k", "v"])
        mixed = make_predicate("arcm_mixed", [])
        mixed._clauses.append(Clause(head=pair(1, 2), body=[]))
        mixed._clauses.append(Clause(head=object(), body=[]))
        assert mixed._clause_arity() is None
        mixed._refuse_call_at(1)         # refusable on the first head alone

    def test_a_clause_list_that_explodes_refuses_nothing(self):
        """``_refuse_call_at`` raises ``PredicateArityMismatchError`` or nothing.

        Not the RuntimeError from here, and not a ``TypeError`` from a head shape
        the walk did not expect.
        """
        class Exploding:
            @property
            def head(self):
                raise RuntimeError("a diagnostic must survive this")

        boom = make_predicate("arcm_boom", [])
        boom._clauses.append(Exploding())
        boom._refuse_call_at(2)


# ── what the docs may claim ──────────────────────────────────────────────────


class TestTwoAritiesInOneFile:
    """``docs/predicates.md`` used to say these stay unrelated.  They do not —
    and since ``todo/done/same-name-two-arities-silently-merge.md`` BOTH
    orders are load errors, so neither can silently rewrite the program.
    The runtime remedy line still must not send the reader to write the
    second arity, because one name has one arity whichever way they try.
    """

    def test_the_longer_head_then_the_shorter_is_a_load_error(self, tmp_path):
        """FLIPPED: this used to pin the silent absorption (the shorter head
        padded to ``citation(REF, META, _)``) plus the accurate-but-confusing
        runtime refusal that followed.  The absorption is now refused at
        load, in the same run the test file's report captures."""
        out = _report(tmp_path, """
            -private([art_1_2, meta])

            citation(art_1_2, "Reg-Z Article 1(2)", meta),
            citation(art_1_2, meta),

            Test("citation record resolves") <- citation(REF, METADATA),
        """, name="argremedy.clausal")
        assert "citation/2 conflicts" in out
        assert "citation/3" in out
        assert "not a partial term" in out

    def test_the_shorter_head_first_is_a_load_error(self, tmp_path):
        out = _report(tmp_path, """
            -private([art_1_2, meta])

            citation(art_1_2, meta),
            citation(art_1_2, "Reg-Z Article 1(2)", meta),
        """, name="argorder.clausal")
        assert "conflicts with the declaration of citation/2" in out
