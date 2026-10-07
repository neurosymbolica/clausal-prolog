"""List-structure dispatch helpers.

Helpers used by the predicate-compilation entrypoints to detect whether
the same head-argument position always destructures to a list in every
clause (``_find_list_dispatch_pos``), and to emit wildcard captures +
list-guard checks for those positions (``_build_list_dispatch_guard``).

``_lift_clause_at_pos`` rewrites a clause so the given position is a
wildcard capture whose structure is checked at runtime instead of in
the match pattern — used together with ``_build_list_dispatch_guard``.

P3-2 Task 5 carry-forward consolidation: every raw cell-shape test in this
module (``_carries_an_uninjected_head_literal``, the raw-cell gate in
``_lift_clause_at_pos``, ``_nested_term_carries_a_literal``,
``_lifted_head_arg_needs_deep_gate``) routes through
``cells._cell_shape`` rather than re-spelling ``type(x) is tuple and
(type(x[0]) is str or x[0] is TUPLE_TAG)`` locally — one home for the
shape discipline, shared with ``head_match``'s live-cell branch and
``globals_env._walk_head``'s cell branch. No behavior change: ``cells.
_valid_functor_slot`` is EXACT-type (``type(slot0) is str``, review fix
round 1 -- matches this module's own two ``type(term[0]) is str`` sites
that predated the fold), so the consolidation is byte-for-byte equivalent
to every one of this module's original spellings, not merely equivalent
in the cases this suite happens to exercise.
"""

from __future__ import annotations

import ast
from typing import Any

from clausal.logic.variables import is_var, deref  # noqa: F401
from clausal.terms import (
    Call, LoadName, LoadAttr,  # noqa: F401
    PyThunk, Unify,
    DictTerm, SetTerm,
)
from clausal.pythonic_ast.nodes import StarUnpack  # noqa: F401
from clausal.logic.predicate import is_term_instance, term_field_names
from clausal.logic.database import Clause

from ._ast_helpers import _name, _call, _assign, _if, _MARK_PREFIX  # noqa: F401
from .head_match import (
    head_to_match_pattern, compile_head_to_match_case, _head_arg_patterns,
    _wrap_yields_with_output_guards,
)
from .terms_to_ast import (  # noqa: F401
    term_to_ast_expr, cell_signature_for_name, _is_opaque_head_literal,
)
from clausal.logic.cells import _cell_shape, cell_args, cell_functor, make_cell
from .arg_index import _bytelist_to_bytes_or_none


# ── Phase 5: deep structural indexing helpers ──────────────────────────────────


def _get_head_arg(clause: Clause, pos: int) -> Any:
    """Return the argument at position *pos* from the clause head (or None).

    Three head shapes, and the CELL is one of them (P2 head flip, 2026-09-19).
    It was not, for two releases: a stored head was a predicate instance,
    ``database._stored_head_key`` refused a cell-headed
    ``Clause`` outright, and this function's missing cell branch was the
    reason it named — a cell head compiled to a predicate that answered with
    its argument UNBOUND.  Both are gone now: a head IS the functor-first cell
    and this reads it positionally, like the other two.
    """
    head = clause.head
    if _cell_shape(head)[0]:                        # P2: a head is a cell
        args = cell_args(head)
        return args[pos] if pos < len(args) else None
    # W4a: no third head shape.  The predicate-INSTANCE arm that stood here
    # went with the instance path, and it never served the OTHER shape
    # `is_term_instance` admits -- a @dataclass head -- because
    # the rebuild it fed called `_clausal_head`, which a dataclass has not
    # got.  So an unsupported head is "not liftable", which is what the
    # callers already handle.
    return None


