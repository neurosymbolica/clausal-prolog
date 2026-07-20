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
