# Goal-position `--` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In Python hosted by a `.clausal` file, `--goal` in the test of `if`/`elif`/`while`, in the iterable of `for`, and under `not` in those tests RUNS the goal and exports its logic variables as plain Python locals; everywhere else `--` keeps building the term.

**Architecture:** Two small runtime helpers in `clausal/logic/seam.py` (`once_bind`, `each`, plus an export check) are injected into every module namespace like `$seam`/`$text`. The Embed transformer (`clausal/templating/term_rewriting.py`) gains `visit_If`, `visit_While` and `visit_For` that recognise a `--` operand in those positions, reuse the existing seam term lowering, and emit ordinary Python: fresh `Var()` assignments before the statement, a helper call as the test/iterable, and one assignment per exported variable. Strict soundness: a WFS-conditional answer raises, an attributed unbound export raises.

**Tech Stack:** Python 3.13, `ast.NodeTransformer`, pytest. Engine APIs used: `clausal.logic.solve.solve`, `_deref_walk`, `_tabled_entry_for_goal`; `clausal.logic.tabling.make_subgoal_key`; `clausal.logic.variables.deref`, `is_var`; `clausal.terms.Undefined`, `Var`, `Trail`.

**Spec:** `docs/superpowers/specs/2026-09-08-goal-position-seam-design.md` (read it first; the plan argues from it).

## Global Constraints

