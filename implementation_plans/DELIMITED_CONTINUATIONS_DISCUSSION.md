# Delimited Continuations in Clausal — Discussion

Not a plan. A collection of observations, trade-offs, and candidate designs for
what a `shift`/`reset`-equivalent facility should look like in Clausal, given
that our execution model is already Python generators driving a trail.

The starting premise (from the user): *delimited continuations are "mixing two
backtrackable threads" — can we express that Pythonically with generators
instead of importing reset/shift wholesale from Scheme/SWI?*

---

## What reset/shift actually buy you

In SWI/Scryer, `reset(Goal, Ball, Cont)` runs `Goal`; if `Goal` calls
`shift(Ball)`, the reset returns with `Cont` bound to a first-class term
representing "the rest of `Goal` after the shift point". Calling `Cont`
resumes execution from there. `Cont` may be called zero, one, or many times.

The practical use cases split cleanly:

| Use case                       | How many times Cont is called |
|--------------------------------|-------------------------------|
| Effect handlers (state, IO)    | exactly once                  |
| Early abort / custom exceptions| zero                          |
| Tabling with aggregation       | once (per answer)             |
| DCG-style translation          | once                          |
| Generator-style "yield" in Prolog | once per consumer step    |
| Nondeterminism as an effect    | many                          |

Multi-shot is exotic. In Scheme it's the Schelling point for expressing
nondeterminism itself. In Prolog, nondeterminism is already native, so the
multi-shot case is mostly academic.

---

## Clausal's execution model, restated

- Compiled predicates are Python generator functions.
- Solutions are emitted by `yield`.
- Backtracking happens by iterating the generator; the trail records bindings
  so that control returning past a `yield` undoes them.
- The trampoline handles tabling suspension.

So Clausal already uses the exact mechanism — `yield` as a control-transfer
primitive with an implicit "rest of the computation" living in the suspended
frame — that reset/shift crystallize in CPS.

The question becomes: **how much of reset/shift's semantics survives if we
just expose this existing mechanism?**

---

## The mapping (straightforward version)

```
Shift(Ball_)       → a yield of a distinguished sentinel + ball
Reset(Goal_, H_)   → driver iterates Goal_; on shift sentinel,
                     calls H_(Ball_, Resume_); on solution, re-yields up.
Resume_            → a thunk closing over the generator; call once to resume.
```

The trail "just works": the generator's suspended frame owns its trail
position; resuming it continues from exactly that state.

### The one-shot constraint

Python generators are one-shot past any given `yield`. `gen.send(x)` consumes
that suspension. You can't rewind.

Three reactions possible:

1. **Accept it.** Document as "Cont is one-shot; for multi-shot, use
   disjunction or `FindAll`." Ships quickly, covers 5/6 of the use cases,
   stays Pythonic.
2. **Simulate multi-shot by re-execution.** Record inputs to `Goal_` up to
   the shift point, re-run the whole thing each time Cont is invoked. This
   is semantically *different* — re-execution re-runs side effects. Only
   sound for pure goals.
3. **Build real continuations.** CPS transform the compiler, as SWI did.
   Abandons the generator model, substantial rewrite, loses the direct map
   to Python stack traces.

Option 1 is what this document gravitates toward. Options 2 and 3 are listed
for completeness.

---

## Candidate designs

### Design A — labeled yield (minimal)

One new sentinel class, one builtin, one wrapper.

```python
class _Shift:
    __slots__ = ('ball',)
    def __init__(self, ball): self.ball = ball

# Shift/1: emit sentinel
def Shift_impl(ball, trail):
    yield _Shift(ball)          # driver picks this up

# Reset/3: Reset(Goal_, Ball_, Handler_)
def Reset_impl(goal, ball_pat, handler, trail):
    gen = iter(goal)
    try:
        sol = next(gen)
    except StopIteration:
        return                  # Goal succeeded deterministically
    while True:
        if isinstance(sol, _Shift):
            # hand Ball + Resume to handler; Resume resumes gen once
            resume = _make_resume(gen)
            yield from call(handler, sol.ball, resume, trail)
            return
        else:
            yield sol
            try:
                sol = next(gen)
            except StopIteration:
                return
```

Points to discuss:

- **Shift inside disjunction.** If `Goal_` has choice points, a Shift
  captured from one branch leaves the other branches in the generator.
  Calling Resume continues that branch; on its exhaustion, control returns
  and the generator may still have alternatives. Does that match SWI
  semantics? (SWI: yes, because its Prolog-level continuation closes over
  the trail state and choice point stack.) Our generator naturally does the
  same.

- **Shift across cut.** If `!/0` appears between Shift and the enclosing
  Reset, what does Resume resume? SWI scopes cut to the nearest clause, so
  cut can't escape a shift. We probably inherit this for free because our
  cut is clause-local.

- **Nested resets.** The sentinel carries no handler identity; innermost
  Reset catches. Works if Reset is lexically visible. If we want named
  prompts ("shift to this specific reset"), sentinel grows a tag.

- **Trail timing.** Resume must not be called *after* the enclosing Reset's
  caller has backtracked past it, otherwise the trail is in the wrong
  state. This is the familiar "escaping continuations" problem. SWI forbids
  it implicitly; we can document "Resume is valid only during the handler
  call" and detect violations with a generation counter on the trail.

### Design B — async/await style

Frame Shift/Reset as Python `async def` + `await`. The Reset driver is an
event loop; Shift is `await Ball`; Handler is the scheduler.

Pros:
- Idiomatic Python.
- `asyncio` primitives (gather, timeout, queues) could compose with logic
  goals, enabling concurrency stories.

