"""clausal.modules.py.random — Random number predicates for Clausal.

Provides relational predicates for random number generation, random
selection, and seeding.  Import via::

    -import_from(py.random, [Random, RandomInteger, RandomMember, Maybe])

Or via module import::

    -import_module(py.random)
    # then use py.random.Random(X_), py.random.RandomInteger(1, 6, X_), etc.

Python interop
--------------
Uses a module-local ``random.Random`` instance to avoid polluting the
global PRNG state.  ``RandomSeed/1`` seeds this local instance.
"""

from __future__ import annotations

from clausal.modules.py import _import_stdlib
_random = _import_stdlib("random")

from typing import Callable

from clausal.logic.variables import Var, deref, is_var, unify
from clausal.logic.trampoline import DONE


# ── Module-local PRNG ───────────────────────────────────────────────────

_rng = _random.Random()


# ── Dispatch adapter (same pattern as uuid.py) ─────────────────────────


class _RandomPredicate:
    """Adapter with ``_get_dispatch()`` for a random predicate."""

    __slots__ = ("_name", "_dispatch_fns")

    def __init__(self, name: str) -> None:
        self._name = name
        self._dispatch_fns: dict[int, Callable] = {}

    def _register(self, arity: int, fn: Callable) -> None:
        self._dispatch_fns[arity] = fn

    def _get_dispatch(self) -> Callable:
        if len(self._dispatch_fns) == 1:
            return next(iter(self._dispatch_fns.values()))
        return self._multi_dispatch

    def _multi_dispatch(self, this_generator, parent, *args):
        arity = len(args) - 1  # exclude trail
        fn = self._dispatch_fns.get(arity)
        if fn is None:
            yield (parent, DONE)
            return
        yield from fn(this_generator, parent, *args)

    def __repr__(self) -> str:
        arities = sorted(self._dispatch_fns)
        return f"random.{self._name}/{arities}"


# ── Simple-mode wrapper ─────────────────────────────────────────────────


def _simple_to_trampoline(simple_fn):
    """Wrap a simple-mode fn(*args, trail, k) → trampoline protocol."""
    def trampoline_fn(this_generator, parent, *args):
        for _ in simple_fn(*args, None):
            yield (parent, None)
        yield (parent, DONE)
    return trampoline_fn


# ── Predicates ──────────────────────────────────────────────────────────


def _random_1(x, trail, k):
    """Random/1: bind X to a random float in [0.0, 1.0)."""
    if unify(x, _rng.random(), trail):
        yield None


def _random_float_3(low, high, x, trail, k):
    """RandomFloat/3: bind X to a random float in [Low, High)."""
    low, high = deref(low), deref(high)
    if is_var(low) or is_var(high):
        return
    try:
        low_f, high_f = float(low), float(high)
    except (TypeError, ValueError):
        return
    if low_f >= high_f:
        return
    if unify(x, _rng.uniform(low_f, high_f), trail):
        yield None


def _random_integer_3(low, high, x, trail, k):
    """RandomInteger/3: bind X to a random integer in [Low, High]."""
    low, high = deref(low), deref(high)
    if is_var(low) or is_var(high):
        return
    try:
        low_i, high_i = int(low), int(high)
    except (TypeError, ValueError):
        return
    if low_i > high_i:
        return
    if unify(x, _rng.randint(low_i, high_i), trail):
        yield None


def _random_member_2(lst, x, trail, k):
    """RandomMember/2: bind X to a randomly chosen element of List."""
    lst = deref(lst)
    if is_var(lst) or not isinstance(lst, list) or len(lst) == 0:
        return
    chosen = _rng.choice(lst)
    if unify(x, chosen, trail):
        yield None


def _random_permutation_2(lst, shuffled, trail, k):
    """RandomPermutation/2: bind Shuffled to a random permutation of List."""
    lst = deref(lst)
    if is_var(lst) or not isinstance(lst, list):
        return
    perm = list(lst)
    _rng.shuffle(perm)
    if unify(shuffled, perm, trail):
        yield None


def _random_sample_3(lst, k, sample, trail, k_cont):
    """RandomSample/3: bind Sample to K randomly chosen elements (no replacement)."""
    lst, k_val = deref(lst), deref(k)
    if is_var(lst) or not isinstance(lst, list):
        return
    if is_var(k_val):
        return
    try:
        k_int = int(k_val)
    except (TypeError, ValueError):
        return
    if k_int < 0 or k_int > len(lst):
        return
    result = _rng.sample(lst, k_int)
    if unify(sample, result, trail):
        yield None


def _random_seed_1(seed, trail, k):
    """RandomSeed/1: set the PRNG seed for reproducibility."""
    seed = deref(seed)
    if is_var(seed):
        return
    _rng.seed(seed)
    yield None


def _maybe_0(trail, k):
    """Maybe/0: succeeds with probability 0.5."""
    if _rng.random() < 0.5:
        yield None


def _maybe_1(p, trail, k):
    """Maybe/1: succeeds with probability P."""
    p = deref(p)
    if is_var(p):
        return
    try:
        p_f = float(p)
    except (TypeError, ValueError):
        return
    if _rng.random() < p_f:
        yield None


# ── Build and export predicate objects ──────────────────────────────────

Random = _RandomPredicate("Random")
Random._register(1, _simple_to_trampoline(_random_1))

RandomFloat = _RandomPredicate("RandomFloat")
RandomFloat._register(3, _simple_to_trampoline(_random_float_3))

RandomInteger = _RandomPredicate("RandomInteger")
RandomInteger._register(3, _simple_to_trampoline(_random_integer_3))

RandomMember = _RandomPredicate("RandomMember")
RandomMember._register(2, _simple_to_trampoline(_random_member_2))

RandomPermutation = _RandomPredicate("RandomPermutation")
RandomPermutation._register(2, _simple_to_trampoline(_random_permutation_2))

RandomSample = _RandomPredicate("RandomSample")
RandomSample._register(3, _simple_to_trampoline(_random_sample_3))

RandomSeed = _RandomPredicate("RandomSeed")
RandomSeed._register(1, _simple_to_trampoline(_random_seed_1))

Maybe = _RandomPredicate("Maybe")
Maybe._register(0, _simple_to_trampoline(_maybe_0))
Maybe._register(1, _simple_to_trampoline(_maybe_1))
