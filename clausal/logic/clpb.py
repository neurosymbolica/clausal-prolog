"""clausal.logic.clpb — CLP(B) Boolean constraint solver.

Constraint Logic Programming over Booleans using reduced ordered BDDs
(Binary Decision Diagrams).  Follows Markus Triska's reference design:
per-variable unique tables, local apply memoization, static variable
ordering, formula storage for aliasing rebuild.

Provides:
  - ``sat(expr, trail)`` — post Boolean constraint, fail if unsatisfiable
  - ``taut(expr, t_var, trail)`` — tautology check
  - ``sat_count(expr, count_var, trail)`` — count satisfying assignments
  - ``bool_labeling(vars_list, trail)`` — enumerate 0/1 assignments

Boolean expressions use Python bitwise operators:
  ``X_ & Y_`` (AND), ``X_ | Y_`` (OR), ``X_ ^ Y_`` (XOR), ``~X_`` (NOT)
  ``BoolEq(X_, Y_)`` (equivalence), ``BoolImpl(X_, Y_)`` (implication)

Trail safety
------------
Every state change creates a **new** ``BoolState`` and calls
``put_attr(var, B_KEY, new_state, trail)``.  The old state is restored
on backtrack.  Never mutate in place.
"""

from __future__ import annotations

import weakref
from typing import Any

from clausal.logic.variables import (
    Var,
    Trail,
    deref,
    is_var,
    unify,
    put_attr,
    get_attr,
    register_attr_hook,
)
from clausal.logic.predicate import make_predicate

# ── Constants ────────────────────────────────────────────────────────────────

B_KEY = "clpb"

BDD_TRUE = 1
BDD_FALSE = 0

# ── Term constructors for equivalence / implication ──────────────────────────

BoolEq = make_predicate("BoolEq", ["left", "right"])
BoolImpl = make_predicate("BoolImpl", ["left", "right"])

# ── BDD node representation ─────────────────────────────────────────────────


class BDDNode:
    """Internal BDD node: if var_id then high else low."""
    __slots__ = ('var_id', 'high', 'low', '_hash')

    def __init__(self, var_id: int, high, low):
        self.var_id = var_id
        self.high = high   # BDD when var=1
        self.low = low     # BDD when var=0
        self._hash = hash((var_id, id(high), id(low)))

    def __eq__(self, other):
        return self is other

    def __hash__(self):
        return self._hash

    def __repr__(self):
        return f"BDDNode({self.var_id}, {self.high!r}, {self.low!r})"


# ── Variable ordering ───────────────────────────────────────────────────────

_next_var_id: int = 0
_var_to_id: dict[int, int] = {}   # id(Var) → ordering index
_id_to_var: dict[int, Var] = {}   # ordering index → Var (strong ref)

# Per-trail record of the (vid, idx) allocated while a trail was live, so the
# module-global tables can be pruned when the trail is garbage-collected
# (A07-F006).  _id_to_var holds a STRONG ref to each Var (Var is not
# weakref-able, so we can't hang the cleanup off the var itself); without
# pruning, every CLP(B) var and its whole BDD level are pinned forever, a
# linear leak per query.  Keying cleanup on the (weakref-able) Trail bounds
# the tables to the lifetime of the constraint store that owns them.
_trail_allocs: dict[int, list] = {}   # id(Trail) → [(vid, idx), ...]


def _register_alloc(trail, vid: int, idx: int) -> None:
    if trail is None:
        return
    tid = id(trail)
    allocs = _trail_allocs.get(tid)
    if allocs is None:
        allocs = []
        _trail_allocs[tid] = allocs
        weakref.finalize(trail, _cleanup_trail_allocs, tid)
    allocs.append((vid, idx))


def _cleanup_trail_allocs(tid: int) -> None:
    for vid, idx in _trail_allocs.pop(tid, ()):
        _var_to_id.pop(vid, None)
        _id_to_var.pop(idx, None)
        _unique_tables.pop(vid, None)


