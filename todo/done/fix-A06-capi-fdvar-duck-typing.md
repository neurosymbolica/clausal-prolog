# fix(A06-F016): _clpfd_propagate duck-types non-FDVar states via raw struct casts (UB)

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/06-clpfd/findings.md A06-F016
**Tests:** none executed (a repro would segfault the suite); confirmed by
inspection of all three sites.

## Bug

Three helpers fall back to a raw `(FDVarObject *)` cast when `FDVar_Check`
fails, then read `->domain` / `->constraints` at fixed struct offsets:

- `get_fdvar` (_clpfd_propagate.c:504-518) — comment says "duck typing: has
  .domain, .constraints" but a C struct cast is NOT duck typing.
- `c_ensure_fd` (:645-648) — returns the raw cast; its caller
- `c_add_constraint` (:826-841) — does `PyTuple_GET_SIZE(state->constraints)`
  on it.

Reachable via the public attr API: `put_attr(x, "fd", <any object>)` then
any fd_* call on x → reads arbitrary memory at FDVarObject field offsets.
In-tree code always stores C FDVars (the Python FDVar class is shadowed at
import), so this is latent — but one refactor away from a segfault.
Contrast: `c_narrow`, `c_narrow_if_changed`, `c_propagate` and `py_fd_hook`
all do it correctly via `PyObject_GetAttrString` fallbacks.

## Fix direction

Replace the raw-cast branches with `PyObject_GetAttrString(state, "domain"/
"constraints")` like the correct sites (small refactor: a static helper
`fdvar_get_domain/constraints(state, &newref_flag)`), or reject non-FDVar
states with a TypeError. While here, delete `get_fdvar` if truly unused
(grep shows no callers).

## Acceptance

- `put_attr(x, "fd", types.SimpleNamespace(domain=((1,2),), constraints=()))`
  followed by `fd_ne(x, 1)` either works or raises TypeError — never crashes
  (add this as a test once fixed; it cannot be xfail'd today).
