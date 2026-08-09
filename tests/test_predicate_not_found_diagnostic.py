"""`Predicate name/N not found` must say which predicates *are* reachable.

See ``todo/done/predicate-not-found-should-list-candidates.md``.  The goal-level
report already names the goal and its index; what it never said is what the
author could have called instead, so the three situations that need three
different fixes were indistinguishable:

* ``citation`` exists here at another arity          → fix the call,
* ``citation`` lives in a module this file can reach → fix the import,
* ``citation`` was never written                     → define it.

Same house rule as ``tests/test_import_export_diagnostic.py``: say what is
available and where, not only what is missing.
"""

from __future__ import annotations

import os
import re
import sys
import textwrap

import pytest

from clausal.logic.compiler import compile_predicate_trampoline
from clausal.logic.database import Clause, Database, Module
from clausal.logic.solve import call
from clausal.terms import Call, Compound, LoadName
from clausal.logic.variables import Var
from clausal.predicate_diagnostics import (
    PredicateNotFoundError,
    describe_missing_predicate,
)
from clausal.testing import main


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def write(tmp_path, name, src):
    p = tmp_path / name
    p.write_text(textwrap.dedent(src).lstrip())
    return p


# ── a Database-backed module whose caller asks for the wrong arity ───────────


def _wrong_arity_module() -> Module:
    """``uses/2`` calls ``citation/2``; the database defines ``citation/3``."""
    mod = Module("prednf_db")
    db = mod.db
    a, b, c = Var(), Var(), Var()
    db.assertz(Clause(head=Compound("citation", (a, b, c)), body=[]))
    compile_predicate_trampoline("citation", 3, db.clauses_for("citation", 3), db)
    db.assertz(Clause(head=Compound("cite", (a,)), body=[]))
    compile_predicate_trampoline("cite", 1, db.clauses_for("cite", 1), db)
    x, y = Var(), Var()
    db.assertz(Clause(
        head=Compound("uses", (x, y)),
        body=[Call(func=LoadName(name="citation"), args=[x, y], kwargs=[])],
    ))
    compile_predicate_trampoline("uses", 2, db.clauses_for("uses", 2), db)
    return mod


def _wrong_arity_error() -> PredicateNotFoundError:
    mod = _wrong_arity_module()
    with pytest.raises(KeyError) as exc:
        list(call("uses", Var(), Var(), module=mod))
    return exc.value


# ── the message is still a KeyError, and still names the predicate ───────────


class TestShape:

    def test_first_line_is_the_original_message(self):
        msg = str(_wrong_arity_error())
        assert msg.splitlines()[0] == "Predicate citation/2 not found"

    def test_still_a_keyerror_for_existing_handlers(self):
        assert isinstance(_wrong_arity_error(), KeyError)

    def test_str_is_not_repr_mangled(self):
        """``str(KeyError(msg))`` is ``repr(msg)`` — quotes and ``\\n``.

        A multi-line diagnostic delivered that way is unreadable, so the
        subclass must render its message verbatim.
        """
        msg = str(_wrong_arity_error())
        assert not msg.startswith("'")
        assert "\\n" not in msg
        assert len(msg.splitlines()) > 1


# ── case 1: same name, another arity, reachable from here ────────────────────


class TestOtherArity:

    def test_names_the_other_arity(self):
        msg = str(_wrong_arity_error())
        assert "citation/3" in msg

    def test_says_it_is_an_arity_mismatch(self):
        msg = str(_wrong_arity_error())
        assert re.search(r"did you mean:[^\n]*citation/3", msg)
        assert "different arity" in msg

    def test_lists_the_other_predicates_too(self):
        msg = str(_wrong_arity_error())
        assert "cite/1" in msg


# ── case 2: the name lives in another module ─────────────────────────────────


CITATIONS_SRC = """
# clausal: no-collect
-module(prednf_citations, [citation(REF, TEXT, NOTE), cite(REF)])

-private([art_1_2, meta])

citation(art_1_2, "Reg-Z Article 1(2)", meta),

cite(art_1_2),
"""

