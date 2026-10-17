# Random Module

!!! warning "Deprecated"
    `py.random` is deprecated (2026-10-07). It draws from one global generator
    seeded from OS entropy, so its answers are not reproducible and do not
    follow backtracking. Use [Pure Random](pure_random.md)
    (`library(pure_random)`) instead: the generator state is a term, every
    draw is a relation `S0 -> S`, and the same seed always gives the same
    answers. The first call of a `py.random` predicate warns once per process
    (`ClausalPyRandomDeprecationWarning`). The module keeps working until it
    is removed.

The `py.random` standard library module provides relational predicates for random number generation, random selection, and seeding. Uses a module-local PRNG instance to avoid polluting global state.

> **Purity warning:** random predicates are inherently impure — they produce different results on each call and do not behave consistently under backtracking. A goal like `float_0_to_1(X)` will bind `X` to a *new* random value each time it is re-entered, which breaks the referential transparency that pure logic programs rely on. Use these predicates at the boundaries of your program (e.g. to generate test data or make stochastic choices) rather than deep inside relational code. For reproducible results, seed the PRNG with `set_seed/1` before use.

The implementation lives in `clausal/modules/py/random.py`.

!!! note "Clausal Prolog examples"

    Examples on this page are [Clausal Prolog](clausal_prolog.md)
    (`.clausal`), which uses ISO Prolog syntax. Clausal Prolog reaches
    Python only through a `.seam` module, so it imports this module through
    its facade `library(py_random)`; the [seam](syntax.md) imports
    `py.random` directly (`-import_from(py.random, [...])`).

---

## Import

```clausal
:- use_module(library(py_random), [float_0_to_1/1, integer_between/3,
                                   choice/2, permutation/2, sample/3,
                                   set_seed/1, maybe/0, maybe/1]).

test("imported") :-
    integer_between(1, 6, N),
    integer(N).
```

Or import the whole module and qualify each call with the module name:

```clausal
:- use_module(library(py_random)).

% then use py_random:float_0_to_1(X), py_random:integer_between(1, 6, X), etc.
test("qualified") :-
    py_random:integer_between(1, 6, N),
    N >= 1, N =< 6.
```

A direct import of the Python module, `:- use_module(py/random, [...])`, is
refused in `.clausal` with `permission_error(access, python_module,
py.random)`; the error names the facade to import instead.

!!! note "`permutation/2` and `sample/3` here are not the list library's"

    Importing `permutation/2` from `library(py_random)` replaces the
    [list library's](lists.md) `permutation/2` in that file: it answers one
    random permutation instead of enumerating every one.

---

## Predicates

### float_0_to_1/1

`float_0_to_1(X)` — bind X to a random float in [0.0, 1.0).

```clausal
:- use_module(library(py_random), [float_0_to_1/1]).

random_unit(X) :-
    float_0_to_1(X).

test("unit") :-
    random_unit(X),
    X >= 0.0, X < 1.0.
```

### float_between/3

`float_between(Low, High, X)` — bind X to a random float in [Low, High). Fails if Low >= High or args are unbound.

```clausal
:- use_module(library(py_random), [float_between/3]).

random_temperature(T) :-
    float_between(36.0, 42.0, T).

test("temperature") :-
    random_temperature(T),
    T >= 36.0, T < 42.0.

test("empty range fails") :-
    \+ float_between(42.0, 36.0, _).
```

### integer_between/3

`integer_between(Low, High, X)` — bind X to a random integer in [Low, High] (inclusive both ends).

```clausal
:- use_module(library(py_random), [integer_between/3]).

roll_die(N) :-
    integer_between(1, 6, N).

test("die") :-
    roll_die(N),
    integer(N), N >= 1, N =< 6.
```

### choice/2

`choice(List, X)` — bind X to a randomly chosen element of [List](lists.md). Deterministic (one solution). Fails if List is empty or unbound.

```clausal
:- use_module(library(py_random), [choice/2]).

pick_color(COLOR) :-
    choice([red, green, blue], COLOR).

test("color") :-
    findall(C, pick_color(C), [COLOR]),
    in_(COLOR, [red, green, blue]).

test("empty list fails") :-
    \+ choice([], _).
```

### permutation/2

`permutation(List, Shuffled)` — bind Shuffled to a random permutation of [List](lists.md).

```clausal
:- use_module(library(py_random), [permutation/2]).

shuffle_deck(DECK, SHUFFLED) :-
    permutation(DECK, SHUFFLED).

test("shuffle") :-
    findall(S, shuffle_deck([1, 2, 3, 4], S), [SHUFFLED]),
    msort(SHUFFLED, [1, 2, 3, 4]).
```

### sample/3

`sample(List, Size, Sample)` — bind Sample to `Size` randomly chosen elements without replacement. Fails if `Size` > length of List.

```clausal
:- use_module(library(py_random), [sample/3]).

draw_hand(DECK, HAND) :-
    sample(DECK, 5, HAND).

test("hand") :-
    draw_hand([a, b, c, d, e, f, g], HAND),
    length(HAND, 5).

test("too few cards fails") :-
    \+ draw_hand([a, b, c], _).
```

### set_seed/1

`set_seed(Seed)` — set the PRNG seed for reproducibility. Always succeeds (given a ground arg).

```clausal
:- use_module(library(py_random), [set_seed/1, float_0_to_1/1]).

deterministic_test(X) :-
    set_seed(42),
    float_0_to_1(X).

test("same seed, same draw") :-
    deterministic_test(X),
    deterministic_test(Y),
    X == Y.
```

### maybe/0, maybe/1

`maybe` — succeeds with probability 0.5, fails otherwise.

`maybe(P)` — succeeds with probability P (float in [0.0, 1.0]).

```clausal
:- use_module(library(py_random), [maybe/0, maybe/1]).

maybe_print(X) :-
    maybe,
    writeln_text(X).

risky_action(X) :-
    maybe(0.1),
    writeln_text(X).

test("certain") :-
    maybe(1.0).

test("never") :-
    \+ maybe(0.0).
```

---

## Example

```clausal
:- use_module(library(py_random), [integer_between/3, set_seed/1, choice/2,
                                   maybe/0]).

roll_die(N) :-
    integer_between(1, 6, N).

pick_color(COLOR) :-
    choice([red, green, blue], COLOR).

maybe_greet(NAME) :-
    maybe,
    format("Hello, ~w!~n", [NAME]).

test("example") :-
    set_seed(7),
    roll_die(N),
    N >= 1, N =< 6,
    pick_color(COLOR),
    in_(COLOR, [red, green, blue]).
```

In the seam the greeting is an f-string, `writeln_text(f"Hello, {NAME}!")`;
Clausal Prolog has no f-strings, so it formats with `format/2`.
