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
    Listing an atom here opts that atom into **module-local public** identity — importers see `traffic.red` as a distinct `PredicateMeta` class from any other `red`. Bare atom references that are **not** listed in `-module` or `-private` resolve to the process-wide **global** atom of the same name instead. See [Atoms § Global by default](syntax.md#atoms) and the [global-atoms-default spec](https://gitlab.com/MikeAmy/clausal/-/blob/main/implementation_plans/atoms_refactor/GLOBAL_ATOMS_DEFAULT.md).

### -private

```clausal
-private([Helper(X, Y), Edge(A, B)])
```

Declares predicates that are internal to the module. Private predicates get proper `PredicateMeta` classes but are not exposed for import.

The list may also contain bare atoms:

```clausal
--8<-- "tests/fixtures/docs/directives_sigs.txt:private_with_atoms"
```

!!! info "When you actually need `-private` for an atom"
    Listing an atom in `-private` only matters when the module wants identity **distinct from the global default** — e.g. when `draft` here must not unify with `other_module.draft` or with the global `draft`. If you only need the spelling, leave the listing out; the global default already gives the same class to every bare `draft` across modules. See the [global-atoms-default spec](https://gitlab.com/MikeAmy/clausal/-/blob/main/implementation_plans/atoms_refactor/GLOBAL_ATOMS_DEFAULT.md).

An atom may not appear in both `-module` and `-private` (mutually exclusive points on the same axis); the compiler rejects this with a hard error.

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

These directives control the new global-by-default atom identity rules introduced by the [global-atoms-default spec](https://gitlab.com/MikeAmy/clausal/-/blob/main/implementation_plans/atoms_refactor/GLOBAL_ATOMS_DEFAULT.md). The short version: bare atom references default to a process-wide global class; `-strict_atoms` opts a file out of that default, and `-overwrites` silences the shadowing warning emitted when an import collides with a local declaration.

### -strict_atoms

**Problem**: Most files want the Prolog-style ergonomic default — `red` in two
modules is the same atom, no ceremony required. But for files where a typo
quietly changes the meaning of the program (regulatory rules, clinical
decision support, legal compliance, financial compliance), the silent
auto-mint is the wrong default: a misspelled `peding` simply mints a new
global atom instead of failing fast.

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
