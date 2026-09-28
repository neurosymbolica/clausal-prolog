"""Term → AST expression lowering.

Converts a compile-time term value (Var, scalar, list, cell,
functor-dataclass, DictTerm, SetTerm, SetLiteral, DictLiteral,
StarUnpack, TupleLiteral, Call-with-LoadName, PyThunk, …) into a
Python AST expression that, at runtime, reconstructs that term.

Also provides the small parsing helpers ``_is_star_list`` /
``_parse_star_segments`` / ``_count_stars`` (used both here for list
rewriting and by ``.star_segments`` for body-Is compilation) and
``_dotted_name_from_loadattr`` (used here and by ``.globals_env``).
Co-locating the parsing helpers with ``term_to_ast_expr`` avoids a
star_segments ↔ terms_to_ast import cycle.
"""

from __future__ import annotations

import ast
import datetime
import sys

from contextlib import contextmanager
from contextvars import ContextVar
from fractions import Fraction

from clausal.logic.exact_arith import (
    exact_add as _exact_add, exact_sub as _exact_sub,
    exact_mul as _exact_mul, python_truediv as _python_truediv,
    python_floordiv as _python_floordiv, python_mod as _python_mod,
    python_pow as _python_pow,
    evaluate as _evaluate, evaluate_python_result as _evaluate_python_result,
)
from typing import Any

from clausal.logic.variables import Var, is_var, deref, present_number
from clausal.terms import (
    Add, Sub, Mult, Div, FloorDiv, Mod, Pow,
    Negate,
    Call, LoadName, LoadAttr, LoadSubscript,
    DictTerm, SetTerm, PyThunk,
    Undefined,
)
from clausal.pythonic_ast.nodes import (
    StarUnpack, TupleLiteral, DictLiteral, SetLiteral,
    Lambda, literal_value,
    SetLiteral as _SetLiteral_t,
)
from clausal.logic.meta_predicate import MetaArg as _MetaArg
from clausal.logic.predicate import (
    is_declared_predicate_name,
    construction_arity_fault,
    namespace_db,
    is_term_instance, predicate_binding_name, term_field_names, term_field_names_of_class,
)
from clausal.logic.atoms import (
    is_atom as _term_is_atom,
    is_mangled as _is_mangled,
    mint as _mint_atom,
    spelling as _atom_spelling,
)
from clausal.logic.constants import _FrozenList, _FrozenDict, _FrozenSet
from clausal.logic.cells import FUNCTOR_SIGNATURES_KEY, IMPLICIT_FUNCTORS_FLAG

from clausal.logic.generated_names import dollar_ref
from ._ast_helpers import _name, _call, _attr
from ._vars import _var_python_name


# ── Parsing helpers (used here and by .star_segments) ────────────────────────




def headlit_global_key(term: Any) -> str:
    """The base_globals key under which an opaque head literal is injected.

    Keyed by ``id()`` (like ``_pyt_<id>`` for PyThunks) so the collector in
    globals_env and the guard emitter in head_match reference the SAME entry.
    The value is kept alive by the clause head, so the id is stable.
    """
    return f"$headlit_{id(term)}"


def _is_opaque_head_literal(term: Any) -> bool:
    """True for a GROUND Python value that ``head_to_match_pattern`` has no
    dedicated branch for (``datetime.date``, ``Decimal``, ``Fraction``,
    ``tuple``, ``set``/``frozenset``, ``Path``, …) and would otherwise compile
    to the accept-all wildcard fallback (A02-F003).

    Such a value is captured and unified against a ``$headlit_<id>`` global
    injected by the globals collector. Types the compiler already handles
    inline (primitives, str/bytes, and structural term nodes) return False, as
    do non-ground containers (which stay structural / keep the old wildcard).
    """
    term = deref(term)
    if is_var(term):
        return False
    # Primitives emitted as ast.Constant; str/bytes have dedicated guards.
    if term is None or isinstance(term, (bool, int, float, complex, str, bytes)):
        return False
    # Structural term types with dedicated head_to_match_pattern branches.
    if isinstance(term, (list, dict, DictTerm, SetTerm,
                         StarUnpack, Call, LoadName, LoadAttr,
                         TupleLiteral, DictLiteral, SetLiteral)):
        return False
    if is_term_instance(term):
        return False
    # Ground containers with a nested unbound Var stay structural (a captured
    # literal can't bind the inner Var) — keep the degraded wildcard for them.
    if isinstance(term, (tuple, set, frozenset)):
        return all(not is_var(deref(e)) for e in term)
    return True


class PredicateAsTermError(Exception):
    """A predicate (arity ≥ 1) was used where a term value was expected.

    Overwhelmingly this is the atom/predicate name clash: a bare name in
    *data* position — most often a dict key, ``{query_date: 5}`` — that is
    also the name of a predicate in the same module resolves to the
    **predicate class**, which is not a term value.

    A predicate object is neither identical nor equal to the same-named atom
    (atoms are global-by-spelling interned strs, §1b/R2; predicates stay
    module-local classes), so accepting it here would replace a load-time
    crash with a dict whose key can never be read back.  It stays an error;
    only the diagnostic is improved.
    """

    def __init__(self, pred: Any) -> None:
        self.pred = pred
        name = getattr(pred, "__name__", repr(pred))
        arity = len(getattr(pred, "_fields", ()) or ())
        super().__init__(
            f"{name}/{arity} is a predicate, not a term value: the bare name "
            f"'{name}' in data position resolves to the predicate defined in "
            f"this module, not to a same-named atom. If an atom was meant "
            f"(e.g. as a dict key), name it unambiguously: use the qualified "
            f"form of the module that owns it (owner.{name}), or use a string "
            f"key (\"{name}\"), or rename one of the two. A predicate object "
            f"is not equal to the atom of the same name, so it cannot be used "
            f"as a key."
        )


# (P3-1 §1b/R2: atoms are global-by-spelling interned strs. The by-identity
# atom lowering that used to live here — ``atom_identity_lowering()`` /
# ``atom_identity_expr()`` / ``$atom(<token>)`` — existed to stop a live
# atom-CLASS object from being silently re-resolved onto a same-named
# predicate in the callee namespace (see the retired
# ``todo/query-template-rebinds-atom-dict-keys.md``). An atom lowers to an
# ``ast.Constant`` unconditionally (below) and is never looked up
# by name at all, so the hazard this machinery guarded against cannot occur
# any more.)


# ── The compile scope: which namespace resolves a bare functor name ─────────
#
# Lowering a source-written compound ``point(1, 2)`` requires answering what
# the name ``point`` MEANS in the module being compiled: a DATA functor
# lowers to a cell literal ``("point", 1, 2)``, a PREDICATE stays a class
# construction (calling it is a goal, and ``call/1`` dispatches on the
# class).  That answer lives in the namespace the compile targets, and this
# stack is how that namespace reaches the lowering: ``term_to_ast_expr`` is
# reached from ~56 call sites across the compiler, and threading ``globals_``
# through every one of them would be a signature change for no benefit.
#
# A ``compile_predicate_*`` entrypoint pushes exactly one entry for the
# duration of one predicate's compilation.  Only the TOP entry is consulted,
# so a nested compile resolves against ITS OWN namespace: a compile handed no
# namespace pushes ``None`` and resolves nothing, rather than inheriting
# whatever scope an outer compile happens to have left open.
_LOWERING_SCOPE_STACK: "list[dict | None]" = []


@contextmanager
def lowering_scope(module_globals: "dict | None"):
    """Scope name resolution for the duration of one predicate's compile.

    *module_globals* is the namespace this compile targets — the same dict
    the compile entrypoint received as ``globals_`` — used to resolve a
    functor name to what it refers to (a declared data functor's signature,
    or a predicate class).

    ``None`` opens a scope that resolves NOTHING: with no namespace there is
    no way to tell a data functor from a predicate, so every name-resolved
    question answers ``None`` (a caller that passes its own
    ``resolve_globals`` is unaffected).  Both
    :func:`clausal.logic.compiler.predicate.compile_predicate_trampoline` and
    ``compile_predicate_shallow`` always enter this manager, so "no
    namespace" is a state the stack records, never merely the absence of one.
    """
    _LOWERING_SCOPE_STACK.append(module_globals)
    try:
        yield
    finally:
        _LOWERING_SCOPE_STACK.pop()


def _lowering_db():
    """The innermost open compile's module DATABASE, or None -- the ruling-Q0
    ``db=`` hint for the era-agnostic predicate resolvers, read from the
    namespace's ``$module`` the same way ``functor_signature_for`` does."""
    namespace = lowering_globals()
    if namespace is None:
        return None
    return namespace_db(namespace)


def lowering_globals() -> "dict | None":
    """The namespace the innermost open compile targets, or None.

    Reads only the TOP of the stack: a compile nested inside another answers
    with its own namespace, because that is what it pushed.
    """
    return _LOWERING_SCOPE_STACK[-1] if _LOWERING_SCOPE_STACK else None


def _implicit_functors_active(namespace: "dict | None") -> bool:
    """True if *namespace* opted into open-world (OWA) functor construction
    via ``-implicit_functors`` (P3-2 Task 6, user ruling R7).

    ``namespace`` is typically :func:`lowering_globals`'s answer -- the SAME
    dict a Site A/head-match call site already resolved the functor name
    against, so the flag check agrees with whatever module the reference is
    actually being compiled in. See ``clausal.logic.cells.
    IMPLICIT_FUNCTORS_FLAG``.
    """
    return namespace is not None and bool(namespace.get(IMPLICIT_FUNCTORS_FLAG))


# (The class-shaped data-functor gate that used to live here --
# ``_is_cell_functor_class``, briefly ``predicate.is_data_functor`` -- is
# DELETED.  Cell-vs-class is decided on the BINDING now (R6): a name bound to
# a ``PredicateMeta`` is a predicate/class reference, a name bound to its
# interned spelling with a signature-registry entry is data.  Nothing asks the
# question of a CLASS any more -- a live instance always keeps class emission
# -- so a gate that inspected ``_fields``/``_clauses``/
# ``position`` had no callers left.)


