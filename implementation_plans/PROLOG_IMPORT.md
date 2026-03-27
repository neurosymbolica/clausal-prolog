# Prolog Import: Import `.pl` Files Directly from Clausal

## Context

Clausal has an offline Prolog-to-Clausal translator (`clausal/tools/prolog_to_clausal.py`) that converts `.pl` source text to `.clausal` source text. Currently, users must manually run the translator, save the output as a `.clausal` file, and then import that. This plan adds **direct `.pl` import** — Clausal's import hook translates, compiles, and caches Prolog files on the fly, just like `.clausal` files.

This is expected to be a primary use case for the translator. Users can drop a `.pl` file on `sys.path` and `import` it, or a `.clausal` file can use `-import_from(some_prolog_module, [Pred])` where `some_prolog_module.pl` exists.

### Why the text pipeline (not a direct AST bridge)

The translator emits **text** (`.clausal` source), not `simple_ast` nodes. Building a direct Prolog AST → `simple_ast` bridge would mean reimplementing all of `EmbedTransformer` (~2800 lines: variable allocation, walrus operators, functor class generation, DCG rewriting, EDCG, operator mapping, etc.). Instead, we pipe the translated text through the existing pipeline:

```
foo.pl → prolog_to_clausal() → .clausal text → ast.parse → EmbedTransformer → bytecode → exec → compile_module
```

This maximally reuses tested infrastructure. The extra parse step is negligible compared to compilation.

### Recursive imports work naturally

when `foo.pl` contains `:- use_module(bar)`, the translator emits `-import_module(bar)` in the `.clausal` text. `EmbedTransformer` generates `import bar` bytecode. At compile time, `_process_imports()` calls `importlib.import_module("bar")`, which hits `PrologFinder`, finds `bar.pl`, translates and compiles it. Python's `sys.modules` sentinel handles circular imports.

### Bytecode caching

`PrologLoader` extends `importlib.abc.SourceLoader` (same as `PredicateLoader`), so `.pyc` caching works automatically. On the first import, the `.pl` file is translated → parsed → transformed → compiled to bytecode → cached as `.pyc`. On subsequent imports, the `.pyc` is loaded directly, skipping translation entirely.

**Cache-hit module_items recovery:** when loading from `.pyc`, `source_to_code()` doesn't run, so `_last_transformer` is missing. The loader must re-translate the `.pl` source and re-run `EmbedTransformer` to recover `module_items`. This matches the existing pattern in `PredicateLoader` (lines 307-319 of `import_hook.py`), which re-parses `.clausal` source on cache hit. The translation step adds ~10-50ms for typical files — acceptable.

---

## Implementation Steps

### Step 1: Extract shared V2 execution logic into `_run_v2_pipeline()`

**File:** `clausal/import_hook.py`

`PredicateLoader._exec_module_v2` (lines 281-335) contains the V2 pipeline logic. Extract it into a standalone function that both `PredicateLoader` and the new `PrologLoader` can call. The only difference between the two loaders is how they recover `module_items` on cache hit.

Create a new function at module level (after `_fact_to_predicate_node`, around line 55):

```python
def _run_v2_pipeline(loader, module, module_dict, filename, recover_module_items_fn):
    """Shared V2 pipeline: exec bytecode, collect predicate_nodes, compile.

    Parameters
    ----------
    loader : SourceLoader
        The loader instance (PredicateLoader or PrologLoader).
    module : ModuleType
        The module being loaded.
    module_dict : dict
        module.__dict__.
    filename : str
        Source file path.
    recover_module_items_fn : callable(path: str) -> list
        Called on .pyc cache hit to recover module_items from source.
        For .clausal files: re-parse the .clausal source.
        For .pl files: re-translate .pl → .clausal, then parse.
    """
    from clausal.logic.compiler_v2 import compile_module

    predicate_nodes = []
    dummy_logic_module = LogicModule(module.__name__, module_dict=module_dict)
    module_dict["$module"] = dummy_logic_module
    module_dict["$define_predicate"] = (
        lambda pred, lm: predicate_nodes.append(pred)
    )
    module_dict["$assert_fact"] = (
        lambda term: predicate_nodes.append(_fact_to_predicate_node(term))
    )
    code = loader.get_code(module.__name__)

    transformer = getattr(loader, '_last_transformer', None)
    if transformer is not None:
        module_items = transformer._module_items
    else:
        module_items = recover_module_items_fn(filename)

    _preseed_py_submodules(module_items)
    exec(code, module_dict)

    logic_module = compile_module(
        predicate_nodes, module_items, module_dict, module.__name__,
    )
    module_dict["$module"] = logic_module
    module.__clausal_module__ = logic_module
```

