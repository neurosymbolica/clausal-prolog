"""clausal.modules.py.json — JSON predicates for Clausal.

Provides relational predicates for parsing, generating, and querying
JSON data.  Import via::

    -import_from(py.json, [parse, generate, get, read_file, write_file])

Or via module import::

    -import_module(py.json)
    # then use py.json.parse(S_, T_), py.json.get(T_, "key", V_), etc.

Type mapping
------------
- JSON objects  → ``DictTerm``  (unification-aware)
- JSON arrays   → Python ``list``
- JSON strings  → Python ``str``
- JSON numbers  → Python ``int`` / ``float``
- JSON booleans → Python ``True`` / ``False``
- JSON null     → Python ``None``

The conversion is recursive: nested objects produce nested DictTerms.
"""

from __future__ import annotations

from clausal.modules.py import (
    ModulePredicate,
    _import_stdlib,
    expect_type,
    note_rejected_call,
    simple_to_trampoline,
)
_json = _import_stdlib("json")

from typing import Any

from clausal.logic.variables import Var, deref, is_var, unify
from clausal.terms import DictTerm


# ── Converters ──────────────────────────────────────────────────────────


def _python_to_clausal(obj: Any) -> Any:
    """Convert a Python object from json.loads() into Clausal terms.

    dicts become DictTerm; lists, scalars, None pass through.
    """
    if isinstance(obj, dict):
        return DictTerm({k: _python_to_clausal(v) for k, v in obj.items()})
    if isinstance(obj, list):
        return [_python_to_clausal(item) for item in obj]
    # str, int, float, bool, None — pass through
    return obj


def _clausal_to_python(term: Any) -> Any:
    """Convert a Clausal term into a plain Python object for json.dumps().

    DictTerm → dict; lists recurse; Vars raise TypeError.
    """
    term = deref(term)
    if is_var(term):
        raise TypeError("Cannot serialize unbound variable to JSON")
    if isinstance(term, DictTerm):
        return {k: _clausal_to_python(deref(v)) for k, v in term.data.items()}
    if isinstance(term, list):
        return [_clausal_to_python(deref(item)) for item in term]
    # str, int, float, bool, None — pass through
    return term


# ── Predicates ──────────────────────────────────────────────────────────


def _parse_2(string, term, trail, k):
    """parse/2: parse JSON string into Clausal terms."""
    string = deref(string)
    if not expect_type(string, str, "parse/2", arg=1):
        return
    try:
        obj = _json.loads(string)
    except (ValueError, TypeError) as exc:
        note_rejected_call("parse/2", exc)
        return
    result = _python_to_clausal(obj)
    if unify(term, result, trail):
        yield None


def _generate_2(term, string, trail, k):
    """generate/2: serialize Clausal term to JSON string."""
    term = deref(term)
    if is_var(term):
        return
    try:
        obj = _clausal_to_python(term)
        result = _json.dumps(obj, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        note_rejected_call("generate/2", exc)
        return
    if unify(string, result, trail):
        yield None


def _pretty_generate_2(term, string, trail, k):
    """pretty_generate/2: serialize Clausal term to indented JSON string."""
    term = deref(term)
    if is_var(term):
        return
    try:
        obj = _clausal_to_python(term)
        result = _json.dumps(obj, indent=2, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        note_rejected_call("pretty_generate/2", exc)
        return
    if unify(string, result, trail):
        yield None


def _get_3(term, key, value, trail, k):
    """get/3: extract a value from a DictTerm by key.

    If Key is bound: look up and unify Value.
    If Key is unbound: enumerate all key-value pairs.
    """
    term = deref(term)
    if not expect_type(term, DictTerm, "get/3", arg=1):
        return
    key = deref(key)
    if is_var(key):
        # Enumerate all key-value pairs
        for dict_key, dict_value in term.data.items():
            mark = trail.mark()
            if unify(key, dict_key, trail) and unify(value, dict_value, trail):
                yield None
            trail.undo(mark)
    else:
        # Direct lookup
        if key not in term.data:
            return
        if unify(value, term.data[key], trail):
            yield None


def _read_file_2(path, term, trail, k):
    """read_file/2: read and parse a JSON file."""
    path = deref(path)
    if not expect_type(path, str, "read_file/2", arg=1):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = _json.load(f)
    except (OSError, ValueError, TypeError):
        return
    result = _python_to_clausal(obj)
    if unify(term, result, trail):
        yield None


def _write_file_2(path, term, trail, k):
    """write_file/2: serialize and write a JSON file."""
    path, term = deref(path), deref(term)
    if not expect_type(path, str, "write_file/2", arg=1):
        return
    if is_var(term):
        return
    try:
        obj = _clausal_to_python(term)
        with open(path, "w", encoding="utf-8") as f:
            _json.dump(obj, f, ensure_ascii=False, indent=2)
    except (TypeError, ValueError) as exc:
        note_rejected_call("write_file/2", exc)
        return
    except OSError:
        return
    yield None


# ── Build and export predicate objects ──────────────────────────────────

parse = ModulePredicate("parse")
parse._register(2, simple_to_trampoline(_parse_2))

generate = ModulePredicate("generate")
generate._register(2, simple_to_trampoline(_generate_2))

pretty_generate = ModulePredicate("pretty_generate")
pretty_generate._register(2, simple_to_trampoline(_pretty_generate_2))

get = ModulePredicate("get")
get._register(3, simple_to_trampoline(_get_3))

read_file = ModulePredicate("read_file")
read_file._register(2, simple_to_trampoline(_read_file_2))

write_file = ModulePredicate("write_file")
write_file._register(2, simple_to_trampoline(_write_file_2))
