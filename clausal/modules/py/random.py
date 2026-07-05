"""clausal.modules.py.random — random number predicates for Clausal.

Provides relational predicates for random number generation, random
selection, and seeding.  Import via::

    -import_from(py.random, [float_0_to_1, integer_between, choice, maybe])

Or via module import::

    -import_module(py.random)
    # then use py.random.float_0_to_1(X_), py.random.integer_between(1, 6, X_), etc.

Python interop
--------------
Uses a module-local ``random.Random`` instance to avoid polluting the
global PRNG state.  ``set_seed/1`` seeds this local instance.
"""

from __future__ import annotations

from clausal.modules.py import _import_stdlib, ModulePredicate, simple_to_trampoline
_random = _import_stdlib("random")

from clausal.logic.variables import Var, deref, is_var, unify


# ── Module-local PRNG ───────────────────────────────────────────────────

_rng = _random.Random()


# ── Predicates ──────────────────────────────────────────────────────────


def _random_1(x, trail, k):
    """float_0_to_1/1: bind X to a random float in [0.0, 1.0)."""
    if unify(x, _rng.random(), trail):
        yield None


def _random_float_3(low, high, x, trail, k):
    """float_between/3: bind X to a random float in [Low, High)."""
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
    """integer_between/3: bind X to a random integer in [Low, High]."""
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
    """choice/2: bind X to a randomly chosen element of List."""
    lst = deref(lst)
    if is_var(lst) or not isinstance(lst, list) or len(lst) == 0:
        return
    chosen = _rng.choice(lst)
    if unify(x, chosen, trail):
        yield None


def _random_permutation_2(lst, shuffled, trail, k):
    """permutation/2: bind Shuffled to a random permutation of List."""
    lst = deref(lst)
    if is_var(lst) or not isinstance(lst, list):
        return
    perm = list(lst)
    _rng.shuffle(perm)
    if unify(shuffled, perm, trail):
        yield None


def _random_sample_3(lst, size, sample, trail, k_cont):
    """sample/3: bind Sample to SampleSize randomly chosen elements (no replacement)."""
    lst, size_val = deref(lst), deref(size)
    if is_var(lst) or not isinstance(lst, list):
        return
    if is_var(size_val):
        return
    try:
        size_int = int(size_val)
    except (TypeError, ValueError):
        return
    if size_int < 0 or size_int > len(lst):
        return
    result = _rng.sample(lst, size_int)
    if unify(sample, result, trail):
        yield None


def _random_seed_1(seed, trail, k):
    """set_seed/1: set the PRNG seed for reproducibility."""
    seed = deref(seed)
    if is_var(seed):
        return
    _rng.seed(seed)
    yield None


def _maybe_0(trail, k):
    """maybe/0: succeeds with probability 0.5."""
    if _rng.random() < 0.5:
        yield None


def _maybe_1(p, trail, k):
    """maybe/1: succeeds with probability P."""
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

float_0_to_1 = ModulePredicate("float_0_to_1")
float_0_to_1._register(1, simple_to_trampoline(_random_1))

float_between = ModulePredicate("float_between")
float_between._register(3, simple_to_trampoline(_random_float_3))

integer_between = ModulePredicate("integer_between")
integer_between._register(3, simple_to_trampoline(_random_integer_3))

choice = ModulePredicate("choice")
choice._register(2, simple_to_trampoline(_random_member_2))

permutation = ModulePredicate("permutation")
permutation._register(2, simple_to_trampoline(_random_permutation_2))

sample = ModulePredicate("sample")
sample._register(3, simple_to_trampoline(_random_sample_3))

set_seed = ModulePredicate("set_seed")
set_seed._register(1, simple_to_trampoline(_random_seed_1))

maybe = ModulePredicate("maybe")
maybe._register(0, simple_to_trampoline(_maybe_0))
maybe._register(1, simple_to_trampoline(_maybe_1))
