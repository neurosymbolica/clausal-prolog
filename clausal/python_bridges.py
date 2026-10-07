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
import importlib.machinery
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
    "non_export": ("an imported name, or a dotted reference, that is not a "
                   "declared export of its module (module.export is the "
                   "only qualified form)"),
    "unresolved_reference": "a module reference that resolves to no module",
    "uncompilable": "the module does not compile (refused, fail closed)",
    "python_call": "generated code calls something not on the allow-list",
    "python_name": "generated code names something the module does not bind",
    "submodule_name": ("a name imported from a package that is also the "
                       "package's SUBMODULE <pkg>.<name>: import it from the "
                       "submodule"),
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
    ``import_hook.ModulesFinder``), ``py`` -> ``clausal.modules.py``; any
    other name unchanged."""
    if dotted == "py":
        return _PY_ADAPTERS
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


def _module_references(tree: ast.Module) -> list:
    """What the file names OUTSIDE itself, unresolved, in source order:

    * ``("import_from", M, entries, line)`` -- *entries* is
      ``[(orig, local)]``, or None when an entry has a shape no export can
      be read from;
    * ``("import_module", M, line)``;
    * ``("chain", parts, line)`` -- every dotted chain ``a.b.c`` in a
      Clausal position (a call, a value, a goal handed to ``call/N``), its
      head not a logic variable (``X.k`` is dict sugar).
    """
    from clausal.templating.desugar import is_dict_attr_access  # noqa: PLC0415
    from clausal.templating.term_rewriting import (  # noqa: PLC0415
        _TITLECASE_EXEMPT_NAMES, _is_titlecase_identifier)
    # A head the COMPILER does not read as a variable is a qualified base:
    # the file's TitleCase -import_from names and the exempt injected names
    # (``term_rewriting._clause_scope_exclusions``).
    excluded = set(_TITLECASE_EXEMPT_NAMES)
    for stmt in tree.body:
        v = getattr(stmt, "value", None)
        if (isinstance(stmt, ast.Expr) and _is_directive(v)
                and isinstance(v.operand, ast.Call)
                and v.operand.func.id == "import_from"
                and len(v.operand.args) > 1):
            for _orig, local in _import_entries(v.operand.args[1]) or ():
                if _is_titlecase_identifier(local):
                    excluded.add(local)
    refs: list = []
    for stmt in tree.body:
        if not isinstance(stmt, ast.Expr):
            continue
        value = stmt.value
        if (_is_directive(value) and isinstance(value.operand, ast.Call)
                and value.operand.func.id in ("import_from", "import_module")
                and value.operand.args):
            call = value.operand
            dotted = _dotted(call.args[0])
            if dotted is None:
                continue        # the compiler refuses it
            if call.func.id == "import_module":
                refs.append(("import_module", dotted, stmt.lineno))
            else:
                entries = (_import_entries(call.args[1])
                           if len(call.args) > 1 else None)
                refs.append(("import_from", dotted, entries, stmt.lineno))
            continue
        inner: set = set()
        for sub in _clausal_nodes(value):
            if not isinstance(sub, ast.Attribute) or id(sub) in inner:
                continue
            # Only the OUTERMOST node of THIS chain is the reference (``a.b``
            # inside ``a.b.c`` is the same one) -- decided per node, as the
            # compiler's visit does, not by comparing spellings.
            node = sub.value
            while isinstance(node, ast.Attribute):
                inner.add(id(node))
                node = node.value
            dotted = _dotted(sub)
            if dotted is None:
                # A chain whose head is no name (``f(x).a``): nothing a
                # qualified name can be.
                refs.append(("chain", None, sub.lineno))
                continue
            parts = tuple(dotted.split("."))
            if is_dict_attr_access(sub, frozenset(excluded)):
                continue    # VAR.k: dict sugar, the compiler's own test
            refs.append(("chain", parts, sub.lineno))
    return refs


def _import_entries(node) -> "list | None":
    """``[(orig, local)]`` of an ``-import_from`` name list: ``name``,
    ``name/N`` (``name//N``), ``alias(name, local)``, ``alias(name/N,
    local)``; None when any entry is another shape."""
    if not isinstance(node, ast.List):
        return None
    out = []
    for e in node.elts:
        local = None
        if (isinstance(e, ast.Call) and isinstance(e.func, ast.Name)
                and e.func.id == "alias" and len(e.args) == 2
                and isinstance(e.args[1], ast.Name)):
            local = e.args[1].id
            e = e.args[0]
        if (isinstance(e, ast.BinOp)
                and isinstance(e.op, (ast.Div, ast.FloorDiv))):
            e = e.left
        if not isinstance(e, ast.Name):
            return None
        out.append((e.id, local or e.id))
    return out


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


#: realpath -> (sha256, _Scan).
_SCANS: dict[str, tuple] = {}


def _scan(path: str) -> _Scan:
    """The scan of the file at *path*, keyed by its CONTENT (sha256): a
    rewrite is never mistaken for the old file, whatever its timestamps."""
    real = os.path.realpath(path)
    with open(real, "rb") as f:
        data = f.read()
    sha = hashlib.sha256(data).hexdigest()
    hit = _SCANS.get(real)
    if hit is not None and hit[0] == sha:
        return hit[1]
    text = data.decode("utf-8", errors="replace")
    try:
        tree = ast.parse(text, filename=path)
    except SyntaxError:
        # The module will not load either; refuse rather than guess.
        scan = _Scan([("python_statement", 0)], [], sha)
    else:
        scan = _Scan(python_routes(tree, text), _module_references(tree),
                     sha)
    _SCANS[real] = (sha, scan)
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
    import clausal.import_hook  # noqa: F401,PLC0415 -- the real finders
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
                    if type(finder).__name__ == "_LazyHookFinder":
                        # The lazy stub only installs the real finders
                        # (installed above) and re-asks importlib.util.
                        # find_spec, which IMPORTS the parents.
                        continue
                    if finder is importlib.machinery.PathFinder:
                        # PathFinder wraps a namespace package's portions in
                        # a _NamespacePath, which reads the PARENT's
                        # __path__ from sys.modules -- a KeyError for a
                        # namespace package nobody imported.  Its role is
                        # played here with the per-entry finders alone.
                        spec = _path_find(name, path)
                    else:
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


def _path_find(fullname: str, path):
    """``importlib.machinery.PathFinder.find_spec`` without its
    ``_NamespacePath``: each search-path entry's own finder
    (``pkgutil.get_importer``: the cached ``FileFinder``, which only
    stats) is asked in order; the first module or regular package wins,
    else the directories that answered as namespace PORTIONS make a
    namespace spec (origin None, its portions as a plain list).  Imports
    nothing."""
    import pkgutil  # noqa: PLC0415
    from importlib.machinery import ModuleSpec  # noqa: PLC0415
    portions: list = []
    for entry in (path if path is not None else sys.path):
        if not isinstance(entry, str):
            continue
        finder = pkgutil.get_importer(entry or os.getcwd())
        if finder is None or not hasattr(finder, "find_spec"):
            continue
        spec = finder.find_spec(fullname)
        if spec is None:
            continue
        if spec.loader is not None:
            return spec
        portions.extend(p for p in spec.submodule_search_locations or ()
                        if p not in portions)
    if not portions:
        return None
    spec = ModuleSpec(fullname, None, is_package=True)
    spec.submodule_search_locations = portions
    return spec


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
    if origin is None and "." in dotted:
        parent = _find(dotted.rpartition(".")[0])
        if parent is not None:
            # ``m.a.b`` with ``m`` a module and ``m.a`` none: the chain walks
            # an attribute OF m's namespace (an object the module imported,
            # ``py.csv.io``) and then goes on into it -- arbitrary Python.
            # A qualified name is ``m.name``, never deeper.
            return "python_module", None
    if origin is None and dotted.startswith(_PY_ADAPTERS + "."):
        # Fail closed: a py.X the engine's adapters do not resolve may fall
        # through at run time to some other ``py`` package on sys.path.
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


def _module_path(written: str) -> str:
    """The module a seam spelling names: its HEAD through the seam's import
    aliases (``units`` -> ``clausal.modules.units``, ``date_time.x`` ->
    ``clausal.modules.py.datetime.x``), then the ``py.X`` redirect."""
    from clausal.templating.term_rewriting import (  # noqa: PLC0415
        _resolve_import_path)
    whole = _resolve_import_path(written)
    if whole != written:
        return _adapter_path(whole)
    head, dot, rest = written.partition(".")
    return _adapter_path(_resolve_import_path(head) + dot + rest)


#: (dotted, origin, stamp) -> frozenset of export names.
_EXPORTS: dict = {}


def _exports(dotted: str, origin: str, _seen: "frozenset" = frozenset()
             ) -> frozenset:
    """:func:`_cached_exports`, less every name that is a SUBMODULE of
    *dotted* now (importing ``pkg.n`` sets ``pkg.n`` to the module object):
    asked on every call, since it depends on other files than *origin*."""
    names = _cached_exports(dotted, origin, _seen)
    if names and _is_source(origin):
        names = frozenset(n for n in names
                          if _find(f"{dotted}.{n}") is None)
    return names


def _cached_exports(dotted: str, origin: str,
                    _seen: "frozenset" = frozenset()) -> frozenset:
    """The names module *dotted* (at *origin*) DECLARES as exports: for a
    Clausal source (``.seam``/``.clausal``/``.pl``) its module/2 export
    list, read statically; for an engine-shipped Python module what an
    ``-import_from`` or its ``library(...)`` facade offers -- its
    predicates (``module_signatures``) and its values (units, currencies,
    numbers: ``clausal.library.is_value``).  Anything else: nothing."""
    try:
        with open(origin, "rb") as f:
            stamp = hashlib.sha256(f.read()).hexdigest()
    except OSError:
        stamp = None
    key = (dotted, origin, stamp)
    hit = _EXPORTS.get(key)
    if hit is not None:
        return hit
    names: frozenset = frozenset()
    try:
        if _is_source(origin):
            from clausal.tools.iso_l3_directives import (  # noqa: PLC0415
                _declared_exports)
            # (A listless package __init__.seam answers its re-exports here
            # too: _declared_exports -> listless_exports, rulings E1/M3.)
            exports = _declared_exports(origin)[1]
            # The list is the (untrusted) module author's text, so only a
            # name the declaration itself BINDS counts: a lowercase name
            # (the module/2 rewrite binds it as an atom, a predicate handle
            # or a constructor).  An underscore-led name (``__dict__``,
            # ``__loader__``) is the module object's own Python attribute,
            # which no declaration binds; a non-identifier is refused too.
            names = frozenset(
                n for n, _a in exports or ()
                if type(n) is str and n.isidentifier()
                and not n.startswith("_") and not n[:1].isupper())
            # A name the module object will hold as a MODULE is no export,
            # whatever the declarations say: one an -import_module binds
            # (it runs after the clauses and rebinds the name), and one
            # naming a submodule (importing pkg.n sets pkg.n to it).
            names = names - _module_bound_names(origin)
        elif is_engine_shipped(dotted, origin):
            import importlib  # noqa: PLC0415
            from clausal.library import is_value  # noqa: PLC0415
            from clausal.logic.solve import module_signatures  # noqa: PLC0415
            mod = importlib.import_module(dotted)
            sig = module_signatures(mod)
            names = frozenset(sig) | frozenset(
                n for n, v in vars(mod).items()
                if not n.startswith("_") and n not in sig and is_value(v))
    except Exception:  # noqa: BLE001 -- unreadable: nothing is exported
        names = frozenset()
    _EXPORTS[key] = names
    return names


def _non_export_kind(dotted: str, name: str) -> str:
    """``submodule_name`` when *name* is not an export of *dotted* because
    it is the package's SUBMODULE (ruling M3), else ``non_export``."""
    return ("submodule_name" if _find(f"{dotted}.{name}") is not None
            else "non_export")


