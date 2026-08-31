# Reflection — Matching Clausal Source with Clausal

The `reflection` module reifies `.clausal` source into ordinary compound
terms — a homoiconic tree the language can inspect — so linters, call-graph
analyses, style checkers, and construction matchers are written **in Clausal
itself**, by unification against clause structure, instead of walking a
Python AST imperatively.

Reification is *pure*: the analysed source is never executed. Directives are
not run, embedded Python does not evaluate, `++` escapes are captured as
source text. It is safe to reflect over untrusted rulebases.

---

## Quick Example

```clausal
-import_from(reflection, [
    reified_clause, clause_head, clause_body, goal_functor, Clause, Goal,
])

HeadName(SRC, NAME) <- (
    reified_clause(SRC, CLAUSE),
    clause_head(CLAUSE, HEAD),
    goal_functor(HEAD, NAME, _)
)
```

```python
>>> from clausal.logic.solve import call
>>> src = "Edge(1, 2),\nConnected(X, Y) <- Edge(X, Y)\n"
>>> # HeadName(src, NAME) enumerates "Edge", "Connected"
```

---

## The Reified Vocabulary

Every top-level item of a source reifies to one of three terms:

| Term | Meaning |
|---|---|
| `Clause(HEAD, GOALS, POSITION)` | One clause. `GOALS` is a list — `[]` for facts. |
| `ModuleDirective(NAME, ARGS, POSITION)` | A `-name(...)` directive (`dynamic`, `import_from`, `module`, …). |
| `PythonCode(KIND, NAME, POSITION)` | An embedded plain-Python statement (`function`, `class`, `import`, …) — reported, never run. |

Inside clauses:

| Term | Meaning |
|---|---|
| `Goal(NAME, ARGS, KWARGS)` | A predicate call *and* any compound term — heads, body goals, and structured arguments share this shape. `NAME` is a string (dotted for qualified calls, e.g. `"mod.Pred"`); `KWARGS` is a list of `[name, value]` pairs. |
| `Variable(NAME)` | A logic variable, as a *ground* term — matchers inspect structure without binding anything. Anonymous variables are numbered `_1`, `_2`, … per clause. |
| `Atom(NAME)` | A bare lowercase name. |
| `Escape(CODE, VARS, POSITION)` | A `++` Python escape. `CODE` is the escaped expression's source text; it is never evaluated. |
| `FormatString(CODE, VARS, POSITION)` | A deferred f-string. |
| `IfThenElse(CONDITION, THEN, OTHERWISE)` | A reified `If/3`. |

Python literals stay raw: numbers, strings, lists, tuples, and dicts appear
as themselves, so `Path([1, 2, 3])` reifies with the plain list `[1, 2, 3]`
as its argument.

**Operator nodes stay raw.** Arithmetic, comparison, and boolean operator
nodes (`Add`, `Gt`, `Unify`, `Not`, `Or`, `StarUnpack`, …) carry structural
unification, so they pass through unwrapped with reified operands. A body
goal `X > 0` reifies as `Gt(left=Variable('X'), right=0)` and is matched by
writing `Gt(A, B)` — the constructor names are available in every `.clausal`
module. This keeps the operator subset matchable exactly as demonstrated by
`clausal/examples/symbolic_diff.clausal`, at the cost of coupling matchers
to the `pythonic_ast` node names.

Conjunctions normalise to Python lists wherever they appear in goal
position: a clause body is always a list, and a parenthesised conjunction
inside `or` becomes a nested list.

---

## Import

```clausal
-import_from(reflection, [
    reified_item, reified_clause, reified_file_item,
    clause_head, clause_body, goal_functor, reified_subterm,
    op_node, replace_subterm, clause_source,
    Clause, Goal, Variable, Atom, Escape,
])
```

Import only what a matcher uses; the vocabulary classes (`Clause`, `Goal`,
`Variable`, `Atom`, `Escape`, `FormatString`, `IfThenElse`,
`ModuleDirective`, `PythonCode`) are needed whenever they appear in a head
pattern or constructed argument.

---

## Builtins

### reified_item/2 — Enumerate All Items

