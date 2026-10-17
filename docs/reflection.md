# Reflection — Matching Seam Source by Unification

The `reflection` module reifies seam (`.seam`) source into ordinary compound
terms — a tree the language can inspect — so linters, call-graph analyses,
style checkers, and construction matchers are written **in logic**, by
unification against clause structure, instead of walking a Python AST
imperatively.

Reification is *pure*: the analysed source is never executed. Directives are
not run, embedded Python does not evaluate, `++` escapes are captured as
source text. It is safe to reflect over untrusted rulebases.

!!! note "Clausal Prolog and the seam"

    The matchers on this page are [Clausal Prolog](clausal_prolog.md)
    (`.clausal`, ISO Prolog syntax), importing the module through its
    facade `library(reflection)`. The source they analyse is seam text,
    passed in as a string. A matcher can also be written in the
    [seam](syntax.md), which has two conveniences of its own, marked below:
    the vocabulary constructors as names (`Clause(HEAD, GOALS)`) and the
    arrow-pattern sugar.

---

## Quick Example

```clausal
:- use_module(library(reflection),
              [reified_clause/2, clause_head/2, goal_functor/3]).

head_name(Src, Name) :-
    reified_clause(Src, Clause),
    clause_head(Clause, Head),
    goal_functor(Head, Name, _).

test("head names") :-
    findall(Name,
            head_name("edge(1, 2),\nconnected(X, Y) <- edge(X, Y)\n", Name),
            Names),
    Names == [edge, connected].
```

(A `.seam` module can also call `head_name/2` from Python with the
goal-position seam; see [Python Integration](python_integration.md).)

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
| `Goal(NAME, ARGS, KWARGS)` | A predicate call *and* any compound term — heads, body goals, and structured arguments share this shape. `NAME` is the functor's spelling, a plain Python `str` — which is the atom (dotted for qualified calls, e.g. `'mod.pred'`); `KWARGS` is a list of `[name, value]` pairs. It is the same value `goal_functor/3` answers. |
| `Variable(NAME)` | A logic variable, as a *ground* term — matchers inspect structure without binding anything. Anonymous variables are numbered `_1`, `_2`, … per clause. |
| `Atom(NAME)` | A bare lowercase name. |
| `Escape(CODE, VARS, POSITION)` | A `++` Python escape. `CODE` is the escaped expression's source text; it is never evaluated. |
| `FormatString(CODE, VARS, POSITION)` | A deferred f-string. |
| `IfThenElse(CONDITION, THEN, OTHERWISE)` | A reified `If/3`. |

Python literals stay raw: numbers, strings, lists, tuples, and dicts appear
as themselves, so `path([1, 2, 3])` reifies with the plain list `[1, 2, 3]`
as its argument.

**From Clausal Prolog**, a vocabulary term is matched by its quoted functor
with **every** field written: `'Clause'(Head, Goals, _)`, `'Goal'(Name,
Args, Kwargs)`, `'Variable'(Name)`, `'Escape'(Code, _, _)`. (The seam's
constructor names also accept fewer arguments, `Clause(HEAD, GOALS)`; a
`.clausal` `'Clause'(Head, Goals)` has the wrong arity and matches nothing.)

**Operator nodes stay raw.** Arithmetic, comparison, and boolean operator
nodes (`Add`, `Gt`, `Unify`, `Not`, `Or`, `StarUnpack`, …) carry structural
unification, so they pass through unwrapped with reified operands. A body
goal `X > 0` reifies as `Gt(left=Variable('X'), right=0)`. From Clausal
Prolog, read it with `op_node/3`: `op_node(G, Name, Args)` gives
`Name = 'Gt'`, `Args = ['Variable'('X'), 0]` (neither `G = (A > B)` nor
`G = 'Gt'(A, B)` unifies with the node). A seam matcher writes `Gt(A, B)` —
the constructor names are available in every `.seam` module. This keeps the operator subset matchable exactly as demonstrated by
`clausal/examples/symbolic_diff.seam`, at the cost of coupling matchers
to the `pythonic_ast` node names.

Conjunctions normalise to Python lists wherever they appear in goal
position: a clause body is always a list, and a parenthesised conjunction
inside `or` becomes a nested list.

---

## Import

```clausal
:- use_module(library(reflection), [
    reified_item/2, reified_clause/2, reified_file_item/2,
    clause_head/2, clause_body/2, goal_functor/3, reified_subterm/2,
    op_node/3, replace_subterm/4, clause_source/2
]).
```

