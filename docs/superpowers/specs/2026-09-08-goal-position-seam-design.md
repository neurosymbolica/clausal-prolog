# Goal-position `--`: running goals from Python-hosted code (design)

**Status:** design, 2026-09-08. Operator-approved direction ("go"); builds on
the `--` seam (`feat/seam-operator-2026-09-07`) and the hosted text crossing
(`feat/hosted-text-crossing-2026-09-07`).

## 1. The rule

`--` already means "this is a Clausal term" in Python hosted by a `.clausal`
file. This design adds Prolog's own rule for it: **a term in goal position is
called.** The rewriter decides the position syntactically; nothing is
inferred from types.

| position | meaning of `--X` | emitted |
|---|---|---|
| test of `if` / `elif` / `while` | run `X` once; on success export its variables as locals | `$once_bind` |
| iterable of `for` | run `X`; one iteration per solution, targets bound per solution | `$each` |
| operand of `not` inside those tests | run `X` once; export nothing | `not $once_bind(...)` |
| anywhere else | the term `X` (unchanged) | `$seam` |

Goal positions are exactly that list. `x = --decide(...)`, `f(--goal)`,
`assert --goal` and a `--` nested inside a larger test expression are term
positions and keep today's meaning. The list is closed on purpose: the
meaning of `--` is decided by a lookup, not by a heuristic.

## 2. Surface

```clausal
-module(oracle, [])
-double_quotes(chars)
-import_from(rulebase, [decide, verdict, permitted])

def check(profile, answer):
    if --(verdict(S, IDS, _) is ++answer):        # one-shot unification
        use(S, IDS)                                 # plain locals from here on

    for S, IDS in --decide(++profile, verdict(S, IDS, _)):   # every solution
        use(S, IDS)

    if --(decide(++profile, V), V is verdict(permitted, _, _)):   # any goal, once
        ...
    if not --decide(++profile, _):                  # failure test, exports nothing
        ...
```

Inside `--` the grammar is the seam's, unchanged: declared/imported names are
atoms, ALL-CAPS and `_x` names are logic variables, `is`/`==` unify, `,`
conjoins, `++expr` is a Python value evaluated now, `'...'`/`"..."` follow
the module's `-double_quotes` mode, functors follow the module's declaration
rules. The goal resolves in the host module (P3-3: calling-module default),
so an imported predicate is called without qualification.

## 3. Emitted code

The rewriter emits ordinary Python; no new statement kinds, no closures over
the body. Multiple assignments, never a tuple built and unpacked; the trail
is created inline, never stored.

`if`:

```python
$v_S = Var(); $v_IDS = Var()
if $once_bind(Unify(('verdict', $v_S, $v_IDS, Var()), answer), globals()):
    S = $export($v_S)
    IDS = $export($v_IDS)
    use(S, IDS)
```

`$once_bind` receives the rewriter's own reified goal NODE — here a `Unify`
node, the same shape a clause body compiles and `solve()` documents — not a
cell; control goals (`,`, `=`) have no cell form to build. It runs the goal
to its first UNCONDITIONAL answer (§4a) against `globals["$module"]`,
returns `True`/`False`, and leaves the exported variables BOUND for the two
`$export` lines that immediately follow: the seam's own variables are
discarded with their bindings; exports are the copies `$export` took, and an
unbound export is refused if it carries attributes. `elif` is the same
shape as `if` (nested in the `else` branch — `visit_If` visits it too).

`for`:

```python
$v_S = Var(); $v_IDS = Var()
for S, IDS in $each(('decide', profile, ('verdict', $v_S, $v_IDS, [])), ($v_S, $v_IDS), globals()):
    use(S, IDS)
```

`$each(goal, vars, globals)` is `query` projected onto `vars`: it yields one
tuple of walked values per solution. The loop target is Python's own, so
Python's own unpacking applies: the tuple exists because the `for` statement
needs an iterable of something, and a 2-tuple per solution is that
something. When there is exactly one exported variable the target is the bare
name and `$each` yields the value itself, no 1-tuple.

`while` is NOT the same shape as `if`/`elif`. Its fresh variables must be
re-created on every evaluation of the test, not once before the loop, so
there is no preceding `$v_NAME = Var()` statement at all: each is
walrus-bound INSIDE the test, and the whole test is a tuple whose last
element is the `$once_bind` call —

```python
while (($v_N := Var()), $once_bind(Call(next, cur, $v_N), globals()))[-1]:
    N = $export($v_N)
    cur = N
```

