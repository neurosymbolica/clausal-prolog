# solve()'s cache key flattens long text; retrying into deep recursion is O(depth) (2026-10-12)

Found while fixing the phrase/2 terminal walk.

1. **Query-cache key flattens text.** In solve(), `_goal_cache_key` → `_structural_key` →
   `flat_carrier` keys a text argument by its whole text. Every long text passed from Python into
   solve() is flattened, and the copy stays in the cache key for the cache's lifetime. Key long
   text by identity plus length, or skip caching above a size, and measure the hit-rate impact.
2. **Backtracking into a deep recursion costs O(depth) per retry.** `lastc(X) --> anything, [X].`
   is quadratic for compiled rules and plain lists, while one deep forward path is linear. Each
   retry re-enters through the whole recursion chain. Engine behaviour, not text-specific. Find
   where the retry walks the chain: the trampoline's resume path or generator nesting. Pin it with
   a scaling test at 1k/2k/4k.
