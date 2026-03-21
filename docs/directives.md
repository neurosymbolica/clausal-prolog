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

```clausal
-dynamic(color/2)
```

Marks a predicate as dynamic — its clauses can be modified at runtime via `Assert/1`, `AssertFirst/1`, and `Retract/1`. Without this directive, predicates are locked after module loading and assertion attempts raise an error.

### -table

```clausal
-table(path/2)
```

Enables SLG tabling (memoization) for a predicate. Tabled predicates automatically cache answers and handle left-recursive definitions that would otherwise loop. Required for well-founded semantics with negation.

See [Tabling](tabling.md) for details.

### -discontiguous

```clausal
-discontiguous(helper/1)
```

Allows clauses for a predicate to be scattered throughout the file rather than grouped together. Without this, the compiler assumes all clauses for a predicate are contiguous and may warn or error.

### -meta_predicate

```clausal
# skip
-meta_predicate(map(2, +, -))
```

Declares the meta-predicate calling convention. Used by the module system for correct import handling of higher-order predicates.

### -shallow

```clausal
-shallow(lookup/2)
```

Compiles a predicate in simple (non-trampoline) mode. This avoids the overhead of the trampoline protocol for predicates known to have bounded recursion depth. The default is trampoline mode for stack safety.

---

## EDCG Directives

!!! warning "Experimental"
    EDCG directives are parsed but end-to-end rewriting is not yet implemented.

Extended DCGs allow multiple named accumulators and passed arguments to be threaded through grammar rules automatically.

### -edcg_acc

```clausal
-edcg_acc(counter, X, IN, OUT, {OUT := IN + X})
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
3. Property directives set metadata flags on the predicate's `PredicateMeta` class
4. Import directives trigger module loading and predicate injection

Directives apply to the entire module — they cannot be scoped to individual clauses.

---

??? info "Test coverage"

    Tests are in `tests/test_directives.py` (21 tests).

    - **Dynamic**: predicate metadata, runtime assert/retract, locking of non-dynamic predicates
    - **Discontiguous**: scattered clause collection
    - **Table**: tabling metadata, SLG resolution
    - **Parsing**: directive syntax recognition, arity extraction
    - **Import-level locking**: predicates locked after load, dynamic predicates remain mutable
