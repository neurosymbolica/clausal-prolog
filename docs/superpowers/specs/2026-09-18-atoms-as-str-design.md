# Atoms are Python strs in every position — design

Engine-lane, 2026-09-18, at the operator's direction ("long term this is the right thing to do,
and the best time is now, before more is committed downstream"). NOTHING IS BUILT. The questions
that need the operator are in §8, each with a recommendation.

## 0. Why, measured

**The ISO targets have no zero-arity compound.** Scryer and Trealla (measured 2026-09-18):
`X =.. [my_atom]` and `functor(T, my_atom, 0)` both yield the ATOM, `T == my_atom` holds;
`compound_name_arguments/3` and `compound_name_arity/3` do not exist in either (SWI additions);
Trealla reads `my_atom()` as a syntax error. The current rule — an atom in argument position is the
arity-0 cell `('atom',)` "because it is a zero-arity compound" — is the SWI-7 model, and SWI is
not a target (ruled 2026-09-06). In ISO an atom in argument position and a functor name are ONE
thing, and the engine already spells functor names as Python strs.

**What the engine does today** (probe, canonical `c070d33f`): `foo` and `'foo'` in source compile
to `('foo',)`; `"foo"` under `-double_quotes(chars)` compiles to the Python str `'foo'`; `[]` is a
Python list, `""` the empty str. So a Python str currently means a STRING (a char list), and the
atom is a 1-tuple whose only element is the functor-name spelling.

**Cost of the 1-tuple** (microbenchmarks, ns per op, 2026-09-18):

    equality equal / different      11 / 19     vs   7 / 9      (str)
    "is this an atom?" type test    44 (is_atom 56)  vs   9
    dict lookup                     14          vs   11
    engine C unify, equal           69          vs   70         (no difference)
    memory per atom                 92 B        vs   44 B
    memory of colour(red, 3)        156 B       vs   108 B

The unify path is indifferent; the type test (on every dispatch path) and memory are the costs.
The correctness/simplicity case is the larger one: one spelling of atoms, no atom-vs-predicate
name-clash machinery, no zero-field-class-as-atom legacy, and dict keys, seam identifiers and
functor names all the same object kind.

**A nested-arguments shape `(f, (a, b))` was considered and rejected** (measured): +14 ns and +48 B
per compound at construction, first-argument access 11 vs 7 ns; its only win (handing out the
argument tuple, 7 vs 38 ns) is one head matching does not need — the dispatch key is `term[0]`
plus arity and first-argument indexing reads `term[1]` directly. Index keys holding a str atom
directly are ~10% cheaper (80 → 71 ns first-arg, 54 → 50 ns two-arg).

**How committed the tree is** (census): ~300 engine sites go through the atoms API (`is_atom` 60,
`mint` 81, `spelling` 71, char-atom helpers 51, `is_zero_field_class` 13); 70 literal `("x",)`
cells in engine code; 121 `str` type tests whose MEANING (atom vs text) has to be classified one
by one; the C core special-cases tuple size 1 in 2 places and touches PyUnicode in ~78; 94 test
files hold 499 literal atom tuples. Closed side: 126 files use the seam correctly, 7 files (17
sites) write `("yes",)` literals directly — the rule violations, small enough to fix in one pass.

## 1. The representation, before and after

| term | today | after |
| --- | --- | --- |
| atom `foo` in argument position | `('foo',)` | `'foo'` (Python str) |
| functor name in a cell | `'foo'` in `('foo', a, b)` | unchanged |
| `functor(T, foo, 0)`, `T =.. [foo]` | `('foo',)` | `'foo'`, identical to the atom |
| string `"abc"` (chars mode) | Python str `'abc'` | the compact char-list carrier, §2 |
| char list `[a, b, c]` | Python list of `('a',)` | Python list of `'a'`, `'b'`, `'c'` |
| `[]` / `""` | `[]` / `''` | `[]` (canonical); the str `'[]'` is the SAME atom (§8 Q3) |
| dict key `payable_amount` | `('payable_amount',)` (or str, seam-dependent) | `'payable_amount'` |
| 0-arity predicate `p` referenced as a value | a `PredicateMeta` class or `('p',)` | `'p'` — the atom IS the name, as in ISO |

Standard order: an atom keys `(_ORD_ATOM, 'foo')` exactly as the arity-0 cell does today, so the
order is unchanged; the str branch that keyed a str as a char list moves to the carrier.

## 2. The char-list carrier

In chars mode a string is not a term type: it IS the list `'.'(a, '.'(b, …))`. The compact form
is an OPTIMISATION (a 2 KB citation as 2,000 one-char cells is a memory blow-up), so the design
question is only the compact carrier's Python shape. Recommended (§8 Q2): **a reserved-tag cell
`('$chars', "abc")`** — a str-headed tuple with a reserved head, the convention the engine already
uses for data tuples (`'()'`, `TUPLE_TAG`); marshal-clean; needs no transfer entry; unambiguous
against an atom (a plain str) and against a compound (a non-reserved head). The list-of-char-atoms
form is the SAME TERM: unify, `==`, standard order, `atom_chars/2` and friends treat the two as
one, exactly as today's str ≡ char-list equivalence does — that equivalence layer (`_text_list_eq`,
`_cons_key`'s str branch, `normalize_seg_input`, the `Seg*` walkers) re-keys from `type is str` to
the tag; it does not grow. Rejected: `('.', "abc")` — `'.'` is the cons functor and every
list-walking site would learn a second arity for it; a `str` SUBCLASS — `isinstance(x, str)` would
be true of both kinds, the ambiguity this design exists to remove.

