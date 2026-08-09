# TODO (DX, optional): lint/warn on `X is not <pattern-with-wildcard>`

**Opened 2026-06-25** from real-world exercise. **Not a correctness bug** — this is
`is not` (= `dif/2`) behaving exactly as specified. It is a high-cost *footgun*: it
silently turns a clause guard into an always-true goal, and aligns with the project
side-goal of hardening Clausal via real use. Treat as a diagnostic enhancement.

## The footgun

`X is not P` is disequality: it succeeds unless `X` is *identical* to `P`. When `P`
contains an unbound var (a `_` wildcard or fresh var), authors routinely *intend*
"X does not match the shape P" — but `dif(X, foo(_))` compares against a fresh `_`,
so it **succeeds for `foo("a")`**. The guard never fails, both clauses of a
disjoint-guarded pair fire, and solutions multiply.

```clausal
-private([tag(X)])
bad(S)  <- (S is not tag(_))        # WRONG: succeeds even for tag("a")
good(S) <- (not (S is tag(_)))      # RIGHT: fails exactly when S matches tag(_)
```

Real impact: this was the second root cause of a 3^N solution explosion in a
downstream helper library's own 6-arity dispatcher predicate (`STATUS is not unmet(_)`
double-firing); it cost significant debugging time because the symptom (solution
blow-up) is far from the cause. See that downstream consumer's own cheat-sheet
§2e for the write-up.

## Proposed

A load-time **warning** (not error) when the RHS of `is not` is a compound/list
containing one or more unbound variables — message suggesting `not (X is P)` if
pattern non-matching was intended, or `dif` with a ground term for disequality.
Scalars / ground RHS (`X is not 0`, `K is not "key"`, `KEYS is not []`) must NOT
warn — those are the correct, common uses. Consider a pragma/comment to suppress
when `dif`-against-a-partial-term is genuinely intended.

## Done when

- Loading a clause with `X is not f(...,_,...)` (unbound var in RHS) emits a
  warning; ground-RHS `is not` stays silent.
- A couple of tests pin both the warn and no-warn cases.
- (Open design Q: is `dif` against a partial term ever *intended* in practice? If
  rarely, a warning is clearly net-positive; if sometimes, gate behind a lint flag.)
