"""Bottom-up semi-naive Datalog engine, semiring-generic.

Evaluation strategy:

1. Collect all `-bottom_up` predicates and their rules from the runtime
   ``PredicateMeta`` classes referenced by the goal.
2. Stratify by SCC over the rule-dependency graph (``stratify.py``).
3. For each SCC in topological order, iterate to fixpoint:

   - Snapshot each predicate's relation as a ``dict[ground_tuple, Tag]``.
   - For each rule, walk body atoms left-to-right, threading a
     semiring-multiplied tag through each ``-bottom_up`` callee match.
     Pure callees and arithmetic / comparison atoms defer to Clausal's
     ``solve`` and contribute ``semiring.one()``.
   - Each successful body firing produces a ground head tuple with the
     accumulated tag; merge into the new relation via ``semiring.add``.
   - Stop when the relation is unchanged under ``semiring.saturated``.

4. Filter the final relations against the user's goal and return
   ``[(ground_term, tag)]`` matches.

Tag-threading semantics:
    For a rule ``H <- A1, A2, ..., An``, each firing's contribution to
    ``H``'s tag is ``mult(t1, mult(t2, ... mult(t_{n-1}, tn) ...))`` where
    ``ti`` is the matched ``-bottom_up`` callee's tag (or ``one()`` for
    pure / arithmetic / comparison atoms). The relation merges firings
    via ``add``. This is correct for the boolean, counting,
    add-mult-prob, and (with tensor ⊕/⊗) the diff-add-mult-prob
    semirings — i.e., every Tier 1 semiring of the plan.
"""

from __future__ import annotations

from typing import Any, Iterable

from clausal.logic.predicate import (
    PredicateMeta,
    is_term_instance,
    term_field_names,
)
from clausal.logic.database import Clause, head_key
from clausal.logic.variables import Var, Trail, deref, is_var, unify
from clausal.logic.trampoline import DONE
from clausal.terms import Compound

from clausal.modules.provenance.protocol import Provenance, NonGroundTupleError
from clausal.modules.provenance.stratify import stratify, StratificationError
from clausal.modules.provenance._registration import is_bottom_up, is_pure
from clausal.modules.provenance._pure_default import is_default_pure


# ── Term shape helpers ──────────────────────────────────────────────────
#
# P2 (clausal 2026-09): a compound term is a CELL -- the functor-first tuple
# ``(name, *args)`` -- not a ``PredicateMeta`` instance.  This engine is built
# around predicate CLASSES (they carry ``_clauses``, and ``-bottom_up`` /
# ``pure_`` registration hangs off them), so a cell has to be resolved back to
# its class through the module.  These three readers are the only places that
# know how a term is shaped; everything below goes through them.



def _clauses_of(cls) -> list:
    """The clause list of a predicate class -- its ROW's (W2, 2026-09-22).

    A class still on no row has no clauses, and reading must not mint one.
    """
    row = getattr(cls, "_row", None)
    return row.clauses if row is not None else []

def _term_args(term: Any) -> tuple:
    """The ARGUMENT tuple of a term -- positions for a cell, fields for an
    instance, ``args`` for a ``Compound``.  Raises for anything else."""
    if type(term) is tuple:
        return term[1:]
    if is_term_instance(term):
        return tuple(getattr(term, n) for n in term_field_names(term))
    if isinstance(term, Compound):
        return tuple(term.args)
    raise TypeError(
        f"Cannot read the arguments of {term!r}; expected a cell, a "
        "PredicateMeta instance or a Compound."
    )


def _class_for_term(term: Any, module: Any = None) -> PredicateMeta | None:
    """The predicate CLASS a term names, or None.

    An instance still answers from ``type(term)``.  A CELL carries only its
    functor, so the class is resolved by ``(functor, arity)`` through the
    module dict -- the same lookup ``_discover_bottom_up_predicates`` already
    does for a clause-body callee.  Arity is checked, not assumed: one name
    can be several predicates.
    """
    if is_term_instance(term):
        return type(term)
    if isinstance(term, type) and isinstance(term, PredicateMeta):
        return term
    if type(term) is not tuple:
        return None
    try:
        name, arity = head_key(term)
    except TypeError:
        # head_key REFUSES the reserved 1-tuple ('x',), the empty tuple, and
        # a TUPLE_TAG data tuple.  "Which class does this term name?" is a
        # question in a dispatch chain -- it has to ANSWER.  None means "no
        # class", and the caller turns that into its own diagnostic.
        return None
    md = module.module_dict if hasattr(module, "module_dict") else None
    if md is not None:
        obj = md.get(name)
        if isinstance(obj, PredicateMeta) and obj._arity == arity:
            return obj
    return None


