"""A seam ``-import_from`` of a DATA name from a ``.pl`` module.

Ruling (2026-09-30): ``-import_from(M, [name])`` against a ``.pl`` module
that neither defines ``name`` as a predicate (at any arity) nor binds it
resolves to the ATOM ``name``.  Data needs no declaration (D4), and a ``.pl``
export list holds only ``name/arity`` predicates, so there is nowhere in the
``.pl`` file an author could have "exported" the data name from.  An atom is
global by spelling, so the import binds the spelling itself.

A name that IS bound by M (an exported or defined predicate, a data atom the
file itself uses) takes the ordinary Python ``from M import name`` path,
unchanged; this module only sees the names that path could not find.  A
``.clausal``/``.seam`` target is never touched: it exports data explicitly
in its ``-module(...)`` list, and a name missing there stays an ImportError.

The directive lowers to::

    try:
        from M import a, b as c
    except ImportError as _cs_import_error:
        if not <this module>.bind_data_names(globals(), 'M', {...}, (...),
                                             _cs_import_error):
            raise

so a failure this module does not own re-raises the original error, which
``import_diagnostics.enrich_import_error`` then explains as before.
"""

from __future__ import annotations

import sys
import warnings
import weakref

#: Edit-distance bound for the misspelled-predicate warning, by name length.
#: Names shorter than ``_TYPO_MIN_LEN`` are never warned about: short data
#: atoms (``a1``, ``p``) sit one edit from almost anything.
_TYPO_MIN_LEN = 4

#: The importer-namespace key recording the names this module resolved to
#: data: ``{spelling: atom}`` for the LOCAL name and the dotted remap key
#: (``module.orig``) the rewriter emits for it.  Operator ruling 2026-09-30
#: (follow-up): such a name licenses ``name(...)`` construction at ANY
#: arity in the importer (``terms_to_ast.cell_signature_for_name``).
PL_DATA_NAMES_KEY = "$pl_data_names"


def record_data_name(namespace: dict, module_name: str, orig: str,
                     local: str, atom: str) -> None:
    """Record that *local* (imported as ``module_name.orig``) is the data
    atom *atom* in *namespace*."""
    names = namespace.get(PL_DATA_NAMES_KEY)
    if names is None:
        names = namespace[PL_DATA_NAMES_KEY] = {}
    names[local] = atom
    names[f"{module_name}.{orig}"] = atom


#: ``(importer namespace id, importer file, module, name)`` already warned
#: about -- one load of an importer warns once per name; a fresh load (a new
#: module namespace) warns again.
_warned: set[tuple[int, str, str, str]] = set()

#: Source-derived predicate names per ``.pl`` module object (re-reading the
#: source is the expensive part; the module object is replaced on reload).
_names_cache: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def _is_pl_module(mod) -> bool:
    from clausal.import_hook import PrologLoader  # noqa: PLC0415

    spec = getattr(mod, "__spec__", None)
    return any(isinstance(loader, PrologLoader)
               for loader in (getattr(mod, "__loader__", None),
                              getattr(spec, "loader", None)))


def _predicate_names(mod) -> set[str]:
    """Every name *mod* defines or exports as a predicate, at any arity."""
    try:
        return _names_cache[mod]
    except (KeyError, TypeError):
        pass
    from clausal.import_diagnostics import _defined_names  # noqa: PLC0415
    names = {bare for bare, _ in _defined_names(mod)}
    names.update(_exported_arities(mod) or ())
    try:
        _names_cache[mod] = names
    except TypeError:  # pragma: no cover - not weak-referenceable
        pass
    return names


#: ``{name: arities}`` of each loaded ``.pl`` module's ``module/2`` export
#: list (``_export_arities_of``), or ``_NO_DIRECTIVE``; recorded by the
#: loader while it holds the module items.
_pl_exports: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()

_NO_DIRECTIVE = "no module/2 directive"


