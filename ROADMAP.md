# Clausal — Roadmap

## Mission

Clausal brings logic programming to Python as a genuine part of the Python runtime — not as a
subprocess call to an external Prolog, not as a foreign-function bridge, but as Python code that
runs on the Python VM alongside ordinary Python code. Logic predicates and Python functions call
into each other freely, share the same objects, and pay no marshalling cost at the boundary.

## Design principles

**Python programmers are the audience, not Prolog programmers.** Clausal uses Python syntax and
Python operator semantics throughout. Concepts are named after what Python programmers already know.

**Python operators have logic semantics in predicate bodies.** Rather than defining new operators
or operator precedence tables, clausal reuses Python's existing operators with analogous meanings:

| Python syntax | Logic meaning | Prolog equivalent |
|---|---|---|
| `X is Y` | unify X with Y | `X = Y` |
| `X is not Y` | constrain X ≠ Y (dif) | `dif(X, Y)` |
| `X == Y` | structural equality (no unification) | `X == Y` |
| `X != Y` | structural inequality | `X \== Y` |
| `X in Y` | membership, enumerate on backtrack | `member(X, Y)` |
| `X not in Y` | non-membership | `\+ member(X, Y)` |
| `A and B` | conjunction | `A, B` |
| `A or B` | disjunction | `A ; B` |
| `not A` | negation-as-failure | `\+ A` |
| `True` | always succeed | `true` |
| `False` | always fail | `fail` |
| `X < Y`, `X > Y`, etc. | arithmetic comparison | `X < Y`, etc. |
| `X ==+ Y` | arithmetic constraint (future CLP) | `X #= Y` |

**Terms are Python values.** Integers, floats, strings, booleans, and `None` are terms directly —
no wrapper types. Logic variables are `Var` objects. Structured terms are Python dataclass
instances (one class per compile-time-known functor) or `Compound(functor, args)` for
runtime-constructed or unknown functors. Python lists are list terms.

**Functor types and node types are the same thing.** The classes that represent structured terms
(`And`, `Or`, `Is`, `Call`, `Add`, `Eq`, etc.) are simply Python dataclasses. They are functors:
instantiable, matchable via Python's structural pattern matching, and passable as data. They do
not need to inherit from a `Node` base class — that infrastructure exists for the Python-as-data
(statement/control-flow) side where tree traversal visitors are genuinely useful. On the term
side, the class IS the functor and Python's `match` statement IS the dispatch mechanism.

**Goal types are term types.** The same classes serve as goal nodes when they appear in a
predicate body. `Is(left, right)` is both the term representing `X is Y` and the goal compiled to
a unification call. No separate goal AST is needed; the compiler simply dispatches on the class of
the term it encounters.

**Compile to Python, not to a WAM.** Each predicate compiles to a Python generator function.
Clauses become match arms. Backtracking is the generator protocol. Unification uses
`clausal.logic.variables`. This approach gets CPython JIT benefits for free, is debuggable with
standard tools, and allows Python calls without FFI.

**All term construction goes through AST transformation.** The import hook rewrites source code at
import time. Terms are always constructed by transformed code — never by string manipulation.

**Variables as functors are allowed.** A logic variable that holds a functor name at runtime can
be called; runtime dispatch handles it. Type inference over this construct is not a goal.

---

## Layer stack (planned and done)

```
clausal.logic.wfs          (future)  well-founded semantics
clausal.logic.tabling      (future)  SLG resolution, answer subsumption
clausal.logic.stdlib       (step 8)  list predicates, arithmetic, term inspection
clausal.logic.solve        (step 7)  top-level query API
clausal.logic.builtins     (step 8)  is, is not, in, not in, True, False, ...
clausal.logic.compiler     (steps 4–5)  predicate clauses → Python generator AST
clausal.logic.database     (step 3)  in-memory clause store, Module, dispatch
clausal.continuation_search  (done)  greenlet-based search iterator
clausal.trampoline           (done)  generator trampoline, stack-safe CPS
clausal.logic.variables      (done)  C extension: Var, Trail, unify, attr hooks
clausal.terms              (step 1)  term layer: Compound, goal nodes, no Literal wrappers
clausal.pythonic_terms     (step 1)  Python-as-data: statement/control-flow nodes
clausal.templating         (done)    DSL syntax → terms AST
clausal.import_hook        (done)    transparent import; IPython integration
```

