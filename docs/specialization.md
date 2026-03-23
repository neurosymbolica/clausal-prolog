# Meta-Interpreter Specialization

Meta-interpreters (MIs) are one of the most powerful features of logic programming: write a small interpreter, extend it with tracing, counting, depth limiting, or proof trees, and run any object program through it. The cost is interpretation overhead — every goal resolution goes through `MatchClause`, `CopyTerm`, list manipulation, and recursive calls.

**Partial deduction** (partial evaluation for logic programs) eliminates this overhead. Specializing an MI with respect to a known object program produces a residual program structurally identical to the object program, but with the MI's extensions woven directly into the compiled code. This is the **first Futamura projection** applied to logic programming.

The implementation lives in `clausal.logic.specialization`.

---

## The meta-interpreters

Clausal ships five MIs ported from Triska's [acomip](https://www.metalevel.at/acomip/), all available via:

```clausal
-import_from(clausal.examples.metainterpreters, [Solve, SolveCount, SolveLimit, SolveTree])
```

| MI | Signature | Extension |
|---|---|---|
| `Solve` | `(GOALS, PROGRAM)` | None — vanilla |
| `SolveCount` | `(GOALS, PROGRAM, COUNT)` | Counts inference steps |
| `SolveLimit` | `(GOALS, PROGRAM, MAX_DEPTH)` | Depth-bounded search |
| `SolveIterativeDeepening` | `(GOALS, PROGRAM)` | Complete search via iterative deepening |
| `SolveTree` | `(GOALS, PROGRAM, TREE)` | Builds proof trees |

Object programs are represented as lists of `[Head, BodyGoals]` pairs, where terms use list form: `f(A, B)` becomes `["f", A, B]`.

---

## Using specialization

### The `-specialize` directive

```clausal
-import_from(clausal.examples.metainterpreters, [SolveCount])

NatnumProgram(PROGRAM) <- (
    PROGRAM is [
        [["natnum", 0], []],
        [["natnum", ["s", X]], [["natnum", X]]]
    ]
)

-specialize(SolveCount, NatnumProgram, alias=SolveCountNatnum)
```

This produces a new predicate `SolveCountNatnum` that:

- Resolves `natnum` goals at full compiled speed (no `MatchClause`, no `Append`)
- Preserves the counting extension from `SolveCount`
- Drops the `PROGRAM` argument (it was static)

Call it directly:

```clausal
# skip
Test("count natnum(s(s(0)))") <- SolveCountNatnum([["natnum", ["s", ["s", 0]]]], 3)
```

### Directive syntax

```
-specialize(MI, Source, alias=Name)
-specialize(MI, Source, alias=Name, depth=N)
-specialize(MI, Source, alias=Name, cpd=True)
```

| Parameter | Required | Description |
|---|---|---|
| `MI` | yes | Meta-interpreter predicate name |
| `Source` | yes | Nullary predicate returning the object program |
| `alias` | yes | Name for the specialized predicate |
| `depth` | no | Deep unfolding depth (default 0 = shallow) |
| `cpd` | no | Enable conjunctive partial deduction / deforestation (default False) |

The MI pattern (goal-list arg, program arg, extra args, recursive style) is recognized automatically from the clause structure — no separate `-metainterpreter` declaration is needed.

---

## What the specializer produces

### Vanilla MI (Solve)

Given the natnum program, `Solve` is specialized to:

```
SolveNatnum([], )                                              # base case
SolveNatnum([["natnum", 0], *GOALS]) <- SolveNatnum(GOALS)     # fact
SolveNatnum([["natnum", ["s", X]], *GOALS]) <-                  # rule
    SolveNatnum([["natnum", X], *GOALS])
```

The `MatchClause`/`Append` machinery is gone. One clause per object clause, plus the base case.

### Counting MI (SolveCount)

```
SolveCountNatnum([], 0)
SolveCountNatnum([["natnum", 0], *GOALS], COUNT) <- (
    SolveCountNatnum(GOALS, SUB_COUNT),
    COUNT := SUB_COUNT + 1
)
SolveCountNatnum([["natnum", ["s", X]], *GOALS], COUNT) <- (
    SolveCountNatnum([["natnum", X], *GOALS], SUB_COUNT),
    COUNT := SUB_COUNT + 1
)
```

The counting logic is woven into each clause. The program argument is gone.

### Object programs with builtins

When an object program uses goals that aren't defined in the program itself (arithmetic, comparisons, etc.), the specializer generates a catch-all clause that dispatches unknown goals through a runtime resolver:

```clausal
# skip
# Factorial uses gt, sub, mul — these are residual goals
-specialize(Solve, FactorialProgram, alias=SolveFactorial)
```

The catch-all handles `gt`, `gte`, `lt`, `lte`, `eq`, `neq`, `add`, `sub`, `mul`, `div`, `mod`, and `true` automatically. User-defined predicates in the module dict are also resolved.

---

## Deep unfolding

With `depth=N`, the specializer recursively unfolds body goals that match object-program heads, up to N levels:

```clausal
# skip
-specialize(SolveCount, NatnumProgram, alias=DeepCount, depth=5)
```

Termination is guaranteed by:

1. **Homeomorphic embedding test** — if a newly generated goal is structurally "bigger" than an ancestor in the unfolding tree, unfolding stops for that branch.
2. **Depth counter** — never unfolds more than N levels deep.
3. **Memoization table** — tracks which goal patterns have been specialized to prevent duplicate work.

Deep unfolding inlines deterministic goals (single matching object clause), producing more specific clause heads at the cost of more clauses.

---

## Conjunctive partial deduction (CPD)

With `cpd=True`, the specializer applies **deforestation** — eliminating intermediate goal-list constructions by unfolding the first goal in a constructed list against *all* matching object clauses:

```clausal
# skip
-specialize(Solve, GraphProgram, alias=SolveGraphCpd, cpd=True)
```

### Before CPD (Phase 1 output)

```
SolveGraph([["path", X, Y], *GOALS]) <-
    SolveGraph([["edge", X, Z], ["path", Z, Y], *GOALS])
```

The body constructs a 3+ element list at runtime, only to immediately decompose it via pattern matching.

### After CPD

```
SolveGraph([["path", "a", Y], *GOALS]) <- SolveGraph([["path", "b", Y], *GOALS])
SolveGraph([["path", "b", Y], *GOALS]) <- SolveGraph([["path", "c", Y], *GOALS])
SolveGraph([["path", "b", Y], *GOALS]) <- SolveGraph([["path", "d", Y], *GOALS])
```

The intermediate list is eliminated — edge matching is inlined directly into the clause heads.

### Pre/post-match chaining

CPD correctly preserves MI extensions:

- **Counting MIs** (SolveCount): each inlined step adds its own `COUNT := SUB_COUNT + 1` via post-match goal chaining.
- **Depth-limited MIs** (SolveLimit): each inlined step adds its own `MAX > 0, MAX1 := MAX - 1` via pre-match goal chaining.

---

## Recognized MI patterns

The specializer automatically recognizes two MI styles:

### Tail-recursive (Pattern A)

Used by `Solve`, `SolveCount`, `SolveLimit`:

```
MI([], ...)                                   # base
MI([GOAL, *GOALS], PROGRAM, ...) <- (         # recursive
    MatchClause(GOAL, BODY, PROGRAM),
    Append(BODY, GOALS, ALL_GOALS),
    MI(ALL_GOALS, PROGRAM, ...)
)
```

### Split / non-tail-recursive (Pattern B)

Used by `SolveTree`:

```
MI([], ..., [])                               # base
MI([GOAL, *GOALS], PROGRAM, ...) <- (         # recursive
    MatchClause(GOAL, BODY, PROGRAM),
    MI(BODY, PROGRAM, BODY_TREE),
    MI(GOALS, PROGRAM, GOALS_TREE)
)
```

### Extra arguments

Pre-match goals (before `MatchClause`, e.g. depth check in `SolveLimit`) and post-match goals (after the recursive call, e.g. counting in `SolveCount`) are detected automatically and preserved in specialized clauses.

---

## Pipeline integration

Specialization runs as Step 6b in the `compile_module()` pipeline — after all predicates are compiled (so source programs can be evaluated) and before non-dynamic predicates are locked:

```
compile_module()
├─ Step 0: _process_imports()
├─ Step 1: run_term_expansion()
├─ Step 1b: run_goal_expansion()
├─ Step 1c: _preregister_specializations()    ← empty class created
├─ Step 2: _process_directives()
├─ Step 3: _process_declarations()
├─ Step 4: assert clauses
├─ Step 5: compile predicates
├─ Step 6: wrap tabled
├─ Step 6b: _run_specialization()             ← clauses unfolded + compiled
└─ Step 7: lock non-dynamic
```

Pre-registration at Step 1c creates an empty `PredicateMeta` class so that later clauses (e.g. `Test` predicates) can reference the specialized predicate during compilation.

---

??? info "Test coverage"

    Tests are in `tests/test_specialization.py` (155 tests) and
    `tests/test_specialization_pipeline.py` (62 tests).

    - **Phase 0**: MI pattern recognition on all five MIs
    - **Phase 1**: Core unfolding with natnum and graph programs
    - **Phase 3**: Residual goal dispatch for builtins and external calls
    - **Phase 4**: Deep unfolding with termination control
    - **Phase 5**: Conjunctive partial deduction / deforestation
    - **Pipeline**: End-to-end `.clausal` fixtures for all specialization modes
    - **Equivalence**: Specialized predicates produce identical results to unspecialized MIs

    Fixtures: `specialize_natnum.clausal`, `specialize_graph.clausal`,
    `specialize_limit.clausal`, `specialize_builtins.clausal`,
    `specialize_deep.clausal`, `specialize_cpd.clausal`.

---

*See also: [Indexing](indexing.md) — first-argument indexing and groundness-keyed dispatch · [Compiler](compiler.md) — the underlying compilation pipeline.*
