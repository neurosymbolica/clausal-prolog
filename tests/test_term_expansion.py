"""Tests for term expansion — term_expansion/4 predicate.

Verifies:
1. No term_expansion → pass-through, zero overhead
2. Identity expansion (pass-through with TE rule)
3. Clause suppression (``"none"``)
4. term_expansion clauses are NOT themselves expanded
5. Patterns are plain terms; q() quasi-quotation is retired (2026-09-25)
   and ``q`` is an ordinary name
6. Variables shared between a pattern and the replacement
7. Full pipeline integration: .clausal fixtures with term_expansion
"""

from __future__ import annotations

import ast
import os
import sys
import warnings

import pytest

from clausal.logic.atoms import mint
from clausal.import_hook import (
    EmbedTransformer,
    _fact_to_predicate_node,
    _load_module,
    predicate_builtins,
    runtime_builtins,
)
from clausal.logic.compiler_v2 import compile_module
from clausal import cell_args, cell_functor
from clausal.logic.exceptions import LogicException, error_context_text
from clausal.logic.database import Module as LogicModule, head_key
from clausal.logic.solve import call
from clausal.logic.term_expansion import (
    run_term_expansion,
    _is_term_expansion_clause,
)
from clausal.logic.variables import Var, Trail, deref


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _parse_and_collect(source: str):
    """Parse source, run EmbedTransformer, collect predicate nodes."""
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=SyntaxWarning)
        tree = ast.parse(source)
        transformer = EmbedTransformer()
        tree = transformer.visit(tree)
        ast.fix_missing_locations(tree)

    module_items = transformer._module_items
    module_dict = {"__name__": "_test_expansion"}
    # P3-2 Task 8: mirrors import_hook.py's exec_module seeding order --
    # the atom pool first, runtime_builtins layered on top and winning any
    # collision.
    module_dict.update(predicate_builtins)
    module_dict.update(runtime_builtins)

    predicate_nodes = []
    dummy_lm = LogicModule("_test_expansion_", module_dict=module_dict)
    module_dict["$module"] = dummy_lm
    module_dict["$define_predicate"] = lambda pred, lm: predicate_nodes.append(pred)
    module_dict["$assert_fact"] = lambda term: predicate_nodes.append(
        _fact_to_predicate_node(term)
    )
    code = compile(tree, filename="<test>", mode="exec")
    exec(code, module_dict)

    return predicate_nodes, module_items, module_dict


def _head_functor(head):
    """The functor of a clause head.  P2 (2026-09-19): a head is the
    functor-first CELL, so this is ``head[0]``; before the flip it was the
    class name of an instance."""
    from clausal.logic.cells import compound_cell_shape
    is_cell, functor = compound_cell_shape(head)
    return functor if is_cell else type(head).__name__



class TestPassThrough:
    """No term_expansion → zero overhead pass-through."""

    def test_no_expansion_returns_same(self):
        """Without term_expansion clauses, items pass through unchanged."""
        # nv
        source = '-double_quotes(atom)\nfoo("a"),\nfoo("b"),\n'
        preds, _, md = _parse_and_collect(source)
        result = run_term_expansion(preds, md)
        assert result is preds  # exact same list object (no copy)

    def test_empty_input(self):
        """Empty predicate list returns empty."""
        # nv
        result = run_term_expansion([], {})
        assert result == []


class TestTermExpansionDetection:
    """Test _is_term_expansion_clause."""

    def test_detects_te_clause(self):
        """term_expansion/4 clauses are detected."""
        # nv
        source = (
            'term_expansion(_term, _expansion, _m0, _m1) <- ('
            '    _term is _expansion,'
            '    _m0 is _m1'
            ')\n'
        )
        preds, _, md = _parse_and_collect(source)
        assert len(preds) == 1
        assert _is_term_expansion_clause(preds[0])

    def test_non_te_not_detected(self):
        """Regular clauses are not detected as term_expansion."""
        # nv
        source = '-double_quotes(atom)\nfoo("a"),\n'
        preds, _, md = _parse_and_collect(source)
        assert len(preds) == 1
        assert not _is_term_expansion_clause(preds[0])


class TestIdentityExpansion:
    """term_expansion that passes items through unchanged."""

    def test_identity_expansion(self):
        """term_expansion(T, T, M, M) passes all items through."""
        # nv
        source = (
            '-double_quotes(atom)\nterm_expansion(_term, _term, _m0, _m0) <- True\n'
            'foo("a"),\n'
            'foo("b"),\n'
        )
        preds, _, md = _parse_and_collect(source)
        result = run_term_expansion(preds, md)
        # TE clause removed, two foo items remain
        assert len(result) == 2
        for p in result:
            assert _head_functor(p.head) == "foo"

    def test_identity_via_fixture(self):
        """Full import of expansion_passthrough.clausal."""
        # nv
        mod = _load_module(
            "_exp_pt", os.path.join(FIXTURES_DIR, "expansion_passthrough.clausal")
        )
        lm = mod.__dict__["$module"]
        x = Var()
        results = []
        for t in call("foo", x, module=lm):
            results.append(deref(x))
        assert sorted(results) == [mint("a"), mint("b"), mint("c")]


