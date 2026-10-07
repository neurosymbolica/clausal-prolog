"""Sandbox mode: a process in which Clausal never reaches Python beyond a
fixed set of pure engine adapters (operator ruling D14, 2026-10-05).

The principle: Python reaches Clausal Prolog only through whitelisted
``.seam`` modules.  A worker that builds goals from untrusted data (an LLM's
validated JSON, say) and runs them with :func:`clausal.solve` turns the
sandbox on before it loads anything of its own::

    import clausal.sandbox
    clausal.sandbox.enable()            # or CLAUSAL_SANDBOX=1 in the env
    import my_domain                    # a .clausal rulebase: checked
    for _ in clausal.solve(goal, module=my_domain): ...

Once on it stays on for the life of the process.  There is no ``disable``,
no Prolog flag and no query that turns it off; a second :func:`enable` may
only narrow the allowlists.

What it does (``docs/sandbox.md`` has the threat model and the tables):

LOAD
    Every Clausal module loaded after :func:`enable` -- ``.seam``,
    ``.clausal`` or ``.pl``, whoever imports it -- is compiled from source
    and its FINAL generated Python is audited
    (:func:`clausal.seam_audit.audit_tree`, the decider the Python-bridge
    gate uses) before any of it runs.  A module with a Python route is
    refused with ``error(permission_error(load, python_escape, File), _)``
    unless it is an allowed bridge (*allow_bridges*, which only narrows
    the importer-project check of ``[tool.clausal] python_bridges``).  A reference to an
    engine adapter outside the allowlist is a route too, so a ``.pl``
    ``use_module(py/os)`` and a ``.seam`` ``-import_from(py.os, ...)`` are
    refused alike.  Python modules a front end would import while
    translating (a ``.pl`` ``use_module`` of a ``.py`` file) are refused
    before they are imported.

RUN TIME
    * Every Python entry point (:func:`clausal.solve`, ``call``, ``query``,
      ``once``, ``query_wfs``, :class:`clausal.Solutions`) checks its goal:
      only atoms, numbers, strings, logic variables and compound terms of
      those (lists, cells, dicts, the engine's quantities) may appear; a
      callable, module, class or any other Python object is refused with
      ``error(permission_error(access, python_object, Type), _)``.
    * A query runs as a Clausal Prolog frame: the dialect gate refuses
      ``M:G``, ``call/N``, ``assert``/``retract``/``clause`` into a ``.pl``
      or Python module (``permission_error(access, prolog_module |
      python_module, M)``), and so does every module frame except a ``.pl``
      module's and an allowed bridge's.
    * Every Python predicate adapter -- an engine ``py.*`` adapter, a
      package's, any foreign ``_get_dispatch`` implementor -- answers only
      when it is on the allowlist: anything else raises
      ``error(permission_error(access, python_module, M), _)`` when it is
      resolved or called, whichever route reached it.
    * Engine builtins with process-wide effects or I/O (``halt``,
      ``set_prolog_flag``, the stdout writers, the clock readers ...) raise
      ``error(permission_error(access, private_procedure, Name/Arity), _)``.
"""
from __future__ import annotations

import ast
import os
import sys
import threading
import warnings
from dataclasses import dataclass

from clausal import _sandbox_state as _st

__all__ = [
    "ENV_VAR",
    "ADAPTERS",
    "Adapter",
    "DENIED_BUILTINS",
    "SandboxLoadError",
    "enable",
    "is_enabled",
    "allowed_adapters",
    "allowed_bridges",
    "QUERY_FRAME",
]

#: The environment variable read at engine import: ``1``/``true``/``yes``/
#: ``on`` turns the sandbox on; ``0``/``false``/``no``/``off`` or unset
#: leaves it off; anything else is an ImportError (never a silent default).
ENV_VAR = "CLAUSAL_SANDBOX"

_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"", "0", "false", "no", "off"})


# ── the adapter classification ──────────────────────────────────────────────


@dataclass(frozen=True)
class Adapter:
    """One engine adapter module's sandbox classification.

    *allowed*: the module is pure computation (no filesystem, process,
    network, environment, clock or randomness, logging/I/O, database or
    reflection); *denied*: the predicates of an allowed module that are NOT
    (``datetime``'s clock readers); *why*: the evidence, in a sentence."""
    module: str
    allowed: bool
    why: str
    denied: frozenset = frozenset()


_PY = "clausal.modules.py."

#: Every engine adapter module, classified by its side effects (survey of
#: 2026-10-05; ``tests/test_sandbox.py`` fails when an engine adapter module
#: has no row, so a new adapter is denied until it is classified here).
ADAPTERS: "dict[str, Adapter]" = {a.module: a for a in (
    Adapter(_PY + "datetime", True,
            "date/time arithmetic and formatting; now/1, now_utc/1 and "
            "today/1 read the clock and timestamp/2 depends on the host "
            "time zone",
            frozenset({"now", "now_utc", "today", "timestamp"})),
    Adapter(_PY + "json", True,
            "parse/generate/get are pure; read_file/2 and write_file/2 touch "
            "the filesystem",
            frozenset({"read_file", "write_file"})),
    Adapter(_PY + "csv", True,
            "parse/generate are pure; read_file, read_records and write_file "
            "touch the filesystem",
            frozenset({"read_file", "read_records", "write_file"})),
    Adapter(_PY + "re", True, "regular expressions over the given text"),
    Adapter(_PY + "hash", True, "hashlib digests of the given data"),
    Adapter(_PY + "hmac", True, "HMAC sign/verify with a caller-given key"),
    Adapter(_PY + "pbkdf2", True,
            "key derivation with a caller-given salt (no randomness)"),
    Adapter(_PY + "url", True, "urllib.parse only; no network"),
    Adapter(_PY + "uuid", True,
            "v3/v5 and the converters are pure; uuid_v1/1 reads the clock "
            "and the MAC address, uuid_v4/1 is random",
            frozenset({"uuid_v1", "uuid_v4"})),
    Adapter(_PY + "units", True, "re-export of clausal.modules.units"),
    Adapter(_PY + "imperial", True,
            "re-export of clausal.modules.imperial"),
    Adapter("clausal.modules.units", True,
            "unit algebra and quantities; units register at import only"),
    Adapter("clausal.modules.imperial", True, "constant quantities"),
    Adapter("clausal.modules.pure_random", True,
            "state-threaded: every draw is a function of the rng(Seed, N) "
            "term (a fresh random.Random over a SHA-256 digest); no clock, "
            "OS entropy or global generator"),
    Adapter("clausal.modules.currency", True,
            "currency tables and money arithmetic over built-in data"),
    Adapter("clausal.modules.countries", True,
            "every clausal.modules.countries.<jurisdiction>: currency "
            "constants registered at import"),
    Adapter("clausal.modules.graphs", True,
            "graph algorithms over the given terms"),
    Adapter("clausal.modules.prolog", True, "no public predicates"),
    Adapter(_PY + "files", False, "filesystem: read, write, delete, rename"),
    Adapter(_PY + "os", False,
            "environment variables, working directory, pid, argv"),
    Adapter(_PY + "process", False, "subprocess and shell, sleep"),
    Adapter(_PY + "http", False, "network (urllib.request)"),
    Adapter(_PY + "tcp", False, "network (sockets)"),
    Adapter(_PY + "sqlite", False,
            "sqlite databases on the filesystem, a global connection table"),
    Adapter(_PY + "logging", False,
            "process-wide logging configuration, stream and file output"),
    Adapter(_PY + "random", False,
            "randomness from a process-wide generator"),
    Adapter(_PY + "asyncio", False,
            "await_value/await_each wait on Python awaitables (objects from "
            "the host program, scheduled on its event loop); sleep/1 is the "
            "clock -- no pure part"),
    Adapter("clausal.modules.reflection", False,
            "reified_file_item/2 reads any file; module internals"),
)}