def _carries_an_uninjected_head_literal(term: Any) -> bool:
    """True if lifting *term* into a head would emit a pattern naming a
    ``$headlit_<id>`` global that nothing injected.

    P3-2 Task 3, found by driving a lifted bucket rather than by reading it.
    ``_collect_globals_info`` walks the PRE-lift clauses, and only its HEAD
    walker records ``$headlit_<id>`` entries — a body walk records call
    targets and ``_pyt_<id>`` thunks instead.  So a value that
    ``head_to_match_pattern`` compiles to an opaque-literal capture is
    reachable from a body ``Unify`` but has no global if the lift moves it
    into the head afterwards, and the bucket raises ``NameError`` the first
    time it is entered.

    A nested ``PyThunk`` (a quantity/currency literal, an f-string, a ``++()``
    escape) is the reachable case from ``.clausal`` source, and it is also
    WRONG on its own terms — the same reason the top-level ``PyThunk`` skip
    above exists: nothing on the head-match path evaluates a thunk, so the
    pattern would guard against the thunk OBJECT and the clause could never
    fire.  This is that skip, applied one level down.

    Deliberately scoped to the ``Call`` branch that Task 3 opened.

    A CELL nested inside the reference is recursed INTO rather than treated
    as a leaf: the live-cell branch of ``head_to_match_pattern`` matches it
    structurally, above the opaque-literal capture, so it needs no injected
    global of its own (the tuple-DATA tag names ``$cells``, which the
    compilation injects unconditionally).
    """
    if isinstance(term, PyThunk):
        return True
    if isinstance(term, Call):
        return (
            any(_carries_an_uninjected_head_literal(a) for a in term.args)
            or any(_carries_an_uninjected_head_literal(kw.value)
                   for kw in (term.kwargs or []))
        )
    if isinstance(term, list):
        return any(_carries_an_uninjected_head_literal(e) for e in term)
    if _cell_shape(term)[0]:
        return any(_carries_an_uninjected_head_literal(e) for e in term[1:])
    return _is_opaque_head_literal(term)