---

## Step-by-step plan

Dependencies are strict: each step may only begin when the steps it depends on are done.
Steps 1, 2, and 3 are largely independent and may be worked in parallel.

---

### Step 1 — Restructure the term layer: `clausal.terms` and `clausal.pythonic_terms`

**Depends on:** nothing

**Goal:** establish a clean term layer where functor types and node types are the same Python
dataclasses, Python built-in literals are terms directly, and the `Node` visitor infrastructure
is confined to the Python-as-data side where it is genuinely useful.

**The central idea:** a functor like `foo(X, Y)` in the DSL becomes an instance of a Python
dataclass `foo(x=X, y=Y)`. The class is the functor. Python's `match` statement dispatches on
it. No separate "node" wrapper is needed. The existing `pythonic_ast` operator classes (`And`,
`Or`, `Is`, `Add`, `Call`, etc.) are already exactly this — plain dataclasses — and they stay
as-is, just rehomed.

**Split `pythonic_ast` into two modules:**

**`clausal.terms`** — every class that is a logic *functor or value*:
  - Plain dataclasses only; no requirement to inherit from `Node`
  - `Var` (re-exported from `clausal.logic.variables`)
  - `Compound(functor: str | Var, args: tuple)` — fallback for runtime-constructed or
    unknown-functor compound terms where no compile-time class exists
  - All operator expression classes: `Add`, `Sub`, `Mul`, `Div`, `FloorDiv`, `Mod`, `Pow`,
    `And`, `Or`, `Not`, `Is`, `IsNot`, `Eq`, `NotEq`, `Lt`, `LtE`, `Gt`, `GtE`,
    `In`, `NotIn`, `Invert`, `Negate`, `BitAnd`, `BitOr`, `BitXor`, `LShift`, `RShift`
  - `Call(func, args, kwargs)`, `LoadName(name)`, `LoadAttr(object, attr)`,
    `LoadSubscript(object, index)`, `Slice`
  - `Predicate(head, body)` — a clause as a term
  - `ArithConstraint(expr)` — stub for future CLP(FD)
  - `term_str(t) -> str` — readable representation for any term
  - Python built-in types (`int`, `float`, `str`, `bool`, `None`, `list`) are terms directly;
    the `IntLiteral`, `FloatLiteral`, `StringLiteral`, `BoolLiteral`, `NoneLiteral`,
    `BytesLiteral`, `ComplexLiteral`, `EllipsisLiteral` wrapper classes are **removed**

**`clausal.pythonic_terms`** — every class that is a Python *statement or control-flow node*,
retained for homoiconic Python-as-data use. These keep the `Node` base class and its
`visit_children` / `transform_children` infrastructure since tree traversal is useful here:
  - `If`, `While`, `For`, `With`, `Try`, `ExceptHandler`
  - `Assign`, `AnnAssign`, `Return`, `Raise`, `Assert`, `Pass`, `Break`, `Continue`
  - `FunctionDef`, `ClassDef`, `TypeAlias`
  - `Import`, `ImportFrom`, `Global`, `Nonlocal`
  - `Match`, `MatchCase`, and all `Match*` pattern nodes
  - `Module`, `Interactive`, `Expression`

**Term transformer update:** wherever the transformer currently emits `IntLiteral(value=5)` it
instead emits just `5` — the Python constant that evaluates to the Python int `5`. Same for all
other literal types. String literals in call-position (e.g. `"foo"(X, Y)`) are already converted
to identifier-based calls by the transformer; this does not change.

