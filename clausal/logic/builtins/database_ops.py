"""Runtime database manipulation builtins: assertz/1, asserta/1, retract/1,
abolish_table/2, abolish_all_tables/0."""

from __future__ import annotations

from typing import Any

from clausal.logic.variables import Var, Trail, deref, is_var, unify
from clausal.logic.predicate import PredicateMeta, is_term_instance
from clausal.terms import Compound

from clausal.logic.builtins._registry import (
    _db_builtin, structural_unify,
)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _normalize_fact_clause(term: Any):
    """Convert a ground Compound fact to Var+Is form for output-mode queries.

    ``Compound("f", (1, 2))`` → head=Compound("f", (v0, v1)), body=[Is(v0,1), Is(v1,2)]

    This makes dynamically asserted facts queryable in output mode (with unbound
    Var arguments), matching standard Prolog semantics for assert.
    Facts asserted via the DSL already use Var+Is form via the term transformer.
    """
    from clausal.logic.database import Clause  # avoid top-level import cycle
    from clausal.terms import Unify as _Unify

    if isinstance(term, Compound):
        new_args = []
        body: list = []
        for arg in term.args:
            arg_val = deref(arg)
            if not is_var(arg_val):
                v = Var()
                new_args.append(v)
                body.append(_Unify(left=v, right=arg_val))
            else:
                new_args.append(arg_val)
        return Clause(head=Compound(term.functor, tuple(new_args)), body=body)
    # Dataclass and KWTerm facts are passed as-is; their field patterns work
    # correctly since they use Python structural matching.
    from clausal.logic.database import Clause  # already imported above
    return Clause(head=term, body=[])


def _build_clause(term_val: Any) -> "Any":
    """Build a Clause from a runtime term passed to assertz/asserta.

    Handles Predicate nodes (rules) and plain terms (facts).
    Ground Compound facts are normalized to Var+Is form.
    """
    from clausal.logic.database import Clause, _flatten_body  # avoid top-level cycle
    from clausal.terms import Predicate as _Predicate

    if isinstance(term_val, _Predicate):
        return Clause(head=term_val.head, body=_flatten_body(term_val.body))
    return _normalize_fact_clause(term_val)


def _find_pred_cls(functor: str, module_dict: "dict | None") -> "Any":
    """Return the PredicateMeta class for functor from module_dict, or None."""
    from clausal.logic.predicate import PredicateMeta  # noqa: PLC0415
    if module_dict is None:
        return None
    candidate = module_dict.get(functor)
    return candidate if isinstance(candidate, PredicateMeta) else None


# ── assertz / retract ──────────────────────────────────────────────────────────


@_db_builtin("assertz", 1, fields=("term",))
def _assertz_factory(db):
    """assertz(Term) — add Term as a fact at end of its predicate's clause list.

    Ground facts are automatically normalized to Var+Is form so they are
    queryable in output mode (matching standard Prolog assert semantics).
    when a module dict is available on the database, also syncs to the
    PredicateMeta class and recompiles with module globals for cross-predicate
    resolution.
    """
    from clausal.logic.database import head_key
    from clausal.logic.compiler import compile_predicate_trampoline
    module_dict = getattr(db, "module_dict", None)

    def assertz__1(term, trail, k):
        term_val = deref(term)
        if is_var(term_val):
            return
        clause = _build_clause(term_val)
        functor, arity = head_key(clause.head)
        pred_cls = _find_pred_cls(functor, module_dict)
        if pred_cls is not None and pred_cls._locked:
            raise RuntimeError(
                f"Predicate {functor}/{arity} is locked. "
                "Use dynamic() to allow runtime assertion."
            )
        # db.assertz syncs pred_cls._clauses and clears its dispatch.
        db.assertz(clause)
        clauses = db.clauses_for(functor, arity)
        compile_predicate_trampoline(functor, arity, clauses, db,
                                     globals_=module_dict, pred_cls=pred_cls)
        yield None

    return assertz__1