def _export_arities_of(module_items):
    """``{name: {arity, ...} | None}`` from every ``-module(...)`` in
    *module_items* (``None``: an entry with no arity, a bare atom, which
    exports the name at every arity), or ``_NO_DIRECTIVE`` when there is
    none.  Every ``name/arity`` entry counts: ``[p/1, p/2]`` is
    ``{'p': {1, 2}}`` (``import_diagnostics._declared_exports`` keeps one
    entry per bare name, for its message, so it cannot answer this)."""
    from clausal.pythonic_ast.nodes import (  # noqa: PLC0415
        Directive, ModuleDeclaration, PrivateDeclaration,
    )
    result, saw, pending = {}, False, []
    for item in module_items or ():
        # An ISO ``name/arity`` entry is a ``predicate_export`` directive
        # item just BEFORE the -module/-private item it belongs to.
        if isinstance(item, Directive) and item.name == "predicate_export":
            pending.extend((functor, arity)
                           for functor, arity, *_ in item.specs)
            continue
        if isinstance(item, PrivateDeclaration):
            pending = []
            continue
        if not isinstance(item, ModuleDeclaration):
            continue
        saw = True
        for functor, arity in pending:
            arities = result.setdefault(functor, set())
            if arities is not None:
                arities.add(arity)
        pending = []
        for entry in item.exports:
            if isinstance(entry, str):
                result[entry] = None
            elif (isinstance(entry, (tuple, list)) and len(entry) == 2
                    and isinstance(entry[0], str)):
                arities = result.setdefault(entry[0], set())
                if arities is not None:
                    arities.add(len(entry[1] or ()))
    return result if saw else _NO_DIRECTIVE


def record_pl_exports(module, module_items) -> None:
    """Record the ``.pl`` *module*'s export list from its *module_items*."""
    try:
        _pl_exports[module] = _export_arities_of(module_items)
    except Exception:  # pragma: no cover - defensive
        _pl_exports.pop(module, None)


def _exported_arities(mod):
    """``{name: {arity, ...} | None}`` for *mod*'s ``module/2`` export list
    (``None``: every arity), or ``None`` when the file has no ``module/2``
    directive.  The loader's record; else (a module loaded before the
    record existed) re-read from source."""
    try:
        result = _pl_exports[mod]
    except (KeyError, TypeError):
        from clausal.import_diagnostics import _module_items_of  # noqa: PLC0415
        try:
            result = _export_arities_of(
                _module_items_of(mod, getattr(mod, "__loader__", None)))
        except Exception:  # pragma: no cover - source unreadable now
            return None
    return None if result is _NO_DIRECTIVE else result


def private_procedure(mod, name: str, selected):
    """The indicator ``name/N`` when importing *name* (every arity when
    *selected* is ``None``, else the arities in *selected*) from the
    ``.pl`` module *mod* names a predicate *mod* DEFINES but does not
    export; else ``None``.

    Operator ruling 2026-10-01: in Clausal code an import of an unexported
    ``.pl`` predicate is an error (Python code is not affected).  A bare
    name is refused when *mod* exports it at no arity; a ``name/N`` entry
    when *mod* defines ``name/N`` and does not export it.  A module with no
    ``module/2`` directive exports everything.  A name *mod* only imports
    (it defines no clauses for it) is not this check's business."""
    if not _is_pl_module(mod):
        return None
    if getattr(getattr(mod, "__spec__", None), "_initializing", False):
        # A circular import: the exporter's database is not complete yet,
        # so "defines" cannot be answered.  Known gap: such an import is
        # not checked.
        return None
    db = getattr(vars(mod).get("$module"), "db", None)
    if db is None:
        return None
    try:
        defined = set(db.arities_for(name))
    except Exception:  # pragma: no cover - defensive
        return None
    if not defined:
        return None
    exports = _exported_arities(mod)
    if exports is None:
        return None
    if name in exports and exports[name] is None:
        return None             # exported with no arity: every arity
    exported = exports.get(name, set())
    if selected is None:
        # Exported at ANY arity imports the name (and so every arity the
        # module defines: a bare entry binds the name, not one arity).
        if exported:
            return None
        return f"{name}/{min(defined)}"
    private = sorted(a for a in selected if a in defined and a not in exported)
    return f"{name}/{private[0]}" if private else None


def _is_predicate_of(mod, name: str) -> bool:
    """The module's database first; the source-derived names (exports with
    no clauses) only when it does not say so."""
    db = getattr(vars(mod).get("$module"), "db", None)
    if db is not None:
        try:
            if db.is_predicate_name(name) or db.arities_for(name):
                return True
        except Exception:  # pragma: no cover - defensive
            pass
    return name in _predicate_names(mod)


