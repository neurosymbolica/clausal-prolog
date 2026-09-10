"""Tabling lifecycle: the wrapper survives a recompile, and a ``-table`` that
cannot be honoured is refused instead of ignored.

See ``todo/done/tabling-lifecycle-gaps-rewrap-and-cross-module-table.md``.

Two faults, both of which used to be invisible from the outside:

* every runtime recompile (``assertz``/``asserta``/``retract``, or the lazy
  recompile they trigger) installed the RAW compiled dispatch over the SLG
  wrapper.  A tabled predicate lost answer dedup, and a *left-recursive* one
  lost termination — ``test_assertz_keeps_left_recursion_terminating`` is the
  one that matters, because it is the difference between a wrong answer count
  and a program that never returns.

* ``-table`` naming a predicate this module does not compile (an import, a
  ``-specialize`` alias, a clause-less declaration) marked the database and
  wrapped nothing at all, with no warning.

Every assertion here is on observable behaviour — answers, or termination —
never on ``_dispatch_fn`` being some particular object: a wrapper that memoises
nothing would satisfy an identity check.
"""
import os
import signal

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.logic.database import Clause
from clausal.terms import Compound


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture
def load(tmp_path):
    """Load ``source`` as a fresh .clausal module under a unique name.

    Tabling state and atom identity are module-scoped, so no two tests here
    share a module.
    """
    counter = [0]

    def _load(source):
        counter[0] += 1
        name = f"tbl_lifecycle_{os.getpid()}_{id(counter)}_{counter[0]}"
        path = tmp_path / f"{name}.clausal"
        path.write_text(source)
        return _load_module(name, str(path))

    return _load


def _lm(mod):
    return mod.__dict__["$module"]


class _Timeout(Exception):
    pass


def _bounded(seconds, thunk):
    """Run *thunk*, raising ``_Timeout`` if it has not returned in *seconds*.

    A predicate that lost tabling does not *fail* the left-recursion test, it
    never finishes it — the trampoline loops without growing the Python stack,
    so there is no RecursionError to catch.  A real clock is the only honest
    bound.  Kept well under the suite-wide 10s pytest-timeout, which kills the
    whole process rather than one test.
    """
    if not hasattr(signal, "SIGALRM"):
        pytest.skip("needs SIGALRM to bound a non-terminating query")

    def _fire(_signum, _frame):
        raise _Timeout

    previous = signal.signal(signal.SIGALRM, _fire)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        return thunk()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


# ── Fault 1: the wrapper must survive a runtime recompile ────────────────────


DEDUP_SRC = """-table(dup/1)
-dynamic(dup/1)

dup(P) <- (P == 1)
dup(P) <- (P < 2)
"""


class TestWrapperSurvivesRecompile:
    """Both clauses of ``dup/1`` succeed for ``dup(1)``, so the table's answer
    dedup is directly countable: 1 answer tabled, 2 untabled."""

    def test_dedup_before_any_mutation(self, load):
        m = load(DEDUP_SRC)
        assert len(list(call("dup", 1, module=_lm(m)))) == 1

    def test_assertz_keeps_dedup(self, load):
        m = load(DEDUP_SRC)
        lm = _lm(m)
        assert len(list(call("dup", 1, module=lm))) == 1
        lm.db.assertz(Clause(head=Compound("dup", (9,)), body=[]))
        assert len(list(call("dup", 1, module=lm))) == 1

    def test_asserta_keeps_dedup(self, load):
        m = load(DEDUP_SRC)
        lm = _lm(m)
        assert len(list(call("dup", 1, module=lm))) == 1
        lm.db.asserta(Clause(head=Compound("dup", (9,)), body=[]))
        assert len(list(call("dup", 1, module=lm))) == 1

    def test_assertz_builtin_keeps_dedup(self, load):
        """Through the ``assertz/1`` builtin, which recompiles itself rather
        than leaving it to the lazy path."""
        m = load(DEDUP_SRC)
        lm = _lm(m)
        assert len(list(call("dup", 1, module=lm))) == 1
        assert sum(1 for _ in call("assertz", m.dup(9), module=lm)) == 1
        assert len(list(call("dup", 1, module=lm))) == 1

    def test_retract_builtin_keeps_dedup_and_drops_stale_answers(self, load):
        """``retract/1`` deletes straight out of ``db._clauses``, so it never
        reaches ``Database.retract``'s table invalidation.  With the wrapper
        restored, the recompile has to abolish the table itself or the retracted
        clause's answers are served from cache forever."""
        m = load("""-table(fact/1)
-dynamic(fact/1)

fact(1),
fact(2),
""")
        lm = _lm(m)
        # Populate a table entry for the variant Fact(1), then remove the only
        # clause that answers it.
        assert len(list(call("fact", 1, module=lm))) == 1
        assert sum(1 for _ in call("retract", m.fact(1), module=lm)) == 1
        assert list(call("fact", 1, module=lm)) == []
        assert len(list(call("fact", 2, module=lm))) == 1

    def test_assertz_keeps_left_recursion_terminating(self, load):
        """THE correctness case: ``path/2`` is left-recursive and terminates only
        because it is tabled.  An ``assertz`` that strips the wrapper turns a
        program that answers into one that never returns."""
        m = load("""-table(path/2)
-dynamic(path/2)

edge(1, 2),
edge(2, 3),

path(X, Y) <- edge(X, Y)
path(X, Y) <- (
    path(X, Z),
    edge(Z, Y)
)
""")
        lm = _lm(m)

        def _reach():
            Y = Var()
            return sorted(deref(Y) for _ in call("path", 1, Y, module=lm))

        assert _bounded(3.0, _reach) == [2, 3]
        lm.db.assertz(Clause(head=Compound("path", (9, 9)), body=[]))
        try:
            after = _bounded(3.0, _reach)
        except _Timeout:
            pytest.fail(
                "left-recursive path/2 no longer terminates after assertz — "
                "the recompile stripped the tabling wrapper"
            )
        assert after == [2, 3]