#: Re-export shims: the same objects as their target, allowed with it.
_SHIMS = {_PY + "units": "clausal.modules.units",
          _PY + "imperial": "clausal.modules.imperial"}


def _canonical(module: str) -> str:
    """The :data:`ADAPTERS` key that decides *module*: a shim's target, a
    jurisdiction's package row."""
    module = _SHIMS.get(module, module)
    if module.startswith("clausal.modules.countries."):
        return "clausal.modules.countries"
    return module


#: Engine modules that are no adapter but that a sandboxed module may
#: import: the CLP(Z) machinery ``library(clpz)`` maps to.  The engine's
#: ``.seam`` stdlib (``clausal.stdlib.*``) is allowed by package, and a
#: ``library(...)`` facade as its adapter is.
_ENGINE_LIBRARIES = frozenset({"clausal.logic.clpfd"})
_ENGINE_SEAM_PACKAGES = ("clausal.stdlib.",)
_FACADES = "clausal.library."

#: Engine builtins a sandboxed query may not run (process-wide effects,
#: I/O, the clock, a global counter, solver options that write files).  The
#: names cover every arity the registries hold.
DENIED_BUILTINS: "dict[str, str]" = {
    "halt": "ends the process",
    "set_prolog_flag": "changes process-wide flags and later loads",
    "global_atom": "writes the atom pool every module is seeded from",
    "gensym": "a process-wide counter",
    "current_time": "reads the clock",
    "statistics": "reads the clock and the process's resource usage",
    "time_goal": "reads the clock; time_goal/1 writes to stderr",
    "write": "writes to stdout",
    "writeln": "writes to stdout",
    "write_text": "writes to stdout",
    "writeln_text": "writes to stdout",
    "writeq": "writes to stdout",
    "write_canonical": "writes to stdout",
    "write_term": "writes to stdout",
    "print_term": "writes to stdout",
    "portray_clause": "writes to stdout",
    "listing": "writes to stdout",
    "format": "writes to stdout",
    "nl": "writes to stdout",
    "tab": "writes to stdout",
    "z3_set_option": "solver options include trace files",
    "z3.set_option": "solver options include trace files",
    "z3_stats": "process-wide solver counters",
    "z3.statistics": "process-wide solver counters",
}

#: The engine's own attributed-variable keys (module, constant): the
#: constraint solvers' and freeze's.  A sandboxed program may not put, read
#: or delete one -- its value is engine state (a frozen goal is a Python
#: closure the hook CALLS; an OR-Tools key holds a solver model).  A test
#: checks every key constant the engine registers a hook for or puts on a
#: variable is listed.  Read from the module SOURCE (some of these modules
#: import an optional solver).
ENGINE_ATTR_KEYS = (
    ("clausal.logic.coroutining", "FREEZE_KEY"),
    ("clausal.logic.constraints", "DIF_KEY"),
    ("clausal.logic.clpfd", "FD_KEY"),
    ("clausal.logic.clpfd", "ZCMP_KEY"),
    ("clausal.logic.clpb", "B_KEY"),
    ("clausal.logic.clpq", "Q_KEY"),
    ("clausal.logic.clpr", "REAL_KEY"),
    ("clausal.logic.units_constraint", "UNITS_KEY"),
    ("clausal.logic.units_clp", "LINK_KEY"),
    ("clausal.logic.clpsat", "SAT_KEY"),
    ("clausal.logic.clportools", "OR_KEY"),
    ("clausal.logic.clportools_lp", "LP_KEY"),
    ("clausal.logic.clpz3", "Z3_KEY"),
)


def adapter_row(module: str) -> "Adapter | None":
    """The :data:`ADAPTERS` row of the engine module *module* (a
    jurisdiction under ``clausal.modules.countries`` takes that package's
    row), or None."""
    row = ADAPTERS.get(module)
    if row is None and module.startswith("clausal.modules.countries."):
        row = ADAPTERS["clausal.modules.countries"]
    return row


def engine_adapter_modules() -> "list[str]":
    """Every engine adapter module, by FILE (the engine's own package
    directory, never a package spliced into the namespace): the public
    ``.py`` files under ``clausal/modules`` and ``clausal/modules/py``, and
    the jurisdictions under ``clausal/modules/countries``."""
    import clausal.modules  # noqa: PLC0415
    root = os.path.dirname(os.path.realpath(clausal.modules.__file__))
    out = []
    for sub, prefix in (("", "clausal.modules."),
                        ("py", "clausal.modules.py."),
                        ("countries", "clausal.modules.countries.")):
        d = os.path.join(root, sub)
        for f in sorted(os.listdir(d)):
            if f.endswith(".py") and not f.startswith("_"):
                out.append(prefix + f[:-3])
    return out


# ── state ───────────────────────────────────────────────────────────────────


class _State:
    __slots__ = ("adapters", "bridges", "allowed_ids",
                 "keep", "admitted_bridges", "lock", "attr_keys")

    def __init__(self):
        self.adapters: frozenset = frozenset()
        self.bridges: tuple = ()
        self.allowed_ids: frozenset = frozenset()
        self.keep: tuple = ()
        self.admitted_bridges: set = set()
        self.lock = threading.RLock()
        self.attr_keys: frozenset = frozenset()


_STATE = _State()


def is_enabled() -> bool:
    """True once the sandbox is on (it never turns off)."""
    return _st.ACTIVE


def allowed_adapters() -> frozenset:
    """The adapter modules (:data:`ADAPTERS` keys) a sandboxed program may
    use; empty while the sandbox is off."""
    return _STATE.adapters


def allowed_bridges() -> tuple:
    """The bridge entries passed to :func:`enable` (after narrowing)."""
    return _STATE.bridges


def _default_adapters() -> frozenset:
    return frozenset(m for m, a in ADAPTERS.items()
                     if a.allowed and m not in _SHIMS)


def _normalise_adapter(name) -> str:
    """``py.datetime`` / ``datetime`` / ``date_time`` /
    ``clausal.library.datetime`` / ``clausal.modules.py.datetime`` -> the
    :data:`ADAPTERS` key."""
    if not isinstance(name, str) or not name:
        raise TypeError(f"clausal.sandbox.enable: an adapter is named by a "
                        f"module name string, got {name!r}")
    cands = [name]
    if name.startswith("py."):
        cands.append(_PY + name[3:])
    if name.startswith(_FACADES):
        cands.append(_facade_adapter(name) or "")
    try:
        from clausal.templating.term_rewriting import (  # noqa: PLC0415
            _resolve_import_path)
        cands.append(_resolve_import_path(name))
    except Exception:  # noqa: BLE001 -- only a spelling aid
        pass
    cands += ["clausal.modules." + name, _PY + name]
    for c in cands:
        if c.startswith("py."):
            c = _PY + c[3:]
        if c in ADAPTERS:
            return _canonical(c)
    raise ValueError(f"clausal.sandbox.enable: {name!r} names no engine "
                     f"adapter (known: {', '.join(sorted(ADAPTERS))})")


