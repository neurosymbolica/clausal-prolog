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

Return an empty list to remove an item from the module. A head pattern
matches facts, so removing a predicate's rules takes the clause pattern
too (see [Matching Rules](#matching-rules)):

```clausal
% Remove every debug/1 clause: the facts, and the rules
term_expansion(debug(_), [], STATE, STATE).
term_expansion((debug(_) :- _), [], STATE, STATE).

debug(trace_on).
debug(X) :- X = verbose.
keep(a).

% No debug/1 clause is left, so calling it is an existence error
test("debug clauses are gone") :-
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

### Handing Back Rules

An expansion may be a rule as well as a fact: write it `(H :- B)`, alone or
in a list with facts. It is compiled as the same clause written in the
file would be, body and all, and a variable shared between `H` and `B` is
one variable of the clause:

```clausal
% Every alias(New, Old) fact makes New answer as Old does
term_expansion(alias(New, Old), (H :- B), S, S) :-
    H =.. [New, X],
    B =.. [Old, X].

% One declaration, a fact and a rule
term_expansion(unit(Name, Factor),
               [unit_name(Name), (to_base(Name, V, Base) :- Base is V * Factor)],
               S, S).

color(red).
color(green).
alias(colour, color).
unit(km, 1000).

test("the alias is a rule") :-
    findall(C, colour(C), CS),
    CS == [red, green].

test("the unit's rule") :-
    unit_name(km),
    to_base(km, 2, B),
    B =:= 2000.
```

The clause is lowered by the same front end, under the same directives, as
a clause written at the end of the file: `,`, `;` and `\+` are control
constructs, a variable goal is `call(G)`, `true` alone makes the clause a
fact, a goal imported with `use_module/2` calls the import, and
`library(reif)`'s `if_/3` and `library(clpq)`'s `{}/1` work as they do
written. What the front end refuses in a written clause -- `!`, `->`,
`*->`, a number, string or list as a goal, a `$`-prefixed name -- it
refuses at load here too, with the same message.

In the seam the rule is `(H <- B)`, and its body follows the seam's body
rules the same way: a bare variable goal (`(b(G) <- G)`) is refused at
load, as `b(G) <- G` written is; write `call(G)`.

A grammar rule `(H --> B)` handed back is refused: term expansion runs after
grammar rules are translated, so hand back the clauses it stands for.

### Matching Rules

A bare head pattern such as `p(X)` matches a FACT only. A rule reads as the
term `(p(X) :- Body)`, which does not unify with `p(X)`, so it passes
through, body intact, as in ISO. To match a rule, write the whole clause:

```clausal
% Give every rule of p/1 a twin of q/1 with the same body
term_expansion((p(X) :- B), [(p(X) :- B), (q(X) :- B)], S, S).

p(X) :- X = 1.
p(2).

test("only the rule is twinned") :-
    findall(X, q(X), XS),
    XS == [1].

test("both p clauses stay") :-
    findall(X, p(X), XS),
    XS == [1, 2].
```

The body `B` is the clause's body as written, so `(p(X) :- B)` handed back
is the very clause matched. In the seam the pattern is `(p(X) <- B)`, and a
seam fact is the clause `p(2) <- True`, so it matches facts too, with
`B = True`.

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
- **A head pattern matches facts, not rules** — `term_expansion(p(X), ...)` leaves a rule `p(X) :- ...` alone; match a rule with `(p(X) :- B)` (see [Matching Rules](#matching-rules)).
- **A clause a rule builds has no variable names** — goal expansion runs after term expansion, and [regex auto-binding](regex.md#term-expansion) binds a group to the variable it names. A clause handed back unchanged (`term_expansion(T, T, S, S)`, or `T` inside `[T, T]`) is the clause as written and keeps its names, so its groups bind. A clause the rule *builds* has only the rule's variables, renamed for each expansion, so no name reaches it: in `.clausal` its groups bind nothing.

---

??? info "Test coverage"

    - `tests/test_term_expansion.py`: pass-through, detection, identity, suppression, one-to-many, module state, init/final injection, imported TE rules, new functors, plain-term patterns (and the retired-q() warning), rules handed back and whole-clause patterns on both surfaces (`TestRuleClausesHandedBack`), full pipeline integration
    - `tests/test_regex.py` (93 tests): goal expansion for regex auto-binding and precompilation

---

*See also: [Regex](regex.md) — auto-binding and precompilation are implemented as goal expansions,
[Module System](import.md) — importing expansion rules from other modules,
[Predicates](predicates.md) — how clauses and facts work before expansion,
[Directives](directives.md) — module-level declarations processed alongside expansion.*