**List terms:** Python list literals in term position are kept as Python lists — the natural fit.
`Compound("cons", (head, tail))` / `Compound("nil", ())` is available for code that needs the
explicit Prolog-style cons structure, with `list_to_cons` / `cons_to_list` helpers.

---

### Step 2 — Goal-operator mapping in the term transformer

**Depends on:** Step 1

**Goal:** ensure every Python operator that has a logic meaning in predicate bodies is recognised
by the transformer and emits the correct term node.

Most of these classes already exist in `clausal.terms` (moved from `pythonic_ast`). They are
plain dataclasses — not `Node` subclasses — and the compiler dispatches on them via Python's
`match` statement. The transformer must confirm it handles each case:

| Python AST node produced by parser | `clausal.terms` node emitted | Compiled meaning |
|---|---|---|
| `Is(left, right)` (Python `is`) | `Is(left, right)` | unify |
| `IsNot(left, right)` (Python `is not`) | `IsNot(left, right)` | dif |
| `Eq(left, right)` (Python `==`) | `Eq(left, right)` | structural equality |
| `NotEq(left, right)` (Python `!=`) | `NotEq(left, right)` | structural inequality |
| `In(left, right)` (Python `in`) | `In(left, right)` | membership |
| `NotIn(left, right)` (Python `not in`) | `NotIn(left, right)` | non-membership |
| `And(left, right)` | `And(left, right)` | conjunction |
| `Or(left, right)` | `Or(left, right)` | disjunction |
| `Not(operand)` | `Not(operand)` | negation-as-failure |
| `Constant(True)` | Python `True` | succeed |
| `Constant(False)` | Python `False` | fail |
| `Lt`, `LtE`, `Gt`, `GtE` | same | arithmetic comparison |
| `== +expr` / `== +(expr)` | `ArithConstraint(expr)` | future CLP stub |

`ArithConstraint` is a new node added to `clausal.terms` in this step; for now it raises
`NotImplementedError` at compile time to mark the future CLP integration point.

The term transformer already handles most of these; the task is auditing, completing any gaps, and
adding tests that confirm each operator round-trips through the transformer correctly.

---

### Step 3 — In-memory predicate database (`clausal.logic.database`)

**Depends on:** Step 1

**Goal:** a Python data structure that stores clauses, recompiles dispatch functions when the
database changes, and serves as the `$module` runtime object injected by the import hook.

**Components:**

- `Clause(head: term, body: list[term])` — one clause; empty body list = fact
- `PredicateTable` — holds the clause list for one `(functor, arity)` pair plus a `dispatch_fn`
  slot; marks itself dirty when clauses are added or retracted
- `Database` — `dict[(functor, arity) → PredicateTable]`; methods: `assertz`, `asserta`,
  `retract`, `clauses_for`, `is_defined`
- `Module(name: str, db: Database)` — the `$module` object; exposes `assert_fact(term)` and
  `define_predicate(predicate_node)` as the two call-sites the import hook uses; also provides
  `solve(goal)` as a convenience entry point (implemented in step 7)

**Dispatch function slot:** the compiled Python generator function for a predicate is stored on
`PredicateTable.dispatch_fn`. It is (re)compiled whenever the clause list changes. The initial
placeholder raises `NotImplementedError` so tests can verify the database layer without a working
compiler.

**Indexing (deferred):** for the POC, dispatch tries all clauses in order. A later pass adds
first-argument indexing and groundness-keyed dispatch: multiple compiled match functions per
predicate, selected at call time by a small decision tree based on which arguments are ground.
`PredicateTable` reserves a `dispatch_index: dict` slot for this.

---

### Step 4 — Compiler: clause head → `match` arm (`clausal.logic.compiler`, part 1)

**Depends on:** Steps 1–3

**Goal:** given a clause head term, produce a Python `match`/`case` arm that tests incoming
arguments against the head pattern without allocating extra objects.

**`head_to_match_pattern(term) -> ast.pattern`** — recursive:

