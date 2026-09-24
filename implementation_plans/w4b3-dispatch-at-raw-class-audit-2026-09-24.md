# W4b-3 prerequisite: raw `PredicateMeta` classes reaching `_dispatch_at` — audit 2026-09-24

Read-only audit of canonical `main` @ `dde50d49`. Probes ran in a detached worktree at
the same sha, with compiled extensions built from 453e5188 (no C diff vs main under
`clausal/**/*.c|h`). Every claim is tagged **MEASURED** or **READ**.

## 1. What the class arm does (READ)

`clausal/logic/predicate.py:1427` `_dispatch_at(obj, arity)`, arm at `:1453`:

```python
if isinstance(obj, PredicateMeta):
    obj._refuse_call_at(arity)   # clause-head / -dynamic arity refusal -> PredicateArityMismatchError (with site=_registered_at)
    return obj._get_dispatch()   # row._db._dispatch[row._key], else lazy recompile, else NotImplementedError
```

`_refuse_call_at` runs on EVERY call, including agreeing arity (it declines after reading one
clause head). Everything the class does is row-derived, except the diagnostic's
`site=cls._registered_at` ("is_pos/1 is defined at <file>" line).

The mangled-atom arm (`type(obj) is str`, `:1491`) already does the post-flip equivalent:
`qualify_mangled_goal` -> `resolve_module` -> `_refuse_if_known_at_another_arity(db, name, arity)`
-> `db.get_dispatch(name, arity)` -> else follow `module_dict[name]` recursively -> else
`existence_error`. So **a site that simply hands `_dispatch_at` the module-dict binding
unchanged is era-agnostic**; the breakage is in the *guards in front of* `_dispatch_at`,
which select on `_get_dispatch`/`type` and silently select nothing once the binding is a str.

## 2. Instrumentation (MEASURED)

`_dispatch_at`'s class arm was instrumented (worktree only) to log the 3-frame caller chain.
Two batches of targeted files (≈29 files; 382 + 441 tests), not the full suite:
arity-mismatch diagnostic, f7, dcg, edcg, bytes_dcg, higher_order, string_higher_order,
solve, w4_qualified_handle, import_from_module_shadow, mangled_handle_dangling_error_shape,
dispatch_target_error, callsite_*, w4b2b_binding_resolver, f3, chars_carrier,
prolog_dialect, phase5_builtins, bytes_patterns, builtin_classes, control, if_spelling,
reflection_builtins, audit_2026_05_25 C10, doc_snippet_coverage, optimisations_call_site,
secondary_dispatch_tro, groundness_dispatch, head_list_tail_call.

