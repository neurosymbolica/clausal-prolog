# SegList vs Compiler: String Binding Asymmetry

**Status:** RESOLVED in Phase 7. All paths now bind star vars to substrings.

## What Changed (Phase 7)

The asymmetry between compiler head patterns and SegList/body paths has been
eliminated. All paths now preserve string type when matching strings:

| Path | Pattern | Input | Star binding |
|------|---------|-------|-------------|
| Compiler head | `[H, *T]` | `"hello"` | `T = "ello"` (str) |
| SegList runtime | `SegList([VarSeg(A)])` | `"hello"` | `A = "hello"` (str) |
| `_body_multi_star_unify` | `[*A, ',', *B]` | `"a,b"` | `A = "a"`, `B = "b"` (str) |
| `Append/3` builtin | `Append(X, Y, "hello")` | `"hello"` | `X = "he"`, `Y = "llo"` (str) |

### Key changes:

1. **`SegList.__unify__`**: No longer converts strings to char lists before
   passing to `_seglist_unify_gen`. String slicing naturally returns substrings.

2. **`_body_multi_star_unify`**: Removed `d = list(d)` conversion for string
   targets. Star vars bind to substrings via string slicing.

3. **`SegList.__walk__`**: Handles VarSegs bound to strings by expanding to
   char lists (since SegList is inherently a list structure).

4. **`SegString`**: New type analogous to SegList but backed by string segments.
   Used for representing partial strings. VarSegs bind to substrings.

5. **`_build_star_list` / `_build_multi_star_list`**: Return strings when all
   parts are string-compatible.