def _goal_cell_functor(fname: str, arity: int, namespace) -> "str | None":
    """The functor of the goal CELL ``fname(A1 ... An)`` builds in TERM
    position although nothing declares *fname* as a functor -- or None, for
    the ordinary construction.

    Two kinds of name, both goals that no predicate CLASS stands behind, so
    the ``ast.Call`` fallback could only fail at run time:

    * a compiler SPECIAL FORM (``findall/3``, ``once/1``, ``catch/3`` ...,
      ``call_body.SPECIAL_FORMS``), bare: nothing callable is bound to the
      name, and ``G is findall(X, p(X), L)`` raised NameError "not in scope
      as a term class";
    * a name -- bare, or the DOTTED spelling ``-import_from`` rewrites an
      imported name into (``py.re.match``) -- bound to a NON-callable
      ``_get_dispatch`` goal object such as a ``ModulePredicate``, where
      ``G is match(P, S)`` raised TypeError "'ModulePredicate' object is not
      callable".  The cell carries the BASE name (``match``), the R5
      spelling every other imported functor's cell has.

    The cell is what ``call/1`` runs as that very goal (``call_body.
    special_form_dispatch``; ``higher_order._goal_object_dispatch``).  A name
    bound to a declared PREDICATE keeps its class construction, and a
    callable binding keeps being called (out-of-tree ``_get_dispatch``
    implementors may construct their term that way).
    """
    resolved = _resolve_functor_binding(fname, namespace) if namespace else None
    binding, leaf = (resolved[0], resolved[1]) if resolved else (None, fname)
    if binding is not None and is_declared_predicate_name(
            binding, db=namespace_db(namespace)):
        return None
    from clausal.logic.builtins.call_body import is_special_form  # noqa: PLC0415
    if "." not in fname and is_special_form(fname, arity):
        return fname
    if (binding is not None and type(binding) is not str
            and hasattr(binding, "_get_dispatch") and not callable(binding)):
        # The base name only where it names THIS object in the module and is
        # not a special form: ``py.re.findall`` must stay dotted, since the
        # bare ``findall/3`` cell is the special form, and so is it in a body
        # (the import rewrote the body call to the dotted name too).
        if (leaf != fname and namespace.get(leaf) is binding
                and not is_special_form(leaf, arity)):
            return leaf
        return fname
    return None


def _resolve_functor_binding(
    name: str, namespace: dict
) -> "tuple[Any, str, Any] | None":
    """Resolve *name* — bare or DOTTED — against *namespace*.

    Returns ``(binding, leaf_name, leaf_namespace)``:

    * *binding* is what the name is bound to, or ``None`` when nothing of
      that spelling is bound — the signature registry may still know the
      functor, so an unbound name is not on its own a refusal.
    * *leaf_name* is the last dotted component (``other.Wrap`` → ``Wrap``),
      the spelling *leaf_namespace*'s registry records it under.
    * *leaf_namespace* is the namespace that directly contains the leaf:
      *namespace* itself for a bare name, and the OWNING module's
      ``__dict__`` for a dotted one — so ``other.Wrap`` reads ``other``'s
      registry, not the referring module's.

    Returns ``None`` only when a dotted prefix does not resolve to anything
    with a namespace (there is nothing to consult at all).

    A dotted name reaching here is module-qualified: it is what
    ``_dotted_name_from_loadattr`` built from a ``LoadAttr`` chain, or what
    the import machinery rewrote an imported functor reference into
    (``tests.fixtures.owner.Wrap`` — note that the generated code carries
    that whole string as ONE ``ast.Name`` id, a single global lookup, not an
    attribute walk).  So the prefix is resolved as a module path: by walking
    attributes from *namespace* when its head is bound there, and otherwise
    through ``sys.modules``, which is where a fully-qualified rewrite's
    target lives.
    """
    if "." not in name:
        return namespace.get(name), name, namespace
    prefix, _, leaf = name.rpartition(".")
    owner = _resolve_module_path(prefix, namespace)
    if owner is None:
        return None
    leaf_namespace = getattr(owner, "__dict__", None)
    if leaf_namespace is None:
        return None
    binding = leaf_namespace.get(leaf)
    if binding is None:
        # The referring namespace may bind the whole dotted spelling as one
        # key (the qualified-rewrite shape described above).
        binding = namespace.get(name)
    return binding, leaf, leaf_namespace


def _resolve_module_path(prefix: str, namespace: dict) -> Any:
    """The object a dotted *prefix* names, or None.

    Walks attributes from *namespace* first (an ``-import_module`` binds the
    module object under its head component), then falls back to
    ``sys.modules`` (a fully-qualified reference names a module that is
    loaded but not necessarily bound in the referring namespace).
    """
    parts = prefix.split(".")
    obj = namespace.get(parts[0])
    for attr in parts[1:]:
        if obj is None:
            break
        obj = getattr(obj, attr, None)
    if obj is not None:
        return obj
    return sys.modules.get(prefix)


def functor_signature_for(name: str, namespace: "dict | None", *, classes: bool = True) -> "tuple[str, ...] | None":
    """Resolve *name*'s declared field-name tuple against *namespace*.

    Consults *namespace*'s ``__clausal_functor_signatures__`` registry
    FIRST — the dict the ``-module``/``-private`` rewrite emits (Task 1 of
    the cell-default-flip bridge; see ``clausal.logic.cells.
    FUNCTOR_SIGNATURES_KEY``), which ``-import_from`` also copies entries
    into under their local spelling.  Falls back to a resolved class's
    declared fields (``term_field_names_of_class``, the same class-cases
    ``head_match._resolved_field_names`` covers) while generated functor
    classes still exist — a later task removes them, at which point the
    registry becomes the only source of truth.

    Returns ``None`` when *namespace* is ``None``, *name* is not in the
    registry, and *name* does not resolve to a term-shaped class either.
    """
    if namespace is None:
        return None
    # P2 Task 2 (R-P2-1): the Database is the registry; the module-level map
    # below is the EXEC-TIME carrier (bound before the module body runs) and
    # answers while the Database has not been filled yet.
    db = getattr(namespace.get("$module"), "db", None)
    if db is not None:
        declared = db.declared_fields_by_name(name)
        if declared is not None:
            return declared
    registry = namespace.get(FUNCTOR_SIGNATURES_KEY)
    if registry is not None and name in registry:
        return registry[name]
    if not classes:
        return None            # the caller resolves a class binding itself (the seam does)
    return term_field_names_of_class(namespace.get(name))


def cell_signature_for_name(
    name: str, resolve_globals: "dict | None" = None, *, arity: "int | None" = None
) -> "tuple[str, tuple[str, ...]] | None":
    """Resolve *name* to ``(functor, fields)`` for a DATA functor, or None.

    Cells are the compiled representation of compound DATA (P3-2 Task 2, the
    flip): a saturated, partial or keyword-shaped reference to a data functor
    lowers to a cell literal, whatever module declared it.  This is the
    arity-agnostic primitive both ``term_to_ast_expr``'s construction placer
    and ``head_match``'s pattern placer route through, since signature
    PLACEMENT (positional args fill leading slots, keyword args fill named
    slots, an omitted slot backfills) has replaced "saturated arity or fall
    back to class emission" as the eligibility test.

    Returns ``None`` when:

    * there is no namespace to resolve against (no *resolve_globals* and no
      open :func:`lowering_scope` — nothing can be decided, so nothing is);
    * a dotted prefix does not resolve;
    * the name is bound to a ``PredicateMeta`` CLASS.  Post-flip (R6) the
      BINDING SHAPE is what decides data-vs-predicate at a reference site:
      a declared data functor binds its interned spelling str
      (``compiler_v2._process_declarations``) and a predicate keeps its
      class, so "resolves to a class" means "not data".  This is also what
      keeps a functor minted in PYTHON and imported into a ``.clausal`` file
      on class construction WHILE IT STILL CARRIES THE BRIDGE FLAG: its
      Python producers build instances at runtime, and a cell-compiled
      clause could never match one.  Task 6 emptied the flag, so the
      vocabularies that used to be the examples here --
      ``clausal.reflection``'s ``Goal``/``Clause`` and ``clpb``'s
      ``BoolEq``/``BoolImpl`` -- now compile to cells on BOTH sides;
    * no signature is known for it — neither the module's
      ``__clausal_functor_signatures__`` registry nor a resolved class's
      ``_fields`` names its fields, so there is no slot layout to place
      arguments into.

    *resolve_globals* is the namespace to look *name* up in.  Call sites that
    have one pass it, so the name resolves against the SAME dict the
    class-emission branch beside it uses — in ``head_match`` that is
    ``_resolve_loadname(name, globals_)``, and a cell branch resolving
    somewhere else could disagree with its own fallback about what ``name``
    means.  When omitted, the open compile scope's namespace is used.

    A DOTTED name (``other.Wrap``) resolves by walking attributes from the
    namespace root, and answers with the BASE functor's spelling — ``Wrap``,
    never ``other.Wrap``, since slot 0 of the cell the owning module builds
    holds the bare functor (R5: compound data crosses module boundaries as
    cells now, so both sides must agree on slot 0).  Its fields come from the
    OWNER's registry, for the same reason.

    A name bound to a predicate HANDLE (the binding after the flip) is
    spelled by :func:`handle_cell_functor`: always its PLAIN name (operator
    ruling 2026-09-25, option (a)).
    """
    namespace = resolve_globals if resolve_globals is not None else lowering_globals()
    if namespace is None:
        return None
    resolved = _resolve_functor_binding(name, namespace)
    if resolved is None:
        return None
    binding, leaf, leaf_namespace = resolved
    _db = namespace_db(namespace)
    if is_declared_predicate_name(binding, db=_db):
        # (W4a: the `_clausal_instances` gate that stood here is gone with the
        # bridge.  It read the flag straight out of `cls.__dict__`, so it kept
        # honouring a class-body assignment after the attribute itself became
        # a tombstone -- the one door left through which the retired flag
        # still changed what the compiler emitted.)
        # P2 Task 3: a PREDICATE functor in term position compiles to the cell
        # too; its class only ever built instances, and __call__ builds cells
        # now, so the class-call path would only cost a runtime construction.
        cls_fields = term_field_names_of_class(binding)
        if cls_fields is None:
            return None
        # ``is_predicate``: the question was just answered above, so the
        # spelling does not ask ``is_declared_predicate_name`` a second time.
        _spelled = _functor_spelling(binding, leaf, is_predicate=True)
        if arity is not None and arity != len(cls_fields):
            # Ruling C (2026-09-24): a term is built at its WRITTEN arity,
            # never padded -- and never refused or corrected when it is
            # LONGER either (operator ruling 2026-09-25: ``--q(1, 2, 3)`` for
            # a ``q/2`` is ``('q', 1, 2, 3)``; this arm used to answer None
            # for the long case, and the caller then placed the arguments
            # against the name's DECLARATION and refused them).  A predicate NAME may be written at several
            # arities (name+arity), so a short construction of one is the
            # compound at the arity written -- ``count_leaves(T)`` naming the
            # nonterminal count_leaves//1 is ``('count_leaves', T)``, and
            # phrase appends S0/S to it.  A DATA functor's declaration does
            # fix the slots, so a short construction of one is refused by
            # ``_place_signature_slots`` exactly as a long one is.
            return (_spelled, tuple(f"arg_{i}" for i in range(arity)))
        return _spelled, tuple(cls_fields)
    fields = functor_signature_for(leaf, leaf_namespace)
    if fields is None:
        if binding is None and "." not in name:
            return evaluable_functor_signature(leaf, arity)
        return None
    return _functor_spelling(binding, leaf), fields


