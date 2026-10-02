"""clausal.modules.py.yaml — YAML predicates for Clausal.

Provides predicates for parsing and generating YAML, wrapping Python's
PyYAML library (``yaml.safe_load`` / ``yaml.safe_dump``).  Import via::

    -import_from(yaml, [Read, write, ReadAll, WriteAll,
                        ReadFile, WriteFile, Get])

Or via module import::

    -import_module(yaml)
    # then use yaml.Read(...), yaml.Get(...), etc.

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

from clausal.modules.py import (
    _import_stdlib, ModulePredicate, simple_to_trampoline,
    raise_os_error, raise_syntax_error, to_text,
)
_yaml = _import_stdlib("yaml")

from typing import Any

from clausal.logic.variables import Var, deref, is_var, unify
from clausal.logic.exceptions import LogicException, type_error


# ── Errors (RULED 2026-10-02: raise, never fail) ─────────────────────────
#
# - a file-system failure -> the shared ISO mapping (``raise_os_error``),
#   exactly as ``py.files``: a missing file is
#   ``existence_error(source_sink, Path)``, no permission
#   ``permission_error(open, source_sink, Path)``, ...;
# - text that is not YAML -> ``syntax_error(invalid_yaml)``, the family
#   ``py.http`` raises for a body that is not JSON (``invalid_json``);
# - a term YAML cannot represent -> ``type_error(yaml_term, Culprit)``, as
#   ``py.json``'s converter raises ``type_error(json_term, Culprit)``.


def _path_text(path):
    """The file name *path* denotes: its text, or ``str`` of anything else
    (the old behaviour, kept for a non-text path)."""
    text = to_text(path)
    return text if text is not None else str(path)


def _raise_yaml_syntax(exc, pred):
    raise_syntax_error("invalid_yaml", pred,
                       f"the text is not YAML: {exc}", cause=exc)


def _raise_unrepresentable(exc, data, pred):
    """``type_error(yaml_term, Culprit)``: PyYAML's RepresenterError
    carries the object it could not represent; any other dump error names
    the whole term."""
    args = getattr(exc, "args", ())
    culprit = args[1] if len(args) > 1 else data
    raise LogicException(type_error(
        "yaml_term", culprit, f"{pred}: {exc}")) from exc


# ── Read ─────────────────────────────────────────────────────────────────


def _read_2(yaml_string, result, trail, k):
    """Read/2: parse YAML string → Python object."""
    yaml_string = deref(yaml_string)
    try:
        data = _yaml.safe_load(str(yaml_string))
    except _yaml.YAMLError as exc:
        _raise_yaml_syntax(exc, "Read/2")
    if unify(result, data, trail):
        yield None


# ── write ────────────────────────────────────────────────────────────────


def _write_2(data, result, trail, k):
    """write/2: serialize Python object → YAML string."""
    data = deref(data)
    try:
        out = _yaml.safe_dump(data, default_flow_style=False)
        out = out.rstrip("\n")
        if out.endswith("\n..."):
            out = out[:-4].rstrip("\n")
    except _yaml.YAMLError as exc:
        _raise_unrepresentable(exc, data, "write/2")
    if unify(result, out, trail):
        yield None


# ── ReadAll ──────────────────────────────────────────────────────────────


def _read_all_2(yaml_string, result, trail, k):
    """ReadAll/2: parse multi-document YAML string → list of objects."""
    yaml_string = deref(yaml_string)
    try:
        docs = list(_yaml.safe_load_all(str(yaml_string)))
    except _yaml.YAMLError as exc:
        _raise_yaml_syntax(exc, "ReadAll/2")
    if unify(result, docs, trail):
        yield None


# ── WriteAll ─────────────────────────────────────────────────────────────


def _write_all_2(docs, result, trail, k):
    """WriteAll/2: serialize list of objects → multi-document YAML string."""
    docs = deref(docs)
    try:
        out = _yaml.safe_dump_all(docs, default_flow_style=False).rstrip("\n")
    except _yaml.YAMLError as exc:
        _raise_unrepresentable(exc, docs, "WriteAll/2")
    if unify(result, out, trail):
        yield None


# ── ReadFile ─────────────────────────────────────────────────────────────


def _read_file_2(path, result, trail, k):
    """ReadFile/2: read and parse YAML from file path."""
    path = deref(path)
    name = _path_text(path)
    try:
        with open(name) as f:
            data = _yaml.safe_load(f)
    except OSError as exc:
        raise_os_error(exc, path, "ReadFile/2", arg=1, path=name)
    except _yaml.YAMLError as exc:
        _raise_yaml_syntax(exc, "ReadFile/2")
    if unify(result, data, trail):
        yield None


# ── WriteFile ────────────────────────────────────────────────────────────


def _write_file_2(path, data, trail, k):
    """WriteFile/2: write Python object as YAML to file path."""
    path = deref(path)
    data = deref(data)
    name = _path_text(path)
    # Serialised BEFORE the file is opened, as py.json's write_file/2 does:
    # a term YAML cannot represent raises and leaves no truncated file.
    try:
        text = _yaml.safe_dump(data, default_flow_style=False)
    except _yaml.YAMLError as exc:
        _raise_unrepresentable(exc, data, "WriteFile/2")
    try:
        with open(name, "w") as f:
            f.write(text)
    except OSError as exc:
        raise_os_error(exc, path, "WriteFile/2", arg=1, path=name)
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

Read = ModulePredicate("Read")
Read._register(2, simple_to_trampoline(_read_2))

write = ModulePredicate("write")
write._register(2, simple_to_trampoline(_write_2))

ReadAll = ModulePredicate("ReadAll")
ReadAll._register(2, simple_to_trampoline(_read_all_2))

WriteAll = ModulePredicate("WriteAll")
WriteAll._register(2, simple_to_trampoline(_write_all_2))

ReadFile = ModulePredicate("ReadFile")
ReadFile._register(2, simple_to_trampoline(_read_file_2))

WriteFile = ModulePredicate("WriteFile")
WriteFile._register(2, simple_to_trampoline(_write_file_2))

Get = ModulePredicate("Get")
Get._register(3, simple_to_trampoline(_get_3))
