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

Handle era (W4b-2d flip): the LOAD binds the handle now, so every
``[class]`` arm is gone (after the flip it silently ran the handle again),
and every stand-in that re-bound a name to its handle (``monkeypatch.setitem``
of the handle, ``_inject(flip=...)``, the specializer's ``md[n] = handle``)
became an assertion that the binding already IS the handle.  Where a test
compared the handle's answer with the class's, the class's answer is pinned
(captured under ``CLAUSAL_NO_FLIP=1`` on 9e6c2633).  The ``stale`` fixture's
hand-built stale CLASS is gone with the class; its module keeps both rows.
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
ping(1, 2),
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


_OWNER_SRC = """\
-module({name}, [])
ping <- (1 > 0)
last(1),
"""


@pytest.fixture
def owner(tmp_path):
    """A second loaded module defining ``ping/0`` and ``last/1`` -- names the
    ``lm`` module (or a builtin) owns at a DIFFERENT arity."""
    name = f"w4b3own_{next(_counter)}"
    p = tmp_path / f"{name}.clausal"
    p.write_text(_OWNER_SRC.format(name=name))
    mod = _load_module(name, str(p))
    try:
        yield mod.__dict__["$module"]
    finally:
        sys.modules.pop(name, None)


_STALE_SRC = """\
-module({name}, [])
last <- (1 > 0)
"""


@pytest.fixture
def stale(tmp_path):
    """A module whose ``last`` is authored as ``last/0``, then a real
    ``assertz(last(1, 1))`` adds a ``last/2`` row.  ``last/2`` is also a
    BUILTIN, so a lookup that trusts the authored arity hands the module's
    own predicate to the builtin.  (Class era: the class was then hand-bound
    to the ``last/2`` row to make its ``_fields`` STALE.  Handle era: there
    is no class to go stale; the binding is the handle, which names both
    rows.)"""
    from clausal.terms import Compound
    name = f"w4b3stale_{next(_counter)}"
    p = tmp_path / f"{name}.clausal"
    p.write_text(_STALE_SRC.format(name=name))
    mod = _load_module(name, str(p))
    m = mod.__dict__["$module"]
    try:
        assert len(list(call("assertz", Compound("last", (1, 1)), module=m))) == 1
        assert m.module_dict["last"] == mangle(m.name, "last")
        assert m.db.row("last", 0) is not None
        assert len(m.db.row("last", 2).clauses) == 1
        yield m
    finally:
        sys.modules.pop(name, None)


def _site_dispatch(base_globals, name, arity):
    """What a compiled call site ``name/arity`` dispatches through, exactly as
    the goal emitters choose it: the ``$disp_name_N`` entry when the resolver
    left one, else ``$dispatch_at(base_globals[name], N)``."""
    from clausal.logic.compiler.globals_env import _disp_key
    from clausal.logic.predicate import _dispatch_at
    fn = base_globals.get(_disp_key(name, arity))
    return fn if fn is not None else _dispatch_at(base_globals[name], arity)


def _handle(lm, name):
    """The post-flip binding for *name*, checked to BE that shape."""
    h = mangle(lm.name, name)
    assert type(h) is str and is_mangled(h)
    assert is_declared_predicate_name(h), f"{name} must resolve as a handle"
    return h


def _bound_handle(lm, name):
    """The module-dict binding for *name*, checked to be the handle the LOAD
    bound (never set here)."""
    h = _handle(lm, name)
    assert lm.module_dict[name] == h, f"the load did not bind {name}'s handle"
    return lm.module_dict[name]


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
        _bound_handle(lm, "last")
        assert len(list(call("last", 1, 1, module=lm))) == 1
        # the builtin would say yes here; the user predicate says no
        assert len(list(call("last", [5], 5, module=lm))) == 0

    def test_ordinary_predicate_same_answer(self, lm, monkeypatch):
        assert len(list(call("is_pos", 3, module=lm))) == 1
        _bound_handle(lm, "is_pos")
        assert len(list(call("is_pos", 3, module=lm))) == 1
        assert len(list(call("is_pos", -3, module=lm))) == 0

    # -- a predicate name is name + ARITY (operator ruling, 2026-09-24) ------
    #
    # A binding (class or handle) at ANOTHER arity -- or, for an IMPORTED one,
    # at an arity it was not imported at -- is not this call's target.  The
    # call resolves in THIS module under THIS name: its own row first, then a
    # builtin under the name.  When neither answers the call REFUSES naming
    # the name used; it never resolves the other arity in the binding's owner
    # (aliased-import ruling, 2026-09-24).  ``test_wrong_arity_still_refuses``
    # below pins the refusal.  The class-era refusal ahead of a live answer
    # was an artefact of the predicate being a class.

    @pytest.mark.parametrize("era", ["handle"])  # the class era is gone
    def test_a_builtin_answers_at_another_arity(self, lm, owner, monkeypatch,
                                                 era):
        """``owner`` has a user ``last/1``; ``call("last", L, X)`` is
        ``last/2`` and reaches the builtin."""
        b = TestInjectResolvedTargets._owner_binding(owner, "last", era)
        assert len(list(call("last", 1, module=owner))) == 1   # last/1 is live
        assert owner.module_dict["last"] is b
        x = Var()
        assert _answers("last", ([4, 5], x), owner, [x]) == [(5,)]
        # and last/1 is still the user's
        assert len(list(call("last", 1, module=owner))) == 1
        assert len(list(call("last", 2, module=owner))) == 0

    @pytest.mark.parametrize("era", ["handle"])  # the class era is gone
    def test_the_local_row_answers_at_another_arity(self, lm, owner,
                                                     monkeypatch, era):
        """``lm`` binds ``ping`` to ``owner``'s ``ping/0``; ``lm``'s own
        ``ping/2`` answers ``call("ping", 1, 2)``."""
        assert lm.db.row("ping", 2) is not None
        b = TestInjectResolvedTargets._owner_binding(owner, "ping", era)
        monkeypatch.setitem(lm.module_dict, "ping", b)
        assert len(list(call("ping", 1, 2, module=lm))) == 1
        assert len(list(call("ping", 1, 3, module=lm))) == 0

    @pytest.mark.parametrize("era", ["handle"])  # the class era is gone
    def test_the_local_row_beats_a_builtin_at_another_arity(
            self, lm, owner, monkeypatch, era):
        """Review round: ``lm`` binds ``last`` to ``owner``'s ``last/1`` and
        has its OWN ``last/2``, which shares the builtin's name and arity.
        The local predicate answers, not the builtin: ``last([5], 5)`` is
        false for ``lm``'s one fact ``last(1, 1)``."""
        b = TestInjectResolvedTargets._owner_binding(owner, "last", era)
        monkeypatch.setitem(lm.module_dict, "last", b)
        assert len(list(call("last", 1, 1, module=lm))) == 1
        assert len(list(call("last", [5], 5, module=lm))) == 0

    @pytest.mark.parametrize("era", ["handle"])  # the class era is gone
    def test_a_stale_fields_class_keeps_its_local_predicate(
            self, stale, monkeypatch, era):
        """Review round: the ``last`` class says ``/0`` but its clauses are
        ``/2``.  ``call("last", A, B)`` must reach the module's own ``last/2``,
        not the builtin ``last/2`` -- both eras (the handle is not stale)."""
        assert stale.module_dict["last"] == _handle(stale, "last")
        assert len(list(call("last", 1, 1, module=stale))) == 1
        assert len(list(call("last", [5], 5, module=stale))) == 0
        assert len(list(call("last", module=stale))) == 1       # last/0

    def test_wrong_arity_still_refuses(self, lm, monkeypatch):
        with pytest.raises(PredicateArityMismatchError):
            list(call("is_pos", 1, 2, module=lm))
        _bound_handle(lm, "is_pos")
        # unconverted: KeyError "not defined in module"
        with pytest.raises(PredicateArityMismatchError):
            list(call("is_pos", 1, 2, module=lm))


# ── 2. phrase/2,3 ───────────────────────────────────────────────────────────


class TestPhrase:
    """Unconverted, a handle rule reaches ``_resolve_nonterminal``, which
    answers None for an atom: phrase fails silently."""

    @pytest.mark.parametrize("which", ["handle"])  # the class era is gone
    def test_phrase_2(self, lm, which):
        rule = _bound_handle(lm, "greeting")
        assert len(list(call("phrase", rule, [mint("hi")], module=lm))) == 1
        assert len(list(call("phrase", rule, [mint("bye")], module=lm))) == 0

    @pytest.mark.parametrize("which", ["handle"])  # the class era is gone
    def test_phrase_3(self, lm, which):
        rule = _bound_handle(lm, "greeting")
        rest = Var()
        got = _answers("phrase", (rule, [mint("hi"), mint("x")], rest), lm, [rest])
        assert got == [([mint("x")],)]

    @pytest.mark.parametrize("which", ["handle"])  # the class era is gone
    def test_phrase_2_wrong_arity_refuses(self, lm, which):
        """``is_pos/1`` used as a nonterminal is called at 2 (S0, S): the
        refusal names the arity, in both eras."""
        rule = _bound_handle(lm, "is_pos")
        with pytest.raises(PredicateArityMismatchError):
            list(call("phrase", rule, [mint("hi")], module=lm))

    def test_a_data_atom_is_still_not_a_rule(self, lm):
        """FLIPPED 2026-09-25 -- operator ruling 2 ("like Scryer"): a
        ``-hide`` DATA atom names no nonterminal, and an unknown procedure
        now raises ``existence_error(procedure, secret/2)`` -- demangled --
        where it used to fail silently."""
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException) as exc:
            list(call("phrase", _secret(lm), [mint("hi")], module=lm))
        assert tuple(exc.value.term.args[0].args[1].args) == ("secret", 2)


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


