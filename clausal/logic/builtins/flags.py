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
unknown                    error         yes         process
double_quotes              chars         directive   module
assert_creates_dynamic     false         yes         module
require_end_module         default       yes         process (goal)
argv                       []            no          process
clpq_max_nodes             20000         yes         process
clpq_max_work              4000000       yes         process
clpq_max_projection        4000000       yes         process
clpq_max_expansion         40000         yes         process
clpq_max_expansion_bits    200000000     yes         process
clpq_max_coefficient_bits  20000000      yes         process
=========================  ============  ==========  =================

``require_end_module`` (implementation-defined) is the process-wide
override of whether a Prolog module file must end with
``:- end_module(Name).`` (``clausal.end_module``): ``true``, ``false``, or
``default`` (each surface's own default: ``.pl`` no, Clausal Prolog yes).
Its value lives in ``clausal.end_module`` -- the same setting
``CLAUSAL_REQUIRE_END_MODULE`` and ``set_require_end_module`` make -- and
it governs the module files loaded AFTER it is set.  As a directive in a
``.pl`` file it is FILE-LOCAL (that file's front end reads it); a seam
file cannot set it.

``argv`` (implementation-defined, as in Scryer and SWI) is the list of the
program's command-line arguments, as atoms: what follows ``--`` on the
``clausal`` command line (``clausal.cli``), set from Python with
:func:`set_argv`.  It is ``[]`` otherwise, and read-only to a program.

The ``clpq_max_*`` flags (implementation-defined) are the resource caps
of the CLP(Q) port of clp(q,r) 1.3.3, each a positive integer: past one
the port raises ``error(resource_error(R), _)`` with R ``clpq_nodes``,
``clpq_work``, ``clpq_projection`` or ``clpq_expansion``
(``clausal/logic/clpq/limits.py``, which holds the values, and
``clausal/logic/clpq/DEVIATIONS.md`` D24).  They exist only under
``CLAUSAL_CLPQ=holzbaur``: the legacy solver has no such caps, and its
flags are as they were.

In the sandbox (``clausal.sandbox``) a program sets no flag that reaches
past its own module: the goal ``set_prolog_flag/2`` is refused there, and
so is a load-time ``set_prolog_flag`` directive of any front end, with the
same ``permission_error(access, private_procedure, set_prolog_flag/2)``,
unless the flag is in :data:`SANDBOX_DIRECTIVE_FLAGS`.  The host sets the
CLP(Q) caps from Python (``clausal.logic.clpq.limits.set_limit``).

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
  ISO value this engine does not implement (``char_conversion`` = ``on``,
  ``double_quotes`` = ``codes``): ``permission_error(modify, flag, F)``.

Scryer differs on the last two: it reports a read-only flag and a bad
``unknown`` value as ``domain_error(prolog_flag, F)``, and it implements
neither ``char_conversion`` nor ``debug``.  Here ISO decides.

``unknown`` (ISO 7.11.2.4) is process-wide, as ISO makes every flag
global.  It is read only where a call finds NO procedure -- every site that
would raise ``existence_error(procedure, PI)`` for a missing procedure asks
:func:`unknown_procedure_fails` first -- so a call that finds its procedure
never looks at it.  ``error`` raises the existence error; ``fail`` fails
the call; ``warning`` writes ``% Warning: predicate PI is undefined`` (the
line Scryer prints) to standard error, the ``user_error`` stream, and fails
the call.  The deliberate REFUSALS of committed choice reported with the
same error term -- ``*->`` on every surface, and on the Clausal Prolog
surface a cut in a meta-called goal (a ``.pl`` caller runs it) -- are not
missing procedures and stay errors whatever the flag says.  So is a
module that does not exist, when no procedure is named (``call(nomod:X)``
with ``X`` unbound).
"""

from __future__ import annotations

import os
from typing import Any

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.exceptions import (
    LogicException, domain_error, instantiation_error, permission_error,
    type_error,
)
from clausal.logic.builtins._registry import _builtin, _db_builtin
from clausal.logic.trampoline import DONE

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
        self.supported = supported      # the values it can be SET to here,
                                        # or a test of the value
        self.scope = scope              # "process" | "module" | "directive"
                                        # | "end_module" (clausal.end_module)
                                        # | "clpq" (clausal.logic.clpq.limits)

    def can_be(self, value) -> bool:
        if callable(self.supported):
            return self.supported(value)
        return value in self.supported


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
          supported=("error", "fail", "warning")),
    _Flag("double_quotes", "chars",
          lambda v: v in ("chars", "codes", "atom"),
          supported=("chars", "atom"), scope="directive"),
    _Flag("assert_creates_dynamic", "false", _is_bool_flag_value,
          supported=("true", "false"), scope="module"),
    _Flag("require_end_module", "default",
          lambda v: v in ("true", "false", "default"),
          supported=("true", "false", "default"), scope="end_module"),
    _Flag("argv", [], lambda v: type(v) is list),
)}


def _is_positive_int(v) -> bool:
    return _is_int(v) and v > 0


#: The CLP(Q) port's caps, flag -> resource (clausal.logic.clpq.limits).
#: Under CLAUSAL_CLPQ=holzbaur only, read here as clausal.logic.clpq reads
#: it: importing that package from here would import the builtins again.
CLPQ_LIMIT_FLAGS = {
    "clpq_max_nodes": "clpq_nodes",
    "clpq_max_work": "clpq_work",
    "clpq_max_projection": "clpq_projection",
    "clpq_max_expansion": "clpq_expansion",
    "clpq_max_expansion_bits": "clpq_expansion_bits",
    "clpq_max_coefficient_bits": "clpq_coefficient_bits",
}
if os.environ.get("CLAUSAL_CLPQ", "legacy") == "holzbaur":
    for _name in CLPQ_LIMIT_FLAGS:
        FLAGS[_name] = _Flag(_name, None, _is_positive_int,
                             supported=_is_positive_int, scope="clpq")

#: The flags a SANDBOXED module may still set with a load-time directive.
#: Each one's value lives on that module's own Database and governs that
#: module alone, so no other program and no later load sees it:
#:
#: * ``assert_creates_dynamic`` (scope "module"): whether an assert into a
#:   missing procedure of THIS module creates it; every ``.pl`` module
#:   starts with a directive setting it (import_hook._prolog_default_items).
#: * ``double_quotes`` (scope "directive"): how THIS module's ``"..."``
#:   literals are read, decided while it compiles.
#:
#: Every other flag is refused (sandbox_refusal), the process-wide ones
#: (``debug``, the ``clpq_max_*`` caps, ...) and any flag added later
#: until it is listed here: the list fails closed.
SANDBOX_DIRECTIVE_FLAGS = frozenset({"assert_creates_dynamic",
                                     "double_quotes"})


#: The scopes a flag of SANDBOX_DIRECTIVE_FLAGS must have for the sandbox
#: to let a directive set it: a flag listed there that ever became process
#: wide is refused like any other (fails closed).
_SANDBOX_DIRECTIVE_SCOPES = ("module", "directive")


def sandbox_refusal(name: str):
    """The error refusing a sandboxed setting of the flag *name* (the
    flag table's name, as check_setting resolved it), or None where the
    setting is allowed: outside the sandbox, or a flag of
    SANDBOX_DIRECTIVE_FLAGS that is still module-scoped.  The term is the
    refused goal's (clausal.sandbox._refusing_dispatch), raised as a
    clausal.sandbox.SandboxLoadError (an ImportError and a LogicException)
    since it refuses a load."""
    from clausal import _sandbox_state  # noqa: PLC0415
    if not _sandbox_state.ACTIVE:
        return None
    spec = FLAGS.get(name)
    if name in SANDBOX_DIRECTIVE_FLAGS and spec is not None \
            and spec.scope in _SANDBOX_DIRECTIVE_SCOPES:
        return None
    from clausal.sandbox import refusal_load_error  # noqa: PLC0415
    return refusal_load_error(permission_error(
        "access", "private_procedure", ("/", "set_prolog_flag", 2),
        f"{_SET}: the {name} flag reaches past this module, so the "
        f"sandbox does not let a program set it, as a goal or as a "
        f"directive"))


#: Process-wide values of the settable process flags.
_PROCESS: dict[str, Any] = {}

#: Flags whose value is a truth value: reported as the Python bool, which is
#: what ``true`` / ``false`` written in source compile to.
_BOOL_FLAGS = frozenset({"bounded", "assert_creates_dynamic",
                         "require_end_module"})


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
    if not spec.can_be(v):
        why = ("is read-only" if not spec.supported else
               f"can only be {' or '.join(spec.supported)} here")
        raise LogicException(permission_error(
            "modify", "flag", spec.name,
            f"{_SET}: the {spec.name} flag {why}"))
    refusal = sandbox_refusal(spec.name)
    if refusal is not None:
        raise refusal
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
    """Record an already-validated setting (:func:`check_setting`).  Every
    setting goes through here, the goal's and each front end's load-time
    directive's, so the sandbox's refusal is checked again here: a path
    that skipped check_setting still cannot write a flag (fails closed)."""
    refusal = sandbox_refusal(name)
    if refusal is not None:
        raise refusal
    spec = FLAGS[name]
    if spec.scope == "end_module":
        from clausal.end_module import set_require_end_module  # noqa: PLC0415
        set_require_end_module(None if value == "default"
                               else value == "true")
    elif spec.scope == "clpq":
        from clausal.logic.clpq import limits  # noqa: PLC0415
        limits.set_limit(CLPQ_LIMIT_FLAGS[name], value)
    elif spec.scope in ("module", "directive"):
        if db is not None:
            module_flags(db)[name] = value
    else:
        _PROCESS[name] = value


def flag_value(db, name: str):
    """The value of flag *name* as the module of *db* sees it, or
    ``_NO_VALUE``."""
    spec = FLAGS[name]
    if spec.scope == "end_module":
        from clausal.end_module import require_end_module_setting  # noqa: PLC0415
        try:
            v = require_end_module_setting()
        except ValueError as e:         # a bad CLAUSAL_REQUIRE_END_MODULE
            raise LogicException(domain_error(
                "flag_value", ("+", name, "CLAUSAL_REQUIRE_END_MODULE"),
                f"{_CURRENT}: {e}")) from None
        return spec.default if v is None else ("true" if v else "false")
    if spec.scope == "clpq":
        from clausal.logic.clpq import limits  # noqa: PLC0415
        return limits.limit(CLPQ_LIMIT_FLAGS[name])
    if spec.scope in ("module", "directive"):
        if db is not None:
            v = module_flags(db).get(name)
            if v is not None:
                return v
        return spec.default
    return _PROCESS.get(name, spec.default)


def unknown_procedure_fails(name, arity) -> bool:
    """Ask the ``unknown`` flag about a call to the missing procedure
    *name*/*arity*; under ``warning`` this WRITES the warning (to standard
    error) before answering True.  What the call does under the
    ``unknown`` flag (ISO 7.11.2.4): False under ``error`` (the default) --
    the caller raises its ``existence_error(procedure, PI)`` -- and True
    under ``fail`` and ``warning``, where the caller FAILS the call instead,
    after the warning is written.  Called only where a procedure was not
    found, never on a call that finds one."""
    mode = _PROCESS.get("unknown")
    if mode is None or mode == "error":
        return False
    if mode == "warning":
        _warn_unknown(name, arity)
    return True


def unknown_procedure_term_fails(term) -> bool:
    """:func:`unknown_procedure_fails` for the procedure an
    ``error(existence_error(procedure, Name/Arity), _)`` *term* names --
    for a site that has built the ISO term already (a string or a list
    called as a goal names '.'/N).  False for any other term."""
    try:
        formal = term[1]
        pi = formal[2]
        if formal[0] != "existence_error" or formal[1] != "procedure":
            return False
        if pi[0] == ":":
            pi = pi[2]
        name, arity = pi[1], pi[2]
    except (TypeError, IndexError, KeyError):
        return False
    return unknown_procedure_fails(name, arity)


def unknown_procedure_of(exc):
    """``(name, arity)`` of the missing procedure a resolver's
    ``LogicException`` *exc* reports, or None: set only where the error IS
    a missing procedure (``cells.resolve_qualified_goal_cell`` for a module
    that does not exist), never on a refusal or another error."""
    return getattr(exc, "unknown_procedure", None)


def _warn_unknown(name, arity) -> None:
    import sys  # noqa: PLC0415
    from clausal.logic.atoms import demangle, is_mangled  # noqa: PLC0415
    if type(name) is str and is_mangled(name):
        name = demangle(name)[1]
    try:
        from clausal.terms import term_write  # noqa: PLC0415
        shown = f"{term_write(name, quoted=False)}/{arity}"
    except Exception:  # noqa: BLE001 - a warning must never be what fails
        shown = f"{name}/{arity}"
    sys.stderr.write(f"% Warning: predicate {shown} is undefined\n")
    sys.stderr.flush()


def _fails_unknown(this_generator, _proceed, _fail, _catcher, *args):
    """The trampoline dispatch of a call that :func:`unknown_procedure_fails`
    turned into a failure."""
    yield (_fail, DONE)


#: Returned by a lookup in place of the missing procedure's dispatch.
UNKNOWN_PROCEDURE_DISPATCH = _fails_unknown


def set_argv(args) -> None:
    """Set the read-only ``argv`` flag: the program's command-line
    arguments, each an atom (a ``str``).  ``clausal.cli`` calls this with
    what follows ``--``."""
    _PROCESS["argv"] = [str(a) for a in args]


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


# ── character conversion (ISO 8.14.5, 8.14.6) ───────────────────────────────
#
# The table is process-wide, as ISO makes it: In -> Out for In \== Out (an
# identity pair is never stored).  No reader applies it: there is no
# read_term/2, and each source front end reads a whole file before its
# directives run, so a mid-file char_conversion directive could not reach
# the text after it.  That is why the char_conversion flag cannot be set to
# on (permission_error, as for any ISO value not implemented here).

#: In_char -> Out_char, each a one-char atom.
_CHAR_CONVERSION: dict[str, str] = {}

_CHAR_CONVERSION_PI = "char_conversion/2"
_CURRENT_CHAR_CONVERSION_PI = "current_char_conversion/2"


def _is_char(v) -> bool:
    return type(v) is str and len(v) == 1


def _check_char(v, context: str, which: str) -> None:
    if not _is_char(v):
        from clausal.logic.exceptions import representation_error  # noqa: PLC0415
        raise LogicException(representation_error(
            "character",
            f"{context}: {which} must be a one-char atom (ISO 8.14.5.3, "
            f"8.14.6.3)"))


@_builtin("char_conversion", 2)
def char_conversion__2(in_char, out_char, trail, k):
    """char_conversion(In_char, Out_char) -- ISO 8.14.5: put In_char ->
    Out_char in the process-wide table, or take In_char out of it when the
    two are the same character."""
    i, o = deref(in_char), deref(out_char)
    if is_var(i) or is_var(o):
        raise LogicException(instantiation_error(
            f"{_CHAR_CONVERSION_PI}: both characters must be bound"))
    _check_char(i, _CHAR_CONVERSION_PI, "In_char")
    _check_char(o, _CHAR_CONVERSION_PI, "Out_char")
    from clausal import _sandbox_state  # noqa: PLC0415
    if _sandbox_state.ACTIVE:           # backstop: the goal is refused there
        from clausal.sandbox import refusal_load_error  # noqa: PLC0415
        raise refusal_load_error(permission_error(
            "access", "private_procedure", ("/", "char_conversion", 2),
            f"{_CHAR_CONVERSION_PI}: the character conversion table is process-wide"))
    if i == o:
        _CHAR_CONVERSION.pop(i, None)
    else:
        _CHAR_CONVERSION[i] = o
    yield None


@_builtin("current_char_conversion", 2)
def current_char_conversion__2(in_char, out_char, trail, k):
    """current_char_conversion(In_char, Out_char) -- ISO 8.14.6: In_char is
    converted to the different character Out_char by the table."""
    i, o = deref(in_char), deref(out_char)
    if not is_var(i):
        _check_char(i, _CURRENT_CHAR_CONVERSION_PI, "In_char")
    if not is_var(o):
        _check_char(o, _CURRENT_CHAR_CONVERSION_PI, "Out_char")
    if not is_var(i):
        pairs = [(i, _CHAR_CONVERSION[i])] if i in _CHAR_CONVERSION else []
    else:
        pairs = sorted(_CHAR_CONVERSION.items())
    for a, b in pairs:
        mark = trail.mark()
        if unify(in_char, a, trail) and unify(out_char, b, trail):
            yield None
        trail.undo(mark)
