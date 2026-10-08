# Compact char lists at construction; the Python boundary must be typed first

Opened 2026-10-08, after the withdrawal of `to_python_text` and a reading of Scryer's construction-time
partial-string compaction (codeberg mthom/scryer-prolog PR 3476).

## The memory case

A plain list of one-char atoms costs one 8-byte pointer per char (CPython shares one-char strs, so
no object per char, but every element is an indirection). The chars carrier `('$chars', s)` costs 1
byte per char for ASCII text (2 or 4 for wider text). Measured on 10,000 chars:

    list of 10000 chars: 80056 bytes;  str: 10041 bytes;  carrier tuple: 10097

## What the engine builds today (main at 83457c29)

    append("ab", "cd", L)    -> ('$chars', 'abcd')      carrier in, carrier out
    append([a, b], "cd", L)  -> ['a', 'b', 'c', 'd']    a plain list anywhere wins
    append(L1, L2, L)        -> list                    L1, L2 from atom_chars/2
    append(X, "cd", "abcd")  -> ('$chars', 'ab')        a split keeps the carrier
    rec(3, L), [a|T] cell by cell -> ('$chars', 'aaa')  compacted, but quadratic (below)

`append/3` picks its output by input TYPE (`_out_str` in `clausal/logic/builtins/lists.py`).

## Step 2: compact where a builtin builds a new ground list in one step

`append/3` (both directions), `atom_chars/2` (reading direction), `reverse/2`, `msort/2`, `sort/2`,
`maplist/3` results, ...: choose the carrier when every element is a one-char atom. The check runs
at C speed over data the builtin copies anyway:

```python
try:
    s = "".join(items)              # TypeError on a Var, a number, a compound
    out_str = len(s) == len(items)  # every element exactly one char
except TypeError:
    out_str = False
```

No mutation is needed (Scryer appends in place at the heap top, guarded by choice points; a Python
str is immutable and there is no heap top, and none of these builtins needs it).

## Where else, ranked by memory saved per unit of work

| where | cost | payoff |
|---|---|---|
| copy points: tabling `add_answer` (`logic/tabling.py`), findall/bagof/setof (`_findall_copy_row`, `logic/compiler/globals_env.py`), `assertz` (`logic/database.py`), `copy_term` (`builtins/inspection.py`) | ~free, the copy already visits every node | highest: long-lived terms (tables, asserted facts, collected bags) |
| one-step builtins (above) | constant factor on an existing copy | medium: results are often short-lived |
| compiler: a ground literal `[a, b]` in source | zero at run time | small; but source is where symbol lists like `[x, y]` are written, so it depends most on step 1 |
| Python -> engine (`to_clausal`) of a list of one-char strs | O(n) on an O(n) conversion | caller-dependent; needs the same declaration in the other direction |
| binding a variable in `unify` | O(n) on every bind, often partial lists | no: the hot path; Scryer's in-place append exists to avoid exactly this |

Already done: the reader (`"..."` is the carrier) and lists built cell by cell (collapsed to the
carrier when an answer is resolved; quadratic, see below).

The copy points are the analogue of a copying collector compacting while it copies.

## Step 1, the blocker: the boundary must know text from list

Inside the engine the carrier and the plain list are one term (they unify and are `==`), so
compaction is invisible there. At the boundary it is not: `to_python` hands the carrier over as a
`str`. Once `append([x], [y], L)` builds the carrier, a `py.*` adapter that wants a list of
SYMBOLS gets `'xy'`, e.g. a JAX partition spec `[[x, y]]` (two mesh axes) becomes the one axis `'xy'`.

