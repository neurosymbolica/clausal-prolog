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

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic import solve as solve_mod
from clausal.logic.variables import Var, deref, is_var
from clausal.logic.exceptions import LogicException
from clausal.terms import Compound, SegString

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
    inner = deref(out[0].B)  # pair(A=5, B=?) — B must be 1, not unbound
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

@pytest.mark.xfail(strict=False, reason="A09-F004: maplist/3 commits to the "
                   "first solution per element — cannot reach Y='b'")
def test_F004_maplist_committed_choice(fix):
    _, m = fix
    Y = Var()
    assert _collect(m, Y, "mlprobe", Y) == ["b"]


@pytest.mark.xfail(strict=False, reason="A09-F004: foldl/4 same commitment")
def test_F004_foldl_committed_choice(fix):
    _, m = fix
    assert _first(m, "foldprobe", Var())


def test_F004_regression_maplist_first_solution(fix):
    """The committed-choice first solution itself is produced correctly."""
    _, m = fix
    Y = Var()
    assert _collect(m, Y, "mlfirst", Y) == ["a"]


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
    with pytest.raises(LogicException):
        _first(m, "azrule", Var())
    V = Var()
    got = set()
    try:
        got = set(_collect(m, V, "seen2", V))
    except NotImplementedError:
        pytest.fail("predicate poisoned: NotImplementedError on later query")
    # The base fact survives; the rejected rule never derived 7.
    assert "dummy" in got and 7 not in got


# ═══════════════════════════════════════════════════════════════════════════
# A09-F006 — assertz/retract on locked predicate silently fail
# (RuntimeError raised, then swallowed by the trampoline drive loop)
# ═══════════════════════════════════════════════════════════════════════════

def test_F006_assertz_locked_raises(locked_mod):
    _, m = locked_mod
    with pytest.raises(Exception):  # permission_error LogicException expected
        _first(m, "lockassert", Var())


def test_F006_retract_locked_raises(locked_mod):
    _, m = locked_mod
    with pytest.raises(Exception):
        _first(m, "lockretract", Var())


# ═══════════════════════════════════════════════════════════════════════════
# A09-F007 — RecursionError from builtin helpers swallowed as failure
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.xfail(strict=False, reason="A09-F007: RecursionError is a "
                   "RuntimeError subclass; drive loop treats it as generator "
                   "exhaustion → cyclic input reported as plain 'no'")
def test_F007_flatten_cyclic_not_silent(fix):
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

@pytest.mark.xfail(strict=False, reason="A09-F008: retract(seen2(X)) leaves "
                   "X unbound (ISO binds the retracted clause's args)")
def test_F008_retract_binds_pattern(fix):
    _, m = fix
    X = Var()
    assert _first(m, "retprobe", X)
    assert not is_var(deref(X)) and deref(X) == 5


# ═══════════════════════════════════════════════════════════════════════════
# A09-F009 — sequence//1 compares terminals with == instead of unify
# ═══════════════════════════════════════════════════════════════════════════

def test_F009_sequence_var_terminal(fix):
    _, m = fix
    X, S = Var(), Var()
    assert _first(m, "sequence", [X], "a", S)
    assert deref(X) == "a" and deref(S) == ""


def test_F009_regression_sequence_ground_modes(fix):
    _, m = fix
    S = Var()
    assert _first(m, "sequence", ["a"], "ab", S) and deref(S) == "b"
    S0 = Var()
    assert _first(m, "sequence", "a", S0, "b") and deref(S0) == "ab"


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

@pytest.mark.xfail(strict=False, reason="A09-F011: plus/3 concatenates "
                   "strings — docstring says numeric")
def test_F011_plus_string_concat(fix):
    _, m = fix
    assert not _first(m, "plus", "a", "b", Var())


@pytest.mark.xfail(strict=False, reason="A09-F011: mixed-type plus raises "
                   "raw TypeError instead of a typed logic error / failure")
def test_F011_plus_mixed_raw_typeerror(fix):
    _, m = fix
    try:
        _first(m, "plus", 1, "a", Var())
    except TypeError:
        pytest.fail("raw TypeError escaped from plus/3")


