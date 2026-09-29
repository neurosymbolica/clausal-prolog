"""A09 builtins & stdlib predicates — adversarial audit tests (2026-07-05).

Findings ledger: docs/superpowers/audits/2026-07-05-fable-partition/09-builtins/findings.md

Suspected-bug tests assert the *correct* behaviour and are marked
``@pytest.mark.xfail(strict=False)`` with the finding ID; confirmed-correct
behaviour is a plain regression guard.  Run PER FILE only:

    python -m pytest tests/audit_2026_07_05/test_09_builtins.py -v

Crash-prone C probes (A09-F020/F021) run in subprocesses with core dumps
disabled.
"""
import os
import subprocess
import sys
import tempfile
import textwrap

import pytest

from clausal.logic.atoms import char_atom, mint, spelling
from clausal.logic.cells import chars
from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic import solve as solve_mod
from clausal.logic.variables import Var, deref, is_var
from clausal import cell_args, cell_functor
from clausal.logic.exceptions import LogicException
from clausal.terms import SegString, SetTerm

PYTHON = sys.executable
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_snippet(code: str) -> subprocess.CompletedProcess:
    """Run a Python snippet in a subprocess with the repo on PYTHONPATH.

    Used for probes that may segfault (A09-F020/F021) — core dumps disabled
    and cwd outside the repo so no ``core`` file lands in the tree.
    """
    env = dict(os.environ, PYTHONPATH=REPO)
    return subprocess.run(
        [PYTHON, "-c", textwrap.dedent(code)],
        capture_output=True, text=True, timeout=120, env=env,
        cwd=tempfile.gettempdir(),
    )


FIXTURE_SRC = """\
-double_quotes(atom)
-module(a09fix, [])
-private([pair(A, B)])
-dynamic(seen2/1)

pick(1, "a"),
pick(1, "b"),
one_(1),
q3(7),
seen2("dummy"),
gkey(X, X),
amb(1, 10),
amb(1, 20),
pos_(1),
pos_(2),
sbkey("a", 1),
sbkey("b", "x"),

sortvar(S) <- (X is 5, sort([X, 5, 1], S))
msortvar(S) <- (X is 5, msort([X, 1, 2], S))
mlprobe(Y) <- (maplist(pick, [1], [Y]), Y is "b")
mlfirst(Y) <- maplist(pick, [1], [Y])
fold_goal(X, A, O) <- (amb(X, V), O == A + V)
foldprobe(R) <- (foldl(fold_goal, [1], 0, R), R == 20)
incprobe(X, R) <- include(one_, [X, 2], R)
twprobe(X, P) <- take_while(pos_, [X, 2, -1], P)
fmg(X, P) <- (Y is 1, P is pair(X, Y))
fmprobe(R) <- filter_map(fmg, [5], R)
tpos(X, T) <- (X > 0, T is True)
tpos(X, T) <- (X <= 0, T is False)
tfprobe(R) <- tfilter(tpos, [1, -2, 3], R)
retprobe(X) <- (assertz(seen2(5)), retract(seen2(X)))
azrule(OK) <- (assertz(seen2(Z) <- q3(Z)), OK is 1)
cpprobe(OK) <- (dif(X, 1), copy_term(X, Y), Y is 1, OK is 1)
drprobe(P, R) <- (length(A, 1), P is pair(A, 0), append(A, [3], R))
gbprobe(G) <- group_by(gkey, [1, True, 2], G)
sbprobe(S) <- sort_by(sbkey, ["a", "b"], S)
mbprobe(E) <- max_by(sbkey, ["a", "b"], E)
"""

LOCKED_SRC = """\
-module(a09locked, [])

locked_(1),
lockassert(OK) <- (assertz(locked_(2)), OK is 1)
lockretract(OK) <- (retract(locked_(1)), OK is 1)
"""


@pytest.fixture(scope="module")
def fix():
    """Load the main fixture module ONCE (never reload — atoms/functors are
    module-scoped; see audit probe-pitfalls memory #1)."""
    with tempfile.NamedTemporaryFile(suffix=".clausal", mode="w",
                                     delete=False) as f:
        f.write(FIXTURE_SRC)
        path = f.name
    pymod = _load_module("a09fix", path)
    yield pymod, pymod.__dict__["$module"]
    os.unlink(path)


@pytest.fixture(scope="module")
def locked_mod():
    with tempfile.NamedTemporaryFile(suffix=".clausal", mode="w",
                                     delete=False) as f:
        f.write(LOCKED_SRC)
        path = f.name
    pymod = _load_module("a09locked", path)
    yield pymod, pymod.__dict__["$module"]
    os.unlink(path)


def _first(m, functor, *args):
    solve_mod._query_cache.clear()
    for _ in call(functor, *args, module=m):
        return True
    return False


def _collect(m, var, functor, *args):
    solve_mod._query_cache.clear()
    out = []
    for _ in call(functor, *args, module=m):
        out.append(deref(var))
    return out


def _dw(t):
    """Deep-deref a term for comparison."""
    t = deref(t)
    if isinstance(t, list):
        return [_dw(e) for e in t]
    return t


