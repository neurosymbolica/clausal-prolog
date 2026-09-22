# W3 — the `_get_dispatch` protocol: scope, measured 2026-09-22

**Status: SCOPE ONLY.** Written by engine-lane after closing W2, from measured
numbers and the three lanes' census answers (see
`todo/w3-get-dispatch-protocol-downstream-constraints-2026-09-22.md`).
Questions for the operator are PARKED at the end, not decided here.

## What the protocol is

`_get_dispatch()` is duck-typed, single-argument (no arity), and frozen:
"do not add an arity parameter to another `_get_dispatch`; add the case" in
`_dispatch_at` (predicate.py). `_dispatch_at(obj, arity)` is the funnel:
`PredicateMeta` gets the arity-aware call, everything else is called bare.
Locked predicates never reach it at runtime — their dispatch is pre-cached in
`base_globals` under `_disp_key(name, arity)` (globals_env.py:492/611); only
`-dynamic` callees and the meta-call funnels (`call/N`, `solve/1`,
`time_goal`) arrive there. The row already holds the dispatch:
`Database.get_dispatch(functor, arity)` (database.py:1053) does the same
three-step (installed → lazy recompile → registry fallback) as
`PredicateMeta._get_dispatch`, minus the arity refusal.

## The numbers, re-measured (the plan's 185 counted every MENTION)

    in-tree CALL sites (code lines, not comments/docstrings)     31
      receivers: fname 5 (globals_env), cls 4, pred_cls 2, obj 2
                 (the funnel), goal_val 1, functor 1, builtin 1, ...
    in-tree implementors                                          6
      PredicateMeta._get_dispatch (arity-aware; the only one)
      globals_env._DbDispatchAdapter, modules/py/__init__ (lookup base),
      _registry.BuiltinPredicate, _registry.MultiArityBuiltin
    out-of-tree implementors (packages/)                         11
      scipy 9 (plain classes, `def _get_dispatch(self): return self._dispatch`)
      spacy 1, provenance 1 (`_RegistrationGoal`)
    downstream (downstream checks the downstream bodies, corpus the downstream trees, iso tooling)
      `_get_dispatch` CALLS                                        0
      predicate CLASS held as a VALUE and called later            31 sites / 5 bodies
      classification keyed on isinstance(x, PredicateMeta)+_fields 1 site
      text-keyed gate on the AttributeError wording                1 (fails open)

**So W3 is not "185 sites and a frozen protocol".** It is: 31 in-tree calls
to re-point at the row, 5 in-tree + 11 out-of-tree implementors that stay
exactly as they are, and a downstream cliff of 31 handle-as-value sites that
is W4's (the class going), not this workstream's.

## The shape that falls out

* **Foreign implementors keep `_get_dispatch(self)` forever.** It is THEIR
  protocol; nothing about retiring `PredicateMeta` touches a plain class with
  that method. `_dispatch_at`'s "everyone else is called bare" arm survives.
* **The in-tree calls on a PREDICATE CLASS move to the row**:
  `cls._get_dispatch(arity)` → `db.get_dispatch(functor, arity)` where a db is
  in hand, else `cls._state_row()` and the row's three-step. The arity refusal
  (`_refuse_call_at`, `_declared_arity`, `_clause_arity`) is row-shaped and
  follows the state (W4's list already says so).
* **`_dispatch_at` keeps a `PredicateMeta` arm until the class goes**, then
  the arm becomes "a `(functor, arity)` key resolved against the caller's db".
* **The gate is `tools/w3_package_gate.sh`** (own venv; 105 / 1566 baseline
  at 34a6dc79). Every W3 commit: house suite NEW 0 / GONE 0 AND package gate
  NEW 0 / GONE 0.

## Constraints from downstream (do not break silently)

1. A dotted goal resolving to a module/non-predicate must raise a NAMED
   exception whose class name is in the rendered first line; send the verbatim
   line to the corpus lane and the export lane BEFORE landing, and say whether the
   plain AttributeError path is still reachable. They hold their gates until
   then.
2. `isinstance(x, PredicateMeta) and x._fields != ()` is a live
   declared-predicate-vs-atom TEST (a downstream classification site); if the class goes,
   announce the replacement TEST, not the replacement attribute.
3. The 31 handle-as-value sites: at P4 a module attribute becomes the ATOM
   (ruled 2026-09-14), so `m.pred` stops being callable there. That migration
   (to goal tuples) is downstream, W4-gated, and has to be dispatched
   explicitly — the phantom-dispatch lesson.

## Parked for the operator

* Q1. Confirm: foreign `_get_dispatch(self)` stays for good (frozen, not
  deprecated). If instead it is to be deprecated, the window and the
  replacement need ruling; nothing in-tree needs it gone.
* Q2. The exception class name for "dotted goal resolved to a non-predicate"
  (`DispatchTargetError`? it becomes a token other lanes key on — pick once).
* Q3. Whether W3 waits for the two P2 counterexamples to be diagnosed. W3 is
  independent of P2 in code, but every gate run stacks on the same rooms.