# ── Term grounding helpers ──────────────────────────────────────────────


def _walk_term(term: Any) -> Any:
    """Recursively dereference a term and return a fully-walked snapshot.

    Variables that remain unbound are left as Var objects (caller decides
    how to handle them).
    """
    term = deref(term)
    if is_var(term):
        return term
    if isinstance(term, (bool, int, float, str, bytes)) or term is None:
        return term
    if isinstance(term, type) and isinstance(term, PredicateMeta) and not term._fields:
        return term
    if isinstance(term, list):
        return [_walk_term(e) for e in term]
    if isinstance(term, tuple):
        return tuple(_walk_term(e) for e in term)
    if isinstance(term, Compound):
        return Compound(term.functor, tuple(_walk_term(a) for a in term.args))
    if is_term_instance(term):
        cls = type(term)
        return cls(**{n: _walk_term(getattr(term, n)) for n in term_field_names(term)})
    return term


def _is_ground(term: Any) -> bool:
    term = deref(term)
    if is_var(term):
        return False
    if isinstance(term, (bool, int, float, str, bytes)) or term is None:
        return True
    if isinstance(term, type):
        return True
    if isinstance(term, list):
        return all(_is_ground(e) for e in term)
    if isinstance(term, tuple):
        return all(_is_ground(e) for e in term)
    if isinstance(term, Compound):
        return all(_is_ground(a) for a in term.args)
    if is_term_instance(term):
        return all(_is_ground(getattr(term, n)) for n in term_field_names(term))
    return True


def _term_to_tuple(term: Any) -> tuple:
    """Convert a ground term-instance into a hashable tuple of its field values.

    Only the field values are returned (the class is implied by where the
    tuple is stored — keyed by ``(functor, arity)``).
    """
    term = _walk_term(term)
    # Test the shape, do not catch _term_args' TypeError: catching would also
    # swallow one raised from INSIDE a legitimate read and report it as the
    # wrong diagnostic.
    if type(term) is tuple or is_term_instance(term) or isinstance(term, Compound):
        return _term_args(term)
    raise TypeError(
        f"Cannot ground-key non-term value {term!r}; expected a cell, a "
        "PredicateMeta instance or Compound."
    )


def _collect_body_callees(body) -> list[tuple[str, int]]:
    """Return (functor_name, arity) for every Call node in body."""
    from clausal.pythonic_ast.nodes import Call, LoadName, And, TupleLiteral, Not
    out: list[tuple[str, int]] = []
    stack = [body]
    while stack:
        node = stack.pop()
        if node is None:
            continue
        if isinstance(node, list):
            for x in node:
                stack.append(x)
            continue
        if isinstance(node, And):
            stack.append(node.right)
            stack.append(node.left)
            continue
        if isinstance(node, TupleLiteral):
            for x in node.elements:
                stack.append(x)
            continue
        if isinstance(node, Not):
            stack.append(node.operand)
            continue
        if isinstance(node, Call) and isinstance(node.func, LoadName):
            out.append((node.func.name, len(node.args)))
            continue
    return out


# ── Relation storage ────────────────────────────────────────────────────


class Relation:
    """A relation: dict of ground tuples → tags, plus the predicate class."""

    __slots__ = ("pred_cls", "tuples")

    def __init__(self, pred_cls: PredicateMeta) -> None:
        self.pred_cls = pred_cls
        self.tuples: dict[tuple, Any] = {}

    def add(self, tup: tuple, tag: Any, semiring: Provenance) -> bool:
        """Insert (tup, tag) into the relation. Return True if changed."""
        old = self.tuples.get(tup)
        if old is None:
            self.tuples[tup] = tag
            return True
        merged = semiring.add(old, tag)
        if not semiring.saturated(old, merged):
            self.tuples[tup] = merged
            return True
        return False

    def snapshot(self) -> dict[tuple, Any]:
        return dict(self.tuples)

    def __repr__(self) -> str:
        return f"<Relation {self.pred_cls.__name__}/{self.pred_cls._arity} {len(self.tuples)} tuples>"


