"""Type-mismatch notes for py-interop predicates in the failure diagnostic.

A py-interop builtin that bails on an ``isinstance`` guard is a bare "no" —
indistinguishable from a goal that genuinely has no solution.  A measured
authoring study stalled for 7 attempts on ``date_add/3`` called with an int
where a timedelta is required.  During the diagnostic re-run the guard now
records what it rejected, and the note lands in the failure report.
See ``todo/done/C1-ill-typed-interop-calls-are-silent-failures.md``.

Normal (non-diagnostic) runs are unchanged: the goal still just fails.
"""

from __future__ import annotations

import textwrap

from clausal.modules.py import (
    collect_type_mismatch_notes,
    expect_type,
    note_rejected_call,
)
from clausal.testing import main


def write(tmp_path, name, src):
    p = tmp_path / name
    p.write_text(textwrap.dedent(src).lstrip())
    return p


# ── helper unit behaviour ─────────────────────────────────────────────────────


def test_expect_type_passes_matching_value_and_records_nothing():
    with collect_type_mismatch_notes() as notes:
        assert expect_type("x", str, "parse/2")
    assert notes == []


def test_expect_type_records_bound_wrong_type():
    with collect_type_mismatch_notes() as notes:
        assert not expect_type(90, str, "parse/2")
    assert notes == ["parse/2 was called with int where str is required"]


def test_expect_type_names_argument_when_given():
    with collect_type_mismatch_notes() as notes:
        assert not expect_type(90, str, "parse/2", arg=1)
    assert notes == [
        "parse/2 was called with int where str is required (argument 1)"
    ]


def test_expect_type_expected_description_override():
    import datetime as dt
    with collect_type_mismatch_notes() as notes:
        assert not expect_type(
            90, (dt.date, dt.datetime), "date_add/3",
            expected="date or datetime", arg=1,
        )
    assert notes == [
        "date_add/3 was called with int where date or datetime is required "
        "(argument 1)"
    ]


def test_expect_type_unbound_var_fails_silently():
    from clausal.logic.variables import Var
    with collect_type_mismatch_notes() as notes:
        assert not expect_type(Var(), str, "parse/2")
    assert notes == []


def test_expect_type_is_silent_noop_outside_collection():
    # No collector active: still a plain type check, records nowhere.
    assert expect_type("x", str, "parse/2")
    assert not expect_type(90, str, "parse/2")


def test_notes_are_deduplicated():
    with collect_type_mismatch_notes() as notes:
        expect_type(90, str, "parse/2")
        expect_type(90, str, "parse/2")
        expect_type(91, str, "parse/2")  # same message → one note
    assert notes == ["parse/2 was called with int where str is required"]


def test_constructor_with_unbound_component_records_nothing():
    # The diagnostic re-run probes predicates with fresh Vars; a construct
    # mode fed an unbound component raises TypeError inside the stdlib
    # constructor, and that must NOT read as "the user passed garbage".
    from clausal.logic.trampoline import DONE  # noqa: F401 - engine import path
    from clausal.logic.variables import Trail, Var
    # The _date_4 half was deleted with the predicate (2026-09-01). date/3 has
    # no equivalent hazard: an unbound component yields a _DatePattern for
    # unification rather than calling the stdlib constructor at all, so there is
    # no TypeError to mis-record. _timedelta_3 still takes this path.
    from clausal.modules.py.datetime import _timedelta_3
    trail = Trail()
    with collect_type_mismatch_notes() as notes:
        list(_timedelta_3(Var(), Var(), Var(), trail, None))
    assert notes == []


def test_note_rejected_call_records_exception():
    with collect_type_mismatch_notes() as notes:
        try:
            import datetime as dt
            dt.date(2024, 13, 1)
        except ValueError as exc:
            note_rejected_call("date/4", exc)
    # Stdlib exception wording is not a stable API — assert the stable
    # prefix and the load-bearing word only.
    assert len(notes) == 1
    assert notes[0].startswith("date/4 rejected its arguments — ValueError:")
    assert "month" in notes[0]


def test_bool_timestamp_records_note():
    # bool subclasses int, so a plain isinstance guard would wave it
    # through — but timestamp/2's binding branch excludes it on purpose.
    from clausal.logic.variables import Trail, Var
    from clausal.modules.py.datetime import _timestamp_2
    with collect_type_mismatch_notes() as notes:
        list(_timestamp_2(Var(), True, Trail(), None))
    assert notes == [
        "timestamp/2 was called with bool where int or float is required "
        "(argument 2)"
    ]


