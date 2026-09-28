"""A05 constraints core (dif, attributed vars, reif) — adversarial audit tests (2026-07-05).

Findings ledger: docs/superpowers/audits/2026-07-05-fable-partition/05-constraints-core/findings.md

Suspected-bug tests assert the *correct* behaviour and are marked
``@pytest.mark.xfail(strict=False)`` with the finding ID; confirmed-correct
behaviour is a plain regression guard.  Run PER FILE only:

    python -m pytest tests/audit_2026_07_05/test_05_constraints_core.py -v

Crash-prone probes (A05-F002 segfaults the interpreter) run in a subprocess.
"""
import os
import subprocess
import sys
import tempfile
import textwrap

import pytest

from clausal.logic.cells import chars  # stage 2: a string is the carrier
from clausal.logic.atoms import mint
import clausal.logic.constraints as C
from clausal.logic.constraints import (
    dif,
    reify_eq,
    structural_eq,
    structural_neq,
    _collect_free_vars,
    DIF_KEY,
)
from clausal.logic.reif import eq__3, dif_t__3
from clausal.logic.variables import (
    Var,
    Trail,
    deref,
    is_var,
    unify,
    put_attr,
    get_attr,
)
from clausal.logic.builtins.attributes import (
    _put_attr__3,
    _get_attr__3,
    _del_attr__2,
    _get_attrs__2,
    _put_attrs__2,
    _is_att_var__1,
    _term_attributed_variables__2,
)
from clausal.logic.units_constraint import (
    UnitState,
    constrain_var_dims,
    _units_hook,
    _has_units,
)
from clausal.terms import (
    DictTerm,
    SetTerm,
    SegList,
    SegString,
    ConcreteSeg,
    VarSeg,
    Quantity,
)
from clausal.import_hook import _load_module
from clausal.logic.solve import solve, once


PYTHON = sys.executable
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_snippet(code: str) -> subprocess.CompletedProcess:
    """Run a Python snippet in a subprocess with the repo on PYTHONPATH."""
    env = dict(os.environ, PYTHONPATH=REPO)
    return subprocess.run(
        [PYTHON, "-c", textwrap.dedent(code)],
        capture_output=True, text=True, timeout=120, env=env,
        cwd=tempfile.gettempdir(),  # keep core dumps (A05-F002) out of the repo
    )


# ── Fixture loader (one load per module name; atoms are module-scoped) ───────

_loaded = {}


@pytest.fixture(scope="session")
def load(tmp_path_factory):
    def _load(name, source):
        if name not in _loaded:
            d = tmp_path_factory.mktemp("a05fix")
            p = d / f"{name}.clausal"
            p.write_text(source)
            _loaded[name] = _load_module(f"a05_{name}", str(p))
        return _loaded[name]
    yield _load
    _loaded.clear()


def answers(gen, *vars_):
    return [tuple(deref(v) for v in vars_) for _ in gen]


# ══════════════════════════════════════════════════════════════════════════
# A05-F001 — dif/2 silently drops constraints whose free vars live only
# inside DictTerm / SegList / SegString / Quantity: _collect_free_vars
# (Python AND C) walks only Var/tuple/list/Compound/term-instances, while
# the sandbox unify binds through any __unify__-hooked container.
# ══════════════════════════════════════════════════════════════════════════