def _module_bound_names(origin: str) -> frozenset:
    """The names the Clausal source at *origin* binds to a MODULE object:
    every ``-import_module``'s binding (its first segment, or its alias),
    from the compiler record.  A ``.pl``/``.clausal`` has none here."""
    if not _is_seam(origin):
        return frozenset()
    return frozenset(r[2] for r in compiler_record(origin) or ()
                     if r[0] == "import_module")


#: Operator ruling M3, item 4 (PENDING): a re-export whose SOURCE module
#: lies outside the package counts.  One switch: False keeps only re-exports
#: from the package's own modules.
REEXPORTS_FROM_OUTSIDE_PACKAGE = True

#: Realpaths whose listless exports are being computed (re-import cycles).
_LISTLESS_IN_PROGRESS: set = set()


def is_listless_package_init(path: str) -> bool:
    """True when *path* is a package ``__init__.seam`` with NO module/2
    export list (it only re-imports from its submodules)."""
    from clausal.end_module import SURFACE_SEAM, surface_of  # noqa: PLC0415
    if (os.path.basename(path).rpartition(".")[0] != "__init__"
            or surface_of(path) != SURFACE_SEAM):
        return False
    from clausal.tools.iso_l3_directives import _seam_exports  # noqa: PLC0415
    try:
        return _seam_exports(path)[1] is None
    except Exception:  # noqa: BLE001 -- unreadable: not one
        return False


