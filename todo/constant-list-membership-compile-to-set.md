# Compile constant-list membership `X in [c1, c2, …]` to a Python set

**Requested:** 2026-07-04. Membership tests against a **ground constant list** are common in the EU
corpus (e.g. MAR `dealing_permitted`: `ACTION in ["acquire","dispose","amend","cancel"]`, and the
Art 9 safe-harbour list). Today `X in LIST` / `in_(X, LIST)` is a linear scan, and the same literal
list is often written several times in one file.

## Idea
When the right operand of `in`/`in_` is a **fully ground list literal**, the compiler can lower it to
a Python **set membership** in the emitted AST — `x in {c1, c2, c3}` — which is O(1) and builds the
frozenset once at load. Only valid when every element is ground (atoms, numbers, strings); if any
element is a var, fall back to the current relational scan (which must stay, for the enumerating
mode `member(X, L)` with X unbound).

Elements are `PredicateMeta` atoms (hashable, identity-equal), numbers, strings — all hashable, so a
frozenset works. Guard: only apply in the **check** mode (ground X against ground list); keep the
relational scan when X is unbound or the list is partial.

## Example (MAR insider-dealing, dealing_permitted)
```clausal
dealing_permitted(TRADE, INFO, PERMITTED) <- (
    ...,
    ACTION in [acquire, dispose, amend, cancel],   # ground list -> compile to `ACTION in {..}`
    ...
)
```
(Corpus-side, the repeated literal is also being factored into a `regulated_action/1` fact set —
first-argument indexed, so already better than a linear list scan; the compiler optimisation would
make the inline `in [..]` form fast too, without needing the helper predicate.)

## Acceptance
`X in [ground, ground, …]` in check mode compiles to frozenset membership; enumerating mode
(`X in L`, X unbound) unchanged; a bench over a large constant list shows O(1) not O(n).
