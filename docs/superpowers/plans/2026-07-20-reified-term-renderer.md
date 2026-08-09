# Reified-term → source renderer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `render_ast(term) -> ast.AST` and `render_source(term) -> str` to `clausal/reflection.py` — the inverse of `reify_ast` — so a rewritten reified term renders back to runnable `.clausal` source.

**Architecture:** A `_ClauseRenderer` class mirroring `_ClauseReifier`, dispatching on reified term type to build a Python surface `ast` node, then `ast.unparse` + the existing `_unparse_clause` arrow repair produces text. Every unhandled node kind raises `RenderError` loudly — never emit malformed text. Correctness is proven by the round-trip invariant `reify(render_source(clause)) ≡structural≡ clause`.

**Tech Stack:** Python 3.13, `ast` module, existing `clausal.reflection` reifier, `clausal.pythonic_ast.nodes` (simple_ast).

## Global Constraints

- Python 3.13.3; run tests with `PYTHONPATH=/workspace/clausal-bug-fix` and the pyenv interpreter (`/home/node/.pyenv/shims/python`). The repo venv lacks pytest.
- All new public names (`render_ast`, `render_source`, `RenderError`) go in `clausal/reflection.py`'s `__all__`.
- The renderer NEVER emits malformed text: any unhandled node kind raises `RenderError`.
- Reuse `ast.unparse` + `_unparse_clause` (reflection.py:529) — do NOT hand-emit text.
- Keep the renderer in `clausal/reflection.py`, next to the reifier, so vocabulary changes keep both halves in sync.
- **Fixture naming rule:** a single-uppercase name (`P`, `Q`, `A`, `B`) is a *logic variable*, so `P(A)` reifies to an `Escape` (unit-`Quantity` metacall), NOT a `Goal`. Predicate/functor names in fixtures MUST be mixed-case (`Pa`, `Busy`, `Head`, `State`) to reify as `Goal`s. Variables in fixtures should be single-caps (`X`, `N`, `A`).
- Verified surface facts (do not re-derive): a fact renders as a **single-element tuple** `(HEAD,)` (a bare `HEAD` reifies as embedded Python, not a clause); a rule renders as `ast.Compare(left=head, ops=[ast.Lt()], comparators=[ast.UnaryOp(ast.USub(), body)])`; a **list cons-tail `[a, b | T]` reifies as a `BitOr` node** (`BinOp(left, ast.BitOr(), right)` in ast), NOT `Starred`; a `*tail` list uses `StarUnpack` → `ast.Starred`; `==`→`ArithEq`→`ast.Eq`, `is`→`Unify`→`ast.Is`; an `Escape` renders as `ast.UnaryOp(ast.UAdd(), ast.UnaryOp(ast.UAdd(), <parsed code>))` which unparses to adjacent `++(code)`.

---

### Task 1: Scaffold + leaves + fact clauses + `strip_positions` test helper

**Files:**
- Modify: `clausal/reflection.py` (add `RenderError`, `render_ast`, `render_source`, `_ClauseRenderer`; extend `__all__`)
- Test: `tests/test_reflection_render.py` (create)

**Interfaces:**
- Consumes: `reify_source`, `Clause`, `Goal`, `Variable`, `Atom`, `_unparse_clause` from `clausal.reflection`.
- Produces:
  - `RenderError(Exception)`
  - `render_ast(term) -> ast.AST` — Clause → an `ast.Expr` statement; any other term → an expression node.
  - `render_source(term) -> str`
  - `_ClauseRenderer` with methods `clause(term)`, `goal(g)`, `term(t)`, `_name_ast(dotted)`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_reflection_render.py`:

```python
"""Round-trip tests for clausal.reflection render_ast/render_source — the
inverse of reify_ast. Invariant: reify(render_source(clause)) is structurally
identical to clause (positions ignored)."""

import dataclasses

import pytest

from clausal.reflection import (
    Clause,
    ReifyError,
    RenderError,
    reify_source,
    render_ast,
    render_source,
)