def _collect_allowed(adapters: frozenset) -> "tuple[frozenset, tuple]":
    """(ids, objects) of every Python goal object the allowed adapter
    modules offer, minus their denied predicates (an object a denied name is
    bound to stays denied under any other name)."""
    import importlib  # noqa: PLC0415
    from clausal.modules.py import ModulePredicate  # noqa: PLC0415
    modules = []
    for m in sorted(adapters):
        if m == "clausal.modules.countries":
            modules += [(j, ADAPTERS[m]) for j in engine_adapter_modules()
                        if j.startswith(m + ".")]
        else:
            modules.append((m, ADAPTERS[m]))
            modules += [(sh, ADAPTERS[sh]) for sh, target in _SHIMS.items()
                        if target == m]
    allowed: dict = {}
    denied: set = set()
    for m, row in modules:
        mod = importlib.import_module(m)
        for name, value in vars(mod).items():
            if not isinstance(value, ModulePredicate):
                continue
            if name in row.denied:
                denied.add(id(value))
            else:
                allowed[id(value)] = value
    for i in denied:
        allowed.pop(i, None)
    return frozenset(allowed), tuple(allowed.values())


def _user_modules() -> "list[str]":
    """The non-engine Clausal modules loaded in this process."""
    from clausal.end_module import surface_of  # noqa: PLC0415
    from clausal.python_bridges import is_engine_shipped  # noqa: PLC0415
    out = []
    for name, mod in list(sys.modules.items()):
        if mod is None:
            continue
        try:
            ns = vars(mod)
        except TypeError:
            continue
        path = ns.get("__file__")
        if isinstance(path, str) and path:
            if is_engine_shipped(name, path):
                continue
            if surface_of(path) is not None or "$module" in ns:
                out.append(f"{name} ({path})")
        elif "$module" in ns:
            out.append(f"{name} (no file)")
    return sorted(out)


def _bridge_entries(allow_bridges) -> tuple:
    """*allow_bridges* as ``(spelling, realpath, sha256 or None)``: each
    entry names ONE file, fixed when ``enable()`` runs -- a path (one
    containing ``/`` or ending in ``.seam``), a dotted module name resolved
    then without importing anything, or a table ``{"module"|"path": ...,
    "sha256": ...}`` that also pins the content.  No project file is read
    here: the list only NARROWS the importer-project check python_bridges
    makes when a ``.clausal`` file imports the bridge (ruling S5) -- and
    since it names files, a same-named module planted elsewhere on
    ``sys.path`` (with its own pyproject) is not the bridge it allows."""
    import re  # noqa: PLC0415
    from clausal import python_bridges as pb  # noqa: PLC0415
    if isinstance(allow_bridges, str):
        raise TypeError("clausal.sandbox.enable: allow_bridges is a "
                        "sequence of module names or paths, not a string")
    entries = []
    for raw in allow_bridges or ():
        sha = None
        spec = raw
        if isinstance(raw, dict):
            keys = set(raw)
            names = [k for k in ("module", "path") if k in raw]
            if keys - {"module", "path", "sha256"} or len(names) != 1:
                raise ValueError(f"clausal.sandbox.enable: the bridge "
                                 f"{raw!r} takes exactly one of module or "
                                 f"path, and optionally sha256")
            spec = raw[names[0]]
            sha = raw.get("sha256")
            if sha is not None and not (isinstance(sha, str)
                                        and re.fullmatch(r"[0-9a-fA-F]{64}",
                                                         sha)):
                raise ValueError(f"clausal.sandbox.enable: {raw!r}: sha256 "
                                 f"must be 64 hex digits")
            if names[0] == "path" and isinstance(spec, str) and not (
                    spec.endswith(".seam") or "/" in spec):
                spec = os.path.join(".", spec)
        if not isinstance(spec, str) or not spec:
            raise TypeError(f"clausal.sandbox.enable: a bridge is a module "
                            f"name, a path or a table, got {raw!r}")
        if spec.endswith(".seam") or "/" in spec:
            real = os.path.realpath(spec)
        elif all(p.isidentifier() for p in spec.split(".")):
            origin = pb._find(spec)
            if not (isinstance(origin, str) and origin.endswith(".seam")):
                raise ValueError(f"clausal.sandbox.enable: the bridge "
                                 f"{spec!r} resolves to no .seam file "
                                 f"({origin!r})")
            real = os.path.realpath(origin)
        else:
            raise ValueError(f"clausal.sandbox.enable: {spec!r} is neither a "
                             f"dotted module name nor a path")
        entries.append((spec, real, sha and sha.lower()))
    return tuple(entries)


def enable(allow_adapters=None, allow_bridges=()) -> None:
    """Turn the sandbox on for the rest of the process.

    *allow_adapters*: None for the default allowlist (every
    :data:`ADAPTERS` row marked allowed), or an iterable of adapter module
    names, each of which must be on the default list -- it can only narrow.
    *allow_bridges*: ``.seam`` modules WITH Python that may still load,
    each naming one FILE: a path, a dotted module name (resolved to its
    file now), or ``{"module"|"path": ..., "sha256": ...}`` pinning it.  It only NARROWS the Python-bridge gate:
    such a module loads when it is named here AND a ``.clausal`` importer's
    project allowlists it (``[tool.clausal] python_bridges`` of the
    pyproject above the IMPORTING file, sha256 pins honoured).  Nothing is
    looked up from the working directory.

    Fails closed with ``RuntimeError`` when a Clausal module of the user's
    is already loaded (it was not checked).  Calling it again only narrows
    (a name outside the current lists raises ``PermissionError``)."""
    from clausal import python_bridges as pb  # noqa: PLC0415
    with _STATE.lock:
        current = _STATE.adapters if _st.ACTIVE else _default_adapters()
        if allow_adapters is None:
            wanted = current
        else:
            if isinstance(allow_adapters, str):
                raise TypeError("clausal.sandbox.enable: allow_adapters is a "
                                "sequence of module names, not a string")
            wanted = frozenset(_normalise_adapter(n) for n in allow_adapters)
            wider = wanted - current
            if wider:
                raise PermissionError(
                    f"clausal.sandbox.enable: {', '.join(sorted(wider))} "
                    f"{'is' if len(wider) == 1 else 'are'} not on the "
                    f"{'current' if _st.ACTIVE else 'default'} adapter "
                    f"allowlist; allow_adapters may only narrow it")
        bridges = _bridge_entries(allow_bridges)
        if _st.ACTIVE:
            old = {(p, h) for _r, p, h in _STATE.bridges}
            wider = [raw for raw, p, h in bridges
                     if (p, h) not in old and (p, None) not in old]
            if wider:
                raise PermissionError(
                    f"clausal.sandbox.enable: the sandbox is already on and "
                    f"{', '.join(wider)} was not an allowed bridge; a second "
                    f"enable() may only narrow")
        else:
            users = _user_modules()
            if users:
                raise RuntimeError(
                    "clausal.sandbox.enable: refusing to turn the sandbox on "
                    "after these Clausal modules of yours were loaded "
                    "unchecked: " + ", ".join(users) + ".  Enable the "
                    "sandbox before loading anything (or set "
                    f"{ENV_VAR}=1).")
        ids, keep = _collect_allowed(wanted)
        _STATE.adapters = wanted
        _STATE.bridges = bridges
        _STATE.allowed_ids = ids
        _STATE.keep = keep
        if not _st.ACTIVE:
            _STATE.attr_keys = _engine_attr_keys()
            _install_finders()
            _deny_builtins()
            _clear_query_caches()
            _st.ACTIVE = True