Then update `PredicateLoader._exec_module_v2` to delegate to this function:

```python
def _exec_module_v2(self, module, module_dict, filename):
    _run_v2_pipeline(self, module, module_dict, filename,
                     self._recover_module_items)

def _recover_module_items(self, path):
    """Cache-hit path: re-parse .clausal source for module_items."""
    source = self.get_data(path).decode("utf-8")
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", message="'str' object is not callable",
            category=SyntaxWarning,
        )
        tree = ast.parse(source, filename=path)
        source_lines = source.splitlines(keepends=True)
        transformer = EmbedTransformer(source_lines=source_lines)
        transformer.visit(tree)
        return transformer._module_items
```

### Step 2: `PrologLoader` class

**File:** `clausal/import_hook.py`

Add after `PredicateLoader` (after line 336), before the `_load_module` helper:

```python
class PrologLoader(SourceLoader):
    """SourceLoader for .pl Prolog modules — translates to clausal on-the-fly.

    Pipeline: .pl source → prolog_to_clausal() → .clausal text →
              ast.parse → EmbedTransformer → bytecode (cached as .pyc)
    """

    def __init__(self, fullname, path, dialect=None):
        self._fullname = fullname
        self._path = path
        self._dialect = dialect

    def get_filename(self, fullname):
        return self._path

    def get_data(self, path):
        with open(path, "rb") as f:
            return f.read()

    def path_stats(self, path):
        st = os.stat(path)
        return {"mtime": int(st.st_mtime), "size": st.st_size}

    def set_data(self, path, data):
        try:
            dir_ = os.path.dirname(path)
            os.makedirs(dir_, exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
        except OSError:
            pass

    def _translate(self, pl_source):
        """Translate .pl source text to .clausal source text."""
        from clausal.tools.prolog_to_clausal import prolog_to_clausal
        from clausal.tools.prolog_dialect import Dialect
        dialect = self._dialect or Dialect.swi()
        return prolog_to_clausal(pl_source, dialect=dialect)

    def source_to_code(self, data, path="<string>"):
        from clausal.tools.prolog_to_clausal import PrologTranslationError
        from clausal.tools.prolog_parser import ParseError

        pl_source = data.decode("utf-8")
        try:
            clausal_source = self._translate(pl_source)
        except (ParseError, PrologTranslationError) as e:
            raise SyntaxError(
                f"Cannot import {path}: {e}",
                (path, 0, 0, ""),
            ) from e

        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore", message="'str' object is not callable",
                category=SyntaxWarning,
            )
            tree = ast.parse(clausal_source, filename=path)
            source_lines = clausal_source.splitlines(keepends=True)
            transformer = EmbedTransformer(source_lines=source_lines)
            tree = transformer.visit(tree)
            ast.fix_missing_locations(tree)
            self._last_transformer = transformer
            return compile(tree, filename=path, mode="exec")

    def exec_module(self, module):
        filename = self._path
        module.__file__ = filename
        sys.modules[module.__name__] = module
        module_dict = module.__dict__
        module_dict.update(predicate_builtins)

        if _USE_V2_PIPELINE:
            _run_v2_pipeline(self, module, module_dict, filename,
                             self._recover_module_items)
        else:
            raise NotImplementedError("PrologLoader requires V2 pipeline")

    def _recover_module_items(self, path):
        """Cache-hit path: re-translate .pl source, then parse for module_items."""
        pl_source = self.get_data(path).decode("utf-8")
        clausal_source = self._translate(pl_source)
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore", message="'str' object is not callable",
                category=SyntaxWarning,
            )
            tree = ast.parse(clausal_source, filename=path)
            source_lines = clausal_source.splitlines(keepends=True)
            transformer = EmbedTransformer(source_lines=source_lines)
            transformer.visit(tree)
            return transformer._module_items
```

**Imports to add** at the top of `import_hook.py`: None needed at module level — all Prolog-specific imports are lazy (inside methods) to avoid circular imports and startup cost when no `.pl` files are used.

### Step 3: `PrologFinder` class

**File:** `clausal/import_hook.py`

Add after `PredicateFinder` (after line 369), before `ModulesFinder`:

```python
class PrologFinder(MetaPathFinder):
    """Find .pl Prolog files and load them via PrologLoader."""

    def find_spec(self, fullname, path, target=None):
        tail = fullname.rsplit(".", 1)[-1]
        search_dirs = path if path else sys.path
        for dir_entry in search_dirs:
            candidate = os.path.join(dir_entry, tail + ".pl")
            if os.path.isfile(candidate):
                loader = PrologLoader(fullname, candidate)
                return ModuleSpec(fullname, loader, origin=candidate)
```

### Step 4: Register `PrologFinder` in `sys.meta_path`

**File:** `clausal/import_hook.py`

Update the registration line (currently line 452):

```python
# Before:
sys.meta_path[:] = [PredicateFinder(), ModulesFinder(), *sys.meta_path]

# After:
sys.meta_path[:] = [PredicateFinder(), PrologFinder(), ModulesFinder(), *sys.meta_path]
```

**Priority order:** `.clausal` files > `.pl` files > `clausal.modules.*` redirects > standard Python. `PrologFinder` goes before `ModulesFinder` so that a user's `bar.pl` is found before the `clausal.modules.bar` fallback. But `PredicateFinder` goes first, so if both `bar.clausal` and `bar.pl` exist, the `.clausal` file wins.

### Step 5: `_load_prolog_module` test helper

**File:** `clausal/import_hook.py`

Add after `_load_module` (after line 354):

```python
def _load_prolog_module(fullname, path, dialect=None):
    """Load a .pl file as a Clausal module and return it.

    Test/external helper. Each call creates a fresh loader and module.
    """
    sys.modules.pop(fullname, None)
    loader = PrologLoader(fullname, path, dialect=dialect)
    spec = ModuleSpec(fullname, loader, origin=path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[fullname] = mod
    loader.exec_module(mod)
    return mod
```

### Step 6: Relative path handling in translator

**File:** `clausal/tools/prolog_to_clausal.py`

in_ `_emit_use_module` (line 406), after extracting `lib_name`, handle non-library module references. Currently, when `use_module` takes a bare atom (not `library(X)`), `_extract_library_name` returns `None` and the directive is emitted as a comment. Fix this to handle:

- `:- use_module(bar)` → `-import_module(bar),`
- `:- use_module('./bar')` → `-import_module(bar),`

Update `_emit_use_module`:

```python
def _emit_use_module(self, body: PCompound) -> str:
    if len(body.args) == 0:
        return f"# use_module({self._emit_term(body)})"

    lib_term = body.args[0]
    lib_name = self._extract_library_name(lib_term)

    if lib_name is not None:
        # library(X) form
        clausal_mod = _LIBRARY_TO_MODULE.get(lib_name)
        if clausal_mod is None:
            clausal_mod = lib_name
    elif isinstance(lib_term, PAtom):
        # Bare atom: use_module(bar)
        clausal_mod = lib_term.name
    else:
        return f"# use_module: {self._emit_term(body)}"

    if len(body.args) >= 2:
        imports = self._emit_import_list(body.args[1])
        return f"-import_from({clausal_mod}, {imports}),"
    else:
        return f"-import_module({clausal_mod}),"
```

### Step 7: Tests

**File:** `tests/test_prolog_import.py` (new)

```python
"""Tests for direct .pl file import."""
import os, sys, textwrap
import pytest
from clausal.import_hook import _load_prolog_module

# ── Helpers ────────────────────────────────────────────────────────

def _write_pl(tmp_path, name, source):
    """write a .pl file and ensure tmp_path is on sys.path."""
    path = tmp_path / f"{name}.pl"
    path.write_text(textwrap.dedent(source))
    if str(tmp_path) not in sys.path:
        sys.path.insert(0, str(tmp_path))
    return str(path)

@pytest.fixture(autouse=True)
def cleanup_modules():
    yield
    # Remove test modules from sys.modules after each test
    for key in list(sys.modules):
        if key.startswith("test_pl_"):
            del sys.modules[key]
```

**Test cases (one class per concern):**

**TestBasicImport:**
1. write `test_pl_edge.pl` with `edge(a, b). edge(b, c).` and a `path/2` rule.
2. `_load_prolog_module("test_pl_edge", path)`
3. Query `mod.Edge` and `mod.Path` — verify correct solutions.