# ── Body atom classification ────────────────────────────────────────────


def _atom_predicate_key(atom):
    """Return ``(functor_name, arity)`` if atom is a Call to a named predicate.

    Returns None for non-Call atoms (Is, comparisons, BinOps, etc.) and for
    Calls whose ``func`` isn't a ``LoadName``.
    """
    from clausal.pythonic_ast.nodes import Call, LoadName
    if isinstance(atom, Call) and isinstance(atom.func, LoadName):
        return (atom.func.name, len(atom.args))
    return None


def _negated_call(atom):
    """If atom is ``Not(Call(LoadName(name), args))`` return the inner Call."""
    from clausal.pythonic_ast.nodes import Not, Call, LoadName
    if isinstance(atom, Not):
        inner = atom.operand
        if isinstance(inner, Call) and isinstance(inner.func, LoadName):
            return inner
    return None


# ── Purity check ────────────────────────────────────────────────────────


def validate_purity(
    bottom_up_classes: dict[tuple[str, int], PredicateMeta],
    module=None,
) -> None:
    """Walk every rule body and refuse impure callees with a clear message.

    A callee is acceptable if any of:
    - it is itself a ``-bottom_up`` predicate,
    - it has been marked via ``pure_/1``,
    - its (functor, arity) is in the default-pure whitelist.
    """
    bu_keys = set(bottom_up_classes.keys())
    md = module.module_dict if (module is not None and hasattr(module, "module_dict")) else None
    for key, cls in bottom_up_classes.items():
        for clause in _clauses_of(cls):
            for callee in _collect_body_callees(clause.body):
                if callee in bu_keys:
                    continue
                if is_default_pure(callee[0], callee[1]):
                    continue
                # Check whether the callee's PredicateMeta carries pure_ flag
                callee_cls = _resolve_callee_class(callee, cls, md)
                if callee_cls is not None and is_pure(callee_cls):
                    continue
                raise PurityError(
                    f"Predicate {key[0]}/{key[1]}: rule body calls "
                    f"{callee[0]}/{callee[1]}, which is neither -bottom_up, "
                    "marked pure_, nor on the default-pure whitelist. "
                    "Bottom-up rule bodies must be pure-monotonic-deterministic. "
                    "See implementation_plans/PROVENANCE_SEMIRINGS.md "
                    "(§ Foreign-predicate constraint) and docs/purity.md."
                )


def _resolve_callee_class(
    callee: tuple[str, int],
    rule_cls: PredicateMeta,
    module_dict: dict | None = None,
) -> PredicateMeta | None:
    """Best-effort lookup of a callee's PredicateMeta class.

    Tries (in order): the supplied module dict; ``sys.modules`` keyed by
    the rule's ``__module__`` attribute. Returns None when the callee
    cannot be resolved as a PredicateMeta (e.g., a builtin).
    """
    if module_dict is not None:
        obj = module_dict.get(callee[0])
        if isinstance(obj, PredicateMeta) and obj._arity == callee[1]:
            return obj
    import sys
    mod = sys.modules.get(rule_cls.__module__)
    if mod is None:
        return None
    obj = getattr(mod, callee[0], None)
    if isinstance(obj, PredicateMeta) and obj._arity == callee[1]:
        return obj
    return None


class PurityError(Exception):
    """A bottom-up rule body calls an unmarked-impure predicate."""


# ── Rule evaluator: tag-threading body interpreter ─────────────────────


def _renew_clause(clause: Clause) -> Clause:
    """Return a copy of the clause with all variables renamed to fresh ones.

    Walks both runtime terms (Compound, KWTerm, PredicateMeta instances,
    lists, tuples) and ``pythonic_ast`` Node subclasses (``Call``,
    ``Unify``, ``BinOp``, etc.) so that variables shared between head and
    body — including those nested inside arithmetic expressions like
    ``TOTAL is A + B`` — are renamed consistently.
    """
    var_map: dict = {}
    new_head = _renew_term(clause.head, var_map)
    new_body = [_renew_term(g, var_map) for g in clause.body]
    return Clause(head=new_head, body=new_body, position=clause.position)


