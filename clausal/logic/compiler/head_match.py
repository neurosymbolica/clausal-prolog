"""Clause head → match-case compilation.

Compiles clause heads (functor dataclass instances, Compounds, etc.)
into Python ``match`` statement arm patterns.  Handles list patterns
(with bidirectional input/output guards — see
``clausal.logic.runtime.list_unify`` for
the runtime design), multi-star list guards, and repeat-variable
guards inside a single head.

Also provides the ``_wrap_yields_with_output_guards`` AST rewriter
that inserts output-phase list-unification checks at solution yield
points.

This module is a leaf in the compilation-call graph: its callers pass
in a pre-compiled body (from ``compile_body`` / ``compile_body_trampoline``),
so head_match never reaches back into goal compilation.
"""

from __future__ import annotations

import ast
import dataclasses
from typing import Any

from clausal.logic.variables import Var, is_var, deref, unify  # noqa: F401
from clausal.terms import (
    Compound,
    Call, LoadName,
    DictTerm, SetTerm, KWTerm,
    SegList, VarSeg,  # noqa: F401
)
from clausal.pythonic_ast.nodes import (
    StarUnpack, TupleLiteral, SetLiteral, literal_value,
)
from clausal.logic.predicate import (
    is_term_instance, term_field_names, term_field_names_of_class, PredicateMeta,
)

from ._ast_helpers import (
    _name, _attr, _call, _assign, _assign_mark, _undo_stmt, _if,
    _MARK_PREFIX, _TRAIL_PARAM_NAME,
)
from ._vars import _var_python_name, _collect_vars
from .terms_to_ast import (
    term_to_ast_expr,
    _is_star_list, _parse_star_segments, _count_stars,
    _is_opaque_head_literal, headlit_global_key,
    cell_functor_for_instance,
    cell_signature_for_name, _place_signature_slots,
)
# Runtime helpers (``_head_list_unify_input`` / ``_head_list_unify_output``
# / ``_head_multi_star_error``) are referenced by name string in the AST
# this module emits — e.g. ``_call(_name("$head_list_unify_input"), ...)``.
# The compiled predicate resolves those names via ``base_globals`` at
# call time, not via Python-level imports here.  So this module
# intentionally does NOT import from ``clausal.logic.runtime``; see the
# one-way boundary enforced by ``tests/test_runtime_compiler_boundary.py``.

# Aliases preserved from the pre-split monolith, where these were bound
# inline inside the function bodies with `_t` / `_SL` / `_SetLiteral`
# suffixes.  Kept verbatim so call sites don't need editing.
_DictTerm = DictTerm
_SetTerm = SetTerm
_KWTerm = KWTerm
_SetLiteral = SetLiteral

# Python types that ``ast.Constant`` accepts as a value.  PredicateMeta
# atom classes, Compound terms, dataclass instances, etc. are NOT in this
# set — they must be lowered via ``term_to_ast_expr`` instead.
_AST_CONST_TYPES = (type(None), bool, int, float, str, bytes, complex)


def _cell_match_pattern(functor: str, arg_patterns: list) -> ast.MatchSequence:
    """The cell pattern ``case ('functor', <p0>, ...)`` for a flagged module.

    A ``MatchSequence`` whose first element is a ``MatchValue`` on the functor
    string: the sequence length discriminates ARITY and the first element
    discriminates the FUNCTOR, which is exactly what the ``MatchClass`` this
    replaces did for class terms.

    NOTE for anyone extending this to tuple-DATA cells ``(tuple, e1, ...)``:
    the slot-0 tag is the ``tuple`` TYPE OBJECT, and a bare ``tuple`` written
    in a pattern is a CAPTURE, not a value test -- it must be spelled as the
    dotted value pattern ``builtins.tuple`` (with ``import builtins`` in the
    compiled function's globals), never ``__builtins__.tuple``, which is a
    dict rather than a module inside an imported module.  This stage's corpus
    reaches no tuple-data head pattern, so no such branch is emitted; see
    ``implementation_plans/tagged-tuple-term-representation.md`` section 4.
    """
    return ast.MatchSequence(
        patterns=[ast.MatchValue(value=ast.Constant(value=functor)),
                  *arg_patterns],
    )


def _matched_field_names(term: Any) -> tuple[str, ...]:
    """The fields of a term instance that a head pattern may test.

    A head pattern must test exactly the fields that runtime unification tests,
    otherwise the two head-matching routes for the same clause disagree: a
    structural head arg is normally hoisted to a body ``Unify`` (decided by
    ``unify``), but the argument-index bucket path lifts it back into the head
    (decided by this pattern).

    ``unify`` ignores a dataclass field declared ``compare=False`` — either
    explicitly (``BinOp.__unify__`` / ``Compound.__unify__`` skip the source
    ``position``) or via the ``==`` fallback, which dataclasses derive from the
    comparable fields only.  So a pattern must skip those fields too.  Today
    that means the cosmetic source ``position`` carried by every
    ``clausal.pythonic_ast`` node, which is what makes an operator head arg
    (``Diff(A + B, ...)``) matchable at all.  ``term_to_ast_expr`` already drops
    the same fields when *constructing* a term; this is the matching half of
    that rule.

    ``PredicateMeta`` terms keep ``_fields`` verbatim — every declared argument
    of a user predicate is semantic.  Note this is deliberately not used by
    ``_head_arg_patterns``: there the field list is the predicate's own argument
    list and must stay aligned with the head's arity.
    """
    names = term_field_names(term)
    if isinstance(type(term), PredicateMeta):
        return names
    if dataclasses.is_dataclass(term):
        skipped = {f.name for f in dataclasses.fields(term) if not f.compare}
        if skipped:
            return tuple(n for n in names if n not in skipped)
    return names


def _wrap_yields_with_output_guards(
    stmts: list[ast.stmt], output_guard_cond: "ast.expr"
) -> list[ast.stmt]:
    """Wrap every solution yield in *stmts* with an output-guard condition.

    Walks the AST statement list recursively.  Any ``Expr(Yield(...))`` that
    represents a solution point — either ``yield None`` (simple mode) or
    ``yield (parent, None)`` (trampoline mode) — is wrapped in
    ``if output_guard_cond: <original yield>``.

    If *output_guard_cond* is None, returns *stmts* unchanged.
    """
    if output_guard_cond is None:
        return stmts

    def _is_solution_yield(stmt: ast.stmt) -> bool:
        """Detect both simple-mode ``yield None`` and trampoline ``yield (parent, None)``."""
        if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Yield)):
            return False
        val = stmt.value.value
        # Simple mode: yield None
        if val is None or (isinstance(val, ast.Constant) and val.value is None):
            return True
        # Trampoline mode: yield (parent, None)
        if (isinstance(val, ast.Tuple) and len(val.elts) == 2
                and isinstance(val.elts[1], ast.Constant)
                and val.elts[1].value is None):
            return True
        return False

    def _walk_stmts(ss: list[ast.stmt]) -> list[ast.stmt]:
        result: list[ast.stmt] = []
        for s in ss:
            if _is_solution_yield(s):
                result.append(ast.If(
                    test=output_guard_cond,
                    body=[s],
                    orelse=[],
                ))
            else:
                result.append(_walk_stmt(s))
        return result

    def _walk_stmt(s: ast.stmt) -> ast.stmt:
        if isinstance(s, ast.If):
            s.body = _walk_stmts(s.body)
            s.orelse = _walk_stmts(s.orelse)
        elif isinstance(s, ast.For):
            s.body = _walk_stmts(s.body)
            s.orelse = _walk_stmts(s.orelse)
        elif isinstance(s, ast.While):
            s.body = _walk_stmts(s.body)
            s.orelse = _walk_stmts(s.orelse)
        elif isinstance(s, ast.Try):
            s.body = _walk_stmts(s.body)
            for h in s.handlers:
                h.body = _walk_stmts(h.body)
            s.orelse = _walk_stmts(s.orelse)
            s.finalbody = _walk_stmts(s.finalbody)
        elif isinstance(s, ast.With):
            s.body = _walk_stmts(s.body)
        return s

    return _walk_stmts(stmts)


# ── head_to_match_pattern ──────────────────────────────────────────────────────


