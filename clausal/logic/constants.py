"""Load-time support for -constants declarations.

A constant is a module global bound to a ground value before any clause
statement executes; clause construction embeds the value, so downstream
(indexing, solve, translation) never sees a name. This module supplies the
groundness gate the lowered assignment routes through.
"""
from clausal.logic.variables import Var


class ConstantNotGroundError(ValueError):
    """A -constants RHS produced a value containing an unbound variable."""


def _contains_var(value) -> bool:
    if isinstance(value, Var):
        return True
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_contains_var(v) for v in value)
    if isinstance(value, dict):
        return any(_contains_var(k) or _contains_var(v)
                   for k, v in value.items())
    # Term objects (Compound, KWTerm, compile-time PredicateMeta instances,
    # Seg* containers): delegate to the canonical recursive ground check
    # instead of duck-typing an ``.args`` tuple — compile-time predicate
    # classes hold fields by name (``_fields``/``__slots__``), not a generic
    # ``.args``, so ``getattr(value, "args", None)`` silently missed them.
    # ``Compound.is_ground`` (terms.py:587) does the same delegation, lazily,
    # to dodge the circular import (this module is imported very early, from
    # import_hook.py, before clausal.logic.builtins exists).
    from clausal.logic.builtins._helpers import _is_ground  # noqa: PLC0415
    return not _is_ground(value)


def check_constant_ground(name: str, value):
    """Gate a -constants binding: return *value* iff it is ground."""
    if _contains_var(value):
        raise ConstantNotGroundError(
            f"-constants: `{name}` must be fully ground at load time; "
            f"got a value containing an unbound variable: {value!r}")
    return value
