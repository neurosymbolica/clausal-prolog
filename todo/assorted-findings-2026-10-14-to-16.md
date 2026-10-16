# Assorted findings, 2026-10-14 to 10-16, not yet filed on their own

Collected during the batch 1–4 reviews. Each needs a repro written down before it is worked on.

1. **Seam head with a SET containing a variable never matches** (silent wrong "no").
2. **Variable dict keys fail loudly** in seam heads (error instead of matching).
3. **`++Rec(...)` records in a seam head never match.**
4. **`LogicException.__repr__` is not cycle-safe** (a cyclic culprit can recurse when the exception is printed; raise-time copy falls back to the uncopied term).
5. **dump/3's type_error prints a Python repr** of the culprit.
6. **Printing huge integers is slow** (quadratic str conversion path).
7. **Parser test gaps** noted by the batch-1 reviewer (operand priority, yf, `{}`/`[]` functors): cover the remaining edge rows.
8. **Stale xfail marks**: a downstream run saw 2 xfail-marked tests xpassing; find them (pytest -rX) and remove the marks.
9. **Operator questions still open with Mike**: D60 (lenient number lexing: 0X1, 1E9, 0B1, 0'', raw tab, unknown escapes; the lexer-tightening branch 8bd6b036+e9d0c7c3 HELD) and D62 (char-list answers print as "a" vs [a]).
