"""Which ``.seam`` modules a Clausal Prolog importer may reach, and why.

Operator ruling 2026-10-04 (applies always, not only in a sandbox mode).
From a Clausal Prolog (``.clausal``) importer, Python is reachable ONLY
through:

1. ENGINE-SHIPPED files: the ``library(...)`` facades, the engine stdlib,
   the engine's own py adapters and every other file under the engine's
   package directory (:func:`is_engine_shipped`).  A ``.seam`` module whose
   only Python contact is importing those is Python-free (case 2).  A
   sandbox mode narrows the engine adapters further; the default trusts
   them all.
2. A ``.seam`` module with NO Python in it (:func:`python_routes` finds
   none) -- Clausal code in seam syntax.  It is a pass-through: the modules
   IT imports are checked the same way, transitively.
3. A ``.seam`` module that does contain Python, but only when the
   importer's PROJECT lists it in ``[tool.clausal] python_bridges`` of its
   ``pyproject.toml`` (optionally sha256-pinned).  A listed bridge is
   trusted Python: its own imports are its business and are not walked.

Anything else is refused with ``error(permission_error(import,
python_bridge, M), Context)``: at load time when a ``.clausal`` file's
``use_module`` names it (``iso_l3_directives._use_module``), and at run time
when a Clausal Prolog frame resolves ``M:G`` (or a dotted call) into it
(``clausal.logic.dialect_edge``) -- so a bridge some ``.seam`` or Python
code loaded first is refused just the same.

The project file is the nearest ``pyproject.toml`` walking up from the
IMPORTING ``.clausal`` file: the importer's project decides what it trusts,
never the imported module (which would let a bridge vouch for itself).

``.seam`` and ``.pl`` importers are not affected: ``.seam`` is the Python
boundary and the programmer's responsibility.

:func:`python_routes` is the one place that knows what "Python in a seam
module" means; a sandbox mode reuses it.
"""
from __future__ import annotations

import ast
import hashlib
import os
import re
import sys
from dataclasses import dataclass, field

__all__ = [
    "ROUTE_KINDS",
    "BridgeRefusal",
    "python_routes",
    "file_python_routes",
    "is_engine_shipped",
    "find_project_file",
    "bridge_refusal",
]


#: Every kind of Python route :func:`python_routes` (and, for
#: ``python_module``, :func:`file_python_routes`) reports, with what it is.
ROUTE_KINDS: dict[str, str] = {
    "escape": "a ++ escape (a Python expression)",
    "seam": "a -- seam operator",
    "fstring": "an f-string slot that evaluates Python",
    "py_adapter": ("an import or dotted call of a py.* adapter the engine "
                   "does not ship (an optional package's, or your own)"),
    "python_import": "a Python import statement",
    "python_def": "a Python def (or @{} template)",
    "python_class": "a Python class",
    "python_statement": "a hosted Python statement",
    "python_module": "an import of a Python (non-Clausal) module",
}


# ── what is Python in a seam module (syntactic, no resolution) ──────────────


def python_routes(tree: ast.Module, source: "str | None" = None
                  ) -> "list[tuple[str, int]]":
    """Every route into Python in the parsed ``.seam`` module *tree*, as
    ``(kind, line)`` pairs in source order (kinds: :data:`ROUTE_KINDS`).

    Purely syntactic: nothing is imported or resolved, so an
    ``-import_from`` of a non-Clausal Python module is not seen here (see
    :func:`file_python_routes`).  *source* (the file's text) lets the ``<-``
    arrow be told from ``< -`` exactly as the compiler tells it; without
    it the compiler's column heuristic is used.

    A statement at module level is Clausal when it is a directive
    (``-name(...)``), a fact (``f(...),`` / ``f,`` / a comma-less ``f(...)``
    for a functor an EARLIER clause established), a rule (``h <- body``), a
    DCG rule (``h >> body``), a query (``*(...)``), a bare name or a
    constant; any other statement is hosted Python.
    """
    from clausal.templating.term_rewriting import (  # noqa: PLC0415
        _detect_arrow)
    lines = source.splitlines(keepends=True) if source is not None else None
    out: list[tuple[str, int]] = []
    heads: set[str] = set()
    for stmt in tree.body:
        line = getattr(stmt, "lineno", 0)
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            out.append(("python_import", line))
            continue
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append(("python_def", line))
            continue
        if isinstance(stmt, ast.ClassDef):
            out.append(("python_class", line))
            continue
        if not isinstance(stmt, ast.Expr):
            out.append(("python_statement", line))
            continue
        kind, name = _top_level_expr(stmt.value, heads, lines, _detect_arrow)
        if kind == "python":
            out.append(("python_statement", line))
        if name is not None:
            heads.add(name)
        out.extend(_expression_routes(stmt.value))
    out.sort(key=lambda r: r[1])
    return out


