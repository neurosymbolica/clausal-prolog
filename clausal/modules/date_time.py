"""Backward compatibility — canonical implementation in clausal.modules.py.datetime."""
from clausal.modules.py.datetime import *  # noqa: F401,F403
from clausal.modules.py.datetime import (  # noqa: F401 — re-export internals for tests
    _DateTimePredicate, _simple_to_trampoline,
    _now_1, _now_utc_1, _today_1, _date_4, _time_4, _datetime_7,
    _timedelta_3, _date_add_3, _date_sub_3, _date_diff_3,
    _format_date_3, _parse_date_3, _day_of_week_2, _date_between_3,
)