class TestF001DifContainerBlindSpots:

    def test_dif_dictterm_enforced(self):
        t = Trail()
        a = Var()
        assert dif(DictTerm({"k": a}), DictTerm({"k": 1}), t) is True
        # making the two terms equal must now fail
        assert unify(a, 1, t) is False

    def test_dif_seglist_enforced(self):
        t = Trail()
        s = Var()
        sl = SegList([ConcreteSeg([1]), VarSeg(s)])
        assert dif(sl, [1, 2], t) is True
        assert unify(s, [2], t) is False

    def test_dif_segstring_enforced(self):
        t = Trail()
        s = Var()
        ss = SegString(["a", VarSeg(s)])
        assert dif(ss, chars("ab"), t) is True   # stage 2: the string is the carrier; a bare str is an atom
        assert unify(s, chars("b"), t) is False

    def test_dif_quantity_enforced(self):
        t = Trail()
        q = Var()
        assert dif(Quantity(q, {"m": 1}), Quantity(5, {"m": 1}), t) is True
        assert unify(q, 5, t) is False

    def test_collect_free_vars_containers(self):
        x = Var()
        assert _collect_free_vars(DictTerm({"k": x})) == [x]

    # ── controls: containers the collector DOES walk are enforced ──────────

    def test_control_dif_list_enforced(self):
        t = Trail()
        v = Var()
        assert dif([1, v], [1, 2], t) is True
        assert unify(v, 2, t) is False
        assert unify(v, 3, t) is True

    def test_control_dif_tuple_enforced(self):
        t = Trail()
        v = Var()
        assert dif((1, v), (1, 2), t) is True
        assert unify(v, 2, t) is False

    def test_control_dif_compound_enforced(self):
        t = Trail()
        v = Var()
        assert dif(("f", v, 2), ("f", 1, 2), t) is True
        assert unify(v, 1, t) is False

    def test_control_setterm_consistent_with_unifier(self):
        # unify() itself refuses SetTerm-with-var element unification, so
        # dif(SetTerm([Y]), SetTerm([2])) → immediately satisfied is
        # *consistent with the unifier* (no constraint needed).
        t = Trail()
        y = Var()
        assert unify(SetTerm([y]), SetTerm([2]), t) is False
        t2 = Trail()
        z = Var()
        assert dif(SetTerm([z]), SetTerm([2]), t2) is True
        assert get_attr(z, DIF_KEY) is None  # nothing pending — consistent

    def test_language_level_dict_is_not(self, load):
        m = load("f001dict", """
-double_quotes(atom)
dictpred(D, V) <- (
    D is not {"k": 1},
    D is {"k": V},
    V is 1
)
""")
        dd, v = Var(), Var()
        assert answers(solve(("dictpred", dd, v), m), v) == []


# ══════════════════════════════════════════════════════════════════════════
# A05-F002 — C _dif_hook: unchecked PyTuple_GET_ITEM on user-controllable
# attr-list items → SIGSEGV.  Reachable from pure Clausal code via the
# put_attr/3 builtin with key "dif".  Python fallback raises a clean
# TypeError instead.
# ══════════════════════════════════════════════════════════════════════════


F002_SNIPPET = """
import clausal.logic.constraints  # registers the dif hook
from clausal.logic.variables import Var, Trail, put_attr, unify
x = Var(); t = Trail()
put_attr(x, "dif", {attr_value!r}, t)
try:
    unify(x, 1, t)
    print("OK-returned")
except Exception as e:
    print("OK-raised", type(e).__name__)
"""


class TestF002DifHookMalformedAttr:

    @pytest.mark.parametrize("attr_value", [[42], [(1,)], ["ab"]])
    def test_malformed_pair_items_no_crash(self, attr_value):
        r = run_snippet(F002_SNIPPET.format(attr_value=attr_value))
        # Correct behaviour: clean Python-level failure or exception,
        # never a signal-death of the interpreter.
        assert r.returncode == 0, (
            f"interpreter died (rc={r.returncode}); stderr: {r.stderr[-500:]}"
        )

    def test_control_nonlist_attr_clean_typeerror(self):
        # attr_value that is not a list IS validated → clean TypeError.
        x = Var()
        t = Trail()
        put_attr(x, "dif", 42, t)
        with pytest.raises(TypeError):
            unify(x, 1, t)

    def test_control_attach_path_malformed_existing_clean(self):
        # dif() posting onto a var whose existing "dif" attr is malformed
        # raises cleanly in both impls (no crash).
        t = Trail()
        v = Var()
        put_attr(v, "dif", 42, t)
        x = Var()
        with pytest.raises(TypeError):
            dif(x, v, t)


