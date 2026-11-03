"""The tabling key and the C term walkers on hostile or very deep terms:
an error, never a crash.

Each case of todo/done/tabling-key-residual-crashes-on-hostile-or-deep-terms-2026-10-08.md
runs in a child process, since what these pin was a segfault (a crash must
fail one test, not end the run).  The use-after-free cases run the child
under ``PYTHONMALLOC=debug``, which fills freed memory with a pattern, so a
read of freed memory crashes every time instead of when the allocator
happens to reuse the block.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest

from clausal.logic import tabling
from clausal.logic.solve import solve
from clausal.logic.variables import Trail, Var, unify
from clausal.terms import ConcreteSeg, SegList, VarSeg
from clausal.testing import load_clausal_module


def _child(src, debug_malloc=False):
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(sys.path))
    if debug_malloc:
        env["PYTHONMALLOC"] = "debug"
    r = subprocess.run([sys.executable, "-c", textwrap.dedent(src)],
                       capture_output=True, text=True, timeout=300, env=env)
    return r.returncode, r.stdout.strip(), r.stderr[-2000:]


def _ok(rc, out, err, allowed):
    """rc 0 and the last line of stdout one of *allowed*; on failure the
    message names the signal and the child's stderr."""
    last = out.splitlines()[-1] if out else ""
    assert rc == 0 and last in allowed, (rc, out, err)


# ── 1. a partial list nested as an ELEMENT tens of thousands deep ────────────

_SEG_ELEMENT_DEEP = """
import sys
from clausal.logic import tabling
from clausal.logic.variables import Var, walk
from clausal.terms import SegList, ConcreteSeg, VarSeg
t = 0
for _ in range(2):
    for _ in range(49000):
        t = [t, 1000]
    t = SegList([ConcreteSeg([t]), VarSeg(Var())])
for name, fn in [("key", tabling._normalize_for_key),
                 ("subgoal", lambda t: tabling.make_subgoal_key((t,), None)),
                 ("walk", walk)]:
    try:
        fn(t)
        print(name, "ok")
    except RecursionError:
        print(name, "RecursionError")
print("survived")
"""


def test_a_partial_list_nested_49000_x_2_deep_does_not_crash():
    """``walk`` restarted its depth inside each ``__walk__``, so two layers of
    49,000 overflowed the C stack (todo case 1)."""
    rc, out, err = _child(_SEG_ELEMENT_DEEP)
    _ok(rc, out, err, {"survived"})
    for line in out.splitlines()[:-1]:
        assert line.split()[1] in ("ok", "RecursionError"), out


_SEG_MANY_ELEMENT_LAYERS = """
from clausal.logic import tabling
from clausal.logic.variables import Var, walk
from clausal.terms import SegList, ConcreteSeg, VarSeg
t = 0
for _ in range(300):
    for _ in range(300):
        t = [t, 1000]
    t = SegList([ConcreteSeg([t]), VarSeg(Var())])
for fn in (walk, tabling._normalize_for_key):
    try:
        fn(t)
        print("ok")
    except RecursionError:
        print("RecursionError")
print("survived")
"""


def test_many_shallow_partial_list_layers_do_not_crash():
    rc, out, err = _child(_SEG_MANY_ELEMENT_LAYERS)
    _ok(rc, out, err, {"survived"})


# ── 2. the dereferenced term is owned while Python code runs ────────────────

_UNDO_IN_FIELD_GETTER = """
import dataclasses, gc
from clausal.logic import tabling
from clausal.logic.variables import Var, Trail, unify
tr = Trail()
class Getter:
    def __get__(self, obj, cls=None):
        if obj is None:
            return self
        tr.undo(0)          # unbinds x: the term held only by its binding goes
        gc.collect()
        return 1
@dataclasses.dataclass
class T:
    a: int
    b: int
T.a = Getter()
def build(x):
    o = T.__new__(T)
    o.__dict__["b"] = 2
    assert unify(x, o, tr)
for name, fn in [("key", tabling._normalize_for_key),
                 ("subgoal", lambda t: tabling.make_subgoal_key((t,), None)),
                 ("freeze", lambda t: tabling.freeze_args((t,), None))]:
    x = Var()
    build(x)
    try:
        fn(x)
    except Exception as e:
        pass
print("survived")
"""