def evaluable_functor_signature(
    name: str, arity: "int | None" = None
) -> "tuple[str, tuple[str, ...]] | None":
    """``(name, fields)`` when *name* is a functor of the closed evaluable
    table (``clausal.logic.exact_arith.EVALUABLE``: ``+ - * / // div mod **
    ^ rdiv``, ``abs min max``, the rounding, float, trigonometric and bitwise
    functors ...) -- else None.  The arity-0 entries (``pi``, ``e``) are
    ATOMS, not constructions: they are never answered here (a zero-field
    signature would build the reserved one-tuple); in ARITHMETIC position the
    rewriter emits their atom without a declaration
    (``term_rewriting._mark_arith_position_names``).

    Ruling Q16 (2026-09-28): "they are builtins really".  Like a builtin
    predicate's name, an evaluable functor is in scope in EVERY module, with
    no declaration, so ``rdiv(7, 2)``, ``'//'(A, B)`` and ``'^'(2, 3)`` are
    written in source as they are in Prolog.  It is only the FALLBACK for a
    name nothing binds: a module's own declaration or predicate of the same
    spelling answers first (and its usual arity errors apply).  *arity*
    picks between ``-/1`` and ``-/2``; with none, the widest is answered and
    ``construction_signature_for_name`` re-asks at the written arity."""
    from clausal.logic.exact_arith import EVALUABLE  # noqa: PLC0415
    arities = [a for (n, a) in EVALUABLE if n == name and a > 0]
    if not arities:
        return None
    if arity is None:
        arity = max(arities)
    elif arity not in arities:
        return None
    return name, tuple(f"arg_{i}" for i in range(arity))


def construction_signature_for_name(
    name: str, resolve_globals: "dict | None" = None, *,
    n_positional: int, has_keywords: bool,
) -> "tuple[str, tuple[str, ...]] | None":
    """The ``(functor, fields)`` a construction or head pattern WRITTEN with
    *n_positional* positional arguments is placed against, or None.

    :func:`cell_signature_for_name`, then ruling C (2026-09-24): when the
    shared decision :func:`~clausal.logic.predicate.construction_arity_fault`
    calls a keyword-free construction ``"too_few"``, ask again at the
    WRITTEN arity -- a predicate NAME answers that arity's own slots (the
    compound at the arity written, as in Scryer), a DATA functor its
    declaration (which ``_place_signature_slots`` then refuses).  The one
    home of that re-ask for ``term_to_ast_expr``'s construction site and
    ``head_match``'s pattern site.
    """
    sig = cell_signature_for_name(name, resolve_globals)
    if (sig is not None and not has_keywords
            and construction_arity_fault(sig[1], n_positional, ())
            in ("too_few", "too_many")):
        # Too MANY as well as too few (operator ruling 2026-09-25): a
        # predicate name written at another arity is the compound AT THAT
        # ARITY, never refused or corrected -- ``--q(1, 2, 3)`` for a
        # ``q/2`` is ``('q', 1, 2, 3)``.  A DATA functor answers its
        # declaration again, which ``_place_signature_slots`` then refuses.
        sig = cell_signature_for_name(name, resolve_globals, arity=n_positional)
    return sig


def handle_cell_functor(handle: str) -> str:
    """The functor a cell built from the predicate HANDLE *handle* carries:
    ALWAYS its PLAIN name (operator ruling 2026-09-25, option (a), which
    supersedes option (c)).

    ISO: a functor is never module-qualified.  Qualification lives only on a
    GOAL, as ``M:G``.  So a cell built in data, term or head position from a
    handle -- an imported or local name, a handle held in Python
    (``h = mangle(m, p)``), a dotted ``lib.p(X)`` in term position -- is the
    plain ``(p, ...)`` cell the owner's own clauses build, and one logical
    term has one spelling (``lib.make(T), T = lib.p(X)`` unifies).  A cell
    that must RUN in another module is called as ``lib:G`` or
    ``solve(cell, lib)``.  The caller has already established that *handle*
    is a declared predicate's handle; a ``-hide`` DATA atom never reaches
    here and keeps its mangled spelling.
    """
    from clausal.logic.atoms import demangle  # noqa: PLC0415
    return demangle(handle)[1]


def _functor_spelling(binding: Any, leaf: str, *,
                      is_predicate: bool = False) -> str:
    """The functor string slot 0 carries for a name bound to *binding*.

    A CLASS answers with its own ``__name__``: an ``-import_from`` alias
    (``pt as local_pt``) binds the owner's class, and the cell the owner
    builds is tagged ``"pt"`` — matching the alias's local spelling instead
    would build a term the owner's clauses can never match.

    An ATOM answers with its SPELLING, for exactly the same reason: post-flip
    a declared data functor whose class was never minted binds the minted atom
    (``compiler_v2._process_declarations``), and an aliased import of one binds
    the OWNER's spelling under the local name.  Read through the public atom
    API (2026-09-06-atoms-as-cells-strings, Task 9) so the arity-0 cell
    ``("pt",)`` answers alongside today's ``str`` binding.

    Anything else (nothing bound, some unrelated value) falls back to the
    leaf name — the only spelling available, and the right one whenever the
    registry entry is the module's own declaration.

    A predicate HANDLE (a mangled atom -- the binding after the flip) is
    spelled by :func:`handle_cell_functor`, always PLAIN: an importer's
    ``gd_p(X)`` builds the ``("gd_p", X)`` cell the owner's clauses are keyed
    by, as its class does (flip dry run R3, fix A2).  *is_predicate*
    says the caller established that *binding* is a declared predicate
    (``is_declared_predicate_name``); without it a mangled binding is a
    ``-hide`` DATA atom, whose mangled spelling is its identity.
    """
    if isinstance(binding, type):
        return binding.__name__
    if is_predicate and type(binding) is str and _is_mangled(binding):
        return handle_cell_functor(binding)
    if _term_is_atom(binding):
        return _atom_spelling(binding)
    return leaf


def cell_functor_for_name(name: str, arity: int,
                          resolve_globals: "dict | None" = None) -> "str | None":
    """Resolve *name* to a cell functor for a saturated *arity* construction.

    A thin, arity-checked wrapper over :func:`cell_signature_for_name` —
    kept for callers that only want the "exact saturation or nothing"
    answer; ``head_match`` and ``term_to_ast_expr``'s construction site route
    through the unwrapped signature instead so they can PLACE a
    partial/keyword construction rather than reject it.
    """
    result = cell_signature_for_name(name, resolve_globals)
    if result is None:
        return None
    functor, fields = result
    if len(fields) != arity:
        return None
    return functor


_UNSET = object()  # sentinel: a signature slot no positional/keyword arg filled


def _cell_arity_error(functor: str, fields: "tuple[str, ...]", n_args: int) -> SyntaxError:
    """Compile-time over-arity error for a cell construction/head reference.

    Mirrors ``clausal.logic.predicate.term_arity_error_for``'s wording (functor,
    declared arity, declared field tuple) — that function builds the RUNTIME
    twin of this same mistake (``PredicateMeta.__call__`` passed too many
    positional arguments); this is the compile-time one, raised while
    lowering a ``.clausal`` source reference instead of while calling a live
    class.
    """
    return SyntaxError(
        f"functor {functor}/{len(fields)} was constructed with {n_args} "
        f"positional argument(s) but its class was registered with "
        f"{len(fields)} field(s) {fields!r}"
    )


def _cell_field_error(functor: str, fields: "tuple[str, ...]", bad_name: str) -> SyntaxError:
    """Compile-time unknown-field error for a cell construction/head reference.

    Mirrors ``clausal.logic.predicate.term_construction_error_for``'s wording
    (functor, declared field tuple, the offending name) — the compile-time
    twin of that function's runtime ``__init__`` ``TypeError`` re-raise.
    """
    return SyntaxError(
        f"functor {functor}/{len(fields)} was constructed with field name "
        f"{bad_name!r} but its class was registered with fields {fields!r}"
    )


def _cell_duplicate_slot_error(functor: str, fields: "tuple[str, ...]", name: str) -> SyntaxError:
    """Compile-time error: *name* was supplied both positionally and by
    keyword in the same construction/head reference — no such runtime shape
    exists (``PredicateMeta.__call__`` never sees the same conflict; a
    keyword there is applied over a plain-dict positional fill with no
    duplicate-detection at all), so this check exists only at compile time,
    where the two forms are still distinguishable expressions rather than
    one dict.
    """
    return SyntaxError(
        f"functor {functor}/{len(fields)} was constructed with both a "
        f"positional argument and keyword `{name}=` for the same field "
        f"{fields!r}"
    )


