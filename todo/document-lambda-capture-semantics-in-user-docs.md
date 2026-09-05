# Write the lambda capture semantics into the user-facing docs

**Type:** docs todo. **Status:** the semantics are RATIFIED (operator, 2026-09-06);
this is about surfacing them where a Clausal *author* will read them, not where a
compiler engineer will.

## What to write

The ratified rules, currently living only in the design note
`implementation_plans/prolog-lambda-lowering.md` §11 (a compiler-facing document):

1. **Capture is by-value / copy-at-call.** A lambda `(Params) <- Body` shares the
   enclosing clause's scope; a **bound** capture flows its value in, an **unbound**
   capture is a **fresh variable on each call** — the lambda never binds the
   enclosing variable, and successive calls do not see each other's bindings.
   (This matches `library(yall)`'s default; probe-confirmed as the engine's live
   behavior, 2026-09-06.)

2. **There are no free-sets, and you do not need them.** Sharing is what a clause
   body already gives you (its variables share by default); a lambda is the
   copy-per-application tool. When you want a value *out* of a higher-order call,
   it comes back as an **argument** of the relation (thread accumulators through
   the HOF's params, let a `find`-style HOF bind a `Result` argument, let
   `findall`/`bagof` return their list) — never through a captured variable. If you
   want sharing, don't reach for a lambda: write the goals inline in the clause
   you're already in.

## Where

The user-facing lambda documentation (wherever `<-` lambdas are introduced for
authors — the language guide / tutorial, not the implementation_plans/ tree). Keep
it short and rule-shaped; the *why* (the four arguments against free-sets, the
∀/∃ scoping, the copy_term footgun) stays in §11 for anyone who wants it, linked.

## Source

`implementation_plans/prolog-lambda-lowering.md` §11 — the "probe result",
"Should free-sets exist at all?" and ratification-banner subsections carry the
full reasoning and the confirmed examples to adapt.