def _lift_clause_at_pos(clause: Clause, pos: int,
                        globals_: dict | None = None) -> Clause:
    """Phase 8: lift the body Unify for head position *pos* into the head.

    in_ bucket compilation contexts the indexed argument is already guaranteed
    ground by the dispatch layer.  Any leading body ``Unify(Var_at_pos, val)``
    is therefore redundant and can be absorbed into the head, letting
    ``head_to_match_pattern`` emit a ``MatchValue``/``MatchClass`` pattern
    rather than a wildcard capture.  This eliminates one ``trail.mark()`` +
    ``unify(...)`` + ``trail.undo()`` triple per clause per invocation.

    The transformation is a no-op when:
    - the head arg at *pos* is already a concrete term (not a Var), or
    - no matching ``Unify`` is found in the body's clean prefix (the
      contiguous run of ``Unify`` goals before the first non-``Unify`` goal), or
    - the lifted term is a ``bytes`` literal (Phase 2 Task 8 / F095, narrowed
      by R8 — §1b): lifting would emit a ``MatchValue`` pattern that uses
      ``==`` for the head match, which fails the codes-model contract when
      the caller arrives via a coalesced bytes/byte-list bucket (e.g. a
      caller passing ``[97, 98, 99]`` reaching a bucket containing a clause
      originally keyed under ``b"abc"``).  Leaving bytes unlifted keeps the
      body ``Unify`` in place where runtime ``unify`` correctly handles the
      bytes↔codes duality.  The ``str`` half of this skip is RETIRED (R8,
      P3-2 Task 4): P3-1 retired str~list unification, so a str head arg is
      no longer coalesced with any char-list bucket and lifting it is safe.

    *globals_* is the namespace the lifted head will be MATCHED against —
    pass the same dict ``head_to_match_pattern`` will get (the compilation's
    ``base_globals``), so the two halves cannot disagree about what a name
    means.  It is what decides the ``Call(LoadName)`` case below.

    Only called from the indexed bucket path — the fallback function always
    uses the original unlifted clauses.
    """
    head = clause.head
    # Extract the head arg at pos
    if _cell_shape(head)[0]:                      # P2: a head is a cell
        cargs = cell_args(head)
        if pos >= len(cargs):
            return clause
        head_arg = deref(cargs[pos])
    else:
        return clause          # W4a: see _head_arg_at -- a cell

    # Only lift when the head arg is an unbound Var
    if not is_var(head_arg):
        return clause
    vid = head_arg._id

    # Scan the body clean prefix for Unify(Var_vid, term) or Unify(term, Var_vid)
    # Stop at the first non-Unify goal (that is the clean-prefix boundary).
    unify_idx = None
    lift_term = None
    for i, goal in enumerate(clause.body):
        if not isinstance(goal, Unify):
            break  # end of clean prefix
        left_d = deref(goal.left)
        right_d = deref(goal.right)
        if is_var(left_d) and left_d._id == vid and not is_var(right_d):
            unify_idx = i
            lift_term = goal.right   # use original (not deref'd) for nested Vars
            break
        if is_var(right_d) and right_d._id == vid and not is_var(left_d):
            unify_idx = i
            lift_term = goal.left
            break
        # Other Unify for a different var — keep scanning

    if unify_idx is None:
        return clause  # no liftable unification found

    # Phase 2 Task 8 (F095), narrowed by R8 (§1b, P3-2 Task 4): skip the
    # lift when the lifted term is a bytes literal.  See docstring above for
    # the codes-model rationale — lifting a bytes literal would emit a
    # ``MatchValue`` head pattern that breaks byte-list callers reaching
    # this clause via the coalesced bytes/byte-list bucket built by
    # ``arg_index._arg_to_index_key``.  The str half of this skip is gone:
    # P3-1 retired str~list unification, so a str head arg is never
    # coalesced with a char-list bucket and lifting it is correct.
    if isinstance(lift_term, bytes):
        return clause

    # Skip the lift when the lifted term is a ground python ``list`` literal.
    #
    # NEW finding, made by DRIVING the repro in
    # todo/first-arg-indexing-str-caller-still-reaches-list-fact-2026-09-04.md
    # after the R8 retirement above, not by reading code: retiring
    # ``_charlist_to_str_or_none`` does not, by itself, make the todo's str
    # caller symmetric with its list caller. The mechanism is one level
    # deeper than the todo's own hypothesis (which pointed at
    # ``_normalize_dataclass_fact`` hoisting — traced and ruled out: str and
    # list literal fact heads are hoisted identically, and that is not where
    # the asymmetry comes from).
    #
    # A GROUND list literal fact (``Foo(['a','b','c'])``, no Vars/StarUnpack)
    # is hoisted to Var + body ``Unify`` by ``_normalize_dataclass_fact``,
    # exactly like a str literal fact. Once its head key is ``_INDEX_VAR``
    # (true for any str-content list post-R8 — see ``_arg_to_index_key``),
    # ``_build_arg_index`` treats it as a "default" clause and MERGES it into
    # EVERY specific-key bucket, including a same-length str literal's own
    # bucket (e.g. a 3-char ``"abc"`` bucket also carries the 3-element
    # ``['a','b','c']`` fact). Lifting the list here turns its head into a
    # sequence PATTERN (``case [_lcap0]: ... $head_list_unify_input(...)``),
    # and ``_head_list_unify_input_py``/its C twin still implement the
    # pre-P3-1 "a string is a list of its chars" contract for HEAD-PATTERN
    # destructuring (see docs/strings_as_lists.md, "Pattern Matching") — a
    # SEPARATE code path from the ``_variables.c`` ``do_unify`` cons rule
    # P3-1 retired, and untouched by that retirement. So the lifted pattern
    # wrongly accepts a same-length str/bytes caller that reaches this
    # bucket only because the list was merged in as a "matches anything"
    # default, giving the str caller a second, spurious solution that the
    # list caller never gets back (a str-headed clause's own lifted pattern
    # is a plain ``MatchValue`` — equality-only, no reciprocal leniency).
    #
    # Leaving the body ``Unify`` in place uses the real runtime ``unify()``
    # instead, which correctly enforces §1b ("lists unify with lists, str
    # unifies with str") — matching what the un-indexed fallback already
    # does for this same clause. This is deliberately narrow: a genuine
    # ``[H, *T]``-style pattern (containing a Var or ``StarUnpack``) is never
    # hoisted by ``_normalize_dataclass_fact`` in the first place (only
    # GROUND lists are), so it never reaches this function at all — the
    # documented "Pattern Matching" string-destructuring feature for
    # written-with-vars list patterns is untouched by this skip.
    #
    # Narrowed to lists that are NOT byte-list-coalescible
    # (``_bytelist_to_bytes_or_none(lift_term) is None``): a list of ints in
    # [0, 255] keys as the joined ``bytes`` value in ``_arg_to_index_key`` —
    # a SPECIFIC key, not ``_INDEX_VAR`` — so it is never merged as a
    # "matches anything" default into a bucket of a different type; the only
    # caller that can ever reach its bucket is one that already shares that
    # exact bytes value (the KEPT bytes~codes coalescing), which
    # ``_head_list_unify_input_py`` implements correctly. Lifting it is safe
    # and already relied upon (``test_list_dispatch_rebuilds_term_instance_
    # head_at_pos`` in tests/test_funnel_accessors.py lifts a plain
    # ``[1, 2, 3]``).
    if isinstance(lift_term, list) and _bytelist_to_bytes_or_none(lift_term) is None:
        return clause

    # Skip the lift when the lifted term is a PyThunk (quantity/currency
    # literal, f-string, ``++()`` escape) — the Unify being lifted is the one
    # ``_normalize_structural_head_args`` created precisely to keep the thunk
    # out of the head: ``head_to_match_pattern`` has no branch that evaluates
    # a thunk, so lifting it back re-creates the dead-clause capture that the
    # hoist fixed.  The body ``Unify`` evaluates the thunk at runtime instead.
    if isinstance(lift_term, PyThunk):
        return clause

    # Skip the lift when the lifted term is a bare name reference
    # (``LoadName('Red')`` / ``LoadAttr(mod, 'Red')``) — an unresolved 0-arity
    # atom, e.g. the RHS of the ``Unify`` that a keyword-atom fact
    # ``Color(C=Red)`` compiles to.  ``head_to_match_pattern`` would emit a
    # ``MatchClass(LoadName, ...)`` pattern that no runtime value matches (the
    # reference resolves to a ``PredicateMeta`` atom, never a ``LoadName``
    # node), so the bucket would yield nothing.  Leaving the body ``Unify`` in
    # place lets the runtime resolve the reference to the atom and unify it.
    if isinstance(lift_term, (LoadName, LoadAttr)):
        return clause

    # A compound reference (``Call(LoadName('point'), …)`` — the shape every
    # compound written in ``.clausal`` source has).  Whether it may be lifted
    # is decided HERE, once, by asking what the name means.
    #
    # P3-2 Task 3.  Pre-flip this was an unconditional refusal, and the reason
    # given was about the bucket's globals: ``_collect_globals_info`` ran on
    # the pre-lift clauses, where the functor lived in a body ``Unify`` and was
    # recorded as a call *target*, not as a head term *class*, so
    # ``head_to_match_pattern`` could not resolve the ``LoadName`` and fell
    # back to ``MatchClass(Call, …)`` — a pattern no runtime term matches, so
    # the bucket yielded nothing.
    #
    # A DATA functor reference dissolves that reason entirely: it compiles to
    # a cell, and a cell pattern is a plain sequence LITERAL —
    # ``case ('point', x, y)`` resolves nothing at match time.  The only
    # resolution left is the one done right here, at LIFT time, and it reads
    # the full module namespace rather than the bucket's collected globals.
    #
    # Still refused, for the same reason as before:
    # * a name bound to a ``PredicateMeta`` (R6b: a ``name/arity`` export
    #   declares a predicate, and a predicate reference has no cell pattern),
    # * a name nothing resolves — no namespace, no registry entry, no class,
    # * a ``Call(LoadAttr(...))`` chain: ``head_to_match_pattern`` has a
    #   ``Call(LoadName)`` branch and no ``LoadAttr`` one, so lifting one would
    #   re-create exactly the dead ``MatchClass(Call, …)`` this refusal
    #   existed to avoid.  (A module-qualified reference reaches the term world
    #   as a single DOTTED ``LoadName`` — see ``_resolve_functor_binding`` —
    #   so R5's cross-module case goes through the branch above, not here.)
    # * a reference with an OPAQUE value nested anywhere inside it — see
    #   ``_carries_an_uninjected_head_literal``.
    #
    # In every refused case the body ``Unify`` stays where it is and the
    # runtime resolves the reference, exactly as the non-indexed fallback path
    # does; bucket SELECTION still keys the clause correctly via
    # ``arg_index._arg_to_index_key``.
    if isinstance(lift_term, Call) and isinstance(
        lift_term.func, (LoadName, LoadAttr)
    ):
        if not isinstance(lift_term.func, LoadName):
            return clause
        if cell_signature_for_name(lift_term.func.name, globals_) is None:
            return clause
        if _carries_an_uninjected_head_literal(lift_term):
            return clause

    # A RAW CELL as the lifted term, carrying an opaque value in a slot.
    #
    # Fix round 1, third instance of the same fault.  The head-walker fix in
    # ``globals_env._walk_head`` injects a ``$headlit_<id>`` per opaque slot
    # of a cell it finds in a HEAD -- but a lifted cell was in the BODY when
    # the collector ran, so the walker never saw it and the gate is what has
    # to cover it, exactly as for the ``Call`` case above.
    #
    # Unreachable today, and measured so rather than assumed:
    # ``arg_index._arg_to_index_key`` does not key a raw cell, so a
    # cell-valued position builds no buckets at all and nothing calls the
    # lift on one.  It goes live the moment a producer or Task 4 changes
    # that, which is why the gate is here now instead of in a todo.
    if _cell_shape(lift_term)[0]:
        if _carries_an_uninjected_head_literal(lift_term):
            return clause

    # Rebuild head with lift_term at pos
    if _cell_shape(head)[0]:                      # P2: a head is a cell
        new_args = list(cell_args(head))
        new_args[pos] = lift_term
        new_head = make_cell(cell_functor(head), *new_args)
    else:
        # Unreachable: the gate above returned `clause` for every head that is
        # not a cell.  Loud rather than silent if the two
        # ever drift apart again -- which is the defect this shape had before
        # W4a, when the gate admitted a shape the rebuild could not build.
        raise TypeError(
            f"head is not a cell: {head!r}")

    # Remove the matched Unify from the body
    new_body = clause.body[:unify_idx] + clause.body[unify_idx + 1:]
    return Clause(head=new_head, body=new_body)


