# Random Module

The `py.random` standard library module provides relational predicates for random number generation, random selection, and seeding. Uses a module-local PRNG instance to avoid polluting global state.

The implementation lives in `clausal/modules/py/random.py`.

---

## Import

```clausal
-import_from(py.random, [Random, RandomInteger, RandomMember,
                         RandomPermutation, RandomSample,
                         RandomSeed, Maybe])
```

Or via [module import](import.md):

```clausal
-import_module(py.random)
# then use py.random.Random(X_), py.random.RandomInteger(1, 6, X_), etc.
```

---

## Predicates

### Random/1

`Random(X)` — bind X to a random float in [0.0, 1.0).

```clausal
random_unit(X) <- Random(X)
```

### RandomFloat/3

`RandomFloat(Low, High, X)` — bind X to a random float in [Low, High). Fails if Low >= High or args are unbound.

```clausal
random_temperature(T) <- RandomFloat(36.0, 42.0, T)
```

### RandomInteger/3

`RandomInteger(Low, High, X)` — bind X to a random integer in [Low, High] (inclusive both ends).

```clausal
roll_die(N) <- RandomInteger(1, 6, N)
```

### RandomMember/2

`RandomMember(List, X)` — bind X to a randomly chosen element of [List](lists.md). Deterministic (one solution). Fails if List is empty or unbound.

```clausal
pick_color(COLOR) <- RandomMember(["red", "green", "blue"], COLOR)
```

### RandomPermutation/2

`RandomPermutation(List, Shuffled)` — bind Shuffled to a random permutation of [List](lists.md).

```clausal
shuffle_deck(DECK, SHUFFLED) <- RandomPermutation(DECK, SHUFFLED)
```

### RandomSample/3

`RandomSample(List, K, Sample)` — bind Sample to K randomly chosen elements without replacement. Fails if K > length of List.

```clausal
draw_hand(DECK, HAND) <- RandomSample(DECK, 5, HAND)
```

### RandomSeed/1

`RandomSeed(Seed)` — set the PRNG seed for reproducibility. Always succeeds (given a ground arg).

```clausal
deterministic_test(X) <- (RandomSeed(42), Random(X))
```

### Maybe/0, Maybe/1

`Maybe` — succeeds with probability 0.5, fails otherwise.

`Maybe(P)` — succeeds with probability P (float in [0.0, 1.0]).

```clausal
maybe_print(X) <- (Maybe(), Writeln(X))

risky_action(X) <- (Maybe(0.1), Writeln(X))
```

---

## Example

```clausal
-import_from(py.random, [RandomInteger, RandomSeed, RandomMember, Maybe])

roll_die(N) <- RandomInteger(1, 6, N)

pick_color(COLOR) <- RandomMember(["red", "green", "blue"], COLOR)

maybe_greet(NAME) <- (Maybe(), Writeln(f"Hello, {NAME}!"))
```
