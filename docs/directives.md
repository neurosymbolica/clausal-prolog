# Directives

Directives are module-level declarations in `.clausal` files that control predicate properties, imports, and compilation behavior. They are prefixed with `-` and placed at the top of the file.

---

## Module Declaration

```clausal
-module(my_module, [Pred1(A, B), Pred2(X)])
```

Declares the module name and its public exports. The export list specifies which predicates are accessible to importers. If omitted, the module name is derived from the filename.

### -private

```clausal
-private([Helper(X, Y), Edge(A, B)])
```

Declares predicates that are internal to the module. Private predicates get proper `PredicateMeta` classes but are not exposed for import.

---

## Import Directives

### -import_from

Import specific predicates from another module:

```clausal
# skip
-import_from(utils, [Double, Helper])
```

With aliasing:

```clausal
# skip
-import_from(utils, [alias(Double, MyDouble)])
```

This imports `Double` from `utils` but makes it available locally as `MyDouble`.

### -import_module

Import all exported predicates from a module:

```clausal
# skip
-import_module(utils)
```

Imported predicates are accessed via qualified names: `utils.Double(X, Y)`.

See [Import System](import.md) for full details.

---

## Predicate Property Directives

### -dynamic

**Problem**: By default, predicates are locked after loading — you can't change
them at runtime. But some programs need to add or remove facts during execution
(counters, caches, learned knowledge).

```clausal
-dynamic(color/1)

color("red"),

Test("add at runtime") <- (
    Assert(color("blue")),
    color("blue")
)
```

Without `-dynamic`, the `Assert` call above would raise a `RuntimeError`.
See [Database Operations](database_ops.md) for full details.

### -table

**Problem**: Recursive predicates can loop infinitely or recompute the same
subproblems. Tabling automatically caches answers and handles left-recursive
definitions.

```clausal
-table(path/2)

edge(1, 2),
edge(2, 3),
edge(3, 1),

path(X, Y) <- edge(X, Y)
path(X, Y) <- (edge(X, Z), path(Z, Y))

Test("path 1 3") <- path(1, 3)
Test("path 2 1") <- path(2, 1)
```

Without `-table`, `path/2` would loop forever on the cycle `1→2→3→1`. With
tabling, it terminates and returns all reachable pairs. Also required for
[Well-Founded Semantics](wfs.md).

See [Tabling](tabling.md) for details.

### -discontiguous

**Problem**: By default, all clauses for a predicate must be grouped together
in the source file. Sometimes it's clearer to interleave related predicates.

```clausal
-discontiguous(Test/1)

helper(X, Y) <- (Y == X + 1)
Test("first") <- helper(1, 2)

other_helper(X, Y) <- (Y == X * 2)
Test("second") <- other_helper(3, 6)
```

Without `-discontiguous`, the `Test` clauses being separated by `other_helper`
would trigger a warning or error.

### -meta_predicate

**Problem**: When higher-order predicates are imported across modules, the
module system needs to know which arguments are goals (to resolve them in the
correct module context).

```clausal
# skip
-meta_predicate(my_map(2, +, -))
```

The `2` means the first argument is a goal that takes 2 extra arguments.
`+` means input, `-` means output. This ensures correct cross-module
resolution when `my_map` is imported. See [Higher-Order Predicates](higher_order.md) for builtins like `MapList` that use this pattern.

### -shallow

**Problem**: The default trampoline compilation mode has slight overhead for
stack safety. For predicates known to have bounded recursion depth (lookups,
simple dispatches), this overhead is unnecessary.

```clausal
-shallow(lookup/2)

lookup("a", 1),
lookup("b", 2),
lookup("c", 3),

Test("lookup a") <- (lookup("a", V), V == 1)
Test("lookup c") <- (lookup("c", V), V == 3)
```

`-shallow` compiles in simple mode (direct generator calls) instead of
trampoline mode. Use it for flat, non-recursive predicates where performance
matters. See [Compiler](compiler.md) for details on the two compilation modes.

---

## Specialization Directive

### -specialize

```clausal
# skip
-specialize(SolveCount, NatnumProgram, alias=SolveCountNatnum)
```

Specializes a [meta-interpreter](metainterpreters.md) with respect to an object program, producing a new predicate with interpretation overhead removed. The MI pattern is auto-detected from the clause structure.

Options:

```clausal
# skip
-specialize(MI, Source, alias=Name, depth=5)     # deep unfolding
-specialize(MI, Source, alias=Name, cpd=True)     # conjunctive partial deduction
```

See [Meta-Interpreter Specialization](specialization.md) for full details.

---

## EDCG Directives

!!! warning "Experimental"
    EDCG directives are parsed but end-to-end rewriting is not yet implemented.

Extended DCGs allow multiple named accumulators and passed arguments to be threaded through grammar rules automatically. See [DCGs](dcg.md) for the standard DCG system.

### -edcg_acc

```clausal
-edcg_acc(counter, X, IN, OUT, {OUT == IN + X})
```

Declares a named accumulator with its joining operation. Arguments: name, value variable, input state, output state, and joiner goal.

### -edcg_pass

```clausal
-edcg_pass(scale)
```

Declares a passed argument — a value that threads through EDCG nonterminals without modification (read-only).

### -edcg_pred

```clausal
# skip
-edcg_pred(scaled_inc, 0, [counter, scale])
```

Declares how many visible arguments a predicate has and which accumulators/passed arguments it uses.

---

## Directive Processing

Directives are processed during module loading:

1. The term transformer parses `-directive(...)` syntax into directive AST nodes
2. The compiler (v2 pipeline) processes directives before clause compilation via `_process_directives`
3. Property directives set metadata flags on the predicate's `PredicateMeta` class (see [Predicates](predicates.md))
4. Import directives trigger module loading and predicate injection (see [Import System](import.md))

Directives apply to the entire module — they cannot be scoped to individual clauses.

---

??? info "Test coverage"

    Tests are in `tests/test_directives.py` (21 tests).

    - **Dynamic**: predicate metadata, runtime assert/retract, locking of non-dynamic predicates
    - **Discontiguous**: scattered clause collection
    - **Table**: tabling metadata, SLG resolution
    - **Parsing**: directive syntax recognition, arity extraction
    - **Import-level locking**: predicates locked after load, dynamic predicates remain mutable

---

*See also: [Predicates](predicates.md) — how predicates and clauses work.*
*See also: [Import System](import.md) — full details on `-import_from` and `-import_module`.*
*See also: [Tabling](tabling.md) — SLG tabling enabled by `-table`.*
*See also: [Database Operations](database_ops.md) — `Assert`/`Retract` builtins that require `-dynamic`.*
