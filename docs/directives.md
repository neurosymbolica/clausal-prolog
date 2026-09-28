# Directives

Directives are module-level declarations in `.clausal` files that control predicate properties, imports, and compilation behavior. They are prefixed with `-` and placed at the top of the file.

---

## Module Declaration

```clausal
-module(my_module, [pred1(A, B), pred2(X)])
```

Declares the module name and its public exports. The export list specifies which predicates are accessible to importers. If omitted, the module name is derived from the filename.

The export list may mix predicates with arity (e.g. `pred1(A, B)`) and bare atoms (zero-arity predicates):

```clausal
--8<-- "tests/fixtures/docs/directives_sigs.txt:module_with_atoms"
```

#### Data functors vs predicates

A **field-carrying** entry — `point(X, Y)` — declares a *data functor*: a shape
you build terms with. Its terms compile to cells, plain tuples tagged with the
functor spelling, and the name binds that spelling rather than a class:

```clausal
--8<-- "tests/fixtures/docs/directives_sigs.txt:module_data_functor"
```

The `kind/2` clause builds and matches the cell `("point", X, Y)`.

From Python, `shapes.point` is the string `"point"`, and a term of it is the
tuple `("point", 1, 2)` — there is no constructor to call. Build the tuple.

An entry that has **clauses** in the file is a predicate: the module attribute
is its handle (`shapes.kind` names the predicate `kind`), `call/1` and friends
dispatch on it, and from Python it runs as a goal cell with `module=`:
`solve(("kind", ("point", 1, 2), K), module=shapes)` binds `K` to `point`.

#### `name/arity` — a predicate export

The ISO `name/arity` spelling exports a **predicate** by name and arity, which
is what module exports look like in ISO Prolog anyway. The module that exports
it is the module that defines it, and other modules import it from there:

```clausal
--8<-- "tests/fixtures/docs/directives_sigs.txt:module_predicate_export_vocab"
```

```clausal
--8<-- "tests/fixtures/docs/directives_sigs.txt:module_predicate_export_impl"
```