def _renew_term(term: Any, var_map: dict) -> Any:
    """Recursively rename Vars in `term`, returning a structurally-fresh copy.

    Mirrors ``clausal.logic.builtins.inspection._copy_term`` for runtime
    terms but extends through ``pythonic_ast`` Node subclasses via
    ``transform_children`` so renaming reaches inside body AST atoms.
    """
    from clausal.pythonic_ast.nodes import Node
    term = deref(term)
    if is_var(term):
        vid = id(term)
        if vid not in var_map:
            var_map[vid] = Var()
        return var_map[vid]
    if isinstance(term, (bool, int, float, str, bytes)) or term is None:
        return term
    if isinstance(term, type) and isinstance(term, PredicateMeta) and not term._fields:
        return term
    if isinstance(term, list):
        return [_renew_term(e, var_map) for e in term]
    if isinstance(term, tuple):
        return tuple(_renew_term(e, var_map) for e in term)
    if isinstance(term, Compound):
        return Compound(term.functor, tuple(_renew_term(a, var_map) for a in term.args))
    if is_term_instance(term) and not isinstance(term, Node):
        cls = type(term)
        return cls(**{
            n: _renew_term(getattr(term, n), var_map)
            for n in term_field_names(term)
        })
    if isinstance(term, Node):
        # AST nodes — recursively rename via dataclass field introspection.
        # We avoid ``transform_children`` because it treats Python lists as
        # node-lists and flattens them, which breaks atoms like
        # ``length([A, B], 2)`` whose first arg is a *value* list, not a
        # sequence of children.
        import dataclasses as _dc
        new_fields = {}
        for f in _dc.fields(term):
            if f.name == "position":
                continue
            new_fields[f.name] = _renew_term(getattr(term, f.name), var_map)
        return _dc.replace(term, **new_fields)
    return term


def _evaluate_rule(
    rule: Clause,
    pred_cls: PredicateMeta,
    relations: dict,
    pred_classes: dict,
    semiring: Provenance,
    module,
) -> Iterable[tuple[tuple, Any, tuple]]:
    """Run rule once; yield (head_tuple, tag, proof_key) for each firing.

    ``proof_key`` is a hashable fingerprint of the body matches used by
    this firing — a tuple of ``(callee_key, matched_tuple)`` for every
    ``-bottom_up`` body atom. The caller uses it to deduplicate proofs
    across iterations (essential for non-idempotent semirings where ⊕
    over-counts when the same proof is rederived).

    Threads a semiring tag through body atoms: ``-bottom_up`` callees
    multiply by the matched tuple's tag; pure / arithmetic / comparison
    atoms contribute ``semiring.one()`` and dispatch via Clausal's
    ``solve``.
    """
    fresh = _renew_clause(rule)
    body = fresh.body
    head = fresh.head

    if not body:
        # Fact clause — head must already be ground.
        if not _is_ground(head):
            raise NonGroundTupleError(
                f"Fact in {pred_cls.__name__}/{pred_cls._arity} has unbound "
                f"variables: {head!r}"
            )
        yield _term_to_tuple(head), semiring.one(), ()
        return

    trail = Trail()
    yield from _drive_atoms(
        body, 0, semiring.one(), (), head, rule, pred_cls,
        relations, pred_classes, semiring, module, trail,
    )