# ═══════════════════════════════════════════════════════════════════════════
# A09-F001 — sort/2 & msort/2 do not deref elements
# ═══════════════════════════════════════════════════════════════════════════

def test_F001_msort_bound_var_element(fix):
    _, m = fix
    S = Var()
    assert _first(m, "msortvar", S)
    assert _dw(S) == [1, 2, 5]  # A09-F001 fixed: was [5, 1, 2]


def test_F001_sort_bound_var_element(fix):
    _, m = fix
    S = Var()
    assert _first(m, "sortvar", S)
    assert _dw(S) == [1, 5]  # A09-F001 fixed: was [5, 1, 5] — unsorted AND dup kept


def test_F001_regression_sum_max_do_deref(fix):
    """sum_list/max_list/min_list DO deref elements — guard the good half."""
    _, m = fix
    T = Var()
    assert _first(m, "sum_list", [2, 3], T) and deref(T) == 5


# ═══════════════════════════════════════════════════════════════════════════
# A09-F002 — filter_map/3 loses inner bindings of compound outputs
# ═══════════════════════════════════════════════════════════════════════════

def test_F002_filter_map_inner_bindings(fix):
    pymod, m = fix
    R = Var()
    assert _first(m, "fmprobe", R)
    out = _dw(R)
    assert len(out) == 1
    # R6 (P3-2 Task 2): ``pair`` is a data functor, so the answer is the cell
    # ``("pair", 5, B)`` -- B is slot 2, not an attribute.
    inner = deref(out[0][2])  # pair(A=5, B=?) — B must be 1, not unbound
    assert not is_var(inner) and inner == 1


# ═══════════════════════════════════════════════════════════════════════════
# A09-F003 — include/take_while/… lose bindings of Var elements
# ═══════════════════════════════════════════════════════════════════════════

def test_F003_include_var_element_binding(fix):
    _, m = fix
    X, R = Var(), Var()
    assert _first(m, "incprobe", X, R)
    assert not is_var(deref(X)) and deref(X) == 1  # SWI binds X=1


def test_F003_take_while_var_element_binding(fix):
    _, m = fix
    X, P = Var(), Var()
    assert _first(m, "twprobe", X, P)
    assert not is_var(deref(X))


# ═══════════════════════════════════════════════════════════════════════════
# A09-F004 — maplist/foldl committed choice loses solutions
# ═══════════════════════════════════════════════════════════════════════════

def test_F004_maplist_committed_choice(fix):
    # A09-F004 closed for maplist (ruling R6, 2026-09-28): maplist/3
    # backtracks into each call, as the prologue's call/N does.
    _, m = fix
    Y = Var()
    assert _collect(m, Y, "mlprobe", Y) == ["b"]


@pytest.mark.xfail(strict=False, reason="A09-F004: foldl/4 same commitment")
def test_F004_foldl_committed_choice(fix):
    _, m = fix
    assert _first(m, "foldprobe", Var())


def test_F004_regression_maplist_first_solution(fix):
    """The first solution comes first, and the call is backtracked into for
    the second (it used to commit to the first)."""
    _, m = fix
    Y = Var()
    assert _collect(m, Y, "mlfirst", Y) == [mint("a"), mint("b")]


# ═══════════════════════════════════════════════════════════════════════════
# A09-F005 — assertz of a rule poisons the predicate
# ═══════════════════════════════════════════════════════════════════════════

def test_F005_assertz_rule(fix):
    """A09-F005 (decision b): assertz of a rule is rejected with a typed
    LogicException at assert time, and the target predicate is NOT poisoned —
    its pre-existing facts stay queryable."""
    _, m = fix
    # azrule(OK) <- (assertz(seen2(Z) <- q3(Z)), OK is 1) — the assertz of a
    # rule must raise, propagating out of azrule.
    with pytest.raises(LogicException) as ei:
        _first(m, "azrule", Var())
    inner = cell_args(ei.value.term)[0]
    assert type(inner) is tuple and cell_functor(inner) == "permission_error"
    # A09-F005 nit: error/2's second argument names the actual caller — there
    # is no assert/1 builtin, only assertz/1 and asserta/1.
    assert cell_args(ei.value.term)[1] == ("/", "assertz", 1)
    assert ei.value.message is None
    V = Var()
    got = set()
    try:
        got = set(_collect(m, V, "seen2", V))
    except NotImplementedError:
        pytest.fail("predicate poisoned: NotImplementedError on later query")
    # The base fact survives; the rejected rule never derived 7.
    assert mint("dummy") in got and 7 not in got


# ═══════════════════════════════════════════════════════════════════════════
# A09-F006 — assertz/retract on locked predicate silently fail
# (RuntimeError raised, then swallowed by the trampoline drive loop)
# ═══════════════════════════════════════════════════════════════════════════