Field names are placeholders (`arg_0`, `arg_1`) until a real clause supplies
its own, exactly as with [`-dynamic`](#-dynamic).

!!! warning "No *vocabulary module*: the importer cannot supply the clauses"
    A module that exports `verdict/2` without defining it does not make
    `verdict/2` a slot other modules can fill. A module that imports it from
    there and writes clauses for it is **refused at load**, with a remedy:
    define `verdict/2` in the module that writes its clauses, export it from
    that module, and have its users import it from there. (This
    "vocabulary-implements" idiom was supported until 2026-09-24; a predicate
    has exactly one defining module.)

Both spellings work in [`-private`](#-private) too.

An entry whose arity looks like a typo loads with a
`ClausalExportArityMismatchWarning`: `-module(m, [base/9])` in a module
whose clauses are all `base/2` warns at the entry's line, names both
arities and suggests `base/2`. It stays a warning because exporting a
predicate with no clauses is legal (calling it raises `existence_error`).
It is silent when `base/9` has clauses or a declaration (`-dynamic(base/9)`,
`-table`, …) in the module, and when `base` has no clauses at any arity.

!!! info "Listing an atom declares the RIGHT to write it, not a new identity"
    **Atoms are global by spelling.** Listing `red` here does not create a module-local variant of it: the atom **is** the interned Python `str` `'red'`, and every module that writes `red` — by `-module`, by `-private`, or by `-import_from` — has that same atom, equal by `==`. What the listing buys is the *right to write the bare name*: an unlisted, unimported bare atom raises a compile-time `NameError` by default (strict is the default). For an atom other modules genuinely cannot reach or spell, use [`-hide`](#-hide), which is the only module-local mechanism. See [Atoms § Strict by default](syntax.md#atoms), [Import System § Atoms are global by spelling](import.md#atoms-are-global-by-spelling), and the [global-atoms-default spec](https://gitlab.com/MikeAmy/clausal/-/blob/main/implementation_plans/atoms_refactor/GLOBAL_ATOMS_DEFAULT.md).

### -private

```clausal
-private([helper(X, Y), edge(A, B)])
```

Declares predicates and atoms that are internal to the module. Predicates are declared on the module's `Database` (and bound to their handles) and atoms become writable bare names, exactly as `-module` exports do — and, as for `-module`, an atom listed here is the ordinary global atom of that spelling, not a module-local variant.

The list may also contain bare atoms:

```clausal
--8<-- "tests/fixtures/docs/directives_sigs.txt:private_with_atoms"
```

!!! warning "`-private` is a marker, not a barrier"
    **`-private` means "not part of my documented surface" — Python's leading underscore, not C++ `private`.** It does *not* make a name unreachable. `-import_from(owner, [draft])` reaches a `-private` atom or predicate just as readily as an exported one, and binds the **owner's** predicate handle (for an atom there is nothing to bind — it is the same global atom either way). Clausal has no access control at all: `-import_from` lowers to a Python `from M import name` and consults nothing about `M`'s declarations — not its `-private` list, not its `-module` export list (see [Why not Prolog-style modules](import.md#why-not-prolog-style-modules) — "No export lists. Everything is public").

    This is deliberate and [pinned by a test](https://gitlab.com/MikeAmy/clausal/-/blob/main/tests/test_global_atoms_default.py). It is also load-bearing: under strict atoms, a fixture or generated module with no `-module(...)` export list has importing from its `-private` list as its identity-preserving route across a file boundary.

!!! info "What `-private` actually buys"
    Listing a name in `-private` has four real effects and one advisory one:

    1. **Not identity** — listing an atom does *not* give it a module-local identity. `draft` here is the same atom as `other_module.draft` and as any bare `draft`; they unify. (This bullet used to claim the opposite; that was the pre-2026-09 model. [`-hide`](#-hide) is the tool if you need a symbol no other module can reach.)
    2. **Strict-atom resolution** — the bare name compiles instead of raising the strict-by-default `NameError`.
    3. **Shadowing** — for a PREDICATE, the private class wins inside this module over `-module`, over imports, and over the global. An atom has nothing to shadow: every route resolves to the same atom.
    4. **Signature pre-registration** — for `P(A, B)` entries, arity and field names are fixed before the first clause rather than inferred from it. A `p/2` entry declares a PREDICATE whose clauses may live in another module, exactly as in [`-module`](#data-functors-vs-predicates).
    5. **Intent** — it tells a reader the name is internal. Advisory only, per the warning above.

    The only thing that distinguishes `-private` from `-module` is which of those a reader is told. See the [global-atoms-default spec](https://gitlab.com/MikeAmy/clausal/-/blob/main/implementation_plans/atoms_refactor/GLOBAL_ATOMS_DEFAULT.md) § "Visibility is advisory".

An atom may appear in both `-module` and `-private`. The first listing processed wins and the second is a no-op — and since both resolve to the same global atom, the duplication is redundant rather than conflicting.

A [constant](#-constant_value) used to be listable in `-private` as pure documentation ("this one is an implementation detail"), a recorded no-op. It declares the ATOM now, which is a stronger reading and the intended one: a constant is spelled like an atom, so `pi` written bare is the atom `'pi'` (a plain `str`) and `++pi` is the value, and one name carries both in one file. The declaration keeps the module global; the atom listing does not bind over it.

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

This imports `double` from `utils` but makes it available locally as `my_double`.

!!! info "Importing an atom: when it matters"
    For predicates, importing is how you reach the defining module's predicate. For **atoms**, importing only grants the right to write the bare name: an atom is the interned `str` of its spelling, so `red` imported from `M` is the same atom as `'red'` anywhere else. (A [`-hide`](#-hide) atom is the one exception, and it cannot be imported by spelling.)

### -import_module

Import all exported predicates from a module:

```clausal
--8<-- "tests/fixtures/docs/directives_sigs.txt:import_module"
```

Imported predicates are accessed via qualified names: `utils.double(X, Y)`.

See [Import System](import.md) for full details. For importing Prolog `.pl` files directly, see [Importing Prolog](importing_prolog.md).

---

## Atom-Identity Directives

These directives control atom resolution and scope. Atoms are **global by spelling** — `red` denotes the same atom everywhere in a process, there is no per-module atom identity to shadow or overwrite (see [Import System](import.md#atoms-are-global-by-spelling) for the full story and its history). The short version: strict resolution is the default — an undeclared bare atom reference is a compile-time `NameError`; there is no opt-out (the old `-implicit_atoms` was removed before 1.0); `-hide` gives a module a private, compiler-renamed atom namespace other modules cannot spell.

Upgrading an existing codebase from the old auto-mint default? See the [strict-atoms migration guide](strict-atoms-migration.md).

### -strict_atoms

> **Deprecated (still supported).** Strict atom resolution is now the default,
> so this directive is redundant and can be deleted. It still forces strict mode
> where present; loading a file that uses it emits a one-per-process
> `ClausalStrictAtomsDeprecationWarning`. There is no way to opt a file *out*
> of strict: [`-implicit_atoms`](#-implicit_atoms) was removed.

**Historical context**: Before strict became the default, files could use
`-strict_atoms` to opt in to compile-time `NameError` on undeclared bare atoms.
That protection now applies everywhere by default, making this directive
redundant.

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

### -implicit_atoms

> **Removed before 1.0.** A file that carries `-implicit_atoms` (in any
> spelling) does not load: it is a `SyntaxError` that reads
> `-implicit_atoms was removed; declare atoms with -private([...]) or quote them`.

Declare the atoms a file uses — list them in `-private([...])` or
`-module(name, [...])`, or [`-hide`](#-hide) them — or write them quoted
(`'red'`, which needs no declaration). The
[strict-atoms migration guide](strict-atoms-migration.md) shows how.

### -implicit_functors

**Problem**: Construction checking is on by default (see
[Data functors vs predicates](#data-functors-vs-predicates)): a keyword-free
reference to an undeclared functor is a runtime error (the ISO term
`existence_error(procedure, F/N)`, or `type_error(evaluable, F/N)` in an
arithmetic position; from Python it is also a `NameError`), and an over-arity
reference to a declared functor's signature is a compile-time `SyntaxError`
naming `functor/arity`. Some modules — prototypes, meta-programming, code that
builds ad hoc structured data — want Prolog's traditional open-world
construction back: any functor, at any written arity, declared or not, just
builds a cell.

`-implicit_functors` is a **file-level opt-in marker** that takes no arguments
(bare `-implicit_functors` or `-implicit_functors()`). With it present, a
module's own functor construction and head matching apply the open-world (OWA)
rule instead of the checked-signature placement rule: any functor reference —
declared or not — at any written arity compiles to a cell (or matches one, on
a clause head). The identical rule applies on the head side, so a flagged
module's own clause heads pattern-match the cells its own bodies build.

```clausal
-implicit_functors
-module(scratch, [p(A)])

p(wibble(1, 2)),
```

`wibble/2` has no declared signature anywhere; under the flag, `wibble(1, 2)`
still compiles to the cell `("wibble", 1, 2)` instead of raising. The identical
source without the directive raises `existence_error(procedure, wibble/2)`
(a `NameError` naming `wibble` from Python) when the goal that references it
actually runs.

**Advisory, not backfilled.** A functor that IS declared, referenced at a
different written arity, is also advisory under the flag: `point/2` declared,
referenced as `point(10, 20, 30)`, builds `("point", 10, 20, 30)` at the arity
actually written; a short reference (`point(1)`) builds `("point", 1)`.
Without the flag, a short or over-arity reference to a declared DATA functor
is a compile-time `SyntaxError` naming `point/2` -- a term is never padded
with fresh variables.

**Keyword construction is gone, flag or no flag.** A term is built
positionally; a keyword argument (`point(x=1, y=2)`) is a load-time
`SyntaxError` in any module.

**Predicates are unaffected.** A functor with clauses in the file is a
predicate, not data — calling it compiles to a goal (class/dispatch emission)
exactly as without the flag; OWA only concerns functor *construction*.

**Dotted references stay loud.** An unresolvable dotted reference
(`other.no_such_thing(1, 2)` — a typo or a missing import) is a name-resolution
failure, not a functor-vocabulary question: it raises the ordinary `NameError`
under the flag exactly as without it. OWA opens the flagged module's own local
functor vocabulary; it does not suppress qualified-name resolution failures. A
dotted reference that *does* resolve to a real data functor is unaffected
either way.

**A [`-constant_value`](#-constant_value) RHS stays checked.** A functor call inside a
structured constant's right-hand side is not covered by the flag: it must
name a functor already declared (or imported) above the `-constant_value`
directive regardless of `-implicit_functors`, or compilation raises a
`SyntaxError` naming the fix (declare it with `-module`/`-private`/
`-dynamic` first, or import it). `-constant_value` compiles its RHS
before any predicate body runs and needs the same functor known at that
earlier point either way — OWA construction elsewhere in the module does
not reach back and relax this check.

**Orthogonal to atom resolution.** `-implicit_functors` concerns functor
*construction* arity/declaredness; it says nothing about bare (0-arity) atom
references, which are governed independently by
the strict-atoms rule (see [`-strict_atoms`](#-strict_atoms)). A
module may carry `-implicit_functors` together with `-strict_atoms`: functor
construction is advisory while bare atom references still require declaration.

**Scope**: per-file only — it does not propagate to
imported modules.

### -hide

**Problem**: Atoms are global by spelling — any module can write `red` and reach the same atom every other module declaring `red` reaches. That is almost always what you want (see [Import System](import.md#atoms-are-global-by-spelling)), but a module occasionally needs a truly private symbol: an internal sentinel or tag value that other modules must not be able to spell, read, or accidentally collide with.

```clausal
--8<-- "tests/fixtures/docs/directives_sigs.txt:hide"
```

`-hide([...])` takes a list of **bare atom names only** (a predicate signature entry like `foo(A, B)` is a compile error — predicates are already module-local through Python's own module scoping, so hiding is purely an atom concern). Every reference to a hidden atom *within its owning module* compiles to the SAME compiler-renamed spelling, so they unify with each other exactly like an ordinary declared atom would; a different module's bare use of the same spelling resolves to the ordinary GLOBAL atom instead — it simply cannot reach the hidden one, because it cannot type the renamed spelling.

**Requires a preceding `-module(...)`** in the same file: the renamed spelling embeds the owning module's name, so there is no principled identity to rename into without one. `-hide` before `-module` (or with no `-module` at all) is a compile error.

**Mechanism — compiler rename, not encryption.** The compiler renames a hidden atom to `module⟨SEP⟩name`, where `⟨SEP⟩` is a reserved codepoint (US, 0x1F — R1-revised, user-ratified 2026-09-05; originally U+E000 under R1) the Clausal reader refuses inside any atom token, quoted or not — so the renamed spelling cannot be typed by hand in ordinary source. **The guarantee this provides is uniqueness and analysis soundness, not runtime security** — the same stance Ciao's `:- hide` and Python's `__name` mangling both take. Runtime construction of the renamed spelling piece-by-piece (`atom_chars/2` and similar) CAN forge it; this is documented out-of-warranty behavior, not blocked.

**Printing renders the human form.** `write/1`, `term_str`, and the reified-term renderer all display a hidden atom as `module.name` (the dotted, human-readable form) rather than leaking the raw `⟨SEP⟩` codepoint. This is display-only — reading `module.name` back through the parser does NOT reconstruct the hidden atom; round-tripping a hidden atom through text is not a supported operation.

**Relationship to `-private`**: `-private([...])` remains visibility-advisory only — a `-private` atom is still a full GLOBAL atom by spelling, indistinguishable at runtime from one declared via `-module`. `-hide` is the stronger tool: reach for it when a different module accidentally (or deliberately) spelling the same identifier must not be able to observe or construct your value.

---

## Predicate Property Directives

### -dynamic

**Problem**: By default, predicates are locked after loading — you can't change
them at runtime. But some programs need to add or remove facts during execution
(counters, caches, learned knowledge).

```clausal
-dynamic(color/1)

color('red'),

test("add at runtime") <- (
    assertz(color('blue')),
    color('blue')
)
```

`assertz`/`asserta`/`retract` work **only** on a predicate declared
`-dynamic` — declare first. Without the declaration the `assertz` above raises
the ISO error `error(permission_error(modify, static_procedure, color/1), assertz/1)`,
and a name that is not declared at all is refused, unless the module sets the
flag [`assert_creates_dynamic`](flags.md#assert_creates_dynamic) (below). A
`-dynamic` predicate may start with no clauses. See
[Database Operations](database_ops.md) for full details.

### -set_prolog_flag

`-set_prolog_flag(Flag, Value)` sets a [Prolog flag](flags.md) when the module
loads, the ISO `:- set_prolog_flag(Flag, Value).` as a directive. A module-scoped
flag is set for this module:

```clausal
-set_prolog_flag(assert_creates_dynamic, true)
```

- `assert_creates_dynamic`: `true` makes `assertz`/`asserta` of a procedure that
  does not exist create it as dynamic (ISO 7.5.2(2)) instead of refusing it.
- `double_quotes`: the same as [`-double_quotes(Mode)`](#-double_quotes), and
  position-sensitive like it.
- A process flag (`debug`) is set for the whole process.

A setting that `set_prolog_flag/2` would refuse is a load-time `SyntaxError`
carrying the ISO error term, e.g.
`error(permission_error(modify,flag,unknown),set_prolog_flag/2)` for
`-set_prolog_flag(unknown, fail)`.

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

test("path 1 3") <- path(1, 3)
test("path 2 1") <- path(2, 1)
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
-discontiguous(test/1)

helper(X, Y) <- (Y == X + 1)
test("first") <- helper(1, 2)

other_helper(X, Y) <- (Y == X * 2)
test("second") <- other_helper(3, 6)
```

Without `-discontiguous`, the `test` clauses being separated by `other_helper`
would trigger a warning or error.

### -meta_predicate

**Problem**: when higher-order predicates are imported across modules, the
module system needs to know which arguments are goals (to resolve them in the
correct module context).

```clausal
-meta_predicate(my_map(2, '+', '-'))

my_map(_, [], []),
my_map(G, [X, *Xs], [Y, *Ys]) <- (
    call(G, X, Y),
    my_map(G, Xs, Ys)
)

double(X, Y) <- (Y == X * 2)

test("my_map calls its goal on each element") <- (
    my_map(double, [1, 2, 3], L),
    L == [2, 4, 6]
)
```

The `2` means the first argument is a goal that takes 2 extra arguments.
`'+'` means input, `'-'` means output (and `'?'` either, `':'` a
module-sensitive argument that is not a goal). The modes are QUOTED atoms:
a bare `+` or `-` is an operator, not a term, in this syntax. This ensures
correct cross-module resolution when `my_map` is imported. See [Higher-Order Predicates](higher_order.md) for builtins like `maplist` that use this pattern.

### -shallow

**Problem**: The default trampoline compilation mode has slight overhead for
stack safety. For predicates known to have bounded recursion depth (lookups,
simple dispatches), this overhead is unnecessary.

```clausal
-shallow(lookup/2)

lookup('a', 1),
lookup('b', 2),
lookup('c', 3),

test("lookup a") <- (lookup('a', V), V == 1)
test("lookup c") <- (lookup('c', V), V == 3)
```

`-shallow` compiles in simple mode (direct generator calls) instead of
trampoline mode. Use it for flat, non-recursive predicates where performance
matters. See [Compiler](compiler.md) for details on the two compilation modes.

---

## Constants Directive

### -constant_value

**Problem**: A magic number like `3.14159` or `3` repeated across several clauses is a
maintenance hazard — rename the meaning, and every occurrence has to be found and checked by
hand. Prolog has no answer to this beyond a fact plus an extra goal (`is_pi(PI), area == PI *
R**2`); Clausal gives constants their own lexical class instead.

```clausal
-constant_value(pi, 3.14159)
-constant_value(max_retries, 3)

area(R, AREA) <- (AREA == constant(pi) * R**2)

test("area of radius 2") <- (
    area(2, AREA),
    AREA == 12.56636
)
```

### -constant_number_units

```clausal
-import_from(european_union, [euro])
-constant_number_units(max_fine, 5000, euro)

applies(X) <- (fine(X, F), F > constant(max_fine))
```

`-constant_number_units(name, number, units)` is the same declaration with the unit kept **out**
of the value. It is spelled `number`, not `value`, because **only numbers carry units** — a
non-numeric value is refused at load time, naming the directive. Reflect on one with
[`constant_number_units/3`](builtins.md#constant_number_units3). It binds `name = Quantity(value, units)` — the identical object the
`5000 (euro)` annotation sugar builds — so the unit travels with the constant instead of being
repeated at every use site. *units* is a unit expression: a name, or names combined with `*`,
`/` and `**`.

The two directives are a family, which is why they are positional rather than keyword
arguments: `-constants(a = 1, b = 2)` had no room for a third argument on one of its pairs.
One line per constant also reads better in a diff.

### Reaching a constant from another module

**Ruled 2026-09-12.** A constant is in scope where it is **declared**, where it is
**imported**, or where its owner is **named**:

```text
-import_from(other_module, [max_fine])      # then: constant(max_fine)
-import_module(other_module)                # then: constant(other_module.max_fine)
```

Both forms work for the value and for
[`constant_number_units/3`](builtins.md#constant_number_units3), whose scope is resolved at
compile time.

The module-qualified form takes a **qualified name**, never an expression — the parentheses of
`constant(...)` still delimit a name, which is what lets the reference be checked before
anything runs. `constant(compute_it())` is refused exactly as it always was.

A name that is neither declared, imported, nor qualified is a **compile-time error** that names
the way out, rather than a silent failure or another module's answer.

### -constant_value (details)

`-constant_value(name, value)` declares one module-level constant — a name spelled like an
atom, which is to say anything the logic-variable rule does not claim (`pi`, `max_retries`,
`円周率`; see [Constants in the
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
    `-constant_value(n_workers, ++os.cpu_count())` is legal — but it binds a different value on
    a different machine. `++()` is evaluated once, at load time; nothing about it guarantees
    reproducibility across environments.

**One constant per directive** — a later one can reference a
constant an earlier one declared, exactly like a later `name = value` pair within one directive
can.

**Constants are always public** — the declaration itself is module-global. Listing the name
in `-module` or `-private` declares the bare **atom** of that spelling (see above), not the
constant. Import a constant the same way you import a predicate:

```clausal
--8<-- "tests/fixtures/docs/syntax_sigs.txt:constants_importing"
```

Every `-constant_value` declaration also registers on the declaring module for
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

test("most general query") <- var(SOME_UNBOUND_VAR)
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

## Migration Ratchet

### -double_quotes

**Transitional — scheduled for removal.** It selects what a **double-quoted**
literal means in the file, and it exists only so modules can migrate one at a
time. Single quotes are unaffected: `'hello'` is the atom `hello` in every
mode, and `b"…"`/`b'…'` are always [codes](bytes_as_lists.md).

```clausal
--8<-- "tests/fixtures/docs/directives_sigs.txt:double_quotes"
```

| Mode | `"hello"` means | Status |
|---|---|---|
| `chars` | the string `"hello"`, which *is* the list `['h','e','l','l','o']`; `atom("hello")` is false, `string("hello")` is true | the engine **default** (since 2026-09-26, as in Scryer and Trealla) |
| `atom` | the atom `hello` — the same term as bare `hello` and as `'hello'` | the **opt-out** for a module that still relies on the old reading |
| `codes` | — | **refused**. Codes are spelled `b"…"`. Any other argument is likewise an error. |

`-set_prolog_flag(double_quotes, Mode)` is the same directive in ISO's
spelling, and `current_prolog_flag(double_quotes, M)` reports the module's mode
([Prolog Flags](flags.md)).

The directive is **file-scoped and position-sensitive**: it governs the
literals written below it, so it belongs at the top of the file, above the
clauses. It is not inherited by importers — each file declares its own.

The whole lifetime is a three-step **ratchet**, not a compatibility flag:

1. ~~**Now.** The default is `atom`.~~ Done: every in-tree module that relied
   on the atom reading carries `-double_quotes(atom)`.
2. ~~**When every module carries one of the two**, the default flips to
   `chars`.~~ Done (2026-09-26). The default **is** `chars`;
   `-double_quotes(atom)` is the opt-out. A module that declares nothing reads
   `"hello"` as a string.
3. **When every module has dropped the directive**, `-double_quotes/1` is
   deleted from the engine and writing it becomes a load error.

Migrating a module means: rewrite each `"x"` it used as a *symbol* to `'x'`
(or to a bare declared atom), leave genuine text as `"..."`, then drop the
directive. Support for string-bearing Prolog dialects is a translation-layer
concern, never an engine flag — a `.pl` file whose strings must load as
strings gets `-double_quotes(chars)` written into its translation
automatically ([Importing Prolog](importing_prolog.md)).

---

## Removed Directive

### -tagged_terms (removed)

`-tagged_terms` used to opt a single file into the *tagged-cell* term
representation, in which a construction of a functor the module declares
compiles to a plain tuple `("point", X, Y)` rather than an instance of a
generated `point` class. **The directive is gone: cells are how compound data
compiles, in every module, with no opt-in to spell.** Writing `-tagged_terms`
is now an ordinary unknown-directive `SyntaxError`; delete the line.

Nothing else has to change in a file that carried it — its clauses compiled to
cells before and compile to cells now. What DID change for every other file is
that its compound data is cells too, which mostly matters at the Python
boundary: `mod.point` is the functor's spelling rather than a constructor, and
a term of it is the tuple `("point", 1, 2)`. See
[Data functors vs predicates](#data-functors-vs-predicates) above.

---

## Backend Directive (planned)

!!! note "Not yet implemented"
    `-backend(scryer)` and `-backend(trealla)` are planned for a future release. Currently, programs are loaded from Python via the `Scryer` or `Trealla` classes. See [Scryer Prolog Embedding](scryer.md) and [Trealla Prolog Embedding](trealla.md). The sketch below does **not** load today.

```text
-backend(scryer)  # or -backend(trealla)
-module(queens, [queens(N, QS)])

queens(N, QS) <- (
    length(QS, N),
    maplist(in_domain(1, N), QS),
    safe_queens(QS),
    labeling([], QS)
)
```

when `-backend(scryer)` is present, the import hook translates the entire file to Prolog and loads it into an embedded Scryer session. Exported predicates become bridge predicates that look like native clausal predicates to callers but execute on Scryer under the hood:

```python
# a .seam file (planned behaviour)
-import_from(queens, [queens])
for QS in --queens(8, QS):   # drives Scryer under the hood
    print(QS)
```

---

## Directive Processing

Directives are processed during module loading:

1. The term transformer parses `-directive(...)` syntax into directive AST nodes
2. The compiler (v2 pipeline) processes directives before clause compilation via `_process_directives`
3. Property directives set metadata flags on the predicate's row in the module's `Database` (see [Predicates](predicates.md))
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