def listless_exports(path: str) -> "list[tuple[str, int | None]]":
    """THE export rule of a listless package ``__init__.seam`` (operator
    rulings E1 and M3), shared by ``iso_l3_directives._declared_exports``
    (so ``use_module/1,2`` and the bridge gate's ``_exports``), the
    sandbox's load audit and ``clausal.module_signatures``.  Read from the
    compiler; nothing is imported.  ``(name, arity)`` for a predicate,
    ``(name, None)`` for any other name (an atom, a constructor, a unit):

    * the predicates the package defines itself (``$declare_head``);
    * each name it ``-import_from``s, under its LOCAL name, when that name
      is an export of its source module (the source's own declared exports,
      recursively -- a listless package source by this same rule -- or an
      engine-shipped Python module's predicates and values), at the
      arities both offer; a source outside the package only while
      :data:`REEXPORTS_FROM_OUTSIDE_PACKAGE`;
    * never an underscore-led or non-lowercase name, nor one an
      ``-import_module`` binds (the module object would hold a module
      there).  A name that is also a SUBMODULE is dropped where it is asked
      (:func:`_exports`), since that depends on other files.

    Re-import cycles answer the cycle's names as no export."""
    real = os.path.realpath(path)
    if real in _LISTLESS_IN_PROGRESS:
        return []
    _LISTLESS_IN_PROGRESS.add(real)
    try:
        return _listless_entries(path, real)
    finally:
        _LISTLESS_IN_PROGRESS.discard(real)


