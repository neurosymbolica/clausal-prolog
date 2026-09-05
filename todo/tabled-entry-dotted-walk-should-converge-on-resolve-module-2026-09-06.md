# `_tabled_entry_for_goal`'s dotted caller-dict walk should converge on `resolve_module`

**Filed:** 2026-09-06 at P3-3 Task 6 close-out, as the brief required (R10's
legacy note pinned the dotted walk as-is for Task 6; the resolver was added
beside it, not through it).

`clausal/logic/solve.py::_tabled_entry_for_goal` now contains two different
answers to "which module's db holds this goal's table":

- **Legacy (dotted `Call(LoadAttr(LoadName(pkg), Pred))` goal):** walk the
  *querying* module's `module_dict` for the first segment, then `getattr`
  segment by segment, with a `sys.modules[".".join(segments)]` shortcut in the
  middle and `_coerce_module` at the end.
- **New (qualified cell `(":", M, G)`):** `resolve_module(M, calling_module)` =
  `sys.modules[dotted]` → `_coerce_module`, nothing else.

Known observable differences (three):
1. the legacy walk resolves a *relative* first segment out of the caller's
   namespace; the resolver does not;
2. the legacy walk accepts any object a `getattr` chain lands on; the resolver
   accepts only what `_coerce_module` accepts;
3. the legacy walk answers `(None, None)` on a miss; the resolver raises
   `existence_error(module, …)`.

**Convergence task.** Decide which of the three the dotted surface actually
needs, keep exactly those as documented parameters of ONE shared resolver, and
delete the second copy. Add a test that the dotted and cell spellings of the
*same* cross-module tabled goal locate the *same* `TableEntry` —
`tests/test_qualified_goals.py::TestQualifiedDottedParity` already asserts
they answer alike, which is the weaker half. Until then the two paths can
disagree about which module owns a table for goals meant to be two spellings
of one thing.

Natural home: the ISO phase (module system unification), or a P3-3 follow-up
once Task 9's perf gate has settled the tabling entry's hot path.
