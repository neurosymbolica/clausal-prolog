"""Type-mismatch notes for py-interop predicates in the failure diagnostic.

A py-interop builtin that bails on an ``isinstance`` guard is a bare "no" —
indistinguishable from a goal that genuinely has no solution.  Study 13's
``study_schengen_max_stay_r1`` stalled for 7 attempts on ``date_add/3`` called
with an int where a timedelta is required.  During the diagnostic re-run the
guard now records what it rejected, and the note lands in the failure report.
See ``todo/C1-ill-typed-interop-calls-are-silent-failures.md``.

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
    from clausal.modules.py.datetime import _date_4, _timedelta_3
    trail = Trail()
    with collect_type_mismatch_notes() as notes:
        list(_date_4(Var(), Var(), Var(), Var(), trail, None))
        list(_timedelta_3(Var(), Var(), Var(), trail, None))
    assert notes == []


def test_note_rejected_call_records_exception():
    with collect_type_mismatch_notes() as notes:
        try:
            import datetime as dt
            dt.date(2024, 13, 1)
        except ValueError as exc:
            note_rejected_call("date/4", exc)
    assert notes == ["date/4 rejected its arguments — ValueError: month must be in 1..12"]


# ── end-to-end: the note reaches the failure report ───────────────────────────


DATE_ADD_INT_SRC = """
-import_from(date_time, [date_add, date])

Test("window end computes") <- (
    date(2024, 1, 1, D),
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
    date(2024, 1, 1, D),
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
    date(2024, 13, 1, D),
    D is not _
),
"""


def test_constructor_rejection_noted(capsys, tmp_path):
    p = write(tmp_path, "d13.clausal", CONSTRUCT_REJECT_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "date/4 rejected its arguments" in out
    assert "month must be in 1..12" in out


UNBOUND_TD_SRC = """
-import_from(date_time, [date_add, date])

Test("unbound timedelta is a mode, not a type error") <- (
    date(2024, 1, 1, D),
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
