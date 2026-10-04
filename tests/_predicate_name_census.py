"""Census of the predicate names PYTHON modules register, for the name gate.

Run in a CHILD process (``python -m tests._predicate_name_census ROOT
[--only-extra] [EXTRA_PKG ...]``); it prints one JSON document on stdout.
The child does the imports so the gate never touches the test session's
``sys.modules``, the ``clausal.modules[.py].__path__`` lists, or the global
unit and currency registries several package modules write to on import.

Which modules: every ``*.py`` under ``ROOT/clausal/modules/`` (the engine's
own, which must all import) and under ``ROOT/packages/<pkg>/clausal/modules/``
(the optional distributions), plus each EXTRA_PKG laid out like a package
(``EXTRA/pyproject.toml`` + ``EXTRA/clausal/modules/...``) -- that is how the
gate's positive controls get in.  A package's directories are spliced onto
``clausal.modules.__path__`` / ``clausal.modules.py.__path__`` right after
the engine's own entry, AHEAD of whatever the interpreter's site-packages or
editable installs contributed, and every imported module's ``__file__`` is
then checked against the source file it was found from: a module that
resolved anywhere else is a failure, not a census of the wrong copy.

Which names: what the REGISTRY holds once the module has run, not what a
grep finds.  Two readings, both checked:

* ``clausal.logic.solve.module_signatures(mod)`` -- the engine's own answer
  to "what does an ``-import_from`` of this module offer", i.e. the
  attribute names Clausal source spells.  Authoritative for what a program
  can CALL.
* the ``_name`` every predicate adapter in the module namespace carries
  (``ModulePredicate`` and the hand-rolled adapters) -- the name an
  ``existence_error(procedure, Name/N)`` and ``repr`` report.  A
  ``foo = ModulePredicate("Foo")`` is callable as ``foo`` but names itself
  ``Foo``, which the first reading cannot see.

A module that cannot be imported because a DECLARED third-party
dependency of its package is missing (``ModuleNotFoundError`` for a
top-level name the package's ``pyproject.toml`` lists) falls back to a
static read of its registration calls -- ``ModulePredicate(...)``,
``_pred(...)``, ``_pred_bidir(...)``, any ``*Predicate(...)`` constructor,
the module-level names they are bound to, and ``X._register(...)``
receivers.  Every other import failure is a FAILURE: an engine module that
does not import, a ``clausal.*`` import that does not resolve, a missing
module the package never declared, or any other exception.

Which DATA names: ``-import_from`` compiles to a Python ``from M import
name``, so it offers every public attribute of the module, not only its
predicates -- a ``Quantity`` constant, a number, a term constructor (a plain
function).  The census also reads those, both ways:

* on a LOADED module, every public attribute that is no predicate adapter,
  no module and no class, and that the module did not itself IMPORT (an
  ``import`` binding or a ``from ... import *`` source is the other
  module's name, censused there);
* statically, every public name the module's own import-time code binds
  (assignments, ``for`` and ``with`` targets, ``def``), plus attributes it
  writes onto its own module object from anywhere -- ``mod.X = ...`` where
  ``mod = sys.modules[__name__]``, ``setattr(mod, "X", ...)``,
  ``globals()["X"] = ...``.  A computed one (``setattr(mod, name, ...)``,
  ``globals().update(...)``) is reported, as for registrations.

A warned alias served by a module ``__getattr__`` (the units module's
retired TitleCase spellings) is no attribute and is not counted: it is the
ruled deprecation mechanism, linted where it is imported.

Validity is the engine's rule, ``term_rewriting._is_logic_var_name``: a
predicate name must be an identifier the variable rule does not claim
(TitleCase ``Foo``, ALL-CAPS ``FOO`` and underscore-led ``_foo`` all
read as logic variables in a bare functor position).  An exported DATA name
must not be TitleCase (see :func:`data_name_problem`).
"""
from __future__ import annotations

import ast
import importlib
import json
import os
import pathlib
import sys
import tomllib
import traceback

