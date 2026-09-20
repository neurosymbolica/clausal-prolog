# Task 5 (the C arms) is BLOCKED: all 17 arms still fire — measured

**Status:** open. Task 5 step 1 (twin-parity pins) is DONE; step 2 (delete the
instance arms) cannot be done yet, and this records exactly why and what has
to move first.

## What the plan says

`docs/superpowers/plans/2026-09-18-predmeta-p2-terms-as-tuples.md`, Task 5:

> **Step 2: delete the instance arms** (the cell arms already walk `PyTuple`);
> keep `py_register_predicate_meta` (predicates' classes still register until P4).

That was written 2026-09-18, BEFORE Tasks 3, 4 and 6 landed. The premise —
"the cell arms already walk PyTuple, so the instance arms are dead" — is
false as stated.

## The measurement

An instrumented `_variables.so` (8 counters, one per arm) over the full house
run, in a faithful room. The instrumented run reproduced the gate exactly
(146 failed / 16722 passed), so the instrument is not perturbing anything.

```
          87  0 c_is_term_instance -> PredicateMeta INSTANCE
      295430  1 c_is_term_instance -> @dataclass instance
          63  2 py_term_field_names -> PredicateMeta arm
          25  3 c_term_field_names  -> PredicateMeta arm
        2646  4 py_is_atom          -> PredicateMeta arm
           6  5 c_is_ground         -> PyType_Check class arm
           6  6 c_copy_term         -> PyType_Check class arm
           4  7 c_collect_vars      -> PyType_Check class arm
```

**Not one arm is dead.** They split into three groups:

* **Arm 1 (295k)** is `@dataclass`, not `PredicateMeta` at all — `Quantity`
  and friends. Out of scope for this retirement, stays regardless.
* **Arms 4/5/6/7** are the `PyType_Check(term) && PredicateMeta_type` arms:
  they answer for a predicate CLASS, not an instance. The class is still the
  predicate handle until P4, so these go when the class goes — the same
  reason the plan already gives for keeping `py_register_predicate_meta`.
* **Arms 0/2/3** are the genuine instance arms.

## Who still feeds arms 0/2/3

43 distinct `tp_name`s. Every one is a test-minted probe functor
(`test_fast_construction`'s `cct_*`/`cw_*`/`ct_*`/`dw_*`/`emit_*`,
`audit_2026_07_05`'s `audit_*`, `test_tagged_terms`' `point`,
`test_funnel_accessors`' `term_expansion`, `Pt`). **No engine vocabulary
mints an instance any more** — stored clause heads are cells (measured: 3
cells / 0 instances for a loaded module).

BUT the engine's own head-rebuild CALL SITES are still there and still fire.
Counting `PredicateMeta._clausal_head` calls over the same run — 102 total,
18 distinct sites:

```
      83  ENGINE  clausal/logic/predicate.py:1155     <- the bridge branch in __call__
       3  ENGINE  clausal/logic/solve.py:129
       1  ENGINE  clausal/logic/compiler/list_dispatch.py:371
      15  tests   (test_funnel_accessors, test_predrow, test_python_fallbacks)
```

* `predicate.py:1155` is `if cls.__dict__.get("_clausal_instances")` — 83
  calls, all from classes declared with the flag BY TESTS (Task 6 emptied it
  in `clausal/`).
* **`solve.py:129` and `list_dispatch.py:371` are real engine paths and they
  really fire.** `solve.py` does `rebuild = getattr(cls, "_clausal_head", cls)`
  — every `PredicateMeta` has `_clausal_head`, so that rebuild yields an
  INSTANCE, which then flows straight into `copy_term`/`ground`/
  `term_variables` and onto arms 0/2/3.
* `database.py:1329`, `database.py:1459` and `database_ops.py:119` call it
  too but did NOT fire in this run — latent, not dead.

## What has to move before step 2

1. The five engine `_clausal_head` call sites above stop producing instances
   (that is the P4 head-channel work, not a C change).
2. `is_term_instance` / `term_field_names` stop being public — Task 4's own
   exit says the definitions "stay until P4 with a deprecation docstring",
   and arms 0/2/3 are what makes them true for an instance.
3. Only then do arms 0/2/3 become deletable. Arms 4/5/6/7 wait for the class
   itself (P4); arm 1 never goes.

**Task 5 should be re-sequenced after the P4 head-channel change, or
rewritten to cover only what is actually dead — which today is nothing.**

## What DID get done

Task 5 step 1, and it found a real hole. The twin-parity corpus in
`tests/test_python_fallbacks.py` (`_corpus()`, from P3-2 Task 2C) already
covers `_is_ground`/`copy_term`/`collect_vars` across cells, classes and
instances — but its three rows named `instance`, `cell_in_instance` and
`instance_in_cell` spelled `Pt(x=..., y=...)`, and **P2 Task 3 turned that
call into a CELL**. All three silently became duplicates of shapes the corpus
already had, and the C instance arms — the ones Task 5 exists to reason about
— stopped being exercised by that file at all. Nothing failed; the parity
assertions passed over the wrong terms.

Fixed: the rows spell `Pt._clausal_head(...)`, and
`TestTheCorpusStillCoversInstances` pins it so the next flip cannot undo it
silently. Parity holds for the restored rows (no twin drift found).
