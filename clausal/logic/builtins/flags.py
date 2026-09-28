"""Prolog flags: set_prolog_flag/2 and current_prolog_flag/2 (ISO 7.11,
8.17).

The ISO flags, plus one implementation-defined flag:

=========================  ============  ==========  =================
flag                       value         settable    scope
=========================  ============  ==========  =================
bounded                    false         no          process
max_integer                (none)        no          process
min_integer                (none)        no          process
integer_rounding_function  toward_zero   no          process
char_conversion            off           off only    process
debug                      off           yes         process
max_arity                  unbounded     no          process
unknown                    error         error only  process
double_quotes              chars         directive   module
assert_creates_dynamic     false         yes         module
=========================  ============  ==========  =================

Integers are unbounded, so ``bounded`` is ``false`` and ``max_integer`` /
``min_integer`` have no value: ``current_prolog_flag(max_integer, X)``
fails, as in Scryer.  ``integer_rounding_function`` is ``toward_zero`` --
the quoted ISO ``'//'`` truncates (a bare ``//`` in source is Python's
floor, which is not the ISO evaluable).  Cells are Python tuples and have no
arity limit, so ``max_arity`` is ``unbounded``.

A MODULE-scoped flag lives on the module's :class:`Database`
(``db.prolog_flags``): ``set_prolog_flag/2`` run as a goal sets it for the
CALLING module, ``current_prolog_flag/2`` reads the calling module's value,
and the directive ``-set_prolog_flag(F, V)`` sets it for the module that
carries the directive.  ``double_quotes`` decides how the compiler reads
``"..."`` literals, so it can only be set by the directive (which is the
same as ``-double_quotes(V)``); run as a goal it is refused.

Errors follow ISO 8.17.1.3 / 8.17.2.3, with ``set_prolog_flag/2`` /
``current_prolog_flag/2`` as the context:

* an unbound flag or value: ``instantiation_error``;
* a flag that is not an atom: ``type_error(atom, F)``;
* an atom that is not a flag: ``domain_error(prolog_flag, F)``;
* a value ISO does not admit for the flag: ``domain_error(flag_value, F+V)``;
* an admissible value the flag cannot take here -- a read-only flag, or an
  ISO value this engine does not implement (``unknown`` = ``fail``,
  ``char_conversion`` = ``on``, ``double_quotes`` = ``codes``):
  ``permission_error(modify, flag, F)``.

Scryer differs on the last two: it reports a read-only flag and a bad
``unknown`` value as ``domain_error(prolog_flag, F)``, and it implements
neither ``char_conversion`` nor ``debug``.  Here ISO decides.
"""

from __future__ import annotations

from typing import Any

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.exceptions import (
    LogicException, domain_error, instantiation_error, permission_error,
    type_error,
)
from clausal.logic.builtins._registry import _db_builtin

_SET = "set_prolog_flag/2"
_CURRENT = "current_prolog_flag/2"

#: No value at all (max_integer / min_integer with unbounded integers).
_NO_VALUE = object()


def _is_bool_flag_value(v) -> bool:
    return v in ("true", "false")


def _is_int(v) -> bool:
    return type(v) is int


class _Flag:
    __slots__ = ("name", "default", "admits", "supported", "scope")

    def __init__(self, name, default, admits, supported=(), scope="process"):
        self.name = name
        self.default = default
        self.admits = admits            # value -> bool: ISO's value set
        self.supported = supported      # the values it can be SET to here
        self.scope = scope              # "process" | "module" | "directive"


#: The flags, in the order current_prolog_flag/2 enumerates them.
FLAGS: dict[str, _Flag] = {f.name: f for f in (
    _Flag("bounded", "false", _is_bool_flag_value),
    _Flag("max_integer", _NO_VALUE, _is_int),
    _Flag("min_integer", _NO_VALUE, _is_int),
    _Flag("integer_rounding_function", "toward_zero",
          lambda v: v in ("toward_zero", "down")),
    _Flag("char_conversion", "off", lambda v: v in ("on", "off"),
          supported=("off",)),
    _Flag("debug", "off", lambda v: v in ("on", "off"),
          supported=("on", "off")),
    _Flag("max_arity", "unbounded",
          lambda v: v == "unbounded" or (_is_int(v) and v > 0)),
    _Flag("unknown", "error", lambda v: v in ("error", "fail", "warning"),
          supported=("error",)),
    _Flag("double_quotes", "chars",
          lambda v: v in ("chars", "codes", "atom"),
          supported=("chars", "atom"), scope="directive"),
    _Flag("assert_creates_dynamic", "false", _is_bool_flag_value,
          supported=("true", "false"), scope="module"),
)}

#: Process-wide values of the settable process flags.
_PROCESS: dict[str, Any] = {}

