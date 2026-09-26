# Random Module

The `py.random` standard library module provides relational predicates for random number generation, random selection, and seeding. Uses a module-local PRNG instance to avoid polluting global state.

> **Purity warning:** random predicates are inherently impure — they produce different results on each call and do not behave consistently under backtracking. A goal like `float_0_to_1(X)` will bind `X` to a *new* random value each time it is re-entered, which breaks the referential transparency that pure logic programs rely on. Use these predicates at the boundaries of your program (e.g. to generate test data or make stochastic choices) rather than deep inside relational code. For reproducible results, seed the PRNG with `set_seed/1` before use.

The implementation lives in `clausal/modules/py/random.py`.

---

## Import

```clausal
-import_from(py.random, [float_0_to_1, integer_between, choice,
                         permutation, sample,
                         set_seed, maybe])
```

Or via [module import](import.md):

```clausal
-import_module(py.random)
# then use py.random.float_0_to_1(X_), py.random.integer_between(1, 6, X_), etc.
```

---

## Predicates

### float_0_to_1/1

`float_0_to_1(X)` — bind X to a random float in [0.0, 1.0).

```clausal
random_unit(X) <- float_0_to_1(X)
```

### float_between/3

`float_between(Low, High, X)` — bind X to a random float in [Low, High). Fails if Low >= High or args are unbound.

```clausal
random_temperature(T) <- float_between(36.0, 42.0, T)
```

### integer_between/3

`integer_between(Low, High, X)` — bind X to a random integer in [Low, High] (inclusive both ends).

```clausal
roll_die(N) <- integer_between(1, 6, N)
```

### choice/2

`choice(List, X)` — bind X to a randomly chosen element of [List](lists.md). Deterministic (one solution). Fails if List is empty or unbound.

```clausal
pick_color(COLOR) <- choice(['red', 'green', 'blue'], COLOR)
```

### permutation/2

`permutation(List, Shuffled)` — bind Shuffled to a random permutation of [List](lists.md).

```clausal
shuffle_deck(DECK, SHUFFLED) <- permutation(DECK, SHUFFLED)
```

### sample/3

`sample(List, Size, Sample)` — bind Sample to `Size` randomly chosen elements without replacement. Fails if `Size` > length of List.

```clausal
draw_hand(DECK, HAND) <- sample(DECK, 5, HAND)
```

### set_seed/1

`set_seed(Seed)` — set the PRNG seed for reproducibility. Always succeeds (given a ground arg).

```clausal
deterministic_test(X) <- (set_seed(42), float_0_to_1(X))
```

### maybe/0, maybe/1

`maybe` — succeeds with probability 0.5, fails otherwise.

`maybe(P)` — succeeds with probability P (float in [0.0, 1.0]).

```clausal
maybe_print(X) <- (maybe(), writeln_text(X))

risky_action(X) <- (maybe(0.1), writeln_text(X))
```

---

## Example

```clausal
-import_from(py.random, [integer_between, set_seed, choice, maybe])

roll_die(N) <- integer_between(1, 6, N)

pick_color(COLOR) <- choice(['red', 'green', 'blue'], COLOR)

maybe_greet(NAME) <- (maybe(), writeln_text(f"Hello, {NAME}!"))
```
