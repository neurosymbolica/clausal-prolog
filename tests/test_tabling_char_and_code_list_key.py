"""One char list or code list, one table key, whatever shape built it.

The engine builds one char list as the chars carrier ``('$chars', s)`` or as a
plain list of one-char atoms, and one code list as ``bytes`` or as a plain list
of ints.  Each pair is one term (they unify, ``compare/3`` says ``=``), so a
tabled predicate must answer it once and a call with either shape is one
variant.  The variant key used to follow the Python shape, so a tabled
predicate answered ``"ab"`` and ``[a, b]`` as two answers.
"""
from __future__ import annotations

import pytest

from clausal.logic import tabling
from clausal.logic.cells import chars
from clausal.logic.solve import solve
from clausal.logic.variables import Trail, Var, unify
from clausal.testing import load_clausal_module


_KEYS = [("py", tabling._normalize_for_key_py)]
try:
    from clausal.logic._tabling_core import _normalize_for_key as _c_key
    _KEYS.append(("c", _c_key))
except ImportError:                       # the C twin is optional
    pass


@pytest.fixture(params=_KEYS, ids=[k for k, _ in _KEYS])
def key(request):
    return request.param[1]


# ── one term, one key ────────────────────────────────────────────────────────

@pytest.mark.parametrize("a, b", [
    (["a", "b"], chars("ab")),
    ([], chars("")),
    ([97, 98], b"ab"),
    ([], b""),
    (("f", ["a", "b"]), ("f", chars("ab"))),          # nested
    ([["x", "y"]], [chars("xy")]),
])
def test_both_shapes_of_one_term_key_alike(key, a, b):
    assert key(a) == key(b)


def test_bound_elements_count():
    x, y = Var(), Var()
    t = Trail()
    assert unify(x, "a", t) and unify(y, "b", t)
    for _, key in _KEYS:
        assert key([x, y]) == key(chars("ab"))


# ── different terms keep different keys ──────────────────────────────────────

@pytest.mark.parametrize("a, b", [
    (["a", "b"], "ab"),                                # a char list is not the atom
    (chars("ab"), "ab"),
    (["a", "b"], ["a", "c"]),
    (["ab"], chars("ab")),                             # one two-char atom
    ([chars("a"), chars("b")], chars("ab")),           # a list of strings
    (["a", "b"], [97, 98]),                            # chars are not codes
    (chars("ab"), b"ab"),
    ([1, 300], b"\x01"),
    ([True], b"\x01"),                                 # a truth atom is not code 1
    ([1.0], b"\x01"),
    ([], ["a"]),
])
def test_different_terms_key_apart(key, a, b):
    assert key(a) != key(b)


def test_an_open_list_is_not_a_char_list(key):
    assert key(["a", Var()]) != key(chars("a_"))


@pytest.mark.parametrize("term", [
    ["a", "b"], chars("ab"), [], chars(""), [97, 98], b"ab", ["a", 1],
    ("f", ["x", "y"], [3]), {"k": ["a"]}, [["a"], []],
])
def test_the_python_and_c_keys_agree(term):
    if len(_KEYS) < 2:
        pytest.skip("C twin not built")
    assert _KEYS[0][1](term) == _KEYS[1][1](term)


# ── end to end: a tabled predicate answers one term once ─────────────────────

_PL = """\
:- table(p/1).
p(L) :- L = "ab".
p(L) :- atom_chars(ab, L).

:- table(e/1).
e(L) :- L = "".
e(L) :- L = [].

:- table(m/1).
m(L) :- L = "ab".
m(L) :- L = [a, c].
m(L) :- atom_chars(ac, L).
"""

_SEAM = """\
-private([ab])
-table(c/1)
c(L) <- atom_codes(ab, L)
c(L) <- (L is [97, 98])
c(L) <- (L is b"ab")
"""


@pytest.fixture(scope="module")
def mods(tmp_path_factory):
    d = tmp_path_factory.mktemp("tabkey")
    (d / "tabkey_pl.clausal").write_text(_PL)
    (d / "tabkey_seam.seam").write_text(_SEAM)
    return (load_clausal_module(d / "tabkey_pl.clausal"),
            load_clausal_module(d / "tabkey_seam.seam"))


