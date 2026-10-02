# Meta-Interpreter Specialization

[Meta-interpreters](metainterpreters.md) (MIs) are one of the most powerful features of logic programming: write a small interpreter, extend it with tracing, counting, depth limiting, or proof trees, and run any object program through it. The cost is interpretation overhead — every goal resolution goes through `match_clause`, `copy_term`, list manipulation, and recursive calls.

**Partial deduction** (partial evaluation for logic programs) eliminates this overhead. Specializing an MI with respect to a known object program produces a residual program structurally identical to the object program, but with the MI's extensions woven directly into the compiled code. This is the **first Futamura projection** applied to logic programming.

The implementation lives in `clausal.logic.specialization`.

---

## The meta-interpreters

Clausal ships five MIs ported from Triska's [acomip](https://www.metalevel.at/acomip/), all available via:

```seam
-import_from(clausal.examples.metainterpreters, [solve, solve_count, solve_limit, solve_tree])
```

| MI | signature | Extension |
|---|---|---|
| `solve` | `(GOALS, PROGRAM)` | None — vanilla |
| `solve_count` | `(GOALS, PROGRAM, COUNT)` | Counts inference steps |
| `solve_limit` | `(GOALS, PROGRAM, MAX_DEPTH)` | Depth-bounded search |
| `solve_iterative_deepening` | `(GOALS, PROGRAM)` | Complete search via iterative deepening |
| `solve_tree` | `(GOALS, PROGRAM, TREE)` | Builds proof trees |

Object programs are represented as lists of `[Head, BodyGoals]` pairs, where terms use list form with an **atom** in first place: `f(A, B)` becomes `['f', A, B]` (a `"f"` would be a string, not an atom).

---

## Using specialization

### The `-specialize` directive

```seam
-import_from(clausal.examples.metainterpreters, [solve_count])

natnum_program(PROGRAM) <- (
    PROGRAM is [
        [['natnum', 0], []],
        [['natnum', ['s', X]], [['natnum', X]]]
    ]
)

-specialize(solve_count, natnum_program, alias=solve_count_natnum)
```

This produces a new predicate `solve_count_natnum` that:

- Resolves `natnum` goals at full compiled speed (no `match_clause`, no `append`)
- Preserves the counting extension from `solve_count`
- Drops the `PROGRAM` argument (it was static)

Call it directly:

```seam
--8<-- "tests/fixtures/docs/specialization_sigs.txt:count_natnum_test"
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

### Vanilla MI (solve)

Given the natnum program, `solve` is specialized to:

```
solve_natnum([], )                                              # base case
solve_natnum([['natnum', 0], *GOALS]) <- solve_natnum(GOALS)     # fact
solve_natnum([['natnum', ['s', X]], *GOALS]) <-                  # rule
    solve_natnum([['natnum', X], *GOALS])
```

The `match_clause`/`append` machinery is gone. One clause per object clause, plus the base case.

### Counting MI (solve_count)

```
solve_count_natnum([], 0)
solve_count_natnum([['natnum', 0], *GOALS], COUNT) <- (
    solve_count_natnum(GOALS, SUB_COUNT),
    COUNT == SUB_COUNT + 1
)
solve_count_natnum([['natnum', ['s', X]], *GOALS], COUNT) <- (
    solve_count_natnum([['natnum', X], *GOALS], SUB_COUNT),
    COUNT == SUB_COUNT + 1
)
```

The counting logic is woven into each clause. The program argument is gone.

### Object programs with builtins

when an object program uses goals that aren't defined in the program itself (arithmetic, comparisons, etc.), the specializer generates a catch-all clause that dispatches unknown goals through a runtime resolver:

```seam
--8<-- "tests/fixtures/docs/specialization_sigs.txt:specialize_factorial"
```

The catch-all handles `gt`, `gte`, `lt`, `lte`, `eq`, `neq`, `add`, `sub`, `mul`, `div`, `mod`, and `true` automatically. User-defined predicates in the module dict are also resolved.

---

## Deep unfolding

With `depth=N`, the specializer recursively unfolds body goals that match object-program heads, up to N levels:

```seam
--8<-- "tests/fixtures/docs/specialization_sigs.txt:deep_unfolding"
```

Termination is guaranteed by:

1. **Homeomorphic embedding test** — if a newly generated goal is structurally "bigger" than an ancestor in the unfolding tree, unfolding stops for that branch.
2. **Depth counter** — never unfolds more than N levels deep.
3. **Memoization table** — tracks which goal patterns have been specialized to prevent duplicate work.

Deep unfolding inlines deterministic goals (single matching object clause), producing more specific clause heads at the cost of more clauses.

---

## Conjunctive partial deduction (CPD)

With `cpd=True`, the specializer applies **deforestation** — eliminating intermediate goal-list constructions by unfolding the first goal in a constructed list against *all* matching object clauses:

```seam
--8<-- "tests/fixtures/docs/specialization_sigs.txt:cpd_directive"
```

### Before CPD (Phase 1 output)

```
solve_graph([['path', X, Y], *GOALS]) <-
    solve_graph([['edge', X, Z], ['path', Z, Y], *GOALS])
