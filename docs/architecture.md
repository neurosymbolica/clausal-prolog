# Clausal — Architecture

## Layer stack

```clausal
--8<-- "tests/fixtures/docs/misc_phase7_sigs.txt:architecture_diagram"
```

The import hook handles both `.clausal` and `.pl` (Prolog) files — see [Importing Prolog](importing_prolog.md). Each layer builds on the one below. Python code and logic code can interact at any layer.

The optional `clausal.trealla` and `clausal.scryer` layers provide embedded Prolog engines. [Trealla](trealla.md) is a fast C-based engine via ctypes (instant startup, ~5MB). [Scryer](scryer.md) is a Rust-based engine via PyO3 (~200ms startup, ~100MB, with tabling support). Both use the existing Prolog translation pipeline and execute programs in-process.

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

For programs that genuinely need a WAM — ISO-conformant constraint solving, rich library ecosystems, or cross-validation against a standards-compliant engine — the [Trealla](trealla.md) and [Scryer](scryer.md) Prolog embeddings provide one in-process, without replacing clausal's native execution model.

---

## Execution model

### The problem with nested iterators

The simplest approach — nested Python generators that `yield` solutions up a chain — has linear overhead per solution proportional to the search depth, and hits Python's recursion limit for deep recursive predicates. `yield from` in Python is designed for shallow nesting; it is not a substitute for tail-call elimination.

To make this concrete: a left-recursive predicate like `append/3` called on a list of length N creates a call stack N frames deep. Each frame is a generator that `yield from`s the next. Python's default recursion limit is 1000; at list length 1000 you get a `RecursionError`. Raising `sys.setrecursionlimit` helps, but the limit is a safety valve against unbounded stack growth, not a solution to it. Stack frames are large (several hundred bytes each), and truly deep recursion (e.g., a search over a graph with millions of nodes) will exhaust memory long before any limit you can set.

`asyncio` is worse: `await` has similar overhead, and the stack depth limit before segfault is lower than with plain generators.

### CPS + trampoline