def _distance(a: str, b: str, cap: int) -> int:
    """Optimal-string-alignment edit distance (adjacent transposition counts
    as one edit), or ``cap + 1`` once it is known to exceed *cap*."""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev2 = None
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = a[i - 1] != b[j - 1]
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if (prev2 is not None and i > 1 and j > 1
                    and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]):
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        if min(cur) > cap:
            return cap + 1
        prev2, prev = prev, cur
    return prev[-1]


def near_predicates(name: str, predicates) -> list[str]:
    """The predicate names within a small edit distance of *name*: one edit
    for a name of 4-7 characters, two from 8 on."""
    if len(name) < _TYPO_MIN_LEN:
        return []
    cap = 1 if len(name) < 8 else 2
    return sorted(p for p in predicates
                  if p != name and _distance(name, p, cap) <= cap)


def _warn_if_misspelled(mod, name: str, namespace: dict) -> None:
    from clausal.lint_warnings import ClausalImportedDataNameWarning  # noqa: PLC0415

    key = (id(namespace), namespace.get("__file__") or "<unknown>",
           mod.__name__, name)
    if key in _warned:
        return
    near = near_predicates(name, _predicate_names(mod))
    if not near:
        return
    _warned.add(key)
    shown = ", ".join(f"`{p}`" for p in near)
    label = mod.__name__.rsplit(".", 1)[-1]
    warnings.warn(
        f"-import_from({mod.__name__}, [{name}]): {label} defines no "
        f"predicate `{name}`, so `{name}` is imported as the ATOM {name} "
        f"(data needs no declaration). {label} does define the predicate "
        f"{shown}: if that is what you meant, fix the spelling.",
        ClausalImportedDataNameWarning,
        stacklevel=3,
    )


def data_atom(mod, name: str):
    """The atom *name* when a bare ``-import_from`` of *name*, which *mod*
    does not bind, resolves to data under the ruling; else ``None``."""
    if not _is_pl_module(mod):
        return None
    if getattr(getattr(mod, "__spec__", None), "_initializing", False):
        return None
    if _is_predicate_of(mod, name):
        return None
    return sys.intern(name)


# ── Attribute access (operator ruling 2026-10-01) ─────────────────────────────
#
# The import ruling extended to ``getattr(mod, 'name')`` / ``mod.name``: on a
# module loaded from ``.pl`` (either front end, a package's ``__init__.pl``
# included), an atom-shaped name the module neither defines as a predicate
# (any arity) nor binds is the ATOM ``name``.  A module-level ``__getattr__``
# (PEP 562), installed by ``PrologLoader.exec_module`` once the module has
# loaded, so it only ever sees names the module's namespace lacks.
#
# ATOM-SHAPED is ``iso_l3_directives._is_declarable``: a lowercase identifier,
# no Python keyword, no reserved name (``true``, ``false``, ``undefined``,
# ``[]`` ...).  That is the spelling a module can bind as a data atom, the
# name-level shape the import ruling accepts (a bare ``-import_from`` entry
# is a seam identifier), and it excludes every dunder and private name.  NOT
# ``is_auto_declarable_atom``: its extra condition (no builtin or evaluable
# of that spelling) is about a binding SHADOWING the engine's own name in
# the defining file, which an attribute read cannot do; and the import path
# resolves ``-import_from(M, [max])`` to the atom ``max`` too.
#
# Who does NOT get the fallback (the caller keeps AttributeError):
#   - the import machinery: importlib's ``_handle_fromlist`` probe, so
#     ``from pkg import sub`` still imports a submodule, and the IMPORT_FROM
#     opcode in CLAUSAL code only, so a seam ``-import_from`` keeps its own
#     path above (its ``name/N`` refusal and per-importer warning).  In
#     PYTHON code ``from M import name`` is getattr and gets the atom
#     (operator ruling 2026-10-01: in Python code, Python semantics apply);
#   - the engine itself (Python code in the ``clausal`` package): its probes
#     (``getattr(x, 'db', None)``, ``hasattr(mod, n)`` ...) ask whether the
#     module BINDS the name, and keep that meaning;
#   - TOOLING: the Python standard library (unittest's ``load_tests``,
#     doctest, pickle's ``whichmodule``, inspect ...) and the third-party
#     tools in ``_TOOLING_PACKAGES`` (pytest's ``pytest_plugins``, Sphinx's
#     ``setup`` ...), whose hook lookups ``getattr(mod, name, None)`` by a
#     lowercase name would otherwise get a str back and call it;
#   - a name that is an importable submodule of a ``.pl`` package.
# Public code asks existence through ``clausal.has_predicate`` /
# ``clausal.defines_predicate`` / ``clausal.module_binds`` instead.