@pytest.mark.xfail(strict=False, reason="A09-F011: max_/3 accepts strings")
def test_F011_max_strings(fix):
    _, m = fix
    assert not _first(m, "max_", "a", "b", Var())


# ═══════════════════════════════════════════════════════════════════════════
# A09-F012 — raw Python exceptions escape from builtins
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.xfail(strict=False, reason="A09-F012: short pair → IndexError")
def test_F012_pairs_values_short_pair(fix):
    _, m = fix
    try:
        _first(m, "pairs_values", [[1]], Var())
    except IndexError:
        pytest.fail("raw IndexError escaped from pairs_values/2")


@pytest.mark.xfail(strict=False, reason="A09-F012: unhashable dict key → "
                   "raw TypeError")
def test_F012_dict_pairs_unhashable_key(fix):
    _, m = fix
    try:
        _first(m, "dict_pairs", Var(), [[[1], 2]])
    except TypeError:
        pytest.fail("raw TypeError escaped from dict_pairs/2")


@pytest.mark.xfail(strict=False, reason="A09-F012: unhashable set element → "
                   "raw TypeError")
def test_F012_set_list_unhashable(fix):
    _, m = fix
    try:
        _first(m, "set_list", Var(), [[1]])
    except TypeError:
        pytest.fail("raw TypeError escaped from set_list/2")


@pytest.mark.xfail(strict=False, reason="A09-F012: exp_mod non-invertible "
                   "base → raw ValueError")
def test_F012_exp_mod_raw_valueerror(fix):
    _, m = fix
    try:
        _first(m, "exp_mod", 2, -1, 4, Var())
    except ValueError:
        pytest.fail("raw ValueError escaped from exp_mod/4")


@pytest.mark.xfail(strict=False, reason="A09-F012: max_by raises raw "
                   "TypeError on incomparable keys while sort_by silently "
                   "falls back")
def test_F012_max_by_incomparable_keys(fix):
    _, m = fix
    try:
        _first(m, "mbprobe", Var())
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
    assert _first(m, "char_type", "٣", "digit")  # ARABIC-INDIC THREE
    C = Var()
    chars = _collect(m, C, "char_type", C, "digit")
    assert "٣" in chars


def test_F013_char_type_space_consistency(fix):
    _, m = fix
    assert _first(m, "char_type", "\xa0", "space")
    C = Var()
    assert "\xa0" in _collect(m, C, "char_type", C, "space")


def test_F013_char_type_punct_consistency(fix):
    _, m = fix
    assert _first(m, "char_type", "\xa1", "punct")
    C = Var()
    assert "\xa1" in _collect(m, C, "char_type", C, "punct")


def test_F013_regression_alpha_enum_unicode(fix):
    """F072 half that WAS fixed: alpha enumeration includes non-ASCII."""
    _, m = fix
    C = Var()
    chars = _collect(m, C, "char_type", C, "alpha")
    assert "α" in chars  # α


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
        types = _collect(m, T, "char_type", "α", T)
    finally:
        ch._c_char_type_find_types = saved
    assert "alpha" in types


def test_F014_regression_char_type_c_path_non_ascii(fix):
    _, m = fix
    T = Var()
    types = _collect(m, T, "char_type", "α", T)
    assert "alpha" in types and "lower" in types


# ═══════════════════════════════════════════════════════════════════════════
# A09-F015 — bool-as-int acceptance is inconsistent; between C/Py diverge
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.xfail(strict=False, reason="A09-F015: length(L, True) builds a "
                   "1-element list — bool accepted as a length")
def test_F015_length_bool(fix):
    _, m = fix
    assert not _first(m, "length", Var(), True)


@pytest.mark.xfail(strict=False, reason="A09-F015: list_item/take/arg/"
                   "functor/sub_atom/numlist/char_code accept bool indices")
def test_F015_list_item_bool_index(fix):
    _, m = fix
    assert not _first(m, "list_item", True, ["a", "b"], Var())


@pytest.mark.xfail(strict=False, reason="A09-F015: between/3 C rejects bool "
                   "bounds but the Python fallback accepts them")
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
    assert _first(m, "is_list", "abc")  # locked-in F080 behaviour
    assert _first(m, "must_be", "list", "abc")  # raises today


