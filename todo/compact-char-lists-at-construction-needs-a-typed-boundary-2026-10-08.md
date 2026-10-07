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
    rec(3, L), [a|T] cell by cell -> ('$chars', 'aaa')  already compacted

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
carrier when an answer is resolved).

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