def _place_signature_slots(fields, positional, keywords, *, functor, missing):
    """Place *positional* values and *keywords* ``(name, value)`` pairs
    against declared *fields*, returning a list of length ``len(fields)``.

    Positional entries fill leading slots in order.  Each keyword fills the
    slot its field name names.  Any slot neither reaches is filled by calling
    ``missing()`` (once PER omitted slot — not memoised — since a Site A
    placement needs a fresh ``Var()`` expression per omitted slot, not one
    shared expression evaluated once).

    Compile-time errors, mirroring the runtime construction errors
    ``clausal.logic.predicate`` raises for the same three mistakes: too many
    positional arguments (:func:`_cell_arity_error`), an unknown field name
    (:func:`_cell_field_error`), and — a check the runtime path does not
    make, since a keyword there just overwrites the positional fill in the
    same dict — a field supplied both positionally and by keyword
    (:func:`_cell_duplicate_slot_error`).

    *positional*/*keywords* are representation-agnostic: Site A passes AST
    expressions, ``head_match`` passes AST patterns, and this function does
    not inspect either beyond placing them.
    """
    n_fields = len(fields)
    if construction_arity_fault(
            fields, len(positional), [name for name, _ in keywords]):
        # Too many positional arguments, or (ruling C, 2026-09-24: no silent
        # padding) too FEW -- decided by the runtime's own helper, so the
        # compile-time and runtime refusals cannot drift apart.  (A predicate
        # name at another arity never reaches here:
        # ``construction_signature_for_name`` gives it the written arity's
        # own slots.)  Keyword-only construction that names only SOME slots
        # is refused as well (operator ruling 2026-09-25): ``missing()`` is
        # never reached any more by a construction the decision admits.
        raise _cell_arity_error(functor, fields, len(positional))
    slots = [_UNSET] * n_fields
    for i, value in enumerate(positional):
        slots[i] = value
    for name, value in keywords:
        if name not in fields:
            raise _cell_field_error(functor, fields, name)
        idx = fields.index(name)
        if slots[idx] is not _UNSET:
            raise _cell_duplicate_slot_error(functor, fields, name)
        slots[idx] = value
    return [missing() if slot is _UNSET else slot for slot in slots]


def cell_literal_ast(functor: str, arg_exprs: list[ast.expr]) -> ast.Tuple:
    """The cell literal ``("functor", <arg0>, ...)`` as an AST expression."""
    return ast.Tuple(
        elts=[ast.Constant(value=functor), *arg_exprs],
        ctx=ast.Load(),
    )


def _is_star_list(term: Any) -> bool:
    """Return True if term is a list containing at least one StarUnpack."""
    return isinstance(term, list) and any(isinstance(e, StarUnpack) for e in term)


def _parse_star_segments(lst: list) -> list[tuple]:
    """Parse a list with StarUnpack(s) into segments.

    Returns a list of ("fixed", [elem, ...]) or ("star", var) tuples.
    """
    segments: list[tuple] = []
    fixed_buf: list = []
    for elem in lst:
        if isinstance(elem, StarUnpack):
            if fixed_buf:
                segments.append(("fixed", fixed_buf))
                fixed_buf = []
            segments.append(("star", elem.value))
        else:
            fixed_buf.append(elem)
    if fixed_buf:
        segments.append(("fixed", fixed_buf))
    return segments


def _count_stars(segments: list[tuple]) -> int:
    return sum(1 for kind, _ in segments if kind == "star")


def _dotted_name_from_loadattr(node) -> str | None:
    """Extract a dotted name string from a LoadAttr chain.

    ``LoadAttr(object=LoadName("graphs"), attr="Path")`` → ``"graphs.Path"``
    ``LoadAttr(object=LoadAttr(..., "sub"), attr="Pred")`` → ``"mod.sub.Pred"``
    ``LoadName("foo")`` → ``"foo"``

    Returns None if the chain contains non-name nodes.
    """
    if isinstance(node, LoadName):
        return node.name
    if isinstance(node, LoadAttr):
        prefix = _dotted_name_from_loadattr(node.object)
        if prefix is not None:
            return f"{prefix}.{node.attr}"
    return None


# ── Term → AST expression ──────────────────────────────────────────────────────


#: Where the construction being lowered stands, for the error an UNDECLARED
#: functor raises there (``globals_env.UndeclaredFunctorError``):
#: ``("evaluable", "(is)/2")`` inside an arithmetic expression,
#: ``("procedure", "assertz/1")`` in the clause handed to assertz, ``None``
#: anywhere else.  Set by the lowering of those positions
#: (:func:`construction_context`), read by :func:`term_to_ast_expr`'s two
#: undeclared-functor emissions.  It changes only which ISO term the refusal
#: carries; every declared construction compiles exactly as before.
_CONSTRUCTION_CONTEXT: "ContextVar[tuple | None]" = ContextVar(
    "_CONSTRUCTION_CONTEXT", default=None)

#: The goals whose argument positions are EVALUABLE (ISO 8.6, 8.7), by
#: argument index.  The context is ``(is)/2`` for all of them: Scryer reports
#: an unknown evaluable in a comparison against ``(is)/2`` too.
_EVALUABLE_ARGS = {
    "is": (1,), "=:=": (0, 1), "=\\=": (0, 1),
    "<": (0, 1), ">": (0, 1), "=<": (0, 1), ">=": (0, 1),
}
#: The database builtins whose clause argument names a PROCEDURE.
_PROCEDURE_ARGS = {"assertz": "assertz/1", "asserta": "asserta/1",
                   "assert": "assert/1"}
#: The builtins whose clause argument is only MATCHED against stored
#: clauses: an undeclared functor there builds its cell, so the goal finds
#: no procedure and fails (ISO 8.9.3: retract of a non-existent procedure
#: fails) instead of refusing the construction.
_MATCH_ARGS = {"retract": "retract/1"}


@contextmanager
def construction_context(kind: "str | None", context: "str | None" = None):
    """Lower the terms built inside this block as standing in position
    *kind* (see ``_CONSTRUCTION_CONTEXT``)."""
    token = _CONSTRUCTION_CONTEXT.set(None if kind is None else (kind, context))
    try:
        yield
    finally:
        _CONSTRUCTION_CONTEXT.reset(token)


def call_arg_context(fname: str, index: int) -> "tuple | None":
    """The construction context of argument *index* of a call to *fname*:
    an evaluable position of an ISO arithmetic builtin, the clause of an
    assert, or None."""
    if index in _EVALUABLE_ARGS.get(fname, ()):
        return ("evaluable", "(is)/2")
    if index == 0 and fname in _PROCEDURE_ARGS:
        return ("procedure", _PROCEDURE_ARGS[fname])
    if index == 0 and fname in _MATCH_ARGS:
        return ("cell", _MATCH_ARGS[fname])
    return None


