# Definite Clause Grammars (DCGs)

DCGs are a notation for defining grammars and other list-processing tasks. Clausal uses `>>` syntax for grammar rules, which are rewritten to ordinary `<-` clauses with two hidden difference-list arguments at compile time.

The implementation lives in `clausal/templating/term_rewriting.py` (source-level rewriting) and `clausal/logic/builtins.py` (`phrase/2,3`). Added in V2-17.

---

## Syntax

Grammar rules use `>>` instead of `<-`:

```
greeting >> (["hello", "world"])
```

This rewrites to a clause with two hidden arguments (the input list and the remainder list):

```
greeting(S0_, S_) <- Append(["hello", "world"], S_, S0_)
```

### Terminals

Terminals are list literals — they consume tokens from the input:

```
greeting >> (["hello", "world"])
```

The empty list `[]` matches without consuming any input:

```
epsilon >> ([])
```

### Non-terminals

Non-terminals are predicate references — they delegate to other grammar rules:

```
sentence >> (noun_phrase, verb_phrase, noun_phrase)
```

This chains three grammar rules: `noun_phrase` consumes some tokens, then `verb_phrase`, then `noun_phrase` again.

### Extra Arguments

DCG rules can have extra arguments beyond the hidden state pair:

```
digit(D_) >> ([D_], {D_ >= 0}, {D_ <= 9})
```

### Inline Goals

Curly braces `{...}` embed arbitrary Clausal goals inside a grammar rule. They do not consume input:

```
digit(D_) >> ([D_], {D_ >= 0}, {D_ <= 9})
```

The goals `D_ >= 0` and `D_ <= 9` are CLP(FD) constraints checked without consuming tokens.

### Conjunction and Disjunction

Multiple items in a rule are joined with `,` (conjunction):

```
sentence >> (noun_phrase, verb_phrase, noun_phrase)
```

Alternatives use `or`:

```
noun_phrase >> (["the", "dog"] or ["the", "cat"] or ["a", "bird"])
verb_phrase >> (["chases"] or ["sees"] or ["likes"])
```

### Negation

`not` tests that a terminal does NOT match:

```
not_a >> (not ["a"], [X_])
```

This matches any single token that is not `"a"`.

### Pushback (Semicontext)

A rule can peek at the next token without consuming it using pushback notation:

```
(look_ahead(T_), [T_]) >> ([T_])
```

The left side `(look_ahead(T_), [T_])` means: match `look_ahead(T_)` and push back `[T_]`. The right side `([T_])` consumes `T_`. Net effect: `T_` is unified with the next token but remains in the input.

### Recursive Rules

DCG rules can be recursive:

```
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

```
valid_sentence(S_) <- phrase(sentence, S_)
```

Query: `valid_sentence(["the", "dog", "chases", "the", "cat"])` succeeds.

### phrase/3

`phrase(RuleName, S0, S)` — parse with explicit remainder. S is the unconsumed suffix:

```
# Parse and get remainder
partial_parse(Input_, Rest_) <- phrase(noun_phrase, Input_, Rest_)
```

`phrase/3` is also used for state threading (see below).

### phrase with extra arguments

For rules with extra arguments, pass them as part of the rule:

```
phrase(digit(D_), [5])    # D_ = 5
```

---

## State Threading

DCGs are a general state-passing mechanism — not just for parsing lists of tokens. The hidden difference-list pair can thread any state.

### Core Pattern

Two helper non-terminals provide state access:

```
# state/1: read current state (passthrough)
(state(S_), [S_]) >> ([S_])

# state/2: read old state, replace with new
(state2(S0_, S_), [S_]) >> ([S0_])
```

### Counter Example

Thread an integer counter through `phrase/3`:

```
inc >> (state(N0_), {N_ := N0_ + 1}, state2(_, N_))

count3 >> (inc, inc, inc)
```

Usage:

```
# phrase(count3, [0], [N_])  →  N_ = 3
```

The initial state `[0]` is passed as the input list; the final state `[N_]` is the remainder.

### Tree Leaf Counting

Thread a counter to count leaves in a binary tree:

```
count_leaves("leaf") >> (state(N0_), {N_ := N0_ + 1}, state2(_, N_))
count_leaves([L_, R_]) >> (count_leaves(L_), count_leaves(R_))

num_leaves(T_, N_) <- phrase(count_leaves(T_), [0], [N_])
```

### Accumulator

Thread a list accumulator to collect items:

```
push(X_) >> (state(Acc0_), {Acc_ is [X_, *Acc0_]}, state2(_, Acc_))

push_all([]) >> ([])
push_all([X_, *Xs_]) >> (push(X_), push_all(Xs_))

collect_items(XS_, R_) <- phrase(push_all(XS_), [[]], [R_])
```

---

## Coexisting with Regular Predicates

DCG rules and regular `<-` clauses can coexist in the same module:

```
sentence >> (noun_phrase, verb_phrase, noun_phrase)

# Regular predicate that uses the DCG rule
valid_sentence(S_) <- phrase(sentence, S_)
```

---

## Test Coverage

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