# What each list builtin answered for the CLASS binding (CLAUSAL_NO_FLIP=1,
# 9e6c2633) -- the comparison the class arm used to make live.
_CLASS_ERA_LIST_ANSWERS = {
    'maplist/2': [()],
    'maplist/3': [([10, 20],)],
    'include/3': [([1, 2],)],
    'exclude/3': [([-1],)],
    'foldl/4': [(2,)],
    'take_while/3': [([1, 2],)],
    'drop_while/3': [([-1],)],
    'span/4': [([1, 2], [-1])],
    'group_by/3': [([[1], [2], [-1]],)],
    'sort_by/3': [([-1, 1, 2],)],
    'max_by/3': [(2,)],
    'min_by/3': [(-1,)],
    'filter_map/3': [([10, 20, 5],)],
    'partition/4': [([1, 2], [-1])],
    'tfilter/3': [([1, 2],)],
    'tpartition/4': [([1, 2], [-1])],
}


def test_the_list_case_table_covers_all_sixteen_builtins():
    """Positive control on the population: 16 distinct builtin/arity pairs,
    each a registered builtin.  Since the aliased-import ruling (2026-09-24)
    they are db-receiving (``_DB_BUILTINS``, ``_db_optional``): the caller's
    database is what says which unqualified name a goal arrived under."""
    from clausal.logic.builtins._registry import _BUILTINS, _DB_BUILTINS
    from clausal.logic.builtins.higher_order import _GOAL_FIRST_LIST_BUILTINS
    keys = {(b, 1 + len(a) + n) for b, _, a, n in _LIST_CASES}
    assert len(keys) == 16
    assert keys == set(_GOAL_FIRST_LIST_BUILTINS)
    assert keys <= set(_DB_BUILTINS), keys - set(_DB_BUILTINS)
    assert not keys & set(_BUILTINS)
    assert all(getattr(_DB_BUILTINS[k], "_db_optional", False) for k in keys)


