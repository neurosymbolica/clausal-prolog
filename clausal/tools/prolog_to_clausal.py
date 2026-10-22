"""Prolog → seam translation (Phase 3.3).

Pipeline: .pl source → tokens → Prolog AST → seam (``.seam``) source text

Public API:
    prolog_to_clausal(source, *, dialect=None) -> str
    prolog_ast_to_clausal(pmodule, *, dialect=None) -> str
    emit_clausal_term(term, dialect) -> str
    emit_clausal_item(item, dialect) -> str
"""

from __future__ import annotations

import json
import keyword
import os
import sys
from pathlib import Path


def _is_plain_atom_name(name: str) -> bool:
    """True if *name* can be emitted as a bare lowercase Clausal atom name."""
    return (
        bool(name)
        and name[0].islower()
        and name.isidentifier()
        and not keyword.iskeyword(name)
    )

from clausal.tools.prolog_ast import (
    PAtom, PVar, PNumber, PString, PCompound, PList, PCurly,
    PClause, PDCGRule, PDirective, PQuery, PComment, PModule,
    PTerm, PItem,
)
from clausal.tools.prolog_operators import OperatorTable
from clausal.tools.prolog_dialect import (
    Dialect,
    prolog_var_to_clausal,
    BUILTIN_NAME_MAP,
)
from clausal.templating.term_rewriting import (
    _is_logic_var_name as _engine_is_logic_var_name,
    _titlecase_to_snake,
)
from clausal.tools.prolog_parser import parse
from clausal.tools.prolog_tokenizer import PL_SOURCE_NESTED_COMMENTS
# The two quoted-token writers (spec §6.7): an ATOM is single-quoted, a
# STRING is double-quoted, and which one a literal gets is the whole
# difference between the two terms after THE FLIP.
from clausal.terms import quote_atom as _quote_atom, quote_string as _quote_string


__all__ = [
    "prolog_to_clausal", "prolog_ast_to_clausal",
    "emit_clausal_term", "emit_clausal_item",
    "PrologTranslationError",
]


class PrologTranslationError(Exception):
    """Raised when Prolog source contains constructs that cannot be translated.

    Cut (``!/0``) and if-then-else (``(C -> T ; E)``) are intentionally
    unsupported.  Programs using them must be rewritten to use pure
    alternatives (``dif/2``, reified conditionals, ``once/1``, indexing).
    """


# ── reverse builtin name map ────────────────────────────────────────
# prolog_name -> clausal_name, built from BUILTIN_NAME_MAP

# Prolog builtins whose Clausal predicate name cannot be derived from
# BUILTIN_NAME_MAP alone.  ``memberchk/2`` keeps the Clausal spelling of
# membership, ``in_check/2``, wherever it is called (F033).  ``member/2`` is
# NOT renamed (2026-10-22): its Clausal spelling ``in_`` is also the class of
# the seam's ``in`` operator node (fields position/left/right), so a
# ``member(X, L)`` built as a term -- data, or the goal argument of a builtin
# that receives it as a term, aggregate_all/3's -- was that node, and the
# file did not load ("functor in_/3 was constructed with 2 positional
# argument(s)").  The engine has member/2 under its ISO name; a body goal
# ``member(X, L)`` is still the seam's infix ``X in L``.  Renames apply to
# called names only: as DATA every term keeps its own name
# (``_emit_compound``).
_REVERSE_OVERRIDES: dict[str, str] = {
    "memberchk": "in_check",
}

# (prolog_name, arity) -> clausal_name, consulted BEFORE the name-only map at
# call sites that know the arity.  The name-only map is built from
# BUILTIN_NAME_MAP, which keys on names alone, so a Prolog name shared by two
# Clausal predicates of different arity resolves to whichever won map order:
# ISO ``catch/3`` came back as ``catch_error/3``, which the compiler treats as
# an ordinary call to an undefined predicate rather than as exception handling
# (``catch_error``'s metacall pattern is 2-arg).  ``catch_error`` stays the
# 2-arg form's name via the name-only map.
_REVERSE_ARITY_OVERRIDES: dict[tuple[str, int], str] = {
    ("catch", 3): "catch",
    # catch/2 is no ISO or Scryer predicate; it is how the exporter writes
    # Clausal's catch_error/2, so the round trip brings it back.
    ("catch", 2): "catch_error",
}


def _is_library(term) -> bool:
    """``library(Name)`` -- a use_module spec naming a library."""
    return (isinstance(term, PCompound) and term.functor == "library"
            and len(term.args) == 1)


def _slash_path(term) -> str | None:
    """``a``, ``'a/b'`` or ``a/b/c`` (the ``/``/2 compound) as the path
    string ``a/b/c``; None for anything else."""
    if isinstance(term, PAtom):
        return term.name
    if (isinstance(term, PCompound) and term.functor == "/"
            and len(term.args) == 2):
        left, right = _slash_path(term.args[0]), _slash_path(term.args[1])
        if left is not None and right is not None:
            return f"{left}/{right}"
    return None


def _plain_term(term) -> str:
    """A Prolog-ish rendering of *term* for an error message."""
    if isinstance(term, PAtom):
        return term.name
    if isinstance(term, PVar):
        return term.name
    if isinstance(term, PNumber):
        return repr(term.value)
    if isinstance(term, PString):
        return '"' + term.value + '"'
    if isinstance(term, PList):
        inner = ", ".join(_plain_term(e) for e in term.elements)
        if term.tail is not None:
            inner += "|" + _plain_term(term.tail)
        return f"[{inner}]"
    if isinstance(term, PCompound):
        if term.functor == "/" and len(term.args) == 2:
            return f"{_plain_term(term.args[0])}/{_plain_term(term.args[1])}"
        return (f"{term.functor}("
                + ", ".join(_plain_term(a) for a in term.args) + ")")
    return str(term)


_MODULE_EXTS = (".pl", ".clausal", ".seam", ".py")


def _module_file_exists(cand: str) -> bool:
    """A module file ``cand.<ext>``, or a PACKAGE ``cand/__init__.<ext>``.
    A plain directory (data, tests) is no module: Scryer opens only
    ``cand.pl``, and counting the directory would stop the fallback to the
    dotted reading on ``sys.path``."""
    return any(os.path.isfile(cand + ext)
               or os.path.isfile(os.path.join(cand, "__init__" + ext))
               for ext in _MODULE_EXTS)


def sibling_module_file(path: str, source_path: str) -> str | None:
    """The module file (without its extension) or package directory the
    ``use_module`` path *path* (``sib``, ``a/b``, ``../x``) names BESIDE the
    importing file *source_path*, or None.  Scryer resolves a relative path
    against the importing file's own directory; so do both ``.pl`` front
    ends, before falling back to the dotted reading on ``sys.path``."""
    base = os.path.dirname(os.path.abspath(source_path))
    cand = os.path.normpath(os.path.join(base, path))
    return cand if _module_file_exists(cand) else None


def package_root(source_path: str | None,
                 module_name: str | None) -> str | None:
    """The directory the importer's dotted name *module_name* is relative
    to: climb one directory per dot from the file's directory -- one more
    for a package ``__init__`` file, whose name IS its directory's.

    None unless the climb ROUND-TRIPS: the file's path below that root,
    read as a dotted name, must be *module_name* itself.  A file loaded by
    PATH under a synthetic name (``clausal.testing`` mints
    ``_clausal_test_<stem>``), or under any name its path does not spell,
    would otherwise climb to the wrong root and mis-qualify every sibling
    (``pkg/dom/__init__.pl`` as ``_clausal_test___init__`` climbs to
    ``pkg/`` and names its sibling ``dom.schema``); the callers then take
    the most specific ``sys.path`` entry, which holds the file under the
    name an import actually finds.  The check is geometric only: a name
    its path does spell (``dom`` for ``pkg/dom/__init__.pl``) is trusted."""
    if not (source_path and module_name):
        return None
    source_path = os.path.abspath(source_path)
    modpath = os.path.splitext(source_path)[0]
    depth = module_name.count(".")
    if os.path.splitext(os.path.basename(source_path))[0] == "__init__":
        depth += 1
        modpath = os.path.dirname(source_path)
    root = os.path.dirname(source_path)
    for _ in range(depth):
        root = os.path.dirname(root)
    if os.path.relpath(modpath, root).split(os.sep) != module_name.split("."):
        return None
    return root


def dotted_for_file(cand: str, root: str | None) -> str | None:
    """*cand* (a module path without extension) as a dotted module name:
    relative to the importer's package *root* when known, else to the most
    specific sys.path entry."""
    roots: list[str] = []
    if root is not None:
        roots.append(root)
    entries = sorted({os.path.abspath(e or os.getcwd()) for e in sys.path
                      if isinstance(e, str)}, key=len, reverse=True)
    roots.extend(entries)
    for root in roots:
        rel = os.path.relpath(cand, root)
        if rel.startswith(os.pardir) or os.path.isabs(rel):
            continue
        parts = rel.split(os.sep)
        if all(p.isidentifier() and not keyword.iskeyword(p)
               for p in parts):
            return ".".join(parts)
    return None


def _names_all_native(term) -> bool:
    """True when *term* is a non-empty import list every name of which the
    engine runs natively (after the builtin rename map)."""
    if not isinstance(term, PList) or not term.elements or term.tail:
        return False
    for e in term.elements:
        if isinstance(e, PCompound) and e.functor == "/" and len(e.args) == 2 \
                and isinstance(e.args[0], PAtom):
            name = e.args[0].name
        elif isinstance(e, PAtom):
            name = e.name
        else:
            return False
        name = _reverse_builtin_map().get(name, name)
        if not _engine_has_goal(name):
            return False
    return True


def _has_elements(term) -> bool:
    """True if *term* is a list with at least one element."""
    return isinstance(term, PList) and bool(term.elements)


def _indicator_arity(term) -> int | None:
    """Integer arity of a ``name/N`` predicate indicator's ``N``, or None when
    it is unbound/non-numeric (a var in a template, say)."""
    if isinstance(term, PNumber) and isinstance(term.value, int):
        return term.value
    return None


#: Clausal names whose BUILTIN_NAME_MAP entry is an EXPORT-direction mapping
#: only, never to be run backwards.  ``get/3`` (attribute-list lookup) is
#: exported as ``profile_get/3``, a predicate a downstream helper library
#: defines; a ``.pl`` file's own ``profile_get`` is that library's (or the
#: file's) predicate, not Clausal's ``get`` (2026-09-29: the backwards
#: mapping made ``profile_get(X, k, V)`` answer ``[]`` silently).
_EXPORT_ONLY_NAMES: frozenset = frozenset({"get"})


def _build_reverse_builtin_map() -> dict[str, str]:
    """Build a mapping from Prolog builtin names to clausal names.

    Only renames the engine still NEEDS survive: a Prolog name the engine
    already knows under that very name (``atomic/1``) crosses unchanged, and
    a rename whose Clausal target the engine does not define (``is_atomic``)
    is dropped rather than emitted as a call to nothing.  Evaluable names are
    handled at the arithmetic emitter, not here (see ``_EVALUABLE_RENAMES``).
    """
    rev: dict[str, str] = {}
    for clausal_name, dialect_map in BUILTIN_NAME_MAP.items():
        if clausal_name in _EXPORT_ONLY_NAMES:
            continue
        for prolog_name in dialect_map.values():
            if prolog_name in rev or prolog_name == clausal_name:
                continue
            if _engine_has_goal(prolog_name) \
                    or not _engine_has_goal(clausal_name):
                continue
            rev[prolog_name] = clausal_name
    rev.update(_REVERSE_OVERRIDES)
    return rev


def _engine_has_goal(name: str) -> bool:
    """True when *name* is a goal the engine runs under that spelling: a
    registered builtin or a control/meta construct the compiler lowers."""
    from clausal.logic.builtins._registry import get_builtin_class  # noqa: PLC0415
    from clausal.logic.compiler.ir import MetaKind  # noqa: PLC0415
    import typing  # noqa: PLC0415
    return (get_builtin_class(name) is not None
            or name in typing.get_args(MetaKind)
            or name in _CONTROL_GOAL_NAMES)


def _is_evaluable(name: str, arity: int | None) -> bool:
    from clausal.logic.exact_arith import EVALUABLE  # noqa: PLC0415
    return arity is not None and (name, arity) in EVALUABLE


_REVERSE_BUILTIN_MAP_CACHE: dict[str, str] | None = None


def _reverse_builtin_map() -> dict[str, str]:
    """The reverse map, built on first use (it consults the builtin
    registry, which must not be imported with this module)."""
    global _REVERSE_BUILTIN_MAP_CACHE
    if _REVERSE_BUILTIN_MAP_CACHE is None:
        _REVERSE_BUILTIN_MAP_CACHE = _build_reverse_builtin_map()
    return _REVERSE_BUILTIN_MAP_CACHE


# ── Operator mapping: Prolog operators → clausal syntax ──────────────

# ISO ``\=`` (not unifiable, 8.2.3) and ``\==`` (term non-identity, 8.4.1)
# are TESTS, run once on the terms as they stand.  Clausal's infix ``is not``
# and ``!=`` are the delayed dif/2 and CLP disequality CONSTRAINTS, which
# answer differently as soon as an operand is unbound, so the translation
# emits the quoted ISO builtins, spelled as Clausal source text.
_QUOTED_NOT_UNIFIABLE = "'\\\\='"
_QUOTED_NOT_IDENTICAL = "'\\\\=='"

# Prolog infix → clausal equivalent
_INFIX_MAP = {
    ":-":   "<-",       # clause arrow (body context)
# (Prolog ``is``/2 is handled as a special case → ``eval_(E, R)``, not infix.)
    "=":    "is",       # unification
# (Prolog ``\=``/2 and ``\==``/2 are emitted as the QUOTED ISO builtins
# ``'\='``/``'\=='`` -- see ``_QUOTED_NOT_UNIFIABLE`` below.)
    "\\+":  "not",      # negation-as-failure (prefix, but listed here)
    ";":    "or",       # disjunction
# (Prolog ``==``/2 and ``#=``/2 are handled as special cases in
# ``_emit_compound`` -- ``==`` is not infix in Clausal any more, see the
# 2026-09-18 ruling.)
    "=<":   "<=",       # arithmetic less-or-equal (Prolog =< → Python <=)
    ">=":   ">=",
    "<":    "<",
    ">":    ">",
    "=:=":  "==",       # arithmetic equality → == (context-dependent)
    "=\\=": "!=",       # arithmetic inequality
    "+":    "+",
    "-":    "-",
    "*":    "*",
    "/":    "/",
    ",":    ",",        # conjunction stays
    "=..":  "=..",      # univ — no direct clausal equivalent, keep as comment
# (``**``, ``^``, ``div``, ``//``, ``mod``, ``rem``, ``<<``, ``>>``, ``/\``,
# ``\/`` and ``xor`` are emitted as the quoted ISO evaluable -- see
# ``_ISO_QUOTED_BINARY_OPS``.)
}

# ISO evaluable OPERATORS whose Python spelling means something else in a
# Clausal expression: Python ``//`` floors where ISO truncates, ``**`` on
# integers is an integer where ISO gives a float, ``^`` is Python XOR, and
# ``<<``/``&``/``|``/``~`` are not evaluated by eval_ at all
# (type_error(evaluable, (<<)/2)).  They are emitted as the QUOTED ISO
# evaluable, ``'//'(X, Y)``, which the engine's evaluable table evaluates
# with ISO's meaning (answers checked against Scryer, 2026-09-29).  Until then
# ``2 ^ -1`` answered 0.5 (ISO: type_error(float, 2)) and ``2 ** 3`` answered
# 8 (ISO: 8.0).
_ISO_QUOTED_BINARY_OPS = frozenset({
    "//", "mod", "rem", "div", "**", "^", "<<", ">>", "/\\", "\\/", "xor",
})
_ISO_QUOTED_UNARY_OPS = frozenset({"\\"})

# The arithmetic comparisons: their operands are expressions wherever the
# comparison stands, goal or term position.
_ARITH_COMPARISONS = frozenset({"<", ">", "=<", ">=", "=:=", "=\\="})

#: The comparison and unification builtins whose arity-1 closure
#: (``=(1)``, ``>(2)``) is emitted as the quoted cell for call/N to complete.
_COMPARISON_CLOSURE_FUNCTORS = _ARITH_COMPARISONS | frozenset({
    "=", "\\=", "==", "\\==", "@<", "@>", "@=<", "@>=", "#="})

#: library(clpz)'s operators other than ``#=`` (the seam's ``==``) and the
#: identifiers ``in``/``ins`` (folded to in_domain/3, D21): the relations,
#: the reification connectives and the domain ``..``
#: (``iso_l3_directives.CLPZ_OPS``).  The seam has no operator for them, so
#: they are emitted as ISO cells.
_CLPZ_CELL_OPERATORS = frozenset({
    "#\\=", "#<", "#>", "#=<", "#>=", "#<==>", "#==>", "#<==", "#\\/",
    "#\\", "#/\\", "..", "#"})