`reified_item(SOURCE, ITEM)` — `SOURCE` is `.clausal` source *text*; `ITEM`
enumerates every reified top-level item on backtracking. Reification is
cached per source text.

### reified_clause/2 — Clauses Only

`reified_clause(SOURCE, CLAUSE)` — like `reified_item`, filtered to `Clause`
terms.

### reified_file_item/2 — From a File

`reified_file_item(PATH, ITEM)` — like `reified_item` over a file path (cached
per path and modification time).

### clause_head/2, clause_body/2 — Accessors

`clause_head(CLAUSE, HEAD)` and `clause_body(CLAUSE, GOALS)` destructure a
`Clause` when `CLAUSE` is bound. Unlike matching `Clause(HEAD, GOALS, _)`
directly, they do *not* construct: with `CLAUSE` unbound they fail rather than
binding it, and a non-`Clause` term simply fails. The enumeration builtins
(`reified_item/2`, `reified_clause/2`, `reified_file_item/2`) raise
`instantiation_error` when their source/path argument is unbound.

### goal_functor/3 — Name and Arity

`goal_functor(GOAL, NAME, ARITY)` — `NAME` is the functor string, `ARITY`
counts positional plus keyword arguments. Fails on non-`Goal` terms (raw
operator nodes, literals), which conveniently skips them in call-graph
sweeps.

### reified_subterm/2 — Recursive Walk

`reified_subterm(TERM, SUB)` — enumerates every subterm depth-first,
starting with `TERM` itself; recurses through vocabulary terms, raw
operator nodes, lists, tuples, and dict values. The workhorse for "find a
`++` escape anywhere" checks:

```clausal
EscapeCode(SRC, CODE) <- (
    reified_item(SRC, ITEM),
    reified_subterm(ITEM, Escape(CODE, _, _))
)
```

### clause_source/2 — Render Back to Source

`clause_source(TERM, TEXT)` — the inverse direction: renders a reified term
(a `Clause`, or any renderable subterm) back to `.clausal` source text, so a
matcher can *quote* the clause it is objecting to — including one it rebuilt
with `replace_subterm/4` that never came from source text:

```clausal
SwappedSource(SRC, TEXT) <- (
    reified_clause(SRC, CLAUSE),
    reified_subterm(CLAUSE, SUB),
    op_node(SUB, "GtE", ARGS),
    op_node(NEW, "Gt", ARGS),
    replace_subterm(CLAUSE, SUB, NEW, CLAUSE2),
    clause_source(CLAUSE2, TEXT)
)
```

`TERM` must be bound (`instantiation_error` otherwise — the reverse mode is
already `reified_item/2`). A term the renderer refuses raises `RenderError`
rather than failing silently.

---

## Arrow Patterns — Matching in Clause Syntax

Inside a reflection builtin's argument, a ``(HEAD <- BODY)`` expression is
sugar for the equivalent vocabulary pattern, so matchers are written in the
same syntax as the clauses they match:

```clausal
ShapeXY(SRC) <- reified_clause(SRC, MyPred(A, B) <- (Goalx(A), Goaly(B)))
```

is rewritten at compile time (goal expansion) into

```clausal
ShapeXY(SRC) <- reified_clause(SRC,
    Clause(Goal("MyPred", [A, B], []),
           [Goal("Goalx", [A], []), Goal("Goaly", [B], [])]))
```

Semantics:

- **Pattern variables are the matcher's own variables.** They *capture*
  the reified subterms they align with — `A` above binds to
  `Variable("X")` when matching `MyPred(X, Y) <- (Goalx(X), Goaly(Y))` —
  and repeated variables enforce sharing: the pattern above rejects
  `MyPred(X, Y) <- (Goalx(Y), Goaly(X))`. To pin an actual source-level
  name, write `Variable("X")` explicitly in the pattern.
- **Facts:** `Tagged(_, ok) <- True` matches the fact `Tagged(1, ok),`
  (a `True` body is the empty goal list). Atoms in patterns match reified
  `Atom` terms, not strings.
- **Whole-body capture:** `MyPred(_, _) <- GOALS` binds `GOALS` to the
  body's goal list.
