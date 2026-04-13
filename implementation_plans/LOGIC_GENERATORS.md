# Logic Generators — `yield` and `yield from` in Clause Bodies

Design notes and implementation sketch for exposing Python's `yield` and
`yield from` as first-class control constructs inside Clausal clause bodies.
This is the Pythonic alternative to delimited continuations: instead of
reifying "the rest of the computation" as a term, we let clause bodies *be*
producers and expose iteration as the consumer side.

See `DELIMITED_CONTINUATIONS_DISCUSSION.md` for the reasoning that led us
here.

---

## The core idea

Clausal compiles clause bodies to Python generator functions already.
`yield` and `yield from` are already Python keywords, already parsed by the
AST, already handled by CPython's runtime. All we need to do is:

1. decide what they *mean* at the Clausal semantic level,
2. wire `term_rewriting` to pass them through (rather than rejecting or
   rewriting them),
3. provide a consumer-side construct that drives a producer goal and binds
   its yielded values.

The execution model already does 90% of the work — we're surfacing it.

---

## The semantic question

A compiled clause body already uses `yield` internally: "yield a solution /
give control back so the caller's choice point can be explored."

If a user writes literal `yield X_` in a clause body, it can't share this
implicit meaning — it has to be a distinct, user-level operation. Some
candidate semantics:

### Interpretation A — yield emits a stream value, orthogonal to solutions

A clause body that contains `yield` becomes a *stream producer*. It still
has the ordinary logical outcome (success / failure / multiple solutions
via backtracking). In addition, during execution, each `yield V_` emits
`V_` to a consumer.

A consumer uses a new builtin `For(V_, ProducerGoal_, BodyGoal_)` (or
decorator-like surface `for V_ from Producer_: ...`) that drives the
producer's generator and runs `BodyGoal_` with `V_` bound to each emitted
value.

Solutions of the producer (the "return" in Python-generator terms) can
either:
- be ignored (streaming-only use), or
- be surfaced as an "after-stream" success (logical success of the whole
  producer).

Recommendation: the producer's logical success is the signal "stream
ended successfully." Failure of the producer is an early abort.

### Interpretation B — yield *is* solution emission

Make `yield X_` just a solution carrying `X_` as metadata. This collapses
the two yield meanings but breaks backward compatibility: existing
predicates succeed without yielding anything, so every solution would need
a sentinel "no value" marker, and the consumer side has to unpack.

Messier. Reject.

### Interpretation C — yield is pure sugar for a disjunction branch

`yield V_` ≡ `X_ = V_ ; ...`. Nope — this loses the streaming property
(caller gets values only on backtrack, can't interleave with handler
logic), and it's just disjunction with extra steps.

**Going with A.** Two distinct channels: ordinary solutions and a value
stream. They coexist cleanly because they're emitted on different events.

---

## Surface syntax

Since Clausal clause bodies are parsed as Python AST, `yield` and
`yield from` are already syntactically valid. We just need `term_rewriting`
to preserve them rather than choke on `ast.Yield` / `ast.YieldFrom`.

### Producer

```clausal
Squares(N_) <- (
    I_ = 0,
    while I_ < N_: (
        yield I_ * I_,
        I_ = I_ + 1,
    ),
)
```

(Assuming `while` as a Clausal construct or modeled via recursion — either
way, the point is the `yield` sits naturally in body position.)

Equivalent pure-recursion form:

```clausal
Squares(N_) <- Squares_(0, N_)
Squares_(I_, N_) <- I_ >= N_
Squares_(I_, N_) <- (
    I_ < N_,
    yield I_ * I_,
    Squares_(I_ + 1, N_),
)
```

### Consumer

Two candidate forms, pick one (or both):

**Form 1 — `For` goal:**

```clausal
CollectSquares(N_, List_) <- (
    Acc_ = [],
    For(S_, Squares(N_), Acc_ = [S_ | Acc_]),
    Reverse(Acc_, List_),
)
```

