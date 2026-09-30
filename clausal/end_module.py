"""``:- end_module(Name).`` -- the ISO module-closing directive (ISO/IEC
13211-2), and the "require end_module" setting.

One implementation of the checks, shared by BOTH ``.pl`` front ends (the
native ``iso_l3`` lowering and the ``prolog_to_clausal`` translator), so the
two agree on what a valid module file is.

THE RULES (operator ruling 2026-09-30).  The ISO 13211-2 text is not
available in this repository, so these are the ruling's rules as given:

* ``end_module(N)`` closes the module a ``module(N, Exports)`` directive
  opened.  ``N`` must be an atom naming THAT module:

  - an unbound ``N``: ``error(instantiation_error, end_module/1)``;
  - ``N`` not an atom: ``error(type_error(atom, N), end_module/1)``;
  - no module is open -- the file has no ``module/2``, or an earlier
    ``end_module`` already closed it (a duplicate), or ``N`` is not the
    open module's name: ``error(existence_error(module, N), end_module/1)``.

* It is the LAST item of the file: only comments and layout may follow.  A
  clause or directive after it would modify a closed module:
  ``error(permission_error(modify, module, M), end_module/1)``.

* When end_module is REQUIRED, a module file (one with ``module/2``) that
  does not end with it fails to load:
  ``error(existence_error(directive, end_module(M)), load/1)``, naming the
  file and the module.

WHETHER IT IS REQUIRED, most specific first:

1. the file's own ``:- set_prolog_flag(require_end_module, true|false).``
   (file-local: it governs the file it is written in, nothing else);
2. the PROCESS-WIDE setting: :func:`set_require_end_module` (also what
   ``set_prolog_flag(require_end_module, V)`` run as a goal sets), else the
   environment variable ``CLAUSAL_REQUIRE_END_MODULE`` (``1``/``true``/
   ``yes`` or ``0``/``false``/``no``; unset or empty = no override);
3. the SURFACE default, :data:`REQUIRE_END_MODULE_DEFAULTS`: ``.pl`` does
   not require it; the Clausal Prolog surface does.

A SEAM file is never affected: the seam has no end_module, and no setting
reaches it (:func:`end_module_required` is False for any surface outside the
table, whatever the override).

Scryer does NOT accept the directive (it reports
``error(domain_error(directive, end_module/1), load/1)`` and the file fails
to load), so a path that hands a Clausal ``.pl`` file to Scryer removes it
first: :func:`strip_end_module`.

This module imports nothing from the engine: both front ends and the flag
table need it before anything heavy is loaded.
"""
from __future__ import annotations

import os
import re

from clausal import _suffixes

#: The environment variable of the process-wide override.
REQUIRE_END_MODULE_ENV = "CLAUSAL_REQUIRE_END_MODULE"

#: The Prolog flag that reads (and, as a goal, sets) the process-wide
#: override, or (as a directive) the file's own requirement.
REQUIRE_END_MODULE_FLAG = "require_end_module"

#: Surfaces, as :func:`surface_of` names them.
SURFACE_PL = "pl"
SURFACE_CLAUSAL_PROLOG = "clausal_prolog"
SURFACE_SEAM = "seam"

#: Whether a module file of each surface must end with ``end_module/1``
#: when no setting overrides it.  Keyed by the SURFACE, not the extension:
#: at the extension flip ``.clausal`` joins ``CLAUSAL_PROLOG_SUFFIXES`` and
#: its files get the Clausal Prolog entry with no change here.  The seam is
#: deliberately absent: it is never affected.
REQUIRE_END_MODULE_DEFAULTS: dict[str, bool] = {
    SURFACE_PL: False,
    SURFACE_CLAUSAL_PROLOG: True,
}

_TRUE = ("1", "true", "yes", "on")
_FALSE = ("0", "false", "no", "off")

_UNSET = object()
#: The process-wide setting made by :func:`set_require_end_module`:
#: ``_UNSET`` (the environment variable decides), ``True``/``False``, or
#: ``None`` (explicitly: each surface's default).
_setting = _UNSET


def surface_of(path) -> "str | None":
    """The surface a source file is written in, from its extension:
    ``"pl"``, ``"clausal_prolog"``, ``"seam"``, or None (not a source
    file)."""
    ext = os.path.splitext(os.fspath(path))[1]
    # Read through the module, at each call: the flip edits the tuples.
    if ext in _suffixes.CLAUSAL_PROLOG_SUFFIXES:
        return SURFACE_CLAUSAL_PROLOG
    if ext == _suffixes.PROLOG_SUFFIX:
        return SURFACE_PL
    if ext in _suffixes.CLAUSAL_SUFFIXES:
        return SURFACE_SEAM
    return None


def _env_setting() -> "bool | None":
    raw = os.environ.get(REQUIRE_END_MODULE_ENV, "").strip().lower()
    if not raw:
        return None
    if raw in _TRUE:
        return True
    if raw in _FALSE:
        return False
    # Never a silent default: a typo would otherwise run the other way.
    raise ValueError(
        f"{REQUIRE_END_MODULE_ENV}={raw!r}: use 1/true/yes or 0/false/no "
        f"(unset means each surface's default)")


def set_require_end_module(value: "bool | None") -> None:
    """Set the process-wide override: ``True`` requires ``end_module/1`` in
    every Prolog module file loaded from now on, ``False`` requires it in
    none, ``None`` restores each surface's default (ignoring
    ``CLAUSAL_REQUIRE_END_MODULE``).  :func:`reset_require_end_module`
    hands the decision back to the environment variable."""
    global _setting
    if value is not None and type(value) is not bool:
        raise TypeError(f"set_require_end_module: expected True, False or "
                        f"None, got {value!r}")
    _setting = value


