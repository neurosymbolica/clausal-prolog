# Plan: Tested Doc Snippets via pymdownx.snippets

## Context

810 `# skip` code blocks in `docs/*.md` are untested and can silently drift from the implementation. The project needs a "super-reliable" mechanism where every doc snippet is backed by a test, and readers see all necessary imports/context. The approach: source doc snippets from tested fixture files using `pymdownx.snippets` (already enabled but unused in mkdocs.yml).

## How It Works

`pymdownx.snippets` supports **named sections** in source files:
```
# --8<-- [start:section_name]
content here
# --8<-- [end:section_name]
```

Markdown includes them via:
````markdown
```clausal
--8<-- "tests/fixtures/docs/torch_examples.clausal:eq_example"
```
````

MkDocs replaces the `--8<--` line with the section content at build time. The `#` delimiters are Clausal comments, so the source file is valid Clausal and runs as a normal test.

## Implementation Steps

### Step 1: Configure pymdownx.snippets

**File:** `mkdocs.yml` (line 149)

```yaml
- pymdownx.snippets:
    base_path: ["."]
    check_paths: true
```

`check_paths: true` makes `mkdocs build --strict` fail if a referenced snippet is missing — the reliability guarantee.

### Step 2: Create doc fixture directory

Create `tests/fixtures/docs/` for doc-snippet fixture files. Convention: one file per doc page (e.g., `torch_examples.clausal` for `docs/torch.md`).

### Important: Clausal syntax in fixture files

When writing `.clausal` fixture files, note:
- **Predicate names are almost always lowercase** (e.g., `partition`, `head_tail`, `is_positive`) - this is in keeping with Prolog (and a lot of Python). There was a big refactor of TitleCase to lower_case, but many names were missed, especially in skipped doc snippets.
- **Fact clauses (no body) need a trailing comma** to avoid being parsed as Python expressions (e.g., `partition([], _, [], []),`)
- **Single-clause predicates with bodies work fine** (e.g., `is_positive(X) <- (X > 0)`) - by convention, if the body is a single name or single call, it doesn't need ().
- **`call` is lowercase** (builtin), not `Call` (which the original untested docs incorrectly used)
- This means some doc snippets will be *corrected* during migration, not just verified — which is the whole point

### Lessons from Phase 1 (builtins.md)

These pitfalls came up repeatedly and will affect all later phases:

**Variables vs names vs atoms:**
- Variables are ALLCAPS (`X`, `BAG`) or start with `_`. Everything else is a predicate/functor name.
- Names starting with uppercase but not all-caps are predicate names (`Partition`, `Test`), not variables.
- Bare lowercase names are predicate calls, not atoms. Use quoted strings for atom values: `"runtime"` not `runtime`, `"my_key"` not `my_key`.

**Boolean and goal syntax:**
- `true`/`false` as bare names cause `LoadName` errors — they are Python values, not Clausal goals. Use `True`/`False` for boolean values in comparisons (`T == True`), and real goals like `(1 == 1)` where a goal is needed.
- `not` after `<-` must be parenthesized: `Test("x") <- (not (goal))`.
- Assignment uses `X is VALUE`, not `X = VALUE` (which is invalid syntax).

**Predicates that don't match their doc names:**
- `Catch/2` does not exist as a callable predicate — it's only `catch/3` (a compiler special form). The docs list it separately but it compiles to `catch(Goal, Error, true)`.
- `atom/1` follows ISO Prolog: strings are NOT atoms. `atom("hello")` fails. Use `is_str` for string checks.
- `compound/1`: lists are not compound terms. Use negation to test callability: `(not compound(42))`.

**Operator syntax:**
- CLP(B) uses `|` for OR, `&` for AND, `~` for NOT — not `+`/`*`/`-`.
- DCG rules use `>>` not `-->`: `greeting >> (["hello"])`.

**Runtime database:**
- `assertz`/`retract` require a prior `-dynamic(Pred/arity)` directive.

**Module predicates:**
- Import paths: `log` (not `logging`), `date_time` (not `datetime`), `yaml_module` (not `yaml`).
- `SetLevel` takes string names (`"warning"`), `GetLevel` returns uppercase strings (`"WARNING"`), not numeric levels.
- `functor/3` works on atoms and lists, not arbitrary `f(1,2)` terms (the predicate must be in scope).
- `arg/3` is 1-based on lists, not 0-based.

### Lessons from Phase 2 (SciPy)

**pymdownx.snippets section names:**
- Section names **cannot start with a digit**. `1_d_transforms` silently fails to resolve; rename to `fft_1d_transforms`. Check all generated names.

**Constants modules vs predicate modules:**
- Some modules export **values**, not predicates. `scipy_constants` exports `SpeedOfLight` as a `Quantity` value, not a callable predicate. Test with `nonvar(SpeedOfLight)`, not `SpeedOfLight(C)`.