#: Distribution name -> top-level import name, where they differ.  A
#: declared dependency missing from this table maps to its normalised
#: distribution name; if that is wrong the missing import is "undeclared"
#: and the gate FAILS, so an omission here cannot pass silently.
_IMPORT_NAME_OF_DIST = {
    "opencv-python": "cv2",
    "opencv-python-headless": "cv2",
    "scikit-learn": "sklearn",
    "pyyaml": "yaml",
}

#: Packages switched off on purpose: importing them raises an ``ImportError``
#: carrying this marker.  Their modules are AST-checked (their names still
#: count), and the gate FAILS once one imports again, so the entry is
#: removed rather than left to rot.
DISABLED_PACKAGES = {
    "clausal-provenance": "is disabled pending a redesign",
}

#: Constructors that register a predicate under their first argument.
_REGISTERING_CALLEES = {"ModulePredicate", "_pred", "_pred_bidir"}


#: First-argument shapes that compute a NAME the static reading cannot see.
_COMPUTED_TEXT = (ast.Name, ast.JoinedStr, ast.BinOp, ast.Subscript,
                  ast.Attribute, ast.Call)


def _callee_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_registering_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    name = _callee_name(node.func)
    return bool(name) and (name in _REGISTERING_CALLEES
                           or name.endswith("Predicate"))


def _module_level_nodes(tree: ast.Module):
    """Every node that runs when the module is imported: the module body,
    including ``if``/``for``/``try``/``with`` blocks, but not the bodies of
    ``def``/``lambda`` (a helper such as ``_pred`` builds its adapter from a
    parameter; it registers nothing until called, and its CALL is what
    names the predicate) nor of ``class`` (methods, likewise)."""
    skip = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
    stack = [n for n in tree.body if not isinstance(n, skip)]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(child for child in ast.iter_child_nodes(node)
                     if not isinstance(child, skip))