def _assert_static_procedure_error(ei, indicator):
    """The term is error(permission_error(modify, static_procedure, F/A), PI).

    REWORDED for P3-3 Task 3: the refusal comes from the ONE mutation gate
    now; error/2's second argument is the calling builtin's indicator — which
    is what a reader uses it for — and the exception's message says who was
    refused, which row, and why.  The ISO formal itself is unchanged.
    """
    inner = cell_args(ei.value.term)[0]
    assert type(inner) is tuple and cell_functor(inner) == "permission_error"
    assert cell_args(inner)[0] == mint("modify")
    assert cell_args(inner)[1] == mint("static_procedure")
    assert cell_args(ei.value.term)[1] == indicator


def test_F006_assertz_locked_raises(locked_mod):
    # Tightened post-A04-F009: pytest.raises(Exception) would also pass on
    # the pre-fix raw RuntimeError (the narrowed trampoline no longer
    # swallows it), so assert the typed LogicException specifically.
    _, m = locked_mod
    with pytest.raises(LogicException) as ei:
        _first(m, "lockassert", Var())
    _assert_static_procedure_error(ei, ("/", "assertz", 1))


def test_F006_retract_locked_raises(locked_mod):
    _, m = locked_mod
    with pytest.raises(LogicException) as ei:
        _first(m, "lockretract", Var())
    _assert_static_procedure_error(ei, ("/", "retract", 1))


# ═══════════════════════════════════════════════════════════════════════════
# A09-F007 — RecursionError from builtin helpers swallowed as failure
# ═══════════════════════════════════════════════════════════════════════════

def test_F007_flatten_cyclic_not_silent(fix):
    # A09-F007 fixed incidentally by A04-F009 (commit 8027e88d): the drive
    # loop no longer treats RecursionError (a RuntimeError subclass) as
    # generator exhaustion, so cyclic input raises instead of a silent 'no'.
    _, m = fix
    l = [1]
    l.append(l)
    with pytest.raises(Exception):  # resource/type error expected, not 'no'
        _first(m, "flatten", l, Var())


def test_F007_regression_direct_generator_raises():
    """The builtin itself DOES raise — the swallowing happens in the engine."""
    from clausal.logic.builtins.lists import _flatten__2
    from clausal.logic.variables import Trail
    l = [1]
    l.append(l)
    gen = _flatten__2(None, "P", "F", None, l, Var(), Trail())
    with pytest.raises(RecursionError):
        next(gen)


# ═══════════════════════════════════════════════════════════════════════════
# A09-F008 — retract/1 undoes the head-unification bindings
# ═══════════════════════════════════════════════════════════════════════════

def test_F008_retract_binds_pattern(fix):
    # A09-F008 (decision A09-D003 a): retract/1 binds the pattern to the
    # retracted clause's args. retract(seen2(X)) removes the FIRST matching
    # clause — seen2("dummy"), loaded before the asserted seen2(5) — so X is
    # bound to "dummy" (ISO first-match), not left unbound.
    _, m = fix
    X = Var()
    assert _first(m, "retprobe", X)
    assert not is_var(deref(X)) and deref(X) == mint("dummy")


# ═══════════════════════════════════════════════════════════════════════════
# A09-F009 — sequence//1 compares terminals with == instead of unify
# ═══════════════════════════════════════════════════════════════════════════

def test_F009_sequence_var_terminal(fix):
    # THE FLIP (spec §6.2): the elements of the string "a" are its CHAR
    # ATOMS, so a Var terminal binds ("a",), not the 1-char str it used to.
    _, m = fix
    X, S = Var(), Var()
    assert _first(m, "sequence", [X], chars("a"), S)
    assert deref(X) == char_atom("a") and deref(S) == chars("")


def test_F009_regression_sequence_ground_modes(fix):
    # THE FLIP: a terminal LIST holds char atoms; ["a"] is a list of one
    # one-character STRING, which is a different term.
    _, m = fix
    S = Var()
    assert _first(m, "sequence", [char_atom("a")], chars("ab"), S) and deref(S) == chars("b")
    S0 = Var()
    assert _first(m, "sequence", chars("a"), S0, chars("b")) and deref(S0) == chars("ab")


# ═══════════════════════════════════════════════════════════════════════════
# A09-F010 — copy_term/2 drops attribute constraints
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.xfail(strict=False, reason="A09-F010: dif constraint not "
                   "copied — the copy can be bound to the excluded value")
def test_F010_copy_term_copies_dif(fix):
    _, m = fix
    # cpprobe succeeds iff the COPY of a dif(X,1)-constrained var unifies
    # with 1 — i.e. iff the constraint was dropped.
    assert not _first(m, "cpprobe", Var())


# ═══════════════════════════════════════════════════════════════════════════
# A09-F011 — plus/max_/min_ lack numeric type checks
# ═══════════════════════════════════════════════════════════════════════════

def test_F011_plus_string_concat(fix):
    _, m = fix
    assert not _first(m, "plus", "a", "b", Var())


def test_F011_plus_mixed_raw_typeerror(fix):
    _, m = fix
    try:
        _first(m, "plus", 1, "a", Var())
    except TypeError:
        pytest.fail("raw TypeError escaped from plus/3")