**SciPy predicate argument patterns:**
- `MakeCSR` takes CSR components `(DATA, INDICES, INDPTR, HANDLE)`, not a dense matrix.
- `RootScalar` requires method and bracket: `RootScalar(FN, "bisect", [LO, HI], R)`.
- `KMeans2` result key is `"centroid"` (singular), not `"centroids"`.
- Spline/interpolation predicates need 5+ data points for proper fitting.
- Many predicates use `ResultGet(R, KEY, VALUE)` to extract named results from dict-like result objects.

**Phase 2 was entirely Kind B (display-only blocks):**
All 189 SciPy skip blocks were display-only signatures/examples. None contained Test clauses. This meant `.txt` files + companion `.clausal` test files for everything, no Kind A `.clausal` snippet files needed.

### Lessons from Phase 3 (Language core)

**Indented code blocks inside admonitions:**
Many docs use `??? example` or `??? info` admonitions with indented code blocks. The extraction script must handle fenced blocks that start with whitespace (e.g., `    ```clausal`). The `# skip` line may be at column 0 even when the block content is indented. When replacing these blocks, preserve the original indentation in the `--8<--` reference line.

**Mixed Kind A + Kind B files:**
`coroutining.md` had both display blocks (9) and executable blocks with Test clauses (5). These go to separate files: display → `.txt`, executable → `.clausal`. Both are referenced from the same markdown file.

### Process tips (all phases)

**Extraction must handle indented fences:**
Use `stripped = line.strip()` and check `stripped.startswith('```clausal')` instead of `line.startswith(...)`. The `# skip` marker may be at column 0 even when the fence and content are indented (MkDocs admonitions). When writing the `--8<--` replacement, preserve the original indent.

**Section name rules:**
- Cannot start with a digit (pymdownx.snippets silently fails). Prefix with a category: `fft_1d_transforms`.
- Use `_ex2`, `_ex3` suffixes for multiple blocks under the same heading, not `_2`, `_3` (avoids confusion with arity).
- Derive from h3 heading first, fall back to h2.

**Companion test strategy:**
- Before writing tests from scratch, check `tests/fixtures/` for existing test files for that module. They show correct imports, predicate names, and argument patterns.
- For value-exporting modules (like `scipy_constants`), use `nonvar(Name)` not `Name(V)`.
- For predicates with `ResultGet`, check the existing tests for the correct key names — they're often surprising (`"centroid"` not `"centroids"`).

**The actual skip counts in the plan are approximate.** The ratchet test's `_count_skip_blocks()` is the source of truth. Always measure the actual count after migration rather than relying on plan arithmetic.

### Step 3: Handle the two kinds of `# skip` blocks

**Kind A — Executable code (examples, imports): ~490 blocks**

These go in `.clausal` fixture files with named sections and Test clauses:

```clausal
# --8<-- [start:torch_import]
-import_from(py.torch, [tensor, zeros, ones, shape, tensor_list])
# --8<-- [end:torch_import]

# --8<-- [start:eq_example]
test("doc: eq element-wise") <- (
    tensor([1.0, 2.0, 3.0], A),
    tensor([1.0, 0.0, 3.0], B),
    eq(A, B, C),
    tensor_list(C, [True, False, True])
)
# --8<-- [end:eq_example]
```

The markdown:
````markdown
```clausal
--8<-- "tests/fixtures/docs/torch_examples.clausal:torch_import"
```

```clausal
--8<-- "tests/fixtures/docs/torch_examples.clausal:eq_example"
```
````

Readers see the import AND the example — everything they need. The file is a valid `.clausal` file, so pytest collects and runs the Test clauses automatically via the existing `ClausalFile` collector.

**Kind B — Signature/mode blocks (e.g., `tensor(DATA, T)`): ~496 blocks**

These use mode annotations like `+Goal` that aren't valid Clausal syntax. Store them in plain `.txt` files that pymdownx.snippets can include:

```
--8<-- [start:tensor_sig]
tensor(DATA, T)
--8<-- [end:tensor_sig]
```

Pair with a companion `.clausal` test file that validates each predicate exists:

```clausal
-import_from(py.torch, [tensor, shape])

test("tensor exists") <- tensor([1.0], _)
test("shape exists") <- (tensor([1.0, 2.0], T), shape(T, [2]))
```

Signature `.txt` files: `tests/fixtures/docs/torch_sigs.txt`
Companion tests: `tests/fixtures/docs/torch_sig_tests.clausal`

### Step 4: Update conftest.py for the transition

**File:** `conftest.py`

1. **Detect snippet blocks** — blocks containing `--8<--` lines in raw markdown aren't executable (they're include directives). Mark them as "tested via fixture" instead of trying to compile:

```python
def _is_snippet_block(content: str) -> bool:
    """True if block consists of --8<-- snippet includes (+ blank lines)."""
    lines = [l.strip() for l in content.strip().split("\n") if l.strip()]
    return bool(lines) and all(l.startswith("--8<--") for l in lines)
```

In `DocMdFile.collect()`, yield a passing item for these blocks (the real tests run on the fixture files).

2. **Add a skip-count ratchet test** — prevents regression during gradual migration. A test that counts remaining `# skip` blocks and asserts the count doesn't increase:

```python
# tests/test_doc_snippet_coverage.py
MAX_ALLOWED_SKIPS = 808  # Decrease as migration proceeds
```

