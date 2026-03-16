# Clausal — Architecture

## Layer stack

```
clausal.modules              standard library modules (regex, log, …)
clausal.logic.goal_expansion body-goal rewriting pass (V3-3)
clausal.logic.compiler_v2    module-level compilation pipeline (V3-2)
clausal.logic.term_expansion TermExpansion/4 rewrite engine (V3-2)
clausal.logic.tabling (wfs)  well-founded semantics (V2-7)
clausal.logic.clpfd          CLP(FD) finite-domain constraints (V2-6)
clausal.logic.constraints    dif/2 via attribute variables (V2-5)
clausal.logic.tabling        SLG resolution (V2-4b)
clausal.logic.compiler       Prolog-style predicates → Python generator AST
clausal.continuation_search  greenlet-based search iterator
clausal.trampoline           generator trampoline, stack-safe CPS
clausal.logic.variables      C extension: unification, trails, backtracking, AttVars
clausal.term_rewriting       DSL syntax → AST (DCG >> rewriting, q() quasi-quotation)
clausal.simple_ast           term representation (homoiconic)
clausal.import_hook          transparent import; module system (V3-1); ModulesFinder
```

Each layer builds on the one below. Python code and logic code can interact at any layer.

---

## Why not a WAM

The Warren Abstract Machine is the standard execution substrate for Prolog. For clausal it is the wrong choice, for several interlocking reasons.

**The memory model conflict is fundamental.** The WAM uses a global heap of tagged machine words with specific pointer arithmetic (REF/STR/CON/LIS tags packed into word-sized cells). Python objects live on the Python GC heap, reference-counted, with a completely different layout. To pass a term from the WAM heap to a Python function, you must marshal it. To pass a Python object into a WAM term, you must wrap it. Every boundary crossing pays this cost, and in an embedded system that is the common case, not the exception. SWI-Prolog, which bridges to Python this way, is a good illustration of how awkward the result is.

**WAM advantages don't transfer.** The WAM's main wins — compact term representation, fast unification via pointer comparison, efficient trail management with the high-water mark — are all relative to a pure Prolog world. The high-water mark optimisation (only trail bindings above the current choice point) requires WAM stack discipline that Python objects don't participate in. We simply trail everything, which `clausal.logic.variables` already does.

**The binding direction and trail design are already right.** `clausal.logic.variables` uses age-ordered binding (newer var → older var, matching GNU Prolog's "bind higher address to lower" and Scryer Prolog's convention), reverse-order undo, and unconditional trailing. This is the correct WAM-derived behaviour adapted to Python's GC heap. The implementation was derived by studying both GNU Prolog (`wam_inst.h`, `unify.c`) and Scryer Prolog (`machine_state_impl.rs`, `unify.rs`). There is nothing more to gain from a full WAM.

**"Compile to Python bytecode" — the right form.** The intuition behind wanting WAM-like compilation is sound: we want predicates to be efficient native code rather than interpreted. But generating raw CPython bytecode is fragile (changes between versions, CPython-only). The correct form of this idea is: **compile Prolog predicates to Python generator functions**. Each clause becomes a Python generator; backtracking is Python's generator protocol; unification uses `clausal.logic.variables`. This approach:
- gets the CPython JIT for free in future Python versions
- is debuggable with standard Python tools
- allows Python calls without FFI
- leverages the AST infrastructure clausal already has
- is exactly what `clausal.trampoline` and `clausal.continuation_search` are already built toward

---

## Execution model

### The problem with nested iterators

The simplest approach — nested Python generators that `yield` solutions up a chain — has linear overhead per solution proportional to the search depth, and hits Python's recursion limit for deep recursive predicates. `yield from` in Python is designed for shallow nesting; it is not a substitute for tail-call elimination.

`asyncio` is worse: `await` has similar overhead, and the stack depth limit before segfault is lower than with plain generators.

### CPS + trampoline

