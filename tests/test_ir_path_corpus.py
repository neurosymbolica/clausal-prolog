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


_FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "clausal_modules")

_CORPUS = [
    "anon.clausal",
    "arith.clausal",
    "exceptions.clausal",
    "family.clausal",
    "higher_order.clausal",
    "lambdas.clausal",
    "list_edge_cases.clausal",
    "lists.clausal",
    "meta.clausal",
    "term_inspection.clausal",
]


@pytest.fixture
def ir_path_on(monkeypatch):
    monkeypatch.setenv("CLAUSAL_IR_PATH", "1")


@pytest.mark.parametrize("filename", _CORPUS)
def test_clausal_module_compiles_with_ir_path_on(filename, ir_path_on):
    # Loading triggers compile_predicate_* → _compile_body_impl → the
    # D4 harness.  Any AST drift for a D2-subset clause raises
    # AssertionError and fails this test.
    path = os.path.join(_FIXTURES_DIR, filename)
    name = f"_ir_corpus_{filename.replace('.', '_')}"
    _load_module(name, path)
