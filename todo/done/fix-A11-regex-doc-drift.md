# fix(A11-F008/F009): regex doc drift — unmatched-optional-group None; findall docstring

- F008 (design, A11-D004): an unmatched optional named group auto-binds Python
  `None` (Python-consistent; SWI omits the key). Undocumented. Decision
  recommendation: keep + document in regex.md Gotchas.
- F009: `findall/3` docstring (modules/py/re.py:141-146) claims "each match is
  a tuple of group strings"; a single-group pattern yields bare strings
  (matches the re.findall oracle — behavior right, docstring wrong).

**Tests** (current-behavior guards, flip docs not code):
test_F008_guard_unmatched_optional_group_binds_none,
test_F009_guard_findall_single_group_is_string.
