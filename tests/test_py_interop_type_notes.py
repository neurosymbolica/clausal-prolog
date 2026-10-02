"""Py-interop argument checks: wrong type RAISES; the notes that remain.

A py-interop builtin that bailed on an ``isinstance`` guard used to be a bare
"no" -- indistinguishable from a goal that genuinely has no solution.  A
measured authoring study stalled for 7 attempts on ``date_add/3`` called with
an int where a timedelta is required.  The first fix recorded a note during
the failure-diagnostic re-run (``todo/done/C1-ill-typed-interop-calls-are-
silent-failures.md``).

RULED 2026-10-02: the call RAISES instead.  An argument of the wrong type
entirely is ``type_error(Type, Culprit)`` with the predicate as context; an
unbound argument where a value is required is ``instantiation_error``; a
right-typed value the library rejects (month 13, malformed JSON) still fails
the goal and records a note during the diagnostic re-run, which is what the
note machinery is kept for.
"""

from __future__ import annotations

import textwrap

import pytest

from clausal.logic.exceptions import LogicException
from clausal.modules.py import (
    collect_type_mismatch_notes,
    expect_type,
    note_mismatch,
    note_rejected_call,
)
from clausal.testing import main
from tests._suffix import SEAM


def write(tmp_path, name, src):
    p = tmp_path / name
    p.write_text(textwrap.dedent(src).lstrip())
    return p


def raised(fn, *args):
    with pytest.raises(LogicException) as info:
        fn(*args)
    return info.value.term


# ── expect_type ───────────────────────────────────────────────────────────────


def test_expect_type_passes_matching_value_and_records_nothing():
    with collect_type_mismatch_notes() as notes:
        assert expect_type("x", str, "parse/2")
    assert notes == []


def test_expect_type_raises_type_error_on_bound_wrong_type():
    with collect_type_mismatch_notes() as notes:
        term = raised(expect_type, 90, str, "parse/2")
    assert term == ("error", ("type_error", "text", 90), ("/", "parse", 2))
    assert notes == []          # an error, not a note


def test_expect_type_argument_position_goes_to_the_message():
    with pytest.raises(LogicException) as info:
        expect_type(90, str, "parse/2", arg=1)
    assert info.value.term == (
        "error", ("type_error", "text", 90), ("/", "parse", 2))
    assert "argument 1" in str(info.value)


@pytest.mark.parametrize("types, name", [
    (int, "integer"),
    ((int, float), "number"),
    (list, "list"),
    ((str, bytes), "text"),
])
def test_expect_type_uses_iso_type_names(types, name):
    assert raised(expect_type, ("f", 1), types, "p/1")[1] == (
        "type_error", name, ("f", 1))


def test_expect_type_adapter_type_name():
    import datetime as dt
    assert raised(expect_type, 90, dt.date, "date_add/3")[1] == (
        "type_error", "date", 90)


def test_expect_type_bool_is_not_an_integer():
    # true/false are atoms (D35), so a bool never passes an int check.
    assert raised(expect_type, True, int, "p/1")[1] == (
        "type_error", "integer", True)


def test_expect_type_unbound_var_raises_instantiation_error():
    from clausal.logic.variables import Var
    assert raised(expect_type, Var(), str, "parse/2") == (
        "error", "instantiation_error", ("/", "parse", 2))


def test_notes_are_deduplicated():
    with collect_type_mismatch_notes() as notes:
        note_mismatch("date_between/3", "mixed a date and a datetime")
        note_mismatch("date_between/3", "mixed a date and a datetime")
    assert notes == ["date_between/3 mixed a date and a datetime"]


def test_note_is_silent_noop_outside_collection():
    note_mismatch("date_between/3", "mixed a date and a datetime")


def test_constructor_with_unbound_component_raises_instantiation_error():
    # A construct mode fed an unbound component (and nothing to decompose)
    # can run in neither mode: an instantiation_error, not a type note.
    from clausal.logic.variables import Trail, Var
    from clausal.modules.py.datetime import _timedelta_3
    with collect_type_mismatch_notes() as notes:
        term = raised(lambda: list(_timedelta_3(Var(), Var(), Var(), Trail(), None)))
    assert term == ("error", "instantiation_error", ("/", "timedelta", 3))
    assert notes == []


def test_constructor_with_wrong_type_component_raises_type_error():
    from clausal.logic.variables import Trail, Var
    from clausal.modules.py.datetime import _time_4
    term = raised(lambda: list(_time_4(10.5, 0, 0, Var(), Trail(), None)))
    assert term == ("error", ("type_error", "integer", 10.5), ("/", "time", 4))


def _wrapper_cases():
    from clausal.logic.cells import chars
    from clausal.logic.variables import Var
    from clausal.modules.py import http, random, uuid
    from clausal.modules.py.datetime import _timedelta_3
    return [
        # integer_between/3 no longer int()-truncates a float or parses an
        # atom spelled as a number.
        (random._random_integer_3, (2.7, 5, Var()),
         ("type_error", "integer", 2.7), "integer_between"),
        (random._random_integer_3, ("3", 5, Var()),
         ("type_error", "integer", "3"), "integer_between"),
        (random._random_float_3, (True, 5, Var()),
         ("type_error", "number", True), "float_between"),
        (uuid._uuid3_3, (42, chars("n"), Var()),
         ("type_error", "uuid", 42), "uuid_v3"),
        (http._get_3, (chars("http://x.test/"), 42, Var()),
         ("type_error", "dict", 42), "get"),
        (http._post_4, (chars("http://x.test/"), chars("d"), 42, Var()),
         ("type_error", "dict", 42), "post"),
        (_timedelta_3, ("x", Var(), Var()),
         ("type_error", "number", "x"), "timedelta"),
    ]


