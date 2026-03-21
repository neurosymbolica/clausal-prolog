# Definite Clause Grammars (DCGs)

DCGs are a notation for defining grammars and other list-processing tasks. Clausal uses `>>` syntax for grammar rules, which are rewritten to ordinary `<-` clauses with two hidden difference-list arguments at compile time.

The implementation lives in `clausal/templating/term_rewriting.py` (source-level rewriting) and `clausal/logic/builtins.py` (`phrase/2,3`).

*The `-table` directive is often used with DCGs to memoize recursive grammar rules. See [Directives](directives.md).*

---

## Syntax

Grammar rules use `>>` instead of `<-`:

```clausal
greeting >> (["hello", "world"])
```

This rewrites to a clause with two hidden arguments (the input list and the remainder list):

```clausal
greeting(S0, S) <- Append(["hello", "world"], S, S0)
```

### Terminals

Terminals are list literals — they consume tokens from the input:

```clausal
greeting >> (["hello", "world"])
```

The empty list `[]` matches without consuming any input:

```clausal
epsilon >> ([])
```

### Non-terminals

Non-terminals are predicate references — they delegate to other grammar rules:

```clausal
sentence >> (noun_phrase, verb_phrase, noun_phrase)
```

This chains three grammar rules: `noun_phrase` consumes some tokens, then `verb_phrase`, then `noun_phrase` again.

### Extra Arguments

DCG rules can have extra arguments beyond the hidden state pair:

```clausal
digit(D) >> ([D], {D >= 0}, {D <= 9})
```

### Inline Goals

Curly braces `{...}` embed arbitrary Clausal goals inside a grammar rule. They do not consume input:

```clausal
digit(D) >> ([D], {D >= 0}, {D <= 9})
```

The goals `D >= 0` and `D <= 9` are CLP(FD) constraints checked without consuming tokens.

### Conjunction and Disjunction

Multiple items in a rule are joined with `,` (conjunction):

```clausal
sentence >> (noun_phrase, verb_phrase, noun_phrase)
```

Alternatives use `or`:

```clausal
noun_phrase >> (["the", "dog"] or ["the", "cat"] or ["a", "bird"])
verb_phrase >> (["chases"] or ["sees"] or ["likes"])
```

### Negation

`not` tests that a terminal does NOT match:

```clausal
not_a >> (not ["a"], [X])
```

This matches any single token that is not `"a"`.

### Pushback (Semicontext)

A rule can peek at the next token without consuming it using pushback notation:

```clausal
(look_ahead(T), [T]) >> ([T])
```

The left side `(look_ahead(T), [T])` means: match `look_ahead(T)` and push back `[T]`. The right side `([T])` consumes `T`. Net effect: `T` is unified with the next token but remains in the input.

### Recursive Rules

DCG rules can be recursive:

```clausal
ab >> (["a"], ab)
ab >> (["b"], ab)
ab >> ([])
```

This matches strings of `a`s and `b`s in any order.

---

## phrase/2 and phrase/3

The `phrase` builtin invokes a grammar rule on an input list.

### phrase/2

`phrase(RuleName, InputList)` — parse InputList with the named rule, succeeding if the entire list is consumed:

```clausal
valid_sentence(S) <- phrase(sentence, S)
```

Query: `valid_sentence(["the", "dog", "chases", "the", "cat"])` succeeds.

### phrase/3

`phrase(RuleName, S0, S)` — parse with explicit remainder. S is the unconsumed suffix:

```clausal
# Parse and get remainder
partial_parse(INPUT, REST) <- phrase(noun_phrase, INPUT, REST)
```

`phrase/3` is also used for state threading (see below).

### phrase with extra arguments

For rules with extra arguments, pass them as part of the rule:

```clausal
phrase(digit(D), [5])    # D = 5
```

---

## State Threading

DCGs are a general state-passing mechanism — not just for parsing lists of tokens. The hidden difference-list pair can thread any state.

### Core Pattern

Two helper non-terminals provide state access:

```clausal
# state/1: read current state (passthrough)
(state(S), [S]) >> ([S])

# state/2: read old state, replace with new
(state2(S0, S), [S]) >> ([S0])
```

### Counter Example

Thread an integer counter through `phrase/3`:

```clausal
inc >> (state(N0), {N := N0 + 1}, state2(_, N))

count3 >> (inc, inc, inc)
```

Usage:

```clausal
# phrase(count3, [0], [N])  →  N = 3
```

The initial state `[0]` is passed as the input list; the final state `[N]` is the remainder.

### Tree Leaf Counting

Thread a counter to count leaves in a binary tree:

```clausal
count_leaves("leaf") >> (state(N0), {N := N0 + 1}, state2(_, N))
count_leaves([L, R]) >> (count_leaves(L), count_leaves(R))

num_leaves(T, N) <- phrase(count_leaves(T), [0], [N])
```

### Accumulator

Thread a list accumulator to collect items:

```clausal
push(X) >> (state(ACC0), {ACC is [X, *ACC0]}, state2(_, ACC))

push_all([]) >> ([])
push_all([X, *XS]) >> (push(X), push_all(XS))

collect_items(XS, R) <- phrase(push_all(XS), [[]], [R])
```

---

## Coexisting with Regular Predicates

DCG rules and regular `<-` clauses can coexist in the same module:

```clausal
sentence >> (noun_phrase, verb_phrase, noun_phrase)

# Regular predicate that uses the DCG rule
valid_sentence(S) <- phrase(sentence, S)
```

---

??? info "Test coverage"

    Tests are in `tests/test_dcg.py` (47 tests).

    - **Terminals**: single, multiple, empty
    - **Non-terminals**: chaining, extra args
    - **Inline goals**: CLP(FD) constraints, arithmetic
    - **Conjunction/disjunction**: multiple alternatives
    - **Negation**: `not [terminal]`
    - **Pushback**: peek without consuming
    - **Recursive rules**: `ab` grammar
    - **phrase/2,3**: full parse, partial parse, remainder
    - **State threading**: counter, tree counting, accumulator
    - **Fixture integration**: `dcg_grammar.clausal` with mixed rules and regular predicates
