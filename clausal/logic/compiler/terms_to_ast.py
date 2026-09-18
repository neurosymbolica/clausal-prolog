"""Term → AST expression lowering.

Converts a compile-time term value (Var, scalar, list, Compound,
functor-dataclass, KWTerm, DictTerm, SetTerm, SetLiteral, DictLiteral,
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
from fractions import Fraction

from clausal.logic.exact_arith import (
    exact_add as _exact_add, exact_sub as _exact_sub,
    exact_mul as _exact_mul, exact_div as _exact_div,
)
from typing import Any

from clausal.logic.variables import Var, is_var, deref, present_number
from clausal.terms import (
    Compound,
    Add, Sub, Mult, Div, FloorDiv, Mod, Pow,
    Negate,
    Call, LoadName, LoadAttr, LoadSubscript,
    DictTerm, SetTerm, KWTerm, PyThunk,
    Undefined,
)
from clausal.pythonic_ast.nodes import (
    StarUnpack, TupleLiteral, DictLiteral, SetLiteral,
    Lambda, literal_value,
    SetLiteral as _SetLiteral_t,
)
from clausal.logic.predicate import (
    PredicateMeta, is_zero_field_class, is_term_instance,
    term_field_names, term_field_names_of_class,
)
from clausal.logic.atoms import (
    is_atom as _term_is_atom,
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
    if isinstance(term, (list, dict, Compound, DictTerm, SetTerm, KWTerm,
                         StarUnpack, Call, LoadName, LoadAttr,
                         TupleLiteral, DictLiteral, SetLiteral)):
        return False
    if is_term_instance(term):
        return False
    if isinstance(term, type) and isinstance(term, PredicateMeta):
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
# ``ast.Constant`` unconditionally (below, and in the
# ``is_zero_field_class(term)`` branch further down) and is never looked up
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
# -- so a gate that inspected ``_fields``/``_clauses``/``_dynamic_arities``/
# ``position`` had no callers left.)


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
    name: str, resolve_globals: "dict | None" = None
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
      (``clausal.reflection``'s ``Goal``/``Clause``, ``clpb``'s ``BoolEq``)
      on class construction: its Python producers build instances at
      runtime, and a cell-compiled clause could never match one;
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
    """
    namespace = resolve_globals if resolve_globals is not None else lowering_globals()
    if namespace is None:
        return None
    resolved = _resolve_functor_binding(name, namespace)
    if resolved is None:
        return None
    binding, leaf, leaf_namespace = resolved
    if isinstance(binding, PredicateMeta):
        if binding.__dict__.get("_clausal_instances"):
            return None            # P2 bridge: this class still builds instances (its consumers read attributes)
        # P2 Task 3: a PREDICATE functor in term position compiles to the cell
        # too; its class only ever built instances, and __call__ builds cells
        # now, so the class-call path would only cost a runtime construction.
        cls_fields = term_field_names_of_class(binding)
        if cls_fields is None:
            return None
        return _functor_spelling(binding, leaf), tuple(cls_fields)
    fields = functor_signature_for(leaf, leaf_namespace)
    if fields is None:
        return None
    return _functor_spelling(binding, leaf), fields