def _top_level_expr(value, heads, lines, detect_arrow):
    """-> (kind, functor established or None).  *kind* is ``"directive"``,
    ``"clausal"`` or ``"python"``."""
    if _is_directive(value):
        return "directive", None
    if isinstance(value, ast.Tuple) and len(value.elts) == 1:
        inner = value.elts[0]
        if isinstance(inner, ast.Call) and _head_name(inner.func):
            return "clausal", _head_name(inner.func)
        if isinstance(inner, ast.Name):
            return "clausal", inner.id
        if isinstance(inner, ast.Compare) and _is_arrow(inner, lines,
                                                         detect_arrow):
            return "clausal", _head_name(inner.left)
        return "python", None
    if isinstance(value, ast.Tuple):
        # ``g1, g2`` / ``h <- g1, g2``: the compiler refuses both.
        return "clausal", None
    if isinstance(value, ast.Compare) and _is_arrow(value, lines,
                                                     detect_arrow):
        return "clausal", _head_name(value.left)
    if isinstance(value, ast.BinOp) and isinstance(value.op, ast.RShift):
        lhs = value.left
        if isinstance(lhs, ast.Tuple) and len(lhs.elts) == 2:
            lhs = lhs.elts[0]
        return "clausal", _head_name(lhs)
    if isinstance(value, ast.Starred):
        return "clausal", None                       # ``*(goal)`` query
    if isinstance(value, (ast.Name, ast.Constant)):
        return "clausal", None                       # resolves, calls nothing
    if (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
            and value.func.id in heads):
        return "clausal", value.func.id              # comma-optional fact
    return "python", None


def _head_name(node) -> "str | None":
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _is_arrow(compare, lines, detect_arrow) -> bool:
    try:
        return detect_arrow(compare.left, compare.ops, compare.comparators,
                            lines) is not None
    except SyntaxError:
        return True         # a malformed rule: the compiler refuses it


def _is_directive(value) -> bool:
    """``-name(...)`` / ``-name`` with the ``-`` adjacent (the compiler's
    test)."""
    return (isinstance(value, ast.UnaryOp) and isinstance(value.op, ast.USub)
            and isinstance(value.operand, (ast.Call, ast.Name))
            and (not isinstance(value.operand, ast.Call)
                 or isinstance(value.operand.func, ast.Name))
            and value.lineno == value.operand.lineno
            and value.col_offset == value.operand.col_offset - 1)


#: The package of the engine's Python adapters (``py.X`` in seam source).
_PY_ADAPTERS = "clausal.modules.py"


def _adapter_path(dotted: str) -> str:
    """``py.X...`` -> ``clausal.modules.py.X...`` (the seam's redirect,
    ``import_hook.ModulesFinder``); any other name unchanged."""
    if dotted.startswith("py."):
        return f"{_PY_ADAPTERS}.{dotted[3:]}"
    return dotted


def _dotted(node) -> "str | None":
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return None if base is None else f"{base}.{node.attr}"
    return None


def _expression_routes(node) -> "list[tuple[str, int]]":
    """The routes inside one module-level expression: ``++``, ``--``,
    Python-evaluating f-string slots, a Python ``lambda``."""
    from clausal.templating.term_rewriting import (  # noqa: PLC0415
        _double_prefix_operand)
    out: list[tuple[str, int]] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.UnaryOp):
            if _double_prefix_operand(sub, ast.UAdd) is not None:
                out.append(("escape", sub.lineno))
            elif _double_prefix_operand(sub, ast.USub) is not None:
                out.append(("seam", sub.lineno))
        elif isinstance(sub, ast.JoinedStr):
            if not _inert_fstring(sub):
                out.append(("fstring", sub.lineno))
        elif isinstance(sub, ast.Lambda):
            out.append(("python_def", sub.lineno))
    return out


