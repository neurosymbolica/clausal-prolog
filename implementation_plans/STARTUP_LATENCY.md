# Startup Latency Reduction Plan

## Current state

`import clausal` takes ~70 ms on a warm filesystem. Three hot spots account
for almost all of it:

| Module | Self-time | Cumulative | What it does |
|--------|-----------|------------|--------------|
| `clausal.pythonic_ast.nodes` | **35 ms** | 37 ms | 74 `@node_class` decorators each call `compile()` 3 times (222 total) |
| `clausal.logic.builtins` | 6 ms | 14 ms | `_build_all_builtin_classes()` creates 171+ `PredicateMeta` classes via `exec()` |
| `clausal.import_hook` | 1 ms self | 7 ms | Eagerly imported from `__init__.py:18`; pulls in `nodes`, `term_rewriting`, `compiler` |

The remaining ~15 ms is unavoidable Python import overhead (`typing`,
`dataclasses`, `inspect`, `re`, `pathlib`, etc.).

Measured with:
```bash
python -X importtime -c "import clausal" 2>&1 | sort -t'|' -k2 -rn | head -20
```

## Goal

Bring `import clausal` below 25 ms. The three changes below are independent
of each other and can be implemented in any order.

## Non-goals

This plan does NOT overlap with `implementation_plans/BENCHMARKING.md` (W1–W7),
which targets runtime query-solving performance. Everything here is purely
about reducing import-time overhead before any user code runs.

---

## Change 1 — Replace `_compile_function` with plain closures in `node_class.py`

**Saving: ~35 ms** (the single largest win)

### Problem

`clausal/pythonic_ast/node_class.py` defines the `@node_class` decorator,
which is applied to 74 AST node classes in `clausal/pythonic_ast/nodes.py`.

For each decorated class, the decorator generates three methods by building
Python AST trees and calling `compile()` + `types.FunctionType()`:

1. `visit_children(self, visit)` — calls `visit()` on each child node field
2. `transform_children(self, transform)` — returns a copy with transformed children
3. `__call__(self, **kwargs)` — returns a copy with selectively replaced fields

That is 74 × 3 = 222 `compile()` invocations at import time.

The compiled methods are marginally faster at call-time because field names
become `LOAD_ATTR` opcodes instead of `getattr()` string lookups — but these
methods are **only used during `.clausal` file parsing** (AST transformation),
not in the logic solver hot path. The 222 `compile()` calls dominate startup.

### Architecture context

The `@node_class` decorator (in `node_class.py`) does the following:

1. Applies `@dataclass` to the class
2. Classifies each dataclass field via `_field_kind(f)` as one of:
   `"node"`, `"optional_node"`, `"node_list"`, or `"plain"` (scalar)
3. Builds an AST tree for each of the three methods, compiles it via
   `_compile_function()`, and assigns to the class

The `_compile_function()` helper (lines 81–100) wraps `compile()` +
`types.FunctionType()`:

```python
def _compile_function(func_def, filename, lineno, func_globals=None, kwdefaults=None):
    module = ast.Module(body=[func_def], type_ignores=[])
    ast.fix_missing_locations(module)
    module_code = compile(module, filename, "exec")
    func_code = next(
        c for c in module_code.co_consts if isinstance(c, _types.CodeType)
        if isinstance(c, _types.CodeType) and c.co_name == func_def.name
    )
    func_code = func_code.replace(co_firstlineno=lineno)
    func = _types.FunctionType(func_code, func_globals or {})
    if kwdefaults is not None:
        func.__kwdefaults__ = kwdefaults
    return func
```

The base `Node` class (in `nodes.py`, line 114) provides default no-op
implementations of `visit_children` and `transform_children`, so node classes
with no child fields don't need overrides.

The `transform_children` methods call `self.transform_fields(**kwargs)` which
is defined on `Node` (line 135) and uses `dataclasses.replace()`. There is
also a helper `_transform_node_list(nodes, transform)` imported from
`clausal/pythonic_ast/transform.py` that handles list-of-nodes fields.

### Fix

Replace the three AST-building + `_compile_function()` blocks with generic
closures that capture a per-class field spec via default arguments. The key
pattern is:

```python
_spec = [(f.name, kind) for f, kind in classified if kind != "plain"]
def method(self, arg, _spec=_spec):
    for name, kind in _spec:
        val = getattr(self, name)
        ...  # dispatch on kind
```

The `_spec=_spec` default-argument trick captures the per-class list at
definition time without a mutable-closure bug.

