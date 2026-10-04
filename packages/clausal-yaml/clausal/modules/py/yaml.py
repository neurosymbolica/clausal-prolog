"""clausal.modules.py.yaml — YAML predicates for Clausal.

Provides predicates for parsing and generating YAML, wrapping Python's
PyYAML library (``yaml.safe_load`` / ``yaml.safe_dump``).  Import via::

    -import_from(yaml, [read, write, read_all, write_all,
                        read_file, write_file, get])

Or via module import::

    -import_module(yaml)
    # then use yaml.read(...), yaml.get(...), etc.

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
    raise_os_error, raise_syntax_error, require_text,
)
_yaml = _import_stdlib("yaml")

from typing import Any

from clausal.logic.variables import Var, deref, is_var, unify
from clausal.logic.cells import chars_text, is_chars
from clausal.logic.to_python import to_python
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


# ── read ─────────────────────────────────────────────────────────────────


def _read_2(yaml_string, result, trail, k):
    """read/2: parse YAML string → Python object."""
    # The YAML is TEXT (a string or an atom): it was ``str()`` of the term,
    # so a string argument parsed as its Python repr.
    text = require_text(deref(yaml_string), "read/2", 1)
    try:
        data = _yaml.safe_load(text)
    except _yaml.YAMLError as exc:
        _raise_yaml_syntax(exc, "read/2")
    if unify(result, data, trail):
        yield None


# ── write ────────────────────────────────────────────────────────────────


def _write_2(data, result, trail, k):
    """write/2: serialize Python object → YAML string."""
    data = to_python(data)    # a string -> its str, a dict term -> a dict, at every depth
    try:
        out = _yaml.safe_dump(data, default_flow_style=False)
        out = out.rstrip("\n")
        if out.endswith("\n..."):
            out = out[:-4].rstrip("\n")
    except _yaml.YAMLError as exc:
        _raise_unrepresentable(exc, data, "write/2")
    if unify(result, out, trail):
        yield None


# ── read_all ──────────────────────────────────────────────────────────────


def _read_all_2(yaml_string, result, trail, k):
    """read_all/2: parse multi-document YAML string → list of objects."""
    text = require_text(deref(yaml_string), "read_all/2", 1)
    try:
        docs = list(_yaml.safe_load_all(text))
    except _yaml.YAMLError as exc:
        _raise_yaml_syntax(exc, "read_all/2")
    if unify(result, docs, trail):
        yield None


# ── write_all ─────────────────────────────────────────────────────────────


def _write_all_2(docs, result, trail, k):
    """write_all/2: serialize list of objects → multi-document YAML string."""
    docs = to_python(docs)
    try:
        out = _yaml.safe_dump_all(docs, default_flow_style=False).rstrip("\n")
    except _yaml.YAMLError as exc:
        _raise_unrepresentable(exc, docs, "write_all/2")
    if unify(result, out, trail):
        yield None


# ── read_file ─────────────────────────────────────────────────────────────


def _read_file_2(path, result, trail, k):
    """read_file/2: read and parse YAML from file path."""
    path = deref(path)
    # A path is text (an atom or a string): unbound -> instantiation_error,
    # anything else -> type_error(text, P), as py.json's read_file/2.
    name = require_text(path, "read_file/2", 1)
    try:
        with open(name, encoding="utf-8") as f:
            data = _yaml.safe_load(f)
    except OSError as exc:
        raise_os_error(exc, path, "read_file/2", arg=1, path=name)
    except UnicodeDecodeError as exc:
        # Bytes that are not UTF-8: Scryer's term for such a text stream.
        raise_syntax_error("invalid_data", "read_file/2",
                           f"the file is not UTF-8 text: {exc}", cause=exc)
    except _yaml.YAMLError as exc:
        _raise_yaml_syntax(exc, "read_file/2")
    if unify(result, data, trail):
        yield None


# ── write_file ────────────────────────────────────────────────────────────


def _write_file_2(path, data, trail, k):
    """write_file/2: write Python object as YAML to file path."""
    path = deref(path)
    data = to_python(data)
    name = require_text(path, "write_file/2", 1)
    # Serialised BEFORE the file is opened, as py.json's write_file/2 does:
    # a term YAML cannot represent raises and leaves no truncated file.
    try:
        text = _yaml.safe_dump(data, default_flow_style=False)
    except _yaml.YAMLError as exc:
        _raise_unrepresentable(exc, data, "write_file/2")
    try:
        with open(name, "w", encoding="utf-8") as f:
            f.write(text)
    except OSError as exc:
        raise_os_error(exc, path, "write_file/2", arg=1, path=name)
    yield None


# ── get ──────────────────────────────────────────────────────────────────


def _get_3(data, path, result, trail, k):
    """get/3: navigate nested structure by key/index path.

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
        if is_chars(key):
            # A string key written in source is the chars carrier; the
            # loaded mapping's keys are ``str``.  It never matched.
            key = chars_text(key)
        try:
            current = current[key]
        except (KeyError, IndexError, TypeError):
            return
    if unify(result, current, trail):
        yield None


# ── Build and export predicate objects ───────────────────────────────────

read = ModulePredicate("read")
read._register(2, simple_to_trampoline(_read_2))

write = ModulePredicate("write")
write._register(2, simple_to_trampoline(_write_2))

read_all = ModulePredicate("read_all")
read_all._register(2, simple_to_trampoline(_read_all_2))

write_all = ModulePredicate("write_all")
write_all._register(2, simple_to_trampoline(_write_all_2))

read_file = ModulePredicate("read_file")
read_file._register(2, simple_to_trampoline(_read_file_2))

write_file = ModulePredicate("write_file")
write_file._register(2, simple_to_trampoline(_write_file_2))

get = ModulePredicate("get")
get._register(3, simple_to_trampoline(_get_3))