def _listless_entries(path: str, real: str) -> list:
    from clausal.seam_audit import generated_tree  # noqa: PLC0415
    from clausal.tools.iso_l3_directives import (  # noqa: PLC0415
        _declared_exports)
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    try:
        tree = generated_tree(text, path)
    except Exception:  # noqa: BLE001 -- does not compile: offers nothing
        return []
    out: list = []
    imported_arities: dict = {}
    for sub in ast.walk(tree):
        if not isinstance(sub, ast.Call):
            continue
        f = sub.func
        if (isinstance(f, ast.Name) and f.id == "$declare_head" and sub.args
                and isinstance(sub.args[0], ast.Constant)
                and isinstance(sub.args[0].value, str)):
            fields = sub.args[1] if len(sub.args) > 1 else None
            arity = (len(fields.elts) if isinstance(fields, ast.Tuple)
                     else None)
            out.append((sub.args[0].value, arity))
        elif (isinstance(f, ast.Attribute)
              and f.attr == "record_import_arities" and len(sub.args) == 2):
            try:
                imported_arities.update(ast.literal_eval(sub.args[1]))
            except ValueError:
                pass
    pkg_dir = os.path.dirname(real)
    for ref in compiler_record(path) or ():
        if ref[0] != "import_from":
            continue
        _k, resolved, orig, local, _line = ref
        source = _module_path(resolved)
        src_origin = _find(source)
        if not isinstance(src_origin, str) or src_origin == _UNRESOLVABLE:
            continue
        src_real = os.path.realpath(src_origin)
        if (not REEXPORTS_FROM_OUTSIDE_PACKAGE
                and not src_real.startswith(pkg_dir + os.sep)):
            continue
        if _is_source(src_origin):
            entries = _declared_exports(src_origin)[1] or ()
            arities = {a for n, a in entries if n == orig}
            if not arities or orig not in _exports(source, src_origin):
                continue
        elif is_engine_shipped(source, src_origin):
            if orig not in _exports(source, src_origin):
                continue
            import importlib  # noqa: PLC0415
            from clausal.logic.solve import module_signatures  # noqa: PLC0415
            sig = module_signatures(importlib.import_module(source))
            arities = set(sig.get(orig, ())) or {None}
        else:
            continue
        wanted = imported_arities.get(local)
        if wanted is not None and None not in arities:
            arities &= set(wanted)
        out.extend((local, a) for a in sorted(arities, key=lambda a: (
            a is None, a)))
    bound = _module_bound_names(path)
    seen: list = []
    for n, a in out:
        if (type(n) is str and n.isidentifier() and not n.startswith("_")
                and not n[:1].isupper() and n not in bound
                and (n, a) not in seen):
            seen.append((n, a))
    return seen