# ══════════════════════════════════════════════════════════════════════════
# A05-F003 — structural_eq is asymmetric (ground SegString vs str) and
# inconsistent with reify_eq/dif/unify on values that unify with no
# bindings (str ↔ char-list Liskov contract; ground SegList ↔ list).
# Invariant asserted: structural_eq(x, y) ⟺ reify_eq(x, y) is True.
# ══════════════════════════════════════════════════════════════════════════


class TestF003StructuralEqInconsistencies:

    def test_segstring_str_symmetric(self):
        ss = SegString(["ab"])
        assert structural_eq("ab", ss) == structural_eq(ss, "ab")

    def test_str_charlist_retired_consistent_with_reify_eq(self):
        """P3-1 Task 5 (§1b): the str~char-list cons rule is retired --
        ``reify_eq``/``structural_eq`` must stay CONSISTENT with each
        other (the invariant this class asserts), now both False.
        (Formerly asserting both True.)
        """
        t = Trail()
        assert reify_eq("ab", ["a", "b"], t) is False
        assert structural_eq("ab", ["a", "b"]) is False

    def test_ground_seglist_vs_list(self):
        sl = SegList([ConcreteSeg([1, 2])])
        t = Trail()
        assert reify_eq(sl, [1, 2], t) is True
        assert structural_eq(sl, [1, 2]) is True

    # ── controls ────────────────────────────────────────────────────────────

    def test_control_basics(self):
        assert structural_eq(1, 1)
        assert not structural_eq(1, 2)
        assert structural_eq("a", "a")
        assert structural_eq([1, [2]], [1, [2]])
        assert not structural_eq((1, 2), [1, 2])  # tuple ≠ list (distinct types)
        x, y = Var(), Var()
        assert structural_eq(x, x)
        assert not structural_eq(x, y)
        assert structural_neq(x, y)

    def test_control_bound_var_chases(self):
        t = Trail()
        x, y = Var(), Var()
        unify(x, [1, 2], t)
        unify(y, [1, 2], t)
        assert structural_eq(x, y)

    def test_control_dictterm_dict_equivalence(self):
        # documented: DictTerm and plain dict are equivalent representations
        assert structural_eq(DictTerm({"k": 1}), {"k": 1})
        assert structural_eq({"k": 1}, DictTerm({"k": 1}))

    def test_control_compound(self):
        x = Var()
        assert structural_eq(("f", x, 1), ("f", x, 1))
        assert not structural_eq(("f", x), ("g", x))


# ══════════════════════════════════════════════════════════════════════════
# A05-F004 — term_attvars/2 collector blind to tuples (a core Clausal
# structure), plain dicts, sets, and Seg* terms.
# ══════════════════════════════════════════════════════════════════════════


def _attvar_with_attr(t):
    v = Var()
    put_attr(v, "k", 1, t)
    return v


class TestF004TermAttvarsBlindSpots:

    def test_tuple(self):
        t = Trail()
        v = _attvar_with_attr(t)
        out = Var()
        list(_term_attributed_variables__2((v,), out, t, []))
        assert deref(out) == [v]

    def test_plain_dict(self):
        t = Trail()
        v = _attvar_with_attr(t)
        out = Var()
        list(_term_attributed_variables__2({"a": v}, out, t, []))
        assert deref(out) == [v]

    def test_seglist(self):
        t = Trail()
        v = _attvar_with_attr(t)
        out = Var()
        list(_term_attributed_variables__2(SegList([ConcreteSeg([1]), VarSeg(v)]), out, t, []))
        assert deref(out) == [v]

    # ── controls ────────────────────────────────────────────────────────────

    def test_control_list_compound_dictterm(self):
        t = Trail()
        v = _attvar_with_attr(t)
        for term in ([v], ("f", v), DictTerm({"a": v})):
            out = Var()
            assert list(_term_attributed_variables__2(term, out, t, [])) == [None]
            assert deref(out) == [v]

    def test_control_through_bound_var(self):
        t = Trail()
        v = _attvar_with_attr(t)
        w = Var()
        unify(w, [v], t)
        out = Var()
        list(_term_attributed_variables__2(w, out, t, []))
        assert deref(out) == [v]

    def test_control_plain_var_excluded(self):
        t = Trail()
        out = Var()
        list(_term_attributed_variables__2([Var()], out, t, []))
        assert deref(out) == []