#: Flags whose value is a truth value: reported as the Python bool, which is
#: what ``true`` / ``false`` written in source compile to.
_BOOL_FLAGS = frozenset({"bounded", "assert_creates_dynamic"})


def _normal(v):
    """A flag or value as the flag table spells it: an atom is its str, a
    truth value is ``'true'`` / ``'false'``."""
    if v is True:
        return "true"
    if v is False:
        return "false"
    return v


def _reported(name: str, v):
    if name in _BOOL_FLAGS and v in ("true", "false"):
        return v == "true"
    return v


def _flag_named(flag, context: str) -> _Flag:
    """The flag *flag* names, or the ISO error (8.17.1.3 c/d, 8.17.2.3)."""
    name = _normal(flag)
    if type(name) is not str:
        raise LogicException(type_error("atom", flag, context))
    spec = FLAGS.get(name)
    if spec is None:
        raise LogicException(domain_error(
            "prolog_flag", flag,
            f"{context}: {name} is not a Prolog flag (the flags are "
            f"{', '.join(FLAGS)})"))
    return spec


def check_setting(flag, value, *, directive: bool = False) -> tuple[str, Any]:
    """Validate ``set_prolog_flag(Flag, Value)`` in ISO 8.17.1.3's order and
    return the normalized ``(name, value)``.  *directive* is True for the
    load-time ``-set_prolog_flag`` directive, where ``double_quotes`` may be
    set."""
    flag, value = deref(flag), deref(value)
    if is_var(flag) or is_var(value):
        raise LogicException(instantiation_error(_SET))
    spec = _flag_named(flag, _SET)
    v = _normal(value)
    if not spec.admits(v):
        raise LogicException(domain_error(
            "flag_value", ("+", spec.name, value),
            f"{_SET}: {v!r} is not a value of the {spec.name} flag"))
    if v not in spec.supported:
        why = ("is read-only" if not spec.supported else
               f"can only be {' or '.join(spec.supported)} here")
        raise LogicException(permission_error(
            "modify", "flag", spec.name,
            f"{_SET}: the {spec.name} flag {why}"))
    if spec.scope == "directive" and not directive:
        raise LogicException(permission_error(
            "modify", "flag", spec.name,
            f"{_SET}: {spec.name} decides how a module's source is read, so "
            f"it is set when the module is compiled: write the directive "
            f"-set_prolog_flag({spec.name}, {v}) (or -double_quotes({v}))"))
    return spec.name, v


def module_flags(db) -> dict:
    """The module-scoped flag values of *db* (created on first use)."""
    flags = getattr(db, "prolog_flags", None)
    if flags is None:
        flags = {}
        try:
            db.prolog_flags = flags
        except AttributeError:
            pass
    return flags


def apply_setting(db, name: str, value) -> None:
    """Record an already-validated setting (:func:`check_setting`)."""
    spec = FLAGS[name]
    if spec.scope in ("module", "directive"):
        if db is not None:
            module_flags(db)[name] = value
    else:
        _PROCESS[name] = value


def flag_value(db, name: str):
    """The value of flag *name* as the module of *db* sees it, or
    ``_NO_VALUE``."""
    spec = FLAGS[name]
    if spec.scope in ("module", "directive"):
        if db is not None:
            v = module_flags(db).get(name)
            if v is not None:
                return v
        return spec.default
    return _PROCESS.get(name, spec.default)


def assert_creates_dynamic(db) -> bool:
    """True when asserting into a procedure that does not exist creates it
    as dynamic in *db*'s module (ISO 7.5.2(2))."""
    return flag_value(db, "assert_creates_dynamic") == "true"


@_db_builtin("set_prolog_flag", 2, fields=("flag", "value"))
def _set_prolog_flag_factory(db):
    """set_prolog_flag(Flag, Value) -- ISO 8.17.1.  A module-scoped flag is
    set for the calling module."""

    def set_prolog_flag__2(flag, value, trail, k):
        name, v = check_setting(flag, value)
        apply_setting(db, name, v)
        yield None

    return set_prolog_flag__2


@_db_builtin("current_prolog_flag", 2, fields=("flag", "value"))
def _current_prolog_flag_factory(db):
    """current_prolog_flag(Flag, Value) -- ISO 8.17.2.  An unbound Flag
    enumerates every flag that has a value."""

    def current_prolog_flag__2(flag, value, trail, k):
        f = deref(flag)
        if is_var(f):
            names = list(FLAGS)
        else:
            names = [_flag_named(f, _CURRENT).name]
        for name in names:
            v = flag_value(db, name)
            if v is _NO_VALUE:
                continue
            mark = trail.mark()
            if (unify(flag, name, trail)
                    and unify(value, _reported(name, v), trail)):
                yield None
            trail.undo(mark)

    return current_prolog_flag__2
