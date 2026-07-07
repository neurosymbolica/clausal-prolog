# fix(A11-F003): regex goal expansion hijacks any predicate named match/search

`logic/goal_expansion.py:242-248` gates only on the short name — a
user-defined `match/2` receives `re.compile('hello')` instead of its literal
arg, and a CAPS-group literal rewrites the call to arity 3 → raw TypeError.
The `nargs == 3` precompile path (:263-265) fires on user `match/3` too.

**Fix** (A11-D003): verify the bound object identity against
`clausal.modules.py.re` through the module dict before expanding — exactly the
`_is_reflection_goal` pattern in the same file (:338-357).

**Note**: file belongs to A10 (goal_expansion); complements A10-F005 (do both
in one change). **Test**: test_F003_user_defined_match_not_hijacked (xfail).