def test_F011_max_strings(fix):
    _, m = fix
    assert not _first(m, "max_", "a", "b", Var())


# ═══════════════════════════════════════════════════════════════════════════
# A09-F012 — raw Python exceptions escape from builtins
# ═══════════════════════════════════════════════════════════════════════════

def test_F012_pairs_values_short_pair(fix):
    # A09-F018/F012: a too-short pair fails (no raw IndexError escapes).
    # R4: a pair is K-V now; [1] and the arity-1 cell are both non-pairs.
    _, m = fix
    try:
        assert not _first(m, "pairs_values", [[1]], Var())
        assert not _first(m, "pairs_values", [("-", 1)], Var())
    except IndexError:
        pytest.fail("raw IndexError escaped from pairs_values/2")


def test_F012_dict_pairs_unhashable_key(fix):
    # A09-F012 (D002 a): an unhashable key raises a typed LogicException,
    # catchable by catch/3 — not a raw TypeError that kills the query.
    _, m = fix
    with pytest.raises(LogicException):
        _first(m, "dict_pairs", Var(), [("-", [1], 2)])


def test_F012_set_list_unhashable(fix):
    _, m = fix
    with pytest.raises(LogicException):
        _first(m, "set_list", Var(), [[1]])


def test_F012_set_add_unhashable(fix):
    # A09-F012 (D002 a): an unhashable Elem raises a typed LogicException
    # (catchable by catch/3), not a raw TypeError that escapes the engine.
    _, m = fix
    with pytest.raises(LogicException) as ei:
        _first(m, "set_add", [9], SetTerm([1, 2]), Var())
    inner = cell_args(ei.value.term)[0]
    assert type(inner) is tuple and cell_functor(inner) == "type_error"
    assert cell_args(inner)[0] == mint("hashable")


def test_F012_set_remove_unhashable(fix):
    _, m = fix
    with pytest.raises(LogicException) as ei:
        _first(m, "set_remove", [9], SetTerm([1, 2]), Var())
    inner = cell_args(ei.value.term)[0]
    assert type(inner) is tuple and cell_functor(inner) == "type_error"
    assert cell_args(inner)[0] == mint("hashable")


def test_F012_regression_set_add_remove_hashable(fix):
    """Hashable elements keep working after the F012 guard."""
    _, m = fix
    Z = Var()
    assert _first(m, "set_add", 9, SetTerm([1, 2]), Z)
    assert deref(Z) == SetTerm([1, 2, 9])
    Z2 = Var()
    assert _first(m, "set_remove", 1, SetTerm([1, 2]), Z2)
    assert deref(Z2) == SetTerm([2])


def test_F012_exp_mod_raw_valueerror(fix):
    # A09-F012: a non-invertible modular inverse raises a typed
    # evaluation_error, not a raw ValueError.
    _, m = fix
    with pytest.raises(LogicException):
        _first(m, "exp_mod", 2, -1, 4, Var())


def test_F012_max_by_incomparable_keys(fix):
    # A09-F012: max_by now uses sort_by's (type-name, repr) fallback for
    # incomparable keys instead of leaking a raw TypeError, so it succeeds.
    _, m = fix
    try:
        assert _first(m, "mbprobe", Var())
    except TypeError:
        pytest.fail("raw TypeError escaped from max_by/3")


def test_F012_regression_sort_by_incomparable_keys(fix):
    """sort_by catches the TypeError (fallback key) — inconsistent with
    max_by but at least does not crash."""
    _, m = fix
    S = Var()
    assert _first(m, "sbprobe", S)


# ═══════════════════════════════════════════════════════════════════════════
# A09-F013 — char_type test-mode vs enumeration-mode Unicode inconsistency
# ═══════════════════════════════════════════════════════════════════════════

def test_F013_char_type_digit_consistency(fix):
    _, m = fix
    assert _first(m, "char_type", char_atom("٣"), mint("digit"))
    C = Var()
    chars = _collect(m, C, "char_type", C, mint("digit"))
    assert char_atom("٣") in chars


def test_F013_char_type_space_consistency(fix):
    _, m = fix
    assert _first(m, "char_type", char_atom("\xa0"), mint("space"))
    C = Var()
    assert char_atom("\xa0") in _collect(
        m, C, "char_type", C, mint("space"))


def test_F013_char_type_punct_consistency(fix):
    _, m = fix
    assert _first(m, "char_type", char_atom("\xa1"), mint("punct"))
    C = Var()
    assert char_atom("\xa1") in _collect(
        m, C, "char_type", C, mint("punct"))


def test_F013_regression_alpha_enum_unicode(fix):
    """F072 half that WAS fixed: alpha enumeration includes non-ASCII."""
    _, m = fix
    C = Var()
    chars = _collect(m, C, "char_type", C, mint("alpha"))
    assert char_atom("α") in chars  # α


# ═══════════════════════════════════════════════════════════════════════════
# A09-F014 — char_type char-bound Python fallback is ASCII-table-only
# ═══════════════════════════════════════════════════════════════════════════

