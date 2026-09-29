# Native ISO front end, strategy step 2: from facts to a loadable rulebase

2026-09-29 · engine-lane · DESIGN ONLY (no engine change in this commit)
Base: canonical main `530814b4` (worktree `/workspace/_isoreader`, branch
`design/native-iso-reader-step2-2026-09-29`). Every number below was measured on this base by
the probes in `implementation_plans/native-iso-reader-step2-2026-09-29/`. Re-run them rather
than quote them.

Inputs: a downstream migration strategy (step 2 is this lane's) and a downstream sizing
document (§6 pilot, §11 rulings);
`implementation_plans/prolog-reader-l1l2-plan.md`; the 2026-09-09 gap survey (clone-only,
untracked); `clausal/tools/{prolog_reader,iso_l3,prolog_parser,prolog_to_clausal}.py`;
`clausal/import_hook.py` (`PrologLoader`, `_run_v2_pipeline`); a downstream
Prolog reader. The plan `iso_l3.py` cites, `clausal-iso-to-transformed-ast-2026-09-14.md`
(rev 4), is not in this tree or in its history. This plan replaces it for P2 onward.

Rulings consumed. Native parser, not the translator (§11.5). Cut-free and no committed
choice, ever: `!`, `->` and `*->` are refused by design. ISO first, then Scryer, never SWI.
`"…"` is a char list; atoms are single-quoted. Declarations are kept, with an ISO-syntax
directive (§11.2). Dicts stay first class, with predicate forms (§11.1). Units are handled
per target (§11.4). `once/1` and `\+` go, through a transition policy (§11.3): existing uses
are allowed and new ones are not.

---

## 1. Measurements (this base)

### 1.1 `iso_l3` today (`probe_l3_today.py`)

| input | reader item | L3 result |
|---|---|---|
| int / atom / quoted atom / negative int fact | Clause | lowered |
| `"abc"` fact arg | Clause | **refused** (`('$chars','abc')`; the P1 message says "strings" are handled, but they are not) |
| float, variable, compound, partial list, `{}` arg | Clause | refused |
| any rule (`:-`) | Clause | refused ("rules are P2") |
| `module/2`, `use_module`, `dynamic`, `initialization` | Directive | refused ("P3") |
| `s --> [a].` | DCGRule | refused |

Three defects that fail open. All three belong in slice 0:

1. **`read_iso` silently drops the last clause when the file does not end in a newline.**
   `read_iso("f(1).\ng(2).")` returns 1 item, and `read_module` on the same text returns 2.
   `read_iso` calls `feed("")` where it should call `close()`, so the final `.` never
   becomes an end token. The P1 stats cannot see this, because the denominator only counts
   items that were read.
2. **A refused clause is dropped but the module still loads.** Through the real
   `PrologLoader` with L3 swapped in, `k("ab").` was refused (read=4, lowered=3, refused=1).
   The import succeeded anyway, and `k([a,b])` then answered `False`. The refusal is visible
   only in a stats dict that the loader throws away.
3. `lower_arg`'s `_is_atom` branch is dead code: `isinstance(t, str)` catches every atom
   first. It also still indexes `t[0]`, which was the pre-stage-2 cell shape. The result is
   correct only because an atom is now a `str` constant.

### 1.2 Audit 3's "silently wrong" row, re-measured on the old `.pl` path (`translator_probe/`)

| Audit 3 item | today | evidence |
|---|---|---|
| `setof`/`bagof` `^` stripped | **still silently wrong** | `setof(X, Y^p(X,Y), L)` over `p(1,a) p(2,a) p(3,b)` answers `[[1,2],[3]]` (two answers). ISO gives one, `[1,2,3]`. The engine groups correctly when handed `^` directly |
| `max`/`min`/`abs` → non-evaluables | **now loud**, still wrong | translated to `max_`/`min_`/`abs_`, then `type_error(evaluable, max_/2)` at call time. The engine evaluates `max(3,5)` natively (cell probe: `5`) |
| `profile_get` → `get` rename | still renames | seam text shows `get(X, k, V)`. `profile_get` exists nowhere in the engine; it is an exporter name |
| imported `euro` shadowed by `-private` | **gone** | `-private([euro])` plus the import still answers `euro`, because atoms are `str` |
| unquoted `lib/x` import dropped as a comment | **still silently dropped at load** | emitted as `# use_module: …`. The load succeeds, and the call fails later with `PredicateNotFoundError mx/1`. The quoted form is refused at load ("must be a dotted module path") |
| NEW: `set_prolog_flag(double_quotes, codes)` | **silently ignored** | the translator turns it into a comment, and `current_prolog_flag(double_quotes, X)` answers `chars`. The seam directive handler would raise `permission_error` |

Also obsolete in Audit 3. Undeclared data compounds now load: `X = pt(1,2)` answers,
because of C1 `e8d5c71d`. `.pl` test discovery now works in file mode and directory mode
(`probe_testdisc.py`): 2 files run 4 tests, the 2 planted reds are reported, and the exit is
1. Its diagnostics still show *translated* goals and line numbers. pytest collects `.pl` only
under this repo's conftest. On a directory outside the repo it collects nothing and exits 5.
That exit is loud, but it is not collection.

Refused or missing on the old path (`probe_refused.py`). `!`, if-then-else, `@<` (the refusal
message is stale) and yall are refused. `#=` is **not even read**: a parse error, because
`use_module(library(clpz))` does not install clpz's operators. `library(clpq)` and
`library(reif)` fail with ModuleNotFoundError. `initialization/1` gives "Unknown directive".
`aggregate_all/3` gives an internal `in_/3` arity SyntaxError. `nth1`, `keysort`,
`atom_number` and `format/3` do not exist in the engine.

### 1.3 Reader facts

* `PrologReader()` defaults to `OperatorTable.swi_default()`, which contradicts "never SWI".
  A downstream reader calls `read_module` with the same default.
* No shipped table has `in`, `ins`, `..`, `#<==>` and the rest; only `scryer_default` has the
  six `#` comparisons. Scryer gets them from the `op/3` entries in `library(clpz)`'s module
  export list (`clpz.pl:44-60`). Our reader applies only top-level `op/3`, so
  `X in 0..5` reads as a SyntaxIssue under every table.
* `:- dynamic d/1.` reads under `swi_default` but is a SyntaxIssue under `scryer_reader`.
  Scryer itself refuses it: `syntax_error(incomplete_reduction)`, and
  `current_op(_,_,dynamic)` fails. So the Scryer-shaped spelling is `:- dynamic(d/1).`
* The reader already produces everything L3 needs for this plan. Cells are functor-first
  tuples, atoms are `str`, strings are `('$chars', s)`, variables are `VarRef(i)` plus
  `var_names`, and there is a span tree that mirrors each cell. Refused constructs still read
  (`(a->b;c)`, `!`, `[X]>>foo(X)`), so L3 can refuse them with a `.pl` position.

### 1.4 Engine goal coverage for reader-shaped cells (`probe_cell_goals.py`)

Solved directly by name: `is` (with `max`, `rdiv` and `**`), `<`, `call/N`, `compare/3`,
`=..`, `#=`, `atom_length`, `succ`, `get/3` on a dict, and `current_prolog_flag`. The last
answers `bounded` as Python `False`, not the atom `false`.
Missing as predicates: `if_/3` and `memberd/2` (they live in `clausal.stdlib.reif` and need
an import), `{}/1` (clpq), `nth1/3`, `keysort/2`, `atom_number/2`, `aggregate_all/3` and
`format/3`. `in/2` with a `..` domain is also missing: the engine spells it
`in_domain(X, Lo, Hi)`. A unit term: `X is euro(5)+euro(1)` gives `type_error(evaluable, euro/1)`.
Control constructs as raw `query()` cells are refused
(`callable_control_construct_unsupported`), but `call/1` in a compiled body metacalls them
(`G = (X = 1, true), call(G)` gives `[1]`). A *variable* in a meta-argument
(`findall(X, G, L)`) is refused at **compile** time (`BareGoalVariableError`). ISO body
conversion (7.6.2) wraps it as `call(G)`, and L3 must do the same.

### 1.5 The seam's directive handlers are reusable as-is (`probe_directive_reuse.py`)

`EmbedTransformer(source_lines=[], filename=…)._handle_directive(name, args, stmt)` is
driven with Python-ast args synthesized from reader cells (atom → `Name`, `f/n` → `BinOp(Div)`,
list → `List`). It yields the right statements and module items for `module/2` (`$declare_head`
+ `predicate_export` items + `ModuleDeclaration`), `dynamic` (`$declare_head` + `mark_dynamic`),
`discontiguous`, `table`, `private([foo, pt(x,y)])` (atom mint + constructor declaration +
signature registry), and `set_prolog_flag`. No text round trip is involved.
Sizes, for scale: `term_rewriting.py` has 10,731 lines, `compiler_v2.py` 3,147, and
`prolog_to_clausal.py` 1,476. Reimplementing the directive semantics is the expensive
option.

---

## 2. The seam: where reader output meets the compiler

Today's `.pl` path is:

    .pl text ─prolog_to_clausal→ seam TEXT ─ast.parse→ EmbedTransformer ─→ transformed ast.Module
                                                            └→ transformer._module_items
    PrologLoader.source_to_code → code;  self._last_transformer._module_items
    _run_v2_pipeline: exec(code, module_dict)  → predicate_nodes ($define_predicate) + $declare_head record
                      compile_module(predicate_nodes, module_items, module_dict, name)

The native path keeps everything from `exec` onward unchanged:

    .pl text ─PrologReader(scryer table)→ ReaderItems ─L3→ (transformed ast.Module, module_items)
    NativePrologLoader.source_to_code → compile(ast.Module); self._last_transformer = _Items(module_items)
    NativePrologLoader._recover_module_items(path) → re-read + re-lower (cache-hit path)
    module_items[:0] = _prolog_default_items()        # assert_creates_dynamic, as today

**The join is the pair (transformed `ast.Module`, `module_items`),** exactly what
`_run_v2_pipeline` consumes today. `iso_l3` P1 already produces the first element for facts,
and it answers identically to a `.seam` twin through the real loader
(`tests/iso_l3/test_l3_p1_facts.py`, 4 pass). Inside L3 (recommended in D1):

* **Clauses: L3 emits the transformed AST itself.** That means `$declare_head`,
  `$define_predicate($Predicate(head=$head(f, arg_i=…), body=…, position=span→(line,col,…)))`,
  and body nodes drawn from a closed set: `$TupleLiteral` (`,`), `$Or` (`;`), `$Not` (`\+`),
  `$Call($LoadName(name), args)` for every other goal and compound, `(V := $Var())` at first
  occurrence, `$SetLiteral`+`$ArithEq` for a clpq `{}` goal (that is what the seam emits
  for `{X == 2*Y}`, measured), and `$DictTerm`/`$Quantity` only if D6/D7 admit literals.
  Every ISO builtin is reached **by its ISO name** through `$LoadName`, never through a seam
  sugar node. `==` must not become `$ArithEq` (the seam's `==` evaluates), `is` must not
  become `$Unify`, and `^` must not become `$BitXor`.
* **Directives: L3 calls the seam's handlers.** It builds the handler's Python-ast args
  from the cell and calls `EmbedTransformer._handle_directive`, then splices the returned
  statements into the module and takes `_module_items` from the same transformer instance.
  One implementation of directive semantics serves both front ends.
* **Module items that clause lowering must also produce**, because the seam's visitor
  produces them: `BareAtomRefs` (strict-atom check, `compiler_v2._process_bare_atom_refs`),
  functor registration for declared data (`_register_functor` /
  `__clausal_functor_signatures__`), and `DirectiveItem`s. L3 does this by **calling the same
  helper functions** (`_make_predicate_decl_ast`, `_make_atom_str_assign_ast`, …). It never
  copies them.
* **Positions.** A span `(start, end)` is a character offset in the `.pl` text, and L3 maps
  it to `(line, col, end_line, end_col)`. Errors and test diagnostics then point at `.pl`
  lines, and the runner's "a .pl file is translated before it runs" note goes away.

---

## 3. Construct inventory: reuse, gap, seam

| construct | engine already has | missing | where it meets the compiler |
|---|---|---|---|
| terms: float, var, compound, partial list, `"…"`, `{}` | cell shapes and seam node equivalents | L3 `lower_arg` cases (P1 refuses them) | `$Call($LoadName(f))` for a compound; `Constant(('$chars', s))` (the seam's own chars carrier) |
| rules, `,` `;` `\+` `true` `fail` | `$TupleLiteral`, `$Or`, `$Not`; `terms_to_goalop` | L3 body lowering; a variable goal → `call(G)` (ISO 7.6.2) | `$Predicate(body=…)` |
| `call/1..8`, `findall`, `bagof`/`setof` with `^`, `catch`/`throw`, `forall`, `once` | builtins registered under ISO names; `^` grouping (91ef2a77) | nothing, provided `^` is **kept** (the translator strips it) | `$Call($LoadName("setof"), [T, ^(V,G), L])` |
| refusals `!` `->` `*->` | reader reads them | L3 refusal naming the `.pl` span; the ISO error shape is D-free: `syntax_error`-class SyntaxError at import | raise in L3 |
| arithmetic, comparisons, `@<` family, `compare/3`, `=..` | `iso_compare.py` ISO-named builtins, flags `integer_rounding_function` | nothing; lower by name | `$Call($LoadName("is"), …)` |
| `module/2`, `use_module/1,2` | seam `-module`, `-import_from`, `-import_module` handlers | a `library(X)` map; slash path → dotted; `name/arity` import lists → the handler's arg shape | `_handle_directive("module"/"import_from", …)` |
| `dynamic`, `discontiguous`, `table`, `meta_predicate` | seam handlers (probe 1.5) | the paren form only (D2) | `_handle_directive(...)` |
| `set_prolog_flag/2` | `flags.py` (ISO 8.17, landed 2026-09-28) and its directive handler | nothing | `_handle_directive("set_prolog_flag", …)` |
| `op/3` | reader applies top-level `op/3` | ops exported from a module's export list (`library(clpz)`) | reader L1 table, before L3 |
| `initialization/1` | nothing | D12 | L3 refuses, or a module item |
| declarations directive | seam `-private([atom, ctor(f1,f2)])`, `-module` bare entries | ISO spelling (D4); per-suffix strictness (D5) | `_handle_directive("private", …)` under a new name |
| dicts | `dict_pairs/2` (both modes), `get/3,4`, `put/4`, `dict_keys/2`, `DictTerm` | the ISO surface (D6); the exporter's name `profile_get` has no engine predicate | `$Call` to the dict builtins; `$DictTerm` only under D6(b) |
| units | `Quantity`, `make_quantity/3`, `quantity_number/2`, `strip_units/2`, the units module | the ISO spelling (D7); unit atoms are not evaluable | D7 |
| constants | `-constant_value/2` family directives, program-wide `constant_value/2` | an ISO spelling for the value use (`++name` has none) (D8) | `_handle_directive("constant_value", …)` |
| clpz | `clausal.logic.clpfd` (`in_domain/3`, `label`, `#=` family) | `in/2`, `ins/2`, `..`/`\/` domains, `#<==>` etc. under Scryer names (D9); the ops (§1.3) | a builtin by name |
| clpq | seam `{…}` goal → `$SetLiteral`+`$ArithEq` | `library(clpq)` mapping | L3 maps goal `{}/1` |
| dif, reif | `dif/2` builtin; `clausal.stdlib.reif` (`if_`, `memberd`, …) | `library(reif)` → `clausal.stdlib.reif` import | the import handler |
| `test/1` discovery | the runner collects `test/1` from any loaded module, `.pl` included (file and dir modes measured) | `.pl` line numbers; the negative-test form (D14) | none: loader-agnostic |
| DCG `-->` | seam `_dcg_body_ast` | not in scope for step 2 (0 downstream sites known); refuse loudly | L3 refuses |

---

## 4. Slices

Every slice lands behind the front-end switch (D3) and keeps the translator as the `.pl`
default until slice 8. Every slice test does four things. It clears `__pycache__`. It asserts
**which front end ran**, which caught the P1 author once. It asserts L3's
read/lowered/refused counts with a **non-zero** denominator. And it includes one negative
control.

### Slice 0: make P1 fail closed (small, lands first)

* `read_iso` uses `close()`. The exit asserts `len(read_iso("f(1).\ng(2)."))==2`.
* A refused item becomes an import-time `SyntaxError` with the `.pl` line (`LoweringRefused` →
  SyntaxError in the loader), not a dropped clause. Stats remain for tooling.
* A `SyntaxIssue` from the reader becomes an import error. Today it would be counted as
  "refused (P3)".
* Remove the dead `_is_atom` branch. Fix the P1 message that claims strings are handled.
* The native loader constructs its reader with `Dialect.scryer_reader().operator_table` (D2).
* **Exit:** `probe_l3_today.py` shows 0 silent drops. A `.pl` file holding one refused clause
  fails to import and names line N. The existing 4 P1 tests still pass.

### Slice 1: terms, rules and control constructs

* `lower_arg` gains float, variable (walrus at first occurrence, matching the seam's
  `(X := $Var())`), compound (`$Call($LoadName(f))`), partial list, `"…"`
  (`('$chars', s)`), and `{}` as a term.
* Bodies: `,` `;` `\+` `true` `fail` `call/N`, plus the generic goal → `$Call($LoadName)`. A
  variable goal becomes `call(G)`, including a variable in a meta-argument position declared
  by `meta_predicate` or by the builtin's meta spec.
* Refusals: `!`, `->`, `*->`, and `;` with a `->` left branch. Each error cites the
  cut-free ruling and the `.pl` span.
* Singleton lint parity. ISO `_X` named-anonymous variables follow the seam's rule, which has
  no exceptions (constants memo).
* Head field names are `arg_i` (P1 decision 1, pinned by test; unchanged).
* The native `PrologLoader` subclass is selected by D3, with the front-end id in the bytecode
  cache key (R2).
* **Exit:** `tests/iso_l3/rulebase_s1.pl` is a hand-written rulebase of about 40 `test/1`
  cases: recursion, disjunction, negation, `call/N`, arithmetic, `==` vs `=:=`, and
  `@<`/`compare`. It passes under `python -m clausal.testing` with the native front end.
  Its hand-written `.seam` twin gives the **same all-answers sets**, compared per predicate
  in order, not just pass/fail. There are 5 Scryer-oracle cases on the ISO-vs-seam hazard
  names (`==`, `is`, `^`, `//`, `max`). Negative control: flip one lowering (`==`→`$ArithEq`)
  and the A/B goes red.

### Slice 2: directives and modules

* `module/2` (a `name/arity` export list; `op/3` entries are applied to the reader table),
  `use_module/1,2` (`library(lists|apply|dif)` → built in, `library(clpz)` →
  `clausal.logic.clpfd` + ops, `library(reif)` → `clausal.stdlib.reif`, `library(clpq)`, and a
  slash path `a/b` or `'a/b'` → dotted `a.b` (D10)), `dynamic`/`discontiguous`/`table`/
  `meta_predicate` (paren form, D2), `set_prolog_flag/2` and `op/3`. `initialization/1` is
  refused (D12). An unknown directive is an error.
* All of these go through `_handle_directive` with synthesized args (§1.5), and the module
  items are taken from that instance. The cache-hit `_recover_module_items` re-reads the file
  and re-lowers only the directives.
* **Exit:** a three-module rulebase in which a `.pl` imports a `.seam` library-style module and
  vice versa, a `.pl` imports a `.pl` via both path spellings, and `dynamic` + `assertz` work
  with `assert_creates_dynamic`. Every probe in `translator_probe/` answers correctly
  natively (`lib/x` imports resolve; `set_prolog_flag(double_quotes, codes)` raises
  `permission_error`).

### Slice 3: declarations (LANDED on feat/iso-reader-slice3-2026-09-30; rulings 2026-09-30)

"Clausal Prolog aims to be a cut-free ISO Prolog", and it is **not strict**: there is no
strict mode for `.pl`. What was built:

* **Auto-declaration.** Every atom and data functor a file uses in a data position (ISO
  7.6.2 positions, read off the reader cells, so the cache-hit path sees the same set) is
  declared through the seam's `-private` handler, at the end of the module. The effect is
  the import surface: the name is bound to its spelling, so a seam `-import_from(m, [red])`
  finds it. A data term builds with or without it (L3 lowers it to a cell); a data-only
  functor already built data natively on the base, and still does (pinned by a test).
  A data functor is declared **by name only, with no field signature**: a signature makes it
  a declared data functor, and `assertz` of its term would then be refused, where ISO 7.5.2
  and `assert_creates_dynamic` create the procedure. Left out: heads, goals (including an
  `assertz`/`retract`/`clause` target and a `call/N` closure), imported names,
  directive-declared names, constructors, engine builtins and evaluables, and any spelling
  that is not a lowercase non-keyword identifier. An atom entry in a `use_module/2` list is
  a use and is declared (it still imports nothing, D11(a)).
* **The size is one INFO line per load** on the `clausal.pl_frontend` logger
  (`file.pl: auto-declared N names (A atoms, F data functors)`); the names at DEBUG;
  `l3_stats["auto_declared"]` holds the counts. The engine had no load-time info channel;
  this is the first user of `logging` there.
* **`:- constructors([pt(x, y)]).`** is optional and only gives a data functor its field
  names: routed to `-private`'s template entry (so `signature/3` and `unbound_keys/2` answer
  `[x, y]`). An exported constructor is `pt/2` in the `module/2` list; a pre-scan (only of a
  file whose text contains `constructors(`) finds the templates first, so the export reaches
  `-module` as the template `pt(x, y)`. That is what exports a DATA functor with its fields:
  a native or seam importer gets the spelling binding and the signature. Refused, with the
  line: an atom entry, a `name/N` entry, a non-identifier or keyword field or name, a
  repeated field, the same name/arity declared twice with different fields, and a
  constructor that is also defined by clauses.
* **Not expressible:** `vary/3` takes a dict of overrides, and ISO has no dict surface until
  D6 is ruled, so field-name *update* has no ISO spelling. The seam's `P.x` is dict access
  and has no cell meaning in the seam either.
* `:- atoms([...])` is not part of the language: an unknown directive.
* **Exit (met):** `tests/iso_l3/test_l3_s3_declarations.py` (26 tests; 25 fail on
  f01790d2, the other pins that `atoms/1` stays unknown). A data functor used only as data, with no declaration, loads and builds data.
  A package facade fixture (`tests/iso_l3/s3`) has a test module importing an atom from the
  facade (`use_module(s3pkg, [class_comparison])`) and the package's exported constructor.
  It answers the same as its seam twin, per predicate, in order.

### Slice 4: meta-predicates, all-solutions, reif, dif, the transition constructs

* Pass `bagof`/`setof` `^` through unchanged. **Exit case:** the §1.2 probe gives one answer,
  `[[1,2,3]]`.
* `findall/3,4`, `forall/2`, `once/1`, `catch/3`/`throw/1`, `maplist/2..7`, `foldl/4..6`,
  `if_/3`, `memberd/2`, `dif/2`. `\+`, `once` and `forall` are accepted and **counted** by the
  transition lint (D13); they are never refused by the loader.
* The missing ISO/Scryer list builtins that downstream code calls (`nth0/nth1`, `keysort`,
  `atom_number`, `aggregate_all(count|sum|max|bag|set)`) are **engine builtin work**. The
  front end does not rewrite them. File them as separate todos and sequence them by downstream
  site counts.
* **Exit:** a rulebase exercising each construct passes natively, with seam-twin all-answers
  identical, and a lint count equal to the number of planted `\+`/`once` sites.

### Slice 5: constraint libraries

* A reader change: `use_module(library(clpz))` installs clpz's `op/3` set in the reader table.
  This is the general "ops exported by an imported module" mechanism, and it closes the
  parked `todo/reader-module-embedded-op-declarations`. The exporting module's op list is read
  from its source.
* Engine builtins under Scryer names (D9): `in/2`, `ins/2`, `..` and `\/` domains, and the
  reified `#<==>`, `#==>`, `#\/`, `#/\`, `#\`. They are thin wrappers over `clpfd` and are
  usable from the seam too, in quoted form.
* clpq: goal `{C}` → `$SetLiteral` of `$ArithEq`/comparisons, matching the seam's lowering.
* **Exit:** 15 clpz and 5 clpq cases with answers identical to Scryer. The units side channel
  inside CLP is out of scope here.

### Slice 6: dicts, units, constants (after D6-D8 are ruled)

* Dicts: the predicate forms (`dict_pairs/2`, `get/3,4`, `put/4`, `dict_keys/2`, …) and
  whatever literal D6 admits.
* Units: D7's spelling, which lowers to the same `Quantity` the seam's `5(euro)` produces
  (`$PyThunk(lambda: $Quantity(5, euro))`, measured).
* Constants: D8.
* **Exit:** for each feature, a `.pl` test module and its `.seam` twin give identical
  all-answers. Scaled-unit normalisation matches the seam (`5000 cent` stays `5000 cent`, per
  the decimal-currency memo).

### Slice 7: the test runner and diagnostics on the native path

* The runner already collects `.pl` `test/1` (measured). This slice makes failure reports
  print `.pl` goals and lines from spans, and removes the translation note.
* Add the negative-test form (D14) to the runner.
* The pytest plugin and directory mode keep the "empty scan fails" behaviour that strategy
  step 1 requires.
* **Exit:** each output shape has a golden test. A directory of `.pl` tests with zero `test/1`
  exits non-zero. A D14 negative test that finds a solution goes red.

### Slice 8: parity and cutover (the strategy's exit test)

1. **The engine-internal A/B, owned by this lane.** This needs a downstream exporter's
   **Clausal-Prolog dialect** of `clausal_to_prolog`. Today's exporter drops declarations,
   lowers dicts to `attribute/2` lists, strips units and emits `profile_get` (measured on a
   5-line file), so a round trip through it cannot be faithful (R7). With that dialect in
   place, round-trip the engine's own 150 `.clausal` test modules that carry `test(...)`
   clauses (of 329 `.clausal`/`.seam` files under `tests/`). Load each natively and require the pass set and
   the per-test all-answers to equal the seam run. Every refusal is listed with its count.
   This becomes a **permanent gate**: the divergence alarm for R1.
2. **The pilot domain, owned downstream.** This lane never reads downstream code. A pilot
   `<downstream-domain>`, exported in the Clausal-Prolog dialect and loaded natively, must pass
   its own tests. The downstream answer-set checks follow.
3. Flip the `.pl` default to native. `prolog_to_clausal` leaves the import path and stays a
   tool until nothing imports it. The downstream reader switches to the same reader table (R4).
4. The `.clausal`-reads-ISO flip is **not** in this slice (D3). It follows downstream migration.

---

## 5. Decisions for the operator

**D1. Lowering route.**
(a) Synthesize the seam's *surface* Python AST and run the whole `EmbedTransformer`. This
reuses the most, but the seam reads quote style and arrow spacing from `source_lines`
(`visit_Constant`'s quote map, `_is_arrow_adjacent`), which do not exist for `.pl` text, and
it inherits Python-surface meanings (`==` evaluates, `is` unifies).
(b) L3 emits the transformed AST for everything, directives included. This duplicates about
10k lines of directive semantics.
(c) **Hybrid: clauses are lowered natively to the transformed AST, and directives go through
the seam's handlers with synthesized args (proved in §1.5).**
**Recommend (c).** ISO meaning is explicit in one small table for bodies, and there is one
implementation of module, declaration, flag and table semantics.

**D2. Reader operator table.**
(a) Keep `swi_default` (today's default, and a downstream reader's).
(b) **`scryer_reader`**, with library-exported ops added on import.
(c) Pure `iso_default`.
**Recommend (b)** (ISO first, then Scryer). Consequence: `:- dynamic d/1.` is refused as it is
in Scryer, and `:- dynamic(d/1).` is the spelling. Flip the downstream reader at the same time.

**D3. Selecting the front end during the transition.**
(a) An env/config switch, `CLAUSAL_PL_FRONTEND=native|translator`, with the translator as
default until slice 8.
(b) A per-file opt-in directive.
(c) Flip `.pl` at once.
**Recommend (a).** The front-end id goes into the bytecode cache key. The `.clausal`
suffix's own flip to ISO syntax is a separate, later, mechanical step: every remaining
seam-syntax file is first renamed `.seam`, and no content sniffing is done.

**D4. The ISO spelling of the declarations directive.** **RULED 2026-09-30 (operator):**
`:- constructors([pt(x, y)]).` only, and it is OPTIONAL: it exists to give a data functor
FIELD NAMES, routed to the same handler that gives seam constructors their fields. An
exported constructor appears as `pt/2` in the `module/2` export list and takes its field
names from `constructors/1`. `:- atoms([...])` is NOT part of the language. (Options were
(a) reuse `private/1`, (b) `atoms/1` + `constructors/1`, (c) one `declare/1`.)

**D5. Strictness by suffix.** **RULED 2026-09-30 (operator), superseding (b)'s second
half:** Clausal Prolog (native `.pl`) is NOT strict. Every atom and data functor a file
uses is auto-declared, with the count printed (an INFO line, see Slice 3). There is no
strict mode for `.pl`.

**D6. Dict surface.**
(a) **Predicate forms only**: construct with `dict_pairs(D, [k-v, …])`, read with `get/3`,
and so on.
(b) Also a literal: `{k: v, …}` read as a dict when every element is `Atom:Value`. This
collides with clpq's `{}` in goal position, and it is a Clausal-only reading of an ISO term.
(c) A reserved constructor, `dict([k-v])`.
**Recommend (a) for slice 6**, then revisit after the pilot. The cost is verbosity at the 1263
dict-literal sites in tests (sizing §4). Also rule that the exporter's Clausal-Prolog dialect
emits the engine's names (`get/3`), not `profile_get`.

**D7. Units spelling.**
(a) **Unit atoms are evaluable inside arithmetic: `X is 5*euro`**, and a data position holds
the unevaluated term until it is evaluated.
(b) The front end folds `N*Unit` to a `Quantity` literal in every position. This matches the
seam's data-position constants, but it gives `X = A*B` a non-ISO answer.
(c) An explicit constructor, `quantity(5, euro)`, or the existing `make_quantity/3`.
**Recommend (a)**, with (c)'s predicate available. Record that a data-position `5*euro`
differs from the seam's `5(euro)` until it is evaluated, and let the A/B in slice 6 show where
that matters.

**D8. Constants.** Keep `:- constant_value(max_fine, 5000).` (and the `number_units` and
`currency` families) verbatim in ISO syntax. The value is used by the goal
`constant_value(max_fine, V)`, which is program-wide by Triska convention, because `++name`
has no ISO spelling. The alternative, a compile-time fold of a bare declared name, is
rejected: a bare name is an atom. **Recommend as stated.**

**D9. The clpz surface.** (a) **Engine builtins under Scryer's names (`in/2`, `ins/2`,
reification ops)**, or (b) front-end rewrites to `in_domain/3`. **Recommend (a).** They work
from any front end and from `query()`.

**D10. Module paths and aliasing.** A slash path (quoted or not) maps to a dotted package
path, and `./` relative paths are refused at first. Aliasing with `as` is refused, and a
downstream reader already flags it. Qualified calls use `m:G`, which needs a `:`/2 lowering to
the seam's qualified name. **Recommend as stated.** The adaptor's alias protocol then uses
`m:G`.

**D11. Bare-atom entries in `use_module/2` import lists** (`[cite, p/1]`; not ISO).
(a) Accept them with a counted warning during the transition, and have the exporter stop
emitting them.
(b) Refuse them now.
**Recommend (a).** Under D4(b) atoms are global by spelling, so the entry is a no-op
declaration. **RULED (a) 2026-09-30:** accepted, imports nothing, counted warning kept
(slice 2). Since slice 3 the entry also counts as a use of the atom, so it is auto-declared
(bound to its own spelling, as a seam facade's `-import_from` of an atom binds it). Scryer
refuses it (`syntax_error(invalid_module_declaration)`, measured), as it does a bare atom in
a `module/2` export list, which stays refused here.

**D12. `initialization/1`.** Refuse it with a clear error, or run the goal after load.
**Recommend refuse.** A rulebase has no entry point, and a load-time side effect is outside
the pure subset.

**D13. The transition constructs (`\+`, `once/1`, `forall/2`, and the `findall(_,G,[])`
backdoors) in the front end.** Accept them silently, accept them and count them, or refuse
them. **Recommend accept + count** (a lint, keyed to the `todo/cut-like-*` files). The ban
is enforced by a lint, not by the loader.

**D14. The negative-test form** (the strategy's open decision; the runner is this lane's).
(a) `test(Name, false) :- Goal.`, meaning "Goal has no solution".
(b) A separate `test_fails/1`.
(c) Keep `\+` in tests.
**Recommend (a).** It reads as the expected truth value, matches the reif `T = false`
vocabulary, and keeps negation out of the language.

---

## 6. Risks

* **R1. The two front ends diverge.** Seam and native lower the same program differently,
  and nothing notices. Mitigations: the directives share one implementation (D1c); clause
  lowering calls the seam's helper functions rather than copies; slice 8.1's round-trip A/B
  over 150 engine test modules is a permanent gate; the downstream answer-set A/B runs on
  each engine candidate. Field-name divergence (`arg_i` vs seam-derived names) is already
  pinned as unobservable within a module.
* **R2. Stale bytecode serves the wrong front end.** The `.pyc` cache is keyed per engine
  version, so a switch between translator and native within one version would serve the
  other front end's code. The P1 author was caught by exactly this. Mitigation: the
  front-end id goes into the cache key, and every test asserts which front end ran.
* **R3. Silent drops.** Measured today (§1.1): the last item is lost without a trailing
  newline, and refused clauses are skipped while the import succeeds. Slice 0 closes both.
  Every later slice prints read/lowered/refused and refuses an N of 0.
* **R4. Reader tables disagree across lanes.** The engine loader and a downstream
  reader both call `read_module` with the SWI default. Flipping only one
  makes the gates read a file differently from the engine that loads it. Mitigation: flip
  both in one coordinated change (D2), with a shared fixture.
* **R5. A seam sugar node carries a non-ISO meaning.** The seam's `==` evaluates, its `is`
  unifies, its `^` is xor, and a bare `//` is floor. Mitigation: bodies lower by ISO name
  only, and slice 1 includes Scryer-oracle cases on exactly these names (Scryer is at
  `/workspace/scryer-prolog/target/release/scryer-prolog`).
* **R6. Metacall gaps.** A variable meta-argument is refused at compile time, and `query()`
  refuses control-construct cells. ISO body conversion in L3 covers the first. Test and REPL
  harnesses must go through `call/1` for the second.
* **R7. The exit test depends on another lane.** Without the exporter's Clausal-Prolog
  dialect, round trips measure the exporter's lossy choices, not this front end. Sequence
  the downstream exporter's dialect work in parallel with slices 3-6.
* **R8. Repository boundary.** This lane cannot run the pilot domain. The pilot
  exit belongs downstream. The engine-internal A/B is this lane's proxy, and it
  cannot stand in for the pilot.
* **R9. Load cost.** The toklex reader and Pratt parser replace `ast.parse` for `.pl`. Measure
  the load time on the 150-module A/B before the slice 8 flip. The `.pyc` cache hides this
  cost only on a hit.
* **R10. The engine builtins are missing for downstream code** (`nth1`, `keysort`,
  `atom_number`, `aggregate_all`, `format/3`, …). Front-end work cannot fix this, and it will
  surface as `PredicateNotFoundError` on the pilot. Size it from the sizing instrument's call
  census before slice 8.

## 7. Out of scope

DCG (`-->`), yall lambdas, consult or a top level, streams, the `.clausal` suffix flip, units
inside CLP, `if_/3`'s purity ruling (strategy open decision), and PlDoc signatures for
downstream library surfaces.

## 8. Probe files (`implementation_plans/native-iso-reader-step2-2026-09-29/`)

Run each from the worktree root with `./venv/bin/python <file>`. Each one asserts that
`clausal.__file__` is under the worktree.

* `probe_l3_today.py`: §1.1 (each construct class through `read_iso`/`lower_items`, plus the
  real-loader facts load).
* `translator_probe/probe_translator.py` with `tpkg/`: §1.2 (the "silently wrong" row
  through the real `PrologLoader`).
* `translator_probe/probe_refused.py`: §1.2 (the refused/missing row, one construct per
  module).
* `probe_cell_goals.py`: §1.4 (which reader-shaped goal cells the engine solves by name).
* `probe_directive_reuse.py`: §1.5 (the seam directive handlers driven from reader cells).
* `testdisc/probe_testdisc.py`: `.pl` `test/1` discovery (file, directory, pytest). The
  fixtures are `*.pl.in`, so a bare `pytest` from the root never collects their planted reds.