@pytest.mark.parametrize(
    "builtin,goal,inputs,n_out", _LIST_CASES,
    ids=[f"{b}/{1 + len(a) + n}" for b, _, a, n in _LIST_CASES])
def test_list_builtin_answers_the_same_for_a_handle(lm, builtin, goal, inputs, n_out):
    h = _bound_handle(lm, goal)
    today = _CLASS_ERA_LIST_ANSWERS[f"{builtin}/{1 + len(inputs) + n_out}"]
    assert len(today) >= 1, "the class answer must be non-empty, or the comparison is vacuous"
    outs = [Var() for _ in range(n_out)]
    assert _answers(builtin, (h, *inputs, *outs), lm, outs) == today


def test_the_pinned_class_answers_cover_every_list_case():
    """Positive control on the pinned population: one answer per case."""
    keys = {f"{b}/{1 + len(a) + n}" for b, _, a, n in _LIST_CASES}
    assert len(keys) == 16 and keys == set(_CLASS_ERA_LIST_ANSWERS)


def test_a_data_atom_is_still_not_a_list_goal(lm):
    """``-hide``'s mangled DATA atom names no procedure.  FLIPPED
    2026-09-25 -- operator ruling 2 ("like Scryer"): it used to fail
    quietly; an unknown procedure in a meta-call now raises
    ``existence_error(procedure, secret/1)``, demangled (no ``\\x1f`` in
    the catchable term)."""
    from clausal.logic.exceptions import LogicException
    with pytest.raises(LogicException) as exc:
        list(call("maplist", _secret(lm), [1], module=lm))
    assert tuple(exc.value.term.args[0].args[1].args) == ("secret", 1)


@pytest.mark.parametrize("which", ["handle"])  # the class era is gone
def test_time_goal_runs_a_handle(lm, which, capsys):
    goal = _bound_handle(lm, "go")
    assert len(list(call("time_goal", goal, module=lm))) == 1
    capsys.readouterr()   # time_goal's timing line


@pytest.mark.parametrize("which", ["handle"])  # the class era is gone
def test_time_goal_wrong_arity_still_refuses(lm, which):
    """greeting is arity 2 (a nonterminal); time_goal calls it at 0."""
    goal = _bound_handle(lm, "greeting")
    with pytest.raises(PredicateArityMismatchError):
        list(call("time_goal", goal, module=lm))


