"""Prolog → Clausal translation (Phase 3.3).

Pipeline: .pl source → tokens → Prolog AST → .clausal source text

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
# BUILTIN_NAME_MAP alone.  Bare `member/2` in goal position is rendered as
# infix `X in L`, so BUILTIN_NAME_MAP has no clausal-side name for it; but
# wherever a predicate *name* is required (qualified goals like
# `lists:member(X, L)`, metacall arguments like `findall(X, member(X, L), Xs)`)
# the underlying Clausal builtin is `in_/2` (F033).  The engine now also
# registers `member/2` under its ISO name; the rename stays so the
# translation keeps the Clausal spelling of membership.
_REVERSE_OVERRIDES: dict[str, str] = {
    "member": "in_",
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


def _module_file_exists(cand: str) -> bool:
    return (os.path.isdir(cand)
            or any(os.path.isfile(cand + ext)
                   for ext in (".pl", ".clausal", ".seam", ".py")))


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
    "iso_ext",
})


# ── Public API ───────────────────────────────────────────────────────


def prolog_to_clausal(source: str, *, dialect: Dialect | None = None,
                      source_path: str | None = None,
                      module_name: str | None = None) -> str:
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
    """
    if dialect is None:
        dialect = Dialect.scryer_reader()
    pmodule = parse(source, dialect=dialect)
    return prolog_ast_to_clausal(pmodule, dialect=dialect,
                                 source_path=source_path,
                                 module_name=module_name)