### Step 5: Add CI validation

Create `tests/test_doc_snippet_integrity.py`:
- Parse all `docs/*.md` for `--8<--` references
- Verify each referenced file exists and contains the named section
- Verify each referenced `.clausal` fixture file has at least one Test clause
- This catches: deleted sections, renamed files, test-less fixture files

Also add `mkdocs build --strict` to CI (catches broken snippet references via `check_paths: true`).

### Step 6: Migration phases by submodule

Each phase: read the doc to understand intent, write correct fixture code,
replace `# skip` blocks with `--8<--` references, decrease the ratchet count.

**Approach for each file:** Read the full doc first. The snippets were never
tested, so expect widespread syntax bugs. Rewrite examples to be correct
Clausal — don't assume the underlying code is broken.

**Known widespread issue: predicate case.** A previous refactor made builtin
predicate names lowercase (e.g., `call`, `append`, `reverse`), but many doc
snippets still use the old uppercase forms (e.g., `Call`, `Append`, `Reverse`).
User-defined predicates remain uppercase. The partition bug in the pilot
(`Call` → `call`, lowercase `partition` → `Partition`) is a typical example.
Expect this pattern in nearly every file — builtins should be lowercase,
user-defined predicates should be uppercase.

#### Phase 0 — Infrastructure + Pilot (DONE)
- `lists.md` (2 skips) — pilot migration, infrastructure setup

#### Phase 1 — Builtins index (233 skips) (DONE)
- `builtins.md` (233) — mostly predicate signatures

#### Phase 2 — SciPy (189 skips) (DONE)
- `scipy_spatial.md` (28)
- `scipy_signal.md` (26)
- `scipy_sparse.md` (24)
- `scipy_interpolate.md` (17)
- `scipy_special.md` (12)
- `scipy_integrate.md` (12)
- `scipy_optimize.md` (12)
- `scipy_fft.md` (11)
- `scipy_stats.md` (10)
- `scipy_constants.md` (8)
- `scipy_ndimage.md` (8)
- `scipy_linalg.md` (8)
- `scipy_cluster.md` (8)
- `scipy_differentiate.md` (5)

#### Phase 3 — Language core (81 skips) (DONE)
- `syntax.md` (25)
- `dicts_sets.md` (24)
- `coroutining.md` (14)
- `exceptions.md` (11)
- `directives.md` (7)

#### Phase 4 — Constraints (41 skips) (DONE)
- `clpq.md` (17)
- `clpr.md` (9)
- `constraints.md` (8)
- `clpb.md` (7)

#### Phase 5 — Standard library (194 skips)
- `sympy.md` (38)
- `spacy.md` (26)
- `logging.md` (20)
- `sqlite.md` (13)
- `yaml.md` (11)
- `strings_as_lists.md` (10)
- `date_time.md` (10)
- `sklearn.md` (10)
- `database_ops.md` (10)
- `z3.md` (9)
- `graphs.md` (8)
- `http.md` (7)
- `keyword_preds.md` (7)
- `tcp.md` (6)
- `crypto.md` (6)
- `uuid.md` (5)

#### Phase 6 — Builtins detail pages (16 skips)
- `control.md` (3)
- `meta_predicates.md` (3)
- `term_inspection.md` (3)
- `regex.md` (3)
- `lambdas.md` (3)
- `type_checking.md` (1)

#### Phase 7 — Advanced & internals (40 skips)
- `tutorial_parallel_clausal.md` (12)
- `term_expansion.md` (10)
- `indexing.md` (7)
- `specialization.md` (4)
- `import.md` (4)
- `metainterpreters.md` (2)
- `wfs.md` (2)
- `testing.md` (2)
- `examples.md` (2)
- `files.md` (1)
- `reified_ite.md` (1)
- `dcg.md` (1)
- `compiler.md` (1)
- `architecture.md` (1)
- `caching.md` (1)
- `python_integration.md` (1)

**Total: 808 skip blocks across 62 files, 8 phases**

## File Summary

| File | Action |
|------|--------|
| `mkdocs.yml` | Configure `pymdownx.snippets` with `base_path` and `check_paths` |
| `conftest.py` | Add `_is_snippet_block()` detection, pass snippet items |
| `tests/fixtures/docs/*.clausal` | New — doc example/import fixtures with sections + Tests |
| `tests/fixtures/docs/*.txt` | New — signature display text with sections |
| `tests/fixtures/docs/*_sig_tests.clausal` | New — predicate existence tests for signatures |
| `tests/test_doc_snippet_integrity.py` | New — CI check for snippet reference validity |
| `tests/test_doc_snippet_coverage.py` | New — skip-count ratchet test |
| `docs/*.md` | Replace `# skip` blocks with `--8<--` references (gradual) |

## Verification

1. `pytest tests/fixtures/docs/` — fixture files pass their Test clauses
2. `mkdocs build --strict` — all snippet references resolve
3. `pytest tests/test_doc_snippet_integrity.py` — all references valid, all have backing tests
4. `mkdocs serve` — visually confirm rendered docs look identical to before
5. Ratchet test tracks migration progress
