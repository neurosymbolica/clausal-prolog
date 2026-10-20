# fix-A01: Seg* _unify_gens pins dead Trails (A01-F005, memory)

**Severity: memory.** The F015 generator cache
(`SegList._unify_gens`, `terms.py:257-262,418-428`; SegString and SegBytes
mirror it) removes an entry only when its generator raises StopIteration. A
suspended generator's frame holds a strong ref to its Trail, so every
(target, trail) pair that was not driven to exhaustion pins its Trail — and
everything the trail entries reference — for the lifetime of the Seg* term.
Probe: 20/20 dead trails stayed alive; a long-lived SegList (e.g. stored in a
fact) grows one entry per query forever. `TestF005UnifyGensRetention`.

## Fix options (pick one; must preserve the F015 mark/unify/undo drive
pattern relied on by the compiler's head matcher — see the regression guard
`test_f015_drive_pattern_enumerates_all_splits`)

1. **Weak-key by trail.** Key the cache on `weakref.ref(trail)` (Trail has
   `tp_weaklistoffset` already) with a callback that pops the entry; the
   generator must then hold the trail weakly too — restructure
   `_seglist_unify_gen` to take the trail per-`next()` step instead of
   closing over it (e.g. cache stores (gen, weak_trail) and `__unify__`
   passes the strong trail in via `gen.send(trail)`).
2. **Bounded cache + explicit invalidation.** Cap `_unify_gens` (e.g. 8
   entries, LRU); exhausting or evicting closes the generator
   (`gen.close()`). Cheap, keeps semantics; worst-case re-enumeration on
   eviction restarts from the first split, which is indistinguishable from a
   fresh trail state for a correctly-driven caller.
3. **Trail-callback cleanup.** On first caching for a trail, use
   `trail.record(cleanup)` so unwinding past the creation mark drops the
   entry. Aligns lifetime with backtracking, but `record` entries fire on
   *any* undo past them — verify the drive pattern (undo between splits)
   doesn't evict the live generator (it would: the caller undoes to a mark
   taken *before* the first `unify` call — so this option likely breaks
   F015; prefer 1 or 2).

## Verify

Flip `TestF005UnifyGensRetention::test_dead_trails_are_collectable` to plain
assert; `test_control_exhausted_generator_is_dropped` and the F015 drive
regression guard must stay green. Apply the same fix to SegString/SegBytes.
