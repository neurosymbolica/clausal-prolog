# Asyncio demo: a solver that waits on the world

Filed 2026-10-06 with the "What it is for" section of docs/asyncio.md. The
operator asked for a demo: async waiting "would really simplify lots of the
temporal issues of dealing with real world problems that neurosymbolic
systems will encounter". The demo should make that concrete, in one runnable
example rather than a toy benchmark.

## Proposal: lazy generate-and-test with a model, a remote fact base and a person

One query, three kinds of wait:

1. **Model candidates as choice points.** `await_each/2` over a stream of
   candidate answers sampled from a model. Backtracking asks for the next
   candidate only when logic rejects the current one. The demo counts how
   many samples the proof consumed.
2. **A remote relation.** Check candidates against facts held elsewhere (a
   SQLite file via an async driver, or a small local HTTP service). Only the
   rows the proof touches are fetched.
3. **An askable predicate.** When the rules can't decide, ask a person:
   the query suspends on a web form or a terminal prompt and resumes with the
   answer.

Around it, run many such queries concurrently (one per user or task), with a
timeout on each and a semaphore bounding model calls in flight. Show the
event loop staying responsive.

The model must be replaceable by a deterministic fake (a scripted async
generator), so the demo runs in CI with no network, API key or GPU. With
`clausal-decide` installed, the real model is a drop-in.

## Where it goes

- `clausal/examples/asyncio_demo/` (or `examples/` at the root if it needs
  non-engine dependencies), with a README.
- A `test/1` or pytest run of the fake-model version, so it can't rot.
- Linked from docs/asyncio.md "What it is for".

## Smaller demos, if the big one is too much at once

- **Racing:** the same problem in two formulations (say CLP(Z) and a
  generate-and-test), first answer wins, the loser is cancelled.
- **Event stream:** `await_each/2` over a simulated sensor feed, with rules
  joining events to the database (complex event processing).
- **Simulation:** queries as processes under a virtual-clock loop, where
  `sleep/1` is simulated time.

## Depends on / would benefit from

- `todo/asyncio-follow-ups-2026-10-06.md` item 2, `concurrent_all(Goals)`,
  for concurrency expressed in Prolog rather than Python.
- A text-friendly `async_predicate` option (convert chars carriers with
  `to_text` automatically), since most model and HTTP adapters take text.