def ast_registrations(source: str, filename: str) -> dict:
    """The names a module's source registers, read statically.

    ``names``: string first arguments of registering calls (the adapter's
    ``_name``), module-level names bound to one, and ``X._register``
    receivers.  ``dynamic``: registering calls whose name is computed, which
    this reading cannot see -- an AST-checked module with any is not clean.
    """
    tree = ast.parse(source, filename)
    # Names a module-level ``def``/``class`` binds: handed to a constructor
    # they are a callable, not a name.
    defined = {n.name for n in tree.body if isinstance(
        n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    names: set[str] = set()
    dynamic: list[int] = []
    string_names: set[str] = set()
    aliases: list[tuple[str, str]] = []
    imported: set[str] = set()
    for node in _module_level_nodes(tree):
        if isinstance(node, ast.ImportFrom) and (
                node.level or (node.module or "").startswith("clausal.modules")):
            imported.update(a.asname or a.name for a in node.names)
            # ``from .x import foo as Foo`` re-offers ``foo`` under a
            # spelling THIS module chose; an un-renamed import keeps the
            # home module's spelling, which the home module's census reads.
            names.update(a.asname for a in node.names
                         if a.asname and a.asname != a.name)
        if _is_registering_call(node):
            if node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    string_names.add(first.value)
                elif isinstance(first, _COMPUTED_TEXT) and not (
                        isinstance(first, ast.Name) and first.id in defined):
                    # A name the code computes: a variable, an f-string, a
                    # concatenation or formatting call.  Anything else (a
                    # function handed to an adapter's constructor, a number)
                    # is no name at all.
                    dynamic.append(node.lineno)
        elif (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "_register"
                and isinstance(node.func.value, ast.Name)):
            names.add(node.func.value.id)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            targets = [t.id for t in (node.targets if isinstance(node, ast.Assign)
                                      else [node.target])
                       if isinstance(t, ast.Name)]
            if _is_registering_call(node.value):
                names.update(targets)
            elif isinstance(node.value, ast.Name):
                aliases.extend((t, node.value.id) for t in targets)
    # ``apply_updates = _apply_updates``: a module-level ALIAS of a
    # registered or a sibling-module-imported adapter re-offers it under the
    # alias's spelling, which is this module's choice.
    for target, source_name in aliases:
        if source_name in names | string_names or source_name in imported:
            names.add(target)
    # A private attribute is never offered to ``-import_from`` (the rule
    # ``module_signatures`` applies), so only a PUBLIC binding is a name a
    # program spells; a private adapter's own ``_name`` was read above.
    names = {n for n in names if not n.startswith("_")} | {
        n for n in string_names}
    return {"names": sorted(names), "dynamic": dynamic}


def _bound_names(target: ast.AST):
    """The plain names an assignment/for/with target binds."""
    if isinstance(target, ast.Name):
        yield target.id
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            yield from _bound_names(elt)
    elif isinstance(target, ast.Starred):
        yield from _bound_names(target.value)


def _is_own_module_expr(node: ast.AST) -> bool:
    """``sys.modules[__name__]`` (or ``sys.modules.get(__name__)``)."""
    if isinstance(node, ast.Subscript):
        base, key = node.value, node.slice
    elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
          and node.func.attr == "get" and node.args):
        base, key = node.func.value, node.args[0]
    else:
        return False
    return (isinstance(base, ast.Attribute) and base.attr == "modules"
            and isinstance(base.value, ast.Name) and base.value.id == "sys"
            and isinstance(key, ast.Name) and key.id == "__name__")


_TYPE_FACTORIES = {"TypeVar", "ParamSpec", "TypeVarTuple", "NewType"}


def _is_type_alias_expr(value: ast.AST, classes: set[str]) -> bool:
    """``T = TypeVar("T")``, ``Conj = frozenset``, ``Alias = SomeClass``:
    the static twin of :func:`_is_type_like` (a type is no constant)."""
    import builtins  # noqa: PLC0415
    if isinstance(value, ast.Call):
        return _callee_name(value.func) in _TYPE_FACTORIES
    if isinstance(value, ast.Name):
        return value.id in classes or isinstance(
            getattr(builtins, value.id, None), type)
    return False


def _is_globals_call(node: ast.AST) -> bool:
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "globals" and not node.args)