def _nested_term_carries_a_literal(term):
    """True if a compiled head_to_match_pattern for term (a value already
    known to be BELOW some indexed root's functor/tag slot -- an element
    of a cell, a Call's arg, a dict/set/instance
    field, ...) would itself compile to a non-wildcard (literal-valued)
    sub-pattern.

    Recursive helper for :func:`_lifted_head_arg_needs_deep_gate` -- see
    that function's docstring for the design rationale.  A bare Var (or
    StarUnpack) is a pure capture: False.  A nested cell/Call
    recurses the SAME way (its own functor/tag slot excluded); a bare
    name reference (LoadName/LoadAttr, e.g. a nested imported atom
    argument) or any other scalar/opaque leaf resolves to a MatchValue
    and counts as a literal: True.  Conservative by construction.
    """
    if is_var(term):
        return False
    if isinstance(term, StarUnpack):
        return False
    if type(term) is tuple and term:
        is_cell, _slot0 = _cell_shape(term)
        start = 1 if is_cell else 0
        return any(_nested_term_carries_a_literal(e) for e in term[start:])
    if isinstance(term, Call) and isinstance(term.func, (LoadName, LoadAttr)):
        return (
            any(_nested_term_carries_a_literal(a) for a in term.args)
            or any(_nested_term_carries_a_literal(kw.value)
                   for kw in (term.kwargs or []))
        )
    if isinstance(term, (LoadName, LoadAttr)):
        return True
    if isinstance(term, list):
        return any(_nested_term_carries_a_literal(e) for e in term)
    if isinstance(term, DictTerm):
        return any(_nested_term_carries_a_literal(v) for v in term.values())
    if isinstance(term, SetTerm):
        return bool(term.elements)
    if is_term_instance(term):
        return any(
            _nested_term_carries_a_literal(getattr(term, n))
            for n in term_field_names(term)
        )
    return True


