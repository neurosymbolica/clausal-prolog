# investigate-A01: two deep-walkers with disjoint blind spots (A01-F008) — Opus

**Tagged for Opus** — needs root-cause/design work across subsystem
boundaries (A01 term layer, A04 tabling, A09 builtins), not a local patch.

Clausal has two "deeply substitute bindings" walkers and they disagree:

| Walker | Handles | Blind to |
|---|---|---|
| C `walk` (`_variables.c:1592-1638`; `clausal.logic.variables.walk`) | list, tuple, `__walk__` hooks (SegList/SegString/SegBytes/DictTerm) | **Compound, KWTerm, PredicateMeta instances**, dict, set |
| `_deref_walk` (`solve.py:49-68` Python; `_tabling_core` C twin) | list, Compound, PredicateMeta instances | **tuple, KWTerm, DictTerm, SegList/SegString/SegBytes** (no `__walk__` delegation) |

Probe-confirmed consequences (2026-07-05):
- `walk(Compound("f",(X<-1,)))` returns the original arg Var un-substituted;
  after `trail.undo` the "snapshot" decays to unbound
  (`TestF008WalkFunctorTerms`, xfail).
- `_deref_walk((X<-1, "tag"))` — tuple template — decays after undo. This is
  the **findall/bagof/setof snapshot path**
  (`compiler/control_constructs.py` `_compile_find_all_core` appends
  `$deref_walk(template)` per solution) and the tabling answer-key path
  (`tabling.py:186`). findall with a tuple / KWTerm / DictTerm / SegList
  template returns corrupted (unbound) results. Needs its own finding +
  tests in A04/A09; seam-noted in the A01 ledger for A12.

## Questions to resolve

1. Should there be ONE deep-walk (C `walk` extended with Compound/KWTerm/
   PredicateMeta arms — or `__walk__` hooks added to those classes — and
   `_deref_walk` reduced to an alias)? The `__walk__`-hook route keeps C
   generic and fixes both walkers if `_deref_walk` also learns to delegate
   to hooks.
2. `walk`'s docstring says "Rebuilds tuples and lists" — is Compound
   blindness *documented* or accidental? (SegList/DictTerm hooks suggest the
   intent was full deep substitution.)
3. Whichever walker wins must preserve: F018 str-promotion on SegList walks,
   sharing of unbound Vars (walk leaves them in place, not copies), and
   `_position` metadata on Compound (currently dropped by `_deref_walk_py`'s
   reconstruction).

## Verify

`TestF008WalkFunctorTerms` xfail flips; new A04/A09 tests for
findall-template corruption (tuple/KWTerm/DictTerm/SegList templates).