def _inert_fstring(joined: ast.JoinedStr) -> bool:
    """True when every slot of the f-string only INTERPOLATES a bare name
    (``f"{X}"``, ``f"{X!r:>8}"``): no Python expression is evaluated.
    Any other slot (a call, an attribute, arithmetic ...) is Python."""
    for part in joined.values:
        if isinstance(part, ast.Constant):
            continue
        if not (isinstance(part, ast.FormattedValue)
                and isinstance(part.value, ast.Name)):
            return False
        spec = part.format_spec
        if spec is not None and not _inert_fstring(spec):
            return False
    return True


# ── what a seam module imports (needs resolution) ───────────────────────────


def _module_references(tree: ast.Module) -> "list[tuple[str, int]]":
    """``(dotted, line)`` for every module the file names: its
    ``-import_from`` / ``-import_module`` paths (resolved through the seam's
    import aliases) and the qualifier of every dotted call ``m.p(...)``."""
    from clausal.templating.term_rewriting import (  # noqa: PLC0415
        _is_logic_var_name, _resolve_import_path)
    refs: list[tuple[str, int]] = []
    for stmt in tree.body:
        if not isinstance(stmt, ast.Expr):
            continue
        value = stmt.value
        if (_is_directive(value) and isinstance(value.operand, ast.Call)
                and value.operand.func.id in ("import_from", "import_module")
                and value.operand.args):
            dotted = _dotted(value.operand.args[0])
            if dotted is not None:
                refs.append((_resolve_import_path(dotted), stmt.lineno))
            continue
        for sub in _clausal_nodes(value):
            if not (isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Attribute)):
                continue
            dotted = _dotted(sub.func.value)
            if dotted is None or _is_logic_var_name(dotted.split(".")[0]):
                continue        # X.k is dict sugar, no module
            refs.append((_resolve_import_path(dotted), sub.lineno))
    return refs


def _clausal_nodes(node):
    """Every node of *node* outside verbatim Python (a ``++``/``--``
    operand, an f-string): there a dotted call is Python's, already a
    route."""
    from clausal.templating.term_rewriting import (  # noqa: PLC0415
        _double_prefix_operand)
    stack = [node]
    while stack:
        sub = stack.pop()
        if isinstance(sub, ast.JoinedStr) or (
                isinstance(sub, ast.UnaryOp)
                and (_double_prefix_operand(sub, ast.UAdd) is not None
                     or _double_prefix_operand(sub, ast.USub) is not None)):
            continue
        yield sub
        stack.extend(ast.iter_child_nodes(sub))


@dataclass
class _Scan:
    routes: list
    refs: list
    sha256: str


#: realpath -> ((mtime_ns, size), _Scan): a file is re-read when it changes.
_SCANS: dict[str, tuple] = {}


def _scan(path: str) -> _Scan:
    real = os.path.realpath(path)
    st = os.stat(real)
    stamp = (st.st_mtime_ns, st.st_ctime_ns, st.st_size, st.st_ino)
    hit = _SCANS.get(real)
    if hit is not None and hit[0] == stamp:
        return hit[1]
    with open(real, "rb") as f:
        data = f.read()
    text = data.decode("utf-8", errors="replace")
    try:
        tree = ast.parse(text, filename=path)
    except SyntaxError:
        # The module will not load either; refuse rather than guess.
        scan = _Scan([("python_statement", 0)], [],
                     hashlib.sha256(data).hexdigest())
    else:
        scan = _Scan(python_routes(tree, text), _module_references(tree),
                     hashlib.sha256(data).hexdigest())
    _SCANS[real] = (stamp, scan)
    return scan


#: What :func:`_find` answers for a name whose resolution RAISED: a finder
#: (or a module object) misbehaved, so the reference is refused, never
#: skipped (fail closed).
_UNRESOLVABLE = "<unresolvable>"