def test_F014_char_type_python_fallback_non_ascii(fix):
    import clausal.logic.builtins.chars as ch
    _, m = fix
    saved = ch._c_char_type_find_types
    ch._c_char_type_find_types = None
    try:
        T = Var()
        types = _collect(m, T, "char_type", char_atom("α"), T)
    finally:
        ch._c_char_type_find_types = saved
    assert mint("alpha") in types


def test_F014_regression_char_type_c_path_non_ascii(fix):
    _, m = fix
    T = Var()
    types = _collect(m, T, "char_type", char_atom("α"), T)
    assert mint("alpha") in types and mint("lower") in types


# ═══════════════════════════════════════════════════════════════════════════
# A09-F015 — bool-as-int acceptance is inconsistent; between C/Py diverge
# ═══════════════════════════════════════════════════════════════════════════

def test_F015_length_bool(fix):
    # A bool is no integer: ISO/Scryer type_error(integer, N), not the silent
    # failure this used to pin (2026-09-28).
    _, m = fix
    for n in (True, False):
        with pytest.raises(LogicException) as ei:
            _first(m, "length", Var(), n)
        assert ei.value.term[1] == ("type_error", "integer", n)


def test_F015_list_item_bool_index(fix):
    _, m = fix
    assert not _first(m, "list_item", True, ["a", "b"], Var())


def test_F015_between_bool_c_py_divergence(fix):
    import clausal.logic.builtins.arithmetic as ar
    _, m = fix
    X = Var()
    with_c = _collect(m, X, "between", False, True, X)
    ar._USE_C_ARITH = False
    try:
        X2 = Var()
        without_c = _collect(m, X2, "between", False, True, X2)
    finally:
        ar._USE_C_ARITH = True
    assert with_c == without_c


def test_F015_regression_succ_rejects_bool(fix):
    _, m = fix
    assert not _first(m, "succ", True, Var())


# ═══════════════════════════════════════════════════════════════════════════
# A09-F016 — must_be/can_be "list" contradicts strings-as-lists
# ═══════════════════════════════════════════════════════════════════════════

def test_F016_must_be_list_string(fix):
    _, m = fix
    assert _first(m, "is_list", chars("abc"))  # locked-in F080 behaviour (stage 2: the string is the carrier)
    assert _first(m, "must_be", mint("list"), chars("abc"))  # raises today


# ═══════════════════════════════════════════════════════════════════════════
# A09-F017 — atom_chars/atom_codes/number_chars/number_codes reject the
# str/bytes forms of their char/code lists
# ═══════════════════════════════════════════════════════════════════════════

def test_F017_atom_chars_str_arg(fix):
    _, m = fix
    A = Var()
    assert _first(m, "atom_chars", A, chars("abc"))
    assert deref(A) == mint("abc")


def test_F017_atom_codes_bytes_arg(fix):
    _, m = fix
    A = Var()
    assert _first(m, "atom_codes", A, b"ab")
    assert deref(A) == mint("ab")


def test_F017_regression_list_forms_work(fix):
    _, m = fix
    A = Var()
    assert (_first(m, "atom_chars", A, [char_atom("a"), char_atom("b")])
            and deref(A) == mint("ab"))
    B = Var()
    assert _first(m, "atom_codes", B, [97, 98]) and deref(B) == mint("ab")


# ═══════════════════════════════════════════════════════════════════════════
# A09-F018 — pairs_* silently skip malformed pairs
# ═══════════════════════════════════════════════════════════════════════════

def test_F018_pairs_keys_values_skips_junk(fix):
    _, m = fix
    K, V = Var(), Var()
    ok = _first(m, "pairs_keys_values", [("-", 1, "a"), "junk"], K, V)
    assert not ok  # A09-F018 fixed: was succeeding with K=[1], V=['a']


# ═══════════════════════════════════════════════════════════════════════════
# A09-F019 — same_length/2 ground-Seg* support is dead code
# ═══════════════════════════════════════════════════════════════════════════

def test_F019_same_length_ground_segstring(fix):
    _, m = fix
    L = Var()
    assert _first(m, "same_length", SegString(["ab"]), L)


def test_F019_regression_same_length_str(fix):
    _, m = fix
    L = Var()
    assert _first(m, "same_length", chars("ab"), L)


# ═══════════════════════════════════════════════════════════════════════════
# A09-F029 — type-check predicates disagree on ground Seg* values
# ═══════════════════════════════════════════════════════════════════════════

