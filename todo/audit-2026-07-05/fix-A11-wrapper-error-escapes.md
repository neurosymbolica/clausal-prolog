# fix(A11-F016–F019): raw stdlib exceptions escape from url/http/hash/date_between

Outliers against the wrappers' own fail-clean majority (json/csv/files/
date_diff/days_between all catch and fail):

- F016 `date_between/3` (datetime.py:377-388): `isinstance(start, date)`
  passes for datetime (subclass), then `current <= end` raises TypeError on a
  date/datetime mix. Siblings catch it.
- F017 `url.parse` (url.py:48-49): `ParseResult.port` raises ValueError on
  out-of-range/non-numeric port; no try/except.
- F018 `http.get/post/request` (http.py:52-63): `_do_request` catches only
  (OSError, URLError); `urlopen("not-a-url")` raises ValueError.
- F019 `hash/3` (hash.py:39-44): shake_128/shake_256 need hexdigest(length);
  bare call raises TypeError (only ValueError from hashlib.new caught).

**Fix**: widen the except tuples / add the missing guards so all four fail
cleanly (A11-D001 interim); the deeper fail-vs-throw policy is D001.

**Tests**: test_F016…test_F019 (xfail) + test_F019_guard_hash_sha256.
