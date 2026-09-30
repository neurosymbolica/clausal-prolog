"""A seam ``-import_from`` of a DATA name from a ``.pl`` module.

Ruling (2026-09-30): ``-import_from(M, [name])`` against a ``.pl`` module
that neither defines ``name`` as a predicate (at any arity) nor binds it
resolves to the ATOM ``name``.  Data needs no declaration (D4), and a ``.pl``
export list holds only ``name/arity`` predicates, so there is nowhere in the
``.pl`` file an author could have "exported" the data name from.  An atom is
global by spelling, so the import binds the spelling itself.

A name that IS bound by M (an exported or defined predicate, a data atom the
file itself uses) takes the ordinary Python ``from M import name`` path,
unchanged; this module only sees the names that path could not find.  A
``.clausal``/``.seam`` target is never touched: it exports data explicitly
in its ``-module(...)`` list, and a name missing there stays an ImportError.

The directive lowers to::

    try:
        from M import a, b as c
    except ImportError as _cs_import_error:
        if not <this module>.bind_data_names(globals(), 'M', {...}, (...),
                                             _cs_import_error):
            raise

so a failure this module does not own re-raises the original error, which
``import_diagnostics.enrich_import_error`` then explains as before.
"""

from __future__ import annotations

import sys
import warnings

#: Edit-distance bound for the misspelled-predicate warning, by name length.
#: Names shorter than ``_TYPO_MIN_LEN`` are never warned about: short data
#: atoms (``a1``, ``p``) sit one edit from almost anything.
_TYPO_MIN_LEN = 4

#: ``(importer file, module, name)`` triples already warned about.
_warned: set[tuple[str, str, str]] = set()


def _is_pl_module(mod) -> bool:
    from clausal.import_hook import PrologLoader  # noqa: PLC0415

    spec = getattr(mod, "__spec__", None)
    return any(isinstance(loader, PrologLoader)
               for loader in (getattr(mod, "__loader__", None),
                              getattr(spec, "loader", None)))


def _predicate_names(mod) -> set[str]:
    """Every name *mod* defines or exports as a predicate, at any arity."""
    from clausal.import_diagnostics import (  # noqa: PLC0415
        _declared_exports, _defined_names, _module_items_of,
    )
    names = {bare for bare, _ in _defined_names(mod)}
    loader = getattr(mod, "__loader__", None)
    try:
        entries, _ = _declared_exports(_module_items_of(mod, loader))
    except Exception:  # pragma: no cover - source unreadable now
        entries = []
    names.update(bare for bare, _ in entries)
    return names


def _is_predicate_of(mod, name: str, predicates: set[str]) -> bool:
    db = getattr(vars(mod).get("$module"), "db", None)
    if db is not None:
        try:
            if db.is_predicate_name(name) or db.arities_for(name):
                return True
        except Exception:  # pragma: no cover - defensive
            pass
    return name in predicates


def _distance(a: str, b: str, cap: int) -> int:
    """Optimal-string-alignment edit distance (adjacent transposition counts
    as one edit), or ``cap + 1`` once it is known to exceed *cap*."""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev2 = None
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = a[i - 1] != b[j - 1]
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if (prev2 is not None and i > 1 and j > 1
                    and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]):
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        if min(cur) > cap:
            return cap + 1
        prev2, prev = prev, cur
    return prev[-1]


def near_predicates(name: str, predicates) -> list[str]:
    """The predicate names within a small edit distance of *name*: one edit
    for a name of 4-7 characters, two from 8 on."""
    if len(name) < _TYPO_MIN_LEN:
        return []
    cap = 1 if len(name) < 8 else 2
    return sorted(p for p in predicates
                  if p != name and _distance(name, p, cap) <= cap)


def _warn_if_misspelled(mod, name: str, importer_file: str,
                        predicates: set[str]) -> None:
    from clausal.lint_warnings import ClausalImportedDataNameWarning  # noqa: PLC0415

    key = (importer_file, mod.__name__, name)
    if key in _warned:
        return
    near = near_predicates(name, predicates)
    if not near:
        return
    _warned.add(key)
    shown = ", ".join(f"`{p}`" for p in near)
    label = mod.__name__.rsplit(".", 1)[-1]
    warnings.warn(
        f"-import_from({mod.__name__}, [{name}]): {label} defines no "
        f"predicate `{name}`, so `{name}` is imported as the ATOM {name} "
        f"(data needs no declaration). {label} does define the predicate "
        f"{shown}: if that is what you meant, fix the spelling.",
        ClausalImportedDataNameWarning,
        stacklevel=3,
    )


def data_atom(mod, name: str):
    """The atom *name* when a bare ``-import_from`` of *name*, which *mod*
    does not bind, resolves to data under the ruling; else ``None``."""
    if not _is_pl_module(mod):
        return None
    if getattr(getattr(mod, "__spec__", None), "_initializing", False):
        return None
    if _is_predicate_of(mod, name, _predicate_names(mod)):
        return None
    return sys.intern(name)


def bind_data_names(namespace: dict, module_name: str, pairs: dict,
                    eligible, error: ImportError) -> bool:
    """Finish a failed ``from module_name import ...`` for a ``.pl`` target.

    *pairs* maps each LOCAL name to the original spelling; *eligible* holds
    the local names imported bare (``name``, ``alias(name, local)``) -- a
    ``name/N`` indicator names a predicate and never resolves to data.

    Returns ``False`` when *error* is not this module's to handle (the target
    is not a loaded ``.pl`` module, or is still initialising): the caller
    re-raises it.  Raises a fresh ``ImportError`` shaped like CPython's own
    for the first missing name that may not become data.  Otherwise binds
    every name into *namespace* and returns ``True``.
    """
    mod = sys.modules.get(module_name)
    if mod is None or not _is_pl_module(mod):
        return False
    if getattr(getattr(mod, "__spec__", None), "_initializing", False):
        return False   # a circular import: the name may simply not be bound YET
    missing = object()
    predicates = None
    resolved = {}
    for local, orig in pairs.items():
        value = getattr(mod, orig, missing)
        if value is missing:
            if predicates is None:
                predicates = _predicate_names(mod)
            if local not in eligible or _is_predicate_of(mod, orig,
                                                         predicates):
                path = getattr(mod, "__file__", None)
                new = ImportError(
                    f"cannot import name {orig!r} from {mod.__name__!r} "
                    f"({path or 'unknown location'})",
                    name=getattr(error, "name", None) or mod.__name__,
                    path=path)
                new.name_from = orig
                raise new
            value = sys.intern(orig)
            _warn_if_misspelled(mod, orig,
                                namespace.get("__file__") or "<unknown>",
                                predicates)
        resolved[local] = value
    namespace.update(resolved)
    return True
