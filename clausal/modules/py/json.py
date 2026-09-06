"""clausal.modules.py.json — JSON predicates for Clausal.

Provides relational predicates for parsing, generating, and querying
JSON data.  Import via::

    -import_from(py.json, [parse, generate, get, read_file, write_file])

Or via module import::

    -import_module(py.json)
    # then use py.json.parse(S_, T_), py.json.get(T_, "key", V_), etc.

Type mapping (spec 2026-09-06-atoms-as-cells-strings §9.2)
---------------------------------------------------------
- JSON objects  → ``DictTerm``  (unification-aware), KEYS minted as atoms
- JSON arrays   → Python ``list``
- JSON strings  → **strings** (a value is minted as an atom only when its
  text is listed in ``parse/3``'s ``atoms(Spellings)`` option)
- JSON numbers  → Python ``int`` / ``float``
- JSON booleans → Python ``True`` / ``False``
- JSON null     → Python ``None``

The conversion is recursive: nested objects produce nested DictTerms, and
the ``atoms`` vocabulary reaches every nested string value.

Generating is the mirror: an atom becomes a JSON string (its spelling), a
string becomes a JSON string, and a compound cell — which has no JSON
counterpart — raises ``error(type_error(json_term, Cell), _)`` rather than
a stdlib ``TypeError`` that the wrapper would swallow into a silent failure.
"""

from __future__ import annotations

from clausal.modules.py import (
    ModulePredicate,
    _import_stdlib,
    expect_type,
    note_rejected_call,
    simple_to_trampoline,
    value_is_ground,
)
_json = _import_stdlib("json")

from typing import Any

from clausal.logic.atoms import is_atom, mint, spelling
from clausal.logic.exceptions import LogicException, domain_error, type_error
from clausal.logic.variables import Var, deref, is_var, unify
from clausal.modules.py._helpers import to_python
from clausal.terms import Compound, DictTerm


# ── Converters ──────────────────────────────────────────────────────────


def _python_to_clausal(obj: Any, atoms: frozenset = frozenset()) -> Any:
    """Convert a Python object from json.loads() into Clausal terms.

    dicts become DictTerm with ATOM keys (spec §9.2: "object keys → atoms");
    lists recurse; scalars and None pass through.

    *atoms* is ``parse/3``'s vocabulary hook: a JSON string value whose text
    is in the set is minted as an atom instead of staying a string.  The
    default empty set is exactly ``parse/2`` — every string value stays a
    string.
    """
    if isinstance(obj, dict):
        return DictTerm({
            mint(k): _python_to_clausal(v, atoms) for k, v in obj.items()
        })
    if isinstance(obj, list):
        return [_python_to_clausal(item, atoms) for item in obj]
    if type(obj) is str:
        return mint(obj) if obj in atoms else obj
    # int, float, bool, None — pass through
    return obj


def _clausal_to_python(term: Any) -> Any:
    """Convert a Clausal term into a plain Python object for json.dumps().

    An atom becomes its spelling (a ``str``, so it serialises as a JSON
    string); DictTerm → dict with converted keys; lists recurse; Vars raise
    TypeError (a mode situation the wrapper turns into a silent failure).

    A compound cell has no JSON counterpart, so it raises a catchable
    ``error(type_error(json_term, Cell), _)`` (spec §9.2) rather than the
    stdlib ``TypeError`` the wrapper would swallow — a tuple used to
    serialise as a JSON array by accident of ``json.dumps``'s tuple support,
    which silently conflated ``point(1, 2)`` with ``[1, 2]``.
    """
    term = deref(term)
    if is_var(term):
        raise TypeError("Cannot serialize unbound variable to JSON")
    if is_atom(term):
        return spelling(term)
    if isinstance(term, DictTerm):
        return {
            to_python(k): _clausal_to_python(deref(v))
            for k, v in term.data.items()
        }
    if isinstance(term, list):
        return [_clausal_to_python(deref(item)) for item in term]
    if type(term) is tuple:
        raise LogicException(
            type_error("json_term", term, "py.json.generate/2")
        )
    # int, float, bool, None — pass through
    return term


# ── parse/3 options ─────────────────────────────────────────────────────


def _parse_options(options: Any) -> frozenset:
    """Read ``parse/3``'s option list into the ``atoms`` vocabulary set.

    The whole vocabulary is ``atoms(Spellings)`` (spec §9.2) — *Spellings* is
    a list of the texts that are to come back as atoms rather than strings.
    Anything else in the list is ``error(domain_error(json_option, Opt), _)``.
    """
    options = deref(options)
    if not isinstance(options, list):
        raise LogicException(
            domain_error("json_option", options, "py.json.parse/3")
        )
    atoms: set = set()
    for opt in options:
        opt = deref(opt)
        name, args = _option_shape(opt)
        if name != "atoms" or len(args) != 1:
            raise LogicException(
                domain_error("json_option", opt, "py.json.parse/3")
            )
        spellings = deref(args[0])
        if not isinstance(spellings, list):
            raise LogicException(
                domain_error("json_option", opt, "py.json.parse/3")
            )
        for s in spellings:
            s = deref(s)
            if not is_atom(s):
                raise LogicException(
                    domain_error("json_option", opt, "py.json.parse/3")
                )
            atoms.add(spelling(s))
    return frozenset(atoms)


def _option_shape(opt: Any) -> tuple:
    """``(functor, args)`` for a one-option term, or ``(None, ())``.

    Deliberately narrow — an option is a compound, written either as a cell
    ``("atoms", [...])`` (the compiled representation) or as a ``Compound``
    (what a hand-built term or an older caller passes).  Everything else,
    including a bare atom, falls through to the caller's domain_error.
    """
    if type(opt) is tuple and opt and type(opt[0]) is str:
        return opt[0], opt[1:]
    if isinstance(opt, Compound):
        return opt.functor, tuple(opt.args)
    return None, ()


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


def _parse_3(string, term, options, trail, k):
    """parse/3: parse JSON, minting the string values named by ``atoms/1``.

    ``parse(S, T, [atoms(["red", "blue"])])`` is ``parse/2`` except that a
    string value whose text is ``"red"`` or ``"blue"`` comes back as the
    corresponding ATOM.  That is the whole vocabulary hook of spec §9.2 —
    "atoms by vocabulary" loaders are built on it rather than in here.
    """
    string = deref(string)
    if not expect_type(string, str, "parse/3", arg=1):
        return
    atoms = _parse_options(options)
    try:
        obj = _json.loads(string)
    except (ValueError, TypeError) as exc:
        note_rejected_call("parse/3", exc)
        return
    result = _python_to_clausal(obj, atoms)
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
        if value_is_ground(term):
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
        if value_is_ground(term):
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
        if value_is_ground(term):
            note_rejected_call("write_file/2", exc)
        return
    except OSError:
        return
    yield None


# ── Build and export predicate objects ──────────────────────────────────

parse = ModulePredicate("parse")
parse._register(2, simple_to_trampoline(_parse_2))
parse._register(3, simple_to_trampoline(_parse_3))

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