def test_ensure_trampoline_dispatch_resolves_a_handle(lm):
    from clausal.logic.builtins._registry import _ensure_trampoline_dispatch
    from clausal.logic.solve import _drive_trampoline
    from clausal.logic.variables import Trail
    h = _bound_handle(lm, "is_pos")
    fn = _ensure_trampoline_dispatch(h, 1)
    # the class era's answer was the row's own dispatch (CLAUSAL_NO_FLIP=1)
    assert fn is lm.db.get_dispatch("is_pos", 1) is lm.db.row("is_pos", 1).dispatch_fn
    assert len(list(_drive_trampoline(fn, Trail(), 3))) == 1
    assert len(list(_drive_trampoline(fn, Trail(), -3))) == 0


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
        """*flip* names the bindings the test relies on being handles; they
        are ASSERTED (the load flipped them), never set here."""
        from clausal.logic.compiler.globals_env import _inject_resolved_targets
        globals_ = dict(lm.module_dict)
        for name in flip:
            assert globals_[name] == _handle(lm, name), name
        base_globals = dict(globals_)
        _inject_resolved_targets(set(targets), base_globals, lm.db, globals_)
        return base_globals

    @pytest.mark.parametrize("flip", [("last",)], ids=["handle"])
    def test_user_predicate_not_the_same_named_builtin(self, lm, flip):
        from clausal.logic.builtins import BuiltinPredicate
        from clausal.logic.predicate import _dispatch_at
        from clausal.logic.solve import _drive_trampoline
        from clausal.logic.variables import Trail
        bg = self._inject(lm, {("last", 2)}, flip)
        target = bg["last"]
        assert not isinstance(target, BuiltinPredicate)
        assert target is lm.module_dict["last"]
        assert target == _handle(lm, "last")
        fn = _dispatch_at(target, 2)
        assert len(list(_drive_trampoline(fn, Trail(), 1, 1))) == 1
        assert len(list(_drive_trampoline(fn, Trail(), [5], 5))) == 0

    @pytest.mark.parametrize("flip", [("key",)], ids=["handle"])
    def test_locked_local_predicate_keeps_its_cached_dispatch(self, lm, flip):
        from clausal.logic.compiler.globals_env import _disp_key
        list(call("key", 1, Var(), module=lm))   # compile it
        row = lm.db.row("key", 2)
        assert row is not None and row.locked and row.dispatch_fn is not None
        bg = self._inject(lm, {("key", 2)}, flip)
        assert bg.get(_disp_key("key", 2)) is row.dispatch_fn

    # -- a predicate name is name + ARITY (operator ruling, 2026-09-24) ------
    #
    # An applied target takes a predicate binding -- class or handle alike --
    # only at its own arity (for an import: an arity it was imported at).  At
    # another arity the call resolves in this module under this name: this
    # db's own row, then a builtin under the name.  When nothing answers, the
    # binding is kept under the name (term construction, its own arity) and
    # the call site gets a ``$disp_`` entry that refuses naming the name --
    # never the owner (aliased-import ruling, 2026-09-24).  A DOTTED name is
    # the qualifier's and still resolves there.  The class-era
    # PredicateArityMismatchError was an artefact of the predicate being a
    # class.

    @staticmethod
    def _owner_binding(owner, name, era):
        """*owner*'s binding for *name*: the handle its load bound."""
        h = owner.module_dict[name]
        assert h == mangle(owner.name, name), "the load did not bind the handle"
        assert is_declared_predicate_name(h)
        return h

    @pytest.mark.parametrize("era", ["handle"])  # the class era is gone
    def test_a_local_predicate_beats_an_owner_binding_at_another_arity(
            self, lm, owner, era):
        from clausal.logic.compiler.globals_env import (
            _disp_key, _inject_resolved_targets,
        )
        from clausal.logic.predicate import _dispatch_at, is_declared_predicate
        from clausal.logic.solve import _drive_trampoline
        from clausal.logic.variables import Trail
        b = self._owner_binding(owner, "ping", era)
        assert is_declared_predicate(b, arity=0)          # the owner has ping/0
        assert not is_declared_predicate(b, arity=2)
        assert lm.db.row("ping", 2) is not None           # the local has ping/2
        globals_ = dict(lm.module_dict)
        globals_["ping"] = b
        base_globals = dict(globals_)
        _inject_resolved_targets({("ping", 2)}, base_globals, lm.db, globals_)
        # round 4: the NAME key keeps the binding; the /2 call site gets its
        # own $disp_ entry, which reaches the local row.
        assert base_globals["ping"] is b
        fn = base_globals[_disp_key("ping", 2)]
        assert len(list(_drive_trampoline(fn, Trail(), 1, 2))) == 1

    @pytest.mark.parametrize("era", ["handle"])  # the class era is gone
    def test_a_local_row_beats_a_builtin_at_another_arity(self, lm, owner, era):
        """Review round: ``lm`` has its own ``last/2``; the binding is
        ``owner``'s ``last/1``.  The local row wins AHEAD of the builtin
        ``last/2`` -- the same order ``solve.call`` uses at run time."""
        from clausal.logic.compiler.globals_env import _inject_resolved_targets
        from clausal.logic.solve import _drive_trampoline
        from clausal.logic.variables import Trail
        b = self._owner_binding(owner, "last", era)
        assert lm.db.row("last", 2) is not None
        globals_ = dict(lm.module_dict)
        globals_["last"] = b
        base_globals = dict(globals_)
        _inject_resolved_targets({("last", 2)}, base_globals, lm.db, globals_)
        assert base_globals["last"] is b                 # round 4: name kept
        fn = _site_dispatch(base_globals, "last", 2)
        assert len(list(_drive_trampoline(fn, Trail(), 1, 1))) == 1
        assert len(list(_drive_trampoline(fn, Trail(), [5], 5))) == 0

    @pytest.mark.parametrize("order", ["1-then-2", "2-then-1"])
    @pytest.mark.parametrize("era", ["handle"])  # the class era is gone
    def test_one_clause_set_using_the_name_at_two_arities_and_as_a_term(
            self, lm, owner, era, order):
        """Roborev round 4 (MEDIUM): one clause set with

            p(X) <- last(X)            # the imported last/1 (owner's)
            q(A, B) <- last(A, B)      # lm's own last/2
            r(T) <- (T = last(1))      # a last/1 TERM

        shares one globals dict, so the resolver sees ``("last", 1)``,
        ``("last", 2)`` and the data reference ``("last", -1)`` together.
        The /2 target used to OVERWRITE the ``last`` key with a
        ``_DbDispatchAdapter`` -- arity-blind, NameError on construction --
        so, depending on which target the set yielded first, /1 calls got
        the /2 dispatch and building ``last(1)`` raised.  The name key must
        keep the binding in BOTH orders, each call site must reach its own
        predicate, and the term must still build.  (A file cannot declare
        this shape -- importing ``last`` and defining ``last/2`` is refused
        at load -- so the resolver is driven directly, with the order
        forced.)"""
        from clausal.logic.compiler.globals_env import _inject_resolved_targets
        from clausal.logic.solve import _drive_trampoline
        from clausal.logic.variables import Trail
        b = self._owner_binding(owner, "last", era)          # owner's last/1
        assert lm.db.row("last", 2) is not None              # lm's last/2
        targets = [("last", 1), ("last", 2), ("last", -1)]
        if order == "2-then-1":
            targets = [("last", 2), ("last", 1), ("last", -1)]
        globals_ = dict(lm.module_dict)
        globals_["last"] = b
        base_globals = dict(globals_)
        _inject_resolved_targets(targets, base_globals, lm.db, globals_)
        assert base_globals["last"] is b
        # p: last/1 is the owner's fact last(1)
        f1 = _site_dispatch(base_globals, "last", 1)
        assert len(list(_drive_trampoline(f1, Trail(), 1))) == 1
        assert len(list(_drive_trampoline(f1, Trail(), 2))) == 0
        # q: last/2 is lm's fact last(1, 1), not the builtin
        f2 = _site_dispatch(base_globals, "last", 2)
        assert len(list(_drive_trampoline(f2, Trail(), 1, 1))) == 1
        assert len(list(_drive_trampoline(f2, Trail(), [5], 5))) == 0
        # r: the term last(1) still builds from the name key: the key is the
        # handle, unchanged (the class era called the class to build it)

    @pytest.mark.parametrize("era", ["handle"])  # the class era is gone
    def test_a_stale_fields_class_is_not_shadowed_by_a_builtin(
            self, stale, era):
        """Review round: compile-time twin of the ``solve.call`` stale test.
        The class's ``_fields`` say ``/0``, its row is ``/2``; the call site
        ``last/2`` must compile to the module's own predicate."""
        from clausal.logic.builtins import BuiltinPredicate
        from clausal.logic.compiler.globals_env import _inject_resolved_targets
        from clausal.logic.predicate import _dispatch_at
        from clausal.logic.solve import _drive_trampoline
        from clausal.logic.variables import Trail
        globals_ = dict(stale.module_dict)
        assert globals_["last"] == _handle(stale, "last")
        base_globals = dict(globals_)
        _inject_resolved_targets({("last", 2)}, base_globals, stale.db, globals_)
        assert base_globals["last"] is globals_["last"]  # round 4: name kept
        fn = _site_dispatch(base_globals, "last", 2)
        assert len(list(_drive_trampoline(fn, Trail(), 1, 1))) == 1
        assert len(list(_drive_trampoline(fn, Trail(), [5], 5))) == 0

    @pytest.mark.parametrize("era", ["handle"])  # the class era is gone
    def test_a_builtin_beats_a_binding_at_another_arity(self, lm, owner, era):
        from clausal.logic.builtins import BuiltinPredicate
        from clausal.logic.compiler.globals_env import _inject_resolved_targets
        from clausal.logic.predicate import _dispatch_at, is_declared_predicate
        from clausal.logic.solve import _drive_trampoline
        from clausal.logic.variables import Trail
        b = self._owner_binding(owner, "last", era)
        assert is_declared_predicate(b, arity=1)          # owner has last/1
        globals_ = {"last": b}                            # no local last/2
        base_globals = dict(globals_)
        _inject_resolved_targets({("last", 2)}, base_globals, owner.db, globals_)
        # round 4: the name key keeps the binding (never a merged builtin);
        # the /2 call site answers as the builtin last/2 does
        assert base_globals["last"] is b
        fn = _site_dispatch(base_globals, "last", 2)
        assert len(list(_drive_trampoline(fn, Trail(), [4, 5], 5))) == 1
        assert len(list(_drive_trampoline(fn, Trail(), [4, 5], 4))) == 0

    @pytest.mark.parametrize("era", ["handle"])  # the class era is gone
    def test_the_other_arity_entry_caches_only_what_cannot_go_stale(
            self, lm, owner, monkeypatch, era):
        """Review round 5 (LOW 1): the ``$disp_`` entry resolves once and
        keeps the answer when it is a BUILTIN or a LOCKED row; an UNLOCKED
        row re-resolves on every call (it may be recompiled or retracted)."""
        from clausal.logic.compiler.globals_env import (
            _disp_key, _inject_resolved_targets,
        )
        from clausal.logic.solve import _drive_trampoline
        from clausal.logic.variables import Trail
        b = self._owner_binding(owner, "last", era)

        def entry(db):
            globals_ = {"last": b}
            bg = dict(globals_)
            _inject_resolved_targets({("last", 2)}, bg, db, globals_)
            return bg[_disp_key("last", 2)]

        def counting(db):
            calls = []
            real = db.get_dispatch
            monkeypatch.setattr(db, "get_dispatch",
                                lambda f, a: calls.append((f, a)) or real(f, a))
            return calls

        # a builtin (owner has no last/2 row): resolved once
        fn = entry(owner.db)
        calls = counting(owner.db)
        for _ in range(3):
            assert len(list(_drive_trampoline(fn, Trail(), [4, 5], 5))) == 1
        assert calls == [("last", 2)]
        # lm's own last/2, LOCKED: resolved once
        row = lm.db.row("last", 2)
        list(call("last", 1, 1, module=lm))            # compile + lock it
        assert row.locked
        fn = entry(lm.db)
        calls = counting(lm.db)
        for _ in range(3):
            assert len(list(_drive_trampoline(fn, Trail(), 1, 1))) == 1
        assert calls == [("last", 2)]
        # the same row UNLOCKED: re-resolved every call
        monkeypatch.setattr(row, "locked", False)
        fn = entry(lm.db)
        calls.clear()
        for _ in range(3):
            assert len(list(_drive_trampoline(fn, Trail(), 1, 1))) == 1
        assert calls == [("last", 2)] * 3

    @pytest.mark.parametrize("era", ["handle"])  # the class era is gone
    def test_a_local_row_asserted_after_the_first_call_outranks_the_cached_builtin(
            self, owner, era):
        """Round 6 (LOW 1): the entry cached the builtin ``last/2`` on its
        first call; a later ``assertz`` creates the module's OWN ``last/2``
        row, which must then answer -- as ``solve.call`` already does -- not
        the cached builtin."""
        from clausal.logic.compiler.globals_env import (
            _disp_key, _inject_resolved_targets,
        )
        from clausal.logic.solve import _drive_trampoline
        from clausal.logic.variables import Trail
        from clausal.terms import Compound
        b = self._owner_binding(owner, "last", era)
        globals_ = {"last": b}
        bg = dict(globals_)
        _inject_resolved_targets({("last", 2)}, bg, owner.db, globals_)
        fn = bg[_disp_key("last", 2)]
        assert len(list(_drive_trampoline(fn, Trail(), [4, 5], 5))) == 1
        assert owner.db.row("last", 2) is None
        assert len(list(call("assertz", Compound("last", (9, 9)),
                             module=owner))) == 1
        assert owner.db.row("last", 2) is not None
        # the local row answers now, through the compiled entry and solve.call
        assert len(list(_drive_trampoline(fn, Trail(), 9, 9))) == 1
        assert len(list(_drive_trampoline(fn, Trail(), [4, 5], 5))) == 0
        assert len(list(call("last", [4, 5], 5, module=owner))) == 0

    @pytest.mark.parametrize("era", ["handle"])  # the class era is gone
    def test_with_nothing_else_to_answer_the_arity_is_reported(
            self, lm, owner, era):
        """No builtin ping/2 and no ping/2 row in the compiling db: the
        binding is kept, and the call reports the arity -- both eras."""
        from clausal.logic.compiler.globals_env import _inject_resolved_targets
        from clausal.logic.predicate import _dispatch_at
        b = self._owner_binding(owner, "ping", era)
        assert owner.db.row("ping", 2) is None
        globals_ = {"ping": b}
        base_globals = dict(globals_)
        _inject_resolved_targets({("ping", 2)}, base_globals, owner.db, globals_)
        assert base_globals["ping"] is b
        with pytest.raises(PredicateArityMismatchError):
            _dispatch_at(b, 2)
        # Operator ruling 2026-09-24 (the aliased-import leak): this call site
        # is UNQUALIFIED, so it gets its own ``$disp_`` entry that resolves in
        # THIS module under THIS name and otherwise refuses -- never the
        # binding's owner.  The emitter prefers it over $dispatch_at.
        from clausal.logic.compiler.globals_env import _disp_key
        from clausal.logic.solve import _drive_trampoline
        from clausal.logic.variables import Trail
        fn = base_globals[_disp_key("ping", 2)]
        with pytest.raises(PredicateArityMismatchError, match="ping"):
            list(_drive_trampoline(fn, Trail(), 1, 2))

    @pytest.mark.parametrize("era", ["handle"])  # the class era is gone
    def test_a_binding_at_its_own_arity_is_still_accepted(self, lm, owner, era):
        from clausal.logic.compiler.globals_env import _inject_resolved_targets
        b = self._owner_binding(owner, "last", era)
        globals_ = {"last": b}
        base_globals = dict(globals_)
        _inject_resolved_targets({("last", 1)}, base_globals, owner.db, globals_)
        assert base_globals["last"] is b

    @pytest.mark.parametrize("era", ["handle"])  # the class era is gone
    def test_a_data_reference_keeps_the_binding(self, lm, owner, era):
        from clausal.logic.compiler.globals_env import _inject_resolved_targets
        b = self._owner_binding(owner, "ping", era)
        globals_ = {"ping": b}
        base_globals = dict(globals_)
        _inject_resolved_targets({("ping", -1)}, base_globals, lm.db, globals_)
        assert base_globals["ping"] is b

    @pytest.mark.parametrize("era", ["handle"])  # the class era is gone
    def test_dotted_applied_at_another_arity_takes_the_attribute_walk(
            self, lm, owner, era):
        """The dotted key holds a /0 binding; the call is /2; the walk finds
        the module attribute that IS /2 and bakes its dispatch."""
        import types
        from clausal.logic.compiler.globals_env import (
            _disp_key, _inject_resolved_targets,
        )
        list(call("ping", 1, 2, module=lm))   # compile it
        row = lm.db.row("ping", 2)
        assert row.locked and row.dispatch_fn is not None
        attr = lm.module_dict["ping"]
        assert attr == _handle(lm, "ping")
        globals_ = {"X": types.SimpleNamespace(ping=attr),
                    "X.ping": self._owner_binding(owner, "ping", era)}
        base_globals = dict(globals_)
        _inject_resolved_targets({("X.ping", 2)}, base_globals, lm.db, globals_)
        assert base_globals["X.ping"] is attr
        assert base_globals.get(_disp_key("X.ping", 2)) is row.dispatch_fn

    @pytest.mark.parametrize("era", ["handle"])  # the class era is gone
    def test_dotted_sys_modules_route_at_another_arity(
            self, lm, owner, monkeypatch, era):
        """``owner.last`` is last/1; the call is /2.  No builtin is dotted, so
        at COMPILE time nothing else answers: the object is kept (not a
        NameError at run time) and nothing is baked.

        At RUN time the kept binding is asked for ``last/2`` in ITS module
        (``owner``), and there the builtin ``last/2`` answers -- UPDATED for
        the name + ARITY ruling (operator, 2026-09-24; ``todo/done/wrong-
        arity-call-still-refuses-in-two-places-2026-09-24.md``): this used to
        pin a ``PredicateArityMismatchError`` from ``_dispatch_at(b, 2)``, the
        class-era refusal the ruling retires.  Both eras agree.

        The compile-time half is NOT mutation-sensitive, by construction:
        with an arity-blind accept the same object is kept and
        ``_maybe_cache_dispatch`` refuses the bake at the wrong arity
        anyway.  It pins the outcome, both eras."""
        from clausal.logic.compiler.globals_env import (
            _disp_key, _inject_resolved_targets,
        )
        from clausal.logic.predicate import _dispatch_at
        from clausal.logic.solve import _drive_trampoline
        from clausal.logic.variables import Trail
        b = self._owner_binding(owner, "last", era)
        assert sys.modules[owner.name].__dict__["last"] is b   # the load's flip
        dotted = f"{owner.name}.last"
        base_globals: dict = {}
        _inject_resolved_targets({(dotted, 2)}, base_globals, lm.db, {})
        assert base_globals[dotted] is b
        assert _disp_key(dotted, 2) not in base_globals
        fn = _dispatch_at(b, 2)                    # the builtin last/2
        assert len(list(_drive_trampoline(fn, Trail(), [4, 5], 5))) == 1
        assert len(list(_drive_trampoline(fn, Trail(), [4, 5], 4))) == 0

    # -- dotted names (review, 2026-09-24) ---------------------------------
    #
    # A dotted target (``mod.last``) resolves by one of three routes: the
    # module's own dotted-key binding (what ``-import_from`` writes), the
    # attribute walk from a name in the globals, or ``sys.modules``.  The
    # early accept above runs before all three, so a class under the dotted
    # key never reached them either; the handle must land on the same answer
    # as the class on every route, in data (-1) and applied (2) position,
    # with the same ``$disp_`` bake.  Unconverted, the dotted-key route lost
    # the bake and the ``sys.modules`` route resolved NOTHING for a handle.

    @pytest.mark.parametrize("targets", [(2,), (-1,), (2, -1)],
                             ids=["applied", "data", "both"])
    @pytest.mark.parametrize("route", ["dotted-key", "attr-walk", "sys-modules"])
    @pytest.mark.parametrize("era", ["handle"])  # the class era is gone
    def test_dotted_target(self, lm, monkeypatch, era, route, targets):
        from clausal.logic.builtins import BuiltinPredicate
        from clausal.logic.compiler.globals_env import (
            _disp_key, _inject_resolved_targets,
        )
        list(call("last", 1, 1, module=lm))   # compile it
        row = lm.db.row("last", 2)
        assert row is not None and row.locked and row.dispatch_fn is not None
        pymod = sys.modules[lm.name]
        binding = lm.module_dict["last"]
        # the module attribute IS the module dict entry, flipped by the load
        assert binding == _handle(lm, "last")
        assert pymod.__dict__["last"] is binding
        dotted = f"{lm.name}.last"
        globals_ = {}
        if route in ("dotted-key", "attr-walk"):
            globals_[lm.name] = pymod
        if route == "dotted-key":
            globals_[dotted] = binding
        base_globals = dict(globals_)
        _inject_resolved_targets({(dotted, a) for a in targets},
                                 base_globals, lm.db, globals_)
        got = base_globals.get(dotted)
        assert not isinstance(got, BuiltinPredicate)
        assert got is binding
        if 2 in targets:
            assert base_globals.get(_disp_key(dotted, 2)) is row.dispatch_fn
        else:
            assert _disp_key(dotted, 2) not in base_globals


