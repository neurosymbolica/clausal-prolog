# Standard Order of Terms — `@<`, `compare/3`, `=..`

**Date:** 2026-09-09
**Status:** approved by the operator, ready for a plan
**Predecessor:** `docs/superpowers/specs/2026-09-08-iso-canonical-form-operators-design.md` (§3.3
designates these predicates as the answer to the `type_error(evaluable, date/3)` red)

## 1. Why

`feat/iso-compare-builtins-2026-09-09` (landed, main `46712278`) gave the corpus ISO
spellings for arithmetic comparison, unification and identity. It deliberately did NOT
deliver standard-order comparison, so a date-comparing site still has no correct spelling
to migrate to and five G3-only-red domains remain blocked. This spec closes that.

The work is mostly EXPOSURE, not invention. `_standard_order_key` in
`clausal/logic/builtins/_helpers.py` already implements a total standard order, already
drives `sort/2` and `msort/2`, and was verified against Scryer on 2026-09-09 for all six
ISO ordering rules (§2). Two corrections to that order are in scope; everything else is
a wrapper.

## 2. The ISO order, verified

Measured 2026-09-09, Scryer and Clausal independently, all six agreeing:

| ISO rule | example | Scryer | Clausal |
| --- | --- | --- | --- |
| Var before Number | `X @< 1` | yes | yes |
| Number before Atom | `1 @< a` | yes | yes |
| Atom before Compound | `a @< f(1)` | yes | yes |
| Compound: arity before name | `g(1) @< f(1,2)` | yes | yes |
| Compound: args left to right | `f(1) @< f(2)` | yes | yes |
| `[]` is an atom | `[] @< a` | yes | yes |

Bands today: `0 var, 1 number, 2 atom, 3 compound, 4 dict, 5 set, 6 opaque`.
Dict, set and opaque are Clausal extensions and sit AFTER every ISO band.

**Conformance rule for every decision below:** an extension may place a non-ISO type
anywhere, but it may never change the relative order of two ISO terms. Moving `Quantity`
into the number band (§3) satisfies this, because no ISO term's position relative to
another ISO term changes.

## 3. Change 1 — `Quantity` joins the number band

Today `Quantity` keys in the OPAQUE band (6), so `5 m` sorts after every atom, compound,
dict and set, and cross-dimension comparison falls back to `repr`. Under the planned
`strict_units` directive (`todo/strict-units-directive-2026-09-09.md`) EVERY number in a
program becomes a `Quantity`, which would put every number above every atom and compound.

The number-band key becomes:

    (_ORD_NUM, dimension_signature, magnitude, type_rank)

- `dimension_signature` — `()` for plain numbers AND for dimensionless quantities; otherwise
  the sorted tuple of `(unit_name, exponent)`. Total and stable, so cross-dimension
  comparison never raises and never reaches `repr`.
- `magnitude` — the numeric value.
- `type_rank` — see §4.

So `5000 ()` sorts immediately beside `5000` rather than after every compound, and
dimensioned values group by dimension and then by value.

## 4. Change 2 — the tiebreak, derived from `==` rather than tabulated

ISO 7.2.1 requires that for numbers of equal value a FLOAT precedes an INT, and ISO
guarantees the identity

    compare(=, X, Y)   holds exactly when   X == Y

Clausal breaks this today: `key(1) == key(1.0)`, so `compare/3` would answer `=` while
`'=='(1, 1.0)` answers false (landed in `46712278`). Scryer: `compare(O, 1, 1.0)` gives
`>`, and `sort([1, 1.0], L)` gives `[1.0, 1]` — both kept.

`type_rank` restores it — but only after a defect found during spec review is fixed.

### 4a. `'=='` is not transitive today, and must be before any of this works

Measured 2026-09-09 on main `46712278`:

    1.0 == Decimal(1)   ->  True
    Decimal(1) == 1     ->  True
    1.0 == 1            ->  False      <- transitivity requires True

`_numeric_tag` leaves `Decimal`/`Fraction` UNTAGGED (the A01-D001 residual), so they read
as identical to both `int` and `float`, which are not identical to each other. Before
`46712278` the relation was transitive-but-non-ISO; making `1.0 == 1` false without
touching `Decimal` produced a relation that is not an equivalence at all.

Order-equality is necessarily transitive, so NO ranking function can satisfy the ISO
identity while this holds. **Fix first:** `_numeric_tag` returns `type(x)` for `Decimal`
and `Fraction` as it already does for `float`, making every numeric type its own kind.
This is a two-line change to a function that returns a TYPE OBJECT — nothing is wrapped,
no term representation changes, and arithmetic never sees it.

**Scope ruling (operator, 2026-09-09):** the COMPARISON site only.
`clausal/logic/tabling.py::_normalize_for_key_py` and its C twin
`_tabling_core.c::do_normalize` share the same residual and are deliberately NOT touched —
a C rebuild and P52 lock-step do not belong in a branch about term ordering. The resulting
inconsistency (tabled answer dedup still collapses `Decimal(1)` with `1` while `'=='` now
distinguishes them) is filed as `todo/a01-d001-tabling-half-2026-09-09.md`.

### 4b. The ranking

With every numeric type its own kind, `type_rank` is total and the ISO identity holds for
ALL numeric types, not a subset:

- float before int, per ISO 7.2.1;
- `Decimal`, `Fraction` after those, each its own rank;
- `Quantity` last — an extension never interleaves between two ISO terms (§2).

A dimensionless `Quantity` therefore sorts ADJACENT to its plain-number twin, not equal to
it: `'=='(Quantity(5000, {}), 5000)` is false (measured), so `compare/3` must not answer `=`.