Import only what a matcher uses. A Clausal Prolog matcher writes the
vocabulary terms with quoted functors and imports nothing more; a seam
matcher also imports the vocabulary classes (`Clause`, `Goal`, `Variable`,
`Atom`, `Escape`, `FormatString`, `IfThenElse`, `ModuleDirective`,
`PythonCode`) whenever they appear in a head pattern or constructed
argument.

---

## Builtins

### reified_item/2 — Enumerate All Items

`reified_item(SOURCE, ITEM)` — `SOURCE` is `.seam` source *text*; `ITEM`
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

`goal_functor(GOAL, NAME, ARITY)` — `NAME` is the functor name as an **atom**
(a name position), `ARITY` counts positional plus keyword arguments. Fails on
non-`Goal` terms (raw operator nodes, literals), which conveniently skips them
in call-graph sweeps.

Because `NAME` is an atom, a matcher writes it as an atom:
`goal_functor(Goal, edge, _)` matches an `edge/…` call. Destructuring
`'Goal'(Name, _, _)` directly gives the same atom. A double-quoted `"edge"` is
a string and matches neither.

### reified_subterm/2 — Recursive Walk

`reified_subterm(TERM, SUB)` — enumerates every subterm depth-first,
starting with `TERM` itself; recurses through vocabulary terms, raw
operator nodes, lists, tuples, and dict values. The workhorse for "find a
`++` escape anywhere" checks:

```clausal
:- use_module(library(reflection), [reified_item/2, reified_subterm/2]).

escape_code(Src, Code) :-
    reified_item(Src, Item),
    reified_subterm(Item, 'Escape'(Code, _, _)).

test("find an escape") :-
    findall(Code, escape_code("p(X) <- (X is ++(1 + 2))\n", Code), Codes),
    % the source text, as an atom
    Codes == ['1 + 2'].
```

### clause_source/2 — Render Back to Source

`clause_source(TERM, TEXT)` — the inverse direction: renders a reified term
(a `Clause`, or any renderable subterm) back to `.seam` source text, so a
matcher can *quote* the clause it is objecting to — including one it rebuilt
with `replace_subterm/4` that never came from source text:

```clausal
:- use_module(library(reflection),
              [reified_clause/2, reified_subterm/2, op_node/3,
               replace_subterm/4, clause_source/2]).

swapped_source(Src, Text) :-
    reified_clause(Src, Clause),
    reified_subterm(Clause, Sub),
    op_node(Sub, 'GtE', Args),
    op_node(New, 'Gt', Args),
    replace_subterm(Clause, Sub, New, Clause2),
    clause_source(Clause2, Text).

test("swap >= for >") :-
    swapped_source("p(X) <- (X >= 0)\n", Text),
    Text == "p(X) <- (X > 0)".
```

`TERM` must be bound (`instantiation_error` otherwise — the reverse mode is
already `reified_item/2`). A term the renderer refuses raises `RenderError`
rather than failing silently.

---

## Arrow Patterns — Matching in Clause Syntax

This sugar is **seam-only**: a Clausal Prolog `(Head :- Body)` argument is
an ordinary term and matches no reified clause. From Clausal Prolog, write
the vocabulary pattern itself, with quoted functors and all three `'Clause'`
fields:

```clausal
:- use_module(library(reflection), [reified_clause/2]).

shape_xy(Src) :-
    reified_clause(Src,
        'Clause'('Goal'(my_pred, [A, B], []),
                 ['Goal'(goalx, [A], []), 'Goal'(goaly, [B], [])],
                 _)).

test("shape matches") :-
    shape_xy("my_pred(X, Y) <- (goalx(X), goaly(Y))\n").

test("shared variables are enforced") :-
    \+ shape_xy("my_pred(X, Y) <- (goalx(Y), goaly(X))\n").
```

In the seam, inside a reflection builtin's argument, a ``(HEAD <- BODY)``
expression is sugar for the equivalent vocabulary pattern, so matchers are
written in the same syntax as the clauses they match (seam syntax):

```seam
shape_xy(SRC) <- reified_clause(SRC, my_pred(A, B) <- (goalx(A), goaly(B)))
```

is rewritten at compile time (goal expansion) into

```seam
-import_from(reflection, [reified_clause, Clause, Goal])

shape_xy(SRC) <- reified_clause(SRC,
    Clause(Goal('my_pred', [A, B], []),
           [Goal('goalx', [A], []), Goal('goaly', [B], [])]))
```