def term_to_ast_expr(
    term: Any, var_context: dict[int, str], *, eval_arith: bool = True
) -> ast.expr:
    """Convert a term value to a Python AST expression.

    The generated expression evaluates at runtime to the term.
    Vars already in var_context are referenced by name.  Vars not yet in
    var_context (body-only Vars) are introduced via walrus ``(_vN := Var())``.

    when *eval_arith* is True (the default), arithmetic term nodes
    (Add, Sub, …) are compiled to the exact-arithmetic helpers so they evaluate
    at runtime.  when False, they are kept as structural term constructors
    (e.g. ``Add(left=x, right=1)``).

    Supports: Var, Python scalars, list, cells, functor dataclasses.
    """
    raw = term
    term = deref(term)

    if type(term) is _MetaArg and term.module is not None:
        # A dotted ``lib.p(...)`` / ``lib.p`` in a qualifying meta position:
        # the qualified goal ``lib:p(...)`` (operator ruling 2026-09-25).  The
        # inner goal is spelled with the WRITTEN leaf name -- the name lib
        # answers to, as ``lib:p(...)`` would look it up there -- never with
        # a spelling resolved in the calling module.
        value = term.value
        if isinstance(value, Call) and not value.kwargs:
            leaf = _dotted_name_from_loadattr(value.func).rpartition(".")[2]
            inner = cell_literal_ast(sys.intern(leaf), [
                term_to_ast_expr(a, var_context, eval_arith=eval_arith)
                for a in value.args])
        elif isinstance(value, Call):
            # Keyword placement needs lib's signature: the term lowering
            # places it (ruling (a): the plain cell).
            inner = term_to_ast_expr(value, var_context, eval_arith=eval_arith)
        else:
            leaf = _dotted_name_from_loadattr(value).rpartition(".")[2]
            inner = ast.Constant(value=_mint_atom(leaf))
        return _call(_name("$meta_qualify_module"), _name("$meta_db"),
                     ast.Constant(value=term.module), inner)

    if type(term) is _MetaArg:
        # A ``-meta_predicate`` argument position (see
        # ``clausal.logic.meta_predicate``): qualified with the calling
        # module at run time.
        return _call(_name("$meta_qualify"), _name("$meta_db"),
                     term_to_ast_expr(term.value, var_context,
                                      eval_arith=eval_arith),
                     ast.Constant(value=term.spec))

    if is_var(term):
        vid = term._id
        if vid in var_context:
            return _name(var_context[vid])
        # Body-only Var: introduce via walrus assignment
        vname = _var_python_name(term)
        var_context[vid] = vname
        return ast.NamedExpr(
            target=ast.Name(id=vname, ctx=ast.Store()),
            value=_call(_name("$Var")),
        )

    if isinstance(term, LoadName):
        # Ruling S (2026-09-24) for CLAUSE SOURCE: a bare name bound to a
        # PREDICATE, in data position, is the plain atom of its name -- the
        # same literal the value arms below bake for an already-resolved
        # class or handle.  A runtime ``Name`` load would hand over the
        # binding itself (the class today, the mangled handle after the
        # flip).  The zero-arity case never gets here (the rewriter already
        # lowers a bare ``z`` to ``'z'``); a ``-hide`` DATA atom is not a
        # declared predicate, so it keeps its load and its mangled spelling.
        # A goal-taking builtin handed the atom resolves it by name in the
        # caller (``call_body.MetaCallGoal``, ``call/N``).
        namespace = lowering_globals()
        if namespace is not None and "." not in term.name:
            _pred_name = predicate_binding_name(
                namespace.get(term.name), db=_lowering_db())
            if _pred_name is not None:
                # The WRITTEN name, not the binding's own: under an
                # ``alias(p, q)`` import, ``q`` is bound to p's binding, and
                # the atom must be ``q`` -- which resolves through the import
                # in this namespace -- never ``p``, which here may name a
                # DIFFERENT local predicate (roborev, 2026-09-25; Scryer
                # passes ``q``).
                return ast.Constant(value=_mint_atom(term.name))
        return _name(term.name)

    # Bare (non-Call) LoadAttr in value position: a module-qualified atom used
    # as a VALUE, e.g. ``currency.euro`` on the RHS of a unify or as a call
    # argument.  Lower it to the equivalent Python attribute access so the
    # ``-import_module``'d module object (present in the compiled function's
    # globals) yields its exported atom at runtime.  Without this the term falls
    # through to the generic term-instance constructor below and is re-emitted as
    # a ``LoadAttr(...)`` reflection node, which never unifies with the atom.
    # Mirrors the qualified-call path (``Call`` + ``LoadAttr`` further down).
    if isinstance(term, LoadAttr):
        dotted = _dotted_name_from_loadattr(term)
        if dotted is not None:
            parts = dotted.split(".")
            expr: ast.expr = _name(parts[0])
            for attr in parts[1:]:
                expr = ast.Attribute(value=expr, attr=attr, ctx=ast.Load())
            return expr

    # Subscript read ``P[K]`` in value position (e.g. the RHS of ``V is P[K]``).
    # Lower to the ``$subscript`` runtime helper, which derefs both operands,
    # reads the DictTerm value, and throws a catchable error on a missing or
    # non-ground key.  See clausal/logic/runtime/dict_ops.py and
    # todo/dict-native-profile-api.md (item 1).
    if isinstance(term, LoadSubscript):
        return _call(
            _name("$subscript"),
            term_to_ast_expr(term.object, var_context, eval_arith=eval_arith),
            term_to_ast_expr(term.index, var_context, eval_arith=eval_arith),
        )

    term = literal_value(term)
    if term is None or isinstance(term, bool):
        return ast.Constant(value=term)

    # The Kleene ``Undefined`` builtin singleton: emit a bare ``Name`` reference
    # (like a zero-arity PredicateMeta atom below), since ``Undefined`` is an
    # injected builtin present in every compiled predicate's globals.  This
    # keeps its process-wide identity through query/clause compilation.
    if term is Undefined:
        return _name("Undefined")

    # A predicate's SELF-DENOTING atom stays PLAIN in both eras (operator
    # ruling 2026-09-24: "the default in Prolog is global, but be cognizant
    # of directive hide/1").  Post-flip a predicate's module binding is its
    # mangled handle (``module\x1fname``), a ``str`` -- so without this arm
    # the generic ``str`` arm below bakes the MANGLED spelling, where the
    # class arms baked ``term.__name__`` (deleted with the class, W4b-3
    # slice 7).  ``predicate_binding_name`` is
    # gated on ``is_declared_predicate_name``, NOT ``is_mangled``: a ``-hide`` DATA
    # atom is mangled too, and its mangled spelling IS its identity (every
    # reference in the owning module compiles to that same spelling), so it
    # must fall through and be baked verbatim.
    #
    # A mangled str whose owner module does NOT resolve (no loaded Clausal
    # module under its module half) also falls through VERBATIM -- it is not
    # refused.  Deliberate: from the spelling alone such a str cannot be told
    # apart from a -hide DATA atom, and an unresolvable -hide atom is a
    # legitimate runtime value (a module loaded under a sys.modules key other
    # than its -module name mints ``hide_owner\x1fhide_secret`` that
    # ``_resolve_mangled_owner`` answers None for; that atom round-trips into
    # queries today).  Raising here would break it.  The cost: a predicate
    # handle whose owner is not loaded keeps its mangled spelling, so the
    # answer depends on load state -- the same dependency every
    # ``is_declared_predicate_name`` caller has.  See
    # todo/done/self-denoting-predicate-atom-spelling-post-flip-mangled-or-plain-2026-09-24.md.
    # Only a MANGLED str can be a predicate handle (a class never reaches this
    # arm), so a plain string -- the common case -- pays one ``in`` test, not
    # a lowering-scope db lookup.
    if type(term) is str and _is_mangled(term):
        _pred_name = predicate_binding_name(term, db=_lowering_db())
        if _pred_name is not None:
            return ast.Constant(value=_mint_atom(_pred_name))

    if isinstance(term, (int, float, str, bytes, complex)):
        return ast.Constant(value=term)

    # datetime values: first-class value terms (immutable, hashable, unify by
    # value; ``Date/4`` produces them and ``DaysBetween``/``DateAdd`` consume
    # them). A DIRECT query arg never reaches here — ``_templatize_query_goal``
    # parameterizes it — but a NESTED occurrence (inside a list/compound arg)
    # is lowered structurally and needs a reconstruction. Emitted through
    # ``__import__`` so the generated code depends on no namespace entry.
    # Exact types only, and only tz-naive datetime/time: a subclass or an
    # arbitrary tzinfo carries state the base constructor cannot rebuild, so
    # those keep the honest fallthrough below. NOT arithmetic: ``==`` on a
    # date stays unification, never a CLP constraint.
    if isinstance(term, StarUnpack):
        return ast.Starred(
            value=term_to_ast_expr(term.value, var_context, eval_arith=eval_arith),
            ctx=ast.Load(),
        )

    if isinstance(term, TupleLiteral):
        _rec = lambda t: term_to_ast_expr(t, var_context, eval_arith=eval_arith)
        return ast.Tuple(
            elts=[_rec(e) for e in term.elements],
            ctx=ast.Load(),
        )

    if isinstance(term, tuple):
        # An already-materialized Python tuple (e.g. a structured
        # -constants RHS, which builds a real tuple directly rather than
        # the uninstantiated TupleLiteral node an ordinary clause body's
        # ``(a, b)`` literal produces — see the docstring on
        # EmbedTransformer._transform_constant_rhs). Same recursive
        # reconstruction as the TupleLiteral branch just above.
        _rec = lambda t: term_to_ast_expr(t, var_context, eval_arith=eval_arith)
        return ast.Tuple(
            elts=[_rec(e) for e in term],
            ctx=ast.Load(),
        )

    if isinstance(term, list):
        # If the list contains a StarUnpack, use _build_star_list/_build_multi_star_list
        # helper to safely handle unbound Vars at runtime.
        _rec = lambda t: term_to_ast_expr(t, var_context, eval_arith=eval_arith)
        # A -constants list value is frozen (_FrozenList — see
        # clausal.logic.constants._freeze). The RECONSTRUCTION a compiled
        # clause builds from it must be frozen too, not just the original:
        # under tabling/answer-caching, a reconstructed answer can be
        # shared across multiple consumers, where a plain mutable list
        # would let one consumer's mutation corrupt what every other
        # consumer of the same cached answer sees. A _FrozenList never
        # holds a StarUnpack (constants are always fully ground), so this
        # only needs to guard the plain-list return path below.
        is_frozen_list = isinstance(term, _FrozenList)
        star_count = sum(1 for e in term if isinstance(e, StarUnpack))
        if star_count == 1:
            # Single-star: use _build_star_list(before, star, after)
            star_idx = next(i for i, e in enumerate(term) if isinstance(e, StarUnpack))
            before = term[:star_idx]
            star_val = term[star_idx].value
            after = term[star_idx + 1:]
            return ast.Call(
                func=_name("$build_star_list"),
                args=[
                    ast.List(
                        elts=[_rec(e) for e in before],
                        ctx=ast.Load(),
                    ),
                    _rec(star_val),
                    ast.List(
                        elts=[_rec(e) for e in after],
                        ctx=ast.Load(),
                    ),
                ],
                keywords=[],
            )
        elif star_count > 1:
            # Multi-star: build segments list and call _build_multi_star_list
            segments = _parse_star_segments(term)
            seg_elts = []
            for kind, val in segments:
                if kind == "star":
                    seg_elts.append(ast.Tuple(
                        elts=[ast.Constant(value="star"), _rec(val)],
                        ctx=ast.Load(),
                    ))
                else:
                    seg_elts.append(ast.Tuple(
                        elts=[
                            ast.Constant(value="fixed"),
                            ast.List(elts=[_rec(e) for e in val], ctx=ast.Load()),
                        ],
                        ctx=ast.Load(),
                    ))
            return ast.Call(
                func=_name("$build_multi_star_list"),
                args=[ast.List(elts=seg_elts, ctx=ast.Load())],
                keywords=[],
            )
        list_ast_ = ast.List(
            elts=[_rec(e) for e in term],
            ctx=ast.Load(),
        )
        if is_frozen_list:
            return _call(_name("$FrozenList"), list_ast_)
        return list_ast_

    if isinstance(term, dict):
        dict_ast_ = ast.Dict(
            keys=[term_to_ast_expr(k, var_context, eval_arith=eval_arith) for k in term.keys()],
            values=[term_to_ast_expr(v, var_context, eval_arith=eval_arith) for v in term.values()],
        )
        # An already-materialized raw dict (e.g. a ++()-escape-built
        # -constants value that never went through DictTerm) — frozen the
        # same way a list is; see the _FrozenList branch's comment above.
        if isinstance(term, _FrozenDict):
            return _call(_name("$FrozenDict"), dict_ast_)
        return dict_ast_


    if isinstance(term, DictTerm):
        # A logic-variable key ({K: V}) must be dereferenced at construction
        # time, exactly as in the DictLiteral lowering below: emitted bare, the
        # frame var keys the rebuilt dict as the Var object and every later
        # get(OUT, <value>, _) misses silently.  $dict_key derefs (and raises a
        # catchable instantiation_error on a never-bound key).
        #
        # Atom keys/values need no special handling here: an atom is a
        # global-by-spelling interned str (§1b/R2), so the recursive call
        # below emits it as a plain ``ast.Constant`` — never a name looked up
        # in the generated code's namespace — and it cannot be re-resolved
        # onto a same-named binding there.
        def _dictterm_key(k):
            expr = term_to_ast_expr(k, var_context, eval_arith=eval_arith)
            return _call(_name("$dict_key"), expr) if is_var(k) else expr
        dict_arg = ast.Dict(
            keys=[_dictterm_key(k) for k in term.keys()],
            values=[term_to_ast_expr(v, var_context, eval_arith=eval_arith) for v in term.values()],
        )
        # A -constants DictTerm value has a frozen backing store (see
        # clausal.logic.constants._freeze's DictTerm branch). The
        # RECONSTRUCTION a compiled clause builds each time it runs must be
        # frozen too — see the _FrozenList branch's comment above for why
        # (tabling/answer-caching can share a reconstructed answer across
        # consumers). Plain ``DictTerm(...)`` can't produce that directly —
        # its constructor takes a defensive ``dict(data)`` copy — so this
        # routes through ``$FrozenDictTerm`` (clausal.logic.constants.
        # _freeze_dict_term), which patches ``._data`` after construction.
        if isinstance(term.data, _FrozenDict):
            return _call(_name("$FrozenDictTerm"), dict_arg)
        return _call(_name("$DictTerm"), dict_arg)

    if isinstance(term, SetTerm):
        # Recurse per element (mirrors the SetLiteral branch just below):
        # a bare ``ast.Constant(value=e)`` is only valid when every element
        # is a Python-literal-embeddable scalar. A SetTerm built from a
        # structured -constants RHS (``_FLAGS_ = {red, green}``) can hold
        # atom instances (PredicateMeta 0-arity classes) or other term
        # types, which ``ast.Constant`` rejects at compile() time — those
        # need the same Name-reference/constructor-call treatment any other
        # term position gets.
        _rec = lambda t: term_to_ast_expr(t, var_context, eval_arith=eval_arith)
        return _call(
            _name("$SetTerm"),
            ast.List(
                elts=[_rec(e) for e in sorted(term.elements, key=repr)],
                ctx=ast.Load(),
            ),
        )

    if isinstance(term, (set, frozenset)):
        # A raw Python set (e.g. a ++()-escape-built -constants value —
        # a SOURCE-level {...} set literal always lowers to SetTerm above,
        # never a raw set). ``frozenset`` values are returned unwrapped by
        # ``_freeze`` (already immutable/hashable), so they reconstruct as
        # a bare ``frozenset(...)`` call; a mutable-set-derived value is a
        # ``_FrozenSet`` (frozen — see the _FrozenList branch's comment
        # above for why the RECONSTRUCTION must be frozen too) and
        # reconstructs via ``$FrozenSet``. Sorted by repr for deterministic
        # codegen, same as the SetTerm branch above.
        _rec = lambda t: term_to_ast_expr(t, var_context, eval_arith=eval_arith)
        elts = [_rec(e) for e in sorted(term, key=repr)]
        ctor = "$FrozenSet" if isinstance(term, _FrozenSet) else "frozenset"
        return _call(_name(ctor), ast.List(elts=elts, ctx=ast.Load()))

    # SetLiteral (AST node from visit_Set): emit SetTerm([elem, ...]) constructor
    if isinstance(term, _SetLiteral_t):
        return _call(
            _name("$SetTerm"),
            ast.List(
                elts=[term_to_ast_expr(e, var_context, eval_arith=eval_arith) for e in term.elements],
                ctx=ast.Load(),
            ),
        )

    if isinstance(term, DictLiteral):
        _rec = lambda t: term_to_ast_expr(t, var_context, eval_arith=eval_arith)
        # A computed key that is a logic VARIABLE must be dereferenced at
        # runtime: a key bound in the same clause frame as the literal
        # (``{K: V}`` / ``{**OLD, K: V}``) otherwise reaches dict construction
        # as the Var object, keying the dict by the variable rather than its
        # value.  $dict_key derefs (and errors on an unbound key).  Literal
        # keys are already ground, so they are emitted unwrapped.
        _key = lambda k: (
            _call(_name("$dict_key"), _rec(k)) if is_var(k) else _rec(k)
        )
        has_splat = any(k is None for k in term.keys)
        if not has_splat:
            # No splats: plain dict used as DictTerm constructor argument.
            return ast.Dict(
                keys=[_key(k) for k in term.keys],
                values=[_rec(v) for v in term.values],
            )
        # Splat dict sugar: {**OLD, k: v} → DictTerm({**deref(OLD).data, k: v})
        # Splat values are DictTerms; access .data to get the underlying dict.
        py_keys = []
        py_vals = []
        for k, v in zip(term.keys, term.values):
            if k is None:
                py_keys.append(None)
                # Splat source: {**OLD, ...} → {**$splat_data(OLD), ...}.
                # $splat_data derefs and validates OLD is a dict, raising a
                # catchable typed error on an unbound/non-dict source rather
                # than a raw AttributeError on ``.data``.
                py_vals.append(_call(_name("$splat_data"), _rec(v)))
            else:
                py_keys.append(_key(k))
                py_vals.append(_rec(v))
        return _call(
            _name("$DictTerm"),
            ast.Dict(keys=py_keys, values=py_vals),
        )

    if isinstance(term, SetLiteral):
        _rec = lambda t: term_to_ast_expr(t, var_context, eval_arith=eval_arith)
        return ast.Set(elts=[_rec(e) for e in term.elements])


    # Arithmetic term nodes: when eval_arith is set, generate native Python
    # operators so they evaluate at runtime.  when False (e.g. predicate call
    # arguments), keep them as structural term constructors.
    if eval_arith and isinstance(term, (Add, Sub, Mult, Div, FloorDiv, Mod, Pow, Negate)):
        # ``$present``: whatever the tree produced, an integral Fraction
        # (e.g. (1/2) + (1/2)) reaches unify as an int.
        return _call(_name("$present"), arith_to_ast_expr(term, var_context))

    # Call nodes with LoadName/LoadAttr func: compile as direct function call so
    # that e.g. phrase(count_leaves(T_), ...) constructs a count_leaves instance,
    # not a Call AST node.  LoadAttr handles qualified calls like mod.Pred(X_).
    if isinstance(term, Call) and isinstance(term.func, (LoadName, LoadAttr)):
        if isinstance(term.func, LoadName):
            fname = term.func.name
        else:
            fname = _dotted_name_from_loadattr(term.func)
        # Only the OUTERMOST construction of an assert's clause is the
        # procedure being written (kind "procedure": the database builtin
        # decides, knowing the calling module's assert_creates_dynamic flag).
        # A functor nested inside it is data, refused at construction as
        # before (kind "procedure_arg"), whatever the flag says.
        _outer = _CONSTRUCTION_CONTEXT.get()
        _inner = (("procedure_arg", _outer[1])
                  if _outer is not None and _outer[0] == "procedure" else _outer)
        _tok = _CONSTRUCTION_CONTEXT.set(_inner)
        try:
            arg_exprs = [
                term_to_ast_expr(a, var_context, eval_arith=eval_arith)
                for a in term.args
            ]
            kw_exprs = [
                ast.keyword(
                    arg=kw.name,
                    value=term_to_ast_expr(kw.value, var_context, eval_arith=eval_arith),
                )
                for kw in (term.kwargs or [])
            ]
        finally:
            _CONSTRUCTION_CONTEXT.reset(_tok)
        # P3-2 Task 2 (THE FLIP): a construction of a DATA functor becomes a
        # cell literal, unconditionally — cells are the compiled
        # representation of compound data, not an opt-in.  This is the branch
        # that matters for ``.clausal`` source: a compound written in a
        # clause (``cons(N, T)``) reaches the compiler as
        # ``Call(LoadName('cons'), …)``, not as a live instance.  A PREDICATE
        # reference resolves to None here and keeps class emission, because
        # calling it is a goal (P3-3 does that half).
        #
        # P3-2 Task 1 (signature-resolved construction): positional args fill
        # leading declared slots,
        # keyword args fill their named slots, and a slot neither reaches
        # is refused (operator ruling 2026-09-25: no padding; it used to
        # backfill with a fresh ``Var()``) -- the same rule
        # ``PredicateMeta.__call__`` applies (see ``_place_signature_slots``).
        # Ruling C: a short keyword-free construction is re-asked at the
        # WRITTEN arity (a predicate name answers that arity's slots; a data
        # functor its declaration) -- see construction_signature_for_name.
        _sig = construction_signature_for_name(
            fname, n_positional=len(arg_exprs), has_keywords=bool(kw_exprs))
        _namespace = lowering_globals()
        _owa = _implicit_functors_active(_namespace)
        if _sig is not None:
            _functor, _fields = _sig
            if _owa and not kw_exprs:
                # P3-2 Task 6 (R7): under OWA a declared signature is
                # advisory for keyword-free construction -- build the cell
                # at the WRITTEN arity, whatever it is, rather than placing
                # positional args against the declared field list (which
                # would either over-arity-error or pad a short call with
                # backfilled Vars the caller never asked for). Keyword
                # construction is unaffected -- it still places by field
                # name below, flag or no flag.
                return cell_literal_ast(_functor, arg_exprs)
            _placed = _place_signature_slots(
                _fields,
                arg_exprs,
                [(kw.arg, kw.value) for kw in kw_exprs],
                functor=_functor,
                missing=lambda: _call(_name("$Var")),
            )
            return cell_literal_ast(_functor, _placed)
        if _owa and "." not in fname:
            # No registry entry at all, and *fname* is a PLAIN (dot-free)
            # name -- OWA opens the flagged module's OWN functor vocabulary,
            # not name resolution across a module boundary. A DOTTED
            # reference that reaches here (``other.Wrap``) has already
            # failed to resolve to a signature via
            # ``cell_signature_for_name`` -- that is a missing import or a
            # typo, not an OWA-advisory functor, and must stay a loud
            # failure (the ``ast.Call`` fallback below, same as without the
            # flag) rather than silently mint a cell tagged with the WHOLE
            # dotted string, which violates R5's base-name-spelling
            # invariant and can never unify with anything (fix round 1,
            # Important finding — reviewer-confirmed live bug: a dotted
            # OWA-unknown built ``('other.Wrap', ...)`` instead of either
            # resolving or failing loudly).
            #
            # OWA still defers to a PREDICATE binding -- a goal is not
            # data, even in a flagged module -- so the binding question is
            # asked the same way ``cell_signature_for_name`` asks it, just
            # without requiring a signature to exist.
            _resolved = _resolve_functor_binding(fname, _namespace) if _namespace else None
            _binding = _resolved[0] if _resolved is not None else None
            if not is_declared_predicate_name(
                    _binding,
                    db=namespace_db(_namespace)):
                if kw_exprs:
                    raise SyntaxError(
                        f"functor {fname!r} has no declared signature: "
                        f"-implicit_functors makes keyword-free construction "
                        f"of any functor/arity advisory, but keyword "
                        f"placement for {fname!r} still requires a declared "
                        f"signature to place its named slots against"
                    )
                return cell_literal_ast(sys.intern(fname), arg_exprs)
        _goal_functor = None if kw_exprs else _goal_cell_functor(
            fname, len(arg_exprs), _namespace)
        if _goal_functor is not None:
            return cell_literal_ast(sys.intern(_goal_functor), arg_exprs)
        # An ATOM is data and cannot build a term, so a name bound to one is
        # an UNDECLARED functor here, exactly as an unbound name is -- never
        # a call of the str.  It is bound without this module saying so more
        # often than not: every module dict is pre-seeded with the
        # process-wide atom pool (GLOBAL_ATOMS_DEFAULT rule 1.4), so an atom
        # ANOTHER module declared sits under the name, and ``zz(1)`` died on
        # CPython's ``TypeError: 'str' object is not callable`` where the
        # same module loaded alone says "not in scope as a term class".
        # (-implicit_functors returned the cell above; a DECLARED data
        # functor binds its atom too, but answered a signature above.)
        _where = _CONSTRUCTION_CONTEXT.get()
        if _namespace is not None:
            _resolved = _resolve_functor_binding(fname, _namespace)
            if _resolved is not None and _term_is_atom(_resolved[0]):
                if _where is not None:
                    return ast.Call(
                        func=_name("$undeclared_functor_in"),
                        args=[ast.Constant(value=_where[0]),
                              ast.Constant(value=_where[1]),
                              ast.Constant(value=fname),
                              ast.Constant(value=len(arg_exprs)), *arg_exprs],
                        keywords=kw_exprs,
                    )
                return ast.Call(
                    func=_name("$undeclared_functor"),
                    args=[ast.Constant(value=fname),
                          ast.Constant(value=len(arg_exprs)), *arg_exprs],
                    keywords=kw_exprs,
                )
        func = _name(fname)
        if _where is not None and not kw_exprs:
            # The name is looked up at run time as before; ``$constructor_in``
            # only swaps the unbound-name stand-in for the refusal that fits
            # this position.
            func = _call(_name("$constructor_in"), func,
                         ast.Constant(value=_where[0]),
                         ast.Constant(value=_where[1]),
                         ast.Constant(value=fname),
                         ast.Constant(value=len(arg_exprs)))
        return ast.Call(
            func=func,
            args=arg_exprs,
            keywords=kw_exprs,
        )

    # A builtin's OBJECT in term position (``clausal.succ`` handed to
    # ``maplist`` from Python) is the ATOM of its name -- what its
    # ``PredicateMeta`` class lowered to until W4b-3 slice 3 (through the
    # class arms slice 7 deleted).  Slice 3 made it a
    # ``BuiltinTerm`` and lost the arm: such a goal raised
    # ``NotImplementedError: unsupported term type BuiltinTerm``.  Lazy
    # import: the builtins package imports the compiler.
    if type(term).__name__ == "BuiltinTerm":
        from clausal.logic.builtins._registry import BuiltinTerm  # noqa: PLC0415
        if type(term) is BuiltinTerm:
            return ast.Constant(value=_mint_atom(term._functor))

    if is_term_instance(term):
        cls = type(term)
        # ``$``-twin for a class the runtime table binds (a simple_ast node
        # such as ``Add``, or another injected class), bare for a user's own
        # predicate class -- see ``generated_names.dollar_ref``.
        cls_name = dollar_ref(cls)
        fields = term_field_names(term)
        # A live term INSTANCE ALWAYS keeps class emission (P3-2 Task 2,
        # controller ruling on the gate asymmetry).  Cell-vs-class is decided
        # on the BINDING (R6): a declared data functor binds its interned
        # spelling, so post-flip no ``.clausal`` module can produce an
        # instance of one at all.  Every instance that still reaches here was
        # minted in PYTHON and belongs to the class world -- since Task 6
        # emptied the bridge that means an out-of-tree producer, the
        # reflection vocabulary and ``clpb``'s ``BoolEq`` having become cells
        # -- and lowering such an instance to a cell
        # here would emit a shape the NAME side of the same functor compiles a
        # class pattern for -- "builds one shape, matches another", the clause
        # that can never fire.  Answering uniformly at the class instead of
        # per site also retires the ``_position``/``position`` exclusion that
        # the old instance gate needed.
        #
        # (``unnameable_instance_cell_functor``, the one exception -- a live
        # ``PredicateMeta`` INSTANCE whose class this compile cannot name --
        # was deleted in W4b-3 slice 2: W4a made such an instance impossible,
        # and for every other instance it answered None.)
        # The Phase-0 fast-constructor emission gate (positional
        # ``cls_name._clausal_new(...)``) that used to precede this keyword
        # call was retired in W4b, 2026-09-23: the emitter can no longer
        # produce a class carrying ``_clausal_new`` (see the note in
        # solve.py's _deref_walk_py), so the gate never matched and the
        # keyword emission below was the only path actually taken.
        return ast.Call(
            func=_name(cls_name),
            args=[],
            keywords=[
                ast.keyword(
                    arg=name,
                    value=term_to_ast_expr(
                        getattr(term, name), var_context, eval_arith=eval_arith,
                    ),
                )
                for name in fields
                if name not in ("_position", "position")
            ],
        )

    # PyThunk: deferred Python expression via lambda wrapper.
    # Used for f-strings in .clausal files and ++() Python escapes.
    # The thunk stores a callable (lambda) and a list of Var objects.
    # The compiler emits:
    #     thunk.fn($unwrap_atom(local0), $unwrap_atom(local1), ...)
    #
    # $unwrap_atom — not $deref, and NOT the deep $to_python the py.* wrappers
    # get — is spec 2026-09-06-atoms-as-cells-strings §9.1's stated fallback,
    # applied 2026-09-07 on Task 14's perf gate (bench_thunk_atoms measured
    # B/A = 1.074 against the 3% bar with the deep walk here; the top-level
    # unwrap recovered 8.2% and landed within 0.9% of this arm's pre-flip
    # $deref).  It derefs and unwraps a TOP-LEVEL atom to its spelling, so it
    # still fixes what the flip broke — a str method called on what used to be
    # a str and is now the 1-tuple ("hello",) — while a container argument
    # crosses raw, exactly as the old single-level $deref left it.  So it is
    # still a widening of $deref, just a one-level one.
    if isinstance(term, PyThunk):
        # Reference to the thunk's .fn stored in compiled function globals.
        # Use a unique name to avoid collisions.
        thunk_name = f"_pyt_{id(term)}"
        arg_exprs = []
        for var_obj in term.var_objects:
            vid = var_obj._id
            if vid in var_context:
                arg_exprs.append(_call(_name("$unwrap_atom"), _name(var_context[vid])))
            else:
                # Body-only var — allocate and convert
                vname = _var_python_name(var_obj)
                var_context[vid] = vname
                arg_exprs.append(_call(
                    _name("$unwrap_atom"),
                    ast.NamedExpr(
                        target=ast.Name(id=vname, ctx=ast.Store()),
                        value=_call(_name("$Var")),
                    ),
                ))
        # STAGE 1 (spec 2026-09-18): the thunk's RESULT crosses in through
        # ``$text_in`` -- a str it hands back is text, and text is the chars
        # carrier; one level, the mirror of ``$unwrap_atom`` on the way out.
        return _call(_name("$text_in"), ast.Call(
            func=_name(thunk_name),
            args=arg_exprs,
            keywords=[],
        ))

    if isinstance(term, Lambda):
        raise NotImplementedError(
            "Lambdas are currently only supported as predicate call arguments"
        )

    # A live BOUND Var whose value has no literal lowering (e.g. a
    # ``datetime.date`` produced by an earlier goal): reference the Var itself
    # so runtime deref yields the value.  ``isinstance``, not ``is_var`` —
    # is_var() derefs and is False for bound Vars.  Only possible when the Var
    # was registered up front (the query compiler collects bound Vars with
    # ``_collect_vars(goal, include_bound=True)``); an unregistered one keeps
    # the honest NotImplementedError below rather than fabricating a fresh
    # (unbound!) Var, which would silently change goal semantics.
    if isinstance(raw, Var) and raw._id in var_context:
        return _name(var_context[raw._id])

    # `...` REIFIES (render inverts reify, so reflection must keep modelling
    # it — TestPlainConstants pins the round-trip) but has no evaluation rule
    # in a goal; without this branch it fell through to the internal
    # NotImplementedError below, with no source line.  The clause-position
    # scope stack the compiler maintains (Slice G5) locates it at the owning
    # clause.
    if term is Ellipsis:
        from ._ast_helpers import _current_position
        msg = ("`...` (Ellipsis) is not supported in a clause body: it is "
               "inert term structure with no evaluation rule. Remove it.")
        pos = _current_position()
        if isinstance(pos, tuple) and pos and isinstance(pos[0], int):
            raise SyntaxError(msg, (None, pos[0], None, None))
        raise SyntaxError(msg)

    # A value with a CANONICAL TERM ENCODING gets told what to write; a value
    # without one gets the plain refusal. That is the distinction the
    # 2026-09-15 ruling turns on -- a date can be a term, an opaque object
    # cannot -- and it is why this is a suggestion rather than a coercion.
    #
    # The shapes come from ``modules.py.datetime``'s own emit table so there is
    # ONE definition of the encoding; a second spelling here would drift.
    suggestion = _term_form_suggestion(term)
    if suggestion is not None:
        raise NotImplementedError(
            f"term_to_ast_expr: a Python {type(term).__name__} is not a term.\n"
            f"  Write the term instead:  {suggestion}\n"
            f"  in .clausal source:      {_source_form(suggestion)}\n"
            f"  (got {term!r})"
        )
    raise NotImplementedError(
        f"term_to_ast_expr: unsupported term type {type(term).__name__}: {term!r}"
    )


