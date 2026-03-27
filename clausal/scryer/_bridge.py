"""Helpers for embedding Python values into Prolog query strings.

Usage::

    from clausal.scryer import Scryer, to_prolog
    with Scryer() as s:
        s.load_string("likes(alice, X) :- friend(alice, X).")
        s.query(f"likes({to_prolog('alice')}, X).")
"""

from clausal.terms import Compound


def to_prolog(value) -> str:
    """Convert a Python value to its Prolog text representation.

    Useful for building queries programmatically::

        s.query(f"foo({to_prolog(my_list)}, X).")
    """
    if value is None:
        return "[]"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace("'", "\\'")
        return f"'{escaped}'"
    if isinstance(value, list):
        return "[" + ", ".join(to_prolog(e) for e in value) + "]"
    if isinstance(value, Compound):
        args = ", ".join(to_prolog(a) for a in value.args)
        return f"{value.functor}({args})"
    raise TypeError(f"Cannot convert {type(value).__name__} to Prolog text")
