# SegList vs Compiler: String Binding Asymmetry

**Status:** Known asymmetry, not a bug. Defer to Phase 7 (SegString).

**Affects:** SegList pattern matching on strings vs compiled head pattern matching on strings.

## The Asymmetry

When a string is matched by a list pattern with star variables, the type bound to
the star variable differs depending on which code path handles it:

| Path | Pattern | Input | Star binding |
|------|---------|-------|-------------|
| Compiler head | `[H, *T]` | `"hello"` | `T = "ello"` (str) |
| SegList runtime | `SegList([VarSeg(A)])` | `"hello"` | `A = ['h','e','l','l','o']` (list) |
| `_body_multi_star_unify` | `[*A, ',', *B]` | `"a,b"` | `A = ['a']`, `B = ['b']` (lists) |
| `Append/3` builtin | `Append(X, Y, "hello")` | `"hello"` | `X = "he"`, `Y = "llo"` (str) |

The compiler path (head patterns) preserves string type because Python string slicing
returns strings: `"hello"[1:]` → `"ello"`. The SegList/body path converts to a char list
via `list("hello")` → `['h','e','l','l','o']` before splitting.

## Why It Matters

A user writing:

```clausal
split_at_comma([*Before, ',', *After], Before, After)
```

Gets different result types depending on whether the pattern is in a clause head
(compiler path) or in a body-position unification (SegList path). In practice, most
patterns are in heads, so the string-preserving behavior dominates.

## Resolution: SegString (Phase 7)

A `SegString` type analogous to `SegList` but backed by string segments would:
- Bind VarSegs to substrings instead of char lists
- Avoid O(n) `list()` conversion for large strings
- Make all paths consistent: star vars always bind to strings when matching strings

This is an optimization/ergonomics improvement, not a correctness fix. Both behaviors
are logically correct — the difference is only in Python-level type of the result.

## Workaround

Users who need string results from body-position star patterns can reconstruct:
```clausal
split_at_comma(Str, Before, After) <- (
    [*B, ',', *A] = Str,
    AtomChars(Before, B),
    AtomChars(After, A)
)
```

## Files Involved

- `clausal/terms.py` — `SegList.__unify__` converts string to char list (line ~289)
- `clausal/logic/compiler.py` — `_head_list_unify_input` preserves string type (line ~226)
- `clausal/logic/compiler.py` — `_body_multi_star_unify` converts string to char list (line ~437)