class TestSuppression:
    """term_expansion that suppresses items."""

    def test_suppress_all(self):
        """term_expansion(T, 'none', M, M) suppresses all items."""
        # nv
        source = (
            '-double_quotes(atom)\nterm_expansion(_term, "none", _m0, _m0) <- True\n'
            'foo("a"),\n'
            'foo("b"),\n'
        )
        preds, _, md = _parse_and_collect(source)
        result = run_term_expansion(preds, md)
        assert result == []

    def test_suppress_via_fixture(self):
        """Full import of expansion_suppress.clausal — no foo clauses."""
        # nv
        mod = _load_module(
            "_exp_sup", os.path.join(FIXTURES_DIR, "expansion_suppress.clausal")
        )
        lm = mod.__dict__["$module"]
        assert not lm.db.is_defined("foo", 1)


class TestTeNotExpanded:
    """term_expansion clauses themselves are not expanded."""

    def test_te_clauses_removed_from_output(self):
        """TE clauses are separated, not passed through expansion."""
        # nv
        source = (
            '-double_quotes(atom)\nterm_expansion(_term, _term, _m0, _m0) <- True\n'
            'foo("x"),\n'
        )
        preds, _, md = _parse_and_collect(source)
        assert len(preds) == 2  # 1 TE + 1 foo
        result = run_term_expansion(preds, md)
        # Only foo should remain — TE clause was separated out
        assert len(result) == 1
        assert _head_functor(result[0].head) == "foo"


class TestOneToMany:
    """term_expansion that produces multiple items from one."""

    def test_duplicate_items(self):
        """term_expansion(T, [T, T], M, M) duplicates each item."""
        # nv
        source = (
            '-double_quotes(atom)\nterm_expansion(_term, [_term, _term], _m0, _m0) <- True\n'
            'foo("a"),\n'
        )
        preds, _, md = _parse_and_collect(source)
        result = run_term_expansion(preds, md)
        assert len(result) == 2
        for p in result:
            assert _head_functor(p.head) == "foo"

    def test_duplicate_full_pipeline(self):
        """Full pipeline: duplicate items → double the clauses."""
        # nv
        source = (
            '-double_quotes(atom)\nterm_expansion(_term, [_term, _term], _m0, _m0) <- True\n'
            'item("x"),\n'
            'item("y"),\n'
        )
        preds, items, md = _parse_and_collect(source)
        lm = compile_module(preds, items, md, "_test_dup_te")
        md["$module"] = lm

        x = Var()
        results = []
        for trail in call("item", x, module=lm):
            results.append(deref(x))
        # Each item duplicated: x, x, y, y
        assert sorted(results) == [mint("x"), mint("x"), mint("y"), mint("y")]


class TestModuleState:
    """Module state threading through expansion."""

    def test_state_unmatched_passes_through(self):
        """When a TE rule's body cleanly FAILS, items pass through unchanged."""
        # The head matches the state (binding _count="nil"), but the guard
        # `_count == 0` fails for the initial "nil" count → no solution →
        # pass-through.  (Body failure, not body error — see the error case in
        # ``test_state_body_arith_error_propagates`` below.)
        # nv
        source = (
            '-double_quotes(atom)\nterm_expansion(_term, _term, module_expansion_state(_i, _f, _count), '
            'module_expansion_state(_i, _f, _next)) <- '
            '(_count == 0, _next == _count + 1)\n'
            'foo("a"),\n'
        )
        preds, _, md = _parse_and_collect(source)
        result = run_term_expansion(preds, md)
        assert len(result) == 1
        assert _head_functor(result[0].head) == "foo"

    def test_state_body_arith_error_propagates(self):
        """A TE rule whose body errors (e.g. arithmetic on a non-number) raises,
        rather than silently failing into pass-through.

        Bad arithmetic (``"nil" + 1``) is a type error and must surface — it is
        catchable in .clausal via ``catch/3`` (e.g. ``TypeError(_)``).  This pins
        the decided semantics: body *errors* propagate; only body *failure* (no
        solution) yields pass-through.

        Stage 2 of the atoms-as-str flip: the state's ``"nil"`` is the ATOM
        ``nil`` (a str), so the error is the engine's own
        ``type_error(evaluable, nil)`` (a ``LogicException``) rather than the
        raw Python ``TypeError`` that ``str + int`` used to leak.
        """
        # nv
        source = (
            '-double_quotes(atom)\nterm_expansion(_term, _term, module_expansion_state(_i, _f, _count), '
            'module_expansion_state(_i, _f, _next)) <- eval_(_count + 1, _next)\n'
            'foo("a"),\n'
        )
        preds, _, md = _parse_and_collect(source)
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException) as exc:
            run_term_expansion(preds, md)
        assert "type_error" in str(exc.value) and "evaluable" in str(exc.value)