# ══════════════════════════════════════════════════════════════════════════
# A05-F005 — has_units/2 crashes with AttributeError instead of failing
# when the second argument is not a units predicate.
# ══════════════════════════════════════════════════════════════════════════


class TestF005HasUnitsErrorPath:

    def test_has_units_bad_arg_fails_cleanly(self):
        t = Trail()
        d = Var()
        assert list(_has_units(d, "meters", t, [])) == []

    # ── controls: the units hook itself is clean in every probed mode ──────

    def test_control_quantity_match_mismatch(self):
        t = Trail()
        d = Var()
        assert constrain_var_dims(d, {"m": 1}, t)
        assert unify(d, Quantity(3, {"m": 1}), t) is True
        t2 = Trail()
        d2 = Var()
        constrain_var_dims(d2, {"m": 1}, t2)
        assert unify(d2, Quantity(3, {"s": 1}), t2) is False

    def test_control_zero_exponent_normalisation(self):
        t = Trail()
        d = Var()
        constrain_var_dims(d, {"m": 1, "s": 0}, t)   # zero exps stripped
        assert unify(d, Quantity(3, {"m": 1}), t) is True

    def test_control_dimensionless_number(self):
        t = Trail()
        d = Var()
        constrain_var_dims(d, {}, t)
        assert unify(d, 5, t) is True
        t2 = Trail()
        d2 = Var()
        constrain_var_dims(d2, {"m": 1}, t2)
        assert unify(d2, 5, t2) is False
        t3 = Trail()
        d3 = Var()
        constrain_var_dims(d3, {"m": 1}, t3)
        assert unify(d3, True, t3) is False  # bools rejected

    def test_control_var_var_merge_and_transfer(self):
        t = Trail()
        a, b = Var(), Var()
        constrain_var_dims(a, {"m": 1}, t)
        constrain_var_dims(b, {"m": 1}, t)
        assert unify(a, b, t) is True
        t2 = Trail()
        c, d = Var(), Var()
        constrain_var_dims(c, {"m": 1}, t2)
        constrain_var_dims(d, {"s": 1}, t2)
        assert unify(c, d, t2) is False
        # transfer: constrained newer var aliased to unconstrained older var
        t3 = Trail()
        old = Var()
        new = Var()
        constrain_var_dims(new, {"m": 1}, t3)
        assert unify(new, old, t3) is True
        assert get_attr(old, "units") == UnitState({"m": 1})

    def test_control_units_backtracking(self):
        t = Trail()
        d = Var()
        m = t.mark()
        constrain_var_dims(d, {"m": 1}, t)
        t.undo(m)
        assert get_attr(d, "units") is None
        assert unify(d, 5, t) is True


# ══════════════════════════════════════════════════════════════════════════
# A05-F006 (doc-drift; consequence of A01-F001) — docs/constraints.md
# promises dif(X, f(X)) is immediately satisfied via the occurs check, but
# unify_with_occurs_check is blind to Compound, so a pending constraint is
# attached instead.  The list form works (occurs check handles lists).
# ══════════════════════════════════════════════════════════════════════════


class TestF006DifOccursCheckCompound:

    def test_dif_x_fx_immediately_satisfied(self):
        t = Trail()
        x = Var()
        assert dif(x, ("f", x), t) is True
        assert get_attr(x, DIF_KEY) is None   # docs: no pending constraint

    def test_control_dif_x_listx_immediately_satisfied(self):
        t = Trail()
        x = Var()
        assert dif(x, [x], t) is True
        assert get_attr(x, DIF_KEY) is None


# ══════════════════════════════════════════════════════════════════════════
# dif/2 core semantics — regression guards (all probed clean)
# ══════════════════════════════════════════════════════════════════════════