def _static_refs(raw) -> list:
    """The scanner's references in the compiler record's shape (see
    ``term_rewriting._EXTERNAL_REFS``)."""
    from clausal.templating.term_rewriting import (  # noqa: PLC0415
        _resolve_import_path)
    out: list = []
    locals_: dict = {}
    for ref in raw:
        if ref[0] == "import_from":
            _k, written, entries, line = ref
            resolved = _resolve_import_path(written)
            if entries is None:
                out.append(("python", "non_export", line))
                continue
            for orig, local in entries:
                out.append(("import_from", resolved, orig, local, line))
                locals_[local] = f"{resolved}.{orig}"
        elif ref[0] == "import_module":
            _k, written, line = ref
            resolved = _resolve_import_path(written)
            out.append(("import_module", resolved,
                        written if resolved != written
                        else written.split(".")[0], line))
    for ref in raw:
        if ref[0] == "chain":
            _k, parts, line = ref
            if parts is None:
                out.append(("python", "non_export", line))
                continue
            out.append(("attr", parts[0], locals_.get(parts[0]),
                        tuple(parts[1:]), line))
    return out


def _check_refs(refs) -> "tuple[list, list]":
    """``(routes, seam children)`` of a module's external references (the
    compiler record's shape), by the ALLOW-LIST rule: an external name is
    Python-free only when it resolves POSITIVELY to a declared export.

    * ``("python", kind, line)``: a Python route, as it is.
    * ``-import_from(M, Names)``: M must be a Clausal module or an
      engine-shipped one, and every imported name (aliased or not) one of
      its exports (:func:`_exports`).
    * ``-import_module(M)``: M must be a Clausal module or an engine-shipped
      one.
    * a qualified chain must be exactly ``<module>.<export>``: its longest
      prefix that is a module, then ONE more segment, an export.  A chain
      on a name this file imported with ``-import_from`` (a value) may not
      go on at all.

    Anything not positively resolved is a route (fail closed)."""
    routes: list = []
    children: list = []
    seen_children: set = set()
    module_names: dict = {}     # -import_module binding -> module path

    def module_ok(dotted, line) -> "tuple[bool, str | None]":
        how, origin = _classify(dotted)
        if how in ("python_module", "py_adapter"):
            routes.append((how, line))
            return False, origin
        if origin is None:
            routes.append(("unresolved_reference", line))
            return False, None
        if how == "seam" and dotted not in seen_children:
            seen_children.add(dotted)
            children.append((dotted, origin, line))
        return True, origin

    for ref in refs:
        kind = ref[0]
        if kind == "python":
            routes.append((ref[1], ref[2]))
        elif kind == "import_from":
            _k, resolved, orig, _local, line = ref
            dotted = _module_path(resolved)
            ok, origin = module_ok(dotted, line)
            if ok and orig not in _exports(dotted, origin):
                routes.append((_non_export_kind(dotted, orig), line))
        elif kind == "import_module":
            _k, resolved, name, line = ref
            module_ok(_module_path(resolved), line)
            if name != resolved.split(".")[0]:
                module_names[name] = resolved
    for ref in refs:
        if ref[0] != "attr":
            continue
        _k, base, remap, parts, line = ref
        if remap is not None or base.startswith("_"):
            # an attribute of an imported VALUE, or of no module at all
            routes.append(("non_export", line))
            continue
        chain = tuple(module_names.get(base, base).split(".")) + tuple(parts)
        _chain_ok(chain, line, module_ok, routes)
    return routes, children


