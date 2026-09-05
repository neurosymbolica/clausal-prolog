# Imported same-spelling ATOM shadows a local arity-N predicate at the call site

**Reported:** 2026-09-06 by a downstream peer (their verification
sweep). Three corpus domains green at their corpus gate on 2026-09-04,
RED after the P3-1 atom pivot (28f93bd6), corpus files byte-identical:
downstream domain A (`dependents_count/2`), downstream domain B
(`query_date/2`), and — plausibly, unconfirmed —
downstream domain C (a `what_if` over
module-qualified atoms; its `get/3` symptom may be a different shape).

**Reproduced on feat/p33-state-reloc at f5ac6b1b** (scratch probe, not a
test yet):

```
% sib.clausal
-module(pp_sib, [dependents_count, other(X)])
other(1),

% main.clausal
-module(pp_main, [go(X)])
-private([a, b])
-import_from(pp_sib, [dependents_count, other])
dependents_count(a, 2),
dependents_count(b, 3),
go(X) <- dependents_count(a, X),
```

Loading `pp_main` succeeds (the Task 4 compile-time atom-as-functor check
sees the LOCAL functor signature for `dependents_count/2` and correctly lets
the program through), then `call(mod.go, X)` dies:

```
existence_error(procedure, dependents_count/2,
  "atom 'dependents_count' is not callable at arity 2 (resolved via a data
   reference; define or import the predicate, or call it by its local name)")
```

raised by `clausal/logic/predicate.py::_dispatch_at` (str branch).

**Cause.** The call site lowers through the `-import_from` remap, keyed on
the NAME alone, to the sibling's arity-0 atom (a plain str post-pivot). The
importer's own `dependents_count/2` row — the thing the program means — is
never consulted. Task 4 covered imported FUNCTOR + local atom (functor wins)
and imported atom + local atom (refused, located); imported ATOM + local
arity-N DEFINITION is the gap.

**History.** Not a broken contract: the `_dispatch_at` str-branch comment
(P3-1 ruling, 2026-09-04) records that pre-pivot this shape worked only via
the class re-minting quirk and that dispatch-to-local-predicate routing was
deferred to P3-3's qualified-goal design. Green by accident, broken at the
pivot, owed by P3-3.

**Ruling (P3-3 controller, 2026-09-06).** Call-site resolution is keyed on
`(name, arity)`: a local arity-N definition wins over an imported
same-spelling ATOM (an atom has no arity-N meaning, so nothing is ambiguous;
ISO treats `f` and `f/2` as unrelated objects). An imported FUNCTOR of arity
N colliding with a local arity-N definition remains a genuine collision —
unchanged by this fix. Lands as an added task on the P3-3 branch (the fix
sits in the transformer region Task 4 rewrote; a main-line hotfix would
conflict at merge), after Task 5. The downstream peer's corpus gate at the landing sync
must show its affected domains green again.

**Fix sketch.** In `EmbedTransformer._visit_call_func` (term_rewriting.py),
when the applied name is in `_import_remap` AND the importer establishes a
functor signature for `(name, N)` locally (clauses or `-module` functor
list — the same fact `_settle_atom_functor_sites` / `functor_signature_for`
already read) AND the imported binding carries NO functor signature at any
arity, lower as the LOCAL call (so the emitter reaches `$disp_<name>_<N>` /
the local row), not the remap. Pin with an owner+importer fixture pair
driven end-to-end (load + answers), plus the negative pin: imported FUNCTOR
of arity N + local arity-N clauses keeps today's behaviour.

---

## Sub-shape 2 (same root, arity-0 corner): imported declared atom that also has a /0 fact arrives as the CLASS

**Reported:** 2026-09-06, same peer sweep — downstream domain C:
`get(PROFILE, key_atom, …)` fails on a
PRESENT key in its public-interface tests (3 tests) and a what_if query test
(1 test); the domain's other 5 test files are green on the branch. The owner declares the key atoms in its
`-module` list AND writes explicit 0-arity facts for them (`key_atom,`).

**Reproduced on feat/p33-state-reloc at f5ac6b1b** (scratch probe):

```
% owner3.clausal
-module(pp_owner3, [kfact, kplain, prof(P), read_fact(P, V), read_plain(P, V)])
kfact,
prof({kfact: 1, kplain: 2}),
read_fact(P, V) <- get(P, kfact, V),
read_plain(P, V) <- get(P, kplain, V),

% importer3.clausal
-module(pp_importer3, [iread_fact(V), iread_plain(V), iread_fact_pass(V)])
-import_from(pp_owner3, [kfact, kplain, prof, read_fact])
iread_fact(V) <- (prof(P), get(P, kfact, V)),
iread_plain(V) <- (prof(P), get(P, kplain, V)),
iread_fact_pass(V) <- (prof(P), read_fact(P, V)),
```

Observed: owner namespace `kfact` → `PredicateMeta` class, `kplain` → `'kplain'`; dict-literal keys are
both `str`; owner-side `read_fact` → `[1]` (the owner's compiler lowers the declared atom as the str in
data position); importer namespace `kfact` → the CLASS (the binding is what `-import_from` copies);
importer-side `iread_fact` → `[]` (class used as dict key; silent miss on a present key), `iread_plain`
→ `[2]`, `iread_fact_pass` → `[1]`.

**Cause.** Post-pivot a name with /0 clauses binds to the predicate class; the owner's own lowering
still knows the name is a declared atom, the importer's does not — it trusts the copied binding. Pre-pivot
the /0 class WAS the atom, so class-vs-str never arose. Distinct from sub-shape 1 (no local definition
in the importer), same root: name-keyed binding conflating the atom with the /0 predicate across the
import edge.

**Ruling (P3-3 controller, 2026-09-06), folded into Task 5b.** Across `-import_from`, a name the owner
declares as an ATOM lowers as the atom str in DATA position in the importer, regardless of the owner
also holding /0 clauses for it; in GOAL position `(name, 0)` resolves via the owner's db row (Task 5
already makes bare-str atom goals in call/N resolve via the db). Pin with the owner3/importer3 pair above
(all three importer reads answer) plus a pin that `call(kfact)` / bare-goal `kfact` from the importer still
runs the /0 predicate. Cost if wrong: an importer that relied on receiving the class object for a
dual-declared /0 name through the Clausal import (not the Python `getattr` surface, which is out of scope).

---

**RESOLVED 2026-09-06 (P3-3 Task 5b, commits 044593b1..c8020d9d).** Across `-import_from`
a name the owner declares as an atom lowers as the atom str in data position in the importer
regardless of the owner also holding /0 clauses for it; goal-position `(name, 0)` resolves via
the owner's db row. Pinned by the owner3/importer3 fixture pair plus the `call(kfact)` /
bare-goal pins named in the ruling above. Follow-ups filed separately:
`todo/mixed-apply-and-read-of-imported-dual-declared-atom-gets-the-class-2026-09-06.md`
(per-predicate hole) and `todo/bare-zero-arity-predicate-body-goal-does-not-compile-2026-09-06.md`.