def reset_require_end_module() -> None:
    """Forget :func:`set_require_end_module`: the environment variable
    decides again."""
    global _setting
    _setting = _UNSET


def require_end_module_setting() -> "bool | None":
    """The process-wide override in force: True, False, or None (none: each
    surface's default applies)."""
    if _setting is not _UNSET:
        return _setting
    return _env_setting()


def end_module_required(surface: "str | None",
                        file_setting: "bool | None" = None) -> bool:
    """Whether a module file of *surface* must end with ``end_module/1``.
    *file_setting* is the file's own ``set_prolog_flag(require_end_module,
    V)``, if it has one."""
    if surface not in REQUIRE_END_MODULE_DEFAULTS:
        return False            # the seam, or not a source file: never
    if file_setting is not None:
        return file_setting
    override = require_end_module_setting()
    if override is not None:
        return override
    return REQUIRE_END_MODULE_DEFAULTS[surface]


def _requirement_source(surface, file_setting) -> str:
    if file_setting is not None:
        return "this file's set_prolog_flag(require_end_module, true)"
    if _setting is not _UNSET and _setting is not None:
        return "the process-wide require_end_module flag"
    if _setting is _UNSET and _env_setting() is not None:
        return f"{REQUIRE_END_MODULE_ENV}=1"
    return f"the {surface} surface's default"


class EndModuleError(Exception):
    """A refused end_module (or a missing required one).  *term* is the ISO
    error term as text; the message already carries it."""

    def __init__(self, message: str, term: str):
        super().__init__(message)
        self.term = term


def _error(term: str, context: str, why: str) -> EndModuleError:
    return EndModuleError(f"{why} (ISO error({term}, {context}))", term)


class EndModuleCheck:
    """The per-file state of the checks.  A front end calls
    :meth:`end_module` on each ``end_module/1`` directive, :meth:`item`
    on every other clause or directive, and :meth:`finish` at the end of
    the file; each raises :class:`EndModuleError`."""

    __slots__ = ("ended", "ended_line", "file_setting")

    def __init__(self):
        #: The module end_module closed, and the line it did so on.
        self.ended: "str | None" = None
        self.ended_line: "int | None" = None
        #: The file's own set_prolog_flag(require_end_module, V).
        self.file_setting: "bool | None" = None

    @staticmethod
    def is_end_module(name, arity) -> bool:
        return name == "end_module" and arity == 1

    def end_module(self, arg, open_module: "str | None", *,
                   is_var: bool = False, shown: "str | None" = None,
                   line: "int | None" = None) -> None:
        """Check ``end_module(arg)``; *open_module* is the name the file's
        module/2 declared (None: it has none)."""
        ctx = "end_module/1"
        shown = shown if shown is not None else str(arg)
        if is_var:
            raise _error("instantiation_error", ctx,
                         "end_module(_): the module name must be an atom, "
                         "and it is unbound")
        if type(arg) is not str:
            raise _error(f"type_error(atom, {shown})", ctx,
                         f"end_module({shown}): the module name must be "
                         f"an atom")
        if self.ended is not None:
            at = f" at line {self.ended_line}" if self.ended_line else ""
            raise _error(f"existence_error(module, {arg})", ctx,
                         f"end_module({arg}): no module is open -- "
                         f"end_module({self.ended}){at} already closed "
                         f"module {self.ended} (a duplicate end_module)")
        if open_module is None:
            raise _error(f"existence_error(module, {arg})", ctx,
                         f"end_module({arg}): no module is open -- "
                         f"end_module/1 closes the module a "
                         f":- module({arg}, Exports). directive opened, and "
                         f"this file has none")
        if arg != open_module:
            raise _error(f"existence_error(module, {arg})", ctx,
                         f"end_module({arg}): the open module is "
                         f"{open_module}, not {arg}; write "
                         f":- end_module({open_module}).")
        self.ended = arg
        self.ended_line = line

    def item(self, what: str) -> None:
        """A clause or directive (*what* shows it): refused after
        end_module."""
        if self.ended is None:
            return
        at = f" (line {self.ended_line})" if self.ended_line else ""
        raise _error(f"permission_error(modify, module, {self.ended})",
                     "end_module/1",
                     f"{what} follows end_module({self.ended}){at}: "
                     f"end_module must be the last item of the file -- "
                     f"only comments may follow it")

    def finish(self, open_module: "str | None", surface: "str | None",
               filename: str) -> None:
        """End of file: a module file without its end_module fails when the
        setting requires one."""
        if open_module is None or self.ended is not None:
            return
        if not end_module_required(surface, self.file_setting):
            return
        why = _requirement_source(surface, self.file_setting)
        raise _error(
            f"existence_error(directive, end_module({open_module}))",
            "load/1",
            f"{filename}: module {open_module} does not end with "
            f":- end_module({open_module}). -- end_module is required "
            f"here ({why})")


def parse_flag_value(value) -> "bool | None":
    """``true``/``false`` (atoms or bools) -> True/False; anything else
    None (not a value of the flag, as a directive gives it)."""
    if value is True or value == "true":
        return True
    if value is False or value == "false":
        return False
    return None


_END_MODULE_DIRECTIVE = re.compile(
    r"^([ \t]*:-[ \t]*end_module[ \t]*\([^()\n]*\)[ \t]*\.)[ \t]*(?=%|$)",
    re.M)


def strip_end_module(text: str) -> str:
    """*text* with each ``:- end_module(Name).`` line commented out, for
    Scryer, which refuses the directive and fails the whole file.  Line
    numbers are kept (the directive becomes a ``%`` comment in place).  A
    line-level edit: it matches the directive written on a line of its
    own, which is where end_module stands (the last item of the file)."""
    return _END_MODULE_DIRECTIVE.sub(lambda m: "% " + m.group(1), text)
