"""Pre-E follow-up: verify ``walk_goal_ops_deep`` finds SubCalls
nested inside meta-call inners.

``walk_goal_ops`` (the original walker) cannot see
``MetaCall.args`` entries that carry raw terms — the schema today
keeps inner goals as Term, not GoalOp, because the lowering
forwards them to legacy ``_compile_*`` helpers that re-dispatch
themselves.  E's analyses need to reach into those inners; the
deep walker bridges the gap by lazily converting raw-term inners
through ``terms_to_goalop._convert`` at walk time.

These tests pin both directions: the standard walker misses the
nested SubCall, and the deep walker finds it.
"""

from __future__ import annotations

from clausal.logic.variables import Var
from clausal.terms import Call, LoadName


# All clausal.logic.compiler imports happen *inside* each test
# function: ``tests/test_runtime_compiler_boundary`` scrubs
# ``sys.modules['clausal.logic.compiler.*']`` mid-session to verify
# import-discipline.  Module-level imports here would leave us
# holding stale class references while ``terms_to_goalop``
# (re-imported per call) produces instances of the post-scrub
# classes — every isinstance check would then quietly fail.  Same
# fix as D6's parallel test files; see Slice D6a commit message
# for the full hazard write-up.


def _body_with_once_inner_call():
    """Body: once(Helper(X))."""
    x = Var()
    inner = Call(func=LoadName(name="Helper"), args=[x], kwargs=[])
    body = [Call(func=LoadName(name="once"), args=[inner], kwargs=[])]
    return body


def _collect_subcalls(walker_fn, ir, **kw):
    from clausal.logic.compiler.ir import GoalOp, SubCall
    found: list = []

    def visit(op: GoalOp) -> None:
        if isinstance(op, SubCall):
            found.append(op)

    walker_fn(ir, visit, **kw)
    return found


def test_walk_goal_ops_misses_meta_inner_subcall():
    """Baseline: standard walker does not see SubCalls inside once()."""
    from clausal.logic.compiler.terms_to_goalop import terms_to_goalop
    from clausal.logic.compiler.ir import walk_goal_ops
    ir = terms_to_goalop(_body_with_once_inner_call(), db=None)
    found = _collect_subcalls(walk_goal_ops, ir)
    # Should be empty — the once() arm wraps the call as raw Term.
    fnames = [sc.fname for sc in found]
    assert "Helper" not in fnames, (
        f"walk_goal_ops should NOT see Helper (the contract is that "
        f"raw-term inners are skipped); got {fnames}"
    )


def test_walk_goal_ops_deep_finds_meta_inner_subcall():
    """Deep walker descends into meta-call inners and surfaces SubCalls."""
    from clausal.logic.compiler.terms_to_goalop import terms_to_goalop
    ir = terms_to_goalop(_body_with_once_inner_call(), db=None)
    from clausal.logic.compiler.ir import walk_goal_ops_deep
    found = _collect_subcalls(walk_goal_ops_deep, ir)
    fnames = [sc.fname for sc in found]
    assert "Helper" in fnames, (
        f"walk_goal_ops_deep must see Helper inside once(); got {fnames}"
    )


def test_walk_goal_ops_deep_handles_findall_inner():
    """findall(Template, Inner, Bag) — inner is a goal, others are terms."""
    template, x, bag = Var(), Var(), Var()
    inner = Call(func=LoadName(name="Producer"), args=[x], kwargs=[])
    body = [Call(func=LoadName(name="findall"),
                 args=[template, inner, bag], kwargs=[])]
    from clausal.logic.compiler.terms_to_goalop import terms_to_goalop
    ir = terms_to_goalop(body, db=None)
    from clausal.logic.compiler.ir import walk_goal_ops_deep
    fnames = [sc.fname for sc in _collect_subcalls(walk_goal_ops_deep, ir)]
    assert "Producer" in fnames


def test_walk_goal_ops_deep_handles_setup_call_cleanup():
    """All three of setup/call/cleanup are goal positions."""
    a, b, c = Var(), Var(), Var()
    setup = Call(func=LoadName(name="Setup"), args=[a], kwargs=[])
    call_g = Call(func=LoadName(name="DoWork"), args=[b], kwargs=[])
    cleanup = Call(func=LoadName(name="Cleanup"), args=[c], kwargs=[])
    body = [Call(func=LoadName(name="setup_call_cleanup"),
                 args=[setup, call_g, cleanup], kwargs=[])]
    from clausal.logic.compiler.terms_to_goalop import terms_to_goalop
    ir = terms_to_goalop(body, db=None)
    from clausal.logic.compiler.ir import walk_goal_ops_deep
    fnames = set(sc.fname for sc in _collect_subcalls(walk_goal_ops_deep, ir))
    assert {"Setup", "DoWork", "Cleanup"} <= fnames, (
        f"deep walker must find all three goal-position SubCalls; got {fnames}"
    )


def test_walk_goal_ops_deep_skips_term_position_args():
    """Only goal-position args descend; term-position args (template,
    bag, var, count, code, error) are left alone."""
    template, x, bag = Var(), Var(), Var()
    inner = Call(func=LoadName(name="Producer"), args=[x], kwargs=[])
    body = [Call(func=LoadName(name="findall"),
                 args=[template, inner, bag], kwargs=[])]
    from clausal.logic.compiler.terms_to_goalop import terms_to_goalop
    ir = terms_to_goalop(body, db=None)
    # Even with deep walk, the only SubCall surfaced from a goal
    # position is "Producer".  Template/bag carry plain Vars, not
    # Calls, so there's nothing else to find — but the test pins the
    # *contract*: only META_GOAL_POSITIONS keys are descended.
    from clausal.logic.compiler.ir import META_GOAL_POSITIONS
    assert META_GOAL_POSITIONS["findall"] == ("inner",)


def test_walk_goal_ops_deep_handles_nested_meta_calls():
    """once(once(Helper(X))) — recursive descent through two layers."""
    x = Var()
    deepest = Call(func=LoadName(name="Helper"), args=[x], kwargs=[])
    middle = Call(func=LoadName(name="once"), args=[deepest], kwargs=[])
    body = [Call(func=LoadName(name="once"), args=[middle], kwargs=[])]
    from clausal.logic.compiler.terms_to_goalop import terms_to_goalop
    ir = terms_to_goalop(body, db=None)
    from clausal.logic.compiler.ir import walk_goal_ops_deep
    fnames = [sc.fname for sc in _collect_subcalls(walk_goal_ops_deep, ir)]
    assert "Helper" in fnames