def enumerate_var(var: Var, trail: Trail | None = None) -> int:
    """Assign a monotonic ordering ID to a variable on first encounter.

    When *trail* is given, the allocation is registered for cleanup when that
    trail is garbage-collected (A07-F006); direct/test callers may omit it.
    """
    global _next_var_id
    vid = id(var)
    if vid in _var_to_id:
        return _var_to_id[vid]
    idx = _next_var_id
    _next_var_id += 1
    _var_to_id[vid] = idx
    _id_to_var[idx] = var
    _register_alloc(trail, vid, idx)
    return idx


def _get_var_for_id(var_id: int) -> Var | None:
    """Look up the Var object for a given ordering ID."""
    return _id_to_var.get(var_id)


# ── Per-variable unique tables (Triska/Knuth technique) ──────────────────────

# Module-level dict: id(Var) → unique table dict.
# Not trail-managed — rebuilt on aliasing (natural GC).
_unique_tables: dict[int, dict] = {}


def _get_unique_table(var: Var) -> dict:
    """Get or create the per-variable unique table."""
    vid = id(var)
    tbl = _unique_tables.get(vid)
    if tbl is None:
        tbl = {}
        _unique_tables[vid] = tbl
    return tbl


def make_node(var_id: int, high, low, var: Var) -> Any:
    """Create or retrieve a BDD node from the per-variable unique table.

    Applies the reduction rule: if high == low, return low (skip node).
    """
    if high is low:
        return low
    tbl = _get_unique_table(var)
    key = (id(high), id(low))
    node = tbl.get(key)
    if node is not None:
        return node
    node = BDDNode(var_id, high, low)
    tbl[key] = node
    return node


# ── BDD apply operation ─────────────────────────────────────────────────────


def _var_id_of(bdd) -> int:
    """Return the top variable ID of a BDD, or infinity for terminals."""
    if isinstance(bdd, BDDNode):
        return bdd.var_id
    return float('inf')


def apply(op: str, f, g, memo: dict | None = None):
    """Apply a binary Boolean operation to two BDDs.

    Local memoization: memo dict is created per call, not persisted.
    """
    if memo is None:
        memo = {}

    key = (op, id(f), id(g))
    cached = memo.get(key)
    if cached is not None:
        return cached

    result = _apply_terminal(op, f, g)
    if result is not None:
        memo[key] = result
        return result

    # Shannon expansion: pick variable with lowest var_id
    fid = _var_id_of(f)
    gid = _var_id_of(g)
    min_id = min(fid, gid)

    # Cofactors for f
    if isinstance(f, BDDNode) and f.var_id == min_id:
        f_high, f_low = f.high, f.low
    else:
        f_high, f_low = f, f

    # Cofactors for g
    if isinstance(g, BDDNode) and g.var_id == min_id:
        g_high, g_low = g.high, g.low
    else:
        g_high, g_low = g, g

    high = apply(op, f_high, g_high, memo)
    low = apply(op, f_low, g_low, memo)

    # Get the variable for this level to use its unique table
    var = _get_var_for_id(min_id)
    if var is not None:
        result = make_node(min_id, high, low, var)
    else:
        # Fallback — shouldn't happen in normal use
        if high is low:
            result = low
        else:
            result = BDDNode(min_id, high, low)

    memo[key] = result
    return result