| Immediate caller of the class arm | hits (batch1+batch2) |
|---|---|
| compiled `$dispatch_at(fname, N)` (`<template>` frames, dozens of generated preds) | 410 + 220 |
| `solve.py:1100` `call()` Phase 5 | 117 + 156 |
| `dcg.py:188` `_phrase__2` class arm | 61 + 11 |
| `dcg.py:235` `_phrase__3` class arm | 21 + 3 |
| `_registry.py:150` `_ensure_trampoline_dispatch`, via all 18 callers (below) | 71 + 8 |
| `predicate.py:1525` self-recursion (`_bound` from handle's module dict) | 1 |
| tests calling `_dispatch_at(cls, n)` directly (`test_predicate_arity_mismatch_diagnostic.py:541,543`, `test_dispatch_target_error.py:87`) | 3 |

Callers of `_ensure_trampoline_dispatch` observed firing with a class: `higher_order.py`
`:277` (call/N), `:324,:354,:382,:413,:441,:477,:505,:533,:569,:616,:652,:697,:746,:782,:822,:860`
(all 16 list builtins), and `control.py:63` (time_goal). All 18 MEASURED.

NOT observed: `dcg.py:195`, `dcg.py:241`, `control.py:84` (see §3, rows 4–6).

## 3. Flip simulation (MEASURED)

Probe: load a module, replace each `PredicateMeta` binding in `module_dict` with
`mangle(module, name)` (what W4b-2d writes), call each site. For compiled sites, called
`globals_env._inject_resolved_targets` directly with a flipped `globals_` (patching
`module_dict` after load does NOT reach compiled code — `base_globals` is a snapshot).

| Site | class (today) | mangled binding, main as-is | mangled, with trial fix |
|---|---|---|---|
| `solve.call('is_pos', 3)` | 1 sol | 1 sol | 1 sol |
| `solve.call('is_pos', 1, 2)` wrong arity | PredicateArityMismatchError | **KeyError "not defined"** | PredicateArityMismatchError (no "defined at" line) |
| `solve.call('last', 1, 1)`, user `last/2` shadows builtin | 1 sol (user) | **0 sol (BUILTIN answered)** | 1 sol |
| `solve.call('last', [5], 5)` | 0 sol (user) | **1 sol (builtin)** | 0 sol |
| `call/2` via name | 1 | 1 | 1 |
| `phrase(greeting, [hi])` / `phrase/3` | 1 | **0 — silent** | 1 |
| `maplist/2`, `maplist/3`, `include/3` | 1 | **0 — silent** | 1 |
| `time_goal(go)` | 1 | **0 — silent** | 1 |
| `time_goal(greeting)` (arity 2 at 0) | PredicateArityMismatchError | **0 — silent** | PredicateArityMismatchError |
| compiled `is_pos/1` (unlocked local) fname global | PredicateMeta | `_DbDispatchAdapter` | mangled str |
| compiled `greeting/2`, `use_pos/1` (LOCKED local) `$disp_` cache | baked | **LOST** (every call -> `$dispatch_at(adapter)`) | baked |
| compiled `last/2` (user shadows builtin) fname global | PredicateMeta (user) | **BuiltinPredicate — silent** | mangled str (user) |
| compiled `is_pos/2` wrong arity | refuses | refuses (str arm) | refuses |

Trial fix = guard widening using the EXISTING accessor `is_declared_predicate_name`
(sketch in §6). With it applied, the targeted files: 711 passed / 1 failed + 462 passed / 0
failed. The one failure (`test_doc_snippet_coverage::test_no_raw_untested_blocks`, 38 doc
blocks that fail to compile) also fails with only the instrumentation applied — not caused
by the fix. `is_mangled` alone was tried first and also reached parity, but it is the
wrong discriminator: a `-hide` data atom is mangled and is NOT a handle (scope doc §W4b-2),
so it would turn today's silent fall-through into an `existence_error`.
`is_declared_predicate_name` asks the owner row, so a hidden data atom stays excluded.

## 4. Site inventory and classification

Classes: **(a)** mechanical conversion available now with an existing accessor;
**(b)** needs the flip first (no site change, correct only once bindings are mangled);
**(c)** needs a design decision.

| # | Site (main line) | Where the class comes from | Post-flip hand-off | Class | Evidence |
|---|---|---|---|---|---|
| 1 | `solve.py:1095-1100` `call()` Phase 5 | `module.module_dict.get(functor)` | the binding unchanged; guard `hasattr(_get_dispatch)` -> `hasattr(...) or is_declared_predicate_name(b)` | **(a)** | firing MEASURED; hazard MEASURED; fix parity MEASURED |
| 2 | `dcg.py:186-188` `_phrase__2` | phrase arg 1 = a module-global name load (compiled body) or a Python caller's `module_dict[...]` | the binding at arity 2; add `is_declared_predicate_name(rule_val)` to the class guard | **(a)** | same |
| 3 | `dcg.py:234-235` `_phrase__3` | same | same | **(a)** | same |
| 4 | `dcg.py:190-195` instance arm `type(rule_val)` | a term INSTANCE's type | nothing to do: since W4a `PredicateMeta.__call__` returns a CELL and `is_term_instance` (Py fallback) is dataclass-only, so a `PredicateMeta` cannot arrive; only a dataclass class reaches here (generic arm) | not a live raw-class path | READ; never fired (MEASURED) |
| 5 | `dcg.py:237-241` same, phrase/3 | same | same | not a live raw-class path | READ; never fired |
| 6 | `control.py:75-84` time_goal instance arm | `type(goal_val)`, gated on `getattr(cls, "_row")` | a dataclass has no `_row`, so the whole arm is dead code; delete at W4b-3 | not a live raw-class path (dead) | READ; never fired |
| 7 | `_registry.py:146-150` `_ensure_trampoline_dispatch` | whatever its 18 callers pass (goal arg = module-global name load) | add a first arm `if is_declared_predicate_name(g): return _dispatch_at(g, arity or 0)` | **(a)** | firing MEASURED |
| 7a | `higher_order.py:462` `_is_goal` + 8 inline copies of `callable(g) or hasattr(g,'_get_dispatch')` at `:321,:350,:378,:409,:438,:778,:818,:856` (16 list builtins in total) | guard in front of #7 | widen `_is_goal` with `is_declared_predicate_name`; fold the 8 inline copies into `_is_goal` | **(a)** | hazard MEASURED (maplist/2, maplist/3, include/3 -> 0 sol) |
| 7b | `control.py:62` time_goal guard | guard in front of #7 | same widening | **(a)** | hazard MEASURED |
| 7c | `higher_order.py:275` call/N guard | guard in front of #7 | nothing to do: the else branch `_resolve_named_goal` already handles a mangled goal | already era-agnostic | MEASURED (call/2 1 sol in both eras) |
| 8 | `predicate.py:1522-1525` recursion `_dispatch_at(_bound, arity)` | `module_dict[name]` of the HANDLE's module = an `-import_from` binding (the exporter's class); needed because importer `db.get_dispatch` does not serve adopted rows | see decision D1 | **(c)** | firing MEASURED (`test_w4_qualified_handle.py:185`) |
| 9 | compiled `$dispatch_at(fname, N)` — `goal_trampoline.py:486-490`, `goal_shallow.py:93-97` | `base_globals[fname]`, fixed at COMPILE time by `globals_env._inject_resolved_targets` from `module_dict` | site: no change **(b)**. Prerequisite **(a)**: `globals_env.py:627` `if existing is not None and hasattr(existing, "_get_dispatch")` -> also accept `is_declared_predicate_name(existing)` (then `_maybe_cache_dispatch` already works via `resolve_predicate_row`) | **(b)** site + **(a)** prereq | firing MEASURED; hazard + fix parity MEASURED (probe of `_inject_resolved_targets`) |
| 10 | tests calling `_dispatch_at(cls, n)`: `test_predicate_arity_mismatch_diagnostic.py:541,543`, `test_dispatch_target_error.py:87` | explicit | rewrite to a mangled handle, or retire, at W4b-3 | **(b)** | MEASURED firing |