Cons:
- Collides with Python's `asyncio` machinery — users may expect that Reset
  integrates with actual event loops, it doesn't.
- Two kinds of "await" in the codebase: real asyncio and Clausal effect
  handlers. Confusing.
- Clausal doesn't otherwise use `async` — introducing it for this one
  feature is a big footprint.

Probably a bad trade unless we also want real concurrency. Noted but not
recommended.

### Design C — explicit CPS transform (the SWI route)

Compile predicates into CPS form: each goal takes an explicit continuation
argument. Shift captures the continuation, Reset installs a prompt.

Pros:
- Full multi-shot semantics.
- Matches the literature, ports papers directly.

Cons:
- Massive compiler rewrite — our whole "compile clauses to generator
  functions" strategy is abandoned.
- Loses natural Python tracebacks.
- We'd need our own stack representation, trampoline, and (probably) a
  scheduler. Re-implementing what Python gives us for free.

Worth it only if multi-shot becomes a load-bearing feature, which seems
unlikely given Clausal's native nondeterminism.

### Design D — thunk-based re-execution

Record `(Goal_, ball_predicate)` at the Reset. When handler calls Resume,
re-run `Goal_` from scratch in a sub-query, intercepting the shift at the
same point. Make Resume a closure over this re-execution.

Pros:
- Multi-shot for free.
- No compiler changes.

Cons:
- Side effects in `Goal_` run again per Resume call. Semantically different
  from real continuations.
- Up to the shift point, the re-execution is wasted work.
- Binding equality: re-executed vars are fresh; users who captured a var
  before Resume see it pointing to the old execution.

Viable *only* for pure, deterministic `Goal_`. Which is a narrow enough
constraint that users may as well write `findall` or explicit disjunction.

---

## Where this would actually get used

A short list of motivating use cases. Worth asking: for each, is reset/shift
the right primitive, or does Clausal have a better native answer already?

| Use case                          | Existing tool         | Would shift/reset help?      |
|-----------------------------------|-----------------------|------------------------------|
| Custom exception handlers         | throw/catch (V2-14)   | No — catch already exists    |
| State threading                   | DCG state (V2-17b)    | Maybe cleaner with effects   |
| Per-goal logging / tracing        | ad hoc                | Yes — clean effect handler   |
| Tabling with aggregation (Swift'd)| not implemented       | Yes — standard use           |
| Backtrackable I/O                 | ad hoc                | Yes — write/read as effects  |
| Coroutines / generator pipelines  | freeze/when           | Yes, if multi-consumer       |
| Algebraic effects research        | n/a                   | Yes — the whole point        |

The case that seems strongest and novel: **effect handlers for
cross-cutting concerns** (tracing, logging, instrumentation, mock-I/O for
tests) where you want the effect to be interpreted by a handler rather than
hardcoded into predicates. This is something we can't do cleanly today.

The case that seems *weakest*: anything multi-shot. Clausal's logic engine
is already a multi-shot environment.

---

## Open points worth deciding before writing a plan

1. **Is one-shot enough?** If yes, Design A is the clear path. If we
   genuinely want multi-shot, we're in Design C territory and it's a year
   of work.

2. **Named prompts or nearest-prompt?** SWI has a single unnamed prompt
   stack (innermost wins). Multi-prompt systems (Dybvig-Peyton Jones-Sabry)
   let you shift to a *specific* named reset. Named is strictly more
   powerful; unnamed is simpler and covers most uses.

3. **Escape detection.** Do we detect and reject calls to Resume outside
   the handler body? Cheap to implement (trail generation counter),
   prevents a class of confusing failures.

4. **Handler as goal vs handler as Python callable.** SWI makes the
   handler a Prolog goal, invoked with `call(Handler, Ball, Cont)`. We
   could make it either, but matching Clausal's pattern (goal terms, not
   Python callables, as the interface) fits better — and `call/N` already
   exists from V2-10.

5. **Syntax.** `Shift(Ball_)`, `Reset(Goal_, Ball_, Handler_)` as
   builtins, following existing CamelCase conventions. Or a directive-
   style `-effect_handler` declaration for static handlers? Probably just
   builtins; no declarative surface needed.

6. **How does this interact with tabling?** Answers in the table should
   *not* carry un-resumed continuations, or they'd be invalid outside
   their original Reset. Simplest rule: shifting across a tabling barrier
   is an error. Needs testing.

7. **How does this interact with attributed variables / CLP?** A Shift
   with un-wakened constraints on its captured variables should either
   wake them at Shift time or leave them; SWI wakes. Easier for us to
   leave them and document.

8. **Do we want it at all?** The Pythonic alternative to effect handlers
   is usually *just pass a handler as an argument*. Clausal has `Call/N`,
   lambdas (V2-9), and meta-predicates. Much of what effect handlers solve
   in Prolog/Scheme may be a non-problem here because passing a predicate
   is already ergonomic.

---

## Rough sense of effort

- Design A, one-shot, unnamed prompts: ~1 week implementation, ~30 tests,
  one docs page. Fits on top of the existing engine.
- Design A + named prompts: +2 days.
- Design C (real CPS): ~2 months, compiler rewrite. Not recommended.

---

## Suggested next step (for discussion)

Before writing a formal plan, resolve:

1. Are the use cases compelling enough to warrant any form of shift/reset,
   given we already have catch, lambdas, and meta-predicates?
2. If yes, is one-shot acceptable?
3. If yes, Design A — basically "name the thing Clausal already does."

If the answer to (1) is "not really," this may be one of those features
that looks important by Prolog analogy but isn't, because the analogous
problem doesn't exist in a Python-embedded logic language.
