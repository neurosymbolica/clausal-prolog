"""A lazy recompile compiles afresh: it never lowers clause bodies against
the context of an earlier compile.

``compile_predicate_trampoline`` (and the shallow twin) rebind their
``body_compiler`` local to a closure over the compile's own context
(``ctx_template``) and installed a lazy recompile that handed THAT closure
to the next compile.  So every recompile after an ``assertz``/``retract``
lowered its bodies against the FIRST compile's context:

- its per-predicate settings were the first compile's, so the recompiled
  code differed from what a fresh compile of the same clauses gives (a
  tail-recursive dynamic predicate, below, gained a loop a fresh compile
  does not emit, and lost the fresh-variable bookkeeping it does);
- its ``clause_ir_cache`` maps ``id(clause)`` to the body IR of clauses of
  that first compile, long since freed.  When CPython handed a freed
  clause's address to a new clause, the recompile compiled the DEAD
  clause's body in the new clause's place.  With a deep ground term in it
  the stale body named a ``$headlit_<id>`` global the new compile never
  injected (``NameError``, seen in
  ``tests/iso_l3/test_l3_assert_rules.py::test_deep_data_in_a_rule_goes_as_deep_as_in_a_fact``
  depending on the hash seed and what ran before); with plain constants it
  answered with the dead clause's values.

Both are pinned here deterministically: the first by comparing a
recompile's code with the fresh compile's, the second by giving the cache
the collision the allocator produced (the entry for one clause, under the
id of another).
"""
from __future__ import annotations

import ast
import importlib
import sys
import types

from clausal.logic.compiler.compile_ctx import CompilationContext
from clausal.logic.compiler.goal_trampoline import _make_body_compiler_trampoline
from clausal.logic.compiler.predicate import _sweep_tro_eligible
from clausal.logic.compiler.strategy import TrampolineStrategy
from clausal.logic.database import Clause, Database
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref, walk
from clausal.terms import Unify

COUNTDOWN = """\
:- module(recompile_ctx, [go/1, touch/0]).
:- dynamic(cnt/2).
cnt(0, done).
cnt(N, R) :- N > 0, N1 is N - 1, cnt(N1, R).
go(R) :- cnt(5, R).
touch :- assertz(cnt(-1, neg)), retract(cnt(-1, neg)).
"""


def _load(tmp_path, monkeypatch, name, text):
    (tmp_path / f"{name}.pl").write_text(text, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("CLAUSAL_PL_FRONTEND", "native")
    sys.modules.pop(name, None)
    importlib.invalidate_caches()
    mod = importlib.import_module(name)
    monkeypatch.setitem(sys.modules, name, mod)
    return mod


def _code_shape(fn, prefix):
    """(name, names, bytecode) of the dispatch function's code and of every
    generated function of the predicate it reaches through its globals."""
    out, seen, stack = [], set(), [fn]
    while stack:
        f = stack.pop()
        code = getattr(f, "__code__", None)
        if code is None or id(code) in seen:
            continue
        seen.add(id(code))
        out.append((code.co_name, code.co_names, code.co_code))
        for v in (getattr(f, "__globals__", None) or {}).values():
            c = getattr(v, "__code__", None)
            if (isinstance(v, types.FunctionType) and c.co_filename == "<template>"
                    and c.co_name.startswith(prefix)):
                stack.append(v)
    return sorted(out)


def _answers(mod, name):
    v = Var()
    return [walk(deref(v)) for _ in call(name, v, module=mod)]


def test_a_recompile_compiles_what_a_fresh_compile_does(tmp_path, monkeypatch):
    mod = _load(tmp_path, monkeypatch, "recompile_ctx", COUNTDOWN)
    db = vars(mod)["$module"].db
    assert _answers(mod, "go") == ["done"]
    fresh = _code_shape(db.get_dispatch("cnt", 2), "cnt")
    for _ in range(3):                      # each round recompiles cnt/2
        assert len(list(call("touch", module=mod))) == 1
        assert _answers(mod, "go") == ["done"]
        assert _code_shape(db.get_dispatch("cnt", 2), "cnt") == fresh


def _clause(n):
    x = Var()
    return Clause(head=("q", x), body=[Unify(left=x, right=n)])


def _constants(stmts):
    return {n.value for s in stmts for n in ast.walk(s)
            if isinstance(n, ast.Constant) and isinstance(n.value, int)
            and not isinstance(n.value, bool)}


def test_the_body_ir_cache_never_answers_for_another_clause():
    """The cache entry of one clause, found under the id of another (what a
    freed and reused address amounts to), is not that other clause's body."""
    db = Database()
    ctx = CompilationContext(db=db, var_context={}, trail_name="trail",
                             strategy=TrampolineStrategy())
    first, second = _clause(1111), _clause(2222)
    _sweep_tro_eligible([first], "q", 1, db, ctx)
    ctx.clause_ir_cache[id(second)] = ctx.clause_ir_cache.pop(id(first))
    body_compiler = _make_body_compiler_trampoline(db, ctx_template=ctx)
    consts = _constants(body_compiler(second, {}))
    assert 2222 in consts and 1111 not in consts, consts
