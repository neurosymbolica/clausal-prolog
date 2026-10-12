# Two error-path bugs found by the catch/3 review (2026-10-13; on main 7c0379db)

**Status: FIXED 2026-10-13 (commits aa07babd, 523e918f).** The shallow builder now forces a generator body (`_stmts_force_generator`), and a special-form name written with fewer arguments builds its closure cell (`call_body.is_special_form_closure`). Pinned in tests/test_shallow_predicate_with_no_yielding_clause_fails.py and tests/test_call_n_control_construct_closure.py.

1. **A shallow predicate with no matching clause raises TypeError.** If none of a shallow
   predicate's clauses yield, it returns None. Calling it with a head that no clause matches then
   raises `TypeError: 'NoneType' object is not iterable` instead of failing.
   Repro: `-shallow([c3/1])`, `c3(2) <- throw(z)`, then `solve(("c3", 1), m)`.
   An over-catching catch/3 used to hide it.
2. **`call(catch(G), C, R)` raises `existence_error(procedure, catch/1)`** in both strategies.
   ISO call/N adds the arguments to the closure, so this is catch/3. Scryer and Trealla both run it.