def _drive_atoms(
    atoms: list, idx: int, tag: Any, proof_key: tuple,
    head, rule: Clause, pred_cls: PredicateMeta,
    relations: dict, pred_classes: dict,
    semiring: Provenance, module, trail: Trail,
):
    """Recursively walk body atoms; yield (head_tuple, tag, proof_key).

    For each ``-bottom_up`` callee atom we iterate its current relation
    snapshot, unifying call args against the stored tuple, multiplying
    the running ``tag`` by the tuple's stored tag, and extending
    ``proof_key`` with ``(callee_key, matched_tuple)``. For other atoms
    we drive Clausal's ``solve`` (treating success as contributing
    ``one()``); pure callees don't extend ``proof_key`` because they are
    deterministic — same input always gives the same answer.
    """
    if idx >= len(atoms):
        head_walked = _walk_term(head)
        if not _is_ground(head_walked):
            raise NonGroundTupleError(
                f"Rule body for {pred_cls.__name__}/{pred_cls._arity} "
                f"left head variables unbound: {head_walked!r}. "
                f"Rule position: {rule.position!r}."
            )
        yield _term_to_tuple(head_walked), tag, proof_key
        return

    atom = atoms[idx]
    callee_key = _atom_predicate_key(atom)
    negated_inner = _negated_call(atom)

    if callee_key is not None and callee_key in pred_classes:
        # ── -bottom_up callee: iterate relation, multiply tags ──
        snapshot = relations[callee_key].snapshot()
        atom_args = atom.args
        for tup, callee_tag in snapshot.items():
            mark = trail.mark()
            ok = True
            for arg, val in zip(atom_args, tup):
                if not unify(arg, val, trail):
                    ok = False
                    break
            if ok:
                new_tag = semiring.mult(tag, callee_tag)
                if not semiring.discard(new_tag):
                    yield from _drive_atoms(
                        atoms, idx + 1, new_tag,
                        proof_key + ((callee_key, tup),),
                        head, rule, pred_cls,
                        relations, pred_classes, semiring, module, trail,
                    )
            trail.undo(mark)
    elif negated_inner is not None and (
        (negated_inner.func.name, len(negated_inner.args)) in pred_classes
    ):
        # ── Stratified negation against a -bottom_up callee ──
        # Args must already be ground (stratified-negation safety):
        # ``not Q(t1, t2)`` looks up the ground tuple in Q's relation,
        # multiplies the running tag by ``semiring.negate(stored_tag)``
        # — or by ``negate(zero())`` (== ``one()``-ish, semiring-defined)
        # if the tuple isn't in the relation.
        neg_key = (negated_inner.func.name, len(negated_inner.args))
        ground_args = [_walk_term(a) for a in negated_inner.args]
        if any(not _is_ground(a) for a in ground_args):
            raise NonGroundTupleError(
                f"Negation of {neg_key[0]}/{neg_key[1]} in "
                f"{pred_cls.__name__}/{pred_cls._arity}'s body has unbound "
                f"arguments {ground_args!r}. Stratified negation requires "
                "the negated atom to be ground; bind its variables earlier "
                "in the body."
            )
        tup = tuple(ground_args)
        stored = relations[neg_key].tuples.get(tup, semiring.zero())
        neg_tag = semiring.negate(stored)
        new_tag = semiring.mult(tag, neg_tag)
        if not semiring.discard(new_tag):
            # Negation contributes a deterministic factor — proof_key stays
            # the same (no choice was made). For boolean: stored=False ⇒
            # negate=True, succeeds; stored=True ⇒ negate=False then
            # ``mult(tag, False) = False`` and ``discard`` (or saturated)
            # prunes — a single child invocation is correct.
            yield from _drive_atoms(
                atoms, idx + 1, new_tag,
                proof_key + ((("not", neg_key), tup),),
                head, rule, pred_cls,
                relations, pred_classes, semiring, module, trail,
            )
    else:
        # ── Pure callee, NAF, or non-Call atom: defer to Clausal solve ──
        from clausal.logic.solve import solve as core_solve
        for _ in core_solve(atom, module=module, trail=trail):
            yield from _drive_atoms(
                atoms, idx + 1, tag, proof_key,
                head, rule, pred_cls,
                relations, pred_classes, semiring, module, trail,
            )


# ── Driver: solve a stratum to fixpoint ─────────────────────────────────


def _evaluate_stratum(
    scc: list[tuple[str, int]],
    relations: dict[tuple[str, int], Relation],
    pred_classes: dict[tuple[str, int], PredicateMeta],
    semiring: Provenance,
    module,
) -> None:
    """Iterate the SCC's predicates to fixpoint, modifying ``relations``.

    Uses proof-deduplication: each unique proof (rule × clause-index ×
    body-match-tuple) contributes exactly once. Without this,
    non-idempotent semirings (anything but ``boolean``) over-count when
    the same proof is rederived across iterations.
    """
    seen_proofs: set[tuple] = set()
    while True:
        any_new = False
        for key in scc:
            cls = pred_classes[key]
            rel = relations[key]
            for rule_idx, rule in enumerate(_clauses_of(cls)):
                for tup, tag, proof_key in _evaluate_rule(
                    rule, cls, relations, pred_classes, semiring, module,
                ):
                    full_proof_key = (key, rule_idx, tup, proof_key)
                    if full_proof_key in seen_proofs:
                        continue
                    seen_proofs.add(full_proof_key)
                    if rel.add(tup, tag, semiring):
                        any_new = True
        if not any_new:
            break


