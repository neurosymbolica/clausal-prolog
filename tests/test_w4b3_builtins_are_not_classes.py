"""W4b-3 slice 3: a builtin's module-level object is a ``BuiltinTerm``, not a
``PredicateMeta`` class.

``clausal.between`` (``_BUILTIN_CLASSES["between"]``) stays a CELL
constructor -- data, exactly what ``--between(...)`` builds in a
``.clausal`` module (operator ruling 2026-09-25: no runner) -- and a goal
object that ``_dispatch_at`` / ``_ensure_trampoline_dispatch`` answer
through their generic ``_get_dispatch()`` arm.

Also pinned: a db-less compile of a predicate NAMED like a builtin no longer
picks the builtin's class up as its ``pred_cls`` (the latent bug the slice-2
inventory found at ``compiler/predicate.py``'s ``pred_cls`` fallback).
"""
from __future__ import annotations

import sys
import textwrap

import pytest

import clausal
import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.builtins import BuiltinTerm
from clausal.logic.builtins import _registry as R
from clausal.logic.predicate import PredicateMeta, _dispatch_at
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref, walk


def _population():
    pop = sorted(R._BUILTIN_CLASSES.items())
    assert len(pop) > 400, len(pop)          # the whole registry, not a sample
    return pop


def test_no_builtin_object_is_a_class():
    pop = _population()
    classes = [n for n, o in pop if isinstance(o, (type, PredicateMeta))]
    assert classes == []
    assert all(type(o) is BuiltinTerm for _, o in pop)
    # every exported ``clausal.<builtin>`` is the registry's object
    exported = [n for n in clausal._builtin_names]
    assert exported and all(getattr(clausal, n) is R._BUILTIN_CLASSES[n]
                            for n in exported)


def test_every_builtin_builds_its_cell_at_every_registered_arity():
    checked = 0
    for name, obj in _population():
        for arity in obj.arities:
            args = tuple(range(1, arity + 1))
            expected = (name, *args) if arity else name
            assert obj(*args) == expected, (name, arity)
            fields = R._BUILTIN_FIELDS[(name, arity)]
            if arity:
                assert obj(**dict(zip(fields, args))) == expected, (name, arity)
            checked += 1
    assert checked > 450, checked


def test_every_builtin_dispatches_through_the_generic_arm():
    """Same arity and wrong arity: ``_dispatch_at`` and
    ``_ensure_trampoline_dispatch`` answer exactly ``_get_dispatch()`` --
    the one arity's function, or the count-keyed dispatcher of a name
    registered at several -- or the same NotImplementedError when there is
    no db-free dispatch.  (What the class era answered: a builtin class's
    arity refusal never fired, measured over all 3,682 cases of the slice-3
    parity probe.)"""
    checked = 0
    for name, obj in _population():
        arities = obj.arities
        for k in sorted(set(arities) | {max(arities) + 1}):
            try:
                expected = obj._get_dispatch()
            except NotImplementedError:
                with pytest.raises(NotImplementedError):
                    _dispatch_at(obj, k)
                with pytest.raises(NotImplementedError):
                    R._ensure_trampoline_dispatch(obj, k)
            else:
                assert _dispatch_at(obj, k) is expected, (name, k)
                assert R._ensure_trampoline_dispatch(obj, k) is expected
            checked += 1
    assert checked > 900, checked


def test_the_object_runs_as_a_goal():
    X = Var()
    assert [walk(deref(X)) for _ in call(clausal.between, 1, 3, X)] == [1, 2, 3]
    # a name registered at several arities keys on the count at call time
    L = Var()
    assert [walk(deref(L)) for _ in call(R._BUILTIN_CLASSES["numlist"],
                                           1, 3, L)] == [[1, 2, 3]]


def test_the_seam_and_the_python_object_build_the_identical_cell(tmp_path):
    """``--between(1, 3, X)`` in a ``.clausal`` module and
    ``clausal.between(1, 3, X)`` in Python build the SAME cell; the seam in
    goal position runs it.  (Measured over every builtin by the slice-3
    parity probe: 322 of 326 identical before AND after; the 4 others are
    seam-side refusals or rewrites, unchanged.)"""
    src = textwrap.dedent("""\
        -implicit_functors
        def term():
            return --between(1, 3, 4)
        def term_len():
            return --length([1, 2], 2)
        def run():
            return [X for X in --between(1, 3, X)]
        """)
    path = tmp_path / "_w4b3_seam_cells.clausal"
    path.write_text(src)
    try:
        mod = _load_module("_w4b3_seam_cells", str(path))
        assert mod.term() == clausal.between(1, 3, 4) == ("between", 1, 3, 4)
        assert mod.term_len() == clausal.length([1, 2], 2)
        assert mod.run() == [1, 2, 3]
    finally:
        sys.modules.pop("_w4b3_seam_cells", None)


