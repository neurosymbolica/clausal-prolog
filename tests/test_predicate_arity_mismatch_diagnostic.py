"""Calling a *visible* predicate at the wrong arity must say so.

See ``todo/arity-mismatch-reports-a-missing-trail-argument.md``.  When the
called name is out of scope the lookup fails and
``clausal.predicate_diagnostics`` already reports it well.  But when the name
IS bound — defined in this file, or imported — the compiler injects the
predicate class directly, the wrong-arity call reaches the generated dispatch
function, and it fails as a raw Python ``TypeError``::

    citation__3() missing 1 required positional argument: 'trail'

which leaks the mangled internal name, blames an argument the author never
wrote and cannot supply, and never says the word *arity* — the entire content
of the fault.  The in-module case is the common one, so the common fault had
the worse message.

The second half of this file is the false-positive guard.  A ``Call`` node in
a clause body is not necessarily a *goal*: partial-kwargs term construction
(``vec(x=1)``) and a DCG nonterminal passed to ``phrase/3``
(``phrase(count_leaves(T), ...)``) both look like arity mismatches at the name
level, and both must keep working.
"""

from __future__ import annotations

import os
import textwrap

import pytest

from clausal.predicate_diagnostics import (
    PredicateArityMismatchError,
    describe_arity_mismatch,
)
from clausal.testing import load_clausal_module, main


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def write(tmp_path, name, src):
    p = tmp_path / name
    p.write_text(textwrap.dedent(src).lstrip())
    return p


CITATIONS = """
    -private([art_1_2, meta])

    citation(art_1_2, "EUMR Article 1(2)", meta),
    cite(art_1_2),

    Test("citation record resolves") <- (
        cite(REF),
        citation(REF, METADATA)
    ),
"""


def _report(tmp_path, src, name="t.clausal"):
    """Run *src* as a .clausal test file and return the printed report."""
    path = write(tmp_path, name, src)
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        main([str(path)])
    return buf.getvalue()


# ── the reported message ─────────────────────────────────────────────────────


class TestTheMessage:

    def test_does_not_blame_trail(self, tmp_path):
        out = _report(tmp_path, CITATIONS)
        assert "positional argument" not in out
        assert "'trail'" not in out

    def test_does_not_leak_the_mangled_name(self, tmp_path):
        assert "citation__3" not in _report(tmp_path, CITATIONS)

    def test_names_both_arities(self, tmp_path):
        out = _report(tmp_path, CITATIONS)
        assert "citation" in out
        # what it takes, and what this call passed
        assert "3 arguments" in out
        assert "2" in out

    def test_states_the_fault_on_the_first_line(self, tmp_path):
        """The summary line is one line; the fault has to fit on it."""
        out = _report(tmp_path, CITATIONS)
        summary = next(ln for ln in out.splitlines()
                       if "citation record resolves" in ln)
        assert "takes 3 arguments" in summary
        assert "passes 2" in summary

    def test_points_at_the_definition(self, tmp_path):
        out = _report(tmp_path, CITATIONS)
        assert "t.clausal:3" in out

    def test_offers_a_remedy(self, tmp_path):
        out = _report(tmp_path, CITATIONS)
        assert "->" in out
        assert "citation/2" in out


class TestForwardReference:
    """A call written *above* the definition resolves the same way."""

    def test_still_diagnosed(self, tmp_path):
        out = _report(tmp_path, """
            -private([art_1_2, meta])

            Test("forward") <- citation(REF, META),

            citation(art_1_2, "EUMR Article 1(2)", meta),
        """)
        assert "takes 3 arguments" in out
        assert "positional argument" not in out


class TestOtherGoalPositions:
    """Every position that turns a name into a dispatch function reports it.

    ``_get_dispatch`` is that one place, which is why negation, ``findall/3``
    and ``call/N`` all arrive at the same message without three separate fixes.
    """

    def _out(self, tmp_path, goal, name):
        return _report(tmp_path, f"""
            -private([art_1_2, meta])

            citation(art_1_2, "EUMR Article 1(2)", meta),

            Test("g") <- {goal},
        """, name=name)

    def test_inside_negation(self, tmp_path):
        out = self._out(tmp_path, "(not citation(REF, META))", "argneg.clausal")
        assert "takes 3 arguments" in out

    def test_inside_findall(self, tmp_path):
        out = self._out(tmp_path, "findall(R, citation(R, M), L)",
                        "argfa.clausal")
        assert "takes 3 arguments" in out

    def test_via_call_n(self, tmp_path):
        """``call/N`` resolves the goal at runtime, inside the builtin."""
        out = self._out(tmp_path, "call(citation, REF, META)",
                        "argcall.clausal")
        assert "takes 3 arguments" in out
        assert "positional argument" not in out


