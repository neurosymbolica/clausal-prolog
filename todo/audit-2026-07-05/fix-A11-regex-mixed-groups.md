# fix(A11-F006): mixed named+positional regex groups drop the positional values

`_groups_dict` (modules/py/re.py:46-58) returns `groupdict()` alone whenever
any named group exists: `match(r"(?P<A>\d+)-(\d+)", "1-2", G)` → `{'A':'1'}`;
group 2's value is unreachable by any documented means. SWI re_matchsub
exposes numbered keys; docs/regex.md:57 says "dict of named groups (or tuple
of positional groups)" — the mixed case silently drops data.

**Fix**: include numbered keys for unnamed groups when both kinds are present
(document the dict shape), or document the limitation loudly.

**Test**: test_F006_mixed_groups_expose_positional_values (xfail).