#: The modules whose attribute probes are import-machinery probes.
_IMPORT_MACHINERY = frozenset({
    "importlib._bootstrap", "_frozen_importlib",
    "importlib._bootstrap_external", "_frozen_importlib_external",
})

#: Third-party TOOLING whose hook lookups (``getattr(mod, 'pytest_plugins',
#: None)``, Sphinx's ``setup`` ...) probe modules by lowercase name: by
#: top-level package.  The Python standard library is tooling too (unittest's
#: ``load_tests``, doctest, pickle's ``whichmodule`` ...), found by path.
_TOOLING_PACKAGES = frozenset({
    "_pytest", "pytest", "pluggy", "sphinx", "docutils", "setuptools",
    "pkg_resources", "coverage", "hypothesis", "IPython", "jedi", "pydoc",
})

#: Names already warned about through attribute access, per module object:
#: once per module and name.
_attr_warned: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def _is_atom_shaped(name) -> bool:
    from clausal.tools.iso_l3_directives import _is_declarable  # noqa: PLC0415
    return type(name) is str and _is_declarable(name)


def _stdlib_dirs() -> tuple:
    import sysconfig  # noqa: PLC0415
    import os  # noqa: PLC0415
    dirs = {sysconfig.get_path(k) for k in ("stdlib", "platstdlib")}
    return tuple(os.path.join(d, "") for d in dirs if d)


_STDLIB_DIRS = _stdlib_dirs()


def _is_stdlib_file(filename: str) -> bool:
    if filename.startswith("<frozen "):
        return True
    return (filename.startswith(_STDLIB_DIRS)
            and "site-packages" not in filename
            and "dist-packages" not in filename)


def _caller_opts_out(frame) -> bool:
    """True when the frame reading the attribute is the import machinery,
    the engine's own Python code, or tooling (see the comment above)."""
    if frame is None:
        return False
    owner = frame.f_globals.get("__name__") or ""
    if owner in _IMPORT_MACHINERY:
        return True
    filename = frame.f_code.co_filename or ""
    if ((owner == "clausal" or owner.startswith("clausal."))
            and filename.endswith(".py")):
        return True     # the engine; not a .clausal/.seam/.pl module under it
    if owner.partition(".")[0] in _TOOLING_PACKAGES:
        return True
    if _is_stdlib_file(filename):
        return True
    # ``from M import name`` (the IMPORT_FROM opcode) in PYTHON code is
    # getattr (operator ruling 2026-10-01, "in Python code, Python semantics
    # apply"), so it gets the atom like ``M.name`` does.  In CLAUSAL code
    # (a compiled .clausal/.seam/.pl module, whose namespace holds
    # ``$module``) the statement is a seam ``-import_from`` or a .pl
    # ``use_module``: it keeps its own path (``bind_data_names``, with its
    # ``name/N`` refusal and per-importer warning, and the .pl importer's
    # plain import).
    if "$module" not in frame.f_globals:
        return False
    try:
        return frame.f_code.co_code[frame.f_lasti] == _IMPORT_FROM
    except (IndexError, AttributeError):  # pragma: no cover - defensive
        return False


def _import_from_opcode() -> int:
    import dis  # noqa: PLC0415
    return dis.opmap["IMPORT_FROM"]


_IMPORT_FROM = _import_from_opcode()


def _is_submodule(mod, name: str) -> bool:
    """True when *name* is an importable submodule of the package *mod*
    (not imported yet, or ``getattr`` would have found it)."""
    if "__path__" not in vars(mod):
        return False
    import importlib.util  # noqa: PLC0415
    try:
        return importlib.util.find_spec(f"{mod.__name__}.{name}") is not None
    except (ImportError, ValueError, AttributeError):
        return False


def _warn_attr_if_misspelled(mod, name: str) -> None:
    from clausal.lint_warnings import ClausalImportedDataNameWarning  # noqa: PLC0415

    try:
        seen = _attr_warned.setdefault(mod, set())
    except TypeError:  # pragma: no cover - not weak-referenceable
        return
    if name in seen:
        return
    seen.add(name)
    near = near_predicates(name, _predicate_names(mod))
    if not near:
        return
    shown = ", ".join(f"`{p}`" for p in near)
    label = mod.__name__.rsplit(".", 1)[-1]
    warnings.warn(
        f"{mod.__name__}.{name}: {label} defines no predicate `{name}`, so "
        f"the attribute is the ATOM {name} (data needs no declaration). "
        f"{label} does define the predicate {shown}: if that is what you "
        f"meant, fix the spelling.",
        ClausalImportedDataNameWarning,
        stacklevel=3,
    )


