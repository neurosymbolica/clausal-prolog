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
      ``set_prolog_flag``, ``op/3``, the stdout writers, the clock
      readers ...) raise
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
    "PACKAGE_ADAPTERS",
    "PackageAdapter",
    "PackageAdapterError",
    "allowed_package_adapters",
    "package_adapter_time_limit",
    "DEFAULT_ADAPTER_TIME_LIMIT",
    "PACKAGE_ADAPTERS_ENV_VAR",
    "ADAPTER_TIME_LIMIT_ENV_VAR",
]

#: The environment variable read at engine import: ``1``/``true``/``yes``/
#: ``on`` turns the sandbox on; ``0``/``false``/``no``/``off`` or unset
#: leaves it off; anything else is an ImportError (never a silent default).
ENV_VAR = "CLAUSAL_SANDBOX"

#: Comma-separated :data:`PACKAGE_ADAPTERS` names a child turns on with the
#: sandbox (``enable(allow_package_adapters=...)``); read only with
#: :data:`ENV_VAR` on, and an error without it.
PACKAGE_ADAPTERS_ENV_VAR = "CLAUSAL_SANDBOX_PACKAGE_ADAPTERS"

#: Seconds, or ``none``: the per-call budget of a vetted package adapter
#: (``enable(package_adapter_time_limit=...)``).
ADAPTER_TIME_LIMIT_ENV_VAR = "CLAUSAL_SANDBOX_ADAPTER_TIME_LIMIT"

_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"", "0", "false", "no", "off"})


# ── the adapter classification ──────────────────────────────────────────────


@dataclass(frozen=True)
class Adapter:
    """One engine adapter module's sandbox classification.

    *allowed*: the module is pure computation (no filesystem, process,
    network, environment, clock or randomness, logging/I/O, database or
    reflection); *denied*: the predicates of an allowed module that are NOT
    (``datetime``'s clock readers); *why*: the evidence, in a sentence.

    *constructors*: the module's plain Python TERM CONSTRUCTORS (functions
    the compiler calls to build a cell, not registered predicates) that a
    sandboxed module may ``-import_from`` the adapter while it is allowed.
    Each entry is reviewed: a function the module itself defines under that
    name, with no clock, I/O, host time zone or other state, that returns
    data built from its arguments (see :func:`sandbox_constructor`).
    Nothing else the module binds (its helpers, its own imports) is ever
    importable."""
    module: str
    allowed: bool
    why: str
    denied: frozenset = frozenset()
    constructors: frozenset = frozenset()


_PY = "clausal.modules.py."

