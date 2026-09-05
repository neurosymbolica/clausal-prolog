# Advisory lint: implicit capture in `<-` lambdas

**Type:** engine todo (translator/lint), advisory — NOT a gate.

## What

A `<-` lambda `(P1, ..., Pn) <- Body` shares its enclosing clause's variable
scope. Its variables partition three ways:

- **parameters** — the head tuple `(P1..Pn)`; explicit, fresh per call.
- **captures** — a Body variable that also appears in the enclosing clause;
  its value flows in (see the capture-semantics section of
  `implementation_plans/prolog-lambda-lowering.md`).
- **body-locals** — a Body variable appearing nowhere else.

Emit an ADVISORY warning naming each **capture** — "lambda at <loc> captures
<var> from the enclosing clause". Same channel and spirit as the singleton
lint. It is visibility, not a guard: a capture is legitimate (usually
intended); the lint makes the deliberate ones auditable and surfaces the rare
accidental one (a body-local that collided with an enclosing name).

## Why advisory, not a guard (operator ruling, 2026-09-05)

Same-name-means-shared is the ratified rule and is programmer-managed; an
accidental collision is no worse than any other accidental same-naming, which
logic programming does not hand-hold. So this is a signal, never a refusal.
`-allow_captures` / per-lambda suppression mirrors `-allow_singletons` if the
noise ever warrants it.

## Depends on

The capture-semantics ratification (doc section, `prolog-lambda-lowering.md`)
— the lint's partition (capture vs body-local) is only well-defined once
"what a capture means at runtime" is pinned. Land the semantics first.

## Not in scope

Export-side lambda lifting (class-c) — that is the ladder's separate concern;
this lint is a source-surface advisory for the Clausal author.
