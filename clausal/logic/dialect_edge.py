"""The one-way dependency edge between Clausal Prolog and ISO Prolog.

Operator ruling 2026-10-01 (final): a ``.pl`` module may call a Clausal
Prolog (``.clausal``) module; a Clausal Prolog module may NEVER call a
``.pl`` module.  No flag or directive opts in, and it is strict for
closures too.  A ``.seam`` module is the Python boundary and is not bound
by the rule (the programmer's responsibility).

Route 1 -- an import -- is refused at load (``iso_l3_directives.
_use_module``).  This module is the RUN-TIME half: every place a goal,
clause or closure is resolved to another module's database asks
:func:`refuse_edge` with the CALLER (the module the resolving builtin or
compiled call site belongs to) and the TARGET.  The refusal reuses route
1's error term, as an ISO error a ``catch/3`` can match::

    error(permission_error(access, prolog_module, M), Context)

and, for a Python module target (§4b: Clausal Prolog reaches Python only
through a ``.seam`` module)::

    error(permission_error(access, python_module, M), Context)

The caller's dialect comes from its source suffix
(:func:`clausal.end_module.surface_of`), read once per module and cached on
the :class:`~clausal.logic.database.Module` / ``Database`` object, so a
``.seam`` or ``.pl`` caller pays one attribute read and nothing else.
"""
from __future__ import annotations

import types
from typing import Any

#: Cache attribute on a Module / Database: True when its source is Clausal
#: Prolog.  Only a definite answer (a ``__file__`` was there) is cached.
_CACHE = "_dialect_is_clausal_prolog"


def _namespace(obj: Any) -> "dict | None":
    if isinstance(obj, types.ModuleType):
        return vars(obj)
    md = getattr(obj, "module_dict", None)
    if isinstance(md, dict):
        return md
    if isinstance(obj, dict):
        return obj
    ns = getattr(obj, "__dict__", None)
    return ns if isinstance(ns, dict) else None


def is_clausal_prolog_caller(obj: Any) -> bool:
    """True when *obj* -- a :class:`Module`, a ``Database`` or a module
    namespace -- was loaded from a Clausal Prolog source file."""
    if obj is None:
        return False
    cached = getattr(obj, _CACHE, None)
    if cached is not None:
        return cached
    md = _namespace(obj)
    path = md.get("__file__") if md is not None else None
    if not path or not isinstance(path, str):
        return False                # not known yet: never cached
    from clausal.end_module import (  # noqa: PLC0415
        SURFACE_CLAUSAL_PROLOG, surface_of)
    answer = surface_of(path) == SURFACE_CLAUSAL_PROLOG
    if not isinstance(obj, (dict, types.ModuleType)):
        # Only on a Module / Database: never written into a namespace.
        try:
            setattr(obj, _CACHE, answer)
        except (AttributeError, TypeError):   # a slotted object
            pass
    return answer


def forbidden_kind(target: Any) -> "str | None":
    """``"prolog_module"`` when *target* (a Module, a Database or a module
    object) was loaded from a ``.pl`` file, ``"python_module"`` when it is
    a Python module (a ``__file__`` that is no predicate-module source),
    else None: a seam or Clausal Prolog module, or one built in memory with
    no source file."""
    md = _namespace(target)
    if md is None:
        return None
    path = md.get("__file__")
    if not path or not isinstance(path, str):
        return None
    try:
        return _KIND_BY_PATH[path]
    except KeyError:
        pass
    from clausal.end_module import SURFACE_PL, surface_of  # noqa: PLC0415
    surface = surface_of(path)
    kind = ("prolog_module" if surface == SURFACE_PL
            else "python_module" if surface is None else None)
    _KIND_BY_PATH[path] = kind
    return kind


#: ``__file__`` -> :func:`forbidden_kind`'s answer.  A path's suffix never
#: changes, so the answer is cached for the process (the extension tuples
#: are fixed since the flip).
_KIND_BY_PATH: "dict[str, str | None]" = {}


def _module_name(target: Any) -> str:
    name = getattr(target, "name", None)
    if type(name) is str:
        return name
    md = _namespace(target)
    if md is not None:
        mod = md.get("$module")
        name = getattr(mod, "name", None)
        if type(name) is str:
            return name
        name = md.get("__name__")
        if type(name) is str:
            return name
    return repr(target)


def edge_error(kind: str, target: Any, context: str):
    """The LogicException refusing a Clausal Prolog -> *kind* edge."""
    from clausal.logic.exceptions import (  # noqa: PLC0415
        LogicException, permission_error)
    from clausal._suffixes import (  # noqa: PLC0415
        CLAUSAL_PROLOG_SUFFIXES, PROLOG_SUFFIX, SEAM_SUFFIX, suffix_list)
    name = _module_name(target)
    if kind == "prolog_module":
        cp = suffix_list(CLAUSAL_PROLOG_SUFFIXES) or "Clausal Prolog"
        why = (f"Clausal Prolog may not call ISO Prolog ({PROLOG_SUFFIX}), "
               f"which may use cut: {name} is a {PROLOG_SUFFIX} module; "
               f"convert it to {cp} (or write a {SEAM_SUFFIX} module)")
    else:
        why = (f"Clausal Prolog reaches Python only through a {SEAM_SUFFIX} "
               f"module: {name} is a Python module")
    return LogicException(permission_error(
        "access", kind, name, f"{context}: {why}"))


def refuse_edge(caller: Any, target: Any, context: str, *,
                python: bool = True) -> None:
    """Raise :func:`edge_error` when *caller* is Clausal Prolog and *target*
    is a ``.pl`` module (or, with *python*, a Python module); a no-op
    otherwise (and for a ``.seam`` or ``.pl`` caller after one cached
    attribute read)."""
    if not is_clausal_prolog_caller(caller):
        return
    kind = forbidden_kind(target)
    if kind is not None and (python or kind == "prolog_module"):
        raise edge_error(kind, target, context)