# ── Public driver ───────────────────────────────────────────────────────


def evaluate(
    semiring: Provenance,
    facts: Iterable[tuple[Any, Any]],
    goal: Any,
    *,
    module=None,
) -> list[tuple[Any, Any]]:
    """Run the bottom-up engine for `goal`; return matching ``(term, tag)`` pairs.

    Parameters
    ----------
    semiring
        A ``Provenance`` instance (e.g., ``boolean``).
    facts
        Iterable of ``(ground_term, user_tag)``. Each ground_term must be
        an instance of a ``-bottom_up`` predicate (registered via
        ``bottom_up_/1``). User tags are lifted via
        ``semiring.tagging_fn``.
    goal
        A goal term whose head is a ``-bottom_up`` predicate. Variables
        in the goal will be matched against the final relation.
    module
        Optional ``clausal.Module`` for resolving foreign predicates in
        rule bodies. If omitted, inferred from the goal's predicate class.

    Returns
    -------
    list[(ground_term, output_tag)]
        Each entry is one ground answer term with its semiring-recovered
        tag. ``output_tag`` is ``semiring.recover_fn(internal_tag)``.
    """
    from clausal.logic.solve import _infer_module, _coerce_module

    # ── Resolve module ───────────────────────────────────────────────
    if module is None:
        module = _infer_module(goal)
    else:
        module = _coerce_module(module)
    if module is None:
        raise TypeError(
            "Cannot infer module from goal. Pass module= explicitly."
        )

    # ── Discover all -bottom_up predicates reachable from the goal's
    #    predicate class via clause bodies. Walk transitive closure.
    pred_classes = _discover_bottom_up_predicates(goal, module)

    # ── Initialize relations from facts ──────────────────────────────
    # Predicates that appear only as input data (no rules of their own,
    # nor referenced via rule body of another -bottom_up predicate) need
    # to be admitted to the program too. A fact's class must be
    # registered as -bottom_up (or be the goal predicate's class).
    fact_list = list(facts)
    for term, _user_tag in fact_list:
        if not _is_ground(term):
            raise NonGroundTupleError(
                f"Input fact is not ground: {term!r}"
            )
        key = head_key(term)
        if key in pred_classes:
            continue
        cls = _class_for_term(term, module)
        if cls is None or not is_bottom_up(cls):
            raise ValueError(
                f"Fact {term!r} has key {key} which is not a -bottom_up "
                f"predicate. Mark it via `bottom_up_({key[0]})`."
            )
        pred_classes[key] = cls

    relations: dict[tuple[str, int], Relation] = {
        key: Relation(cls) for key, cls in pred_classes.items()
    }
    for term, user_tag in fact_list:
        key = head_key(term)
        tup = _term_to_tuple(term)
        relations[key].add(tup, semiring.tagging_fn(user_tag), semiring)

    # ── Validate purity ──────────────────────────────────────────────
    validate_purity(pred_classes, module=module)

    # ── Stratify and evaluate ────────────────────────────────────────
    program = {key: list(_clauses_of(cls)) for key, cls in pred_classes.items()}
    sccs = stratify(program)
    for scc in sccs:
        _evaluate_stratum(scc, relations, pred_classes, semiring, module)

    # ── Filter by the goal ───────────────────────────────────────────
    return _filter_by_goal(goal, pred_classes, relations, semiring)