Logic predicates compiled to continuation-passing style (CPS) avoid the linear yield-chain overhead, but CPS requires tail-call optimisation — which Python does not provide and almost certainly never will (Guido's explicit position).

The solution is a **trampoline**: a driver loop that receives the next continuation to execute, rather than having continuations call each other directly. This gives:

- true tail-call elimination (constant stack depth)
- the ability to interrupt execution for timeouts, concurrency, asyncio interop
- a point of control that can be swapped (e.g. a C trampoline for reduced overhead)

`clausal.logic.trampoline` implements this. A C extension (`_trampoline`) provides optimised versions; the pure-Python module is the fallback.

### Why generators rather than functions for CPS

Generators are better than plain functions for CPS in this setting because they allow resumption for the next choice point without a new continuation being passed. A generator implementing a predicate can:

1. match arguments and set up bindings
2. yield a `(target, value)` tuple to the trampoline
3. be resumed for the next clause (next choice point)

Each resumption corresponds to a choice point. This maps the Prolog search tree directly onto Python's generator protocol.

Every trampoline-compiled generator is wrapped in a `StepGenerator`. `StepGenerator.__init__(func, *args)` calls `func(self, *args)`, so the generator receives its own wrapper as the first parameter (`this_generator`) without any bootstrap round-trip. The compiled function signature is:

```python
def my_predicate(this_generator, parent, arg1, arg2, trail):
    # clause 1
    match (deref(arg1), deref(arg2)):
        case (pattern1, pattern2):
            mark = trail.mark()
            if unify(...):
                yield (parent, None)       # solution
            trail.undo(mark)
    yield (parent, DONE)                   # exhausted
```

Sub-predicate calls wrap the child dispatch in `StepGenerator`:

```python
_gen = StepGenerator(child._get_dispatch(), this_generator, ...)
_st = yield (_gen, None)
while _st is not DONE:
    ...                     # continuation
    _st = yield (_gen, None)
```

The compiler (`clausal.logic.compiler`) generates this from predicate definitions written in clausal syntax. See [compiler.md](compiler.md) for full details.

---

## Tabling and well-founded semantics

Plain SLD resolution (what the trampoline currently implements) loops on left-recursive predicates and cannot soundly handle negation. For ontological reasoning, Datalog, and XSB-style queries, two additional layers are needed.

### Tabling (SLG resolution)

Tabling memoises subgoal calls and their answers in a call/answer table. When a subgoal is called again before it has completed, the caller suspends and waits for new answers rather than re-entering the computation. This:

- prevents infinite loops on recursive predicates
- enables Datalog-style bottom-up evaluation
- is a prerequisite for well-founded semantics

The key insight is that **tabling is easier to implement on coroutines/generators than on a WAM**. Tabling requires suspending a computation mid-execution and resuming it when new answers arrive. Generators do this naturally; on a WAM it requires saving and restoring the full register file and stack explicitly — which is why tabling required deep engine surgery in SWI-Prolog.

The `clausal.logic.tabling` module maintains a table mapping `(functor, arity, variant_key)` to `TableEntry` objects that track status, cached answers, and suspended consumers. See [tabling.md](tabling.md) for full details.

### Well-founded semantics (V2-7)

Well-founded semantics (WFS) assigns three truth values to ground atoms: *true*, *false*, or *undefined*. It gives a principled treatment of negation in the presence of recursion — the "undefined" value propagates through mutually recursive negations rather than looping or giving arbitrary results.

WFS is implemented directly in `clausal.logic.tabling` (V2-7), extending the existing SLG machinery with delayed negation and conditional answer resolution. When `not P(args)` targets a tabled predicate whose table is still evaluating (cycle through negation), the negation is *delayed* rather than checked immediately. After SLG completion, a simplification pass resolves delayed negations:

- Negation of a completed table with no matching answer → **true** (delay removed)
- Negation of a completed table with an unconditional matching answer → **false** (answer invalidated)
- Remaining delays form unfounded sets → truth value **undefined**

The compiler detects `not P(args)` where `P` is tabled and emits a call to `_naf_tabled` (a plain function, not a generator) instead of the inline NAF generator pattern. This is transparent — programs with recursion through negation "just work". See [tabling.md](tabling.md) for full details.

**Note on Python interop and WFS:** calling Python code with side effects from within a tabled or WFS predicate during an incomplete subgoal evaluation requires care — the Python code may observe intermediate (undefined) state. This is a known constraint, not a fundamental obstacle. Clausal documents it rather than prohibiting it.

---

## Homoiconicity

The import hook (`clausal.import_hook`) intercepts module imports and transforms ASTs before compilation. This gives clausal two kinds of homoiconicity:

**Logic terms as data.** Expressions marked with `--` are captured as `clausal.simple_ast` nodes rather than being evaluated. This means Prolog-style terms can appear inline in Python code, and are just Python objects.

**Python code as data.** Expressions or statement blocks can be captured as AST nodes without being executed. This allows the logic system to reason about Python programs — useful for meta-interpreters, program analysis, and code generation.

The cost of AST transformation is paid once at import time. `PredicateLoader` (a `SourceLoader` subclass) caches the transformed bytecode in `__pycache__/` as a `.pyc` file. Subsequent imports load the cached bytecode directly, skipping parsing and AST transformation entirely. See [caching.md](caching.md) for details.

---

## Python ↔ logic interop

Logic predicates can be called from Python via the iterator protocol or callbacks:

```python
# Iterator: receive solutions one at a time
for solution in Goal(X, Y):
    print(X.value, Y.value)

# Callback style
Goal(X, Y).solutions(lambda x, y: print(x, y))
```

The recursion and yielding challenges are solved by the trampoline. Python code called from within logic code runs normally with no special requirements.

The deep layering — Python → logic → Python → logic — is explicitly supported. There is no artificial restriction on nesting depth or call direction.

---

## Roadmap

| Layer | Status |
|---|---|
| `clausal.logic.variables` | Done — C extension, 88 tests |
| `clausal.trampoline` | Done |
| `clausal.continuation_search` | Done |
| `clausal.simple_ast` / `clausal.conversion` | Done |
| `clausal.term_rewriting` | Done |
| `clausal.import_hook` | Done — `.pyc` caching, deferred compilation |
| `clausal.logic.compiler` | Done — head patterns + body goals, simple + trampoline modes |
| `clausal.logic.database` | Done — clause store, directives, dispatch |
| `clausal.logic.builtins` | Done — Assert/Retract, In/Append, arithmetic, higher-order, term inspection, exceptions, I/O; constructable PredicateMeta classes for all 75+ builtins |
| `clausal.logic.solve` | Done — call/solve/query/once |
| Predicate indexing | Done — groundness-keyed multi-arg dispatch (V2-2) |
| Bytecode caching | Done — `__pycache__/*.pyc` via SourceLoader (V2-3) |
| `clausal.logic.tabling` | Done — SLG resolution, variant tabling (V2-4b) |
| `clausal.logic.constraints` | Done — dif/2 via attributed variables (V2-5) |
| `clausal.logic.clpfd` | Done — CLP(FD) finite-domain constraints (V2-6) |
| Well-founded semantics | Done — delayed negation, conditional answers (V2-7) |
| Meta-predicates | Done — FindAll, BagOf, SetOf, ForAll, Call/N (V2-10) |
| Higher-order list builtins | Done — MapList, Filter, Exclude, FoldLeft (V2-11) |
| Arithmetic builtins | Done — Sign, Gcd, DivMod (V2-12) |
| Term inspection | Done — CopyTerm, TermVariables, NumberVars (V2-13) |
| Control exceptions | Done — throw/1, catch/3, halt/0, halt/1 (V2-14) |
| I/O builtins | Done — Write, Writeln, PrintTerm, Nl, Tab, WriteToString, TermToString; f-string support (V2-15) |
| Python interop | Done — `++()` escape evaluates arbitrary Python at search time; PyThunk lambda wrapper (V2-16) |
| DCGs | Done — `>>` grammar rules, source-level rewriting, phrase/2,3, state threading (V2-17) |
| Module system | Done — `-import_from`, `-import_module`, qualified calls, dotted name resolution (V3-1) |
| Pipeline split | Done — `compiler_v2.compile_module()`, two-phase architecture (V3-2) |
| Term expansion | Done — `TermExpansion/4`, `q()` quasi-quotation, imported TE rules, init/final injection (V3-2) |
| Goal expansion | Done — body-goal rewriting, regex auto-binding, pattern pre-compilation (V3-3) |
| `clausal.modules` | Done — standard library package with `ModulesFinder`; `regex` module (V3-3), `log` module (structured logging wrapping Python's `logging`) |