def _apply_terminal(op: str, f, g):
    """Handle terminal cases for apply. Returns result or None."""
    f_term = not isinstance(f, BDDNode)
    g_term = not isinstance(g, BDDNode)

    if op == 'and':
        if f is BDD_FALSE or g is BDD_FALSE:
            return BDD_FALSE
        if f is BDD_TRUE:
            return g
        if g is BDD_TRUE:
            return f
    elif op == 'or':
        if f is BDD_TRUE or g is BDD_TRUE:
            return BDD_TRUE
        if f is BDD_FALSE:
            return g
        if g is BDD_FALSE:
            return f
    elif op == 'xor':
        if f_term and g_term:
            return BDD_TRUE if (f != g) else BDD_FALSE
        if f is BDD_FALSE:
            return g
        if g is BDD_FALSE:
            return f
    elif op == 'equiv':
        if f_term and g_term:
            return BDD_TRUE if (f == g) else BDD_FALSE
        if f is BDD_TRUE:
            return g
        if g is BDD_TRUE:
            return f
    elif op == 'impl':
        # f → g  ≡  ¬f ∨ g
        if f is BDD_FALSE or g is BDD_TRUE:
            return BDD_TRUE
        if f is BDD_TRUE:
            return g
        if g is BDD_FALSE and f_term:
            return BDD_TRUE if f is BDD_FALSE else BDD_FALSE
    elif op == 'nand':
        if f is BDD_FALSE or g is BDD_FALSE:
            return BDD_TRUE
        if f_term and g_term:
            return BDD_FALSE  # both TRUE

    return None


def negate(bdd):
    """Negate a BDD: ¬bdd = bdd XOR 1."""
    return apply('xor', bdd, BDD_TRUE)


def restrict(bdd, var_id: int, value: int):
    """Restrict a BDD: substitute var_id = value (0 or 1).

    Follows the low branch for value=0, high branch for value=1.
    """
    if not isinstance(bdd, BDDNode):
        return bdd
    if bdd.var_id == var_id:
        return bdd.high if value else bdd.low
    if bdd.var_id > var_id:
        return bdd
    # Recurse on both children
    high = restrict(bdd.high, var_id, value)
    low = restrict(bdd.low, var_id, value)
    if high is low:
        return low
    var = _get_var_for_id(bdd.var_id)
    if var is not None:
        return make_node(bdd.var_id, high, low, var)
    if high is bdd.high and low is bdd.low:
        return bdd
    return BDDNode(bdd.var_id, high, low)


# ── Expression → BDD conversion ─────────────────────────────────────────────

# Lazy imports to avoid circular dependencies
_BitAnd = _BitOr = _BitXor = _Invert = None


def _ensure_node_imports():
    global _BitAnd, _BitOr, _BitXor, _Invert
    if _BitAnd is None:
        from clausal.pythonic_ast.nodes import BitAnd, BitOr, BitXor, Invert
        _BitAnd = BitAnd
        _BitOr = BitOr
        _BitXor = BitXor
        _Invert = Invert


def _expr_to_bdd(expr, trail: Trail | None = None):
    """Convert a Boolean expression tree to a BDD."""
    expr = deref(expr)

    # Terminal constants
    if isinstance(expr, bool):
        return BDD_TRUE if expr else BDD_FALSE
    if isinstance(expr, int):
        if expr == 1:
            return BDD_TRUE
        if expr == 0:
            return BDD_FALSE
        raise ValueError(f"CLP(B): integer must be 0 or 1, got {expr}")

    # Logic variable → identity BDD
    if is_var(expr):
        var_id = enumerate_var(expr, trail)
        var = expr
        return make_node(var_id, BDD_TRUE, BDD_FALSE, var)

    _ensure_node_imports()

    # BoolEq / BoolImpl term constructors
    if isinstance(expr, type(BoolEq()).__class__) or (hasattr(expr, '_fields') and hasattr(type(expr), '_functor')):
        functor = type(expr).__name__
        if functor == 'BoolEq':
            left_bdd = _expr_to_bdd(expr.left, trail)
            right_bdd = _expr_to_bdd(expr.right, trail)
            return apply('equiv', left_bdd, right_bdd)
        if functor == 'BoolImpl':
            left_bdd = _expr_to_bdd(expr.left, trail)
            right_bdd = _expr_to_bdd(expr.right, trail)
            return apply('impl', left_bdd, right_bdd)

    # Bitwise operators from AST nodes
    if isinstance(expr, _BitAnd):
        left_bdd = _expr_to_bdd(expr.left, trail)
        right_bdd = _expr_to_bdd(expr.right, trail)
        return apply('and', left_bdd, right_bdd)

    if isinstance(expr, _BitOr):
        left_bdd = _expr_to_bdd(expr.left, trail)
        right_bdd = _expr_to_bdd(expr.right, trail)
        return apply('or', left_bdd, right_bdd)

    if isinstance(expr, _BitXor):
        left_bdd = _expr_to_bdd(expr.left, trail)
        right_bdd = _expr_to_bdd(expr.right, trail)
        return apply('xor', left_bdd, right_bdd)

    if isinstance(expr, _Invert):
        operand_bdd = _expr_to_bdd(expr.operand, trail)
        return negate(operand_bdd)

    raise TypeError(f"CLP(B): unsupported expression type {type(expr).__name__}: {expr!r}")


