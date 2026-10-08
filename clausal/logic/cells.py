"""Tagged cells: the unconditional plain-tuple compiled term representation.

Every compound term compiles to a cell (P3-2, the cell-default flip) -- there
is no opt-in flag left to spell. (History: this module started as the Phase 2
bridge's opt-in representation, Task 1 of
``docs/superpowers/plans/2026-09-03-phase2-bridge.md``; P3-2 deleted the
``-tagged_terms`` flag that gated it.)

Spec: ``implementation_plans/tagged-tuple-term-representation.md`` (design
§1, optimisations §3c).

A *cell* is a plain Python ``tuple`` whose slot 0 identifies its shape:

  - a ``str`` functor   -> ``("point", x, y)``   a compound term ``point/2``.
  - the ``tuple`` TYPE OBJECT (``TUPLE_TAG``) -> ``(tuple, e1, e2, ...)``
    tuple-DATA, not a compound -- this is how a cell represents a bare
    Python tuple as term data without slot 0 colliding with a real user
    value (a plain data tuple's own slot 0 could be anything; tagging with
    the ``tuple`` type itself sidesteps that).

Nothing else may occupy slot 0 -- ``make_cell`` enforces this; ``is_cell``
recognizes it.

Phase 3 Task 5 (§1b, ``implementation_plans/tagged-tuple-term-representation.md``):
an unbound-``Var`` functor slot -- the bridge's higher-order/not-yet-resolved
cell, ``(X, a, b)`` -- is DEPRECATED and no longer part of this domain.
It caused the bridge's one Critical (a cell built with a Var functor
vanished from recognition the instant ``unify`` bound that functor, because
recognition dereferenced slot 0 and the bound value could be anything),
imposed a permanent deref on every recognition site, and permitted category
instability (``(F, 1)`` flipping from compound to tuple-data if ``F`` binds
to the ``tuple`` type). Higher-order metaprogramming over cells routes
through ``functor/3`` / ``=../2`` / ``call/N`` instead (P3-3; ISO's own
trade-off). A tuple whose slot 0 is a Var (bound or not) is therefore not a
cell at all -- it falls through to plain-tuple handling everywhere, the
same as a tuple tagged with an ``int`` or any other non-str, non-``tuple``
value. ``make_cell`` raises ``TypeError`` for a Var functor same as any
other invalid one; every recognition site (``is_cell``, the funnel
accessors, ``head_match``, the head walker, the list-dispatch gates) reads
slot 0 RAW -- no deref, ever, on this path.

BRIDGE-ENTRY RULING (ledgered in the Phase 2 bridge plan's Global
Constraints): ``is_cell`` does NOT require ``sys.intern``'d functors --
equality is the semantics of functor comparison everywhere a cell is
compared (the existing C tuple-unify branch this module deliberately rides
compares slot 0 with ``==``, never ``is``; see ``do_unify``'s
``PyTuple_Check(t1) && PyTuple_Check(t2)`` branch in
``clausal/logic/variables/_variables.c``). ``make_cell`` interns as a
convenience only (fewer distinct string objects, marginally faster
compares in practice) -- ``is_cell`` and every accessor here accept ANY
``str`` in slot 0, interned or not.

THE DISCIPLINE (formerly documented here as an accepted "known ambiguity",
now the rule per §1b's slot-0 narrowing): every runtime tuple IS a cell --
a plain user tuple whose slot 0 happens to be a ``str`` -- e.g. ``("hello",
1)`` meant as ordinary tuple data, not a compound -- is a str-functor cell
by shape, full stop, and ``is_cell``/the funnel accessors in
``clausal/logic/builtins/_helpers.py`` treat it as one. There is no
narrower "is this REALLY a cell" test to fall back on; a caller that needs
"plain tuple data, not a compound" must use the ``TUPLE_TAG``-tagged form
(``make_tuple_cell``) rather than a bare str-first tuple. The residual
untagged shapes this bridge stage still has -- ``dict``/``set`` pairs, which
carry no slot-0 tag at all -- are Phase 4's business (pair migration,
per the plan's roadmap), not this module's.

Cells ride the *existing* C unify/walk tuple branches unchanged (they are
just tuples): this module adds no C code and no new representation
machinery, only Python-level construction/inspection helpers, per the
Phase 2 bridge plan's Global Constraints ("Cells are plain tuples ...
They already unify/walk/key through the existing C tuple branches -- do
not add representation machinery the engine already has.").
"""

from __future__ import annotations

import sys
from typing import Any

from clausal.logic.variables import deref, is_var
from clausal.logic.dialect_edge import (
    _CACHE as _DIALECT_CACHE, refuse_edge as _refuse_dialect_edge)
from clausal import _sandbox_state

__all__ = [
    "FUNCTOR_SIGNATURES_KEY",
    "registry_fields",
    "registry_signatures",
    "IMPLICIT_FUNCTORS_FLAG",
    "CELLS_NAMESPACE_KEY",
    "TUPLE_TAG",
    "CHARS_TAG", "chars", "is_chars", "chars_text",
    "register_compiled_constants", "is_compiled_constant",
    "is_reserved_1tuple", "refuse_reserved_1tuple",
    "make_cell",
    "make_tuple_cell",
    "is_cell",
    "cell_functor",
    "cell_args",
    "cell_arity",
    "intern_cell",
    "clear_intern_table",
    "is_intern_enabled",
    "set_intern_enabled",
    "compound_cell_shape",
    "CELL_GOAL_CONTROL_FUNCTORS",
    "refuse_control_construct_cell",
    "QUALIFIED_GOAL_FUNCTOR",
    "MAX_QUALIFICATION_DEPTH",
    "resolve_qualified_goal_cell",
]
# NOTE: `_cell_shape` is intentionally NOT in __all__ (internal helper) but
# IS imported directly by other modules that need to test "is this
# cell-shaped" without a second read of slot 0 -- the same
# "leading-underscore, cross-module funnel helper" convention that
# `_helpers.py` already uses for _functor_name/_arity/etc. Importers, all
# routing raw slot-0 checks through this ONE predicate rather than
# re-spelling "type(x) is tuple and (type(x[0]) is str or x[0] is
# TUPLE_TAG)" locally (P3-2 Task 5 carry-forward consolidation):
#   - clausal/logic/builtins/_helpers.py (the funnel -- inlines the str-only
#     compound check directly, see `_cell_functor`, since it additionally
#     needs to exclude TUPLE_TAG from "compound")
#   - clausal/logic/compiler/head_match.py (the live-cell branch)
#   - clausal/logic/compiler/globals_env.py (`_walk_head`'s cell branch)
#   - clausal/logic/compiler/list_dispatch.py (the head-literal/deep-gate
#     helpers)
#   - `compound_cell_shape` below -- the P3-3 Task 5 narrowing (str functor
#     only) that database.head_key, solve._term_to_goal/_structural_key/
#     _templatize_query_goal, builtins/higher_order's call/N family and
#     builtins/database_ops' assert/retract gate all share.  Those five call
#     `compound_cell_shape`, NOT `_cell_shape` directly, so the
#     "is this cell-shaped AND does it name a predicate" question has one
#     spelling too.
# See _cell_shape's docstring.


# The tag used in slot 0 for a "tuple as term data" cell: ``('()', e1, ...)``.
#
# A RESERVED QUOTED ATOM, completing a convention rather than inventing one:
# ISO gives each bracket syntax a reserved quoted-atom functor, and this engine
# already stores ``{X}`` as the cell ``('{}', X)`` (``tools/prolog_reader.py``)
# and spells nil ``'[]'`` (``atoms.NIL_SPELLING``). ``'()'`` is the third.
#
# It replaced the ``tuple`` TYPE OBJECT, which could not be marshalled -- the
# single fact that forced emitted code to reach the tag by name through the
# ``$cells`` namespace instead of folding it into a constant. A ``str`` tag
# also collapses ``_valid_functor_slot`` to one branch.
#
# Why not the empty spellings: ``unify((), '')`` is TRUE though ``() == ''`` is
# False -- ``()``, ``''`` and ``[]`` are already ONE term, nil -- so the empty
# data tuple would collide with the empty atom under either. ``'()'`` collides
# with none of them, and ``'()'(1, 2)`` reads and writeq-round-trips in SWI and
# Scryer, so a ``.pl`` file carrying tuple-data stays portable.
TUPLE_TAG = "()"

# THE CHARS CARRIER (spec docs/superpowers/specs/2026-09-18-atoms-as-str-design.md,
# RULED Q2 2026-09-18).  Under ``-double_quotes(chars)`` a string IS the list
# of its one-char atoms; ``('$chars', "abc")`` is that list's COMPACT form --
# a reserved-tag cell, arity 1, the Python str as the sole payload, EQUAL to
# the list term everywhere (unify, ==, standard order, the text builtins).
# ``$``-prefixed like every reserved engine name and, like ``TUPLE_TAG``, a
# head no user functor can spell.  It exists so that a bare Python ``str``
# can stop meaning "text" (stage 1) and start meaning "atom" (stage 2).
CHARS_TAG = "$chars"