def test_F029_ground_segstring_typecheck_coherent(fix):
    """A09-F029: for a ground SegString the type-check matrix must cohere —
    is_str = string = is_list = is_chars = True.

    THE FLIP (2026-09-06-atoms-as-cells-strings §6.3) moved ``atomic`` out of
    that row and into the FALSE column, and the coherence argument moves with
    it: a string IS the list of its char atoms, so ``atomic`` must answer for
    it exactly what it answers for that list, which is False.  Task 15
    item 2 (ISO alignment, 2026-09-07) moves ``compound`` the other way for
    the same reason: a NON-EMPTY list is the ``'.'/2`` compound, so a ground
    non-empty ``SegString`` is compound, and the empty one is the atom
    ``'[]'`` and is not.  The incoherence F029 fixed (``is_str`` true while
    ``is_list`` false) is not reintroduced — every row still agrees with the
    list the string denotes."""
    _, m = fix
    seg = SegString(["ab"])
    assert _first(m, "is_str", seg)
    assert _first(m, "string", seg)
    assert _first(m, "is_list", seg)
    assert not _first(m, "atomic", seg)
    assert _first(m, "is_chars", seg)
    assert _first(m, "compound", seg)
    assert not _first(m, "atom", seg)
    # …and each row answers what it answers for the LIST the string denotes.
    lst = [mint("a"), mint("b")]
    for pred in ("is_str", "string", "is_list", "atomic", "is_chars",
                 "compound", "atom"):
        assert bool(_first(m, pred, seg)) is bool(_first(m, pred, lst)), pred


# ═══════════════════════════════════════════════════════════════════════════
# A09-F020 / A09-F021 — C-level defence (subprocess probes)
# ═══════════════════════════════════════════════════════════════════════════

def test_F020_chars_core_non_trail():
    p = run_snippet("""
        import resource
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        from clausal.logic.builtins._chars_core import char_type_find_types
        from clausal.logic.variables import Var
        try:
            char_type_find_types("a", 0, Var(), "not a trail")
        except TypeError:
            print("TYPEERROR-OK")
    """)
    assert p.returncode == 0 and "TYPEERROR-OK" in p.stdout


def test_F020_chars_core_empty_string():
    p = run_snippet("""
        import resource
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        from clausal.logic.builtins._chars_core import char_type_find_types
        from clausal.logic.variables import Var, Trail
        r = char_type_find_types("", 0, Var(), Trail())
        print("RESULT", r)
    """)
    # Correct behaviour: None (no char to classify) or a typed error.
    assert p.returncode == 0 and ("RESULT None" in p.stdout
                                  or "TypeError" in p.stderr)


def test_F021_lists_core_non_list_segfault():
    p = run_snippet("""
        import resource
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        from clausal.logic._lists_core import member_find
        from clausal.logic.variables import Var, Trail
        try:
            member_find("abc", 0, Var(), Trail())
        except TypeError:
            print("TYPEERROR-OK")
    """)
    assert p.returncode == 0  # today: rc=-11 (SIGSEGV)


def test_F020_regression_c_error_paths_hold_under_loop(refcount_stable, fix):
    """C inner loops (member/append-split/char_type/atom_concat/sub_atom)
    do not leak objects or allocations across repeated full enumerations."""
    _, m = fix

    def thunk():
        X = Var()
        _collect(m, X, "in_", X, [1, 2, 3])
        A, B = Var(), Var()
        _collect(m, A, "atom_concat", A, B, mint("abcd"))
        S = Var()
        _collect(m, S, "sub_atom", mint("abc"), Var(), Var(), Var(), S)
        C = Var()
        _collect(m, C, "char_type", C, mint("digit"))
        E, R = Var(), Var()
        _collect(m, E, "select", E, [1, 2, 3], R)

    refcount_stable(thunk, iterations=300, tol=256, alloc_tol=262144)


# ═══════════════════════════════════════════════════════════════════════════
# A09-F022 — cross-type == conflation (inherits A01-D001; A05-D001 precedent)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.xfail(strict=False, reason="A09-F022: subtract removes 1 for "
                   "True via Python == (cross-type conflation)")
def test_F022_subtract_cross_type(fix):
    _, m = fix
    D = Var()
    assert _first(m, "subtract", [1], [True], D)
    assert _dw(D) == [1]  # actual: []


# A09-F022 (group_pairs_by_key) CLOSED by R4 (2026-09-28): keys are compared
# with ISO `==` as in Scryer's library(pairs), not by Python hash, so 1 and
# True stay apart and two equal list keys group together.  xfail removed.
def test_F022_group_pairs_cross_type(fix):
    _, m = fix
    G = Var()
    assert _first(m, "group_pairs_by_key", [("-", 1, "a"), ("-", True, "b")], G)
    assert len(_dw(G)) == 2


def test_F022_group_pairs_unhashable_split(fix):
    _, m = fix
    G = Var()
    assert _first(m, "group_pairs_by_key", [("-", [1], "a"), ("-", [1], "b")], G)
    assert len(_dw(G)) == 1


# A09-F022 CLOSED 2026-09-09. `sort/2` deduped 1/1.0/True into one element
# because `_standard_order_key` gave equal-value numbers of different types the
# same key. The ISO 7.2.1 tiebreak (float before int, then the other numeric
# kinds) makes them distinct terms, so all three survive. The xfail marker is
# REMOVED rather than left at strict=False: a stale non-strict xfail would let
# a regression back to deduping pass silently.
# Spec: docs/superpowers/specs/2026-09-09-standard-order-of-terms-design.md §4
def test_F022_sort_cross_type_dedup(fix):
    _, m = fix
    S = Var()
    assert _first(m, "sort", [1, 1.0, True], S)
    assert len(_dw(S)) != 1  # ISO keeps 1 and 1.0 distinct