**`visit_children`** — replace lines 131–174 of `node_class.py`:

```python
_visit_spec = [(f.name, kind) for f, kind in classified
               if kind in ("node", "optional_node", "node_list")]

if _visit_spec:
    def visit_children(self, visit, _spec=_visit_spec):
        for name, kind in _spec:
            val = getattr(self, name)
            if kind == "node":
                visit(val)
            elif kind == "optional_node":
                if val is not None:
                    visit(val)
            else:  # node_list
                for elem in val:
                    visit(elem)
    NodeClass.visit_children = visit_children
# else: inherits Node.visit_children (no-op)
```

**`transform_children`** — replace lines 176–218:

```python
_transform_spec = [(f.name, kind) for f, kind in classified
                   if kind in ("node", "optional_node", "node_list")]

if _transform_spec:
    def transform_children(self, transform, _spec=_transform_spec,
                           _tl=_transform_node_list):
        kwargs = {}
        for name, kind in _spec:
            val = getattr(self, name)
            if kind == "node":
                kwargs[name] = transform(val)
            elif kind == "optional_node":
                kwargs[name] = transform(val) if val is not None else None
            else:  # node_list
                kwargs[name] = _tl(val, transform)
        return self.transform_fields(**kwargs)
    NodeClass.transform_children = transform_children
# else: inherits Node.transform_children (returns self)
```

**`__call__`** — replace lines 220–263:

```python
_call_fields = tuple(f.name for f in user_fields)

def __call__(self, _fields=_call_fields, _unspec=_unspecified, **kwargs):
    kw = {"position": self.position}
    for name in _fields:
        val = kwargs.pop(name, _unspec)
        kw[name] = getattr(self, name) if val is _unspec else val
    if kwargs:
        raise TypeError(f"Unexpected keyword arguments: {set(kwargs)}")
    return self.__class__(**kw)
NodeClass.__call__ = __call__
```

**Cleanup** — after these replacements, delete from `node_class.py`:

- `_compile_function` (lines 81–100)
- All the tiny AST-building helpers it uses: `_name`, `_attr`, `_self_attr`,
  `_call`, `_arg`, `_positional_args`, `_self_and_kwonly_args` (lines 47–78)
- `import sys` (line 2) — was only used for `sys._getframe(1)` to get
  filename/lineno for `_compile_function`
- `import types as _types` (line 3) — was only used by `_compile_function`
- The `frame = sys._getframe(1)` / `filename` / `lineno` block (lines 119–121)
- Keep `import ast` only if something else in the file still uses it;
  `from dataclasses import dataclass, fields` stays (used by the decorator).
  `from .transform import _transform_node_list` stays (used by
  `transform_children`).

### Correctness notes

- `visit_children` / `transform_children` are only called during AST
  transformation of `.clausal` source files. A few `getattr` calls per node
  is negligible relative to the cost of parsing and compiling a source file.
- The `__call__` replacement uses `**kwargs` + explicit `TypeError` check
  instead of the original keyword-only arguments. Semantically identical —
  callers always pass keyword arguments.
- Three classes in `nodes.py` define custom `visit_children` overrides
  (`DictLiteral` at line 344, `FormattedExpr` at line 395, `With_` at
  line 1127). The `@node_class` decorator sets `visit_children` *before*
  these manual overrides execute in the class body, so the manual ones take
  precedence. Wait — actually `@node_class` is a decorator that runs *after*
  the class body, so it would *overwrite* manual definitions. **Check this**:
  read the three manual override classes and confirm whether `@node_class`
  clobbers them or not. If it does, the existing code already has this
  "problem" (the AST-compiled version also overwrites), so the closures are
  no worse. If the manual overrides are intentionally placed *after*
  `@node_class` via some mechanism, preserve that.

### Tests

```bash
pytest tests/test_simple_ast.py tests/test_transform_nodes.py tests/test_compiler_v2.py -x -q
```

These exercise the `visit_children` and `transform_children` paths via
`EmbedTransformer`. Also run the full suite to catch any regressions:

```bash
pytest tests/ -x -q
```

---

## Change 2 — Lazy-load `import_hook` via a stub finder

**Saving: ~7 ms** (after Change 1 removes the `nodes` cost, the remaining
overhead is `term_rewriting`, `compiler`, and module-scope dict-building)

### Problem

`clausal/__init__.py` line 18:

```python
import clausal.import_hook as _import_hook  # registers .clausal finder on sys.meta_path
```

