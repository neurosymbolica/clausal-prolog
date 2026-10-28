"""Tab completion for the ``?-`` top-level: predicate names (the program's,
then the engine's builtins) and, inside ``library(``, library names."""
from __future__ import annotations

import re

#: What ends a word to complete: Prolog punctuation.
DELIMS = " \t\n`~!@#$%^&*()-=+[{]}\\|;:'\",<>/?"

_LIBRARY_CONTEXT = re.compile(r"library\(\s*$")


def library_names() -> list[str]:
    from clausal.tools.iso_l3_directives import (  # noqa: PLC0415
        _BUILTIN_LIBRARIES, _LIBRARY_MODULES)
    return sorted(set(_BUILTIN_LIBRARIES) | set(_LIBRARY_MODULES))


def builtin_names() -> dict[str, int]:
    """name -> the least arity the engine's builtins of that name have."""
    from clausal.logic.builtins import _registry  # noqa: PLC0415
    out: dict[str, int] = {}
    for name, arity in (*_registry._BUILTINS, *_registry._DB_BUILTINS):
        if type(name) is str and name[:1].islower():
            out[name] = min(arity, out.get(name, arity))
    return out


def program_names(module) -> dict[str, int]:
    """name -> least arity of the predicates ``current_predicate/1`` reports
    for *module*."""
    from clausal import solve  # noqa: PLC0415
    from clausal.logic.variables import Var  # noqa: PLC0415
    from clausal.logic.solve import _deref_walk  # noqa: PLC0415
    names: dict[str, int] = {}
    if module is None:
        return names
    pi = Var()
    try:
        for _ in solve(("current_predicate", pi), module=module):
            w = _deref_walk(pi)
            if type(w) is tuple and len(w) == 3 and type(w[1]) is str \
                    and type(w[2]) is int:
                names[w[1]] = min(w[2], names.get(w[1], w[2]))
    except Exception:  # noqa: BLE001 -- completion never raises
        pass
    return names


def candidates(text: str, line_before: str, module) -> list[str]:
    """The completions of the word *text*, which follows *line_before*."""
    if _LIBRARY_CONTEXT.search(line_before):
        return [n for n in library_names() if n.startswith(text)]
    if not text[:1].islower():
        return []
    pool = {**builtin_names(), **program_names(module)}
    # a name that takes arguments is completed with its opening bracket
    # (readline adds a space after a lone match, and `f (` is not `f(`)
    return sorted(n + ("(" if a > 0 else "") for n, a in pool.items()
                  if n.startswith(text))


class Completer:
    """A readline completer over a top-level's current module."""

    def __init__(self, top):
        self.top = top
        self._matches: list[str] = []

    def __call__(self, text: str, state: int):
        if state == 0:
            import readline  # noqa: PLC0415
            buf = readline.get_line_buffer()
            begin = readline.get_begidx()
            self._matches = candidates(text, buf[:begin], self.top.module)
        return self._matches[state] if state < len(self._matches) else None
