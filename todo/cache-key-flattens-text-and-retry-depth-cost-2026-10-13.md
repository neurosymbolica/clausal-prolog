# solve()'s cache key flattens long text; retrying into deep recursion is O(depth) (2026-10-12)

Found while fixing the phrase/2 terminal walk.

1. **Query-cache key flattens text.** In solve(), `_goal_cache_key` → `_structural_key` →
   `flat_carrier` keys a text argument by its whole text. Every long text passed from Python into
   solve() is flattened, and the copy stays in the cache key for the cache's lifetime. Key long
   text by identity plus length, or skip caching above a size, and measure the hit-rate impact.
2. **In a deep recursion, every enclosing frame runs again for each answer or retry.** This happens even
   though the trampoline can jump straight to a choice point at any depth. Example:
   `lastc(X) --> anything, [X].` with `anything --> []. anything --> [_], anything.` and
   `phrase(lastc(X), L)`. cProfile counts calls of the compiled body `anything__2`:

   | n | anything__2 calls |
   |---|---|
   | 2000 | 2,012,998 |
   | 4000 | 8,009,998 |

   That is about n²/2. Each generator resume counts as one call, so at depth k all k nested frames
   execute again for every answer or retry. With a direct choice-point jump covering this case, the
   count would be about n. So the likely cause is that a recursive call in last position re-yields
   its child's answers level by level through the generator chain. The cause is not reaching the
   choice point. Call counts alone cannot say whether the cost is answers travelling up or retries
   travelling down.

   A second, smaller factor is Python's GC: at n=8000 the run takes 10.7 s with GC on and 5.3 s with
   GC off, because each collection scans the whole live chain.

   Next steps:
   - find where a last-position call re-yields (the trampoline's handling of a tail call that is a
     generator);
   - pin it with a call-count scaling test at 1k/2k/4k.

   Engine behaviour, not text-specific. Rebuild the repro from the rules above.