`For(V_, ProducerGoal_, BodyGoal_)` drives `ProducerGoal_`'s generator,
binds `V_` to each yielded value, runs `BodyGoal_`.

**Form 2 — Python-style `for … in` in clause bodies:**

```clausal
CollectSquares(N_, List_) <- (
    Acc_ = [],
    for S_ from Squares(N_): Acc_ = [S_ | Acc_],
    Reverse(Acc_, List_),
)
```

`from` (instead of `in`) signals "iterate this *producer*, not a list." We
want this keyword distinction because `for X_ in List_:` already has a
natural list-iteration meaning we may want later.

Recommendation: ship Form 1 first (plain builtin, no syntax work). Add
Form 2 once the semantics are settled.

### `yield from`

```clausal
Concat(A_, B_) <- (
    yield from A_,
    yield from B_,
)
```

Where `A_`, `B_` are producer goals. Semantics: drain A_'s stream, then
B_'s. This is exactly Python's `yield from`, because A_/B_ compile to
generators.

---

## Examples this enables

### Lazy `FindAll`

```clausal
# traditional: materializes all answers
FindAll(X_, P_, Xs_)

# streaming: consumer processes each answer without the list ever existing
for Answer_ from StreamAll(X_, P_): Handler(Answer_)
```

`StreamAll(Template_, Goal_)` yields `Template_` for each solution of
`Goal_`. Implementable in 3 lines on top of the existing solution loop.

### Pipelines

```clausal
# produce primes, filter to those matching predicate, take first N
TakeFirst(10, Filter(IsPrime, Naturals()), Result_)
```

Where `Filter`, `TakeFirst`, `Naturals` all use yield and compose like
Python generators. No intermediate list materialization.

### Tracing / logging handler

```clausal
TracedGoal_(G_) <- (
    for Event_ from RunWithTrace(G_):
        Writeln(Event_),
)
```

`RunWithTrace(G_)` is a meta-interpreter that yields a trace event at each
step.

### Incremental search

Producer-side:
```clausal
Solutions(Problem_) <- (
    Search_(Problem_, State0_),
    yield State0_,
    Refine_(State0_, State1_),
    yield State1_,
    ...
)
```

Consumer displays intermediate solutions as they arrive.

### Tabling with aggregation (one of the motivating DC use cases)

The tabling engine yields partial answers; an aggregation handler consumes
them, folds, and emits a refined answer. Doable today with callbacks;
cleaner with yield.

---

## What this doesn't give you

Worth naming the gaps up front, to avoid overselling:

- **Multi-shot continuations.** A consumer can't rewind the producer.
  Same limitation as Design A in the delimited-continuations doc. Still
  fine — the use cases that matter are one-shot.
- **Non-local control flow that skips over intermediate frames.** `yield`
  only returns to the nearest `For`. If you want `shift` that crosses
  arbitrary call depth, you're back in CPS land. In practice, threading
  the consumer goal explicitly through calls is tolerable.
- **True coroutines (resume from outside).** The producer runs only when
  the consumer asks for the next value. We don't get symmetric coroutines.

---

## Implementation

### Compiler changes

Current `term_rewriting.py` rejects or doesn't handle `ast.Yield` and
`ast.YieldFrom`. Add cases:

```python
def visit_Yield(self, node):
    # preserve as-is: the surrounding compiled function is already
    # a generator, so Python yield works natively
    return ast.Yield(value=self.visit(node.value) if node.value else None)

def visit_YieldFrom(self, node):
    # node.value is a Call node (a producer goal); compile to
    # a Python expression that returns a generator.
    gen_expr = self._compile_goal_to_generator_expr(node.value)
    return ast.YieldFrom(value=gen_expr)
```

The subtle case: `yield from Goal_` where `Goal_` is a logic goal. The
compiled form needs to be an expression that evaluates to a Python
iterator/generator. This is essentially "compile Goal_ in the same way the
engine compiles a goal, but return the raw generator instead of driving
it." The infrastructure exists — `compile_goal` already does this; just
expose it for use in expression position.