class TestDifCoreRegression:

    def test_ground(self):
        assert dif(1, 2, Trail()) is True
        assert dif(1, 1, Trail()) is False
        assert dif("a", "b", Trail()) is True
        assert dif("a", "a", Trail()) is False

    def test_same_var_fails(self):
        x = Var()
        assert dif(x, x, Trail()) is False

    def test_var_pair_bind_equal_blocked(self):
        t = Trail()
        x, y = Var(), Var()
        assert dif(x, y, t) is True
        assert unify(x, 1, t) is True
        assert unify(y, 1, t) is False
        assert unify(y, 2, t) is True

    def test_structural_incompatibility_immediate(self):
        t = Trail()
        x = Var()
        assert dif(("f", x), ("g", x), t) is True
        assert get_attr(x, DIF_KEY) is None
        assert dif((1, x), (1, 2, 3), t) is True   # arity mismatch
        assert get_attr(x, DIF_KEY) is None

    def test_multi_pair_rollback_integrity(self):
        # A violated pair mid-hook must roll back re-attachments of earlier
        # pairs, and the surviving constraints must stay enforceable.
        t = Trail()
        x, y = Var(), Var()
        assert dif(x, y, t) is True
        assert dif(x, 2, t) is True
        assert unify(x, 2, t) is False   # violates dif(x,2); rollback
        assert unify(x, 3, t) is True
        assert unify(y, 3, t) is False   # dif(x,y) still enforced
        assert unify(y, 4, t) is True

    def test_transitive_via_aliasing(self):
        t = Trail()
        x, y, z = Var(), Var(), Var()
        assert dif(x, y, t) is True
        assert unify(x, z, t) is True
        assert unify(y, z, t) is False   # x and y would become identical

    def test_backtracking_restores_constraint_state(self):
        t = Trail()
        x, y = Var(), Var()
        m = t.mark()
        assert dif(x, y, t) is True
        assert unify(x, 1, t) is True
        t.undo(m)
        assert get_attr(x, DIF_KEY) is None
        assert get_attr(y, DIF_KEY) is None
        # after undo the pair is gone — equal binding allowed again
        assert unify(x, 7, t) is True
        assert unify(y, 7, t) is True

    def test_partial_binding_reattaches(self):
        t = Trail()
        x, y = Var(), Var()
        assert dif((x, y), (1, 2), t) is True
        assert unify(x, 1, t) is True        # still pending on y
        assert unify(y, 2, t) is False       # would complete equality
        assert unify(y, 3, t) is True

    def test_bound_args_input_mode(self):
        t = Trail()
        x = Var()
        unify(x, 1, t)
        assert dif(x, 1, t) is False
        assert dif(x, 2, t) is True

    def test_deep_nesting_clean_recursion_error(self):
        # MAX_DEPTH (50k) guard raises a clean RecursionError, no crash.
        x, y = Var(), Var()
        t1, t2 = x, y
        for _ in range(51000):
            t1, t2 = [t1], [t2]
        with pytest.raises(RecursionError):
            dif(t1, t2, Trail())

    def test_deep_nesting_below_limit_ok(self):
        x, y = Var(), Var()
        t1, t2 = x, y
        for _ in range(30000):
            t1, t2 = [t1], [t2]
        assert dif(t1, t2, Trail()) is True

    def test_dif_fd_seam(self):
        # dif composes with CLP(FD): singleton domain that violates dif fails.
        from clausal.logic.clpfd import in_domain, label
        t = Trail()
        x = Var()
        assert dif(x, 1, t) is True
        assert in_domain(x, 1, 1, t) is False   # {1} conflicts with dif
        t2 = Trail()
        y = Var()
        assert dif(y, 1, t2) is True
        assert in_domain(y, 1, 2, t2) is True
        assert [deref(y) for _ in label([y], t2)] == [2]


# ══════════════════════════════════════════════════════════════════════════
# reify_eq / eq/3 / dif_t/3 — regression guards (probed clean under the
# suspended-generator engine contract)
# ══════════════════════════════════════════════════════════════════════════


