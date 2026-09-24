"""W4b-3 class (a) conversions: the guards in front of ``_dispatch_at`` accept
a module-qualified predicate HANDLE, not only a ``PredicateMeta`` class.

The W4b-2d flip binds every predicate's module-dict name to
``mangle(module, name)`` instead of a class.  ``_dispatch_at`` already resolves
that shape; what broke were the SELECTORS in front of it, keyed on the class
shape (``hasattr(x, "_get_dispatch")``, ``isinstance(x, type)``).  After the
flip they select nothing, and the result is a silent fall-through, not an
error -- see ``implementation_plans/w4b3-dispatch-at-raw-class-audit-2026-09-24.md``
section 7.  Each test below binds (or hands over) the post-flip shape for a
really loaded module and requires the same answer the class gives today; each
also pins that the class binding still answers (the population is not empty)
and that a mangled DATA atom (``-hide``) is still not taken for a handle --
the reason the accessor is ``is_declared_predicate_name``, never
``is_mangled``.
"""
from __future__ import annotations

import itertools
import sys

import pytest

from clausal.import_hook import _load_module
from clausal.logic.atoms import is_mangled, mangle, mint
from clausal.logic.predicate import PredicateMeta, is_declared_predicate_name
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.predicate_diagnostics import PredicateArityMismatchError


_SRC = """\
-module({name}, [])
-hide([secret])
is_pos(X) <- (X > 0)
key(1, 10),
key(2, 20),
key(-1, 5),
pos_t(1, True),
pos_t(2, True),
pos_t(-1, False),
step(1, 0, 1),
step(2, 1, 3),
step(-1, 3, 2),
last(1, 1),
holds(secret),
greeting >> (["hi"])
go <- is_pos(3)
"""

_counter = itertools.count()


@pytest.fixture
def lm(tmp_path):
    """A really loaded module (in ``sys.modules``, so a handle naming it
    resolves), under a fresh name per test."""
    name = f"w4b3dg_{next(_counter)}"
    p = tmp_path / f"{name}.clausal"
    p.write_text(_SRC.format(name=name))
    mod = _load_module(name, str(p))
    assert sys.modules[name] is mod
    try:
        yield mod.__dict__["$module"]
    finally:
        sys.modules.pop(name, None)


def _handle(lm, name):
    """The post-flip binding for *name*, checked to BE that shape."""
    h = mangle(lm.name, name)
    assert type(h) is str and is_mangled(h)
    assert is_declared_predicate_name(h), f"{name} must resolve as a handle"
    return h


def _both(lm, name):
    """(class binding today, handle binding post-flip), with the class
    checked to be a class -- so the 'today' arm really is the class arm."""
    cls = lm.module_dict[name]
    assert isinstance(cls, PredicateMeta)
    return cls, _handle(lm, name)


def _secret(lm):
    """A mangled DATA atom: mangled, but NOT a predicate handle."""
    s = mangle(lm.name, "secret")
    assert is_mangled(s) and not is_declared_predicate_name(s)
    return s


def _answers(functor, args, lm, out_vars):
    """Every solution's bindings of *out_vars*, deref'd."""
    return [tuple(deref(v) for v in out_vars)
            for _ in call(functor, *args, module=lm)]


# ── 1. solve.call() Phase 5 ─────────────────────────────────────────────────