# ── Fault 2: an unhonourable -table is refused, not ignored ──────────────────


class TestTableTargetRefused:
    def test_imported_target_refused_naming_the_other_module(self):
        with pytest.raises(SyntaxError) as exc:
            _load_module(
                "tbl_imported_target",
                os.path.join(FIXTURES, "table_imported_target.clausal"),
            )
        msg = str(exc.value)
        assert "-table(double/2)" in msg
        assert "another module" in msg
        assert "importable_utils" in msg  # names where it IS defined
        assert "Move -table(double/2)" in msg  # and the remedy

    def test_specialize_alias_target_refused(self, load):
        with pytest.raises(SyntaxError) as exc:
            load("""-import_from(clausal.examples.metainterpreters, [solve])

tiny_program(PROGRAM) <- (
    PROGRAM is [
        [["edge", "a", "b"], []]
    ]
)

-specialize(solve, tiny_program, alias=solve_tiny)
-table(solve_tiny/1)
""")
        msg = str(exc.value)
        assert "-table(solve_tiny/1)" in msg
        assert "-specialize alias" in msg

    def test_clauseless_declared_target_refused(self, load):
        with pytest.raises(SyntaxError) as exc:
            load("""-private([ghost(A, B)])

real(X) <- (X == 1)
""".replace("real(X) <- (X == 1)", "-table(ghost/2)\n\nreal(X) <- (X == 1)"))
        msg = str(exc.value)
        assert "-table(ghost/2)" in msg
        assert "no clauses in this module" in msg

    def test_undefined_target_still_refused(self, load):
        with pytest.raises(SyntaxError) as exc:
            load("""-table(no_such/2)

real(X) <- (X == 1)
""")
        assert "no_such/2" in str(exc.value)

    def test_dynamic_clauseless_target_still_accepted(self, load):
        """The one clause-less target that IS tabled: a ``-dynamic`` predicate
        compiles here (to always-fail until asserted into) and gets wrapped like
        any other, so refusing it would be over-refusal."""
        m = load("""-table(later/1)
-dynamic(later/1)
""")
        lm = _lm(m)
        assert list(call("later", 1, module=lm)) == []
        assert sum(1 for _ in call("assertz", m.later(1), module=lm)) == 1
        assert len(list(call("later", 1, module=lm))) == 1

    def test_discontiguous_on_imported_target_still_accepted(self, load):
        """``-table`` is the strict one.  ``-discontiguous`` is a statement about
        this module's own clause layout and keeps the looser check."""
        m = load("""-import_from(tests.fixtures.importable_utils, [double])
-discontiguous(double/2)

uses_double(X, Y) <- double(X, Y)
""")
        Y = Var()
        lm = _lm(m)
        assert sorted(deref(Y) for _ in call("uses_double", 2, Y, module=lm)) == [4]
