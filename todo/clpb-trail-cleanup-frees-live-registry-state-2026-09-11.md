# CLP(B): trail-death pruning frees registry state that is still in use — SEGFAULT

**Found 2026-09-11** by the engine lane, while gating an unrelated branch
(`feat/lowercase-constants-2026-09-11`). **Not caused by that branch** — it only shifted
allocation and GC timing enough to expose it. Severity: hard crash, exit 139, and a silent
wrong-answer risk on the same path.

## Reproduction

    cd /workspace/clausal-bug-fix
    git checkout feat/lowercase-constants-2026-09-11        # with its uncommitted working tree
    python -m pytest $(head -86 <file-list>) tests/test_clpb.py -p no:randomly -q --tb=no
    # exit 139, in tests/test_clpb.py::TestBoolHook::test_bind_to_invalid_int

The crashing test passes ALONE (all 115 in that file do). It needs the ~4200 preceding tests to
have RUN, not merely to have been imported — collecting all 86 files and running only that one
test is clean.

## The proof, in three measurements

| experiment | result |
| --- | --- |
| `gc.disable()` for the whole run | **clean** |
| `gc.set_threshold(1, 1, 1)` on the BASELINE tree | clean — so it is not simply "more GC" |
| **`clpb._cleanup_trail_allocs = lambda tid: None`**, GC fully enabled | **clean** |

The third is the decisive one: neutering the trail-death pruning removes the crash while
leaving everything else alone. The fault is in that pruning.

## Mechanism

`clausal/logic/clpb.py` keeps three module-global registries:

    _var_to_id      : dict  id(Var)  -> ordering index      # keyed on a raw ADDRESS
    _id_to_var      : dict  index    -> Var                 # the ONLY strong ref to the Var
    _unique_tables  : dict  id(Var)  -> {(id(hi), id(lo)) -> BDDNode}

Cleanup is driven by `weakref.finalize(trail, _cleanup_trail_allocs, tid)`, so it fires when a
`Trail` is garbage-collected — at an arbitrary point in an arbitrary allocation. It then does

    _var_to_id.pop(vid); _id_to_var.pop(idx); _unique_tables.pop(vid)

Dropping `_id_to_var[idx]` releases the **last strong reference to the Var**, so the object can
be freed and its address reused; dropping `_unique_tables[vid]` discards the hash-consing table
that live BDD nodes were built against. The C side (`clausal/logic/_clpb_core.c`,
`c_make_node`) looks the Var up by ordinal in `id_to_var` and then keys the unique table on
`(Py_ssize_t)var` — the address — so both halves of the state it depends on can vanish or alias
underneath it.

The refcounting is per `(vid, idx)` **across trails**, and that is the gap: a live BDD, a node
held by a constraint store, or an in-flight C call is not a trail and takes no reference. When
the last *trail* dies, state that is still reachable by other means is pruned anyway.

This is the same family as a hole the code already documents and fixed once — "Pruning on the
first trail's death was a soundness hole: a second live trail's BDDs still used those ordinals"
(clpb.py, `_trail_allocs` comment). Refcounting trails fixed the two-trail case; it did not make
trails the right thing to count.

## Why it is not only a crash

If a Var is freed and a NEW Var lands at the same address, `_unique_tables[id(new_var)]` can
find the OLD variable's hash-consing table, and `c_make_node` will hand back nodes built for a
different variable. That is a wrong answer, silently, with no crash — the crash is the lucky
outcome.

## What it is not

- Not the `-constant_value` work: every sub-change in that branch was disabled individually and
  the crash survived each one; only reverting the whole transformer file (which shifts
  allocation wholesale) made it go away.
- Not a use-after-free of a Python-allocated block that `PYTHONMALLOC=debug` catches — that was
  tried and does not fire before the segfault, which fits a stale *logical* entry rather than a
  poisoned block.

## Suggested fix directions (not chosen — this needs the CLP(B) owner)

1. **Stop keying on `id()`.** The address of a non-weakref-able object is not an identity: it
   is reusable the instant the object dies. If `Var` cannot be made weakref-able, give each
   registered Var a monotonic token and key on that.
2. **Make the ordinal own the Var.** If a BDD node carries `var_id`, the registry entry for that
   ordinal must live at least as long as any node carrying it — i.e. count NODES, not trails.
3. **Never prune from a finalizer.** A finalizer runs inside someone else's allocation. Queue
   the (vid, idx) and drain the queue at a safe point (the start of a solve, say), so pruning
   cannot land in the middle of a C call that is using the entry.

## Note for whoever picks it up

The exposure is timing-dependent: the baseline tree does not crash even under aggressive GC, so
a fix must be verified against the reproduction above (the branch's working tree), not against
`main`. Keep `-p no:randomly` — the order matters.