def test_json_generate_nested_var_records_nothing():
    # A term that is bound at the top but holds a nested unbound Var is a
    # mode/instantiation situation — no note (and no leaked "Var" text).
    from clausal.logic.variables import Trail, Var
    from clausal.modules.py.json import _generate_2
    with collect_type_mismatch_notes() as notes:
        list(_generate_2([1, Var()], Var(), Trail(), None))
    assert notes == []


def test_json_generate_ground_unserializable_records_note():
    from clausal.logic.variables import Trail, Var
    from clausal.modules.py.json import _generate_2
    with collect_type_mismatch_notes() as notes:
        list(_generate_2([1, b"raw-bytes"], Var(), Trail(), None))
    assert len(notes) == 1
    assert notes[0].startswith("generate/2 rejected its arguments")


def test_http_post_wrong_typed_data_notes_but_behaves_as_before(monkeypatch):
    # The body-less POST for non-str/bytes data is pre-existing behaviour;
    # the guard is note-only.
    import clausal.modules.py.http as http_mod
    from clausal.logic.variables import Trail, Var
    calls = []
    monkeypatch.setattr(http_mod, "_do_request",
                        lambda *a, **kw: calls.append((a, kw)) or (200, "ok"))
    body = Var()
    with collect_type_mismatch_notes() as notes:
        results = list(http_mod._post_3("http://x.test/", 42, body, Trail(), None))
    assert notes == [
        "post/3 was called with int where str or bytes is required (argument 2)"
    ]
    assert len(results) == 1 and len(calls) == 1  # request still made


def test_diagnose_failure_survives_broken_interop_import(
        capsys, tmp_path, monkeypatch):
    # diagnose_failure promises never to raise; a broken py-interop package
    # must degrade to no notes, not crash the harness.
    import sys
    import types
    monkeypatch.setitem(sys.modules, "clausal.modules.py",
                        types.ModuleType("clausal.modules.py"))
    p = write(tmp_path, "plain.clausal", """
    prc("alpha", 10),

    Test("fails plainly") <- (
        prc("beta", _N)
    ),
    """)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "goal 1 of 1 failed" in out


# ── end-to-end: the note reaches the failure report ───────────────────────────


DATE_ADD_INT_SRC = """
-import_from(date_time, [date_add, date])

Test("window end computes") <- (
    D is date(2024, 1, 1),
    date_add(D, 90, END),
    END is not _
),
"""


def test_date_add_int_note_in_failure_report(capsys, tmp_path):
    p = write(tmp_path, "dadd.clausal", DATE_ADD_INT_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "date_add/3 was called with int where timedelta is required" in out


DATE_ADD_DEEP_SRC = """
-import_from(date_time, [date_add, date])

window_end(START, END) <- (
    date_add(START, 90, END)
),

Test("window end via helper") <- (
    D is date(2024, 1, 1),
    window_end(D, END),
    END is not _
),
"""


def test_note_survives_descent_into_user_predicate(capsys, tmp_path):
    # The ill-typed call sits one predicate down — the descent re-runs it,
    # so the guard note must still surface.
    p = write(tmp_path, "dadd_deep.clausal", DATE_ADD_DEEP_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "date_add/3 was called with int where timedelta is required" in out


CONSTRUCT_REJECT_SRC = """
-import_from(date_time, [date])

Test("month 13") <- (
    D is date(2024, 13, 1),
    D is not _
),
"""


def test_constructor_rejection_noted(capsys, tmp_path):
    p = write(tmp_path, "d13.clausal", CONSTRUCT_REJECT_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "date/3 rejected its arguments" in out
    assert "month must be in 1..12" in out
    # date/3 is a TERM constructor, so it cannot fail the way date/4's goal
    # could: it raises an ISO domain_error carrying the culprit. The note is
    # kept as well, because the note is what names the predicate in a failure
    # report and losing it would make the diagnostic worse than what it replaced.
    assert "domain_error" in out


UNBOUND_TD_SRC = """
-import_from(date_time, [date_add, date])

Test("unbound timedelta is a mode, not a type error") <- (
    D is date(2024, 1, 1),
    date_add(D, TD, END),
    END is not _
),
"""


def test_unbound_arg_gets_no_type_note(capsys, tmp_path):
    # An unbound Var is a legitimate "different mode / no solution" signal —
    # rung-2 already covers it; a type note would be noise.
    p = write(tmp_path, "dvar.clausal", UNBOUND_TD_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "was called with" not in out