def _lifted_head_arg_needs_deep_gate(term):
    """True if a compiled head_to_match_pattern for term -- a clause head
    argument AFTER _lift_clause_at_pos has (possibly) replaced a Var with
    a real value -- would contain a non-wildcard (literal-valued)
    sub-pattern BELOW the indexed root own functor/tag slot.

    P3-2 Task 4 fix round 2 (controller design ruling): bucket SELECTION
    by shallow (functor, arity) is always correct for a partially-ground
    caller -- its functor and arity are necessarily ground (that is what
    selected the bucket), and no clause of a DIFFERENT functor/arity can
    ever unify with it. The only miss-hazard is a bucket ARM whose lifted
    pattern carries a literal SUB-value: a MatchValue there fails to
    match where the caller own unbound Var -- reaching this bucket via
    full unify() on the un-indexed fallback instead -- would have happily
    bound. A bucket with NO such arm needs no runtime groundness check at
    all: this function decides, ONCE PER BUCKET AT COMPILE TIME (never
    per dispatch call), whether that risk exists, so
    _runtime_arg_key's bounded walk (round 1) only has to run for the
    predicate/position pairs that actually carry it.

    Only a CELL, a compound reference (Call(LoadName)), or a
    resolved term instance can EVER reach ``_runtime_arg_key``'s
    deep-groundness-gated branch at all -- a bare scalar, atom
    (LoadName/LoadAttr with no surrounding Call), or unlifted Var keys
    through a wholly different, un-gated path (the PredicateMeta-atom
    branch, or a plain scalar return) regardless of what this function
    says, so those shapes are NOT recursed into as "the root" here: they
    return False unconditionally, and it is only what is nested INSIDE a
    cell/compound/instance -- checked by
    :func:`_nested_term_carries_a_literal` -- that can trigger True.  This
    is the fix for a round-2 self-test finding: an ATOM pad clause
    (``Depth(Pad1, 0)``) lifted at position 0 must NOT turn the gate on
    for a co-indexed CONS-cell clause at the same position just because a
    bare atom reference is conservatively "a literal" in the nested
    sense -- an atom has no sub-slots to be partially ground, so it is
    not a root this function needs to examine.
    """
    if is_var(term):
        return False
    if _cell_shape(term)[0]:
        return any(_nested_term_carries_a_literal(e) for e in term[1:])
    if isinstance(term, Call) and isinstance(term.func, (LoadName, LoadAttr)):
        return (
            any(_nested_term_carries_a_literal(a) for a in term.args)
            or any(_nested_term_carries_a_literal(kw.value)
                   for kw in (term.kwargs or []))
        )
    # A bare 0-arity atom reference (LoadName/LoadAttr with no surrounding
    # Call): no sub-slots at all, so no partial-groundness risk -- must be
    # excluded explicitly, BEFORE the is_term_instance catch-all below,
    # which would otherwise duck-type match it (LoadName/LoadAttr are
    # themselves dataclasses) and wrongly recurse into its own ``.name``
    # field.
    if isinstance(term, (LoadName, LoadAttr)):
        return False
    if is_term_instance(term):
        return any(
            _nested_term_carries_a_literal(getattr(term, n))
            for n in term_field_names(term)
        )
    return False


