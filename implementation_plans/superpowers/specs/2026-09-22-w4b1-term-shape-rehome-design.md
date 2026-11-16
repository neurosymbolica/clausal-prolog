# W4b-1 — rehoming the TERM SHAPE off `PredicateMeta` (design, 2026-09-22)

**Status:** design approved by the operator 2026-09-22; spec for review before
the implementation plan. First of the four W4b sub-projects
(`implementation_plans/w4b-class-retirement-scope-2026-09-22.md`). The CLASS
is not removed here and no handle changes hands — both are W4b-2/W4b-3.

## The question this answers

A `PredicateMeta` class does two jobs. It is the predicate HANDLE — what a
module attribute binds to, what carries dispatch and the Database row — and
it is the TERM SHAPE — the field names, the arity, and "zero fields means
this is an atom". The handle has a ruled destination (the module-qualified
mangled atom plus the row; pieces 1–2 landed at `f73ccc65`). The shape has
none, and it is the half that 289 in-engine `_fields` reads hang off.

W4b-1 gives the shape a home that does not need the class, so that W4b-2 can
flip the handle without the shape falling over, and W4b-3 can delete the
class without thirty sites changing a second time.

## Premise check: does Clausal use field NAMES in practice?

Asked by the operator, 2026-09-22, and measured before answering, because
ISO Prolog needs no such thing and a rehome of something vestigial would be
waste.

**Keyword term CONSTRUCTION in `.clausal` is already gone** — retired
2026-09-19; a term is built positionally
(`tests/fixtures/builtins_keywords.seam:17` records it). On that surface
Clausal already agrees with ISO.

Names are nonetheless live in four places:

1. **Declarations name their fields** — it is the syntax, not an option:
   `-private([natnum(VALUE), succ(INNER), edge(FROM, TO), path(FROM, TO)])`.
   481 such entries in the tree. The compiler is handed names whatever else
   changes.
2. **EDCG accumulators are addressed BY NAME at call sites** — the one
   genuinely semantic use: `process_list(L, _edcg_counter_in=0,
   _edcg_counter_out=COUNT, _edcg_items_in=[], ...)`, resolved to positions
   at `solve.py:1362` through `db.signature_for`. Retiring names would cost
   EDCG its addressing.
3. **Three builtins** — `vary/3`, `unbound_keys/2`, `signature/3`, all of
   `builtins/keyword_ops.py`; 9 uses in the tree, every one a test fixture.
   The thinnest surface, and the only one a "do we need this?" ruling would
   really bite.
4. The Python API's `Pt(x=1, y=2)` (`__call__`'s kwargs path) — an
   ergonomic, not a language feature. **NOT MEASURED, AND RULED NOT TO BE**:
   how often `__call__` receives kwargs at runtime needs a counting plugin
   over the suite, not a grep; the operator declined it 2026-09-22 and W4b-1
   proceeds on the assumption that the path is in use. It is recorded here as
   an assumption, not a finding, so that a later reading of "can field names
   be retired outright?" knows which number is still missing and that it was
   declined rather than overlooked.

**And the consequence for this spec.** Reading the ~50 `signature_for` /
`cell_signature_for_name` call sites, the compiler's DOMINANT use of the
registry is the presence test — `if functor_signature_for(name, ns) is
None:` (`compiler_v2:1420`, `list_dispatch:334`, `control_constructs:718`) —
"is this a declared functor, or an atom being applied as one?" Those sites
never read a name.

So `field_names_for` is, first, a **declaredness** reader and only second a
shape reader, and its `tuple | None` return is what lets it be both:
`None` = not declared; `len(t)` = the arity; `t` = the names, for the four
consumers above. The name is kept for continuity with
`term_field_names_of_class`, but the contract to hold in mind while
migrating a site is the declaredness one.

## Why additive, and why now

It is additive: the class keeps `_fields`, keeps minting, keeps answering.
Nothing a caller does today stops working. That is deliberate — W1's ruling
is that P4 is a **migration, not a flag day**, and a shape rehome that can
land against either binding is what makes the handle flip a one-function
change instead of a thirty-site one.

## Scope

### 1. One accessor, generalised from the one that exists

`predicate.term_field_names_of_class(cls) -> tuple | None` already returns
the right type, already has the right `None` semantics, already handles
`@dataclass`, and already has 8 engine call sites. It becomes:

```python
def field_names_for(value, *, arity=None, db=None, namespace=None) -> tuple[str, ...] | None
```

resolving in this order:

| arm | input | answer | fate |
|---|---|---|---|
| 1 | a `@dataclass` class | its declared field names, in declaration order | permanent |
| 2 | a `PredicateMeta` class | `cls._fields` | deleted at W4b-3 |
| 3 | a **name** (`str`, plain or mangled) | the registry read below | permanent |
| 4 | anything else | `None` | permanent |

**Arm 3 in full**, because two things in it are lossy if left implicit:

* **Arity.** `db.signature_for(functor, arity)` is the exact read — it
  chains `_signatures` then `_declared`, so it sees both registration routes.
  `db.declared_fields_by_name(functor)` is the by-name fallback and resolves a
  name declared at two arities to the LAST declaration, a documented lossiness
  inherited from the exec-time registry map, and it sees only `_declared`. So
  arm 3 prefers `signature_for` whenever an *arity* is known and falls back to
  the by-name read only when it is not. Callers that hold an arity pass it;
  the plan records, per migrated site, which of the two it uses, because a
  site that silently takes the by-name read on a two-arity name is a defect
  this spec would otherwise have introduced.
* **Mangling.** A mangled name (`is_mangled`, `clausal.logic.atoms`) is
  `demangle`d to its module and bare name, and resolved against THAT module's
  db — not the caller's. A plain name resolves against *db* as given, else
  *namespace*, else answers `None`. Arm 3 never guesses a module.

The resolution order within arm 3 is therefore: demangle if mangled →
`db.signature_for(functor, arity)` if an arity is known → the by-name read →
the namespace's `FUNCTOR_SIGNATURES_KEY` map → `_BUILTIN_FIELDS` → `None`.

`term_field_names_of_class` stays as a thin alias for the duration of W4b-1
— it is in `predicate.__all__`, so out-of-tree callers keep working. It
retires with the class at W4b-3, not here.

Arm 3 is the point of the change: when W4b-2 makes `m.pred` a mangled `str`,
arm 3 already answers for it, so the handle flip edits one function's
internals rather than every reader.

**The contract, stated so the idiom it replaces cannot survive:**

* `()` means *declared, with zero fields* — the 0-arity predicate written
  `p()` (as opposed to the bare-name atom `p`), which `make_predicate(n, [])`
  still legitimately mints and which `predicate.py` documents as a permanent
  shape, not a pre-pivot straggler.
* `None` means *not term-shaped, or not declared*.

So `isinstance(x, PredicateMeta) and not x._fields` becomes
`field_names_for(x) == ()` — a question about the declaration rather than
about the Python type, and one arm 3 can answer from a name alone.

### 2. The registry precedence, stated

**CORRECTED while writing the plan, 2026-09-22.** There are FIVE homes,
not three, and two of them are already chained:

| home | populated by | read by |
|---|---|---|
| `cls._fields` | every minter | arm 2 (the legacy answer) |
| `db._signatures` | `db.register_signature` | `db.signature_for`, FIRST |
| `db._declared` | `db.declare_functor` | `db.signature_for`, as fallback |
| `__clausal_functor_signatures__` | generated code; copied by `-import_from` | `functor_signature_for` |
| `_BUILTIN_FIELDS` (`builtins/_registry.py:52`) | the `@_builtin` decorators | the registry itself |

`db.signature_for(functor, arity)` **already chains `_signatures` then
`_declared`** (database.py:992–997). So arm 3's db read is `signature_for`,
not `declared_fields_by_name` — using the narrower read would have missed
every predicate registered through `register_signature`, which is how
`-specialize` registers (see section 3).

Precedence, stated: `db.signature_for` is the authority for anything a
Database knows; `__clausal_functor_signatures__` is its exec-time carrier for
a namespace with no db in hand; `_BUILTIN_FIELDS` is the authority for
builtins, which are minted detached ON PURPOSE and have no module db to be
registered with. `cls._fields` is the legacy answer and **must agree**; a
disagreement is a defect, not a fallback, and section 4's census is what says
so.

### 3. Populating the authority — THREE gaps, not six

The spec originally listed six minters as bypassing `declare_functor`. Writing
the plan checked each, as the spec required, and **three of the six were
already covered**:

| minter | verdict |
|---|---|
| `specialization.py` ×3 (439, 1489, 1827) | **COVERED.** All three `specialize_mi*` variants route through `_install_specialized` (300), which calls `db.register_signature(new_name, arity, tuple(fields))` at line 388. `signature_for` reads `_signatures` first, so arm 3 answers. |
| `builtins/_registry.py` ×2 (515, 535) | **NOT A GAP.** These are minted DETACHED on purpose — the comment at 516–519 calls it "the engine's one DELIBERATE minter of a detached row". `_BUILTIN_FIELDS` is already the name-keyed registry for builtins, populated at decoration time. Arm 3 reads it; nothing is wired to a db. |
| `compiler_v2._preregister_specializations` (1229) | **GAP.** Its signature is `(module_items, module_dict)` — no db, deliberately, because it runs before `_install_specialized`. The db must be threaded from its caller, which already holds one. |
| `term_expansion.py:314` | **GAP, easily closed.** It binds into a synthetic `LogicModule("_term_expansion_")`; `lm.db` is in hand at the mint site. |
| `modules/py/datetime.py:204` (`_DatePattern`) | **GAP, and it carries a stale premise.** Its docstring justifies `metaclass=PredicateMeta` on the grounds that "the engine's clause copier rebuilds *term instances* … and it recognises them via PredicateMeta or @dataclass (`c_is_term_instance`)". **W4a retired the instance path and deleted that C arm**, so the stated reason no longer holds and a partially-instantiated date now builds a cell. The plan re-reads it rather than assuming either that it still needs the metaclass or that it does not. |