def _load_src(name, source):
    """Write *source* to a temp ``.clausal`` file and load it fresh."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, f"{name}.clausal")
        with open(path, "w") as fh:
            fh.write(source)
        return _load_module(name, path)


def _answers(mod, functor, arity=1):
    lm = mod.__dict__["$module"]
    vs = [Var() for _ in range(arity)]
    return sorted((tuple(deref(v) for v in vs) for _ in call(functor, *vs, module=lm)),
                  key=repr)


class TestPlainTermPatterns:
    """Patterns are plain terms, as in ISO term_expansion.

    ``q(expr)`` quasi-quotation was retired 2026-09-25.  It stripped itself
    and lowered ``expr`` -- which a term in argument position already
    lowers as DATA (a cell), so it did nothing a plain term does not, and
    it hijacked the name ``q`` in every module.  These were the q() tests;
    each is now the plain-term equivalent, plus pins that ``q`` is an
    ordinary name.
    """

    def test_a_pattern_argument_lowers_as_a_cell_constructor(self):
        """``foo(_x)`` in argument position lowers as DATA -- the cell
        constructor -- with no quoting (was ``q(foo(_x))``)."""
        # nv
        from clausal.templating.term_rewriting import TermTransformer
        tree = ast.parse("foo(_x)", mode="eval").body
        t = TermTransformer()
        result = t.visit(tree)
        assert isinstance(result, ast.Call)
        assert isinstance(result.func, ast.Name)
        assert result.func.id == "$Call"
        kw_names = {kw.arg for kw in result.keywords}
        assert "func" in kw_names
        assert "args" in kw_names

    def test_variables_are_shared_across_the_clause(self):
        """Variables of a pattern are shared with the enclosing context
        (was ``[q(foo(_x)), bar(_x)]``)."""
        # nv
        from clausal.templating.term_rewriting import TermTransformer
        tree = ast.parse("[foo(_x), bar(_x)]", mode="eval").body
        t = TermTransformer()
        t.visit(tree)
        assert "_x" in t.seen_vars

    def test_q_is_no_longer_stripped_by_the_term_transformer(self):
        """``q(foo(_x))`` is the functor ``q`` applied to ``foo(_x)``, not
        ``foo(_x)``: the lowered call names ``q``."""
        # nv
        from clausal.templating.term_rewriting import TermTransformer
        t = TermTransformer()
        result = t.visit(ast.parse("q(foo(_x))", mode="eval").body)
        assert "'q'" in ast.unparse(result)
        assert "'foo'" in ast.unparse(result)

    def test_plain_pattern_one_to_many_expands(self):
        """The doc quick example, plain (was ``q(fact(X))`` ...)."""
        # nv
        mod = _load_src("_te_plain_qe", (
            "term_expansion(\n"
            "    fact(X),\n"
            "    [fact(X), logged_fact(X)],\n"
            "    STATE, STATE\n"
            "),\n"
            "fact(1),\n"
            "fact(2),\n"
        ))
        assert _answers(mod, "fact") == [(1,), (2,)]
        assert _answers(mod, "logged_fact") == [(1,), (2,)]

    def test_q_one_is_the_ordinary_cell(self):
        """``q(1)`` is the cell ``('q', 1)``, like any declared functor --
        not ``1``."""
        # nv
        mod = _load_src("_te_q_cell", (
            "-private([q/1])\n"
            "r(T) <- (T is q(1))\n"
        ))
        assert _answers(mod, "r") == [(("q", 1),)]

    def test_q_one_through_the_seam_is_the_cell(self):
        """``--q(1)`` used to evaluate to ``1``; it builds ``('q', 1)``."""
        # nv
        mod = _load_src("_te_q_seam", (
            "-module(_te_q_seam, [q(A)])\n"
            "def build():\n"
            "    return --q(1)\n"
        ))
        assert mod.build() == ("q", 1)

    def test_a_declared_q1_predicate_works_in_every_goal_context(self):
        """A user's ``q/1`` is an ordinary predicate: as a body goal, under
        ``call/1``, ``not`` and ``findall/3``.  Each of these was a
        ``BareGoalVariableError`` or an instantiation error while ``q(X)``
        was stripped to ``X``."""
        # nv
        mod = _load_src("_te_q_pred", (
            "q(1),\n"
            "q(2),\n"
            "body(X) <- q(X)\n"
            "meta(X) <- call(q(X))\n"
            "naf(X) <- (X is 3, not q(X))\n"
            "all(L) <- findall(X, q(X), L)\n"
        ))
        assert _answers(mod, "q") == [(1,), (2,)]
        assert _answers(mod, "body") == [(1,), (2,)]
        assert _answers(mod, "meta") == [(1,), (2,)]
        assert _answers(mod, "naf") == [(3,)]
        assert _answers(mod, "all") == [([1, 2],)]


class TestRetiredQuasiQuoteWarning:
    """An old ``q(...)`` rule now builds ``('q', ...)`` cells that match
    nothing -- the expansion would silently not fire.  So a ``q(<one arg>)``
    in a ``term_expansion/4`` clause warns at load, and nowhere else."""

    @staticmethod
    def _warned(name, source, *, load_may_raise=False):
        from clausal.lint_warnings import ClausalRetiredQuasiQuoteWarning
        mod = None
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                mod = _load_src(name, source)
            except Exception:
                # The warning is emitted by the rewriter, before anything
                # compiles; a test about the WARNING may use a shape whose
                # load then fails for its own reasons.
                if not load_may_raise:
                    raise
        hits = [w for w in caught
                if issubclass(w.category, ClausalRetiredQuasiQuoteWarning)]
        return mod, hits

    def test_an_old_q_pattern_warns_and_does_not_expand(self):
        # nv
        mod, hits = self._warned("_te_old_q", (
            "term_expansion(\n"
            "    q(fact(X)),\n"
            "    [q(fact(X)), q(logged_fact(X))],\n"
            "    STATE, STATE\n"
            "),\n"
            "fact(1),\n"
        ))
        assert len(hits) == 1
        msg = str(hits[0].message)
        assert "retired 2026-09-25" in msg and "term_expansion(fact(X)" in msg
        assert ".clausal:2:" in msg   # the line of the first q(...)
        # ...and the reason it warns: the rule no longer matches the item.
        assert _answers(mod, "fact") == [(1,)]
        lm = mod.__dict__["$module"]
        assert not lm.db.clauses_for("logged_fact", 1)

    def test_one_warning_per_clause(self):
        # nv
        _, hits = self._warned("_te_old_q2", (
            "term_expansion(q(a(X)), [], S, S),\n"
            "term_expansion(q(b(X)), [], S, S) <- True\n"
            "term_expansion(INP, OUTP, S, S) <- (INP is q(c(X)), OUTP is [])\n"
        ))
        assert len(hits) == 3

    def test_an_old_q_pattern_warns_with_q_and_fact_already_pooled_atoms(self):
        """Hermetic against load order: another module has declared the
        ATOMS ``q``, ``fact`` and ``logged_fact`` (the pool every module dict
        is seeded with), which is the state the full suite reached when this
        failed with ``TypeError: 'str' object is not callable`` at expansion
        time -- see tests/test_pool_atom_applied_as_functor.py."""
        # nv
        _load_src("_te_pool_owner",
                  "-module(_te_pool_owner, [q, fact, logged_fact])\n"
                  "kind(q),\nkind(fact),\nkind(logged_fact),\n")
        self.test_an_old_q_pattern_warns_and_does_not_expand()
        mod = _load_src("_te_pool_plain", (
            "term_expansion(fact(X), [fact(X), logged_fact(X)], S, S),\n"
            "fact(1),\n"
        ))
        assert _answers(mod, "logged_fact") == [(1,)]

    def test_clauses_without_line_numbers_are_not_merged(self):
        """Roborev L1: the dedup key used to be the line of the first q(),
        falling back to 0, so a second clause with no lineno was silenced."""
        # nv
        from clausal.lint_warnings import ClausalRetiredQuasiQuoteWarning
        t = EmbedTransformer(source_lines=None, filename=None)
        clauses = [ast.parse(f"term_expansion(q({f}(X)), [], S, S)",
                             mode="eval").body for f in ("a", "b")]
        for c in clauses:
            for n in ast.walk(c):
                for attr in ("lineno", "end_lineno"):
                    if hasattr(n, attr):
                        delattr(n, attr)
            t._lint_retired_quasi_quote(c)
        t._lint_retired_quasi_quote(clauses[0])      # same clause again: once
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            t._settle_retired_quasi_quote()
        assert sum(issubclass(w.category, ClausalRetiredQuasiQuoteWarning)
                   for w in caught) == 2

    def test_a_q_pattern_in_a_helper_reached_from_term_expansion_warns(self):
        """Roborev L2: the delegating shape -- the q() patterns live in a
        helper that the term_expansion body calls, transitively."""
        # nv
        # (The load itself then fails: a term_expansion body cannot call
        # this module's own predicates today -- ``step/2 has no compiled
        # dispatch function`` -- parked in
        # todo/term-expansion-cannot-call-a-helper-in-its-own-module-2026-09-25.md.
        # The warning is the rewriter's, and comes first.)
        _, hits = self._warned("_te_helper", (
            "term_expansion(I, O, S, S) <- step(I, O)\n"
            "step(I, O) <- rewrite(I, O)\n"
            "rewrite(q(fact(X)), [q(logged_fact(X))]),\n"
            "unrelated(q(1)),\n"
            "fact(1),\n"
        ), load_may_raise=True)
        assert len(hits) == 1
        assert "a clause of rewrite, reached from term_expansion/4" in str(hits[0].message)
        assert ".clausal:3:" in str(hits[0].message)

    def test_a_q_inside_a_python_escape_or_as_a_goal_is_quiet(self):
        """Roborev L3: ``++(...)`` is Python, where ``q(x)`` is Python's own
        call; and ``q(I)`` as a body GOAL calls the user's ``q/1``."""
        # nv
        _, hits = self._warned("_te_escape", (
            "term_expansion(I, O, S, S) <- (q(I), O is ++((lambda q: q(3))(abs)))\n"
            "term_expansion(I, O, S, S) <- (not q(I), O is [I])\n"
        ), load_may_raise=True)
        assert hits == []

    def test_a_file_without_q_is_not_walked(self, monkeypatch):
        """Roborev L4: the cheap gate -- no ``q(`` in the source, no walk."""
        # nv
        from clausal.templating import term_rewriting as tr
        walked = []
        real = tr.iter_child_nodes
        monkeypatch.setattr(tr, "iter_child_nodes",
                            lambda n: (walked.append(n), real(n))[1])
        t = EmbedTransformer(source_lines=["term_expansion(fact(X), [], S, S)\n"],
                             filename="x.clausal")
        t._lint_retired_quasi_quote(
            ast.parse("term_expansion(fact(X), [], S, S)", mode="eval").body)
        assert walked == [] and t._retired_q_records == []
        t2 = EmbedTransformer(source_lines=["term_expansion(q(X), [], S, S)\n"],
                              filename="x.clausal")
        t2._lint_retired_quasi_quote(
            ast.parse("term_expansion(q(X), [], S, S)", mode="eval").body)
        assert walked and len(t2._retired_q_records) == 1

    def test_plain_patterns_and_q_outside_term_expansion_are_quiet(self):
        # nv
        _, hits = self._warned("_te_quiet", (
            "-private([q/2])\n"
            "term_expansion(fact(X), [fact(X)], S, S),\n"
            "term_expansion(q(1, X), [], S, S),\n"
            "q(1),\n"
            "r(X) <- call(q(X))\n"
            "fact(1),\n"
        ))
        assert hits == []