def _collect_bool_vars(expr, result: set | None = None) -> set:
    """Collect all Var objects from a Boolean expression tree."""
    if result is None:
        result = set()
    expr = deref(expr)
    if is_var(expr):
        result.add(id(expr))
        return result
    if isinstance(expr, (int, bool)):
        return result
    _ensure_node_imports()
    if isinstance(expr, (_BitAnd, _BitOr, _BitXor)):
        _collect_bool_vars(expr.left, result)
        _collect_bool_vars(expr.right, result)
    elif isinstance(expr, _Invert):
        _collect_bool_vars(expr.operand, result)
    elif hasattr(expr, 'left') and hasattr(expr, 'right'):
        _collect_bool_vars(expr.left, result)
        _collect_bool_vars(expr.right, result)
    return result


def _collect_bool_var_objects(expr, result: list | None = None) -> list:
    """Collect all Var objects from a Boolean expression tree (preserving objects)."""
    if result is None:
        result = []
    expr = deref(expr)
    if is_var(expr):
        if not any(v is expr for v in result):
            result.append(expr)
        return result
    if isinstance(expr, (int, bool)):
        return result
    _ensure_node_imports()
    if isinstance(expr, (_BitAnd, _BitOr, _BitXor)):
        _collect_bool_var_objects(expr.left, result)
        _collect_bool_var_objects(expr.right, result)
    elif isinstance(expr, _Invert):
        _collect_bool_var_objects(expr.operand, result)
    elif hasattr(expr, 'left') and hasattr(expr, 'right'):
        _collect_bool_var_objects(expr.left, result)
        _collect_bool_var_objects(expr.right, result)
    return result


# ── Per-variable CLP(B) state ───────────────────────────────────────────────


class BoolState:
    """Boolean constraint state for one variable.

    Immutable for trail safety — updates create a new instance.
    """
    __slots__ = ('sat_expr', 'bdd', 'root_var')

    def __init__(self, sat_expr, bdd, root_var: Var):
        self.sat_expr = sat_expr    # original Boolean formula (for rebuild)
        self.bdd = bdd              # current BDD (BDDNode or terminal)
        self.root_var = root_var    # shared root variable linking all vars

    def __repr__(self):
        return f"BoolState(bdd={self.bdd!r}, root={self.root_var!r})"


def _ensure_bool(var: Var, trail: Trail) -> BoolState:
    """Get or auto-create BoolState for a variable."""
    state = get_attr(var, B_KEY)
    if state is not None:
        return state
    # Create identity BDD for this variable
    var_id = enumerate_var(var, trail)
    bdd = make_node(var_id, BDD_TRUE, BDD_FALSE, var)
    state = BoolState(sat_expr=None, bdd=bdd, root_var=var)
    put_attr(var, B_KEY, state, trail)
    return state


# ── Core solver functions ────────────────────────────────────────────────────


