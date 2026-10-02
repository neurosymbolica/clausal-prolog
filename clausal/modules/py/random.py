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

from clausal.modules.py import (
    ModulePredicate,
    _import_stdlib,
    NUMBER_TYPES,
    expect_type,
    raise_domain_error,
    simple_to_trampoline,
    to_text,
)
_random = _import_stdlib("random")

from clausal.logic.exceptions import LogicException, instantiation_error
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
    expect_type(low, NUMBER_TYPES, "float_between/3", arg=1)
    expect_type(high, NUMBER_TYPES, "float_between/3", arg=2)
    low_f, high_f = float(low), float(high)
    if low_f >= high_f:
        return
    if unify(x, _rng.uniform(low_f, high_f), trail):
        yield None


def _random_integer_3(low, high, x, trail, k):
    """integer_between/3: bind X to a random integer in [Low, High]."""
    low, high = deref(low), deref(high)
    # An integer, not anything int() accepts: int(2.7) truncated, and int()
    # of an atom spelled '3' parsed it (RULED 2026-10-02: type_error).
    expect_type(low, int, "integer_between/3", arg=1)
    expect_type(high, int, "integer_between/3", arg=2)
    low_i, high_i = low, high
    if low_i > high_i:
        return
    if unify(x, _rng.randint(low_i, high_i), trail):
        yield None


def _random_member_2(lst, x, trail, k):
    """choice/2: bind X to a randomly chosen element of List."""
    lst = deref(lst)
    if not expect_type(lst, list, "choice/2", arg=1):
        return
    if len(lst) == 0:
        # An empty list is a legitimate "no solution", not a mismatch.
        return
    chosen = _rng.choice(lst)
    if unify(x, chosen, trail):
        yield None


def _random_permutation_2(lst, shuffled, trail, k):
    """permutation/2: bind Shuffled to a random permutation of List."""
    lst = deref(lst)
    if not expect_type(lst, list, "permutation/2", arg=1):
        return
    perm = list(lst)
    _rng.shuffle(perm)
    if unify(shuffled, perm, trail):
        yield None


def _random_sample_3(lst, size, sample, trail, k_cont):
    """sample/3: bind Sample to Size randomly chosen elements (no replacement)."""
    lst, size_val = deref(lst), deref(size)
    if not expect_type(lst, list, "sample/3", arg=1):
        return
    expect_type(size_val, int, "sample/3", arg=2)
    size_int = size_val
    if size_int < 0:
        raise_domain_error("not_less_than_zero", size_int, "sample/3", arg=2)
    if size_int > len(lst):
        return                         # no sample that size: a legitimate "no"
    result = _rng.sample(lst, size_int)
    if unify(sample, result, trail):
        yield None


def _random_seed_1(seed, trail, k):
    """set_seed/1: set the PRNG seed for reproducibility."""
    seed = deref(seed)
    if is_var(seed):
        # RULED 2026-10-02: an unbound seed is an instantiation_error; it
        # used to fail the goal and leave the generator unseeded.
        raise LogicException(instantiation_error("set_seed/1: argument 1"))
    text = to_text(seed)
    if text is not None:
        _rng.seed(text)                # an atom or a string seeds by its text
    elif isinstance(seed, bytes):
        _rng.seed(seed)
    else:
        expect_type(seed, (int, float), "set_seed/1", arg=1)
        _rng.seed(seed)
    yield None


def _maybe_0(trail, k):
    """maybe/0: succeeds with probability 0.5."""
    if _rng.random() < 0.5:
        yield None


def _maybe_1(p, trail, k):
    """maybe/1: succeeds with probability P."""
    p = deref(p)
    expect_type(p, NUMBER_TYPES, "maybe/1", arg=1)
    if not 0 <= p <= 1:
        # A probability; 1.5 used to always succeed and -1 never.
        raise_domain_error("probability", p, "maybe/1", arg=1)
    p_f = float(p)
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