# ═══════════════════════════════════════════════════════════════════════════
# A09-F025 — open-mode gaps (doc: append "works in all directions")
# ═══════════════════════════════════════════════════════════════════════════

def test_F025_append_open_tail(fix):
    # A09-F025 closed (2026-09-28): append([1], L2, L3) answers L3 = [1|L2].
    _, m = fix
    assert _first(m, "append", [1], Var(), Var())


def test_F025_regression_append_supported_modes(fix):
    _, m = fix
    Z = Var()
    assert _first(m, "append", [1], [2], Z) and _dw(Z) == [1, 2]
    L, R = Var(), Var()
    assert len(_collect(m, L, "append", L, R, [1, 2])) == 3
    S = Var()
    assert _first(m, "append", chars("he"), chars("llo"), S) and deref(S) == chars("hello")


# ═══════════════════════════════════════════════════════════════════════════
# A09-F027 — functor/unpack non-atom functor handling (low)
# ═══════════════════════════════════════════════════════════════════════════

def test_F027_functor_numeric_roundtrip(fix):
    _, m = fix
    N, A = Var(), Var()
    assert _first(m, "functor", 3, N, A)
    assert deref(N) == 3 and deref(A) == 0


def test_F027_unpack_numeric_functor(fix):
    _, m = fix
    with pytest.raises(LogicException):
        _first(m, "unpack", Var(), [3, 1, 2])


# ═══════════════════════════════════════════════════════════════════════════
# A09-F028/F030/F031 — minor ISO divergences (must_be, number parse, atom_concat)
# ═══════════════════════════════════════════════════════════════════════════

def test_F028_must_be_unknown_type_domain_error(fix):
    """A09-F028: an unknown type name is a domain_error(type, Name) — the
    TYPE is wrong, not the term — not a misleading type_error(Name, Term)."""
    _, m = fix
    with pytest.raises(LogicException) as ei:
        _first(m, "must_be", mint("nonsense"), 5)
    inner = cell_args(ei.value.term)[0]
    assert type(inner) is tuple and cell_functor(inner) == "domain_error"


def test_F028_must_be_unbound_type_raises(fix):
    """A09-F028: must_be raises on violation — an unbound Type is a usage
    error, not a silent failure."""
    _, m = fix
    with pytest.raises(LogicException):
        _first(m, "must_be", Var(), 5)


def test_F028_regression_must_be_known_types(fix):
    _, m = fix
    assert _first(m, "must_be", mint("integer"), 5)
    with pytest.raises(LogicException):
        _first(m, "must_be", mint("integer"), mint("x"))


def test_F031_atom_concat_check_mode_type_error(fix):
    """A09-F031: a non-atom bound arg raises type_error(atom, _) in check
    mode too, not just the open mode (was a silent failure)."""
    _, m = fix
    with pytest.raises(LogicException):
        _first(m, "atom_concat", 12, mint("a"), mint("12a"))


def test_F031_regression_atom_concat_valid(fix):
    _, m = fix
    C = Var()
    assert (_first(m, "atom_concat", mint("1"), mint("2"), C)
            and deref(C) == mint("12"))


def test_F030_number_chars_python_lenient(fix):
    """A09-F030: parsing is deliberately Python-native/lenient — a char list
    with surrounding whitespace parses (documented in docs/builtins.md)."""
    _, m = fix
    N = Var()
    assert _first(m, "number_chars", N, chars(" 1")) and deref(N) == 1


# ═══════════════════════════════════════════════════════════════════════════
# A09-F032 — Seg*-input str promotion inconsistency (low)
# ═══════════════════════════════════════════════════════════════════════════

def test_F032_msort_segstring_promotion(fix):
    _, m = fix
    S = Var()
    assert _first(m, "msort", SegString(["ba"]), S)
    assert deref(S) == chars("ab")  # A09-F032 fixed: was ['a', 'b']


def test_F032_regression_reverse_segstring_promotion(fix):
    _, m = fix
    R = Var()
    assert _first(m, "reverse", SegString(["ab"]), R)
    assert deref(R) == chars("ba")


# ═══════════════════════════════════════════════════════════════════════════
# Regression guards — behaviours probed and found CORRECT
# ═══════════════════════════════════════════════════════════════════════════

def test_regression_arg_bounds(fix):
    """arg/3 rejects n=0 and negative n — no Python-indexing leak (C path)."""
    _, m = fix
    t = ("f", 1, 2)
    assert not _first(m, "arg", 0, t, Var())
    assert not _first(m, "arg", 0, [10, 20], Var())
    # A negative N is ISO 8.5.2.3's domain_error(not_less_than_zero, N)
    # (Scryer-verified, 2026-09-30); it used to fail silently.
    for term in (t, chars("ab")):
        with pytest.raises(LogicException) as info:
            _first(m, "arg", -1, term, Var())
        assert cell_args(info.value.term)[0] == (
            "domain_error", "not_less_than_zero", -1)
    X = Var()
    assert _first(m, "arg", 1, t, X) and deref(X) == 1