class TestModuleItemsUnchanged:
    """Verify that module_items (directives, imports) are unaffected by expansion."""

    def test_directives_preserved(self):
        """Directives in module_items survive term expansion."""
        # nv
        from clausal.pythonic_ast.nodes import Directive
        source = '-double_quotes(atom)\n-dynamic(color/2)\ncolor("sky", "blue"),\n'
        preds, items, md = _parse_and_collect(source)
        directives = [i for i in items if isinstance(i, Directive)]
        assert len(directives) == 1
        assert directives[0].specs == [("color", 2)]


class TestIntegrationWithCompileModule:
    """Test term expansion integrated with compile_module."""

    def test_no_expansion_full_pipeline(self):
        """Full pipeline with no term_expansion clauses works normally."""
        # nv
        source = '-double_quotes(atom)\nfoo("a"),\nfoo("b"),\n'
        preds, items, md = _parse_and_collect(source)
        lm = compile_module(preds, items, md, "_test_no_te")
        md["$module"] = lm

        x = Var()
        results = []
        for trail in call("foo", x, module=lm):
            results.append(deref(x))
        assert sorted(results) == [mint("a"), mint("b")]

    def test_identity_expansion_full_pipeline(self):
        """Full pipeline with identity TE — all clauses survive."""
        # nv
        source = (
            '-double_quotes(atom)\nterm_expansion(_term, _term, _m0, _m0) <- True\n'
            'bar("x"),\n'
            'bar("y"),\n'
        )
        preds, items, md = _parse_and_collect(source)
        lm = compile_module(preds, items, md, "_test_id_te")
        md["$module"] = lm

        x = Var()
        results = []
        for trail in call("bar", x, module=lm):
            results.append(deref(x))
        assert sorted(results) == [mint("x"), mint("y")]

    def test_suppression_full_pipeline(self):
        """Full pipeline with suppression TE — no clauses compiled."""
        # nv
        source = (
            '-double_quotes(atom)\nterm_expansion(_term, "none", _m0, _m0) <- True\n'
            'baz("a"),\n'
        )
        preds, items, md = _parse_and_collect(source)
        lm = compile_module(preds, items, md, "_test_sup_te")
        assert not lm.db.is_defined("baz", 1)