Bare `make_predicate` out of tree has no db and keeps arm 2 until W4b-3 —
that is the detached-row population, named here so it stays a known residue
rather than becoming a silent gap.

### 4. The site migration: classify, never sweep

The ~30 shape sites are an estimate from grep context, not from reading. The
plan's first task is to read all 63 engine `isinstance(…, PredicateMeta)`
sites and classify each:

* **asks about shape** — "what are the field names", "is it zero-field" →
  migrate to `field_names_for`;
* **asks about identity** — "is this binding a clausal declaration
  *specifically*, not any term-shaped Python class" → **leave it**, still
  `isinstance`, and record it as W4b-2's measured input.

The classification is the main output of that task and it is published as a
list, site by site, with the reason — not as two numbers.

**Why this is not optional.** Arm 1 answers for a `@dataclass` class;
`isinstance(x, PredicateMeta)` refuses one. Migrating an identity site to the
accessor widens it to accept dataclass terms, silently, in a direction the
house suite is poorly placed to catch. This is the single sharpest
correctness risk in W4b-1.

### Stays, named so it is not absorbed

`PredicateMeta` and every member W4a left; `make_predicate`; `_state_row` and
the detached-row mode; the `db=None` compile default; the four C CLASS arms,
`PredicateMeta_type` and `py_register_predicate_meta`; every handle-identity
site; the seam; `qualify_mangled_goal` and the demangling entry points. **No
C file is touched**, so no `.so` is built and no rename-swap happens in this
landing.

## Tests

* The accessor's four arms, each pinned separately, including a
  `@dataclass` class (arm 1) and a non-class value (arm 4).
* `field_names_for(p) == ()` for a zero-field declared predicate, and
  `field_names_for(x) is None` for an undeclared name — the two halves of
  the contract, pinned beside each other so they cannot drift.
* A **mangled** name resolving through arm 3 against its OWN module's db
  rather than the caller's, and a plain name resolving through a namespace
  with no db.
* A name declared at TWO arities: the exact read answers each correctly; the
  by-name fallback answers the last declaration, pinned so the lossiness is a
  recorded property rather than a surprise.
* One test per GAP minter from section 3 (three, not six): after the mint,
  `db.signature_for` answers with the fields the class carries. Plus one test
  each for the two already-covered routes — `_install_specialized`'s
  `register_signature` and `_BUILTIN_FIELDS` — so a later change that removes
  the coverage fails here rather than silently.
* `term_field_names_of_class` still answers, unchanged, for its 8 existing
  callers' inputs — the alias is load-bearing until W4b-3.

## Gate

The two standard gates, baselines regenerated on `main` at the start rather
than read from a file:

* house suite **NEW 0 / GONE 0** (`pytest tests -q -rfE -p no:cacheprovider
  --continue-on-collection-errors --ignore=tests/test_clportools.py`, run FROM
  the room, `clausal.__file__` asserted to start with the room);
* `tools/w3_package_gate.sh` **NEW 0 / GONE 0**.

Neither can show what this change is FOR. A green suite says nothing about
whether the registry is a working substitute for `_fields`, because arm 2
will cheerfully answer every call while the class exists. So the exit
criterion is a census:

**A pytest plugin instruments `field_names_for` over the whole house suite
and publishes, with denominators:**

* **N** — total calls. `N == 0` is a refusal, not a pass.
* per-arm counts: dataclass / class / name / none.
* for every **arm-2** answer, the shadow arm-3 read: **agreed / disagreed /
  could not answer**.
* the set of functors where arm 3 could not answer — listed **by name**, not
  counted, because that set is the residue W4b-3 must account for.

**Fail conditions:** any disagreement; `N == 0`; a residue set not fully
explained by the out-of-tree-`make_predicate` population named in section 3.

**Positive control, run before any real number is printed:** plant a functor
whose registered fields deliberately differ from its `_fields` and assert the
census reports the disagreement. An instrument that has not been seen to fire
is the 57th entry in the fail-open ledger, not a gate.

## Risks

* **The widening in section 4.** Mitigated only by reading each site; there
  is no sweep that can do it.
* **A minter with no db reachable at its mint point.** Section 3 assumes one
  is in hand; if a site turns out not to have one, it joins the named residue
  rather than acquiring a db by threading one through — that would be a
  redesign, not this change.
* **The three registries may already disagree** and nothing checks today. If
  the census finds a real disagreement on `main`, that is a bug this spec
  discovered and not a defect in the change; it gets its own todo and a
  ruling before W4b-1 lands on top of it.
* **Out-of-tree minters** keep arm 2 and are ungated beyond the three
  packages the W3 gate runs. Nothing here makes that worse; W4b-3 is where
  it has to be made loud.