Not a `_dispatch_at` caller, noted in passing: `solve.py:1079` fast path
`hasattr(functor,'_get_dispatch') -> functor._get_dispatch()` takes a raw class and skips the
arity refusal. After the flip a mangled functor is qualified before it (`:1071`), so nothing
more to do; it just stops seeing classes (READ).

**Counts:** (a) = 5 conversions — #1, #2+#3 (one guard shape), #7 + its guards 7a/7b,
and the #9 prerequisite in `globals_env`; counting call lines, that is 1 + 2 + (1 + 1 + 8
inline + 1) + 1. (b) = 2 — compiled `$dispatch_at` (2 emitters) and the 3 direct test
calls. (c) = 1 — #8 plus decision D2. Not live raw-class paths = 3 (#4, #5, #6).

## 5. Decisions needed (c)

- **D1 — what does an `-import_from`'d name bind to after the flip?** Row #8 depends on it.
  If the flip binds the importer's name to the OWNER's handle `mangle(exporter, name)`, the
  recursion follows it and works unchanged. If it binds `mangle(importer, name)`, the
  interned `_bound is obj` guard trips and the call raises `existence_error` on an
  imported predicate. Recommendation: the owner's handle, OR make the str arm resolve the
  importer's ADOPTED row (the adoption store, not `_rows`) before the namespace fallback.
  Pin with `test_the_funnel_resolves_a_handle_to_an_imported_predicate` run post-flip.
- **D2 — F7 refusal parity.** Once the class arm is gone, arity refusal comes only from
  `_refuse_if_known_at_another_arity` (db `declared_kind`/`is_predicate_name`), not from
  `_refuse_call_at` (clause heads + `-dynamic` + `_fields` veto). MEASURED difference so far:
  the message loses the "`name/N` is defined at <file>" site line (the class's
  `_registered_at`). Not measured: the stale-`_arity` fixture
  (`impord_atom_then_pred.clausal`) and the `-dynamic` veto cases. Rule whether the site
  line must be carried on the row (so the str arm can pass `site=`), and re-run the 38
  arity-diagnostic tests with bindings flipped before deleting the arm.

## 6. Trial-fix sketch (worktree only, NOT applied to canonical)

