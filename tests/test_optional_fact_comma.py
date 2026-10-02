"""Comma-optional bodyless facts + undeclared-fact diagnostic.

See docs/superpowers/specs/2026-07-20-optional-fact-comma-design.md
"""
import pytest

from clausal.import_hook import _load_module
from tests._suffix import SEAM


def load_src(tmp_path, name, src):
    """Write *src* to <tmp>/<name>.clausal and load it, returning the module."""
    p = tmp_path / f"{name}{SEAM}"
    p.write_text(src)
    return _load_module(name, str(p))


def clause_count(mod, functor, arity):
    return len(mod.__clausal_module__.db.clauses_for(functor, arity))


class TestTrailingCommaStillWorks:
    def test_comma_facts_land(self, tmp_path):
        mod = load_src(tmp_path, "t1_comma", "edge(1, 2),\nedge(3, 4),\n")
        assert clause_count(mod, "edge", 2) == 2

    def test_zero_arity_comma_fact_lands(self, tmp_path):
        mod = load_src(tmp_path, "t1_zero", "flag,\n")
        assert clause_count(mod, "flag", 0) == 1


class TestCommaOptionalWhenDeclared:
    def test_canonical_repro_module_declared(self, tmp_path):
        # p declared via -module; bare fact with `_` in head, no trailing comma.
        src = (
            "-module(r1, [ p(A, B), q(A) ])\n"
            "-strict_atoms\n"
            "p(_, 1)\n"
            "q(X) <- ( p(X, 1) )\n"
        )
        mod = load_src(tmp_path, "t2_canon", src)
        assert clause_count(mod, "p", 2) == 1

    def test_block_last_fact_no_comma_lands(self, tmp_path):
        # The silent-drop bug: last fact in a block omits its comma.
        src = "-dynamic(counter/1)\ncounter(0),\ncounter(1),\ncounter(2)\n"
        mod = load_src(tmp_path, "t2_block", src)
        assert clause_count(mod, "counter", 1) == 3

    def test_prior_clause_declares_functor(self, tmp_path):
        # First fact has a comma (registers the functor); second omits it.
        src = "edge(1, 2),\nedge(3, 4)\n"
        mod = load_src(tmp_path, "t2_prior", src)
        assert clause_count(mod, "edge", 2) == 2

    def test_zero_arity_declared_bare_fact(self, tmp_path):
        src = "-module(z, [ flag ])\nflag\n"
        mod = load_src(tmp_path, "t2_zero", src)
        assert clause_count(mod, "flag", 0) == 1

    def test_declared_later_does_not_apply(self, tmp_path):
        # Single-pass boundary: `_t2_later_pred_(9)` appears BEFORE any
        # declaration of that functor, so it is NOT recognized as a fact
        # (comma-optional requires a prior declaration).  The functor is unbound
        # at that point (an undeclared functor is not a bound PredicateMeta),
        # so the load errors rather than silently succeeding — documents that a
        # declaration must precede a comma-less fact.
        #
        # The functor name is deliberately obscure to avoid colliding with
        # globally-registered predicates from other test modules (the process-
        # wide predicate_builtins dict would otherwise supply the name, causing
        # the guard's try-branch to resolve and skip the NameError).
        src = "_t2_later_pred_(9)\n_t2_later_pred_(1),\n"
        with pytest.raises(NameError):
            load_src(tmp_path, "t2_later", src)


class TestUndeclaredDiagnostic:
    def test_undeclared_bare_fact_hints_comma(self, tmp_path):
        # Functor undeclared, no -module: functor name is undefined.
        #
        # The functor name is deliberately obscure (same rationale as
        # test_declared_later_does_not_apply above) to avoid colliding with
        # globally-registered atoms from OTHER test modules: post-P3-1,
        # atoms are interned by spelling into the process-wide
        # predicate_builtins dict FOREVER (§1b/R2's global-by-spelling
        # design), so a single-letter name like the `p` this test used to
        # use collides with e.g. tests/test_operator_head_indexed_dispatch.py's
        # -private([p, ...]) -- whichever test runs first wins the name, and
        # once `p` is a known atom the try/except NameError guard this test
        # exercises no longer sees an undefined name, so it silently takes
        # the "legitimate call" branch instead of raising the "bodyless
        # fact" diagnostic. Root-caused in
        # phase3-decomposition-and-p31-atom-pivot.md Task 7 work item 3
        # (order-dependent flake); a per-test predicate_builtins reset was
        # considered and rejected as disproportionate -- that dict's
        # whole-process persistence is the deliberate global-atom-identity
        # design (other tests pin `mod.x is predicate_builtins["x"]`-shaped
        # object identity), so resetting it here would just move the
        # fragility onto those tests instead of removing it.
        src = "-strict_atoms\n_t3_undeclared_pred_(_ATOM, 1)\n"
        with pytest.raises(NameError) as ei:
            load_src(tmp_path, "t3_undecl", src)
        msg = str(ei.value)
        assert "bodyless fact" in msg
        assert "trailing" in msg
        assert "_t3_undeclared_pred_" in msg

    def test_legit_undeclared_call_still_runs(self, tmp_path, capsys):
        # `print` resolves (a real callable), so the else-branch runs it: no error.
        src = 'print("clausal-ok")\n'
        mod = load_src(tmp_path, "t3_legit", src)  # must not raise
        assert mod is not None
        assert "clausal-ok" in capsys.readouterr().out

    def test_zero_arity_undeclared_bare_name_hints_comma(self, tmp_path):
        # A bare undeclared zero-arity Name (not a logic var) must also produce
        # the bodyless-fact diagnostic, not a raw NameError.
        # Name must not start with '_' (single-leading-underscore → logic var)
        # and must not be ALL-CAPS (those are logic vars too).
        src = "xyzzy_zero_undecl\n"
        with pytest.raises(NameError) as ei:
            load_src(tmp_path, "t3_zero_undecl", src)
        msg = str(ei.value)
        assert "bodyless fact" in msg
        assert "xyzzy_zero_undecl" in msg

    def test_functor_resolves_but_arg_typo_is_honest(self, tmp_path):
        # `print` resolves; the undefined ARG error must NOT be reported as a
        # missing-comma fact.
        src = "print(nope_undefined_arg)\n"
        with pytest.raises(NameError) as ei:
            load_src(tmp_path, "t3_argtypo", src)
        msg = str(ei.value)
        assert "nope_undefined_arg" in msg
        assert "bodyless fact" not in msg


class TestReplModeUnaffected:
    """A fresh EmbedTransformer with no source_lines (the IPython/console REPL
    path via _FreshEmbedTransformer) must NOT wrap bare calls/names — otherwise
    the trailing node stops being an ast.Expr and result echo breaks."""

    def _last_node_kind(self, src):
        import ast
        from clausal.templating.term_rewriting import EmbedTransformer
        tree = ast.parse(src)
        out = EmbedTransformer().visit(tree)   # no source_lines => REPL mode
        ast.fix_missing_locations(out)
        return type(out.body[-1]).__name__

    def test_bare_call_stays_expr_in_repl(self):
        assert self._last_node_kind("len([1, 2, 3])") == "Expr"

    def test_bare_name_stays_expr_in_repl(self):
        assert self._last_node_kind("result") == "Expr"

    def test_functor_call_stays_expr_in_repl(self):
        assert self._last_node_kind("edge(1, 2)") == "Expr"