- **Goal lists match exactly.** A two-goal pattern body matches two-goal
  bodies only.
- **Operators stay raw on both sides:** `Positive(A) <- (A > 0)` matches
  via the `Gt` node's structural unification; `not`/`or` bodies work the
  same way.

Boundaries:

- The sugar fires **only** in the argument positions of the reflection
  builtins (detected by identity, so a same-named user predicate never
  triggers it). Everywhere else `(HEAD <- BODY)` keeps its existing
  meaning — a runtime clause term, as consumed by `assertz`.
- A **variable head** (`HEAD <- GOALS`) is lambda syntax, not a clause
  pattern — for full head destructuring match `Clause(HEAD, GOALS)`
  directly.
- `++` escapes cannot be written in pattern syntax (they would be live
  thunks); match them explicitly with `Escape(CODE, _, _)`.

---

## A Call-Graph Lint in Clausal

The motivating example — "a called predicate that is neither defined nor
imported":

```clausal
CalledPredicate(SRC, NAME, ARITY) <- (
    reified_clause(SRC, CLAUSE),
    clause_body(CLAUSE, GOALS),
    GOAL in GOALS,
    goal_functor(GOAL, NAME, ARITY)
)

DefinedName(SRC, NAME) <- (
    reified_clause(SRC, Clause(Goal(NAME, _, _), _, _))
)  # head name is a variable — vocabulary form, not arrow sugar

UndefinedCall(SRC, NAME) <- (
    CalledPredicate(SRC, NAME, _),
    not DefinedName(SRC, NAME)
)
```

---

## DCG Construction Matching

A clause body is a plain list of goals, so [DCGs](dcg.md) match goal
*sequences* directly — the right tool for "a body that starts with an
`Edge/2` call":

```clausal
edge_goal >> ([Goal("Edge", _, _)])
any_goal >> ([_])
any_goals >> ([])
any_goals >> (any_goal, any_goals)

starts_with_edge >> (edge_goal, any_goals)

StartsWithEdge(SRC, NAME) <- (
    reified_clause(SRC, CLAUSE),
    clause_head(CLAUSE, HEAD),
    goal_functor(HEAD, NAME, _),
    clause_body(CLAUSE, GOALS),
    phrase(starts_with_edge, GOALS)
)
```

---

## Python API

For Python-side tooling (e.g. static analysers that must not load the
target's engine or imports), `clausal.reflection` exposes the pure layer:

```python
from clausal.reflection import reify_source, reify_file, reify_ast, Clause, Goal

items = reify_source(open("rules.clausal").read())
clauses = [item for item in items if isinstance(item, Clause)]
heads = [clause.head.name for clause in clauses]
```

- `reify_source(text, filename="<reflected>")` — parse and reify every
  top-level item, ordered by source position (directives, whose positions
  are not tracked, sort first).
- `reify_file(path)` — the same over a file.
- `reify_ast(node)` — reify a single parsed Python `ast` node of `.clausal`
  surface syntax; statements yield items, expressions yield terms.

Positions are `(line, column, end_line, end_column)` tuples. Field access
is plain attribute access: `clause.head`, `clause.goals`,
`goal.name`, `goal.args`, `escape.code`.

Note the difference from the runtime clause store: reified terms hold
ground `Variable('X')` terms where the compiled database holds real unbound
`Var` objects, and reification needs neither directive execution nor
predicate compilation.

---

## Notes

- `Goal` has no position field: goals are compared whole far more often
  than clauses, and an always-present position would make structurally
  identical goals compare unequal. Positions live on `Clause`,
  `ModuleDirective`, `PythonCode`, `Escape`, and `FormatString`; raw
  operator nodes keep their own (comparison-neutral) `position` attribute.
- Head patterns written with fewer arguments wildcard the remaining fields
  (`Clause(HEAD, GOALS)` leaves `POSITION` unconstrained), so matchers stay
  concise.
- DCG rules in the *analysed* source reify in their expanded `<-` form
  (with the two threaded state arguments), since expansion happens at the
  surface-syntax level.
