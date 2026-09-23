# W4b-2: F2b design, and the eight hard families sized — 2026-09-23

Read-only pass over `/workspace/clausal` main (`28982190`). Every claim below
is a file:line citation, the verbatim output of a probe run via
`./venv/bin/python -c "..."` from the repo root during this session, or is
marked **INFERENCE** where I reasoned from the code's stated design rather
than running something. No source was changed. `resolve_predicate_row` (F1)
and `is_declared_predicate` (F2) are read as landed on
`feat/w4b2b-resolver-2026-09-23` (`clausal/logic/predicate.py:1556-1690`,
not yet on main) and taken as given, per the brief.

---

## Job 1 — F2b: the 13 arity-agnostic rows

### Q1 — what question are these sites really asking

**One sentence:** *"Does this namespace binding denote a PREDICATE (so a bare
reference to it in term position means the atom of its own name), as opposed
to a data functor or an ordinary value — regardless of what arity the
predicate happens to be declared at?"*

Checked against the actual code at five of the thirteen (the full 13 are
listed in Q4's table below):

- `compiler/terms_to_ast.py:1225` — `if isinstance(term, PredicateMeta): return ast.Constant(value=term.__name__)`, directly under the comment *"A predicate CLASS (arity ≥ 1 — the zero-arity/atom case returned above) in term position. Almost always the atom/predicate name clash."* No arity is read or compared anywhere in the branch — confirms the sentence exactly.
- `compiler/terms_to_ast.py:1067` — `if not isinstance(_binding, PredicateMeta):` guards OWA's "does this dotted-free name resolve to a predicate (so a goal, not data) or should it fall through to a cell". Comment: *"a goal is not data, even in a flagged module"*. No arity read.
- `logic/compiler/arg_index.py:184` and `:386` (rows 49/50) — `if isinstance(arg, type) and isinstance(arg, PredicateMeta): return (arg.__name__, 0)`. The comment says this exists so *"atom-headed clauses are indexable again"* — the index key is unconditionally `(name, 0)`, independent of whatever arity the predicate class actually carries (a `p/3` class reached here bare still keys as `(p, 0)`, matching the sentence's "exactly as a `p/0` would").
- `logic/builtins/inspection.py:394` (`functor/3` construct, row 43) — `isinstance(name_val, (PredicateMeta, int, float, bool, bytes))` sitting inside an ISO 8.5.1.3(e) **atomicity** gate. `PredicateMeta` beside four scalar types is the tell (per `w4b1-site-classification`'s own "generalisable tell", fix round 1): the question is "is this value atomic", and a predicate class answers yes for the same name-denotes-itself reason, with no arity check anywhere in the branch.

All four confirm the sentence with no counter-example. (`logic/seam.py:153`,
`logic/constants.py:258`, `compiler/head_match.py:757` were also opened during
this session for Job 2/F5 purposes and show the identical arity-blind
`isinstance(binding, PredicateMeta)` shape — see the code quoted there.)

### Q2 — is "declared as a predicate at *some* arity" the right test, and does `arities_for` answer it

The test is right in spirit but **`Database.arities_for` cannot be used to
implement it** — it silently under-reports for two of the containers
`declared_kind` itself treats as `"predicate"`. Verified by probe
(`clausal/logic/database.py:525-538` is `arities_for`'s body; it scans
`self._rows` plus `self._clauses`, `self._dispatch`, `self._lazy_recompile`,
`self._signatures`, `self._dynamic` — **not** `self._predicate_export` or
`self._adopted`):

```
db.mark_dynamic('p', 1)
  arities_for('p')      -> {1}                      # correct
  declared_kind('p', 1) -> 'predicate'

db2.mark_predicate_export('q', 3)     # bare name/arity -module export, no clauses
  arities_for('q')       -> set()                    # WRONG — misses it
  declared_kind('q', 3)  -> 'predicate'

db3.adopt_row('r', 1, <row from db_owner>)     # -import_from
  arities_for('r')       -> set()                    # WRONG — misses it
  declared_kind('r', 1)  -> 'predicate'

db.mark_dynamic('p', 1); db.mark_dynamic('p', 2)
  arities_for('p')       -> {1, 2}                   # correct, two arities

db4 (nothing declared)
  arities_for('nope')    -> set()                    # correct, empty

db5.declare_functor('d', ('x', 'y'))          # DATA functor
  arities_for('d')       -> set()                    # correctly excludes data
  declared_kind('d', 2)  -> 'data'
```

So: for a name declared at two arities via clauses/dispatch/`-dynamic`,
`arities_for` is correct (`{1, 2}`). For a name declared at *no* arity, it is
correctly empty. But `mark_predicate_export` (a bare `name/arity` entry in a
`-module`/`-private` export list — the mechanism `declared_kind`'s own
docstring cites the real corpus example `gv_free/1`,
`tests/fixtures/gate_vocab.clausal`, for) and `adopt_row` (`-import_from`)
are both real, in-corpus ways a name becomes a declared predicate with **no**
row and **no** entry in any container `arities_for` scans. `arities_for`
would answer "not declared anywhere" for a predicate `declared_kind` calls
`"predicate"` outright. Building F2b on `arities_for` would therefore
misclassify exactly the two declaration shapes W2's discipline exists to
catch — an export-only predicate and an imported one — as "not a predicate",
sending a bare reference to either down the data/cell-construction path
instead of the atom-coercion path. **`arities_for` does not answer the
question; a new existence-only scan over the same containers
`declared_kind` consults is needed** (sketched in Q4).

### Q3 — required answers for the hazard cases

| input | required answer | why |
|---|---|---|
| a `-hide` **data** atom's binding | `False` | it is data, never a predicate reference; per `w4b2-open-questions-2026-09-23.md` Q1.1 Fact B, `-hide` does not currently register into `db._declared` either, so it is invisible to *every* accessor here — it answers `False` today for the same reason `is_declared_predicate` does (nothing affirms it as a predicate), not because of special-casing |
| a plain, non-mangled `str` that happens to spell a declared/builtin name | `False` | the sibling resolvers' hazard list (`resolve_predicate_row`/`is_declared_predicate` docstrings, `predicate.py:1596-1600`, `1690-1693`) is explicit: "a plain non-mangled string (even one that happens to spell something)" must resolve to nothing — a bare string is text, not a binding, and letting it through would let an ordinary atom masquerade as its own predicate |
| a `@dataclass` class | `False` | this is the row-23/43/44/46/49/50/52 finding itself: "there is no established rule that a bare dataclass CLASS reference means the atom of its name" — widening to accept any zero/N-field class here is exactly the regression `w4b1-site-classification`'s fix round 1 caught (`functor(T, SomeDataclass, 0)` must keep raising `type_error(atomic, ...)`, not silently bind `T` to the class) |
| an ordinary atom (plain str) not declared anywhere | `False` | matches `declared_kind`'s `None` — an atom that spells nothing meaningful is just an atom, no coercion applies |

### Q4 — proposed signature and why one function cannot serve both

```python
def is_declared_predicate_name(binding) -> bool:
    """F2b: True iff *binding* denotes a declared PREDICATE, AT ANY ARITY,
    era-agnostic.  The predicate-name-as-atom coercion population — 13 of
    F2's original 15 rows, arity-independent by design (a bare reference to
    p/3 denotes the atom 'p' exactly as a bare p/0 would).

    Two cases (same six hazard-1 shapes as resolve_predicate_row/
    is_declared_predicate refuse in every other case):

    1. binding is a PredicateMeta class -> True, unconditionally.  None of
       the 13 sites this serves check arity on the class arm today (bare
       `isinstance(x, PredicateMeta)`), so this preserves exactly that.
    2. binding is a mangled atom naming a loaded Clausal module -> True iff
       the owner db affirms the functor as a predicate at ANY arity --
       NOT via Database.arities_for (Q2: misses _predicate_export and
       _adopted).  Needs a new Database method, e.g.:

           def is_predicate_name(self, functor: str) -> bool:
               """True iff *functor* is declared PREDICATE at some arity --
               the arity-free twin of arities_for, scanning the same
               containers declared_kind consults (_rows, _adopted,
               _predicate_export, _clauses, _dispatch, _lazy_recompile,
               _signatures, _dynamic) rather than arities_for's narrower
               set, which arities_for's own docstring never claimed covered
               "is this a predicate" -- it was built for the import
               plant's arity question, a different caller."""
               for (f, _a) in self._rows: 
                   if f == functor: return True
               for (f, _a) in self._adopted:
                   if f == functor: return True
               for (f, _a) in self._predicate_export:
                   if f == functor: return True
               for keyed in (self._clauses, self._dispatch,
                             self._lazy_recompile, self._signatures,
                             self._dynamic):
                   for (f, _a) in keyed:
                       if f == functor: return True
               return False

       (`declared_fields_by_name`, `database.py:1023-1029`, is precedent
       for a "by name, arity stripped off" scan already living on
       Database — this mirrors its shape for the predicate side instead
       of the data side.)
    3. anything else (dataclass class, plain non-mangled str, None, an
       arbitrary object, an unmangled/undeclared atom) -> False.
    """
```

**Why `is_declared_predicate` cannot also serve this:** its `arity` keyword
is *required* and was made arity-**strict** by a deliberate review-round
ruling (`predicate.py:1662-1677`) specifically to avoid the trap of a site
migrating arity-blind now and then silently flipping to arity-strict the
moment a binding becomes a mangled atom. F2b's 13 sites need the *opposite*
contract on purpose: arity is irrelevant to "does a bare reference to this
name mean its own atom". Forcing them through `is_declared_predicate` would
mean either (a) passing a fabricated arity, which is wrong for a predicate
declared at an arity other than the guess and would wrongly answer `False`
for a real predicate, or (b) loosening `is_declared_predicate` itself back
to arity-blind, which reopens exactly the typo-masking hole rows 30/31 exist
to close (a same-named, same-arity DATA functor would satisfy a
`-table foo/2` guard again). One function cannot hold both an
arity-**required-and-exact** contract and an arity-**irrelevant** contract;
this is the same shape of trap the resolver's own docstring already names,
mirrored in the opposite direction — further confirmation it is two
functions, not one with an optional parameter.

### Q5 — Row 20 ruling: **OUT** (not F2b, not F2 at all)

`compiler/terms_to_ast.py:578`, `unnameable_instance_cell_functor(term)`:

```python
cls = type(term)
if not isinstance(cls, PredicateMeta):
    return None
```

This is not a namespace-binding read. `term` is a **live instance**
(something already *called*, e.g. `Point(0, 0)` from a `-constants`
right-hand side — the function's own docstring gives this exact example),
and the test is on `type(term)`, not on a value pulled out of a module dict
or resolved by name. Two findings rule it out of F2/F2b:

1. **The predicate-vs-data discrimination it needs is not this isinstance
   check.** Per the function's own docstring, *both* a genuine predicate
   class *and* a locally-declared data functor's transient pre-rebind class
   are `PredicateMeta` at this point (*"the `-module` rewrite's class block
   runs at EXEC time, before `_process_declarations` rebinds the name"* —
   i.e. `Point` is bound to a `PredicateMeta` class for the brief exec-time
   window before the data-functor rebind to its interned string). The
   `isinstance(cls, PredicateMeta)` line filters "is this a functor class at
   all" (as opposed to some other Python value reaching a `-constants` RHS);
   the *actual* predicate-vs-data decision happens three lines later
   (`scope.get(name) is cls` for "nameable, class emission" vs. the
   signature-registry lookup for "data, cell"). F2b's contract answers "is
   this specifically a predicate, never data" — this function's guard
   answers "is this a functor class of either kind", a different, coarser
   question with no F2b-shaped fix.
2. **There is no mangled arm to give it, confirmed by the surrounding
   caller.** The one live call site
   (`compiler/terms_to_ast.py:1099-1128`) is gated by `is_term_instance(term)`
   one level up, whose own comment states: *"since Task 6 emptied the
   bridge... an out-of-tree producer, the reflection vocabulary and
   clpb's BoolEq having become cells"* — i.e. almost nothing still mints a
   live `PredicateMeta` **instance** in-repo; the one surviving trigger is
   the `-constants`/data-functor transient-class case in finding 1, which
   is untouched by the W4b-2 predicate flip (predicate classes stop being
   minted; the *data*-functor momentary-class-then-rebind mechanism is a
   different, still-standing piece of machinery). A mangled atom is a
   `str`; nothing calls a `str` to produce an instance, so there is no
   post-flip "instance whose type is a mangled atom" for this line to ever
   need to handle — the open-questions doc's suspicion that "its mangled
   arm may never fire in either era" is correct, and for a structural
   reason (instances and mangled atoms are different Python kinds), not
   merely an empirical rarity.

**Ruling:** row 20 is **not** F2/F2b-shaped and needs no era-agnostic
accessor. It stays exactly as written through W4b-2 (a `PredicateMeta`
instance can still occur via the `-constants` data-functor transient-class
path in *both* eras) and becomes a genuine dead-code candidate only at
W4b-3, when the class itself is deleted and the `-module` rewrite's
transient-class trick presumably changes shape too (out of this pass's
scope to re-derive). Not F10 either — F10's row (22) was confirmed already
deleted this morning (see Job 2), and unlike that row this one is not
unreachable today; it is reachable by a live, still-open path (the
`-constants` case), just not one the W4b-2 predicate flip touches.

---

## Job 2 — the eight hard families, sized and ordered

Each row references the file:line as it reads on today's main (`28982190`);
line numbers have drifted from `w4b1-site-classification-2026-09-22.md`'s
count in a few files (compile-time cleanup commits landed between the two
documents) — re-located by grep for this pass, not assumed.

### F5 — coupled pair (rows 18, 39): **smallest real fix, contingent on F2b**

`terms_to_ast.py:101` (`_is_opaque_head_literal`) and `head_match.py:858`
both gate on the *identical* arity-blind test:
`isinstance(term, type) and isinstance(term, PredicateMeta)`. Read in full:
the terms_to_ast side returns `False` ("not opaque, already handled")
*specifically because* the head_match side has a dedicated branch a few
lines later that captures-and-`unify()`s the same shape
(`head_match.py:858-861`, comment: *"An atom is a class, so it never
reaches the `is_term_instance` branch... Route it through `unify()`"*).
Once F2b's `is_declared_predicate_name` exists, both sites become a literal
one-line swap of the same call — `if is_declared_predicate_name(term):` —
in the *same commit*. **Size: 2 files, ~2 lines each, zero new design once
F2b lands.** The coupling risk is entirely about sequencing (must move
together), not about difficulty. No operator ruling needed.

### F9 — import/attribute-listing filter (row 1): **small, needs a rewrite not a swap, F1 already sufficient**

`import_diagnostics.py:195-208` (`_defined_names`) walks
`vars(mod).items()` and keeps only `isinstance(value, PredicateMeta)`
entries for a "what may I import from here" diagnostic. Confirmed by
reading the full function: post-flip a predicate binding is a plain
mangled `str`, indistinguishable by `isinstance` from any other module-level
string. The fix is not a swapped test but a re-aimed population: filter on
`is_mangled(value)` instead (already exists, per
`w4b2-open-questions-2026-09-23.md` Q1), which *by construction* excludes
both a data functor's plain interned spelling and an unrelated `str`
constant (mangled atoms are a distinct format), then resolve
name/fields through `resolve_predicate_row`/`field_names_for` in place of
`value.__name__`/`value._fields`. **Size: 1 file, 1 function
(~15 lines), no new storage.** F1 (already landed on the resolver branch)
and `is_mangled`/`demangle` (already exist) are sufficient; no operator
ruling needed.

### F7 — frozen `_get_dispatch(arity)` protocol (row 8): **smaller than the "frozen, ~22 implementors" framing suggests**

`predicate.py:1377-1405` (`_dispatch_at`) is the **one** row in F7, and its
own docstring already names the fix's shape: *"Do not add an `arity`
parameter to another `_get_dispatch`; add the case here."* Confirmed: this
function's `isinstance(obj, PredicateMeta)` branch is the *only* place the
frozen, arity-aware overload is special-cased; the ~22 (38 files under
`packages/` mention `_get_dispatch`, consistent with "~22" real
implementors plus tests/helpers) out-of-tree implementors are called
through the **untouched** `obj._get_dispatch()` fallback three lines below
and are never on this function's critical path. The needed change is a
**third branch** inside `_dispatch_at` — `if is_mangled(obj): <resolve via
F1, call the row's own dispatch resolution>` — using exactly the extension
point the function's docstring already invites, not a protocol change.
Verified the 8 call sites of `_dispatch_at` (`solve.py:1023`,
`predicate.py:1438`, `builtins/_registry.py:150`, `builtins/dcg.py:188,195,
235,241`, `builtins/control.py:84`) all pass a *resolved goal/predicate
value*, never a raw arbitrary object, so a mangled atom reaching here is
exactly the shape F1's callers already produce elsewhere. **Size: 1
function, ~5 new lines, no protocol change, no new implementor coordination
needed.** No operator ruling needed — the frozen-protocol constraint from
project memory is about the ~22 implementors' *own* signature, which this
fix does not touch.

### F6 — class-object-as-storage (rows 17, 47, 48): **moderate, but F1 already supplies the new home**

Two independent carriers, both confirmed by reading every writer/reader:

- `_tabled_home_db` (row 17): 1 writer (`database.py:1149`, inside
  `mark_tabled`), 1 class-default declaration (`predicate.py:825`), 2
  readers (`tabling.py:863`, `compiler/tabled_naf.py:45`, both a bare
  `getattr(cand, "_tabled_home_db", None)`).
- `_te_predicate_nodes` on the `term_expansion` class specifically (rows
  47/48 — the *other* stamp site in the same file, on the `LogicModule`
  object `lm`, is unaffected by this migration): 1 writer
  (`term_expansion.py:113`), 1 reader
  (`term_expansion.py:159-170`, inside `_collect_imported_te_clauses`'s
  `elif isinstance(value, PredicateMeta) and value.__name__ == "term_expansion"`
  branch, which additionally has to change its *population test*, not just
  the attribute read).

The open-questions doc flagged F6 as needing storage with "no row-shaped
home" post-flip. **That is no longer accurate now that F1 has landed**:
`PredRow` (what `resolve_predicate_row` already returns) is exactly a
row-shaped home that survives the flip — both stamps can become fields on
`PredRow` (`row.tabled_home_db`, `row.te_predicate_nodes`), set via
`db.row(functor, arity, create=True)` at the existing writer sites and read
via `resolve_predicate_row(binding, arity=N)` at the existing reader sites.
**Size: 2 new `PredRow` fields + 6 touch points across 3 files** (writer,
default, 2 readers for the first carrier; writer + reader for the second,
whose reader also needs its `isinstance` population test replaced with
`is_mangled`/F2b-shaped logic to find a `term_expansion` mangled atom
sitting in `module_dict.values()`). **Recommend a one-line operator
confirmation** that `PredRow` is the intended new home (vs. e.g. a side
dict on `Database`) before starting — low-risk, but it is new shared-state
plumbing, and `mark_tabled`'s own docstring documents a "last marker wins,
multiple dbs may stamp the same predicate" semantics worth carrying forward
deliberately rather than by accident.

### F4 — diagnostic arity reader with a must-not-raise contract (row 5): **larger than flagged — a real design question, not just a guard**

`predicate_diagnostics.py:190-198` (`_arity_of`): `getattr(obj, "_fields",
None)` then falls back to `getattr(obj, "_arity", None)`, both guarded,
answering `None` gracefully for a bare `class X(metaclass=PredicateMeta):
pass`. The open-questions doc's framing ("wrap in try/except") undersells
the real problem, found on inspection: **`_arity_of` answers a single int**,
but F2b/F1's era-agnostic machinery answers per-`(functor, arity)`, and a
predicate NAME can legitimately be declared at *more than one* arity (the
`is_declared_predicate` docstring's own example, `p/1` and `p/2` coexisting).
For a `PredicateMeta` class binding this is a non-issue (one class, one
arity, by construction). For a **mangled atom** binding — which is what a
predicate reference in the namespaces `_arity_of` scans
(`predicate_diagnostics.py:252,280`) will be post-flip — "the declared
arity" is ill-defined when more than one exists, and the new
`is_predicate_name`-style existence scan proposed for F2b deliberately does
not disambiguate (Q4: it answers a bool, not a set). **Size: 1 function,
small in lines, but needs an actual decision** — return `None` for a
multi-arity name (safe, matches the existing graceful-`None` contract, loses
information a class binding today would never have lost since a class binding
never carries more than one arity) vs. building a full `arities_for`-correct
enumeration and picking one (matches today's information content more
closely, more code, an arbitrary "which one" choice for a diagnostic).
**Recommend an operator ruling on which**, since it is a user-visible
diagnostic behaviour change either way, before implementing.

### F3 — shared helper, callers outside the 49-row population (row 9): **likely mostly MOOT, confirmed for one call site, INFERENCE for three**

`is_zero_field_class`/`_is_zero_field_class_py` (`predicate.py:1533`,
aliased `predicate.py:1727`) is called from 4 sites the grep population
never sees. Opened all four this session:

- `logic/database.py` `head_key` (the row 9 example already flagged
  "IDENTITY"; line drifted to **1533** from the doc's 1502) — **verified,
  not INFERENCE**: the function already has a `if type(head) is str: return
  head, 0` branch immediately after the `is_zero_field_class` branch
  (comment: *"STAGE 2: an atom head is name/0"*). Once predicate classes
  stop being minted, a zero-arity predicate reaching a clause head arrives
  as a plain mangled/plain atom `str` and is caught by the **existing**
  `str` branch, never reaching the `is_zero_field_class` check at all. No
  code change needed here — the fallback that already exists covers the
  post-flip shape.
- `logic/solve.py:487` (`_ground_value`), `logic/builtins/_helpers.py:207`
  (`_is_ground_py`), `logic/compiler/terms_to_ast.py:1099`
  (`term_to_ast_expr`'s zero-field-class-as-atom-Constant branch) — **all
  three operate on a bare deref'd Python VALUE**, not a namespace binding.
  Today, that value can be a live `PredicateMeta` class object because a
  bare predicate reference in source currently compiles to a `Name` node
  resolving to the class in module globals. Post-flip, per the W4b-2d
  spec's own description ("mint handles with the import name" — a module
  attribute for a predicate becomes the mangled atom directly), that same
  source position resolves to a plain `str` at the point the class used to
  sit, so it would already look like an ordinary atom to `type(dv) in (int,
  float, ..., str, ...)` (the branch immediately above the
  `is_zero_field_class` check in every one of these three functions) —
  the special-case branch would simply stop being reached, harmlessly.
  **This is INFERENCE**, not verified by running the flip (which is not
  built yet) — flagging per the standards note rather than asserting it.

**Size: 1 shared definition + 4 call sites, but likely requiring *zero*
call-site edits** — `head_key`'s existing fallback and the other three
functions' pre-existing `str`/scalar branches appear to already cover the
post-flip shape, leaving `is_zero_field_class` itself simply unreachable
(dead, like F10) rather than needing a swap. **This needs the caller census
W2's discipline calls for before being marked closed** — the INFERENCE
above should become a probe once the flip exists (a fixture that declares a
zero-arity predicate, references it bare in each of the three positions,
and confirms no branch anywhere raises or misbehaves). Recommend this be the
**first thing verified once W4b-2d lands**, not designed further now.

### F8 — cross-copy class-identity diagnostic (row 11): **ruled — not moot, but needs NO migration**

`predicate.py:1851-1883` (`_describe_term_identity_mismatch`): `type(obj)`
compared against *this* process's own `PredicateMeta` to diagnose two
copies of the `clausal` package being loaded at once. Read in full: this is
**not moot**, because the mechanism it inspects — a `PredicateMeta`-typed
`type(obj)` — is not exclusively the predicate case. Per Q5's row-20
finding, a **data** functor's transient pre-rebind class is *also*
`PredicateMeta`-typed, and that mechanism is untouched by the W4b-2
predicate flip. So the diagnostic keeps a live trigger (a foreign copy's
data-functor instance) indefinitely, while its predicate-instance trigger
narrows toward impossible only once *both* copies in a mixed-version
process are past the flip. **Ruling: leave as-is, no migration, no operator
decision needed for W4b-2** — the function degrades gracefully (never fires
for a predicate-shaped `obj` once predicates stop minting instances; still
fires correctly for the data case it shares with row 20) rather than
needing new code. Recommend a one-line note in the tracking doc that this
row is "closed, no action" rather than left open, so it is not mistaken for
outstanding work.

### F10 — dead code (row 22): **DONE, verified on today's main**

`terms_to_ast.py`'s old line ~1141 (`isinstance(cls, PredicateMeta) and
isinstance(vars(cls).get("_clausal_new"), classmethod)`) **no longer
exists**. Verified: `git log --oneline -3 -- clausal/logic/compiler/terms_to_ast.py`
shows it was removed this morning in `ca4e49dd` ("W4b-0: retire the five
dead `_clausal_new` gates + call-key path", 2026-09-23 07:47), whose message
confirms the exact reasoning row 22 gave ("DEAD SINCE W4a... the gate never
matches"). `grep -n "isinstance([^)]*PredicateMeta" clausal/logic/compiler/terms_to_ast.py`
today returns exactly 5 lines (101, 385, 578, 1067, 1225 — rows 18/F5, 19,
20, 21, 23), none of them this one. **Size: zero — already landed, nothing
to do.**

### Recommended order

1. **F2b** (this document's Job 1) — unblocks F5 outright and is the
   long pole for the 13-row population.
2. **F5** — same commit as F2b lands, or immediately after; trivial once
   F2b exists.
3. **F9** — small, self-contained, F1 already sufficient.
4. **F7** — small, self-contained, does not touch the frozen protocol.
5. **F6** — moderate; do after confirming `PredRow` as the new home.
6. **F3** — spend an hour confirming the "likely moot" inference with a
   built flip before writing any code; probably closes with zero edits.
7. **F4** — needs an operator ruling on the multi-arity diagnostic
   question before implementing; small once ruled.
8. **F8** — no work; mark closed.
9. **F10** — already done; remove from the tracked 49 rows.

**Operator rulings needed before starting, in bite order:** (a) F4's
multi-arity-diagnostic-answer question (blocks only F4, small blast
radius); (b) F6's `PredRow`-as-new-home confirmation (blocks only F6,
low-risk but touches shared cross-module state semantics). Neither blocks
F2b, F5, F7, or F9, which can start immediately. F3 and F8 need no ruling,
only (for F3) a verification pass once the flip lands.