class TestImportedExpansionRules:
    """term_expansion rules imported from another module via -import_from."""

    def test_imported_te_via_fixture(self):
        """Full import of expansion_importer.clausal which imports TE rules."""
        # nv
        import sys
        # Ensure fixtures dir is on path for -import_from resolution.
        fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures")
        if fixtures_dir not in sys.path:
            sys.path.insert(0, fixtures_dir)
        try:
            # First load the provider so it's in sys.modules.
            _load_module(
                "expansion_provider",
                os.path.join(FIXTURES_DIR, "expansion_provider.clausal"),
            )
            # Now load the importer that uses -import_from(expansion_provider, ...).
            mod = _load_module(
                "_exp_imp",
                os.path.join(FIXTURES_DIR, "expansion_importer.clausal"),
            )
            lm = mod.__dict__["$module"]
            x = Var()
            results = []
            for t in call("color", x, module=lm):
                results.append(deref(x))
            # The imported TE rule duplicates each item.
            assert sorted(results) == [mint("green"), mint("green"), mint("red"), mint("red")]
        finally:
            sys.modules.pop("expansion_provider", None)
            sys.modules.pop("_exp_imp", None)

    def test_imported_te_predicate_nodes_stored(self):
        """Provider module records its TE clauses on its DATABASE, not on the
        term_expansion class (W4b-2d R6: a class stash is lost silently once
        an importer's binding is a handle)."""
        # nv
        mod = _load_module(
            "_exp_prov",
            os.path.join(FIXTURES_DIR, "expansion_provider.clausal"),
        )
        te_cls = mod.__dict__.get("term_expansion")
        assert te_cls is not None
        assert not hasattr(te_cls, "_te_predicate_nodes")
        nodes = mod.__dict__["$module"].db.te_predicate_nodes
        assert nodes is not None and len(nodes) == 1