def test_regression_arg_cons_semantics(fix):
    """Lists decompose as cons cells (user decision 2026-06-13).

    THE FLIP (2026-09-06-atoms-as-cells-strings §5.4/§13 row 18b) restores
    the same reading for a STRING, which is the list of its char atoms:
    ``arg(2, "abc", Y)`` gives ``Y = "bc"``, a ``str`` SLICE — the tail of a
    string stays a string, nothing is expanded.  P3-1 Task 5 had retired
    that because a str was then an ATOM, and an atom has no arguments.
    """
    _, m = fix
    X = Var()
    assert _first(m, "arg", 2, [10, 20, 30], X) and _dw(X) == [20, 30]
    Y = Var()
    assert _first(m, "arg", 2, chars("abc"), Y) and _dw(Y) == chars("bc")


def test_regression_tfilter_user_reified(fix):
    """tfilter drives a clause-compiled reified predicate correctly."""
    _, m = fix
    R = Var()
    assert _first(m, "tfprobe", R) and _dw(R) == [1, 3]


def test_regression_dr_alias_guard(fix):
    """Destructive-reuse append does NOT mutate a list aliased through an
    earlier-built compound (runtime refcount guard holds)."""
    _, m = fix
    P, R = Var(), Var()
    assert _first(m, "drprobe", P, R)
    # R6: pair(A, 0) is the cell ("pair", A, 0) -- A is slot 1.
    inner = deref(deref(P)[1])  # the list captured in pair(A, 0)
    assert len(inner) == 1  # DR extend would have made it [_, 3]


def test_regression_bytes_codes_model(fix):
    _, m = fix
    assert _first(m, "in_", 97, b"abc")
    assert not _first(m, "in_", "a", b"abc")  # chars/codes divide holds


def test_regression_seg_length(fix):
    _, m = fix
    N = Var()
    assert _first(m, "length", SegString(["ab"]), N) and deref(N) == 2


def test_regression_numbervars(fix):
    _, m = fix
    X, Y, E = Var(), Var(), Var()
    t = [X, Y, X]
    assert _first(m, "numbervars", t, 0, E)
    assert deref(E) == 2
    a, b, c = (deref(e) for e in t)
    assert a == ("$VAR", 0) and b == ("$VAR", 1) and c == ("$VAR", 0)


def test_regression_replicate_str_promotion(fix):
    _, m = fix
    R = Var()
    # A list of CHAR ATOMS is a string, so the result promotes back to one.
    assert (_first(m, "replicate", 3, char_atom("a"), R)
            and deref(R) == chars("aaa"))


def test_regression_atom_concat_typed_error(fix):
    """F077 lock-in: non-atom bound arg in open mode → type_error, not
    instantiation_error."""
    _, m = fix
    with pytest.raises(LogicException):
        _first(m, "atom_concat", 12, mint("a"), Var())


def test_regression_must_be_and_listing_errors(fix):
    _, m = fix
    with pytest.raises(LogicException):
        _first(m, "must_be", mint("integer"), mint("x"))
    with pytest.raises(LogicException):
        _first(m, "listing", 3)


def test_regression_dcg_state_oracle(fix):
    """Differential oracle: clausal/examples/dcg_state.clausal semantics."""
    pymod = _load_module(
        "a09_dcg_oracle", os.path.join(REPO, "clausal/examples/dcg_state.clausal"))
    m = pymod.__dict__["$module"]
    N = Var()
    assert _first(m, "phrase", pymod.count3, [0], [N]) and deref(N) == 3
    N2 = Var()
    leaf = mint("leaf")
    assert _first(m, "num_leaves", [leaf, [leaf, leaf]], N2)
    assert deref(N2) == 3


def test_regression_group_by_consecutive(fix):
    _, m = fix
    G = Var()
    assert _first(m, "gbprobe", G)  # keys 1/True conflate (F022) but no crash


def test_regression_statistics_and_gensym(fix):
    _, m = fix
    K = Var()
    keys = _collect(m, K, "statistics", K, Var())
    assert mint("wall_time") in keys and mint("cpu_time") in keys
    A = Var()
    assert (_first(m, "gensym", mint("g"), A)
            and spelling(deref(A)).startswith("g_"))


def test_regression_take_drop_negative(fix):
    _, m = fix
    T = Var()
    assert _first(m, "take", -1, [1, 2], T) and _dw(T) == []
    D = Var()
    assert _first(m, "drop", -1, [1, 2], D) and _dw(D) == [1, 2]


def test_regression_python_list_builtins_leak_free(refcount_stable, fix):
    """Python-path list builtins under backtracking-heavy enumeration."""
    _, m = fix

    def thunk():
        P = Var()
        _collect(m, P, "permutation", [1, 2, 3], P)
        L, R = Var(), Var()
        _collect(m, L, "append", L, R, chars("abc"))

    refcount_stable(thunk, iterations=300, tol=256, alloc_tol=262144)
