# W4a — retiring the PredicateMeta INSTANCE path (design, 2026-09-22)

**Status:** design approved by the operator 2026-09-22 (evening); spec for
review before the implementation plan. First landing of W4 (the class
removal); the class itself is W4b and is NOT in scope here.

## Why this is a deletion, not a behaviour change

Measured on main (whole-suite census, a plugin counting every
`PredicateMeta._clausal_head` construction by caller site):

    1006 instance-head constructions over the house suite
     919  from tests   (906 in one file that pins the C instance arms on
                        purpose; 13 more across 5 files)
      87  from the engine, all three sites downstream of a TEST-SET bridge:
           83  PredicateMeta.__call__'s `_clausal_instances` branch
                (no engine class sets the flag; 55 test sites in 7 files do)
            3  solve.py's instance rebuild
            1  list_dispatch's instance rebuild

A loaded clause stores its head as a CELL (facts and rules alike);
`_head_ctor_ast` has been the identity since the 2026-09-19 head flip;
`__call__` builds a cell. So on the engine's own paths no instance of a
predicate class exists at runtime, and every arm that handles one is dead
code kept alive by tests written to pin it. Deleting the path changes no
answer the engine gives; it removes the doors through which an instance
could re-enter.

## Scope

### Goes (Python)

| what | where | replacement |
|---|---|---|
| `PredicateMeta._clausal_head` | predicate.py | a RAISING tombstone (`RetiredStateError`, W2's class) naming `__call__` / the cell |
| the `_clausal_instances` bridge branch | `PredicateMeta.__call__` | none: `__call__` always builds the cell |
| `make_predicate(..., instances=True)` | predicate.py | the keyword is refused with a `TypeError` naming this spec |
| `_clausal_new` (the instance fast constructor) and `_make_fast_new` | predicate.py | none |
| the instance-rebuild arm | database.py x2 (head rewrite helpers) | deleted: a head is a cell |
| the instance-rebuild arm | compiler/list_dispatch.py | deleted |
| the instance-rebuild arm | builtins/database_ops.py | deleted |
| `getattr(cls, "_clausal_head", cls)` | solve.py's `_deref_walk_py` rebuild | the generic `cls(**fields)` path (dataclass terms) only |
| the PredicateMeta-INSTANCE branch of `is_term_instance` / `term_field_names` (Python twins) | predicate.py | deleted; the `@dataclass` branch stays |

### Goes (C) — `clausal/logic/variables/_variables.c`

Arms 0, 2 and 3 of the task-5 map: the PredicateMeta-instance branch of
`c_is_term_instance`, and the PredicateMeta arms of `py_term_field_names` /
`c_term_field_names`. Twin parity between the C entry points and the Python
twins is preserved by removing the same branch on both sides in one commit.

### Stays until W4b (the class)

`__init__`/`__eq__`/`__repr__`/`__slots__`/`__match_args__` generation, the
`__unify__` / `__occurs_check__` hooks (their class-as-value `_CLASS_CALL`
branch is live; the instance branch becomes unreachable and is left inert),
`is_term_instance`'s `@dataclass` arm (arm 1, never goes), the four C CLASS
arms (4–7) and `py_register_predicate_meta`, `make_predicate` itself,
`_state_row()` and the detached mode, the `db=None` compile default.
Touching any of these here would turn a deletion into a redesign.

## Tests

Two kinds, decided per test by READING it, never by a sweep:

* **Subject IS the instance path** → RETIRED, listed by name in the commit
  message. Known: the instance rows (`"instance"`, `cell_in_instance`,
  `instance_in_cell`) and `TestTheCorpusStillCoversInstances` in
  `tests/test_python_fallbacks.py`; the instance-construction tests in
  `tests/test_fast_construction.py`; the `_clausal_head`-built instances in
  `tests/test_predrow.py` (W2's "instances carry no state face" tests become
  moot: there are no instances) and `tests/test_funnel_accessors.py`.
* **Subject is something else, reached through an instance** → MIGRATED to
  the cell (`Pt(x=1, y=2)` instead of `Pt._clausal_head(x=1, y=2)`;
  `make_predicate(...)` without the keyword), asserting the same thing about
  the cell. Files: test_clpb, test_predicate_class_as_term_value,
  test_tagged_terms, test_second_package_copy_term_identity, the two audit
  files.

New pins: `Pt._clausal_head(...)` raises `RetiredStateError`;
`make_predicate("x", ["a"], instances=True)` raises `TypeError`; a
`PredicateMeta` class called with keywords builds the cell with fresh
`Var()`s for missing fields (unchanged, pinned beside the tombstone so the
two cannot drift).

## Gate

* House suite: **NEW 0**; **GONE = exactly the retired tests**, by name, and
  nothing else. A GONE not on the list is a defect in the change.
* Package gate (`tools/w3_package_gate.sh`): NEW 0 / GONE 0.
* C: the `.so` is built in a same-sha worktree and rename-swapped under live
  importers (never `build_ext --inplace` on a tree long-lived processes
  imported); the positive control OBSERVES the removal — a probe that the
  Python twin and the C entry point agree that a `@dataclass` instance is a
  term instance and that no PredicateMeta instance can be constructed to
  disagree — not an exit code.
* Barrier scan of the range before landing (0 hits on closed-side terms).

## Out of scope, named so it is not absorbed

W4b (mint handles with the import name at load; the 293 references / 64
`isinstance` sites / 12 `make_predicate` minters; the four C class arms;
`_state_row` and the detached mode; the `db=None` compile default). W5's
remaining arms. The downstream side is already at zero for this landing:
0 `_get_dispatch` calls, 0 vocabulary `isinstance`, the 31 hold-and-call
sites migrated (2026-09-22).

## Risks

* A test that used an instance incidentally and asserts on instance-only
  behaviour (attribute access) will fail on migration; that is the review
  reading each file, not a sweep.
* Out-of-tree code minting instances (`packages/`, the 11 implementors):
  the W3 package gate sees the three packages that implement
  `_get_dispatch`; the other nine are ungated, and the tombstone + refusal
  are what makes a miss loud rather than silent.
* The `.so` swap: procedure and its traps are in the durable record
  (rename-swap under live importers; the clone's `.so` went stale once).