This eagerly imports `clausal.import_hook`, which at module scope (lines 36–42):
- Imports `clausal.pythonic_ast.nodes` (big cost, already fixed by Change 1)
- Imports `clausal.templating.term_rewriting` (~2 ms)
- Imports `clausal.logic.compiler` (~1 ms)
- Imports `clausal.logic.variables`, `clausal.terms`
- Builds the `_simple_ast_builtins` dict (lines 582–607)

The sole purpose of importing `import_hook` at startup is to register three
finders on `sys.meta_path` (line 577):

```python
sys.meta_path[:] = [PredicateFinder(), PrologFinder(), ModulesFinder(), *sys.meta_path]
```

These finders handle:
1. **`PredicateFinder`** — finds `.clausal` files on `sys.path`
2. **`PrologFinder`** — finds `.pl` Prolog files on `sys.path`
3. **`ModulesFinder`** — redirects bare names like `regex` and dotted
   `py.re` to `clausal.modules.regex` / `clausal.modules.py.re`

None of this is needed until someone actually imports a `.clausal`/`.pl` file
or uses a `py.*` module redirect.

### Fix

Create a new file `clausal/_lazy_hook.py` containing a single lightweight
`MetaPathFinder` subclass with **no clausal-internal imports** (stdlib only).
It sits on `sys.meta_path` and returns `None` for everything that isn't a
`.clausal`/`.pl`/`py.*` import. On first match, it does
`import clausal.import_hook` (which installs the real finders), removes
itself, and re-dispatches.

```python
"""Lightweight stub that defers the real import hook until first use."""
from importlib.abc import MetaPathFinder
import importlib.util
import os
import sys


class _LazyHookFinder(MetaPathFinder):
    """Sits on sys.meta_path; replaces itself with the real finders on first hit."""

    _installing = False

    def find_spec(self, fullname, path, target=None):
        if self._installing:
            return None

        # Condition 1: py.X redirect (e.g. "py.re" -> clausal.modules.py.re)
        if fullname.startswith("py.") and "." not in fullname[3:]:
            return self._activate_and_retry(fullname, path, target)

        # Condition 2: bare top-level name that might be in clausal.modules
        if "." not in fullname:
            qualified = f"clausal.modules.{fullname}"
            try:
                if importlib.util.find_spec(qualified) is not None:
                    return self._activate_and_retry(fullname, path, target)
            except (ModuleNotFoundError, ValueError):
                pass

        # Condition 3: .clausal or .pl file on sys.path
        tail = fullname.rsplit(".", 1)[-1]
        search_dirs = path if path else sys.path
        for d in search_dirs:
            if (os.path.isfile(os.path.join(d, tail + ".clausal"))
                    or os.path.isfile(os.path.join(d, tail + ".pl"))):
                return self._activate_and_retry(fullname, path, target)

        return None

    def _activate_and_retry(self, fullname, path, target):
        if self._installing:
            return None
        self._installing = True
        try:
            import clausal.import_hook  # noqa: F401 -- registers real finders
            # Remove ourselves from sys.meta_path
            sys.meta_path[:] = [f for f in sys.meta_path if f is not self]
        finally:
            self._installing = False
        # Re-dispatch through the now-installed real finders
        return importlib.util.find_spec(fullname)


sys.meta_path.insert(0, _LazyHookFinder())
```

In `clausal/__init__.py`, replace line 18:

```python
import clausal.import_hook as _import_hook  # registers .clausal finder on sys.meta_path
```

with:

```python
import clausal._lazy_hook as _lazy_hook  # registers lightweight stub finder
```

### Correctness notes

- The stub's `find_spec` returns `None` for anything that is not a `.clausal`
  file, `.pl` file, or `py.*`/modules redirect — so it never interferes with
  normal Python imports.
- The `_installing` flag prevents re-entrancy when `import clausal.import_hook`
  itself triggers `find_spec` calls.
- `ModulesFinder`'s own re-entrancy guard (`_resolving` set, line 518 of
  `import_hook.py`) handles the `clausal.modules.*` check correctly once
  activated.
- `_simple_ast_builtins` and `_try_auto_enable_ipython()` (defined at the
  bottom of `import_hook.py`) are only needed when a `.clausal` file is loaded
  or IPython integration is requested — both of which trigger the real hook.
