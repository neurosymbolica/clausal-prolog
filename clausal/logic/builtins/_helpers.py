"""Shared helper functions for builtin predicates.

The heavy-lifting functions (_functor_name, _arity, _nth_arg, _args_list,
_is_compound, _is_ground) are implemented in C in _variables.c for performance.
"""

from __future__ import annotations

from clausal.logic.variables._variables import (
    _functor_name,
    _arity,
    _nth_arg,
    _args_list,
    _is_compound,
    _is_ground,
    _register_term_types,
)
from clausal.terms import Compound, KWTerm

# Register Compound and KWTerm types with the C extension
_register_term_types(Compound, KWTerm)