def _find(dotted: str) -> "str | None":
    """The source file of the module *dotted* names, or None (no such
    module, or a namespace package, which runs nothing).

    Resolved WITHOUT importing anything: each segment is looked up through
    ``sys.meta_path`` with its parent's search path (from ``sys.modules``
    when the parent is loaded), so a parent package's ``__init__`` never
    runs while the gate is still deciding.  A lookup that raises answers
    :data:`_UNRESOLVABLE`."""
    parts = dotted.split(".")
    path = None
    spec = None
    for i in range(len(parts)):
        name = ".".join(parts[:i + 1])
        mod = sys.modules.get(name)
        try:
            if mod is not None:
                spec = getattr(mod, "__spec__", None)
                origin = getattr(spec, "origin", None) or getattr(
                    mod, "__file__", None)
                locations = getattr(mod, "__path__", None)
            else:
                spec = None
                for finder in sys.meta_path:
                    find_spec = getattr(finder, "find_spec", None)
                    if find_spec is None:
                        continue
                    spec = find_spec(name, path)
                    if spec is not None:
                        break
                if spec is None:
                    return None
                origin = spec.origin
                locations = spec.submodule_search_locations
        except Exception:  # noqa: BLE001 -- fail closed, see _UNRESOLVABLE
            return _UNRESOLVABLE
        if i < len(parts) - 1:
            if locations is None:
                return None     # not a package: nothing below it
            path = list(locations)
    if not origin or origin == "<namespace>":
        return None
    return origin       # a file, or "built-in"/"frozen" (Python all the same)


def _classify(dotted: str) -> "tuple[str, str | None]":
    """How a module reference counts: ``("python_module", origin)`` -- a
    Python (non-Clausal) module the engine does not ship, or one that could
    not be resolved safely; ``("seam", origin)`` -- a ``.seam`` module the
    engine does not ship (walked); ``("ignored", origin)`` -- nothing,
    engine-shipped, or a Clausal Prolog / ``.pl`` module (gated on its own
    load, and by the dialect gate)."""
    dotted = _adapter_path(dotted)
    origin = _find(dotted)
    if origin == _UNRESOLVABLE:
        return "python_module", None
    if origin is None or is_engine_shipped(dotted, origin):
        return "ignored", origin
    if not _is_source(origin):
        if dotted.startswith(_PY_ADAPTERS + "."):
            return "py_adapter", origin
        return "python_module", origin
    if _is_seam(origin):
        return "seam", origin
    return "ignored", origin


def _is_source(origin: str) -> bool:
    from clausal._suffixes import SOURCE_SUFFIXES  # noqa: PLC0415
    return origin.endswith(SOURCE_SUFFIXES)


def _is_seam(origin: "str | None") -> bool:
    from clausal.end_module import SURFACE_SEAM, surface_of  # noqa: PLC0415
    return origin is not None and surface_of(origin) == SURFACE_SEAM


def file_python_routes(path: str) -> "list[tuple[str, int]]":
    """:func:`python_routes` of the ``.seam`` file at *path*, plus a
    ``python_module`` route for each module it names (``-import_from``,
    ``-import_module``, a dotted call's qualifier) that resolves to a
    Python module the engine does not ship."""
    scan = _scan(path)
    out = list(scan.routes)
    for dotted, line in scan.refs:
        how = _classify(dotted)[0]
        if how in ("python_module", "py_adapter"):
            out.append((how, line))
    out.sort(key=lambda r: r[1])
    return out


# ── engine-shipped ──────────────────────────────────────────────────────────


def _engine_dir() -> str:
    import clausal  # noqa: PLC0415
    return os.path.realpath(os.path.dirname(clausal.__file__))


def is_engine_shipped(dotted: str, origin: "str | None") -> bool:
    """True when the module *dotted* (loaded from *origin*) ships with the
    engine: its file lies under the engine's OWN package directory (the
    directory of ``clausal/__init__.py``).  Decided by the resolved PATH,
    not by the name: the optional ``clausal-*`` packages splice their
    adapters into the same namespaces (``clausal.modules.py.scipy_stats``),
    and those are not the engine's.  So the engine's ``library(...)``
    facades, its stdlib, its own py adapters (``py.datetime``, via any
    spelling: ``py.datetime``, the alias ``date_time``) and its other
    modules are trusted; an optional package's adapter, or any user
    module, is not.  (Route 7c of the dialect gate still refuses a
    ``.clausal`` file's DIRECT ``use_module(py/X)``; this is about what a
    ``.seam`` module may import.)  *dotted* is accepted for the callers'
    symmetry; only the path decides."""
    if origin is None or origin == "<namespace>":
        return dotted == "clausal" or dotted.startswith("clausal.")
    if origin in ("built-in", "frozen"):
        return False
    real = os.path.realpath(origin)
    root = _engine_dir()
    return real.startswith(root + os.sep)