def _engine_attr_keys() -> frozenset:
    """The key strings of :data:`ENGINE_ATTR_KEYS`, read from each module's
    source (a top-level ``NAME = "key"``) without importing it.  A key that
    cannot be read fails ``enable()`` (closed)."""
    from clausal import python_bridges as pb  # noqa: PLC0415
    out = set()
    for m, c in ENGINE_ATTR_KEYS:
        origin = pb._find(m)
        value = None
        if isinstance(origin, str) and origin.endswith(".py"):
            with open(origin, encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=origin)
            for node in tree.body:
                targets = (node.targets if isinstance(node, ast.Assign)
                           else [node.target] if isinstance(node, ast.AnnAssign)
                           else [])
                if (any(isinstance(t, ast.Name) and t.id == c
                        for t in targets)
                        and isinstance(node.value, ast.Constant)
                        and isinstance(node.value.value, str)):
                    value = node.value.value
        if value is None:
            raise RuntimeError(f"clausal.sandbox: cannot read the engine "
                               f"attribute key {m}.{c}")
        out.add(value)
    return frozenset(out)


def check_attr_key(key: str, context: str) -> None:
    """In the sandbox: refuse the engine's own attribute *key*
    (``permission_error(access, attribute, Key)``)."""
    if key in _STATE.attr_keys:
        raise _access_error(
            "attribute", key,
            f"{key} is an attribute the engine's own solvers keep (its value "
            f"is engine state); a sandboxed program may not touch it",
            context)


def engine_attr_key(key) -> bool:
    return key in _STATE.attr_keys


def read_attr(obj, name: str):
    """An attribute of the WALKABLE module *obj*, read from its namespace
    (never ``getattr``: a module ``__getattr__`` -- the units module's
    deprecated spellings warn on stderr -- is not run); None when absent."""
    try:
        ns = object.__getattribute__(obj, "__dict__")
    except AttributeError:
        return None
    return ns.get(name)


def _install_finders() -> None:
    """The real import hook, and no lazy stub: the stub's lookups import
    parent packages (``importlib.util.find_spec``), and the sandbox's
    module resolution must import nothing."""
    import clausal.import_hook  # noqa: F401,PLC0415 -- installs the finders
    from clausal._lazy_hook import _LazyHookFinder  # noqa: PLC0415
    sys.meta_path[:] = [f for f in sys.meta_path
                        if type(f).__name__ != _LazyHookFinder.__name__
                        or type(f).__module__ != _LazyHookFinder.__module__]


def _enable_from_env() -> None:
    """Called at engine import: ``CLAUSAL_SANDBOX``."""
    raw = os.environ.get(ENV_VAR, "").strip().lower()
    if raw in _FALSE:
        return
    if raw not in _TRUE:
        raise ImportError(f"{ENV_VAR}={os.environ.get(ENV_VAR)!r} is not a "
                          f"sandbox setting; use 1 (on) or 0 (off)")
    enable()


# ── errors ──────────────────────────────────────────────────────────────────


def _logic_exception():
    from clausal.logic.exceptions import LogicException  # noqa: PLC0415
    return LogicException


class SandboxLoadError(ImportError):
    """A module the sandbox refuses to load.  Raised as the ISO term
    ``error(permission_error(load, python_escape, File), load/1)`` -- a
    :class:`~clausal.logic.exceptions.LogicException` too (the class is
    rebuilt with that base on first use, see :func:`load_error`)."""


_LOAD_ERROR_CLASS = None


def load_error(path: str, why: str) -> Exception:
    """The :class:`SandboxLoadError` (an ImportError AND a LogicException)
    refusing the module at *path*."""
    global _LOAD_ERROR_CLASS
    from clausal.logic.exceptions import (  # noqa: PLC0415
        LogicException, permission_error)
    if _LOAD_ERROR_CLASS is None:
        _LOAD_ERROR_CLASS = type("SandboxLoadError",
                                 (LogicException, SandboxLoadError), {})
        _LOAD_ERROR_CLASS.__module__ = __name__
    term = permission_error("load", "python_escape", os.path.abspath(path),
                            f"load/1: {why}")
    return _LOAD_ERROR_CLASS(term)


def _access_error(kind: str, culprit, why: str, context: str = "call/1"):
    from clausal.logic.exceptions import permission_error  # noqa: PLC0415
    return _logic_exception()(permission_error(
        "access", kind, culprit, f"{context}: {why}"))


# ── LOAD ────────────────────────────────────────────────────────────────────


_ROUTE_TEXT = {
    "sandbox_adapter": ("an engine adapter outside the sandbox's allowlist, "
                        "or a denied predicate of an allowed one"),
    "sandbox_engine_module": ("an engine module the sandbox does not let a "
                              "program import"),
}


#: facade dotted name -> adapter module (from the facade's compiler record).
_FACADE_ADAPTERS: dict = {}


def _facade_adapter(facade: str) -> "str | None":
    """The engine adapter module the ``library(...)`` facade *facade*
    re-exports, read from the facade's own compiler record."""
    if facade in _FACADE_ADAPTERS:
        return _FACADE_ADAPTERS[facade]
    from clausal import python_bridges as pb  # noqa: PLC0415
    found = None
    origin = pb._find(facade)
    if origin and origin.endswith(".seam"):
        record = pb.compiler_record(origin) or ()
        mods = {pb._module_path(r[1]) for r in record
                if r[0] in ("import_from", "import_module")}
        if len(mods) == 1:
            found = mods.pop()
    _FACADE_ADAPTERS[facade] = found
    return found


def _engine_reference_ok(dotted: str, name: "str | None") -> "str | None":
    """None when a sandboxed module may reference the ENGINE module
    *dotted* (and its export *name*, when given); else the route kind."""
    if dotted.startswith(_ENGINE_SEAM_PACKAGES) or dotted in _ENGINE_LIBRARIES:
        return None
    if dotted.startswith(_FACADES):
        adapter = _facade_adapter(dotted)
        if adapter is None:
            return "sandbox_engine_module"
        dotted = adapter
    row = adapter_row(dotted)
    if row is None:
        return "sandbox_engine_module"
    key = _canonical(dotted)
    if key not in _STATE.adapters:
        return "sandbox_adapter"
    if name is not None and name in row.denied:
        return "sandbox_adapter"
    return None


_STDLIB_EXPORTS: dict = {}


def _stdlib_exports(dotted: str) -> frozenset:
    """The predicates the engine ``.seam`` stdlib module *dotted* defines
    (it declares no module/2 list, so the bridge gate's export reading
    finds none): what the module itself registers."""
    hit = _STDLIB_EXPORTS.get(dotted)
    if hit is None:
        import importlib  # noqa: PLC0415
        from clausal.logic.solve import module_signatures  # noqa: PLC0415
        try:
            hit = frozenset(module_signatures(importlib.import_module(dotted)))
        except Exception:  # noqa: BLE001 -- unreadable: nothing exported
            hit = frozenset()
        _STDLIB_EXPORTS[dotted] = hit
    return hit