def _discover_bottom_up_predicates(
    goal: Any,
    module,
) -> dict[tuple[str, int], PredicateMeta]:
    """Collect every -bottom_up predicate transitively referenced by `goal`'s
    predicate class clauses, plus the goal's own class."""
    out: dict[tuple[str, int], PredicateMeta] = {}
    stack: list[PredicateMeta] = []

    cls = _class_for_term(goal, module)
    if cls is None:
        raise TypeError(
            f"Goal {goal!r} is not a predicate term (expected a cell whose "
            "functor names a predicate in this module, a PredicateMeta "
            "instance, or a class)."
        )
    root_cls = cls
    stack.append(cls)

    md = module.module_dict if hasattr(module, "module_dict") else None

    while stack:
        cls = stack.pop()
        if not is_bottom_up(cls):
            # The goal predicate must be -bottom_up; intermediate callees
            # only count if they are -bottom_up. Pure callees are treated
            # as leaves.
            if cls is not None and (cls._functor, cls._arity) in out:
                continue
            # Goal is required to be bottom_up; if the *root* fails this,
            # error early.
            if not out and cls is root_cls:
                raise ValueError(
                    f"Goal predicate {cls.__name__}/{cls._arity} is not "
                    f"registered as -bottom_up. Add `bottom_up_({cls.__name__})` "
                    "at module load time."
                )
            continue
        key = (cls._functor, cls._arity)
        if key in out:
            continue
        out[key] = cls
        # Walk callees in clause bodies
        for clause in _clauses_of(cls):
            for callee in _collect_body_callees(clause.body):
                callee_cls = None
                if md is not None:
                    obj = md.get(callee[0])
                    if isinstance(obj, PredicateMeta) and obj._arity == callee[1]:
                        callee_cls = obj
                if callee_cls is None:
                    # Fallback: search via class' module
                    import sys
                    obj = getattr(sys.modules.get(cls.__module__), callee[0], None)
                    if isinstance(obj, PredicateMeta) and obj._arity == callee[1]:
                        callee_cls = obj
                if callee_cls is not None and is_bottom_up(callee_cls):
                    stack.append(callee_cls)

    return out


def goal_cls_initial(stack, goal, module=None):
    """Helper: re-derive the original goal class for error messages.

    NEEDS THE MODULE to answer for a CELL -- a cell carries only its functor,
    and without a module dict to resolve it this returns the TERM, which is
    the right thing for a message but is NOT the class.  The root-predicate
    check in ``_discover_bottom_up_predicates`` used to compare against this
    and silently stopped matching when the goal became a cell; it now holds
    the root class directly, from the one place the module is in scope.
    """
    return _class_for_term(goal, module) or goal


def _filter_by_goal(
    goal: Any,
    pred_classes: dict[tuple[str, int], PredicateMeta],
    relations: dict[tuple[str, int], Relation],
    semiring: Provenance,
) -> list[tuple[Any, Any]]:
    """Match the goal against the final relations.

    For each ground tuple in the goal's predicate's relation, attempt to
    unify with the goal term; on success, build a fresh ground term and
    record (term, recovered_tag).
    """
    # No ``module`` here -- ``pred_classes`` is already the resolved map, so a
    # CELL goal keys straight into it rather than repeating the lookup.
    cls = _class_for_term(goal)
    if cls is not None:
        key = (cls._functor, cls._arity)
    elif type(goal) is tuple:
        key = head_key(goal)
        cls = pred_classes.get(key)
        if cls is None:
            raise TypeError(f"Cannot match goal {goal!r}.")
    else:
        raise TypeError(f"Cannot match goal {goal!r}.")

    rel = relations.get(key)
    if rel is None:
        return []

    fields = cls._fields
    # A goal supplies the patterns its arguments must match; a bare CLASS
    # supplies none, so every slot is a fresh Var and everything matches.
    if isinstance(goal, type):
        patterns: tuple = tuple(Var() for _ in fields)
    else:
        patterns = _term_args(goal)
    out: list[tuple[Any, Any]] = []
    trail = Trail()
    for tup, tag in rel.tuples.items():
        mark = trail.mark()
        ok = True
        for pattern, val in zip(patterns, tup):
            if not unify(pattern, val, trail):
                ok = False
                break
        if ok:
            ground = cls(**{n: v for n, v in zip(fields, tup)})
            out.append((ground, semiring.recover_fn(tag)))
        trail.undo(mark)
    return out


__all__ = [
    "evaluate",
    "Relation",
    "PurityError",
    "NonGroundTupleError",
    "StratificationError",
]