- **Caution with Condition 2 (bare names)**: The stub calls
  `importlib.util.find_spec("clausal.modules.{fullname}")` on *every*
  top-level import that misses the normal finders. This is cheap (it's a
  dict lookup in `sys.modules` or a filesystem stat) but be aware it runs
  on every `import foo` that Python can't find elsewhere. If this turns out
  to cause issues, narrow it to a hardcoded set of known module names.

### Tests

```bash
pytest tests/test_import.py tests/test_clausal_modules.py tests/test_module_imports.py tests/test_prolog_import.py -x -q
```

These exercise all three finder paths (`.clausal`, `.pl`, `py.*` redirects).

---

## Change 3 — Cache `_make_init` by field tuple

**Saving: ~4–5 ms**

### Problem

`clausal/logic/predicate.py` defines `_make_init()` (lines 28–39):

```python
def _make_init(fields: tuple[str, ...]):
    """Generate an __init__ that accepts fields as keyword args with _MISSING default."""
    if not fields:
        def __init__(self):
            pass
        return __init__
    params = ", ".join(f"{f}=_MISSING" for f in fields)
    assigns = "\n    ".join(f"self.{f} = {f}" for f in fields)
    code = f"def __init__(self, {params}):\n    {assigns}"
    globs = {"_MISSING": _MISSING}
    exec(code, globs)  # noqa: S102
    return globs["__init__"]
```

This is called from `PredicateMeta.__new__` (line 114 of the same file) every
time a predicate class is created. At startup,
`_build_all_builtin_classes()` in `clausal/logic/builtins/_registry.py`
(line 372) creates 171+ predicate classes, calling `_make_init()` for each.

Most builtins share common field tuples — dozens of unary predicates have
`("arg0",)`, dozens of binary have `("arg0", "arg1")`, etc. The generated
`__init__` only references `self` and field names — it is completely
independent of the class — so identical field tuples can safely share the
same function object.

### Fix

Add a cache dict at module scope in `predicate.py`, keyed by the fields tuple:

```python
_init_cache: dict[tuple[str, ...], Callable] = {}


def _make_init(fields: tuple[str, ...]):
    cached = _init_cache.get(fields)
    if cached is not None:
        return cached
    if not fields:
        def __init__(self):
            pass
        _init_cache[fields] = __init__
        return __init__
    params = ", ".join(f"{f}=_MISSING" for f in fields)
    assigns = "\n    ".join(f"self.{f} = {f}" for f in fields)
    code = f"def __init__(self, {params}):\n    {assigns}"
    globs = {"_MISSING": _MISSING}
    exec(code, globs)  # noqa: S102
    fn = globs["__init__"]
    _init_cache[fields] = fn
    return fn
```

This reduces ~171 `exec()` calls to ~20–30 (one per unique field tuple).

### Correctness notes

The cached `__init__` only does `self.field = field` assignments. These
hit `__slots__` descriptors on the actual class (set independently per class
in `PredicateMeta.__new__` at line 108), not on the class that originally
generated the function. Two classes with identical field tuples safely share
the same `__init__`. Each class still gets its own independent `_clauses`,
`_dispatch_fn`, etc. via `PredicateMeta.__init__` (line 127).

### Tests

```bash
pytest tests/test_meta.py tests/test_predicate_meta.py tests/test_builtin_classes.py -x -q
```

Verify that two independent `make_predicate("foo", ["x"])` calls produce
distinct classes with separate `_clauses` lists.

---

## Expected result

| Change | Before | After | Saving |
|--------|--------|-------|--------|
| 1. Generic closures in `node_class.py` | 35 ms | <1 ms | ~35 ms |
| 2. Lazy `import_hook` | 7 ms | 0 ms (deferred) | ~7 ms |
| 3. Cache `_make_init` | 5 ms | <1 ms | ~4 ms |
| **Total** | **~70 ms** | **~24 ms** | **~46 ms** |

Note: Changes 1 and 2 overlap — the `nodes` import is the biggest chunk of
both. With Change 1 alone, `nodes` drops from 35 ms to <1 ms, so Change 2's
incremental saving is the *remaining* `import_hook` overhead (~7 ms for
`term_rewriting`, `compiler`, dict-building). If both are applied, the savings
compound rather than double-count.

## Verification

After all changes, measure with:

```bash
python -c "
import time
t0 = time.perf_counter()
import clausal
t1 = time.perf_counter()
print(f'import clausal: {(t1-t0)*1000:.1f}ms')
"
```

And confirm correctness with:

```bash
pytest tests/ -x -q
```