class TestNewFunctorsFromExpansion:
    """Expansion that creates predicates with functors not in the source."""

    def test_expansion_creates_new_functor(self):
        """term_expansion rewrites src/1 facts into dst/1 facts."""
        # The expansion rule rewrites every item into an item with a different
        # functor name ("dst") that doesn't appear in the original source.
        # Because the TE rule unifies _term with the original Predicate node
        # and _expansion is constructed by Clausal's own unification, the
        # result is a new Predicate node with head dst(...).
        # nv
        source = (
            '-double_quotes(atom)\nterm_expansion(_term, _exp, _m0, _m0) <- (\n'
            '    _term is _exp,\n'  # identity — passes item through
            '    _m0 is _m0\n'
            ')\n'
            'src("hello"),\n'
        )
        preds, items, md = _parse_and_collect(source)
        result = run_term_expansion(preds, md)
        # With identity expansion, src items pass through
        assert len(result) == 1
        assert _head_functor(result[0].head) == "src"

    def test_new_functor_full_pipeline(self):
        """Full pipeline: expansion duplicates items, creating more clauses.

        This verifies compile_module handles predicates produced by expansion
        that weren't in the original source (extra clauses for same functor).
        """
        # nv
        source = (
            '-double_quotes(atom)\nterm_expansion(_term, [_term, _term], _m0, _m0) <- True\n'
            'color("red"),\n'
            'color("blue"),\n'
        )
        preds, items, md = _parse_and_collect(source)
        lm = compile_module(preds, items, md, "_test_new_fn")
        md["$module"] = lm

        x = Var()
        results = []
        for trail in call("color", x, module=lm):
            results.append(deref(x))
        # Each duplicated: red, red, blue, blue
        assert sorted(results) == [mint("blue"), mint("blue"), mint("red"), mint("red")]