def _classify_list_key(arg: Any) -> str:
    """Classify a head argument as ``"nil"``, ``"cons"``, ``"var"``, or ``"other"``.

    - ``"nil"``  — argument is the empty list ``[]``
    - ``"cons"`` — argument is a non-empty Python list (may contain Vars)
    - ``"var"``  — argument is an unbound Var (wildcard, matches anything)
    - ``"other"``— anything else (integer, string, …)
    """
    arg = deref(arg)
    if is_var(arg):
        return "var"
    if isinstance(arg, list):
        return "nil" if not arg else "cons"
    return "other"


def _find_list_dispatch_pos(clauses: list[Clause], arity: int) -> int | None:
    """Find the best argument position for list structural dispatch.

    Returns the position index when ALL clauses have nil/cons/var heads at that
    position (no scalars or compound terms) AND both ``"nil"`` and ``"cons"``
    appear in the clause set — guaranteeing the dispatch saves work.

    Returns ``None`` if no suitable position is found.
    """
    if arity == 0 or len(clauses) < 2:
        return None
    best_pos = None
    best_score = 0
    for pos in range(arity):
        keys = [_classify_list_key(_get_head_arg(c, pos)) for c in clauses]
        if "other" in keys:
            continue  # mixed list + non-list types at this position
        list_keys = {k for k in keys if k != "var"}
        score = len(list_keys)  # 0 (all var), 1 (only nil or only cons), or 2
        if score >= 2 and score > best_score:
            best_pos = pos
            best_score = score
    return best_pos


