# A refused `.seam` import from Clausal Prolog loads as a plain SyntaxError

Filed 2026-10-15 from the third review of the CLP(Q) resource caps (Info
item; out of that candidate's scope).

A sandboxed `.clausal` file that does `use_module` of a `.seam` module is
refused with `permission_error(import, python_bridge, Module)`, but the
refusal reaches the host as a plain **SyntaxError**. A host that catches
`ImportError` or `LogicException` around the import misses it. This is the
same class of gap as the one fixed for load-time `set_prolog_flag`
directives (c891dbf1, which now raises `clausal.sandbox.SandboxLoadError`,
an ImportError and a LogicException carrying the term), for a different
refusal.

Where it is raised: `clausal/tools/iso_l3_directives.py`, the Clausal
Prolog branch of the import lowering:

```python
refusal = bridge_refusal(ctx.source_path, dotted, found, record=True)
if refusal is not None:
    raise _refused(f"{what}: {refusal.term_text} -- "
                   f"{refusal.message}", span)
```

`_refused` builds the front end's SyntaxError; the ISO term exists only as
text (`BridgeRefusal.term_text`).

## To decide

- Should the load-time bridge refusal raise as `SandboxLoadError` (or a
  sibling ImportError + LogicException class) with the term
  `error(permission_error(import, python_bridge, M), use_module/1)`, as the
  flag-directive refusal does? Note the refusal is not sandbox-only: the
  python_bridges allowlist applies outside the sandbox too, so the class
  may not belong in `clausal.sandbox`.
- The run-time half (`dialect_edge.bridge_kind`, for `M:G` into a module
  someone else loaded) already raises a permission error term; check both
  halves give the same term.

## Pin

A test in tests/test_sandbox.py: a sandboxed `.clausal` importing a
non-allowlisted `.seam`, caught by `except ImportError`, by
`except LogicException`, and with `.term` the ISO term.