def sat(expr, trail: Trail) -> bool:
    """Post a Boolean constraint. Returns False if unsatisfiable.

    Builds a BDD from the expression, conjoins with ALL existing constraints
    on connected variables, and propagates forced values.  This ensures that
    multiple sat() calls sharing variables form a single constraint network.
    """
    expr = deref(expr)
    bdd = _expr_to_bdd(expr, trail)

    if bdd is BDD_FALSE:
        return False
    if bdd is BDD_TRUE:
        return True

    # Collect all variables in this expression
    vars_ = _collect_bool_var_objects(expr)
    if not vars_:
        return bdd is BDD_TRUE

    # Gather all existing BDDs from variables in this expression,
    # and transitively from variables in those BDDs (connected components).
    combined_bdd = bdd
    seen_bdd_ids: set[int] = {id(bdd)}
    all_vars: list[Var] = list(vars_)
    processed: set[int] = set()
    # Accumulate every formula posted to this network so var-var aliasing can
    # rebuild the BDD from source and collapse the merged levels (A07-F002).
    formulas: list = [expr]
    formula_ids: set[int] = {id(expr)}

    i = 0
    while i < len(all_vars):
        v = deref(all_vars[i])
        i += 1
        if not is_var(v):
            continue
        vid = id(v)
        if vid in processed:
            continue
        processed.add(vid)

        state = get_attr(v, B_KEY)
        if state is None:
            continue
        bid = id(state.bdd)
        if bid in seen_bdd_ids:
            continue
        seen_bdd_ids.add(bid)

        # Carry this component's posted formulas into the merged network.
        for f in _formulas_of(state):
            if id(f) not in formula_ids:
                formula_ids.add(id(f))
                formulas.append(f)

        # Conjoin this existing BDD
        combined_bdd = apply('and', combined_bdd, state.bdd)
        if combined_bdd is BDD_FALSE:
            return False

        # Discover any new variables from this BDD
        new_var_ids: set = set()
        _collect_bdd_var_ids(state.bdd, new_var_ids)
        for nid in new_var_ids:
            nv = _get_var_for_id(nid)
            if nv is not None:
                nv = deref(nv)
                if is_var(nv) and id(nv) not in processed:
                    all_vars.append(nv)

    if combined_bdd is BDD_FALSE:
        return False

    # Store combined BDD + the accumulated formula set on all unbound vars.
    merged_expr = tuple(formulas)
    for v in all_vars:
        v = deref(v)
        if not is_var(v):
            continue
        new_state = BoolState(sat_expr=merged_expr, bdd=combined_bdd, root_var=all_vars[0])
        put_attr(v, B_KEY, new_state, trail)

    # Propagate: check if any variable is forced to 0 or 1
    return _propagate_forced(combined_bdd, trail)


def _propagate_forced(bdd, trail: Trail) -> bool:
    """Check all variables in a BDD and unify any that are forced."""
    if not isinstance(bdd, BDDNode):
        return True

    # Collect all var_ids in the BDD
    var_ids = set()
    _collect_bdd_var_ids(bdd, var_ids)

    for vid in var_ids:
        var = _get_var_for_id(vid)
        if var is None:
            continue
        var = deref(var)
        if not is_var(var):
            continue

        # Check if restricting to 0 gives FALSE → variable must be 1
        r0 = restrict(bdd, vid, 0)
        r1 = restrict(bdd, vid, 1)

        if r0 is BDD_FALSE and r1 is BDD_FALSE:
            return False
        if r0 is BDD_FALSE:
            if not unify(var, 1, trail):
                return False
        elif r1 is BDD_FALSE:
            if not unify(var, 0, trail):
                return False

    return True