def prolog_ast_to_clausal(pmodule: PModule, *,
                          dialect: Dialect | None = None,
                          source_path: str | None = None,
                          module_name: str | None = None) -> str:
    """Translate a Prolog AST module to clausal source text."""
    if dialect is None:
        dialect = Dialect.scryer_reader()
    emitter = _PrologToClausal(dialect, source_path=source_path,
                               module_name=module_name)
    return emitter.emit_module(pmodule)


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
#: database builtins) in the meta-predicates a ``.pl`` file commonly calls
_META_GOAL_ARGS: dict[str, tuple[int, ...]] = {
    "call": (0,), "once": (0,), "ignore": (0,), "\\+": (0,), "not": (0,),
    "findall": (1,), "bagof": (1,), "setof": (1,), "aggregate_all": (1,),
    "forall": (0, 1), "catch": (0, 2), "call_cleanup": (0, 1),
    "setup_call_cleanup": (0, 1, 2), "freeze": (1,), "when": (1,),
    "call_nth": (0,), "time": (0,), "phrase": (0,),
    "maplist": (0,), "foldl": (0,), "include": (0,), "exclude": (0,),
    "partition": (0,),
    "assert": (0,), "asserta": (0,), "assertz": (0,), "retract": (0,),
    "retractall": (0,), "clause": (0,),
}

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
                 module_name: str | None = None):
        self._dialect = dialect
        self._source_path = source_path
        self._module_name = module_name
        self._user_ops = operator_mappings or {}
        self._data_atoms: set[str] = set()  # atoms used as data values
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

    def emit_module(self, pmodule: PModule) -> str:
        """Emit a complete module as clausal source text."""
        self._predicate_names = _collect_predicate_names(pmodule)
        self._own_names = _own_predicate_names(pmodule)
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
        if "prolog." in body:
            preamble_parts.append("-import_module(prolog)")
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

    def _emit_head(self, term: PTerm) -> str:
        """Emit a clause head as a clausal predicate call."""
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

    def _emit_goal(self, goal: PTerm) -> str:
        """Emit a single goal in body context."""
        # A10-F001: a body-position cut must be REJECTED, not emitted as a
        # dead ``Cut()`` goal (no Cut predicate exists — the query later died
        # with KeyError). Delegate to _emit_atom, which raises the documented
        # PrologTranslationError (the cut-free contract, docs/import.md).
        if isinstance(goal, PAtom) and goal.name == "!":
            return self._emit_atom(goal)
        # D21: the forward translator's in_domain/3 type dispatch folds back.
        folded = self._fold_in_domain(goal)
        if folded is not None:
            return folded
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
            parts = ", ".join(
                self._emit_term(p) for p in self._flatten_conjunction(rule.head)
            )
            head = f"({parts})"
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
        # Disjunction in DCG
        if isinstance(goal, PCompound) and goal.functor == ";":
            return self._emit_disjunction(goal)
        # Regular non-terminal
        if isinstance(goal, PCompound):
            return self._emit_compound(goal, goal=True)
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
        # program's text.  Clausal keeps no run-time operator table
        # (current_op/3, op/3 as a goal), so what remains is a comment
        # recording the declaration.
        if isinstance(body, PCompound) and body.functor == "op" and len(body.args) == 3:
            return (f"# operator: op({_plain_term(body.args[0])}, "
                    f"{_plain_term(body.args[1])}, {_plain_term(body.args[2])}) "
                    "-- applied by the reader to the terms below")
        # Generic directive
        return f"-{self._emit_term(body)}"

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
            if lib_name in _LIBRARY_TO_MODULE:
                clausal_mod = _LIBRARY_TO_MODULE[lib_name]
            elif len(body.args) == 2 and _names_all_native(body.args[1]):
                return (f"# library({lib_name}): every name it imports is "
                        "provided by the engine -- no import needed")
            else:
                # Unknown library -- read it as a module of that name (a
                # missing one is an import error at load).
                clausal_mod = self._dotted_or_refuse(lib_name, directive)
        else:
            spec = _slash_path(lib_term)
            if spec is None:
                raise PrologTranslationError(
                    f"{directive}: the module is not an atom, an a/b path "
                    "or library(Name), so it names no module to import.")
            clausal_mod = self._resolve_module_path(spec, directive)

        if len(body.args) == 1:
            # ISO-family use_module/1 imports every EXPORTED predicate,
            # unqualified.  -import_module alone gives only qualified
            # access (``m.p(...)``), so an unqualified call of an import
            # failed; when the module is a .pl file its module/2 export
            # list is read and imported by name as well.
            exports = self._pl_exports(clausal_mod, directive)
            if exports:
                self._own_names.update(exports)
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
            base = os.path.dirname(os.path.abspath(self._source_path))
            cand = os.path.normpath(os.path.join(base, path))
            if _module_file_exists(cand):
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
            pmod = parse(text, dialect=self._dialect)
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
        """The directory the importer's dotted name is relative to: climb
        one directory per dot from the file's directory -- one more for a
        package ``__init__.pl``, whose name IS its directory's."""
        if not (self._source_path and self._module_name):
            return None
        depth = self._module_name.count(".")
        if os.path.basename(self._source_path) == "__init__.pl":
            depth += 1
        root = os.path.dirname(os.path.abspath(self._source_path))
        for _ in range(depth):
            root = os.path.dirname(root)
        return root

    def _find_module_file(self, dotted: str) -> str | None:
        # Only with the importer's name: a direct API call must not read
        # the file system through sys.path (cwd included), or its output
        # would depend on the caller's working directory.
        root = self._package_root()
        if root is None:
            return None
        parts = dotted.split(".")
        roots = [root]
        roots.extend(os.path.abspath(e or os.getcwd()) for e in sys.path
                     if isinstance(e, str))
        for root in roots:
            base = os.path.join(root, *parts)
            if os.path.isfile(base + ".pl"):
                # a .clausal/.seam twin is what the import hook loads
                if any(os.path.isfile(base + ext)
                       for ext in (".clausal", ".seam")):
                    return None
                return base + ".pl"
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
        """*cand* (a module path without extension) as a dotted module name:
        relative to this module's own package root when the importer's
        dotted name is known, else to the most specific sys.path entry."""
        roots: list[str] = []
        root = self._package_root()
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
            return "{" + self._emit_term(term.body) + "}"
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

    def _emit_compound(self, term: PCompound, goal: bool = False) -> str:
        """Emit a compound term (*goal*: it stands in goal position)."""
        functor = term.functor
        args = term.args

        # D21, in TERM position too (a meta-call's goal argument), like `#=`.
        folded = self._fold_in_domain(term)
        if folded is not None:
            return folded

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
                    f"{self._emit_quantified(args[1])}, "
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
        if functor == "," and len(args) == 2:
            parts = ", ".join(
                self._emit_term(p) for p in self._flatten_conjunction(term)
            )
            return f"({parts})"

        # Univ: T =.. L → unpack(T, L) (=.. is not valid Clausal syntax) — F033.
        if functor == "=.." and len(args) == 2:
            left = self._emit_term(args[0])
            right = self._emit_term(args[1])
            return f"unpack({left}, {right})"

        # Module-qualified goal: Module:Goal → Module.Goal(...) (F033).
        if functor == ":" and len(args) == 2 and isinstance(args[0], PAtom):
            module = args[0].name
            goal = args[1]
            if isinstance(goal, PCompound):
                goal_name = self._predicate_name(goal.functor,
                                                 len(goal.args))
                inner = ", ".join(self._emit_term(a) for a in goal.args)
                return f"{module}.{goal_name}({inner})"
            if isinstance(goal, PAtom):
                return f"{module}.{goal.name}()"

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

        # Unification: X = Y → X is Y
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

        # Arithmetic operators (precedence-aware)
        if functor in self._EXPR_PREC and len(args) == 2:
            return self._emit_expr(term)

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
            clausal_op = _PREFIX_MAP[functor]
            operand = self._emit_term(args[0])
            if clausal_op == "not":
                return f"not {operand}"
            return f"{clausal_op}{operand}"

        # Regular compound: functor(args) → functor(args), name unchanged
        name = self._predicate_name(functor, len(args))
        if not goal and args and name == functor and _is_plain_atom_name(name):
            self._data_functors.setdefault(name, set()).add(len(args))
        if not args:
            return f"{name}()"
        arg_strs = self._emit_args(functor, args)
        return f"{name}({arg_strs})"

    def _emit_args(self, functor: str, args) -> str:
        """The emitted argument list of a ``functor(args)`` head, goal or
        data term.

        plunit's ``test(Name, Option)``: the option is DATA the test runner
        reads, so an atom option (``fail``, ``false``) stays the atom it
        spells rather than folding to the truth value ``False``.  Applied in
        every position -- head, goal and data alike -- so a ``test/2`` fact
        and a call of it still unify."""
        emitted = [self._emit_term(a) for a in args]
        if (functor == "test" and len(args) == 2
                and isinstance(args[1], PAtom)):
            emitted[1] = _quote_atom(args[1].name)
        return ", ".join(emitted)

    @staticmethod
    def _refuse_caret_goal() -> None:
        raise PrologTranslationError(
            "The existential quantifier ((^)/2) is only supported inside "
            "the goal argument of bagof/3 or setof/3; `V^Goal` called as a "
            "goal (directly, or in a goal argument of findall/forall/\\+/"
            "...) cannot be translated."
        )

    def _emit_quoted_op_term(self, term: PCompound) -> str:
        """An ISO operator term in DATA position: the quoted functor over
        operands emitted as TERMS (so their functors are declared), not as
        arithmetic."""
        inner = ", ".join(self._emit_term(a) for a in term.args)
        return f"{_quote_atom(term.functor)}({inner})"

    def _emit_quantified(self, term: PTerm) -> str:
        """The goal argument of bagof/setof: ``V^G`` → ``V ^ (G)``, nested
        to the right; anything else is the goal term itself."""
        if (isinstance(term, PCompound) and term.functor == "^"
                and len(term.args) == 2):
            witness = self._emit_term(term.args[0])
            inner = term.args[1]
            inner_s = self._emit_quantified(inner)
            # Always parenthesised (a conjunction already is): Python's
            # ``^`` binds tighter than ``is``/comparison, so ``Y ^ X is Y``
            # would read as ``(Y ^ X) is Y``.
            if not (isinstance(inner, PCompound) and inner.functor == ","
                    and len(inner.args) == 2):
                inner_s = f"({inner_s})"
            return f"{witness} ^ {inner_s}"
        return self._emit_term(term)

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
        """Emit a list, converting [H|T] to [H, *T]."""
        if not lst.elements and lst.tail is None:
            return "[]"
        parts = [self._emit_term(e) for e in lst.elements]
        if lst.tail is not None:
            tail_s = self._emit_term(lst.tail)
            parts.append(f"*{tail_s}")
        return "[" + ", ".join(parts) + "]"

    # ── Name conversion helpers ──────────────────────────────────────

    def _predicate_name(self, prolog_name: str, arity: int | None = None) -> str:
        """Convert a Prolog predicate/functor name to its Clausal spelling.

        Clausal predicate names are lowercase like Prolog's, so an unmapped
        name crosses the seam unchanged (``edge`` stays ``edge``).  The
        translator used to PascalCase here; TitleCase is now a load-time
        error in a Clausal position, so that spelling would not load.

        ``arity`` disambiguates Prolog names shared by Clausal predicates of
        different arity (``catch/3`` vs ``catch_error/2``); pass it wherever
        the call site knows it."""
        if arity is not None and prolog_name not in self._own_names:
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
        if prolog_name not in self._own_names and not (
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

    parser = argparse.ArgumentParser(
        prog="prolog_to_clausal",
        description="Translate Prolog (.pl) source to clausal (.clausal) source.",
    )
    parser.add_argument("input", nargs="?", help="Input .pl file (stdin if omitted)")
    parser.add_argument("-o", "--output", help="Output .clausal file (stdout if omitted)")
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
