# Definite Clause Grammars (DCGs)

DCGs are a notation for defining grammars and other [list](lists.md)-processing tasks. Examples on this page are [Clausal Prolog](clausal_prolog.md) (`.clausal`), which writes grammar rules with ISO `-->`. A grammar rule is rewritten at compile time to an ordinary clause with two hidden difference-list arguments. (The [seam](syntax.md), Clausal's Python-syntax surface, spells the same rule `head >> (body)`.)

The implementation lives in `clausal/templating/term_rewriting.py` (source-level rewriting) and `clausal/logic/builtins/dcg.py` (`phrase/2,3`).

*The `table` directive is often used with DCGs to memoize recursive grammar rules. See [Directives](directives.md).*

!!! note "Clausal Prolog is cut-free"

    Grammar rules here are standard ISO `-->` rules, so most Prolog DCG
    resources apply directly. The one difference is that Clausal Prolog is
    cut-free: `!` (and `{!}` in a grammar body) is refused at load time.
    Grammars in `.pl` files can be [imported directly](importing_prolog.md).

---

## Syntax

Grammar rules use `-->` instead of `:-`:

```clausal
greeting -->
    [hello, world].
```

This rewrites to a clause with two hidden arguments (the input list and the remainder list), equivalent to:

```clausal
greeting(S0, S) :-
    append([hello, world], S, S0).
```

### Terminals

Terminals are list literals — they consume tokens from the input:

```clausal
greeting -->
    [hello, world].
```

The empty list `[]` matches without consuming any input:

```clausal
epsilon -->
    [].
```

### Non-terminals

Non-terminals are predicate references — they delegate to other grammar rules:

```clausal
sentence -->
    noun_phrase, verb_phrase, noun_phrase.
```

This chains three grammar rules: `noun_phrase` consumes some tokens, then `verb_phrase`, then `noun_phrase` again.

### Extra Arguments

DCG rules can have extra arguments beyond the hidden state pair:

```clausal
digit(D) -->
    [D], {D >= 0}, {D =< 9}.

test("digit 5") :-
    phrase(digit(D), [5]),
    D == 5.
```

### Inline Goals

Curly braces `{...}` embed arbitrary [goals](syntax.md) inside a grammar rule. They do not consume input:

```clausal
digit(D) -->
    [D], {D >= 0}, {D =< 9}.
```

The goals `D >= 0` and `D =< 9` are ISO arithmetic comparisons, run without consuming tokens; the terminal `[D]` has bound `D` by the time they run. To post a [CLP(ℤ)](constraints.md) constraint instead, write `{D #>= 0}` with `library(clpz)` loaded.

A single brace pair may hold **several goals**, separated by commas — this is a conjunction of embedded goals, exactly like Prolog's `{A, B}`. All goals must succeed; the source order is preserved:

```clausal
digit(D) -->
    [D], {D >= 0, D =< 9}.

in_range(D) -->
    {D >= 0, D =< 9}.

test("one block, two goals") :-
    phrase(digit(D), [7]),
    D == 7,
    \+ phrase(digit(_), [12]).

test("a goal-only body consumes nothing") :-
    phrase(in_range(3), [], []).
```

This is equivalent to the two-block form `[D], {D >= 0}, {D =< 9}` above. A multi-goal block may also stand alone as a whole body (`in_range//1` above), consuming no input.

> **Braces claim DCG *body* position only.** In a rule body, `{...}` always means "embedded goal(s)". Inside a terminal list or a non-terminal argument a curly term is ordinary data: `tok --> [{a}].` consumes the token `{a}`. (In the seam, where `{1, 2}` is a set literal, the same rule applies: set literals are data everywhere except body position.)

### Conjunction and Disjunction

Multiple items in a rule are joined with `,` (conjunction):

```clausal
sentence -->
    noun_phrase, verb_phrase, noun_phrase.
```

Alternatives use `;`:

```clausal
noun_phrase -->
    [the, dog] ; [the, cat] ; [a, bird].

verb_phrase -->
    [chases] ; [sees] ; [likes].
```

### Negation

A grammar body cannot negate a terminal directly: `\+` in a grammar body is
refused at load time, as Scryer refuses it (ISO leaves it implementation
defined). Consume the token and constrain it instead, here with
[`dif/2`](constraints.md):

```clausal
not_a -->
    [X], {dif(X, a)}.

test("not a") :-
    phrase(not_a, [b]),
    \+ phrase(not_a, [a]).
```

This matches any single token that is not `a`. (The seam can also write it with a negated
terminal, `not ['a'], [X]`.)

### Pushback (Semicontext)

A rule can peek at the next token without consuming it using pushback notation:

```clausal
look_ahead(T), [T] -->
    [T].

test("peek") :-
    phrase(look_ahead(T), [x, y], REST),
    T == x,
    REST == [x, y].
```

The head `look_ahead(T), [T]` means: match `look_ahead(T)` and push back `[T]`. The body `[T]` consumes `T`. Net effect: `T` is unified with the next token but remains in the input.

### Recursive Rules

DCG rules can be recursive:

```clausal
ab -->
    [a], ab.

ab -->
    [b], ab.

ab -->
    [].

test("ab") :-
    phrase(ab, [a, b, b, a]).
```

This matches strings of `a`s and `b`s in any order.

---

## phrase/2 and phrase/3

The `phrase` builtin invokes a grammar rule on an input list.

### phrase/2

`phrase(RuleName, InputList)` — parse InputList with the named rule, succeeding if the entire list is consumed:

```clausal
sentence -->
    noun_phrase, verb_phrase, noun_phrase.

noun_phrase -->
    [the, dog] ; [the, cat] ; [a, bird].

verb_phrase -->
    [chases] ; [sees] ; [likes].

valid_sentence(S) :-
    phrase(sentence, S).

test("a sentence") :-
    valid_sentence([the, dog, chases, the, cat]).
```

From Python, in a `.seam` file, the goal-position seam runs the same query
(the lower-level `solve(...)` API is in [Python integration](python_integration.md)):

```python
if --valid_sentence(['the', 'dog', 'chases', 'the', 'cat']):
    print("parsed")
```

### Strings as input

A double-quoted literal is a **string** (the default since 2026-09-26, as in
Scryer), and a string *is* the list of its one-character **atoms**, so it can
be passed directly to `phrase`. This makes character-level DCGs natural:

```clausal
digit -->
    [D], {char_type(D, digit)}.

digits -->
    digit.

digits -->
    digit, digits.

test("parse string") :-
    phrase(digits, "123").

test("partial") :-
    phrase(digits, "12ab", REST),
    REST = [a, b].
```

The remainder comes back as a string: a goal-position seam hands Python the
engine's term, the carrier `('$chars', 'ab')`, and `clausal.to_python` turns
it into `'ab'`.

No `atom_chars` conversion is needed. See [Strings as Lists](strings_as_lists.md)
for more details.

### phrase/3

`phrase(RuleName, S0, S)` — parse with explicit remainder. S is the unconsumed suffix:

```clausal
noun_phrase -->
    [the, dog] ; [the, cat] ; [a, bird].

% Parse and get remainder
partial_parse(INPUT, REST) :-
    phrase(noun_phrase, INPUT, REST).

test("remainder") :-
    partial_parse([the, cat, sees], [sees]).
```

`phrase/3` is also used for state threading (see below).

### phrase with extra arguments

For rules with extra arguments, pass them as part of the rule: with `digit//1` from [Extra Arguments](#extra-arguments), `phrase(digit(D), [5])` answers `D = 5`.

```clausal
digit(D) -->
    [D], {D >= 0, D =< 9}.

test("phrase(digit(D), [5])") :-
    phrase(digit(D), [5]),
    D == 5.
```

---

## State Threading

DCGs are a general state-passing mechanism — not just for parsing lists of tokens. The hidden difference-list pair can thread any state through `phrase/3`.

A complete working example of all patterns below, in seam syntax, is in `clausal/examples/dcg_state.seam`.

### Core Pattern

Two helper non-terminals provide state access:

```clausal
% state//1: read the current state (passthrough)
state(S), [S] -->
    [S].

% state2//2: read the old state, replace it with a new one
state2(S0, S), [S] -->
    [S0].

test("state reads without consuming") :-
    phrase(state(S), [7], REST),
    S == 7,
    REST == [7].

test("state2 replaces the state") :-
    phrase(state2(OLD, 8), [7], REST),
    OLD == 7,
    REST == [8].
```

The examples below repeat these two helpers so that each block is a whole program.

### Counter Example

Thread an integer counter through `phrase/3`:

```clausal
:- use_module(library(clpz)).

state(S), [S] --> [S].
state2(S0, S), [S] --> [S0].

inc -->
    state(N0), {N #= N0 + 1}, state2(_, N).

count3 -->
    inc, inc, inc.

test("count3") :-
    phrase(count3, [0], [N]),
    N == 3.
```

`phrase(count3, [0], [N])` answers `N = 3`. The initial state `[0]` is passed as the input list; the final state `[N]` is the remainder.

### Tree Leaf Counting

Thread a counter to count leaves in a binary tree:

```clausal
:- use_module(library(clpz)).

state(S), [S] --> [S].
state2(S0, S), [S] --> [S0].

count_leaves(leaf) -->
    state(N0), {N #= N0 + 1}, state2(_, N).

count_leaves([L, R]) -->
    count_leaves(L), count_leaves(R).

num_leaves(T, N) :-
    phrase(count_leaves(T), [0], [N]).

test("three leaves") :-
    num_leaves([leaf, [leaf, leaf]], N),
    N == 3.
```

### Accumulator

Thread a list accumulator to collect items:

```clausal
state(S), [S] --> [S].
state2(S0, S), [S] --> [S0].

push(X) -->
    state(ACC0), {ACC = [X|ACC0]}, state2(_, ACC).

push_all([]) -->
    [].

push_all([X|XS]) -->
    push(X), push_all(XS).

collect_items(XS, R) :-
    phrase(push_all(XS), [[]], [R]).

test("collect, most recent first") :-
    collect_items([a, b, c], R),
    R == [c, b, a].
```

---

## Coexisting with Regular Predicates

DCG rules and regular `:-` clauses can coexist in the same module:

```clausal
sentence -->
    noun_phrase, verb_phrase, noun_phrase.

noun_phrase --> [the, dog] ; [the, cat].
verb_phrase --> [sees].

% Regular predicate that uses the DCG rule
valid_sentence(S) :-
    phrase(sentence, S).

test("valid") :-
    valid_sentence([the, cat, sees, the, dog]).
```

---

??? info "Test coverage"

    Tests are in `tests/test_dcg.py`.

    - **Terminals**: single, multiple, empty
    - **Non-terminals**: chaining, extra args
    - **Inline goals**: CLP(ℤ) constraints, arithmetic
    - **Conjunction/disjunction**: multiple alternatives
    - **Negation**: the seam's `not [terminal]`
    - **Pushback**: peek without consuming
    - **Recursive rules**: `ab` grammar
    - **phrase/2,3**: full parse, partial parse, remainder
    - **State threading**: counter, tree counting, accumulator
    - **Fixture integration**: `dcg_grammar.seam` with mixed rules and regular predicates

---

*See also: [Lambdas](lambdas.md) — goal closures, an alternative to DCGs for some patterns.*
*See also: [Directives](directives.md) — the `table` directive for memoizing recursive DCG rules.*
*See also: [Tabling](tabling.md) — SLG tabling, useful for left-recursive grammars.*