def _collect_bdd_var_ids_impl(bdd, result: set, _seen: set | None = None):
    """Collect all variable IDs present in a BDD.

    A BDD is a hash-consed DAG: shared sub-nodes are the same object, so a
    visited-set keyed by node identity keeps this O(nodes) instead of
    O(paths) — without it an n-var XOR chain (2n-1 nodes, 2^n paths) makes
    sat/sat_count exponential (A07-F001).

    Recurses via its own private name so it stays a correct pure-Python
    reference even after the module-global ``_collect_bdd_var_ids`` is rebound
    to the 2-arg C wrapper (A07-F008).
    """
    if _seen is None:
        _seen = set()
    if not isinstance(bdd, BDDNode):
        return
    nid = id(bdd)
    if nid in _seen:
        return
    _seen.add(nid)
    result.add(bdd.var_id)
    _collect_bdd_var_ids_impl(bdd.high, result, _seen)
    _collect_bdd_var_ids_impl(bdd.low, result, _seen)


# Dispatch name (rebound to the C wrapper below when the extension loads).
_collect_bdd_var_ids = _collect_bdd_var_ids_impl


def taut(expr, t_var, trail: Trail) -> bool:
    """Tautology check: unify t_var=1 if expr is always true,
    t_var=0 if always false. Fail if indeterminate.
    """
    expr = deref(expr)
    bdd = _expr_to_bdd(expr, trail)

    if bdd is BDD_TRUE:
        return unify(t_var, 1, trail)
    if bdd is BDD_FALSE:
        return unify(t_var, 0, trail)
    # Indeterminate — fail
    return False


def sat_count(expr, count_var, trail: Trail) -> bool:
    """Count the number of satisfying assignments for expr.

    Unifies count_var with the count.
    """
    expr = deref(expr)
    bdd = _expr_to_bdd(expr, trail)

    # Collect all variable IDs from the expression (not just BDD — reduced
    # vars may be absent from BDD but still contribute to counting).
    var_ids = set()
    vars_ = _collect_bool_var_objects(expr)
    for v in vars_:
        v = deref(v)
        if is_var(v):
            vid = id(v)
            if vid in _var_to_id:
                var_ids.add(_var_to_id[vid])
    # Also pick up any in the BDD itself
    _collect_bdd_var_ids(bdd, var_ids)

    n_vars = len(var_ids)
    if n_vars == 0:
        count = 1 if bdd is BDD_TRUE else 0
        return unify(count_var, count, trail)

    # Map var_ids to sorted list for level assignment
    sorted_ids = sorted(var_ids)
    level_map = {vid: i for i, vid in enumerate(sorted_ids)}

    count = _count_paths(bdd, level_map, n_vars, {})
    return unify(count_var, count, trail)


def _count_paths_impl(bdd, level_map: dict, n_vars: int, memo: dict,
                      current_level: int = 0) -> int:
    """Count satisfying paths in a BDD, accounting for skipped variables.

    current_level is the expected level at this point in the BDD traversal.

    Recurses via its own private name (not the module-global ``_count_paths``,
    which the C block rebinds to a wrapper that drops current_level/memo), so
    this stays a correct pure-Python reference even when C is loaded
    (A07-F008).
    """
    if bdd is BDD_TRUE:
        # All remaining variables can be 0 or 1
        remaining = n_vars - current_level
        return 2 ** remaining if remaining > 0 else 1
    if bdd is BDD_FALSE:
        return 0

    key = (id(bdd), current_level)
    if key in memo:
        return memo[key]

    node_level = level_map.get(bdd.var_id, current_level)

    # Account for skipped variables between current_level and node_level
    skipped = node_level - current_level
    multiplier = 2 ** skipped if skipped > 0 else 1

    high_count = _count_paths_impl(bdd.high, level_map, n_vars, memo,
                                   node_level + 1)
    low_count = _count_paths_impl(bdd.low, level_map, n_vars, memo,
                                  node_level + 1)

    result = multiplier * (high_count + low_count)
    memo[key] = result
    return result


# Dispatch name (rebound to the C wrapper below when the extension loads).
_count_paths = _count_paths_impl