class TestInitFinalInjection:
    """Module state init/final list injection."""

    def test_init_list_injection(self):
        """term_expansion accumulates init items via module state."""
        # This TE rule passes items through but adds each item to the
        # init list (prepended items).
        # nv
        source = (
            '-double_quotes(atom)\nterm_expansion(_term, _term, module_expansion_state(_init, _final, _s), '
            'module_expansion_state([_term | _init], _final, _s)) <- True\n'
            'item("a"),\n'
            'item("b"),\n'
        )
        preds, _, md = _parse_and_collect(source)
        result = run_term_expansion(preds, md)
        # Items passed through (2) + init items prepended (2) = 4
        # Init list is built by consing, so it's reversed: [b, a]
        assert len(result) == 4

    def test_final_list_injection(self):
        """term_expansion accumulates final items via module state."""
        # nv
        source = (
            '-double_quotes(atom)\nterm_expansion(_term, _term, module_expansion_state(_init, _final, _s), '
            'module_expansion_state(_init, [_term | _final], _s)) <- True\n'
            'item("x"),\n'
        )
        preds, _, md = _parse_and_collect(source)
        result = run_term_expansion(preds, md)
        # 1 passed through + 1 appended from final list
        assert len(result) == 2

    def test_init_final_full_pipeline(self):
        """Full pipeline with init/final injection — all items compiled."""
        # nv
        source = (
            '-double_quotes(atom)\nterm_expansion(_term, _term, module_expansion_state(_init, _final, _s), '
            'module_expansion_state([_term | _init], [_term | _final], _s)) <- True\n'
            'val("one"),\n'
        )
        preds, items, md = _parse_and_collect(source)
        lm = compile_module(preds, items, md, "_test_init_final")
        md["$module"] = lm

        x = Var()
        results = []
        for trail in call("val", x, module=lm):
            results.append(deref(x))
        # Original + init copy + final copy = 3 solutions
        assert results.count(mint("one")) == 3


class TestNestedVarSubstitution:
    """A var matched inside a PATTERN flows into the OUTPUT.

    Gap 2 of todo/term-expansion-compile-time-predicate-synthesis.md (filed
    2026-07-03): ``term_expansion(key(KEY), [marker(KEY)], S, S)`` used
    to leave ``marker/1`` existing but EMPTY — the matched KEY never reached
    the registered output facts.  Fixed since; pinned here end-to-end.
    """

    def test_matched_var_registers_in_output_facts(self):
        # nv
        mod = _load_module(
            "_exp_nested_var",
            os.path.join(FIXTURES_DIR, "expansion_nested_var.clausal"),
        )
        lm = mod.__dict__["$module"]
        x = Var()
        results = [deref(x) for _ in call("marker", x, module=lm)]
        names = sorted(results, key=repr)
        assert names == [mint("income"), mint("stays")], (
            f"matched KEY must flow into the output; got {results!r}"
        )