# ── 5. the specializer's residual-goal dispatcher (found by review) ─────────


class TestSpecializerSolveGoal:
    """``_make_solve_goal_predicate``'s ``module_dict`` fallback: a residual
    goal ``[name, *args]`` is dispatched to the module's predicate of that
    name.  Unconverted, a handle binding reached "Unknown goal -- fail
    silently"."""

    @staticmethod
    def _dispatcher(lm, era):
        from clausal.logic.specialization import _make_solve_goal_predicate
        md = dict(lm.module_dict)
        for n in ("is_pos", "last"):
            assert md[n] == _bound_handle(lm, n)
        return _make_solve_goal_predicate("SG_w4b3", None, md)

    @pytest.mark.parametrize("era", ["handle"])  # the class era is gone
    def test_residual_goal_reaches_the_user_predicate(self, lm, era):
        sg = self._dispatcher(lm, era)
        assert len(list(call(sg, ["is_pos", 3]))) == 1
        assert len(list(call(sg, [mint("is_pos"), 3]))) == 1
        assert len(list(call(sg, ["is_pos", -3]))) == 0
        # the user's last/2, not the builtin
        assert len(list(call(sg, ["last", 1, 1]))) == 1
        assert len(list(call(sg, ["last", [5], 5]))) == 0

    @pytest.mark.parametrize("era", ["handle"])  # the class era is gone
    def test_wrong_arity_raises_in_both_eras(self, lm, era):
        """Both shapes resolve through ``_dispatch_at`` at the goal's arity,
        so both raise PredicateArityMismatchError (a TypeError subclass, so
        an ``except TypeError`` still catches it)."""
        assert issubclass(PredicateArityMismatchError, TypeError)
        sg = self._dispatcher(lm, era)
        with pytest.raises(PredicateArityMismatchError):
            list(call(sg, ["is_pos", 1, 2]))

    def test_a_non_predicate_implementor_is_dispatched(self, lm):
        """A ``_get_dispatch`` implementor that is not a ``PredicateMeta``
        (here a ``BuiltinPredicate``) goes through ``_dispatch_at``'s
        generic arm, called bare."""
        from clausal.logic.builtins import get_builtin_predicate
        from clausal.logic.specialization import _make_solve_goal_predicate
        bp = get_builtin_predicate("last", 2, lm.db)
        assert bp is not None and not isinstance(bp, PredicateMeta)
        md = dict(lm.module_dict)
        md["my_last"] = bp
        sg = _make_solve_goal_predicate("SG_w4b3", None, md)
        assert len(list(call(sg, ["my_last", [4, 5], 5]))) == 1
        assert len(list(call(sg, ["my_last", [4, 5], 4]))) == 0

    def test_a_data_atom_is_still_an_unknown_goal(self, lm):
        from clausal.logic.specialization import _make_solve_goal_predicate
        md = dict(lm.module_dict)
        md["secret"] = _secret(lm)
        sg = _make_solve_goal_predicate("SG_w4b3", None, md)
        assert list(call(sg, ["secret", 1])) == []
