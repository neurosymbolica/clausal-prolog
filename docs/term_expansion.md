# Term & Goal Expansion

Term expansion and goal expansion are compile-time transformation passes that rewrite [clauses](predicates.md) and goals before [compilation](compiler.md). They enable metaprogramming, syntactic sugar, and optimization — transforming what you write into what the compiler sees.

---

## Quick Example

```seam
--8<-- "tests/fixtures/docs/term_expansion_sigs.txt:quick_example"
```

---

## Term Expansion

Term expansion rewrites module items (clauses, facts, directives) at load time, before compilation. Define `term_expansion/4` clauses to transform your source.

### Writing Expansion Rules

```seam
--8<-- "tests/fixtures/docs/term_expansion_sigs.txt:writing_expansion_rules"
```

Arguments:

- **INPUT** — the original module item (a quoted term)
- **OUTPUT** — the transformed item (or list of items for one-to-many expansion)
- **MODULE_STATE** — current state threaded through all expansions
- **NEW_STATE** — updated state after this expansion

### Identity Expansion

If no rule matches an item, it passes through unchanged. You can also write an explicit identity rule:

```seam
--8<-- "tests/fixtures/docs/term_expansion_sigs.txt:identity_expansion"
```

### Suppressing Items

Return an empty list to remove an item from the module:

```seam
--8<-- "tests/fixtures/docs/term_expansion_sigs.txt:suppressing_items"
```

### One-to-Many Expansion

Return a list to expand one item into multiple items. This is the most powerful pattern — it lets a single declaration generate multiple clauses:

```seam
--8<-- "tests/fixtures/docs/term_expansion_sigs.txt:one_to_many_expansion"
```

**Walkthrough**: when this rule is active and the module contains `color('red'),`:

1. The expansion engine matches `color('red')` against `TERM`
2. OUTPUT becomes `[color('red'), color('red')]`
3. The module now has two copies of `color('red')`

### Patterns Are Plain Terms

A pattern is written as a plain term, as in ISO `term_expansion/2`: in argument position a term is data, never a goal, so nothing needs quoting:

```seam
--8<-- "tests/fixtures/docs/term_expansion_sigs.txt:plain_term_patterns"
```

Variables are shared between the pattern and the replacement. In the example above, `X` in the input pattern is the same `X` in both output terms.

`q()` quasi-quotation was retired on 2026-09-25: `q` is an ordinary name now, and `q(fact(X))` is the term `q(fact(X))`. A `q(...)` left in a `term_expansion/4` clause (or in a clause of a helper its body calls) would match nothing, so loading one emits a `ClausalRetiredQuasiQuoteWarning` naming the line. Drop the wrapper.

### Module State Threading

The STATE arguments thread a value through all expansions in order. Use this to count items, collect metadata, or coordinate between rules:

```seam
--8<-- "tests/fixtures/docs/term_expansion_sigs.txt:module_state_threading"
```

Start the count at 0 — the expansion engine initializes MODULE_STATE to `None` if no initial value is set.

---

## Importing Expansion Rules

Expansion rules can be [imported](import.md) from other modules. The imported rules apply to items in the **importing** module:

```seam
--8<-- "tests/fixtures/docs/term_expansion_sigs.txt:importing_expansion_rules"
```

```seam
--8<-- "tests/fixtures/docs/term_expansion_sigs.txt:importing_expansion_rules_ex2"
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

**[Regex](regex.md) auto-binding**: Named capture groups with ALLCAPS or leading-underscore names are automatically bound to clause variables:

```seam
--8<-- "tests/fixtures/docs/term_expansion_sigs.txt:regex_auto_binding"
```

**Pattern precompilation**: String-literal regex patterns are compiled to `re.Pattern` objects at load time, avoiding runtime recompilation.

**Dotted-name support**: Qualified calls like `module.pred(X)` are resolved during goal expansion (see [Import](import.md)).

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
.seam source
    → parse (TermTransformer)
    → term expansion (run_term_expansion)
    → goal expansion (run_goal_expansion)
    → compilation (compile_module)
```

`compiler_v2.compile_module()` coordinates the full pipeline. Term expansion runs first (rewriting whole clauses), then goal expansion (rewriting goals within clause bodies).

---

## Integration Example

The goal expansion for regex auto-binding shows both systems working together. when you write:

```seam
-allow_singletons
# Named-group auto-bind: YEAR's binding occurrence lives inside the
# pattern STRING, invisible to the singleton counter's AST-Name check.
-import_from(regex, [match])

test("auto-bind year") <- (
    match(r"(?P<YEAR>\d{4})-\d{2}", '2026-03'),
    YEAR is "2026"
)
```

The goal expansion pass detects the `(?P<YEAR>...)` group, rewrites `match/2` to `match/3` with group extraction, and binds `YEAR` automatically — to a **string** (`"2026"`, the `('$chars', '2026')` term), so compare it with unification (`is`), not with the CLP(ℤ) `==`, which raises `domain_error(clpz_expression, ...)` on text. The regex pattern is also precompiled at load time.

---

## Gotchas

- **term_expansion clauses are NOT themselves expanded** — they pass through unchanged to prevent infinite loops.
- **Write patterns as plain terms** — `term_expansion(fact(X), ...)`, not `term_expansion(q(fact(X)), ...)`. `q()` was retired 2026-09-25; an old `q(...)` pattern matches nothing and warns at load.
- **Module state starts as `None`** unless you initialize it. Guard arithmetic operations accordingly.
- **One-to-many expansion returns a list** — make sure OUTPUT is `[item1, item2, ...]`, not a bare term, when you want multiple outputs.

---

??? info "Test coverage"

    - `tests/test_term_expansion.py` (25 tests): pass-through, detection, identity, suppression, one-to-many, module state, init/final injection, imported TE rules, new functors, plain-term patterns (and the retired-q() warning), full pipeline integration
    - `tests/test_regex.py` (93 tests): goal expansion for regex auto-binding and precompilation

---

*See also: [Regex](regex.md) — auto-binding and precompilation are implemented as goal expansions,
[Module System](import.md) — importing expansion rules from other modules,
[Predicates](predicates.md) — how clauses and facts work before expansion,
[Directives](directives.md) — module-level declarations processed alongside expansion.*