def _facade_value(facade: str, name: str) -> bool:
    """True when the engine facade *facade* binds *name* to a VALUE it
    re-exports (``clausal.library.is_value``)."""
    if name.startswith("_"):
        return False
    import importlib  # noqa: PLC0415
    from clausal.library import is_value  # noqa: PLC0415
    try:
        mod = importlib.import_module(facade)
    except Exception:  # noqa: BLE001 -- unreadable: no value
        return False
    return is_value(vars(mod).get(name))


def _dotted_builtin(dotted: str) -> bool:
    """True when *dotted* is the name of a registered engine builtin
    (``clpq.rational``, ``z3.sat``): a dotted name, no module reference."""
    from clausal.logic.builtins._registry import (  # noqa: PLC0415
        _BUILTINS, _DB_BUILTINS)
    return any(k[0] == dotted for k in _BUILTINS) or any(
        k[0] == dotted for k in _DB_BUILTINS)


def _denied_name(dotted: str, name: "str | None") -> "str | None":
    """The adapter module when *name* is a DENIED predicate of the ALLOWED
    adapter *dotted* names (directly or through its ``library(...)``
    facade), else None."""
    if name is None:
        return None
    adapter = _facade_adapter(dotted) if dotted.startswith(_FACADES) \
        else dotted
    row = adapter_row(adapter) if adapter else None
    if (row is None or _canonical(adapter) not in _STATE.adapters
            or name not in row.denied):
        return None
    return adapter


def _denied_hint(denied) -> str:
    """Ruling D26: what a refusal over denied predicates says -- per
    module, the denied predicates the import brought in, and how to list
    the needed ones instead."""
    import importlib  # noqa: PLC0415
    from clausal.logic.solve import module_signatures  # noqa: PLC0415
    by: dict = {}
    for dotted, adapter, name in denied:
        by.setdefault(dotted, (adapter, set()))[1].add(name)
    parts = []
    for dotted, (adapter, names) in sorted(by.items()):
        try:
            sigs = module_signatures(importlib.import_module(dotted))
        except Exception:  # noqa: BLE001 -- unreadable: names only
            sigs = {}
        row = adapter_row(adapter)

        def ind(n, sigs=sigs):
            return ", ".join(f"{n}/{a}" for a in sorted(sigs.get(n, ()))) \
                or n
        listed = ", ".join(ind(n) for n in sorted(names))
        if dotted.startswith(_FACADES):
            label = f"library({dotted[len(_FACADES):]})"
            ok = sorted(n for n in sigs
                        if n not in row.denied and not n.startswith("_"))
            how = (f"e.g. use_module({label}, [{ind(ok[0]).split(', ')[0]}])"
                   if ok else f"in the use_module({label}, [...]) list")
        else:
            label = dotted
            how = "in the import list"
        parts.append(f"{label} brings in denied {listed}: the sandbox "
                     f"refuses them, so list the predicates you need, {how}")
    return "; ".join(parts)


def _sandbox_checker(routes: list, children: list,
                     denied: "list | None" = None):
    """:func:`clausal.python_bridges.audit_checker`, narrowed: an
    engine-shipped module a sandboxed module references must be an allowed
    adapter (or its facade, or the stdlib).  Two engine shapes the bridge
    gate does not know are read here: an engine ``.seam`` stdlib module
    exports the predicates it defines, and a dotted BUILTIN name
    (``clpq.rational``) names no module -- unless a module of that name
    resolves, which the base check then judges."""
    from clausal import python_bridges as pb  # noqa: PLC0415
    base = pb.audit_checker(routes, children)

    def engine(dotted, name, line) -> bool:
        origin = pb._find(dotted)
        if origin in (None, pb._UNRESOLVABLE):
            return True         # the base check routes it
        if not pb.is_engine_shipped(dotted, origin):
            return True         # judged on its own load
        kind = _engine_reference_ok(dotted, name)
        if kind is not None:
            routes.append((kind, line))
            adapter = _denied_name(dotted, name)
            if adapter is not None and denied is not None:
                denied.append((dotted, adapter, name))
            return False
        return True

    def _parents_ok(a, line) -> bool:
        """Importing ``p.q.m`` imports ``p`` and ``p.q`` first: a parent
        that is a Python package (an ``__init__.py`` not the engine's, not
        yet imported) would RUN, whatever ``m`` is.  A Clausal package, a
        namespace package and an engine package are fine."""
        from clausal._suffixes import SOURCE_SUFFIXES  # noqa: PLC0415
        parts = pb._module_path(a).split(".")
        for i in range(1, len(parts)):
            name = ".".join(parts[:i])
            if name in sys.modules:
                continue
            origin = pb._find(name)
            if origin is None:
                # No module, or a NAMESPACE package -- which runs nothing
                # but may hold a Python package below it: every level is
                # checked (a missing one makes the deeper ones None too).
                continue
            if origin == pb._UNRESOLVABLE:
                routes.append(("python_module", line))
                return False
            if origin.endswith(SOURCE_SUFFIXES) or pb.is_engine_shipped(
                    name, origin):
                continue
            routes.append(("python_module", line))
            return False
        return True

    def base_check(kind, a, b, node, dotted, origin, name) -> bool:
        """The bridge gate's check, except that an engine ``library(...)``
        facade also exports the VALUES it re-exports (a unit, a currency,
        a number: ``use_module(library(units), [metre])``), which its
        module/2 list does not name."""
        n = len(routes)
        ok = base(kind, a, b, node)
        new = routes[n:]
        if (new and name is not None and all(r[0] == "non_export"
                                             for r in new)
                and dotted.startswith(_FACADES)
                and origin not in (None, pb._UNRESOLVABLE)
                and pb.is_engine_shipped(dotted, origin)
                and _facade_value(dotted, name)):
            del routes[n:]
            return True
        return ok

    def stdlib(dotted, origin, name, line) -> bool:
        if name is not None and name not in _stdlib_exports(dotted):
            routes.append(("non_export", line))
            return False
        return True

    def check(kind, a, b, node) -> bool:
        from clausal.seam_audit import node_line  # noqa: PLC0415
        line = node_line(node)
        if not _parents_ok(a, line):
            return False
        if kind in ("module", "name"):
            dotted = pb._module_path(a)
            origin = pb._find(dotted)
            if (dotted.startswith(_ENGINE_SEAM_PACKAGES)
                    and origin not in (None, pb._UNRESOLVABLE)
                    and pb.is_engine_shipped(dotted, origin)):
                return stdlib(dotted, origin, b if kind == "name" else None,
                              line)
            ok = base_check(kind, a, b, node, dotted, origin,
                            b if kind == "name" else None)
            return engine(dotted, b if kind == "name" else None, line) and ok
        chain = tuple(a.split("."))
        for i in range(len(chain) - 1, 0, -1):
            dotted = pb._module_path(".".join(chain[:i]))
            origin = pb._find(dotted)
            if origin is None:
                continue
            name = chain[i] if len(chain) - i == 1 else None
            if (dotted.startswith(_ENGINE_SEAM_PACKAGES)
                    and origin != pb._UNRESOLVABLE
                    and pb.is_engine_shipped(dotted, origin)):
                if name is None:
                    routes.append(("non_export", line))
                    return False
                return stdlib(dotted, origin, name, line)
            ok = base_check(kind, a, b, node, dotted, origin, name)
            return engine(dotted, name, line) and ok
        if _dotted_builtin(a):
            return True         # no prefix resolves: the builtin's name
        return base(kind, a, b, node)

    return check


