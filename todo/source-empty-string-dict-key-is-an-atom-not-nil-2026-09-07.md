# `{"": 1}` in source is the atom `("",)`; a Python-side `d[""]` is nil

Filed 2026-09-07 by the Task 15 fix-round-3 ledger (deferred there, not
fixed). Belongs with `implementation_plans/dict-atom-keys-vs-predicates.md`.

## The inconsistency

`""` is the empty list, which is the reserved atom `'[]'` — so
`DictTerm.__init__`/`as_dict_key` fold a `""` KEY onto `()`
(`atoms.NIL_KEY`), and `d[""]`, `d[[]]`, `d[b""]` and `d[()]` are one key.

But a `.seam` source dict written `{"": 1}` does not produce a `""` key.
In `-double_quotes(atom)` mode (the default) the compiler's `visit_Constant`
turns the literal into the ATOM cell `("",)` — an atom whose spelling is the
empty string, which is a *different* atom from `'[]'`. So:

```
{"": 1}      # source, atom mode  -> key ("",)   -- the empty-spelling atom
{'': 1}      # source             -> key ("",)   -- same
DictTerm({"": 1})   # Python side -> key ()      -- nil
```

The two never meet: a program that writes `{"": 1}` and then looks the key
up from Python with `d[""]` misses, and vice versa.

## Why it is not simply a bug in the key path

The nil folding is right: `""` the TERM is nil. What is questionable is the
COMPILER's reading — that a quoted empty literal is an atom whose spelling is
`""`. There is no way to write the atom `'[]'`'s *spelling* as an empty
string, and ISO has no empty-spelling atom at all: `''` is a legal atom token
in ISO, distinct from `[]`, so both readings are defensible and the choice is
a design question, not a defect.

## What to decide

Either:

1. **The empty-spelling atom stays.** `("",)` is a real atom distinct from
   `'[]'`, and the inconsistency is only that `as_dict_key` folds the *bare*
   `""` — a Python-side spelling — onto nil. Then Python callers must write
   `mint("")` for the atom and `[]`/`()` for nil, and the folding is correct
   as it stands. Document it and move on.
2. **There is no empty-spelling atom.** A source `''`/`""` in atom mode reads
   as nil, exactly as `'[]'` does, and `visit_Constant` gains the same
   substitution the `'[]'` spelling got in fix round 1. Then all four
   spellings agree end to end.

Option 2 is the "one term, one answer" line the rest of Task 15 took, but it
retires a term (`("",)`) that source can currently write, so it needs the
same operator ruling `'[]'` got — and it interacts with the atom-key /
predicate-name question the companion plan is already weighing.

## Where it bites today

Nowhere in-tree: no fixture or module uses an empty-spelling atom as a dict
key. It is a latent trap for a downstream program that mixes source-written
and Python-built dicts, which is exactly the shape fix round 2 and 3 were
closing elsewhere.