def install_attribute_fallback(module) -> None:
    """Give the loaded ``.pl`` *module* the PEP 562 ``__getattr__`` that
    answers an unbound atom-shaped data name with its atom."""
    ref = weakref.ref(module)

    def __getattr__(name):
        mod = ref()
        if (mod is not None and _is_atom_shaped(name)
                and not _caller_opts_out(sys._getframe(1))):
            atom = data_atom(mod, name)
            if atom is not None and not _is_submodule(mod, name):
                _warn_attr_if_misspelled(mod, name)
                return atom
        owner = mod.__name__ if mod is not None else "?"
        raise AttributeError(
            f"module {owner!r} has no attribute {name!r}", name=name, obj=mod)

    __getattr__.clausal_pl_data_fallback = True
    vars(module).setdefault("__getattr__", __getattr__)


def record_bound_data_names(namespace: dict, module_name: str,
                            pairs: dict, eligible) -> None:
    """After a SUCCESSFUL ``from module_name import ...``: record each bare
    name the ``.pl`` module binds as a plain data atom with no functor
    signature, so it builds ``name(...)`` at any arity in the importer.

    The native front end binds a data functor its ``.pl`` file uses
    (``v(ok, [...])``) as the atom ``v`` and declares no signature for it,
    where the translator declares ``v(_, _)``; without this the importer
    could build ``v(...)`` under one front end and not the other.  A name
    WITH a signature (the translator's) keeps it."""
    mod = sys.modules.get(module_name)
    if mod is None or not _is_pl_module(mod):
        return
    if getattr(getattr(mod, "__spec__", None), "_initializing", False):
        return
    for local, orig in pairs.items():
        if local not in eligible:
            continue
        atom = _unsigned_data_atom(mod, orig, namespace.get(local))
        if atom is not None:
            record_data_name(namespace, module_name, orig, local, atom)


def _unsigned_data_atom(mod, orig: str, value):
    """*value* when it is *mod*'s plain data atom *orig* with no functor
    signature in *mod*; else ``None``."""
    if type(value) is not str or value != orig:
        return None
    from clausal.logic.compiler.terms_to_ast import functor_signatures_for  # noqa: PLC0415
    if functor_signatures_for(orig, vars(mod)):
        return None
    if _is_predicate_of(mod, orig):
        return None
    return value


def bind_data_names(namespace: dict, module_name: str, pairs: dict,
                    eligible, error: ImportError) -> bool:
    """Finish a failed ``from module_name import ...`` for a ``.pl`` target.

    *pairs* maps each LOCAL name to the original spelling; *eligible* holds
    the local names imported bare (``name``, ``alias(name, local)``) -- a
    ``name/N`` indicator names a predicate and never resolves to data.

    Returns ``False`` when *error* is not this module's to handle (the target
    is not a loaded ``.pl`` module, or is still initialising): the caller
    re-raises it.  Raises a fresh ``ImportError`` shaped like CPython's own
    for the first missing name that may not become data.  Otherwise binds
    every name into *namespace* and returns ``True``.
    """
    mod = sys.modules.get(module_name)
    if mod is None or not _is_pl_module(mod):
        return False
    if getattr(getattr(mod, "__spec__", None), "_initializing", False):
        return False   # a circular import: the name may simply not be bound YET
    missing = object()
    resolved = {}
    for local, orig in pairs.items():
        value = getattr(mod, orig, missing)
        if value is missing:
            if local not in eligible or _is_predicate_of(mod, orig):
                path = getattr(mod, "__file__", None)
                new = ImportError(
                    f"cannot import name {orig!r} from {mod.__name__!r} "
                    f"({path or 'unknown location'})",
                    name=getattr(error, "name", None) or mod.__name__,
                    path=path)
                new.name_from = orig
                raise new from None
            value = sys.intern(orig)
            _warn_if_misspelled(mod, orig, namespace)
            record_data_name(namespace, module_name, orig, local, value)
        resolved[local] = value
    namespace.update(resolved)
    return True
