"""clausal.modules.py.datetime — Date/time predicates under the ``py.datetime`` name.

Re-exports everything from :mod:`clausal.modules.date_time` so that
``.clausal`` files can use the familiar name::

    -import_from(py.datetime, [Now, Today, Date, TimeDelta])
"""

from clausal.modules.date_time import (  # noqa: F401
    Now,
    NowUTC,
    Today,
    Date,
    Time,
    DateTime,
    TimeDelta,
    DateAdd,
    DateSub,
    DateDiff,
    FormatDate,
    ParseDate,
    DayOfWeek,
    DateBetween,
)