class TestReifyEqRegression:

    def test_three_values(self):
        t = Trail()
        assert reify_eq(1, 1, t) is True
        assert reify_eq(1, 2, t) is False
        x = Var()
        assert reify_eq(x, 1, t) is None
        assert reify_eq(x, x, t) is True
        y = Var()
        assert reify_eq(x, y, t) is None

    def test_no_bindings_leak(self):
        t = Trail()
        x = Var()
        assert reify_eq(x, [1, 2], t) is None
        assert len(t) == 0
        assert is_var(deref(x))

    def test_entailment_via_prior_dif(self):
        # reify_eq consults constraints: with dif(x,1) posted, x=1 is
        # impossible → False (deterministic), not None.
        t = Trail()
        x = Var()
        assert dif(x, 1, t) is True
        assert reify_eq(x, 1, t) is False


class TestReifBuiltinsRegression:

    def test_eq_deterministic(self):
        t = Trail()
        tv = Var()
        assert [deref(tv) for _ in eq__3(1, 1, tv, t, [])] == [True]
        t = Trail()
        tv = Var()
        assert [deref(tv) for _ in eq__3(1, 2, tv, t, [])] == [False]

    def test_dif_t_deterministic(self):
        t = Trail()
        tv = Var()
        assert [deref(tv) for _ in dif_t__3(1, 1, tv, t, [])] == [False]
        t = Trail()
        tv = Var()
        assert [deref(tv) for _ in dif_t__3(1, 2, tv, t, [])] == [True]

    def test_eq_undetermined_enumerates_both(self):
        t = Trail()
        x, tv = Var(), Var()
        g = eq__3(x, 1, tv, t, [])
        next(g)
        assert deref(x) == 1 and deref(tv) is True
        next(g)
        assert is_var(deref(x)) and deref(tv) is False
        # committed branch 2: dif is live while the generator is suspended
        assert unify(x, 1, t) is False
        assert unify(x, 7, t) is True

    def test_eq_truth_input_modes(self):
        # T=True acts as unify
        t = Trail()
        x = Var()
        assert [deref(x) for _ in eq__3(x, 1, True, t, [])] == [1]
        # T=False acts as dif (checked while suspended)
        t = Trail()
        x = Var()
        g = eq__3(x, 1, False, t, [])
        next(g)
        assert unify(x, 1, t) is False
        assert unify(x, 2, t) is True
        # T bound to a non-truth value: no solutions
        t = Trail()
        assert list(eq__3(1, 1, "zzz", t, [])) == []

    def test_dif_t_undetermined_branch_order(self):
        # dif_t explores T=True (dif) first, then T=False (unify)
        t = Trail()
        x, tv = Var(), Var()
        out = [deref(tv) for _ in dif_t__3(x, 1, tv, t, [])]
        assert out == [True, False]

    def test_exhaustion_restores_trail(self):
        t = Trail()
        x, tv = Var(), Var()
        list(eq__3(x, 1, tv, t, []))
        assert len(t) == 0
        assert is_var(deref(x)) and is_var(deref(tv))

    def test_eq_var_var_aliases_then_difs(self):
        t = Trail()
        x, y, tv = Var(), Var(), Var()
        g = eq__3(x, y, tv, t, [])
        next(g)
        assert deref(tv) is True
        assert deref(x) is deref(y)        # aliased
        next(g)
        assert deref(tv) is False
        assert unify(x, 1, t) and unify(y, 1, t) is False


# ══════════════════════════════════════════════════════════════════════════
# Language-level integration: `is not` sugar, immediate `not (X is Y)`,
# reified builtins from Clausal source
# ══════════════════════════════════════════════════════════════════════════


LANG_SRC = """
-double_quotes(atom)
color("red"),
color("green"),

pair_diff(X, Y) <- (
    X is not Y,
    color(X),
    color(Y)
)

pick(1),
pick(2),
pick(3),

survive(X) <- (
    X is not 2,
    pick(X)
)

imm(X, Y) <- (
    not (X is Y),
)

reif_eq_test(X, Y, T) <- eq(X, Y, T)
reif_dif_test(X, Y, T) <- dif_t(X, Y, T)
"""


