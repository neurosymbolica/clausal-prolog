# Seam: a tuple head whose first element is a variable leaves its arguments unbound

**Status: OPEN, unverified beyond one report.** Seen 2026-11-04 in code review: a seam predicate
`k((A, B), N, R)` called with `(1, 2)` answers with `A` and `B` unbound, with TRO on or off. A
tuple whose first element is an atom (`('f', A)`) is read as a compound and binds normally.

Check whether the seam lowers a tuple head with a variable first element as something other than
the 2-tuple data it denotes, and what `(1, 2)` unifies with there. Then either fix it, or refuse
the head at load with a named error. Compare with the `.clausal` `k((A, B), N, R)`, which reads
`(A, B)` as `','(A, B)`.