def is_reserved_1tuple(x: Any) -> bool:
    """True for the arity-0 str-headed tuple ``('x',)`` -- the OLD atom cell,
    RESERVED after stage 2 of the atoms-as-str flip (RULED 2026-09-18: a
    future opaque Python object reference).  ``(TUPLE_TAG,)`` is the empty
    tuple-DATA cell and is not it."""
    return (type(x) is tuple and len(x) == 1 and type(x[0]) is str
            and x[0] != TUPLE_TAG)


def refuse_reserved_1tuple(x: Any) -> None:
    """Raise on the reserved 1-tuple; the ONE spelling of the refusal."""
    if is_reserved_1tuple(x):
        raise TypeError(
            f"the 1-tuple {x!r} is reserved (a future opaque Python object "
            f"reference); an atom is the str {x[0]!r} -- write mint({x[0]!r}) "
            f"or the bare name")


def chars(text: str) -> tuple:
    """The chars carrier for *text* (a Python str)."""
    if type(text) is not str:
        raise TypeError(f"chars(): expected a str, got {type(text).__name__}")
    return (CHARS_TAG, text)


class _Text:
    """A read-only view ``base[lo:hi]`` of a str, held in slot 1 of a chars
    carrier in place of a str.

    Taking the rest of a text after a matched prefix -- a DCG terminal, a head
    ``[C|Cs]`` against text -- binds a view of the same str instead of a copy
    of the rest, so parsing n chars holds the input once rather than about
    n^2/2 chars in the slices its choice points keep alive.  Slicing a view is
    another view of the same base.

    A view IS its text: equal to the str (and to any view) that spells it,
    ordered like it, hashed like it -- so a view carrier and a str carrier of
    the same text are one term, one dict key, one tabling key.  The text is
    read by position for len, one char and slices; anything that needs the
    whole str (``flat``, ``chars_text``) builds it once and keeps it.  The
    chars ``[lo, hi)`` never change, so the hash (cached in a tuple by CPython
    3.14) never goes stale."""
    __slots__ = ("base", "lo", "hi", "_flat")

    def __init__(self, base: str, lo: int, hi: int):
        self.base, self.lo, self.hi, self._flat = base, lo, hi, None

    @property
    def flat(self) -> str:
        """The text as a str, built once."""
        if self._flat is None:
            self._flat = self.base[self.lo:self.hi]
        return self._flat

    def __len__(self):
        return self.hi - self.lo

    def __getitem__(self, i):
        if isinstance(i, slice):
            a, b, step = i.indices(self.hi - self.lo)
            if step != 1:
                return self.flat[i]
            return text_slice(self.base, self.lo + a, self.lo + max(a, b))
        n = self.hi - self.lo
        if i < 0:
            i += n
        if not 0 <= i < n:
            raise IndexError("text view index out of range")
        return self.base[self.lo + i]

    def __iter__(self):
        return iter(self.flat)

    def _other_text(self, other):
        if type(other) is _Text:
            return other.flat
        if isinstance(other, str):
            return other
        return None

    def __eq__(self, other):
        if type(other) is _Text or isinstance(other, str):
            if len(other) != self.hi - self.lo:
                return False            # a mismatch never builds the text
            return self.flat == self._other_text(other)
        return NotImplemented

    def __ne__(self, other):
        r = self.__eq__(other)
        return r if r is NotImplemented else not r

    def __lt__(self, other):
        o = self._other_text(other)
        return NotImplemented if o is None else self.flat < o

    def __le__(self, other):
        o = self._other_text(other)
        return NotImplemented if o is None else self.flat <= o

    def __gt__(self, other):
        o = self._other_text(other)
        return NotImplemented if o is None else self.flat > o

    def __ge__(self, other):
        o = self._other_text(other)
        return NotImplemented if o is None else self.flat >= o

    def __hash__(self):
        return hash(self.flat)

    def __str__(self):
        return self.flat

    def __repr__(self):
        return repr(self.flat)


# A slice shorter than this is copied, as before; a longer one is a view.
# The same number as CHARS_VIEW_MIN in variables/_chars_carrier.h.
VIEW_MIN = 64


def text_slice(base: str, lo: int, hi: int):
    """``base[lo:hi]`` of the str *base*: a view when long, a str when short."""
    if hi - lo >= VIEW_MIN:
        return _Text(base, lo, hi)
    return base[lo:hi]


def is_chars(x) -> bool:
    """True if *x* is a well-formed chars carrier ``('$chars', text)``, text a
    str or a view (``_Text``)."""
    # isinstance before ``==``: slot 0 of an arbitrary tuple may be an array,
    # whose ``==`` is elementwise and has no truth value (a pair of NumPy
    # arrays made this raise ValueError, and to_python with it).
    return (type(x) is tuple and len(x) == 2 and isinstance(x[0], str)
            and x[0] == CHARS_TAG and (type(x[1]) is str or type(x[1]) is _Text))


def chars_text(x) -> str:
    """The Python str a chars carrier holds (caller checked ``is_chars``); a
    view is built into its str once."""
    t = x[1]
    return t if type(t) is str else t.flat


def flat_carrier(term):
    """*term*, with a VIEW carrier replaced by the str carrier of its text;
    anything else unchanged.  For copy points that outlive a parse -- the
    clause compiler embedding a literal, an asserted clause -- which must not
    keep a view's whole base str alive (and cannot embed a view in code)."""
    if type(term) is tuple and len(term) == 2 and type(term[1]) is _Text and term[0] == CHARS_TAG:
        return (CHARS_TAG, term[1].flat)
    return term


def chars_payload(x):
    """The carrier's slot 1 as a SEQUENCE: the str, or the view without
    flattening it (len, [i], [a:b] all O(1))."""
    return x[1]


# The module-namespace key holding a module's functor-signature registry:
# ``{"point": ("x", "y"), ...}``, one entry per ``(name, fields)`` the
# ``-module``/``-private`` rewrite saw -- predicates included, since the
# data/predicate split is decided by binding shape (whether a functor has
# clauses), not by anything the registry itself records.  Emitted by
# ``clausal/templating/term_rewriting.py``'s ``_handle_module_directive`` /
# ``_handle_private_directive`` as a module-level
# ``__clausal_functor_signatures__ = {...}`` assignment (accumulated via
# ``dict.update`` across multiple directives in the same file -- an
# assignment rather than a ``module_items`` entry, deliberately: module items
# are recovered separately when a module loads from its ``.pyc`` cache,
# whereas an assignment is part of the cached bytecode and therefore cannot
# go missing on the cached path);
# ``-import_from`` copies the imported names' entries into the importer's
# dict under their LOCAL spelling.
#
# ``clausal/logic/compiler/terms_to_ast.py``'s ``functor_signature_for``
# consults this registry FIRST, falling back to a resolved class's
# ``_fields`` while generated functor classes still exist (P3-2 Tasks 1-2 of
# the cell-default flip).  Once a later task removes those classes, this
# registry becomes the sole source of truth for a functor's declared field
# names.
#
# A name DECLARED with field names at several arities (operator ruling
# 2026-09-29: "-module(lib, [q(X), q(X, Y)]): allow it") has a DICT value,
# ``{arity: fields}``; every other name keeps its ``fields`` tuple.  Read
# the registry through :func:`registry_signatures` / :func:`registry_fields`,
# never by indexing it, so both shapes are honoured.
FUNCTOR_SIGNATURES_KEY = "__clausal_functor_signatures__"


def registry_signatures(value) -> "dict[int, tuple[str, ...]] | None":
    """``{arity: fields}`` for one functor-signature registry *value* (a
    ``fields`` tuple, or the per-arity dict of a name declared at several
    arities); ``None`` for ``None``."""
    if value is None:
        return None
    if isinstance(value, dict):
        return {a: tuple(f) for a, f in value.items()}
    return {len(value): tuple(value)}


def registry_fields(registry, name: str,
                    arity: "int | None" = None) -> "tuple[str, ...] | None":
    """*name*'s field names in the functor-signature *registry*.

    A single-arity name answers its one entry whatever *arity* is (the old
    by-name read, unchanged).  A name declared at several arities answers
    the entry AT *arity*, and ``None`` when *arity* is ``None`` or not one
    of them: by name alone, which arity is meant is not the registry's to
    guess."""
    if not registry:
        return None
    value = registry.get(name)
    if value is None:
        return None
    if not isinstance(value, dict):
        return tuple(value)
    if arity is None:
        return None
    found = value.get(arity)
    return None if found is None else tuple(found)


