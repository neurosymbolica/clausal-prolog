# fix(A02-F004): multi-star head — trailing fixed elements after the last star unify at index 0

**Finding:** `docs/superpowers/audits/2026-07-05-fable-partition/02-compiler-heads/findings.md` A02-F004
**Tests:** `tests/audit_2026_07_05/test_02_compiler_heads.py::TestF004MultiStarTrailingFixed` (4 xfail — flip to pass)

## Bug

`_compile_multi_star_guard` (`head_match.py`) walks segments left-to-right
tracking the current position as `pos_const + sum(pos_sp)`. On the LAST star
it computes the star's slice end as `n - trailing_fixed`, then resets

    pos_const = 0
    pos_sp = []          # head_match.py:795-801

with a comment claiming trailing fixed elements "were already counted above"
— they were not: the loop still visits the trailing `("fixed", …)` segment
and emits `unify(elem, _d[_pos_expr() + j])` (`:736-748`), which now indexes
from **0**. So `[*A, 1, *B, 2]` vs `[1, 2]` emits `unify(2, _d[0])` → fails;
every ground/input call of a trailing-fixed multi-star head fails (or, when
`d[j]` coincidentally equals the trailing literal, yields wrong splits —
e.g. `[*A, x, *B, x]` shapes). Output mode (unbound caller →
`$build_multi_star_list`) is unaffected, as is the single-star runtime path
(`$head_list_unify_input` handles its `after` list correctly).

Repros: `ms3([1,2],A,B)`, `mst([0,1,5,2,3],A,B)` (two trailing fixed),
`mchr("xayb",A,B)` (str caller, char fixed elems) — all `[]`.

## Fix direction

After the last star, set the position to the star's `end_expr` instead of
resetting to zero — e.g. track a flag `after_last_star` and for trailing
fixed segments emit indices `n - trailing_remaining + j` (mirror of how
`end_expr` was computed), or simply keep `pos = end_expr` symbolically:
replace the reset with `pos_const/pos_sp := (n - trailing_fixed)`
represented as an AST expression (the `_pos_expr` machinery only handles
const+sp-names, so the cleanest patch is a dedicated index expression for
post-last-star segments: `BinOp(n_name - Constant(trailing_total - offset_of_this_segment) + j)`).
Multiple trailing fixed SEGMENTS cannot occur (adjacent fixed segments
merge), but two trailing fixed ELEMENTS do — `mst` covers that.

Also verify `[*A, x, *B, y, *C, z]`-style (fixed after a non-final star is
already correct; only post-LAST-star segments change).

## Acceptance

- 4 xfails flip; the 6 controls (between-stars fixed, adjacent stars,
  enumeration, int-code-vs-bytes, output construction incl. trailing fixed,
  single-star trailing fixed) stay green.
- `tests/` multi-star suites stay green (per-file runs).
