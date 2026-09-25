"""Date-family values as query args: the TERM is the argument, the object is refused.

RULED 2026-09-14/15: a date is the term ``('date', Y, M, D)`` (datetime/time/
timedelta likewise) and a Python datetime object is not a term. ``date/3``
yields the term; the builtins consume it; a caller passes it.

HISTORY, because the door this file used to hold open is the bug it now pins
shut. ab0dabcd (2026-09-02, before the ruling) let a DIRECT ground query arg
that was a Python datetime be PARAMETERIZED by ``_templatize_query_goal`` --
the object bound to a Var on the trail by reference, never lowered -- while a
NESTED one lowered through ``term_to_ast_expr``. When the nested route was made
to refuse (2026-09-15) the direct route was left as it was, and harness-date-
migration measured the consequence on 2026-09-16: a bare Python date bound by
reference unifies with nothing a rulebase produces any more, so the goal
silently yields NO solutions -- the quiet-wrong shape ruling (b) exists to
exclude -- while the same value nested in a list is refused loudly. The
parameterization of datetimes is retired here, so both routes refuse and the
message names the term to write.

``call(functor, *args)`` is a third door: it does no lowering at all, and is
the "runtime object route" the section-4 answer sequences for a later uniform
refusal. It is deliberately not touched by this file.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest

import clausal.import_hook  # noqa: F401
from clausal.import_hook import _load_module
from clausal import Var, solve
from clausal.logic.variables import deref


def _load(tmp_path, name, text):
    src = tmp_path / f"{name}.clausal"
    src.write_text(text)
    return _load_module(name, str(src))


def _solutions(goal, out=None, *, module=None):
    """Solution count, capturing ``deref(out)`` per solution while the trail
    bindings are still live.

    P2: a cell goal carries no module and ``solve`` refuses to guess one
    (R-P2-2, module locality), so the caller passes the module the goal's
    predicate came off."""
    vals = []
    for _ in solve(goal, module):
        vals.append(deref(out) if out is not None else True)
        if len(vals) > 3:
            break
    return vals


D1 = ("date", 2024, 1, 1)
D2 = ("date", 2024, 1, 2)


def test_a_date_term_arg_unifies_by_value(tmp_path):
    mod = _load(tmp_path, "dq_a", "same_day(D, D),\n")
    x = Var()
    assert _solutions(("same_day", D1, x), x, module=mod) == [D1]
    assert len(_solutions(("same_day", D1, ("date", 2024, 1, 1)), module=mod)) == 1
    assert _solutions(("same_day", D1, D2), module=mod) == []


def test_a_date_term_does_not_unify_with_a_ymd_list(tmp_path):
    mod = _load(tmp_path, "dq_b", "same_day(D, D),\n")
    assert _solutions(("same_day", D1, [2024, 1, 1]), module=mod) == []


def test_a_date_term_arg_flows_into_the_date_time_builtins(tmp_path):
    mod = _load(
        tmp_path, "dq_c",
        "-import_from(date_time, [days_between, date])\n"
        "\n"
        "window(REF, N) <- (EPOCH is date(2024, 1, 1), days_between(REF, EPOCH, N))\n",
    )
    n = Var()
    expected = (date(2024, 6, 1) - date(2024, 1, 1)).days
    assert _solutions(("window", ("date", 2024, 6, 1), n), n, module=mod) == [expected]


def test_distinct_date_term_args_all_answer(tmp_path):
    # The old test also pinned "ONE compiled query for 20 dates": that was the
    # parameterization of the OBJECT, which is gone. A ground tuple takes the
    # value-keyed cache today; whether ground cell tuples should be
    # parameterized like scalars is a separate (performance) question.
    mod = _load(tmp_path, "dq_d", "echo(D, D),\n")

    def run(d):
        v = Var()
        for _ in solve(("echo", d, v), mod):
            return deref(v)
        return None

    days = [("date", 2024, 1, 1 + i) for i in range(20)]
    assert [run(d) for d in days] == days


def test_datetime_time_timedelta_TERM_args_echo(tmp_path):
    mod = _load(tmp_path, "dq_e", "echo(D, D),\n")
    for value in (
        ("datetime", 2024, 1, 1, 12, 30, 15, 250),
        ("datetime", 2024, 1, 1, 12, 30, 0, 0, 0),     # aware: ninth field, UTC offset in minutes
        ("time", 23, 59, 59, 0),
        ("timedelta", 3, 71, 0),
    ):
        v = Var()
        assert _solutions(("echo", value, v), v, module=mod) == [value], f"{value!r}"


def test_a_BARE_python_datetime_query_arg_is_refused_and_names_the_term(tmp_path):
    """The door is shut: a bare Python datetime meets the same refusal a nested
    one does, instead of binding by reference and quietly answering nothing."""
    mod = _load(tmp_path, "dq_g", "same_day(D, D),\n")
    for value, form in (
        (date(2024, 5, 5), "('date', 2024, 5, 5)"),
        (datetime(2024, 11, 3, 1, 30), "('datetime', 2024, 11, 3, 1, 30, 0, 0)"),
        (time(12, 0), "('time', 12, 0, 0, 0)"),
        (timedelta(days=3), "('timedelta', 3, 0, 0)"),
    ):
        with pytest.raises(NotImplementedError) as exc:
            _solutions(("same_day", value, Var()), module=mod)
        assert form in str(exc.value), str(exc.value)


def test_a_NESTED_python_datetime_is_refused(tmp_path):
    """The nested route, refused since 2026-09-15; kept so both doors are pinned
    side by side."""
    from clausal.logic.compiler.terms_to_ast import term_to_ast_expr

    for value in (date(2024, 5, 5),
                  datetime(2024, 11, 3, 1, 30, fold=1),
                  time(12, 0),
                  timedelta(days=3)):
        with pytest.raises(NotImplementedError):
            term_to_ast_expr([value], {})


def test_the_ruled_term_form_is_what_a_nested_caller_passes(tmp_path):
    """And it is simpler than either the object or the `[Y, M, D]` + `Date/4`
    dance this file's docstring records: ordinary data, no reconstruction."""
    mod = _load(tmp_path, "dq_f", "heads(L, H) <- (L is [H, *_REST])\n")
    h = Var()
    assert _solutions(
        ("heads", [("date", 2024, 5, 5), ("date", 2024, 5, 6)], h), h
    , module=mod) == [("date", 2024, 5, 5)]
