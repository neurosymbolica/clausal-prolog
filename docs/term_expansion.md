# Term & Goal Expansion

Term expansion and goal expansion are compile-time transformation passes that rewrite clauses and goals before compilation. They enable metaprogramming, syntactic sugar, and optimization — transforming what you write into what the compiler sees.

---

## Quick Example

```clausal
# skip
# Every fact automatically gets a "logged" wrapper
TermExpansion(
    q(fact(X)),
    [q(fact(X)), q(logged_fact(X))],
    STATE, STATE
)

fact("a"),
fact("b"),
# After expansion, the module also contains:
# logged_fact("a"), logged_fact("b")
```

---

## Term Expansion

Term expansion rewrites module items (clauses, facts, directives) at load time, before compilation. Define `TermExpansion/4` clauses to transform your source.

### Writing Expansion Rules

```clausal
# skip
TermExpansion(INPUT, OUTPUT, MODULE_STATE, NEW_STATE) <- (
    # transform INPUT into OUTPUT
    ...
)
```

Arguments:

- **INPUT** — the original module item (a quoted term)
- **OUTPUT** — the transformed item (or list of items for one-to-many expansion)
- **MODULE_STATE** — current state threaded through all expansions
- **NEW_STATE** — updated state after this expansion

### Identity Expansion

If no rule matches an item, it passes through unchanged. You can also write an explicit identity rule:

```clausal
# skip
TermExpansion(ITEM, ITEM, STATE, STATE) <- True
```

### Suppressing Items

Return an empty list to remove an item from the module:

```clausal
# skip
# Remove all facts for "debug" predicate
TermExpansion(q(debug(X)), [], STATE, STATE) <- True
```

### One-to-Many Expansion

Return a list to expand one item into multiple items. This is the most powerful pattern — it lets a single declaration generate multiple clauses:

```clausal
# skip
# Duplicate every item (expansion_provider.clausal)
TermExpansion(TERM, [TERM, TERM], STATE, STATE) <- True
```

**Walkthrough**: When this rule is active and the module contains `color("red"),`:

1. The expansion engine matches `color("red")` against `TERM`
2. OUTPUT becomes `[color("red"), color("red")]`
3. The module now has two copies of `color("red")`

### q() Quasi-Quotation

The `q()` function creates term templates in expansion rules. It quotes a term so it can be manipulated as data:

```clausal
# skip
# Without q(): the expansion rule would try to CALL double_fact(X)
# With q(): double_fact(X) is treated as data to be transformed
TermExpansion(q(double_fact(X)), [q(fact(X)), q(fact(X))], S, S)
```

Variables inside `q()` are shared between the pattern and the replacement. In the example above, `X` in the input pattern is the same `X` in both output terms.

### Module State Threading

The STATE arguments thread a value through all expansions in order. Use this to count items, collect metadata, or coordinate between rules:

```clausal
# skip
# Count clauses as they are expanded
TermExpansion(ITEM, ITEM, COUNT, NEXT) <- (
    NEXT == COUNT + 1
)
```

Start the count at 0 — the expansion engine initializes MODULE_STATE to `None` if no initial value is set.

---

## Importing Expansion Rules

Expansion rules can be imported from other modules. The imported rules apply to items in the **importing** module:

```clausal
# skip
# expansion_provider.clausal
TermExpansion(TERM, [TERM, TERM], STATE, STATE) <- True
```

```clausal
# skip
# my_module.clausal — imports TE rules from provider
-import_from(expansion_provider, [TermExpansion])

color("red"),
color("green"),
# Each color fact is duplicated by the imported expansion rule
```

This lets you build reusable expansion libraries.

---

## Init/Final Injection

Term expansion can inject initialization and finalization clauses:

- `_init` predicates are added at the start of the module
- `_final` predicates are added at the end

This is useful for setup/teardown patterns in modules.

---

## Goal Expansion

Goal expansion rewrites individual goals within clause bodies at compile time. Unlike term expansion (which transforms whole clauses), goal expansion transforms the goals inside clause bodies.

### Built-in Goal Expansions

The goal expansion pass (`clausal/logic/goal_expansion.py`) applies these transformations automatically:

**Regex auto-binding**: Named capture groups with ALLCAPS or trailing-underscore names are automatically bound to clause variables:

```clausal
# skip
# What you write:
Match(r"(?P<YEAR>\d{4})-(?P<MONTH>\d{2})", S)

# What the compiler sees (after expansion):
Match(r"(?P<YEAR>\d{4})-(?P<MONTH>\d{2})", S, _G),
YEAR is _G["YEAR"], MONTH is _G["MONTH"]
```

**Pattern precompilation**: String-literal regex patterns are compiled to `re.Pattern` objects at load time, avoiding runtime recompilation.

**Dotted-name support**: Qualified calls like `module.Pred(X)` are resolved during goal expansion.

### How Goal Expansion Works

Goal expansion runs after term expansion and before compilation:

1. Walk each goal in a clause body
2. For each goal, check if any expansion rule applies
3. Replace the goal with its expansion
4. Continue until no more expansions apply (fixpoint)

---

## Pipeline

The compiler pipeline orchestrates both expansions in sequence:

```
.clausal source
    → parse (TermTransformer)
    → term expansion (run_term_expansion)
    → goal expansion (run_goal_expansion)
    → compilation (compile_module)
```

`compiler_v2.compile_module()` coordinates the full pipeline. Term expansion runs first (rewriting whole clauses), then goal expansion (rewriting goals within clause bodies).

---

## Integration Example

The goal expansion for regex auto-binding shows both systems working together. When you write:

```clausal
-import_from(regex, [Match])

Test("auto-bind year") <- (
    Match(r"(?P<YEAR>\d{4})-\d{2}", "2026-03"),
    YEAR == "2026"
)
```

The goal expansion pass detects the `(?P<YEAR>...)` group, rewrites `Match/2` to `Match/3` with group extraction, and binds `YEAR` automatically. The regex pattern is also precompiled at load time.

---

## Gotchas

- **TermExpansion clauses are NOT themselves expanded** — they pass through unchanged to prevent infinite loops.
- **Always use `q()`** to quote terms in expansion rules. Without it, the term is evaluated instead of treated as data.
- **Module state starts as `None`** unless you initialize it. Guard arithmetic operations accordingly.
- **One-to-many expansion returns a list** — make sure OUTPUT is `[item1, item2, ...]`, not a bare term, when you want multiple outputs.

---

??? info "Test coverage"

    - `tests/test_term_expansion.py` (25 tests): pass-through, detection, identity, suppression, one-to-many, module state, init/final injection, imported TE rules, new functors, q() quasi-quotation, full pipeline integration
    - `tests/test_regex.py` (93 tests): goal expansion for regex auto-binding and precompilation

---

*See also: [Regex](regex.md) — auto-binding and precompilation are implemented as goal expansions.*
*See also: [Module System](import.md) — importing expansion rules from other modules.*
*See also: [Predicates](predicates.md) — how clauses and facts work before expansion.*
