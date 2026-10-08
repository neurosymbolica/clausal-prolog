# must_be(list, L) on a partial list should be an instantiation error

Found 2026-10-08 while checking the closed-partial-list fix.

    must_be(list, [a|_])     ->  type_error(list, [a|_])          today
                             ->  instantiation_error               ISO, Scryer

A partial list is not yet known not to be a list, so ISO (and Scryer's `library(error)`) raises
`instantiation_error`; `type_error(list, _)` is for a term that can never become a list
(`[a|b]`, `foo`). The decision is `must_be`'s `list` row in
`clausal/logic/builtins/type_checks.py`, which now asks `seg_closed` for a Seg* term; an open
Seg* (or an unbound tail) should raise the instantiation error instead of the type error. Check
`is_list/1` stays a plain failure (it is a type test, not a check).