# The module-namespace key recording every spelling this file DECLARED as a
# bare 0-arity ATOM (a name with no parentheses in its ``-module``/
# ``-private`` list).  P3-3 Task 5b.
#
# Post-pivot a declaration alone binds the interned spelling, so "declared as
# an atom" is usually readable straight off the binding -- but not when the
# file ALSO writes 0-arity clauses for the name: the clause block mints a
# real ``PredicateMeta`` and the declaration must not clobber it (see
# ``compiler_v2._process_declarations``), so the binding then says
# "predicate" and the atom-ness is lost.  The owning file's own lowering
# still knows (its ``-module`` list is right there in the source); an
# ``-import_from``ing file does not, and used to receive the CLASS as the
# value of a data reference -- a dict key that silently missed the str key
# every other module writes.  This registry is what the import edge reads to
# answer the question the way the owner would.
#
# Written by ``compiler_v2._process_declarations`` (both ``-module`` and
# ``-private`` bare entries; the list is a DECLARATION record, not an export
# list) and read by ``compiler_v2._process_imports``.
DECLARED_ATOMS_KEY = "__clausal_declared_atoms__"


# The module-namespace key holding a file's ``-import_from`` RECORD: a list of
# ``(name, exporter)`` pairs in source order, one per imported name, where
# *name* is the EXPORTER's spelling (an ``alias(orig, local)`` entry records
# ``orig``, the atom the alias binds) and *exporter* is the resolved module's
# ``__name__`` (a ``sys.modules`` key, so ``clausal.declared_atoms`` accepts
# it).  Every imported name is recorded, predicates included: which of them
# are ATOMS is the exporter's declaration, asked at read time.
#
# Written by ``compiler_v2._process_imports``; read by
# ``solve.imported_atoms``.  Like ``DECLARED_ATOMS_KEY`` it is per FILE, so
# the answer does not depend on what else was loaded into the namespace.
IMPORT_FROM_KEY = "__clausal_import_from__"


# The module-namespace key marking a module as opted into OPEN-WORLD functor
# construction (P3-2 Task 6, user ruling R7): ``-implicit_functors`` compiles
# to a module-level ``__clausal_implicit_functors__ = True`` assignment, the
# same "flag survives the ``.pyc``-cached load path" shape
# ``TAGGED_TERMS_FLAG`` used before the Phase 2 bridge's flag machinery was
# deleted (P3-2 Task 2, THE FLIP) -- an assignment rather than a
# ``module_items`` entry, because an assignment is part of the cached
# bytecode and therefore cannot go missing on the cached path, whereas a
# module item is recovered separately when a module loads from its ``.pyc``.
#
# Construction checking is ON by default everywhere (``FUNCTOR_SIGNATURES_KEY``
# governs it): a keyword-free reference to an undeclared functor is a runtime
# ``NameError`` and an over-arity reference to a declared one is a
# compile-time ``SyntaxError`` (see
# ``clausal.logic.compiler.terms_to_ast.cell_signature_for_name`` /
# ``_place_signature_slots``).  A module carrying this flag opts OUT of both
# checks for keyword-free construction only: ``clausal.logic.compiler.
# terms_to_ast.term_to_ast_expr`` and ``clausal.logic.compiler.head_match.
# head_to_match_pattern`` both consult it (via ``terms_to_ast.
# lowering_globals()``) to build a cell of ANY functor at ANY WRITTEN arity,
# declared signature or not -- signatures become advisory, not a keyhole, for
# every plain (keyword-free) reference in a flagged module.  Keyword
# construction/matching still needs a real signature to place its named
# slots against, flag or no flag -- the flag opens functor VOCABULARY, not
# the keyword-placement contract.  Orthogonal to the strict-atoms rule:
# this flag says nothing about bare (0-arity) ATOM references, which keep
# the declaredness discipline that rule governs.
IMPLICIT_FUNCTORS_FLAG = "__clausal_implicit_functors__"


# The key under which a compiled predicate's ``base_globals`` holds THIS
# module, so emitted code can name ``TUPLE_TAG`` as a DOTTED value pattern
# (``$cells.TUPLE_TAG``).  A ``match`` pattern cannot test a bare name -- that
# is a capture, not a value test -- so the tuple-DATA tag needs an attribute
# access, and this is its root.  The ``$`` prefix is what makes it safe: no
# Python identifier can collide with it, whereas rooting the pattern at
# ``builtins`` would break in any module that happens to bind that name
# (``base_globals`` is updated FROM the module namespace).  Injected by
# ``clausal/logic/compiler/predicate.py`` and read by
# ``head_match.head_to_match_pattern``'s live-cell branch, which emits the
# tuple-DATA arm only when the entry is actually present.
CELLS_NAMESPACE_KEY = "$cells"


def _valid_functor_slot(slot0: Any) -> bool:
    """True if *slot0* is a legal cell slot-0 value (the bridge-entry
    ruling, narrowed by §1b/Task 5): a ``str`` functor or the ``tuple``
    type object. Nothing else -- a Var functor is DEPRECATED (see the
    module docstring) and no longer legal here.

    *slot0* is read RAW by the caller (see ``_cell_shape`` below) -- this
    function never derefs.

    EXACT type, not ``isinstance`` (Task 5 review fix round 1): matches
    the exact-type convention the rest of the post-Task-4 cell machinery
    already committed to (``arg_index._arg_to_index_key``,
    ``_runtime_arg_key``/``_is_deeply_ground_walk``, and this task's own
    brief-mandated ``_helpers._cell_functor``, which spells
    ``type(term[0]) is str`` directly). No test in this suite constructs a
    ``str`` subclass as a functor.
    """
    # ONE branch since the tag became a str (it used to be the ``tuple``
    # type object, which needed a second test). Measured 2.08x on this path.
    return type(slot0) is str


def _cell_shape(x: Any) -> tuple[bool, Any]:
    """Return ``(is_cell, slot0)`` for *x*, reading slot 0 RAW.

    §1b/Task 5: NO deref, ever, on this recognition path -- the bridge's
    slot-0-Var (higher-order functor) support is deprecated precisely
    because it required one (see the module docstring). ``is_cell`` is
    defined in terms of this; several other modules import this directly
    to test "is this cell-shaped" without a second read of slot 0 (see the
    NOTE above ``__all__`` for the full, current list of importers) --
    ``clausal/logic/builtins/_helpers.py``'s own ``_cell_functor`` is the
    one exception, inlining an equivalent str-only check directly instead
    of importing this, since it needs different "compound" semantics
    (excluding ``TUPLE_TAG``).
    """
    if type(x) is not tuple or len(x) < 1:
        return False, None
    if len(x) == 1:
        refuse_reserved_1tuple(x)       # STAGE 2: the old atom cell is RESERVED
    slot0 = x[0]
    return _valid_functor_slot(slot0), slot0


def compound_cell_shape(x: Any) -> tuple[bool, Any]:
    """Return ``(is_compound_cell, functor)`` -- ``_cell_shape`` narrowed to
    the cells that can name a PREDICATE.

    A ``TUPLE_TAG`` cell is tuple DATA: it has no functor name, so it is
    never a goal, never a clause head, and never an ``assertz`` argument.
    Everything ``_cell_shape`` accepts that is not ``TUPLE_TAG`` is a ``str``
    functor (see ``_valid_functor_slot``), so this is exactly "a cell with a
    str functor", read RAW, with no second look at slot 0.

    THE ONE SPELLING for P3-3's goal/head surfaces (Task 5, R11):
    ``database.head_key``, ``solve._term_to_goal``/``_structural_key``/
    ``_templatize_query_goal``, ``higher_order``'s ``call/N`` family and
    ``database_ops``'s assert/retract gate all ask this question and all ask
    it here, built ON ``_cell_shape`` rather than re-spelling it.
    ``builtins/_helpers._cell_functor`` is the funnel's own equivalent and
    stays separate for the reason recorded above ``__all__``: the funnel
    inlines its slot-0 check rather than importing one.
    """
    ok, functor = _cell_shape(x)
    # ``!=``, not ``is not``: the tag is a str now, and a str that is equal
    # but not identical (not interned by the same route) must still be read
    # as tuple-data.
    if ok and functor != TUPLE_TAG and functor != CHARS_TAG:
        return True, functor
    return False, None


# The control-construct functors an ISO term can spell (``','(A, B)`` is the
# conjunction as a TERM, which under cells is ``(",", A, B)``).  DEFERRED in
# cell-GOAL position this phase -- see ``refuse_control_construct_cell``.
#
# ``*->`` (soft cut) is in the set on the P3-3 Task 5 fix-round-1 ruling: it is
# a control construct in every Prolog that has it, and the fact that this
# engine has no compile-time form for it yet is a reason to give the SAME
# diagnostic, not a reason to let it fall through to an ordinary ``*->``/2
# lookup and fail silently.
CELL_GOAL_CONTROL_FUNCTORS = frozenset({",", ";", "->", "*->", "\\+"})

