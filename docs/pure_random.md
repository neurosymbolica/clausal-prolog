# Pure Random Numbers

`pure_random` is a random-number library with **no hidden state**. The
generator state is an ordinary term, `rng(Seed, N)`: the seed you chose and
the number of draws taken so far. Every predicate is a relation from an input
state `S0` to an output state `S`:

| Predicate | Mode | Answer |
|---|---|---|
| `rng_seed(Seed, S)` | `+Seed, -S` | `S = rng(Seed, 0)`, the initial state |
| `random(X, S0, S)` | `-X, +S0, -S` | a float in `[0, 1)` |
| `random_between(L, H, X, S0, S)` | `+L, +H, -X, +S0, -S` | an integer in `[L, H]`, both ends included |
| `random_member(X, List, S0, S)` | `-X, +List, +S0, -S` | an element of `List` |
| `random_permutation(List, Perm, S0, S)` | `+List, -Perm, +S0, -S` | a permutation of `List` |
| `random_sample(List, K, Sample, S0, S)` | `+List, +K, -Sample, +S0, -S` | `K` elements of `List` at distinct positions, in the order drawn |

The implementation lives in `clausal/modules/pure_random.py`.

## Why state-threaded

- **Reproducible.** The same seed gives the same answers on every run, in
  every process, on every platform, under every supported Python version (see
  [the guarantee](#the-reproducibility-guarantee) below).
- **Backtrack-safe.** The state is a binding, so backtracking restores it.
  Re-running a goal from the same `S0` gives the same answer. A global
  generator cannot do this: it moves on even when the goal that drew from it
  is undone.
- **Pure.** No clock, no OS entropy, no global variable. A predicate's answer
  depends only on its arguments, so the library is safe to allow under a
  sandbox.

Want different answers on each run? Choose the seed outside the program, for
example from the command line, and pass it in.

## Import

From the seam:

```seam
-import_from(pure_random, [rng_seed, random, random_between, random_member,
                           random_permutation, random_sample])
```

From Clausal Prolog (`.clausal`) or a `.pl` file:

```prolog
:- use_module(library(pure_random),
              [rng_seed/2, random/3, random_between/5, random_member/4,
               random_permutation/4, random_sample/5]).
```

## Threading the state

Pass each output state on as the next input:

```seam
-import_from(pure_random, [rng_seed, random_between])

two_dice(A, B) <- (
    rng_seed(42, S0),
    random_between(1, 6, A, S0, S1),
    random_between(1, 6, B, S1, _)
)

test("the same seed gives the same rolls") <- (
    two_dice(A1, B1), two_dice(A2, B2), A1 == A2, B1 == B2
)
```

Backtracking restores the state, so both branches below draw the same
number:

```seam
-import_from(pure_random, [rng_seed, random_between])

test("backtracking restores the state") <- (
    rng_seed(7, S0),
    findall(X, (random_between(1, 100, X, S0, _)
                or random_between(1, 100, X, S0, _)), [A, B]),
    A == B
)
```

### With DCGs

The state is the last two arguments, which is where a grammar rule threads
its pair. So a DCG body threads the generator with no plumbing, and
`phrase/3` runs it from a seed:

```seam
-import_from(pure_random, [rng_seed, random_between])

dice([X, Y]) >> (random_between(1, 6, X), random_between(1, 6, Y))

test("a grammar threads the state") <- (
    rng_seed(1, S0),
    phrase(dice([X, Y]), S0, _),
    between(1, 6, X), between(1, 6, Y)
)
```

The same in Clausal Prolog:

```prolog
dice([X, Y]) --> random_between(1, 6, X), random_between(1, 6, Y).

roll(Xs) :- rng_seed(1, S0), phrase(dice(Xs), S0, _).
```

## Errors

A random predicate never fails silently.

| Case | Error |
|---|---|
| `S0` unbound, or `rng(Seed, N)` with an unbound part | `instantiation_error` |
| `S0` bound but not `rng(Seed, N)` with a valid seed and an integer `N >= 0` | `type_error(rng_state, S0)` |
| `rng_seed/2`: `Seed` unbound | `instantiation_error` |
| `rng_seed/2`: `Seed` not an integer, an atom or a string | `type_error(rng_seed, Seed)` |
| `random_between/5`: `L` or `H` unbound | `instantiation_error` |
| `random_between/5`: `L` or `H` not an integer | `type_error(integer, _)` |
| `random_between/5`: `L > H` (an empty range) | `domain_error(not_less_than(L), H)` |
| A list argument that is partial | `instantiation_error` |
| A list argument that is not a list | `type_error(list, _)` |
| `random_member/4` on `[]` | `domain_error(non_empty_list, [])` |
| `random_sample/5`: `K` not an integer | `type_error(integer, K)` |
| `random_sample/5`: `K < 0` | `domain_error(not_less_than_zero, K)` |
| `random_sample/5`: `K` greater than the list's length `Len` | `domain_error(not_greater_than(Len), K)` |

An empty range and an empty list are errors and not failures. A draw from
nothing is almost always a bug in the caller, and a failure would hide it.

## Seeds

A seed is an integer, an atom or a string. An atom and a string seed by their
text, so `abc` and `"abc"` give the same stream. The integer `5` and the atom
`'5'` are different seeds. The seed is never hashed with Python's `hash()`,
which changes from one process to the next.

## The reproducibility guarantee

The `N`-th draw from a seed is a fixed float:

1. The seed is encoded as bytes: an integer as `i` followed by its decimal
   digits, an atom or a string as `t` followed by its text in UTF-8. The seed
   material is the SHA-256 digest of `clausal.pure_random.v1`, a zero byte,
   the seed bytes, a zero byte and the decimal digits of `N`, read as a
   big-endian integer.
2. The float is `random.Random(material).random()`. Python promises that
   `random()` gives the same sequence for the same seed on every version.
   Nothing else in Python's `random` module is used. `randint`, `randrange`,
   `choice`, `shuffle` and `sample` have changed between Python versions.
3. Clausal's own rules turn draws into the other answers:
    - each draw gives 53 random bits;
    - an integer in `[L, H]` is built from enough draws to cover the range,
      and rejection sampling keeps it unbiased; every call takes at least one
      draw;
    - `random_member/4` takes the element at a random index;
    - `random_permutation/4` is a Fisher–Yates shuffle from the end;
    - `random_sample/5` runs `K` steps of a Fisher–Yates shuffle from the
      front.

The output state is `rng(Seed, N + D)`, where `D` is the number of draws the
call took. The tests in `tests/test_pure_random.py` pin fixed seeds to fixed
outputs, so any change to this mapping, or in Python, fails the tests.

## Compared with Scryer's `library(random)`

Scryer Prolog's `library(random)` is impure: `random/1`,
`random_integer/3` (the upper bound is *excluded*), `set_random/1` and
`maybe/0` share one global generator. This library keeps Scryer's
argument order and adds the two state arguments: `random(X)` becomes
`random(X, S0, S)`. For integers it uses the name `random_between`, whose
upper bound is *included*, so `random_integer` never means two things.

The library is named `library(pure_random)`. Scryer already has a
`library(random)`, and a facade never takes the name of a Scryer library.
Importing Scryer's `random/1` from `library(pure_random)` is an error that
lists what the library does export. It never binds to something else.

A Scryer-compatible impure layer (`random/1`, `random_integer/3`,
`set_random/1`) is not provided. It may be added if a program needs it.

## The old `py.random` module

[`py.random`](random.md) (`library(py_random)`) draws from a process-global
generator. It is **deprecated**. The first time a program calls one of its
predicates, it warns once per process
(`clausal.lint_warnings.ClausalPyRandomDeprecationWarning`). It still works,
and will be removed in a later release.