## 3. The seam and the transfer layer

* **A Python str crossing the seam (`++`, `--`, a goal argument, a dict key) is an ATOM** (§8 Q1).
  This matches the engine and the corpus's actual use (identifiers, labels, dict keys); an opaque
  text payload as an atom is legal Prolog (`'a b c'`) and ISO's text predicates (`atom_length/2`,
  `sub_atom/5`, `atom_chars/2`) work on atoms. A Python caller who means a char list writes the
  list of one-char strs or `chars("...")` (a small helper on the seam). `text_of` keeps giving
  Python the spelling of an atom.
* **Transfer:** a bare str inside a transfer term is an atom (today: a string scalar); the carrier
  transfers as itself. `_SCALARS` keeps str; nothing else moves. The decimal/rdiv/quantity/date
  transfer forms are unaffected (str heads, int arguments).
* **The exporter** consumes engine terms and has atom-vs-string branches; it flips WITH the engine,
  in the same landing, and its emitted Prolog does not change (an atom prints as an atom, a char
  list as a char list) — which is what makes its golden files the exporter's own gate.

## 4. What disappears

* The atom-vs-predicate name-clash diagnostic (`PredicateAsTermError` at `terms_to_ast.py:1209`,
  `_make_atom_str_assign_ast`'s guard, `_make_functor_class_ast`'s guard): an atom `foo` and a
  predicate `foo/0` coexist as in Prolog; a bare name in goal position is a call, in argument
  position a value, and both are the str.
* `is_zero_field_class` as an atom test (13 sites) and the "same-spelled atom and class atom key
  alike" rule of the standard order: no class is an atom any more. This is the piece P4 (the
  PredicateMeta retirement) would otherwise have to carry — do this first.
* `mint()`/`spelling()`: `mint("foo")` returns `"foo"` and `spelling` is identity; both stay as the
  API so the 300 sites need no edit, and become trivial.

## 5. Staging

1. **Spec + rulings (§8).** Then the pre-build measurement (§7).
2. **The carrier first**, alone: introduce `('$chars', …)` as what the reader produces for a chars
   string and what the equivalence layer keys on, while atoms are still 1-tuples. This is the step
   that makes a Python str unambiguous during the flip, and it is separately gateable.
3. **The atom flip behind the atoms API**: `mint`/`is_atom`/`spelling`/`char_atom` change once; the
   70 literal cells and the classified `str` tests are edited; the two C sites; the 13
   zero-field-class sites and the name-clash diagnostic deleted.
4. **Tests**: the 499 literal atom tuples in 94 files by a mechanical rewrite (`("x",)` → `"x"`),
   then the tests that asserted str-means-string by hand.
5. **Closed side, same window**: the 17 direct-representation sites (harness-batch-lane's files);
   the seam rule of §3 announced to every lane BEFORE step 2 lands so the 17 does not grow.
6. **Landing window** (the operator's, 2026-09-18): after iso-export-lane's first G3 result on a
   frozen sha is recorded; harness-batch-lane re-baselines the 82 the same day (every row moves by
   construction — a re-baseline, not a null); corpus-lane's rulebase axis is unaffected (sources
   never see the representation).

## 6. Gates

Engine failure-set A/B on a clean base per step; the exporter golden files; the twin/wrapper
parity matrix (`tests/test_comparison_twin_parity.py`) and the standard-order suite; the
transfer round-trip tests; a positive control per step (a site that must fail when the step is
reverted). Harness: a RE-BASELINE at the landing sha, then the usual 82-row diff for everything
after. The barrier scan on every crossing commit.

## 7. Measure before building

* Engine sites that reach around the atoms API: every `type(x) is tuple and len(x) == 1` /
  `x[0]` on a suspected atom outside `atoms.py` (the 70 literal cells are the known ones).
* The 121 `str` type tests classified by MEANING — "this is text" vs "this is a name" — because
  the flip inverts the first class and keeps the second; the count of the first is the real size
  of step 3.
* The exporter's atom/string branches (`clausal_to_prolog.py`), counted.
* Closed side: harness-batch-lane's exact list of the 17 sites, and whether any harness body
  passes a Python str MEANING text through the seam (that is the one seam semantics change, §3).

## 8. Parked for the operator (recommendations in bold)

* **Q1.** A Python str crossing the seam is an ATOM. **Yes.** Text is a list of one-char strs or
  `chars(...)`.
* **Q2.** The compact char-list carrier is the reserved-tag cell `('$chars', "…")`, equal to the
  list-of-chars term. **Yes**; tag spelling open (`'$chars'` follows `'()'`).
* **Q3.** `[]` stays the Python list as the canonical empty list/`'[]'` atom, and the str `'[]'`
  is the same atom. **Yes.**
* **Q4.** `p()` in a `-module`/`-private` export list stays the spelling for "a 0-arity
  PREDICATE" (a declaration, not a term); `p()` in term position stays a syntax error, as in the
  targets. **Yes.**
* **Q5.** The exporter flips in the same landing as the engine. **Yes.**