def strip_positions(term):
    """Recursively null every ``position`` field so structural == ignores
    source location. Reified terms carry ``_fields``; simple_ast operator
    nodes are dataclasses (their position is compare=False, but we normalise
    anyway to reach nested position-bearing terms)."""
    if isinstance(term, list):
        return [strip_positions(x) for x in term]
    if isinstance(term, tuple):
        return tuple(strip_positions(x) for x in term)
    if isinstance(term, dict):
        return {k: strip_positions(v) for k, v in term.items()}
    if dataclasses.is_dataclass(term) and not isinstance(term, type):
        return dataclasses.replace(term, **{
            f.name: (None if f.name == "position" else strip_positions(getattr(term, f.name)))
            for f in dataclasses.fields(term)
        })
    fields = getattr(type(term), "_fields", None)
    if fields is not None:
        return type(term)(*[
            None if name == "position" else strip_positions(getattr(term, name))
            for name in fields
        ])
    return term


def only_clause(src):
    clauses = [i for i in reify_source(src) if isinstance(i, Clause)]
    assert len(clauses) == 1, f"expected one clause, got {len(clauses)}"
    return clauses[0]


def assert_round_trips(src):
    """render_source then re-reify equals the original clause (ignoring positions)."""
    original = only_clause(src)
    rendered_text = render_source(original)
    reparsed = only_clause(rendered_text + "\n")
    assert strip_positions(reparsed) == strip_positions(original), (
        f"round-trip mismatch for {src!r}\n  rendered: {rendered_text!r}"
    )


class TestFacts:
    @pytest.mark.parametrize("src", [
        "Edge(1, 2),\n",
        "Item('widget', 2.5),\n",
        "Status(ok, 1),\n",
        "Temp(-40),\n",
        "Rule(X, Y),\n",
    ])
    def test_fact_round_trips(self, src):
        assert_round_trips(src)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/shims/python -m pytest tests/test_reflection_render.py -x -q`
Expected: FAIL — `ImportError: cannot import name 'RenderError'` (and `render_ast`/`render_source`).

- [ ] **Step 3: Write minimal implementation**

In `clausal/reflection.py`, extend `__all__` — add `"RenderError"`, `"render_ast"`, `"render_source"` (keep alphabetical: `RenderError` after `ReifyError`; `render_ast`, `render_source` after `reify_source`).

Add after `class ReifyError`:

```python
class RenderError(Exception):
    """Raised when a reified term cannot be rendered back to ``.clausal`` source."""
```

Add the renderer class after `_ClauseReifier` (before the "Module directives" section):

```python
class _ClauseRenderer:
    """Render a reified term back to a Python surface ``ast`` node — the
    inverse of :class:`_ClauseReifier`.  Building fresh nodes; positions are
    filled by :func:`ast.fix_missing_locations` before unparse."""

    # -- clause entry ---------------------------------------------------------

    def clause(self, term):
        """``Clause(head, goals, position)`` → an ``ast.Expr`` statement.

        A fact renders as a single-element tuple ``(HEAD,)`` so re-reification
        sees a clause, not embedded Python.  A rule renders as the
        ``Compare(head, [Lt], [USub(body)])`` shape that surface ``HEAD <- BODY``
        parses to and that ``_unparse_clause`` repairs."""
        head = self.term(term.head)
        if not term.goals:
            return ast.Expr(value=ast.Tuple(elts=[head], ctx=ast.Load()))
        if len(term.goals) == 1:
            body = self.goal(term.goals[0])
        else:
            body = ast.Tuple(
                elts=[self.goal(goal) for goal in term.goals], ctx=ast.Load()
            )
        arrow = ast.Compare(
            left=head, ops=[ast.Lt()],
            comparators=[ast.UnaryOp(op=ast.USub(), operand=body)],
        )
        return ast.Expr(value=arrow)

    def goal(self, node):
        """Goals render identically to terms (both are ``ast`` expressions)."""
        return self.term(node)

    # -- names ----------------------------------------------------------------

    def _name_ast(self, dotted):
        """``"a"`` → ``Name(a)``; ``"a.b.c"`` → nested ``Attribute`` chain."""
        parts = dotted.split(".")
        node = ast.Name(id=parts[0], ctx=ast.Load())
        for part in parts[1:]:
            node = ast.Attribute(value=node, attr=part, ctx=ast.Load())
        return node

    # -- terms ----------------------------------------------------------------

    def term(self, value):
        if isinstance(value, Variable):
            # Anonymous vars reify to non-identifier names (#anon1, …); render
            # each as `_`.  Per-clause anon numbering is deterministic by
            # encounter order, so `_` re-reifies to the same #anonN.
            name = "_" if value.name.startswith("#") else value.name
            return ast.Name(id=name, ctx=ast.Load())
        if isinstance(value, Atom):
            return self._name_ast(value.name)
        if isinstance(value, Goal):
            return self._goal_ast(value)
        if isinstance(value, bool):
            return ast.Constant(value)
        if isinstance(value, (int, float, complex)):
            return ast.Constant(value)
        if isinstance(value, str):
            return ast.Constant(value)
        if isinstance(value, (ModuleDirective, PythonCode)):
            raise RenderError(
                f"cannot render {type(value).__name__} — only clause bodies "
                "are in scope for the renderer"
            )
        raise RenderError(f"cannot render term: {value!r}")

    def _goal_ast(self, goal):
        """``Goal(name, args, kwargs)`` → ``ast.Call``."""
        return ast.Call(
            func=self._name_ast(goal.name),
            args=[self.term(arg) for arg in goal.args],
            keywords=[
                ast.keyword(arg=name, value=self.term(value))
                for name, value in goal.kwargs
            ],
        )