# ── the project allowlist ───────────────────────────────────────────────────


PROJECT_FILE = "pyproject.toml"


def find_project_file(start: "str | None") -> "str | None":
    """The nearest ``pyproject.toml`` walking up from the file (or
    directory) *start*; from the working directory when *start* is None.
    The FIRST one found is the project, whether or not it has a
    ``[tool.clausal]`` table."""
    if start is None:
        d = os.getcwd()
    else:
        d = os.path.abspath(start)
        if not os.path.isdir(d):
            d = os.path.dirname(d)
    while True:
        cand = os.path.join(d, PROJECT_FILE)
        if os.path.isfile(cand):
            return cand
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


@dataclass(frozen=True)
class _Entry:
    module: "str | None"
    path: "str | None"          # absolute realpath
    sha256: "str | None"
    spelled: str


@dataclass
class _Allowlist:
    project: "str | None"
    entries: list = field(default_factory=list)
    error: "str | None" = None

    def match(self, dotted: str, origin: str) -> "_Entry | None":
        real = os.path.realpath(origin)
        for e in self.entries:
            if e.module is not None and e.module == dotted:
                return e
            if e.path is not None and e.path == real:
                return e
        return None


def project_stamp(project: "str | None"):
    """What identifies the content of the project file *project* (None for
    no file): a change to it changes the stamp."""
    if project is None:
        return None
    try:
        st = os.stat(project)
    except OSError:
        return "missing"
    return (st.st_mtime_ns, st.st_ctime_ns, st.st_size, st.st_ino)


#: pyproject path -> (stamp, _Allowlist)
_ALLOWLISTS: dict[str, tuple] = {}

_SHA = re.compile(r"[0-9a-fA-F]{64}")


def _allowlist(project: "str | None") -> _Allowlist:
    if project is None:
        return _Allowlist(None)
    stamp = project_stamp(project)
    if stamp == "missing":
        return _Allowlist(project, error=f"{project} could not be read")
    hit = _ALLOWLISTS.get(project)
    if hit is not None and hit[0] == stamp:
        return hit[1]
    allow = _read_allowlist(project)
    _ALLOWLISTS[project] = (stamp, allow)
    return allow