#: Every engine adapter module, classified by its side effects (survey of
#: 2026-10-05; ``tests/test_sandbox.py`` fails when an engine adapter module
#: has no row, so a new adapter is denied until it is classified here).
ADAPTERS: "dict[str, Adapter]" = {a.module: a for a in (
    Adapter(_PY + "datetime", True,
            "date/time arithmetic and formatting; now/1, now_utc/1 and "
            "today/1 read the clock and timestamp/2 depends on the host "
            "time zone",
            frozenset({"now", "now_utc", "today", "timestamp"}),
            # date/3, the date TERM constructor: it validates (Y, M, D)
            # through datetime.date and returns the cell ('date', Y, M, D)
            # of its own arguments (an ISO type_error/domain_error for a
            # non-date); no clock, I/O or time zone.  (time, datetime and
            # timedelta are registered predicates, judged as such.)
            constructors=frozenset({"date"})),
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


# ── vetted package adapters (operator ruling 2026-11-04) ────────────────────


@dataclass(frozen=True)
class PackageAdapter:
    """One optional package's adapter that the sandbox may admit, by name,
    when ``enable(allow_package_adapters=[name])`` asks for it: a trust kind
    of its own, narrower than a bridge (operator ruling 2026-11-04, "vetted
    package: yes"; ``implementation_plans/sympy-package-adapter-sandbox-
    2026-11-04.md``).

    Only the engine's own table names one -- a project's ``pyproject.toml``
    cannot -- and :func:`enable` verifies every pin before anything is
    imported, failing closed (:class:`PackageAdapterError`):

    *files*: ``(module, sha256)`` of every Python file of the package the
    adapter runs, executed from exactly the bytes hashed;
    *distribution*/*version*: the package's own distribution;
    *third_party*: ``(distribution, version, top-level package)`` of each
    library it imports, whose installed metadata must describe the package
    on the path;
    *predicates*: the registered predicate names a ``.seam`` may
    ``-import_from`` it -- nothing else it binds (its term constructors, its
    raw library objects) is importable, and the importing module must still
    be Python-free;
    *reset*: the name of a function here run after a call ran out of its
    budget (state an interrupted call may have left half written)."""
    name: str
    module: str
    distribution: str
    version: str
    files: tuple
    third_party: tuple
    predicates: frozenset
    why: str
    reset: "str | None" = None


#: The vetted package adapters.  A row is added or re-pinned only by engine
#: review, with a CHANGELOG entry (docs/sandbox.md, "Re-pinning a vetted
#: package adapter"); ``tests/test_sandbox_package_adapters.py`` prints the
#: pins of the files on disk when they no longer match.
PACKAGE_ADAPTERS: "dict[str, PackageAdapter]" = {a.name: a for a in (
    PackageAdapter(
        "sympy", _PY + "sympy", "clausal-sympy", "0.1.0",
        files=(
            (_PY + "sympy",
             "5b9a657d123386af35a51a86a1635093a8855df87f94704937e293a661e285ab"),
            (_PY + "_sympy_units",
             "3c69993c20326e5a9c05e4d118c9b45823591d51066dcd3931d63669a0d22a97"),
        ),
        third_party=(("sympy", "1.14.0", "sympy"),
                     ("mpmath", "1.3.0", "mpmath")),
        # Symbolic algebra over terms.  Not: sym/2 (names a symbol from
        # text), the printers, number theory, sums/products, and every
        # constructor and raw SymPy object the module binds (sin, log, pi,
        # e, inf, ...): an ISO cell such as log(X) converts without them.
        predicates=frozenset({
            "simplify", "expand", "factor", "cancel", "apart", "together",
            "collect", "trig_simp", "expand_trig",
            "solve", "solve_all", "roots",
            "diff", "integrate", "limit", "series", "subs", "free_vars",
            "degree", "coeffs", "sym_equal", "sym_str", "sympy_term"}),
        why=("symbolic algebra over the given terms; the converter refuses "
             "anything it has no case for (no sympify, no eval), pinned by "
             "TestNoEvalFallback"),
        reset="_reset_sympy"),
)}

#: The default per-call budget, in seconds, of a vetted package adapter
#: call under the sandbox: SymPy has no timeout of its own, and one solve
#: can run for minutes.  Above what an ordinary producer equation takes --
#: the log mean temperature difference solved backwards with integer data,
#: the slowest case in the package's own suite, takes 8.5-9.5 s on the
#: development machine -- with room for a loaded machine; and under the
#: 20 s wall clock a sandboxed worker child is usually given, so a runaway
#: call is reported as the ball ``time_limit_exceeded`` while the child
#: still has time to say so, instead of the child being killed.
DEFAULT_ADAPTER_TIME_LIMIT = 15.0


class PackageAdapterError(RuntimeError):
    """:func:`enable` refused a vetted package adapter: a pin does not hold.
    ``.reason`` names which (``sha256_mismatch``, ``version_mismatch``,
    ``distribution_mismatch``, ``impostor_module``, ``not_found``); the
    message starts with it in brackets."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(f"[{reason}] clausal.sandbox.enable: {message}")
        self.reason = reason


def _reset_sympy() -> None:
    """After a SymPy call ran out of its budget: the alarm may have landed
    inside a function that was filling one of SymPy's caches or running
    with mpmath's precision raised.  SymPy's ``cacheit`` caches store a
    result only when the call returns (an interrupted call stores nothing),
    and mpmath restores its precision in ``finally`` blocks, but not every
    SymPy path is written that way, so the caches are emptied and mpmath's
    working precision put back to its default -- a later call recomputes
    instead of trusting state an interrupted one left."""
    import sympy  # noqa: PLC0415
    import mpmath  # noqa: PLC0415
    sympy.core.cache.clear_cache()
    mpmath.mp.prec = 53
    mpmath.mp.pretty = False


def _package_adapter_entries(spec) -> "tuple[tuple[str, tuple], ...]":
    """``allow_package_adapters`` as ``((name, importers), ...)``: each entry
    a :data:`PACKAGE_ADAPTERS` name, or ``{"name": ..., "importers": [...]}``
    naming the only ``.seam`` files that may import it (paths, or
    ``{"path": ..., "sha256": ...}``)."""
    import re  # noqa: PLC0415
    if spec is None:
        return ()
    if isinstance(spec, str):
        raise TypeError("clausal.sandbox.enable: allow_package_adapters is "
                        "a sequence of adapter names, not a string")
    out = []
    for raw in spec:
        importers = None
        name = raw
        if isinstance(raw, dict):
            if set(raw) - {"name", "importers"} or "name" not in raw:
                raise ValueError(f"clausal.sandbox.enable: the package "
                                 f"adapter {raw!r} takes name and, "
                                 f"optionally, importers")
            name = raw["name"]
            imps = []
            for imp in raw.get("importers") or ():
                sha = None
                path = imp
                if isinstance(imp, dict):
                    if set(imp) - {"path", "sha256"} or "path" not in imp:
                        raise ValueError(f"clausal.sandbox.enable: the "
                                         f"importer {imp!r} takes path and, "
                                         f"optionally, sha256")
                    path, sha = imp["path"], imp.get("sha256")
                    if sha is not None and not (
                            isinstance(sha, str)
                            and re.fullmatch(r"[0-9a-fA-F]{64}", sha)):
                        raise ValueError(f"clausal.sandbox.enable: {imp!r}: "
                                         f"sha256 must be 64 hex digits")
                if not isinstance(path, str) or not path:
                    raise TypeError(f"clausal.sandbox.enable: an importer "
                                    f"is a path, got {imp!r}")
                imps.append((os.path.realpath(path), sha and sha.lower()))
            importers = tuple(imps)
        if not isinstance(name, str) or name not in PACKAGE_ADAPTERS:
            raise ValueError(
                f"clausal.sandbox.enable: {name!r} is not a vetted package "
                f"adapter (vetted: {', '.join(sorted(PACKAGE_ADAPTERS))})")
        out.append((name, importers))
    return tuple(out)


def _sha256_file(path: str) -> "tuple[bytes, str]":
    import hashlib  # noqa: PLC0415
    with open(path, "rb") as f:
        data = f.read()
    return data, hashlib.sha256(data).hexdigest()


def _real(path) -> str:
    return os.path.realpath(str(path))


def _module_file(mod) -> "str | None":
    try:
        ns = object.__getattribute__(mod, "__dict__")
    except AttributeError:
        return None
    f = ns.get("__file__")
    return f if isinstance(f, str) else None


def _locate(module: str) -> "str | None":
    """The file the path finders would load *module* from, asked WITHOUT
    ``sys.modules`` for *module* itself (an entry there is what
    :func:`_check_not_impostor` judges) and without importing anything but
    its engine parent package."""
    import importlib  # noqa: PLC0415
    from importlib.machinery import PathFinder  # noqa: PLC0415
    parent, dot, _leaf = module.rpartition(".")
    try:
        if dot:
            path = list(importlib.import_module(parent).__path__)
            spec = PathFinder.find_spec(module, path)
        else:
            spec = PathFinder.find_spec(module)
    except Exception:  # noqa: BLE001 -- fail closed
        return None
    return getattr(spec, "origin", None) if spec is not None else None


def _check_not_impostor(module: str, origin: str) -> None:
    """Refuse when ``sys.modules`` already holds *module* from another file
    than *origin* (or no file)."""
    mod = sys.modules.get(module)
    if mod is None:
        return
    f = _module_file(mod)
    if f is None or _real(f) != _real(origin):
        raise PackageAdapterError(
            "impostor_module",
            f"sys.modules already holds {module} from {f!r}, not from the "
            f"pinned file {origin}; enable the sandbox before anything "
            f"imports it")


def _dist_owns(dist, rel: str, origin: str) -> bool:
    """Whether the installed distribution *dist* lists *rel* (a path inside
    site-packages) and it is the file *origin*; or, installed editable,
    whether *origin* lies in the source tree it points at."""
    import json  # noqa: PLC0415
    try:
        files = dist.files or ()
    except Exception:  # noqa: BLE001 -- unreadable metadata: not owned
        files = ()
    for f in files:
        if str(f).replace(os.sep, "/") == rel:
            try:
                if _real(dist.locate_file(f)) == _real(origin):
                    return True
            except Exception:  # noqa: BLE001
                pass
    try:
        raw = dist.read_text("direct_url.json")
        info = json.loads(raw) if raw else {}
    except Exception:  # noqa: BLE001
        info = {}
    url = info.get("url", "") if isinstance(info, dict) else ""
    editable = (isinstance(info, dict)
                and (info.get("dir_info") or {}).get("editable"))
    if editable and url.startswith("file://"):
        root = _real(url[len("file://"):])
        return _real(origin).startswith(root + os.sep)
    return False


def _source_tree_version(origin: str, distribution: str, depth: int
                         ) -> "str | None":
    """In a source checkout (no distribution installed): the version the
    ``pyproject.toml`` *depth* directories above *origin* declares, when
    its project name is *distribution*."""
    import tomllib  # noqa: PLC0415
    root = os.path.dirname(_real(origin))
    for _ in range(depth):
        root = os.path.dirname(root)
    try:
        with open(os.path.join(root, "pyproject.toml"), "rb") as f:
            project = tomllib.load(f).get("project", {})
    except (OSError, ValueError):
        return None
    if project.get("name") != distribution:
        return None
    v = project.get("version")
    return v if isinstance(v, str) else None


def _verify_distribution(distribution: str, version: str, rel: str,
                         origin: str, source_depth: "int | None") -> None:
    """The distribution *distribution* is installed at *version* and owns
    the file *origin* (``rel`` inside site-packages) -- or, with
    *source_depth*, the source tree *origin* lies in declares them."""
    import importlib.metadata as md  # noqa: PLC0415
    try:
        dist = md.distribution(distribution)
    except md.PackageNotFoundError:
        dist = None
    if dist is not None:
        got = dist.version
        if got != version:
            raise PackageAdapterError(
                "version_mismatch",
                f"{distribution} {got} is installed; the sandbox vets "
                f"{distribution}=={version}")
        if _dist_owns(dist, rel, origin):
            return
    if source_depth is not None:
        got = _source_tree_version(origin, distribution, source_depth)
        if got is not None:
            if got != version:
                raise PackageAdapterError(
                    "version_mismatch",
                    f"the source tree of {origin} is {distribution} {got}; "
                    f"the sandbox vets {distribution}=={version}")
            return
    if dist is None:
        raise PackageAdapterError(
            "not_found", f"no {distribution} distribution is installed")
    raise PackageAdapterError(
        "distribution_mismatch",
        f"the installed {distribution} {dist.version} metadata does not "
        f"describe {origin}, the file on the path")


def _verify_package_adapter(row: PackageAdapter) -> "tuple[dict, tuple]":
    """Every pin of *row*, checked before anything of it is imported, then
    its modules executed from the very bytes hashed.  Returns ``({id:
    predicate}, modules)``.  Raises :class:`PackageAdapterError`."""
    import importlib.util  # noqa: PLC0415
    from clausal.modules.py import ModulePredicate  # noqa: PLC0415
    sources = []
    for module, pin in row.files:
        origin = _locate(module)
        if not (isinstance(origin, str) and origin.endswith(".py")
                and os.path.isfile(origin)):
            raise PackageAdapterError(
                "not_found", f"{module} resolves to no Python file "
                             f"({origin!r}); is {row.distribution} installed?")
        _check_not_impostor(module, origin)
        data, sha = _sha256_file(origin)
        if sha != pin:
            raise PackageAdapterError(
                "sha256_mismatch",
                f"{origin} has sha256 {sha}; the sandbox vets {module} at "
                f"{pin}.  A changed adapter needs engine review and a new "
                f"pin (docs/sandbox.md)")
        sources.append((module, origin, data))
    adapter_origin = sources[0][1]
    _verify_distribution(row.distribution, row.version,
                         row.module.replace(".", "/") + ".py",
                         adapter_origin, source_depth=3)
    for dist_name, version, top in row.third_party:
        origin = _locate(top)
        if not (isinstance(origin, str) and origin.endswith(".py")):
            raise PackageAdapterError(
                "not_found", f"the {top} package resolves to {origin!r}")
        _check_not_impostor(top, origin)
        _verify_distribution(dist_name, version, f"{top}/__init__.py",
                             origin, source_depth=None)
    # Execute the hashed bytes themselves (never a bytecode cache, never a
    # second read): helpers first, so the adapter's own import finds them.
    import clausal.modules.py as parent  # noqa: PLC0415
    loaded = []
    for module, origin, data in reversed(sources):
        mod = sys.modules.get(module)
        if mod is None:
            spec = importlib.util.spec_from_file_location(module, origin)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[module] = mod
            try:
                exec(compile(data, origin, "exec"), vars(mod))  # noqa: S102
            except BaseException:
                sys.modules.pop(module, None)
                raise
            setattr(parent, module.rpartition(".")[2], mod)
        loaded.append(mod)
    adapter = sys.modules[row.module]
    ns = vars(adapter)
    preds = {}
    for name in sorted(row.predicates):
        obj = ns.get(name)
        if type(obj) is not ModulePredicate or obj._name != name:
            raise PackageAdapterError(
                "not_found", f"{row.module}.{name} is not the predicate the "
                             f"table vets ({type(obj).__name__})")
        preds[id(obj)] = obj
    return preds, tuple(loaded)


def allowed_package_adapters() -> frozenset:
    """The vetted package adapters (:data:`PACKAGE_ADAPTERS` names) turned
    on; empty while the sandbox is off."""
    return frozenset(_STATE.packages)


def package_adapter_time_limit() -> "float | None":
    """The per-call budget, in seconds, of a vetted package adapter call
    (None: unbudgeted)."""
    return _STATE.adapter_budget


def vetted_import(dotted: str, name: "str | None") -> bool:
    """In the sandbox: True when *name*, imported from *dotted*, is a
    listed predicate of a vetted package adapter turned on now, still bound
    to the very object :func:`enable` admitted.  The ONE question the load
    audits ask (here and in :mod:`clausal.python_bridges`): only an
    ``-import_from`` of such a name counts as clean -- ``-import_module``,
    a dotted ``py.sympy.x`` and every other name stay routes."""
    if not _st.ACTIVE or not name:
        return False
    for row_name in _STATE.packages:
        row = PACKAGE_ADAPTERS[row_name]
        if dotted != row.module or name not in row.predicates:
            continue
        mod = sys.modules.get(dotted)
        if mod is None or mod not in _STATE.package_modules:
            return False
        obj = vars(mod).get(name)
        return obj is not None and id(obj) in _STATE.allowed_ids
    return False


def vetted_reference(kind: str, a: str, b, node) -> bool:
    """In the sandbox: whether the load audit's module question *(kind, a,
    b)* about the generated *node* is exactly what an ``-import_from`` of
    listed vetted predicates lowers to (:func:`vetted_import`):

    * the ``from <module> import n, ...`` statement itself, every name
      listed (``-import_module`` lowers to ``import <module>``: refused);
    * a use of an imported name, which the import rewrite spells as ONE
      dotted ``LoadName`` (``py.sympy.solve``) -- a dotted reference
      written in the source is a ``LoadAttr`` chain: refused;
    * the bridge gate's ``name`` question for one imported name."""
    if not _st.ACTIVE or not _STATE.packages:
        return False
    from clausal import python_bridges as pb  # noqa: PLC0415
    if kind == "name":
        return vetted_import(pb._module_path(a), b)
    if kind == "module":
        if not (isinstance(node, ast.ImportFrom) and node.level == 0
                and node.module == a and node.names):
            return False
        dotted = pb._module_path(a)
        return all(al.name != "*" and vetted_import(dotted, al.name)
                   for al in node.names)
    if kind == "chain":
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "$LoadName"):
            return False
        head, dot, name = a.rpartition(".")
        return bool(dot) and vetted_import(pb._module_path(head), name)
    return False