- **`Var`** in head position: `MatchAs(name=var_name)` to capture the argument, then a guard that
  calls `unify(arg, var, trail)`; or for simple cases, `MatchAs` alone and bind inline
- **Python literal** (`int`, `str`, `float`, `True`, `False`, `None`): `MatchLiteral(value)` —
  Python's match checks equality natively, no unification needed
- **Compile-time functor dataclass instance**: `MatchClass(cls=FooClass, kwd_attrs=[...],
  kwd_patterns=[...])` — uses Python's `MATCH_CLASS` opcode, recurses into field patterns
- **`Compound(functor, args)` at compile time**: `MatchClass(cls=Compound, kwd_attrs=["functor",
  "args"], kwd_patterns=[MatchLiteral(f), MatchSequence([...])])` — same opcode, slightly heavier
- **`Var` as functor** (variable predicate call): no static head pattern; defer to runtime dispatch

**`compile_head_to_match_case(head_term, body_stmts) -> ast.match_case`** — outer combinator that
combines the pattern with a trail mark, the body statements, and a fall-through trail undo.

Each clause of a predicate becomes one `case` arm of the outer `match (arg0, arg1, ...)`.
The match is over a tuple of arguments so multiple arguments are tested simultaneously.

---

### Step 5 — Compiler: body goals → continuation chain (`clausal.logic.compiler`, part 2)

**Depends on:** Step 4

**Goal:** compile a goal term into Python statements that execute the goal and, on success, thread
to the continuation.

**`compile_goal(goal: term, trail: str, k: ast.expr) -> list[ast.stmt]`** — dispatches on the
class of `goal` using a Python `match` statement. Because functor types and term types are the
same dataclasses, `case Is(left=a, right=b):` is both the pattern match and the documentation
of intent. No visitor protocol needed.

- **`True`**: emit the continuation statements directly (succeed unconditionally)
- **`False`**: emit nothing (fail unconditionally)
- **`Is(left, right)`** (unify):
  ```python
  mark = trail.mark()
  if unify(left, right, trail):
      <continuation>
  trail.undo(mark)
  ```
- **`IsNot(left, right)`** (dif): for the POC, register a deferred check on the trail; at
  solution time verify `deref(left) != deref(right)` structurally. Full dif via attr-vars is
  deferred to the CLP step.
- **`Eq(left, right)`** (structural equality): `if structural_eq(deref(left), deref(right)):
  <continuation>`
- **`NotEq`**, **`Lt`**, **`LtE`**, **`Gt`**, **`GtE`**: arithmetic/structural comparison guards,
  no trail needed
- **`And(left, right)`** (conjunction): `compile_goal(left, trail, compile_goal(right, trail,
  k))` — right-nested, the trampoline keeps this stack-safe
- **`Or(left, right)`** (disjunction): two `mark/undo` blocks tried in order:
  ```python
  mark = trail.mark()
  <compile_goal(left, trail, k)>
  trail.undo(mark)
  mark = trail.mark()
  <compile_goal(right, trail, k)>
  trail.undo(mark)
  ```
- **`Not(goal)`** (negation-as-failure): run `goal` against a fresh trail copy; if it yields no
  solution, execute `k`; no bindings escape
- **`In(elem, collection)`** (membership): iterate `collection` under `deref`, unify `elem` with
  each element, yield continuation on match, undo on backtrack
- **`NotIn(elem, collection)`**: succeed iff `In` fails
- **`Call(func, args)`** where `func` is a `Var`: `deref(func)` at runtime to get the functor
  string, look up in `db`, call dispatch
- **Predicate call `f(args)`** (compile-time known): `yield from db.dispatch("f", arity)(args,
  trail, k)` inlined as a generator delegation

**`compile_clause(clause: Clause, db: Database) -> ast.FunctionDef`** — wraps:

```python
def foo__2(arg0, arg1, trail, k):
    match (arg0, arg1):
        case <head pattern for clause 1>:
            <compiled body for clause 1>
        case <head pattern for clause 2>:
            <compiled body for clause 2>
```