def test_a_db_less_compile_of_a_builtin_named_predicate_is_its_own():
    """The latent bug: ``compile_predicate_trampoline('last', 2, ..., None)``
    looked ``last`` up in its globals, found the BUILTIN's class there, took
    it as ``pred_cls`` and installed onto it.  A ``BuiltinTerm`` is no
    class, so the fallback finds nothing and the predicate is its own."""
    from clausal.logic.compiler import compile_predicate_trampoline
    from clausal.logic.compiler import predicate as CP
    from clausal.logic.database import Clause
    from clausal.logic.solve import _drive_trampoline
    from clausal.logic.variables import Trail

    seen = []
    real = CP._install

    def spy(db, functor, arity, fn, pred_cls=None, **kw):
        seen.append((functor, arity, pred_cls))
        return real(db, functor, arity, fn, pred_cls=pred_cls, **kw)

    CP._install = spy
    try:
        fn = compile_predicate_trampoline(
            "last", 2, [Clause(head=("last", "mine", 7), body=[])], None)
    finally:
        CP._install = real
    assert seen and seen[-1] == ("last", 2, None), seen
    A, B = Var(), Var()
    sols = [(walk(deref(A)), walk(deref(B)))
            for _ in _drive_trampoline(fn, Trail(), A, B)]
    assert sols == [("mine", 7)]
    # the builtin itself is untouched
    X = Var()
    assert [walk(deref(X)) for _ in call(clausal.last, [1, 2], X)] == [2]


# ── Follow-ups (2026-09-25): no padding, listing, Solutions, lowering ───────


def test_a_builtin_object_in_a_goal_lowers_to_its_atom():
    """A builtin's object in TERM position of a Python-built goal is the atom
    of its name, as its class was before slice 3 -- ``maplist(succ, ...)``
    from Python.  Slice 3 lost the lowering arm (``NotImplementedError:
    unsupported term type BuiltinTerm``)."""
    m = clausal.Module("_w4b3_lower")
    X = Var()
    assert [walk(deref(X)) for _ in clausal.solve(("=", X, clausal.between),
                                                  module=m)] == ["between"]
    L = Var()
    assert [walk(deref(L)) for _ in clausal.solve(
        ("maplist", clausal.succ, [1, 2], L), module=m)] == [[2, 3]]


def _listing_output(arg):
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        n = len(list(call("listing", arg, module=clausal.Module("_w4b3_lst"))))
    return n, buf.getvalue()


def test_listing_takes_a_builtin_object_in_an_indicator_as_its_name():
    """roborev Low on slice 3: ``listing(<builtin>/3)`` from Python raised
    type_error(atomic, ...) -- ``_checked_indicator`` knew only the class.
    It names the builtin, exactly as the atom spelling does."""
    assert _listing_output(("/", clausal.between, 3)) == \
        _listing_output(("/", "between", 3))


def test_listing_a_builtin_object_says_it_is_a_builtin():
    assert _listing_output(clausal.between) == (1, "% between/3 — builtin\n")
    assert _listing_output(clausal.maplist)[1].splitlines()[:2] == [
        "% maplist/2 — builtin", "% maplist/3 — builtin"]


def test_solutions_refuses_a_module_it_would_ignore():
    """roborev Low on slice 3: ``Solutions(<not a goal value>, module=m)``
    dropped ``module=`` silently.  Now a TypeError; a goal value still
    takes it."""
    from clausal.repl import Solutions
    m = clausal.Module("_w4b3_sol")
    for not_a_goal_value in (True, False, iter([{}])):
        with pytest.raises(TypeError, match="module="):
            Solutions(not_a_goal_value, module=m)
    X = Var()
    assert [d["X"] for d in Solutions(clausal.between(1, 2, X), module=m,
                                      _varnames={"X": X})._iter] == [1, 2]
    assert list(Solutions(iter([{"a": 1}]))._iter) == [{"a": 1}]


def test_a_slot_given_positionally_and_by_name_is_refused():
    """The no-padding audit: ``build_term_cell`` let a positional overwrite
    a keyword naming the SAME slot, dropping the keyword's value silently.
    Python's own "multiple values" refusal, now."""
    from clausal.logic.predicate import (
        ClausalTermConstructionError, build_term_cell)
    with pytest.raises(ClausalTermConstructionError,
                       match=r"\(a\) given both positionally and by name"):
        build_term_cell("q", ("a", "b"), (1,), {"b": 2, "a": 5})
    assert build_term_cell("q", ("a", "b"), (1,), {"b": 2}) == ("q", 1, 2)
