# fix(A11-F024): -> rejection bypassed in term/metacall argument position

`_emit_compound` (prolog_to_clausal.py:553-624) has no `->` handling and `;`
is in _INFIX_MAP, so `q(L) :- findall(X, (c(X) -> t ; e), L).` emits
`findall(X, ->(C(X), t) or e, L)` — no PrologTranslationError, and `->(...)`
is not even valid Python, so users get downstream syntax soup instead of the
designed message. Cut in the same position IS rejected (verified). Sibling of
A10-F001 (body `!` at :271-273) — fix jointly with
fix-A10-pl-cut-emitted-as-dead-goal.md; also `(a ; !)` rides that fix.

**Fix**: route control constructs found in term position through the same
rejection as `_emit_goal`; also reject `*->`.

**Tests**: test_F024_arrow_rejected_in_term_position (xfail),
test_guard_body_ite_rejected, test_guard_cut_rejected_in_metacall_conjunction.