**`compile_predicate(functor, arity, clauses, db) -> callable`** — calls `compile_clause` for all
clauses, assembles into one `FunctionDef`, compiles via `clausal.codegen.functiondef_to_function`,
stores on `PredicateTable.dispatch_fn`.

---

### WK-VAR — Variable naming: ALL-CAPS and trailing-underscore conventions

**Depends on:** Steps 1–5

**Goal:** Establish clear logic variable conventions that are visually distinct from
Python names, conflict-free with Python's own naming conventions, and natural for
logic programming.

**Two recognised conventions:**

1. **ALL-CAPS** (preferred) — any identifier where every cased character is uppercase
   and there is at least one cased character. Underscores and digits inside are
   allowed. Examples: `X`, `Y`, `HEAD`, `TAIL`, `N1`, `MAX_OF`.

2. **Trailing single underscore** (also valid) — any identifier ending with a single
   `_` that is not a dunder (`__`) and is not the bare wildcard `_`. Examples:
   `X_`, `head_`, `result_`.

**Rule:** `_is_logic_var_name(identifier)` in `clausal/templating/term_rewriting.py`
implements both tests. A bare `_` is always the anonymous wildcard, never a named
variable.

**Changes:**
- `_is_logic_var_name()` helper added to `clausal/templating/term_rewriting.py`.
- `TermTransformer.visit_Name`: uses `_is_logic_var_name` to detect variables.
- `EmbedTransformer.visit_Name`: same — triggers `.value` unbox rewrite.
- `_derive_field_names()`: uses `_is_logic_var_name`; strips trailing `_` before
  lowercasing so `B_` → field `b`, `HEAD` → field `head`.
- All `.clausal` files use ALL-CAPS style.
- All tests and examples updated.

---

### Tool-VIS — Compiled predicate visualizer

**Depends on:** Steps 4–5

**Goal:** Provide a developer tool for inspecting what the compiler generates, as
readable Python source and/or as an AST node tree.  Essential for debugging the
compiler and for validating that generated code looks as expected.

**`clausal/tools/visualize.py`:**
- `predicate_to_source(functor, arity, clauses, db, *, trampoline=False) -> str`
  — builds the predicate's AST and unparses it to Python source via `ast.unparse`
- `predicate_ast(functor, arity, clauses, db, *, trampoline=False) -> ast.FunctionDef`
  — returns the raw `ast.FunctionDef` for further inspection
- `show(functor, arity, clauses, db, *, trampoline=False, mode='source') -> None`
  — prints to stdout; `mode='source'` uses `ast.unparse`, `mode='ast'` uses
  `astpretty.pprint` if available

**Compiler additions** (`clausal/logic/compiler.py`):
- `compile_predicate_ast(functor, arity, clauses, db, ...) -> ast.FunctionDef`
  — like `compile_predicate` but returns the FunctionDef without compiling
- `compile_predicate_trampoline_ast(...)` — same for the trampoline variant

Tests can call `show()` directly; pytest's `-s` flag passes output through.

---

### WK-LAZY — Lazy dispatch and method-swap for dynamic predicates

**Depends on:** Steps 4–5, WK-VAR

**Goal:** When new clauses are added to a predicate at runtime, defer recompilation
until the predicate is actually *called* — not at assert time.  This keeps the
assertz/asserta path cheap and supports fully dynamic rule addition.

**Pattern:** `PredicateTable` gains a `_lazy_recompile: Callable | None` slot.
After the compiler first compiles a predicate it stores a recompile closure on
`_lazy_recompile`.  Subsequent `assertz`/`asserta`/`retract` calls set
`dispatch_fn = None` but leave `_lazy_recompile` intact.  On the next call to
`get_dispatch()`, if `dispatch_fn is None` and `_lazy_recompile` is set, it is
invoked to recompile with the fresh clause list and the result is stored back in
`dispatch_fn`.