```

The body constructs a 3+ element list at runtime, only to immediately decompose it via pattern matching.

### After CPD

```
solve_graph([['path', 'a', Y], *GOALS]) <- solve_graph([['path', 'b', Y], *GOALS])
solve_graph([['path', 'b', Y], *GOALS]) <- solve_graph([['path', 'c', Y], *GOALS])
solve_graph([['path', 'b', Y], *GOALS]) <- solve_graph([['path', 'd', Y], *GOALS])
```

The intermediate list is eliminated — edge matching is inlined directly into the clause heads.

### Pre/post-match chaining

CPD correctly preserves MI extensions:

- **Counting MIs** (solve_count): each inlined step adds its own `COUNT == SUB_COUNT + 1` via post-match goal chaining.
- **Depth-limited MIs** (solve_limit): each inlined step adds its own `MAX > 0, MAX1 == MAX - 1` via pre-match goal chaining.

---

## Recognized MI patterns

The specializer automatically recognizes two MI styles:

### Tail-recursive (Pattern A)

Used by `solve`, `solve_count`, `solve_limit`:

```
MI([], ...)                                   # base
MI([GOAL, *GOALS], PROGRAM, ...) <- (         # recursive
    match_clause(GOAL, BODY, PROGRAM),
    append(BODY, GOALS, ALL_GOALS),
    MI(ALL_GOALS, PROGRAM, ...)
)
```

### Split / non-tail-recursive (Pattern B)

Used by `solve_tree`:

```
MI([], ..., [])                               # base
MI([GOAL, *GOALS], PROGRAM, ...) <- (         # recursive
    match_clause(GOAL, BODY, PROGRAM),
    MI(BODY, PROGRAM, BODY_TREE),
    MI(GOALS, PROGRAM, GOALS_TREE)
)
```

### Extra arguments

Pre-match goals (before `match_clause`, e.g. depth check in `solve_limit`) and post-match goals (after the recursive call, e.g. counting in `solve_count`) are detected automatically and preserved in specialized clauses.

---

## Pipeline integration

Specialization runs as Step 6b in the [`compile_module()` pipeline](compiler.md) — after all predicates are compiled (so source programs can be evaluated) and before non-dynamic predicates are locked:

```
compile_module()
├─ Step 0: _process_imports()
├─ Step 1: [run_term_expansion()](term_expansion.md)
├─ Step 1b: run_goal_expansion()
├─ Step 1c: _preregister_specializations()    ← empty row + handle registered
├─ Step 2: _process_directives()
├─ Step 3: _process_declarations()
├─ Step 4: assert clauses
├─ Step 5: compile predicates
├─ Step 6: [wrap tabled](tabling.md)
├─ Step 6b: _run_specialization()             ← clauses unfolded + compiled
└─ Step 7: lock non-dynamic
```

Pre-registration at Step 1c registers the specialized predicate's empty row and binds its handle, so that later clauses (e.g. `test` predicates) can reference the specialized predicate during compilation.

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

    Fixtures: `specialize_natnum.seam`, `specialize_graph.seam`,
    `specialize_limit.seam`, `specialize_builtins.seam`,
    `specialize_deep.seam`, `specialize_cpd.seam`.

---

*See also: [Indexing](indexing.md) — first-argument indexing and groundness-keyed dispatch · [Compiler](compiler.md) — the underlying compilation pipeline.*