def _read_allowlist(project: str) -> _Allowlist:
    import tomllib  # noqa: PLC0415
    try:
        with open(project, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        return _Allowlist(project, error=f"{project} could not be read: {e}")
    where = f"{project} [tool.clausal] python_bridges"
    raw = data
    for key in ("tool", "clausal"):
        raw = raw.get(key, {})
        if not isinstance(raw, dict):
            return _Allowlist(project, error=(
                f"{project}: [{'tool' if key == 'tool' else 'tool.clausal'}]"
                f" is not a table"))
    raw = raw.get("python_bridges", [])
    if not isinstance(raw, list):
        return _Allowlist(project, error=f"{where} must be a list")
    base = os.path.dirname(os.path.abspath(project))
    entries = []
    for item in raw:
        spelled = repr(item)
        sha = None
        if isinstance(item, str):
            ref = item
            is_path = item.endswith(".seam") or "/" in item
        elif isinstance(item, dict):
            unknown = set(item) - {"module", "path", "sha256"}
            names = [k for k in ("module", "path") if k in item]
            if unknown or len(names) != 1:
                return _Allowlist(project, error=(
                    f"{where}: the entry {spelled} must be a table with "
                    f"exactly one of `module` or `path`, and optionally "
                    f"`sha256`"))
            ref = item[names[0]]
            is_path = names[0] == "path"
            sha = item.get("sha256")
            if sha is not None and not (isinstance(sha, str)
                                        and _SHA.fullmatch(sha)):
                return _Allowlist(project, error=(
                    f"{where}: the entry {spelled} has a sha256 that is not "
                    f"64 hex digits"))
        else:
            return _Allowlist(project, error=(
                f"{where}: the entry {spelled} is neither a string nor a "
                f"table"))
        if not isinstance(ref, str) or not ref:
            return _Allowlist(project, error=(
                f"{where}: the entry {spelled} names no module"))
        if is_path:
            path = ref if os.path.isabs(ref) else os.path.join(base, ref)
            entries.append(_Entry(None, os.path.realpath(path),
                                  sha and sha.lower(), spelled))
        else:
            if not all(p.isidentifier() for p in ref.split(".")):
                return _Allowlist(project, error=(
                    f"{where}: the entry {spelled} is neither a dotted "
                    f"module name nor a path (a path contains / or ends in "
                    f".seam)"))
            entries.append(_Entry(ref, None, sha and sha.lower(), spelled))
    return _Allowlist(project, entries)


# ── the decision ────────────────────────────────────────────────────────────


@dataclass
class BridgeRefusal:
    """Why a Clausal Prolog importer may not reach the ``.seam`` module
    :attr:`module`.  :attr:`message` is the explanation (without the
    leading directive); the error term is ``permission_error(import,
    python_bridge, module)``."""
    module: str
    origin: str
    message: str

    @property
    def term_text(self) -> str:
        return f"permission_error(import, python_bridge, {self.module})"


def _describe(routes) -> str:
    shown = ", ".join(f"{k} at line {ln}" if ln else k
                      for k, ln in routes[:6])
    more = f", and {len(routes) - 6} more" if len(routes) > 6 else ""
    return shown + more


def bridge_refusal(importer: "str | None", dotted: str,
                   origin: "str | None") -> "BridgeRefusal | None":
    """None when a Clausal Prolog file at *importer* may import the module
    *dotted* (whose source is *origin*); else the :class:`BridgeRefusal`.

    Only a ``.seam`` target is judged here (a Python module, a ``.pl`` and a
    Clausal Prolog module are the dialect gate's).  The file is read every
    time it changes, never trusted from a module object, so a bridge some
    ``.seam`` importer loaded earlier is judged exactly as a fresh one."""
    if not _is_seam(origin) or is_engine_shipped(dotted, origin):
        return None
    project = find_project_file(importer)
    allow = _allowlist(project)
    return _walk(dotted, origin, allow, [], set())


def _walk(dotted, origin, allow, chain, seen) -> "BridgeRefusal | None":
    real = os.path.realpath(origin)
    if real in seen:
        return None
    seen.add(real)
    entry = None if allow.error else allow.match(dotted, origin)
    try:
        scan = _scan(origin)
    except OSError as e:
        return BridgeRefusal(dotted, origin, f"{origin} could not be read: "
                                             f"{e}")
    if entry is not None:
        if entry.sha256 is not None and entry.sha256 != scan.sha256:
            return BridgeRefusal(dotted, origin, (
                f"{dotted} ({os.path.abspath(origin)}) is allowlisted in "
                f"{allow.project} "
                f"pinned to sha256 {entry.sha256}, but the file's sha256 is "
                f"{scan.sha256}: it changed since it was pinned; review it "
                f"and update the pin"))
        return None     # a trusted bridge: its own imports are its business
    routes = list(scan.routes)
    children = []
    for ref, line in scan.refs:
        how, ref_origin = _classify(ref)
        if how in ("python_module", "py_adapter"):
            routes.append((how, line))
        elif how == "seam":
            children.append((ref, ref_origin, line))
    if routes:
        routes.sort(key=lambda r: r[1])
        return BridgeRefusal(dotted, origin, _refusal_text(
            dotted, origin, routes, allow, chain))
    for ref, ref_origin, line in children:
        found = _walk(ref, ref_origin, allow,
                      chain + [(dotted, line)], seen)
        if found is not None:
            return found
    return None


def _refusal_text(dotted, origin, routes, allow, chain) -> str:
    via = ""
    if chain:
        hops = " -> ".join(f"{m} (line {ln})" for m, ln in chain)
        via = (f", reached through the Python-free module(s) {hops}, which "
               f"pass imports through")
    head = (f"{dotted} ({os.path.abspath(origin)}) runs Python "
            f"({_describe(routes)}){via}; "
            f"Clausal Prolog reaches Python only through the engine's "
            f"library(...) facades, a .seam module with no Python in it, or "
            f"a Python bridge its project allowlists")
    if allow.error:
        return f"{head}. The allowlist could not be used: {allow.error}"
    where = allow.project or (f"a {PROJECT_FILE} at the importing project's "
                              f"root (none was found)")
    return (f"{head}. To trust it, list it in {where}:\n"
            f"    [tool.clausal]\n"
            f"    python_bridges = [\"{dotted}\"]\n"
            f"  or pin its content: {{ module = \"{dotted}\", "
            f"sha256 = \"{_scan(origin).sha256}\" }}")