# ═══════════════════════════════════════════════════════════════════════════
# A09-F017 — atom_chars/atom_codes/number_chars/number_codes reject the
# str/bytes forms of their char/code lists
# ═══════════════════════════════════════════════════════════════════════════

def test_F017_atom_chars_str_arg(fix):
    _, m = fix
    A = Var()
    assert _first(m, "atom_chars", A, "abc")
    assert deref(A) == "abc"


def test_F017_atom_codes_bytes_arg(fix):
    _, m = fix
    A = Var()
    assert _first(m, "atom_codes", A, b"ab")
    assert deref(A) == "ab"


def test_F017_regression_list_forms_work(fix):
    _, m = fix
    A = Var()
    assert _first(m, "atom_chars", A, ["a", "b"]) and deref(A) == "ab"
    B = Var()
    assert _first(m, "atom_codes", B, [97, 98]) and deref(B) == "ab"


# ═══════════════════════════════════════════════════════════════════════════
# A09-F018 — pairs_* silently skip malformed pairs
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.xfail(strict=False, reason="A09-F018: non-list 'pair' entries "
                   "are silently dropped — should fail or raise")
def test_F018_pairs_keys_values_skips_junk(fix):
    _, m = fix
    K, V = Var(), Var()
    ok = _first(m, "pairs_keys_values", [[1, "a"], "junk"], K, V)
    assert not ok  # today: succeeds with K=[1], V=['a']


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
    assert _first(m, "same_length", "ab", L)


# ═══════════════════════════════════════════════════════════════════════════
# A09-F029 — type-check predicates disagree on ground Seg* values
# ═══════════════════════════════════════════════════════════════════════════

def test_F029_ground_segstring_typecheck_coherent(fix):
    """A09-F029: for a ground SegString the type-check matrix must cohere —
    is_str = string = is_list = atomic = is_chars = True, compound = False.
    Before the fix, atomic and is_chars rejected it while is_str/is_list
    accepted it (is_str(X) implying not-atomic(X) is incoherent)."""
    _, m = fix
    seg = SegString(["ab"])
    assert _first(m, "is_str", seg)
    assert _first(m, "string", seg)
    assert _first(m, "is_list", seg)
    assert _first(m, "atomic", seg)
    assert _first(m, "is_chars", seg)
    assert not _first(m, "compound", seg)


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
        _collect(m, A, "atom_concat", A, B, "abcd")
        S = Var()
        _collect(m, S, "sub_atom", "abc", Var(), Var(), Var(), S)
        C = Var()
        _collect(m, C, "char_type", C, "digit")
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


@pytest.mark.xfail(strict=False, reason="A09-F022: group_pairs_by_key "
                   "merges 1 and True keys")
def test_F022_group_pairs_cross_type(fix):
    _, m = fix
    G = Var()
    assert _first(m, "group_pairs_by_key", [[1, "a"], [True, "b"]], G)
    assert len(_dw(G)) == 2  # actual: 1 merged group


@pytest.mark.xfail(strict=False, reason="A09-F022: equal unhashable keys "
                   "split into separate groups (id() fallback)")
def test_F022_group_pairs_unhashable_split(fix):
    _, m = fix
    G = Var()
    assert _first(m, "group_pairs_by_key", [[[1], "a"], [[1], "b"]], G)
    assert len(_dw(G)) == 1  # actual: 2 groups


@pytest.mark.xfail(strict=False, reason="A09-F022: sort dedups 1/1.0/True "
                   "into one element")
def test_F022_sort_cross_type_dedup(fix):
    _, m = fix
    S = Var()
    assert _first(m, "sort", [1, 1.0, True], S)
    assert len(_dw(S)) != 1  # ISO keeps 1 and 1.0 distinct


# ═══════════════════════════════════════════════════════════════════════════
# A09-F025 — open-mode gaps (doc: append "works in all directions")
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.xfail(strict=False, reason="A09-F025: append(+,-,-) yields no "
                   "solution (no partial-list mode)")
def test_F025_append_open_tail(fix):
    _, m = fix
    assert _first(m, "append", [1], Var(), Var())


def test_F025_regression_append_supported_modes(fix):
    _, m = fix
    Z = Var()
    assert _first(m, "append", [1], [2], Z) and _dw(Z) == [1, 2]
    L, R = Var(), Var()
    assert len(_collect(m, L, "append", L, R, [1, 2])) == 3
    S = Var()
    assert _first(m, "append", "he", "llo", S) and deref(S) == "hello"


