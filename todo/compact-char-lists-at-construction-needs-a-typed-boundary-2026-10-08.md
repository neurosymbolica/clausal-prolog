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

- `rec`: the time is inside the C function `_head_list_unify_output` (profiled; not GC, checked
  with `gc.disable()`). Why it is quadratic is not yet known: find that before anything else here.
- `recs`: `append("a", T, L)` goes through `_as_items`, which explodes the carrier `T` into a
  list of chars, and `_seq_result`, which joins it back into a new carrier. Both run at Python
  level, once per char, so building n chars costs O(n^2) Python-level work.

These are bugs in the current construction paths, independent of compaction, and are the first thing
to fix: a fix that keeps the carrier and does not explode it makes `recs` O(n) copies at C speed.

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

## Order (recommended; not yet ruled)

1. Find and fix the two quadratics above. No new shape, no boundary change.
2. A census: which programs build char lists incrementally, how long they get, and which `py.*`
   adapters take a list of atoms (the step 1 census).
3. Step 1 (the typed boundary), then step 2 (compaction at copy points and one-step builtins).
4. The buffer view, only if the census shows incremental growth of long text matters after 1.
5. Refcount-driven mutation: parked; it needs last-use and determinism analysis in the compiler.

Dropped: compiler-inserted compaction calls. The copy points and one-step builtins already see every
long-lived list, and a static pass that guesses where text is built adds analysis without a case it
covers that those do not.

Open question for the operator: start with this order, or go straight to the buffer view?