def _build_list_dispatch_guard(
    clauses: list[Clause],
    dispatch_pos: int,
    arity: int,
    subject: ast.expr,
    body_compiler: Callable[[Clause, dict[int, str]], list[ast.stmt]],
) -> list[ast.stmt]:
    """Build the isinstance/is_var structural dispatch guard for list predicates.

    Generates:

        if isinstance(_d_pos, (list, str, bytes)):
            if not _d_pos:          # nil branch
                <nil_clauses + var_clauses>
            else:                   # cons branch
                <cons_clauses + var_clauses>
        elif is_var(_d_pos):        # unbound — try all clauses
            <all clauses>
        else:                       # int/tuple/SegList/… → all-clauses scan
            <all clauses>           # (nil/cons arms fail their list guards)

    ``var_clauses`` (wildcard heads) appear in both the nil and cons branches
    because a wildcard matches any list.  They also appear in the is_var
    fallback because the variable might be bound to any list at call time.
    """
    nil_clauses: list[Clause] = []
    cons_clauses: list[Clause] = []
    var_clauses: list[Clause] = []
    for c in clauses:
        key = _classify_list_key(_get_head_arg(c, dispatch_pos))
        if key == "nil":
            nil_clauses.append(c)
        elif key == "cons":
            cons_clauses.append(c)
        else:  # "var"
            var_clauses.append(c)

    def _match_stmts(subset: list[Clause]) -> list[ast.stmt]:
        stmts: list[ast.stmt] = []
        for clause in subset:
            vc: dict[int, str] = {}
            _head_arg_patterns(clause.head, vc, arity)
            body_stmts = body_compiler(clause, vc)
            case_arm = compile_head_to_match_case(
                head=clause.head,
                body_stmts=body_stmts,
                var_context=vc,
                arity=arity,
            )
            stmts.append(ast.Match(subject=subject, cases=[case_arm]))
        return stmts or [ast.Pass()]

    nil_body = _match_stmts(nil_clauses + var_clauses)
    cons_body = _match_stmts(cons_clauses + var_clauses)
    var_body = _match_stmts(nil_clauses + cons_clauses + var_clauses)
    # A02-F002: callers that are neither list/str/bytes nor an unbound Var
    # (int, tuple, a non-ground SegList, …) previously fell through to DONE,
    # silently losing every clause the arg would unify with. Run all clauses
    # through their match arms — the nil/cons arms fail their list guards on a
    # non-list, and the cons guard routes SegLists through
    # ``$head_list_unify_input`` — so this matches the un-dispatched compile.
    other_body = _match_stmts(nil_clauses + cons_clauses + var_clauses)

    deref_name = f"_d{dispatch_pos}"

    # if not _d_pos: <nil> else: <cons>
    nil_vs_cons = ast.If(
        test=ast.UnaryOp(op=ast.Not(), operand=_name(deref_name)),
        body=nil_body,
        orelse=cons_body,
    )

    # elif is_var(_d_pos): <all>  else: <all-clauses fallback>
    is_var_branch = ast.If(
        test=_call(_name("$is_var"), _name(deref_name)),
        body=var_body,
        orelse=other_body,
    )

    # if isinstance(_d_pos, (list, str, bytes)): <nil_vs_cons>
    # elif is_var: <all>  else: <all-clauses fallback>
    # Strings/bytes are treated as lists (of chars / codes) for head matching.
    _list_str_bytes = ast.Tuple(
        elts=[_name("$list"), _name("$str"), _name("$bytes")], ctx=ast.Load(),
    )
    return [
        ast.If(
            test=_call(_name("$isinstance"), _name(deref_name), _list_str_bytes),
            body=[nil_vs_cons],
            orelse=[is_var_branch],
        )
    ]