@_db_builtin("asserta", 1, fields=("term",))
def _asserta_factory(db):
    """asserta(Term) — add Term as a fact at front of its predicate's clause list.

    when a module dict is available on the database, also syncs to the
    PredicateMeta class and recompiles with module globals.
    """
    from clausal.logic.database import head_key
    from clausal.logic.compiler import compile_predicate_trampoline
    module_dict = getattr(db, "module_dict", None)

    def asserta__1(term, trail, k):
        term_val = deref(term)
        if is_var(term_val):
            return
        clause = _build_clause(term_val)
        functor, arity = head_key(clause.head)
        pred_cls = _find_pred_cls(functor, module_dict)
        if pred_cls is not None and pred_cls._locked:
            raise RuntimeError(
                f"Predicate {functor}/{arity} is locked. "
                "Use dynamic() to allow runtime assertion."
            )
        # db.asserta syncs pred_cls._clauses and clears its dispatch.
        db.asserta(clause)
        clauses = db.clauses_for(functor, arity)
        compile_predicate_trampoline(functor, arity, clauses, db,
                                     globals_=module_dict, pred_cls=pred_cls)
        yield None

    return asserta__1


@_db_builtin("retract", 1, fields=("term",))
def _retract_factory(db):
    """retract(Term) — remove the first clause whose head unifies with Term.

    Uses unification (not structural equality) so it correctly handles
    normalized facts whose heads contain Var placeholders.  Bindings
    from the head unification are undone after the clause is removed
    (retract is not backtrackable in this implementation).
    when a module dict is available on the database, also syncs to the
    PredicateMeta class.
    """
    from clausal.logic.database import head_key
    from clausal.logic.compiler import compile_predicate_trampoline
    module_dict = getattr(db, "module_dict", None)

    def retract__1(term, trail, k):
        term_val = deref(term)
        if is_var(term_val):
            return
        try:
            functor, arity = head_key(term_val)
        except TypeError:
            return
        clause_list = db._clauses.get((functor, arity))
        if clause_list is None:
            return
        pred_cls = _find_pred_cls(functor, module_dict)
        if pred_cls is not None and pred_cls._locked:
            raise RuntimeError(
                f"Predicate {functor}/{arity} is locked. "
                "Use dynamic() to allow runtime retraction."
            )
        # Find first clause whose head unifies with term_val (and whose
        # Is-body goals are consistent with that unification).
        from clausal.terms import Unify as _Unify  # avoid top-level cycle
        for i, clause in enumerate(clause_list):
            tmp_trail = Trail()
            mark = tmp_trail.mark()
            if not structural_unify(term_val, clause.head, tmp_trail):
                tmp_trail.undo(mark)
                continue
            # Verify body: check that Unify goals are consistent with the head
            # unification.  We check only Unify goals (normalization artefacts).
            body_ok = True
            for goal in clause.body:
                if isinstance(goal, _Unify):
                    lv = deref(goal.left)
                    rv = deref(goal.right)
                    chk_trail = Trail()
                    chk_mark = chk_trail.mark()
                    if not structural_unify(lv, rv, chk_trail):
                        body_ok = False
                        chk_trail.undo(chk_mark)
                        break
                    chk_trail.undo(chk_mark)  # don't retain Is bindings
            if not body_ok:
                tmp_trail.undo(mark)  # undo head bindings before next iteration
                continue
            # Found a matching clause — remove it.
            tmp_trail.undo(mark)  # clean up temporary bindings
            del clause_list[i]
            # Sync removal to pred_cls if available (match by identity).
            if pred_cls is not None:
                for j, pcls_clause in enumerate(pred_cls._clauses):
                    if pcls_clause is clause:
                        del pred_cls._clauses[j]
                        pred_cls._dispatch_fn = None
                        break
            clauses = db.clauses_for(functor, arity)
            if clauses:
                compile_predicate_trampoline(functor, arity, clauses, db,
                                             globals_=module_dict, pred_cls=pred_cls)
            yield None
            return  # retract is not backtrackable

    return retract__1


# ── Tabling ───────────────────────────────────────────────────────────────────


@_db_builtin("abolish_table", 2, fields=("functor", "arity"))
def _abolish_table_factory(db):
    """abolish_table(functor, Arity) — remove cached answers for a tabled predicate."""

    def abolish_table__2(functor_arg, arity_arg, trail, k):
        f = deref(functor_arg)
        a = deref(arity_arg)
        if is_var(f) or is_var(a):
            return
        if not isinstance(f, str) or not isinstance(a, int):
            return
        db.abolish_table(f, a)
        yield None

    return abolish_table__2


@_db_builtin("abolish_all_tables", 0, fields=())
def _abolish_all_tables_factory(db):
    """abolish_all_tables — remove all cached tabling answers."""

    def abolish_all_tables__0(trail, k):
        db.abolish_all_tables()
        yield None

    return abolish_all_tables__0