# ═══════════════════════════════════════════════════════════════════════════
# A09-F027 — functor/unpack non-atom functor handling (low)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.xfail(strict=False, reason="A09-F027: functor(3,N,0) gives "
                   "N='3' (str) — not roundtrippable, ISO gives the number")
def test_F027_functor_numeric_roundtrip(fix):
    _, m = fix
    N, A = Var(), Var()
    assert _first(m, "functor", 3, N, A)
    assert deref(N) == 3 and deref(A) == 0


@pytest.mark.xfail(strict=False, reason="A09-F027: unpack(T,[3,1,2]) builds "
                   "Compound('3',(1,2)) instead of raising type_error(atom)")
def test_F027_unpack_numeric_functor(fix):
    _, m = fix
    with pytest.raises(LogicException):
        _first(m, "unpack", Var(), [3, 1, 2])


# ═══════════════════════════════════════════════════════════════════════════
# A09-F032 — Seg*-input str promotion inconsistency (low)
# ═══════════════════════════════════════════════════════════════════════════

def test_F032_msort_segstring_promotion(fix):
    _, m = fix
    S = Var()
    assert _first(m, "msort", SegString(["ba"]), S)
    assert deref(S) == "ab"  # A09-F032 fixed: was ['a', 'b']


def test_F032_regression_reverse_segstring_promotion(fix):
    _, m = fix
    R = Var()
    assert _first(m, "reverse", SegString(["ab"]), R)
    assert deref(R) == "ba"


# ═══════════════════════════════════════════════════════════════════════════
# Regression guards — behaviours probed and found CORRECT
# ═══════════════════════════════════════════════════════════════════════════

def test_regression_arg_bounds(fix):
    """arg/3 rejects n=0 and negative n — no Python-indexing leak (C path)."""
    _, m = fix
    t = Compound("f", (1, 2))
    assert not _first(m, "arg", 0, t, Var())
    assert not _first(m, "arg", -1, t, Var())
    assert not _first(m, "arg", 0, [10, 20], Var())
    assert not _first(m, "arg", -1, "ab", Var())
    X = Var()
    assert _first(m, "arg", 1, t, X) and deref(X) == 1


def test_regression_arg_cons_semantics(fix):
    """Lists/strings decompose as cons cells (user decision 2026-06-13)."""
    _, m = fix
    X = Var()
    assert _first(m, "arg", 2, [10, 20, 30], X) and _dw(X) == [20, 30]
    Y = Var()
    assert _first(m, "arg", 2, "abc", Y) and deref(Y) == "bc"


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
    inner = deref(deref(P).A)  # the list captured in pair(A, 0)
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
    assert a.args == (0,) and b.args == (1,) and c.args == (0,)


def test_regression_replicate_str_promotion(fix):
    _, m = fix
    R = Var()
    assert _first(m, "replicate", 3, "a", R) and deref(R) == "aaa"


def test_regression_atom_concat_typed_error(fix):
    """F077 lock-in: non-atom bound arg in open mode → type_error, not
    instantiation_error."""
    _, m = fix
    with pytest.raises(LogicException):
        _first(m, "atom_concat", 12, "a", Var())


def test_regression_must_be_and_listing_errors(fix):
    _, m = fix
    with pytest.raises(LogicException):
        _first(m, "must_be", "integer", "x")
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
    assert _first(m, "num_leaves", ["leaf", ["leaf", "leaf"]], N2)
    assert deref(N2) == 3


def test_regression_group_by_consecutive(fix):
    _, m = fix
    G = Var()
    assert _first(m, "gbprobe", G)  # keys 1/True conflate (F022) but no crash


def test_regression_statistics_and_gensym(fix):
    _, m = fix
    K = Var()
    keys = _collect(m, K, "statistics", K, Var())
    assert "wall_time" in keys and "cpu_time" in keys
    A = Var()
    assert _first(m, "gensym", "g", A) and deref(A).startswith("g_")


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
        _collect(m, L, "append", L, R, "abc")

    refcount_stable(thunk, iterations=300, tol=256, alloc_tol=262144)
