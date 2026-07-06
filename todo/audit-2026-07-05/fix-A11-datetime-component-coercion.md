# fix(A11-F015): date/time/datetime/timedelta ctors int()-truncate float components

`modules/py/datetime.py:88,125,153,184` wrap every component in `int(...)`:
`date(2020.9, 1.9, 5, D)` silently constructs `date(2020,1,5)` (a month
computed as 1.9 becomes January); numeric strings parse. stdlib
`datetime.date` raises TypeError for both.

**Fix** (A11-D002): reject floats (at minimum floats with a fractional part);
decide separately whether numeric-string convenience stays. Fail or raise a
typed error — never truncate.

**Tests**: test_F015_date4_rejects_float_components (xfail),
test_F015_guard_date4_construct_and_decompose (guard).