# What to tell the user instead, per functor -- the whole remedy clause, not
# just a node name, because ``*->`` has no compile-time form to point at.
_CONTROL_CONSTRUCT_REMEDY = {
    ",": "write the conjunction in the clause body, where `,` compiles to an "
         "And node",
    ";": "write the disjunction in the clause body, where `;` compiles to an "
         "Or node",
    "->": "write the if-then in the clause body, where `->` compiles to an Or "
          "of And nodes",
    "\\+": "write the negation in the clause body, where `\\+` compiles to a "
           "Not node",
    "*->": "there is no compile-time `*->` on the adaptor surface either — "
           "soft cut arrives with the ISO surface, and this refusal is what "
           "keeps it from looking like an ordinary missing predicate",
}


def refuse_control_construct_cell(cell: Any, functor: Any, context: str) -> None:
    """Refuse a control-construct functor in cell-GOAL position (P3-3 Task 5).

    ISO's conjunction-as-a-term is ``','(A, B)``, which under the cell
    representation is the ordinary cell ``(",", A, B)``; the same goes for
    ``;``, ``->``, ``*->`` and ``\\+``.  Calling one means running a control construct
    the engine only ever lowers at COMPILE time -- the adaptor surface never
    produces these as terms (a conjunction written in a clause body becomes an
    ``And`` node), so only a runtime-built term can reach a goal position
    spelling one.

    Supporting them is a real feature (a runtime goal-tree interpreter), not a
    branch: it needs cut/barrier semantics, a delimited-control story for
    ``->``, and a decision about ``\\+``'s NAF database -- all of which the
    ISO-surface phase owns.  Until then the diagnostic names the functor and
    the compile-time form, instead of the goal quietly failing (which is what
    ``call((",", A, B))`` did before this task) or an internal
    ``NotImplementedError`` from ``terms_to_goalop``.

    Raises ``LogicException(type_error(callable_control_construct_unsupported,
    Cell))``; returns None for every other functor.  The culprit is the cell
    itself -- a plain tuple, so it round-trips through unification and
    ``copy_term`` and can be matched by a ``catch/3`` pattern.
    """
    if functor not in CELL_GOAL_CONTROL_FUNCTORS:
        return
    # Local import, and it has to be: ``clausal.terms`` imports THIS module
    # for ``TUPLE_TAG`` and ``clausal.logic.exceptions`` imports
    # ``clausal.terms``, so a module-level import here would close the cycle.
    from clausal.logic.exceptions import (  # noqa: PLC0415
        LogicException, type_error,
    )
    remedy = _CONTROL_CONSTRUCT_REMEDY[functor]
    arity = 0 if type(cell) is str else len(cell) - 1   # STAGE 2: *cell* is the ATOM itself for the 0-arity case
    raise LogicException(type_error(
        "callable_control_construct_unsupported", cell,
        f"{context}: {functor}/{arity} is a control construct, and a "
        f"control construct built as a TERM is not callable yet — {remedy} "
        f"(deferred to the ISO-surface phase; see clausal/logic/cells.py "
        f"refuse_control_construct_cell)",
    ))


# The functor of the module-QUALIFIED goal form ``M:G``, which under cells is
# the arity-2 cell ``(":", M, G)``.
QUALIFIED_GOAL_FUNCTOR = ":"

# How many ``:`` layers ``resolve_qualified_goal_cell`` will peel before it
# gives up.  ISO's ``m1:m2:G`` is two; anything approaching this many is a
# runtime-built term, and a CYCLIC one (``V`` bound to ``(":", m, V)``) has no
# bottom at all -- see the ``else`` arm of that function's loop.
MAX_QUALIFICATION_DEPTH = 64


def resolve_qualified_goal_cell(
    cell: Any, context: str, calling_module: Any = None,
    *, call_extra: "int | None" = None, qualified_culprit: bool = False,
    phrase_args: "tuple | None" = None, dialect_gate: bool = True,
) -> tuple:
    """Resolve the module-qualified goal cell ``(":", M, G)`` to ``(module, G)``.

    P3-3 Task 6 (R10) -- this replaces Task 5's stub, which raised an
    ``existence_error`` naming itself so the hand-off would be a symbol rather
    than a grep.  The two callers -- ``solve``'s query path (via
    ``_strip_module_qualification`` and ``_term_to_goal``) and
    ``higher_order._resolve_named_goal`` for the ``call/N`` family -- keep the
    call shape they already had; only the return is new.

    Returns ``(module, inner_goal)``: the :class:`~clausal.logic.database.
    Module` whose database ANSWERS, and the goal to run against it.  The
    caller decides what to do with the module -- ``solve`` compiles the inner
    goal against it, ``call/N`` dispatches in its ``db`` -- which is why this
    function resolves and unwraps but never runs anything.

    NESTING is innermost-wins, ISO's reading of ``m1:m2:G``: the loop below
    peels one qualification per turn, so the LAST module it resolves is the
    one returned.  Every designator in the chain is resolved on the way down,
    though, so an unresolvable OUTER module raises even when the inner one
    would have answered -- ``m1:m2:G`` names two modules and both have to
    exist.  Each layer's designator is resolved with the layer above it as the
    calling module, which is what the diagnostic reports asked it.

    A bare ``str`` inner goal is the zero-arity cell it names: ``M:k`` is
    ``M:k()``, because a ``str`` IS an atom (P3-1 §1b/R2) and an atom in goal
    position names a predicate of the arity its arguments make up -- here,
    none.  Normalising it here is what lets the qualified form spell a /0 goal
    that the unqualified top-level cell path cannot yet spell (see
    ``todo/bare-zero-arity-predicate-body-goal-does-not-compile``).

    Any other inner goal shape (a class-term instance, an
    already-lowered goal node) is handed back UNCHANGED -- deciding what is
    callable is the caller's job, and each caller already has that rule.

    :param cell:           the ``(":", M, G)`` cell.  Callers guard the shape
                           (``:``/2 exactly); anything else comes straight back
                           as ``(None, cell)``.
    :param context:        the calling surface's indicator, for the error's
                           context.
    :param calling_module: the module the qualification was written in, if
                           known -- reported in the diagnostic.
    :param call_extra:     set by a caller that CALLS the goal (``solve``,
                           ``call/N``): how many extra arguments call/N adds
                           to the inner goal (0 for ``solve``/``call/1``).
                           See "A MODULE THAT DOES NOT EXIST" below.
    :raises LogicException: ``existence_error(module, <designator repr'd>)``
                           when a designator in the chain names no module, or
                           when the chain is cyclic / deeper than
                           ``MAX_QUALIFICATION_DEPTH``.

    A MODULE THAT DOES NOT EXIST, when the goal is CALLED (operator ruling
    2026-09-30, Scryer's form): a designator that is an ATOM naming no
    module raises ``existence_error(procedure, Name/Arity)`` for the
    innermost goal -- ``call(nosuchmod:mp(_))`` is
    ``error(existence_error(procedure, mp/1), mp/1)``, and
    ``call(nosuchmod:mp, X)`` is ``mp/1`` -- rather than
    ``existence_error(module, nosuchmod)``: calling ``M:G`` asks for a
    procedure, and there is none.  Only when *call_extra* is given (a
    clause lookup or an assert into ``M:`` is not a call) and only for an
    atom designator whose innermost goal is an atom or a cell that names a
    procedure; a variable, a number, a non-callable or a control-construct
    CELL (``,``/``;``/``->``/``*->``/``\\+``) inside keeps the module error
    (an atom goal, ``true`` included, names a procedure: Scryer reports
    ``nosuchmod:true`` as a missing procedure too), and so does a missing OUTER module of
    ``m1:m2:G`` (every layer is still resolved; ``m2`` would answer).

    An UNBOUND or NON-CALLABLE innermost goal under a missing module
    (operator ruling 2026-10-01, Scryer's terms): ``call(nosuchmod:_)`` is
    ``error(instantiation_error, call/1)`` and ``call(nosuchmod:1)`` is
    ``error(type_error(callable, 1), call/1)`` -- the context is call/N,
    N counting call/N's extras (``call(nosuchmod:_, x)`` is ``call/2``),
    what call/N answers for a module that exists.  phrase/2,3 follow
    Scryer's phrase: ``call/3`` and ``call/1`` (see _raise_if_not_a_goal).

    *qualified_culprit* (phrase/2,3, Scryer's form): the missing procedure
    is reported QUALIFIED, ``existence_error(procedure, nosuchmod:g/2)``,
    with the plain ``g/2`` as the context.

    A MODULE ARGUMENT THAT IS NOT AN ATOM, when the goal is CALLED
    (operator ruling 2026-10-01, Scryer's terms; see
    :func:`_raise_if_bad_module_argument`): ``call(7:foo)`` is
    ``error(type_error(atom, 7), call/0)`` and ``call(_:foo)`` is
    ``error(instantiation_error, call/0)`` -- not the module error.  Any
    layer of a chain counts (``nosuchmod:7:foo`` is the type error too); a
    clause lookup or an assert into ``M:`` (no *call_extra*) is unchanged.
    *phrase_args* (phrase/2,3): the S0/S pair, for Scryer's phrase culprit.

    THE ONE-WAY DEPENDENCY EDGE (operator ruling 2026-10-01; routes 2-4 of
    the dialect gate): when *calling_module* was loaded from Clausal Prolog
    and the module that ANSWERS (the innermost) is a ``.pl`` or Python
    module, the resolution raises ``permission_error(access, prolog_module,
    M)`` (``python_module`` for Python) -- see :mod:`clausal.logic.
    dialect_edge`.  Every run-time builtin that resolves ``M:X`` for a
    clause body (call/N, assert/retract, clause/2, phrase/2,3) passes its
    own database's module here, so this one site gates them all.
    *dialect_gate* False is for Python-side ``solve()`` (route 5: Python is
    the programmer's responsibility by ruling).
    """
    from clausal.logic.solve import resolve_module  # noqa: PLC0415 -- see the
    from clausal.logic.variables import deref       # note in
    #                            refuse_control_construct_cell: importing
    #     ``clausal.logic.solve`` at module scope would close a cycle through
    #     ``clausal.terms``.

    module = None
    goal = cell
    caller = calling_module if dialect_gate else None
    for _ in range(MAX_QUALIFICATION_DEPTH + 1):
        ok, functor = compound_cell_shape(goal)
        if not (ok and functor == QUALIFIED_GOAL_FUNCTOR and len(goal) == 3):
            break
        designator = deref(goal[1])
        if call_extra is None:
            module = resolve_module(designator, calling_module, context)
        elif type(designator) is not str:
            from clausal.logic.exceptions import LogicException  # noqa: PLC0415
            try:
                module = resolve_module(designator, calling_module, context)
            except LogicException as exc:
                if getattr(exc, "sandbox_refusal", False):
                    raise       # the sandbox's refusal, never a lookup miss
                _raise_if_bad_module_argument(
                    cell, call_extra, exc, phrase=qualified_culprit,
                    phrase_args=phrase_args)
                raise
        else:
            from clausal.logic.exceptions import LogicException  # noqa: PLC0415
            try:
                module = resolve_module(designator, calling_module, context)
            except LogicException as exc:
                if getattr(exc, "sandbox_refusal", False):
                    raise       # the sandbox's refusal, never a lookup miss
                _raise_if_bad_module_argument(
                    cell, call_extra, exc, phrase=qualified_culprit,
                    phrase_args=phrase_args)
                _raise_if_not_a_goal(goal[2], call_extra, exc,
                                     phrase=qualified_culprit)
                missing = _missing_procedure_error(
                    goal[2], call_extra, designator, context,
                    qualified=qualified_culprit)
                if missing is None:
                    raise
                raise LogicException(missing) from exc
        calling_module = module
        goal = deref(goal[2])
    else:
        # The peel ran out of turns.  A term is CYCLIC (``V`` bound to
        # ``(":", m, V)`` -- unify builds those, nothing forbids them) or is
        # qualified past any plausible intent; either way there is no
        # innermost module to report, so the goal names none (P3-3 Task 6 fix
        # round 1, F5).  A bounded loop rather than an occurs check: the
        # bound is cheap, needs no bookkeeping, and the diagnostic is the same
        # "this does not name a module" the caller already handles.
        from clausal.logic.exceptions import (  # noqa: PLC0415
            LogicException, existence_error,
        )
        raise LogicException(existence_error(
            "module", repr(cell),
            f"{context}: the module-qualified goal is nested more than "
            f"{MAX_QUALIFICATION_DEPTH} deep, or is cyclic — there is no "
            f"innermost goal to run and so no module that answers",
        ))
    if (caller is not None and module is not None
            and (_sandbox_state.ACTIVE
                 or getattr(caller, _DIALECT_CACHE, None) is not False)):
        # Clausal Prolog may never resolve into a .pl (or Python) module --
        # innermost wins, so ``pl:cp:G`` naming a Clausal Prolog module last
        # is allowed and ``cp:pl:G`` is not.  A .seam/.pl caller pays one
        # cached attribute read (the getattr above), not a call.
        _refuse_dialect_edge(caller, module, context)
    # THE FLIP (spec §6.4): the ``str`` → ``(str,)`` wrap that used to sit
    # here is gone — a ``str`` inner goal is a STRING, which is not callable,
    # and the caller (``_resolve_named_goal`` / ``_term_to_goal``) is where
    # that refusal belongs, uniformly with an unqualified string goal.
    return module, goal