SIBLING_USE_SRC = """
-private([art_1_2])

local_ref(art_1_2),

Test("citation record resolves") <- (
    local_ref(REF),
    citation(REF, METADATA)
),
"""


class TestOtherModule:

    def test_unimported_sibling_file_is_found(self, capsys, tmp_path):
        write(tmp_path, "prednf_citations.clausal", CITATIONS_SRC)
        p = write(tmp_path, "sib_use.clausal", SIBLING_USE_SRC)
        assert main([str(p)]) == 1
        out = capsys.readouterr().out
        assert "citation/3" in out
        assert "prednf_citations" in out

    def test_sibling_is_flagged_as_not_imported(self, capsys, tmp_path):
        write(tmp_path, "prednf_citations.clausal", CITATIONS_SRC)
        p = write(tmp_path, "sib_use.clausal", SIBLING_USE_SRC)
        main([str(p)])
        out = capsys.readouterr().out
        assert "-import_from(" in out

    def test_imported_module_is_searched(self):
        """``-import_module(M)`` binds M here; an unqualified call still fails,
        and the message must point at M."""
        sys.modules.pop("_prednf_impuse", None)
        sys.modules.pop("tests.fixtures.prednf_citations", None)
        from clausal.import_hook import _load_module
        mod = _load_module("_prednf_impuse",
                           os.path.join(FIXTURES, "prednf_impmod_use.clausal"))
        with pytest.raises(KeyError) as exc:
            list(call("uses", Var(), Var(), module=mod.__dict__["$module"]))
        msg = str(exc.value)
        assert "citation/3" in msg
        assert "tests.fixtures.prednf_citations" in msg


# ── case 3: nothing similar anywhere ─────────────────────────────────────────


NOTHING_SRC = """
-private([art_1_2])

local_ref(art_1_2),

Test("absent predicate") <- (
    local_ref(REF),
    zzz_quux(REF, OUT)
),
"""


class TestNothingSimilar:

    def test_says_no_predicate_of_that_name(self, capsys, tmp_path):
        p = write(tmp_path, "nothing.clausal", NOTHING_SRC)
        assert main([str(p)]) == 1
        out = capsys.readouterr().out
        assert "no predicate named" in out
        assert "zzz_quux" in out

    def test_does_not_print_an_empty_candidate_list(self, capsys, tmp_path):
        p = write(tmp_path, "nothing.clausal", NOTHING_SRC)
        main([str(p)])
        out = capsys.readouterr().out
        # An empty list reads as "nothing is defined", a different claim.
        assert not re.search(r"defines:\s*$", out, re.M)
        assert not re.search(r"did you mean:\s*\??\s*$", out, re.M)

    def test_still_lists_what_this_module_does_define(self, capsys, tmp_path):
        p = write(tmp_path, "nothing.clausal", NOTHING_SRC)
        main([str(p)])
        out = capsys.readouterr().out
        assert "local_ref/1" in out


def test_module_defining_nothing_says_so():
    """A module with nothing in it must say that in words.

    Printing an empty ``defines:`` list would read as a list, not as an
    absence — the same trap the import diagnostic avoids for export lists.
    """
    msg = describe_missing_predicate("zzz_quux", 1, db=Database())
    assert re.search(r"defines no .*predicate", msg)
    assert not re.search(r"defines:\s*$", msg, re.M)


# ── the name is a builtin, at another arity ──────────────────────────────────


BUILTIN_SRC = """
Test("builtin at the wrong arity") <- (
    atom_length("abc", LEN, EXTRA)
),
"""


class TestBuiltinArity:

    def test_points_at_the_builtin_arity(self, capsys, tmp_path):
        p = write(tmp_path, "bi.clausal", BUILTIN_SRC)
        assert main([str(p)]) == 1
        out = capsys.readouterr().out
        assert "atom_length/2" in out
        assert "builtin" in out

    def test_does_not_claim_the_name_is_undefined(self, capsys, tmp_path):
        """The pre-fix message would have said "define atom_length/3" — a
        worse diagnosis than the bare line it replaces."""
        p = write(tmp_path, "bi.clausal", BUILTIN_SRC)
        main([str(p)])
        out = capsys.readouterr().out
        assert "no predicate named" not in out


