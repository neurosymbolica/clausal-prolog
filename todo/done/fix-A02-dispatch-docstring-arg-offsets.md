# fix(A02-F005, doc-drift): dispatch docstrings say trampoline arg_offset is 2; callers pass 4

**Finding:** `docs/superpowers/audits/2026-07-05-fable-partition/02-compiler-heads/findings.md` A02-F005

Three docstrings in `clausal/logic/compiler/arg_index.py` describe the
trampoline argument offset as **2** ("positions 0/1 are
``self_generator``/``parent``"), predating the Phase-2 split-continuation
layout ``(this_generator, _proceed, _fail, _catcher, arg0, …, trail)``.
Every trampoline caller passes **4**:

| Docstring (says 2) | Caller (passes 4) |
|---|---|
| `_make_secondary_dispatch_impl` (`arg_index.py:641-646`) | `_make_secondary_dispatch_trampoline` (`:714-716`) |
| `_make_indexed_dispatch_impl` (`:727-733`) | `_make_indexed_dispatch_trampoline` (`:775-779`) |
| `_groundness_dispatch_body_multi` (`:814-817`) | `_make_groundness_dispatch_trampoline` (`:954-959`) |

(`_make_joint_dispatch_trampoline` at `:519-522` documents the layout
correctly — use its wording.)

Doc-only fix; no behavior change, no test. Update the three docstrings to
the Phase-2 layout.