class TestSolveCallPhase5:
    """``call(name, ...)`` looks the name up in the module dict.  Unconverted,
    a handle binding skips Phase 5, and Phase 6 hands the call to a same-named
    BUILTIN."""

    def test_user_last_answers_not_the_builtin(self, lm, monkeypatch):
        # today: the user's last/2 (one fact, last(1, 1)) answers
        assert len(list(call("last", 1, 1, module=lm))) == 1
        assert len(list(call("last", [5], 5, module=lm))) == 0
        _, h = _both(lm, "last")
        monkeypatch.setitem(lm.module_dict, "last", h)
        assert len(list(call("last", 1, 1, module=lm))) == 1
        # the builtin would say yes here; the user predicate says no
        assert len(list(call("last", [5], 5, module=lm))) == 0

    def test_ordinary_predicate_same_answer(self, lm, monkeypatch):
        assert len(list(call("is_pos", 3, module=lm))) == 1
        _, h = _both(lm, "is_pos")
        monkeypatch.setitem(lm.module_dict, "is_pos", h)
        assert len(list(call("is_pos", 3, module=lm))) == 1
        assert len(list(call("is_pos", -3, module=lm))) == 0

    def test_wrong_arity_still_refuses(self, lm, monkeypatch):
        with pytest.raises(PredicateArityMismatchError):
            list(call("is_pos", 1, 2, module=lm))
        _, h = _both(lm, "is_pos")
        monkeypatch.setitem(lm.module_dict, "is_pos", h)
        # unconverted: KeyError "not defined in module"
        with pytest.raises(PredicateArityMismatchError):
            list(call("is_pos", 1, 2, module=lm))


# ── 2. phrase/2,3 ───────────────────────────────────────────────────────────


class TestPhrase:
    """Unconverted, a handle rule reaches ``_resolve_nonterminal``, which
    answers None for an atom: phrase fails silently."""

    @pytest.mark.parametrize("which", ["class", "handle"])
    def test_phrase_2(self, lm, which):
        cls, h = _both(lm, "greeting")
        rule = cls if which == "class" else h
        assert len(list(call("phrase", rule, [mint("hi")], module=lm))) == 1
        assert len(list(call("phrase", rule, [mint("bye")], module=lm))) == 0

    @pytest.mark.parametrize("which", ["class", "handle"])
    def test_phrase_3(self, lm, which):
        cls, h = _both(lm, "greeting")
        rule = cls if which == "class" else h
        rest = Var()
        got = _answers("phrase", (rule, [mint("hi"), mint("x")], rest), lm, [rest])
        assert got == [([mint("x")],)]

    def test_a_data_atom_is_still_not_a_rule(self, lm):
        assert list(call("phrase", _secret(lm), [mint("hi")], module=lm)) == []


# ── 3. the 16 list builtins, time_goal, _ensure_trampoline_dispatch ─────────


L = [1, 2, -1]

# (builtin, goal predicate, input args, number of trailing output vars)
_LIST_CASES = [
    ("maplist", "is_pos", ([1, 2],), 0),
    ("maplist", "key", ([1, 2],), 1),
    ("include", "is_pos", (L,), 1),
    ("exclude", "is_pos", (L,), 1),
    ("foldl", "step", (L, 0), 1),
    ("take_while", "is_pos", (L,), 1),
    ("drop_while", "is_pos", (L,), 1),
    ("span", "is_pos", (L,), 2),
    ("group_by", "key", (L,), 1),
    ("sort_by", "key", (L,), 1),
    ("max_by", "key", (L,), 1),
    ("min_by", "key", (L,), 1),
    ("filter_map", "key", (L,), 1),
    ("partition", "is_pos", (L,), 2),
    ("tfilter", "pos_t", (L,), 1),
    ("tpartition", "pos_t", (L,), 2),
]


def test_the_list_case_table_covers_all_sixteen_builtins():
    """Positive control on the population: 16 distinct builtin/arity pairs,
    each a registered builtin."""
    from clausal.logic.builtins._registry import _BUILTINS
    keys = {(b, 1 + len(a) + n) for b, _, a, n in _LIST_CASES}
    assert len(keys) == 16
    assert keys <= set(_BUILTINS), keys - set(_BUILTINS)


@pytest.mark.parametrize(
    "builtin,goal,inputs,n_out", _LIST_CASES,
    ids=[f"{b}/{1 + len(a) + n}" for b, _, a, n in _LIST_CASES])
def test_list_builtin_answers_the_same_for_a_handle(lm, builtin, goal, inputs, n_out):
    cls, h = _both(lm, goal)
    outs = [Var() for _ in range(n_out)]
    today = _answers(builtin, (cls, *inputs, *outs), lm, outs)
    assert len(today) >= 1, "the class arm must answer, or the comparison is vacuous"
    outs = [Var() for _ in range(n_out)]
    assert _answers(builtin, (h, *inputs, *outs), lm, outs) == today