def bool_labeling(vars_list, trail: Trail):
    """Enumerate 0/1 assignments for Boolean variables.

    Generator: yields None for each satisfying assignment.
    """
    vars_list = deref(vars_list)
    if isinstance(vars_list, list):
        vars_ = vars_list
    else:
        # Try to convert cons list
        from clausal.terms import cons_to_list
        try:
            vars_ = cons_to_list(vars_list)
        except (ValueError, TypeError):
            vars_ = [vars_list]

    yield from _label_bools(vars_, trail)


def _label_bools(vars_: list, trail: Trail):
    """Recursive labeling of Boolean variables."""
    # Validate: every already-ground element must be a Boolean 0/1 integer
    # (A07-F009).  bool is excluded per A01-D001 (bool is not an int here);
    # SWI clpb raises type_error(sat, _) for non-Boolean terms.
    for v in vars_:
        dv = deref(v)
        if not is_var(dv) and (type(dv) is not int or dv not in (0, 1)):
            raise TypeError(
                f"bool_labeling: expected a Boolean variable or 0/1, got {dv!r}"
            )
    # Find first unbound variable
    target = None
    target_idx = None
    for i, v in enumerate(vars_):
        v = deref(v)
        if is_var(v):
            target = v
            target_idx = i
            break

    if target is None:
        # All bound — yield solution
        yield None
        return

    # Try 0 then 1
    for val in (0, 1):
        mark = trail.mark()
        if unify(target, val, trail):
            yield from _label_bools(vars_, trail)
        trail.undo(mark)


# ── Attribute hook ───────────────────────────────────────────────────────────


def _formulas_of(state) -> tuple:
    """The posted formula(s) recorded on a BoolState, as a flat tuple.

    ``sat_expr`` is a tuple of every formula posted to the variable's network
    (or ``None`` for an auto-created identity state); older single-formula
    values are wrapped for backward compatibility.
    """
    se = state.sat_expr if state is not None else None
    if se is None:
        return ()
    if isinstance(se, tuple):
        return se
    return (se,)


def _bool_hook(attr_value: Any, bound_to: Any, trail: Trail) -> bool:
    """Called when a CLP(B)-constrained variable is unified.

    *attr_value* is the BoolState snapshot (from before unification).
    *bound_to* is the value the variable was bound to.
    """
    state = attr_value
    bound_to = deref(bound_to)

    # Python bool is a subclass of int, so True/False would otherwise slip
    # through the 0/1 check and pin the var to True/False.  CLP(B)'s domain is
    # the integers {0, 1}; reject bool, consistent with CLP(Z)/CLP(R) and the
    # A01-D001 decision to stop conflating bool with int (A07-F010).
    if isinstance(bound_to, bool):
        return False

    if isinstance(bound_to, int):
        if bound_to not in (0, 1):
            return False

        # Restrict BDD at this variable's level
        bdd = state.bdd
        if isinstance(bdd, BDDNode):
            # Find the var_id for the variable that was just bound
            # We need to restrict the BDD for ALL vars that are now bound
            new_bdd = bdd
            var_ids = set()
            _collect_bdd_var_ids(new_bdd, var_ids)
            for vid in var_ids:
                v = _get_var_for_id(vid)
                if v is not None:
                    dv = deref(v)
                    if isinstance(dv, int):
                        new_bdd = restrict(new_bdd, vid, dv)

            if new_bdd is BDD_FALSE:
                return False

            # Propagate forced values on remaining variables
            if isinstance(new_bdd, BDDNode):
                # Update BoolState on remaining unbound vars
                remaining_ids = set()
                _collect_bdd_var_ids(new_bdd, remaining_ids)
                for vid in remaining_ids:
                    v = _get_var_for_id(vid)
                    if v is not None:
                        v = deref(v)
                        if is_var(v):
                            new_state = BoolState(
                                sat_expr=state.sat_expr,
                                bdd=new_bdd,
                                root_var=state.root_var,
                            )
                            put_attr(v, B_KEY, new_state, trail)

                return _propagate_forced(new_bdd, trail)

        return True

    if is_var(bound_to):
        # Var-var aliasing.  The two variables are now ONE logical variable but
        # occupy two distinct BDD levels; conjoining the stale per-var BDDs
        # (state.bdd & other.bdd) cannot express x_id == y_id, so it misses
        # failures and forced propagation (A07-F002).  Instead rebuild from the
        # posted formulas: the hook runs after the binding commits, so
        # _expr_to_bdd derefs the aliased vars to a single level and the
        # collapse falls out.
        other_state = get_attr(bound_to, B_KEY)
        if other_state is None:
            # Other var has no CLP(B) — transfer our state.
            put_attr(bound_to, B_KEY, state, trail)
            return True

        formulas: list = []
        seen_f: set = set()
        for f in _formulas_of(state) + _formulas_of(other_state):
            if id(f) not in seen_f:
                seen_f.add(id(f))
                formulas.append(f)

        new_bdd = BDD_TRUE
        for f in formulas:
            new_bdd = apply('and', new_bdd, _expr_to_bdd(f, trail))
            if new_bdd is BDD_FALSE:
                return False

        merged_expr = tuple(formulas)
        if isinstance(new_bdd, BDDNode):
            # Re-store the rebuilt BDD on every (still unbound) network var.
            ids: set = set()
            _collect_bdd_var_ids(new_bdd, ids)
            for vid in ids:
                v = _get_var_for_id(vid)
                if v is not None:
                    v = deref(v)
                    if is_var(v):
                        put_attr(v, B_KEY,
                                 BoolState(sat_expr=merged_expr, bdd=new_bdd,
                                           root_var=v),
                                 trail)
            return _propagate_forced(new_bdd, trail)
        # new_bdd is BDD_TRUE → the conjunction is a tautology, nothing to post.
        return True

    # Non-integer, non-var → fail
    return False