(The expansion is built by the compiler, so its `'my_pred'` is the raw
spelling the reified `Goal.name` field holds — a plain `str`, which is
exactly the atom `'my_pred'`, whatever `-double_quotes` mode the matcher's
module is in. Writing the vocabulary form by hand works with single-quoted
names, as shown; a double-quoted `"my_pred"` under the default `chars`
mode is a *string*, which the field never holds, and matches nothing —
prefer the arrow sugar, or `goal_functor/3`.)

Semantics:

- **Pattern variables are the matcher's own variables.** They *capture*
  the reified subterms they align with — `A` above binds to
  `Variable('X')` when matching `my_pred(X, Y) <- (goalx(X), goaly(Y))` —
  and repeated variables enforce sharing: the pattern above rejects
  `my_pred(X, Y) <- (goalx(Y), goaly(X))`. To pin an actual source-level
  name, write `Variable('X')` explicitly in the pattern.
- **Facts:** `tagged(_, ok) <- True` matches the fact `tagged(1, ok),`
  (a `True` body is the empty goal list). Atoms in patterns match reified
  `Atom` terms, not strings.
- **Whole-body capture:** `my_pred(_, _) <- GOALS` binds `GOALS` to the
  body's goal list.
- **Goal lists match exactly.** A two-goal pattern body matches two-goal
  bodies only.
- **Operators stay raw on both sides:** `positive(A) <- (A > 0)` matches
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

## A Call-Graph Lint

The motivating example — "a called predicate that is neither defined nor
imported":

```clausal
:- use_module(library(reflection),
              [reified_clause/2, clause_head/2, clause_body/2, goal_functor/3]).

called_predicate(Src, Name, Arity) :-
    reified_clause(Src, Clause),
    clause_body(Clause, Goals),
    in_(Goal, Goals),
    goal_functor(Goal, Name, Arity).

% goal_functor on both sides, so both names are atoms
defined_name(Src, Name) :-
    reified_clause(Src, Clause),
    clause_head(Clause, Head),
    goal_functor(Head, Name, _).

undefined_call(Src, Name) :-
    called_predicate(Src, Name, _),
    \+ defined_name(Src, Name).

test("undefined call") :-
    findall(Name,
            undefined_call("edge(1, 2),\npath(X, Y) <- (edge(X, Y), missing(Y))\n",
                           Name),
            Names),
    Names == [missing].
```

---

## DCG Construction Matching

A clause body is a plain list of goals, so [DCGs](dcg.md) match goal
*sequences* directly — the right tool for "a body that starts with an
`edge/2` call":

```clausal
:- use_module(library(reflection),
              [reified_clause/2, clause_head/2, clause_body/2, goal_functor/3]).

edge_goal --> [Goal], { goal_functor(Goal, edge, _) }.
any_goal --> [_].
any_goals --> [].
any_goals --> any_goal, any_goals.

edge_first --> edge_goal, any_goals.

starts_with_edge(Src, Name) :-
    reified_clause(Src, Clause),
    clause_head(Clause, Head),
    goal_functor(Head, Name, _),
    clause_body(Clause, Goals),
    phrase(edge_first, Goals).

test("starts with edge") :-
    findall(Name,
            starts_with_edge("a(X) <- (edge(X, 1), b(X))\nb(X) <- (c(X), edge(X, 2))\n",
                             Name),
            Names),
    Names == [a].
```

(The nonterminal is `edge_first`, not `starts_with_edge`: a grammar rule
`starts_with_edge --> ...` defines `starts_with_edge/2`, the same predicate
as the two-argument rule.)

---

## Python API

For Python-side tooling (e.g. static analysers that must not load the
target's engine or imports), `clausal.reflection` exposes the pure layer.
It is not covered by the 1.0 API promise (see [Public API](public-api.md)):

```python
from clausal.reflection import reify_source, reify_file, reify_ast, Clause, Goal

items = reify_source(open("rules.seam").read())
clauses = [item for item in items if isinstance(item, Clause)]
heads = [clause.head.name for clause in clauses]
```

- `reify_source(text, filename="<reflected>")` — parse and reify every
  top-level item, ordered by source position (directives, whose positions
  are not tracked, sort first).
- `reify_file(path)` — the same over a file.
- `reify_ast(node)` — reify a single parsed Python `ast` node of `.seam`
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
- In the seam, head patterns written with fewer arguments wildcard the
  remaining fields (`Clause(HEAD, GOALS)` leaves `POSITION` unconstrained),
  so matchers stay concise. A Clausal Prolog pattern writes every field
  (`'Clause'(Head, Goals, _)`).
- DCG rules in the *analysed* source reify in their expanded `<-` form
  (with the two threaded state arguments), since expansion happens at the
  surface-syntax level.