def test_undoing_the_trail_in_a_field_getter_does_not_crash():
    """``do_normalize`` borrowed the dereferenced term across the field
    getter's Python code (todo case 2)."""
    rc, out, err = _child(_UNDO_IN_FIELD_GETTER, debug_malloc=True)
    _ok(rc, out, err, {"survived"})


# ── 3. re-entry through a field getter carries the depth ────────────────────

_REENTRY = """
import dataclasses
from clausal.logic import tabling
@dataclasses.dataclass
class D:
    inner: object
class Getter:
    def __get__(self, obj, cls=None):
        if obj is None:
            return self
        tabling.make_subgoal_key((obj.__dict__["payload"],), None)  # tables a call
        return 0
D.inner = Getter()
def deep(t, n):
    for _ in range(n):
        t = [t, 1000]
    return t
for n, layers in [(40000, 3), (5000, 100)]:
    t = 0
    for _ in range(layers):
        d = D.__new__(D)
        d.__dict__["payload"] = deep(t, n)
        t = d
    try:
        tabling.make_subgoal_key((deep(t, n),), None)
        print("ok")
    except RecursionError:
        print("RecursionError")
print("survived")
"""


def test_a_field_getter_that_tables_does_not_restart_the_depth():
    """Each re-entry through a dataclass field getter got a fresh MAX_DEPTH of
    C stack (todo case 3)."""
    rc, out, err = _child(_REENTRY)
    _ok(rc, out, err, {"survived"})


# ── 4. a partial list whose tail is bound to () or bytes ────────────────────

_KEYS = [("py", tabling._normalize_for_key_py)]
try:
    from clausal.logic._tabling_core import _normalize_for_key as _c_key
    _KEYS.append(("c", _c_key))
except ImportError:                       # the C twin is optional
    pass


@pytest.fixture(params=_KEYS, ids=[k for k, _ in _KEYS])
def key(request):
    return request.param[1]


@pytest.mark.parametrize("tail, closed", [
    ((), [1]),
    (b"", [1]),
    (b"ab", [1, 97, 98]),
    ([97, 98], [1, 97, 98]),
])
def test_a_partial_list_closed_by_nil_or_bytes_keys_as_the_closed_list(key, tail, closed):
    v = Var()
    assert unify(v, tail, Trail())
    assert key(SegList([ConcreteSeg([1]), VarSeg(v)])) == key(closed)


def test_a_hole_bound_to_bytes_walks_to_its_codes():
    from clausal.logic.variables import walk
    v = Var()
    assert unify(v, b"ab", Trail())
    assert walk(SegList([ConcreteSeg(["x"]), VarSeg(v)])) == ["x", 97, 98]


# ── hostile hash / eq and cyclic terms through a tabled predicate ────────────

_PL = """\
:- table(p/1).
p(_).
cyc(R) :- X = f(X), catch((p(X), R = ok), error(E, _), R = caught(E)).
cyclist(R) :- X = [a|X], catch((p(X), R = ok), error(E, _), R = caught(E)).
"""


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    p = tmp_path_factory.mktemp("tabhostile") / "tabhostile.clausal"
    p.write_text(_PL)
    return load_clausal_module(p)


class _BadHash:
    def __hash__(self):
        raise ValueError("no hash for you")


class _Unhashable:
    __hash__ = None


@pytest.mark.parametrize("obj, exc", [(_BadHash(), ValueError),
                                      (_Unhashable(), TypeError)])
def test_an_argument_that_cannot_hash_is_a_clear_error(mod, obj, exc):
    """The object's own exception, with a note naming the tabled call."""
    with pytest.raises(exc) as info:
        list(solve(("p", obj), mod))
    notes = "\n".join(getattr(info.value, "__notes__", []))
    assert "p/1" in notes and "tabled" in notes, notes


