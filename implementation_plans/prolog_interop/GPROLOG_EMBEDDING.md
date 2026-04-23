# GNU Prolog Embedding — Implementation Retrospective

Clausal's second embedded Prolog engine, after [Scryer](SCRYER_EMBEDDING.md).
GNU Prolog is accessed via a Python C extension linked directly against
`libgprolog`.

## Why GNU Prolog

GNU Prolog offers different tradeoffs than Scryer:

| | Scryer | GNU Prolog |
|---|---|---|
| Language | Rust | C |
| Compilation | Bytecode (WAM) | Native code |
| FD constraints | `library(clpz)` import | Built-in (`fd_*`) |
| Module system | ISO modules | None |
| Tabling | Yes | No |
| CLP(B) | Yes | No |
| Multiple engines | Yes | No (single global) |
| Binding | PyO3/Rust (in-process) | C extension (in-process) |

---

## Architecture

### Files

```
clausal-gprolog/
├── _gprolog_ext.c       # Python C extension — the entire native layer
├── setup.py             # Finds libgprolog, compiles + links
└── pyproject.toml       # setuptools build config

clausal/gprolog/
├── __init__.py          # Conditional import, AVAILABLE flag
├── _gprolog.py          # GnuProlog class (context manager, query API)
└── _bridge.py           # to_prolog() value serializer

clausal/tools/
├── prolog_dialect.py    # Dialect.gprolog() + BUILTIN_NAME_MAP (modified)
├── prolog_operators.py  # OperatorTable.gprolog_default() (modified)
├── clausal_to_prolog.py # GNU Prolog emission rules (modified)
└── prolog_to_clausal.py # Reverse map updated for dict schema (modified)

tests/
├── test_gprolog_raw.py       # Raw _gprolog_ext tests
└── test_gprolog_embedding.py # GnuProlog class tests
```

### Query model

GNU Prolog's C API (`Pl_Query_Call`) takes a functor atom, arity, and
`PlTerm` array — it does not accept goal strings.  To support free-form
queries with variable capture, a helper predicate is consulted at engine
init:

```prolog
'__clausal_qw__'(GoalAtom, Bindings) :-
    read_term_from_atom(GoalAtom, Goal, [variable_names(Bindings)]),
    call(Goal).
```

Each query passes `[GoalAtom, BindingsVar]` to `Pl_Query_Call`.
`read_term_from_atom/3` parses the goal and returns a `Bindings` list of
`=(VarName, Var)` pairs.  `call(Goal)` executes it.  On backtracking
(`Pl_Query_Next_Solution`), the variables inside the Bindings list are
rebound — so re-reading `args[1]` after each solution gives updated
bindings.

### Dialect support

`Dialect.gprolog()` configures:
- `module_system = "none"` — module/import directives skipped
- `clpfd_module = "fd"` — constraint predicates use `fd_*` naming
- `tabling_directive = ""` — tabling directives emit a warning comment
- `library_map = {}` — no library imports (predicates are built-in)

`BUILTIN_NAME_MAP` was refactored from 3-tuples to dict-based mapping
for extensibility:
```python
"AllDifferent": {"swi": "all_different", "scryer": "all_distinct", "gprolog": "fd_all_different"},
```

---

## Pitfalls discovered during implementation

These are things that weren't obvious from the docs and cost significant
debugging time.  **Read this section before modifying the extension.**

### 1. `--disable-regs` is mandatory for shared-library embedding

GNU Prolog normally maps WAM registers to callee-saved CPU registers
(x19-x28 on ARM64, ebx/esi/edi on x86) via GCC's `register ... asm(...)`
extension.  When loaded as a `.so` inside Python, this corrupts Python's
own use of those registers — causing immediate segfaults at seemingly
random locations.

The fix is to build GNU Prolog from source with `--disable-regs`, which
stores WAM registers in global variables instead.  This is slower (~20%)
but necessary for embedding.

**Standard `apt install gprolog` packages will NOT work.**

```bash
CFLAGS="-O2 -fPIC" ./configure --prefix=... --disable-regs --with-c-flags="-fPIC"
```

### 2. `-fPIC` is also mandatory

GNU Prolog's default build produces position-dependent `.o` and `.a`
files.  These can't be linked into a shared library (Python C extensions
are `.so` files).  Pass `-fPIC` through both `CFLAGS` and
`--with-c-flags`.

### 3. `Pl_Create_Atom` does NOT copy the string

`Pl_Create_Atom(char *name)` stores a **pointer** to `name` in the atom
table without copying it.  If the caller frees `name`, the atom's name
becomes a dangling pointer.  This manifests as garbage atom names and
bizarre Prolog exceptions.

Use `Pl_Create_Allocate_Atom(char *name)` instead — it copies the string
into the atom table.  This applies to any dynamically allocated string:
goal text, file paths from temp files, etc.

For string literals and `argv` buffers that outlive the atom, plain
`Pl_Create_Atom` is fine.

### 4. `atom_to_term/3` does not exist in GNU Prolog

Unlike SWI-Prolog, GNU Prolog does not provide `atom_to_term/3`.
Use `read_term_from_atom/3` instead:

```prolog
read_term_from_atom('foo(X, Y).', Term, [variable_names(Vars)])
```

The atom **must** end with `.` — `read_term_from_atom` is a wrapper
around `read_term` which requires a period to terminate the term.

### 5. `Pl_Start_Prolog` return value is NOT a boolean

`Pl_Start_Prolog(argc, argv)` returns the **number of user directives
executed**, not a success/failure flag.  A return of 0 means success with
no user directives.  Treating 0 as failure was a bug in the initial
implementation.

### 6. `consult/1` requires `pl2wam` on PATH