```text
solve.py:1095      hasattr(pred_cls,'_get_dispatch')  ->  ... or is_declared_predicate_name(pred_cls)
dcg.py:186,234     (isinstance(rule_val,type) and hasattr(...)) or is_declared_predicate_name(rule_val)
_registry.py:146   if is_declared_predicate_name(goal_val): return _dispatch_at(goal_val, 0 if arity is None else arity)
higher_order.py    _is_goal += is_declared_predicate_name(val); 8 inline guards -> _is_goal(goal_val)
control.py:62      ... or is_declared_predicate_name(goal_val)
globals_env.py:627 ... or is_declared_predicate_name(existing)
```

These do not change behaviour before the flip: the class arms still answer first, and today
the only mangled bindings are held handles, where the change is the intended one.
The trial diff was exactly the six lines above (plus folding the 8 inline guards into
`_is_goal`); it was never committed.

As landed on `fix/w4b3-dispatch-conversions-2026-09-24`, two of the sketch lines were
changed on review, because each DID change behaviour before the flip:
- `_registry.py`: the handle arm goes AFTER the class arm (`is_declared_predicate_name` is
  also true of a class, so a first arm would send a class with `arity=None` through
  `_dispatch_at(cls, 0)` and its arity refusal), and a handle with no arity raises
  `TypeError` instead of guessing 0.
- `globals_env.py`: an APPLIED target (arity >= 0) accepts a handle only via
  `is_declared_predicate(existing, arity=target_arity)`; the arity-blind accept kept a
  handle naming `name` at another arity for every arity, pre-empting the builtin lookup,
  `_atom_shadows_row` and the dotted routing.

## 7. Silent-selector hazards (the recurring failure mode)

Each of these selects NOTHING after the flip, and the result is a fall-through, not an
error. All MEASURED except where noted:

1. `solve.py:1095` `hasattr(pred_cls, '_get_dispatch')` -> Phase 5 skipped -> Phase 6
   **builtin wins over a same-named user predicate**. A wrong-arity call also degrades to
   a KeyError.
2. `dcg.py:186/234` `isinstance(rule_val, type) and hasattr(...)` -> `_resolve_nonterminal`
   returns None for a bare atom (the pinned `test_phrase_bare_str_rule_reference_fails_cleanly`
   behaviour) -> **phrase fails silently**.
3. `higher_order.py` `_is_goal` + 8 inline copies -> **all 16 list builtins fail silently**.
4. `control.py:62` -> **time_goal fails silently**, including a wrong-arity call that
   raises today.
5. `globals_env.py:627` `hasattr(existing, "_get_dispatch")` -> compiled calls get the
   **builtin in place of a same-named user predicate**, and every LOCKED local predicate
   **loses its `$disp_` fast path** (it goes to `_DbDispatchAdapter`). That is a perf hazard
   the suite will not catch, and it contradicts `_dispatch_at`'s "off the hot path by
   construction" docstring.
6. (READ, not audited further) `higher_order._namespace_dispatch` -> `database_ops._find_pred_cls`
   returns a class and keys the home lookup on `pred_cls.__name__`. This is how call/N
   reaches `-import_from`'d predicates. Check it in the same pass as D1.
7. (Found by review of the conversion branch, 2026-09-24; MEASURED; CONVERTED on
   `fix/w4b3-dispatch-conversions-2026-09-24`) `specialization.py:1374`
   `_make_solve_goal_predicate`'s `module_dict` fallback,
   `hasattr(pred, '_get_dispatch')` -> `pred._get_dispatch()`: a handle binding fell to
   "Unknown goal — fail silently" (every residual goal, including one specialized
   predicate calling another, 0 solutions). Converted: the guard also accepts
   `is_declared_predicate_name(pred)`, and a handle dispatches via
   `_dispatch_at(pred, len(args))`; the class arm is unchanged.
8. (Found in the same review pass; MEASURED; CONVERTED on the same branch)
   `globals_env._inject_resolved_targets`' DOTTED-name branch has two more copies of
   the #5 guard: the attribute walk (`hasattr(obj, "_get_dispatch")`) and the
   `sys.modules` route (`hasattr(resolved, "_get_dispatch")`). With a handle as the
   module attribute, the walk kept the handle but lost the `$disp_` bake, and the
   `sys.modules` route resolved NOTHING. Both now also accept
   `is_declared_predicate_name`; the early accept (#5's conversion) was measured not
   to change dotted-name behaviour against the class path, which already took it.
