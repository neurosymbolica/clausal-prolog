# Trail release and bare-unify follow-ups after 9b38a0f1 (2026-10-12)

Found by the reviews of the hook-error / bare-unify candidate (landed 9b38a0f1). None is reachable
from code in the tree today; each needs a hook, finaliser or undo callback that does something
unusual, or direct Python use of the runtime helpers.

1. **Entries pushed during an undo survive the backtrack.** `trail_undo_to` releases only the entries
   present at entry. An entry pushed mid-undo stays live above the mark, and its "old value" is a
   mid-undo state:

   ```python
   t = Trail(); av = AttVar()
   put_attr(av, 'k', 1, t); t.record(lambda: put_attr(av, 'k', 'cb', t)); put_attr(av, 'k', 2, t)
   t.undo(0)   # attr None, len 1
   t.undo(0)   # attr 1, although it was absent before the first put_attr
   ```

   A binding made inside an undo callback also survives `undo(0)`. Either document it as the contract,
   or undo pushed entries in the same pass and bound only the re-arming case.
2. **Nested undo vs pushed entries is inconsistent.** An entry pushed by a callback inside a nested
   `undo(1)` is undone by the outer `undo(0)`. One pushed at the outer level stays live.
3. **The `Trail_clear` test hard-codes the type layout.** In tests/test_trail_undo_never_grows.py it
   uses `8 * i` and the default object header. Use `ctypes.sizeof(ctypes.c_void_p)`, and skip on
   free-threaded builds.
4. **Undo with pushes is O(entries x pushed),** because each step memmoves the pushed block.
5. **`Trail_dealloc` keeps its own copy of the release switch.** Reuse `trail_entry_release`.
6. **Bare `unify_with_occurs_check` on a multi-hole SegList builds a cyclic term.** For example,
   `[*A, 2, *B]` against `[A, 2]` gives True with `A = [A]`. The split binding skips the occurs check
   outside a driver. This predates 9b38a0f1 and is present on b7b93c11.
7. **A hook that undoes below the unify's mark and then returns True** makes `unify` return True with
   its bindings gone. This is memory-safe since 938db46a, but semantically wrong. The unify should fail,
   or raise a system error.
8. **A goal pushed by hand with `push_pending` while no driver owns the trail** is drained by the next
   bare unify. If it fails, it blocks every later bare unify on that trail, because the failed unify's
   undo restores the queue. No engine path does this since `_run_now` runs in place outside a driver.
9. **`pending.run_first` takes one answer and abandons the suspended drain generator.** A woken goal
   that is a generator with `finally`/undo cleanup could fire late, on GC, after the trail moved on.
   Check whether compiled bodies can carry such cleanup.