- Work on branch `feat/goal-position-seam-2026-09-08` in the worktree that carries the seam and text-crossing branches (the plan's paths are relative to that worktree). No C changes; no `build_ext`.
- Run tests with `/workspace/clausal/venv/bin/python -m pytest -q --no-header -p no:cacheprovider <files>` FROM the worktree root (cwd wins over the venv's `.pth`).
- Which names are logic variables is decided ONLY by `_is_logic_var_name` in `term_rewriting.py`; never test case or shape yourself.
- Emitted code: one assignment per exported variable, never a tuple built then unpacked; no stored trail. Seam-internal locals are spelled `$v_<NAME>` (a `$` name cannot collide with user code).
- Every helper name generated code references must be in `INJECTED_RUNTIME_BUILTINS` (`clausal/logic/compiler/predicate.py`, near `"$seam"`).
- Commit messages: neutral wording, no downstream project names; end with the two attribution trailers used by the seam commits (`git log -3 --format=%B` shows them).
- Gate before the final commit: full suite `tests/` failing-name set identical to the branch base (`git stash` is forbidden in this shared repo; compare name lists, not counts).

---

### Task 1: Runtime helpers — `once_bind`, `each`, `export`, and the two errors

**Files:**
- Modify: `clausal/logic/seam.py` (append after `text_of`)
- Modify: `clausal/logic/compiler/predicate.py` (the `INJECTED_RUNTIME_BUILTINS` dict, next to `"$text"`)
- Test: `tests/test_goal_position_seam.py` (new)

**Interfaces:**
- Produces:
  - `class UndefinedAnswer(Exception)`, `class ResidualConstraints(Exception)`
  - `export(var) -> Any` — the fully dereferenced copy of `var`; raises `ResidualConstraints` if `var` is unbound and attributed.
  - `once_bind(goal, module_globals: dict) -> bool` — runs `goal` in `module_globals["$module"]`; True on the first unconditional answer with the goal's variables left bound for the caller's `export` lines; False on failure; raises `UndefinedAnswer` on a conditional answer.
  - `each(goal, variables: tuple, module_globals: dict) -> Iterator` — yields per unconditional answer: the exported value when `len(variables) == 1`, else a tuple of exported values in `variables` order.
  - Injected names: `"$once_bind"`, `"$each"`, `"$export"`.

- [ ] **Step 1: Write the failing tests (helpers called directly, no rewriter yet)**

```python
# tests/test_goal_position_seam.py
"""Goal-position ``--``: if/elif/while tests, for iterables and ``not`` run
the goal and export its variables as plain locals (spec:
docs/superpowers/specs/2026-09-08-goal-position-seam-design.md)."""
import os
import tempfile

import pytest

from clausal.import_hook import _load_module


def _load_inline(name: str, source: str):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, f"{name}.clausal")
        with open(path, "w") as fh:
            fh.write(source)
        return _load_module(name, path)


RULEBASE = (
    "-module({name}, [decide(P, V), verdict(S, IDS), small, large, permitted, prohibited, r1, r2])\n"
    "-double_quotes(chars)\n"
    "decide(small, verdict(permitted, [r1, r2]))\n"
    "decide(large, verdict(prohibited, [r1]))\n"
    "decide(large, verdict(prohibited, [r2]))\n"
)


class TestHelpersDirectly:
    def test_once_bind_binds_the_first_answer_and_export_copies_it(self):
        from clausal import Var
        from clausal.logic.seam import once_bind, export
        mod = _load_inline("_gp_h1", RULEBASE.format(name="_gp_h1"))
        S, IDS = Var(), Var()
        goal = ("decide", ("large",), ("verdict", S, IDS))
        assert once_bind(goal, mod.__dict__) is True
        assert export(S) == ("prohibited",) and export(IDS) == [("r1",)]

    def test_once_bind_is_false_on_failure(self):
        from clausal import Var
        from clausal.logic.seam import once_bind
        mod = _load_inline("_gp_h2", RULEBASE.format(name="_gp_h2"))
        assert once_bind(("decide", ("tiny",), Var()), mod.__dict__) is False

    def test_each_yields_every_answer_as_a_tuple_or_a_bare_value(self):
        from clausal import Var
        from clausal.logic.seam import each
        mod = _load_inline("_gp_h3", RULEBASE.format(name="_gp_h3"))
        S, IDS = Var(), Var()
        goal = ("decide", ("large",), ("verdict", S, IDS))
        assert list(each(goal, (S, IDS), mod.__dict__)) == [
            (("prohibited",), [("r1",)]), (("prohibited",), [("r2",)])]
        V = Var()
        assert list(each(("decide", ("small",), V), (V,), mod.__dict__)) == [
            ("verdict", ("permitted",), [("r1",), ("r2",)])]

    def test_export_refuses_an_attributed_unbound_variable(self):
        from clausal import Var, Trail
        from clausal.logic.variables import put_attr
        from clausal.logic.seam import export, ResidualConstraints
        x = Var()
        put_attr(x, "dom", (1, 3), Trail())
        with pytest.raises(ResidualConstraints):
            export(x)
        y = Var()
        assert export(y) is y          # free and unattributed: the variable itself

    def test_a_conditional_answer_raises_undefined_answer(self):
        from clausal import Var
        from clausal.logic.seam import each, once_bind, UndefinedAnswer
        mod = _load_inline("_gp_h5", (
            "-module(_gp_h5, [move(A, B), wins(X), a, b, c])\n"
            "-double_quotes(chars)\n"
            "-table(wins/1)\n"
            "move(a, b),\n"
            "move(b, c),\n"
            "move(c, a),\n"
            "wins(X) <- (move(X, Y), not wins(Y))\n"
        ))
        with pytest.raises(UndefinedAnswer):
            list(each(("wins", ("a",)), (), mod.__dict__))
        with pytest.raises(UndefinedAnswer):
            once_bind(("wins", ("a",)), mod.__dict__)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/workspace/clausal/venv/bin/python -m pytest -q --no-header -p no:cacheprovider tests/test_goal_position_seam.py`
Expected: FAIL with `ImportError: cannot import name 'once_bind' from 'clausal.logic.seam'` (every test).

- [ ] **Step 3: Implement the helpers**

Append to `clausal/logic/seam.py`:

```python
class UndefinedAnswer(Exception):
    """A goal in goal position produced a WFS-conditional (undefined) answer.

    The sugar is strict: it neither skips the answer nor takes it as true.
    Truth-aware code uses ``clausal.query_wfs``.
    """


class ResidualConstraints(Exception):
    """An exported variable is still unbound and carries constraint attributes.

    Exports are answers; a constraint store crossing a seam is the lower
    level (``solve`` with an explicit ``Trail``) or, once it exists,
    ``copy_term/3`` inside the goal.
    """


def export(var: Any) -> Any:
    """The fully dereferenced copy of *var*'s value for Python to keep."""
    from clausal.logic.solve import _deref_walk
    from clausal.logic.variables import deref, is_var
    d = deref(var)
    if is_var(d) and getattr(d, "attrs", None):
        raise ResidualConstraints(
            f"--: exported variable is unbound and constrained "
            f"({sorted(d.attrs)}); exports are answers. Keep the store alive "
            f"with an explicit Trail, or ask for the residue inside the goal")
    return _deref_walk(var)


def _module_of(module_globals: dict):
    try:
        return module_globals["$module"]
    except KeyError:
        raise NameError(
            "--: goal position needs the host module's `$module`; a plain "
            ".py file never reaches the rewriter — host this code in a "
            ".clausal file") from None


def _definite_answers(goal: Any, module) -> "Iterator[None]":
    """Yield once per UNCONDITIONAL answer of *goal*; raise UndefinedAnswer
    on a conditional one.

    A single tabled-predicate goal can only be judged after SLG completes,
    so it is collected first (the same discipline as ``query_wfs``); every
    other goal shape streams.
    """
    from clausal.logic.solve import solve, _tabled_entry_for_goal
    from clausal.terms import Trail, Undefined
    trail = Trail()
    entry, goal_args = _tabled_entry_for_goal(goal, module, trail)
    if entry is None:
        yield from solve(goal, module, trail)
        return
    from clausal.logic.tabling import make_subgoal_key
    from clausal.logic.variables import deref
    marks = []
    for _ in solve(goal, module, trail):
        cand = [deref(a) for a in goal_args]
        idx = entry._answer_index.get(make_subgoal_key(cand, None))
        if idx is not None and entry.truth_value(idx) is Undefined:
            raise UndefinedAnswer(
                f"--: {goal!r} has a conditional (undefined) answer; use "
                f"clausal.query_wfs for truth values and delays")
        yield


def once_bind(goal: Any, module_globals: dict) -> bool:
    """True on the first unconditional answer, leaving the goal's variables
    bound for the caller's ``$export`` lines; False if the goal fails."""
    for _ in _definite_answers(goal, _module_of(module_globals)):
        return True
    return False


def each(goal: Any, variables: tuple, module_globals: dict):
    """Yield the exported values of *variables* once per unconditional answer:
    the bare value for one variable, else a tuple in *variables* order."""
    single = len(variables) == 1
    for _ in _definite_answers(goal, _module_of(module_globals)):
        if single:
            yield export(variables[0])
        else:
            yield tuple(export(v) for v in variables)
```

Then in `clausal/logic/compiler/predicate.py`, next to the existing `"$text": _text_of,` line, add:

```python
    # Goal-position `--`: if/for/while/not run the goal (clausal.logic.seam).
    "$once_bind": _once_bind,
    "$each": _each,
    "$export": _export,
```

and extend the import line at the top of that block to
`from clausal.logic.seam import seam_term as _seam_term, text_of as _text_of, once_bind as _once_bind, each as _each, export as _export`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `/workspace/clausal/venv/bin/python -m pytest -q --no-header -p no:cacheprovider tests/test_goal_position_seam.py`
Expected: 5 passed. If `test_a_conditional_answer_raises_undefined_answer` fails because `once_bind` streamed a tabled goal without judging it, check that `_tabled_entry_for_goal` recognised the cell goal `("wins", ("a",))` — it must return a non-None entry; if it returns None for cell goals, extend its cell branch (it already handles `Compound` and reified `Call` shapes; a cell is `(functor, *args)`).

- [ ] **Step 5: Commit**

```bash
git add clausal/logic/seam.py clausal/logic/compiler/predicate.py tests/test_goal_position_seam.py
git commit -m "seam: once_bind/each/export runtime helpers for goal-position --"
```

---

### Task 2: `if` / `elif` — run the goal once, export variables as locals

**Files:**
- Modify: `clausal/templating/term_rewriting.py` — `EmbedTransformer.visit_UnaryOp` (the `--` branch, search for `# THE SEAM: ``--term`` yields`) and a new `visit_If`
- Test: `tests/test_goal_position_seam.py`

**Interfaces:**
- Consumes: `$once_bind(goal, globals())`, `$export(var)` from Task 1.
- Produces: `EmbedTransformer._seam_goal(expression, anchor) -> (term_ast, fresh_names)` — the seam lowering of `expression` as a GOAL: returns the `$seam(...)` call AST and the ordered fresh logic-variable names it binds through `$v_<NAME>` locals (not through walruses). `EmbedTransformer._goal_operand(test) -> (expression, negated) | None` — recognises `--X` and `not --X` in a test.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_goal_position_seam.py`:

```python
class TestIf:
    def test_if_binds_locals_on_success_and_they_survive_the_block(self):
        mod = _load_inline("_gp_if1", RULEBASE.format(name="_gp_if1") + (
            "def first(profile):\n"
            "    if --decide(++profile, verdict(S, IDS)):\n"
            "        seen = True\n"
            "    return S, IDS\n"
        ))
        assert mod.first(("large",)) == (("prohibited",), [("r1",)])

    def test_if_assigns_nothing_on_failure(self):
        mod = _load_inline("_gp_if2", RULEBASE.format(name="_gp_if2") + (
            "def first(profile):\n"
            "    if --decide(++profile, verdict(S, IDS)):\n"
            "        return S\n"
            "    return S\n"
        ))
        with pytest.raises(UnboundLocalError):
            mod.first(("tiny",))

    def test_if_with_a_unification_pattern(self):
        mod = _load_inline("_gp_if3", RULEBASE.format(name="_gp_if3") + (
            "def parts(answer):\n"
            "    if --(verdict(S, IDS) is ++answer):\n"
            "        return S, IDS\n"
            "    return None\n"
        ))
        assert mod.parts(("verdict", ("permitted",), [])) == (("permitted",), [])
        assert mod.parts(("other", 1)) is None

    def test_elif_and_a_conjunction(self):
        mod = _load_inline("_gp_if4", RULEBASE.format(name="_gp_if4") + (
            "def which(profile):\n"
            "    if --decide(++profile, verdict(permitted, IDS)):\n"
            "        return ('yes', IDS)\n"
            "    elif --(decide(++profile, V), V is verdict(prohibited, IDS)):\n"
            "        return ('no', IDS)\n"
            "    return 'none'\n"
        ))
        assert mod.which(("small",)) == ("yes", [("r1",), ("r2",)])
        assert mod.which(("large",)) == ("no", [("r1",)])
        assert mod.which(("tiny",)) == "none"

    def test_term_positions_are_unchanged(self):
        mod = _load_inline("_gp_if5", RULEBASE.format(name="_gp_if5") + (
            "def term():\n"
            "    x = --decide(small, V)\n"
            "    return x[0], x[1]\n"
        ))
        assert mod.term()[0] == "decide" and mod.term()[1] == ("small",)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/workspace/clausal/venv/bin/python -m pytest -q --no-header -p no:cacheprovider tests/test_goal_position_seam.py -k TestIf`
Expected: the first four FAIL (a seam in an `if` test today yields the term, a non-empty tuple, so `if` is always true and `S` is never assigned: `NameError`/`UnboundLocalError` or wrong values); `test_term_positions_are_unchanged` PASSES already.

- [ ] **Step 3: Refactor the `--` branch into `_seam_goal`, then add `visit_If`**

In `EmbedTransformer`, replace the body of the `--` case in `visit_UnaryOp` (from `outer = set().union(...)` through the final `return replace(Call(... "$seam" ...))`) with a call to a new method, keeping term-position behaviour byte-for-byte:

```python
                if (
                    unary_op.col_offset == unary_op.operand.col_offset - 1
                    and unary_op.lineno == unary_op.operand.lineno
                ):
                    term_ast, fresh = transformer._seam_term_ast(expression, unary_op)
                    if fresh:
                        # term position: bind the fresh variables inline
                        binds = [transformer._var_bind(n, unary_op) for n in fresh]
                        term_ast = replace(
                            Subscript(
                                value=replace(Tuple(elts=[*binds, term_ast], ctx=Load()), unary_op),
                                slice=replace(Constant(value=-1), unary_op),
                                ctx=Load(),
                            ),
                            unary_op,
                        )
                    return transformer._seam_call(term_ast, unary_op)
```

and add these methods to `EmbedTransformer` (next to `_make_term_transformer`):

```python
    def _seam_term_ast(transformer, expression, anchor):
        """Lower *expression* through a seam TermTransformer.  Returns
        ``(term_ast, fresh)``: the lowered term and the ordered logic-variable
        names this seam introduces (already-bound names of an enclosing seam
        are excluded).  The caller decides how to bind ``fresh``."""
        outer = set().union(*transformer._seam_bound) if transformer._seam_bound else set()
        fresh = [n for n in _collect_logic_var_names(expression) if n not in outer]
        term_tf = transformer._make_term_transformer(seam=True)
        term_tf.seen_vars.update(outer)
        term_tf.seen_vars.update(fresh)
        transformer._seam_bound.append(outer | set(fresh))
        try:
            return term_tf.visit(expression), fresh
        finally:
            transformer._seam_bound.pop()

    def _var_bind(transformer, name, anchor):
        """``(NAME := Var())`` — the term-position binding of one variable."""
        return replace(NamedExpr(
            target=replace(Name(id=name, ctx=Store()), anchor),
            value=replace(Call(func=replace(Name(id="Var", ctx=Load()), anchor),
                               args=[], keywords=[]), anchor),
        ), anchor)

    def _seam_call(transformer, term_ast, anchor):
        seam_kw = ([keyword(arg="loose", value=Constant(value=True))]
                   if transformer._implicit_atoms_default else [])
        return replace(
            Call(func=Name(id="$seam", ctx=Load()),
                 args=[term_ast, Call(func=Name(id="globals", ctx=Load()), args=[], keywords=[])],
                 keywords=seam_kw),
            anchor,
        )

    # ── goal position ──────────────────────────────────────────────────
    @staticmethod
    def _goal_operand(test):
        """``--X`` -> (X, False); ``not --X`` -> (X, True); else None.
        Adjacency of the two ``-`` is required, as for term position."""
        negated = False
        node = test
        if isinstance(node, UnaryOp) and isinstance(node.op, Not):
            negated, node = True, node.operand
        if (isinstance(node, UnaryOp) and isinstance(node.op, USub)
                and isinstance(node.operand, UnaryOp) and isinstance(node.operand.op, USub)
                and node.col_offset == node.operand.col_offset - 1
                and node.lineno == node.operand.lineno):
            return node.operand.operand, negated
        return None

    def _goal_seam(transformer, expression, anchor):
        """Lower a GOAL: returns ``(pre_stmts, goal_ast, fresh)`` where
        ``pre_stmts`` assign ``$v_<NAME> = Var()`` for every fresh variable
        and ``goal_ast`` is the ``$seam(...)`` call with those names in
        place of the variables."""
        term_ast, fresh = transformer._seam_term_ast(expression, anchor)
        rename = {n: f"$v_{n}" for n in fresh}

        class _Rename(NodeTransformer):
            def visit_Name(self, node):
                if node.id in rename and isinstance(node.ctx, Load):
                    return replace(Name(id=rename[node.id], ctx=Load()), node)
                return node
        goal_ast = _Rename().visit(term_ast)
        pre = [
            replace(Assign(
                targets=[replace(Name(id=rename[n], ctx=Store()), anchor)],
                value=replace(Call(func=replace(Name(id="Var", ctx=Load()), anchor),
                                   args=[], keywords=[]), anchor),
            ), anchor)
            for n in fresh
        ]
        for stmt in pre:
            fix_missing_locations(stmt)
        return pre, transformer._seam_call(goal_ast, anchor), fresh

    def _export_stmts(transformer, names, anchor):
        """``NAME = $export($v_NAME)`` — one assignment per exported name."""
        out = []
        for n in names:
            out.append(replace(Assign(
                targets=[replace(Name(id=n, ctx=Store()), anchor)],
                value=replace(Call(func=replace(Name(id="$export", ctx=Load()), anchor),
                                   args=[replace(Name(id=f"$v_{n}", ctx=Load()), anchor)],
                                   keywords=[]), anchor),
            ), anchor))
        return out

    def _globals_call(transformer, anchor):
        return replace(Call(func=Name(id="globals", ctx=Load()), args=[], keywords=[]), anchor)

    def visit_If(transformer, node):
        found = transformer._goal_operand(node.test)
        if found is None:
            return transformer.generic_visit(node)
        expression, negated = found
        pre, goal_ast, fresh = transformer._goal_seam(expression, node.test)
        test = replace(Call(func=Name(id="$once_bind", ctx=Load()),
                            args=[goal_ast, transformer._globals_call(node.test)],
                            keywords=[]), node.test)
        if negated:
            test = replace(UnaryOp(op=Not(), operand=test), node.test)
            exports = []
        else:
            exports = transformer._export_stmts(fresh, node.test)
        node.test = test
        node.body = exports + [transformer.visit(s) for s in node.body]
        # ``elif`` is an If nested in orelse: visit it so it gets the same treatment.
        new_orelse = []
        for s in node.orelse:
            r = transformer.visit(s)
            new_orelse.extend(r if isinstance(r, list) else [r])
        node.orelse = new_orelse
        fix_missing_locations(node)
        return pre + [node]
```

Note: `_goal_seam` binds `$v_<NAME>` locals for fresh variables; inside the goal the seam still references `Name(NAME)` so the rename pass swaps them. The `$seam` call keeps its `loose` keyword behaviour.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `/workspace/clausal/venv/bin/python -m pytest -q --no-header -p no:cacheprovider tests/test_goal_position_seam.py tests/test_seam_operator.py tests/test_hosted_text_crossing.py`
Expected: all pass (the seam-operator suite guards term-position behaviour).

- [ ] **Step 5: Commit**

```bash
git add clausal/templating/term_rewriting.py tests/test_goal_position_seam.py
git commit -m "seam: if/elif --goal runs the goal once and exports its variables as locals"
```

---

### Task 3: `not --goal` exports nothing

**Files:**
- Modify: `clausal/templating/term_rewriting.py` — `visit_If` already handles `negated`; this task pins it and the `not` inside `elif`.
- Test: `tests/test_goal_position_seam.py`

- [ ] **Step 1: Write the failing test**

```python
class TestNot:
    def test_not_is_true_exactly_when_the_goal_fails_and_exports_nothing(self):
        mod = _load_inline("_gp_not1", RULEBASE.format(name="_gp_not1") + (
            "def absent(profile):\n"
            "    if not --decide(++profile, verdict(S, _)):\n"
            "        return 'absent'\n"
            "    return 'present'\n"
            "def leaks(profile):\n"
            "    if not --decide(++profile, verdict(S, _)):\n"
            "        return S\n"
        ))
        assert mod.absent(("tiny",)) == "absent"
        assert mod.absent(("small",)) == "present"
        with pytest.raises(UnboundLocalError):
            mod.leaks(("tiny",))
```

- [ ] **Step 2: Run to verify it fails or passes**

Run: `/workspace/clausal/venv/bin/python -m pytest -q --no-header -p no:cacheprovider tests/test_goal_position_seam.py -k TestNot`
Expected: PASS if Task 2's `negated` path is complete; if `leaks` returns a value instead of raising, `visit_If` is exporting under `not` — fix so `exports = []` when `negated`.

- [ ] **Step 3: Commit**

```bash
git add tests/test_goal_position_seam.py clausal/templating/term_rewriting.py
git commit -m "seam: not --goal is a pure failure test and exports nothing"
```

---

### Task 4: `for TARGETS in --goal` — every solution, targets bound per solution

**Files:**
- Modify: `clausal/templating/term_rewriting.py` — new `visit_For` in `EmbedTransformer`
- Test: `tests/test_goal_position_seam.py`

**Interfaces:**
- Consumes: `$each(goal, (vars...), globals())` from Task 1; `_goal_seam` from Task 2.

- [ ] **Step 1: Write the failing tests**

```python
class TestFor:
    def test_for_yields_every_solution_and_leaves_the_last_values(self):
        mod = _load_inline("_gp_for1", RULEBASE.format(name="_gp_for1") + (
            "def all_ids(profile):\n"
            "    out = []\n"
            "    for S, IDS in --decide(++profile, verdict(S, IDS)):\n"
            "        out.append((S, IDS))\n"
            "    return out, S\n"
        ))
        out, last = mod.all_ids(("large",))
        assert out == [(("prohibited",), [("r1",)]), (("prohibited",), [("r2",)])]
        assert last == ("prohibited",)

    def test_a_single_target_gets_the_bare_value(self):
        mod = _load_inline("_gp_for2", RULEBASE.format(name="_gp_for2") + (
            "def verdicts(profile):\n"
            "    out = []\n"
            "    for V in --decide(++profile, V):\n"
            "        out.append(V)\n"
            "    return out\n"
        ))
        assert mod.verdicts(("small",)) == [("verdict", ("permitted",), [("r1",), ("r2",)])]

    def test_a_goal_variable_that_is_not_a_target_is_not_exported(self):
        mod = _load_inline("_gp_for3", RULEBASE.format(name="_gp_for3") + (
            "def only_status(profile):\n"
            "    for S in --decide(++profile, verdict(S, IDS)):\n"
            "        pass\n"
            "    return IDS\n"
        ))
        with pytest.raises((UnboundLocalError, NameError)):
            mod.only_status(("large",))

    def test_a_target_not_in_the_goal_is_a_load_time_syntax_error(self):
        with pytest.raises(SyntaxError, match="X"):
            _load_inline("_gp_for4", RULEBASE.format(name="_gp_for4") + (
                "def bad(profile):\n"
                "    for S, X in --decide(++profile, verdict(S, _)):\n"
                "        pass\n"
            ))

    def test_a_non_name_target_is_a_load_time_syntax_error(self):
        with pytest.raises(SyntaxError):
            _load_inline("_gp_for5", RULEBASE.format(name="_gp_for5") + (
                "def bad(profile, box):\n"
                "    for box.S in --decide(++profile, verdict(S, _)):\n"
                "        pass\n"
            ))

    def test_values_are_copies_per_solution(self):
        mod = _load_inline("_gp_for6", RULEBASE.format(name="_gp_for6") + (
            "def mutate(profile):\n"
            "    out = []\n"
            "    for IDS in --decide(++profile, verdict(_, IDS)):\n"
            "        IDS.append(('x',))\n"
            "        out.append(len(IDS))\n"
            "    return out\n"
        ))
        assert mod.mutate(("large",)) == [2, 2]

    def test_break_stops_the_search(self):
        mod = _load_inline("_gp_for7", RULEBASE.format(name="_gp_for7") + (
            "def first(profile):\n"
            "    for IDS in --decide(++profile, verdict(_, IDS)):\n"
            "        break\n"
            "    return IDS\n"
        ))
        assert mod.first(("large",)) == [("r1",)]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/workspace/clausal/venv/bin/python -m pytest -q --no-header -p no:cacheprovider tests/test_goal_position_seam.py -k TestFor`
Expected: FAIL — iterating a term today iterates the cell's elements.

- [ ] **Step 3: Implement `visit_For`**

Add to `EmbedTransformer` after `visit_If`:

```python
    def visit_For(transformer, node):
        found = transformer._goal_operand(node.iter)
        if found is None or found[1]:
            # ``for x in not --goal`` is not a goal position: leave it to Python.
            return transformer.generic_visit(node)
        expression, _ = found
        # Targets: a Name, or a Tuple of Names, each a variable of the goal.
        if isinstance(node.target, Name):
            targets = [node.target.id]
        elif isinstance(node.target, Tuple) and all(isinstance(e, Name) for e in node.target.elts):
            targets = [e.id for e in node.target.elts]
        else:
            raise SyntaxError(
                f"{transformer._filename}:{node.lineno}: `for ... in --goal` "
                f"binds plain names (a name or a tuple of names); got "
                f"{unparse(node.target)}")
        pre, goal_ast, fresh = transformer._goal_seam(expression, node.iter)
        goal_vars = set(_collect_logic_var_names(expression))
        for t in targets:
            if t not in goal_vars:
                raise SyntaxError(
                    f"{transformer._filename}:{node.lineno}: `{t}` is not a "
                    f"variable of the goal `{unparse(expression)}`")
        var_refs = replace(Tuple(
            elts=[replace(Name(id=f"$v_{t}", ctx=Load()), node.iter) for t in targets],
            ctx=Load()), node.iter)
        node.iter = replace(Call(func=Name(id="$each", ctx=Load()),
                                 args=[goal_ast, var_refs, transformer._globals_call(node.iter)],
                                 keywords=[]), node.iter)
        node.body = [transformer.visit(s) for s in node.body]
        node.orelse = [transformer.visit(s) for s in node.orelse]
        fix_missing_locations(node)
        return pre + [node]
```

`unparse` is `ast.unparse`; the module does `from ast import *`, so it is in scope. A target that is a variable of an ENCLOSING seam (in `transformer._seam_bound`) is not fresh here; `_goal_seam` only renames fresh names, so such a target would reference the enclosing seam's variable — refuse it with the same "not a variable of the goal" error by checking `t in fresh` rather than `t in goal_vars` (a `for` never shares with an outer seam, spec §4).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `/workspace/clausal/venv/bin/python -m pytest -q --no-header -p no:cacheprovider tests/test_goal_position_seam.py tests/test_seam_operator.py`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add clausal/templating/term_rewriting.py tests/test_goal_position_seam.py
git commit -m "seam: for TARGETS in --goal iterates every solution, binding targets per solution"
```

---

### Task 5: `while --goal` re-runs the goal per iteration

**Files:**
- Modify: `clausal/templating/term_rewriting.py` — new `visit_While`
- Test: `tests/test_goal_position_seam.py`

- [ ] **Step 1: Write the failing test**

```python
class TestWhile:
    def test_while_reruns_the_goal_each_iteration(self):
        mod = _load_inline("_gp_while1", (
            "-module(_gp_while1, [next(A, B), a, b, c])\n"
            "-double_quotes(chars)\n"
            "next(a, b),\n"
            "next(b, c),\n"
            "def walk(start):\n"
            "    cur = start\n"
            "    path = [cur]\n"
            "    while --next(++cur, N):\n"
            "        cur = N\n"
            "        path.append(cur)\n"
            "    return path\n"
        ))
        assert mod.walk(("a",)) == [("a",), ("b",), ("c",)]
```

- [ ] **Step 2: Run to verify it fails**

Run: `/workspace/clausal/venv/bin/python -m pytest -q --no-header -p no:cacheprovider tests/test_goal_position_seam.py -k TestWhile`
Expected: FAIL (an infinite loop guarded by pytest's timeout, or a wrong path) — if it hangs, run with `timeout 60`.

- [ ] **Step 3: Implement `visit_While`**

The fresh variables must be re-created every iteration, so the `Var()` assignments go INSIDE the loop test. Emit the test as a tuple-index expression that binds then calls — this is the one place the spec allows a container, because a `while` test is a single expression:

```python
    def visit_While(transformer, node):
        found = transformer._goal_operand(node.test)
        if found is None:
            return transformer.generic_visit(node)
        expression, negated = found
        pre, goal_ast, fresh = transformer._goal_seam(expression, node.test)
        call = replace(Call(func=Name(id="$once_bind", ctx=Load()),
                            args=[goal_ast, transformer._globals_call(node.test)],
                            keywords=[]), node.test)
        if fresh:
            binds = [replace(NamedExpr(
                target=replace(Name(id=f"$v_{n}", ctx=Store()), node.test),
                value=replace(Call(func=replace(Name(id="Var", ctx=Load()), node.test),
                                   args=[], keywords=[]), node.test)), node.test)
                for n in fresh]
            call = replace(Subscript(
                value=replace(Tuple(elts=[*binds, call], ctx=Load()), node.test),
                slice=replace(Constant(value=-1), node.test), ctx=Load()), node.test)
        if negated:
            node.test = replace(UnaryOp(op=Not(), operand=call), node.test)
            exports = []
        else:
            node.test = call
            exports = transformer._export_stmts(fresh, node.test)
        node.body = exports + [transformer.visit(s) for s in node.body]
        node.orelse = [transformer.visit(s) for s in node.orelse]
        fix_missing_locations(node)
        return node
```

(`pre` is unused here on purpose: the binds live in the test.)

- [ ] **Step 4: Run to verify it passes**

Run: `/workspace/clausal/venv/bin/python -m pytest -q --no-header -p no:cacheprovider tests/test_goal_position_seam.py`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add clausal/templating/term_rewriting.py tests/test_goal_position_seam.py
git commit -m "seam: while --goal re-runs the goal with fresh variables each iteration"
```

---

### Task 6: Soundness pins through the rewriter, REPL, reflection, docs, gate

**Files:**
- Modify: `docs/python_integration.md` (the `--` section: add "Goal position"; the "Querying from Python" section: mark class iteration as legacy)
- Modify: `docs/superpowers/specs/2026-09-08-goal-position-seam-design.md` §3/§4 (the trail is dropped, not undone: exports are copies taken by `$export`, and the seam's own variables are discarded)
- Test: `tests/test_goal_position_seam.py`

- [ ] **Step 1: Write the failing/passing pins**

```python
class TestSoundnessThroughTheRewriter:
    def test_a_conditional_answer_raises_in_an_if(self):
        from clausal.logic.seam import UndefinedAnswer
        mod = _load_inline("_gp_s1", (
            "-module(_gp_s1, [move(A, B), wins(X), a, b, c])\n"
            "-double_quotes(chars)\n"
            "-table(wins/1)\n"
            "move(a, b),\n"
            "move(b, c),\n"
            "move(c, a),\n"
            "wins(X) <- (move(X, Y), not wins(Y))\n"
            "def check():\n"
            "    if --wins(a):\n"
            "        return True\n"
            "    return False\n"
        ))
        with pytest.raises(UndefinedAnswer):
            mod.check()

    def test_an_attributed_unbound_export_raises_in_a_for(self):
        from clausal.logic.seam import ResidualConstraints
        mod = _load_inline("_gp_s2", (
            "-module(_gp_s2, [constrain(X)])\n"
            "-double_quotes(chars)\n"
            "constrain(X) <- dif(X, 1)\n"
            "def get():\n"
            "    for X in --constrain(X):\n"
            "        return X\n"
        ))
        with pytest.raises(ResidualConstraints):
            mod.get()


class TestBoundaries:
    def test_repl_cell_form(self):
        from clausal.python_repl import ClausalConsole
        console = ClausalConsole(filename="<test>")
        console.runsource("fact(1),", "<test>", "single")
        console.runsource("fact(2),", "<test>", "single")
        console.runsource("out = [X for X in [1]]", "<test>", "single")
        console.runsource("got = []\nfor X in --fact(X):\n    got.append(X)\n", "<test>", "exec")
        assert console.locals.get("got") == [1, 2]

    def test_reflection_models_python_code_by_position_only(self):
        from clausal.reflection import reify_source
        src = RULEBASE.format(name="_gp_r") + "def f():\n    if --decide(small, V):\n        return V\n"
        dumped = "\n".join(repr(vars(i)) if hasattr(i, "__dict__") else repr(i) for i in reify_source(src))
        assert "PythonCode(kind='function', name='f'" in dumped and "$once_bind" not in dumped
```

`dif/2` leaves `X` unbound with a `dif` attribute (the C module `_constraints_dif`); confirm with `grep -rn "dif" clausal/logic/builtins/*.py | head` if the spelling is doubted. The point is an unbound export carrying an attribute.

- [ ] **Step 2: Run, fix anything that fails**

Run: `/workspace/clausal/venv/bin/python -m pytest -q --no-header -p no:cacheprovider tests/test_goal_position_seam.py tests/test_seam_operator.py tests/test_hosted_text_crossing.py tests/test_python_repl.py tests/test_ipython_integration.py tests/test_repl_integration.py tests/test_term_rewriting.py`
Expected: all pass. The REPL case works because `ClausalConsole` runs the same `EmbedTransformer` with `implicit_atoms_default=True` and seeds `$each`/`$once_bind` from `runtime_builtins`.

- [ ] **Step 3: Docs**

In `docs/python_integration.md`, after the "Text crossings" subsection, add:

```markdown
### Goal position: `if --goal`, `for ... in --goal`

A term in goal position is called. Goal positions are exactly: the test of
`if`/`elif`/`while`, the iterable of `for`, and `not` inside those tests.

```seam
if --(verdict(S, IDS, _) is ++answer):      # unify once; S, IDS become locals
    use(S, IDS)
for S, IDS in --decide(++profile, verdict(S, IDS, _)):   # every solution
    use(S, IDS)
if not --decide(++profile, _):               # failure test; exports nothing
    ...
while --next(++cur, N):                      # re-run each iteration
    cur = N
```

Exported names are ordinary locals: on success they survive the block; on
failure nothing is assigned (a later read is an `UnboundLocalError`). A
`for` exports exactly its target names, which must be variables of the goal.
Values are copies; two seams never share a variable — goals that must share
one go in one seam as a conjunction. The sugar is strict: a WFS-conditional
answer raises `UndefinedAnswer` (use `query_wfs`), and an export that is
unbound and constrained raises `ResidualConstraints` (keep the store with an
explicit `Trail`, or ask for the residue inside the goal). Everywhere else
`--` is still the term.
```

In the "Querying from Python" section, prefix the "Direct iteration" subsection with: `> Legacy surface: iterating a predicate class instance predates the cell representation. New code uses goal-position \`--\` above.`

In the spec §3, replace "the trail object is then unreachable and nothing else observes the bindings" and §4's "the helper undoes its trail; the seam's own variable objects revert and are discarded" with: "the seam's own variables are discarded with their bindings; exports are the copies `$export` took, and an unbound export is refused if it carries attributes."

- [ ] **Step 4: Full-suite gate**

Run: `/workspace/clausal/venv/bin/python -m pytest -q -rfE --continue-on-collection-errors -p no:cacheprovider tests/ 2>&1 | grep -E "^(FAILED|ERROR) " | sed -E 's/ - .*//' | sort > /tmp/gp_fail.txt`
and the same on the branch base (`git worktree add /tmp/gp-base feat/hosted-text-crossing-2026-09-07`, copy the `.so` files in, run, sort to `/tmp/base_fail.txt`).
Expected: `comm -3 /tmp/base_fail.txt /tmp/gp_fail.txt` is empty except the known C17 F026 timing flake (passes on rerun).

- [ ] **Step 5: Commit**

```bash
git add docs/python_integration.md docs/superpowers/specs/2026-09-08-goal-position-seam-design.md tests/test_goal_position_seam.py
git commit -m "seam: goal-position docs, soundness pins, REPL and reflection pins"
```

---

### Task 7: Query-cache participation for goal-position seams (added after Task 2's review)

**Why:** Task 2's reviewer measured that a goal handed to `once_bind`/`each` as a
reified goal node (`pythonic_ast.nodes.Call`/`Unify`/`And`) never hits `solve()`'s
query cache — `_goal_cache_key` (`clausal/logic/solve.py:321-341`) admits only a
`PredicateMeta` instance, a `Compound`, or a cell — so `if --goal:` inside a loop
recompiles its query on every execution (~24x slower than an equivalent cached
`solve()` over 2000 iterations). Oracle loops put `if --(pattern is ++answer)`
inside a per-case loop, so this is load-bearing.

**Files:**
- Modify: `clausal/logic/solve.py` — `_goal_cache_key`, `_structural_key`, `_templatize_query_goal`, and the cache-hit path in `_compile_as_query` (`solve.py:502-566`)
- Test: `tests/test_goal_position_seam.py` (new class `TestQueryCache`)

**Interfaces:**
- Consumes: goal nodes as emitted by Task 2/4/5 (`Call`/`Unify`/`And`/`TupleLiteral` nodes whose leaves are `Var`s, `PyThunk`s, cells, lists, scalars, `LoadName`/`LoadAttr`).
- Produces: cache participation for such nodes; no signature changes to `solve`/`once`/`query`.

**Approach (spike first, then implement the one that works; the implementer decides):**
- (A, preferred — benefits every caller that passes a node goal) extend `_structural_key` to key the node structurally (node class name + recursively keyed fields), with a `Var` leaf keyed as the existing var sentinel and a `PyThunk` leaf keyed as a PARAMETER SLOT (`('thunk', i)`), and extend `_templatize_query_goal` so each `PyThunk` leaf is replaced by a fresh `Var` bound at run time to the current thunk object — the same parameterization already applied to ground scalar args — so the compiled query calls whatever thunk object the current execution supplies. Ground scalar/cell leaves are keyed by value exactly as today.
- (B, fallback if A cannot bind a thunk through a Var at run time) parameterize only the thunks' RESULTS: evaluate every `PyThunk` in the node eagerly at `once_bind`/`each` entry (they are Python values now, spec §2), substitute the values, and cache on the resulting value-leafed node. Note B changes when a `++` that references a goal variable is evaluated (before the goal runs) — that is the reason A is preferred; if B is chosen, `++` inside a goal-position seam must be documented as evaluated before the goal runs.

- [ ] **Step 1: Write the failing tests**

```python
class TestQueryCache:
    def _compile_count(self, fn):
        """How many query compiles *fn()* triggers (instrumented, not timed)."""
        import clausal.logic.compiler as comp
        import clausal.logic.solve as solve_mod
        calls = []
        real = comp.compile_predicate_trampoline
        def counting(*a, **k):
            calls.append(1)
            return real(*a, **k)
        comp.compile_predicate_trampoline = counting
        solve_mod._query_cache.clear()
        try:
            fn()
        finally:
            comp.compile_predicate_trampoline = real
        return len(calls)

    def test_a_goal_seam_in_a_loop_compiles_once(self):
        mod = _load_inline("_gp_c1", RULEBASE.format(name="_gp_c1") + (
            "def hits(profiles):\n"
            "    n = 0\n"
            "    for p in profiles:\n"
            "        if --decide(++p, verdict(S, IDS)):\n"
            "            n += 1\n"
            "    return n\n"
        ))
        profiles = [("small",), ("large",), ("tiny",)] * 10
        assert self._compile_count(lambda: mod.hits(profiles)) == 1
        assert mod.hits(profiles) == 20

    def test_a_thunk_is_re_evaluated_per_execution_not_captured(self):
        mod = _load_inline("_gp_c2", RULEBASE.format(name="_gp_c2") + (
            "def status(p):\n"
            "    if --decide(++p, verdict(S, _)):\n"
            "        return S\n"
            "    return None\n"
        ))
        assert mod.status(("small",)) == ("permitted",)
        assert mod.status(("large",)) == ("prohibited",)
        assert mod.status(("small",)) == ("permitted",)

    def test_a_unification_pattern_seam_compiles_once(self):
        mod = _load_inline("_gp_c3", RULEBASE.format(name="_gp_c3") + (
            "def parts(answers):\n"
            "    out = []\n"
            "    for a in answers:\n"
            "        if --(verdict(S, IDS) is ++a):\n"
            "            out.append(S)\n"
            "    return out\n"
        ))
        answers = [("verdict", ("permitted",), []), ("verdict", ("prohibited",), [])] * 5
        assert self._compile_count(lambda: mod.parts(answers)) == 1
```

- [ ] **Step 2: Run to verify they fail** — expected: compile count equals the number of loop iterations (30 / 10), not 1.

- [ ] **Step 3: Implement A (or B with the documented caveat), keeping every existing test in `tests/test_goal_position_seam.py`, `tests/test_seam_operator.py`, `tests/test_query_cache*.py` (if present; `grep -rl "_query_cache" tests/`) and `tests/test_solve*.py` green.**

- [ ] **Step 4: Run the tests to verify they pass; run the full suite once and compare the failing-name set to the branch base.**

- [ ] **Step 5: Commit** — `git add clausal/logic/solve.py tests/test_goal_position_seam.py` and a neutral message with the two trailers.