def _bridge_admitted(fullname: str, path: str, data: bytes) -> bool:
    """True when the module at *path* is an allowed bridge: named in
    ``allow_bridges`` AND approved, with exactly this content, by the
    Python-bridge gate for a ``.clausal`` importer whose project allowlists
    it (``python_bridges.APPROVED_BRIDGES``).  Loaded any other way -- by
    Python directly, by a ``.seam`` -- it has no importer project: refused."""
    import hashlib  # noqa: PLC0415
    from clausal.python_bridges import APPROVED_BRIDGES  # noqa: PLC0415
    real = os.path.realpath(path)
    sha = hashlib.sha256(data).hexdigest()
    if APPROVED_BRIDGES.get(real) != sha:
        return False
    return any(p == real and (h is None or h == sha)
               for _raw, p, h in _STATE.bridges)


def _diagnostic_routes(text: str, path: str) -> list:
    """The compiler record's and the ``--`` pre-scan's routes of the
    ``.seam`` source *text* (the bridge gate's diagnostics; they only ADD
    routes)."""
    from clausal import python_bridges as pb  # noqa: PLC0415
    from clausal.templating.term_rewriting import (  # noqa: PLC0415
        EmbedTransformer)
    routes = []
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tree = ast.parse(text, filename=path)
            transformer = EmbedTransformer(
                source_lines=text.splitlines(keepends=True), filename=path)
            transformer.visit(tree)
        record = getattr(transformer, "_external_refs", None)
    except Exception:  # noqa: BLE001 -- does not compile: fail closed
        record = None
    if record is None:
        return [("uncompilable", 0)]
    routes += pb._check_refs(record)[0]
    try:
        routes += [r for r in pb.python_routes(ast.parse(text), text)
                   if r[0] == "seam"]
    except SyntaxError:
        routes.append(("uncompilable", 0))
    return routes


def _describe(routes) -> str:
    from clausal.python_bridges import ROUTE_KINDS  # noqa: PLC0415
    seen = []
    for kind, line in sorted(set(routes), key=lambda r: (r[1], r[0])):
        text = ROUTE_KINDS.get(kind) or _ROUTE_TEXT.get(kind, kind)
        seen.append(f"{kind} at line {line} ({text})" if line
                    else f"{kind} ({text})")
    return "; ".join(seen)       # every site: a refusal is read to be fixed


_LOADING = threading.local()


def _loading_file() -> "str | None":
    stack = getattr(_LOADING, "stack", None)
    return stack[-1] if stack else None


def sandboxed_code(loader, fullname: str):
    """See :func:`_sandboxed_code`; records the file being loaded, so a
    refusal raised while its front end translates names that file."""
    stack = getattr(_LOADING, "stack", None)
    if stack is None:
        stack = _LOADING.stack = []
    stack.append(loader.get_filename(fullname))
    try:
        return _sandboxed_code(loader, fullname)
    finally:
        stack.pop()


def _sandboxed_code(loader, fullname: str):
    """The code object a loader runs for *fullname* in the sandbox, built
    from the source read ONCE here: the final generated tree is audited and
    that very tree is compiled (no bytecode cache, so nothing stale or
    planted runs).  None for an engine-shipped module (its normal path).
    Raises :func:`load_error` on a Python route."""
    from clausal import import_hook as ih  # noqa: PLC0415
    from clausal import python_bridges as pb  # noqa: PLC0415
    from clausal import seam_audit  # noqa: PLC0415
    path = loader.get_filename(fullname)
    if pb.is_engine_shipped(fullname, path):
        return None
    data = loader.get_data(path)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise load_error(path, f"{path} is not UTF-8: {e}") from None
    translations = ()
    extra: list = []
    if isinstance(loader, ih.NativePrologLoader):
        tree, items = loader._lower(text, path)
        loader._last_transformer = ih._NativeItems(items)
    elif isinstance(loader, ih.PrologLoader):
        from clausal.tools.prolog_to_clausal import (  # noqa: PLC0415
            PrologTranslationError)
        from clausal.tools.prolog_parser import ParseError  # noqa: PLC0415
        try:
            seam_text = loader._translate(text)
        except (ParseError, PrologTranslationError) as e:
            raise SyntaxError(f"Cannot import {path}: {e}",
                              (path, 0, 0, "")) from e
        tree, transformer = ih.transform_seam_source(seam_text, path, True)
        transformer._module_items[:0] = ih._prolog_default_items()
        loader._last_transformer = transformer
        translations = getattr(transformer, "_emitted_translations", ())
        items = transformer._module_items
        extra = _diagnostic_routes(seam_text, path)
    else:
        tree, transformer = ih.transform_seam_source(text, path)
        loader._last_transformer = transformer
        translations = getattr(transformer, "_emitted_translations", ())
        items = transformer._module_items
        extra = _diagnostic_routes(text, path)
    routes: list = []
    children: list = []
    denied: list = []
    found, _ = seam_audit.audit_tree(
        tree, _sandbox_checker(routes, children, denied),
        translations=translations or (), module_items=items or (),
        prolog_surface=isinstance(loader, ih.PrologLoader))
    routes = routes + found + extra
    if routes:
        if _bridge_admitted(fullname, path, data):
            _STATE.admitted_bridges.add(os.path.realpath(path))
        else:
            raise load_error(path, (
                f"the sandbox refuses {fullname} ({os.path.abspath(path)}): "
                f"it reaches Python -- {_describe(routes)}"
                f"{'.  ' + _denied_hint(denied) if denied else ''}"
                f".  In a sandbox "
                f"Python is reachable only through the allowed engine "
                f"adapters and the bridges enable(allow_bridges=...) "
                f"names"))
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", message="'str' object is not callable",
            category=SyntaxWarning)
        return compile(tree, path, "exec")


def find_origin(dotted: str) -> "str | None":
    """The source file of the module *dotted* names, found WITHOUT importing
    anything (:func:`clausal.python_bridges._find`: each segment through
    ``sys.meta_path``, a parent's search path from its spec) -- what the
    front ends use in the sandbox instead of ``importlib.util.find_spec``,
    which imports every parent package and so runs its ``__init__``.  None
    when nothing (or a namespace package) answers; a lookup that raised is
    refused."""
    from clausal import python_bridges as pb  # noqa: PLC0415
    origin = pb._find(pb._adapter_path(dotted))
    if origin == pb._UNRESOLVABLE:
        loading = _loading_file() or dotted
        raise load_error(loading, (
            f"the sandbox refuses {loading}: the module {dotted} could not "
            f"be resolved without importing it"))
    return origin


