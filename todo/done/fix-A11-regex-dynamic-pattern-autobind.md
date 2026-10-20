# fix(A11-F007): dynamic regex patterns silently skip named-group auto-binding

`goal_expansion.py:252-254` (A10 file) only expands literal patterns, so
`Dyn(P, S, YEAR) <- match(P, S)` called with `P = r"(?P<YEAR>\d+)"` succeeds
with YEAR left UNBOUND — silently wrong downstream. docs/regex.md "Dynamic
Patterns" (:271-287) warns only about precompilation, never about lost
auto-binding.

**Fix directions**: (a) document in regex.md Gotchas (minimum); (b) runtime
named-group fallback in match/2 when the pattern derefs to a string with named
groups whose names match caller vars is NOT statically knowable — so prefer
(a) plus a load-time warning when a match/search goal has an extra ALLCAPS var
and a non-literal pattern.

**Test**: test_F007_dynamic_pattern_autobind_or_documented (xfail).