def test_a_data_atom_is_still_not_a_list_goal(lm):
    """``-hide``'s mangled DATA atom keeps failing quietly; widening on
    ``is_mangled`` would raise existence_error here instead."""
    assert list(call("maplist", _secret(lm), [1], module=lm)) == []


@pytest.mark.parametrize("which", ["class", "handle"])
def test_time_goal_runs_a_handle(lm, which, capsys):
    cls, h = _both(lm, "go")
    goal = cls if which == "class" else h
    assert len(list(call("time_goal", goal, module=lm))) == 1
    capsys.readouterr()   # time_goal's timing line


@pytest.mark.parametrize("which", ["class", "handle"])
def test_time_goal_wrong_arity_still_refuses(lm, which):
    """greeting is arity 2 (a nonterminal); time_goal calls it at 0."""
    cls, h = _both(lm, "greeting")
    goal = cls if which == "class" else h
    with pytest.raises(PredicateArityMismatchError):
        list(call("time_goal", goal, module=lm))


def test_ensure_trampoline_dispatch_resolves_a_handle(lm):
    from clausal.logic.builtins._registry import _ensure_trampoline_dispatch
    cls, h = _both(lm, "is_pos")
    assert _ensure_trampoline_dispatch(h, 1) is _ensure_trampoline_dispatch(cls, 1)


def test_ensure_trampoline_dispatch_refuses_a_handle_without_an_arity(lm):
    """A handle has no arity of its own to resolve at: loud, not a
    simple-mode wrapper around a str."""
    from clausal.logic.builtins._registry import _ensure_trampoline_dispatch
    with pytest.raises(TypeError, match="arity"):
        _ensure_trampoline_dispatch(_handle(lm, "is_pos"))


# ── 4. compile-time: globals_env._inject_resolved_targets ───────────────────


class TestInjectResolvedTargets:
    """What a compiled ``$dispatch_at(fname, N)`` receives is fixed at compile
    time from the module's globals.  Patching ``module_dict`` after load does
    not reach already-compiled code, so this drives the resolver directly with
    a flipped ``globals_`` -- exactly what ``compile_predicate`` hands it
    (``base_globals.update(globals_)`` first)."""

    @staticmethod
    def _inject(lm, targets, flip=()):
        from clausal.logic.compiler.globals_env import _inject_resolved_targets
        globals_ = dict(lm.module_dict)
        for name in flip:
            globals_[name] = _handle(lm, name)
        base_globals = dict(globals_)
        _inject_resolved_targets(set(targets), base_globals, lm.db, globals_)
        return base_globals

    @pytest.mark.parametrize("flip", [(), ("last",)], ids=["class", "handle"])
    def test_user_predicate_not_the_same_named_builtin(self, lm, flip):
        from clausal.logic.builtins import BuiltinPredicate
        from clausal.logic.predicate import _dispatch_at
        from clausal.logic.solve import _drive_trampoline
        from clausal.logic.variables import Trail
        bg = self._inject(lm, {("last", 2)}, flip)
        target = bg["last"]
        assert not isinstance(target, BuiltinPredicate)
        assert target is (_handle(lm, "last") if flip else lm.module_dict["last"])
        fn = _dispatch_at(target, 2)
        assert len(list(_drive_trampoline(fn, Trail(), 1, 1))) == 1
        assert len(list(_drive_trampoline(fn, Trail(), [5], 5))) == 0

    @pytest.mark.parametrize("flip", [(), ("key",)], ids=["class", "handle"])
    def test_locked_local_predicate_keeps_its_cached_dispatch(self, lm, flip):
        from clausal.logic.compiler.globals_env import _disp_key
        list(call("key", 1, Var(), module=lm))   # compile it
        row = lm.db.row("key", 2)
        assert row is not None and row.locked and row.dispatch_fn is not None
        bg = self._inject(lm, {("key", 2)}, flip)
        assert bg.get(_disp_key("key", 2)) is row.dispatch_fn
