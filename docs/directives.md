# Directives

Directives are module-level declarations in `.clausal` files that control predicate properties, imports, and compilation behavior. They are prefixed with `-` and placed at the top of the file.

---

## Module Declaration

```clausal
-module(my_module, [Pred1(A, B), Pred2(X)])
```

Declares the module name and its public exports. The export list specifies which predicates are accessible to importers. If omitted, the module name is derived from the filename.

The export list may mix predicates with arity (e.g. `Pred1(A, B)`) and bare atoms (zero-arity predicates):

```clausal
--8<-- "tests/fixtures/docs/directives_sigs.txt:module_with_atoms"
```

!!! info "Per-module atom identity"
    Listing an atom here opts that atom into **module-local public** identity — importers see `traffic.red` as a distinct `PredicateMeta` class from any other `red`. Bare atom references that are **not** listed in `-module`, `-private`, or an import raise a compile-time `NameError` by default (strict is the default). In files that carry [`-implicit_atoms`](#-implicit_atoms), unlisted bare atoms resolve to the process-wide **global** atom of the same name instead. See [Atoms § Strict by default](syntax.md#atoms) and the [global-atoms-default spec](https://gitlab.com/MikeAmy/clausal/-/blob/main/implementation_plans/atoms_refactor/GLOBAL_ATOMS_DEFAULT.md).

### -private

```clausal
-private([Helper(X, Y), Edge(A, B)])
```

Declares predicates and atoms that are internal to the module. They get proper `PredicateMeta` classes, exactly as `-module` exports do.

The list may also contain bare atoms:

```clausal
--8<-- "tests/fixtures/docs/directives_sigs.txt:private_with_atoms"
```

!!! warning "`-private` is a marker, not a barrier"
    **`-private` means "not part of my documented surface" — Python's leading underscore, not C++ `private`.** It does *not* make a name unreachable. `-import_from(owner, [draft])` reaches a `-private` atom or predicate just as readily as an exported one, and binds the **owner's** class, so both modules share one identity. Clausal has no access control at all: `-import_from` lowers to a Python `from M import name` and consults nothing about `M`'s declarations — not its `-private` list, not its `-module` export list (see [Why not Prolog-style modules](import.md#why-not-prolog-style-modules) — "No export lists. Everything is public").

    This is deliberate and [pinned by a test](https://gitlab.com/MikeAmy/clausal/-/blob/main/tests/test_global_atoms_default.py). It is also load-bearing: under strict atoms, a fixture or generated module with no `-module(...)` export list has importing from its `-private` list as its identity-preserving route across a file boundary.

!!! info "What `-private` actually buys"
    Listing a name in `-private` has four real effects and one advisory one:

    1. **Module-local identity** — the atom gets a class distinct from the process-wide global atom of the same name, and from any other module's declaration of it (so `draft` here does not unify with `other_module.draft` or with the global `draft`).
    2. **Strict-atom resolution** — the bare name compiles instead of raising the strict-by-default `NameError`. In files that carry [`-implicit_atoms`](#-implicit_atoms) you can omit the listing and rely on auto-minting.
    3. **Shadowing** — inside this module the private class wins over `-module`, over imports, and over the global.
    4. **Signature pre-registration** — for `P(A, B)` entries, arity and field names are fixed before the first clause rather than inferred from it.
    5. **Intent** — it tells a reader the name is internal. Advisory only, per the warning above.

    The only thing that distinguishes `-private` from `-module` is which of those a reader is told. See the [global-atoms-default spec](https://gitlab.com/MikeAmy/clausal/-/blob/main/implementation_plans/atoms_refactor/GLOBAL_ATOMS_DEFAULT.md) § "Visibility is advisory".

An atom may appear in both `-module` and `-private`. The first listing processed wins and the second is a no-op, so the name still gets exactly one module-local class.

---

## Import Directives

### -import_from

Import specific predicates from another module:

```clausal
--8<-- "tests/fixtures/docs/directives_sigs.txt:import_from"
```

With aliasing:

```clausal
--8<-- "tests/fixtures/docs/directives_sigs.txt:import_from_ex2"
```

This imports `Double` from `utils` but makes it available locally as `MyDouble`.

!!! info "Importing an atom: when it matters"
    For predicates with arity, importing is the only way to reach the source module's local class. For **atoms**, importing is meaningful only when the source module owns a local version (because it listed the atom in its `-module` / `-private`). Importing an atom that the source module does not list is a no-op documentation hint — the atom is already global, so there is nothing distinct to import. See the [global-atoms-default spec](https://gitlab.com/MikeAmy/clausal/-/blob/main/implementation_plans/atoms_refactor/GLOBAL_ATOMS_DEFAULT.md) for the full resolution rules.

    Importing an atom **always shadows** the global default in the importing module: bare `red` after `-import_from(M, [red])` resolves to `M.red`, not the global `red`. Use `global_atom/2` (see [Term Inspection](builtins.md#global_atom2)) to reach the global class from such a module.

### -import_module

Import all exported predicates from a module:

```clausal
--8<-- "tests/fixtures/docs/directives_sigs.txt:import_module"
```

Imported predicates are accessed via qualified names: `utils.Double(X, Y)`.

See [Import System](import.md) for full details. For importing Prolog `.pl` files directly, see [Importing Prolog](importing_prolog.md).

---

## Atom-Identity Directives

These directives control atom identity resolution as specified by the [global-atoms-default spec](https://gitlab.com/MikeAmy/clausal/-/blob/main/implementation_plans/atoms_refactor/GLOBAL_ATOMS_DEFAULT.md). The short version: strict resolution is the default — an undeclared bare atom reference is a compile-time `NameError`; `-implicit_atoms` opts a file out of strict and restores Prolog-style auto-minting; `-overwrites` silences the shadowing warning emitted when an import collides with a local declaration.

Upgrading an existing codebase from the old auto-mint default? See the [strict-atoms migration guide](strict-atoms-migration.md).

### -strict_atoms

> **Deprecated (still supported).** Strict atom resolution is now the default,
> so this directive is redundant and can be deleted. It still forces strict mode
> where present; loading a file that uses it emits a one-per-process
> `ClausalStrictAtomsDeprecationWarning`. To opt a file *out* of strict, use
> [`-implicit_atoms`](#-implicit_atoms).

**Historical context**: Before strict became the default, files could use
`-strict_atoms` to opt in to compile-time `NameError` on undeclared bare atoms.
That protection now applies everywhere by default, making this directive
redundant. Use [`-implicit_atoms`](#-implicit_atoms) to opt a file *out* of
strict when Prolog-style ceremony-free tag atoms are desired.

```clausal
--8<-- "tests/fixtures/docs/directives_sigs.txt:strict_atoms"
```

`-strict_atoms` is a **file-level opt-in marker** that takes no arguments. With it present, every bare atom reference in the file must be reachable through one of:

- a `-module([...])` listing,
- a `-private([...])` listing,
- a `-import_from(M, [...])` listing,
- a qualified reference (`other_module.red`),
- a `global_atom/2` call (see [Term Inspection](builtins.md#global_atom2)).

A bare reference that satisfies none of the above raises a compile-time `NameError` instead of being silently auto-minted. The diagnostic names every offending atom and the module, and spells out the five legitimate routes so the fix is obvious.

**Scope**: per-file only. The directive does not propagate to imported modules — each file decides for itself. A strict file can freely import from non-strict files and vice versa.

**Interaction with `global_atom/2`**: even in strict files, `global_atom/2` still resolves against the global atom dict. The directive restricts *bare* references, not the reflection escape hatch.

**Recommended use**: turn on for any file whose clauses encode authoritative rules (regulatory, legal, clinical, compliance). Leave off for general code, library code, and prototypes.

### -implicit_atoms

**Problem**: Strict atom resolution is the default (a typo in a bare atom is a
compile-time `NameError`). Some files — prototypes, exploratory scripts, and
code that deliberately relies on Prolog-style ceremony-free tag atoms — want the
looser behavior back.

`-implicit_atoms` is a **file-level opt-in marker** that takes no arguments (bare
`-implicit_atoms` or `-implicit_atoms()`). With it present, an undeclared bare
atom reference is auto-minted into the process-wide global atom dict instead of
raising. It is the exact inverse of [`-strict_atoms`](#-strict_atoms); a file may
not carry both (doing so is a compile error).

The REPL uses this mode implicitly so interactive queries keep auto-minting.

### -overwrites

**Problem**: When a module both `-import_from`s an atom *and* declares the same name in its own `-module` / `-private`, the two declarations describe **distinct** `PredicateMeta` classes. This is almost always unintentional (a typo, a forgotten cleanup after a refactor) and triggers `ClausalAtomShadowingWarning`. But occasionally it is deliberate — the module needs both the imported class and a separate local one with the same spelling.

```clausal
--8<-- "tests/fixtures/docs/directives_sigs.txt:overwrites"
```

`-overwrites([...])` silences `ClausalAtomShadowingWarning` for the listed atom names. The list contains **atom names only** — predicate functors are not affected because predicate-functor shadowing is the existing per-module convention, not the new atom-identity confusion the warning is meant to catch.

If an `-overwrites` entry does not actually correspond to an imported atom shadowed by a local declaration, the compiler emits `ClausalUnusedOverwritesWarning` for that entry. Unused entries typically indicate a stale import or a typo in the `-overwrites` list itself; the warning gives the author a chance to clean up.

See [Atoms](syntax.md#atoms) for the resolution-order context and the [global-atoms-default spec](https://gitlab.com/MikeAmy/clausal/-/blob/main/implementation_plans/atoms_refactor/GLOBAL_ATOMS_DEFAULT.md) for the full warning-trigger semantics.

---

## Predicate Property Directives

### -dynamic

**Problem**: By default, predicates are locked after loading — you can't change
them at runtime. But some programs need to add or remove facts during execution
(counters, caches, learned knowledge).

```clausal
-dynamic(color/1)

color("red"),

Test("add at runtime") <- (
    assertz(color("blue")),
    color("blue")
)
```

Without `-dynamic`, the `assertz` call above would raise a `RuntimeError`.
See [Database Operations](database_ops.md) for full details.

### -table

**Problem**: Recursive predicates can loop infinitely or recompute the same
subproblems. Tabling automatically caches answers and handles left-recursive
definitions.

```clausal
-table(path/2)

edge(1, 2),
edge(2, 3),
edge(3, 1),

path(X, Y) <- edge(X, Y)
path(X, Y) <- (edge(X, Z), path(Z, Y))

Test("path 1 3") <- path(1, 3)
Test("path 2 1") <- path(2, 1)
```

Without `-table`, `path/2` would loop forever on the cycle `1→2→3→1`. With
tabling, it terminates and returns all reachable pairs. Also required for
[Well-Founded Semantics](wfs.md).

**`-table` only tables predicates the declaring module compiles.** Tabling is a
property of the dispatch function, and that function belongs to the module the
clauses live in. So a `-table` this module cannot honour is a load error rather
than a directive that quietly does nothing: writing `-table(path/2)` in a module
that merely `-import_from`s `path/2` fails at load and tells you to move the
directive into the defining module, and so does `-table` on a `-specialize`
alias, which is compiled against a database of its own. A clause-less target
fails too, with one exception: a `-dynamic` predicate, which this module does
compile and whose clauses arrive later.

Tabling survives runtime clause changes. `assertz`/`asserta`/`retract` on a
tabled `-dynamic` predicate recompile it *and* re-establish tabling, discarding
the cached answers the old clause set produced.

See [Tabling](tabling.md) for details.

### -discontiguous

**Problem**: By default, all clauses for a predicate must be grouped together
in the source file. Sometimes it's clearer to interleave related predicates.

```clausal
-discontiguous(Test/1)

helper(X, Y) <- (Y == X + 1)
Test("first") <- helper(1, 2)

other_helper(X, Y) <- (Y == X * 2)
Test("second") <- other_helper(3, 6)
```

Without `-discontiguous`, the `Test` clauses being separated by `other_helper`
would trigger a warning or error.

### -meta_predicate

**Problem**: when higher-order predicates are imported across modules, the
module system needs to know which arguments are goals (to resolve them in the
correct module context).

```clausal
--8<-- "tests/fixtures/docs/directives_sigs.txt:meta_predicate"
```

The `2` means the first argument is a goal that takes 2 extra arguments.
`+` means input, `-` means output. This ensures correct cross-module
resolution when `my_map` is imported. See [Higher-Order Predicates](higher_order.md) for builtins like `maplist` that use this pattern.

### -shallow

**Problem**: The default trampoline compilation mode has slight overhead for
stack safety. For predicates known to have bounded recursion depth (lookups,
simple dispatches), this overhead is unnecessary.

```clausal
-shallow(lookup/2)

lookup("a", 1),
lookup("b", 2),
lookup("c", 3),

Test("lookup a") <- (lookup("a", V), V == 1)
Test("lookup c") <- (lookup("c", V), V == 3)
```

`-shallow` compiles in simple mode (direct generator calls) instead of
trampoline mode. Use it for flat, non-recursive predicates where performance
matters. See [Compiler](compiler.md) for details on the two compilation modes.

---

## Constants Directive

### -constants

**Problem**: A magic number like `3.14159` or `3` repeated across several clauses is a
maintenance hazard — rename the meaning, and every occurrence has to be found and checked by
hand. Prolog has no answer to this beyond a fact plus an extra goal (`is_pi(PI), area == PI *
R**2`); Clausal gives constants their own lexical class instead.

```clausal
-constants(_PI_ = 3.14159, _MAX_RETRIES_ = 3)

area(R, AREA) <- (AREA == _PI_ * R**2)

Test("area of radius 2") <- (
    area(2, AREA),
    AREA == 12.56636
)
```

`-constants(name = value, ...)` declares one or more module-level constants — identifiers with
exactly one leading and one trailing underscore (`_PI_`, `_MAX_RETRIES_`; see [Constants in the
syntax reference](syntax.md#constants) for the full lexical rule). Every reference to a
declared constant is replaced by its value at compile time — there is no runtime lookup, and
the substitution applies uniformly, head position included.

The right-hand side must be **fully ground**: scalar literals, previously-declared constants,
declared atoms, arithmetic over those, a `++(expr)` escape evaluated at load time, or (2026-08-25)
a **structured literal** — a list, tuple, set, dict, or functor call, nested arbitrarily. An
unground right-hand side (one that computes to a value containing an unbound variable) raises
`ConstantNotGroundError` before any clause compiles; a logic-variable-shaped name anywhere in a
structured RHS is caught earlier still, as a located `SyntaxError` at compile time. A structured
RHS builds the same real Clausal term the identical literal would build in a clause body — see
[Structured constants](syntax.md#structured-constants) for the full reference, including the
declared-above ordering rule a functor call needs and the frozen/immutable-value guarantee.

!!! warning "`++` RHS values can be machine-dependent"
    `-constants(_N_WORKERS_ = ++os.cpu_count())` is legal — but it binds a different value on
    a different machine. `++()` is evaluated once, at load time; nothing about it guarantees
    reproducibility across environments.

**A file may carry more than one `-constants` directive** — a later one can reference a
constant an earlier one declared, exactly like a later `name = value` pair within one directive
can.

**Constants are always public** — there is nothing to list in `-module` or `-private`; doing
so is a `SyntaxError` pointing back at `-constants` and `-import_from`. Import a constant the
same way you import a predicate:

```clausal
--8<-- "tests/fixtures/docs/syntax_sigs.txt:constants_importing"
```

Every `-constants` declaration also registers on the declaring module for
[`module_constant/3`](builtins.md#module_constant3) reflection — an imported constant is *not*
re-registered on the importer, so it is only reachable through the module that actually
declared it.

See [Constants](syntax.md#constants) for the full reference, including the undeclared-reference
error and the `_UNUSED`-suffix naming trap.

---

## Lint Directives

### -allow_singletons

**Problem**: Clausal warns by default whenever a named variable occurs exactly once in its
clause (`ClausalSingletonWarning`) — almost always a typo. A few files have a *legitimate*
reason to be full of them: a fixture built to demonstrate the singleton pattern itself, or a
page of "most general query" examples where an unbound variable is the whole point.

```clausal
-allow_singletons

Test("most general query") <- var(SOME_UNBOUND_VAR)
```

`-allow_singletons` is a **file-level opt-out marker** that takes no arguments (bare
`-allow_singletons` or `-allow_singletons()`). With it present, the singleton lint does not run
at all for this file — including its inverse check (a `_UNUSED`-suffixed variable that occurs
more than once). It is a load-time-only flag: nothing about it survives into the compiled
predicate.

Prefer the narrower, per-variable [`_UNUSED` suffix](syntax.md#singleton-variables-and-_unused)
where only a handful of variables in an otherwise-normal file are deliberately unused — reach
for `-allow_singletons` only when the *file itself* is about demonstrating or exercising the
pattern.

See [Singleton variables and `_UNUSED`](syntax.md#singleton-variables-and-_unused) for the full
lint reference, including the exact warning text and the DCG/EDCG coverage gap.

---

## Specialization Directive

### -specialize

```clausal
--8<-- "tests/fixtures/docs/directives_sigs.txt:specialize"
```

Specializes a [meta-interpreter](metainterpreters.md) with respect to an object program, producing a new predicate with interpretation overhead removed. The MI pattern is auto-detected from the clause structure.

Options:

```clausal
--8<-- "tests/fixtures/docs/directives_sigs.txt:specialize_ex2"
```

See [Meta-Interpreter Specialization](specialization.md) for full details.

---

## EDCG Directives

!!! warning "Experimental"
    EDCG directives are parsed but end-to-end rewriting is not yet implemented.

Extended DCGs allow multiple named accumulators and passed arguments to be threaded through grammar rules automatically. See [DCGs](dcg.md) for the standard DCG system.

### -edcg_acc

```clausal
-edcg_acc(counter, X, IN, OUT, {OUT == IN + X})
```

Declares a named accumulator with its joining operation. Arguments: name, value variable, input state, output state, and joiner goal.

### -edcg_pass

```clausal
-edcg_pass(scale)
```

Declares a passed argument — a value that threads through EDCG nonterminals without modification (read-only).

### -edcg_pred

```clausal
--8<-- "tests/fixtures/docs/directives_sigs.txt:edcg_pred"
```

Declares how many visible arguments a predicate has and which accumulators/passed arguments it uses.

---

## Backend Directive (planned)

!!! note "Not yet implemented"
    `-backend(scryer)` and `-backend(trealla)` are planned for a future release. Currently, programs are loaded from Python via the `Scryer` or `Trealla` classes. See [Scryer Prolog Embedding](scryer.md) and [Trealla Prolog Embedding](trealla.md).

```clausal
-backend(scryer)  # or -backend(trealla)
-module(queens, [Queens(N, QS)])

Queens(N, QS) <- (
    length(QS, N),
    Maplist(in_domain(1, N), QS),
    SafeQueens(QS),
    labeling([], QS)
)
```

when `-backend(scryer)` is present, the import hook translates the entire file to Prolog and loads it into an embedded Scryer session. Exported predicates become bridge `PredicateMeta` classes that look like native clausal predicates to callers but execute on Scryer under the hood:

```python
from queens import Queens
from clausal import Var, Solutions

QS = Var()
*Queens(8, QS)   # drives Scryer, displays via Solutions
```

---

## Directive Processing

Directives are processed during module loading:

1. The term transformer parses `-directive(...)` syntax into directive AST nodes
2. The compiler (v2 pipeline) processes directives before clause compilation via `_process_directives`
3. Property directives set metadata flags on the predicate's `PredicateMeta` class (see [Predicates](predicates.md))
4. Import directives trigger module loading and predicate injection (see [Import System](import.md))

Directives apply to the entire module — they cannot be scoped to individual clauses.

---

??? info "Test coverage"

    Tests are in `tests/test_directives.py` (21 tests).

    - **Dynamic**: predicate metadata, runtime assert/retract, locking of non-dynamic predicates
    - **Discontiguous**: scattered clause collection
    - **Table**: tabling metadata, SLG resolution
    - **Parsing**: directive syntax recognition, arity extraction
    - **Import-level locking**: predicates locked after load, dynamic predicates remain mutable

---

*See also: [Predicates](predicates.md) — how predicates and clauses work.*
*See also: [Import System](import.md) — full details on `-import_from` and `-import_module`.*
*See also: [Tabling](tabling.md) — SLG tabling enabled by `-table`.*
*See also: [Database Operations](database_ops.md) — `assertz`/`retract` builtins that require `-dynamic`.*