def import_bound_names(tree: ast.Module) -> tuple[set[str], list[str]]:
    """Names the module's import-time code binds by IMPORTING them, and the
    sources of its ``from M import *`` statements."""
    bound: set[str] = set()
    star: list[str] = []
    for node in _module_level_nodes(tree):
        if isinstance(node, ast.Import):
            bound.update(a.asname or a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.name == "*":
                    star.append("." * node.level + (node.module or ""))
                else:
                    bound.add(a.asname or a.name)
    return bound, star


def ast_data_names(source: str, filename: str) -> dict:
    """The data names a module's source binds as module attributes, read
    statically (see the module docstring).

    ``names``: public names bound at import time other than by an import,
    plus constant attribute names written onto the module object from
    anywhere.  ``dynamic``: line numbers of module-object writes whose
    attribute name is computed.
    """
    tree = ast.parse(source, filename)
    names: set[str] = set()
    dynamic: list[int] = []
    classes = {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
    for node in _module_level_nodes(tree):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names.add(child.name)
        if isinstance(node, ast.Assign):
            if _is_type_alias_expr(node.value, classes):
                continue
            for t in node.targets:
                names.update(_bound_names(t))
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            names.update(_bound_names(node.target))
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            names.update(_bound_names(node.target))
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars is not None:
                    names.update(_bound_names(item.optional_vars))
        elif isinstance(node, ast.NamedExpr):
            names.update(_bound_names(node.target))
    # Writes onto the module object, from ANY scope (a helper that fills
    # the module's globals when it runs at import time).
    own: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and _is_own_module_expr(node.value):
            for t in node.targets:
                own.update(_bound_names(t))

    def _is_own(expr) -> bool:
        return ((isinstance(expr, ast.Name) and expr.id in own)
                or _is_own_module_expr(expr))

    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = (node.targets if isinstance(node, ast.Assign)
                       else [node.target])
            for t in targets:
                for sub in ast.walk(t):
                    if isinstance(sub, ast.Attribute) and _is_own(sub.value):
                        names.add(sub.attr)
                    elif (isinstance(sub, ast.Subscript)
                          and _is_globals_call(sub.value)):
                        key = sub.slice
                        if isinstance(key, ast.Constant) and isinstance(
                                key.value, str):
                            names.add(key.value)
                        else:
                            dynamic.append(node.lineno)
        elif isinstance(node, ast.Call):
            func = node.func
            if (isinstance(func, ast.Name) and func.id == "setattr"
                    and len(node.args) >= 2 and _is_own(node.args[0])):
                key = node.args[1]
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    names.add(key.value)
                else:
                    dynamic.append(node.lineno)
            elif (isinstance(func, ast.Attribute) and func.attr == "update"
                  and (_is_globals_call(func.value)
                       or (isinstance(func.value, ast.Attribute)
                           and func.value.attr == "__dict__"
                           and _is_own(func.value.value)))):
                dynamic.append(node.lineno)
    return {"names": sorted(n for n in names if not n.startswith("_")),
            "dynamic": sorted(dynamic)}


def name_problem(name: str) -> str | None:
    """Why *name* is no valid Clausal predicate name, or ``None``."""
    from clausal.templating.term_rewriting import (  # noqa: PLC0415
        _is_logic_var_name, _is_titlecase_identifier)
    if not name.isidentifier():
        return "not an identifier"
    if _is_logic_var_name(name):
        if _is_titlecase_identifier(name):
            return "TitleCase (reads as a logic variable)"
        return "logic-variable spelling"
    return None


def data_name_problem(name: str) -> str | None:
    """Why *name* is no valid exported DATA name, or ``None``.

    Only TitleCase: that is the spelling ``-import_from`` lets through
    silently (it exempts a TitleCase name from its variable check, so the
    import binds and the name is then read as the module's value).  An
    ALL-CAPS ``FOO`` or ``_foo`` is refused by the directive itself with a
    load-time error naming an ``alias(...)``, and is the ordinary spelling
    of a Python-side module constant (``NUMBER_TYPES``), so it is no silent
    hole and not this gate's business."""
    from clausal.templating.term_rewriting import (  # noqa: PLC0415
        _is_titlecase_identifier)
    if _is_titlecase_identifier(name):
        return "TitleCase (reads as a logic variable)"
    return None


def _is_predicate_adapter(value) -> bool:
    """A predicate adapter: what ``module_signatures`` counts (an adapter
    registering at least one arity), PLUS a ``ModulePredicate`` subclass
    that overrides ``_get_dispatch`` and keeps its ``_dispatch_fns`` empty
    -- it dispatches on ``*args`` itself (``scipy_stats.stats_dist``,
    ``scipy_interpolate.free``) and is a callable predicate that
    ``module_signatures`` currently leaves out.  A unit or currency
    constant (no arity, the inherited ``_get_dispatch``) is neither."""
    from clausal.logic.solve import _adapter_arities  # noqa: PLC0415
    from clausal.modules.py import ModulePredicate  # noqa: PLC0415
    if isinstance(value, type):
        return False
    if _adapter_arities(value) is not None:
        return True
    return (isinstance(value, ModulePredicate)
            and type(value)._get_dispatch is not ModulePredicate._get_dispatch)


def registry_names(mod) -> dict:
    """Names read off a LOADED module.

    ``offered``: ``module_signatures(mod)``, what ``-import_from`` offers.
    ``offered_gap``: public attributes holding a predicate adapter that
    ``module_signatures`` leaves out (see ``_is_predicate_adapter``).
    ``adapter_names``: the ``_name`` of every predicate adapter in the
    namespace, public or not.
    """
    from clausal.logic.solve import module_signatures  # noqa: PLC0415
    offered = set(module_signatures(mod))
    gap = set()
    adapter_names = set()
    for attr, value in list(vars(mod).items()):
        if not _is_predicate_adapter(value):
            continue
        if not attr.startswith("_") and attr not in offered:
            gap.add(attr)
        own = getattr(value, "_name", None)
        if isinstance(own, str):
            adapter_names.add(own)
    return {"offered": sorted(offered), "offered_gap": sorted(gap),
            "adapter_names": sorted(adapter_names)}


def data_names(mod, source: str, filename: str) -> list[str]:
    """Public DATA names read off a LOADED module: what ``-import_from``
    offers besides its predicates (see the module docstring)."""
    import types  # noqa: PLC0415
    tree = ast.parse(source, filename)
    imported, star = import_bound_names(tree)
    # (resolved against the module's PACKAGE, as Python resolves them; the
    # caller records a failure here as the module's own)
    star_mods = []
    for src in star:
        star_mods.append(importlib.import_module(
            src, package=mod.__package__ if src.startswith(".") else None))
    out = []
    for attr, value in list(vars(mod).items()):
        if attr.startswith("_") or attr in imported:
            continue
        if (_is_predicate_adapter(value) or _is_type_like(value)
                or isinstance(value, types.ModuleType)):
            continue
        if any(getattr(m, attr, _MISSING) is value for m in star_mods):
            continue
        out.append(attr)
    return sorted(out)


_MISSING = object()


def _is_type_like(value) -> bool:
    """A class, or a typing construct standing for one (a ``TypeVar``, a
    ``list[int]`` alias): a TYPE, named by Python's convention, which no
    Clausal program spells as a constant."""
    import types  # noqa: PLC0415
    import typing  # noqa: PLC0415
    return isinstance(value, (type, typing.TypeVar, typing.ParamSpec,
                              typing.TypeVarTuple, types.GenericAlias,
                              types.UnionType)) or type(value).__module__ == "typing"


def _declared_imports(pkg_dir: pathlib.Path) -> list[str]:
    pyproject = pkg_dir / "pyproject.toml"
    if not pyproject.is_file():
        return []
    project = tomllib.loads(pyproject.read_text()).get("project", {})
    specs = list(project.get("dependencies", []))
    for group in project.get("optional-dependencies", {}).values():
        specs.extend(group)
    out = set()
    for spec in specs:
        dist = spec
        for sep in "<>=!~[; ":
            dist = dist.split(sep, 1)[0]
        dist = dist.strip().lower()
        if not dist or dist.startswith("clausal"):
            continue
        out.add(_IMPORT_NAME_OF_DIST.get(dist, dist.replace("-", "_")))
    return sorted(out)


def _module_files(modules_dir: pathlib.Path):
    for p in sorted(modules_dir.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        rel = p.relative_to(modules_dir).with_suffix("").parts
        if rel[-1] == "__init__":
            rel = rel[:-1]
        yield p, ".".join(("clausal", "modules") + rel)


def census(root: pathlib.Path, extra: list[pathlib.Path], only_extra: bool) -> dict:
    sys.path.insert(0, str(root))
    import clausal  # noqa: PLC0415
    if not os.path.realpath(clausal.__file__).startswith(
            os.path.join(os.path.realpath(root), "")):
        raise SystemExit(f"census loaded the wrong engine: {clausal.__file__}")
    import clausal.modules as cm  # noqa: PLC0415
    import clausal.modules.py as cmp  # noqa: PLC0415

    packages = [] if only_extra else sorted(
        p.parent.parent for p in (root / "packages").glob("*/clausal/modules"))
    packages += extra
    # Splice each package's directories in right after the engine's own.
    for pkg in reversed(packages):
        for ns, sub in ((cm, pkg / "clausal" / "modules"),
                        (cmp, pkg / "clausal" / "modules" / "py")):
            if sub.is_dir():
                ns.__path__.insert(1, str(sub))

    origins = []
    if not only_extra:
        origins.append(("engine", None, root / "clausal" / "modules"))
    for pkg in packages:
        origins.append((pkg.name, pkg, pkg / "clausal" / "modules"))

    stdlib = set(sys.stdlib_module_names)
    records = []
    for origin, pkg_dir, modules_dir in origins:
        declared = _declared_imports(pkg_dir) if pkg_dir else []
        for path, dotted in _module_files(modules_dir):
            rec = {"origin": origin, "module": dotted,
                   "file": str(path.relative_to(root) if root in path.parents
                               else path)}
            source = path.read_text()
            static = ast_registrations(source, str(path))
            rec["ast_names"] = static["names"]
            rec["dynamic"] = static["dynamic"]
            static_data = ast_data_names(source, str(path))
            rec["ast_data_names"] = static_data["names"]
            rec["data_dynamic"] = static_data["dynamic"]
            try:
                mod = importlib.import_module(dotted)
            except ModuleNotFoundError as exc:
                missing = (exc.name or "").split(".")[0]
                rec["missing"] = missing
                if (pkg_dir is not None and missing in declared
                        and missing not in stdlib
                        and not missing.startswith("clausal")):
                    rec["mode"] = "ast"
                else:
                    rec["mode"] = "failed"
                    if missing.startswith("clausal"):
                        why = "an engine import that does not resolve"
                    elif pkg_dir is None:
                        why = "an engine module must import"
                    else:
                        why = (f"not a declared dependency of {origin} "
                               f"(declares {declared})")
                    rec["error"] = f"ModuleNotFoundError {exc.name!r} -- {why}"
            except ImportError as exc:
                marker = DISABLED_PACKAGES.get(origin)
                if pkg_dir is not None and marker and marker in str(exc):
                    rec["mode"] = "ast"
                    rec["disabled"] = True
                else:
                    rec["mode"] = "failed"
                    rec["error"] = "".join(traceback.format_exception_only(
                        type(exc), exc)).strip()
            except BaseException as exc:  # noqa: BLE001 -- census every failure
                rec["mode"] = "failed"
                rec["error"] = "".join(
                    traceback.format_exception_only(type(exc), exc)).strip()
            else:
                got = os.path.realpath(getattr(mod, "__file__", "") or "")
                if got != os.path.realpath(path):
                    rec["mode"] = "failed"
                    rec["error"] = f"imported from {got}, not this source"
                else:
                    rec["mode"] = "import"
                    rec.update(registry_names(mod))
                    try:
                        rec["data_names"] = data_names(mod, source, str(path))
                    except BaseException as exc:  # noqa: BLE001
                        rec["mode"] = "failed"
                        rec["error"] = "reading its data names: " + "".join(
                            traceback.format_exception_only(type(exc), exc)).strip()
            if rec["mode"] == "import":
                names = (set(rec["offered"]) | set(rec["offered_gap"])
                         | set(rec["adapter_names"]))
            elif rec["mode"] == "ast":
                names = set(rec["ast_names"])
            else:
                names = set()
            rec["names"] = sorted(names)
            rec["bad"] = {n: why for n in sorted(names)
                          if (why := name_problem(n))}
            if rec["mode"] == "import":
                data = set(rec["data_names"])
            elif rec["mode"] == "ast":
                # Statically every bound public name counts, predicates
                # included: the static reading cannot tell them apart, and
                # a predicate name is held to the same rule anyway.
                data = set(rec["ast_data_names"])
            else:
                data = set()
            rec["data"] = sorted(data)
            rec["data_bad"] = {n: why for n in sorted(data)
                               if (why := data_name_problem(n))}
            records.append(rec)
    return {"engine_file": clausal.__file__, "records": records}


def main(argv: list[str]) -> None:
    only_extra = "--only-extra" in argv
    args = [a for a in argv if a != "--only-extra"]
    root = pathlib.Path(args[0]).resolve()
    extra = [pathlib.Path(a).resolve() for a in args[1:]]
    json.dump(census(root, extra, only_extra), sys.stdout)


if __name__ == "__main__":
    main(sys.argv[1:])