def guard_python_import(dotted: str, what: str = "use_module/1") -> None:
    """Called by the front ends before they import the Python module
    *dotted* while translating a module: in the sandbox only an
    engine-shipped module may be imported (an adapter outside the allowlist
    is refused at run time and by the audit); a module of the user's would
    RUN, so it is refused here, before it is imported."""
    if not _st.ACTIVE:
        return
    from clausal import python_bridges as pb  # noqa: PLC0415
    target = pb._adapter_path(dotted)
    origin = pb._find(target)
    if origin is None:
        return                      # nothing to import: the caller refuses
    loading = _loading_file() or target
    if origin == pb._UNRESOLVABLE or not pb.is_engine_shipped(target, origin):
        raise load_error(loading, (
            f"{what}: the sandbox refuses {loading}: it imports the Python "
            f"module {dotted} ({origin}), which is not the engine's own and "
            f"would run"))
    kind = _engine_reference_ok(target, None)
    if kind is not None and adapter_row(target) is not None:
        raise load_error(loading, (
            f"{what}: the sandbox refuses {loading}: it imports the engine "
            f"adapter {dotted} ({_ROUTE_TEXT[kind]})"))


# ── RUN TIME ────────────────────────────────────────────────────────────────


class _QueryFrame:
    """The caller every Python-side query is resolved as: Clausal Prolog."""
    _dialect_is_clausal_prolog = True

    def __repr__(self):
        return "<sandboxed query>"


#: The frame a sandboxed solve() resolves ``M:G`` as.
QUERY_FRAME = _QueryFrame()

_GATED = "_sandbox_gated_frame"


def gated_caller(obj) -> bool:
    """In the sandbox: whether the frame *obj* (a Module, a Database, a
    namespace, :data:`QUERY_FRAME`) is held to the Clausal Prolog dialect
    gate -- every frame except a ``.pl`` module's and an allowed bridge's
    (fail closed: a frame with no source file is gated)."""
    if obj is QUERY_FRAME:
        return True
    cached = getattr(obj, _GATED, None)
    if cached is not None:
        return cached
    from clausal.logic.dialect_edge import _file_of  # noqa: PLC0415
    from clausal.end_module import SURFACE_PL, surface_of  # noqa: PLC0415
    path = _file_of(obj)
    answer = True
    if path is not None:
        if surface_of(path) == SURFACE_PL:
            answer = False
        elif os.path.realpath(path) in _STATE.admitted_bridges:
            answer = False
    if not isinstance(obj, dict) and not isinstance(obj, type(sys)):
        try:
            setattr(obj, _GATED, answer)
        except (AttributeError, TypeError):
            pass
    return answer


def permits_python_target(target) -> bool:
    """In the sandbox: whether the Python module *target* (a Module /
    Database / module) is an allowed adapter module, which a gated frame
    may reach (its predicates are then checked one by one)."""
    from clausal.logic.dialect_edge import _namespace  # noqa: PLC0415
    md = _namespace(target)
    name = md.get("__name__") if md is not None else None
    path = md.get("__file__") if md is not None else None
    if not isinstance(name, str) or not isinstance(path, str):
        return False
    from clausal.python_bridges import is_engine_shipped  # noqa: PLC0415
    if not is_engine_shipped(name, path):
        return False
    return _engine_reference_ok(name, None) is None and adapter_row(
        name) is not None


def walkable(obj) -> bool:
    """In the sandbox: whether a dotted name may walk INTO *obj* (read an
    attribute of it): only a loaded Clausal module or an allowed adapter
    module.  Reading an attribute of anything else can run Python (a
    module ``__getattr__``, a property), so the walk stops there.  Decided
    from the module's own ``__dict__``, never by ``getattr``."""
    if not isinstance(obj, type(sys)):
        return False
    try:
        ns = object.__getattribute__(obj, "__dict__")
    except AttributeError:
        return False
    if "$module" in ns or "__clausal_module__" in ns:
        return True
    if ns.get("__name__") in _ENGINE_PACKAGES and ns.get("__path__"):
        from clausal.python_bridges import is_engine_shipped  # noqa: PLC0415
        f = ns.get("__file__")
        return isinstance(f, str) and is_engine_shipped(ns["__name__"], f)
    return permits_python_target(obj)


#: The engine packages a dotted name may walk through on its way to an
#: allowed adapter (``py.datetime.date_add`` from ``-import_module``).
_ENGINE_PACKAGES = frozenset({
    "clausal", "clausal.modules", "clausal.modules.py",
    "clausal.modules.countries", "clausal.library",
    "clausal.library.countries", "clausal.stdlib"})


def refuse_unwalkable(base, context: str) -> None:
    """In the sandbox: a dotted goal (or a module designator) whose
    qualifier the walk may not read is refused, whatever frame asks: a
    MODULE (a denied adapter, a Python module of the worker's) is
    ``permission_error(access, python_module, M)``, any other object
    ``permission_error(access, python_object, Type)``."""
    if base is None or walkable(base):
        return
    if isinstance(base, type(sys)):
        from clausal.logic.dialect_edge import edge_error  # noqa: PLC0415
        exc = edge_error("python_module", base, context)
    else:
        # Not a module at all (an object a module binds, a non-module
        # entry of sys.modules): named by its TYPE -- reading anything of
        # the object could run its __getattr__ or a property.
        tname = type(base).__name__
        exc = _access_error(
            "python_object", tname,
            f"a dotted name or a module designator reaches a Python "
            f"{tname}; the sandbox reads attributes only of Clausal and "
            f"allowed adapter modules", context)
    exc.sandbox_refusal = True
    raise exc


def walk_ok(parts) -> bool:
    """In the sandbox: a dotted name may be walked at all -- no segment is
    underscore-led (a qualified name is ``module.name``)."""
    return not any(p.startswith("_") for p in parts)


def _owner_of(obj) -> str:
    """The module that binds the adapter object *obj* (for the error)."""
    for name, mod in list(sys.modules.items()):
        try:
            ns = vars(mod)
        except TypeError:
            continue
        for v in list(ns.values()):
            if v is obj:
                return name
    mod = getattr(obj, "_module", "") or type(obj).__module__
    return mod or "python"


def _adapter_refusal(obj, context: str):
    owner = _owner_of(obj)
    name = getattr(obj, "_name", None) or type(obj).__name__
    row = adapter_row(owner) if isinstance(owner, str) else None
    if row is not None and row.allowed and name in row.denied:
        why = (f"{owner}.{name} is denied in the sandbox ({row.why})")
    elif row is not None:
        why = (f"{owner} is not an allowed adapter in the sandbox "
               f"({row.why})")
    else:
        why = (f"{owner}.{name} is Python ({type(obj).__name__}) and not an "
               f"allowed engine adapter")
    return _access_error("python_module", owner, why, context)


def check_adapter(obj, context: str = "call/1") -> None:
    """Raise unless the engine adapter object *obj* (a ModulePredicate) is
    on the sandbox allowlist."""
    if id(obj) in _STATE.allowed_ids:
        return
    raise _adapter_refusal(obj, context)


def goal_object_permitted(obj) -> bool:
    """Whether the ``_get_dispatch`` implementor *obj* may be dispatched in
    the sandbox: the engine's own machinery (builtins, meta-call goals,
    predicate handles) or an allowed adapter object."""
    if id(obj) in _STATE.allowed_ids:
        return True
    from clausal.modules.py import ModulePredicate  # noqa: PLC0415
    if isinstance(obj, ModulePredicate):
        return False
    mod = type(obj).__module__ or ""
    return mod.startswith("clausal.logic.")