```

Add the public functions at the end of the "Public API" section (after `reify_ast`):

```python
def render_ast(term):
    """Render a reified term back to a Python surface ``ast`` node — the
    inverse of :func:`reify_ast`.

    A ``Clause`` renders to an ``ast.Expr`` statement; any other reified term
    renders to an expression node.  Raises :class:`RenderError` for any node
    kind the renderer does not handle (never emits malformed source)."""
    renderer = _ClauseRenderer()
    if isinstance(term, Clause):
        node = renderer.clause(term)
    else:
        node = renderer.term(term)
    return ast.fix_missing_locations(node)


def render_source(term):
    """Render a reified term to ``.clausal`` source text — :func:`render_ast`
    followed by ``ast.unparse`` with the ``<-`` arrow repair."""
    node = render_ast(term)
    if isinstance(node, ast.Expr):
        return _unparse_clause(node)
    return ast.unparse(node)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/shims/python -m pytest tests/test_reflection_render.py -x -q`
Expected: PASS (5 parametrized cases).

- [ ] **Step 5: Commit**

```bash
git add clausal/reflection.py tests/test_reflection_render.py
git commit -m "feat(reflection): render_ast/render_source scaffold — facts, leaves, atoms"
```

---

### Task 2: Rules (arrow) + multi-goal conjunctions + variables shared

**Files:**
- Modify: `clausal/reflection.py` (no new code expected — `clause()` already handles rules; this task proves it and adds variable coverage)
- Test: `tests/test_reflection_render.py`

**Interfaces:**
- Consumes: everything from Task 1.
- Produces: no new API.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_reflection_render.py`:

```python
class TestRules:
    @pytest.mark.parametrize("src", [
        "Connected(X, Y) <- Edge(X, Y)\n",
        "Grandparent(X, Z) <- (Parent(X, Y), Parent(Y, Z))\n",
        "Reachable(X) <- Edge(_, _)\n",
        "Three(A) <- (P(A), Q(A), R(A))\n",
    ])
    def test_rule_round_trips(self, src):
        assert_round_trips(src)
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/shims/python -m pytest tests/test_reflection_render.py::TestRules -x -q`
Expected: PASS is acceptable (Task 1's `clause()` already handles rules) — but the goal bodies here contain only `Goal`s, which `term()` handles. If a case FAILS, it is because the body goal is not a `Goal`; there is none in these cases, so expect PASS. If PASS, this task is a regression guard; proceed to commit.

- [ ] **Step 3: (only if a case failed) Fix**

No implementation change expected. If `Reachable(X) <- Edge(_, _)` fails on anonymous-variable numbering, confirm `term()` renders `#anonN` as `_` (Task 1 Step 3 already does). No other change.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/shims/python -m pytest tests/test_reflection_render.py::TestRules -x -q`
Expected: PASS (4 cases).

- [ ] **Step 5: Commit**

```bash
git add tests/test_reflection_render.py
git commit -m "test(reflection): render round-trips for rules and multi-goal bodies"
```

---

### Task 3: Operator nodes (comparison, arithmetic, is, ==, not, and/or, cons-tail, star-tail)

**Files:**
- Modify: `clausal/reflection.py` (add operator dispatch tables + `_operator_ast`; add list/tuple/dict rendering to `term()`)
- Test: `tests/test_reflection_render.py`

**Interfaces:**
- Consumes: Task 1 renderer.
- Produces: `_ClauseRenderer._operator_ast(node)`; module-level `_RENDER_BINOP_OPS`, `_RENDER_CMP_OPS`, `_RENDER_BOOL_OPS`, `_RENDER_UNARY_OPS`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_reflection_render.py`:

```python
class TestOperators:
    @pytest.mark.parametrize("src", [
        "Positive(N) <- (N > 0)\n",
        "AtLeast(N) <- (N >= 10)\n",
        "Eq(N) <- (N == 0)\n",
        "Neq(N) <- (N != 0)\n",
        "Sum(X, Y, Z) <- (Z is X + Y)\n",
        "Prod(X, Y, Z) <- (Z is X * Y)\n",
        "Diff(X, Y, Z) <- (Z is X - Y)\n",
        "Unify2(X, Y) <- (X is Y)\n",
        "Dif2(X, Y) <- (X is not Y)\n",
        "Free(A) <- (not Busy(A))\n",
        "Either(A) <- (Pa(A) or Qa(A))\n",
        "Both(A) <- (Pa(A) and Qa(A))\n",
        "Neg(X, Y) <- (Y is -X)\n",
        "ConsTail(T) <- Head([a, b | T])\n",
        "StarTail(T) <- Head([a, b, *T])\n",
    ])
    def test_operator_round_trips(self, src):
        assert_round_trips(src)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/shims/python -m pytest tests/test_reflection_render.py::TestOperators -x -q`
Expected: FAIL — `RenderError: cannot render term: Gt(...)` (operator nodes and lists not yet handled).

- [ ] **Step 3: Write minimal implementation**

Add module-level tables just above `class _ClauseRenderer` in `clausal/reflection.py`:

```python
# simple_ast operator class name → Python ast operator, for rendering.
_RENDER_BINOP_OPS = {
    "Add": ast.Add, "Sub": ast.Sub, "Mult": ast.Mult, "Div": ast.Div,
    "FloorDiv": ast.FloorDiv, "Mod": ast.Mod, "Pow": ast.Pow,
    "MatMult": ast.MatMult, "LShift": ast.LShift, "RShift": ast.RShift,
    "BitOr": ast.BitOr, "BitXor": ast.BitXor, "BitAnd": ast.BitAnd,
}
_RENDER_CMP_OPS = {
    "Lt": ast.Lt, "LtE": ast.LtE, "Gt": ast.Gt, "GtE": ast.GtE,
    "ArithEq": ast.Eq, "ArithNeq": ast.NotEq,
    "Unify": ast.Is, "DoesNotUnify": ast.IsNot,
    "in_": ast.In, "NotIn": ast.NotIn,
}
_RENDER_BOOL_OPS = {"And": ast.And, "Or": ast.Or}
_RENDER_UNARY_OPS = {
    "Not": ast.Not, "Negate": ast.USub, "UnaryPlus": ast.UAdd,
    "Invert": ast.Invert,
}
```

In `_ClauseRenderer.term`, add these branches BEFORE the final `raise RenderError` (and before the `ModuleDirective`/`PythonCode` guard is fine — order: after the `str` branch):

```python
        if isinstance(value, list):
            return ast.List(
                elts=[self.term(item) for item in value], ctx=ast.Load()
            )
        if isinstance(value, tuple):
            return ast.Tuple(
                elts=[self.term(item) for item in value], ctx=ast.Load()
            )
        if isinstance(value, dict):
            return ast.Dict(
                keys=[self.term(key) for key in value],
                values=[self.term(val) for val in value.values()],
            )
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            return self._operator_ast(value)
```

Add the operator renderer method to `_ClauseRenderer`:

```python
    def _operator_ast(self, node):
        """Raw ``simple_ast`` operator node → Python ``ast`` operator expr."""
        name = type(node).__name__
        if name in _RENDER_BINOP_OPS:
            return ast.BinOp(
                left=self.term(node.left),
                op=_RENDER_BINOP_OPS[name](),
                right=self.term(node.right),
            )
        if name in _RENDER_CMP_OPS:
            return ast.Compare(
                left=self.term(node.left),
                ops=[_RENDER_CMP_OPS[name]()],
                comparators=[self.term(node.right)],
            )
        if name in _RENDER_BOOL_OPS:
            return ast.BoolOp(
                op=_RENDER_BOOL_OPS[name](),
                values=[self.term(node.left), self.term(node.right)],
            )
        if name in _RENDER_UNARY_OPS:
            return ast.UnaryOp(
                op=_RENDER_UNARY_OPS[name](), operand=self.term(node.operand)
            )
        if name == "StarUnpack":
            return ast.Starred(value=self.term(node.value), ctx=ast.Load())
        raise RenderError(f"cannot render operator node: {name}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/shims/python -m pytest tests/test_reflection_render.py::TestOperators -x -q`
Expected: PASS (15 cases).

- [ ] **Step 5: Commit**

```bash
git add clausal/reflection.py tests/test_reflection_render.py
git commit -m "feat(reflection): render operator nodes, lists, tuples, dicts"
```

---

### Task 4: Nested compounds, kwargs, dict `get`, qualified names

**Files:**
- Modify: `clausal/reflection.py` (only if a gap surfaces — expect none)
- Test: `tests/test_reflection_render.py`

**Interfaces:**
- Consumes: Tasks 1 & 3.
- Produces: no new API (regression coverage for `Goal.kwargs`, nested `Goal` args, dotted names).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_reflection_render.py`:

```python
class TestCompoundAndKwargs:
    @pytest.mark.parametrize("src", [
        "Holds(State(A)) <- Check(A)\n",
        "Deep(Pp(Qq(Rr(X)))) <- Base(X)\n",
        "WithList(Pp([1, 2, 3])),\n",
        "Nested([Pp(X), Qq(Y)]),\n",
    ])
    def test_compound_round_trips(self, src):
        assert_round_trips(src)
```

- [ ] **Step 2: Run test to verify it passes**

Run: `PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/shims/python -m pytest tests/test_reflection_render.py::TestCompoundAndKwargs -x -q`
Expected: PASS — nested `Goal`s recurse through `term()`; lists recurse. If any case FAILS, inspect the mismatch message and add the missing `term()` branch (do NOT add speculative branches).

- [ ] **Step 3: (only if a case failed) Fix the specific gap**

If a keyword-bearing goal appears in the corpus later and fails, confirm `_goal_ast` emits `ast.keyword(arg=name, value=...)` with `arg=None` tolerated for `**` splat. No change expected for these fixtures.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/shims/python -m pytest tests/test_reflection_render.py::TestCompoundAndKwargs -x -q`
Expected: PASS (4 cases).

- [ ] **Step 5: Commit**

```bash
git add tests/test_reflection_render.py
git commit -m "test(reflection): render round-trips for nested compounds and lists"
```

---

### Task 5: IfThenElse → `ast.IfExp`

**Files:**
- Modify: `clausal/reflection.py` (add `IfThenElse` branch to `term()`)
- Test: `tests/test_reflection_render.py`

**Interfaces:**
- Consumes: Task 1.
- Produces: `IfThenElse` handling in `_ClauseRenderer.term`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_reflection_render.py`:

```python
class TestIfThenElse:
    @pytest.mark.parametrize("src", [
        "Pick(X, Y) <- (Y is (1 if X > 0 else 2))\n",
    ])
    def test_ite_round_trips(self, src):
        assert_round_trips(src)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/shims/python -m pytest tests/test_reflection_render.py::TestIfThenElse -x -q`
Expected: FAIL — `RenderError: cannot render term: IfThenElse(...)`.

First confirm the reified shape (field names) with a quick probe if uncertain:
`PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/shims/python -c "from clausal.reflection import reify_source, Clause; c=[i for i in reify_source('Pick(X, Y) <- (Y is (1 if X > 0 else 2))\n') if isinstance(i, Clause)][0]; print(repr(c.goals[0]))"`
Expected: shows `IfThenElse(condition=..., then=1, otherwise=2)`.

- [ ] **Step 3: Write minimal implementation**

In `_ClauseRenderer.term`, add before the operator/dataclass branch:

```python
        if isinstance(value, IfThenElse):
            return ast.IfExp(
                test=self.term(value.condition),
                body=self.term(value.then),
                orelse=self.term(value.otherwise),
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/shims/python -m pytest tests/test_reflection_render.py::TestIfThenElse -x -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add clausal/reflection.py tests/test_reflection_render.py
git commit -m "feat(reflection): render IfThenElse to ast.IfExp"
```

---

### Task 6: Escape (`++`) and FormatString (f-string)

**Files:**
- Modify: `clausal/reflection.py` (add `Escape`/`FormatString` branch to `term()`)
- Test: `tests/test_reflection_render.py`

**Interfaces:**
- Consumes: Task 1.
- Produces: `Escape`/`FormatString` handling in `_ClauseRenderer.term`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_reflection_render.py`:

```python
class TestEscapes:
    @pytest.mark.parametrize("src", [
        "Calc(X, Y) <- (Y is ++(X + 1))\n",
        "Calc2(X, Y, Z) <- (Z is ++(X * Y + 1))\n",
    ])
    def test_escape_round_trips(self, src):
        assert_round_trips(src)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/shims/python -m pytest tests/test_reflection_render.py::TestEscapes -x -q`
Expected: FAIL — `RenderError: cannot render term: Escape(...)`.

- [ ] **Step 3: Write minimal implementation**

In `_ClauseRenderer.term`, add before the final `raise RenderError` (and before the `ModuleDirective` guard):

```python
        if isinstance(value, Escape):
            # `++(<code>)`: the escaped expression text re-parsed and wrapped in
            # two adjacent unary `+` — ast.unparse emits `++(code)`, which the
            # reifier re-detects as an escape and re-collects the captured vars.
            inner = ast.parse(value.code, mode="eval").body
            return ast.UnaryOp(
                op=ast.UAdd(),
                operand=ast.UnaryOp(op=ast.UAdd(), operand=inner),
            )
        if isinstance(value, FormatString):
            return ast.parse(value.code, mode="eval").body
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/shims/python -m pytest tests/test_reflection_render.py::TestEscapes -x -q`
Expected: PASS (2 cases).

Note: `FormatString` rendering is best-effort — its round-trip is validated by the corpus sweep (Task 8). If no f-string fixture is easy to author, the `Escape` cases here are the required coverage; the `FormatString` branch is proven by the corpus.

- [ ] **Step 5: Commit**

```bash
git add clausal/reflection.py tests/test_reflection_render.py
git commit -m "feat(reflection): render Escape (++) and FormatString"
```

---

### Task 7: `ModuleDirective` / `PythonCode` raise `RenderError`

**Files:**
- Modify: `clausal/reflection.py` (the `ModuleDirective`/`PythonCode` guard from Task 1 already raises — this task tests it)
- Test: `tests/test_reflection_render.py`

**Interfaces:**
- Consumes: Task 1's guard.
- Produces: no new API.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_reflection_render.py`:

```python
class TestOutOfScope:
    def test_module_directive_raises(self):
        items = reify_source("-module(m)\n")
        directive = next(i for i in items if type(i).__name__ == "ModuleDirective")
        with pytest.raises(RenderError):
            render_source(directive)

    def test_python_code_raises(self):
        items = reify_source("def helper():\n    return 1\n")
        pycode = next(i for i in items if type(i).__name__ == "PythonCode")
        with pytest.raises(RenderError):
            render_source(pycode)
```

- [ ] **Step 2: Run test to verify it passes**

Run: `PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/shims/python -m pytest tests/test_reflection_render.py::TestOutOfScope -x -q`
Expected: PASS — Task 1's guard already raises `RenderError` for both. If a case FAILS because the reified item is not produced as expected, adjust the `next(...)` selector to match the actual `reify_source` output (probe first).

- [ ] **Step 3: (only if a case failed) Fix**

If `render_source` returns text instead of raising, confirm `render_ast` routes `ModuleDirective`/`PythonCode` through `term()` (non-Clause path) and that `term()`'s guard fires. No change expected.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/shims/python -m pytest tests/test_reflection_render.py::TestOutOfScope -x -q`
Expected: PASS (2 cases).

- [ ] **Step 5: Commit**

```bash
git add tests/test_reflection_render.py
git commit -m "test(reflection): render raises RenderError on directives and embedded Python"
```

---

### Task 8: Corpus round-trip sweep (skips if absent) — the completeness gate

**Files:**
- Test: `tests/test_reflection_render.py`

**Interfaces:**
- Consumes: the whole renderer.
- Produces: no API. This is the completeness proof a source-rewriting tool depends on.

- [ ] **Step 1: Write the test**

Append to `tests/test_reflection_render.py`:

```python
import glob
import os

CORPUS_DIR = os.environ.get("CLAUSAL_CORPUS_DIR", "")


def _corpus_files():
    if not CORPUS_DIR or not os.path.isdir(CORPUS_DIR):
        return []
    return sorted(glob.glob(os.path.join(CORPUS_DIR, "**", "*.clausal"), recursive=True))


@pytest.mark.skipif(not _corpus_files(), reason="CLAUSAL_CORPUS_DIR not set or absent")
@pytest.mark.parametrize("path", _corpus_files())
def test_corpus_clause_round_trips(path):
    """Every Clause in every file of an external corpus, if one is configured
    (via ``CLAUSAL_CORPUS_DIR``), renders and re-reifies identically.

    Only Clause items are exercised: every file opens with -module/-import_from
    which reify to ModuleDirective/PythonCode — node kinds the renderer
    deliberately raises on. A RenderError on a real clause is a hard failure
    (a silently-corrupt mutant would falsely 'survive' in a source-rewriting
    tool)."""
    try:
        items = reify_source(open(path, encoding="utf-8").read(), filename=path)
    except ReifyError as exc:
        pytest.skip(f"source not reifiable ({exc})")
    clauses = [i for i in items if isinstance(i, Clause)]
    if not clauses:
        pytest.skip("no clauses in file")
    for clause in clauses:
        rendered = render_source(clause)              # must not raise RenderError
        reparsed = [i for i in reify_source(rendered + "\n") if isinstance(i, Clause)]
        assert len(reparsed) == 1, f"{path}: render produced {len(reparsed)} clauses:\n{rendered}"
        assert strip_positions(reparsed[0]) == strip_positions(clause), (
            f"{path}: round-trip mismatch\n  rendered: {rendered!r}"
        )
```

- [ ] **Step 2: Run the sweep**

Run: `PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/shims/python -m pytest tests/test_reflection_render.py -q -k corpus 2>&1 | tail -40`
Expected: initially may reveal node kinds not yet covered (e.g. `StructuralEq`, `CompareChain`, `Slice`, `Evaluate`, `MatMult`, keyword goals, `**` splat). Each surfaces as either a `RenderError` or a round-trip mismatch, naming the file and rendered text.

- [ ] **Step 3: Triage and extend the renderer per uncovered node kind**

For EACH distinct failure:
1. Probe the reified shape: `reify_source` the offending clause, `repr` the goal/term.
2. If it's an operator node missing from the dispatch tables, add it to the correct `_RENDER_*_OPS` table (e.g. `"StructuralEq": ast.Eq` only if `==` truly reifies to it — VERIFY the surface first; if `==`→`ArithEq` already, `StructuralEq` needs a different surface, so investigate what surface produces it before mapping).
3. If it's a structural node (`CompareChain`, `Slice`), add a dedicated `term()`/`_operator_ast` branch that builds the matching `ast` node, then re-probe its round-trip.
4. Add a targeted fixture to the relevant `Test*` class capturing that node kind (so the fixture set grows to cover what the corpus found — the fixture set is the smoke test, the corpus is the gate).
5. Re-run the sweep. Repeat until zero `RenderError` and zero mismatches, OR a node kind is genuinely out of scope (document it: `pytest.skip` with a specific reason and a note in the design doc's "Out of scope").

- [ ] **Step 4: Run the full suite green**

Run: `PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/shims/python -m pytest tests/test_reflection_render.py -q 2>&1 | tail -20`
Expected: PASS (all fixture classes + corpus sweep), zero `RenderError` on real clauses.

Also run the existing reflection suite to confirm no regression:
Run: `PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/shims/python -m pytest tests/test_reflection.py tests/test_reflection_sugar.py tests/test_reflection_builtins.py -q 2>&1 | tail -10`
Expected: PASS (unchanged).

- [ ] **Step 5: Commit**

```bash
git add clausal/reflection.py tests/test_reflection_render.py
git commit -m "test(reflection): corpus round-trip sweep + coverage for node kinds it surfaced"
```

---

### Task 9: Update todo status + design doc, final verification

**Files:**
- Modify: `todo/reified-term-to-source-renderer.md` (mark DONE, note corpus result)
- Modify: `docs/superpowers/specs/2026-07-20-reified-term-renderer-design.md` (record any node kinds found out-of-scope)

**Interfaces:** none.

- [ ] **Step 1: Update the todo**

Change `STATUS: OPEN` → `STATUS: DONE (2026-07-20)` and add a one-line result: how many corpus files/clauses swept, and any node kinds deferred with reason.

- [ ] **Step 2: Record out-of-scope node kinds in the design doc**

If Task 8 deferred any node kind, add it under "Out of scope" with the reason. If none, add a line: "Corpus sweep: N files / M clauses round-trip clean, no deferrals."

- [ ] **Step 3: Full verification**

Run: `PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/shims/python -m pytest tests/test_reflection_render.py tests/test_reflection.py -q 2>&1 | tail -10`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add todo/reified-term-to-source-renderer.md docs/superpowers/specs/2026-07-20-reified-term-renderer-design.md
git commit -m "docs(todo): reified-term renderer done — corpus round-trip clean"
```

---

## Self-Review

**Spec coverage:**
- `render_ast` primitive + `render_source` wrapper → Tasks 1, 3, 5, 6 (all term kinds), `render_source` in Task 1. ✓
- `RenderError` loud on unhandled → Task 1 (guard) + Task 7 (test). ✓
- Clause fact/rule/multi-goal → Tasks 1, 2. ✓
- Goal/Variable/Atom (dotted) → Task 1. ✓
- Operator nodes incl. cons-tail `BitOr` vs star-tail `StarUnpack` → Task 3 (explicit distinct fixtures). ✓
- IfThenElse → Task 5. ✓
- Escape (with captured vars) / FormatString → Task 6. ✓
- ModuleDirective/PythonCode raise → Tasks 1 + 7. ✓
- Fixture set (always runs) → Tasks 1–7. ✓
- Corpus sweep, Clause-filtered, skips if absent, MUST run & pass → Task 8. ✓
- Recurse on children → every `term()`/`_operator_ast`/`_goal_ast` recurses. ✓
- `ast.fix_missing_locations` → `render_ast` (Task 1). ✓
- Out of scope: `clause_source/2` predicate not built → not in any task. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code; every command has expected output. Task 8 Step 3 is intentionally iterative (triage loop) but names exact probe steps and the termination condition (zero RenderError/mismatch). ✓

**Type consistency:** `render_ast`/`render_source`/`RenderError`, `_ClauseRenderer.{clause,goal,term,_name_ast,_goal_ast,_operator_ast}`, `strip_positions`, `assert_round_trips`, `only_clause`, `_RENDER_{BINOP,CMP,BOOL,UNARY}_OPS` used consistently across tasks. `render_ast` returns `ast.Expr` for Clause / expression node otherwise; `render_source` branches on `ast.Expr`. ✓