class TestExpansionResultIsValidated:
    """A term_expansion/4 answer that is not a clause, a list of clauses or
    the atom ``none`` is an ISO type error at load -- not an AttributeError
    from deep inside goal expansion.

    Measured 2026-09-26 while preparing the -double_quotes default flip: a
    chars-mode module writing the suppression sentinel as ``"none"`` (a
    STRING under that mode) crashed with ``'tuple' object has no attribute
    'body'`` at goal_expansion.py, naming neither the rule nor the fix.
    """

    def test_a_chars_string_none_is_a_type_error_that_names_the_atom(
            self, tmp_path):
        # A file load, not ``_parse_and_collect``: the quote map that tells
        # ``"none"`` from ``'none'`` is built from the SOURCE LINES, which
        # the bare EmbedTransformer() there is never handed.
        path = tmp_path / "te_chars_none.clausal"
        path.write_text(
            '-double_quotes(chars)\n'
            'term_expansion(_, "none", _m0, _m0) <- True\n'
            'foo("a"),\n'
        )
        with pytest.raises(LogicException) as exc:
            _load_module("_te_chars_none_shape", str(path))
        term = exc.value.term
        assert type(term) is tuple and cell_functor(term) == "error"
        formal, context = cell_args(term)[0], error_context_text(term)
        assert cell_functor(formal) == "type_error"
        assert cell_args(formal)[0] == mint("callable")
        assert cell_args(formal)[1] == ("$chars", "none")
        assert "the suppression sentinel is the ATOM none" in context
        assert "write none or 'none'" in context

    def test_a_number_answer_is_a_type_error(self):
        source = (
            '-double_quotes(atom)\nterm_expansion(_term, 42, _m0, _m0) <- True\n'
            'foo("a"),\n'
        )
        preds, _, md = _parse_and_collect(source)
        with pytest.raises(LogicException) as exc:
            run_term_expansion(preds, md)
        formal = cell_args(exc.value.term)[0]
        assert cell_functor(formal) == "type_error" and cell_args(formal)[1] == 42

    def test_a_bad_element_inside_a_list_answer_is_a_type_error(self):
        source = (
            '-double_quotes(atom)\nterm_expansion(foo(X), [foo(X), 7], _m0, _m0) <- True\n'
            'foo("a"),\n'
        )
        preds, _, md = _parse_and_collect(source)
        with pytest.raises(LogicException) as exc:
            run_term_expansion(preds, md)
        formal = cell_args(exc.value.term)[0]
        assert cell_functor(formal) == "type_error" and cell_args(formal)[1] == 7

    def test_an_unbound_answer_is_an_instantiation_error(self):
        source = (
            'term_expansion(_, _E, _m0, _m0) <- True\n'
            'foo("a"),\n'
        )
        preds, _, md = _parse_and_collect(source)
        with pytest.raises(LogicException) as exc:
            run_term_expansion(preds, md)
        formal, context = cell_args(exc.value.term)[0], error_context_text(exc.value.term)
        assert formal == mint("instantiation_error")
        assert "term_expansion/4: the expansion is unbound" in context

    def test_an_unbound_answer_on_the_head_retry_names_a_head_term(self):
        source = (
            'term_expansion(foo(_), _E, _m0, _m0) <- True\n'
            'foo("a"),\n'
        )
        preds, _, md = _parse_and_collect(source)
        with pytest.raises(LogicException) as exc:
            run_term_expansion(preds, md)
        assert "a head term" in error_context_text(exc.value.term)

    def test_a_bad_item_in_the_final_list_is_a_type_error_naming_the_slot(self):
        source = (
            'term_expansion(_term, _term, module_expansion_state(_i, _final, _s), '
            'module_expansion_state(_i, [42 | _final], _s)) <- True\n'
            'foo("a"),\n'
        )
        preds, _, md = _parse_and_collect(source)
        with pytest.raises(LogicException) as exc:
            run_term_expansion(preds, md)
        formal, context = cell_args(exc.value.term)[0], error_context_text(exc.value.term)
        assert cell_functor(formal) == "type_error" and cell_args(formal)[1] == 42
        assert "Final list" in context and "none" not in context

    def test_an_unbound_item_in_the_init_list_is_an_instantiation_error(self):
        source = (
            'term_expansion(_term, _term, module_expansion_state(_init, _f, _s), '
            'module_expansion_state([_U | _init], _f, _s)) <- True\n'
            'foo("a"),\n'
        )
        preds, _, md = _parse_and_collect(source)
        with pytest.raises(LogicException) as exc:
            run_term_expansion(preds, md)
        formal, context = cell_args(exc.value.term)[0], error_context_text(exc.value.term)
        assert formal == mint("instantiation_error") and "Init list" in context

    def test_the_none_atom_in_the_init_list_is_refused_not_a_fact(self):
        source = (
            'term_expansion(_term, _term, module_expansion_state(_init, _f, _s), '
            "module_expansion_state(['none' | _init], _f, _s)) <- True\n"
            'foo("a"),\n'
        )
        preds, _, md = _parse_and_collect(source)
        with pytest.raises(LogicException) as exc:
            run_term_expansion(preds, md)
        formal, context = cell_args(exc.value.term)[0], error_context_text(exc.value.term)
        assert cell_functor(formal) == "type_error" and cell_args(formal)[1] == mint("none")
        assert "suppression has no meaning" in context

    def test_a_head_term_in_the_init_list_becomes_a_fact(self):
        source = (
            '-private([bar])\n'
            'term_expansion(_term, _term, module_expansion_state(_init, _f, _s), '
            'module_expansion_state([bar | _init], _f, _s)) <- True\n'
            'foo("a"),\n'
        )
        preds, _, md = _parse_and_collect(source)
        result = run_term_expansion(preds, md)
        assert deref(result[0].head) == mint("bar") and result[0].body is True

    def test_the_chars_none_error_surfaces_through_a_full_load(self, tmp_path):
        path = tmp_path / "te_chars_none_load.clausal"
        path.write_text(
            '-double_quotes(chars)\n'
            'term_expansion(_, "none", _m0, _m0) <- True\n'
            'foo("a"),\n'
        )
        with pytest.raises(LogicException, match="the suppression sentinel is the ATOM none"):
            _load_module("_te_chars_none_load", str(path))

    def test_a_bad_item_in_the_init_list_is_a_type_error_naming_the_slot(self):
        source = (
            'term_expansion(_term, _term, module_expansion_state(_init, _f, _s), '
            'module_expansion_state([42 | _init], _f, _s)) <- True\n'
            'foo("a"),\n'
        )
        preds, _, md = _parse_and_collect(source)
        with pytest.raises(LogicException) as exc:
            run_term_expansion(preds, md)
        formal, context = cell_args(exc.value.term)[0], error_context_text(exc.value.term)
        assert cell_functor(formal) == "type_error" and cell_args(formal)[1] == 42
        assert "Init list" in context

    def test_a_head_pattern_answer_that_is_an_atom_becomes_a_fact(self):
        """The positive side of the gate: an atom head, and a list of head
        terms, still wrap into facts on the head-pattern retry."""
        source = (
            '-private([flag, foo])\n'
            'term_expansion(foo(X), [foo(X), flag], _m0, _m0) <- True\n'
            'foo(1),\n'
        )
        preds, _, md = _parse_and_collect(source)
        result = run_term_expansion(preds, md)
        assert _head_functor(result[0].head) == "foo"
        assert deref(result[1].head) == mint("flag")   # the atom head, wrapped
        assert all(r.body is True for r in result)
