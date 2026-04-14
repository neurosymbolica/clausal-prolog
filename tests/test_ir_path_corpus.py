"""Slice D4 corpus test: compile real ``.clausal`` modules with the
GoalOp IR path enabled and verify nothing diverges from the legacy
dispatcher.

The parallel-implementation harness in ``_compile_body_impl``:

1. Runs the legacy right-to-left fold over ``strategy.compile_goal``.
2. If ``ctx.use_ir_path`` or ``CLAUSAL_IR_PATH=1``, also runs
   ``terms_to_goalop`` → ``lower_python_<strategy>`` with a cloned
   ``FreshNames`` seeded at the pre-legacy counter.
3. Asserts ``ast.dump`` equality — any diff raises ``AssertionError``
   (stop-the-line).
4. ``NotImplementedError`` from ``terms_to_goalop`` is the legitimate
   fallback for body shapes outside the D2 subset.

This file enables the flag via env var and loads each ``.clausal``
fixture module end-to-end.  Loading runs the full compilation
pipeline, so any AST drift for a D2-subset clause surfaces as a test
failure here without needing to enumerate individual clauses.

The plan (``todo/slice_d_goalop_ir.md`` D4) asks for ~50 clauses; the
fixtures below collectively contain well over that, spanning every D2
construct (Unify, Dif, Evaluate, FD compares, StructuralEq, MemberIn)
plus clauses that exercise the ``NotImplementedError`` fallback (And,
Or, Not, IfExpr, Call, meta-predicates, …).
"""

from __future__ import annotations

import os

import pytest

from clausal.import_hook import _load_module


_TESTS_DIR = os.path.dirname(__file__)

# (subdir, filename) — kept as tuples so the parametrize id stays unique
# across roots and so the tabled-NAF fixtures (which live under
# ``tests/fixtures/`` alongside the WFS / tabling integration tests) can
# join the corpus without duplication.
_CORPUS: list[tuple[str, str]] = [
    ("clausal_modules", "anon.clausal"),
    ("clausal_modules", "arith.clausal"),
    ("clausal_modules", "exceptions.clausal"),
    ("clausal_modules", "family.clausal"),
    ("clausal_modules", "higher_order.clausal"),
    ("clausal_modules", "lambdas.clausal"),
    ("clausal_modules", "list_edge_cases.clausal"),
    ("clausal_modules", "lists.clausal"),
    ("clausal_modules", "meta.clausal"),
    ("clausal_modules", "term_inspection.clausal"),
    # D5h follow-up: gate tabled-NAF (Not + IfExpr-test on tabled
    # predicates) without needing ``CLAUSAL_IR_PATH=1`` over the full
    # suite.  ``wfs_win`` exercises ``Not(Call(tabled))`` →
    # ``MetaCall(naf_tabled)``; ``tabled_ite`` exercises
    # ``IfExpr(test=Call(tabled))`` → ``Branch(tabled_naf=True)``.
    ("fixtures", "wfs_win.clausal"),
    ("fixtures", "tabled_ite.clausal"),
]


@pytest.fixture
def ir_path_on(monkeypatch):
    monkeypatch.setenv("CLAUSAL_IR_PATH", "1")


@pytest.mark.parametrize("subdir,filename", _CORPUS)
def test_clausal_module_compiles_with_ir_path_on(subdir, filename, ir_path_on):
    # Loading triggers compile_predicate_* → _compile_body_impl → the
    # D4 harness.  Any AST drift for a D2-subset clause raises
    # AssertionError and fails this test.
    path = os.path.join(_TESTS_DIR, subdir, filename)
    name = f"_ir_corpus_{subdir}_{filename.replace('.', '_')}"
    _load_module(name, path)