# ISO evaluable constants (functors of arity 0 in arithmetic context).
# Emitted as math.* attribute references — emit_module adds the matching
# -import_module(math) preamble. epsilon has no math.* name, so it is
# emitted as the numeric literal (sys.float_info.epsilon) instead (F025).
_EVALUABLE_CONSTANTS = {
    "pi":      "math.pi",
    "e":       "math.e",
    "inf":     "math.inf",
    "nan":     "math.nan",
    "epsilon": "2.220446049250313e-16",  # sys.float_info.epsilon
}

# Prolog prefix → clausal equivalent
_PREFIX_MAP = {
    "\\+": "not",
    "-":   "-",
    "+":   "+",
}

# Prolog library paths → clausal module names
#: `(name, arity)` pairs that Clausal spells as an OPERATOR rather than as a
#: predicate name, so they can never stand in an `-import_from` list. `#=/2` is
#: here because the forward translator emits `:- use_module(library(clpz),
#: [(#=)/2]).` alongside every `#=` it emits (ruling 2026-09-18), and the
#: Clausal spelling of that goal is the `==` operator.
#:
#: `in/2` and `ins/2` (D21) are the same kind of artifact: the forward
#: translator writes `in_domain(V, Lo, Hi)` as clpz's `in`/`ins` and imports
#: them itself; Clausal's in_domain/3 is a global builtin, never imported.
_OPERATOR_ONLY_IMPORTS: frozenset = frozenset({("#=", 2), ("in", 2), ("ins", 2)})

_LIBRARY_TO_MODULE: dict[str, str] = {
    "clpfd": "clausal.logic.clpfd",
    "clpz": "clausal.logic.clpfd",
    "clpb": "clausal.logic.clpb",
    "tabling": "clausal.logic.tabling",
}

#: Libraries whose predicates the engine provides natively, so importing one
#: is a no-op, not a loss (2026-09-29: ``library(dif)`` became
#: ``-import_module(dif)``, "No module named 'dif'").  Each library's core
#: predicates are engine builtins: lists (append/3, length/2, ...), apply
#: (maplist, foldl, include, exclude, partition), dif (dif/2), between
#: (between/3, numlist/3), error (must_be/2, can_be/2), pairs
#: (pairs_keys_values/3, ...), when (when/2), freeze (freeze/2), iso_ext
#: (forall/2, call_cleanup/2, setup_call_cleanup/3).  A predicate of one of
#: these the engine lacks is an ISO existence_error when called.  Any other
#: library is dropped only when every name its import list gives is native.
_BUILTIN_LIBRARIES: frozenset = frozenset({
    "lists", "apply", "dif", "between", "error", "pairs", "when", "freeze",
    "iso_ext", "dcgs",
})


# ── Public API ───────────────────────────────────────────────────────


def prolog_to_clausal(source: str, *, dialect: Dialect | None = None,
                      source_path: str | None = None,
                      module_name: str | None = None,
                      surface: str | None = None) -> str:
    """Translate Prolog source text to clausal source text.

    Parameters
    ----------
    source : str
        Complete Prolog (.pl) source text.
    dialect : Dialect, optional
        Dialect for operator table and name resolution.
        Defaults to Scryer's operator table (``Dialect.scryer_reader``,
        ruling R11).
    source_path, module_name : str, optional
        Where the file lives and the dotted name it is imported as.  A
        relative ``use_module`` path is resolved against the file's own
        directory, as Scryer does; without them only the dotted reading
        (``a/b`` is the module ``a.b`` on ``sys.path``) is available.
    surface : str, optional
        The file's surface (``clausal.end_module.surface_of``), which
        decides whether a module file must end with ``end_module/1`` when
        no setting says otherwise.  Default: from *source_path*, else
        ``pl``.
    """
    if dialect is None:
        dialect = Dialect.scryer_reader()
    # ``use_module(library(clpz))`` brings clpz's operators (``#=``,
    # ``in``, ``..``) into the reader from that directive on, as on the
    # native front end and in Scryer.
    from clausal.tools.iso_l3_directives import (  # noqa: PLC0415
        library_reader_ops)
    pmodule = parse(source, dialect=dialect,
                    nested_comments=PL_SOURCE_NESTED_COMMENTS,
                    library_ops=library_reader_ops)
    return prolog_ast_to_clausal(pmodule, dialect=dialect,
                                 source_path=source_path,
                                 module_name=module_name, surface=surface)


def prolog_ast_to_clausal(pmodule: PModule, *,
                          dialect: Dialect | None = None,
                          source_path: str | None = None,
                          module_name: str | None = None,
                          surface: str | None = None) -> str:
    """Translate a Prolog AST module to clausal source text."""
    if dialect is None:
        dialect = Dialect.scryer_reader()
    pmodule = _check_end_module(pmodule, source_path, surface)
    emitter = _PrologToClausal(dialect, source_path=source_path,
                               module_name=module_name, surface=surface)
    return emitter.emit_module(pmodule)


def _check_end_module(pmodule: PModule, source_path: str | None,
                      surface: str | None) -> PModule:
    """The ``end_module/1`` checks (``clausal.end_module``, shared with the
    native front end), and *pmodule* without the directives they consume:
    ``end_module/1`` and ``set_prolog_flag(require_end_module, V)`` (the
    file's own requirement) emit nothing.  A refusal is a
    :class:`PrologTranslationError` naming the line."""
    from clausal.end_module import (  # noqa: PLC0415
        EndModuleCheck, EndModuleError, parse_flag_value, surface_of)
    if surface is None:
        surface = surface_of(source_path or "") or "pl"
    check = EndModuleCheck()
    open_module: str | None = None
    kept: list = []
    for item in pmodule.items:
        if isinstance(item, PComment):
            kept.append(item)
            continue
        body = item.body if isinstance(item, PDirective) else None
        line = getattr(item, "line", 0)
        try:
            if (isinstance(body, PCompound) and body.functor == "end_module"
                    and len(body.args) == 1):
                arg = body.args[0]
                check.end_module(
                    arg.name if isinstance(arg, PAtom) else arg, open_module,
                    is_var=isinstance(arg, PVar), shown=_plain_term(arg),
                    line=line or None)
                continue
            if isinstance(item, PDirective):
                shown = f"the directive :- {_plain_term(body)}"
            elif isinstance(item, (PClause, PDCGRule)):
                shown = f"the clause {_plain_term(item.head)}"
            elif isinstance(item, PQuery):
                shown = f"the query ?- {_plain_term(item.body)}"
            else:
                shown = f"the {type(item).__name__}"
            check.item(shown)
        except EndModuleError as e:
            raise PrologTranslationError(
                f"line {line}: {e}" if line else str(e)) from None
        if (isinstance(body, PCompound) and body.functor == "module"
                and len(body.args) == 2 and isinstance(body.args[0], PAtom)
                and open_module is None):
            open_module = body.args[0].name
        if (isinstance(body, PCompound) and body.functor == "set_prolog_flag"
                and len(body.args) == 2 and isinstance(body.args[0], PAtom)
                and body.args[0].name == "require_end_module"):
            value = body.args[1]
            setting = parse_flag_value(
                value.name if isinstance(value, PAtom) else None)
            if setting is None:
                raise PrologTranslationError(
                    f"line {line}: :- set_prolog_flag(require_end_module, "
                    f"{_plain_term(value)}): the require_end_module values "
                    f"are true and false (ISO error(domain_error(flag_value, "
                    f"require_end_module+{_plain_term(value)}), "
                    f"set_prolog_flag/2))")
            check.file_setting = setting
            continue
        kept.append(item)
    try:
        check.finish(open_module, surface,
                     os.path.basename(source_path) if source_path else "<.pl>")
    except EndModuleError as e:
        raise PrologTranslationError(str(e)) from None
    if len(kept) == len(pmodule.items):
        return pmodule
    return PModule(tuple(kept), source_path=pmodule.source_path)


def emit_clausal_term(term: PTerm, dialect: Dialect | None = None) -> str:
    """Render a single Prolog AST term as clausal syntax."""
    if dialect is None:
        dialect = Dialect.scryer_reader()
    emitter = _PrologToClausal(dialect)
    return emitter._emit_term(term)


def emit_clausal_item(item: PItem, dialect: Dialect | None = None) -> str:
    """Render a single Prolog AST item as clausal syntax."""
    if dialect is None:
        dialect = Dialect.scryer_reader()
    emitter = _PrologToClausal(dialect)
    return emitter._emit_item(item)


# ── User-defined operator mapping (Step 3.4) ────────────────────────


def load_operator_mapping(path: str | Path) -> dict[str, dict]:
    """Load a user-defined operator mapping file.

    The file is JSON with the structure::

        {
          "operator_mappings": {
            "<>": {"clausal": "NotEqual", "arity": 2},
            ...
          }
        }

    Returns the ``operator_mappings`` dict.
    """
    with open(path) as f:
        data = json.load(f)
    return data.get("operator_mappings", {})


# ── Emitter ──────────────────────────────────────────────────────────


def _native_knows_library(lib: str) -> bool:
    """Whether the native front end knows ``library(<lib>)``
    (``iso_l3_directives._is_known_library``)."""
    from clausal.tools.iso_l3_directives import (  # noqa: PLC0415
        _is_known_library)
    return _is_known_library(lib)


def _unknown_library_message(directive: str, lib: str) -> str:
    """The native front end's unknown-library refusal, for *directive*."""
    from clausal.tools.iso_l3_directives import (  # noqa: PLC0415
        _unknown_library)
    return _unknown_library(directive, lib)


def _library_facade(lib: str) -> "str | None":
    """The ``library(<lib>)`` facade's dotted name, or None (the native
    front end's rule, ``iso_l3_directives._library_facade``)."""
    from clausal.tools.iso_l3_directives import (  # noqa: PLC0415
        _library_facade as facade)
    return facade(lib)


def _clausal_prolog_facade(directive: str, dotted: str) -> "str | None":
    """For a Clausal Prolog import of *dotted*: None when it is a seam or
    Clausal Prolog source (imported as before); a ``.pl`` module is refused
    (:func:`iso_l3_directives._prolog_import_refusal`); the facade
    when it is a module NAME a seam alias resolves to an engine Python
    module (``european_union``, ``units``); else -- a Python path such as
    ``py/datetime`` -- a :class:`PrologTranslationError`.  The native front
    end's rule (``iso_l3_directives._use_module``), with its message."""
    from clausal.tools.iso_l3_directives import (  # noqa: PLC0415
        _engine_module_path, _facade_for, _is_iso_prolog_source,
        _is_python_module, _module_source, _prolog_import_refusal,
        _python_import_refusal, _resolve_import_path)
    target = _engine_module_path(dotted)
    found = _module_source(target)
    via_alias = False
    if found is None:
        target = _resolve_import_path(dotted)
        found = _module_source(target)
        via_alias = target != dotted
    if _is_iso_prolog_source(found):
        # One-way dependency: Clausal Prolog never imports a .pl module.
        raise PrologTranslationError(
            _prolog_import_refusal(directive, dotted, found))
    if found is None or not _is_python_module(found):
        return None
    facade = _facade_for(target) if via_alias else None
    if facade is None:
        raise PrologTranslationError(
            _python_import_refusal(directive, dotted, target))
    return facade


def _python_backed_module(dotted: str):
    """The Python module *dotted* names when it is PYTHON-backed (a ``.py``
    file, not a Clausal source a ``module/2`` list is read from), else None.
    ``py.X`` is the seam's ``clausal.modules.py.X`` (the import hook's
    redirect).  Nothing is imported unless its source is a Python file."""
    import importlib  # noqa: PLC0415
    import importlib.util  # noqa: PLC0415
    from clausal._suffixes import SOURCE_SUFFIXES  # noqa: PLC0415
    candidates = [dotted]
    if dotted.startswith("py.") and "." not in dotted[3:]:
        candidates.insert(0, f"clausal.modules.{dotted}")
    from clausal import _sandbox_state  # noqa: PLC0415
    for cand in candidates:
        if _sandbox_state.ACTIVE:
            # Nothing is imported to find it: a parent package's __init__
            # would run before the gate could refuse it (clausal.sandbox).
            from clausal.sandbox import find_origin  # noqa: PLC0415
            origin = find_origin(cand)
            if origin is None:
                continue
        else:
            try:
                spec = importlib.util.find_spec(cand)
            except (ImportError, ValueError):
                continue
            if spec is None:
                continue
            origin = spec.origin or ""
        if not origin.endswith(".py") or origin.endswith(SOURCE_SUFFIXES):
            return None
        from clausal.sandbox import guard_python_import  # noqa: PLC0415
        guard_python_import(cand, f"use_module({dotted})")
        try:
            mod = importlib.import_module(cand)
        except Exception as e:  # noqa: BLE001
            # Refused HERE, as the native front end refuses it: falling back
            # to the Clausal path would emit indicators and fail later with
            # a misleading "not a Clausal module" at load.
            raise PrologTranslationError(
                f"{dotted} could not be imported: {e}") from e
        from clausal.logic.predicate import namespace_db  # noqa: PLC0415
        if namespace_db(vars(mod)) is not None:
            return None     # a .py module carrying a Clausal database
        return mod
    return None


def _collect_predicate_names(pmodule: PModule) -> set[str]:
    """Every name *pmodule* uses as a predicate: clause/DCG head functors
    (including 0-arity atom heads) and the functor of every compound term.

    BREADTH IS DELIBERATE. Compound functors are swept from EVERY position --
    goal, nested argument, list element, curly body -- not just goal position.
    A name used as a functor anywhere is a predicate or a term constructor,
    and either way the bare Clausal name for it is already spoken for, so
    declaring the same spelling as a `-private` data atom would shadow it.
    Erring wide costs only a str literal (`'x'` denotes the same atom as bare
    `x`, R2); erring narrow silently breaks every call to the shadowed
    predicate, which is the failure this function exists to prevent.
    """
    names: set[str] = set()

    def walk(term) -> None:
        if isinstance(term, PCompound):
            names.add(term.functor)
            for a in term.args:
                walk(a)
        elif isinstance(term, PList):
            for e in term.elements:
                walk(e)
            if term.tail is not None:
                walk(term.tail)
        elif isinstance(term, PCurly):
            walk(term.body)

    for item in pmodule.items:
        head = getattr(item, "head", None)
        if isinstance(head, PAtom):
            names.add(head.name)
        elif head is not None:
            walk(head)
        body = getattr(item, "body", None)
        if body is not None:
            walk(body)
    return names


def _names_not_data_functors(pmodule: PModule) -> set[str]:
    """Names *pmodule* gives a predicate meaning of its own: clause and DCG
    head functors, the names its ``dynamic``/``discontiguous``/``table``
    directives declare, and the names its ``use_module/2`` lists import.

    A compound whose functor is one of these builds a term already (a
    predicate is a declared functor), so it must NOT be declared a data
    functor too -- ``-private([u(_)])`` beside a clause for ``u/1`` would
    shadow the predicate."""
    names: set[str] = set()

    def head_name(head) -> None:
        if isinstance(head, PCompound) and head.functor == ",":
            head = head.args[0]            # DCG pushback head
        if isinstance(head, PCompound):
            names.add(head.functor)
        elif isinstance(head, PAtom):
            names.add(head.name)

    def indicators(term) -> None:
        if isinstance(term, PCompound) and term.functor in (",", "/", "//") \
                and len(term.args) == 2:
            if term.functor == ",":
                indicators(term.args[0])
                indicators(term.args[1])
            elif isinstance(term.args[0], PAtom):
                names.add(term.args[0].name)
        elif isinstance(term, PList):
            for e in term.elements:
                indicators(e)
        elif isinstance(term, PAtom):
            names.add(term.name)

    for item in pmodule.items:
        if isinstance(item, (PClause, PDCGRule)):
            head_name(item.head)
        elif isinstance(item, PDirective) and isinstance(item.body, PCompound):
            body = item.body
            if body.functor in ("dynamic", "discontiguous", "table"):
                for a in body.args:
                    indicators(a)
            elif body.functor == "use_module" and len(body.args) >= 2:
                indicators(body.args[1])
    return names


def _module_qualifiers(pmodule: PModule) -> set[str]:
    """Every atom *pmodule* writes as the module of an ``M:G`` -- in a goal,
    a grammar body or data alike.  The seam's qualified call ``m.g(...)``
    reads ``m`` as the MODULE, so a ``-private([m])`` data atom of that
    name shadows it ("goal shape not yet supported (Call):
    LoadAttr(object='m', ...)" at load)."""
    names: set[str] = set()
    stack: list = []
    for item in pmodule.items:
        for attr in ("head", "body"):
            t = getattr(item, attr, None)
            if t is not None:
                stack.append(t)
    while stack:
        t = stack.pop()
        if isinstance(t, PCompound):
            if (t.functor == ":" and len(t.args) == 2
                    and isinstance(t.args[0], PAtom)):
                names.add(t.args[0].name)
            stack.extend(t.args)
        elif isinstance(t, PList):
            stack.extend(t.elements)
            if t.tail is not None:
                stack.append(t.tail)
        elif isinstance(t, PCurly):
            stack.append(t.body)
    return names


