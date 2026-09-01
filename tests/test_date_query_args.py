"""`datetime.date` (and datetime/time/timedelta) as first-class query-arg terms.

The runtime always treated these as first-class terms — `Date/4` binds a real
`datetime.date`, `DaysBetween`/`DateAdd` consume them, they unify by value and
hash into tabling — but the input-lowering path rejected them:
`term_to_ast_expr: unsupported term type date`, forcing the `[Y, M, D]` triple
+ `Date/4` reconstruction dance on every Python-interop caller
(todo/date-as-first-class-term-type.md).

Two coordinated paths:
- a DIRECT ground query arg is parameterized (`_templatize_query_goal`), so the
  object is bound at runtime by reference — no reconstruction, tz-aware values
  included, and distinct dates reuse ONE compiled query like ints do;
- a NESTED occurrence (inside a list/compound arg, which templatization leaves
  structural) lowers through a `term_to_ast_expr` reconstruction branch.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import clausal.import_hook  # noqa: F401
from clausal.import_hook import _load_module
from clausal import Var, solve
from clausal.logic import solve as _solve_mod
from clausal.logic.variables import deref


def _load(tmp_path, name, text):
    src = tmp_path / f"{name}.clausal"
    src.write_text(text)
    return _load_module(name, str(src))


def _solutions(goal, out=None):
    """Solution count, capturing ``deref(out)`` per solution while the trail
    bindings are still live."""
    vals = []
    for _ in solve(goal):
        vals.append(deref(out) if out is not None else True)
        if len(vals) > 3:
            break
    return vals


def test_date_arg_unifies_by_value(tmp_path):
    mod = _load(tmp_path, "dq_a", "same_day(D, D),\n")
    x = Var()
    assert _solutions(mod.same_day(date(2024, 1, 1), x), x) == [date(2024, 1, 1)]
    assert len(_solutions(mod.same_day(date(2024, 1, 1), date(2024, 1, 1)))) == 1
    assert _solutions(mod.same_day(date(2024, 1, 1), date(2024, 1, 2))) == []


def test_date_does_not_unify_with_ymd_triple(tmp_path):
    mod = _load(tmp_path, "dq_b", "same_day(D, D),\n")
    assert _solutions(mod.same_day(date(2024, 1, 1), [2024, 1, 1])) == []


def test_date_arg_flows_into_date_time_builtins(tmp_path):
    mod = _load(
        tmp_path, "dq_c",
        "-import_from(date_time, [days_between, date])\n"
        "\n"
        "window(REF, N) <- (date(2024, 1, 1, EPOCH), days_between(REF, EPOCH, N))\n",
    )
    n = Var()
    expected = (date(2024, 6, 1) - date(2024, 1, 1)).days
    assert _solutions(mod.window(date(2024, 6, 1), n), n) == [expected]


def test_distinct_date_args_reuse_one_compiled_query(tmp_path):
    mod = _load(tmp_path, "dq_d", "echo(D, D),\n")
    _solve_mod._query_cache.clear()

    def run(d):
        v = Var()
        for _ in solve(mod.echo(d, v)):
            return deref(v)
        return None

    days = [date(2024, 1, 1) + timedelta(days=i) for i in range(20)]
    assert [run(d) for d in days] == days
    assert len(_solve_mod._query_cache) == 1


def test_datetime_time_timedelta_args(tmp_path):
    mod = _load(tmp_path, "dq_e", "echo(D, D),\n")
    for value in (
        datetime(2024, 1, 1, 12, 30, 15, 250),
        datetime(2024, 1, 1, 12, 30, tzinfo=timezone.utc),  # tz-aware: by ref
        time(23, 59, 59),
        timedelta(days=3, seconds=71),
    ):
        v = Var()
        assert _solutions(mod.echo(value, v), v) == [value], f"{value!r}"


def test_date_nested_in_a_list_arg(tmp_path):
    # A structural arg is NOT parameterized — the date inside it must lower
    # through the term_to_ast_expr reconstruction branch.
    mod = _load(tmp_path, "dq_f", "heads(L, H) <- (L is [H, *_REST])\n")
    h = Var()
    assert _solutions(mod.heads([date(2024, 5, 5), date(2024, 5, 6)], h), h) == [
        date(2024, 5, 5)
    ]


def test_naive_datetime_and_timedelta_nested_in_a_list_arg(tmp_path):
    mod = _load(tmp_path, "dq_g", "heads(L, H) <- (L is [H, *_REST])\n")
    for value in (datetime(2024, 1, 2, 3, 4, 5, 6), time(1, 2, 3),
                  timedelta(hours=2)):
        h = Var()
        assert _solutions(mod.heads([value, "sentinel"], h), h) == [value], f"{value!r}"