def _resolve_loadname(qualified_name: str, globals_: dict | None) -> Any:
    """Resolve a (possibly dotted) ``LoadName.name`` to its compile-time value.

    Mirrors the dotted-name resolution that
    ``globals_env._inject_resolved_targets`` performs for body call
    targets: first try a direct dict hit (covers bare names that the
    import-remap stage left intact plus dotted names that the host
    module already binds verbatim — both happen after
    ``-import_from``), then fall back to splitting the dotted name and
    walking attributes.  Returns ``None`` when the name cannot be
    resolved; the caller treats that as "fall through to other pattern
    branches."
    """
    if globals_ is None or not qualified_name:
        return None
    direct = globals_.get(qualified_name)
    if direct is not None:
        return direct
    if "." in qualified_name:
        parts = qualified_name.split(".")
        obj = globals_.get(parts[0])
        for part in parts[1:]:
            if obj is None:
                return None
            obj = getattr(obj, part, None)
        return obj
    return None


def _resolved_field_names(resolved: Any) -> tuple[str, ...] | None:
    """Return the field-name tuple for *resolved*, or None if not term-shaped.

    Accepts both ``PredicateMeta`` classes (via ``cls._fields``) and
    bare ``@dataclass`` classes (via ``dataclasses.fields``).  Refuses
    anything else so the caller falls back through to the dataclass-
    instance / wildcard branches.

    Delegates the class-cases to ``term_field_names_of_class`` (the
    canonical version in predicate.py, modeled on this function). The one
    thing dropped versus the pre-funnel body is a generic "any class with
    a tuple ``_fields`` attribute" duck-type check that predated
    ``PredicateMeta``-specific typing; ``resolved`` here only ever comes
    from resolving a head functor name against compiled-module globals,
    so it is always either a ``PredicateMeta`` class or a bare dataclass
    in practice — the dropped branch could in theory also match an
    unrelated class that happens to carry a ``_fields`` tuple (a
    namedtuple, an ``ast.AST`` subclass), which was never a legitimate
    resolution target in this position.
    """
    if resolved is None or not isinstance(resolved, type):
        return None
    return term_field_names_of_class(resolved)