The engine cannot tell text from a list of symbols: they are the same term. Only the consumer
knows. Proposal: an adapter declares, per argument where it matters, "list of atoms" (or "text");
`to_python` (or the adapter's conversion) then hands a carrier over as a list of one-char strs for a
"list of atoms" argument. With that in place every compaction is invisible at the boundary too, as
it is in Scryer (whose top level prints a char list in `"..."` notation however it was built).

Open questions:

- the declaration's shape (an adapter-table column? a wrapper decorator? a typed signature?);
- the default for undeclared arguments (today's rule: carrier -> str, plain list -> list);
- a census of the `py.*` adapters that take a list of atoms, before step 2 changes any builtin.

Docs already say which shape a builtin builds is not guaranteed (python_integration.md,
strings_as_lists.md), so step 2 changes no documented contract; it does change observed output.

## Construction is quadratic today (measured 2026-10-08, main at d9586317)

```prolog
rec(0, []).
rec(N, [a|T]) :- N > 0, M is N - 1, rec(M, T).
recs(0, "").
recs(N, L) :- N > 0, M is N - 1, recs(M, T), append("a", T, L).
```

    rec   n=1000     14 ms    n=4000    113 ms    n=16000   1514 ms
    recs  n=1000     72 ms    n=4000   1031 ms    n=16000  16131 ms

Both are quadratic (4x the length, ~13-16x the time), and both come back as the carrier.

- `rec`: the output list is bound AFTER the body (deferred output-mode head unification,
  `_head_has_deferred_pattern` in `logic/compiler/goal_shallow.py`), so `T` is already the finished
  carrier when `[a|T]` is built: each level prepends one char to the whole tail. The general path in
  `_head_list_unify_output` split the tail into one list entry per char and joined it again.
- `recs`: `append("a", T, L)` goes through `_as_items`, which explodes the carrier `T` into a
  list of chars, and `_seq_result`, which joins it back into a new carrier. Both run at Python
  level, once per char, so building n chars costs O(n^2) Python-level work.

**Step 1, done (this commit):** both paths now concatenate the str when the result is text anyway
(`carrier_star_concat` in `_list_unify.c` and its Python twin; a text-with-text fast path at the top
of `append/3`). Same answers; the copy is a memcpy instead of per-char Python objects:

    rec   n=16000   1514 ms -> 173 ms      n=64000  ~0.9-1.5 s (time outside the call grows linearly)
    recs  n=16000  16131 ms -> 190 ms      n=64000  1184 ms

Still quadratic in bytes copied (each level copies the tail once); step 2 removes that.

## Growing in place: what Python gives, and what it would take

Scryer appends to a partial string in place when the string ends at the heap top and no choice
point protects the old end. Clausal has no heap top. The ideas discussed, and where each stands:

**A buffer view.** A carrier `('$chars', buf, n)` whose first n chars are the term. Appending to a
view with `n == len(buf)` extends `buf` and hands back `('$chars', buf, n + k)`; the old term still
sees its n chars. A second appender to the same old view finds `n < len(buf)` and copies. That is
the heap-top rule without a heap, and needs no choice-point check: an older term only ever reads
its own prefix. The cost is a third carrier shape every consumer must accept (unify, compare, the
key, the boundary), which is why it waits on the census.

**Refcount uniqueness.** If nothing else holds the carrier, the builtin may mutate it. This
subsumes the choice-point guard (a choice point holds a reference), but today it never fires: at
`append/3` the carrier tuple has refcount 5 (the engine's Vars and suspended generator frames hold
it) against 2 when it is truly unique; only the str inside is uniquely held, by the carrier. Making
refcounts informative needs the compiler to know a variable's last use and that the call is
deterministic (Mercury's `di`/`uo` modes; WAM environment trimming). In C the check is
`Py_REFCNT`; on free-threaded builds `PyUnstable_Object_IsUniquelyReferenced` (3.14).

**What CPython already does for str.** `s += t` (`PyUnicode_Append`) resizes in place when `s` has
refcount 1, no cached hash, is not interned and is an exact `str`. A cached hash forces a copy
(measured: 200 of 200 appends copied once the hash was computed), and a missed dict lookup computes
the hash while leaving refcount 1. A str has no spare capacity: room comes from `realloc`, which
for large blocks is `mremap`, so growth measured flat at ~35-43 ns/char up to 1M chars. `list` and
`bytearray` over-allocate (~12.5%; 86 reallocations per 1M appends), so they have room by design.

**Sharing, already partly built.** `logic/compiler/destructive_reuse.py` rewrites `append/3`,
`dict_put/4`, `set_union/3` and `reverse/2` to an in-place variant when the source argument is a
variable that is dead after the call and the preceding goals are deterministic, guarded at run time by
`sys.getrefcount`. It never fires for text: the runtime variant only extends a Python `list`, and in
`append("a", T, L)` the source (first argument) is a literal. A carrier variant would meet the
refcount problem above.

## Step 2: the carrier is the indirection

Every reader of a string already goes through the carrier, so its second slot can hold something
other than a flat str, with no new term shape for unify, `==` or the tabling key:

```python
class _Text:        # carrier slot 1 when it isn't a plain str
    __slots__ = ("buf", "lo", "hi", "flat")
    # buf: shared growable buffer; [lo, hi): this term's chars
    # prepend/append writes in place only when this view's edge is the buffer's edge
    # (the heap-top rule at both ends); anyone else copies
```

`rec` prepends at `lo - 1`, `append` extends at `hi`: O(1) amortised, ~1 byte per char from the start,
no undo on backtracking (an older term only reads its own range). Hashing (dict keys, the tabling key)
and `to_python` flatten to a str, once: those are copy points anyway.

Hashing constraint: CPython 3.14 caches a tuple's hash in the tuple (measured: 3.13 hashes the
items on every `hash(t)`, 3.14 once; `getsizeof(())` 40 -> 48). So a carrier's hash is frozen the
first time anything hashes it. `_Text.__hash__` must therefore depend only on `[lo, hi)`, which never
changes (writes land outside every existing view), and must equal `hash(text)` so a `_Text` carrier
and a str carrier that spell the same text are one dict key. Flatten on first hash and cache in
`flat`. The same caching constrains mutating a carrier's str in place (item 5 below): it must also check
that the tuple's hash is uncached.

The cost is the readers. `is_chars` requires `type(x[1]) is str`, so an unconverted reader would see
a `_Text` carrier as an ordinary 2-tuple and unify or compare it WRONGLY, silently. Today:

| reader | sites |
|---|---|
| `chars_text(x)` (Python accessor) | 89 callers, one function |
| direct `x[1]` on a carrier, Python | 12 |
| C `PyTuple_GET_ITEM(s, 1)` | 24, in 2 files with `is_chars_carrier` |

- **2a**: route all 36 direct reads through `chars_text` / one C `carrier_text()`. A pure refactor,
  suite identical. Worth doing on its own.
- **2b**: the `_Text` payload, then local to the accessors and the writers (head output, `append`,
  `atom_chars`, the reader).

This replaces both the SegList tail-sharing idea and the separate `('$chars', buf, n)` shape.

## Order (ruled 2026-10-08: this order)

1. ~~Fix the two quadratics' constant factor~~ (done, step 1 above).
2. A census: which programs build char lists incrementally, how long they get, and which `py.*`
   adapters take a list of atoms (the step 1 census of the boundary section).
3. The typed boundary, then compaction at copy points and one-step builtins.
4. Step 2a (reader refactor), then 2b (`_Text`) if the census shows long incremental text matters.
5. Refcount-driven mutation of text: parked. It is checkable: CPython's own `unicode_modifiable`
   rule extended to the tuple -- carrier and str uniquely referenced, carrier `ob_hash == -1` (3.14+,
   `cpython/tupleobject.h`), str hash `-1`, not interned, exact `str`; a moved str is written back
   into slot 1, legal only because the tuple is unique. The hash checks are cheap; the blocker is
   uniqueness (refcount 5 at `append/3` today), which needs last-use and determinism analysis in
   the compiler (and see destructive reuse above). Views need none of it.

Dropped: compiler-inserted compaction calls. The copy points and one-step builtins already see every
long-lived list, and a static pass that guesses where text is built adds analysis without a case it
covers that those do not.