def check_goal_object(obj, context: str = "call/1") -> None:
    """Raise unless :func:`goal_object_permitted`."""
    if not goal_object_permitted(obj):
        raise _adapter_refusal(obj, context)


def check_callable(obj, context: str = "call/1") -> None:
    """A plain Python callable reached as a goal: only the engine's core
    machinery's (``clausal.logic``), never an adapter's function."""
    mod = getattr(obj, "__module__", None) or ""
    if not (isinstance(mod, str) and mod.startswith("clausal.logic.")):
        raise _access_error(
            "python_object", type(obj).__name__,
            f"a Python {type(obj).__name__} is not a goal in the sandbox",
            context)


def _data_leaf_types() -> tuple:
    """The leaf types a sandboxed goal may carry, from the engine's own
    tables: the scalars the Python boundary passes through
    (``python_terms._SCALARS``: atoms are ``str``, numbers, bytes) and the
    numbers the query compiler passes by value (``Decimal``, ``Fraction``,
    ``Quantity``)."""
    from clausal.logic.python_terms import _SCALARS  # noqa: PLC0415
    from clausal.terms import Quantity  # noqa: PLC0415
    return tuple(t for t in _SCALARS if t is not bytearray) + (Quantity,)


_LEAVES = None
_QUANTITY = None
_DICT_TERM = None
_SET_TERM = None
_VAR_MODULES = ("clausal.", "_variables")


def check_term(term, context: str = "solve/1") -> None:
    """Refuse a goal or argument built by Python that carries anything but
    data: atoms, numbers, strings, logic variables (as bound), lists, cells
    (tuples), dicts (a plain dict or the engine's DictTerm), the engine's
    SetTerm, quantities, and an allowed adapter object (a unit).
    Iterative and cycle-safe."""
    global _LEAVES, _QUANTITY, _DICT_TERM, _SET_TERM
    if _LEAVES is None:
        from clausal.terms import DictTerm, Quantity, SetTerm  # noqa: PLC0415
        _QUANTITY = Quantity
        _DICT_TERM, _SET_TERM = DictTerm, SetTerm
        _LEAVES = _data_leaf_types()
    from clausal.logic.variables import Var, deref  # noqa: PLC0415
    leaves = _LEAVES
    stack = [term]
    seen: set = set()
    while stack:
        t = stack.pop()
        if isinstance(t, Var):
            if not type(t).__module__.startswith(_VAR_MODULES):
                raise _access_error(
                    "python_object", type(t).__name__,
                    f"a subclass of the engine's logic variable "
                    f"({type(t).__module__}.{type(t).__name__}) is Python",
                    context)
            t = deref(t)
            if isinstance(t, Var):
                continue
        tt = type(t)
        if tt in leaves:
            if tt is _QUANTITY:
                # A quantity is data all the way down: its magnitude and
                # its dimension map (unit name -> exponent).
                stack.append(t._value)
                stack.extend(t._dims.keys())
                stack.extend(t._dims.values())
            continue
        if tt is tuple or tt is list:
            if id(t) in seen:
                continue
            seen.add(id(t))
            stack.extend(t)
            continue
        if tt is dict:
            if id(t) in seen:
                continue
            seen.add(id(t))
            stack.extend(t.keys())
            stack.extend(t.values())
            continue
        if tt is _DICT_TERM or tt is _SET_TERM:
            # The engine's own dict and set terms (EXACT types: a subclass
            # could carry code): walked like a dict, through their slots,
            # so no method of theirs runs.
            if id(t) in seen:
                continue
            seen.add(id(t))
            if tt is _DICT_TERM:
                stack.extend(t._data.keys())
                stack.extend(t._data.values())
            else:
                stack.extend(t._elements)
            continue
        if isinstance(t, leaves) and tt.__module__ in ("decimal",
                                                       "fractions"):
            continue            # the C/Python twins of Decimal, Fraction
        if id(t) in _STATE.allowed_ids:
            continue
        raise _access_error(
            "python_object", tt.__name__,
            f"a sandboxed goal may hold only atoms, numbers, strings, "
            f"logic variables and compound terms of those; it holds a "
            f"Python {tt.__module__}.{tt.__name__}", context)


def check_query_module(module, context: str = "solve/2") -> None:
    """A sandboxed query runs in a Clausal module: never in a ``.pl`` one
    (a Clausal Prolog frame may not call ISO Prolog) or a Python one."""
    from clausal.logic.dialect_edge import (  # noqa: PLC0415
        edge_error, forbidden_kind)
    kind = forbidden_kind(module)
    if kind == "prolog_module" or (
            kind == "python_module" and not permits_python_target(module)):
        raise edge_error(kind, module, context)


def check_query(goal, module, context: str = "solve/2") -> None:
    """The run-time entry check: the goal's data, then its module."""
    check_term(goal, context)
    if module is not None:
        check_query_module(module, context)


# ── builtins ────────────────────────────────────────────────────────────────


def _refusing_dispatch(name: str, arity: int):
    from clausal.logic.exceptions import permission_error  # noqa: PLC0415
    why = DENIED_BUILTINS.get(name, "denied in the sandbox")
    LogicException = _logic_exception()

    def dispatch(this_generator, _proceed, _fail, _catcher, *args):
        raise LogicException(permission_error(
            "access", "private_procedure", ("/", name, arity),
            f"{name}/{arity}: {name}/{arity} is not available in the "
            f"sandbox ({why})"))
        yield  # pragma: no cover -- a generator, as the protocol wants
    dispatch.__qualname__ = f"sandbox_refused[{name}/{arity}]"
    return dispatch


def _deny_builtins() -> None:
    """Replace every registry entry of a :data:`DENIED_BUILTINS` name, in
    the stateless table, the db table and the builtin objects' own tables,
    with a dispatch raising ``permission_error(access, private_procedure,
    Name/Arity)``."""
    from clausal.logic.builtins import _BUILTIN_CLASSES  # noqa: PLC0415
    from clausal.logic.builtins._registry import (  # noqa: PLC0415
        _BUILTINS, _DB_BUILTINS)
    for key in list(_BUILTINS):
        if key[0] in DENIED_BUILTINS:
            _BUILTINS[key] = _refusing_dispatch(*key)
    for key in list(_DB_BUILTINS):
        if key[0] in DENIED_BUILTINS:
            fn = _refusing_dispatch(*key)
            _DB_BUILTINS[key] = (lambda fn: lambda db: fn)(fn)
    for name, obj in _BUILTIN_CLASSES.items():
        if name not in DENIED_BUILTINS:
            continue
        table = getattr(obj, "_dispatch_by_arity", None)
        if isinstance(table, dict):
            for arity in list(table):
                table[arity] = _refusing_dispatch(name, arity)
        if hasattr(obj, "_multi_dispatch"):
            try:
                obj._multi_dispatch = None
            except AttributeError:
                pass


def halt_refusal_term(arity: int):
    """The ball a sandboxed ``halt/0,1`` throws (the special form's
    lowering raises it instead of SystemExit)."""
    pi = ("/", "halt", arity)
    return ("error", ("permission_error", "access", "private_procedure", pi),
            pi)


def _clear_query_caches() -> None:
    """Compiled queries made before the sandbox was on are not reused."""
    from clausal.logic import solve as _solve  # noqa: PLC0415
    _solve._query_cache.clear()