def _chain_ok(chain, line, module_ok, routes) -> bool:
    """Whether the dotted *chain* is exactly ``module.export``: its longest
    prefix that resolves to a module, then ONE more part, an export."""
    for i in range(len(chain) - 1, 0, -1):
        dotted = _module_path(".".join(chain[:i]))
        if _find(dotted) is None:
            continue
        ok, origin = module_ok(dotted, line)
        if ok and (len(chain) - i != 1
                   or chain[-1] not in _exports(dotted, origin)):
            routes.append(("non_export", line))
            return False
        return ok
    routes.append(("unresolved_reference", line))
    return False


def _module_checker(routes, children):
    """``module_ok(dotted, line)``: may module *dotted* be imported by a
    Python-free module (a Clausal module or an engine-shipped one); records
    the routes it finds and the ``.seam`` modules to walk."""
    seen: set = set()

    def module_ok(dotted, line) -> "tuple[bool, str | None]":
        how, origin = _classify(dotted)
        if how in ("python_module", "py_adapter"):
            routes.append((how, line))
            return False, origin
        if origin is None:
            routes.append(("unresolved_reference", line))
            return False, None
        if how == "seam" and dotted not in seen:
            seen.add(dotted)
            children.append((dotted, origin, line))
        return True, origin

    return module_ok


def audit_checker(routes: list, children: list):
    """The *check_module* :func:`clausal.seam_audit.audit_tree` asks: the
    allow-list's module questions, recording routes and the ``.seam``
    modules to walk into *routes* / *children*."""
    module_ok = _module_checker(routes, children)

    def check_module(kind, a, b, node) -> bool:
        from clausal.seam_audit import node_line  # noqa: PLC0415
        line = node_line(node)
        if kind == "module":
            return module_ok(_module_path(a), line)[0]
        if kind == "name":
            dotted = _module_path(a)
            ok, origin = module_ok(dotted, line)
            if ok and b not in _exports(dotted, origin):
                routes.append((_non_export_kind(dotted, b), line))
                return False
            return ok
        return _chain_ok(tuple(a.split(".")), line, module_ok, routes)

    return check_module


def audit_routes(path: str) -> "tuple[list, list]":
    """THE DECIDER: ``(routes, seam children)`` of the audit of the FINAL
    generated Python of the ``.seam`` file at *path*
    (:mod:`clausal.seam_audit`), its module questions answered by the
    allow-list rules here.  No routes = Python-free."""
    from clausal import seam_audit  # noqa: PLC0415
    routes: list = []
    children: list = []
    check_module = audit_checker(routes, children)
    with open(path, encoding="utf-8", errors="replace") as f:
        source = f.read()
    found, _ = seam_audit.audit_source(source, path, check_module)
    return routes + found, children


#: realpath -> (sha256, record or None)
_RECORDS: dict = {}


def compiler_record(path: str) -> "tuple | None":
    """The COMPILER's record of the ``.seam`` file at *path*: every
    external resolution and Python route its lowering performs
    (``term_rewriting._EXTERNAL_REFS``), from the same parse and
    transformer the import hook runs -- nothing is executed.  None when the
    file does not compile (it cannot load either)."""
    import warnings  # noqa: PLC0415
    real = os.path.realpath(path)
    with open(real, "rb") as f:
        data = f.read()
    sha = hashlib.sha256(data).hexdigest()
    hit = _RECORDS.get(real)
    if hit is not None and hit[0] == sha:
        return hit[1]
    from clausal.templating.term_rewriting import (  # noqa: PLC0415
        EmbedTransformer)
    text = data.decode("utf-8", errors="replace")
    record = None
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
    _RECORDS[real] = (sha, record)
    return record


#: A switch for tests that prove the audit ALONE refuses: with it False the
#: record and the static pre-scan add nothing.
_DIAGNOSTICS = True


def _routes_and_children(path: str) -> "tuple[list, list]":
    """Everything that makes the file at *path* a Python bridge, and the
    ``.seam`` modules it passes through.

    THE DECIDER is :func:`audit_routes`, the allow-list audit of the final
    generated Python: a module is Python-free only when it finds nothing.
    The compiler record runs as DIAGNOSTICS (it names the route the author
    wrote); its routes are ADDED, never a reason to allow."""
    routes, children = audit_routes(path)
    if _DIAGNOSTICS:
        # The compiler record names the construct the author wrote (an
        # escape, a seam, a hosted statement).  The static pre-scan is NOT
        # consulted here: it only approximates the compiler (its comma-less
        # fact rule refused facts the compiler accepts), and the audit
        # covers everything it could find; it stays for the differential
        # test that keeps it honest.
        record = compiler_record(path)
        if record is None:
            routes.append(("uncompilable", 0))
            record = ()
        r1, c1 = _check_refs(record)
        routes += r1
        children += c1
        # The ruling's "no --": a ``--`` in a clause lowers to no Python
        # (double negation), so neither the audit nor the record sees it;
        # the policy refusal comes from the pre-scan's exact adjacency rule.
        routes += [r for r in _scan(path).routes if r[0] == "seam"]
    seen = set()
    unique = []
    for c in children:
        if c[0] not in seen:
            seen.add(c[0])
            unique.append(c)
    routes = sorted(set(routes), key=lambda r: (r[1], r[0]))
    return routes, unique


