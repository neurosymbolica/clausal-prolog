# Remove the StepGenerator wrapper

## Context

Every logic call currently allocates two objects: a `StepGenerator` wrapper and
its inner Python generator. The wrapper exists for three reasons:

1. **Self-reference** — the inner body needs `this_generator` to pass to
   children. The wrapper is constructed first, then passed in as an argument.
2. **Catcher slot** — the trampoline reads `gen.catcher` from outside the gen
   to walk the catch/3 handler chain when a `LogicException` is raised
   (`clausal/logic/trampoline.py:161`, mirrored in `_trampoline.c`).
3. **`send` bootstrap** — Python requires `next(gen)` before `send(non-None)`;
   the `_started` flag in `StepGenerator.send` lets call sites uniformly do
   `gen.send(value)` without caring whether it is the first call.

(1) and (3) are cheap to eliminate. (2) is the only one that justifies a wrapper
object today — but at the C level, frame locals are an array (`localsplus` /
`_PyInterpreterFrame->localsplus` since 3.11) and arguments occupy the first
slots in declaration order. So `catcher` is always at a fixed slot index of the
gen's frame, and a small C helper can read it without going through `f_locals`
materialisation or PEP 667's `FrameLocalsProxy`.

If we accept binding to CPython frame internals (which `_trampoline.c` already
does, more lightly), the wrapper can disappear entirely. Net win per logic call:
one fewer allocation, one fewer branch per `send`, no `__getattr__`-style slot
fetch when routing exceptions.

## Proposal

Replace the wrapper with raw Python generators plus a tiny C helper.

### New body signature

```
def pred__N(proceed, fail, catcher, *args, trail): ...
```

`this_generator` is gone. Most uses can be eliminated by passing the gen down
at *call construction* (the parent already has the gen object once it has done
`gen = pred_fn(...)`). Sites that genuinely need self-reference call:

```c
PyObject *current_generator(void);  // walks PyEval_GetFrame() → owning gen
```

`current_generator()` is implemented in the C extension via
`_PyEval_GetFrame()` + `_PyFrame_GetGenerator()` (3.11+) or `frame->f_gen`
(3.10).

### Catcher access

Trampoline / `solutions` / `_drive_until_yield` read `catcher` via:

```c
static PyObject *
gen_get_catcher(PyObject *gen) {
    _PyInterpreterFrame *f = _PyGen_GetFrame((PyGenObject *)gen);
    return f->localsplus[CATCHER_SLOT];   // borrowed
}
```

`CATCHER_SLOT` is discovered once per code object by scanning `co_varnames`
for the name `catcher`, then cached on the code object via
`_PyCode_GetExtra` so subsequent reads are an array index. Same scheme for
`proceed` / `fail` if anything outside the body needs them.

### Always-prime; drop `_started`

Construction primes the generator (`PyIter_Next` / `gen.send(None)`). This
shifts prologue exceptions and `_TABLING_SUSPEND` from the first send into
construction, so call sites can no longer just write
`StepGenerator(fn, ..., trail)` — they go through a helper:

```c
PyObject *make_call(func, proceed, fail, catcher, args..., trail);
```

`make_call` constructs the gen, primes it, and routes any `LogicException`
raised during prime through the catcher chain (the same loop currently in
`trampoline.py:158-167`).

### Trampoline loop

```c
PyObject *gen, *value;
gen = make_call(root_fn, NULL, NULL, NULL, args..., trail);
step = PyGen_Send(gen, Py_None);
while (target(step) != NULL) {
    step = PyGen_Send(target(step), value(step));
    /* on LogicException: walk gen_get_catcher() chain via PyGen_Throw */
}
return value(step);
```

No `StepGenerator` allocation, no `_started` branch, no Python-level method
dispatch on `send`.

## Tasks

- [ ] Add `current_generator()`, `gen_get_catcher()`, and the `co_varnames`
      slot-discovery cache to `_trampoline.c`. Gate behind `#if PY_VERSION_HEX`
      bands for 3.10 / 3.11+ frame layouts.
- [ ] Add a pure-Python fallback for each helper using `inspect.currentframe()`
      and `gen.gi_frame.f_locals[name]` so the no-extension path keeps working
      (slow but correct).
- [ ] Introduce `make_call(...)` (C + Python fallback) that constructs +
      primes the gen and routes prime-time exceptions through the catcher
      chain.
- [ ] Update the compiler (`clausal/logic/compiler.py`) to emit the new body
      signature `(proceed, fail, catcher, *args, trail)` — drop
      `this_generator` from the parameter list and from every call-site
      construction.
- [ ] Replace every `StepGenerator(...)` construction with `make_call(...)`.
      Audit list (search for `StepGenerator(`):
      - `clausal/logic/runtime/tramp_call.py:26`
      - `clausal/logic/specialization.py:1107`
      - `clausal/logic/builtins/higher_order.py` (×11)
      - `clausal/logic/builtins/dcg.py` (×4)
      - `clausal/logic/builtins/control.py` (×2)
      - `clausal/logic/builtins/_registry.py`
      - `clausal/logic/clpz3.py` (×3)
      - `clausal/logic/tabling.py` (×3)
- [ ] Rewrite the trampoline / `solutions` / `_drive_until_yield` loops to
      read catcher via the C helper rather than `gen.catcher`.
- [ ] Adapt `tests/test_tail_recursion.py:485` (`_solve_mod.StepGenerator =
      counting_cls`) — it monkey-patches the wrapper class to count
      constructions; redirect to a counter on `make_call` instead.
- [ ] Re-run the full test suite. Pay particular attention to:
      `tests/test_exceptions.py` (catcher-chain routing),
      `tests/test_tabling.py` (suspend/resume on the trampoline),
      `tests/test_reified_ite.py` (general ITE uses sub-generator commit).
- [ ] Benchmark before/after using the suite under `implementation_plans/
      benchmarking/`. Target: measurable drop in fib / nqueens / qsort
      tottime; the wrapper allocation and `_started` branch should disappear
      from profiles.

## Risks

- **CPython coupling.** `_PyInterpreterFrame`, `_PyGen_GetFrame`, and
  `localsplus` are underscore-prefixed and shifted between 3.10 → 3.11.
  Each Python minor release needs a re-check. The C extension already touches
  some private API; this is a step deeper.
- **Construction-time exceptions.** Always-prime means a `LogicException`
  raised during the predicate prologue surfaces from `make_call` rather than
  the trampoline's main loop. The helper must replicate the catcher walk;
  miss this and previously-caught errors will start leaking.
- **Tabling suspend.** `_TABLING_SUSPEND` is delivered via the first send; if
  it can be raised during the prologue, `make_call` must detect it and
  return a marker rather than a primed gen. Audit
  `clausal/logic/tabling.py:496` and `:578` for this case.
- **Self-reference removal.** Most uses of `this_generator` should disappear,
  but any case where the body yields `(this_generator, …)` to itself
  (iterative tail-call) needs the C helper or to keep a local set up at
  function entry. Verify the compiler-generated code does not need the
  wrapper as a target other call sites already hold a reference to.

## Decision gate

Only worth doing if `StepGenerator` allocation or its `send` overhead shows
up in profiles after the `_drive_trampoline`-to-C move
(`implementation_plans/compiler/todo/C_drive_trampoline.md`). Run that first
and re-profile; if wrapper allocation is still in the top 5%, this plan is
the next lever. Otherwise park it — the brittleness cost is real and the
current shape is readable.
