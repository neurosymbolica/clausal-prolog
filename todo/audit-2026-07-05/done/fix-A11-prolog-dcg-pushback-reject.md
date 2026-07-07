# fix(A11-F039): DCG pushback heads emit silent garbage instead of a clear error

`_emit_head` (prolog_to_clausal.py:250-261) has no `,/2` case:
`h, [t] --> b.` → `,(h, [t]) >> (b)` — invalid Python, emitted silently.
Same shape for user-op/3 clause heads (`a === b.` → `===(a, b),` with
`xfx`/`===` polluting -private). prolog_translation.md's "known roundtrip
limitations" mentions pushback only as a re-parse issue, not a forward-leg
corruption.

**Fix**: raise PrologTranslationError with a clear "DCG pushback not
supported" (or implement pushback); reject non-callable heads.

**Test**: test_F039_dcg_pushback_clear_error_or_valid (xfail).