class TestImportedPredicate:
    """-import_from binds the exporter's class, so the name IS in scope."""

    def _error(self):
        from clausal.import_hook import _load_module
        from clausal.logic.solve import call
        from clausal.logic.variables import Var
        mod = _load_module("_arimp_use",
                           os.path.join(FIXTURES, "arimp_use.clausal"))
        with pytest.raises(TypeError) as exc:
            list(call("arimp_uses", Var(), module=mod.__dict__["$module"]))
        return str(exc.value)

    def test_names_the_arity(self):
        assert "arimp_pair takes 2 arguments" in self._error()

    def test_points_across_the_module_boundary(self):
        assert "arimp_lib.clausal:" in self._error()


# ── the unit-level message builder ───────────────────────────────────────────


class TestDescribe:

    def test_never_raises_on_junk(self):
        # A diagnostic that fails must degrade, not replace one failure with
        # another.
        assert describe_arity_mismatch("f", 2, None, object())

    def test_mentions_the_site_when_known(self):
        msg = describe_arity_mismatch("citation", 2, 3, ("t.clausal", 3))
        assert "t.clausal:3" in msg

    def test_omits_the_site_when_unknown(self):
        msg = describe_arity_mismatch("citation", 2, 3, None)
        assert "<unknown>" not in msg
        assert "takes 3 arguments" in msg

    def test_singular_argument(self):
        assert "1 argument," in describe_arity_mismatch("f", 3, 1)


class TestExceptionType:

    def test_is_a_type_error(self, tmp_path):
        """It was a TypeError before; anything catching that keeps working."""
        assert issubclass(PredicateArityMismatchError, TypeError)


# ── false positives: a Call in a body is not necessarily a goal ──────────────


class TestTermConstructionUnaffected:

    def test_partial_kwargs_functor(self):
        """``vec(x=1)`` builds a *term* — arity 1 against a /2 class."""
        assert main([os.path.join(FIXTURES, "builtins_keywords.clausal")]) == 0

    def test_partial_term_in_argument_position(self, tmp_path):
        """``citation(REF)`` as an *argument* — arity 1 against a /3 predicate.

        This is the shape a DCG nonterminal handed to ``phrase/3`` takes after
        translation (``phrase(count_leaves(T), [0], [N])`` names a /3
        nonterminal at /1); ``tests/test_dcg.py`` covers that instance.
        """
        out = _report(tmp_path, """
            -private([art_1_2, meta])

            citation(art_1_2, "EUMR Article 1(2)", meta),
            arcm_shape(REF, N) <- functor(citation(REF), N, _),

            Test("partial term") <- (arcm_shape(art_1_2, N), N == "citation"),
        """)
        assert "PASSED" in out

    def test_atom_vocabulary_then_predicate(self):
        """A 0-arity imported atom re-minted as a /2 predicate (Phenomenon A).

        ``_arity`` stays 0 on the shared class while the clauses on it are
        already at /2, so the cheap check in ``_get_dispatch`` fires and the
        clause-head confirmation has to clear it.  Behaviour is pinned in
        ``tests/test_functor_import_ordering.py``; this asserts the property
        the confirmation relies on.
        """
        use = load_clausal_module(
            os.path.join(FIXTURES, "impord_atom_then_pred.clausal"))
        shared = use.impord_qd               # the imported atom's class
        assert shared._arity == 0            # stale
        assert shared._clause_arity() == 2   # the truth
        shared._refuse_call_at(2)            # must not raise


class TestCorrectCallsUnaffected:

    def test_right_arity_still_runs(self, tmp_path):
        out = _report(tmp_path, """
            -private([art_1_2, meta])

            citation(art_1_2, "EUMR Article 1(2)", meta),

            Test("ok") <- citation(REF, LABEL, META),
        """)
        assert "PASSED" in out
