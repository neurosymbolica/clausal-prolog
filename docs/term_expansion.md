# Term & Goal Expansion

Term expansion and goal expansion are compile-time transformation passes that rewrite clauses and goals before compilation. They enable metaprogramming, syntactic sugar, and optimization.

Term expansion and goal expansion are separate compilation passes.

---

## Term Expansion

Term expansion rewrites module items (clauses, facts, directives) at load time.

### Writing Expansion Rules

Define `TermExpansion/4` clauses in a `.clausal` file:

```
TermExpansion(Input_, Output_, ModuleState_, NewState_) <- (
    # transform Input_ into Output_
    ...
)
```

Arguments:

- **Input_** — the original module item (clause or fact)
- **Output_** — the transformed item (or list of items for one-to-many expansion)
- **ModuleState_** — current state threaded through expansions
- **NewState_** — updated state after this expansion

### Importing Expansion Rules

Expansion rules can be imported from other modules:

```
-import_from(expansion_provider, [TermExpansion])
```

Imported expansion rules apply to items in the importing module.

### Built-in Expansions

- **Identity**: if no rule matches, the item passes through unchanged
- **Suppression**: return an empty list to suppress an item
- **One-to-many**: return a list to expand one item into multiple

### Init/Final Injection

Term expansion can inject initialization and finalization clauses:

- `_init` predicates are added at the start of the module
- `_final` predicates are added at the end

### q() Quasi-Quotation

The `q()` function creates term templates in expansion rules:

```
TermExpansion(q(double_fact(X_)), [q(fact(X_)), q(fact(X_))], S_, S_)
```

`q()` quotes a term so it can be manipulated as data during expansion.

---

## Goal Expansion

Goal expansion rewrites individual goals within clause bodies at compile time.

### Built-in Goal Expansions

The goal expansion pass (`clausal/logic/goal_expansion.py`) applies these transformations:

**Regex auto-binding**: Named capture groups with ALLCAPS or trailing-underscore names are automatically bound to clause variables:

```
# Before expansion:
Match(r"(?P<YEAR>\d{4})-(?P<MONTH>\d{2})", S_)

# After expansion (conceptual):
Match(r"(?P<YEAR>\d{4})-(?P<MONTH>\d{2})", S_, G_),
YEAR_ is G_["YEAR"], MONTH_ is G_["MONTH"]
```

**Pattern precompilation**: String-literal regex patterns are compiled to `re.Pattern` objects at load time.

**Dotted-name support**: Qualified calls like `module.Pred(X_)` are resolved during goal expansion.

### How It Works

Goal expansion runs after term expansion and before compilation:

1. Walk each goal in a clause body
2. For each goal, check if any expansion rule applies
3. Replace the goal with its expansion
4. Continue until no more expansions apply

---

## Pipeline

The compiler pipeline orchestrates both expansions:

```
.clausal source
    → parse (TermTransformer)
    → term expansion (run_term_expansion)
    → goal expansion (run_goal_expansion)
    → compilation (compile_module)
```

`compiler_v2.compile_module()` coordinates the full pipeline.

---

??? info "Test coverage"

    - `tests/test_term_expansion.py` (25 tests): pass-through, detection, identity, suppression, one-to-many, module state, init/final injection, imported TE rules, new functors, q() quasi-quotation, full pipeline integration
    - `tests/test_regex.py` (93 tests): goal expansion for regex auto-binding and precompilation