def _raise_if_bad_module_argument(
    cell: Any, call_extra: int, cause: Any,
    *, phrase: bool = False, phrase_args: "tuple | None" = None,
) -> None:
    """Scryer's error when a module argument of the CALLED qualified goal
    *cell* is unbound or is not an atom (operator ruling 2026-10-01); a
    no-op when every designator is an atom or resolves (a ``Module``, an
    imported module object).  Asked only once resolution has already
    failed, so the success path pays nothing.

    Measured on scryer-prolog (N counts the goal's arity plus call/N's
    extras -- Scryer names the call/N it would have run):

      call(7:foo)            error(type_error(atom, 7), call/0)
      call(_:foo)            error(instantiation_error, call/0)
      call(7:foo(a), x)      error(type_error(atom, 7), call/2)
      call(f(x):foo)         error(type_error(atom, f(x)), call/0)
      call(7:(foo(a), foo))  error(type_error(atom, 7), call/1)  (leftmost)
      call(7:_)              error(type_error(callable, 7:_), call/1)
      call(7:1)              error(type_error(callable, 7:1), call/1)
      call(7:_, x)           error(instantiation_error, call/2)
      call(7:1, x)           error(type_error(callable, 1), call/2)
      phrase(7:g, L)         error(type_error(callable, 7:g(L, [])), call/1)
      phrase(7:_, L)         error(instantiation_error, call/3)
      phrase(7:1, L)         error(type_error(callable, 7:1), call/1)

    The INNERMOST bad designator is the one reported (``f(x):_:foo`` is the
    instantiation error, as Scryer has it)."""
    from clausal.logic.solve import resolve_module  # noqa: PLC0415
    from clausal.logic.exceptions import (  # noqa: PLC0415
        LogicException, instantiation_error, type_error,
    )
    layers = []
    goal = deref(cell)
    for _ in range(MAX_QUALIFICATION_DEPTH + 1):
        if type(goal) is tuple and len(goal) < 2:
            return      # () / the reserved 1-tuple: the caller refuses it
        ok, functor = compound_cell_shape(goal)
        if not (ok and functor == QUALIFIED_GOAL_FUNCTOR and len(goal) == 3):
            break
        layers.append(goal)
        goal = deref(goal[2])
    else:
        return              # cyclic / too deep: the resolver's own error
    bad = None
    for layer in reversed(layers):
        designator = deref(layer[1])
        if type(designator) is str:
            continue
        if not is_var(designator):
            try:
                resolve_module(designator)
                continue
            except LogicException:
                pass
        bad = layer, designator
        break
    if bad is None:
        return
    layer, designator = bad
    innermost = layer is layers[-1]
    from clausal.logic.builtins.call_body import (  # noqa: PLC0415
        is_non_callable_term, non_callable_goal_error,
    )
    at = f"call/{1 + call_extra}"
    if is_var(goal) or is_non_callable_term(goal, lists=False):
        if innermost and (call_extra == 0
                          or (phrase and not is_var(goal))):
            # Scryer's call/1 refuses the whole ``M:G``: its module part is
            # no module, so ``M:G`` is not a qualified goal it can run.
            raise LogicException(type_error(
                "callable", (QUALIFIED_GOAL_FUNCTOR, designator, goal),
                "call/1: the module of a qualified goal is not an atom and "
                "its goal is not callable")) from cause
        if is_var(goal):
            raise LogicException(instantiation_error(at)) from cause
        raise LogicException(non_callable_goal_error(
            goal, "call/1" if phrase else at)) from cause
    if phrase and innermost and phrase_args is not None:
        # Scryer's phrase/2,3 builds ``M:NT(.., S0, S)`` and call/1 refuses
        # it whole (``phrase(7:g, L)`` -> type_error(callable, 7:g(L, []))).
        ok, functor = compound_cell_shape(goal)
        if type(goal) is str:
            built = (goal, *phrase_args)
        elif ok and type(functor) is str:
            built = (*goal, *phrase_args)
        else:
            built = None
        if built is not None:
            raise LogicException(type_error(
                "callable", (QUALIFIED_GOAL_FUNCTOR, designator, built),
                "call/1: the module of a qualified nonterminal is not an "
                "atom")) from cause
    at = f"call/{_scryer_call_arity(goal, call_extra)}"
    if is_var(designator):
        raise LogicException(instantiation_error(
            f"{at}: the module of a qualified goal is unbound")) from cause
    culprit = list(chars_text(designator)) if is_chars(designator) \
        else designator
    raise LogicException(type_error(
        "atom", culprit,
        f"{at}: {culprit!r} is not a module name -- the module of a "
        f"qualified goal must be an atom")) from cause