def _term_form_suggestion(term: Any) -> "str | None":
    """The term a Python datetime value should have been written as, or None.

    None for everything else, deliberately: only a value the language HAS an
    encoding for can be suggested, and suggesting one for an opaque object
    would promise a migration that does not exist.
    """
    try:
        from clausal.modules.py.datetime import _dt_to_term  # noqa: PLC0415
    except Exception:  # noqa: BLE001 -- a diagnostic must not upstage the fault
        return None
    form = _dt_to_term(term)
    return repr(form) if type(form) is tuple else None


def _source_form(term_repr: str) -> str:
    """``('date', 2023, 6, 1)`` -> ``date(2023, 6, 1)``, the .clausal spelling."""
    inner = term_repr.strip("()").split(", ", 1)
    if len(inner) != 2:
        return term_repr
    return f"{inner[0].strip(chr(39))}({inner[1]})"


# ── Arithmetic term → AST expression ──────────────────────────────────────────

def exact_div(l, r):
    """``$exact_div``: a literal int/int Div in compiled arithmetic -- which
    is EVALUATION, so Python's true division (ruling Q15, 2026-09-28:
    ``7 / 2`` is 3.5, ``6 / 2`` is 3.0; it was the exact rational).  The
    name is kept for already-compiled code.  A zero divisor raises
    ``evaluation_error(zero_divisor)`` (Q4)."""
    return _python_truediv(l, r)


