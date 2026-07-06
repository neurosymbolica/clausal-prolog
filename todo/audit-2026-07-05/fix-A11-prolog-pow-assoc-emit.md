# fix(A11-F030): _emit_expr emits all ops left-assoc — (2**3)**2 becomes 2 ** 3 ** 2

`prolog_to_clausal.py:651-659` parenthesizes left child at my_prec and right
at my_prec+1 (left-assoc for ALL ops). Python `**` is right-associative:
`q(X) :- X is (2 ** 3) ** 2.` (Prolog value 64) emits `X := 2 ** 3 ** 2`
(Python value 512). The reverse emitter (`clausal_to_prolog._emit_infix`)
handles this correctly (guarded).

**Fix**: per-op associativity in _emit_expr (right-assoc for `**`).

**Tests**: test_F030_pow_grouping_preserved (xfail),
test_guard_pow_emit_parse_fixpoint_c2p (guard).