def _count(mod, name):
    v = Var()
    return sum(1 for _ in solve((name, v), mod))


@pytest.mark.parametrize("name, n", [("p", 1), ("e", 1), ("m", 2)])
def test_a_tabled_char_list_is_answered_once(mods, name, n):
    assert _count(mods[0], name) == n


def test_a_tabled_code_list_is_answered_once(mods):
    assert _count(mods[1], "c") == 1


# ── the nil cell () and partial lists (Seg*) ─────────────────────────────────

def test_the_nil_cell_keys_as_nil(key):
    assert key(()) == key([]) == key(chars("")) == key(b"")


def test_a_ground_seg_keys_as_its_list(key):
    from clausal.terms import ConcreteSeg, SegList, VarSeg
    v = Var()
    assert unify(v, ["b"], Trail())
    assert key(SegList([ConcreteSeg(["a"]), VarSeg(v)])) == key(chars("ab"))


def test_a_partial_list_and_a_partial_string_key_alike(key):
    from clausal.terms import ConcreteSeg, SegList, SegString, VarSeg
    t1, t2 = Var(), Var()
    lst = SegList([ConcreteSeg(["a"]), VarSeg(t1)])
    s = SegString(["a", VarSeg(t2)])
    assert key(lst) == key(s)
    assert key(lst) != key(SegList([ConcreteSeg(["a", "b"]), VarSeg(Var())]))
    assert key(lst) != key(chars("a"))
    hash(key(lst))                                     # usable as a table key


_PARTIAL = """\
:- table(tq/2).
tq(X, Y) :- append(X, Y, "ab").
ground_after_binding(Y) :- X = [a|T], T = [b], tq(X, Y).
open_tail(R) :- X = [a|_], tq(X, R).
"""


@pytest.fixture(scope="module")
def partial_mod(tmp_path_factory):
    p = tmp_path_factory.mktemp("tabpartial") / "tabpartial.clausal"
    p.write_text(_PARTIAL)
    return load_clausal_module(p)


def test_a_tabled_call_with_a_partial_list_argument_answers(partial_mod):
    """It used to raise ``TypeError: unhashable type: 'SegList'``."""
    v = Var()
    got = [v.value for _ in solve(("ground_after_binding", v), partial_mod)]
    assert len(got) == 1 and unify(got[0], [], Trail()), got     # Y = []
    v = Var()
    got = [v.value for _ in solve(("open_tail", v), partial_mod)]
    assert len(got) == 2, got                                    # "b" and []
    assert any(unify(g, ["b"], Trail()) for g in got), got
    assert any(unify(g, [], Trail()) for g in got), got


# ── hostile and deep terms: an error, never a crash ──────────────────────────
# Run in a child process: the failure these pin was a segfault.

def _child(src):
    import subprocess, sys, os
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(sys.path))
    r = subprocess.run([sys.executable, "-c", src], capture_output=True,
                       text=True, timeout=300, env=env)
    return r.returncode, r.stdout.strip()


_DEEP = """
from clausal.logic import tabling
from clausal.logic.variables import Var
from clausal.terms import SegList, ConcreteSeg, VarSeg
t = 0
for _ in range(2):
    for _ in range(30000):
        t = [t, 1000]
    t = SegList([ConcreteSeg([t]), VarSeg(Var())])
try:
    tabling._normalize_for_key(t)
    print("ok")
except RecursionError:
    print("RecursionError")
"""


def test_a_partial_list_nested_deep_is_a_recursion_error_not_a_crash():
    """The depth counter restarted inside each partial list, so two layers
    of 30000 overflowed the C stack."""
    rc, out = _child(_DEEP)
    assert (rc, out) == (0, "RecursionError")


_HOSTILE = """
from clausal.logic import tabling
lst = []
class Evil:
    @property
    def __class__(self):
        lst.clear()
        return Evil
lst.extend([Evil(), 1000, 2000])
try:
    tabling._normalize_for_key(lst)
except Exception:
    pass
print("survived")
"""


def test_an_element_that_mutates_the_list_does_not_crash():
    """The Seg* test used isinstance, which runs a hostile ``__class__``."""
    rc, out = _child(_HOSTILE)
    assert (rc, out) == (0, "survived")
