"""Backward compatibility — canonical implementation in clausal.modules.py.random."""
from clausal.modules.py.random import *  # noqa: F401,F403
from clausal.modules.py.random import (  # noqa: F401 — re-export internals for tests
    _RandomPredicate, _simple_to_trampoline, _rng,
    _random_1, _random_float_3, _random_integer_3,
    _random_member_2, _random_permutation_2, _random_sample_3,
    _random_seed_1, _maybe_0, _maybe_1,
)