— so the tuple is rebuilt (fresh `Var()`s, fresh goal node evaluation) on
every pass through the test, and the `[-1]` picks out `$once_bind`'s
`True`/`False` for the `while` to test. The export lines stay the first
statements of the body, exactly as for `if`/`for`.

`not`:

```python
if not $once_bind(Call(decide, profile, Var()), globals()):
```

No variables are created for a negated goal beyond the fresh ones the goal
needs; nothing is exported.

## 4. Which variables are exported, and scope

- **Exported names**: for `if`/`elif`/`while`, every ALL-CAPS name in the
  goal, in first-occurrence order. For `for`, exactly the names in the loop
  target; each must occur in the goal, and every ALL-CAPS name in the goal
  that is not a target is bound per solution but not exported. `_` and `_x`
  names are never exported.
- **Scope is Python's.** On success the names are ordinary locals of the
  enclosing function (or module globals at module level) and survive the
  block, like any assignment. A `for` leaves the last iteration's values,
  like any Python `for`. On failure nothing is assigned, so a later read
  raises `UnboundLocalError`: loud, and the same as a Python name assigned
  only inside an `if`.
- **Rebinding** an existing Python local of the same name is an ordinary
  overwrite. The rewriter does not warn; it is an assignment.
- **No sharing across seams.** Two `--` in one function that both mention
  `S` bind two unrelated fresh variables. Goals that must share a variable go
  in one seam as a conjunction. (A `--` inside `++` inside `--` shares with
  its enclosing seam as today; that is the same seam.)
- **Which names are variables is not this design's decision.** The
  rewriter's own classifier (`_is_logic_var_name`: today ALL-CAPS or a
  single leading underscore; CamelCase is an atom) decides, and the seam
  calls it — never a private rule. If the convention moves toward ISO's,
  the seam follows without change.
- **Exports are copies; the seam's own variables are discarded.** The
  seam's own variables are discarded with their bindings; exports are the
  copies `$export` took, and an unbound export is refused if it carries
  attributes (§4a). An export that is still UNBOUND and free of attributes
  is a fresh, unconstrained variable Python now holds. Exports are for
  answers.
- **Nesting composes values, conjunction composes search.** A seam inside
  the body of another is an independent query; outer values reach it as
  Python values through `++`. Two goals that must share a still-unbound
  variable, with the second's bindings undone when the first backtracks, go
  in ONE seam as a conjunction (or in a predicate). No seam shares a trail
  with another; the trail is never exposed by the sugar. Holding a trail
  across two calls is the lower level (`unify`/`solve` with an explicit
  `Trail`), which stays available unchanged.
- **Every mentioned variable is a local, exported or not.** A negated test's
  variables and a `for`'s non-target goal variables are never exported, but
  every variable the seam MENTIONS still becomes a local of the enclosing
  function, via a dead `if False:` block that assigns it without ever
  running. A stray read of one is an `UnboundLocalError`, never a silent
  read of a same-named module global (Tasks 3/4).

## 4a. Soundness: undefined answers and residual constraints

The plain query path is not sound enough to sit under the sugar: `query`,
`call` and `solve` yield WFS-conditional (undefined) answers alongside true
ones with no annotation (docs/wfs.md), and an unbound variable carrying
constraint attributes comes back as the variable itself, whose attributes
§4's trail undo would strip. The sugar is strict by default and never
silent:

- **Unconditional answers only.** `if --goal` is true, and `for ... in
  --goal` yields, only for answers with an empty delay set. A conditional
  answer raises `UndefinedAnswer` (naming the goal, pointing to
  `query_wfs`) at the point it is produced — not skipped, not taken as
  true. The helpers therefore run through the delay-aware machinery that
  `query_wfs` uses, not through `once`/`query` as written today.
- **No residual constraints on an export.** If an exported variable is
  still unbound AND attributed at export time, the helper raises
  `ResidualConstraints` naming the variable. A free unbound export is fine
  (a fresh variable). Keeping a constraint store alive across calls is the
  lower level: `solve` with an explicit `Trail`.
- **Residue is requested inside the goal, ISO-style.** With `copy_term/3`
  (attribute goals as a term), `--(goal, copy_term(X, X2, GOALS))` exports
  `GOALS` as a plain list and `X2` as a plain term, and the sugar needs no
  special form. `copy_term/3` does not exist yet: todo filed
  (`todo/copy-term-3-attribute-goals-2026-09-08.md`); until it lands the
  strict rule above is the whole story.

## 5. Errors