def _importer_admitted(path: str, data: bytes) -> "str | None":
    """None when the module at *path* may import every vetted package
    adapter it uses; else the adapter whose ``importers`` list leaves it
    out."""
    import hashlib  # noqa: PLC0415
    real = os.path.realpath(path)
    sha = hashlib.sha256(data).hexdigest()
    for name, importers in _STATE.packages.items():
        if importers is None:
            continue
        if not any(p == real and (h is None or h == sha)
                   for p, h in importers):
            return name
    return None


def adapter_budget(obj) -> "tuple[float, object] | None":
    """In the sandbox: ``(seconds, reset)`` when the predicate object *obj*
    is a vetted package adapter's and its calls are budgeted (*reset*: the
    row's state repair after a timeout, or None), else None."""
    budget = _STATE.adapter_budget
    if budget is None:
        return None
    hit = _STATE.budgeted.get(id(obj))
    return None if hit is None else (budget, hit)


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
    "char_conversion": "changes the process-wide character conversion table",
    "op": "changes the process-wide operator table",
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
    "print": "writes to stdout",
    "print_term": "writes to stdout",
    "portray_clause": "writes to stdout",
    "listing": "writes to stdout",
    "format": "writes to stdout",
    "nl": "writes to stdout",
    "tab": "writes to stdout",
    # ISO streams (8.11-8.14): file access and the process's standard
    # streams are I/O like the writers above, refused the same way.
    "open": "opens a file",
    "close": "closes a stream",
    "current_input": "reads the process's stream table",
    "current_output": "reads the process's stream table",
    "set_input": "changes the process's current input stream",
    "set_output": "changes the process's current output stream",
    "flush_output": "writes to a stream",
    "at_end_of_stream": "reads a stream",
    "set_stream_position": "repositions a file",
    "stream_property": "reads the process's stream table",
    "get_char": "reads a stream",
    "get_code": "reads a stream",
    "peek_char": "reads a stream",
    "peek_code": "reads a stream",
    "put_char": "writes to a stream",
    "put_code": "writes to a stream",
    "get_byte": "reads a stream",
    "peek_byte": "reads a stream",
    "put_byte": "writes to a stream",
    "read": "reads a stream",
    "read_term": "reads a stream",
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
    ("clausal.logic.coroutining", "WHEN_KEY"),
    ("clausal.logic.constraints", "DIF_KEY"),
    ("clausal.logic.clpfd", "FD_KEY"),
    ("clausal.logic.clpfd", "ZCMP_KEY"),
    ("clausal.logic.clpb", "B_KEY"),
    ("clausal.logic.clpq.legacy", "Q_KEY"),
    ("clausal.logic.clpq.attributes", "CLPQ_KEY"),
    ("clausal.logic.clpq.components", "COMPONENT_KEY"),
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
                 "keep", "admitted_bridges", "lock", "attr_keys",
                 "packages", "package_modules", "adapter_budget", "budgeted",
                 "package_preds")

    def __init__(self):
        # Vetted package adapters (operator ruling 2026-11-04): name ->
        # importers (None: any Python-free .seam); the modules enable()
        # executed; the per-call budget; predicate id -> reset (or None).
        self.packages: dict = {}
        self.package_modules: tuple = ()
        self.adapter_budget: "float | None" = None
        self.budgeted: dict = {}
        self.package_preds: dict = {}   # name -> {id: predicate object}
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