```python
# Conceptual closure stored by _install():
def _recompile():
    return compile_predicate(functor, arity, table.clauses, db)
table._lazy_recompile = _recompile
```

No changes to `Database` or `Module` are needed — all state lives on the table.

---

### Step 6 — Import hook wiring

**Depends on:** Steps 3–5

**Goal:** connect the term transformer's output to real runtime behaviour so that importing a
`.clausal` file populates a live database with compiled predicates.

**`$define_predicate(predicate_node, module)`** becomes real:
1. Extract `head` and `body` from the `Predicate` term node (already fully transformed)
2. Create `Clause(head, body_goals)` and call `module.db.assertz(...)`
3. Recompile the entire predicate: call `compile_predicate(functor, arity, all_clauses, module.db)`
4. Install the compiled function in `module.db`'s dispatch slot and optionally in the module
   namespace under a mangled name (e.g. `_clausal_foo__2`) for direct Python call access

**Compiled AST into module bytecode:** predicate `ast.FunctionDef` nodes are injected into
the transformed module's `ast.Module` body *before* `compile()` is called.  This means the
compiled predicate functions end up in the `.pyc` bytecode cached in `__pycache__` alongside
the rest of the module.  On re-import of an unchanged file, Python loads the cached `.pyc`
directly; the predicate functions are already present and no recompilation is needed at
startup.  Only predicates added at runtime via `assertz`/`asserta` (after import) use the
WK-LAZY lazy-recompile path.

**`$assert_fact(term)`** becomes: `module.db.assertz(Clause(term, []))` + recompile.

**Namespace injected into each imported module:**
- `Var`, `Trail`, `Compound` from `clausal.terms` / `clausal.logic.variables`
- `unify`, `deref`, `walk` from `clausal.logic.variables`
- `$module` — the `Module` instance for this file
- `$define_predicate`, `$assert_fact` — as above
- All built-in predicates from `clausal.logic.builtins` (step 8)

The exact mechanism of injection (attribute on the importer, `exec` globals dict, etc.) is not
finalised; the `Module` interface is stable enough to code against independently.

---

### Step 7 — Query API (`clausal.logic.solve`)

**Depends on:** Steps 5–6, `clausal.trampoline`, `clausal.continuation_search`

**Goal:** make logic predicates callable from Python with a clean iterator interface.

**`solve(goal, module, trail=None) -> Iterator`**:
- Compiles `goal` (or looks up if already compiled)
- Creates a fresh `Trail` if none provided
- Top-level continuation `k` simply `yield`s the current trail state
- Wraps in `continuation_search.Search` so the greenlet drives the trampoline and surfaces
  solutions one at a time through the iterator protocol

**`query(goal, variables: dict[str, Var], module) -> Iterator[dict[str, Any]]`**:
- Yields `{name: deref_term(var, trail)}` for each solution — fully dereferenced, ready to use

**`once(goal, module) -> dict[str, Any] | None`**:
- Returns the first solution dict or `None`

**`call(functor, *args, module)`**:
- Python-callable entry: looks up `(functor, len(args))` in `module.db`, calls dispatch

The composition: greenlet (from `continuation_search`) runs the trampoline (from
`clausal.trampoline`); the trampoline drives the compiled generator chain; each `yield` from the
chain surfaces a solution through the greenlet's `switch`, which the `Search` iterator delivers to
the caller.

---

### Step 8 — Built-ins and standard library (`clausal.logic.builtins`, `clausal.logic.stdlib`)

**Depends on:** Step 7

**Goal:** a complete set of primitive predicates and a standard library of useful predicates
written in the clausal DSL itself.

**Built-ins** (implemented as compiled generator functions in `clausal.logic.builtins`):