**TestArithmetic:**
1. write `test_pl_arith.pl` with `double(X, Y) :- Y is X * 2.`
2. Import and query — verify `double(3, Y)` yields `Y = 6`.

**TestPycacheCreation:**
1. Import `.pl` file.
2. Check `__pycache__/` directory exists and contains a `.pyc` for the `.pl` source.
3. Use `importlib.util.cache_from_source(pl_path)` to verify the `.pyc` path.

**TestPycacheCacheHit:**
1. Import `.pl` file (first time — runs `source_to_code`).
2. Clear module, re-import from cache.
3. Patch `PrologLoader.source_to_code` to assert it's NOT called on second import.

**TestPycacheInvalidation:**
1. Import `.pl` file.
2. Modify the `.pl` source (touch mtime).
3. Re-import — verify new predicates are visible.

**TestRecursiveImport:**
1. write `test_pl_base.pl` with `helper(x).`
2. write `test_pl_main.pl` with `:- use_module(test_pl_base).` and a rule calling `helper/1`.
3. Import `test_pl_main` — verify it transitively loaded `test_pl_base` and the rule works.

**TestLibraryImport:**
1. write `.pl` with `:- use_module(library(clpfd), [all_different/1]).`
2. Import and verify the predicate is available.

**TestPriority:**
1. write both `test_pl_prio.clausal` and `test_pl_prio.pl` with different facts.
2. Import `test_pl_prio` — verify the `.clausal` version wins.

**TestErrors:**
1. write `.pl` with cut (`!`) — import raises `SyntaxError` mentioning cut.
2. write `.pl` with if-then-else (`->`) — import raises `SyntaxError`.
3. write `.pl` with syntax error — import raises `SyntaxError`.

**TestDCG:**
1. write `.pl` with DCG rules (`greeting --> [hello, world].`).
2. Import and verify the DCG predicate works.

**TestDynamic:**
1. write `.pl` with `:- dynamic(color/2).`
2. Import and verify `assertz` works on the dynamic predicate.

### Step 8: Test fixtures

**Directory:** `tests/fixtures/prolog_import/` (new)

Create reusable `.pl` fixtures for larger integration tests. Can reuse content from existing `tests/fixtures/prolog_golden/*.pl` files.

- `base_module.pl` — exports `helper/2`, `double/2`
- `importing_module.pl` — `:- use_module(base_module).` with rules that call `helper`
- `clpfd_module.pl` — `:- use_module(library(clpfd), [...]).` with constraint predicates
- `dcg_module.pl` — DCG rules

---

## Files to modify

| File | Changes |
|------|---------|
| `clausal/import_hook.py` | Extract `_run_v2_pipeline()`, add `PrologLoader`, `PrologFinder`, `_load_prolog_module`; update `sys.meta_path` registration |
| `clausal/tools/prolog_to_clausal.py` | Fix `_emit_use_module()` to handle bare atom module references (non-library `use_module`) |
| `tests/test_prolog_import.py` | New — comprehensive test suite (10+ test classes) |
| `tests/fixtures/prolog_import/` | New — `.pl` fixture files |

## Key functions to reuse

- `prolog_to_clausal(source, dialect=...)` — `clausal/tools/prolog_to_clausal.py:120` — main translator
- `PrologTranslationError` — `clausal/tools/prolog_to_clausal.py:38` — for error handling
- `Dialect.swi()` — `clausal/tools/prolog_dialect.py` — default dialect
- `EmbedTransformer` — `clausal/templating/term_rewriting.py:2020` — AST transformer
- `compile_module()` — `clausal/logic/compiler_v2.py:36` — V2 compilation pipeline
- `_preseed_py_submodules()` — `clausal/import_hook.py:151` — import safety
- `_fact_to_predicate_node()` — `clausal/import_hook.py:51` — fact wrapping
- `predicate_builtins` — `clausal/import_hook.py:122` — injected builtins dict
- `_load_module()` — `clausal/import_hook.py:342` — existing `.clausal` test helper (pattern to follow)
- `PredicateLoader` — `clausal/import_hook.py:196` — model for `PrologLoader` structure

## Verification

```bash
# Run new tests
python -m pytest tests/test_prolog_import.py -v

# Ensure existing tests are unaffected
python -m pytest tests/test_pycache.py -v
python -m pytest tests/test_prolog_to_clausal.py -v
python -m pytest tests/test_module_imports.py -v
python -m pytest tests/test_import.py -v

# Full suite
python -m pytest tests/ -x -q
```