Logic predicates compiled to continuation-passing style (CPS) avoid the linear yield-chain overhead, but CPS requires tail-call optimisation — which Python does not provide and almost certainly never will (Guido's explicit position).

The solution is a **trampoline**: a driver loop that receives the next continuation to execute, rather than having continuations call each other directly. Instead of each predicate calling the next predicate (which grows the call stack), each predicate *yields* a description of what to call next, and the trampoline loop (a single function on the Python stack) dispatches it. The stack depth remains constant regardless of the depth of the logic search.

This gives:

- **bounded stack depth** — the trampoline loop runs at a fixed stack depth; deep or infinitely recursive predicates do not exhaust the Python call stack or trigger `RecursionError`
- true tail-call elimination (constant stack depth for deterministic chains)
- **tail recursion optimization (TRO)** — when the last goal in a clause body is a self-recursive call preceded only by deterministic goals, the compiler emits a `while True` loop with argument reassignment instead of allocating a new `StepGenerator` per recursion depth, reducing memory from O(n) to O(1). Works across groundness-keyed and list structural dispatch boundaries; runtime `is_var()` ground-check ensures correctness when head-decomposition variables might be unbound
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

Plain SLD resolution (what the trampoline currently implements) loops on left-recursive predicates and cannot soundly handle negation. For ontological reasoning, Datalog, and XSB-style queries, two additional layers are needed. See [Tabling](tabling.md) and [Well-Founded Semantics](wfs.md) for full documentation.

### Tabling (SLG resolution)

Tabling memoises subgoal calls and their answers in a call/answer table. when a subgoal is called again before it has completed, the caller suspends and waits for new answers rather than re-entering the computation. This:

- prevents infinite loops on recursive predicates
- enables Datalog-style bottom-up evaluation
- is a prerequisite for well-founded semantics

The key insight is that **tabling is easier to implement on coroutines/generators than on a WAM**. Tabling requires suspending a computation mid-execution and resuming it when new answers arrive. Generators do this naturally; on a WAM it requires saving and restoring the full register file and stack explicitly — which is why tabling required deep engine surgery in SWI-Prolog.

The `clausal.logic.tabling` module maintains a table mapping `(functor, arity, variant_key)` to `TableEntry` objects that track status, cached answers, and suspended consumers. See [tabling.md](tabling.md) for full details.

### Well-founded semantics

Well-founded semantics (WFS) assigns three truth values to ground atoms: *true*, *false*, or *unknown*. It gives a principled treatment of negation in the presence of recursion — the unknown value propagates through mutually recursive negations rather than looping or giving arbitrary results. WFS is a three-valued semantics over strong Kleene, so its third value is represented by the language's own `Undefined` singleton rather than a separate sentinel.

WFS is implemented directly in `clausal.logic.tabling`, extending the existing SLG machinery with delayed negation and conditional answer resolution. when `not P(args)` targets a tabled predicate whose table is still evaluating (cycle through negation), the negation is *delayed* rather than checked immediately. After SLG completion, a simplification pass resolves delayed negations:

- Negation of a completed table with no matching answer → **true** (delay removed)
- Negation of a completed table with an unconditional matching answer → **false** (answer invalidated)
- Remaining delays form unfounded sets → truth value **undefined**

The compiler detects `not P(args)` where `P` is tabled and emits a call to `_naf_tabled` (a plain function, not a generator) instead of the inline NAF generator pattern. This is transparent — programs with recursion through negation "just work". See [tabling.md](tabling.md) for full details.

**Note on Python interop and WFS:** calling Python code with side effects from within a tabled or WFS predicate during an incomplete subgoal evaluation requires care — the Python code may observe intermediate (undefined) state. This is a known constraint, not a fundamental obstacle. Clausal documents it rather than prohibiting it.

---

## Homoiconicity

The import hook (`clausal.import_hook`) intercepts module imports and transforms ASTs before compilation. This gives clausal two kinds of homoiconicity:

**Logic terms as data.** Expressions marked with `--` are captured as `clausal.simple_ast` nodes rather than being evaluated. This means Prolog-style terms can appear inline in Python code, and are just Python objects.

**Python code as data.** Expressions or statement blocks can be captured as AST nodes without being executed. This allows the logic system to reason about Python programs — useful for [meta-interpreters](metainterpreters.md), program analysis, and code generation.

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
| `clausal.logic.builtins` | Done — assertz/retract, in_/append, arithmetic, higher-order, term inspection, exceptions, I/O; constructable PredicateMeta classes for all 75+ builtins |
| `clausal.logic.solve` | Done — call/solve/query/once |
| Predicate indexing | Done — groundness-keyed multi-arg dispatch |
| Bytecode caching | Done — `__pycache__/*.pyc` via SourceLoader |
| `clausal.logic.tabling` | Done — SLG resolution, variant tabling |
| [`clausal.logic.constraints`](constraints.md) | Done — dif/2 via attributed variables |
| [`clausal.logic.clpfd`](constraints.md) | Done — CLP(ℤ) integer constraints |
| [Well-founded semantics](wfs.md) | Done — delayed negation, conditional answers |
| [Meta-predicates](meta_predicates.md) | Done — findall, bagof, setof, forall, Call/N |
| [Higher-order list builtins](higher_order.md) | Done — maplist, include, exclude, foldl |
| Arithmetic builtins | Done — sign, gcd, divmod_ |
| [Term inspection](term_inspection.md) | Done — copy_term, term_variables, numbervars |
| [Control exceptions](exceptions.md) | Done — throw/1, catch/3, halt/0, halt/1 |
| [I/O builtins](io.md) | Done — write, writeln, print_term, nl, tab, write_to_string, term_to_string; f-string support |
| [Python interop](python_integration.md) | Done — `++()` escape evaluates arbitrary Python at search time; PyThunk lambda wrapper |
| [DCGs](dcg.md) | Done — `>>` grammar rules, source-level rewriting, phrase/2,3, state threading |
| [Module system](import.md) | Done — `-import_from`, `-import_module`, qualified calls, dotted name resolution |
| Pipeline split | Done — `compiler_v2.compile_module()`, two-phase architecture |
| [Term expansion](term_expansion.md) | Done — `TermExpansion/4`, `q()` quasi-quotation, imported TE rules, init/final injection |
| Goal expansion | Done — body-goal rewriting, regex auto-binding, pattern pre-compilation |
| `clausal.modules` | Done — standard library package with `ModulesFinder`; [regex](regex.md) module, [log](logging.md) module (structured logging wrapping Python's `logging`), [date_time](date_time.md) module (relational date/time using Python `datetime` objects) |

---

*See also: [Compiler](compiler.md) — clause compilation details · [Indexing](indexing.md) — first-argument indexing and groundness dispatch · [Module System](import.md) — import hook and `.pyc` caching.*