def _functor_spelling(binding: Any, leaf: str) -> str:
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
    """
    if isinstance(binding, type):
        return binding.__name__
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

    Mirrors ``clausal.logic.predicate._term_arity_error``'s wording (functor,
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

    Mirrors ``clausal.logic.predicate._term_construction_error``'s wording
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
    if len(positional) > n_fields:
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


def unnameable_instance_cell_functor(term: Any) -> "str | None":
    """A live INSTANCE whose class cannot be named here → its cell functor.

    P3-2 Task 2.  A live ``PredicateMeta`` instance normally keeps CLASS
    emission (the controller's ruling on the gate asymmetry: cell-vs-class is
    decided on the BINDING, and an instance's producer is class-world).  That
    rests on a premise with one hole in it: post-R6 a ``.clausal`` data
    functor's name binds its interned spelling, but the ``-module`` rewrite's
    class block runs at EXEC time, before ``_process_declarations`` rebinds
    the name -- so a ``-constants`` right-hand side (``-constant_value(_ORIGIN_, Point(0, 0))``) is evaluated through the class and yields exactly the
    instance the ruling says cannot exist.

    Emitting a class construction for it produces code that cannot run: the
    only spelling available is ``Point``, and ``Point`` is the str.  So the
    binding question is asked HERE too, and the answer is the same one the
    NAME side gives -- which is the whole point, since a construction that
    disagreed with its own matching half is the hazard the ruling exists to
    remove:

    * the compile scope binds this class under its own name -> nameable,
      class emission (every Python-minted functor: ``clausal.reflection``'s
      ``Goal``, ``clpb``'s ``BoolEq``).  Returns None.
    * the name resolves as DATA (str binding + signature registry) and the
      registry's slot layout is this class's own -> a cell, the identical
      shape every other reference to that functor in this module compiles to.
    * anything else -> None; class emission, unchanged.
    """
    cls = type(term)
    if not isinstance(cls, PredicateMeta):
        return None
    scope = lowering_globals()
    if scope is None:
        return None
    name = cls.__name__
    if scope.get(name) is cls:
        return None
    signature = cell_signature_for_name(name)
    if signature is None:
        return None
    functor, fields = signature
    if tuple(fields) != tuple(getattr(cls, "_fields", ())):
        return None
    return functor


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


def term_to_ast_expr(
    term: Any, var_context: dict[int, str], *, eval_arith: bool = True
) -> ast.expr:
    """Convert a term value to a Python AST expression.

    The generated expression evaluates at runtime to the term.
    Vars already in var_context are referenced by name.  Vars not yet in
    var_context (body-only Vars) are introduced via walrus ``(_vN := Var())``.

    when *eval_arith* is True (the default), arithmetic term nodes
    (Add, Sub, …) are compiled to native Python operators so they evaluate
    at runtime.  when False, they are kept as structural term constructors
    (e.g. ``Add(left=x, right=1)``).

    Supports: Var, Python scalars, list, Compound, functor dataclasses.
    """
    raw = term
    term = deref(term)

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

    if isinstance(term, Compound):
        f = term.functor
        f_expr: ast.expr
        if is_var(f):
            vid = f._id
            f_expr = _name(var_context[vid]) if vid in var_context else _call(_name("$Var"))
        else:
            f_expr = ast.Constant(value=f)
        args_elts = [term_to_ast_expr(a, var_context, eval_arith=eval_arith) for a in term.args]
        return _call(
            _name("$Compound"),
            f_expr,
            ast.Tuple(elts=args_elts, ctx=ast.Load()),
        )

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
        # keyword args fill their named slots, and every slot neither
        # reaches backfills with a fresh ``Var()`` — the same "missing field
        # -> fresh Var()" rule ``PredicateMeta.__call__`` applies to class
        # construction (see ``_place_signature_slots``), so a kwarg/partial
        # reference now builds a cell too instead of falling back to class
        # emission.
        _sig = cell_signature_for_name(fname)
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
            if not isinstance(_binding, PredicateMeta):
                if kw_exprs:
                    raise SyntaxError(
                        f"functor {fname!r} has no declared signature: "
                        f"-implicit_functors makes keyword-free construction "
                        f"of any functor/arity advisory, but keyword "
                        f"placement for {fname!r} still requires a declared "
                        f"signature to place its named slots against"
                    )
                return cell_literal_ast(sys.intern(fname), arg_exprs)
        return ast.Call(
            func=_name(fname),
            args=arg_exprs,
            keywords=kw_exprs,
        )

    # Zero-arity PredicateMeta class reaching the compiler as a live term
    # object.  Atoms are global strs post-pivot (§1b/R2) — no module mints
    # this class any more, but one can still ARRIVE here from old code
    # (another package, a test) constructing one directly, so this branch
    # stays as a compatibility lowering: emit the class's NAME as a str
    # Constant (the identical literal a bare atom of that spelling would
    # produce), not a bare Name reference into a namespace.  There is no
    # by-identity special case any more (that machinery is deleted, §1b/R2)
    # — a plain-str atom and a live zero-field class of the same spelling
    # both lower to the identical ``ast.Constant``.
    #
    # 2026-09-06-atoms-as-cells-strings, Task 9: the constant is
    # ``atoms.mint(term.__name__)`` — under Plan 0 byte-identical output, and
    # at Stage B this becomes the arity-0 cell without a second edit here.
    # ``ast.Constant`` takes the cell directly (a 1-tuple of a str folds into
    # ``co_consts`` and is marshal-clean — spec §5.2).
    if is_zero_field_class(term):
        return ast.Constant(value=_mint_atom(term.__name__))

    if is_term_instance(term):
        cls = type(term)
        # ``$``-twin for a class the runtime table binds (a simple_ast node
        # such as ``Add``, an injected class such as ``BoolEq``), bare for
        # a user's own predicate class -- see ``generated_names.dollar_ref``.
        cls_name = dollar_ref(cls)
        fields = term_field_names(term)
        # A live term INSTANCE ALWAYS keeps class emission (P3-2 Task 2,
        # controller ruling on the gate asymmetry).  Cell-vs-class is decided
        # on the BINDING (R6): a declared data functor binds its interned
        # spelling, so post-flip no ``.clausal`` module can produce an
        # instance of one at all.  Every instance that still reaches here was
        # minted in PYTHON (``clausal.reflection``'s ``Goal``/``Clause``,
        # ``clpb``'s ``BoolEq``) and belongs to the class world: those
        # producers build instances at runtime, and lowering them to cells
        # here would emit a shape the NAME side of the same functor compiles a
        # class pattern for -- "builds one shape, matches another", the clause
        # that can never fire.  Answering uniformly at the class instead of
        # per site also retires the ``_position``/``position`` exclusion that
        # the old instance gate needed.
        #
        # The one exception is an instance whose class this compile cannot
        # NAME -- see ``unnameable_instance_cell_functor``, which asks the
        # same binding question the name side asks and therefore cannot
        # disagree with it.
        _cell_f = unnameable_instance_cell_functor(term)
        if _cell_f is not None:
            return cell_literal_ast(
                _cell_f,
                [
                    term_to_ast_expr(
                        getattr(term, name), var_context,
                        eval_arith=eval_arith,
                    )
                    for name in fields
                ],
            )
        if (
            isinstance(cls, PredicateMeta)
            and isinstance(vars(cls).get("_clausal_new"), classmethod)
            and not any(name in ("_position", "position") for name in fields)
        ):
            # Saturated, no position field, generated fast constructor
            # available: emit a positional call to it instead of the
            # keyword-based slow-path constructor call below.  Gate on
            # ``vars(cls).get("_clausal_new")`` actually BEING the generated
            # classmethod, not merely present by that name — a class whose
            # FIELD is literally named "_clausal_new" also has an entry at
            # that key (the __slots__ member descriptor; see the attach guard
            # in predicate.py), and calling that descriptor as a constructor
            # raises a TypeError at runtime.
            #
            # This positional emission is order-dependent on ``fields`` for
            # whichever class ``cls_name`` resolves to at call time; it is
            # solve.py's ``_collect_types_from_term`` update-after-module-dict
            # that keeps query templates resolving to the caller's actual
            # class rather than a stale one.
            #
            # Cross-ref: this gate is DELIBERATELY narrower than the walk/copy
            # rebuilders' Phase 0 gate (see solve.py's _deref_walk_py) — the
            # extra ``"_position"``/``"position"`` exclusion above is required
            # here because the slow path just below drops those fields from
            # the emitted kwargs entirely, whereas the walkers' slow path
            # keeps all fields. Do not "unify" the two gates by deleting this
            # condition.
            return _call(
                _attr(cls_name, "_clausal_new"),
                *[
                    term_to_ast_expr(
                        getattr(term, name), var_context, eval_arith=eval_arith,
                    )
                    for name in fields
                ],
            )
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

    # KWTerm: generate KWTerm("functor", key=val, ...)
    if isinstance(term, KWTerm):
        keywords = [
            ast.keyword(arg=k, value=term_to_ast_expr(v, var_context, eval_arith=eval_arith))
            for k, v in term.items()
        ]
        return ast.Call(
            func=_name("$KWTerm"),
            args=[ast.Constant(value=term.functor)],
            keywords=keywords,
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

    # A predicate CLASS (arity ≥ 1 — the zero-arity/atom case returned above)
    # in term position.  Almost always the atom/predicate name clash.
    if isinstance(term, PredicateMeta):
        # STAGE 2 (spec 2026-09-18 §4): a predicate referenced BY NAME in
        # argument position is the ATOM of that name -- the str.  The
        # name-clash diagnostic is gone: an atom foo and a predicate foo/N
        # coexist as in Prolog.
        return ast.Constant(value=term.__name__)

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

_ARITH_BINOP_MAP: list[tuple[type, ast.operator]] = [
    (Add,      ast.Add()),
    (Sub,      ast.Sub()),
    (Mult,     ast.Mult()),
    (Div,      ast.Div()),
    (FloorDiv, ast.FloorDiv()),
    (Mod,      ast.Mod()),
    (Pow,      ast.Pow()),
]


def exact_div(l, r):
    """``$exact_div``: a literal int/int Div in compiled arithmetic — exact
    (``3/2`` is ``Fraction(3, 2)``), an integral quotient as int."""
    return present_number(Fraction(l, r))


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
    "$div": _exact_div,
}
_EXACT_BINOP_NAMES = ((Add, "$add"), (Sub, "$sub"), (Mult, "$mul"), (Div, "$div"))


def arith_to_ast_expr(term: Any, var_context: dict[int, str]) -> ast.expr:
    """Convert an arithmetic term to a Python arithmetic AST expression.

    Generates code that evaluates the expression to a Python number at runtime.
    Vars are dereferenced.  Arithmetic binary operators are unboxed to native
    Python ``ast.BinOp`` nodes.
    """
    term = deref(term)

    if is_var(term):
        vid = term._id
        vname = var_context.get(vid, _var_python_name(term))
        return _call(_name("$deref"), _name(vname))

    term = literal_value(term)
    if isinstance(term, (int, float, Fraction)) and not isinstance(term, bool):
        return ast.Constant(value=term)

    # int / int → an exact rational; ``$exact_div`` presents an integral
    # quotient as int (4/2 is 2, not Fraction(2, 1)).
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

    if isinstance(term, Negate):
        return ast.UnaryOp(
            op=ast.USub(),
            operand=arith_to_ast_expr(term.operand, var_context),
        )

    # ``+``, ``-``, ``*``, ``/`` go through the exact helpers (a call, ~30 ns,
    # measured); ``//``, ``%``, ``**`` stay native Python operators.
    for cls, runtime_name in _EXACT_BINOP_NAMES:
        if isinstance(term, cls):
            return ast.Call(
                func=_name(runtime_name),
                args=[arith_to_ast_expr(term.left, var_context),
                      arith_to_ast_expr(term.right, var_context)],
                keywords=[],
            )
    for cls, ast_op in _ARITH_BINOP_MAP:
        if isinstance(term, cls):
            return ast.BinOp(
                left=arith_to_ast_expr(term.left, var_context),
                op=ast_op,
                right=arith_to_ast_expr(term.right, var_context),
            )

    # Fallback: treat as a plain term (e.g. a Var holding a number at runtime)
    return term_to_ast_expr(term, var_context)