def file_python_routes(path: str) -> "list[tuple[str, int]]":
    """Every route of the ``.seam`` file at *path*: the final-AST audit's
    (the decider), plus the compiler record's and the static pre-scan's
    (diagnostics) -- see :func:`_routes_and_children`."""
    return _routes_and_children(path)[0]


# ── engine-shipped ──────────────────────────────────────────────────────────


def _engine_distribution():
    """The installed ``clausal`` distribution, or None.  (A hook, so a test
    can hand in a simulated RECORD.)"""
    import importlib.metadata  # noqa: PLC0415
    try:
        return importlib.metadata.distribution("clausal")
    except importlib.metadata.PackageNotFoundError:
        return None


def _is_wheel_install(dist) -> bool:
    """True when *dist* is a real (non-editable) wheel install: its metadata
    directory is a ``*.dist-info`` holding a RECORD, and its
    ``direct_url.json`` (PEP 610) does not mark it editable.  An
    ``*.egg-info`` never qualifies."""
    import json  # noqa: PLC0415
    try:
        path = getattr(dist, "_path", None)
        if path is None or not str(path).endswith(".dist-info"):
            return False
        if not dist.read_text("RECORD"):
            return False
        direct = dist.read_text("direct_url.json")
        if direct:
            info = json.loads(direct).get("dir_info") or {}
            if info.get("editable"):
                return False
        return True
    except Exception:  # noqa: BLE001 -- unreadable metadata: not a wheel
        return False


_SITE_DIRS = frozenset({"site-packages", "dist-packages"})

#: (rule, data): ``("record", frozenset of realpaths)``, ``("dir", engine
#: package directory)`` or ``("none", None)``.  Computed once per process.
_ENGINE_RULE: "tuple | None" = None


def _engine_rule() -> tuple:
    """How :func:`is_engine_shipped` decides, established once:

    * ``record`` -- the engine is INSTALLED (its distribution's RECORD lists
      the very ``clausal/__init__.py`` that is imported): engine-shipped is
      exactly the files that RECORD lists.  Optional ``clausal-*``
      distributions install into the same ``site-packages/clausal`` tree,
      so a directory test could not tell them apart.
    * ``dir`` -- an editable install or a source checkout (no RECORD lists
      the imported ``__init__``) whose package directory is not inside a
      ``site-packages``/``dist-packages`` tree: there the optional packages
      live in their own directories (``packages/clausal-*/clausal``), so
      "under the engine's package directory" is exact.
    * ``none`` -- neither could be established: nothing is engine-shipped
      (fail closed).
    """
    global _ENGINE_RULE
    if _ENGINE_RULE is not None:
        return _ENGINE_RULE
    import clausal  # noqa: PLC0415
    init = os.path.realpath(clausal.__file__)
    root = os.path.dirname(init)
    rule: tuple = ("none", None)
    dist = _engine_distribution()
    files = None
    if dist is not None:
        try:
            # Only the distribution installed BESIDE the imported package
            # (its dist-info in the same directory), and only its relative,
            # ``..``-free entries that resolve under the package directory:
            # a dist-info planted earlier on sys.path cannot vouch for files
            # of its choosing.
            site = os.path.dirname(root)
            if os.path.realpath(dist.locate_file("")) == site:
                files = []
                for f in dist.files or ():
                    rel = str(f)
                    if os.path.isabs(rel) or ".." in rel.replace(
                            "\\", "/").split("/"):
                        continue
                    real = os.path.realpath(dist.locate_file(f))
                    if real.startswith(root + os.sep):
                        files.append(real)
        except Exception:  # noqa: BLE001 -- unreadable RECORD: not "record"
            files = None
    # A RECORD vouches only for a real WHEEL install: a ``*.dist-info``
    # with a RECORD that is not an editable install.  A source checkout's
    # ``clausal.egg-info`` (left by an editable install or a build) or an
    # editable install's dist-info lists whatever existed when it was
    # written, so files added since would count as NOT the engine's -- the
    # engine's own facades were refused (2026-10-05).  The test is the
    # metadata's TYPE, not the folder name: ``pip install --target``,
    # Lambda layers and pex caches are real installs with no
    # site-packages in their path.
    if files and init in files and _is_wheel_install(dist):
        rule = ("record", frozenset(files))
    elif not (_SITE_DIRS & set(root.split(os.sep))):
        rule = ("dir", root)
    _ENGINE_RULE = rule
    return rule