register_attr_hook(B_KEY, _bool_hook)


# ── C acceleration with Python fallback ─────────────────────────────────────
# Keep Python reference implementations so the module works without C.

_BDDNodePy = BDDNode
_apply_py = apply
_negate_py = negate
_restrict_py = restrict
# Point at the self-recursing _impl functions directly, so the saved
# reference stays pure even after the dispatch names are rebound to C below
# (A07-F008).
_count_paths_py = _count_paths_impl
_collect_bdd_var_ids_py = _collect_bdd_var_ids_impl

try:
    from clausal.logic._clpb_core import (
        BDDNode as _CBDDNode,
        c_apply as _c_apply,
        c_restrict as _c_restrict,
        c_count_paths as _c_count_paths,
        c_collect_bdd_var_ids as _c_collect_bdd_var_ids,
    )

    BDDNode = _CBDDNode

    def apply(op: str, f, g, memo: dict | None = None):  # noqa: F811
        return _c_apply(op, f, g, _unique_tables, _id_to_var)

    def negate(bdd):  # noqa: F811
        return _c_apply('xor', bdd, BDD_TRUE, _unique_tables, _id_to_var)

    def restrict(bdd, var_id: int, value: int):  # noqa: F811
        return _c_restrict(bdd, var_id, value, _unique_tables, _id_to_var)

    def _count_paths(bdd, level_map: dict, n_vars: int, memo: dict,  # noqa: F811
                     current_level: int = 0) -> int:
        return _c_count_paths(bdd, level_map, n_vars)

    def _collect_bdd_var_ids(bdd, result: set):  # noqa: F811
        _c_collect_bdd_var_ids(bdd, result)

except ImportError:
    pass


# ── Public API ───────────────────────────────────────────────────────────────

__all__ = [
    "BDD_TRUE", "BDD_FALSE", "BDDNode",
    "B_KEY",
    "BoolEq", "BoolImpl", "BoolState",
    "enumerate_var", "make_node", "apply", "negate", "restrict",
    "sat", "taut", "sat_count", "bool_labeling",
    "_expr_to_bdd", "_collect_bool_vars", "_collect_bool_var_objects",
    "_propagate_forced", "_collect_bdd_var_ids",
]