def _own_signatures(pmodule: PModule) -> set[tuple[str, int | None]]:
    """``(name, arity)`` of each predicate *pmodule* defines, declares or
    imports from a non-library module (the items _own_predicate_names
    reads); a grammar rule's nonterminal ``name//N`` is ``name/(N+2)``, and
    an import or declaration with no arity is ``(name, None)``, every
    arity.  A program's own ``forall/1`` leaves forall/2 a meta-call."""
    sigs: set[tuple[str, int | None]] = set()

    def head(h, extra) -> None:
        if isinstance(h, PCompound) and h.functor == ",":
            h = h.args[0]                  # DCG pushback head
        if isinstance(h, PCompound):
            sigs.add((h.functor, len(h.args) + extra))
        elif isinstance(h, PAtom):
            sigs.add((h.name, extra))

    def indicators(term) -> None:
        if isinstance(term, PCompound) and term.functor == "," \
                and len(term.args) == 2:
            indicators(term.args[0])
            indicators(term.args[1])
        elif isinstance(term, PCompound) and term.functor in ("/", "//") \
                and len(term.args) == 2 and isinstance(term.args[0], PAtom):
            n = _indicator_arity(term.args[1])
            if n is not None and term.functor == "//":
                n += 2
            sigs.add((term.args[0].name, n))
        elif isinstance(term, PList):
            for e in term.elements:
                indicators(e)
        elif isinstance(term, PAtom):
            sigs.add((term.name, None))
        elif isinstance(term, PCompound) and term.functor == "as" \
                and len(term.args) == 2 and isinstance(term.args[1], PAtom):
            sigs.add((term.args[1].name, None))

    for item in pmodule.items:
        if isinstance(item, PClause):
            head(item.head, 0)
        elif isinstance(item, PDCGRule):
            head(item.head, 2)
        elif isinstance(item, PDirective) and isinstance(item.body, PCompound):
            body = item.body
            if body.functor in ("dynamic", "discontiguous", "table"):
                for a in body.args:
                    indicators(a)
            elif (body.functor == "use_module" and len(body.args) >= 2
                  and not _is_library(body.args[0])):
                indicators(body.args[1])
    return sigs


def _own_predicate_names(pmodule: PModule) -> set[str]:
    """Names *pmodule* gives a predicate meaning of its own: clause and DCG
    head functors, ``dynamic``/``discontiguous``/``table`` declarations, and
    the names ``use_module/2`` imports from a module that is NOT a
    ``library(...)`` (a library import names the engine's predicate)."""
    names = set()
    for item in pmodule.items:
        if (isinstance(item, PDirective) and isinstance(item.body, PCompound)
                and item.body.functor == "use_module"
                and len(item.body.args) >= 2
                and isinstance(item.body.args[0], PCompound)
                and item.body.args[0].functor == "library"):
            continue
        names |= _names_not_data_functors(PModule((item,)))
    return names


#: argument positions (0-based) that hold a GOAL (or a clause, for the
#: database builtins) in the meta-predicates a ``.pl`` file commonly calls,
#: by ``.pl`` name across arities (``catch``'s also serves catch/2, the
#: spelling of Clausal's catch_error/2).  Covers every special form of
#: ``clausal/logic/special_forms.py`` (tests/test_meta_goal_tables_agree.py).
_META_GOAL_ARGS: dict[str, tuple[int, ...]] = {
    "call": (0,), "once": (0,), "ignore": (0,), "\\+": (0,), "not": (0,),
    "findall": (1,), "bagof": (1,), "setof": (1,), "aggregate_all": (1,),
    "forall": (0, 1), "catch": (0, 2), "call_cleanup": (0, 1),
    "setup_call_cleanup": (0, 1, 2), "freeze": (1,), "when": (1,),
    "call_nth": (0,), "count_all": (0,), "catch_recover": (0, 2),
    "time": (0,), "phrase": (0,),
    "maplist": (0,), "foldl": (0,), "include": (0,), "exclude": (0,),
    "partition": (0,),
    "assert": (0,), "asserta": (0,), "assertz": (0,), "retract": (0,),
    "retractall": (0,), "clause": (0,),
}

#: The arguments of _META_GOAL_ARGS that are CALLED as goals, where a ``[]``
#: is the goal ``[]/0``.  Not phrase/2's (there ``[]`` is the empty terminal
#: list), nor a closure (maplist/2...) or a clause term (assertz/1...).
_NIL_GOAL_ARGS: dict[str, tuple[int, ...]] = {
    f: ix for f, ix in _META_GOAL_ARGS.items()
    if f not in ("phrase", "maplist", "foldl", "include", "exclude",
                 "partition", "assert", "asserta", "assertz", "retract",
                 "retractall", "clause")}

def _is_goal_arity(name: str, arity: int) -> bool:
    """Whether ``name/arity`` is a meta-call whose _NIL_GOAL_ARGS positions
    ARE goals: a special form or goal control at that arity (by its ``.pl``
    name: ``catch/2`` is Clausal's catch_error/2, ``time/1`` its
    time_goal/1), aggregate_all/3, or call/N.  _META_GOAL_ARGS keys on the
    name alone, and ``time(H, M, S, T)`` is a date term, not time/1."""
    from clausal.logic.special_forms import (  # noqa: PLC0415
        GOAL_CONTROLS, GOAL_POSITIONS,
    )
    return (name == "call" and arity >= 1) or (name, arity) in GOAL_POSITIONS \
        or (name, arity) in GOAL_CONTROLS \
        or (name, arity) in (("catch", 2), ("time", 1), ("aggregate_all", 3))


#: library(reif)'s if_/3, which the translator has built in (without
#: library(reif)): its condition and both branches are goals.  Not in
#: _META_GOAL_ARGS, which tests/test_meta_goal_tables_agree.py holds to
#: clausal.logic.special_forms (if_/3 is a compiler goal of its own).
_REIF_GOAL_ARGS: dict[str, tuple[int, ...]] = {"if_": (0, 1, 2)}

#: The arguments emitted as GOALS when their meta-call is a goal: every
#: goal or closure position of _META_GOAL_ARGS except the database
#: builtins' clause argument (a clause TERM, built as data), and if_/3's.
#: A control construct there keeps the seam's goal spelling (``(a, b)``,
#: ``a or b``, ``X is 1``); as DATA it would be the ISO cell, which the seam
#: compiles as a call of ``','/2`` rather than inline.  Not phrase/2,3's
#: grammar body: see _DCG_BODY_ARGS.
_GOAL_EMIT_ARGS: dict[str, tuple[int, ...]] = {
    **{f: ix for f, ix in _META_GOAL_ARGS.items()
       if f not in ("assert", "asserta", "assertz", "retract", "retractall",
                    "clause", "phrase")},
    **_REIF_GOAL_ARGS,
}

#: The GRAMMAR BODY arguments (phrase/2,3's first), emitted as the ISO body
#: term the runtime phrase translates (``_emit_dcg_body_term``), as the
#: native front end passes it (2026-10-22).  In the seam's goal spelling
#: phrase did not read it as a grammar body: ``phrase((g, [c]), L)`` raised
#: existence_error(procedure, g/3), ``phrase(([x] ; [y], []), L)``
#: type_error(callable, <class Or>).
_DCG_BODY_ARGS: dict[str, tuple[int, ...]] = {"phrase": (0,)}

_CONTROL_FUNCTORS = frozenset({",", ";", "->", "*->", "\\+", ":-", "|"})


def _collect_goal_names(pmodule: PModule) -> set[str]:
    """Every name *pmodule* uses as a GOAL -- in a clause body, or in a goal
    argument of a meta-predicate (``findall(X, counter(X), L)``,
    ``assertz(counter(X))``), through the control constructs.  Such a name is
    a predicate (possibly one ``assertz`` creates at run time), never a data
    functor."""
    names: set[str] = set()

    def goal(term) -> None:
        if isinstance(term, PAtom):
            names.add(term.name)
            return
        if not isinstance(term, PCompound):
            return
        f, args = term.functor, term.args
        if f in _CONTROL_FUNCTORS:
            for a in args:
                goal(a)
            return
        if f == "^" and len(args) == 2:
            goal(args[1])
            return
        if f == ":" and len(args) == 2:
            goal(args[1])
            return
        names.add(f)
        for i in _META_GOAL_ARGS.get(f, ()):
            if i < len(args):
                goal(args[i])

    for item in pmodule.items:
        body = getattr(item, "body", None)
        if isinstance(item, PDCGRule):
            _dcg_goal_names(body, goal, names)
        elif body is not None:
            goal(body)
    return names


def _dcg_goal_names(body, goal, names) -> None:
    """The DCG body walk of :func:`_collect_goal_names`: a nonterminal is a
    goal name, ``{G}`` holds goals, a list is terminals."""
    if isinstance(body, PCurly):
        goal(body.body)
    elif isinstance(body, PCompound) and body.functor in _CONTROL_FUNCTORS:
        for a in body.args:
            _dcg_goal_names(a, goal, names)
    elif isinstance(body, PCompound):
        goal(body)
    elif isinstance(body, PAtom):
        names.add(body.name)


#: goal names the compiler lowers itself, beyond ``ir.MetaKind``
_CONTROL_GOAL_NAMES = frozenset({"call", "not", "not_", "and_", "or_"})


def _engine_knows_name(name: str, arity: int) -> bool:
    """True when the engine gives *name* a meaning of its own -- a registered
    builtin, a control/meta construct the compiler lowers (``findall``,
    ``catch``, ``call``, ...), or an arithmetic evaluable.  Such a name is
    never declared a data functor: the declaration would shadow it."""
    from clausal.logic.builtins._registry import get_builtin_class  # noqa: PLC0415
    from clausal.logic.exact_arith import EVALUABLE  # noqa: PLC0415
    from clausal.logic.compiler.ir import MetaKind  # noqa: PLC0415
    import typing  # noqa: PLC0415
    if get_builtin_class(name) is not None:
        return True
    if name in typing.get_args(MetaKind) or name in _CONTROL_GOAL_NAMES:
        return True
    return (name, arity) in EVALUABLE


def _checked_var_name(prolog_name: str) -> str:
    """A Prolog variable's Clausal spelling, or a refusal naming the variable.

    Names cross unchanged, so this is ``prolog_var_to_clausal`` plus one
    check: does the result still read as a VARIABLE to the Clausal loader?

    Almost always yes -- capital-initial and ``_``-led are variables in both
    languages. Two legal ISO spellings are the exception, and the loader's own
    classifier is what decides, so this cannot drift from the rule:

        ``_PI_``   the module-CONSTANT class (one leading, one trailing ``_``)
        ``__Foo``  a dunder, excluded from the variable class

    Translated verbatim these produce Clausal that will not load, from a `.pl`
    file that was well-formed -- and the eventual error comes from the
    constants machinery, naming a generated symptom rather than the Prolog
    variable that caused it. So the refusal happens here, where the offending
    name is still in hand.

    This is the variable-position instance of an invariant the module already
    holds for functors (see ``_emit_functor``'s refusal of ``'Foo'``): the
    translator never emits a name the loader reads as something other than
    what was meant.

    REFUSING IS NOT RENAMING. The mapping stays injective -- no two Prolog
    variables are merged. A name that cannot cross is reported, not repaired.
    The check is deliberately NOT inside ``prolog_var_to_clausal``: making
    that function partial would tempt a future caller into a "safe" rename,
    which is how non-injectivity arrived the first time.
    """
    name = prolog_var_to_clausal(prolog_name)
    # ``_`` is the anonymous variable. It fails the classifier by design
    # (it names nothing) and is handled by the reader, not by this rule.
    if name == "_" or _engine_is_logic_var_name(name):
        return name
    # Only one reason is left to reject a name here.  Until 2026-09-11 a
    # second one existed -- one leading and one trailing underscore was the
    # module-CONSTANT class -- but constants are spelled like atoms now, so
    # ``_Pi_`` crosses as an ordinary variable and needs no diagnostic.
    detail = ("Clausal excludes names beginning with a double underscore "
              "from the logic-variable class")
    # Only offer the de-doubled spelling when it is itself a variable.
    # ``__`` would reduce to ``_``, the ANONYMOUS variable, and renaming
    # a named variable to the wildcard changes what the clause means --
    # every occurrence would become independent.
    single = name[1:]
    remedy = (
        "Rename the variable in the Prolog source to use a single "
        f"leading underscore ({single!r}) and translate again."
        if _engine_is_logic_var_name(single)
        else "Rename the variable in the Prolog source to a single "
             "leading underscore followed by a letter, or to a "
             "capital-initial name, and translate again."
    )
    raise PrologTranslationError(
        f"Prolog variable {prolog_name!r} has no Clausal variable spelling: "
        f"{detail}, so the translated file would not load.\n" + remedy
    )


#: Lowercase names that are NOT atoms when written bare in Clausal source:
#: ``undefined`` is the alias of the truth value ``Undefined`` (the alias
#: fold, docs/kleene), so a Prolog atom of that spelling is emitted quoted.
#: (``true``/``false`` are mapped to ``True``/``False`` on purpose -- see
#: ``_BUILTIN_ATOM_REWRITES``.)
_RESERVED_BARE_NAMES: frozenset = frozenset({"undefined"})