# The ``$``-runtime names ``arith_to_ast_expr`` can emit, bound to their
# implementations. The ONE place this set lives: the compiler's base
# namespaces (predicate.py) and the seam's value arithmetic (seam.py) both
# spread it in, so a new name added here reaches every evaluator of the
# emitted code. ``$present`` IS ``clausal.logic.variables.present_number``.
ARITH_RUNTIME_NAMES: dict = {
    "$exact_div": exact_div,
    "$present": present_number,
    # Step 2 of the rdiv/decimal design (2026-09-17): the four exact
    # operators, ONE spelling shared with the interpreted evaluator, so the
    # compiled and interpreted paths cannot disagree (they did: runtime
    # ``7 / 2`` was a float here and ``Fraction(7, 2)`` there).
    "$add": _exact_add,
    "$sub": _exact_sub,
    "$mul": _exact_mul,
    "$div": _python_truediv,        # bare / in evaluation: Python (Q15)
    # The bare ``//``, ``%``, ``**``: Python's operators (operator rulings
    # 2026-09-28: a bare operator in today's source syntax keeps Python's
    # meaning), with a zero divisor raised as evaluation_error(zero_divisor)
    # rather than a raw ZeroDivisionError (Q4).
    "$floordiv": _python_floordiv,
    "$mod": _python_mod,
    "$pow": _python_pow,
    # Ruling R9 (2026-09-27): an operand that may be a TERM at runtime --
    # ``eval_``'s whole operand when it is a variable or a literal term, or an
    # operand of the native ``//``, ``%``, ``**``, unary ``-`` -- is evaluated
    # through the one evaluable table; an atom or a non-evaluable compound
    # raises type_error(evaluable, F/N).
    "$eval": _evaluate,
    "$eval_py": _evaluate_python_result,
    # the inline int test on a native operator's variable operand
    # (``_native_operand``): builtins under names a module cannot shadow
    "$type": type,
    "$int": int,
}
_EXACT_BINOP_NAMES = ((Add, "$add"), (Sub, "$sub"), (Mult, "$mul"), (Div, "$div"))
_NATIVE_OPS = {FloorDiv: "$floordiv", Mod: "$mod", Pow: "$pow"}