# ── near-miss on the name itself ─────────────────────────────────────────────


NEAR_MISS_SRC = """
exceeds_limit(10),

Test("near miss on the name") <- (
    within_limit(10)
),
"""


def test_near_miss_on_the_name(capsys, tmp_path):
    """Same scoring as the import diagnostic: plain difflib rates this pair
    0.48 and would say nothing."""
    p = write(tmp_path, "nearmiss.clausal", NEAR_MISS_SRC)
    main([str(p)])
    out = capsys.readouterr().out
    assert re.search(r"did you mean:[^\n]*exceeds_limit", out)


# ── rendering through the runner the author actually reads ───────────────────


class TestCliRendering:

    def test_header_stays_one_line(self, capsys, tmp_path):
        write(tmp_path, "prednf_citations.clausal", CITATIONS_SRC)
        p = write(tmp_path, "sib_use.clausal", SIBLING_USE_SRC)
        main([str(p)])
        out = capsys.readouterr().out
        header = [ln for ln in out.splitlines() if ":: citation record" in ln]
        assert len(header) == 1
        assert header[0].endswith("Predicate citation/2 not found")

    def test_candidates_are_indented_under_the_goal(self, capsys, tmp_path):
        write(tmp_path, "prednf_citations.clausal", CITATIONS_SRC)
        p = write(tmp_path, "sib_use.clausal", SIBLING_USE_SRC)
        main([str(p)])
        out = capsys.readouterr().out
        assert "goal 2 of 2 raised:" in out
        for line in out.splitlines():
            if "citation/3" in line:
                assert line.startswith("      "), repr(line)

    def test_message_is_not_printed_twice(self, capsys, tmp_path):
        write(tmp_path, "prednf_citations.clausal", CITATIONS_SRC)
        p = write(tmp_path, "sib_use.clausal", SIBLING_USE_SRC)
        main([str(p)])
        out = capsys.readouterr().out
        assert out.count("did you mean:") == 1


# ── cost: the candidate walk must never run on the success path ──────────────


def test_no_candidate_work_on_the_success_path(monkeypatch):
    """A successful dispatch must not touch the diagnostic at all."""
    import clausal.predicate_diagnostics as pd

    def _boom(*a, **k):  # pragma: no cover - must not be reached
        raise AssertionError("candidate search ran on the success path")

    monkeypatch.setattr(pd, "describe_missing_predicate", _boom)
    mod = _wrong_arity_module()
    assert len(list(call("citation", Var(), Var(), Var(), module=mod))) == 1


# ── the message builder in isolation ─────────────────────────────────────────


def test_capped_sibling_scan_says_it_was_capped(tmp_path, monkeypatch):
    """A truncated search must not report an untruncated absence."""
    import clausal.predicate_diagnostics as pd

    monkeypatch.setattr(pd, "_MAX_SIBLING_FILES", 3)
    for i in range(10):
        write(tmp_path, f"m{i}.clausal", f"-module(m{i}, [p{i}(A)])\n\np{i}(1),\n")
    p = write(tmp_path, "nothing.clausal", NOTHING_SRC)
    msg = pd.describe_missing_predicate(
        "zzz_quux", 2, module_globals={"__name__": "m", "__file__": str(p)})
    assert "first 3 of 10" in msg
    assert "7 NOT searched" in msg


def test_describe_handles_a_bare_database():
    db = Database()
    msg = describe_missing_predicate("citation", 2, db=db, module_globals=None)
    assert msg.splitlines()[0] == "Predicate citation/2 not found"
    assert "no predicate named" in msg


def test_describe_never_raises_on_a_broken_namespace():
    """Diagnostics must not replace one failure with another."""

    class Exploding(dict):
        def items(self):
            raise RuntimeError("boom")

    msg = describe_missing_predicate("citation", 2, db=None,
                                     module_globals=Exploding())
    assert msg.splitlines()[0] == "Predicate citation/2 not found"
