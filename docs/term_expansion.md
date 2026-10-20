# Term & Goal Expansion

Term expansion and goal expansion are compile-time transformation passes that rewrite [clauses](predicates.md) and goals before [compilation](compiler.md). They enable metaprogramming, syntactic sugar, and optimization — transforming what you write into what the compiler sees.

Examples on this page are [Clausal Prolog](clausal_prolog.md) (`.clausal`),
which uses ISO Prolog syntax.

---

## Quick Example

```clausal
% Every fact automatically gets a "logged" wrapper
term_expansion(fact(X), [fact(X), logged_fact(X)], STATE, STATE).

fact(a).
fact(b).
% After expansion, the module also contains:
% logged_fact(a), logged_fact(b)

test("logged facts") :-
    findall(X, logged_fact(X), XS),
    XS == [a, b].
```

---

## Term Expansion

Term expansion rewrites module items (clauses, facts, directives) at load time, before compilation. Define `term_expansion/4` clauses to transform your source.

### Writing Expansion Rules

```text
--8<-- "tests/fixtures/docs/term_expansion_sigs.txt:writing_expansion_rules"
```

Arguments:

- **INPUT** — the original module item (a quoted term)
- **OUTPUT** — the transformed item (or list of items for one-to-many expansion)
- **MODULE_STATE** — current state threaded through all expansions (see
  [Module State Threading](#module-state-threading))
- **NEW_STATE** — updated state after this expansion

### Identity Expansion

If no rule matches an item, it passes through unchanged. You can also write an explicit identity rule:

```clausal
term_expansion(ITEM, ITEM, STATE, STATE).

color(red).

test("passes through") :-
    color(red).
```

### Suppressing Items

Return an empty list to remove an item from the module:

```clausal
% Remove all facts for the "debug" predicate
term_expansion(debug(_), [], STATE, STATE).

debug(trace_on).
keep(a).

% No debug/1 clause is left, so calling it is an existence error
test("debug facts are gone") :-
    catch((debug(_), fail),
          error(existence_error(procedure, debug/1), _),
          true),
    keep(a).
```

### One-to-Many Expansion

Return a list to expand one item into multiple items. This is the most powerful pattern — it lets a single declaration generate multiple clauses:

```clausal
% Duplicate every item
term_expansion(TERM, [TERM, TERM], STATE, STATE).

color(red).

test("two copies") :-
    findall(C, color(C), CS),
    CS == [red, red].
```

**Walkthrough**: when this rule is active and the module contains `color(red).`:

1. The expansion engine matches `color(red)` against `TERM`
2. OUTPUT becomes `[color(red), color(red)]`
3. The module now has two copies of `color(red)` (the `test/1` clause is
   duplicated too, so it runs twice)

### Patterns Are Plain Terms

A pattern is written as a plain term, as in ISO `term_expansion/2`: in argument position a term is data, never a goal, so nothing needs quoting:

```clausal
% A pattern is a plain term: in argument position it is DATA, never a goal
term_expansion(double_fact(X), [fact(X), fact(X)], S, S).

double_fact(a).

test("double fact") :-
    findall(X, fact(X), XS),
    XS == [a, a].
```

Variables are shared between the pattern and the replacement. In the example above, `X` in the input pattern is the same `X` in both output terms.

`q()` quasi-quotation was retired on 2026-09-25: `q` is an ordinary name now, and `q(fact(X))` is the term `q(fact(X))`. A `q(...)` left in a `term_expansion/4` clause (or in a clause of a helper its body calls) would match nothing, so loading one emits a `ClausalRetiredQuasiQuoteWarning` naming the line. Drop the wrapper.

### Module State Threading

The STATE arguments thread a value through all expansions in order. Use this to count items, collect metadata, or coordinate between rules.

The state is the term `module_expansion_state(Init, Final, User)`. `Init`
and `Final` are the injection lists (see
[Init/Final Injection](#initfinal-injection)), and `User` is yours. The
expansion engine starts it as `module_expansion_state([], [], nil)`, so a
counter starts from the atom `nil`, not from a number:

```clausal
% Number the color facts as they are expanded
term_expansion(color(C), [color(C), color_index(C, N)],
               module_expansion_state(I, F, N0),
               module_expansion_state(I, F, N)) :-
    next_index(N0, N).

next_index(nil, 1).
next_index(N0, N) :-
    integer(N0),
    N is N0 + 1.

color(red).
color(green).
color(blue).

test("numbered") :-
    findall(C-N, color_index(C, N), PAIRS),
    PAIRS == [red-1, green-2, blue-3].
```

A rule body may call helper predicates of the same module, as
`next_index/2` here.

---

## Importing Expansion Rules

Expansion rules can be [imported](import.md) from other modules. The imported rules apply to items in the **importing** module:

```clausal
--8<-- "tests/fixtures/docs/term_expansion_provider.clausal:importing_expansion_rules"
```

```clausal
--8<-- "tests/fixtures/docs/term_expansion_importer.clausal:importing_expansion_rules_ex2"
```

The importing module names `term_expansion/4` in its `use_module/2` import
list. The provider's rules also apply to the provider's own items.

This lets you build reusable expansion libraries.

---

## Init/Final Injection

Term expansion can inject initialization and finalization clauses through
the module state, `module_expansion_state(Init, Final, User)`:

- the items in the `Init` list are added at the start of the module
- the items in the `Final` list are added at the end

This is useful for setup/teardown patterns in modules.

```clausal
% Record each color in an item at the start and one at the end
term_expansion(color(C), color(C),
               module_expansion_state(I, F, S),
               module_expansion_state([first_seen(C)|I], [last_seen(C)|F], S)).

color(red).
color(green).

test("injected") :-
    findall(C, first_seen(C), FIRST),
    FIRST == [green, red],
    findall(C, last_seen(C), LAST),
    LAST == [green, red].
```

Each list is added in its own order, so consing onto it, as here, adds the
items in reverse.

---

## Goal Expansion

Goal expansion rewrites individual goals within clause bodies at compile time. Unlike term expansion (which transforms whole clauses), goal expansion transforms the goals inside clause bodies.

### Built-in Goal Expansions

The goal expansion pass (`clausal/logic/goal_expansion.py`) applies these transformations automatically:

**[Regex](regex.md) auto-binding**: Named capture groups with ALLCAPS or leading-underscore names are automatically bound to the clause variable of the same name. What you write, and what the compiler sees after expansion, in effect:

```clausal
:- set_prolog_flag(double_quotes, chars).
:- use_module(library(re), [match/2, match/3]).

% What you write:
parse(S, YEAR, MONTH) :-
    match("(?P<YEAR>\\d{4})-(?P<MONTH>\\d{2})", S).

% What the compiler sees (after expansion):
parse_expanded(S, YEAR, MONTH) :-
    match("(?P<YEAR>\\d{4})-(?P<MONTH>\\d{2})", S, G),
    get(G, 'YEAR', YEAR),
    get(G, 'MONTH', MONTH).

test("auto-binding reads the groups") :-
    parse("2026-03", Y, M),
    parse_expanded("2026-03", Y, M),
    Y == "2026",
    M == "03".
```

**Pattern precompilation**: String-literal regex patterns are compiled to `re.Pattern` objects at load time, avoiding runtime recompilation.

**Dotted-name support** (seam): Qualified calls like `module.pred(X)` are resolved during goal expansion (see [Import](import.md)). `.clausal` writes a qualified call `module:pred(X)`.

### How Goal Expansion Works

Goal expansion runs after term expansion and before compilation:

1. Walk each goal in a clause body
2. For each goal, check if any expansion rule applies
3. Replace the goal with its expansion
4. Continue until no more expansions apply (fixpoint)

---

## Pipeline

The compiler pipeline orchestrates both expansions in sequence:

For a `.seam` file:

```
.seam source
    → parse (TermTransformer)
    → term expansion (run_term_expansion)
    → goal expansion (run_goal_expansion)
    → compilation (compile_module)
```

`compiler_v2.compile_module()` coordinates the full pipeline. Term expansion runs first (rewriting whole clauses), then goal expansion (rewriting goals within clause bodies). Term expansion runs on `.clausal` files as well: every term expansion example on this page is `.clausal`.

---

## Integration Example

The goal expansion for regex auto-binding shows both systems working together. When you write:

```clausal
:- set_prolog_flag(double_quotes, chars).
:- use_module(library(re), [match/2]).

test("auto-bind year") :-
    match("(?P<YEAR>\\d{4})-\\d{2}", "2026-03"),
    YEAR == "2026".
```

The goal expansion pass detects the `(?P<YEAR>...)` group, rewrites `match/2` to `match/3` with group extraction, and binds `YEAR` automatically — to a **string** (`"2026"`, the `('$chars', '2026')` term), which ISO `==` compares structurally. (In the seam, `==` is CLP(ℤ) equality and raises `domain_error(clpz_expression, ...)` on text, so compare with `is` there.) The regex pattern is also precompiled at load time.

---

## Gotchas

- **The rule is `term_expansion/4`**: a two-argument ISO-style `term_expansion/2` clause is an ordinary predicate and expands nothing.
- **term_expansion clauses are NOT themselves expanded** — they pass through unchanged to prevent infinite loops.
- **Write patterns as plain terms** — `term_expansion(fact(X), ...)`, not `term_expansion(q(fact(X)), ...)`. `q()` was retired 2026-09-25; an old `q(...)` pattern matches nothing and warns at load.
- **Module state starts as `module_expansion_state([], [], nil)`**: the user slot is the atom `nil`, not a number. Handle `nil` before doing arithmetic on it.
- **One-to-many expansion returns a list** — make sure OUTPUT is `[item1, item2, ...]`, not a bare term, when you want multiple outputs.
- **A clause a rule builds has no variable names** — goal expansion runs after term expansion, and [regex auto-binding](regex.md#term-expansion) binds a group to the variable it names. A clause handed back unchanged (`term_expansion(T, T, S, S)`, or `T` inside `[T, T]`) is the clause as written and keeps its names, so its groups bind. A clause the rule *builds* has only the rule's variables, renamed for each expansion, so no name reaches it: in `.clausal` its groups bind nothing.

---

??? info "Test coverage"

    - `tests/test_term_expansion.py` (25 tests): pass-through, detection, identity, suppression, one-to-many, module state, init/final injection, imported TE rules, new functors, plain-term patterns (and the retired-q() warning), full pipeline integration
    - `tests/test_regex.py` (93 tests): goal expansion for regex auto-binding and precompilation

---

*See also: [Regex](regex.md) — auto-binding and precompilation are implemented as goal expansions,
[Module System](import.md) — importing expansion rules from other modules,
[Predicates](predicates.md) — how clauses and facts work before expansion,
[Directives](directives.md) — module-level declarations processed alongside expansion.*