- A `for` target name not occurring in the goal: `SyntaxError` at load,
  naming both (`for S, X in --decide(...)`: `X` is not a variable of the goal).
- A `for` whose target is not a Name or a Tuple of Names (e.g. `a.b`,
  `L[0]`): `SyntaxError`; the export is an assignment to locals by design.
- A goal that raises a logic exception propagates as today (`LogicException`
  out of `once`/`query`); the exported names are not assigned.
- `--goal` in goal position inside a namespace that has no `$module` (a
  `.clausal` file's own module namespace always has one; a fresh
  `ClausalConsole`/IPython namespace does not unless the caller sets one,
  and a plain `.py` file never reaches the rewriter at all): `$once_bind`
  raises `NameError` naming `$module`, the same failure a bare `call` gives.
- `while --goal:` with variables: allowed; each iteration re-runs the goal
  with fresh variables and re-assigns. Documented as such.

## 6. Interaction with the existing pieces

- **Term position is untouched.** `$seam` and its tests stay as they are;
  the new positions are additional branches in the Embed transformer's
  `visit_If` / `visit_While` / `visit_For` (and `visit_UnaryOp` for `not`
  only when reached from those tests).
- **`query`/`once`/`solve` keep their signatures.** `$each` and
  `$once_bind` are two small helpers in `clausal/logic/seam.py`, injected
  through `INJECTED_RUNTIME_BUILTINS` like `$seam` and `$text`.
- **The documented class-iteration idiom** (`for trail in Fib(10, F :=
  Var())`) is the old surface; `docs/python_integration.md` re-centres on
  `for ... in --goal` and marks class iteration as legacy.
- **REPL/IPython**: the same transformer runs the cell, and `$each`/
  `$once_bind` are seeded from `runtime_builtins` under the loose rules, so
  `for X in --fact(X): print(X)` drives the same helpers a file's `for`
  does — PROVIDED the cell's namespace already has a `$module` and `fact`
  bound (a `.clausal` file gets both from its own load; a bare `fact(1),`
  typed at the console does not declare one today — no `$define_predicate`
  is wired into the REPL/IPython namespace, so declaring a NEW predicate
  interactively is a separate, unbuilt piece).
- **Reflection** models Python code by source position, so nothing leaks
  into renderings (pinned already for `$text`; re-pinned here).

## 7. Testing

`tests/test_goal_position_seam.py`, one behaviour per test:

- `if --(pattern is ++value)` binds locals on success; nothing on failure;
  values survive the block; a failed test leaves `UnboundLocalError`.
- `if --goal` over an imported predicate, once semantics (first solution).
- `for A, B in --goal` yields every solution in order; single-target form
  yields bare values; targets not in the goal are a `SyntaxError`.
- `not --goal` exports nothing and is true exactly when the goal fails.
- `while --goal` re-runs per iteration.
- Term positions unchanged: `x = --goal` is still the cell; `f(--t)` too.
- `_`/`_x` never exported; ALL-CAPS not in a `for` target not exported.
- Values are copies: mutating a solution's list does not affect the next;
  after a seam its own variables are unbound again (trail undone); an
  unbound export handed to an inner seam through `++` binds there without
  touching the outer seam.
- Clause bodies and reflection untouched.
- REPL cell form works.
- A WFS-conditional answer raises `UndefinedAnswer`; an unconditional one
  from the same program is exported normally.
- An attributed unbound export raises `ResidualConstraints`; a bound one
  from the same goal is exported; a free unbound one is a fresh `Var`.
- Full-suite failing-name set unchanged.

## 8. Not in scope

Query-cache participation for node goals (Task 7 of the plan) HAS landed:
`solve()`'s `_goal_cache_key` now keys a goal node structurally, so the two
executions of an `if --goal:` in a loop share one compiled query. A `++`
escape is a parameter of that query, not part of its key — its per-execution
closure is rebound on a cache hit, exactly as the goal's `Var`s already were —
so `++` still runs when the goal runs, with the caller's current values.

Still out of scope:

- Sharing variables or a trail across separate seams (see §4: nesting
  composes values; conjunction composes search).
- `--goal` in expression positions other than the listed tests and `for`.
  Comprehensions are the notable other goal-shaped position
  (`[S for S in --goal]`, `any(--goal for ...)`); extension todo
  (`todo/goal-position-seam-in-comprehensions-2026-09-08.md`), not needed yet.
- A push/callback query API (the pull generator is the control flow).
- Dict-lookup rewriting of body names; exports are plain locals.
- Any change to `unify`, `solve`, `query`, `once` or the trail.