class TestLanguageIntegration:

    def test_is_not_sugar_enumerates_distinct_pairs(self, load):
        m = load("lang", LANG_SRC)
        x, y = Var(), Var()
        got = answers(solve(("pair_diff", x, y), m), x, y)
        assert got == [(mint("red"), mint("green")), (mint("green"), mint("red"))]

    def test_is_not_survives_clause_backtracking(self, load):
        m = load("lang", LANG_SRC)
        x = Var()
        assert answers(solve(("survive", x), m), x) == [(1,), (3,)]

    def test_immediate_not_unify_point_in_time(self, load):
        m = load("lang", LANG_SRC)
        # two unbound vars unify → not(is) fails immediately
        assert once(("imm", Var(), Var()), module=m) is None
        assert once(("imm", 1, 2), module=m) is not None

    def test_reified_builtins_from_source(self, load):
        m = load("lang", LANG_SRC)
        tv = Var()
        assert answers(solve(("reif_eq_test", 1, 1, tv), m), tv) == [(True,)]
        tv = Var()
        assert answers(solve(("reif_eq_test", 1, 2, tv), m), tv) == [(False,)]
        x, tv = Var(), Var()
        assert len(answers(solve(("reif_dif_test", x, 1, tv), m), x, tv)) == 2


# ══════════════════════════════════════════════════════════════════════════
# Attribute builtins — regression guards
# ══════════════════════════════════════════════════════════════════════════


class TestAttributeBuiltinsRegression:

    def test_put_get_del_roundtrip(self):
        t = Trail()
        v = Var()
        assert list(_put_attr__3(v, mint("color"), "red", t, [])) == [None]
        out = Var()
        assert list(_get_attr__3(v, mint("color"), out, t, [])) == [None]
        assert deref(out) == "red"
        assert list(_del_attr__2(v, mint("color"), t, [])) == [None]
        out2 = Var()
        assert list(_get_attr__3(v, mint("color"), out2, t, [])) == []

    def test_put_attr_rejects_bad_modes(self):
        t = Trail()
        assert list(_put_attr__3(1, mint("k"), 2, t, [])) == []    # non-var
        assert list(_put_attr__3(Var(), Var(), 2, t, [])) == []    # unbound key
        assert list(_put_attr__3(Var(), 5, 2, t, [])) == []        # non-atom key

    def test_get_attr_fails_on_bound_or_missing(self):
        t = Trail()
        v = Var()
        unify(v, 3, t)
        assert list(_get_attr__3(v, mint("k"), Var(), t, [])) == []
        assert list(_get_attr__3(Var(), mint("k"), Var(), t, [])) == []

    def test_attvar_check(self):
        t = Trail()
        v = Var()
        assert list(_is_att_var__1(v, t, [])) == []
        put_attr(v, "k", 1, t)
        assert list(_is_att_var__1(v, t, [])) == [None]
        # deleting the only attr → attvar/1 fails again
        list(_del_attr__2(v, mint("k"), t, []))
        assert list(_is_att_var__1(v, t, [])) == []

    def test_get_attrs_put_attrs_roundtrip(self):
        t = Trail()
        v = Var()
        assert list(_put_attrs__2(v, DictTerm({mint("a"): 1, mint("b"): 2}), t, [])) == [None]
        out = Var()
        list(_get_attrs__2(v, out, t, []))
        assert deref(out).data == {mint("a"): 1, mint("b"): 2}

    def test_put_attrs_non_atom_key_fails(self):
        # THE FLIP (spec §6.4): a Key is an ATOM; an int is neither an atom
        # nor a string, so it still FAILS rather than raising.
        t = Trail()
        v = Var()
        assert list(_put_attrs__2(v, DictTerm({mint("a"): 1, 2: "bad"}), t, [])) == []
        # earlier puts are trailed, so an enclosing choice point undoes them

    def test_attr_backtracking(self):
        t = Trail()
        v = Var()
        m = t.mark()
        put_attr(v, "k", 1, t)
        put_attr(v, "k", 2, t)
        assert get_attr(v, "k") == 2
        t.undo(m)
        assert get_attr(v, "k") is None


