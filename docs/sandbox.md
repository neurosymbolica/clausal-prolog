# Sandbox mode

A Clausal process can be put in **sandbox mode**: from then on, nothing a
program loads and no goal it is asked to solve can reach Python, except
through a fixed set of pure engine adapters (date arithmetic, units,
currency, regular expressions, hashing, ...).

It is meant for a worker that runs goals built from **untrusted data**: an
LLM emits validated JSON, the worker turns it into terms and asks
whitelisted predicates of a rulebase. The rule behind it: *Python reaches
Clausal Prolog only through whitelisted `.seam` modules*. The worker's own
Python is trusted. What it loads, and the goals it builds, are not.

```python
import clausal.sandbox
clausal.sandbox.enable()               # first, before loading anything

import my_rulebase                     # a .clausal file: checked at load
from clausal import solve, Var

X = Var()
goal = ("eligible", "bob", X)          # built from JSON: atoms, numbers, cells
for _ in solve(goal, module=my_rulebase):
    print(X.value)
```

Or set `CLAUSAL_SANDBOX=1` in the environment. The variable is read once,
when `clausal` is first imported, and the sandbox is on before anything of
yours can load.

## The threat model

**Trusted:** the worker's own Python code, the engine, and the Python
bridges the worker names (below).

**Untrusted:**

- **Goals.** A goal is a term the worker built from outside data.
- **Clausal source.** Every `.clausal`, `.seam` or `.pl` module the process
  loads after the sandbox is on, and everything those modules import.

**Goal of the sandbox:** no untrusted goal or module can run Python other
than the allowed adapters. That rules out a Python escape (`++`), a hosted
Python statement, an import of a Python module, an adapter with side
effects, a Python object smuggled into a goal, and a path through a `.pl`
module.

**Out of scope:**

- **Resource exhaustion.** A goal can loop, recurse deeply, or hand a
  catastrophic regular expression to `re`. Run the worker with a time limit
  and a memory limit.
- **What a rulebase computes.** A Clausal module may still `assert` into
  another Clausal module, or read its clauses. That is ordinary Clausal
  Prolog, not Python.
- **The worker's own Python.** It can do anything, including set the
  sandbox's state by hand. The sandbox does not protect a process from
  itself.

## Turning it on

```python
clausal.sandbox.enable(allow_adapters=None, allow_bridges=())
```

