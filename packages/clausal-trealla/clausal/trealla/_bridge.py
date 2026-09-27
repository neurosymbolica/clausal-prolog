"""Helpers for embedding Python values into Prolog query strings.

Usage::

    from clausal.trealla import Trealla, to_prolog
    with Trealla() as t:
        t.load_string("likes(alice, X) :- friend(alice, X).")
        t.query(f"likes({to_prolog('alice')}, X).")
"""



def to_prolog(value) -> str:
    """Convert a Python value to its Prolog text representation.

    Useful for building queries programmatically::

        t.query(f"foo({to_prolog(my_list)}, X).")
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
    if type(value) is tuple and len(value) > 1 and type(value[0]) is str:
        # a compound term: the cell (functor, *args)
        args = ", ".join(to_prolog(a) for a in value[1:])
        return f"{value[0]}({args})"
    raise TypeError(f"Cannot convert {type(value).__name__} to Prolog text")