For the producer, no extra machinery: the compiled clause body already
*is* a generator function. Its internal `yield` statements (for solutions)
and the user's `yield` statements (for stream values) coexist — they're
different yields from the same generator.

Wait: that actually *is* a problem. If both are raw `yield`, the driver
can't tell them apart. Fix: wrap user yields in a sentinel class, e.g.
`_StreamValue(v)`. Then `visit_Yield` becomes:

```python
def visit_Yield(self, node):
    inner = self.visit(node.value) if node.value else ast.Constant(None)
    return ast.Yield(value=ast.Call(
        func=ast.Name(id='_StreamValue', ctx=ast.Load()),
        args=[inner], keywords=[],
    ))
```

The solution-emitting yield stays unwrapped; the driver in `solve.py`
distinguishes by isinstance check. `yield from` gets the same treatment:
wrap in an adapter that re-yields `_StreamValue(v)` for each item from the
delegated generator's stream values, and lets ordinary solutions pass
through untouched.

### Runtime: `For/3` builtin

```python
class For(BuiltinPredicate):
    _fields = ('var', 'producer_goal', 'body_goal')

    def _resolve(self, var, producer_goal, body_goal, db, trail):
        gen = iter(_drive_goal(producer_goal, db, trail))
        for emitted in gen:
            if isinstance(emitted, _StreamValue):
                mark = trail.mark()
                if unify(var, emitted.value, trail):
                    yield from _drive_goal(body_goal, db, trail)
                trail.undo_to(mark)
            # ordinary solutions of the producer are discarded in For/3;
            # use a different consumer if you want them
```

Semantics decisions this pins down:
- **Producer's logical solutions are silently consumed.** Rationale:
  `For/3` is about the stream, not the success count. Users who want
  both use `FindAll` + a stream consumer.
- **Body is run per stream value, with backtracking scoped to that
  iteration.** Body may succeed multiply or fail; iteration continues
  regardless.
- **Producer failure ends iteration.** Consumer's `For/3` succeeds
  (having produced nothing for failed iterations).

### Runtime: `yield from` delegation

`yield from OtherGoal_` in source compiles to a `yield from` over a
generator that filters for stream values from OtherGoal_:

```python
def _stream_of(goal, db, trail):
    for item in _drive_goal(goal, db, trail):
        if isinstance(item, _StreamValue):
            yield item
        # solutions of inner goal are consumed here, not passed out
```

Or — for maximum Python analogy — pass solutions through too. Decision
needed; streams-only is simpler.

### Interaction with trail and backtracking

Producer generator holds its trail position in its suspended frame. When
consumer calls `next(gen)`, producer resumes from its last yield, possibly
establishing further bindings, yields, or choice points. If consumer
backtracks out of its own clause, the producer generator is garbage-
collected (CPython calls `gen.close()`), which runs any `finally` blocks
— we need those to untrail.

Practical rule: whenever we enter a `yield`, record a trail mark; on
close, undo to that mark. Implementable as a `try/finally` wrapper around
the compiled body — but more robust to do it inside the driver.

### Interaction with cut

Cut inside a producer clause scopes to that clause, as normal. It affects
the producer's choice points, not the consumer's. No special handling.

### Interaction with tabling

Yielding from a tabled predicate should pass stream values through the
answer cache? Probably not — the cache stores *logical* answers, not
stream events. Rule: tabled predicates can't contain `yield` (compiler
error). Re-examine if a use case appears.

### Interaction with `FindAll` / `BagOf`

`FindAll(Template_, Goal_, List_)` ignores stream values from `Goal_` and
collects logical solutions as today. Users who want to collect stream
values use a helper:

```clausal
CollectStream(Goal_, List_) <- (
    Acc_ = [],
    For(V_, Goal_, Acc_ = [V_ | Acc_]),
    Reverse(Acc_, List_),
)
```

Could ship `CollectStream/2` as a builtin.