def head_to_match_pattern(
    term: Any,
    var_context: dict[int, str],
    dup_guards: list[tuple[str, str]] | None = None,
    list_guards: list[tuple] | None = None,
    _list_reg_ids: set[int] | None = None,
    globals_: dict | None = None,
) -> ast.pattern:
    """Convert a head field value to a Python ``ast.pattern`` node.

    Parameters
    ----------
    term:        value from a clause head (may be a Var, literal, dataclass, …)
    var_context: mutable dict mapping ``Var._id`` → Python local variable name.
                 Unbound Vars are registered here on first encounter.
    globals_:    the compiled function's globals dict (typically the host
                 module's namespace, post-import-remap).  Used to resolve
                 ``Call(func=LoadName(qualified_name), args=...)`` head
                 terms — emitted whenever a rule head references an
                 imported-compound functor like ``Item(...)`` — into the
                 actual ``PredicateMeta`` / dataclass class so a real
                 ``MatchClass`` pattern can be generated instead of falling
                 through to a value-rejecting wildcard.

    Pattern mapping
    ---------------
    Var (unbound)          → ``MatchAs(name="_v{id}")`` — captures the arg
    Var (bound)            → recurse after dereferencing
    None / True / False    → wildcard capture + ``== or unify`` guard (scalar)
    int, float, complex    → wildcard capture + ``== or unify`` guard (scalar)
    str, bytes             → wildcard capture + ``== or unify`` guard
    list                   → ``MatchSequence`` of sub-patterns

    NOTE on the bug class this guards against: a bare ``MatchValue`` /
    ``MatchSingleton`` matches with ``==`` / identity, which only succeeds when
    the deref'd caller arg ALREADY equals the literal (input mode). An unbound
    Var caller (output / var-query mode) silently fails the match and yields no
    solution — it never *binds* the literal. Every atomic head literal must
    therefore capture the arg and route through ``unify()`` (which binds a Var
    and rejects a mismatch), never rely on ``==``/identity alone.
    Compound(f, args)      → ``MatchClass(Compound, functor=f, args=...)``
    functor dataclass      → ``MatchClass(cls, kwd field patterns)``
    Call(LoadName(qn), …)  → resolve ``qn`` in ``globals_``; if a class with
                             ``_fields`` results, emit ``MatchClass(cls,
                             kwd field patterns)``; else wildcard (with the
                             matching ``is_term_instance`` fall-through if
                             applicable to a dataclass like ``Call`` itself).
    other                  → ``MatchAs(name=None)``  (wildcard ``_``)
    """
    term = deref(term)

    # Unbound Var → MatchAs to capture the incoming argument
    # Repeated Var (already in var_context) → fresh dup name + unification guard
    if is_var(term):
        vid = term._id
        if vid in var_context:
            # Duplicate occurrence — generate a unique dup name
            orig_name = var_context[vid]
            dup_name = f"{orig_name}__dup{len(dup_guards) if dup_guards is not None else 0}"
            if dup_guards is not None:
                dup_guards.append((orig_name, dup_name))
            return ast.MatchAs(pattern=None, name=dup_name)
        name = _var_python_name(term)
        var_context[vid] = name
        # This Var is registered as a DIRECT match capture (not a list element).
        # _list_reg_ids tracks list-registered Vars; absence means direct capture.
        return ast.MatchAs(pattern=None, name=name)

    # Python singletons (None / True / False) → wildcard capture + unify guard,
    # NOT a bare MatchSingleton. A MatchSingleton matches by identity, so an
    # unbound Var caller (output / var-query mode) silently fails to match and
    # never binds — the same bug class as numeric MatchValue literals below.
    # Route through the scalar guard (`== or unify`) so a Var caller binds.
    # (bool is an int subclass and would otherwise reach the numeric branch;
    # None is handled here.) Falls back to MatchSingleton only when there is no
    # list_guards sink to assemble the guard.
    term = literal_value(term)
    if term is None or term is True or term is False:
        if list_guards is not None:
            cap_name = f"_ncap{len(list_guards)}"
            list_guards.append(("scalar", cap_name, term))
            return ast.MatchAs(pattern=None, name=cap_name)
        return ast.MatchSingleton(value=term)

    # Python scalar literals (non-string, non-bytes) → wildcard capture +
    # runtime unify guard, mirroring the str/bytes paths below. A bare
    # MatchValue only matches when the deref'd arg already *equals* the literal
    # (input mode); an unbound Var caller (output / var-query mode) silently
    # fails the match and yields no solution. Routing through unify() binds the
    # literal into the caller's Var, matching how bare facts and string/atom
    # head literals behave. The guard short-circuits on an already-equal caller
    # via `==` before falling through to unify(). (numeric-head-literal bug)
    # When there is no list_guards sink (e.g. a nested context that does not
    # assemble guards) fall back to the literal MatchValue.
    if isinstance(term, (int, float, complex)):
        if list_guards is not None:
            cap_name = f"_ncap{len(list_guards)}"
            list_guards.append(("scalar", cap_name, term))
            return ast.MatchAs(pattern=None, name=cap_name)
        return ast.MatchValue(value=ast.Constant(value=term))

    # Python str literal → wildcard capture + runtime unify guard, mirroring the
    # list-literal path below. Routes the comparison through unify() so the
    # strings-as-lists contract (str ↔ char-list) is honoured for clause heads.
    # The guard, assembled in compile_head_to_match_case, short-circuits on a
    # same-type str caller via `==` before falling through to unify(). (F046)
    if isinstance(term, str):
        cap_name = f"_scap{len(list_guards) if list_guards is not None else 0}"
        if list_guards is not None:
            list_guards.append(("str", cap_name, term))
        return ast.MatchAs(pattern=None, name=cap_name)

    # Python bytes literal → wildcard capture + runtime unify guard, mirroring
    # the str path. Routes through unify() so the bytes-as-lists contract
    # (bytes ↔ int-code-list) is honoured for clause heads. The guard
    # short-circuits on a same-type bytes caller via `==` before unify().
    if isinstance(term, bytes):
        cap_name = f"_bcap{len(list_guards) if list_guards is not None else 0}"
        if list_guards is not None:
            list_guards.append(("bytes", cap_name, term))
        return ast.MatchAs(pattern=None, name=cap_name)

    # Python list → wildcard capture + _head_list_unify guard
    # This handles both input (destructuring) and output (construction) modes.
    if isinstance(term, list):
        # Parse list into segments: alternating fixed elements and stars
        segments: list[tuple[str, Any]] = []  # ("fixed", [elems]) or ("star", var)
        current_fixed: list[Any] = []
        star_count = 0
        for e in term:
            if isinstance(e, StarUnpack):
                star_count += 1
                if current_fixed:
                    segments.append(("fixed", current_fixed))
                    current_fixed = []
                segments.append(("star", deref(e.value)))
            else:
                current_fixed.append(deref(e))
        if current_fixed:
            segments.append(("fixed", current_fixed))

        # ── Flatten nested star-lists ──────────────────────────────────────
        # If a fixed element is itself a star-list (e.g. [HEAD, *TAIL]),
        # replace it with a fresh proxy Var and record the inner pattern
        # as a separate list guard (processed after the outer guard).
        _nested_star_guards: list[tuple[Any, list]] = []  # (proxy_var, star_list)
        for seg_idx, (seg_type, seg_val) in enumerate(segments):
            if seg_type != "fixed":
                continue
            new_val = []
            for elem in seg_val:
                if _is_star_list(elem):
                    proxy = Var()
                    new_val.append(proxy)
                    _nested_star_guards.append((proxy, elem))
                else:
                    new_val.append(elem)
            segments[seg_idx] = ("fixed", new_val)

        # Collect all vars from segments for registration (recursing into nested lists)
        def _collect_vars(items):
            result = []
            for item in items:
                if isinstance(item, list):
                    result.extend(_collect_vars(item))
                else:
                    result.append(item)
            return result

        all_vars: list[Any] = []
        for seg_type, seg_val in segments:
            if seg_type == "fixed":
                all_vars.extend(_collect_vars(seg_val))
            else:
                all_vars.append(seg_val)
        # Also collect vars from nested star-lists (they need registration too)
        for _proxy, _nested_list in _nested_star_guards:
            for _ne in _nested_list:
                if isinstance(_ne, StarUnpack):
                    all_vars.append(deref(_ne.value))
                elif isinstance(_ne, list):
                    all_vars.extend(_collect_vars(_ne))
                else:
                    all_vars.append(deref(_ne))

        # Register vars from list elements into var_context.
        # Three cases for a Var v inside this list:
        #   (a) New Var: register normally, mark as list-registered in _list_reg_ids.
        #   (b) Already registered from a PREVIOUS LIST: same name, no dup needed
        #       (both list guards share the pre-allocated Var).
        #   (c) Already registered as a DIRECT MATCH CAPTURE (not in _list_reg_ids):
        #       generate a dup name + dup_guard so the match-captured value is
        #       compared against the list-element Var after unification.
        list_elem_vc: dict[int, str] = {}  # name overrides for this list's elements
        for v in all_vars:
            if not is_var(v):
                continue
            if v._id in var_context:
                if v._id not in list_elem_vc:
                    # is_direct_capture: True only when _list_reg_ids is provided
                    # (meaning compile_head_to_match_case called us) AND the var
                    # was registered by the direct Var branch (not a list branch).
                    is_direct_capture = (
                        _list_reg_ids is not None and v._id not in _list_reg_ids
                    )
                    if is_direct_capture:
                        # Case (c): direct match capture — need dup name
                        orig_name = var_context[v._id]
                        n_dups = len(dup_guards) if dup_guards is not None else 0
                        dup_name = f"{orig_name}__dup{n_dups}"
                        if dup_guards is not None:
                            dup_guards.append((orig_name, dup_name))
                        list_elem_vc[v._id] = dup_name
                    else:
                        # Case (b): already list-allocated or _list_reg_ids not
                        # provided (legacy call) — reuse same name
                        list_elem_vc[v._id] = var_context[v._id]
            else:
                # Case (a): new Var — register and mark as list-allocated
                name = _var_python_name(v)
                var_context[v._id] = name
                if _list_reg_ids is not None:
                    _list_reg_ids.add(v._id)
                list_elem_vc[v._id] = name
        # Build a var_context snapshot for this list guard using the element vc.
        guard_vc = dict(var_context)
        guard_vc.update(list_elem_vc)
        # Generate a capture name and record the list guard
        cap_name = f"_lcap{len(list_guards) if list_guards is not None else 0}"
        if list_guards is not None:
            if star_count > 1:
                # Multi-star: store segments format with "multi" tag
                list_guards.append((cap_name, segments, guard_vc, "multi"))
            else:
                # Single-star: existing (before, star, after) format
                before: list[Any] = []
                star: Any = None
                after: list[Any] = []
                in_after = False
                for seg_type, seg_val in segments:
                    if seg_type == "star":
                        star = seg_val
                        in_after = True
                    elif in_after:
                        after.extend(seg_val)
                    else:
                        before.extend(seg_val)
                list_guards.append((cap_name, before, star, after, guard_vc))

            # Record sub-guards for nested star-lists.
            # Each nested pattern becomes its own list guard whose target is
            # the proxy Var's python name (bound by the outer guard).
            # Uses a worklist to handle arbitrary nesting depth.
            _pending = list(_nested_star_guards)
            while _pending:
                _proxy, _nested_list = _pending.pop(0)
                inner_segs: list[tuple[str, Any]] = []
                inner_fixed: list[Any] = []
                inner_star_count = 0
                for _ne in _nested_list:
                    if isinstance(_ne, StarUnpack):
                        inner_star_count += 1
                        if inner_fixed:
                            inner_segs.append(("fixed", inner_fixed))
                            inner_fixed = []
                        inner_segs.append(("star", deref(_ne.value)))
                    else:
                        inner_fixed.append(deref(_ne))
                if inner_fixed:
                    inner_segs.append(("fixed", inner_fixed))
                # Recursively flatten nested star-lists in inner segments
                for _iseg_idx, (_ist, _isv) in enumerate(inner_segs):
                    if _ist != "fixed":
                        continue
                    _inew = []
                    for _ie in _isv:
                        if _is_star_list(_ie):
                            _iproxy = Var()
                            _inew.append(_iproxy)
                            _pending.append((_iproxy, _ie))
                            pname = _var_python_name(_iproxy)
                            var_context[_iproxy._id] = pname
                            if _list_reg_ids is not None:
                                _list_reg_ids.add(_iproxy._id)
                            guard_vc[_iproxy._id] = pname
                            for _ine in _ie:
                                _iv = deref(_ine.value) if isinstance(_ine, StarUnpack) else deref(_ine)
                                if is_var(_iv) and _iv._id not in var_context:
                                    ivname = _var_python_name(_iv)
                                    var_context[_iv._id] = ivname
                                    if _list_reg_ids is not None:
                                        _list_reg_ids.add(_iv._id)
                                    guard_vc[_iv._id] = ivname
                        else:
                            _inew.append(_ie)
                    inner_segs[_iseg_idx] = ("fixed", _inew)
                proxy_name = guard_vc[_proxy._id]
                if inner_star_count > 1:
                    list_guards.append((proxy_name, inner_segs, guard_vc, "multi"))
                else:
                    ibefore: list[Any] = []
                    istar: Any = None
                    iafter: list[Any] = []
                    iin_after = False
                    for ist, isv in inner_segs:
                        if ist == "star":
                            istar = isv
                            iin_after = True
                        elif iin_after:
                            iafter.extend(isv)
                        else:
                            ibefore.extend(isv)
                    list_guards.append((proxy_name, ibefore, istar, iafter, guard_vc))

        return ast.MatchAs(pattern=None, name=cap_name)

    # DictTerm → wildcard capture + unify guard (pairwise value unification)
    if isinstance(term, _DictTerm):
        # Register Var values in var_context so they get python names
        for val in term.values():
            if is_var(val) and val._id not in var_context:
                name = _var_python_name(val)
                var_context[val._id] = name
                if _list_reg_ids is not None:
                    _list_reg_ids.add(val._id)
        cap_name = f"_dcap{len(list_guards) if list_guards is not None else 0}"
        if list_guards is not None:
            guard_vc = dict(var_context)
            list_guards.append(("dict", cap_name, term, guard_vc))
        return ast.MatchAs(pattern=None, name=cap_name)

    # SetTerm → wildcard capture + unify guard (set equality)
    if isinstance(term, _SetTerm):
        cap_name = f"_scap{len(list_guards) if list_guards is not None else 0}"
        if list_guards is not None:
            list_guards.append(("set", cap_name, term))
        return ast.MatchAs(pattern=None, name=cap_name)

    # SetLiteral (AST node) → wildcard capture + unify guard
    if isinstance(term, _SetLiteral):
        cap_name = f"_scap{len(list_guards) if list_guards is not None else 0}"
        if list_guards is not None:
            list_guards.append(("set_literal", cap_name, term))
        return ast.MatchAs(pattern=None, name=cap_name)

    # Compound(functor, args) → MatchClass on Compound
    #
    # Structural head args are hoisted to Var + Unify at assert time
    # (_normalize_structural_head_args), so this MatchClass only ever sees a
    # ground (input-mode) caller; output-mode binding is handled by the Unify.
    if isinstance(term, Compound):
        f = term.functor
        if is_var(f):
            # Variable functor: cannot match statically → wildcard
            return ast.MatchAs(pattern=None, name=None)
        sub_patterns = [head_to_match_pattern(a, var_context, dup_guards, list_guards, _list_reg_ids, globals_=globals_) for a in term.args]
        return ast.MatchClass(
            cls=_name("Compound"),
            patterns=[],
            kwd_attrs=["functor", "args"],
            kwd_patterns=[
                ast.MatchValue(value=ast.Constant(value=f)),
                ast.MatchSequence(patterns=sub_patterns),
            ],
        )

    # Call(func=LoadName(qualified_name), args=[...]) — emitted whenever a
    # rule head references an imported-compound functor (e.g. ``Item(...)``
    # from another module).  Without this branch the term falls through to
    # ``is_term_instance`` (Call is itself a dataclass), which produces a
    # ``MatchClass(Call, ...)`` pattern that requires the runtime value to
    # *be* a Call AST instance — which it never is.  Same shape used for
    # the fact path's runtime-Unify resolution, but here we resolve the
    # name at compile time against the module globals.
    #
    # Structural head args are hoisted to Var + Unify at assert time
    # (_normalize_structural_head_args), so this MatchClass only ever sees a
    # ground (input-mode) caller; output-mode binding is handled by the Unify.
    if isinstance(term, Call) and isinstance(term.func, LoadName):
        resolved = _resolve_loadname(term.func.name, globals_)
        fields = _resolved_field_names(resolved)
        # We only emit a MatchClass/cell pattern when we can pin the
        # field-name list at compile time; otherwise (resolution failed, or
        # the resolved value isn't a term-shaped class) we MUST fall through
        # to the value-rejecting branches below — the previous wildcard
        # fallback at the end is what masked this whole class of bug.
        if fields is not None:
            # ``-tagged_terms``: in a flagged module this reference builds a
            # CELL (see the Call(LoadName) branch of ``term_to_ast_expr``), so
            # the pattern that matches it is a sequence literal
            # ``case ('point', x, y)`` -- a MatchClass would test for a class
            # instance that the flagged module never constructs.
            #
            # P3-2 Task 1 (controller ruling extending the construction-side
            # brief to this, the matching half of the same symmetry --
            # ``_is_cell_functor_class``'s own docstring: a check applied to
            # construction but not to matching yields a clause that builds
            # one shape and matches another, one that can never fire):
            # signature PLACEMENT applies here too -- positional args fill
            # leading slots, keyword args fill named slots, and every
            # omitted slot becomes a WILDCARD pattern (an omitted head slot
            # binds nothing, exactly as a bare ``_`` argument would), so a
            # partial head reference ``point(x=1)`` compiles to the pattern
            # ``('point', 1, _)``.  Resolve against ``globals_`` -- the very
            # dict ``_resolve_loadname`` just used for ``fields``, so the
            # cell branch and the MatchClass fallback beside it cannot
            # disagree about which class ``term.func.name`` names.
            _sig = cell_signature_for_name(term.func.name, globals_)
            if _sig is not None:
                _functor, _cell_fields = _sig
                _positional = [
                    head_to_match_pattern(
                        a, var_context, dup_guards, list_guards,
                        _list_reg_ids, globals_=globals_,
                    )
                    for a in term.args
                ]
                _keywords = [
                    (
                        kw.name,
                        head_to_match_pattern(
                            kw.value, var_context, dup_guards, list_guards,
                            _list_reg_ids, globals_=globals_,
                        ),
                    )
                    for kw in (term.kwargs or [])
                ]
                _placed = _place_signature_slots(
                    _cell_fields, _positional, _keywords,
                    functor=_functor,
                    missing=lambda: ast.MatchAs(pattern=None, name=None),
                )
                return _cell_match_pattern(_functor, _placed)
            if len(term.args) <= len(fields):
                return ast.MatchClass(
                    cls=_name(term.func.name),
                    patterns=[],
                    kwd_attrs=list(fields[: len(term.args)]),
                    kwd_patterns=[
                        head_to_match_pattern(a, var_context, dup_guards, list_guards, _list_reg_ids, globals_=globals_)
                        for a in term.args
                    ],
                )

    # PredicateMeta atom (a zero-arity predicate *class* used as a value)
    # → wildcard capture + unify guard. Atoms became class objects in the
    # string→PredicateMeta migration (commit 92ce2636); that change updated
    # term_to_ast_expr / indexing but not this match-pattern path, so atoms
    # silently fell through to the value-rejecting wildcard fallback below
    # and matched ANY argument. An atom is a class, so it never reaches the
    # is_term_instance branch (that matches term *instances*). Route it
    # through unify() — atoms compare by identity/equality — mirroring the
    # str/bytes capture+guard pattern so it works in all argument modes.
    if isinstance(term, type) and isinstance(term, PredicateMeta):
        cap_name = f"_acap{len(list_guards) if list_guards is not None else 0}"
        if list_guards is not None:
            list_guards.append(("atom", cap_name, term))
        return ast.MatchAs(pattern=None, name=cap_name)

    # Functor term instance → MatchClass with field patterns
    #
    # Structural head args are hoisted to Var + Unify at assert time
    # (_normalize_structural_head_args), so this MatchClass only ever sees a
    # ground (input-mode) caller; output-mode binding is handled by the Unify —
    # except in an argument-index bucket, where _lift_clause_at_pos lifts that
    # Unify back into the head.  Fields unification ignores are excluded, so the
    # lifted pattern decides the match the same way the Unify would have.
    if is_term_instance(term):
        cls_name = type(term).__name__
        fields = _matched_field_names(term)
        # ``-tagged_terms``: the matching half of the term-instance emission
        # branch in ``term_to_ast_expr``.  ``_matched_field_names`` returns
        # ``_fields`` verbatim for a PredicateMeta term (every declared
        # argument of a user functor is semantic), and cell eligibility
        # requires PredicateMeta -- so the sequence pattern's positions line
        # up with the cell's slots exactly.
        _cell_f = cell_functor_for_instance(term)
        if _cell_f is not None:
            return _cell_match_pattern(
                _cell_f,
                [
                    head_to_match_pattern(
                        getattr(term, name), var_context, dup_guards,
                        list_guards, _list_reg_ids, globals_=globals_,
                    )
                    for name in fields
                ],
            )
        return ast.MatchClass(
            cls=_name(cls_name),
            patterns=[],
            kwd_attrs=list(fields),
            kwd_patterns=[
                head_to_match_pattern(getattr(term, name), var_context, dup_guards, list_guards, _list_reg_ids, globals_=globals_)
                for name in fields
            ],
        )

    # A02-F003: a ground head literal with no dedicated branch above (date,
    # Decimal, Fraction, tuple, set, Path, …) previously fell through to a bare
    # accept-all wildcard — matching EVERY caller in input mode and never
    # binding an unbound caller in output mode. Capture it and unify against the
    # value, injected into base_globals under $headlit_<id> by the globals
    # collector (mirroring the str/bytes/atom capture+guard pattern).
    if list_guards is not None and _is_opaque_head_literal(term):
        cap_name = f"_xcap{len(list_guards)}"
        list_guards.append(("headlit", cap_name, term))
        return ast.MatchAs(pattern=None, name=cap_name)

    # Fallback: wildcard (accept anything, no binding). Degraded path when there
    # is no list_guards sink, and for var-functor Compound heads (blocked on
    # A01-D004) which reach this only via the wildcard at the var-functor branch.
    return ast.MatchAs(pattern=None, name=None)