_KEEP = object()


def enable(allow_adapters=None, allow_bridges=(), allow_package_adapters=None,
           package_adapter_time_limit=_KEEP) -> None:
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

    *allow_package_adapters*: the vetted package adapters
    (:data:`PACKAGE_ADAPTERS` names, e.g. ``["sympy"]``) a Python-free
    ``.seam`` may ``-import_from`` -- their listed predicates only -- each a
    name or ``{"name": ..., "importers": [path | {"path", "sha256"}]}``
    naming the only files that may import it (operator ruling 2026-11-04).
    Every pin of the row is verified before anything of it is imported:
    a pin that does not hold raises :class:`PackageAdapterError` and leaves
    the sandbox off.  *package_adapter_time_limit*: the wall-clock budget,
    in seconds, of each call of such a predicate (default
    :data:`DEFAULT_ADAPTER_TIME_LIMIT`; None for none): running out throws
    the ball ``time_limit_exceeded`` (:mod:`clausal.logic.time_limit`).

    Fails closed with ``RuntimeError`` when a Clausal module of the user's
    is already loaded (it was not checked).  Calling it again only narrows
    (a name outside the current lists, a package adapter not on now, or a
    longer budget raises ``PermissionError``)."""
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
        packages, budget = _narrow_packages(allow_package_adapters,
                                            package_adapter_time_limit)
        # Everything that can fail is computed BEFORE any state changes, so
        # a failed enable() leaves no half-on sandbox behind (the adapter
        # set is read by sandbox_constructor and the bridge gate).
        ids, keep = _collect_allowed(wanted)
        attr_keys = _engine_attr_keys() if not _st.ACTIVE else None
        preds = dict(_STATE.package_preds)
        modules = list(_STATE.package_modules)
        if not _st.ACTIVE:
            for name in packages:
                preds[name], mods = _verify_package_adapter(
                    PACKAGE_ADAPTERS[name])
                modules.extend(mods)
        budgeted = {}
        for name in packages:
            row = PACKAGE_ADAPTERS[name]
            reset = globals()[row.reset] if row.reset else _no_reset
            for i in preds[name]:
                budgeted[i] = reset
        pkg_ids = frozenset(budgeted)
        pkg_keep = tuple(o for name in packages
                         for o in preds[name].values())
        _STATE.adapters = wanted
        _STATE.bridges = bridges
        _STATE.allowed_ids = ids | pkg_ids
        _STATE.keep = keep + pkg_keep
        _STATE.packages = packages
        _STATE.package_preds = {n: preds[n] for n in packages}
        _STATE.package_modules = tuple(modules)
        _STATE.adapter_budget = budget
        _STATE.budgeted = budgeted
        _clear_audits()
        if not _st.ACTIVE:
            _STATE.attr_keys = attr_keys
            _install_finders()
            _deny_builtins()
            _clear_query_caches()
            _st.ACTIVE = True


def _no_reset() -> None:
    pass


def _narrow_packages(spec, budget) -> "tuple[dict, float | None]":
    """The package adapters and budget an :func:`enable` call asks for, as
    ``({name: importers}, seconds)``; on a second call only a narrowing
    (``PermissionError`` otherwise)."""
    from clausal.logic.time_limit import check_seconds  # noqa: PLC0415
    from clausal.logic.exceptions import LogicException  # noqa: PLC0415
    entries = _package_adapter_entries(spec)
    current = dict(_STATE.packages)
    if spec is None:
        packages = current if _st.ACTIVE else {}
    else:
        packages = {}
        for name, importers in entries:
            if _st.ACTIVE:
                if name not in current:
                    raise PermissionError(
                        f"clausal.sandbox.enable: the sandbox is already on "
                        f"and the package adapter {name} is not on; a "
                        f"second enable() may only narrow")
                old = current[name]
                if importers is None:
                    importers = old
                elif old is not None and not all(
                        e in old or (e[0], None) in old for e in importers):
                    # Each importer must be one of the old list's, or the
                    # pinned form of an unpinned one.
                    raise PermissionError(
                        f"clausal.sandbox.enable: the importers of {name} "
                        f"may only narrow")
            packages[name] = importers
    if budget is _KEEP:
        budget = (_STATE.adapter_budget if _st.ACTIVE
                  else DEFAULT_ADAPTER_TIME_LIMIT)
    elif budget is not None:
        try:
            budget = check_seconds(budget, "enable/1")
        except LogicException as e:
            raise ValueError(f"clausal.sandbox.enable: "
                             f"package_adapter_time_limit {budget!r}: "
                             f"{e}") from None
    if _st.ACTIVE and _STATE.adapter_budget is not None and (
            budget is None or budget > _STATE.adapter_budget):
        raise PermissionError(
            f"clausal.sandbox.enable: the package adapter time limit is "
            f"{_STATE.adapter_budget} s; a second enable() may only shorten "
            f"it")
    return packages, budget


def _clear_audits() -> None:
    """The bridge gate's memoised audits ask the vetted-import question
    again on a hit; emptied anyway whenever the lists change."""
    from clausal import python_bridges as _pb  # noqa: PLC0415
    with _pb._AUDITS_LOCK:
        _pb._AUDITS.clear()


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
    """Called at engine import: ``CLAUSAL_SANDBOX``, and with it
    ``CLAUSAL_SANDBOX_PACKAGE_ADAPTERS`` (comma-separated vetted package
    adapter names) and ``CLAUSAL_SANDBOX_ADAPTER_TIME_LIMIT`` (seconds, or
    ``none``) -- so a parent opts a sandboxed child in through its
    environment.  A setting that is not one is an ImportError, never a
    silent default."""
    raw = os.environ.get(ENV_VAR, "").strip().lower()
    packages = os.environ.get(PACKAGE_ADAPTERS_ENV_VAR, "").strip()
    limit = os.environ.get(ADAPTER_TIME_LIMIT_ENV_VAR, "").strip()
    if raw in _FALSE:
        if packages or limit:
            raise ImportError(
                f"{PACKAGE_ADAPTERS_ENV_VAR} / {ADAPTER_TIME_LIMIT_ENV_VAR} "
                f"are set but {ENV_VAR} is not on: they configure the "
                f"sandbox, so set {ENV_VAR}=1 too (or unset them)")
        return
    if raw not in _TRUE:
        raise ImportError(f"{ENV_VAR}={os.environ.get(ENV_VAR)!r} is not a "
                          f"sandbox setting; use 1 (on) or 0 (off)")
    kwargs = {}
    if packages:
        names = [n.strip() for n in packages.split(",") if n.strip()]
        bad = [n for n in names if n not in PACKAGE_ADAPTERS]
        if bad:
            raise ImportError(
                f"{PACKAGE_ADAPTERS_ENV_VAR}={packages!r}: "
                f"{', '.join(bad)} is not a vetted package adapter "
                f"(vetted: {', '.join(sorted(PACKAGE_ADAPTERS))})")
        kwargs["allow_package_adapters"] = names
    if limit:
        if limit.lower() == "none":
            kwargs["package_adapter_time_limit"] = None
        else:
            try:
                kwargs["package_adapter_time_limit"] = float(limit)
            except ValueError:
                raise ImportError(
                    f"{ADAPTER_TIME_LIMIT_ENV_VAR}={limit!r} is not a "
                    f"number of seconds (or none)") from None
    try:
        enable(**kwargs)
    except (PackageAdapterError, ValueError) as e:
        raise ImportError(f"{ENV_VAR}=1: {e}") from e


# ── errors ──────────────────────────────────────────────────────────────────


def _logic_exception():
    from clausal.logic.exceptions import LogicException  # noqa: PLC0415
    return LogicException


class SandboxLoadError(ImportError):
    """A module the sandbox refuses to load, carrying the ISO term of the
    refusal as ``.term``: ``error(permission_error(load, python_escape,
    File), load/1)`` for a Python escape (:func:`load_error`), or the
    refused goal's ``error(permission_error(access, private_procedure,
    set_prolog_flag/2), set_prolog_flag/2)`` for a load-time
    ``set_prolog_flag`` directive (:func:`refusal_load_error`).  A
    :class:`~clausal.logic.exceptions.LogicException` too (the class is
    rebuilt with that base on first use), so a host catching ImportError,
    LogicException or SandboxLoadError around an import catches it."""


_LOAD_ERROR_CLASS = None


def _load_error_class():
    global _LOAD_ERROR_CLASS
    from clausal.logic.exceptions import LogicException  # noqa: PLC0415
    if _LOAD_ERROR_CLASS is None:
        _LOAD_ERROR_CLASS = type("SandboxLoadError",
                                 (LogicException, SandboxLoadError), {})
        _LOAD_ERROR_CLASS.__module__ = __name__
    return _LOAD_ERROR_CLASS


def load_error(path: str, why: str) -> Exception:
    """The :class:`SandboxLoadError` (an ImportError AND a LogicException)
    refusing the module at *path*."""
    from clausal.logic.exceptions import permission_error  # noqa: PLC0415
    term = permission_error("load", "python_escape", os.path.abspath(path),
                            f"load/1: {why}")
    return _load_error_class()(term)


def refusal_load_error(term) -> Exception:
    """The :class:`SandboxLoadError` (an ImportError AND a LogicException)
    whose term is *term*: a load the sandbox refuses for a directive
    (``clausal.logic.builtins.flags.sandbox_refusal``), raised as such so
    a host that catches ImportError or LogicException around an import
    catches it."""
    return _load_error_class()(term)


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


def sandbox_constructor(dotted: str, name: "str | None") -> bool:
    """True when *name*, imported from the engine module *dotted*, is a
    reviewed pure term constructor (:attr:`Adapter.constructors`) of an
    adapter the sandbox ALLOWS now (under ``enable(allow_adapters=...)``).

    Fail closed: *dotted* must be the adapter module itself (not a
    ``library(...)`` facade, which does not re-export constructors), the
    name must not be denied or underscore-led, and the module must bind it
    to the very function it defines under that name -- not a re-export,
    a class, a predicate object or anything rebound later."""
    import types  # noqa: PLC0415
    if (not _st.ACTIVE or not name or name.startswith("_")
            or dotted.startswith(_FACADES)):
        return False
    row = adapter_row(dotted)
    if (row is None or name not in row.constructors or name in row.denied
            or _canonical(dotted) not in _STATE.adapters):
        return False
    mod = sys.modules.get(dotted)
    if mod is None:
        import importlib  # noqa: PLC0415
        try:
            mod = importlib.import_module(dotted)
        except Exception:  # noqa: BLE001 -- unreadable: no constructor
            return False
    fn = vars(mod).get(name)
    return (type(fn) is types.FunctionType
            and fn.__module__ == _SHIMS.get(dotted, dotted)
            and fn.__qualname__ == name)


def check_constructor(module: str, name: str, context: str) -> None:
    """At CALL time, in the sandbox: raise unless *name* is still a
    constructor of an adapter allowed NOW.  A module compiled before a
    narrowing ``enable(allow_adapters=...)`` calls the constructor
    directly, so the constructor itself asks, as a registered predicate's
    dispatch does (:func:`check_adapter`)."""
    row = adapter_row(module)
    if (row is not None and name in row.constructors
            and _canonical(module) in _STATE.adapters):
        return
    why = (f"{module}.{name} is a term constructor of an adapter the "
           f"sandbox does not allow now")
    raise _access_error("python_module", module, why, context)


def _drop_constructor_refs(record):
    """The compiler *record* less each ``-import_from`` of a
    :func:`sandbox_constructor` (its own export check would call it a
    non-export; every other reference is kept as it is)."""
    from clausal import python_bridges as pb  # noqa: PLC0415
    return [r for r in record
            if not (r[0] == "import_from"
                    and sandbox_constructor(pb._module_path(r[1]), r[2]))]


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
                     denied: "list | None" = None,
                     vetted: "list | None" = None):
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
        module/2 list does not name; and that an allowed adapter's
        reviewed pure term constructor (``-import_from(date_time,
        [date])``, :func:`sandbox_constructor`) is an export too: by its
        import, and by the exact ``module.name`` chain the compiler lowers
        each use of it to (``date_time.date``)."""
        n = len(routes)
        ok = base(kind, a, b, node)
        new = routes[n:]
        if (new and name is not None and all(r[0] == "non_export"
                                             for r in new)
                and origin not in (None, pb._UNRESOLVABLE)
                and pb.is_engine_shipped(dotted, origin)
                and ((dotted.startswith(_FACADES)
                      and _facade_value(dotted, name))
                     or sandbox_constructor(dotted, name))):
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
        if vetted is not None and vetted_reference(kind, a, b, node):
            # A listed predicate of a vetted package adapter, by
            # -import_from (operator ruling 2026-11-04).  Only the shapes
            # that import lowers to are answered here: -import_module, a
            # dotted chain into the module and every other name it binds
            # stay routes.
            vetted.append((kind, a, b, line))
            return True
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
    routes += pb._check_refs(_drop_constructor_refs(record))[0]
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