def is_engine_shipped(dotted: str, origin: "str | None") -> bool:
    """True when the module *dotted* (loaded from *origin*) ships with the
    engine, decided by the resolved FILE (:func:`_engine_rule`): listed in
    the installed engine distribution's RECORD, or -- in an editable or
    source checkout -- under the engine's own package directory.  Not by
    the name: the optional ``clausal-*`` packages splice their adapters
    into the same namespaces (``clausal.modules.py.scipy_stats``), and
    those are not the engine's.  So the engine's ``library(...)`` facades,
    its stdlib, its own py adapters (``py.datetime``, via any spelling:
    ``py.datetime``, the alias ``date_time``) and its other modules are
    trusted; an optional package's adapter, or any user module, is not.
    (Route 7c of the dialect gate still refuses a ``.clausal`` file's
    DIRECT ``use_module(py/X)``; this is about what a ``.seam`` module may
    import.)"""
    if origin is None or origin == "<namespace>":
        return dotted == "clausal" or dotted.startswith("clausal.")
    if origin in ("built-in", "frozen"):
        return False
    real = os.path.realpath(origin)
    kind, data = _engine_rule()
    if kind == "record":
        return real in data
    if kind == "dir":
        return real.startswith(data + os.sep)
    return False


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
                   origin: "str | None", *, record: bool = False
                   ) -> "BridgeRefusal | None":
    """None when a Clausal Prolog file at *importer* may import the module
    *dotted* (whose source is *origin*); else the :class:`BridgeRefusal`.

    Only a ``.seam`` target is judged here (a Python module, a ``.pl`` and a
    Clausal Prolog module are the dialect gate's).  The file is read every
    time it changes, never trusted from a module object, so a bridge some
    ``.seam`` importer loaded earlier is judged exactly as a fresh one."""
    if not _is_seam(origin) or is_engine_shipped(dotted, origin):
        return None
    # A source compiled from memory (no file) has NO project, so no
    # bridge is allowlisted for it (fail closed, ruling Y4) -- never the
    # pyproject found from the working directory.
    project = find_project_file(importer) if importer else None
    allow = _allowlist(project)
    approved: dict = {}
    refusal = _walk(dotted, origin, allow, [], set(), approved)
    if record and refusal is None:
        # Only a WHOLE decision that admits the import, made for a load
        # (the importer's use_module, *record*), approves its bridges for
        # the sandbox -- never a run-time check, never a refused walk.
        APPROVED_BRIDGES.update(approved)
    return refusal


#: realpath -> sha256 of every bridge an importer's project allowlist
#: admitted (:func:`_walk`): what :mod:`clausal.sandbox` requires before it
#: lets a module with Python load.
APPROVED_BRIDGES: dict = {}


def _walk(dotted, origin, allow, chain, seen, approved=None
          ) -> "BridgeRefusal | None":
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
        # A trusted bridge: its own imports are its business.  Recorded as
        # approved, with the content judged, for the sandbox (which admits a
        # bridge only when an importer's project approved it, ruling S5).
        if approved is not None:
            approved[real] = scan.sha256
        return None
    routes, children = _routes_and_children(origin)
    if routes:
        routes.sort(key=lambda r: r[1])
        return BridgeRefusal(dotted, origin, _refusal_text(
            dotted, origin, routes, allow, chain))
    for ref, ref_origin, line in children:
        found = _walk(ref, ref_origin, allow,
                      chain + [(dotted, line)], seen, approved)
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