def _scryer_call_arity(goal: Any, call_extra: int) -> int:
    """The N of the ``call/N`` Scryer reports for a qualified goal it could
    not run: the goal's arity plus call/N's extras.  With no extras a
    control construct is not the goal Scryer reports -- it reports the
    leftmost goal it reached (``7:(foo(a), foo)`` is ``call/1``)."""
    if call_extra == 0:
        for _ in range(MAX_QUALIFICATION_DEPTH):
            goal = deref(goal)
            if type(goal) is tuple and len(goal) < 2:
                break
            ok, functor = compound_cell_shape(goal)
            if not ok:
                break
            if (functor in CELL_GOAL_CONTROL_FUNCTORS
                    or (functor == "call" and len(goal) == 2)):
                goal = deref(goal[1])
                continue
            break
    goal = deref(goal)
    if type(goal) is tuple and len(goal) < 2:
        return call_extra
    ok, functor = compound_cell_shape(goal)
    arity = len(goal) - 1 if ok and type(functor) is str else 0
    return arity + call_extra


def _raise_if_not_a_goal(goal: Any, call_extra: int, cause: Any,
                         *, phrase: bool = False) -> None:
    """Scryer's error for an unbound or non-callable innermost goal of a
    call into a missing module: ``instantiation_error`` /
    ``type_error(callable, G)``, context ``call/N`` (N = 1 + extras) -- the
    terms call/N and solve give for a module that exists
    (``call(lists:_)``).  Through phrase/2,3 (*phrase*) Scryer reports the
    non-callable case at ``call/1`` (measured: ``phrase(nosuchmod:1, L)``
    is ``error(type_error(callable, 1), call/1)``; ``phrase(nosuchmod:_,
    L)`` is ``call/3``)."""
    from clausal.logic.exceptions import (  # noqa: PLC0415
        LogicException, instantiation_error,
    )
    goal = deref(goal)
    if type(goal) is tuple and len(goal) < 2:
        return      # () / the reserved 1-tuple: the caller refuses it
    at = f"call/{1 + call_extra}"
    if is_var(goal):
        raise LogicException(instantiation_error(at)) from cause
    from clausal.logic.builtins.call_body import (  # noqa: PLC0415
        is_non_callable_term, non_callable_goal_error,
    )
    if is_non_callable_term(goal, lists=False):
        raise LogicException(non_callable_goal_error(
            goal, "call/1" if phrase else at)) from cause


def _missing_procedure_error(
    goal: Any, call_extra: int, designator: str, context: str,
    *, qualified: bool = False,
) -> Any:
    """``existence_error(procedure, Name/Arity)`` for the innermost goal of
    *goal* (the part of ``M:G`` after a module that does not exist), with
    call/N's *call_extra* arguments counted -- or None when that goal names
    no procedure (a variable, a number, a control construct ...).

    None, too, when the missing module is not the INNERMOST qualifier
    (``nosuchmod:m2:G``): the module that would answer is ``m2``, so there
    is no procedure to name, and the module error stands."""
    goal = deref(goal)
    if type(goal) is tuple and len(goal) < 2:
        return None     # () / the reserved 1-tuple: no goal (the caller says so)
    ok, functor = compound_cell_shape(goal)
    if ok and functor == QUALIFIED_GOAL_FUNCTOR and len(goal) == 3:
        return None
    if type(goal) is str:
        name, arity = goal, 0
    elif (ok and type(functor) is str
            and functor not in CELL_GOAL_CONTROL_FUNCTORS):
        name, arity = functor, len(goal) - 1
    else:
        return None
    from clausal.logic.builtins.call_body import _indicator  # noqa: PLC0415
    from clausal.logic.exceptions import existence_error  # noqa: PLC0415
    arity += call_extra
    if qualified:
        return existence_error(
            "procedure",
            (QUALIFIED_GOAL_FUNCTOR, designator, _indicator(name, arity)),
            f"{name}/{arity}: {designator!r} names no module (resolution "
            f"is lookup-only and never imports), so {designator}:{name}/"
            f"{arity} is no procedure")
    return existence_error(
        "procedure", _indicator(name, arity),
        f"{context}: {designator!r} names no module (resolution is "
        f"lookup-only and never imports), so {designator}:{name}/{arity} "
        f"is no procedure")


def qualify_mangled_goal(goal: Any, db: Any = None) -> Any:
    """A goal whose functor is a MANGLED atom (``module<US>name``, the
    ``-hide`` spelling) as the module-qualified goal ``(":", module_name,
    inner)`` the engine already resolves; anything else comes back untouched.

    W4's Python boundary (ruled 2026-09-22): a predicate HANDLE is the
    module-qualified atom, so a goal built from one -- ``(handle, X)`` from
    the seam, or the bare handle as an arity-0 goal -- carries its module in
    its own spelling and needs no ``module=``.  Pure data: the module is
    named by its dotted string, and ``resolve_qualified_goal_cell`` looks
    that up as it does any designator.  Called at the three entry points
    (``solve``'s goal normalisation, ``call/N``, ``_dispatch_at``).

    WHAT COUNTS AS A HANDLE, in one place: a mangled atom whose module half
    is a LOADED CLAUSAL module (the import name, which for a package-nested
    module is dotted) -- checked via
    ``predicate._db_for_module_name(module_name) is not None``, the same
    "does this module carry a Clausal ``$module``/``db``" idiom
    ``testing.py`` and ``compiler_v2.py`` already use.  ``sys.modules``
    membership alone is NOT enough: it is true of every imported PYTHON
    module (``json``, ``csv``, ``types``, ...), Clausal or not, and a
    mangled atom whose module half collides with one of those would
    wrongly qualify into it (2026-09-23 bug -- see
    ``todo/qualify-mangled-goal-tests-only-sys-modules-2026-09-23.md``).  A
    ``-hide`` data atom carries the BARE declared module name instead,
    which need not be an import name at all; one of those reaching a goal
    position is the pre-existing "atom is not callable" mistake, and it
    comes back untouched here so the caller's existing atom path reports
    it, not a new "no such module" error.
    """
    from clausal.logic.atoms import demangle, is_mangled  # noqa: PLC0415
    from clausal.logic.predicate import (  # noqa: PLC0415
        _owner_db_for_module_name, handle_designator,
    )

    # *db* (optional) is the CALLER's database, the ruling-Q0 hint: a handle
    # naming the caller's own module counts as loaded even when the runner
    # popped it from ``sys.modules``.  The owner is found by the HANDLE-ONLY
    # rule (``_owner_db_for_module_name``: caller's db, by identity,
    # ``sys.modules``, then the handle-owner registry for a popped
    # cross-module owner).  The designator is the dotted name whenever
    # ``sys.modules`` resolves it to that same owner (unchanged pure data);
    # otherwise it is the owner's Module OBJECT (``handle_designator``), so
    # ``resolve_module`` -- the user-designator path, lookup-only in
    # ``sys.modules`` -- is never asked to resolve a popped name.
    if type(goal) is str:
        if is_mangled(goal):
            module_name, name = demangle(goal)
            owner = _owner_db_for_module_name(module_name, db)
            if owner is not None:
                return (QUALIFIED_GOAL_FUNCTOR,
                        handle_designator(module_name, owner), name)
        return goal
    is_cell, functor = _cell_shape(goal) if isinstance(goal, tuple) else (False, None)
    if is_cell and type(functor) is str and is_mangled(functor):
        module_name, name = demangle(functor)
        owner = _owner_db_for_module_name(module_name, db)
        if owner is not None:
            return (QUALIFIED_GOAL_FUNCTOR,
                    handle_designator(module_name, owner), (name, *goal[1:]))
    return goal


