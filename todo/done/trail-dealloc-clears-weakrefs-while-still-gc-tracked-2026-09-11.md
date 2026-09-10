# FIXED: `Trail_dealloc` cleared weakrefs while still GC-tracked — interpreter SIGSEGV

**Found and fixed 2026-09-11.** One line. It is worth reading anyway, because the bug was
misattributed twice before it was found and the misattributions were each supported by
real, reproducible measurements.

## The bug

`clausal/logic/variables/_variables.c`, `Trail_dealloc`:

```c
if (self->weakrefs)
    PyObject_ClearWeakRefs((PyObject *)self);   /* runs arbitrary Python */
PyObject_GC_UnTrack(self);                      /* ...too late */
```

`PyObject_ClearWeakRefs` invokes the weakref callbacks, which is arbitrary Python, and Python
code can run a pending collection at any eval-breaker check — the `RESUME` at the top of
`weakref.finalize.__call__` is enough. The dying Trail is still **GC-tracked at refcount 0**,
so the collector classifies it unreachable, `tp_clear`s it and deallocates it a SECOND time.
Control returns to the outer `Trail_dealloc`, which calls `PyObject_GC_UnTrack` on freed
memory: `_gc_next` now holds pymalloc's freelist link and `_gc_prev` is 0, so
`prev->_gc_next = next` writes to address 0. SIGSEGV.

CPython documents exactly this in `gc.c` (`update_refs`: "a tp_dealloc routine left a gc-aware
object tracked during its teardown phase ... a mysterious segfault in a release build"), and
`subtype_dealloc` untracks before clearing weakrefs for this reason.

**The fix is to move `PyObject_GC_UnTrack(self)` above the `ClearWeakRefs` call.** That is the
whole change. Regression test: `tests/test_variables.py::TestTrailDeallocWeakrefCallback`,
which drives it in a subprocess (the failure is a hard crash) and asserts BOTH that the driver
exits 0 and that the collection inside the callback reports **0** unreachable objects — the
dying Trail was never offered to the collector. Asserting only "did not crash" would pass on a
build where the timing merely happened not to line up.

## Reproduction, with no CLP(B) anywhere

```python
import gc, weakref
from clausal.logic.variables import Trail
def fin(): gc.collect()
t = Trail(); weakref.finalize(t, fin); del t
```

Pre-fix: exit 139. Post-fix: exit 0. Twenty lines, no constraint solver, no test suite.

## Why it looked like a CLP(B) bug for most of a day

CLP(B) is the only place in the engine that puts a `weakref.finalize` on a Trail
(`clpb._register_alloc`, for pruning its registries when a trail dies). So it was the only
code that could trigger this — and every experiment that disturbed it "fixed" the crash:

| experiment | result | why it misled |
| --- | --- | --- |
| `gc.disable()` | clean | no collection is ever pending inside the callback |
| neuter `_cleanup_trail_allocs` | clean | the callback body no longer runs Python long enough to hit an eval-breaker |
| keep `_unique_tables` (skip that pop) | clean | changes the GC count phase, so no collection is due at that instant |
| keep `_id_to_var` | clean | same |
| keep only `_var_to_id` | **crashes** | same |
| reverting an unrelated transformer file | clean | shifted allocation timing wholesale |

Every one of those is a real, repeatable measurement, and every one points at the wrong thing.
The lesson worth keeping: **"disabling X makes the crash go away" identifies a TRIGGER, not a
cause** — especially for a memory fault, where anything that moves allocation or GC phase can
mask or unmask it. The discriminating question was not "what did I change" but "what is
different about the ONE place that does this", and the answer was: it is the only weakref on a
Trail.

## What was ruled out on the way, and is genuinely fine

- The apply memo's borrowed `f`/`g` pointers (`_clpb_core.c` ~516) and the `PyDict_GetItem`
  sites on `memo`/`level_map`: not this bug class. They borrow from objects the call keeps
  alive, and on 3.12+ `c_apply`/`c_restrict`/`c_count_paths` never call back into Python, so no
  collection can start inside them.
- `c_make_node`'s borrowed `var`/`tbl` (fixed separately in `25fe9dce`): a genuine latent
  defect and worth keeping, but it could not have caused this crash. Relevant only on ≤3.11,
  where allocation could collect synchronously.

## Still open, and unrelated to this crash

The CLP(B) registry design — module-global dicts keyed on `id(Var)`, with `_id_to_var` holding
the only strong reference and a trail-driven finalizer pruning all three — remains fragile on
its own account: a freed Var's address can be recycled, and a new Var can inherit an old one's
hash-consing table. That is a silent wrong-answer hazard, not a crash, and it is filed at
`todo/clpb-registry-keyed-on-object-addresses-2026-09-11.md`.

## Diagnostic notes worth reusing

- No gdb in this environment. The C backtrace came from an `LD_PRELOAD` shim interposing
  `sigaction` and chaining to faulthandler; interposing `PyObject_ClearWeakRefs`,
  `PyObject_GC_UnTrack` and `PyObject_GC_Del` is what showed the nested same-object untrack.
- `-p no:faulthandler` makes the crash vanish — another GC-phase mask, not a clue.
- A detector that `dup(2)`s lazily during a test writes into pytest's capture file and reports
  nothing. Two rounds of "found nothing" were that, not evidence. Dup in a constructor.
- Python-level instrumentation inside the finalizer misses the collection entirely: it runs at
  the first `RESUME`, before any statement of the wrapper body.