GNU Prolog's `consult/1` compiles Prolog source to native code at
runtime.  It invokes the `pl2wam` compiler as a subprocess.  If
`pl2wam` isn't on `$PATH`, consult fails with a Prolog exception.

This means `$PATH` must include GNU Prolog's `bin/` directory at
runtime, not just at build time.

### 7. The standalone `.o` files are NOT duplicates of archive contents

GNU Prolog's `lib/` directory contains both static archives (`.a`) and
standalone object files (`.o`) with the same names:

```
lib/
├── libengine_pl.a     ← C implementations
├── libbips_pl.a       ← C implementations
├── all_pl_bips.o      ← Prolog-compiled predicate registrations
├── all_fd_bips.o      ← Prolog-compiled FD registrations
├── debugger.o         ← Prolog-compiled debugger
├── top_level.o        ← Prolog-compiled top-level
└── top_level_main.o   ← contains main() — DO NOT LINK
```

The archives contain C code (e.g. `Pl_Unlink_1` — the C implementation
of `unlink/1`).  The standalone `.o` files contain Prolog-compiled
initialization routines that **register** those C functions in the
Prolog predicate dispatch table.

If you link only the archives without the standalone `.o` files,
built-in predicates like `unlink/1`, `consult/1`, etc. won't be found
at runtime — they exist as C symbols but aren't registered in the
Prolog engine.

`top_level_main.o` contains its own `main()` and must **not** be linked
into a shared library.

### 8. Why not PyO3/Rust?

The initial attempt used a Rust PyO3 crate wrapping GNU Prolog's C API
via `extern "C"`.  This failed due to:

- **Archive extraction name collisions:** Multiple `.a` files contained
  `.o` files with the same names but different contents.  `ar x` into a
  single directory caused overwrites.
- **Link ordering:** `--whole-archive` was needed but still missed the
  standalone `.o` registration files.
- **Debugging difficulty:** Errors in FFI declarations (wrong return
  types, wrong constants) were harder to diagnose through the
  Rust/PyO3/maturin stack.

Since GNU Prolog is C, a direct Python C extension eliminates all of
this.  The C compiler links against the same objects the same way `gplc`
does.

---

## Term type constants (from gprolog.h)

The numbering is non-sequential and doesn't match what you'd guess:

| Constant | Value | Meaning |
|----------|-------|---------|
| `PL_REF` | 0 | Unbound variable |
| `PL_LST` | 1 | Non-empty list |
| `PL_STC` | 2 | Compound/structure |
| `PL_ATM` | 3 | Atom |
| `PL_FLT` | 4 | Float |
| `PL_FDV` | 5 | FD variable |
| `PL_INT` | 7 | Integer |

Note: there is no value 6.

### `Pl_Query_Call` / `Pl_Query_Next_Solution` return values

| Constant | Value | Meaning |
|----------|-------|---------|
| `PL_FAILURE` | 0 | Goal failed |
| `PL_SUCCESS` | 1 | Goal succeeded |
| `PL_EXCEPTION` | 2 | Prolog exception thrown |

Use `Pl_Get_Exception()` and `Pl_Write_To_String()` to get the
exception text when `PL_EXCEPTION` is returned.

### Key API signatures (from gprolog.h 1.5.0)

```c
int          Pl_Start_Prolog(int argc, char *argv[]);  // returns nb user directives
void         Pl_Stop_Prolog(void);

int          Pl_Type_Of_Term(PlTerm term);
PlLong       Pl_Rd_Integer(PlTerm term);
double       Pl_Rd_Float(PlTerm term);
int          Pl_Rd_Atom(PlTerm term);                  // returns atom id
PlTerm      *Pl_Rd_List(PlTerm term);                  // returns &[car, cdr]
PlTerm      *Pl_Rd_Compound(PlTerm term, int *func, int *arity);  // returns args (0-based)

char        *Pl_Atom_Name(int atom);
int          Pl_Create_Atom(char *name);               // stores pointer — does NOT copy
int          Pl_Create_Allocate_Atom(char *name);      // copies string into atom table

PlTerm       Pl_Mk_Variable(void);                     // returns PlTerm, not void
PlTerm       Pl_Mk_Atom(int atom);                     // returns PlTerm, not void
PlTerm       Pl_Mk_Integer(PlLong n);
PlTerm       Pl_Mk_Float(double f);

void         Pl_Query_Begin(int recoverable);
int          Pl_Query_Call(int func, int arity, PlTerm *args);
int          Pl_Query_Next_Solution(void);
void         Pl_Query_End(int op);                     // PL_RECOVER=0 or PL_CUT=1

PlTerm       Pl_Get_Exception(void);
char        *Pl_Write_To_String(PlTerm term);
```

`PlTerm` is `intptr_t`.  `PlLong` is `intptr_t`.

---

## Build requirements

- C compiler (gcc or clang)
- GNU Prolog 1.5.0+ compiled from source with `--disable-regs` and
  `CFLAGS="-fPIC"`
- `GPROLOG_HOME` env var pointing to the versioned install directory
  (e.g. `/opt/gprolog-embed/gprolog-1.5.0`)
- `pl2wam` on `$PATH` at runtime

## Testing

- `tests/test_gprolog_raw.py` — raw `_gprolog_ext` extension tests
  (session-scoped fixture; engine is never closed)
- `tests/test_gprolog_embedding.py` — `GnuProlog` class tests
  (session-scoped fixture; requires `clausal.terms` for compound tests)

All tests use unique predicate names (suffixed `_raw`, `_e`, `_r`,
`_fd1`, etc.) to avoid collisions in GNU Prolog's single global
namespace.

Tests are skipped if the extension is not built (`AVAILABLE == False`).