@pytest.mark.parametrize("i", range(7))
def test_wrapper_wrong_type_raises(i, monkeypatch):
    import clausal.modules.py.http as http_mod
    from clausal.logic.variables import Trail
    monkeypatch.setattr(http_mod, "_do_request", lambda *a, **kw: (200, "ok"))
    fn, args, formal, name = _wrapper_cases()[i]
    term = raised(lambda: list(fn(*args, Trail(), None)))
    assert term[1] == formal and term[2][1] == name


def test_timedelta_accepts_a_rational_day_count():
    # A rational is a number: it crosses to timedelta as its float rather
    # than being refused by the stdlib constructor.
    from fractions import Fraction
    from clausal.logic.variables import Trail, Var, deref
    from clausal.modules.py.datetime import _timedelta_3
    td = Var()
    assert len(list(_timedelta_3(Fraction(3, 2), Var(), td, Trail(), None))) == 1
    assert deref(td)[:3] == ("timedelta", 1, 43200)


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


def test_bool_timestamp_raises_type_error():
    # bool subclasses int, so a plain isinstance check would wave it
    # through -- but true is an atom, not a number.
    from clausal.logic.variables import Trail, Var
    from clausal.modules.py.datetime import _timestamp_2
    term = raised(lambda: list(_timestamp_2(Var(), True, Trail(), None)))
    assert term == ("error", ("type_error", "number", True), ("/", "timestamp", 2))


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


def test_http_post_wrong_typed_data_raises_before_any_request(monkeypatch):
    # It used to send a body-less POST and record a note; now no request.
    import clausal.modules.py.http as http_mod
    from clausal.logic.cells import chars
    from clausal.logic.variables import Trail, Var
    calls = []
    monkeypatch.setattr(http_mod, "_do_request",
                        lambda *a, **kw: calls.append((a, kw)) or (200, "ok"))
    term = raised(lambda: list(
        http_mod._post_3(chars("http://x.test/"), 42, Var(), Trail(), None)))
    assert term == ("error", ("type_error", "text", 42), ("/", "post", 3))
    assert calls == []


def test_diagnose_failure_survives_broken_interop_import(
        capsys, tmp_path, monkeypatch):
    # diagnose_failure promises never to raise; a broken py-interop package
    # must degrade to no notes, not crash the harness.
    import sys
    import types
    monkeypatch.setitem(sys.modules, "clausal.modules.py",
                        types.ModuleType("clausal.modules.py"))
    p = write(tmp_path, f"plain{SEAM}", """
    -double_quotes(atom)
    prc("alpha", 10),

    test("fails plainly") <- (
        prc("beta", _N)
    ),
    """)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "goal 1 of 1 failed" in out


# ── end-to-end: the note reaches the failure report ───────────────────────────


DATE_ADD_INT_SRC = """
-double_quotes(atom)
-import_from(date_time, [date_add, date])

test("window end computes") <- (
    D is date(2024, 1, 1),
    date_add(D, 90, END),
    END is not _
),
"""


def test_date_add_int_raises_type_error_in_report(capsys, tmp_path):
    p = write(tmp_path, f"dadd{SEAM}", DATE_ADD_INT_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "error(type_error(timedelta,90),date_add/3)" in out


DATE_ADD_DEEP_SRC = """
-double_quotes(atom)
-import_from(date_time, [date_add, date])

window_end(START, END) <- (
    date_add(START, 90, END)
),

test("window end via helper") <- (
    D is date(2024, 1, 1),
    window_end(D, END),
    END is not _
),
"""


def test_type_error_raised_from_inside_user_predicate(capsys, tmp_path):
    # The ill-typed call sits one predicate down; the error still names it.
    p = write(tmp_path, f"dadd_deep{SEAM}", DATE_ADD_DEEP_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "error(type_error(timedelta,90),date_add/3)" in out


CONSTRUCT_REJECT_SRC = """
-double_quotes(atom)
-import_from(date_time, [date])

test("month 13") <- (
    D is date(2024, 13, 1),
    D is not _
),
"""


def test_constructor_rejection_noted(capsys, tmp_path):
    p = write(tmp_path, f"d13{SEAM}", CONSTRUCT_REJECT_SRC)
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
-double_quotes(atom)
-import_from(date_time, [date_add, date])

test("unbound timedelta is an instantiation error") <- (
    D is date(2024, 1, 1),
    date_add(D, TD, END),
    END is not _
),
"""


def test_unbound_required_arg_raises_instantiation_error(capsys, tmp_path):
    # date_add/3 has one mode: its timedelta is a required input, so an
    # unbound one is an instantiation_error (and no type note).
    p = write(tmp_path, f"dvar{SEAM}", UNBOUND_TD_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "error(instantiation_error,date_add/3)" in out
    assert "was called with" not in out
