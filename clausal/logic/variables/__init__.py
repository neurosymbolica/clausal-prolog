from ._variables import (
    Var as PlainVar,
    AttVar,
    Trail,
    unify,
    unify_with_occurs_check,
    deref,
    walk,
    is_var,
    occurs_check,
    put_attr,
    get_attr,
    del_attr,
    register_attr_hook,
)

# All logic variables are AttVars so constraints (dif, etc.) can be attached.
# AttVar IS-A Var (C tp_base inheritance) — is_var/deref/unify all work unchanged.
# Only overhead: +8 bytes per variable for the attrs pointer (NULL until first put_attr).
Var = AttVar

__all__ = [
    "Var",
    "PlainVar",
    "AttVar",
    "Trail",
    "unify",
    "unify_with_occurs_check",
    "deref",
    "walk",
    "is_var",
    "occurs_check",
    "put_attr",
    "get_attr",
    "del_attr",
    "register_attr_hook",
]
