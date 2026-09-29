# Clausal — Module System and Import Hook

## Overview

Clausal predicate files use the `.clausal` extension. `.seam` is an accepted alias: a `.seam` file carries exactly the same syntax and is found, loaded and cached the same way (where both `name.clausal` and `name.seam` exist in one directory, `.clausal` wins). Importing one with a normal Python `import` statement is enough to load and compile all predicates in that file. The `clausal.import_hook` module installs a `sys.meta_path` finder that intercepts these imports before Python's standard machinery runs.

```python
import clausal  # installs the import hook as a side effect
from clausal import Var, solve

import fibonacci                  # loads fibonacci.clausal

for trail in solve(("fib", 7, F := Var()), module=fibonacci):
    print(F.value)  # 13
```

A `.clausal`/`.seam` file imports another the same way, with a directive, and
can then query it in [goal position](python_integration.md#goal-position-if-goal-for-in-goal)
— the usual way to drive Clausal from Python code:

```clausal
# report.seam
-import_module(fibonacci)

def fib_of(n):
    for F in --fibonacci.fib(++n, F):
        return F
```

`python -c "import clausal, report; print(report.fib_of(7))"` prints `13`.
(`import clausal` must come first: it installs the hook that finds `.seam` and
`.clausal` files.)

After the import:
- `fibonacci.fib` is the predicate's **handle** — a `str` naming the owning module and the predicate. Its clauses are compiled and its dispatch installed on its row in the module's `Database`; the handle names it, it is not called
- From Python, a goal is a cell — the predicate's name and its arguments — run against the module: `solve(("fib", 7, F), module=fibonacci)`
- `-import_from(fibonacci, [fib])` in another `.clausal` file binds the same handle, so both files reach the one predicate — no separate wiring step needed

On the first import, the source is parsed, AST-transformed, and compiled to Python bytecode. The bytecode is cached in `__pycache__/` as a `.pyc` file. Subsequent imports of the same file load the cached bytecode directly, skipping parsing and transformation entirely. See [caching.md](caching.md) for details.

---

## The two module objects

Every `.clausal` file has **two** associated objects, both stored in the module's globals dict:

| Name | Type | Role |
|---|---|---|
| Python module (`sys.modules[name]`) | `types.ModuleType` | Standard Python module; holds each predicate's handle and anything else defined in the file |
| `$module` | `clausal.logic.database.Module` | Logic module; holds the `Database` (clause store) and a reference to the Python module's `__dict__` |

The `$` prefix makes `$module` inaccessible as a normal Python identifier — it is injected by the import hook and used only by generated code (`$define_predicate`).

### Module vs Database

`Module` wraps a `Database`. The `Database` stores:
- `_clauses: dict[(functor, arity), list[Clause]]` — raw clauses (used as the authoritative normalization source)
- `_signatures: dict[(functor, arity), tuple[str,...]]` — keyword parameter name lists
- `_dispatch: dict[(functor, arity), Callable|None]` — compiled dispatch functions (the same functions the predicates' rows hold)

The `Module` also holds `module_dict: dict | None` — a reference to the Python module's `__dict__`. This is used by the compiler for cross-predicate name resolution and by runtime builtins like `assertz`.

---

## Import hook mechanics

### PredicateFinder

`PredicateFinder.find_spec` searches for `<name>.clausal` files in `sys.path` (or the package's `__path__` for sub-packages). On a match it creates a per-file `PredicateLoader(fullname, path)` instance and returns a `ModuleSpec` pointing to it.

### PredicateLoader (SourceLoader subclass)

`PredicateLoader` extends `importlib.abc.SourceLoader`, which provides automatic `.pyc` caching via the `get_code()` method. The key override is `source_to_code(data, path)`, which performs the AST transformation step — parsing the `.clausal` source and running `EmbedTransformer`. The resulting bytecode is what gets cached.

### PredicateLoader.exec_module

1. **Inject builtins** — all `simple_ast` names (term constructors), plus `Var`, `Trail`, `unify`, `deref`, `walk`, and `$ast` are merged into the module's `__dict__`. This makes them available in clause bodies without explicit imports.

2. **Create LogicModule** — a `clausal.logic.database.Module` is created with `module_dict=module.__dict__`. It is stored as `$module` in the globals.

3. **Install per-module closures** — `$define_predicate` (and the legacy `$assert_fact`, which the transformer no longer emits) are deferred closures that only collect the predicate nodes; nothing is asserted or compiled while the body runs.

4. **Load bytecode** — `self.get_code(module.__name__)` either loads the cached `.pyc` or calls `source_to_code()` to parse and transform fresh source. The `SourceLoader` protocol handles cache validation automatically (comparing size and an mtime stamp that also folds in a digest of the engine sources, so an engine upgrade invalidates the cache — see [caching.md](caching.md)).

5. **Execute** — the bytecode is executed in the module's `__dict__`. Each `$define_predicate` call — one per rule or fact — collects its predicate node but defers all database and compilation work.

6. **Compile the module** — `compiler_v2.compile_module(predicate_nodes, module_items, module_dict, module_name)` handles directives, clause assertion, and predicate compilation in a single pass — and binds every predicate name in the module dict to its owner's **handle**, compiling each predicate once. This is O(N) per predicate (one compilation with all N clauses) instead of the O(N²) that would result from recompiling after every single clause assertion. In a second pass, predicates marked with `-table(pred/arity)` are wrapped with `make_tabled_wrapper_trampoline`. The two-pass approach ensures cross-predicate references resolve before wrapping. See [tabling.md](tabling.md).

7. **Lock non-dynamic predicates** — lock the row of every predicate in the module's `Database` that was not declared with [`-dynamic(pred/arity)`](directives.md).

---

## `$define_predicate` — asserting a rule (deferred)

Called once per clause — a `head <- body` rule or a trailing-comma fact — as the module executes. Steps:

1. `logic_module.define_predicate(predicate_node)` — flattens the `And`-chain body, normalises fact heads (ground values → `Var + Is`), asserts the resulting `Clause` to the database, and registers the keyword signature.

2. Look up the binding the module body declared for the functor (`$declare_head` bound the module's own predicate handle).

3. Whatever the name is bound to, stamp the row the clause landed on: its owner (`record_clause_source`) and, if it has no signature yet, the head's field names from the rewriter's `HeadFieldNames` module item (the snapshot of `EmbedTransformer._seen_functors`, first registration wins). 

4. Record `(functor, arity) → handle` in the pending dict. Compilation is deferred until all clauses have been asserted.

---

### Facts

A trailing-comma fact goes through the same `$define_predicate` call, with a
body of `True`. Fact normalization: ground values in functor field positions are replaced with fresh `Var` objects and corresponding `Is(var, value)` body goals. This enables output-mode queries — e.g., `fib(N, RESULT)` with both args unbound can enumerate facts rather than only checking them.

---

## Deferred compilation

Previously, each `$define_predicate` call immediately recompiled the predicate with all accumulated clauses. For a predicate with N clauses, this meant N compilations — O(N²) work.

With deferred compilation, assertions and compilation are separated:
- During `exec()`, each `$define_predicate` only collects the predicate node.
- After `exec()` completes, `compiler_v2.compile_module` asserts and compiles each predicate exactly once with the full clause set.

This is safe because no predicate of the file is queried during its own load. (A module-level goal-position `--goal` over a predicate of the same file therefore fails at load: put it in a `def`, or query an imported predicate.) [Directives](directives.md) (`-dynamic`, etc.) execute before clause definitions, so `db.is_dynamic()` is already set when compilation runs.

---

## Importing predicates between `.clausal` files

`.clausal` files can import predicates from other `.clausal` files (or from Python modules that bind a plain object with a `_get_dispatch()` method) using two directives: `-import_from` and `-import_module`.

### `-import_from` — selective import

```text
-import_from(myapp.graphs.utils, [shortest_path, reachable])
```

This emits `from myapp.graphs.utils import shortest_path, reachable` in the generated Python code. The imported names are bound to the exporting module's predicate handles in module globals, where the compiler picks them up and wires dispatch automatically.

Imported predicates can be used in clause bodies just like locally-defined ones:

```clausal
connected(X, Y) <- reachable(X, Y)
```

#### Aliases

```text
-import_from(myapp.graphs.utils, [alias(reachable, reach)])
```

Generates `from myapp.graphs.utils import reachable as reach`. Use the alias name in clause bodies:

```clausal
connected(X, Y) <- reach(X, Y)
```

Write alias names like every other predicate name, in lowercase `snake_case`. An ALL-CAPS name (`R`, `REACH`) is a logic variable to the name resolver and will not work as an alias.

#### Name isolation

Behind the scenes, imported predicates are stored under a fully-qualified dotted key in compiled function globals — e.g., `"myapp.graphs.utils.reachable"` rather than bare `"reachable"`. This means Python code in the `.clausal` file cannot accidentally shadow an imported predicate by assigning to the same name. The dotted key is invisible to the user; clause bodies use the short local name as written.

#### Importing constants

[Module-level constants](syntax.md#constants) (`pi`) use the same two directives, with the
same direct and alias forms:

```clausal
--8<-- "tests/fixtures/docs/import_sigs.txt:import_from_constants"
```

One difference from a predicate import: importing a name that this file already declared with
`-constants` is a `SyntaxError` rather than a silent overwrite, since the import would rebind
the same module global — rename the incoming one with `alias(...)`.

The alias form used to require a constant-shaped name on **both** sides. That rule lapsed on
2026-09-11 with the spelling it was built on: an importer cannot tell a constant from an atom
or a predicate in another module, because whether a name is a constant is the *owner's* fact
and an atom-shaped name does not carry it. `alias(pi, mypi)` is an ordinary rename now.

A module's `-constants` declarations are all public interface — there is nothing to list in
`-module`/`-private` and no export step — and enumerable via
[`module_constant/3`](builtins.md#module_constant3); an imported constant is *not* re-registered
on the importing module, so it stays reachable only through the module that actually declared
it.

### `-import_module` — whole-module import with qualified calls

```clausal
--8<-- "tests/fixtures/docs/import_sigs.txt:import_module_directive"
```

This emits `import myapp.graphs.utils` in the generated Python code. The module object lands in globals. Predicates are accessed via qualified (dotted) names:

```clausal
connected(X, Y) <- myapp.graphs.utils.reachable(X, Y)
```

Qualified calls are resolved at compile time: the compiler walks the dotted attribute chain, finds the predicate's handle, and stores it under the dotted key `"myapp.graphs.utils.reachable"` in compiled globals. At runtime the call site dispatches through `$dispatch_at(handle, arity)` — or, for a locked predicate, through the dispatch function captured at compile time — with no attribute lookup on each call.

### Restrictions on qualified names

The dotted chain in a qualified call must consist entirely of non-variable names. Logic variables (ALL-CAPS like `FOO`, or leading underscore like `_x`) are rejected with a `SyntaxError`:

```clausal
--8<-- "tests/fixtures/docs/import_sigs.txt:qualified_name_errors"
```

Only simple dotted name chains are supported. Computed attribute access or method calls are not valid in predicate position.

[Constants](syntax.md#constants) (`pi`) are not variable names — a constant is spelled like an
atom, which is exactly the complement of `_is_logic_var_name` — so a qualified constant
reference passes this rule by construction, with no special-casing needed. After
`-import_module(other_module)`, `other_module.pi` resolves in **both** term position and inside
a `++()` escape:

```clausal
--8<-- "tests/fixtures/docs/import_sigs.txt:qualified_constant_access"
```

### How it works under the hood

1. **`_handle_import_from_directive`** on `EmbedTransformer` parses the directive, emits a Python `from ... import` statement, and records a remap (`{local_name: "full.module.path.Name"}`) in `_import_remap`.
2. The remap is passed to every `TermTransformer` instance created for clause heads and bodies.
3. when `TermTransformer.visit_Name` sees a name in the remap, it emits `LoadName(name="full.module.path.Name")` instead of `LoadName(name="Name")`.
4. The compiler's `_collect_globals_info` collects the dotted name as a call target. `_inject_resolved_targets` resolves it — first by attribute traversal from globals (for `-import_module` qualified calls), then by `sys.modules` lookup (for `-import_from` remapped names).
5. The resolved predicate binding (the owner's handle) is stored under the dotted key in the compiled function's globals dict. Dict keys don't need to be valid Python identifiers — `"myapp.graphs.utils.reachable"` works fine.

### Cross-module calls from Python

From Python, import the module and run a goal cell against it:

1. `import fibonacci` loads it; `fibonacci.fib` is the predicate's handle — a name, not a callable.
2. `solve(("fib", 7, F), module=fibonacci)` resolves `fib` in that module's dict to the handle and dispatches through the owner's row.
3. A `.clausal` module that `-import_from`s `fib` binds the same handle, and its compiled call sites reach the same row.
4. Python hosted in a `.clausal`/`.seam` file skips the cell-building: after `-import_module(fibonacci)`, `for F in --fibonacci.fib(7, F):` runs the goal in place.

### Why not Prolog-style modules

Prolog's module system is widely regarded as one of the language's weakest points. Clausal avoids every major pitfall:

| Prolog pain point | Clausal's approach |
|---|---|
| **Meta-predicate "context module" confusion** — the #1 complaint | A predicate binding is its owner's handle, which names the defining module. A goal argument is resolved in the caller only where the callee declares it with [`-meta_predicate`](directives.md#-meta_predicate), as in Scryer. |
| **Flat namespace** | Python packages give hierarchical dotted paths for free. |
| **Operator scoping** | No user-defined operators. Non-issue. |
| **Export list maintenance** | No export lists. Everything is public — `-module`/[`-private`](directives.md#-private) declare a module's *documented surface*, not an access barrier, and `-import_from` reaches a private name just as readily (Python convention: `_` prefix = private). |
| **`assert`/`retract` module context confusion** | Each predicate's clauses live on its owner's row. `assertz` through an imported name writes to *the owner's* row. |
| **ISO standard fragmentation** | We use Python's `importlib` — one standard, universally implemented. |

### Circular imports

Same strategy as Python — partial module objects. The deferred compilation model helps: all clauses are asserted before any compilation happens. If module A imports module B which imports module A, B sees A's partially-loaded module object (handles bound, dispatch not yet compiled). when B's predicates call A's predicates at runtime, A's dispatch is already compiled by then.

### Error handling

- Unknown module in `-import_from` or `-import_module` → Python's `ImportError`
- Unknown predicate name in import list → Python's `ImportError` (from `from X import Y`)
- Bad directive syntax (non-dotted path, missing list) → `SyntaxError`
- Logic variable in qualified name → `SyntaxError`

#### The import error tells you what the target *does* export

`cannot import name X from M` on its own only says what is missing. Since the
loader knows what `M` declares, it appends it (`clausal/import_diagnostics.py`,
called from the module-exec seam in `clausal/import_hook.py`):

```text
ImportError: cannot import name 'under_budget' from 'shop.catalog' (/…/shop/catalog.clausal)
  catalog exports: price/2, in_stock/1, apple, pear, over_budget
  did you mean: over_budget ?
  -> either add `under_budget` to that -module(...) list and define it there,
     or stop importing it and remove every use.
```

Predicates carry their arity, bare atoms do not — the same spelling
`-module(...)` uses. Three situations are reported differently, because they
need different repairs:

| situation | what you get |
|---|---|
| module exists, is Clausal, lacks the name | the `-module(...)` export list, plus a near-miss suggestion |
| module does not exist at all | "names a module that does not exist … no export list to show" — never an empty list, which would read as "exports nothing" |
| module exists but is not a Clausal module | Python's own message, untouched — a Clausal file importing `re` or `numpy` gets Python's diagnosis, not a Clausal one |
| a segment's directory is on disk but misnamed | the directory, the identifier rule, and the rename — see below |

A module with no `-module(...)` list is told so, and then shown the names it
actually binds. Export lists longer than 40 names are truncated, and the
message says so and gives the file path — a silently cut list would read as
authoritative.

### A path segment is a directory name, literally

Every segment of a dotted import is a **valid Python identifier**, and a package
directory is importable only under its own name. So `shop/order-rules/` can never be
the `order_rules` of `-import_from(shop.order_rules.pricing, …)`: `order-rules` is not an
identifier, and `order_rules` is a different segment, not a spelling of it. The
same goes for a file — `order-rules.clausal` is not the module `order_rules`.

Reported as "no module named 'shop.order_rules'" this reads as a missing file, and
sends you looking for a typo (or creating a second copy of a package you already
have). So when the failing segment is explained by a misnamed directory or file
sitting on the search path, the message names it:

```text
ModuleNotFoundError: No module named 'shop.order_rules'
  -import_from(shop.order_rules.pricing, [discount])
    in app.clausal
  the segment 'order_rules' did not resolve, so neither can
    'shop.order_rules.pricing'.
  /…/shop/order-rules
    is there, but 'order-rules' is not a valid Python identifier, so no dotted
    import can name it — 'order_rules' is a different segment, not a spelling
    of it. There is therefore no export list to show.
  -> rename the directory 'order-rules' to 'order_rules'. Renaming is the only
     repair: a package directory is importable only under its own name, so the
     import cannot be adjusted to meet it.
```

Renaming really is the only repair: there is no way to write the import that
matches a non-identifier name. A **digit-leading** name (`2024_rules`) is
rejected earlier still — you cannot even write the directive, so you get a
syntax error with a caret on the digit rather than an import error.

If nothing on the search path resembles the segment, the older "does not exist"
wording stands: claiming a naming fault with no misnamed entry to point at would
be an invention.

---

## Name resolution is lexical (Pythonic), not dynamic (Prolog)

This is the single most important scoping rule to internalise, and it is where
Clausal deliberately departs from Prolog. **It follows Python, not Prolog.**

**The rule.** A predicate resolves the names it calls against **its own
defining module's namespace** — the module the clause was *written in* — fixed
when that predicate is compiled. It does **not** resolve them in the namespace
of whoever *calls* it. This is exactly how a Python function behaves: a function
defined in module `lib` looks its free names up in `lib`'s globals, never in the
globals of the module that happens to call it.

**Prolog is split on this — and neither half works like Clausal.** Standard ISO
Prolog (ISO/IEC 13211-1) defines *no* module system at all, so a classic
"consult everything into one database" program has a single flat global
namespace: there is only one `requirement/4`, and any library predicate that
calls it picks up whatever the program happened to load. That is less
"resolution relative to the caller" than "there is nothing to encapsulate" — and
it is the behaviour that breaks the encapsulation you would expect.

Real systems add module systems to fix exactly this, but those are **de facto**,
per-implementation (SWI, SICStus, …); the ISO *Modules* standard, ISO/IEC
13211-2, was essentially never adopted. And here is the subtlety: in those module
systems an *ordinary* call like `requirement(...)` inside a library module
**does** resolve to that library's own `requirement/4` — lexically, just like
Clausal. The genuinely caller-relative behaviour is reserved for
**meta-predicates**: when a library declares `:- meta_predicate assess(…, :, …)`,
Prolog makes that argument module-sensitive and *implicitly* threads the caller's
module into goals passed there (the "context module"). That implicit threading is
the part Prolog programmers reliably trip over.

Clausal collapses both cases into one rule: names are always resolved lexically
against the defining module, and when a predicate needs to call something the
caller owns, the caller **passes it in explicitly** as a goal. There is no flat
global database and no implicit context module — the wiring a `meta_predicate`
declaration would do behind your back becomes an ordinary, visible argument.

### What this means in practice

A library predicate cannot "reach back" into the importer to call a predicate
the importer defined. The name isn't in the library's namespace, so the call
raises at runtime:

```clausal
# lib.clausal — the library knows nothing about hook
run_check(X) <- (hook(X))
```

```clausal
# caller.clausal
-import_from(lib, [run_check])

hook(42),                          # defined HERE, in the caller
test_dynamic(X) <- (run_check(X))    # asks the library to call hook
```

Querying `test_dynamic(X)` raises `Predicate hook/1 not found` (a
`PredicateNotFoundError`, which is a `KeyError` and, since 2026-09-25, also a
`LogicException` carrying the ISO term Scryer raises for the same call:
`error(existence_error(procedure, hook/1), hook/1)`, so
`catch(G, error(existence_error(procedure, PI), _), Recovery)` catches it, as do
`except KeyError` in Python and a `++KeyError` catcher). The message goes on to name
the namespace it searched and list what `lib` *does* define — which is the
point: the list is `run_check/1`, and `hook` is not on it.
`run_check` was compiled in `lib`'s namespace, where `hook` does not exist — and
Clausal never consults the caller's namespace to find it. A Prolog programmer
coming from the flat, module-less style expects this to find the caller's
`hook/1`; in Clausal — as in a properly modularised SWI/SICStus program — it does
not.

### The idiom: pass the predicate as a goal

When a library predicate needs to invoke something the caller supplies, the
caller passes that predicate **as a goal argument** (higher-order), and the
library invokes it with the [`call/N` / `call_goal` higher-order builtins](higher_order.md).
This is the Pythonic equivalent of passing a callback / function object instead
of relying on a global name being in scope.

A predicate name passed as data is a plain atom, so the library must say which
argument is a goal, with Scryer's [`-meta_predicate`](directives.md#-meta_predicate)
declaration. An integer (or `':'`) position is qualified with the **caller's**
module at the call site; `'+'`, `'-'` and `'?'` positions are left alone:

```clausal
# lib.clausal — the hook is a parameter, not a free name
-meta_predicate(run_check(1, '?'))

run_check(HOOK, X) <- (call_goal(HOOK, X))
```

```clausal
# caller.clausal
-import_from(lib, [run_check])

hook(42),
test_ho(X) <- (run_check(hook, X))   # pass our hook in as a goal → binds X = 42
```

Without the `-meta_predicate` line, `hook` would be looked up in `lib`, and the
call raises `error(existence_error(procedure,hook/1),hook/1)` — exactly what
Scryer does.

This is the right pattern whenever a generic library predicate must call back
into domain-specific predicates. For example, a generic eligibility engine takes
the domain's `requirement` predicate as a goal argument rather than calling a
bare `requirement/4` and hoping the caller defined one:

```clausal
-allow_singletons
# Generic, reusable: the requirement relation is passed in. Every
# parameter below is a singleton on purpose — the body is elided; the
# point of this sketch is the meaningful argument names themselves.
assess(SUBJECT, REQ_IDS, PROFILE, REQUIREMENT, LABELS, RESULT) <- (
    # ... evaluate each id in REQ_IDS by calling REQUIREMENT as a goal ...
)
```

### Why Clausal chose this

Clausal is a logic-programming layer for Python programmers, many of whom do not
know Prolog. The guiding principle is **least surprise for a Python programmer**:
imports, modules, and name scoping should behave the way they already do in
Python — lexical resolution against the defining module, predicates as
first-class objects you pass explicitly — rather than a flat global predicate
database. Caller-module qualification happens only where a library declares it
with `-meta_predicate`, as in Scryer. The closure/lexical model is also what
makes predicates ordinary named values (their handles) you can import, pass around,
and call by reference, which is exactly what the [`call/N`/`call_goal`
higher-order builtins](higher_order.md) and [lambdas](lambdas.md) rely on.

> **One-line summary.** If you came from Prolog: a library predicate sees the
> names *in its own file*, never the caller's. Need it to call something the
> caller owns? Pass that predicate in as a goal argument, and declare the
> argument with `-meta_predicate` in the library.

### Atoms are global by spelling

Unlike predicates, **atoms are not lexically scoped.** An atom **is** the
interned Python `str` itself, and its spelling IS its value, everywhere in
the process — two atoms of the same spelling are the same value wherever
they were made (`==`; interning makes `is` agree too, but `==` is the
test). Listing
an atom in `-module(...)` / `-private([...])` declares that this file is
allowed to reference the spelling (undeclared bare atoms are a compile-time
error — see [`-strict_atoms`](directives.md#-strict_atoms)) — it does **not**
create a module-local variant of it. Two modules that each declare the same
atom hold the exact same value.

```clausal
# lib.clausal — declares its own `approved`
-module(lib, [approved, check(X)])

check(approved),
```

```clausal
# caller.clausal — separately declares the SAME spelling `approved`
-import_from(lib, [check])
-private([approved])

ask <- check(approved)             # SUCCEEDS: `approved` is the same atom
                                   # everywhere, whichever file declares it
```

`ask` succeeds: `check`'s clause head and the goal `check(approved)` both
carry the atom `approved` (the interned `str` `'approved'`) — there is nothing to
re-import for agreement's sake. (Importing it anyway, `-import_from(lib,
[check, approved])`, still works and is a reasonable style choice — it just
is not REQUIRED the way it used to be.)

**This used to be the sharpest edge in Clausal's scoping model** — atoms
previously carried per-module identity (a distinct class per declaring
module), so the SAME example above silently failed instead of succeeding, a
trap easy to misdiagnose as a legitimately-unsatisfiable query. That design
is gone: atoms are global by spelling now, matching standard Prolog/Ciao
semantics, and the module-local-identity failure mode described above cannot
happen any more.

**Need genuine privacy instead?** Occasionally a module wants a symbol other
modules truly cannot spell, read, or collide with — an internal sentinel, a
tag value that must not leak. That is what
[`-hide`](directives.md#-hide) is for: it compiler-renames the atom into a
namespace keyed by the owning module, using a codepoint the reader refuses
elsewhere. `-private([...])` alone does **not** provide this — a private atom
is visibility-advisory only, and (per the above) is still the same global
value any other module reaches by spelling it.

### Field names are local; arity is the contract

A functor's argument *names* are a module-local labelling of its slots. Two
modules may spell the same functor's fields differently — one
`verdict(STATUS, CITATIONS)`, the other `verdict(OUTCOME, CITES)` — and both
spellings are valid views of the same two slots. Its **arity** is not local:
it is part of the functor's identity. `verdict/2` and `verdict/3` are two
different functors (and two different procedures, as in ISO), and one file
may define both -- unless the file DECLARES `verdict`'s field names, which
belong to one arity (see [Predicates](predicates.md)).

The rewriter follows that rule. A clause head is normally emitted with the
field names derived from the head variables, but when the same file also
`-import_from`s that functor, the head binds by **position** instead. The
import rebinds the name to the exporting module's predicate, and a positional head
fits that predicate whatever it calls its slots — so declaring a functor locally
and importing the same name (the re-export idiom) is safe in either textual
order.

A genuine disagreement is therefore always an arity disagreement, and it still
raises: a head with more arguments than the declared head has fields raises
`ClausalTermConstructionError`, naming the functor, both arities, where the
head was declared and where the term was constructed. A declaration's field
names belong to one arity, so they cannot be reconciled with another: give
every declaration and clause head the same number of arguments, spell the
declaration `name/N` (no field names) so the other arity is a procedure of its
own, or rename one of them.

### One defining module per predicate

`-import_from` binds the **exporting module's predicate itself** (its handle), not a copy
of it. That shared identity is the point — it is what lets a term built in one
module unify with a pattern built in another — but it also means a clause head
written under an imported name lands on the exporter's predicate.

So a module that imports a functor and then writes a clause for it is refused at
load time, whenever that functor already has clauses:

```text
ext defines a clause for colour/1, which it -import_from's from exp.
  An -import_from binds the EXPORTER's predicate, so this clause would not add
  to the 2 clauses already on colour — it would replace all of them, for every
  module that can reach it. Clausal has no -multifile: a predicate has exactly
  one defining module.
  those 2 clauses are exp's own
    /path/to/exp.clausal
  colour is declared at /path/to/exp.clausal:1
  -> move this clause into exp, which supplies colour's clauses — that is the
     only module whose clauses for it are compiled together;
     or, if it is meant to be a predicate of this module, drop colour from the
     -import_from(exp, [...]) list and give the local one a name of its own.
```

Before this check the clause list was silently **replaced**: the exporter's own
facts vanished, from the exporter's own queries, load-order dependent and with
no error. Extending the list instead is not available — one predicate compiles
to one dispatch function against one module's globals, so the exporter's clause
bodies (written against *its* `-private` atoms and *its* imports) cannot be
compiled in the importer's scope. Hence the rule: one predicate, one defining
module.

**What still works: declare here, implement there.** A functor exported with no
clauses is a *declaration* — a bare vocabulary atom used as a dict key, or a
signature whose implementation lives downstream. Importing it and supplying the
clauses is the intended idiom and is not refused; there is nothing to destroy.
Only the second implementer of the same functor is refused, and the message
names the module that actually supplied the clauses, which may be an importer
rather than the exporter.

Reloading the *same file* — under its dotted name and again under a private test
name, say — is not a redefinition and never refuses: ownership is tracked by
source path.

Runtime `assertz/1` against an imported predicate is unaffected by this check; it
already raises `permission_error(modify, static_procedure, F/N)`.

---

## Builtin injection

The following names are injected into every predicate module's namespace by the import hook:

**Simple AST constructors**: all names from `clausal.pythonic_ast.nodes.__all__` — `LoadName`, `Call`, `IntLiteral`, `Is`, `And`, `Or`, `Not`, etc. Generated code references each through its `$` twin (`$Call`, `$Predicate`, …), so a user predicate spelled like one can never shadow it.

**Runtime values**: `Var`, `Trail`, `DictTerm`, `SetTerm`, `PyThunk`, `FStringThunk`, `Quantity`, `Undefined`, `BoolEq`, `BoolImpl` (one table: `INJECTED_RUNTIME_BUILTINS` in `clausal/logic/compiler/predicate.py`). The engine helpers are injected only as `$walk`, `$deref`, `$unify`, so `walk/2`, `deref/2` and `unify/2` are free for user predicates.

**Hidden globals** (inaccessible as normal identifiers):
- `$module` — the `LogicModule` for this file
- `$define_predicate` — per-module closure for clauses (rules and facts)
- `$assert_fact` — legacy per-module closure for fact statements (no longer emitted for `.clausal` source)
- `$ast` — the Python `ast` standard library module

---

## IPython integration

`clausal.import_hook.enable_ipython(globals())` installs the `EmbedTransformer` as an [IPython](ipython.md) AST transformer and injects the same builtin set into the IPython namespace. This lets you write `.clausal` syntax in IPython cells interactively. Per-module LogicModules are not used in IPython; the session shares a single namespace.

---

## Importing `.pl` (Prolog) files directly

!!! warning "Experimental in 1.0"
    `.pl` import is **experimental** and outside the 1.0 compatibility promise
    (see [Public API](public-api.md)). It runs an older translator into the
    seam syntax: cut and if-then-else are refused, and it is not an ISO
    Prolog consult.

Clausal can import Prolog `.pl` files without a manual translation step. Placing a `.pl` file on `sys.path` makes it importable:

```python
import clausal            # installs the import hook
import my_prolog_module   # finds and translates my_prolog_module.pl
```

The translation pipeline runs on the fly:

```
.pl source → prolog_to_clausal() → .clausal text → EmbedTransformer → bytecode
```

The resulting bytecode is cached as a `.pyc` file, so subsequent imports skip translation entirely.

### Finder priority

The import hook registers three finders in `sys.meta_path`, in this order:

1. **PredicateFinder** — searches for `.clausal` files
2. **PrologFinder** — searches for `.pl` files
3. **ModulesFinder** — redirects bare names to `clausal.modules.*`

If both `foo.clausal` and `foo.pl` exist in the same directory, the `.clausal` file wins.

### Recursive imports

when a `.pl` file contains `:- use_module(bar, [helper/1]).`, the translator emits `-import_from(bar, [helper])` in the `.clausal` text. At compile time, `importlib.import_module("bar")` triggers the import hook again, which finds and translates `bar.pl`. Python's `sys.modules` sentinel handles circular imports.

Library imports are mapped to Clausal built-in modules:

| Prolog | Clausal |
|---|---|
| `:- use_module(library(clpfd), [...])` | `-import_from(clausal.logic.clpfd, [...])` |
| `:- use_module(library(clpz), [...])` | `-import_from(clausal.logic.clpfd, [...])` |
| `:- use_module(library(lists))` | *(built-in — no import emitted)* |
| `:- use_module(library(apply))` | *(built-in — no import emitted)* |
| `:- use_module(bar)` | `-import_module(bar)` |

### Translation errors

If a `.pl` file contains constructs that cannot be translated (cut, if-then-else), the import raises a `SyntaxError` with a clear message:

```
SyntaxError: Cannot import foo.pl: Cut (!/0) cannot be translated to Clausal.
```

### Caveats

- **Bare Prolog atoms** (lowercase identifiers like `red`, `foo`) are declared for you: the translator emits a `-private([red, ...])` line, so they load under the strict-atoms default.
- **The `.pl` extension is also used by Perl.** If a Perl script ends up on `sys.path`, the import hook will attempt to parse it as Prolog and raise a `SyntaxError`. Avoid placing Perl scripts in directories on `sys.path`.
- **Encoding:** All `.pl` files must be UTF-8 encoded. Non-UTF-8 files will raise `UnicodeDecodeError`.
- **Stdlib shadowing:** The Clausal finders (`.clausal`, `.pl`) run *before* Python's `PathFinder` on `sys.meta_path`. A file like `os.clausal` or `re.pl` on `sys.path` named after a standard-library module is almost always an accident, so Clausal does **not** shadow it: the finder emits a `ClausalLintWarning` and defers to the standard library (the stdlib module is imported). Rename the file to avoid the warning. Avoid naming `.clausal`/`.pl` files after standard Python or Clausal modules.

### Loading `.pl` files programmatically

```python
from clausal.import_hook import _load_prolog_module

mod = _load_prolog_module("my_prolog", "/path/to/my_prolog.pl")
logic_module = mod.__clausal_module__
```

---

## File discovery

`PredicateFinder` and `PrologFinder` search for `<modulename>.clausal` and `<modulename>.pl` respectively in:
- `sys.path` for top-level module names
- the parent package's `__path__` for sub-modules

Standard `.py` files are unaffected — Python's built-in finders handle them independently.

---

## Loading `.clausal` files programmatically

For tests and external callers, `clausal.testing.load_clausal_module(path)` loads a `.clausal` file from its path, without relying on `sys.path` discovery; each call compiles it afresh, with its own database:

```python
from clausal import Var, solve
from clausal.testing import load_clausal_module

mod = load_clausal_module("/path/to/my_predicates.clausal")
for _ in solve(("my_pred", X := Var()), module=mod):
    print(X.value)
```

Underneath it is `clausal.import_hook._load_module(fullname, path)` (private), which creates a fresh `PredicateLoader` and module instance and evicts any previously cached `sys.modules` entry for the name first; the engine's own test helpers use it directly.

---

*See also: [Architecture](architecture.md) — how the import hook fits into the overall pipeline · [Caching](caching.md) — `.pyc` bytecode caching details · [Term & Goal Expansion](term_expansion.md) — module-level compile passes that run during import.*