**Blast radius, and it is real:** `sort/2` stops collapsing `1` and `1.0` into one element, and stops collapsing
`Decimal(1)` with `1`.
This requires a full-corpus gate BEFORE landing, with the diff reported rather than
summarised. Backing out is a one-line revert of `type_rank`, independent of §3 and §5.

## 5. Change 3 — the `sort/2` fast path is unsound and must be gated

`_standard_order_sorted` tries `sorted(items)` before falling back to the key. Measured:

    _standard_order_sorted([1, 1.0])  ->  [1, 1.0]
    _standard_order_sorted([1.0, 1])  ->  [1.0, 1]     same multiset, different answer

So `sort/2` has no stable opinion about equal-value int/float today, and no tiebreak can
be implemented while that path survives. Worse, SAME-TYPE is not a sufficient guard —
measured 2026-09-09:

    [('f',1,2), ('g',1)]   native = [f/2, g/1]   keyed = [g/1, f/2]   DISAGREE

All tuples, one type; cells key ARITY-FIRST per ISO 7.2.1 while Python compares tuples
elementwise. The guard is therefore a membership test against a set of types whose native
`<` is KNOWN to agree:

    _NATIVE_ORDER_SAFE = frozenset({int, float, bool, str, bytes, _Decimal, _Fraction})

    def _standard_order_sorted(items):
        types = set(map(type, items))               # one C-level pass
        if len(types) == 1 and types.pop() in _NATIVE_ORDER_SAFE:
            return sorted(items)
        return sorted(items, key=_standard_order_key)

- `set(map(type, items))` runs in C and is bounded by the number of DISTINCT types.
- `type()` not `isinstance()`: exact identity keeps subclasses off the fast path. This
  matters for `bool` (a subclass of `int`) and for any future `StrictQuantity`.
- Membership is a POSITIVE claim needing measurement; absence costs only speed. `tuple` is
  excluded because it is proven wrong; `list` is excluded because it is NOT proven right.
- This removes the old `try/except TypeError` fallback, which discovered incomparability by
  catching a failure. `Quantity.__lt__` raises `UnitsMismatch`, which is NOT a `TypeError`
  (measured 2026-09-09), so the fallback never fires and the exception ESCAPES TO THE CALLER:

      _standard_order_sorted([3, Quantity(5, {"m": 1}), 4])   -> raises UnitsMismatch
      _standard_order_sorted([Quantity(5, {"m": 1}), Quantity(2, {"kg": 1})]) -> raises

  So `sort/2` and `msort/2` CRASH TODAY on any list mixing dimensions, or mixing quantities
  with plain numbers, while the key handles all of them (`sorted(..., key=...)` gives
  `[3, 4, 5 m]`). Task 3 is therefore a live bug fix, not only a correctness prerequisite:
  the type gate sends every such list to the key path. Corrected 2026-09-09 — an earlier
  draft of this section said the path "returned nonsense instead of raising", which was
  reasoned rather than measured, and wrong.

If measurement shows the scan costs more than the keys it saves, DELETE the fast path
instead. That decision is the implementer's, on evidence, and must be recorded.

## 6. What gets added

All in `clausal/logic/builtins/iso_compare.py`, reachable from `.clausal` ONLY as quoted
canonical forms, consistent with the predecessor spec. No infix surface is added and no
existing infix meaning changes.

| name | behaviour |
| --- | --- |
| `'@<'/2`, `'@>'/2`, `'@=<'/2`, `'@>='/2` | compare two standard-order keys; succeed or fail; NEVER raise |
| `'compare'/3` | unify arg 1 with the atom `<`, `=` or `>` |
| `'=..'/2` | canonical spelling over the EXISTING `univ/2` (`clausal/logic/builtins/inspection.py:465`); no new logic |

`functor/3` and `arg/3` already exist (`inspection.py:352`, `:423`) and are out of scope.

## 7. Testing

Follows what worked on the predecessor branch, including its failures:

1. **Scryer oracle rows** for every operator. Engine assertions live in tests SEPARATE from
   oracle assertions, so a missing binary cannot retire engine coverage (42 of 52 tests
   silently skipped on the last branch).
2. **The identity property test — the primary instrument.** Over a matrix of term pairs
   spanning every band: assert `compare(=, X, Y)` holds exactly when `'=='(X, Y)`. This
   encodes ISO's guarantee directly and would have caught the `1`/`1.0` contradiction
   before it shipped.
3. **A discrimination property test**: no two of `@<`, `@>`, `@=<`, `@>=` agree on all
   rows. The predecessor shipped six comparison operators that were indistinguishable
   from each other for three review rounds.
4. **Every test proven to FAIL before its fix**, with the observed output recorded. A test
   that has only ever passed proves nothing.
5. **Full-suite gate** by failure-NAME set, ANSI-stripped, both sets asserted non-empty.
   **Plus a corpus gate** for §4 and §5, since both change `sort/2` output.

## 8. Out of scope

- `predsort/3`, `sort/4`, `msort/2` extensions — YAGNI.
- The `Seg*` opaque-band inconsistency (a ground `SegString(["ab"])` does not sort beside
  the equal `"ab"`). Pre-existing, already filed, and walking inside the key changes the
  cost of every sort.
- The TABLING half of A01-D001 (`_normalize_for_key_py` and the C twin `do_normalize`).
  §4a fixes the comparison site only; the tabling half is filed as a todo.
- Narrowing engine-wide `unify` (`todo/iso-unify-conflates-int-and-float-2026-09-09.md`).
- The `#` family's error behaviour (`todo/clp-domain-spans-reals-while-clpz-is-integers-2026-09-09.md`).