_CYCLIC = """
from clausal.logic.solve import solve
from clausal.logic.variables import Var, walk
from clausal.testing import load_clausal_module
import pathlib, sys
p = pathlib.Path(sys.argv[1])
p.write_text(%r)
m = load_clausal_module(p)
for name in ("cyc", "cyclist"):
    v = Var()
    for _ in solve((name, v), m):
        print(name, walk(v))
print("survived")
"""


def test_a_cyclic_tabled_argument_is_a_resource_error(tmp_path):
    """Scryer loops on it; here it is ISO resource_error(stack)."""
    src = _CYCLIC % _PL
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(sys.path))
    r = subprocess.run([sys.executable, "-c", src, str(tmp_path / "cyc.clausal")],
                       capture_output=True, text=True, timeout=300, env=env)
    assert r.returncode == 0, r.stderr[-2000:]
    lines = r.stdout.strip().splitlines()
    assert lines == ["cyc ('caught', ('resource_error', 'stack'))",
                     "cyclist ('caught', ('resource_error', 'stack'))",
                     "survived"], r.stdout


# ── the C walkers: a list mutated by Python code mid-walk ────────────────────

_CLEAR_MID_WALK = """
import dataclasses, gc
from clausal.logic import tabling
from clausal.logic.variables import walk, Var
from clausal.logic.builtins._helpers import _is_ground
from clausal.logic.variables._variables import _copy_term_impl, _collect_vars_impl
lst = []
class Getter:
    def __get__(self, obj, cls=None):
        if obj is None:
            return self
        lst.clear()
        gc.collect()
        return 1
@dataclasses.dataclass
class T:
    a: int
T.a = Getter()
walkers = [
    ("walk", walk),
    ("is_ground", _is_ground),
    ("copy_term", lambda t: _copy_term_impl(t, {})),
    ("collect_vars", lambda t: _collect_vars_impl(t, [])),
    ("key", tabling._normalize_for_key),
    ("freeze", lambda t: tabling.freeze_args((t,), None)),
]
for name, fn in walkers:
    lst[:] = [T.__new__(T)] + [[i, Var()] for i in range(200)]
    try:
        fn(lst)
    except Exception:
        pass
print("survived")
"""


def test_a_list_cleared_by_a_field_getter_mid_walk_does_not_crash():
    """The walkers looped over a cached size with borrowed items (the todo's
    last section)."""
    rc, out, err = _child(_CLEAR_MID_WALK, debug_malloc=True)
    _ok(rc, out, err, {"survived"})


# ── _head_list_unify_output and str subclasses (the todo's "also" items) ─────

_HEAD_LIST_TUPLES = """
from clausal.logic.runtime import list_unify
from clausal.logic.variables import Trail, Var
fn = list_unify._head_list_unify_output
for args in [((Var(),), None, []), ([Var()], None, (Var(),))]:
    try:
        fn(Var(), *args, Trail())
        print("accepted")
    except TypeError:
        print("TypeError")
"""


def test_head_list_unify_output_refuses_non_list_values():
    """Called directly with a tuple it read it as a list and segfaulted."""
    rc, out, err = _child(_HEAD_LIST_TUPLES)
    assert (rc, out.splitlines()) == (0, ["TypeError", "TypeError"]), (rc, out, err)


class _S(str):
    pass


def test_the_c_and_python_head_list_twins_agree_on_str_subclasses():
    from clausal.logic.cells import chars
    from clausal.logic.runtime import list_unify
    from clausal.logic.variables import deref
    twins = [list_unify._head_list_unify_output_py]
    if list_unify._head_list_unify_output is not list_unify._head_list_unify_output_py:
        twins.append(list_unify._head_list_unify_output)
    if len(twins) < 2:
        pytest.skip("C twin not built")
    got = []
    for fn in twins:
        t, a, s = Var(), Var(), Var()
        tr = Trail()
        assert unify(a, _S("a"), tr) and unify(s, chars("cd"), tr)
        assert fn(t, [a], s, [], tr)
        got.append(deref(t))
    assert type(got[0]) is type(got[1]) and got[0] == got[1], got