class _PrologToClausal:
    """Translates Prolog AST → clausal source text."""

    def __init__(self, dialect: Dialect,
                 operator_mappings: dict[str, dict] | None = None, *,
                 source_path: str | None = None,
                 module_name: str | None = None,
                 surface: str | None = None):
        self._dialect = dialect
        self._source_path = source_path
        self._module_name = module_name
        if surface is None:
            from clausal.end_module import surface_of  # noqa: PLC0415
            surface = surface_of(source_path or "") or "pl"
        #: The file's surface: under ``clausal_prolog`` a Python module is
        #: no import target (the native front end refuses it the same way).
        self._surface = surface
        self._user_ops = operator_mappings or {}
        self._data_atoms: set[str] = set()  # atoms used as data values
        # > 0 while emitting text the seam reads as SOURCE, not as a term:
        # a generic directive's arguments and a ``{...}`` term.  There
        # ``+ - * /`` keep their seam spelling (``foo / 0``); elsewhere a
        # data operator term is the ISO cell ``'/'(foo, 0)`` (2026-10-20).
        self._seam_operators = 0
        # THE FLIP (2026-09-06-atoms-as-cells-strings §7): a Prolog
        # ``"..."`` is a STRING and is emitted as a double-quoted literal,
        # which only MEANS a string under ``-double_quotes(chars)``.  The
        # module emitter writes that directive iff at least one string was
        # emitted, so a translated module that has no strings keeps the
        # engine default and no directive it does not need.
        self._emitted_string = False
        # The double_quotes flag in force at the current item (``chars``,
        # ``codes`` or ``atom``), and the mode the emitted module is in
        # (never ``codes``: Clausal has no such module mode).
        self._dq_mode = "chars"
        self._dq_engine = "chars"
        # Names this module uses as a PREDICATE (clause-head or goal
        # functor). Populated by emit_module before the emission pass.
        self._predicate_names: set[str] = set()
        # C1 (2026-09-29): functors of compound DATA terms (``p(f(1)).``,
        # ``X = g(2)``), name -> arities.  Declared ``-private([f(_)])`` so
        # the term builds; a Prolog compound needs no declaration.
        self._data_functors: dict[str, set[int]] = {}
        # Names the program defines, declares, or imports from a non-library
        # module: they mean the program's own predicate, so no builtin
        # rename applies to them.  Populated by emit_module.
        self._own_names: set[str] = set()
        self._own_sigs: set[tuple[str, int | None]] = set()
        self._own_any: set[str] = set()
        # Atoms written as the module of an ``M:G`` (_module_qualifiers).
        self._qualifiers: set[str] = set()
        # Names this module uses in GOAL position (a body goal, or a goal
        # argument of a meta-predicate).  Populated by emit_module.
        self._goal_names: set[str] = set()

    def emit_module(self, pmodule: PModule) -> str:
        """Emit a complete module as clausal source text."""
        self._predicate_names = _collect_predicate_names(pmodule)
        self._own_names = _own_predicate_names(pmodule)
        self._own_sigs = _own_signatures(pmodule)
        self._qualifiers = _module_qualifiers(pmodule)
        # Names an import adds to _own_names while emitting (a .pl module's
        # export list): arity unknown here, so every arity.
        self._own_any: set[str] = set()
        self._goal_names = _collect_goal_names(pmodule)
        lines: list[str] = []
        for item in pmodule.items:
            try:
                text = self._emit_item(item)
            except PrologTranslationError as e:
                # Name the source line: a refusal must point at the Prolog
                # the user wrote, not at a translation they never see.
                line = getattr(item, "line", 0)
                if line and not str(e).startswith("line "):
                    raise PrologTranslationError(f"line {line}: {e}") from e
                raise
            if text is not None:
                lines.append(text)
        body = "\n\n".join(lines) + "\n"
        # Prepend auto-generated directives.
        preamble_parts: list[str] = []
        # FIRST, above every other directive: it is position-sensitive and
        # governs the literals below it.
        if self._emitted_string:
            preamble_parts.append("-double_quotes(chars)")
        if "math." in body:
            preamble_parts.append("-import_module(math)")
        private = sorted(self._data_atoms)
        not_data = _names_not_data_functors(pmodule) | _collect_goal_names(pmodule)
        for name, arities in sorted(self._data_functors.items()):
            # One -private entry per arity the name is used at as data: a
            # declaration's field names are per (name, arity) (operator
            # ruling 2026-09-29), so ``box(1)`` and ``box(1, 2)`` declare
            # ``box(_)`` and ``box(_, _)``.
            if name in not_data or name in _RESERVED_BARE_NAMES:
                continue
            known = {a for a in arities if _engine_knows_name(name, a)}
            if known and len(arities) > 1:
                # The engine knows the name at one of its arities (an
                # evaluable ``atan2/2`` beside data ``atan2/3``): a
                # declaration at the other would answer the known arity's
                # construction too, so the name is left undeclared, as it
                # was before (roborev on the per-arity ruling).
                continue
            for arity in sorted(arities - known):
                private.append(f"{name}({', '.join(['_'] * arity)})")
        if private:
            atom_list = ", ".join(private)
            preamble_parts.append(f"-private([{atom_list}])")
        if preamble_parts:
            body = "\n".join(preamble_parts) + "\n\n" + body
        return body

    def _emit_item(self, item: PItem) -> str | None:
        if isinstance(item, PClause):
            return self._emit_clause(item)
        if isinstance(item, PDCGRule):
            return self._emit_dcg_rule(item)
        if isinstance(item, PDirective):
            return self._emit_directive(item)
        if isinstance(item, PQuery):
            # A comment here was a silent drop: the goal never ran.  (Scryer
            # skips it too, but saying nothing is the failure this module
            # refuses; ISO prolog text holds only clauses and directives.)
            raise PrologTranslationError(
                f"?- {_plain_term(item.body)}: a query in program text is "
                "not run on load (ISO 6.2: prolog text is clauses and "
                "directives). Remove it, or write the goal as a test/1 "
                "clause.")
        if isinstance(item, PComment):
            return f"# {item.text}"
        raise PrologTranslationError(
            f"cannot translate item {type(item).__name__}")

    # ── Clauses ──────────────────────────────────────────────────────

    def _emit_clause(self, clause: PClause) -> str:
        head = self._emit_head(clause.head)
        if clause.body is None:
            # Fact: trailing comma
            return f"{head},"
        # Rule: head <- (body)
        body = self._emit_body(clause.body)
        return f"{head} <- ({body})"

    @staticmethod
    def _is_nil(term: PTerm) -> bool:
        """The atom ``[]``, spelled ``[]`` or ``'[]'`` (D70: one atom)."""
        return ((isinstance(term, PList) and not term.elements
                 and term.tail is None)
                or (isinstance(term, PAtom) and term.name == "[]"))

    @staticmethod
    def _nil_head_refused() -> PrologTranslationError:
        # ISO makes ``[]`` an atom, so a text may define ``[]/N`` -- the
        # native front end does.  This translator writes seam text, whose
        # predicate names are Python identifiers, so it cannot: refuse,
        # rather than drop the clause (``[].`` used to load and define
        # nothing) or emit a ``[] >> ...`` that dies with a TypeError.
        return PrologTranslationError(
            "Prolog functor '[]' cannot be translated to a Clausal "
            "predicate name: the translator writes seam text, whose "
            "predicate names are Python identifiers, so it cannot define "
            "the predicate [] (a clause, fact or grammar rule headed [] or "
            "'[]').\nLoad the file with the native front end (the default; "
            "unset CLAUSAL_PL_FRONTEND), which defines it, or rename the "
            "predicate.")

    def _emit_head(self, term: PTerm) -> str:
        """Emit a clause head as a clausal predicate call."""
        if self._is_nil(term) or (isinstance(term, PCompound)
                                  and term.functor == "[]"):
            raise self._nil_head_refused()
        # A ','/2 head is a DCG pushback (`Head, [Tokens] --> Body`), not a
        # callable predicate — emitting it bare produced invalid Python
        # silently (F039). Reject with a clear message.
        if isinstance(term, PCompound) and term.functor == ",":
            raise PrologTranslationError(
                "DCG pushback heads ('Head, [Tokens] --> Body') are not "
                "supported by the translator.\n"
                "Rewrite the grammar rule without a pushback list."
            )
        if isinstance(term, PCompound):
            name = self._predicate_name(term.functor, len(term.args))
            if not term.args:
                return f"{name}()"
            args = self._emit_args(term.functor, term.args)
            return f"{name}({args})"
        if isinstance(term, PAtom):
            name = self._predicate_name(term.name, 0)
            return f"{name}()"
        return self._emit_term(term)

    def _emit_body(self, body: PTerm) -> str:
        """Emit a clause body as comma-separated goals."""
        goals = self._flatten_conjunction(body)
        parts = [self._emit_goal(g) for g in goals]
        return ", ".join(parts)

    def _emit_clpq_constraint(self, c: PTerm) -> str:
        if (isinstance(c, PCompound) and c.functor in ("=", "=:=")
                and len(c.args) == 2):
            return (f"{self._emit_expr(c.args[0])} == "
                    f"{self._emit_expr(c.args[1])}")
        # A constraint, not data: the seam's comparison operators.
        self._seam_operators += 1
        try:
            return self._emit_term(c)
        finally:
            self._seam_operators -= 1

    def _emit_goal(self, goal: PTerm) -> str:
        """Emit a single goal in body context."""
        # A10-F001: a body-position cut must be REJECTED, not emitted as a
        # dead ``Cut()`` goal (no Cut predicate exists — the query later died
        # with KeyError). Delegate to _emit_atom, which raises the documented
        # PrologTranslationError (the cut-free contract, docs/import.md).
        if isinstance(goal, PAtom) and goal.name == "!":
            return self._emit_atom(goal)
        # A body goal ``[]`` CALLS the predicate ``[]/0`` (ISO: ``[]`` is
        # an atom), as on the native front end.  Emitted bare it was the
        # seam's empty list, which as a goal succeeded: ``t :- [].`` was
        # true with no ``[]/0`` defined, where ISO raises
        # existence_error(procedure, []/0).
        if self._is_nil(goal):
            return "call([])"
        # A variable goal is call(G) (ISO 7.6.2); the seam refuses a bare
        # variable in goal position (BareGoalVariableError at load).
        if isinstance(goal, PVar):
            return f"call({self._emit_term(goal)})"
        # D21: the forward translator's in_domain/3 type dispatch folds back.
        folded = self._fold_in_domain(goal)
        if folded is not None:
            return folded
        # library(clpq)'s {C}: the seam's set goal, one element per
        # constraint, `=` and `=:=` both equality (`==`), as the native front
        # end lowers it.  `{X + Y = 3, X - Y = 1}` used to come out as ONE
        # element `(X + Y is 3, ...)` -- a SetGoalElementError at load.
        if isinstance(goal, PCurly):
            return "{" + ", ".join(
                self._emit_clpq_constraint(c)
                for c in self._flatten_conjunction(goal.body)) + "}"
        # A conjunction in goal position (inside `;` or `\\+`) is goals, not a
        # tuple term: `( {X = Y}, fail ; true )` emitted `{X is Y}`, a
        # SetGoalElementError at load.
        if isinstance(goal, PCompound) and goal.functor == "," and len(goal.args) == 2:
            return "(" + ", ".join(
                self._emit_goal(g) for g in self._flatten_conjunction(goal)) + ")"
        # Disjunction: (A ; B) → (A or B)
        if isinstance(goal, PCompound) and goal.functor == ";":
            return self._emit_disjunction(goal)
        # If-then: (Cond -> Then) — REJECTED
        if isinstance(goal, PCompound) and goal.functor == "->":
            return self._emit_if_then(goal)
        # Negation: \+(Goal) → not Goal
        if isinstance(goal, PCompound) and goal.functor == "\\+" and len(goal.args) == 1:
            inner = self._emit_goal(goal.args[0])
            return f"not {inner}"
        # Unification: X = Y → X is Y
        if isinstance(goal, PCompound) and goal.functor == "=" and len(goal.args) == 2:
            left = self._emit_term(goal.args[0])
            right = self._emit_term(goal.args[1])
            return f"{left} is {right}"
        # Dis-unification: X \= Y → '\='(X, Y), ISO "not unifiable" (8.2.3).
        # NOT ``X is not Y``: that is dif/2, a DELAYED constraint, so
        # ``X \= 1, X = 2`` succeeded where ISO fails (the test runs once,
        # on the terms as they are now).
        if isinstance(goal, PCompound) and goal.functor == "\\=" and len(goal.args) == 2:
            left = self._emit_term(goal.args[0])
            right = self._emit_term(goal.args[1])
            return f"{_QUOTED_NOT_UNIFIABLE}({left}, {right})"
        # Arithmetic is: R is Expr → eval_(Expr, R) — the eager arithmetic
        # builtin (the former ':=' operator, now deprecated).
        if isinstance(goal, PCompound) and goal.functor == "is" and len(goal.args) == 2:
            result = self._emit_term(goal.args[0])
            expr = self._emit_expr(goal.args[1])
            return f"eval_({expr}, {result})"
        # Structural inequality: X \== Y → '\=='(X, Y), ISO term
        # non-identity (8.4.1).  NOT ``X != Y``: unquoted ``!=`` is the CLP
        # disequality constraint, which DELAYS on unbound operands -- so
        # ``X \== Y, X = 1, Y = 1`` failed where ISO succeeds.
        if isinstance(goal, PCompound) and goal.functor == "\\==" and len(goal.args) == 2:
            left = self._emit_term(goal.args[0])
            right = self._emit_term(goal.args[1])
            return f"{_QUOTED_NOT_IDENTICAL}({left}, {right})"
        # Comparison operators
        if isinstance(goal, PCompound) and goal.functor in ("<", ">", ">=", "=<") and len(goal.args) == 2:
            left = self._emit_expr(goal.args[0])
            right = self._emit_expr(goal.args[1])
            op = "<=" if goal.functor == "=<" else goal.functor
            return f"{left} {op} {right}"
        # Arithmetic comparison: =:=, =\=
        if isinstance(goal, PCompound) and goal.functor == "=:=" and len(goal.args) == 2:
            left = self._emit_expr(goal.args[0])
            right = self._emit_expr(goal.args[1])
            return f"{left} == {right}"
        if isinstance(goal, PCompound) and goal.functor == "=\\=" and len(goal.args) == 2:
            left = self._emit_expr(goal.args[0])
            right = self._emit_expr(goal.args[1])
            return f"{left} != {right}"
        # member/2 → X in List
        if isinstance(goal, PCompound) and goal.functor == "member" and len(goal.args) == 2:
            elem = self._emit_term(goal.args[0])
            lst = self._emit_term(goal.args[1])
            return f"{elem} in {lst}"
        # Regular compound goal → a call under the same name
        if isinstance(goal, PCompound):
            return self._emit_compound(goal, goal=True)
        return self._emit_term(goal)

    def _emit_disjunction(self, term: PTerm) -> str:
        """Emit (A ; B) as (A or B). Reject if-then-else."""
        if not isinstance(term, PCompound) or term.functor != ";" or len(term.args) != 2:
            return self._emit_goal(term)

        left, right = term.args
        # If-then-else: (Cond -> Then ; Else) — REJECTED
        if isinstance(left, PCompound) and left.functor == "->" and len(left.args) == 2:
            raise PrologTranslationError(
                "If-then-else (( -> ; )) cannot be translated to Clausal.\n"
                "ISO defines (C -> T ; E) in terms of cut, so it inherits "
                "cut's problems — non-monotonicity, broken completeness, and "
                "unsound interaction with constraints.\n"
                "Rewrite using pure alternatives:\n"
                "  - Reified if-then-else: (THEN if COND else ELSE)\n"
                "  - Separate clauses with dif/2 guards\n"
                "  - CLP(FD) / CLP(B) constraints\n"
                "See: docs/reified_ite.md, docs/for_prolog_programmers.md"
            )

        left_s = self._emit_goal(left)
        right_s = self._emit_goal(right)
        return f"({left_s} or {right_s})"

    def _emit_if_then(self, term: PCompound) -> str:
        """Bare (Cond -> Then) without else — REJECTED."""
        raise PrologTranslationError(
            "If-then (( -> )) cannot be translated to Clausal.\n"
            "The -> operator is defined in terms of cut and inherits "
            "cut's problems.\n"
            "Rewrite using pure alternatives:\n"
            "  - Reified if-then-else: (THEN if COND else ELSE)\n"
            "  - Separate clauses with dif/2 guards\n"
            "See: docs/reified_ite.md, docs/for_prolog_programmers.md"
        )

    # ── DCG rules ────────────────────────────────────────────────────

    def _emit_dcg_rule(self, rule: PDCGRule) -> str:
        # A ','/2 DCG head is a pushback (`Head, [Tokens] --> Body`), which
        # Clausal expresses as `(Head, [Tokens]) >> (Body)`; translate it
        # faithfully rather than mangling it into invalid Python (F039).
        if isinstance(rule.head, PCompound) and rule.head.functor == ",":
            base = rule.head.args[0]
            if self._is_nil(base) or (isinstance(base, PCompound)
                                      and base.functor == "[]"):
                raise self._nil_head_refused()
            # The nonterminal is a HEAD (``pb()``, not the atom ``'pb'``,
            # which the seam's ``>>`` did not read as one: "unsupported
            # operand type(s) for >>"); the pushback is its terminal list.
            parts = [self._emit_head(base)] + [
                self._emit_term(p)
                for p in self._flatten_conjunction(rule.head.args[1])]
            head = "(" + ", ".join(parts) + ")"
        else:
            head = self._emit_head(rule.head)
        body = self._emit_dcg_body(rule.body)
        return f"{head} >> ({body})"

    def _emit_dcg_body(self, body: PTerm) -> str:
        """Emit DCG rule body."""
        # Conjunction in DCG
        goals = self._flatten_conjunction(body)
        parts = [self._emit_dcg_goal(g) for g in goals]
        return ", ".join(parts)

    def _emit_dcg_goal(self, goal: PTerm) -> str:
        """Emit a single DCG body goal."""
        # Terminal list: [a, b, c]
        if isinstance(goal, PList):
            tail = goal.tail
            while isinstance(tail, PList):
                tail = tail.tail
            if tail is not None and not self._list_tail(tail):
                # ISO 7.14 / Scryer: a terminal list must be a list;
                # ``g --> [x|foo]`` is type_error(list, [x|foo]), as the
                # native front end refuses it.  Emitted, it would be the
                # cons cell ('.', x, foo) read as a nonterminal call.
                raise PrologTranslationError(
                    f"grammar rule: a terminal list ends in "
                    f"{_plain_term(tail)}: an improper list is no terminal "
                    f"list (ISO type_error(list, ...))")
            return self._emit_term(goal)
        # Inline goal: {Goal}. Braces mark DCG *body* position in Clausal;
        # emit them explicitly so the goal is not rewritten as a non-terminal.
        # A single goal → ``{Goal}``; a conjunction ``{A, B, C}`` → ``{(A, B, C)}``
        # (the parenthesised-conjunction form, which loads on both the old and
        # the multi-goal-aware engine).
        if isinstance(goal, PCurly):
            inner_goals = self._flatten_conjunction(goal.body)
            if len(inner_goals) == 1:
                return "{" + self._emit_goal(inner_goals[0]) + "}"
            parts = ", ".join(self._emit_goal(g) for g in inner_goals)
            return "{(" + parts + ")}"
        # Pushback: comma([T], ...) — handled as regular term
        # Negation in DCG
        if isinstance(goal, PCompound) and goal.functor == "\\+" and len(goal.args) == 1:
            inner = self._emit_dcg_goal(goal.args[0])
            return f"not {inner}"
        # Disjunction in DCG: each branch is a grammar body (``|`` is
        # ``;``, ISO 7.14.2).  Through the goal emitter a branch's terminal
        # list ``[]`` was the goal ``call([])`` (existence_error(procedure,
        # []/2) for ``r --> [x] ; [y], []``), and ``|`` did not translate.
        if (isinstance(goal, PCompound) and goal.functor in (";", "|")
                and len(goal.args) == 2 and goal.functor not in self._user_ops):
            left, right = goal.args
            if isinstance(left, PCompound) and left.functor in ("->", "*->"):
                return self._emit_disjunction(goal)     # refused
            def branch(b: PTerm) -> str:
                text = self._emit_dcg_body(b)
                return (f"({text})" if len(self._flatten_conjunction(b)) > 1
                        else text)
            return f"({branch(left)} or {branch(right)})"
        # Regular non-terminal
        if isinstance(goal, PCompound):
            return self._emit_compound(goal, goal=True)
        # An atom nonterminal ``r --> s.`` is the call ``s()``: the quoted
        # atom ``'s'`` the term emitter writes is, in a seam grammar body,
        # the TERMINALS of its characters (``phrase(r, L)`` answered
        # ``L = [s]``, and ``[r, '1']`` for ``r1``).  ``true``/``fail``
        # keep the seam's truth values; ``!`` and ``[]`` are the term
        # emitter's (refused / the empty terminal list).
        if (isinstance(goal, PAtom) and not self._is_nil(goal)
                and goal.name not in ("!", "true", "fail", "false")):
            return f"{self._predicate_name(goal.name, 0)}()"
        return self._emit_term(goal)

    # ── Directives ───────────────────────────────────────────────────

    def _emit_directive(self, directive: PDirective) -> str:
        body = directive.body
        # :- module(Name, Exports)
        if isinstance(body, PCompound) and body.functor == "module" and len(body.args) == 2:
            return self._emit_module_directive(body)
        # :- use_module(library(Lib), Imports) or :- use_module(library(Lib))
        if isinstance(body, PCompound) and body.functor == "use_module":
            return self._emit_use_module(body)
        # :- dynamic pred/N
        if isinstance(body, PCompound) and body.functor == "dynamic":
            return self._emit_meta_directive("dynamic", body)
        # :- discontiguous pred/N
        if isinstance(body, PCompound) and body.functor == "discontiguous":
            return self._emit_meta_directive("discontiguous", body)
        # :- table pred/N
        if isinstance(body, PCompound) and body.functor == "table":
            return self._emit_meta_directive("table", body)
        # :- double_quotes(Mode)
        #
        # THE FLIP (2026-09-06-atoms-as-cells-strings §7): clausal spells this
        # directive the same way, and the module emitter above writes it into
        # the preamble (FIRST, because it is position-sensitive).  Routing it
        # through the generic branch instead produced ``-DoubleQuotes(chars)``
        # -- a predicate-shaped directive nothing reads -- next to a second,
        # auto-generated ``-double_quotes(chars)``, and ``chars`` was
        # additionally collected as a data atom into ``-private([chars])``.
        # ``:- set_prolog_flag(double_quotes, Mode)`` is the ISO spelling
        # (7.11.2.5) and the one the forward translator emits (item J,
        # 2026-09-07: Scryer refuses ``:- double_quotes(chars).`` at load).
        # Both spellings carry the same mode across.
        if (isinstance(body, PCompound) and body.functor == "set_prolog_flag"
                and len(body.args) == 2 and isinstance(body.args[0], PAtom)
                and body.args[0].name == "double_quotes"):
            body = PCompound("double_quotes", (body.args[1],))
        if (isinstance(body, PCompound) and body.functor == "double_quotes"
                and len(body.args) == 1):
            # The flag governs every later "..." (ISO 7.11.2.5), and the
            # translator honours it AT THE LITERAL: each PString is emitted
            # in the mode in force where it stands (``_emit_string``), so
            # ``codes`` -- which Clausal has no module mode for -- is kept
            # too (2026-09-29; it was a comment, and "ab" stayed chars).
            # The module's own mode follows for chars/atom, so
            # current_prolog_flag(double_quotes, M) reports it.
            mode = body.args[0]
            mode_name = mode.name if isinstance(mode, PAtom) else None
            if mode_name not in ("chars", "codes", "atom"):
                raise PrologTranslationError(
                    f":- set_prolog_flag(double_quotes, {_plain_term(mode)}): "
                    "ISO's double_quotes values are chars, codes and atom "
                    "(Scryer: domain_error(flag_value, double_quotes+"
                    f"{_plain_term(mode)})).")
            self._dq_mode = mode_name
            if mode_name == "codes":
                return (f"# double_quotes(codes): each \"...\" below is "
                        "emitted as its list of character codes")
            if mode_name == self._dq_engine:
                # Already the module's mode (chars: the preamble carries
                # it); emitting it again would double it.
                if mode_name == "chars":
                    self._emitted_string = True
                return None
            self._dq_engine = mode_name
            return f"-double_quotes({mode_name})"
        # :- set_prolog_flag(Flag, Value) for any other flag carries across as
        # the directive of the same name; the value is emitted QUOTED, so an
        # atom such as ``fail`` stays the atom rather than becoming a goal or
        # a truth value.
        if (isinstance(body, PCompound) and body.functor == "set_prolog_flag"
                and len(body.args) == 2 and isinstance(body.args[0], PAtom)):
            flag, value = body.args
            if isinstance(value, PAtom):
                v = "'" + value.name.replace("\\", "\\\\").replace("'", "\\'") + "'"
            else:
                v = self._emit_term(value)
            return f"-set_prolog_flag({flag.name}, {v})"
        # :- op(P, T, N): the READER has already applied it (the terms
        # below it parse with the operator), which is its effect on a
        # program's text.  This seam translation keeps no run-time effect
        # (the native front end's run-time table, current_op/3's, is
        # clausal.tools.prolog_operators.runtime_op_table), so what remains
        # is a comment recording the declaration.
        if isinstance(body, PCompound) and body.functor == "op" and len(body.args) == 3:
            return (f"# operator: op({_plain_term(body.args[0])}, "
                    f"{_plain_term(body.args[1])}, {_plain_term(body.args[2])}) "
                    "-- applied by the reader to the terms below")
        # Generic directive: the seam's directive handlers read their
        # arguments as SOURCE (``-constants_number_currency(snap_max/2,
        # ...)`` wants the written ``name/arity``), so the operators keep
        # their seam spelling here (``_seam_operators``).
        self._seam_operators += 1
        try:
            return f"-{self._emit_term(body)}"
        finally:
            self._seam_operators -= 1

    def _emit_module_directive(self, body: PCompound) -> str:
        name = self._emit_atom_name(body.args[0])
        exports = self._emit_export_list(body.args[1])
        return f"-module({name}, {exports})"

    def _emit_use_module(self, body: PCompound) -> str:
        """Emit :- use_module(...) as -import_from(...) or -import_module(...).

        Never a comment in place of an import (2026-09-29: an unquoted
        ``a/b`` path became one, so the import silently vanished): a module
        spec this cannot map to an importable module is refused, naming the
        directive."""
        directive = f":- {_plain_term(body)}"
        if len(body.args) == 0 or len(body.args) > 2:
            raise PrologTranslationError(
                f"{directive}: use_module/{len(body.args)} is not a "
                "use_module the translator knows (use_module/1 or /2).")
        if (len(body.args) == 2 and isinstance(body.args[1], PList)
                and not body.args[1].elements and body.args[1].tail is None):
            # Measured 2026-09-29: Scryer reads use_module(M, []) as
            # remove_module(M) (it drops M's exports and never loads M, so
            # M:p(X) is an existence_error), Trealla and SWI as "load M,
            # import nothing".  Picking either silently makes a program
            # answer differently from one of the two; -import_from(m, [])
            # was a loader crash (``empty names on ImportFrom``).
            raise PrologTranslationError(
                f"{directive}: an empty import list has no portable meaning. "
                "Scryer reads it as remove_module/2 (it drops the module's "
                "imports and does not load it), Trealla and SWI as 'load "
                "it, import nothing'. Write use_module(M) to load it and "
                "import its exports, or use_module(M, [p/1, ...]) to import "
                "some; either way M:p(X) then reaches any predicate it "
                "exports.")

        lib_term = body.args[0]
        if (isinstance(lib_term, PCompound) and lib_term.functor == "library"
                and len(lib_term.args) == 1):
            lib_name = _slash_path(lib_term.args[0])
            if lib_name is None:
                raise PrologTranslationError(
                    f"{directive}: the library name is not an atom or an "
                    "a/b path.")
            if lib_name in _BUILTIN_LIBRARIES:
                return f"# library({lib_name}) is built-in — no import needed"
            if lib_name == "clpq" and len(body.args) == 1:
                # Its {}/1 is the seam's set goal and its predicates are
                # engine builtins: nothing to import.  (It was read as a
                # module named clpq: "No module named 'clpq'" at load.)
                return "# library(clpq) is built-in — no import needed"
            facade = (None if lib_name in _LIBRARY_TO_MODULE
                      else _library_facade(lib_name))
            if lib_name in _LIBRARY_TO_MODULE:
                clausal_mod = _LIBRARY_TO_MODULE[lib_name]
            elif facade is not None:
                # library(datetime): the .seam facade over py/datetime
                # (clausal/library/datetime.seam).  Its offer is the
                # adapter's, so the list is checked as for a py/ module.
                import importlib  # noqa: PLC0415
                return self._emit_python_use_module(
                    facade, importlib.import_module(facade),
                    body.args[1] if len(body.args) == 2 else None, directive)
            elif not _native_knows_library(lib_name):
                # Unknown to Clausal: refused, as the native front end
                # refuses it -- never read as a module of that name, which
                # for library(os) would be Python's os.
                raise PrologTranslationError(
                    _unknown_library_message(directive, lib_name))
            elif len(body.args) == 2 and _names_all_native(body.args[1]):
                return (f"# library({lib_name}): every name it imports is "
                        "provided by the engine -- no import needed")
            else:
                # A library the NATIVE front end maps but this translator
                # has no table entry for (reif, clpq, lambda: every unknown
                # name was refused above).  Its long-standing handling is
                # kept: the name read as a module of that name.  No Clausal
                # Prolog Python-module check is needed here: none of these
                # names is a Python module, and a new one cannot arrive
                # without joining the native table first.
                clausal_mod = self._dotted_or_refuse(lib_name, directive)
        else:
            spec = _slash_path(lib_term)
            if spec is None:
                raise PrologTranslationError(
                    f"{directive}: the module is not an atom, an a/b path "
                    "or library(Name), so it names no module to import.")
            clausal_mod = self._resolve_module_path(spec, directive)
            if self._surface == "clausal_prolog":
                facade = _clausal_prolog_facade(directive, clausal_mod)
                if facade is not None:
                    # A module NAME an alias resolves (european_union):
                    # its .seam facade.
                    import importlib  # noqa: PLC0415
                    return self._emit_python_use_module(
                        facade, importlib.import_module(facade),
                        body.args[1] if len(body.args) == 2 else None,
                        directive)
            try:
                py_mod = _python_backed_module(clausal_mod)
            except PrologTranslationError as e:
                raise PrologTranslationError(f"{directive}: {e}") from None
            if py_mod is not None:
                return self._emit_python_use_module(
                    clausal_mod, py_mod,
                    body.args[1] if len(body.args) == 2 else None, directive)

        if len(body.args) == 1:
            # ISO-family use_module/1 imports every EXPORTED predicate,
            # unqualified.  -import_module alone gives only qualified
            # access (``m.p(...)``), so an unqualified call of an import
            # failed; when the module is a .pl file its module/2 export
            # list is read and imported by name as well.
            exports = self._pl_exports(clausal_mod, directive)
            if exports:
                self._own_names.update(exports)
                self._own_any.update(exports)
                return (f"-import_module({clausal_mod})\n"
                        f"-import_from({clausal_mod}, [{', '.join(exports)}])")
            return f"-import_module({clausal_mod})"
        if len(body.args) >= 2:
            # With import list
            # A module FILE's list keeps its indicators (D20): ``p/1``
            # imports p/1 only, as in Scryer.  A library list stays bare --
            # a library may map to a Python module, which has no arities.
            imports = self._emit_import_list(
                body.args[1], keep_arity=not _is_library(lib_term))
            if imports == "[]" and _has_elements(body.args[1]):
                # Every item was operator-only and got dropped, so the import
                # itself was an artifact of the forward emission. Emitting
                # `-import_from(m, [])` is NOT the harmless version of this:
                # the Clausal loader rejects an empty name list outright
                # (`ValueError: empty names on ImportFrom`), so dropping the
                # item without dropping the directive fails at LOAD time.
                return (f"# library import of {clausal_mod} dropped: it named "
                        "only operator-spelled predicates")
            return f"-import_from({clausal_mod}, {imports})"
        else:
            return f"-import_module({clausal_mod})"

    def _emit_python_use_module(self, dotted, mod, imports, directive) -> str:
        """``use_module(py/datetime, [days_between/3])`` -- a PYTHON-backed
        module: it has no ``module/2`` list and the seam's ``-import_from``
        takes its names BARE (an indicator against one is refused at load:
        "not a Clausal module, so its names have no predicate arities to
        select").  Each ``name/N`` entry is CHECKED against
        ``clausal.module_signatures`` -- an unknown name or an arity the
        module does not register is a translation error naming the line and
        listing what the module offers -- and the checked names are imported
        bare.  No list imports every predicate the module has.  The native
        front end (``iso_l3_directives._use_python_module``) does the same,
        with the same message."""
        from clausal.logic.solve import module_signatures  # noqa: PLC0415
        sig = module_signatures(mod)
        offer = ", ".join(f"{n}/{a}" for n in sig
                          for a in (sorted(sig[n]) or ["?"])) or "no predicates"
        if imports is None:
            names = list(sig)
        else:
            if not isinstance(imports, PList) or imports.tail is not None:
                raise PrologTranslationError(
                    f"{directive}: the import list is not a list")
            names = []
            for e in imports.elements:
                if (isinstance(e, PCompound) and e.functor in ("/", "//")
                        and len(e.args) == 2 and isinstance(e.args[0], PAtom)):
                    n = e.args[0].name
                    a = _indicator_arity(e.args[1])
                    if not isinstance(a, int):
                        raise PrologTranslationError(
                            f"{directive}: {_plain_term(e)} is not a name/N "
                            "indicator")
                    if e.functor == "//":
                        a += 2
                    have = sig.get(n)
                    if have is None or (have and a not in have):
                        at = (f"{dotted} has {n} as "
                              + ", ".join(f"{n}/{x}" for x in sorted(have))
                              if have else f"{dotted} has no predicate {n}")
                        raise PrologTranslationError(
                            f"{directive}: existence_error(procedure, "
                            f"{n}/{a}) -- {at}; {dotted} offers {offer}")
                elif isinstance(e, PAtom):
                    n = e.name
                else:
                    raise PrologTranslationError(
                        f"{directive}: {_plain_term(e)} is not a name/N "
                        "indicator")
                if n not in names:
                    names.append(n)
        if not names:
            return f"# {directive}: {dotted} offers no predicates to import"
        self._own_names.update(names)
        self._own_any.update(names)
        return (f"-import_from({dotted}, "
                f"[{', '.join(self._predicate_name(n) for n in names)}])")

    def _resolve_module_path(self, spec: str, directive: str) -> str:
        """The dotted module a ``use_module`` path names.

        Relative to the importing file's directory first, as Scryer resolves
        it (``'../lib'``, ``sub/lib``); a path with no such file beside the
        importer is read as a dotted module on ``sys.path`` (``a/b`` is
        ``a.b``), which is how a bare name has always been resolved."""
        path = spec
        if path.startswith("./") or path.startswith(".\\"):
            path = path[2:]
        if path.endswith(".pl"):
            path = path[:-3]
        if self._source_path:
            cand = sibling_module_file(path, self._source_path)
            if cand is not None:
                if not self._module_name:
                    # Without it the dotted name would come from whichever
                    # sys.path entry (cwd included) happens to contain the
                    # file: output depending on the caller's cwd.
                    raise PrologTranslationError(
                        f"{directive}: relative use_module needs the "
                        "importing module's name (pass module_name= with "
                        "source_path=; the import hook always does).")
                dotted = self._dotted_for_file(cand)
                if dotted is None:
                    raise PrologTranslationError(
                        f"{directive}: {spec!r} is the file {cand}, which "
                        "no sys.path entry (nor this module's own package "
                        "root) contains as a dotted module path, so it "
                        "cannot be imported.")
                return dotted
        return self._dotted_or_refuse(path, directive, spec=spec)

    def _pl_exports(self, dotted: str, directive: str) -> list[str]:
        """The predicate names a ``.pl`` module's ``module/2`` directive
        exports, or [] when *dotted* is no ``.pl`` file with one.  A file
        that cannot be read is refused here, naming the directive -- the
        fallback (qualified access only) would fail far from the cause."""
        path = self._find_module_file(dotted)
        if path is None or not path.endswith(".pl"):
            return []
        try:
            text = Path(path).read_text(encoding="utf-8")
            pmod = parse(text, dialect=self._dialect,
                         nested_comments=PL_SOURCE_NESTED_COMMENTS)
        except Exception as e:  # noqa: BLE001
            raise PrologTranslationError(
                f"{directive}: cannot read the export list of {path}: "
                f"{e}") from e
        for item in pmod.items:
            b = getattr(item, "body", None)
            if (isinstance(item, PDirective) and isinstance(b, PCompound)
                    and b.functor == "module" and len(b.args) == 2
                    and isinstance(b.args[1], PList)):
                names = []
                for e in b.args[1].elements:
                    if (isinstance(e, PCompound) and e.functor in ("/", "//")
                            and len(e.args) == 2
                            and isinstance(e.args[0], PAtom)
                            and _is_plain_atom_name(e.args[0].name)
                            and e.args[0].name not in names):
                        names.append(e.args[0].name)
                return names
            if isinstance(item, (PClause, PDCGRule)):
                break
        return []

    def _package_root(self) -> str | None:
        return package_root(self._source_path, self._module_name)

    def _find_module_file(self, dotted: str) -> str | None:
        # Only with the importer's name: a direct API call must not read
        # the file system through sys.path (cwd included), or its output
        # would depend on the caller's working directory.
        if not (self._source_path and self._module_name):
            return None
        root = self._package_root()
        parts = dotted.split(".")
        roots = [root] if root is not None else []
        roots.extend(os.path.abspath(e or os.getcwd()) for e in sys.path
                     if isinstance(e, str))
        # A twin in any extension the import hook's finder tries BEFORE
        # ``.pl`` is what an import loads, so the ``.pl`` is not the module.
        # Read from the finder-order constants at each call, never spelled
        # here, so a new or reordered surface cannot drift from the hook.
        from clausal import _suffixes  # noqa: PLC0415
        order = _suffixes.SOURCE_SUFFIXES
        pl = _suffixes.PROLOG_SUFFIX
        twins = order[:order.index(pl)]
        for root in roots:
            base = os.path.join(root, *parts)
            if os.path.isfile(base + pl):
                if any(os.path.isfile(base + ext) for ext in twins):
                    return None
                return base + pl
        return None

    def _dotted_or_refuse(self, path: str, directive: str,
                          spec: str | None = None) -> str:
        parts = [p for seg in path.split("/") for p in seg.split(".")]
        if parts and all(p.isidentifier() and not keyword.iskeyword(p)
                         for p in parts):
            return ".".join(parts)
        raise PrologTranslationError(
            f"{directive}: {spec or path!r} names no module: there is no "
            "such file beside this one, and it is not a dotted module path "
            "(a/b/c of plain names).")

    def _dotted_for_file(self, cand: str) -> str | None:
        return dotted_for_file(cand, self._package_root())

    def _emit_meta_directive(self, kind: str, body: PCompound) -> str:
        """Emit -dynamic(pred/N), -discontiguous(pred/N), -table(pred/N)."""
        if len(body.args) == 1:
            indicator = self._emit_pred_indicator(body.args[0])
            return f"-{kind}({indicator})"
        # Multiple: :- dynamic(a/1, b/2)
        indicators = ", ".join(self._emit_pred_indicator(a) for a in body.args)
        return f"-{kind}({indicators})"

    def _emit_pred_indicator(self, term: PTerm) -> str:
        """Emit pred/N as a predicate indicator."""
        if isinstance(term, PCompound) and term.functor == "/" and len(term.args) == 2:
            name = self._emit_atom_name(term.args[0])
            clausal_name = self._predicate_name(
                name, _indicator_arity(term.args[1]))
            arity = self._emit_term(term.args[1])
            return f"{clausal_name}/{arity}"
        # Comma-separated list: (a/1, b/2)
        if isinstance(term, PCompound) and term.functor == ",":
            parts = self._flatten_conjunction(term)
            return ", ".join(self._emit_pred_indicator(p) for p in parts)
        return self._emit_term(term)

    # ── Terms ────────────────────────────────────────────────────────

    def _emit_term(self, term: PTerm) -> str:
        """Emit a Prolog AST term as clausal syntax."""
        if isinstance(term, PAtom):
            return self._emit_atom(term)
        if isinstance(term, PVar):
            return _checked_var_name(term.name)
        if isinstance(term, PNumber):
            if isinstance(term.value, float):
                return repr(term.value)
            return str(term.value)
        if isinstance(term, PString):
            return self._emit_string(term.value)
        if isinstance(term, PList):
            return self._emit_list(term)
        if isinstance(term, PCurly):
            # A ``{...}`` term may be library(clpq)'s constraint set run by a
            # meta-call (``findall(X, {X > 1}, L)``): its operators stay the
            # seam's arithmetic, as before (``_seam_operators``).
            self._seam_operators += 1
            try:
                return "{" + self._emit_term(term.body) + "}"
            finally:
                self._seam_operators -= 1
        if isinstance(term, PCompound):
            return self._emit_compound(term)
        return str(term)

    def _emit_string(self, value: str) -> str:
        """A ``"..."`` literal, read under the double_quotes flag in force:
        ``codes`` → the list of codes, ``atom`` → the quoted atom, ``chars``
        → a string (the module carries ``-double_quotes(chars)`` so it
        re-reads as one)."""
        if self._dq_mode == "codes":
            return "[" + ", ".join(str(ord(c)) for c in value) + "]"
        if self._dq_mode == "atom":
            return _quote_atom(value)
        self._emitted_string = True
        return _quote_string(value)

    # Atoms that map to Python builtins and should not be collected as data atoms.
    _BUILTIN_ATOMS = frozenset({"true", "false", "fail", "True", "False", "None"})

    # Prolog spelling -> Clausal spelling for builtin truth atoms. Prolog uses
    # lowercase 'true'/'false'/'fail'; Clausal uses Python 'True'/'False'.
    _BUILTIN_ATOM_REWRITES = {
        "true": "True",
        "false": "False",
        "fail": "False",
    }

    def _emit_atom(self, atom: PAtom) -> str:
        """Emit an atom as a bare name, registering it for ``-private`` declaration.

        Prolog atoms like ``red``, ``foo_bar`` are symbolic constants.  in_
        Clausal they become module-level string variables declared via
        ``-private([red, foo_bar, ...])``, which the EmbedTransformer
        compiles to ``red = "red"`` etc.
        """
        name = atom.name
        # Special atoms that map to Python builtins
        if name in self._BUILTIN_ATOMS:
            return self._BUILTIN_ATOM_REWRITES.get(name, name)
        if name == "!":
            raise PrologTranslationError(
                "Cut (!/0) cannot be translated to Clausal.\n"
                "Clausal intentionally omits cut — it breaks declarative "
                "semantics and monotonicity.\n"
                "Rewrite using pure alternatives:\n"
                "  - dif/2 and constraints for mutual exclusion between clauses\n"
                "  - once(Goal) for first-solution commitment\n"
                "  - First-argument indexing (automatic) for determinism\n"
                "  - Reified if-then-else for conditional branching\n"
                "See: docs/for_prolog_programmers.md"
            )
        if name == "[]":
            return "[]"
        if name == "{}":
            return "{}"
        # A quoted atom, or one whose spelling is not a plain lowercase
        # identifier (space, punctuation, uppercase) or collides with a Python
        # keyword, cannot be emitted as a bare Clausal name — `p('hello world')`
        # / `p(class)` would be a SyntaxError and `p('Foo')` would silently
        # become a variable/predicate reference. Emit a Python string literal
        # instead (F025).
        if getattr(atom, "quoted", False) or not _is_plain_atom_name(name):
            # SINGLE quotes (THE FLIP, spec §7): ``'...'`` is an atom in
            # every mode, which is what this atom must stay.  ``repr`` is
            # not usable — it picks its quotes by content, so an atom whose
            # spelling holds an apostrophe would come out DOUBLE-quoted and,
            # under the ``-double_quotes(chars)`` header this emitter may
            # write, would re-read as a string.
            return _quote_atom(name)
        # A bare name that this module also uses as a PREDICATE cannot be
        # declared `-private` as well: in Clausal one module-level name is
        # either the atom or the predicate, never both, so `-private([subtract])`
        # shadows `subtract/3` and every call to it stops being a goal
        # ("terms_to_goalop: goal shape not yet supported"). A quoted literal
        # denotes the same atom and carries no declaration, so it is the
        # faithful spelling here -- the same escape hatch F025 already uses for
        # names that cannot be bare. SINGLE-quoted (item J re-land, 2026-09-07):
        # ``'...'`` is an atom in every -double_quotes mode, where ``repr``
        # could pick double quotes and re-read as a string under chars.
        # Reachable since Prolog test names became atoms:
        # `test(subtract) :- subtract(...)`.
        if name in self._predicate_names:
            return _quote_atom(name)
        # The same for a name the module CALLS or IMPORTS without defining it
        # (``:- use_module(lib, [g/0]).  c(L) :- findall(1, g, L).``): neither
        # sweep above sees a 0-arity import, so ``g`` was declared
        # ``-private([g])`` and the private DATA atom shadowed the imported
        # predicate -- the goal raised existence_error(procedure, g/0).
        if name in self._goal_names or name in self._own_names:
            return _quote_atom(name)
        # And a name the module qualifies goals with (``r --> m:g`` beside
        # ``phrase(m:g, L)``, ``X = lists`` beside ``lists:member(...)``):
        # ``-private([m])`` would shadow the module ``m``.
        if name in self._qualifiers:
            return _quote_atom(name)
        # A name the engine RESERVES: bare ``undefined`` is the truth value
        # Undefined, and ``-private([undefined])`` is a load error.  The
        # quoted literal is the plain atom and needs no declaration.
        if name in _RESERVED_BARE_NAMES:
            return _quote_atom(name)
        # Register as a data atom (will be declared via -private).
        self._data_atoms.add(name)
        return name

    def _fold_in_domain(self, term: PTerm) -> str | None:
        """``in_domain(T, Lo, Hi)`` if *term* is what the forward translator
        writes for it (D21), else None.

        Three shapes: ``in(T, Lo..Hi)``, ``ins(T, Lo..Hi)``, and the type
        dispatch it writes when T may be a variable or a list,

            ( (var(T) ; integer(T)), in(T, Lo..Hi)
            ; nonvar(T), (T == [] ; T = [_|_], ins(T, Lo..Hi)) )

        which is matched whole, every occurrence of T and of the domain the
        same, so a hand-written disjunction that merely resembles it is left
        alone and translated as the disjunction it is. The first two are the
        clpz constraints themselves; in_domain/3 is the same relation over
        one variable or a list.
        """
        def domain(t):
            if isinstance(t, PCompound) and t.functor == ".." and len(t.args) == 2:
                return t.args
            return None

        def call(t, name, arity):
            return (isinstance(t, PCompound) and t.functor == name
                    and len(t.args) == arity)

        if (call(term, "in", 2) or call(term, "ins", 2)) and domain(term.args[1]):
            lo, hi = domain(term.args[1])
            return (f"in_domain({self._emit_term(term.args[0])}, "
                    f"{self._emit_term(lo)}, {self._emit_term(hi)})")
        if not call(term, ";", 2):
            return None
        single, listed = term.args
        if not (call(single, ",", 2) and call(listed, ",", 2)):
            return None
        types, one = single.args
        nonvar_t, alts = listed.args
        if not (call(types, ";", 2) and call(alts, ";", 2)):
            return None
        var_t, int_t = types.args
        is_nil, cons_ins = alts.args
        if not call(cons_ins, ",", 2):
            return None
        is_cons, many = cons_ins.args
        if not (call(var_t, "var", 1) and call(int_t, "integer", 1)
                and call(one, "in", 2) and call(nonvar_t, "nonvar", 1)
                and call(is_nil, "==", 2) and call(is_cons, "=", 2)
                and call(many, "ins", 2) and domain(one.args[1])
                and domain(many.args[1])):
            return None
        cons = is_cons.args[1]
        if not (isinstance(is_nil.args[1], PList) and not is_nil.args[1].elements
                and is_nil.args[1].tail is None
                and isinstance(cons, PList) and len(cons.elements) == 1
                and isinstance(cons.elements[0], PVar) and cons.elements[0].name == "_"
                and isinstance(cons.tail, PVar) and cons.tail.name == "_"):
            return None
        targets = {self._emit_term(t) for t in (
            var_t.args[0], int_t.args[0], one.args[0], nonvar_t.args[0],
            is_nil.args[0], is_cons.args[0], many.args[0])}
        # Compared bound by bound: `..` itself has no Clausal spelling to emit.
        domains = {tuple(self._emit_term(b) for b in domain(d))
                   for d in (one.args[1], many.args[1])}
        if len(targets) != 1 or len(domains) != 1:
            return None
        lo, hi = domain(one.args[1])
        return f"in_domain({targets.pop()}, {self._emit_term(lo)}, {self._emit_term(hi)})"

    def _emit_compound(self, term: PCompound, goal: bool = False,
                       called: bool = False) -> str:
        """Emit a compound term (*goal*: it stands in goal position;
        *called*: it is a meta-call's goal argument, so it is run as a goal
        but otherwise emitted as a term).  Only in those two positions is a
        meta-call's own goal argument ``[]`` the goal ``[]/0``
        (``_emit_goal_arg``); a ``catch([], ...)`` in a head or as data
        keeps its ``[]``."""
        functor = term.functor
        args = term.args

        # D21, in TERM position too (a meta-call's goal argument), like `#=`.
        # Not as DATA: ``G = (X in 1..2)`` is the term ``X in 1..2``.
        if not self._is_data(goal, called):
            folded = self._fold_in_domain(term)
            if folded is not None:
                return folded

        # library(clpz)'s in/2 (unfolded: a domain with ``\/``, or not
        # known at translation time) is the quoted builtin ``'in'(X, D)``
        # in every position.  Through the keyword rename it was ``in_``,
        # the class of the seam's ``in`` operator node: as a goal it was
        # LIST membership (``X in 1..2 \/ 5`` failed), and built as a term
        # it did not load ("functor in_/3 was constructed with 2 positional
        # argument(s)").
        if functor == "in" and len(args) == 2 and functor not in self._user_ops \
                and functor not in self._own_names:
            return self._emit_quoted_op_term(term)

        # Control constructs in term/metacall position (e.g. inside findall's
        # goal argument) are rejected the same way as in goal position — the
        # bare fall-through would otherwise emit invalid `->(...)` / `*->(...)`
        # (F024, sibling of A10-F001).
        if functor in ("->", "*->") and len(args) == 2:
            raise PrologTranslationError(
                f"If-then(-else) / soft-cut ('{functor}') cannot be translated "
                "to Clausal, even in a metacall argument.\n"
                "Rewrite using reified conditionals or dif/2 guards.\n"
                "See: docs/reified_ite.md, docs/for_prolog_programmers.md"
            )

        # Standard-order comparison (ISO 8.4.1): the engine has the quoted
        # ISO builtins '@<'/2 etc. (2026-09-09), so they cross as those.
        # They were refused as "no standard-order builtins" until
        # 2026-09-29.  Quoted, because a bare ``@`` is Python's matmul.
        if functor in ("@<", "@>", "@=<", "@>=") and len(args) == 2:
            left = self._emit_term(args[0])
            right = self._emit_term(args[1])
            return f"{_quote_atom(functor)}({left}, {right})"

        # A comparison or unification CLOSURE (``maplist(=(1), L)``,
        # ``include(>(2), Xs, Ys)``, ``call(<(0), X)``): fewer arguments
        # than the builtin, which call/N completes.  It is the quoted cell
        # ``'>'(2)``; it was refused as "not a valid Python identifier".
        if functor in _COMPARISON_CLOSURE_FUNCTORS and len(args) == 1:
            return self._emit_quoted_op_term(term)

        # Variant equality has no Clausal equivalent (F041 — the designed
        # rejection promised when =@=/\=@= were added to the parser tables).
        if functor in ("=@=", "\\=@=") and len(args) == 2:
            raise PrologTranslationError(
                f"Variant equality ('{functor}') cannot be translated: "
                "Clausal has no term-variance builtin.\n"
                "Rewrite using structural ==/\\== (for identical terms) or "
                "an explicit double copy_term/subsumes check."
            )

        # bagof/setof: the ISO existential quantifier (V^Goal, 8.10) crosses
        # as Clausal's own ``V ^ Goal``.  Clausal's bagof/setof group by the
        # free variables like ISO's, so the quantifier CHANGES the answers:
        # stripping it (as this translator did until 2026-09-29) turned
        # ``setof(X, Y^p(X,Y), L)`` into one answer per Y.  Python's ``^`` is
        # left-associative, so a nested ``A^B^G`` is parenthesised to the
        # right: ``A ^ (B ^ G)``.
        if functor in ("bagof", "setof") and len(args) == 3:
            name = self._predicate_name(functor, 3)
            return (f"{name}({self._emit_term(args[0])}, "
                    f"{self._emit_quantified(args[1], goal or called)}, "
                    f"{self._emit_term(args[2])})")

        # A ``V^G`` in a GOAL argument of any other meta-predicate
        # (findall, forall, aggregate_all, \+, ...) is called as a goal,
        # which Clausal has no meaning for; emitting the data term '^'(V, G)
        # would call that term.  Refused, as in direct goal position.
        for i in _META_GOAL_ARGS.get(functor, ()):
            if (i < len(args) and isinstance(args[i], PCompound)
                    and args[i].functor == "^" and len(args[i].args) == 2):
                self._refuse_caret_goal()

        # (^)/2 as a DATA term is the term ^(A, B), spelled as the quoted
        # ISO functor ('^'(A, B); a bare ``^`` is Python XOR, ``**`` a
        # different functor).  As a GOAL (``Y^p(Y)`` called directly) it has
        # no Clausal equivalent -- refused.  In arithmetic context it is the
        # ISO evaluable (``_emit_expr``).
        if functor == "^" and len(args) == 2:
            if not goal:
                return self._emit_quoted_op_term(term)
            self._refuse_caret_goal()

        # ','/2 in term position is a tuple, NOT a flattened argument list:
        # emitting it bare turned foo(a, (b, c)) into a foo/3 call (F023).
        #
        # As DATA it is the quoted cell ``','(b, c)``: the seam reads a
        # parenthesised ``(b, c)`` in ARGUMENT position as the call
        # ``b(c)`` (``f((b, c))`` was ``f(b(c))``, and ``X = (a :- b, c)``
        # raised domain_error(clpz_expression, b(c))).
        if functor == "," and len(args) == 2 and self._is_data(goal, called):
            return self._emit_quoted_op_term(term)
        if functor == "," and len(args) == 2:
            parts = ", ".join(
                self._emit_term(p) for p in self._flatten_conjunction(term)
            )
            return f"({parts})"

        # Univ: T =.. L → unpack(T, L) (=.. is not valid Clausal syntax) — F033.
        # As DATA it is the cell ``'=..'(T, L)``, not a ``unpack/2`` term.
        if functor == "=.." and len(args) == 2 and self._is_data(goal, called):
            return self._emit_quoted_op_term(term)
        if functor == "=.." and len(args) == 2:
            left = self._emit_term(args[0])
            right = self._emit_term(args[1])
            return f"unpack({left}, {right})"

        # As DATA ``M:G`` is the cell ``':'(M, G)``, as the native front end
        # builds it (``t(x36, E, catch(call(foo:bar), E, true))``): the
        # qualified call ``foo.bar()`` built as a term did not load (a
        # TypeError in the functor lookup), and with a variable module
        # (``T = t(M:P)``) the functor was refused.
        if functor == ":" and len(args) == 2 and self._is_data(goal, called):
            return self._emit_quoted_op_term(term)

        # Module-qualified goal: Module:Goal → Module.Goal(...) (F033).
        if functor == ":" and len(args) == 2 and isinstance(args[0], PAtom):
            module = args[0].name
            qualified = args[1]
            # ``m:foo/1`` -- a qualified predicate indicator, or any operator
            # term after the colon -- names no predicate: it is the data cell
            # ``':'(m, '/'(foo, 1))``.  (``_predicate_name`` refused it.)
            if (isinstance(qualified, PCompound)
                    and not qualified.functor.isidentifier()):
                return self._emit_quoted_op_term(term)
            if isinstance(qualified, PCompound):
                goal_name = self._predicate_name(qualified.functor,
                                                 len(qualified.args))
                inner = ", ".join(self._emit_term(a) for a in qualified.args)
                return f"{module}.{goal_name}({inner})"
            if isinstance(qualified, PAtom):
                return f"{module}.{qualified.name}()"

        # Check user-defined operator mappings
        if functor in self._user_ops:
            mapping = self._user_ops[functor]
            clausal_name = mapping.get("clausal", functor)
            if len(args) == 2:
                left = self._emit_term(args[0])
                right = self._emit_term(args[1])
                return f"{clausal_name}({left}, {right})"
            elif len(args) == 1:
                operand = self._emit_term(args[0])
                return f"{clausal_name}({operand})"

        # A disjunction or negation in DATA position is the ISO cell
        # (``X = (a ; b)`` -> ``X is ';'(a, b)``): the seam's ``a or b`` and
        # ``not a`` after ``X is`` read as ``(X is a) or b`` and ``X is not
        # a``.  As a goal, or a meta-call's goal argument, they keep the
        # seam's own spelling.
        if (((functor in (";", "|") and len(args) == 2)
                or (functor == "\\+" and len(args) == 1))
                and self._is_data(goal, called)):
            return self._emit_quoted_op_term(term)

        # Negation prefix: \+(X) → not X
        if functor == "\\+" and len(args) == 1:
            inner = self._emit_term(args[0])
            return f"not {inner}"

        # Ruling 2026-09-18, reverse direction. These two are handled HERE,
        # in the compound emitter, rather than beside the other goal-level
        # special cases, because `#=` occurs in TERM position too -- inside a
        # meta-call's conjunction, say -- and a goal-only fix leaves that
        # second shape raising `'#=' is not a valid Python identifier`. The
        # goal path falls through to here, so one site covers both.
        #
        # `#=(X, Y)` → `X == Y`: unquoted `==` in Clausal IS the CLP
        # arithmetic constraint, and `#=` is what it emits.
        #
        # In DATA position (neither a goal nor a meta-call's goal argument)
        # it is the ISO cell ``'#='(X, '+'(1, 1))``, like the other clpz
        # relations below: the bare ``X == 1 + 1`` after ``G is`` read as
        # the Python chained comparison ``G is X == 1 + 1``.
        if functor == "#=" and len(args) == 2 and self._is_data(goal, called):
            return self._emit_quoted_op_term(term)
        if functor == "#=" and len(args) == 2:
            left = self._emit_expr(args[0])
            right = self._emit_expr(args[1])
            return f"{left} == {right}"
        # `==(X, Y)` → `'=='(X, Y)`. The QUOTED form is required, not
        # stylistic: emitting bare `X == Y` would read back as the CLP
        # constraint above, so a round trip would silently turn an identity
        # test into a constraint -- the exact direction the respell that
        # preceded this ruling existed to prevent.
        if functor == "==" and len(args) == 2:
            left = self._emit_term(args[0])
            right = self._emit_term(args[1])
            return f"'=='({left}, {right})"

        # Unification: X = Y → X is Y; as DATA the cell ``'='(X, Y)`` (the
        # bare ``G is X is Y`` read as a chained comparison, and a stored
        # body ``(p, X = 1)`` printed as the seam's Unify node).
        if functor == "=" and len(args) == 2 and self._is_data(goal, called):
            return self._emit_quoted_op_term(term)
        if functor == "=" and len(args) == 2:
            left = self._emit_term(args[0])
            right = self._emit_term(args[1])
            return f"{left} is {right}"

        # Dis-unification and term non-identity: the QUOTED ISO builtins, for
        # the reasons given at the goal-position arms above.
        if functor == "\\=" and len(args) == 2:
            left = self._emit_term(args[0])
            right = self._emit_term(args[1])
            return f"{_QUOTED_NOT_UNIFIABLE}({left}, {right})"
        if functor == "\\==" and len(args) == 2:
            left = self._emit_term(args[0])
            right = self._emit_term(args[1])
            return f"{_QUOTED_NOT_IDENTICAL}({left}, {right})"

        # Arithmetic is: R is Expr → eval_(Expr, R)
        if functor == "is" and len(args) == 2:
            # R is E → eval_(E, R): the eager arithmetic builtin (the former
            # ':=' operator, now deprecated).
            result = self._emit_term(args[0])
            expr = self._emit_expr(args[1])
            return f"eval_({expr}, {result})"

        # ``+ - * /`` in DATA position are the ISO cells ``'/'(foo, 0)``
        # (2026-10-20).  The seam's ``foo / 0`` is its arithmetic ``Div``
        # node, not the cell ('/', foo, 0) the engine's error terms and the
        # native front end build, so a catcher ``error(existence_error(
        # procedure, foo/0), _)`` never matched, ``functor(foo/0, N, A)``
        # answered 'Div'/3 and a ``K-V`` pattern missed library(pairs)'
        # pairs.  Arithmetic positions (``is``, the comparisons below,
        # ``#=``, ``{...}``) emit through ``_emit_expr``, which keeps the
        # Python operators; the engine evaluates the cells as well.
        if functor in self._EXPR_PREC and len(args) == 2:
            if self._seam_operators:
                return self._emit_expr(term)
            return self._emit_quoted_op_term(term)

        # library(clpz)'s other relations and its reification connectives
        # have no seam operator spelling: the ISO cell in every position
        # (as a goal it is the call of the quoted builtin ``'#<'/2``).  It
        # used to be refused as "not a valid Python identifier".
        if functor in _CLPZ_CELL_OPERATORS and len(args) in (1, 2):
            return self._emit_quoted_op_term(term)

        # A comparison in DATA position is the ISO cell ``'<'('+'(1, 1),
        # 3)``.  Emitted bare, ``G = (1+1 < 3)`` became ``G is 1 + 1 < 3``,
        # which the seam reads as the Python chained comparison ``G is 1 +
        # 1 and 1 + 1 < 3`` (so call(G) raised type_error(callable, 1+1)).
        if (functor in _ARITH_COMPARISONS and len(args) == 2
                and self._is_data(goal, called)):
            return self._emit_quoted_op_term(term)

        # A clause or grammar rule in DATA position (``X = (a :- b, c)``,
        # ``assertz((H :- B))``) is the ISO cell ``':-'(a, (b, c))``: the
        # seam's ``a <- (b, c)`` after ``X is`` read as ``X is a < -(b,
        # c)``, and as assertz's argument its unparenthesised body was a
        # load error.  assertz/retract take the cell (``Head :- true`` is
        # the fact; a rule body is the runtime refusal, as on the native
        # front end).
        if (functor in (":-", "-->") and len(args) in (1, 2)
                and not goal and not self._seam_operators):
            return self._emit_quoted_op_term(term)

        # Arithmetic comparison in term position (a meta-call's goal
        # argument): its operands are expressions, as in goal position.
        if functor in _ARITH_COMPARISONS and len(args) == 2:
            left = self._emit_expr(args[0])
            right = self._emit_expr(args[1])
            return f"{left} {_INFIX_MAP[functor]} {right}"

        # Comparison operators
        if functor in _INFIX_MAP and len(args) == 2:
            clausal_op = _INFIX_MAP[functor]
            left = self._emit_term(args[0])
            right = self._emit_term(args[1])
            return f"{left} {clausal_op} {right}"

        # ISO evaluable operators Python spells differently → '//'(X, Y)
        if ((functor in _ISO_QUOTED_BINARY_OPS and len(args) == 2)
                or (functor in _ISO_QUOTED_UNARY_OPS and len(args) == 1)):
            return self._emit_quoted_op_term(term)

        # Prefix operators
        if functor in _PREFIX_MAP and len(args) == 1:
            # The compound -(1) is not the integer -1, and the seam's `-1`
            # IS the integer: emit the quoted functor, `'-'(1)`. (The
            # reader already turned `- 1` into the number; only `-(1)` and
            # `- (1)` reach here.)
            if (functor == "-" and isinstance(args[0], PNumber)
                    and args[0].unit is None):
                return self._emit_quoted_op_term(term)
            # Prefix ``-``/``+`` as DATA is the cell ``'-'(a)``, not the
            # seam's ``Negate``/``UAdd`` node -- as for the binary
            # operators above.
            if functor in ("-", "+") and not self._seam_operators:
                return self._emit_quoted_op_term(term)
            clausal_op = _PREFIX_MAP[functor]
            operand = self._emit_term(args[0])
            if clausal_op == "not":
                return f"not {operand}"
            if functor == "-" and isinstance(args[0], PCompound):
                # Bracketed: a bare `-1 * 2` is (-1)*2, `-a, b` a tuple.
                return f"-({operand})"
            return f"{clausal_op}{operand}"

        # Regular compound: functor(args) → functor(args); a called name
        # through the builtin renames, a DATA term under its own name.
        name = self._predicate_name(functor, len(args),
                                    rename=not self._is_data(goal, called))
        if not goal and args and name == functor and _is_plain_atom_name(name):
            self._data_functors.setdefault(name, set()).add(len(args))
        if not args:
            return f"{name}()"
        arg_strs = self._emit_args(functor, args, called=goal or called)
        return f"{name}({arg_strs})"

    def _emit_args(self, functor: str, args, called: bool = False) -> str:
        """The emitted argument list of a ``functor(args)`` head, goal or
        data term.

        plunit's ``test(Name, Option)``: the option is DATA the test runner
        reads, so an atom option (``fail``, ``false``) stays the atom it
        spells rather than folding to the truth value ``False``.  Applied in
        every position -- head, goal and data alike -- so a ``test/2`` fact
        and a call of it still unify.

        *called*: the term is run as a goal (a body goal, or a meta-call's
        goal argument), so its own goal arguments are emitted by
        ``_emit_goal_arg``; in a head or as data they are terms."""
        nil_ix = _NIL_GOAL_ARGS.get(functor, ()) if called else ()
        goal_ix = _GOAL_EMIT_ARGS.get(functor, ()) if called else ()
        dcg_ix = _DCG_BODY_ARGS.get(functor, ()) if called else ()
        # A program's own time/1 is no meta-call (tests/
        # test_pl_translator_honest.py::TestNoStaleRenames) -- by SIGNATURE:
        # its own forall/1 leaves forall/2 the meta-call.  call/N needs no
        # wrap: call(G) already calls G (it was call(call(G))).
        var_goal = (functor != "call"
                    and _is_goal_arity(functor, len(args))
                    and not self._is_own_signature(functor, len(args)))
        emitted = [self._emit_goal_arg(a, nil_is_goal=i in nil_ix,
                                       var_is_goal=i in nil_ix and var_goal)
                   if i in goal_ix or i in nil_ix
                   else self._emit_dcg_body_term(a) if i in dcg_ix
                   else self._emit_term(a) for i, a in enumerate(args)]
        if (functor == "test" and len(args) == 2
                and isinstance(args[1], PAtom)):
            emitted[1] = _quote_atom(args[1].name)
        return ", ".join(emitted)

    def _is_own_signature(self, name: str, arity: int) -> bool:
        """The program defines, declares or imports ``name/arity`` itself."""
        return ((name, arity) in self._own_sigs
                or (name, None) in self._own_sigs or name in self._own_any)

    def _emit_goal_arg(self, term: PTerm, nil_is_goal: bool = True,
                       var_is_goal: bool | None = None) -> str:
        """A meta-call's goal argument (``catch(G, ...)``, ``findall(_, G,
        _)``): a term, except that a ``[]`` called as a goal -- the whole
        argument, or a conjunct, disjunct or negated goal of it -- is
        ``call([])``, the predicate ``[]/0``.  Emitted bare it is the seam's
        empty list: as the whole argument it succeeded (``catch([], ...)``
        was true with no ``[]/0``), and inside ``(A, [])`` the seam's goal
        compiler refused it.  The text is otherwise exactly what
        ``_emit_term`` writes: ``,``, ``;`` and ``\\+`` are spelled as its
        compound emitter spells them, and any other compound goes through
        that emitter, flagged *called* so that a meta-call nested in it
        (``findall(_, catch([], _, _), _)``) is treated the same way.

        *nil_is_goal* False: a closure or DCG-body argument (maplist's,
        phrase's), where ``[]`` is the empty list; the rest is the same.

        *var_is_goal* (default: *nil_is_goal*): a variable there is the goal
        ``call(V)``; False where the meta-call's arity is not one whose
        argument is a goal (``time/4`` is no time/1)."""
        if var_is_goal is None:
            var_is_goal = nil_is_goal
        if self._is_nil(term):
            return "call([])" if nil_is_goal else self._emit_term(term)
        # A variable called as a goal is call(G), as in a clause body: bare,
        # the seam refused it at load (``G = p(X), findall(X, G, L)``,
        # BareGoalVariableError).  A closure stays the variable call/N
        # extends.
        if isinstance(term, PVar) and var_is_goal:
            return f"call({self._emit_term(term)})"
        if not isinstance(term, PCompound):
            return self._emit_term(term)
        f, a = term.functor, term.args
        if f == "," and len(a) == 2:
            return "(" + ", ".join(
                self._emit_goal_arg(p, nil_is_goal, var_is_goal)
                for p in self._flatten_conjunction(term)) + ")"
        if f == ";" and len(a) == 2 and f not in self._user_ops and not (
                isinstance(a[0], PCompound)
                and a[0].functor in ("->", "*->")):
            return (
                f"{self._emit_goal_arg(a[0], nil_is_goal, var_is_goal)} or "
                f"{self._emit_goal_arg(a[1], nil_is_goal, var_is_goal)}")
        if f == "|" and len(a) == 2 and nil_is_goal \
                and self._has_nil_goal(term) and not (
                isinstance(a[0], PCompound)
                and a[0].functor in ("->", "*->")):
            return (
                f"({self._emit_goal_arg(a[0], nil_is_goal, var_is_goal)} or "
                f"{self._emit_goal_arg(a[1], nil_is_goal, var_is_goal)})")
        if f == "\\+" and len(a) == 1 and f not in self._user_ops:
            if (isinstance(a[0], PCompound) and a[0].functor == "^"
                    and len(a[0].args) == 2):
                self._refuse_caret_goal()
            return f"not {self._emit_goal_arg(a[0], nil_is_goal, var_is_goal)}"
        return self._emit_compound(term, called=True)

    def _emit_dcg_body_term(self, term: PTerm) -> str:
        """A grammar body passed to phrase/2,3, as the ISO term the runtime
        phrase translates (ISO 7.14.2, ``dcg._dcg_translate``): ``,``,
        ``;``, ``|`` and ``\\+`` are their ISO cells over grammar bodies,
        ``{G}`` is ``'{}'(G)`` with G a goal term (call/1 runs it), and a
        list, string or nonterminal (``call(G, A)`` is call//N) is the term
        itself.  ``->`` is refused by the compound emitter, as everywhere
        (the translator is cut-free)."""
        if isinstance(term, PCurly):
            return f"{_quote_atom('{}')}({self._emit_term(term.body)})"
        if isinstance(term, PCompound) and term.functor not in self._user_ops \
                and ((term.functor in (",", ";", "|") and len(term.args) == 2)
                     or (term.functor == "\\+" and len(term.args) == 1)):
            inner = ", ".join(self._emit_dcg_body_term(a) for a in term.args)
            return f"{_quote_atom(term.functor)}({inner})"
        return self._emit_term(term)

    def _has_nil_goal(self, term: PTerm) -> bool:
        """Whether *term*, read as a goal, calls ``[]`` -- itself, or through
        ``,``/``;``/``|``/``\\+`` (the constructs ``_emit_goal_arg`` walks)."""
        if self._is_nil(term):
            return True
        if not isinstance(term, PCompound):
            return False
        f, a = term.functor, term.args
        if f in (",", ";", "|") and len(a) == 2:
            if f != "," and isinstance(a[0], PCompound) \
                    and a[0].functor in ("->", "*->"):
                return False
            return self._has_nil_goal(a[0]) or self._has_nil_goal(a[1])
        if f == "\\+" and len(a) == 1:
            return self._has_nil_goal(a[0])
        return False

    @staticmethod
    def _refuse_caret_goal() -> None:
        raise PrologTranslationError(
            "The existential quantifier ((^)/2) is only supported inside "
            "the goal argument of bagof/3 or setof/3; `V^Goal` called as a "
            "goal (directly, or in a goal argument of findall/forall/\\+/"
            "...) cannot be translated."
        )

    def _is_data(self, goal: bool, called: bool) -> bool:
        """The term being emitted is DATA: not a goal, not a meta-call's
        goal argument, and not where the seam's own operators are wanted
        (a directive argument, a ``{...}`` constraint set)."""
        return not goal and not called and not self._seam_operators

    def _emit_quoted_op_term(self, term: PCompound) -> str:
        """An ISO operator term in DATA position: the quoted functor over
        operands emitted as TERMS (so their functors are declared), not as
        arithmetic."""
        inner = ", ".join(self._emit_term(a) for a in term.args)
        return f"{_quote_atom(term.functor)}({inner})"

    def _emit_quantified(self, term: PTerm, called: bool = False) -> str:
        """The goal argument of bagof/setof: ``V^G`` → ``V ^ (G)``, nested
        to the right; anything else is the goal term itself."""
        if (isinstance(term, PCompound) and term.functor == "^"
                and len(term.args) == 2):
            witness = self._emit_term(term.args[0])
            inner = term.args[1]
            inner_s = self._emit_quantified(inner, called)
            # Always parenthesised (a conjunction already is): Python's
            # ``^`` binds tighter than ``is``/comparison, so ``Y ^ X is Y``
            # would read as ``(Y ^ X) is Y``.
            if not (isinstance(inner, PCompound) and inner.functor == ","
                    and len(inner.args) == 2):
                inner_s = f"({inner_s})"
            return f"{witness} ^ {inner_s}"
        return self._emit_goal_arg(term) if called else self._emit_term(term)

    # Python operator precedence (higher number = tighter binding).
    _EXPR_PREC: dict[str, int] = {
        "+": 5, "-": 5,
        "*": 6, "/": 6,
    }

    def _emit_expr(self, term: PTerm, parent_prec: int = 0) -> str:
        """Emit an arithmetic expression with precedence-aware parenthesization."""
        if isinstance(term, PNumber):
            return str(term.value) if isinstance(term.value, int) else repr(term.value)
        if isinstance(term, PVar):
            return _checked_var_name(term.name)
        if isinstance(term, PAtom):
            # ISO evaluable constants: X is pi must not emit a bare `pi`
            # name (NameError at runtime) — map to math.* / a literal (F025).
            mapped = _EVALUABLE_CONSTANTS.get(term.name)
            if mapped is not None:
                return mapped
            # Any other atom goes through the normal atom path so it is
            # quoted/registered like an arg-position atom.
            return self._emit_atom(term)
        if isinstance(term, PCompound):
            # ISO evaluable operators Python spells differently → the
            # quoted ISO evaluable, '//'(X, Y)
            if ((len(term.args) == 2 and term.functor in _ISO_QUOTED_BINARY_OPS)
                    or (len(term.args) == 1
                        and term.functor in _ISO_QUOTED_UNARY_OPS)):
                inner = ", ".join(self._emit_expr(a) for a in term.args)
                return f"{_quote_atom(term.functor)}({inner})"
            # Arithmetic binary operators
            if len(term.args) == 2 and term.functor in self._EXPR_PREC:
                my_prec = self._EXPR_PREC[term.functor]
                left = self._emit_expr(term.args[0], my_prec)
                right = self._emit_expr(term.args[1], my_prec + 1)
                op = _INFIX_MAP.get(term.functor, term.functor)
                result = f"{left} {op} {right}"
                if my_prec < parent_prec:
                    result = f"({result})"
                return result
            # Arithmetic unary operators
            if len(term.args) == 1 and term.functor in ("-", "+"):
                if (term.functor == "-" and isinstance(term.args[0], PNumber)
                        and term.args[0].unit is None):
                    # The compound -(1), not the integer -1 that the seam's
                    # `-1` is (a data `1-(-(1))` is emitted through here);
                    # as an expression it evaluates the same.
                    return self._emit_quoted_op_term(term)
                operand = self._emit_expr(term.args[0], 9)
                op = _PREFIX_MAP.get(term.functor, term.functor)
                return f"{op}{operand}"
            # Arithmetic functions: an ISO evaluable keeps its own name
            # (``max``, ``float``), which is what the engine evaluates;
            # anything else is a user function name as before.
            from clausal.logic.exact_arith import EVALUABLE  # noqa: PLC0415
            if (term.functor, len(term.args)) in EVALUABLE:
                name = term.functor
            else:
                name = self._predicate_name(term.functor, len(term.args))
            args = ", ".join(self._emit_expr(a) for a in term.args)
            return f"{name}({args})"
        return self._emit_term(term)

    def _emit_list(self, lst: PList) -> str:
        """Emit a list, converting [H|T] to [H, *T].

        Only a tail that can BE a list is spliced: a variable, a list, or a
        ``"..."`` read as chars or codes.  Any other tail -- ``[x|foo]``,
        ``[x|1]``, ``[x|f(a)]``, ``[x|"ab"]`` under ``double_quotes(atom)``
        -- makes an IMPROPER list, the cons cells ``'.'(H, T)`` (D50), and
        is emitted as those tuples, as the native front end lowers it.
        Spliced as ``*foo`` the seam reads the atom as one more element,
        ``[x, foo]``, a different term."""
        elements = list(lst.elements)
        tail = lst.tail
        while isinstance(tail, PList):        # [x|[y|T]] is [x, y|T]
            elements.extend(tail.elements)
            tail = tail.tail
        if not elements and tail is None:
            return "[]"
        parts = [self._emit_term(e) for e in elements]
        if tail is None:
            return "[" + ", ".join(parts) + "]"
        tail_s = self._emit_term(tail)
        if self._list_tail(tail):
            return "[" + ", ".join(parts + [f"*{tail_s}"]) + "]"
        for part in reversed(parts):
            tail_s = f"('.', {part}, {tail_s})"
        return tail_s

    def _list_tail(self, tail: PTerm) -> bool:
        """Whether a list's ``|`` tail can be a list, so it splices: a
        variable, ``[]``, or a ``"..."`` the double_quotes flag reads as
        chars or codes (a list is flattened before this is asked)."""
        if isinstance(tail, PVar):
            return True
        if isinstance(tail, PAtom):
            return tail.name == "[]"
        if isinstance(tail, PString):
            return self._dq_mode != "atom"
        return False

    # ── Name conversion helpers ──────────────────────────────────────

    def _predicate_name(self, prolog_name: str, arity: int | None = None,
                        rename: bool = True) -> str:
        """Convert a Prolog predicate/functor name to its Clausal spelling.

        Clausal predicate names are lowercase like Prolog's, so an unmapped
        name crosses the seam unchanged (``edge`` stays ``edge``).  The
        translator used to PascalCase here; TitleCase is now a load-time
        error in a Clausal position, so that spelling would not load.

        ``arity`` disambiguates Prolog names shared by Clausal predicates of
        different arity (``catch/3`` vs ``catch_error/2``); pass it wherever
        the call site knows it.

        *rename* False: the name of a DATA term, which keeps its Prolog
        spelling -- the builtin renames below name the predicate a CALL
        runs (as data ``time(foo)`` printed ``time_goal(foo)`` and
        ``zip(a, b)`` raised existence_error(procedure, zip_/2))."""
        if (rename and arity is not None
                and prolog_name not in self._own_names):
            override = _REVERSE_ARITY_OVERRIDES.get((prolog_name, arity))
            if override is not None:
                return override
        # Check reverse builtin map first -- unless the program defines or
        # imports the name itself, when it means its OWN predicate (a
        # program's ``time/1`` is not Clausal's ``time_goal/1``).
        # Nor an ISO evaluable at its evaluable arity (max/2, abs/1): that is
        # no predicate, and as data it is an ordinary compound -- the old
        # rename to the RELATIONAL max_/3 raised type_error(evaluable,
        # max_/2).  The expression emitter keeps evaluables by itself;
        # float/1 is the exception here, being ISO's type test too, which
        # Clausal spells float_/1.
        if rename and prolog_name not in self._own_names and not (
                prolog_name != "float" and _is_evaluable(prolog_name, arity)):
            clausal_name = _reverse_builtin_map().get(prolog_name)
            if clausal_name is not None:
                return clausal_name
        # Unmapped names cross unchanged — except that a Python keyword
        # gets the trailing underscore the codebase uses for the same
        # collision (``in_``, ``if_``): ``not/1`` -> ``not_``.
        name = prolog_name
        if keyword.iskeyword(name):
            name = name + "_"
        # A functor whose EMITTED name is not a plain atom name is a name
        # the Clausal loader reads as something OTHER than a predicate, and
        # this translator must never emit one.  Two shapes reach here:
        # TitleCase (a quoted atom such as ``'Foo'``), which the lint makes
        # a load-time error; and the variable-shaped names — an initial
        # capital (``'FOO'``, ``'X1'``) or a LEADING UNDERSCORE (``'_foo'``),
        # both of which ``_is_logic_var_name`` classifies as logic
        # variables, so the emitted clause would quietly acquire a variable
        # where a predicate was meant.
        #
        # The test is ``not _is_plain_atom_name`` rather than an initial-
        # capital one: keying on the capital missed the underscore case, and
        # paired the two as ``name[:1].isupper() and not
        # _is_plain_atom_name(name)``, whose second conjunct is dead
        # (``_is_plain_atom_name`` requires ``name[0].islower()``).  A name
        # that is not an identifier at all falls through to the check below,
        # which owns that message.
        if name.isidentifier() and not _is_plain_atom_name(name):
            stripped = name.lstrip("_") or name
            if stripped[:1].isupper() and any(c.islower() for c in stripped):
                suggested = _titlecase_to_snake(stripped)
            else:
                suggested = stripped.lower()
            if name[:1] == "_":
                shape = "underscore-led (variable-shaped)"
            elif any(c.islower() for c in name):
                shape = "TitleCase"
            else:
                shape = "capitalised (variable-shaped)"
            # Only offer a rename that would itself load — ``'_'`` and
            # friends have no plain spelling to suggest.
            remedy = (f"Rename it in the Prolog source to {suggested!r} and "
                      f"translate again."
                      if _is_plain_atom_name(suggested)
                      else "Rename it in the Prolog source to a lowercase "
                           "name and translate again.")
            raise PrologTranslationError(
                f"Prolog functor {prolog_name!r} is {shape}, which has no "
                f"role as a Clausal predicate or functor name (those are "
                f"lowercase; a file spelling {name!r} does not load).\n"
                + remedy
            )
        # A functor whose converted name is not a plain Python identifier
        # (quoted atoms like 'hello world', operator soup from unmapped
        # user ops, keyword collisions like `none` → None) cannot become a
        # Clausal predicate — emitting it bare would be a SyntaxError or a
        # silent rebinding downstream (F035, sibling of the F025 arg-position
        # check in _emit_atom). Reject loudly instead.
        if not name.isidentifier() or keyword.iskeyword(name):
            raise PrologTranslationError(
                f"Prolog functor {prolog_name!r} cannot be translated to a "
                f"Clausal predicate name ({name!r} is not a valid Python "
                "identifier).\n"
                "Only plain (unquoted-style) functor names can name Clausal "
                "predicates. Rename the predicate, or provide a user "
                "operator mapping for operator functors."
            )
        return name

    def _emit_atom_name(self, term: PTerm) -> str:
        """Extract an atom name from a term."""
        if isinstance(term, PAtom):
            return term.name
        return self._emit_term(term)

    def _emit_export_list(self, term: PTerm) -> str:
        """Emit an export list [pred/N, ...]."""
        if isinstance(term, PList):
            items = [self._emit_pred_indicator(e) for e in term.elements]
            return "[" + ", ".join(items) + "]"
        return self._emit_term(term)

    def _emit_import_list(self, term: PTerm, keep_arity: bool = False) -> str:
        """Emit an import list [pred1, pred2, ...].

        Indicators in :data:`_OPERATOR_ONLY_IMPORTS` are DROPPED. They name
        Prolog predicates that Clausal writes as an OPERATOR, never as a
        predicate name, so there is no import list they could legally appear
        in: `-import_from(m, [==])` is not even valid Python. The forward
        translator regenerates the import from the emission itself, so
        dropping it here loses nothing on a round trip.
        """
        if isinstance(term, PList):
            items = []
            for e in term.elements:
                if isinstance(e, PCompound) and e.functor == "/" and len(e.args) == 2:
                    name = self._emit_atom_name(e.args[0])
                    if (name, _indicator_arity(e.args[1])) in _OPERATOR_ONLY_IMPORTS:
                        continue
                    pname = self._predicate_name(
                        name, _indicator_arity(e.args[1]))
                    arity = _indicator_arity(e.args[1])
                    items.append(f"{pname}/{arity}"
                                 if keep_arity and isinstance(arity, int)
                                 else pname)
                elif isinstance(e, PAtom):
                    items.append(self._predicate_name(e.name))
                else:
                    items.append(self._emit_term(e))
            # F3: a library's ``[baz/1, baz/2]`` both emit ``baz`` (a bare
            # name imports every arity), so the second is the same entry:
            # once.
            items = list(dict.fromkeys(items))
            return "[" + ", ".join(items) + "]"
        return self._emit_term(term)

    # ── Conjunction/disjunction flattening ────────────────────────────

    def _flatten_conjunction(self, term: PTerm) -> list[PTerm]:
        """flatten nested ',' into a flat list of goals."""
        if isinstance(term, PCompound) and term.functor == "," and len(term.args) == 2:
            left = self._flatten_conjunction(term.args[0])
            right = self._flatten_conjunction(term.args[1])
            return left + right
        return [term]


