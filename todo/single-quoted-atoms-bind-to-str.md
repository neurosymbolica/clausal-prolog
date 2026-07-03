# CLARIFIED (not a bug/regression): quoted string literals are `str`, not `PredicateMeta` atoms

**Found:** 2026-07-02, during the EU-corpus atom/date idiom spike.
**Diagnosed:** 2026-07-02 — see "What actually happens" below. This is **working as designed**;
the "regression" framing in the original report was wrong. What remains is a *design question*
(true-atom identity for spaced/punctuated names) plus a *docs contradiction* to fix.

## TL;DR
- Quote **style is irrelevant**: `'x'` and `"x"` are identical. Python's `ast.parse` erases the
  quote character before any Clausal code runs, so there is nothing single-quote-specific to fix.
  (Verified: `pythonic_ast/conversion_from_python_ast.py:convert_constant` dispatches purely on
  `type(node.value)` — `str → StringLiteral`, `bytes → BytesLiteral`. Nothing inspects quotes, and
  it doesn't even read `Constant.kind`, so `u"…"` and plain `"…"` collapse to the same node too.)
- A string literal → runtime Python **`str`**. A bare identifier → **`PredicateMeta`** class.
  These are Clausal's **two representations of an atom**, by design.
- The "prior work" the report half-remembers is `92ce2636 refactor: declared atoms as zero-field
  PredicateMeta classes`. Its commit message scopes it explicitly: *"-private/-module **bare atoms**
  generate zero-field PredicateMeta classes."* Quoted-string → `PredicateMeta` was **never**
  implemented — so nothing regressed.

## What actually happens
Two atom representations, only one of which is a `PredicateMeta`:

| source form            | reifies as              | `atom/1` / `is_atom` | unifies with char list |
|------------------------|-------------------------|----------------------|------------------------|
| bare `art_6_1_a`, `Red`| `PredicateMeta` (class) | ✓ "declared atom"    | n/a                    |
| quoted `'…'` / `"…"`   | Python `str`            | ✗ "undeclared atom"  | ✓ (chars model)        |

Bare identifiers are `ast.Name`/`LoadName` nodes → name-resolution + auto-mint turns them into the
declared class. A quoted literal is an `ast.Constant` → passes through as a runtime `str`; there is
**no name-resolution for Constants**, so a `-private(['…'])` declaration does not mint a class for it
and a body literal never resolves to one. (Verified: the repro module has a `PredicateMeta` for
`art_6_1_a` but none for the quoted `'Regulation…'`.)

## Repro (behaviour confirmed, not a defect)
```clausal
-module(cite, [ c_undecl(V), c_decl(V), c_ident(V) ])
-private(['Regulation (EU) 2016/679, Art 6', art_6_1_a])
c_undecl(V) <- (V is 'some undeclared phrase')
c_decl(V)   <- (V is 'Regulation (EU) 2016/679, Art 6')
c_ident(V)  <- (V is art_6_1_a)
```
```
c_undecl -> ('str', 'some undeclared phrase')
c_decl   -> ('str', 'Regulation (EU) 2016/679, Art 6')   # str even though declared in -private
c_ident  -> ('PredicateMeta', art_6_1_a)                 # bare identifier is a true atom
```

## Strings-as-lists / bytes-as-lists are intact (this is the feature the report half-remembered)
Clausal keeps the Scryer `double_quotes = chars` model, and the bytes/codes analogue:
- A plain `str` unifies structurally as a **list of 1-char strings**: `"abc" is ["a","b","c"]` ✓.
- `bytes` unifies as a **list of int codes** in `[0,255]`: `b"abc" is [97,98,99]` ✓ (no fixed point;
  a byte decomposes to an `int`, never a 1-byte `bytes`).
- `str` and `bytes` are **distinct domains** and never cross-unify.
- Partial-term types `SegString` / `SegBytes`; full DCG support; docs at `docs/strings_as_lists.md`
  and `docs/bytes_as_lists.md`; suites `test_bytes_*`, `test_segbytes`, `test_chars` (217 passed on
  main as of 2026-07-02). The `feature/bytes-as-lists` branch is merged.

So a plain string is simultaneously the "undeclared atom" representation **and** a char-list — that
duality (not a lost feature) is what made the citation case confusing.

## The actual open items
1. **Docs contradiction to fix.** `docs/syntax.md:333` ("Plain string literals (without `u`) are
   atoms") and `syntax_sigs.txt:233` (`'an atom'  # atoms (titlecase or quoted string)`) read as
   "quoted = atom", but `docs/builtins.md:985` (`atom/1` "does not match plain strings") and
   `iso_prolog_compatibility_report.md:158` ("plain strings = undeclared atoms") say the opposite.
   Reconcile: a quoted literal is an atom-*value* but **not** a `PredicateMeta`. Also worth noting
   the `u"…"` prefix is currently a no-op (ignored by `convert_constant`) — either wire it up or
   drop the claim that it distinguishes char-lists from plain strings.
2. **Optional feature — `PredicateMeta` identity for spaced/punctuated names.** If citations ever
   need true-atom identity *with* spaces/punctuation, it does not exist and would need BOTH:
   (a) `-private(['quoted'])` minting a class for quoted entries, and (b) a way to *reference* that
   class from a clause body (a Constant carries no name to resolve). Non-trivial; likely not worth it.

## Workaround (adopted; recommended to keep)
Bare snake_case **identifier atoms** for statuses and citation KEYS, with the verbatim citation text
held in a separate (multilingual) translation lexicon keyed by the atom — so the logic never depends
on string identity. This is the grain-of-the-system approach; keep it regardless of item 2.

## Separate aside (not about atoms)
The report noted bare-identifier **FACT-head queries with a fresh Var returned no solution** — that
is an indexing/query matter, unrelated to atom representation. Track separately if it reproduces.
