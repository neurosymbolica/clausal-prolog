"""Comma-optional bodyless facts + undeclared-fact diagnostic.

See docs/superpowers/specs/2026-07-20-optional-fact-comma-design.md
"""
import pytest

from clausal.import_hook import _load_module


def load_src(tmp_path, name, src):
    """Write *src* to <tmp>/<name>.clausal and load it, returning the module."""
    p = tmp_path / f"{name}.clausal"
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

    def test_declared_later_still_requires_comma(self, tmp_path):
        # Single-pass boundary: `foo(9)` before any declaration is NOT a fact.
        # foo(9) is ground, so it does not raise; it is silently a no-op call
        # and no clause is asserted (documents the ordering limitation).
        src = "foo(9)\nfoo(1),\n"
        mod = load_src(tmp_path, "t2_later", src)
        assert clause_count(mod, "foo", 1) == 1
