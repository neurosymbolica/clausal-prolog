"""clausal.modules.py.json — JSON predicates for Clausal.

Provides relational predicates for parsing, generating, and querying
JSON data.  Import via::

    -import_from(py.json, [Parse, Generate, Get, ReadFile, WriteFile])

Or via module import::

    -import_module(py.json)
    # then use py.json.Parse(S_, T_), py.json.Get(T_, "key", V_), etc.

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

from clausal.modules.py import _import_stdlib, ModulePredicate, simple_to_trampoline
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
    """Parse/2: parse JSON string into Clausal terms."""
    string = deref(string)
    if is_var(string) or not isinstance(string, str):
        return
    try:
        obj = _json.loads(string)
    except (ValueError, TypeError):
        return
    result = _python_to_clausal(obj)
    if unify(term, result, trail):
        yield None


def _generate_2(term, string, trail, k):
    """Generate/2: serialize Clausal term to JSON string."""
    term = deref(term)
    if is_var(term):
        return
    try:
        obj = _clausal_to_python(term)
        result = _json.dumps(obj, ensure_ascii=False)
    except (TypeError, ValueError):
        return
    if unify(string, result, trail):
        yield None


def _pretty_generate_2(term, string, trail, k):
    """PrettyGenerate/2: serialize Clausal term to indented JSON string."""
    term = deref(term)
    if is_var(term):
        return
    try:
        obj = _clausal_to_python(term)
        result = _json.dumps(obj, indent=2, ensure_ascii=False)
    except (TypeError, ValueError):
        return
    if unify(string, result, trail):
        yield None


def _get_3(term, key, value, trail, k):
    """Get/3: extract a value from a DictTerm by key.

    If Key is bound: look up and unify Value.
    If Key is unbound: enumerate all key-value pairs.
    """
    term = deref(term)
    if not isinstance(term, DictTerm):
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
    """ReadFile/2: read and parse a JSON file."""
    path = deref(path)
    if is_var(path) or not isinstance(path, str):
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
    """WriteFile/2: serialize and write a JSON file."""
    path, term = deref(path), deref(term)
    if is_var(path) or not isinstance(path, str):
        return
    if is_var(term):
        return
    try:
        obj = _clausal_to_python(term)
        with open(path, "w", encoding="utf-8") as f:
            _json.dump(obj, f, ensure_ascii=False, indent=2)
    except (TypeError, ValueError, OSError):
        return
    yield None


# ── Build and export predicate objects ──────────────────────────────────

Parse = ModulePredicate("Parse")
Parse._register(2, simple_to_trampoline(_parse_2))

Generate = ModulePredicate("Generate")
Generate._register(2, simple_to_trampoline(_generate_2))

PrettyGenerate = ModulePredicate("PrettyGenerate")
PrettyGenerate._register(2, simple_to_trampoline(_pretty_generate_2))

Get = ModulePredicate("Get")
Get._register(3, simple_to_trampoline(_get_3))

ReadFile = ModulePredicate("ReadFile")
ReadFile._register(2, simple_to_trampoline(_read_file_2))

WriteFile = ModulePredicate("WriteFile")
WriteFile._register(2, simple_to_trampoline(_write_file_2))
