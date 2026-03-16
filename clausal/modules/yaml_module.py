"""clausal.modules.yaml_module — YAML predicates for Clausal.

Provides predicates for parsing and generating YAML, wrapping Python's
PyYAML library (``yaml.safe_load`` / ``yaml.safe_dump``).  Import via::

    -import_from(yaml_module, [Read, Write, ReadAll, WriteAll,
                                ReadFile, WriteFile, Get])

Or via module import::

    -import_module(yaml_module)
    # then use yaml_module.Read(...), yaml_module.Get(...), etc.

Data representation
-------------------
YAML data is represented as **native Python objects**:

- Mappings  → ``dict``
- Sequences → ``list``
- Strings   → ``str``
- Numbers   → ``int`` / ``float``
- Booleans  → ``True`` / ``False``
- Null      → ``None``

These are the objects returned by ``yaml.safe_load``.  Any Python method
can be called on them via ``++()`` interop.

Security
--------
Only ``yaml.safe_load`` is used — no arbitrary Python object
construction from YAML tags.
"""

from __future__ import annotations

import yaml as _yaml
from typing import Any, Callable

from clausal.logic.variables import Var, deref, is_var, unify
from clausal.logic.trampoline import DONE


# ── Dispatch adapter (same pattern as regex.py) ───────────────────────────


class _YamlPredicate:
    """Adapter with ``_get_dispatch()`` for a yaml_module predicate."""

    __slots__ = ("_name", "_dispatch_fns")

    def __init__(self, name: str) -> None:
        self._name = name
        self._dispatch_fns: dict[int, Callable] = {}

    def _register(self, arity: int, fn: Callable) -> None:
        self._dispatch_fns[arity] = fn

    def _get_dispatch(self) -> Callable:
        if len(self._dispatch_fns) == 1:
            return next(iter(self._dispatch_fns.values()))
        return self._multi_dispatch

    def _multi_dispatch(self, this_generator, parent, *args):
        arity = len(args) - 1  # exclude trail
        fn = self._dispatch_fns.get(arity)
        if fn is None:
            yield (parent, DONE)
            return
        yield from fn(this_generator, parent, *args)

    def __repr__(self) -> str:
        arities = sorted(self._dispatch_fns)
        return f"yaml_module.{self._name}/{arities}"


# ── Simple-mode wrapper ──────────────────────────────────────────────────


def _simple_to_trampoline(simple_fn):
    """Wrap a simple-mode fn(*args, trail, k) → trampoline protocol."""
    def trampoline_fn(this_generator, parent, *args):
        for _ in simple_fn(*args, None):
            yield (parent, None)
        yield (parent, DONE)
    return trampoline_fn


# ── Read ─────────────────────────────────────────────────────────────────


def _read_2(yaml_string, result, trail, k):
    """Read/2: parse YAML string → Python object."""
    yaml_string = deref(yaml_string)
    try:
        data = _yaml.safe_load(str(yaml_string))
    except _yaml.YAMLError:
        return
    if unify(result, data, trail):
        yield None


# ── Write ────────────────────────────────────────────────────────────────


def _write_2(data, result, trail, k):
    """Write/2: serialize Python object → YAML string."""
    data = deref(data)
    try:
        out = _yaml.safe_dump(data, default_flow_style=False)
        out = out.rstrip("\n")
        if out.endswith("\n..."):
            out = out[:-4].rstrip("\n")
    except _yaml.YAMLError:
        return
    if unify(result, out, trail):
        yield None


# ── ReadAll ──────────────────────────────────────────────────────────────


def _read_all_2(yaml_string, result, trail, k):
    """ReadAll/2: parse multi-document YAML string → list of objects."""
    yaml_string = deref(yaml_string)
    try:
        docs = list(_yaml.safe_load_all(str(yaml_string)))
    except _yaml.YAMLError:
        return
    if unify(result, docs, trail):
        yield None


# ── WriteAll ─────────────────────────────────────────────────────────────


def _write_all_2(docs, result, trail, k):
    """WriteAll/2: serialize list of objects → multi-document YAML string."""
    docs = deref(docs)
    try:
        out = _yaml.safe_dump_all(docs, default_flow_style=False).rstrip("\n")
    except _yaml.YAMLError:
        return
    if unify(result, out, trail):
        yield None


# ── ReadFile ─────────────────────────────────────────────────────────────


def _read_file_2(path, result, trail, k):
    """ReadFile/2: read and parse YAML from file path."""
    path = deref(path)
    try:
        with open(str(path)) as f:
            data = _yaml.safe_load(f)
    except (OSError, _yaml.YAMLError):
        return
    if unify(result, data, trail):
        yield None


# ── WriteFile ────────────────────────────────────────────────────────────


def _write_file_2(path, data, trail, k):
    """WriteFile/2: write Python object as YAML to file path."""
    path = deref(path)
    data = deref(data)
    try:
        with open(str(path), "w") as f:
            _yaml.safe_dump(data, f, default_flow_style=False)
    except (OSError, _yaml.YAMLError):
        return
    yield None


# ── Get ──────────────────────────────────────────────────────────────────


def _get_3(data, path, result, trail, k):
    """Get/3: navigate nested structure by key/index path.

    Path can be a single key (string or int) or a list of keys for
    nested access.  Fails if any key is missing or index is out of range.
    """
    data = deref(data)
    path = deref(path)
    # Normalize path: single key → [key]
    if not isinstance(path, list):
        path = [path]
    current = data
    for key in path:
        key = deref(key)
        try:
            current = current[key]
        except (KeyError, IndexError, TypeError):
            return
    if unify(result, current, trail):
        yield None


# ── Build and export predicate objects ───────────────────────────────────

Read = _YamlPredicate("Read")
Read._register(2, _simple_to_trampoline(_read_2))

Write = _YamlPredicate("Write")
Write._register(2, _simple_to_trampoline(_write_2))

ReadAll = _YamlPredicate("ReadAll")
ReadAll._register(2, _simple_to_trampoline(_read_all_2))

WriteAll = _YamlPredicate("WriteAll")
WriteAll._register(2, _simple_to_trampoline(_write_all_2))

ReadFile = _YamlPredicate("ReadFile")
ReadFile._register(2, _simple_to_trampoline(_read_file_2))

WriteFile = _YamlPredicate("WriteFile")
WriteFile._register(2, _simple_to_trampoline(_write_file_2))

Get = _YamlPredicate("Get")
Get._register(3, _simple_to_trampoline(_get_3))