# ── Multi-star list guard compilation ──────────────────────────────────────────


def _compile_multi_star_guard(
    cap_name: str,
    segments: list[tuple[str, Any]],
    vc: dict[int, str],
    trail_name: str,
    body_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    """Compile a multi-star list pattern into nested splitting loops.

    Generates code like::

        _d0 = deref(_lcap0)
        if isinstance(_d0, SegList):
            _d0 = _d0.__walk__()
        if is_var(_d0):
            # Unbound: build a SegList and bind target once
            _mark = trail.mark()
            _sl = _build_multi_star_list([...])
            if unify(_cap0, _sl, trail):
                <body_stmts>
            trail.undo(_mark)
        if isinstance(_d0, list):
            _n0 = len(_d0)
            if _n0 >= <min_len>:
                for _sp0 in range(...):
                    ...nested loops...
                        _mmark0 = trail.mark()
                        if (unify(...) and unify(...) and ...):
                            <body_stmts>
                        trail.undo(_mmark0)
    """
    def _var_or_const_expr(elem):
        if is_var(elem) and elem._id in vc:
            return _name(vc[elem._id])
        if isinstance(elem, StarUnpack):
            return ast.Starred(
                value=_var_or_const_expr(elem.value), ctx=ast.Load(),
            )
        if isinstance(elem, list):
            return ast.List(
                elts=[_var_or_const_expr(e) for e in elem],
                ctx=ast.Load(),
            )
        if isinstance(elem, _AST_CONST_TYPES):
            return ast.Constant(value=elem)
        # Non-scalar term (PredicateMeta atom, Compound, dataclass
        # instance, ...): delegate to term_to_ast_expr, which emits a
        # Name reference for atoms and constructor calls for compounds.
        return term_to_ast_expr(elem, vc, eval_arith=False)

    # Count fixed elements and stars
    star_vars: list[Any] = []  # star Var objects in order
    fixed_counts: list[int] = []  # fixed-elem count per fixed segment
    fixed_segments: list[list[Any]] = []  # fixed elem lists
    for seg_type, seg_val in segments:
        if seg_type == "star":
            star_vars.append(seg_val)
        else:
            fixed_counts.append(len(seg_val))
            fixed_segments.append(seg_val)

    n_stars = len(star_vars)
    min_len = sum(fixed_counts)
    d_name = f"_msd{cap_name}"  # deref'd list local
    n_name = f"_msn{cap_name}"  # len local

    # Build the unify chain and loops from inside out.
    # Strategy: enumerate lengths assigned to each star var.
    # The last star's length is determined (remaining elements).
    # For k stars we need k-1 loop variables.

    # Compute the position-to-slice mapping for each segment.
    # pos tracks current position in the list as an AST expression.
    # We build the innermost body first, then wrap with loops.

    # The innermost body: mark + unify chain + body + undo
    mark_name = f"_mmark{cap_name}"

    # Build unify chain: for each segment, unify the var/elements with the slice
    # We'll represent positions as expressions relative to split vars.
    # split var names: _sp0, _sp1, ... (k-1 of them)
    sp_names = [f"_msp{cap_name}_{i}" for i in range(n_stars - 1)]

    # Position tracking: we walk segments left-to-right building slice exprs.
    # pos_expr: AST expression for current position in the list.
    # We accumulate position as: start=0, then add fixed-segment lengths and
    # star-var lengths (star lengths are sp_names[i] for first k-1, remainder for last).
    unify_calls: list[ast.expr] = []
    # Track position as components to sum: list of (constant_offset, [sp_name, ...])
    pos_const = 0  # constant part of current position
    pos_sp: list[str] = []  # split-var names added to position so far
    star_idx = 0
    fixed_idx = 0
    # A02-F004: once the LAST star is consumed, absolute position tracking
    # (pos_const/pos_sp) no longer applies — trailing fixed segments must be
    # indexed backward from ``n`` (they sit at n - trailing_fixed, ...).
    after_last_star = False
    post_star_trailing = 0  # total trailing fixed element count
    post_star_offset = 0    # trailing fixed elements emitted so far

    def _pos_expr():
        """Build AST expr for current position."""
        parts: list[ast.expr] = []
        if pos_const:
            parts.append(ast.Constant(value=pos_const))
        parts.extend(_name(sp) for sp in pos_sp)
        if not parts:
            return ast.Constant(value=0)
        if len(parts) == 1:
            return parts[0]
        result = parts[0]
        for p in parts[1:]:
            result = ast.BinOp(left=result, op=ast.Add(), right=p)
        return result

    for seg_type, seg_val in segments:
        if seg_type == "fixed":
            # Unify each fixed element with list[pos], list[pos+1], ...
            for j, elem in enumerate(seg_val):
                if after_last_star:
                    # A02-F004: trailing fixed elements are indexed relative to
                    # the last star's end (n - trailing_fixed), not from 0. The
                    # element at offset ``post_star_offset`` into the trailing
                    # region sits at ``n - (trailing_fixed - post_star_offset)``.
                    back = post_star_trailing - post_star_offset
                    idx_expr = ast.BinOp(
                        left=_name(n_name), op=ast.Sub(),
                        right=ast.Constant(value=back),
                    )
                    post_star_offset += 1
                else:
                    idx_expr = _pos_expr()
                    if j > 0:
                        idx_expr = ast.BinOp(
                            left=idx_expr, op=ast.Add(),
                            right=ast.Constant(value=j),
                        )
                subscript = ast.Subscript(
                    value=_name(d_name), slice=idx_expr, ctx=ast.Load(),
                )
                unify_calls.append(
                    _call(_name("$unify"), _var_or_const_expr(elem), subscript, _name(trail_name))
                )
            if not after_last_star:
                pos_const += len(seg_val)
        else:
            # Star segment: slice from pos to pos+length
            star_var = seg_val
            start_expr = _pos_expr()
            if star_idx < n_stars - 1:
                # length is sp_names[star_idx]
                end_parts: list[ast.expr] = [_pos_expr()]
                end_parts.append(_name(sp_names[star_idx]))
                end_expr = end_parts[0]
                for p in end_parts[1:]:
                    end_expr = ast.BinOp(left=end_expr, op=ast.Add(), right=p)
                pos_sp.append(sp_names[star_idx])
            else:
                # last star: takes everything remaining up to len - trailing fixed
                trailing_fixed = 0
                # Count fixed elements in segments after this star
                found_last_star = False
                for st, sv in segments:
                    if found_last_star and st == "fixed":
                        trailing_fixed += len(sv)
                    if st == "star" and sv is star_var:
                        found_last_star = True
                if trailing_fixed:
                    end_expr = ast.BinOp(
                        left=_name(n_name), op=ast.Sub(),
                        right=ast.Constant(value=trailing_fixed),
                    )
                else:
                    end_expr = _name(n_name)

            slice_expr = ast.Subscript(
                value=_name(d_name),
                slice=ast.Slice(lower=start_expr, upper=end_expr),
                ctx=ast.Load(),
            )
            unify_calls.append(
                _call(
                    _name("$unify"),
                    _var_or_const_expr(star_var),
                    slice_expr,
                    _name(trail_name),
                )
            )
            if star_idx < n_stars - 1:
                pass  # pos_sp already updated above
            else:
                # A02-F004: the last star consumed [start : n - trailing_fixed],
                # so trailing fixed segments start at n - trailing_fixed. Switch
                # to backward-from-n indexing for them (see the fixed branch).
                after_last_star = True
                post_star_trailing = trailing_fixed
                post_star_offset = 0
            star_idx += 1

    # Build the if-unify chain
    if len(unify_calls) == 1:
        unify_cond = unify_calls[0]
    else:
        unify_cond = ast.BoolOp(op=ast.And(), values=unify_calls)

    innermost = [
        _assign_mark(mark_name, trail_name),
        ast.If(test=unify_cond, body=body_stmts, orelse=[]),
        _undo_stmt(mark_name, trail_name),
    ]

    # Wrap with nested for-loops (inside-out, from last split var to first)
    # Each sp_names[i] ranges from 0 to (remaining - sum of later splits)
    # remaining = _n - min_len - sum of earlier splits
    current = innermost
    for i in range(n_stars - 2, -1, -1):
        # upper bound for sp_names[i]:
        # remaining after fixed and earlier splits = _n - min_len - sp0 - sp1 - ... - sp(i-1)
        # but also need to leave room for later splits (which can be 0), so upper is:
        # _n - min_len - sum(sp[0..i-1]) + 1
        upper_parts: list[ast.expr] = [
            ast.BinOp(
                left=_name(n_name), op=ast.Sub(),
                right=ast.Constant(value=min_len),
            )
        ]
        for j in range(i):
            upper_parts.append(_name(sp_names[j]))
        # Also subtract later split vars (they take the remainder)
        # For k splits (k-1 loop vars), sp[i] can range from 0 to
        # (remaining - sum_of_later_sps). But later sps are inner loops.
        # Actually: sp[i] + sp[i+1] + ... + sp[k-2] + last_star_len = remaining - sum(sp[0..i-1])
        # And each later sp and last_star can be >= 0, so sp[i] <= remaining - sum(sp[0..i-1]) - (n_stars-1-i-1)*0
        # Wait, no: remaining = n - min_len. sp[0] + sp[1] + ... + sp[k-2] + last_star_len = remaining
        # For sp[i]: upper = remaining - sp[0] - ... - sp[i-1] - sp[i+1] - ... - sp[k-2]
        # But sp[i+1]...sp[k-2] are inner loops that can be 0, and last_star = remaining - all sps >= 0
        # So sp[i] <= remaining - sp[0] - ... - sp[i-1] - 0 - ... - 0
        # upper = remaining - sum(sp[0..i-1]) + 1  (range is exclusive)
        # remaining = n - min_len
        # So upper = n - min_len - sum(sp[0..i-1]) + 1

        # sp[i] ranges from 0 to (remaining - sum(sp[0..i-1])) inclusive.
        # Later splits (sp[i+1]...) are inner loops that can be 0, so they
        # don't constrain the upper bound of sp[i].
        remaining_expr: ast.expr = ast.BinOp(
            left=_name(n_name), op=ast.Sub(),
            right=ast.Constant(value=min_len),
        )
        for j in range(i):
            remaining_expr = ast.BinOp(
                left=remaining_expr, op=ast.Sub(),
                right=_name(sp_names[j]),
            )
        upper_expr = ast.BinOp(
            left=remaining_expr, op=ast.Add(),
            right=ast.Constant(value=1),
        )

        current = [ast.For(
            target=_name(sp_names[i], ast.Store()),
            iter=_call(_name("range"), upper_expr),
            body=current,
            orelse=[],
        )]

    # Wrap with: if isinstance(_d, list) and len >= min_len
    len_check = ast.Compare(
        left=_name(n_name),
        ops=[ast.GtE()],
        comparators=[ast.Constant(value=min_len)],
    )
    guarded = [ast.If(test=len_check, body=current, orelse=[])]

    # _n = len(_d)
    len_assign = _assign(n_name, _call(_name("len"), _name(d_name)))

    # isinstance check — accept list, str (chars), and bytes (codes). Native
    # indexing/slicing handles all three: str[i] is a 1-char str, bytes[i] is
    # an int code, and slicing preserves the container type.
    isinstance_check = _call(
        _name("isinstance"), _name(d_name),
        ast.Tuple(elts=[_name("list"), _name("str"), _name("bytes")], ctx=ast.Load()),
    )

    # Build segments list AST for _build_multi_star_list (used in unbound Var case)
    seg_elts = []
    for s_kind, s_val in segments:
        if s_kind == "star":
            seg_elts.append(ast.Tuple(
                elts=[ast.Constant(value="star"), _var_or_const_expr(s_val)],
                ctx=ast.Load(),
            ))
        else:  # "fixed"
            seg_elts.append(ast.Tuple(
                elts=[
                    ast.Constant(value="fixed"),
                    ast.List(elts=[_var_or_const_expr(e) for e in s_val], ctx=ast.Load()),
                ],
                ctx=ast.Load(),
            ))
    segments_ast = ast.List(elts=seg_elts, ctx=ast.Load())

    var_build_mark = f"_msvm{cap_name}"
    var_sl_name = f"_msvsl{cap_name}"

    # if is_var(_d): build SegList and bind target once
    var_check = ast.If(
        test=_call(_name("is_var"), _name(d_name)),
        body=[
            _assign_mark(var_build_mark, trail_name),
            _assign(var_sl_name, _call(_name("$build_multi_star_list"), segments_ast)),
            ast.If(
                test=_call(_name("$unify"), _name(cap_name), _name(var_sl_name), _name(trail_name)),
                body=body_stmts,
                orelse=[],
            ),
            _undo_stmt(var_build_mark, trail_name),
        ],
        orelse=[],
    )

    list_branch = ast.If(
        test=isinstance_check,
        body=[len_assign] + guarded,
        orelse=[],
    )

    # _d = deref(_lcap)
    deref_assign = _assign(d_name, _call(_name("$deref"), _name(cap_name)))

    # If _d is a SegList, walk it: a fully-ground SegList becomes a plain list
    # so the existing isinstance(list) branch fires; a non-ground SegList stays
    # a SegList and the list branch simply doesn't fire (no solutions for now —
    # SegList-vs-SegList unification is Phase 6).
    seglist_normalise = ast.If(
        test=_call(_name("isinstance"), _name(d_name), _name("SegList")),
        body=[
            _assign(
                d_name,
                ast.Call(
                    func=ast.Attribute(
                        value=_name(d_name), attr="__walk__", ctx=ast.Load()
                    ),
                    args=[],
                    keywords=[],
                ),
            )
        ],
        orelse=[],
    )

    # F047 (C3 audit): mirror the SegList walk for SegString so the multi-
    # star head guard accepts ground SegStrings (which walk to plain str and
    # route through the (list, str) isinstance arm below).
    segstring_normalise = ast.If(
        test=_call(_name("isinstance"), _name(d_name), _name("SegString")),
        body=[
            _assign(
                d_name,
                ast.Call(
                    func=ast.Attribute(
                        value=_name(d_name), attr="__walk__", ctx=ast.Load()
                    ),
                    args=[],
                    keywords=[],
                ),
            )
        ],
        orelse=[],
    )

    # bytes-as-lists: mirror the SegString walk for SegBytes so the multi-star
    # head guard accepts ground SegBytes (which walk to plain bytes and route
    # through the (list, str, bytes) isinstance arm below).
    segbytes_normalise = ast.If(
        test=_call(_name("isinstance"), _name(d_name), _name("SegBytes")),
        body=[
            _assign(
                d_name,
                ast.Call(
                    func=ast.Attribute(
                        value=_name(d_name), attr="__walk__", ctx=ast.Load()
                    ),
                    args=[],
                    keywords=[],
                ),
            )
        ],
        orelse=[],
    )

    # F047 (C3 audit): a still-non-ground SegString delegates to
    # ``$body_multi_star_unify`` (runtime), which knows how to align a
    # non-ground SegString with a multi-star pattern via
    # ``_segstring_align`` (yields one True per valid alignment). The
    # body_stmts run inside the for-loop so each alignment yields a
    # solution.
    segstring_branch = ast.If(
        test=_call(_name("isinstance"), _name(d_name), _name("SegString")),
        body=[
            ast.For(
                target=ast.Name(id=f"_ssms{cap_name}", ctx=ast.Store()),
                iter=_call(
                    _name("$body_multi_star_unify"),
                    _name(cap_name),
                    segments_ast,
                    _name(trail_name),
                ),
                body=body_stmts,
                orelse=[],
            ),
        ],
        orelse=[],
    )

    # bytes-as-lists: a still-non-ground SegBytes delegates to
    # ``$body_multi_star_unify`` (runtime), which aligns it with the multi-star
    # pattern via ``_segbytes_align`` (one True per valid alignment). Mirror of
    # ``segstring_branch``.
    segbytes_branch = ast.If(
        test=_call(_name("isinstance"), _name(d_name), _name("SegBytes")),
        body=[
            ast.For(
                target=ast.Name(id=f"_sbms{cap_name}", ctx=ast.Store()),
                iter=_call(
                    _name("$body_multi_star_unify"),
                    _name(cap_name),
                    segments_ast,
                    _name(trail_name),
                ),
                body=body_stmts,
                orelse=[],
            ),
        ],
        orelse=[],
    )

    return [
        deref_assign,
        seglist_normalise,
        segstring_normalise,
        segbytes_normalise,
        var_check,
        segstring_branch,
        segbytes_branch,
        list_branch,
    ]


# ── compile_head_to_match_case ─────────────────────────────────────────────────


def compile_head_to_match_case(
    head: Any,
    body_stmts: list[ast.stmt],
    var_context: dict[int, str],
    arity: int,
    trail_name: str = _TRAIL_PARAM_NAME,
    mark_name: str = "_mark",
    skip_trail: bool = False,
    globals_: dict | None = None,
) -> ast.match_case:
    """Compile a clause head into one ``match_case`` arm.

    Parameters
    ----------
    head:        head term (functor dataclass or Compound)
    body_stmts:  pre-compiled body statements (from compile_body or a placeholder)
    var_context: mutable dict; Var._id → python_name mappings are added here
    arity:       expected number of arguments (len of head's fields/args)
    trail_name:  name of the trail parameter in the enclosing function
    mark_name:   name for the trail mark local variable

    Generated structure::

        case (<per-arg patterns…>,):
            _mark = trail.mark()
            try:
                <body_stmts>
            finally:
                trail.undo(_mark)
    """
    dup_guards: list[tuple[str, str]] = []
    list_guards: list[tuple] = []
    # Use a fresh context for head pattern generation so that repeated vars
    # within a single head are correctly detected (the caller's var_context
    # may already contain vars from a pre-collection pass).
    head_var_ctx: dict[int, str] = {}
    # _list_reg_ids tracks Var IDs registered via list-element branches (not direct
    # match captures).  A Var appearing in multiple list patterns reuses the same
    # pre-allocated name; a Var that was first registered as a direct match capture
    # and then appears in a list gets a dup name to avoid overwriting the capture.
    _list_reg_ids: set[int] = set()
    arg_patterns = _head_arg_patterns(head, head_var_ctx, arity, dup_guards, list_guards, _list_reg_ids, globals_=globals_)
    var_context.update(head_var_ctx)
    outer_pattern = ast.MatchSequence(patterns=arg_patterns)

    # Equality-vs-unification invariant: no head arg may compile to a bare
    # MatchValue / MatchSingleton (== / identity match), which never binds an
    # unbound Var caller. See assert_head_pattern_unify_safe.
    from .invariants import assert_head_pattern_unify_safe
    assert_head_pattern_unify_safe(outer_pattern, head)

    # _mark = trail.mark()
    mark_assign = _assign_mark(mark_name, trail_name)

    # trail.undo(_mark)
    undo_stmt = ast.Expr(value=_call(_attr(trail_name, "undo"), _name(mark_name)))

    # Wrap body_stmts with dup-var unification guards (innermost first)
    inner = body_stmts if body_stmts else [ast.Pass()]
    for orig_name, dup_name in reversed(dup_guards):
        # if unify(orig, dup, trail): <inner>
        inner = [ast.If(
            test=_call(
                _name("$unify"),
                _name(orig_name),
                _name(dup_name),
                _name(trail_name),
            ),
            body=inner,
            orelse=[],
        )]

    # Emit dict/set guards: isinstance check + unify
    dict_guards = [g for g in list_guards if isinstance(g[0], str) and g[0] == "dict"]
    set_guards = [g for g in list_guards if isinstance(g[0], str) and g[0] in ("set", "set_literal")]
    if dict_guards or set_guards:
        dict_set_stmts: list[ast.stmt] = []
        # Pre-allocate Vars for dict value patterns
        _ds_alloc_seen: set[str] = set()
        for _, _cap, dt, _vc in dict_guards:
            for val in dt.values():
                if is_var(val) and val._id in _vc:
                    vname = _vc[val._id]
                    if vname not in _ds_alloc_seen:
                        _ds_alloc_seen.add(vname)
                        dict_set_stmts.append(_assign(vname, _call(_name("Var"))))

        for _, cap_name, dt, vc in dict_guards:
            # Build DictTerm({k: var_or_const, ...}) expression
            dict_keys_ast = []
            dict_vals_ast = []
            for key in dt.keys():
                dict_keys_ast.append(ast.Constant(value=key))
                val = dt[key]
                if is_var(val) and val._id in vc:
                    dict_vals_ast.append(_name(vc[val._id]))
                else:
                    dict_vals_ast.append(term_to_ast_expr(val, vc))
            expected_expr = _call(
                _name("DictTerm"),
                ast.Dict(keys=dict_keys_ast, values=dict_vals_ast),
            )
            inner = [ast.If(
                test=_call(_name("$unify"), _name(cap_name), expected_expr, _name(trail_name)),
                body=inner,
                orelse=[],
            )]

        for tag, cap_name, st in set_guards:
            if tag == "set":
                # SetTerm (runtime value): elements are ground, emit constants
                elts = [ast.Constant(value=e) for e in sorted(st.elements, key=repr)]
            else:
                # SetLiteral (AST node): elements are term values, convert via term_to_ast_expr
                elts = [term_to_ast_expr(e, var_context) for e in st.elements]
            expected_expr = _call(
                _name("SetTerm"),
                ast.List(elts=elts, ctx=ast.Load()),
            )
            inner = [ast.If(
                test=_call(_name("$unify"), _name(cap_name), expected_expr, _name(trail_name)),
                body=inner,
                orelse=[],
            )]

        inner = dict_set_stmts + inner

    # Emit str-literal guards (F046): wildcard capture + same-type short-circuit.
    #   if _scap == "abc" or unify(_scap, "abc", trail): <inner>
    # The `==` disjunct short-circuits at C speed for a same-type str caller;
    # list / SegString callers fall through to unify(), which applies the
    # strings-as-lists contract. Binds the raw str on an unbound caller arg,
    # matching how _normalize_dataclass_fact handles ground fact head literals.
    str_guards = [g for g in list_guards if g and g[0] == "str"]
    for _tag, cap_name, literal in str_guards:
        inner = [ast.If(
            test=ast.BoolOp(
                op=ast.Or(),
                values=[
                    ast.Compare(
                        left=_name(cap_name),
                        ops=[ast.Eq()],
                        comparators=[ast.Constant(value=literal)],
                    ),
                    _call(
                        _name("$unify"),
                        _name(cap_name),
                        ast.Constant(value=literal),
                        _name(trail_name),
                    ),
                ],
            ),
            body=inner,
            orelse=[],
        )]

    # Emit bytes-literal guards (bytes-as-lists): wildcard capture +
    # same-type short-circuit. Mirrors the str-guards block above.
    bytes_guards = [g for g in list_guards if g and g[0] == "bytes"]
    for _tag, cap_name, literal in bytes_guards:
        inner = [ast.If(
            test=ast.BoolOp(
                op=ast.Or(),
                values=[
                    ast.Compare(
                        left=_name(cap_name),
                        ops=[ast.Eq()],
                        comparators=[ast.Constant(value=literal)],
                    ),
                    _call(
                        _name("$unify"),
                        _name(cap_name),
                        ast.Constant(value=literal),
                        _name(trail_name),
                    ),
                ],
            ),
            body=inner,
            orelse=[],
        )]

    # Emit scalar-literal guards (int/float/complex/bool/None): wildcard capture
    # + same-type short-circuit. Mirrors the str-/bytes-guards blocks above. The
    # `==` disjunct accepts an already-equal caller at C speed; an unbound Var
    # caller falls through to unify(), which binds the literal (output /
    # var-query mode). A bare MatchValue/MatchSingleton would compare with
    # `==`/identity and silently fail to bind a Var — the bug this guards.
    scalar_guards = [g for g in list_guards if g and g[0] == "scalar"]
    for _tag, cap_name, literal in scalar_guards:
        inner = [ast.If(
            test=ast.BoolOp(
                op=ast.Or(),
                values=[
                    ast.Compare(
                        left=_name(cap_name),
                        ops=[ast.Eq()],
                        comparators=[ast.Constant(value=literal)],
                    ),
                    _call(
                        _name("$unify"),
                        _name(cap_name),
                        ast.Constant(value=literal),
                        _name(trail_name),
                    ),
                ],
            ),
            body=inner,
            orelse=[],
        )]

    # Emit opaque head-literal guards (A02-F003): wildcard capture + same-value
    # short-circuit + unify against the value injected under $headlit_<id> in
    # base_globals. Mirrors the scalar/str/bytes guards but references the value
    # by name (it cannot go through ast.Constant — non-primitive — nor reliably
    # through term_to_ast_expr, which raises for e.g. Fraction/date).
    headlit_guards = [g for g in list_guards if g and g[0] == "headlit"]
    for _tag, cap_name, literal in headlit_guards:
        lit_key = headlit_global_key(literal)
        inner = [ast.If(
            test=ast.BoolOp(
                op=ast.Or(),
                values=[
                    ast.Compare(
                        left=_name(cap_name),
                        ops=[ast.Eq()],
                        comparators=[_name(lit_key)],
                    ),
                    _call(
                        # $-prefixed like every sibling guard: the public
                        # "unify" key in the module dict is shadowable by a
                        # user predicate of that name (A12-F004).
                        _name("$unify"),
                        _name(cap_name),
                        _name(lit_key),
                        _name(trail_name),
                    ),
                ],
            ),
            body=inner,
            orelse=[],
        )]

    # Emit atom guards (R1): wildcard capture + unify guard. Atoms compare by
    # identity/equality; unify() binds an unbound caller arg to the atom and
    # rejects a different atom/term. term_to_ast_expr emits the atom as a Name
    # reference resolved via the compiled predicate's globals.
    atom_guards = [g for g in list_guards if g and g[0] == "atom"]
    for _tag, cap_name, atom in atom_guards:
        inner = [ast.If(
            test=_call(
                _name("$unify"),
                _name(cap_name),
                term_to_ast_expr(atom, var_context, eval_arith=False),
                _name(trail_name),
            ),
            body=inner,
            orelse=[],
        )]

    # Emit list guards: input destructuring + deferred output construction
    # Filter out dict/set/str/bytes/atom guards from list_guards
    actual_list_guards = [g for g in list_guards if g[0] not in ("dict", "set", "set_literal", "str", "bytes", "atom", "scalar", "headlit")]
    if actual_list_guards:
        # Separate single-star and multi-star guards
        single_star_guards = [g for g in actual_list_guards if len(g) == 5]
        multi_star_guards = [g for g in actual_list_guards if len(g) == 4]

        # Pre-allocate Var() for list-pattern vars (not captured by match pattern)
        def _flatten_elems(items):
            """Recursively collect all items from nested lists."""
            result = []
            for item in items:
                if isinstance(item, list):
                    result.extend(_flatten_elems(item))
                else:
                    result.append(item)
            return result

        list_var_allocs: list[ast.stmt] = []
        _alloc_seen: set[str] = set()
        for guard in actual_list_guards:
            if len(guard) == 5:
                _cap_name, _before, _star, _after, _vc = guard
                elems = _flatten_elems(_before + ([_star] if _star is not None else []) + _after)
            else:
                _cap_name, _segments, _vc, _ = guard
                elems = []
                for seg_type, seg_val in _segments:
                    if seg_type == "fixed":
                        elems.extend(_flatten_elems(seg_val))
                    else:
                        elems.append(seg_val)
            for elem in elems:
                if is_var(elem) and elem._id in _vc:
                    vname = _vc[elem._id]
                    if vname not in _alloc_seen:
                        _alloc_seen.add(vname)
                        list_var_allocs.append(_assign(vname, _call(_name("Var"))))

        # ── Single-star guards (existing path) ────────────────────────────
        if single_star_guards:
            def _list_guard_args(cap_name, before, star, after, vc):
                """Build AST expressions for _head_list_unify_* call args."""
                def _var_or_const(elem):
                    if is_var(elem) and elem._id in vc:
                        return _name(vc[elem._id])
                    if isinstance(elem, StarUnpack):
                        return ast.Starred(
                            value=_var_or_const(elem.value), ctx=ast.Load(),
                        )
                    if isinstance(elem, list):
                        return ast.List(
                            elts=[_var_or_const(e) for e in elem],
                            ctx=ast.Load(),
                        )
                    if isinstance(elem, _AST_CONST_TYPES):
                        return ast.Constant(value=elem)
                    # Non-scalar term: delegate to term_to_ast_expr so atoms
                    # become Name references rather than bare ast.Constants.
                    return term_to_ast_expr(elem, vc, eval_arith=False)
                before_list = ast.List(elts=[_var_or_const(e) for e in before], ctx=ast.Load())
                if star is not None and is_var(star) and star._id in vc:
                    star_expr = _name(vc[star._id])
                else:
                    star_expr = ast.Constant(value=None)
                after_list = ast.List(elts=[_var_or_const(e) for e in after], ctx=ast.Load())
                return (_name(cap_name), before_list, star_expr, after_list, _name(trail_name))

            input_check_stmts: list[ast.stmt] = []
            lr_names: list[str] = []
            all_guard_args: list[tuple] = []
            for i, (cap_name, before, star, after, _vc) in enumerate(single_star_guards):
                lr_name = f"_lr{i}"
                lr_names.append(lr_name)
                args = _list_guard_args(cap_name, before, star, after, _vc)
                all_guard_args.append(args)
                input_check_stmts.append(
                    _assign(lr_name, _call(_name("$head_list_unify_input"), *args))
                )

            gate_tests = []
            for lr_name in lr_names:
                gate_tests.append(ast.Compare(
                    left=_name(lr_name),
                    ops=[ast.IsNot()],
                    comparators=[ast.Constant(value=False)],
                ))
            if len(gate_tests) == 1:
                gate_cond = gate_tests[0]
            else:
                gate_cond = ast.BoolOp(op=ast.And(), values=gate_tests)

            output_conditions: list[ast.expr] = []
            for i, lr_name in enumerate(lr_names):
                args = all_guard_args[i]
                output_conditions.append(ast.BoolOp(
                    op=ast.Or(),
                    values=[
                        ast.Compare(
                            left=_name(lr_name),
                            ops=[ast.IsNot()],
                            comparators=[ast.Constant(value=None)],
                        ),
                        _call(_name("$head_list_unify_output"), *args),
                    ],
                ))
            if len(output_conditions) == 1:
                output_cond = output_conditions[0]
            else:
                output_cond = ast.BoolOp(op=ast.And(), values=output_conditions)

            inner = _wrap_yields_with_output_guards(inner, output_cond)

            gated_inner = [ast.If(test=gate_cond, body=inner, orelse=[])]
            inner = input_check_stmts + gated_inner

        # ── Multi-star guards ─────────────────────────────────────────────
        for ms_guard in multi_star_guards:
            cap_name, segments, vc, _ = ms_guard
            inner = _compile_multi_star_guard(
                cap_name, segments, vc, trail_name, inner,
            )

        inner = list_var_allocs + inner

    # If the head captured no variables and there are no guards that unify
    # (dup_guards, list_guards), the clause cannot modify the trail —
    # skip the mark/undo overhead.
    # Also skip when *skip_trail* is set (single-clause index bucket —
    # there is no sibling clause to backtrack to, so the caller's
    # mark/undo will clean up head bindings).
    if skip_trail or (not head_var_ctx and not dup_guards and not list_guards):
        return ast.match_case(
            pattern=outer_pattern,
            guard=None,
            body=inner,
        )

    # The body contains ``yield``s, so this generator can be suspended at a
    # choicepoint and later abandoned (e.g. once/1 or \+ commits past it). If the
    # garbage collector then reclaims the suspended generator, CPython throws
    # ``GeneratorExit`` into it and the ``finally`` would run ``trail.undo(_mark)``
    # — truncating the *live* trail of the in-flight search back to this old mark
    # and destroying bindings made after it (lost/duplicate solutions, only with
    # GC enabled). So skip the undo when the generator is being closed: an
    # abandoned choicepoint's bindings are cleaned up by the enclosing mark/undo
    # (or discarded with the per-query trail), never by this finally.
    closing_name = mark_name + "_cl"
    try_finally = ast.Try(
        body=inner,
        handlers=[ast.ExceptHandler(
            type=_name("GeneratorExit"),
            name=None,
            body=[_assign(closing_name, ast.Constant(value=True)),
                  ast.Raise(exc=None, cause=None)],
        )],
        orelse=[],
        finalbody=[ast.If(
            test=ast.UnaryOp(op=ast.Not(), operand=_name(closing_name)),
            body=[undo_stmt],
            orelse=[],
        )],
    )

    return ast.match_case(
        pattern=outer_pattern,
        guard=None,
        body=[mark_assign,
              _assign(closing_name, ast.Constant(value=False)),
              try_finally],
    )


def _head_arg_patterns(
    head: Any, var_context: dict[int, str], arity: int,
    dup_guards: list[tuple[str, str]] | None = None,
    list_guards: list[tuple] | None = None,
    _list_reg_ids: set[int] | None = None,
    globals_: dict | None = None,
) -> list[ast.pattern]:
    """Extract per-argument patterns from a head term."""
    def _pat(term):
        return head_to_match_pattern(term, var_context, dup_guards, list_guards, _list_reg_ids, globals_=globals_)
    if isinstance(head, Compound):
        return [_pat(a) for a in head.args]
    # Call(func=LoadName(f), args=[...]) — e.g. from $assert_fact with trailing comma.
    # Extract patterns from the positional args, not from the Call dataclass fields.
    if isinstance(head, Call) and isinstance(head.func, LoadName):
        return [_pat(a) for a in head.args]
    if is_term_instance(head):
        return [_pat(getattr(head, name)) for name in term_field_names(head)]
    # Fallback: arity wildcards (accept any args)
    return [ast.MatchAs(pattern=None, name=None) for _ in range(arity)]