# ══════════════════════════════════════════════════════════════════════════
# C toolkit — memory stability over post / propagate / violate / backtrack
# ══════════════════════════════════════════════════════════════════════════


class TestMemoryStability:

    def test_dif_post_propagate_backtrack_stable(self, refcount_stable):
        def thunk():
            t = Trail()
            x, y = Var(), Var()
            m = t.mark()
            dif(x, y, t)
            dif(x, 1, t)
            unify(x, 2, t)     # re-attach + satisfy
            t.undo(m)
        refcount_stable(thunk, iterations=2000)

    def test_dif_violation_path_stable(self, refcount_stable):
        def thunk():
            t = Trail()
            x, y = Var(), Var()
            m = t.mark()
            dif(x, y, t)
            unify(x, 1, t)
            unify(y, 1, t)     # hook rejects
            t.undo(m)
        refcount_stable(thunk, iterations=2000)

    def test_shared_value_refcount_stable(self, getrefcount_stable):
        val = ("shared", 1)

        def use():
            t = Trail()
            x = Var()
            m = t.mark()
            dif(x, val, t)
            unify(x, val, t)   # violates
            t.undo(m)
        getrefcount_stable(val, use, iterations=2000)

    def test_reify_eq_stable(self, refcount_stable):
        def thunk():
            t = Trail()
            x = Var()
            reify_eq(x, [1, 2, x], t)
            reify_eq(1, 1, t)
        refcount_stable(thunk, iterations=2000)


# ══════════════════════════════════════════════════════════════════════════
# Python ↔ C parity (differential oracle): the pure-Python implementation
# must agree with the C one.  Runs the same canonical probe in a
# subprocess with the C module import-blocked and compares transcripts.
# ══════════════════════════════════════════════════════════════════════════


PARITY_SNIPPET = """
import sys
if sys.argv[1] == "py":
    sys.modules['clausal.logic._constraints_dif'] = None  # force Python impl
import clausal.logic.constraints as C
from clausal.logic.variables import Var, Trail, unify, get_attr

t = Trail(); print(C.dif(1, 2, t))
t = Trail(); print(C.dif(1, 1, t))
t = Trail(); x = Var(); print(C.dif(x, x, t))
t = Trail(); x, y = Var(), Var()
print(C.dif(x, y, t), unify(x, 1, t), unify(y, 1, t), unify(y, 2, t))
t = Trail(); x = Var()
print(C.dif(("f", x, 2), ("f", 1, 2), t), unify(x, 1, t))
t = Trail(); x, y = Var(), Var()
C.dif(x, y, t); C.dif(x, 2, t)
print(unify(x, 2, t), unify(x, 3, t), unify(y, 3, t))
t = Trail(); x, y, z = Var(), Var(), Var()
C.dif(x, y, t); print(unify(x, z, t), unify(y, z, t))
t = Trail(); print(C.reify_eq(1, 1, t), C.reify_eq(1, 2, t), C.reify_eq(Var(), 1, t))
x = Var(); print(len(C._collect_free_vars([x, (x, [Var()])])))
"""


class TestPythonCParity:

    def test_transcripts_match(self, tmp_path):
        p = tmp_path / "parity.py"
        p.write_text(textwrap.dedent(PARITY_SNIPPET))
        env = dict(os.environ, PYTHONPATH=REPO)
        outs = {}
        for impl in ("c", "py"):
            r = subprocess.run([PYTHON, str(p), impl], capture_output=True,
                               text=True, timeout=120, env=env)
            assert r.returncode == 0, r.stderr[-500:]
            outs[impl] = r.stdout
        assert outs["c"] == outs["py"]