| Name | Semantics |
|---|---|
| `True` | succeed once |
| `False` | fail |
| `X is Y` | unify X with Y (also handles deref of both sides) |
| `X is not Y` | dif constraint |
| `X == Y` | structural equality test |
| `X != Y` | structural inequality |
| `X in Y` | membership / enumeration |
| `X not in Y` | non-membership |
| `not X` | negation-as-failure |
| `functor(T, F, A)` | decompose term into functor name and arity |
| `arg(N, T, A)` | Nth argument of compound term |
| `T =.. L` | univ: compound ↔ `[functor | args]` list |
| `assert(C)` | add clause to database at runtime |
| `retract(C)` | remove matching clause |
| Arithmetic: `+`, `-`, `*`, `//`, `%`, `**` | in `is`-goals (right-hand side evaluation) |
| `==+` / `== +()` | stub → `NotImplementedError`, future CLP(FD) |

**Standard library** (`clausal.logic.stdlib` — written in the clausal DSL):
- `append/3`, `length/2`, `last/2`, `reverse/2`, `nth/3`, `flatten/2`
- `between/3`, `succ/2`, `plus/3`
- `msort/2`, `sort/2`
- `atom/1`, `number/1`, `integer/1`, `float/1`, `string/1`, `compound/1`, `var/1`, `nonvar/1`

These exercise the full stack end-to-end and serve as both library predicates and integration tests.

---

### Step 9 — Tests and regression suite

**Depends on:** Steps 1–8

**`tests/test_terms.py`**: term construction, `Compound`, `term_str`, list ↔ cons conversion,
Python literals as terms

**`tests/test_unify.py`**: var-var, var-ground, compound match/mismatch, structural equality,
`is not` / dif basics, nested terms, occurs-check

**`tests/test_database.py`**: assertz, asserta, retract, recompile on change, lookup by
functor/arity, duplicate and empty cases

**`tests/test_compiler.py`**: compile single-clause and multi-clause predicates; inspect
generated AST structure; verify head pattern types (literal, class, Compound, Var)

**`tests/test_search.py`**: classic programs that validate the full search stack:
- `append/3` — covers conjunction, recursive call, list matching
- `permutation/2` — covers member enumeration on backtrack
- `last/2` — covers linear recursion
- N-queens (N = 4, 5) — covers conjunction, arithmetic comparison, negation-as-failure
- Fibonacci via arithmetic — covers `is`-goals with arithmetic evaluation

**`tests/test_compiled_programs.py`**: meatier end-to-end tests that exercise the
compiled predicates with realistic programs (no import hook needed):
- Graph reachability (`edge/2` facts + `path/2` transitive closure via predicate calls)
- Classification (`animal/2` with multiple compound-head clauses, dataclass patterns)
- Fibonacci via accumulator (arithmetic Is goals + recursive calls)
- Combination search (multiple predicate calls in conjunction, verifying all solutions)
- N-queens (4×4) — arithmetic constraints + negation-as-failure, no stack overflow

**`tests/test_import.py`**: import a `.clausal` source file, call predicates from Python via
`solve` / `query`, verify solutions, verify re-assert at runtime

---

## Deferred (not blocking the POC)

- **First-argument indexing** — dispatch selects subset of clauses by the deref'd first argument
  type/value; `PredicateTable.dispatch_index` reserved for this
- **Groundness-keyed dispatch** — multiple compiled match functions per predicate, selected at
  call time by a decision tree over which arguments are ground; callable via a dict keyed on
  groundness bit-vector
- **Full dif via attribute variables** — proper `dif/2` propagation using attr-var hooks from
  `clausal.logic.variables`; POC uses deferred check at solution time
- **CLP(FD) arithmetic constraints** — `==+` / `== +()` operator; requires a constraint store
  and propagation engine
- **Tabling (SLG resolution)** — memoised subgoal calls; suspending and resuming on new answers;
  prevents infinite loops on recursive predicates
- **Well-founded semantics** — three-valued semantics for negation in recursive predicates;
  requires tabling as foundation
- **Compiled bytecode caching** — cache compiled dispatch functions across import sessions
- **Type-directed dispatch** — use Python type annotations on predicate arguments to narrow
  dispatch at compile time