def _is_pl_surface(path) -> bool:
    """D59: may this file's generated tree hold the cut nodes?  Only a
    ``.pl`` file's (the extension decides, as it decides the db's surface
    and so ``call_body.cut_allowed``); ``.clausal`` and ``.seam`` never."""
    from clausal.end_module import SURFACE_PL, surface_of  # noqa: PLC0415
    return surface_of(path) == SURFACE_PL


def _cut_surface(loader, path) -> bool:
    """D59: the audit's *cut_surface* for this load -- exact, and fail
    closed: a ``.pl`` file (:func:`_is_pl_surface`) loaded by the native
    front end, the only loader that emits the cut nodes.  The translator
    refuses cut, so a ``.pl`` it loads never needs them."""
    from clausal import import_hook as ih  # noqa: PLC0415
    return isinstance(loader, ih.NativePrologLoader) and _is_pl_surface(path)


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
    # Only a .seam importer may use a vetted package adapter (the design:
    # "the importing .seam must itself still be Python-free"); a .clausal
    # or .pl file reaches one through such a .seam, never directly.
    vetted: "list | None" = (
        [] if not isinstance(loader, (ih.NativePrologLoader, ih.PrologLoader))
        else None)
    found, _ = seam_audit.audit_tree(
        tree, _sandbox_checker(routes, children, denied, vetted),
        translations=translations or (), module_items=items or (),
        prolog_surface=isinstance(loader, ih.PrologLoader),
        cut_surface=_cut_surface(loader, path))
    routes = routes + found + extra
    if vetted and not routes:
        refused_by = _importer_admitted(path, data)
        if refused_by is not None:
            raise load_error(path, (
                f"the sandbox refuses {fullname} ({os.path.abspath(path)}): "
                f"it imports the vetted package adapter {refused_by}, and "
                f"it is not an importer enable(allow_package_adapters=...) "
                f"lists for it"))
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
    """Compiled queries made before the sandbox was on are not reused,
    nor are the Python-bridge audits (their key carries the switch, so
    this is belt and braces)."""
    from clausal.logic import solve as _solve  # noqa: PLC0415
    from clausal import python_bridges as _pb  # noqa: PLC0415
    _solve._query_cache.clear()
    with _pb._AUDITS_LOCK:
        _pb._AUDITS.clear()
