# Constants resolve lexically, by compile-time module insertion

**Status**: design, awaiting review. Supersedes the first version of this file (same path,
2026-09-12), whose mechanism was not feasible — see *What changed, and why*.

## The rule (unchanged)

**A constant is in scope if this module declared it, imported it, or names its owner.** Nothing
else. `/3` stops answering for other modules; an imported constant becomes reachable in the
current spelling; a bound name that is no constant here raises.

## What changed, and why

The first version proposed "`/3` filters by the querying module". **That is not feasible**, and
the codebase says so in `inspection.py`'s own docstring for `constant_value/2`:

> the module-implicit reading would need the CALLING module — which a builtin does not get: the
> registry hands dispatch functions their arguments and a trail, and nothing else. … Two modules
> that declare the same constant name both answer, in load order. Use `module_constant/3` when
> the module matters.

So the cross-module answers are a **documented compromise, not a defect**, and its cause is
architectural: builtins receive arguments and a trail. `_get_dispatch` is a frozen duck-typed
protocol with ~22 out-of-tree implementors, so it cannot grow a calling-module parameter.

**The lever is that the COMPILER knows the calling module even though the builtin cannot** — and
this codebase already uses it: `$register_constant_units` is handed `$module` by the transformer
at declaration time rather than discovering it at runtime. Reading should work the way writing
already does.

## Design

| written | compiles to | note |
| --- | --- | --- |
| `constant(fee)` | runtime module-global read | unchanged |
| `constant(prov.fee)` | lookup in `prov`'s registry | dotted form is a QUALIFIED NAME, never evaluated |
| `constant_number_units(fee, N, U)` | `module_constant_units(<this module>, fee, N, U)` | module inserted at compile time |
| `constant_value(N, V)` | unchanged, stays unscoped | Triska's cross-implementation spelling, not ours to vary |
| `module_constant(M, N, V)` | unchanged | already the module-scoped form |

### 1. One new primitive

`module_constant_units/4` — a near-copy of the existing `module_constant/3`, reading
`module.constant_units` instead of `module.constants`. The registries are already per-module and
already correct; **nothing about registration changes.** The leak was only ever in the query
path.

### 2. Imported constants

`constant(fee)` after `-import_from(prov, [fee])` raises today ("nothing declares `fee`") — the
error tells you to do the thing you just did. The blocker is the compile-time `transformer._constants`
set, which imports never touch, by a 2026-09-11 decision recorded at the import handler:

> There is no imported-constant branch here. A constant name is atom-shaped now, so the importer
> cannot tell a constant from an atom or a predicate in the owner module — that is the OWNER's
> fact and the name no longer carries it.

The reasoning holds: the importer genuinely cannot tell. But it **does know the owner**, from the
directive, recorded in `_import_remap`. So the compile-time question changes from *"is this a
constant?"* (unanswerable without executing the owner) to *"do I know who owns this?"*
(answerable, statically). The "is it really a constant" check moves to the owner's registry,
consulted where the owner is known.

### 3. Module-prefixed access

`constant(prov.fee)`. Today refused deliberately:

> constant() takes a bare name … the whole point of the parentheses is that what is inside cannot
> be a Python expression.

**That invariant survives**, because a dotted name is read as a *qualified name*, not evaluated
as an `Attribute` expression — the same way `-import_from(py.units, …)` takes a dotted module
path without evaluating it. What the invariant buys (compile-time resolvability) is preserved:
the owner is named at the site, so resolution is more static, not less.

This supersedes the operator's earlier "import-only for now" ruling, and the reason is that the
investigation changed the facts: prefixing was deferred because it looked like a second
namespace to build. It is not — it is the same owner-registry lookup as (2), reached from a
different syntax. Recorded rather than silently reversed.

### 4. Undefined names raise

`constant(never_defined)` already raises at LOAD. `/3` fails silently on a bound in-scope
non-constant; it should raise, and can do so at compile time where the name is a literal.

**Constraint from measurement**: `/3` with an **unbound** first argument legitimately enumerates
(2 rows for a module with 2 constants). So the raise applies only to the bound case, and
enumeration must be module-scoped too or the leak returns through the back door.

## Not in this change

* **`constant_value/2` stays unscoped.** Fixed by cross-implementation convention.
* **`-hide`** already mangles the atom, so a hidden constant's key is module-unique. It is the
  private half and needs nothing.
* **Registration.** Both registries are per-module and correct.
* **Prolog term expansion** for Scryer/Trealla — the operator's stated direction, and a separate
  design. Noted because it may change what the exporter does with all of this; see
  `todo/exporter-folds-scaled-units-to-the-wrong-magnitude-2026-09-11.md`.

## Blast radius: measured zero

A downstream user censused **call sites**, not names, across four surfaces: **zero** `/3` call sites in
rulebase bodies, Python/harness, and the library; the 18 files matching are all DIRECTIVES, verified
specifically so declarations are not counted as goals. Sites relying on `/3` FAILING were
searched as their own shape (`\+ constant_number_units(...)`) — zero. **With a planted positive
control**, so the zeros are the absence of call sites, not of a detector.

**Why zero**: downstream code reaches constants exclusively through `constant(name)`, never the `/3`
reflection channel — 176 declared values across several domains. So `/3` has never been exercised by
a rulebase in either direction. The leak never leaked; the silence never silenced.

**Consequence: a strict improvement with no migration**, and the cheap moment to do it, because
a name-vs-unit gate will need exactly the declared pair.

## Testing

TDD, with mutation controls on every gate:

* two modules declaring one name — the querying module gets its own, **once**
* an imported constant answers `constant()` and `/3` (both fail today)
* `constant(prov.fee)` resolves without an import; a non-constant there raises naming the owner
* a bound in-scope non-constant raises; **an unbound query still enumerates, this module only**
* `-hide`-en constants keep working; `constant_value/2` still enumerates across modules
* neutering the module insertion must fail exactly the leak test; neutering the raise must fail
  exactly the raise tests

Three axes before landing: engine suite (failure **and skip** name sets), export bytes
(a downstream user), domain answers (a downstream checker).