# ── CLI ──────────────────────────────────────────────────────────────

def _main() -> None:
    import argparse
    import sys

    from clausal._suffixes import SEAM_SUFFIX

    parser = argparse.ArgumentParser(
        prog="prolog_to_clausal",
        description=f"Translate Prolog (.pl) source to seam ({SEAM_SUFFIX}) "
                    "source.",
    )
    parser.add_argument("input", nargs="?", help="Input .pl file (stdin if omitted)")
    parser.add_argument("-o", "--output",
                        help=f"Output {SEAM_SUFFIX} file (stdout if omitted)")
    parser.add_argument("--dialect", choices=["swi", "scryer", "iso"], default=None,
                        help="Prolog dialect (default: Scryer's operator table)")
    parser.add_argument("--operator-map", help="JSON file with user-defined operator mappings")

    args = parser.parse_args()

    # Read input
    if args.input:
        source = Path(args.input).read_text()
    else:
        source = sys.stdin.read()

    # Dialect
    dialect_factories = {"swi": Dialect.swi, "scryer": Dialect.scryer, "iso": Dialect.iso}
    dialect = (dialect_factories[args.dialect]() if args.dialect
               else Dialect.scryer_reader())

    # Translate
    result = prolog_to_clausal(source, dialect=dialect)

    # Write output
    if args.output:
        Path(args.output).write_text(result)
    else:
        sys.stdout.write(result)


if __name__ == "__main__":
    _main()