def make_cell(functor: Any, *args: Any) -> tuple:
    """Construct a cell ``(functor, *args)``, enforcing the slot-0 ruling.

    *functor* must be one of:

      - a ``str`` -- interned via ``sys.intern`` as a convenience (see the
        module docstring's BRIDGE-ENTRY RULING: ``is_cell`` does not
        require this, ``make_cell`` does it only to make repeated
        same-functor cells cheaper to compare/store).
      - ``TUPLE_TAG`` (the ``tuple`` type object) -- for tuple-as-data cells.

    Anything else (``int``, a class other than ``tuple``, ``None``, an
    unbound or bound ``Var``, ...) raises ``TypeError``. A ``Var`` functor
    is DEPRECATED per §1b (see the module docstring) -- it is no longer a
    legal slot-0 value, regardless of whether it is bound: higher-order
    metaprogramming over cells routes through ``functor/3`` / ``=../2`` /
    ``call/N`` instead (P3-3).
    """
    if isinstance(functor, str):
        functor = sys.intern(functor)
    elif functor is TUPLE_TAG:
        pass
    else:
        raise TypeError(
            "make_cell: functor must be a str or the `tuple` type object "
            f"(TUPLE_TAG); got {functor!r} ({type(functor).__name__}) -- "
            "a Var functor is deprecated (§1b), use functor/3 or =../2 for "
            "higher-order construction over cells"
        )
    return (functor, *args)


def make_tuple_cell(*elems: Any) -> tuple:
    """Construct a tuple-DATA cell ``(tuple, e1, ..., en)``.

    Equivalent to ``make_cell(TUPLE_TAG, *elems)``, spelled out for callers
    building tuple-as-data cells (no functor validation to speak of --
    ``TUPLE_TAG`` is always valid).
    """
    return (TUPLE_TAG, *elems)


def is_cell(x: Any) -> bool:
    """True if *x* is shaped like a cell.

    A cell is a non-empty ``tuple`` (exactly ``type(x) is tuple`` -- a
    ``tuple`` subclass, e.g. a namedtuple, is deliberately excluded; term
    instances in this engine are dataclasses / ``PredicateMeta`` instances,
    never tuple subclasses, so this cannot collide with them) whose slot 0,
    read RAW (no deref -- §1b/Task 5), is a ``str`` or the ``tuple`` type
    object. A Var functor -- bound or not -- is DEPRECATED (see the module
    docstring) and is no longer cell-shaped at all: a tuple built with one
    falls through to plain-tuple handling everywhere, the same as any
    other non-str, non-``tuple`` tag.

    This is a SHAPE-only test -- see the module docstring's THE DISCIPLINE
    note: a plain user tuple like ``("hello", 1)`` also answers ``True``
    here. That is the rule for this bridge stage, not a bug.
    """
    return _cell_shape(x)[0]


def cell_functor(c: tuple) -> Any:
    """Return the functor slot (slot 0) of cell *c*, read RAW.

    §1b/Task 5: no deref -- a legally-constructed cell's slot 0 is always
    already a ``str`` or the ``tuple`` type object (``make_cell`` enforces
    this; a Var functor is deprecated and never reaches here). No shape
    validation -- callers that don't already know *c* is cell-shaped
    should check ``is_cell(c)`` first.
    """
    return c[0]


def cell_args(c: tuple) -> tuple:
    """Return the argument slice (slots 1..) of cell *c*, as a tuple."""
    return c[1:]


def cell_arity(c: tuple) -> int:
    """Return the arity (argument count) of cell *c*."""
    return len(c) - 1


# ── Selective ground-cell interning (Task 4) ──────────────────────────────
#
# Spec: ``docs/superpowers/plans/2026-09-03-phase2-bridge.md`` Task 4.
#
# ``intern_cell`` recursively collapses structurally-equal, FULLY-GROUND
# cells to the same tuple object via a module-level table -- the tabling
# freeze boundary (``clausal.logic.tabling.TableEntry.add_answer``) is the
# hook that calls it, gated by ``is_intern_enabled()`` below (default OFF).
#
# Scope, per the plan's Global Constraints ("Interning (Task 4) applies
# ONLY to fully-ground cells ... a Var anywhere disqualifies -- Var.__hash__
# stays untouched this stage"):
#
#   - Only CELLS are ever looked up in / stored into the intern table.
#     Class terms, atoms, scalars, lists, dicts -- everything that is not
#     ``is_cell``-shaped -- passes through ``intern_cell`` UNCHANGED and
#     never touches the table.
#   - "Ground" here means: no ``Var`` reachable by walking slot 0 or the
#     argument slots of the cell and any CELL nested inside it. A ``Var``
#     found anywhere in that walk disqualifies the whole cell (and every
#     cell containing it) from interning -- it is returned unchanged,
#     object-identical to what was passed in. A non-cell argument (e.g. a
#     list) is not walked further for embedded Vars -- this stage's cells
#     are built from declared functors and scalars/cells per Task 2's
#     emission rules, so that gap is not exercised by this bridge's corpus.
#   - Interning never calls ``Var.__hash__``: ``_try_intern`` below is
#     STRICTLY groundness-first -- it never calls ``hash()``/``==`` (via a
#     dict operation) on ANY value until every value reachable inside it
#     has already been proven Var-free by this same walk. A tuple's
#     native ``hash()`` recurses through nested tuples calling ``hash()``
#     on every element, so a table lookup attempted on a not-yet-proven
#     substructure would transitively hash any ``Var`` nested inside it --
#     an earlier version of this function took exactly that shortcut (a
#     "does *c* already match a previously-interned value?" pre-check
#     before walking *c*'s own structure) and was rejected on review
#     because it violated this invariant, even though it happened to be
#     safe in practice (default ``object.__hash__`` on a Var never raises,
#     and a Var-containing key can never collide with a stored ground
#     one). See the task report's "TDD" section for the full trace.
#
# ITERATIVE, NOT RECURSIVE (also load-bearing): ``_try_intern`` walks
# post-order using an explicit stack, not Python recursion. A tabled
# predicate's cons-chain grows ONE cell per subgoal, bottom-up (``Nats(K,
# cons(K, T))`` where ``T`` is subgoal ``K-1``'s already-frozen answer) --
# and ``freeze_args`` (the tabling freeze boundary this hook sits behind,
# Python fallback or C twin -- see ``clausal.logic.solve._deref_walk_py``)
# unconditionally rebuilds a brand-new nested tuple on every call, even
# for substructure that is already fully ground. So *T* arriving at
# subgoal K is always a length-(K-1) chain that must be groundness-checked
# in full (no identity or value shortcut is available before groundness
# is established -- see above), and a naive Python-recursive walk would
# recurse that many call frames deep on EVERY subsequent cell: for a long
# chain (n ~ 1500, this stage's target size) that is enough, added to the
# tabling trampoline's own already-deep call stack, to raise
# ``RecursionError`` -- hit for real during this task's own measurement
# dry run before this function was made iterative; see the task report's
# "TDD" section. An explicit Python-``list``-based stack has no such
# limit (bounded by available memory, not ``sys.getrecursionlimit()``).
#
# Net effect: checking/caching a K-deep chain costs O(K) work on every
# ``add_answer`` call (O(depth^2) total over a chain of that depth, same
# order as the O(depth^2) the walk/freeze work already costs by design at
# each level) -- slower than the (rejected) value-shortcut version, but
# correct per the ``Var.__hash__`` invariant and immune to
# ``RecursionError`` regardless of chain depth.
def intern_cell(c: Any) -> Any:
    """Recursively intern *c* bottom-up, ground cells only.

    - Not a cell at all (``is_cell(c)`` False) -> returned unchanged. Class
      terms, atoms, and every other non-cell value take this path; they
      never touch ``_INTERN_TABLE``.
    - A cell that is not fully ground (a ``Var`` reachable anywhere in its
      cell structure) -> returned unchanged, object-identical to *c*.
      Non-ground cells are never cached (their shape can still change via
      later unification), and no ``Var`` anywhere in *c* is ever hashed
      while establishing this (see the section docstring above).
    - A fully-ground cell -> its nested cell arguments are interned first
      (bottom-up), then ``(functor, *args)`` is looked up in the shared
      table; the first cell built with a given ground shape becomes the
      canonical object every structurally-equal cell thereafter collapses
      to.

    Hashing a ground cell can still raise ``TypeError`` (e.g. a ``list``
    argument -- ground but unhashable): guarded per level with try/except,
    falling back to returning that level's cell unchanged rather than
    raising or caching a bogus entry.
    """
    if not is_cell(c):
        return c
    ok, result = _try_intern(c)
    return result if ok else c


# The intern table itself: canonical-tuple -> the SAME canonical-tuple
# object (a set would do the membership check, but storing the value lets
# ``.get`` return the canonical object in one lookup).
_INTERN_TABLE: dict[tuple, tuple] = {}


def clear_intern_table() -> None:
    """Empty the intern table.

    Test isolation: the table is process-global (module-level), so a test
    that asserts identity via interning must not see another test's
    entries -- call this in setup/teardown. Also useful between benchmark
    rounds that must not let one round's interned answers keep an earlier
    round's table entries "warm."
    """
    _INTERN_TABLE.clear()