- **It cannot be undone.** There is no `disable`, no Prolog flag, and no
  query that turns it off. `set_prolog_flag/2` is itself refused in the
  sandbox (see [Refused builtins](#refused-builtins)).
- **It fails closed on earlier loads.** If a Clausal module of yours is
  already loaded, it was never checked, so `enable()` raises `RuntimeError`
  and names those modules. Call it first, or use the environment variable.
- **`allow_adapters`** narrows the default adapter allowlist. `None` keeps
  the default (the table below). Otherwise give an iterable of adapter
  module names, each of which must be on the current list: `py.datetime`,
  `date_time`, `units`, `clausal.library.datetime` and
  `clausal.modules.py.datetime` are all accepted spellings. A name that
  is not on the list raises `PermissionError`, so the list can only shrink.
- **`allow_bridges`** names `.seam` modules that do contain Python and may
  still load. Each entry names one **file**, fixed when `enable()`
  runs: a path, a dotted module name (resolved to its file then), or a
  table `{"module": ..., "sha256": ...}` (or `"path"`) that also pins the
  file's content. A same-named module elsewhere on `sys.path` is not the
  bridge an entry allows. The list only **narrows** the Python-bridge check a `.clausal` importer
  already gets (see [importing Prolog](importing_prolog.md)). A bridge
  loads only when it is named here **and** the `pyproject.toml` above
  the importing `.clausal` file lists it in `[tool.clausal]
  python_bridges`. A sha256 pin there is checked against the file that
  loads. Nothing is read from the working directory. A bridge imported
  any other way, by Python directly or by a `.seam` file, has no
  importer project and is refused.
- **`allow_package_adapters`** turns on [vetted package
  adapters](#vetted-package-adapters) (`["sympy"]`), and
  **`package_adapter_time_limit`** sets their per-call budget.
- **A second call may only narrow.** Calling `enable()` again can shrink
  any list, and shorten the package adapters' budget. A name outside the
  current lists, a package adapter that is not on, or a longer budget
  raises `PermissionError`.
- **Reading the state.** `clausal.sandbox.is_enabled()`,
  `allowed_adapters()` and `allowed_bridges()` report it.

## What is checked when a module loads

Every Clausal module loaded after `enable()` is checked, whatever its
suffix (`.seam`, `.clausal`, `.pl`) and whoever imports it, whether a
`.clausal` file, a `.seam` file or the worker's own `import`. The engine's
own files are exempt.

1. **The source is read once and compiled from that text.** The bytecode
   cache is not used.
2. **The final generated Python is audited.** This is the tree the import
   hook would run, checked by the same allow-list audit the Python-bridge
   gate uses (`clausal.seam_audit`).
3. **The audited tree is the one that runs.** The audit and the compiled
   code come from the same tree.
4. **A Python route refuses the module** with
   `error(permission_error(load, python_escape, File), load/1)`. The
   exception is both an `ImportError` and a `LogicException`, and its
   message names each route and its line. A Python route is any of these:
   - a `++` escape or a `--` seam;
   - a hosted Python statement, `def` or `class`;
   - a `@{}` template;
   - an f-string slot that evaluates Python;
   - an import of a Python module the engine does not ship;
   - a dotted reference that is not exactly `module.export`;
     a unit or currency is not a module export here, so `united_states.usd`
     after `-import_module(united_states)` is refused: import it by name,
     `-import_from(united_states, [usd])` or `[alias(usd, dollar)]`
     (operator ruling 2026-10-23);
   - an engine adapter outside the allowlist, or a denied predicate of an
     allowed one;
   - a name an allowed adapter binds that is neither one of its
     predicates nor one of its reviewed **term constructors** (see
     [The adapter allowlist](#the-adapter-allowlist));
   - any other engine module (only the adapters on the allowlist, their
     `library(...)` facades, the `.seam` stdlib and CLP(Z) may be
     imported).
5. **Allowed bridges load anyway.** A module named in `allow_bridges`
   and allowlisted by its `.clausal` importer's project loads, and its
   Python runs. It is trusted code.

`.pl` modules get the same audit, so a direct `use_module(py/os)` in a
`.pl` file is refused. This also closes the chain
`.clausal` → Python-free `.seam` → `.pl` → `py/os`, because the `.pl`
module is refused when it loads. Outside the sandbox that chain reaches
Python: the default Python-bridge gate does not follow a `.seam` into a
`.pl` file (see [importing Prolog](importing_prolog.md)). Both `.pl` front ends refuse a
`use_module` of a Python module that is not the engine's own **before**
importing it, so none of its code runs.

In the sandbox every `.pl` file is lowered by the **native** front end,
whatever `CLAUSAL_PL_FRONTEND` says (the legacy translator lowers float
functions to Python's `math`, which the audit would refuse).

## What is checked when a goal runs

**Data only in goals.** Every Python-side entry point (`clausal.solve`,
`clausal.call`, `clausal.once`, `clausal.query`, `clausal.query_wfs`,
`clausal.Solutions` (also awaited), `clausal.logic.seam.judged_answers`,
and the async twins in `clausal.aio`: `asolve`, `aonce`, `acall`,
`adrive`) checks the goal it is handed. The goal may hold only:

- atoms (`str`);
- numbers (`int`, `float`, `bool`, `Fraction`, `Decimal`) and the
  engine's other scalars (`bytes`, `complex`, `None`);
- strings (`('$chars', text)`);
- logic variables, checked through to what they are bound to;
- lists, tuples (cells) and dicts of the above (a plain `dict` or the
  engine's `DictTerm`), and the engine's `SetTerm` of the above;
- quantities (`clausal.Quantity`), checked to their magnitude and units.

Anything else is refused with
`error(permission_error(access, python_object, Type), Context)`. That
includes a function, a module, a class, an AST node, a module designator
inside `M:G`, an adapter object, or any other object.

**A query is a Clausal Prolog frame.** `M:G`, `call/N`, `findall/3`,
`assert`/`retract` and `clause/2` from a query refuse a `.pl` target
(`permission_error(access, prolog_module, M)`) and a Python-module target
(`permission_error(access, python_module, M)`). So does every module
frame except a `.pl` module's (ISO Prolog may call ISO Prolog) and an
allowed bridge's. The one target that is let through is an **allowed**
adapter module. A query may not run in a `.pl` module either:
`solve(G, module=a_pl_module)` is refused.

**A dotted name reads only Clausal modules.** Resolving a dotted name or
`M:G` reads attributes only of:

- a Clausal module;
- an allowed adapter module;
- the engine packages on the way to one.

It reads them from the module's namespace and never runs a module's
`__getattr__`. It never follows an underscore-led segment. Any other
qualifier is refused.

**Every Python predicate is checked twice:**

- **When it is resolved.** This covers a dotted goal (`py.os.pid(X)` as
  the atom `'clausal.modules.py.os.pid'`), a facade (`'clausal.library.
  py_os.pid'`), `M:G`, `call/N` and a goal object.
- **When it runs**, in the adapter's own dispatch. A compiled, cached or
  re-exported route cannot run an adapter outside the allowlist.

The error is `error(permission_error(access, python_module, M), Name/Arity)`.

## Refused builtins

These builtins have I/O or process-wide effects. In the sandbox each one
raises `error(permission_error(access, private_procedure, Name/Arity), _)`:

| Builtin | Why |
|---|---|
| `halt/0,1` | ends the process |
| `set_prolog_flag/2` | changes process-wide flags and later loads |
| `char_conversion/2` | changes the process-wide character conversion table (the directive is refused too) |
| `op/3` | changes the process-wide operator table |
| `global_atom/2` | writes the atom pool every module is seeded from |
| `gensym/2` | a process-wide counter |
| `current_time/1`, `statistics/2`, `time_goal/1,2` | read the clock (`time_goal/1` writes to stderr) |
| `write/1,2`, `writeln/1`, `write_text/1`, `writeln_text/1`, `writeq/1,2`, `write_canonical/1,2`, `write_term/2,3`, `print_term/1`, `portray_clause/1`, `listing/1`, `format/1,2,3`, `nl/0,1`, `tab/1,2` | write to stdout or a stream |
| `open/3,4`, `close/1,2`, `current_input/1`, `current_output/1`, `set_input/1`, `set_output/1`, `flush_output/0,1`, `at_end_of_stream/0,1`, `set_stream_position/2`, `stream_property/2`, `get_char/1,2`, `get_code/1,2`, `peek_char/1,2`, `peek_code/1,2`, `put_char/1,2`, `put_code/1,2`, `get_byte/1,2`, `peek_byte/1,2`, `put_byte/1,2`, `read/1,2`, `read_term/2,3` | the ISO stream table: file access, the standard streams |
| `z3_set_option/2`, `z3.set_option/2` | solver options include trace files |
| `z3_stats/1`, `z3.statistics/1` | process-wide solver counters |

A load-time `set_prolog_flag` directive is refused the same way, in every
front end (`:- set_prolog_flag(F, V).` in a `.pl` or `.clausal` file,
`-set_prolog_flag(F, V)` in a `.seam` file): the module does not load,
and the import raises `clausal.sandbox.SandboxLoadError` (an `ImportError`
and a `LogicException`) whose term is the refused goal's. The exceptions
are the two flags whose value belongs to the module alone,
`assert_creates_dynamic` and `double_quotes`
(`clausal.logic.builtins.flags.SANDBOX_DIRECTIVE_FLAGS`), and only while
each is still module-scoped. The CLP(Q)
port's resource caps (`clpq_max_*`) are therefore the host's: it sets them
from Python with `clausal.logic.clpq.limits.set_limit`. They bound one
call; time and memory limits on the worker remain the host's too.

An `op/3` directive still loads, with only its local effect. The
operator applies to the table its file is read with, so the file reads as
it would: `:- op(...)` in a file that is not a module, an `op(...)` a
module exports, and the ops a `use_module` brings in, `library(clpz)`'s
`#=` and the other ops included. None of them reaches the process-wide
run-time table, which outside the sandbox these directives also change:
`current_op/3` does not list them and the term writers
(`write_to_string/2` and the others) do not print with
them, in this query or any other. `current_op/3` is allowed.

Some other builtins behave differently in the sandbox:

- **The engine's own attribute keys are off limits.** These are `freeze`,
  `dif`, `fd`, the CLP(B/Q/R) keys, the units keys and the SAT, OR-Tools,
  LP and Z3 solver keys
  (`clausal.sandbox.ENGINE_ATTR_KEYS`). Their values are solver state, and
  freeze's are Python closures its hook calls. `put_attr/3`, `get_attr/3`,
  `del_attr/2` and `put_attrs/2` on one of these keys raise
  `error(permission_error(access, attribute, Key), _)`, and `get_attrs/2`
  leaves them out. A program's own keys work as usual.
- **`module_constant/3` names a module by its atom, never by the module
  object.**
- **"Unknown procedure" errors are short.** The message names no file and
  lists nothing else from the directory.

## The adapter allowlist

The default allowlist is fixed. It comes from classifying every engine
adapter module by its side effects. A module is **allowed** only if it is
pure computation:

- no filesystem, process, network or environment access;
- no reading the clock or drawing random numbers;
- no logging or other I/O;
- no database;
- no reflection into the program.

**Denied predicates** are refused even though their module is allowed.
A bare import of such a module, `:- use_module(library(datetime)).`,
brings its denied predicates in too, so it is refused at load. The
refusal names them. List only the predicates you need:
`:- use_module(library(datetime), [date_add/3]).` loads.
**Term constructors** are the plain functions an adapter offers to build
a term, not registered predicates: `date` in `clausal.modules.py.datetime`
(`D is date(2024, 2, 28)`). A sandboxed module may import only the ones
listed in the adapter's row (`clausal.sandbox.ADAPTERS`, field
`constructors`), each reviewed as pure: no clock, I/O, host time zone or
other state, and it returns data built from its own arguments. Import one
by name or alias (`-import_from(date_time, [date])`), or import its module
(`-import_module(date_time)`) and write `date_time.date(...)`. A qualified
`py.datetime.date(...)` with no import of its module is not a supported
spelling: it loads but does not resolve when it runs.

- **Only while the adapter is allowed.** `enable(allow_adapters=...)`
  without datetime refuses `date` at load. Narrowing after a load revokes
  it everywhere: the Python-bridge check decides again (its cached
  verdicts are keyed by the allowed adapters), and `date` itself refuses to
  run, with `permission_error(access, python_module, M)`, in code compiled
  before the narrowing, as a registered predicate does.
- **Bad calls are ISO errors.** A non-date (`date(2025, 2, 29)`, a year too
  big for the calendar such as `10^30`) is `domain_error(date, Term)`. A
  component of the wrong type is `type_error(integer, Term)`. The wrong
  number of components (`date(2024, 1)`) is `type_error(date, Term)`.
- **Nothing else.** Everything else the adapter module binds (its helpers,
  its own imports) stays a `non_export`, as does any attribute of the
  constructor (`date.year`). A `library(...)` facade re-exports no
  constructor.
- **The same rule at the bridge check.** A query's `M:G` or `call/N` into
  a module that uses a constructor passes the Python-bridge check by the
  same rule.
- **The function object is inert data.** A bare `F is date` binds it, but
  `call(F, ...)`, `maplist(F, ...)` and a goal that resolves to it refuse
  it as no goal.

Any adapter that is not engine-shipped is refused, including an optional
`clausal-*` package's adapter, even one spliced into
`clausal.modules.py`, unless it is a [vetted package
adapter](#vetted-package-adapters) turned on by `enable()`. A new engine adapter is refused until it gets a row
in this table (`clausal.sandbox.ADAPTERS`). A test fails while one is
missing.

| Adapter module | `library(...)` | Verdict | Denied predicates | Evidence |
|---|---|---|---|---|
| `clausal.modules.py.datetime` | `datetime` | allow | `now/1`, `now_utc/1`, `today/1`, `timestamp/2` | date/time arithmetic and formatting; `now`/`now_utc`/`today` read the clock, `timestamp/2` depends on the host time zone. Term constructor: `date` (validates through `datetime.date`, returns `date(Y, M, D)`), importable from the module, not from the facade |
| `clausal.modules.py.json` | `json` | allow | `read_file/2`, `write_file/2` | parse/generate/get are pure; the two file predicates touch the filesystem |
| `clausal.modules.py.csv` | `py_csv` | allow | `read_file`, `read_records`, `write_file` | parse/generate are pure; the file predicates touch the filesystem |
| `clausal.modules.py.re` | `re` | allow | | regular expressions over the given text |
| `clausal.modules.py.hash` | `hash` | allow | | hashlib digests |
| `clausal.modules.py.hmac` | `hmac` | allow | | HMAC with a caller-given key |
| `clausal.modules.py.pbkdf2` | `pbkdf2` | allow | | key derivation with a caller-given salt |
| `clausal.modules.py.url` | `url` | allow | | `urllib.parse` only; no network |
| `clausal.modules.py.uuid` | `py_uuid` | allow | `uuid_v1/1`, `uuid_v4/1` | v3/v5 and the converters are pure; v1 reads the clock and MAC, v4 is random |
| `clausal.modules.units` (and its shim `py.units`) | `units` | allow | | unit algebra; units register at import only |
| `clausal.modules.imperial` (and its shim `py.imperial`) | `imperial` | allow | | constant quantities |
| `clausal.modules.pure_random` | `pure_random` | allow | | every draw is a function of the `rng(Seed, N)` state term; no clock, OS entropy or global generator |
| `clausal.modules.currency` | `currency` | allow | | currency tables and money arithmetic |
| `clausal.modules.countries.*` | `countries/*` | allow | | currency constants |
| `clausal.modules.graphs` | `graphs` | allow | | graph algorithms over the given terms |
| `clausal.modules.prolog` | | allow | | no public predicates |
| `clausal.modules.py.files` | `py_files` | **deny** | | filesystem |
| `clausal.modules.py.os` | `py_os` | **deny** | | environment, working directory, pid, argv |
| `clausal.modules.py.process` | `py_process` | **deny** | | subprocess, shell, sleep |
| `clausal.modules.py.http` | `http` | **deny** | | network |
| `clausal.modules.py.tcp` | `tcp` | **deny** | | network (sockets) |
| `clausal.modules.py.sqlite` | `sqlite` | **deny** | | databases on disk, a global connection table |
| `clausal.modules.py.logging` | `logging` | **deny** | | process-wide logging, stream and file output |
| `clausal.modules.py.random` | `py_random` | **deny** | | randomness from a process-wide generator |
| `clausal.modules.py.asyncio` | `asyncio` | **deny** | | waits on the host's Python awaitables on its event loop; `sleep/1` is the clock |
| `clausal.modules.reflection` | `reflection` | **deny** | | `reified_file_item/2` reads any file |

The engine's Clausal stdlib (`library(clpz)`, `library(reif)`,
`clausal.stdlib.*`) and the CLP solvers are engine code, not adapters, and
stay available.

## Vetted package adapters

An optional package's adapter is refused in the sandbox, with one kind of
exception (operator ruling 2026-11-04, "vetted package: yes"): a **vetted
package adapter**, a row of the engine's own table
`clausal.sandbox.PACKAGE_ADAPTERS`. A project's `pyproject.toml` cannot add
one. Each row pins the package's Python files by sha256, the package's
version and the versions of the libraries it imports, and lists the
predicates a sandboxed module may import from it. One row exists:

| Name | Module | Pins | Predicates |
|---|---|---|---|
| `sympy` | `clausal.modules.py.sympy` | `clausal-sympy==0.1.0`; sha256 of `sympy.py` and `_sympy_units.py`; `sympy==1.14.0`, `mpmath==1.3.0` | `simplify`, `expand`, `factor`, `cancel`, `apart`, `together`, `collect`, `trig_simp`, `expand_trig`, `solve`, `solve_all`, `roots`, `diff`, `integrate`, `limit`, `series`, `subs`, `free_vars`, `degree`, `coeffs`, `sym_equal`, `sym_str`, `sympy_term` |

Not listed, and so refused: `sym/2`, the printers, number theory, sums
and products, and every term constructor and raw SymPy object the module
binds (`sin`, `log`, `pi`, `e`, `inf`, ...). An ISO cell such as
`log(X)` converts without them.

**Turning one on.** Off by default:

```text
clausal.sandbox.enable(allow_package_adapters=["sympy"],
                       package_adapter_time_limit=15.0)
```

or, for a child process, in its environment:
`CLAUSAL_SANDBOX=1 CLAUSAL_SANDBOX_PACKAGE_ADAPTERS=sympy`
(comma-separated names) and optionally
`CLAUSAL_SANDBOX_ADAPTER_TIME_LIMIT=<seconds>` (or `none`). Either package
variable without `CLAUSAL_SANDBOX=1`, or a name that is not vetted, is an
`ImportError` at engine import. An entry may also be
`{"name": "sympy", "importers": [path, {"path": ..., "sha256": ...}]}`:
then only those `.seam` files may import it.

**Verified at `enable()`, before anything of it is imported.** A pin that
does not hold raises `clausal.sandbox.PackageAdapterError`, whose message
starts with the reason in brackets, and the sandbox stays off:

| Reason | When |
|---|---|
| `sha256_mismatch` | a pinned file's content is not its pin (one changed byte is enough) |
| `version_mismatch` | the installed (or source-tree) version of the package, of `sympy` or of `mpmath` is not the pinned one |
| `distribution_mismatch` | the installed metadata does not describe the file on the path |
| `impostor_module` | `sys.modules` already holds the adapter, its helper, `sympy` or `mpmath` from another file |
| `not_found` | a pinned module resolves to no file, or a listed predicate is not one |

The package's own version is read from its installed distribution, which
must list the adapter file (an editable install's source tree must contain
it), or else from the `pyproject.toml` of the source tree the file lies in.
The pinned files are then executed from the very bytes that were hashed,
never from a bytecode cache.

**At load.** Only a `.seam` module may import a vetted adapter, and only
with `-import_from` of listed names; that import alone is no Python route,
so the module must still be Python-free otherwise (no `++`, no `--`, no
Python f-string slot). `-import_module(py.sympy)`, a dotted
`py.sympy.solve(...)` and any unlisted name stay routes, and the module is
refused with `permission_error(load, python_escape, File)`. A `.clausal`
or `.pl` file reaches the predicates through such a `.seam`, never
directly, and the `.seam` is never admitted as a bridge. `simplify` is also
a name the runtime binds, which an import may not shadow: import it under
another name, `-import_from(py.sympy, [alias(simplify, sym_simplify)])`.

**At run time.** Each predicate is checked when it runs, as every adapter
is: narrowing with a second `enable(allow_package_adapters=[])` revokes it
in code compiled before. A SymPy result (a `SymExpr`) passed back in through
`solve()` is a Python object and refused like any other.

**The time budget.** SymPy has no timeout, and one `solve/3` can run for
minutes. Each call of a vetted predicate runs under a wall-clock budget,
`package_adapter_time_limit` seconds in all (default 15; `None` for none),
counted only while the predicate itself runs. Running out throws the ball
`time_limit_exceeded`, the ball of
[`call_with_time_limit/2`](control.md#call_with_time_limit2), whose
mechanism it uses: an enclosing `call_with_time_limit/2` still fires at its
own time, and a timeout is never "no roots". After a timeout SymPy's caches
are emptied and mpmath's precision reset, so a later call recomputes rather
than trust state the interrupted one may have left. The budget applies only
under the sandbox. Off the main thread a budgeted call is refused with
`error(system_error(time_limit_not_main_thread), Name/Arity)`; pass
`package_adapter_time_limit=None` to run such calls unbudgeted there.

### Re-pinning a vetted package adapter

The pins bind the exact files, so any change to `sympy.py` or
`_sympy_units.py`, or a new `sympy`/`mpmath` release, makes `enable()`
refuse until the row is re-pinned. A re-pin is an engine change, and needs
the same review as the row itself:

1. Review the diff of the pinned files against the design's checks
   (`implementation_plans/sympy-package-adapter-sandbox-2026-11-04.md`): no
   `sympify`, `parse_expr` or `S()` on a value derived from a term, no raw
   Python objects exported, imports limited to `clausal.*` and `sympy`.
2. Run `python -m pytest tests/test_sandbox_package_adapters.py -s -k pins`:
   it prints the pins of the files on disk and the installed versions.
3. Copy them into the row in `clausal/sandbox.py` (`PACKAGE_ADAPTERS`), and
   the version into `version` when `packages/clausal-sympy` was bumped.
4. Add a `CHANGELOG.md` entry under "Unreleased" saying what changed and
   that it was reviewed.

## Errors at a glance

| When | Error term |
|---|---|
| A loaded module has a Python route | `error(permission_error(load, python_escape, File), load/1)` |
| A Python object in a goal | `error(permission_error(access, python_object, Type), Context)` |
| A non-allowlisted adapter, or a denied predicate, is resolved or run | `error(permission_error(access, python_module, M), Name/Arity)` |
| `M:G` (and the like) into a `.pl` module | `error(permission_error(access, prolog_module, M), Context)` |
| `M:G` (and the like) into a Python module | `error(permission_error(access, python_module, M), Context)` |
| A refused builtin | `error(permission_error(access, private_procedure, Name/Arity), Name/Arity)` |
| A loaded module's `set_prolog_flag` directive of a flag outside its module | `error(permission_error(access, private_procedure, set_prolog_flag/2), set_prolog_flag/2)`, raised as `SandboxLoadError` |
| The engine's own attribute key | `error(permission_error(access, attribute, Key), _)` |
| A dotted name or `M:G` reaching a non-module Python object | `error(permission_error(access, python_object, Type), _)` |
| `enable()` after an unchecked load | `RuntimeError` (Python) |
| `enable()` asked to widen a list | `PermissionError` (Python) |
| `enable()` with a vetted package adapter whose pin does not hold | `PackageAdapterError` (Python), `[reason]` first in its message |
| A vetted package adapter call runs out of its budget | `time_limit_exceeded` (a bare atom, as `call_with_time_limit/2` throws) |
| A budgeted call off the main thread | `error(system_error(time_limit_not_main_thread), Name/Arity)` |

Every run-time refusal can be caught with `catch/3`. None of them turns
into a silent failure.

## Running a worker

```python
# worker.py -- run with CLAUSAL_SANDBOX=1
import json, sys
import clausal
from clausal import solve, Var, LogicException, to_python
import rulebase                              # checked at load

ALLOWED = {("eligible", 2), ("deadline", 3)}  # the predicates you expose

def to_term(j):
    """JSON -> term: data only (the sandbox checks this again)."""
    if isinstance(j, dict) and "functor" in j:
        return (j["functor"], *[to_term(a) for a in j["args"]])
    if isinstance(j, dict) and "var" in j:
        return VARS.setdefault(j["var"], Var())
    if isinstance(j, list):
        return [to_term(a) for a in j]
    return j                                  # atom (str) or number

for line in sys.stdin:
    VARS = {}
    req = json.loads(line)
    goal = to_term(req["goal"])
    if (goal[0], len(goal) - 1) not in ALLOWED:
        print(json.dumps({"error": "not exposed"})); continue
    try:
        rows = [{n: to_python(v.value) for n, v in VARS.items()}
                for _ in solve(goal, module=rulebase)]
        print(json.dumps({"answers": rows}, default=str))
    except LogicException as e:
        print(json.dumps({"error": str(e)}))
```

Some practical points:

- **Expose only the predicates you mean to.** Check each goal's
  name/arity against your own list. The sandbox keeps the goal away from
  Python, but which of your predicates it may call is your decision.
- **Run the worker with time and memory limits.** The sandbox does not
  bound resources. (A vetted package adapter's per-call budget bounds
  that one call's time, not the query's.)
- **Keep the rulebase's Python in bridges.** Rulebases written for the
  sandbox should be Python-free. Python that must run belongs in a `.seam`
  bridge listed in `pyproject.toml` and named in `allow_bridges`.
