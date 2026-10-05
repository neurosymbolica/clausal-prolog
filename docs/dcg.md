# Definite Clause Grammars (DCGs)

DCGs are a notation for defining grammars and other [list](lists.md)-processing tasks. The seam uses `>>` syntax for grammar rules, which are rewritten to ordinary `<-` clauses with two hidden difference-list arguments at compile time.

The implementation lives in `clausal/templating/term_rewriting.py` (source-level rewriting) and `clausal/logic/builtins/dcg.py` (`phrase/2,3`).

*The `-table` directive is often used with DCGs to memoize recursive grammar rules. See [Directives](directives.md).*

!!! note "Seam vs Prolog syntax"

    Seam and Prolog syntax may slightly differ — for example, variables are
    `ALLCAPS`, rules use `<-` instead of `:-`, and lists are Python-style. Keep
    this in mind when comparing with Prolog resources.
    Prolog DCGs (`-->`) can be [imported directly](importing_prolog.md) — they translate to the seam's `>>` syntax automatically. [Clausal Prolog](clausal_prolog.md) (`.clausal`) files write grammar rules with ISO `-->` directly.

---

## Syntax

Grammar rules use `>>` instead of `<-`:

```seam
greeting >> (['hello', 'world'])
```

This rewrites to a clause with two hidden arguments (the input list and the remainder list):

```seam
greeting(S0, S) <- append(['hello', 'world'], S, S0)
```

### Terminals

Terminals are list literals — they consume tokens from the input:

```seam
greeting >> (['hello', 'world'])
```

The empty list `[]` matches without consuming any input:

```seam
epsilon >> ([])
```

### Non-terminals

Non-terminals are predicate references — they delegate to other grammar rules:

```seam
sentence >> (noun_phrase, verb_phrase, noun_phrase)
```

This chains three grammar rules: `noun_phrase` consumes some tokens, then `verb_phrase`, then `noun_phrase` again.

### Extra Arguments

DCG rules can have extra arguments beyond the hidden state pair:

```seam
digit(D) >> ([D], {D >= 0}, {D <= 9})
```

### Inline Goals

Curly braces `{...}` embed arbitrary [goals](syntax.md) inside a grammar rule. They do not consume input:

```seam
digit(D) >> ([D], {D >= 0}, {D <= 9})
```

The goals `D >= 0` and `D <= 9` are [CLP(ℤ)](constraints.md) constraints checked without consuming tokens.

A single brace pair may hold **several goals**, separated by commas — this is a conjunction of embedded goals, exactly like Prolog's `{A, B}`. All goals must succeed; the source order is preserved:

```seam
digit(D) >> ([D], {D >= 0, D <= 9})
```

This is equivalent to the two-block form `([D], {D >= 0}, {D <= 9})` above. A multi-goal block may also stand alone as a whole body (`r(D) >> ({D >= 0, D <= 9})`), consuming no input. An empty `{}` block is an error.

> **Braces claim DCG *body* position only.** In a rule body, `{...}` always means "embedded goal(s)", so a bare set literal there has no data meaning. Set literals still work as ordinary data everywhere data belongs — inside terminals (`tok >> ([{1, 2}])` consumes a set token) and in non-terminal arguments — because those positions are not body position.

### Conjunction and Disjunction

Multiple items in a rule are joined with `,` (conjunction):

```seam
sentence >> (noun_phrase, verb_phrase, noun_phrase)
```

Alternatives use `or`:

```seam
noun_phrase >> (['the', 'dog'] or ['the', 'cat'] or ['a', 'bird'])
verb_phrase >> (['chases'] or ['sees'] or ['likes'])
```

### Negation

`not` tests that a terminal does NOT match:

```seam
not_a >> (not ['a'], [X])
```

This matches any single token that is not `'a'`.

### Pushback (Semicontext)

A rule can peek at the next token without consuming it using pushback notation:

```seam
(look_ahead(T), [T]) >> ([T])
```

The left side `(look_ahead(T), [T])` means: match `look_ahead(T)` and push back `[T]`. The right side `([T])` consumes `T`. Net effect: `T` is unified with the next token but remains in the input.

### Recursive Rules

DCG rules can be recursive:

```seam
ab >> (['a'], ab)
ab >> (['b'], ab)
ab >> ([])
```

This matches strings of `a`s and `b`s in any order.

---

## phrase/2 and phrase/3

The `phrase` builtin invokes a grammar rule on an input list.

### phrase/2

`phrase(RuleName, InputList)` — parse InputList with the named rule, succeeding if the entire list is consumed:

```seam
sentence >> (noun_phrase, verb_phrase, noun_phrase)
noun_phrase >> (['the', 'dog'] or ['the', 'cat'] or ['a', 'bird'])
verb_phrase >> (['chases'] or ['sees'] or ['likes'])

valid_sentence(S) <- phrase(sentence, S)

test("a sentence") <- valid_sentence(['the', 'dog', 'chases', 'the', 'cat'])
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

```seam
# `'digit'` is single-quoted: char_type/2's Type argument is an atom, and a
# bare `digit` would name the nonterminal on the next line.
digit >> ([D], {char_type(D, 'digit')})
digits >> (digit)
digits >> (digit, digits)

test("parse string") <- phrase(digits, "123")
test("partial") <- (phrase(digits, "12ab", REST), REST is ['a', 'b'])
```

The remainder comes back as a string: a goal-position seam hands Python the
engine's term, the carrier `('$chars', 'ab')`, and `clausal.to_python` turns
it into `'ab'`.

No `atom_chars` conversion is needed. See [Strings as Lists](strings_as_lists.md)
for more details.

### phrase/3

`phrase(RuleName, S0, S)` — parse with explicit remainder. S is the unconsumed suffix:

```seam
noun_phrase >> (['the', 'dog'] or ['the', 'cat'] or ['a', 'bird'])

# Parse and get remainder
partial_parse(INPUT, REST) <- phrase(noun_phrase, INPUT, REST)

test("remainder") <- partial_parse(['the', 'cat', 'sees'], ['sees'])
```

`phrase/3` is also used for state threading (see below).

### phrase with extra arguments

For rules with extra arguments, pass them as part of the rule:

```seam
--8<-- "tests/fixtures/docs/misc_phase7_sigs.txt:dcg_phrase_example"
```

---

## State Threading

DCGs are a general state-passing mechanism — not just for parsing lists of tokens. The hidden difference-list pair can thread any state through `phrase/3`.

A complete working example of all patterns below is in `clausal/examples/dcg_state.seam`.

### Core Pattern

Two helper non-terminals provide state access:

```seam
# state/1: read current state (passthrough)
(state(S), [S]) >> ([S])

# state/2: read old state, replace with new
(state2(S0, S), [S]) >> ([S0])
```

### Counter Example

Thread an integer counter through `phrase/3`:

```seam
inc >> (state(N0), {N == N0 + 1}, state2(_, N))

count3 >> (inc, inc, inc)
```

Usage:

```seam
# phrase(count3, [0], [N])  →  N = 3
```

The initial state `[0]` is passed as the input list; the final state `[N]` is the remainder.

### Tree Leaf Counting

Thread a counter to count leaves in a binary tree:

```seam
count_leaves('leaf') >> (state(N0), {N == N0 + 1}, state2(_, N))
count_leaves([L, R]) >> (count_leaves(L), count_leaves(R))

num_leaves(T, N) <- phrase(count_leaves(T), [0], [N])
```

### Accumulator

Thread a list accumulator to collect items:

```seam
push(X) >> (state(ACC0), {ACC is [X, *ACC0]}, state2(_, ACC))

push_all([]) >> ([])
push_all([X, *XS]) >> (push(X), push_all(XS))

collect_items(XS, R) <- phrase(push_all(XS), [[]], [R])
```

---

## Coexisting with Regular Predicates

DCG rules and regular `<-` clauses can coexist in the same module:

```seam
sentence >> (noun_phrase, verb_phrase, noun_phrase)

# Regular predicate that uses the DCG rule
valid_sentence(S) <- phrase(sentence, S)
```

---

??? info "Test coverage"

    Tests are in `tests/test_dcg.py`.

    - **Terminals**: single, multiple, empty
    - **Non-terminals**: chaining, extra args
    - **Inline goals**: CLP(ℤ) constraints, arithmetic
    - **Conjunction/disjunction**: multiple alternatives
    - **Negation**: `not [terminal]`
    - **Pushback**: peek without consuming
    - **Recursive rules**: `ab` grammar
    - **phrase/2,3**: full parse, partial parse, remainder
    - **State threading**: counter, tree counting, accumulator
    - **Fixture integration**: `dcg_grammar.seam` with mixed rules and regular predicates

---

*See also: [Lambdas](lambdas.md) — goal closures, an alternative to DCGs for some patterns.*
*See also: [Directives](directives.md) — the `-table` directive for memoizing recursive DCG rules.*
*See also: [Tabling](tabling.md) — SLG tabling, useful for left-recursive grammars.*