# Sentinel for "this node's subtree contains a Var" in ``_try_intern``'s
# ``result_of`` map -- distinct from every real value a cell could ever
# resolve to (never returned to a caller, never stored in
# ``_INTERN_TABLE``, so no risk of confusion with a genuine cell answer).
_NOT_GROUND = object()


def _try_intern(root: tuple) -> tuple[bool, Any]:
    """Iterative, post-order, groundness-first combined check-and-intern
    pass over cell *root*. Returns ``(True, interned_value)`` if *root* is
    fully ground (recursively) and has been looked-up/stored in
    ``_INTERN_TABLE``; ``(False, None)`` if a ``Var`` was found anywhere
    in the reachable structure -- the caller (``intern_cell``) returns
    *root* itself unchanged in that case.

    Caller has already proven ``is_cell(root)``; this function does not
    re-check that for *root* itself (only for nested args, via ``is_cell``
    below). See the section docstring above for why this walk is BOTH
    iterative (an explicit stack, not Python recursion -- avoids
    ``RecursionError`` on a long chain) and groundness-first (never
    hashes/looks-up a value until everything nested inside it has already
    been proven Var-free -- never touches ``Var.__hash__``).

    Stack entries are ``("visit", node)`` -- node's children still need
    processing before node itself can be resolved -- or ``("finish",
    node)`` -- every cell-shaped child of node already has an entry in
    ``result_of`` (real value if ground, ``_NOT_GROUND`` if not), so
    node's own result can now be computed.
    """
    result_of: dict[int, Any] = {}  # id(cell) -> interned value or _NOT_GROUND
    stack: list[tuple[str, tuple]] = [("visit", root)]
    while stack:
        action, node = stack.pop()
        node_id = id(node)
        if action == "finish":
            raw_functor = node[0]
            functor = deref(raw_functor)
            # Dead post-§1b (Task 5 review, optional courtesy note): every
            # `node` reaching this walk already passed `is_cell`, which now
            # guarantees a str/TUPLE_TAG functor -- `is_var(functor)` can
            # never be True here any more. Left in place rather than
            # removed: harmless, and removing it is out of this task's
            # scope (Task 4's interning walk, gated OFF by default).
            if is_var(functor):
                result_of[node_id] = _NOT_GROUND
                continue
            changed = functor is not raw_functor
            new_args = []
            ground = True
            for a in node[1:]:
                da = deref(a)
                if is_var(da):
                    ground = False
                    break
                if is_cell(da):
                    na = result_of.get(id(da), _NOT_GROUND)
                    if na is _NOT_GROUND:
                        ground = False
                        break
                else:
                    na = da
                if na is not a:
                    changed = True
                new_args.append(na)
            if not ground:
                result_of[node_id] = _NOT_GROUND
                continue
            candidate = node if not changed else (functor, *new_args)
            try:
                existing = _INTERN_TABLE.get(candidate)
            except TypeError:
                # Some leaf under this cell isn't hashable (e.g. a list
                # argument, ground but unhashable) -- this node is still
                # "ground" (no Var was found), so record success, but
                # with THIS level built fresh here (nested cells already
                # interned where possible) rather than cached or raising.
                result_of[node_id] = candidate
            else:
                if existing is not None:
                    result_of[node_id] = existing
                else:
                    _INTERN_TABLE[candidate] = candidate
                    result_of[node_id] = candidate
        else:  # "visit"
            if node_id in result_of:
                continue  # already resolved via an earlier stack entry
            stack.append(("finish", node))
            raw_functor = node[0]
            functor = deref(raw_functor)
            # Dead post-§1b, same reasoning as the "finish" branch above.
            if is_var(functor):
                continue  # "finish" will re-detect this cheaply and stop
            for a in node[1:]:
                da = deref(a)
                if is_var(da):
                    continue  # "finish" will re-detect this cheaply too
                if is_cell(da) and id(da) not in result_of:
                    stack.append(("visit", da))

    final = result_of.get(id(root), _NOT_GROUND)
    if final is _NOT_GROUND:
        return False, None
    return True, final


# Module-level switch gating the tabling freeze-boundary hook
# (``clausal.logic.tabling.TableEntry.add_answer``). Default OFF so the
# DEFAULT-PATH INVARIANT holds unconditionally: nothing calls
# ``set_intern_enabled(True)`` except Task 4's own tests and
# ``benchmarks/workloads.py``'s ``bench_struct_tabling_tagged(..., intern=True)``.
_INTERN_ENABLED = False


def is_intern_enabled() -> bool:
    """True if the tabling freeze-boundary hook should call ``intern_cell``
    on cell-shaped answer args. Read live (a function, not a cached
    import) so callers see toggles made after their own import."""
    return _INTERN_ENABLED


def set_intern_enabled(value: bool) -> None:
    """Flip the module-level interning switch. Test/benchmark use only --
    no production code path calls this."""
    global _INTERN_ENABLED
    _INTERN_ENABLED = bool(value)


# ── Compiled-constant certificate (dumb seam, 2026-09-26) ──────────────────
#
# A goal-position seam hands an answer back BY IDENTITY only when it can
# prove the object holds no ``Var`` -- bound or unbound -- because Var
# equality is identity and backtracking rebinds.  The one certificate that
# costs nothing at export time is PROVENANCE: a tuple or frozenset that the
# compiler baked into a clause's code object as an ``ast.Constant`` can never
# contain a Var (``compile`` refuses one), is immutable, and is the very
# object every call hands out (probe 2026-09-26: a fact's cell answer is the
# same object across calls).  ``codegen.functiondef_to_function`` registers
# every such constant here, recursively; ``seam.export`` asks
# ``is_compiled_constant``.
#
# LEAK-FREE BY CONSTRUCTION (roborev 252/253): an entry maps the constant's
# id to a WEAK reference to the code object that owns it, with a callback
# that removes the entry when that code object dies.  Nothing here keeps a
# constant alive: a dynamic predicate that recompiles on every assertz
# drops its old code objects, and their entries go with them.  Sound
# because an entry whose referent is alive names a code object that holds
# the constant in ``co_consts`` (or inside a constant it holds), so the
# constant is alive and its id cannot belong to any other object; an entry
# whose referent is gone answers False, and losing a certificate only costs
# the export a probe or a copy.

_COMPILED_GROUND: dict = {}


def register_compiled_constants(code) -> None:
    """Record every tuple / frozenset constant of *code*, recursively
    through nested tuples; a nested code object is registered on its own
    weak reference (it can outlive or predecease its parent)."""
    import weakref  # noqa: PLC0415
    table = _COMPILED_GROUND
    ids: list = []
    stack = list(code.co_consts)
    while stack:
        obj = stack.pop()
        t = type(obj)
        if t is tuple or t is frozenset:
            ids.append(id(obj))
            stack.extend(obj)
        elif hasattr(obj, "co_consts"):
            register_compiled_constants(obj)
    if not ids:
        return

    def _drop(ref, ids=ids, table=table):
        for i in ids:
            if table.get(i) is ref:
                del table[i]        # only our own entry: a re-registration may own it now

    ref = weakref.ref(code, _drop)
    for i in ids:
        table[i] = ref


def is_compiled_constant(obj) -> bool:
    """True iff *obj* IS a constant of a LIVE generated code object."""
    ref = _COMPILED_GROUND.get(id(obj))
    return ref is not None and ref() is not None


def is_pool_seeded_atom(namespace, name: str) -> bool:
    """True when *namespace* binds *name* to the plain atom of that spelling
    ONLY because the process-wide atom pool seeded it there: the module
    neither declares the atom (``DECLARED_ATOMS_KEY``) nor imports the name
    (``IMPORT_FROM_KEY``).

    Every module dict is seeded from that pool, so once ANY module declares
    ``-private([nosuch])``, every other module has an attribute ``nosuch``
    too -- and a qualified call ``m.nosuch(1)`` read it as a data reference
    of m's, so its error depended on what an unrelated module declared.

    An atom a module only USES bare (auto-accepted, recorded nowhere) is
    counted as seeded too: ``m.red(1)`` then raises the unknown-procedure
    error rather than the data-reference one.  Both are
    ``existence_error(procedure, red/1)``; only the message and the Python
    type differ, and the answer no longer depends on load order.
    """
    if not isinstance(namespace, dict):
        return False
    value = namespace.get(name)
    if type(value) is not str or value != name:
        return False
    if name in (namespace.get(DECLARED_ATOMS_KEY) or ()):
        return False
    # Declared or defined under the name at ANY arity (a fielded data
    # functor such as ``edge(A, B)``, a ``name/N`` export, a row): the
    # module's own binding, whose "declared as DATA" diagnostic must stand.
    db = getattr(namespace.get("$module"), "db", None)
    arities = getattr(db, "declared_arities_for", None)
    if arities is not None and arities(name):
        return False
    for entry in namespace.get(IMPORT_FROM_KEY) or ():
        if entry and entry[0] == name:
            return False
    return True