def _native_operand(term: Any, var_context: dict[int, str]) -> ast.expr:
    """An operand of a native ``//``/``%``/``**``/unary ``-``: as compiled, or
    wrapped in ``$eval`` when it may be a term at runtime.  A variable goes to
    ``$eval`` directly (it dereferences), one call as ``$deref`` was."""
    t = deref(term)
    if is_var(t):
        # ``(v if type(v := $deref(V)) is int else $eval(v))``: an int -- the
        # overwhelmingly common operand -- costs the one C ``$deref`` call it
        # always did; anything else goes to the evaluator.  ``$arith_tmp`` is
        # consumed by its own conditional before any other operand assigns it.
        var = _name(var_context.get(t._id, _var_python_name(t)))
        tmp_store = ast.Name(id="$arith_tmp", ctx=ast.Store())
        return ast.IfExp(
            test=ast.Compare(
                left=_call(_name("$type"), ast.NamedExpr(
                    target=tmp_store, value=_call(_name("$deref"), var))),
                ops=[ast.Is()], comparators=[_name("$int")]),
            body=_name("$arith_tmp"),
            orelse=_call(_name("$eval"), _name("$arith_tmp")),
        )
    expr = arith_to_ast_expr(term, var_context)
    wrapper = runtime_eval_wrapper(term)
    return expr if wrapper is None else _call(_name(wrapper), expr)


def runtime_eval_wrapper(term: Any) -> "str | None":
    """How an arithmetic operand's compiled value is checked at runtime --
    the ONE answer, used for ``eval_``'s whole operand and for an operand of
    a native ``//``/``%``/``**``/unary ``-`` (ruling R9):

    * ``None`` -- it can only be a Python value: a number literal, an
      arithmetic sub-tree (whose helpers evaluate any term operand), or a
      ``++`` escape, which keeps Python's operators (``++("%d") % 5``);
    * ``"$eval_py"`` -- a QUALIFIED call (``math.sqrt(X)``, ``os.getcwd()``,
      but also a qualified term constructor ``utils.double(3)``): a str
      result is Python's (it formats, it binds), a term result is evaluated
      or refused like any other;
    * ``"$eval"`` -- a variable, whatever it will hold, or a literal term
      such as a bare-name ``foo(1)``.  (A bare-name Python builtin is not
      callable there: ``eval_(str(5), X)`` is a NameError, "Predicate
      'str/1' is not in scope as a term class".)
    """
    term = deref(term)
    if is_var(term):
        return "$eval"
    if isinstance(term, (Add, Sub, Mult, Div, FloorDiv, Mod, Pow, Negate, PyThunk)):
        return None
    if isinstance(term, Call) and isinstance(term.func, LoadAttr):
        return "$eval_py"
    term = literal_value(term)
    if isinstance(term, (int, float, Fraction)) and not isinstance(term, bool):
        return None
    return "$eval"


def arith_to_ast_expr(term: Any, var_context: dict[int, str]) -> ast.expr:
    """Convert an arithmetic term to a Python arithmetic AST expression.

    Generates code that evaluates the expression to a Python number at runtime.
    Vars are dereferenced.  ``+``, ``-``, ``*``, ``/`` become calls to the
    exact helpers (``$add`` & co.); ``//``, ``%``, ``**`` and unary ``-`` stay
    native Python operators, with an operand that may be a term at runtime
    evaluated first through ``$eval`` (ruling R9).
    """
    term = deref(term)

    if is_var(term):
        vid = term._id
        vname = var_context.get(vid, _var_python_name(term))
        return _call(_name("$deref"), _name(vname))

    term = literal_value(term)
    if isinstance(term, (int, float, Fraction)) and not isinstance(term, bool):
        return ast.Constant(value=term)

    # int / int literal: ``$exact_div``, Python's true division (Q15).
    if isinstance(term, Div):
        left_t = deref(term.left)
        right_t = deref(term.right)
        if (isinstance(left_t, int) and not isinstance(left_t, bool)
                and isinstance(right_t, int) and not isinstance(right_t, bool)):
            return ast.Call(
                func=_name("$exact_div"),
                args=[ast.Constant(value=left_t), ast.Constant(value=right_t)],
                keywords=[],
            )

    # ``//``, ``%``, ``**`` and unary ``-`` stay native Python operators; an
    # operand that may be a TERM at runtime (a variable, a literal compound)
    # is evaluated first through the one evaluable table (``$eval``, ruling
    # R9) -- it used to meet Python's tuple/dataclass operators and raise a
    # raw TypeError.  A Python-value operand (a ``++`` escape, a qualified
    # call) is left as it is, so ``++("%d items") % N`` still formats.
    if isinstance(term, Negate):
        return ast.UnaryOp(op=ast.USub(),
                           operand=_native_operand(term.operand, var_context))
    native = _NATIVE_OPS.get(type(term))
    if native is not None:
        return _call(_name(native), _native_operand(term.left, var_context),
                     _native_operand(term.right, var_context))

    # ``+``, ``-``, ``*``, ``/`` go through their exact helper (a call, ~30 ns,
    # measured): exactness, Decimal scale and term-operand evaluation live there.
    for cls, runtime_name in _EXACT_BINOP_NAMES:
        if isinstance(term, cls):
            return ast.Call(
                func=_name(runtime_name),
                args=[arith_to_ast_expr(term.left, var_context),
                      arith_to_ast_expr(term.right, var_context)],
                keywords=[],
            )

    # Fallback: treat as a plain term (e.g. a Var holding a number at runtime)
    # -- built in an EVALUABLE position, so an undeclared functor here is
    # ``type_error(evaluable, F/N)`` (ISO), not the plain undeclared-functor
    # refusal.
    with construction_context("evaluable", "(is)/2"):
        return term_to_ast_expr(term, var_context)