---

## Open questions

1. **Does `yield from` preserve logical solutions too, or only stream
   values?** Python's `yield from` preserves return values via
   `StopIteration.value`. We could map this to "the delegated goal's
   logical success/failure becomes ours." Leaning yes — it's the
   principle-of-least-surprise mapping from Python.

2. **Can `yield` appear inside `If-Then-Else`?** Yes, it's just control
   flow — no reason to restrict.

3. **Can a goal be both a producer *and* have multiple logical
   solutions?** Yes, they're orthogonal channels. Consumer decides which
   to observe.

4. **Static vs dynamic detection of producers.** A predicate is a
   producer iff any of its clauses contain `yield`. We could surface this
   as a `PredicateProperty` (see REFLECTION.md). Useful for tooling;
   not required for semantics.

5. **Should `yield` bind fresh variables per iteration?** If the body of
   a consumer loop uses `V_` and the producer yields 10 different values,
   does each iteration get a fresh `V_`, or the same logic variable
   rebound? Python semantics: same name, rebound. Logic semantics: each
   iteration is a fresh scope. Go with the logic semantics — `For/3`
   binds `V_` fresh each iteration via a trail mark. Matches how `BagOf`
   handles its template.

6. **Syntax for `For` — builtin call or new keyword?** Builtin first.
   If ergonomics demand, add `for V_ from Goal_:` Python-style keyword
   later. Don't pre-commit.

7. **What does a yield in a failing branch do?** If the producer yields,
   then fails, the consumer *has already seen the value*. This is
   different from ordinary Prolog semantics where failure undoes
   everything. Worth documenting: yield is an observable side-effect from
   the consumer's perspective, and not undone by backtracking of the
   producer.

   This is a meaningful departure from pure logical reading. Consistent
   with `Write/1`, `Print/1`, etc — all side-effectful. Document as
   "yield is a stream-level effect, not a logical binding."

8. **How does this compose with `++()` Python interop?** Can
   `yield ++some_python_expr()` work? Should work by construction —
   `++()` produces a term, `yield` emits it. No interaction needed.

---

## Phases

### Phase 1 — compiler pass-through + For/3 (1 week)
- [ ] `term_rewriting.visit_Yield` / `visit_YieldFrom` preserve and wrap
- [ ] `_StreamValue` sentinel class
- [ ] `For/3` builtin
- [ ] `CollectStream/2` builtin
- [ ] `yield from` delegation via stream-filter adapter
- [ ] Trail-safe driver: mark on yield, undo on close
- [ ] Compiler rejects `yield` inside tabled predicates (V2-D metadata check)
- [ ] 30+ tests: squares, primes, filter, take_first, yield-from chains,
      early-abort via body failure, interaction with FindAll, cut inside
      producer
- [ ] Docs page with pipeline examples

### Phase 2 — ergonomics (optional)
- [ ] `for V_ from Goal_:` surface syntax
- [ ] `PredicateProperty(P_, producer)` via reflection
- [ ] Examples: streaming aggregation, tracing meta-interpreter, lazy
      search

### Phase 3 — deeper integration (speculative)
- [ ] Interplay with CHR (if built) — yield as a way to emit constraints
      into a consuming handler
- [ ] Interplay with DCGs — DCGs already have a "state stream"; unify
      with logic generators?

---

## Summary for the decision

- Doable in ~1 week, minor compiler work, one new sentinel, one new
  builtin.
- Feels native — `yield` and `yield from` are Python keywords that
  already work in the generator functions Clausal compiles to.
- Covers the practical use cases reset/shift is typically reached for
  (streaming, pipelines, tracing, incremental output).
- One-shot only; multi-shot is not supported. Nondeterminism handles
  that side of the space natively.
- Side-effect semantics (yields survive producer backtracking) is the
  one thing worth flagging to users — it's Pythonic, not Prologic.

This is the recommendation: build this, and shelve delimited
continuations as "considered, declined for being less Pythonic and less
minimal."
