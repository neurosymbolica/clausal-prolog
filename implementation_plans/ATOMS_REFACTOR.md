# Atoms Refactor — From Strings to Identity-Based Symbols

## Background and Design Discussion

### The problem: atoms are strings

Currently, atoms in Clausal are plain Python `str` values. The `-private([red, blue])`
directive generates `red = "red"; blue = "blue"`. This has several problems:

1. **No identity guarantee.** `"red" is "red"` depends on CPython string interning —
   an implementation detail, not a contract. Code that relies on `is` for atoms is fragile.

2. **No type distinction.** `atom/1` (mapped to `IsStr/1`) cannot distinguish symbolic
   constants from string data. ISO Prolog requires this distinction.

3. **Not callable.** In Prolog, atoms are zero-arity functors: `foo` and `foo()` are
   the same thing. String atoms can't participate in the predicate machinery.

4. **No module scoping.** `"red"` is the same object (or not, depending on interning)
   regardless of which module created it. `-private` is purely a documentation hint.

### Design principles (from discussion)

1. **Atoms don't need a consistent class.** Anything with object identity can be used
   as an atom in Clausal. The defining property is identity (`is`), not membership
   in a particular type.

2. **Declared atoms are functors.** Atoms appearing in `-private` or `-module` directives
   exist in the declared logic world and should be callable zero-arity functors. This
   follows from the OWA on the Clausal side — but on the Python side, things must be
   defined before use, so declaration is the boundary.

3. **Undeclared atoms are just values.** Strings, enum members, sentinels, or any Python
   object can flow through unification as atomic data. No special class required.

4. **Module scoping comes naturally.** Zero-field PredicateMeta classes live in their
   module's namespace, so `colors.red` and `traffic.red` are different objects.

5. **`red() is red` must hold.** For zero-field PredicateMeta, calling the class should
   return the class itself. No instance allocation, no singleton caching — the class
   IS the atom value.

### Why PredicateMeta for declared atoms

Declared atoms becoming zero-field PredicateMeta classes means:

- **Identity**: classes are singletons in their module — `is` works
- **Callability**: `red()` works (returns `red` itself for zero-arity)
- **Unification**: already handled — C `do_unify` checks `t1 == t2` (pointer identity)
  at line 886 of `_variables.c` before anything else
- **Clause storage**: an atom/0 predicate can have clauses (facts), just like any other
- **Module scoping**: `colors.red is traffic.red` → `False` (different classes)
- **Repr**: `<Predicate red/0, 0 clause(s), compiled>` — clear debugging output
- **Pattern matching**: works with Python `match` statements
- **No new type**: reuses existing infrastructure; atoms and compounds are on the same
  continuum (zero fields vs N fields)

The only "baggage" is `_clauses`, `_dispatch_fn`, etc. on the class — a few pointers
per atom, negligible for declared symbols.

### How C-level unification handles this

In `clausal/logic/variables/_variables.c`, `do_unify()` (line 875) follows this path
for two non-Var values:

1. **Line 886**: `if (t1 == t2) return 1;` — pointer identity (same as Python `is`).
   For zero-field PredicateMeta where `cls() is cls`, this catches the common case.

2. **Lines 950-980**: Tuple/list structural recursion.

3. **Lines 982-1024**: `__unify__` protocol — tries `t1.__unify__(t2, trail)`, then
   `t2.__unify__(t1, trail)`. PredicateMeta instances with fields use this path.

4. **Line 1030**: `PyObject_RichCompareBool(t1, t2, Py_EQ)` — fallback `==` check.
   For two different zero-field PredicateMeta classes, `red == blue` is `False`
   (classes use identity comparison by default), so this correctly fails.

No C code changes are needed.

---

## Implementation Plan

### Phase 1: PredicateMeta `__call__` returns `cls` for zero-arity

**File:** `clausal/logic/predicate.py`

#### Current code (lines 124-147):

```python
def __call__(cls, *args: Any, **kwargs: Any) -> Any:
    """Create a term instance, filling missing fields with fresh Var()."""
    fields = cls._fields

    if args:
        for i, val in enumerate(args):
            if i < len(fields):
                kwargs[fields[i]] = val

    instance = cls.__new__(cls)
    cls.__init__(instance, **kwargs)

    # Replace _MISSING with fresh Var()
    from clausal.logic.variables import Var
    for f in fields:
        if getattr(instance, f) is _MISSING:
            object.__setattr__(instance, f, Var())

    return instance
```

#### Change:

Add an early return at the top of `__call__`:

```python
def __call__(cls, *args: Any, **kwargs: Any) -> Any:
    """Create a term instance, filling missing fields with fresh Var().

    For zero-arity predicates (atoms), returns the class itself —
    the class IS the atom value.  ``red() is red`` holds.
    """
    if not cls._fields and not args and not kwargs:
        return cls

    fields = cls._fields
    # ... rest unchanged ...
```

#### Also in `__new__` (lines 89-111):

For zero-field classes, the generated `__init__`, `__eq__`, `__repr__` instance methods
will never be called (no instances are created). But they're harmless — skip optimization
for now to keep the change minimal.

**However**, `__hash__` needs attention. Currently line 108 sets:

```python
cls.__hash__ = None  # mutable terms shouldn't be hashable
```

This disables hashing on **instances**. For zero-field classes where the class IS the
value, the class itself remains hashable via `type.__hash__` (inherited from `type`).
Verify this:

```python
class red(metaclass=PredicateMeta):
    _fields = ()

hash(red)        # Works — type.__hash__ is not affected by instance __hash__ = None
hash(red())      # After our change, red() is red, so hash(red()) == hash(red) — works
```

This is safe because `cls.__hash__ = None` sets it on the **class** (affecting instances),
but `type.__hash__` on the **metaclass** still handles `hash(cls)` itself.

#### Gotcha: `is_term_instance` guard

`is_term_instance()` at `predicate.py:236-247`:

```python
def is_term_instance(obj: Any) -> bool:
    if isinstance(obj, type):
        return False          # ← Filters out classes
    if isinstance(type(obj), PredicateMeta):
        return True
    return dataclasses.is_dataclass(obj)
```

After this change, `is_term_instance(red)` returns `False` (correct — `red` is a class,
not an instance). But callers in builtins that check `is_term_instance` for compound
term handling will skip atoms entirely — which is the desired behavior for zero-arity.

#### New helper function:

Add `is_atom` to `predicate.py` after `is_term_instance`:

```python
def is_atom(obj: Any) -> bool:
    """True if obj is a zero-arity PredicateMeta class (a declared atom)."""
    return isinstance(obj, PredicateMeta) and not obj._fields
```

Export it in `__all__` (line 277).

#### Tests (add to `tests/test_predicate_meta.py`):

The existing test file already has a zero-arity class:

```python
class atom(metaclass=PredicateMeta):  # line 21
    _fields = ()
```

And existing test `test_zero_arity` (line 89-91) creates an instance:

```python
def test_zero_arity(self):
    t = atom()
    assert isinstance(t, atom)
```

**This test will need updating** — after the change, `atom()` returns `atom` (the class),
and `isinstance(atom, atom)` is `False` (a class is not an instance of itself).
Change to:

```python
def test_zero_arity_returns_class(self):
    """Zero-arity __call__ returns the class itself — class IS the atom."""
    assert atom() is atom

def test_zero_arity_hashable(self):
    """Atoms (zero-arity classes) must be usable as dict keys and set members."""
    d = {atom: "value"}
    assert d[atom()] == "value"
    s = {atom}
    assert atom() in s
```

Also update `test_repr_zero_arity` (line 112):
```python
def test_repr_zero_arity(self):
    assert repr(atom()) == "atom()"  # OLD — creates instance
```
→
```python
def test_repr_zero_arity(self):
    # atom() is atom (the class), so repr is the class repr
    assert "atom/0" in repr(atom())
```

Also update `test_zero_arity_fields` (line 373-375):
```python
def test_zero_arity_fields(self):
    from clausal.logic.predicate import term_field_names
    assert term_field_names(atom()) == ()  # OLD — calls on instance
```
→
```python
def test_zero_arity_fields(self):
    # atom() is atom (the class); use _fields directly
    assert atom._fields == ()
    assert atom()._fields == ()  # same object
```

**New tests to add:**

```python
class red(metaclass=PredicateMeta):
    _fields = ()

class blue(metaclass=PredicateMeta):
    _fields = ()

class TestAtomIdentity:
    def test_call_returns_class(self):
        assert red() is red

    def test_different_atoms_not_identical(self):
        assert red is not blue

    def test_atom_is_hashable(self):
        assert hash(red) == hash(red())
        assert {red: 1}[red()] == 1

    def test_atom_in_set(self):
        s = {red, blue}
        assert red() in s
        assert blue() in s

    def test_unify_same_atom(self):
        from clausal.logic.variables import Var, Trail, unify
        trail = Trail()
        assert unify(red, red, trail)

    def test_unify_different_atoms_fails(self):
        from clausal.logic.variables import Var, Trail, unify
        trail = Trail()
        assert not unify(red, blue, trail)

    def test_unify_var_with_atom(self):
        from clausal.logic.variables import Var, Trail, unify, deref
        trail = Trail()
        x = Var()
        assert unify(x, red, trail)
        assert deref(x) is red

    def test_call_with_unexpected_args_still_works(self):
        """If someone passes args to a zero-arity, PredicateMeta should handle gracefully."""
        # This should raise TypeError or similar — zero-arity has no fields
        import pytest
        with pytest.raises((TypeError, IndexError)):
            red(1)

    def test_is_atom_helper(self):
        from clausal.logic.predicate import is_atom
        assert is_atom(red)
        assert is_atom(blue)
        assert not is_atom(fib)   # has fields
        assert not is_atom("str")
        assert not is_atom(42)

    def test_non_zero_arity_unchanged(self):
        """Predicates with fields still create instances as before."""
        t = fib(n=1, f=2)
        assert t is not fib
        assert isinstance(t, fib)
        assert t.n == 1
```

---

### Phase 2: `-private` and `-module` bare atoms → zero-field PredicateMeta classes

#### 2a. `-private` directive

**File:** `clausal/templating/term_rewriting.py`

**Current code** (`_handle_private_directive`, lines 2477-2490):

```python
for item in export_list.elts:
    if isinstance(item, Name):
        # Bare atom: generate ``name = "name"``
        transformer._atoms.add(item.id)
        private_info.append(item.id)
        statements.append(
            replace(
                Assign(
                    targets=[replace(Name(id=item.id, ctx=Store()), item)],
                    value=replace(Constant(value=item.id), item),
                ),
                expr_stmt,
            )
        )
```

**New code:**

```python
for item in export_list.elts:
    if isinstance(item, Name):
        # Bare atom: generate zero-arity PredicateMeta class
        transformer._atoms.add(item.id)
        private_info.append(item.id)
        if item.id not in transformer._seen_functors:
            transformer._seen_functors[item.id] = []
            statements.append(
                _make_functor_class_ast(item.id, [], expr_stmt)
            )
```

This generates (via `_make_functor_class_ast` at line 1258):

```python
try:
    red
except NameError:
    class red(metaclass=PredicateMeta):
        _fields = ()
```

**Key points:**
- `_make_functor_class_ast` (lines 1258-1283) already handles empty field lists —
  `repr(tuple([]))` produces `"()"`, so `_fields = ()` is generated correctly.
- The `try/except NameError` guard ensures idempotency if the same name appears in
  both `-module` and `-private`.
- Adding to `_seen_functors` prevents duplicate class generation if the same atom
  appears in multiple directives.
- The atom is still added to `transformer._atoms` so `TermTransformer.visit_Name`
  (line 835) recognizes it as an atom (not a logic variable) in clause bodies.

#### 2b. `-module` directive

**File:** `clausal/templating/term_rewriting.py`

**Current code** (`_handle_module_directive`, around lines 2425-2437):

```python
if isinstance(export, Name):
    # Bare atom: generate ``name = "name"``
    transformer._atoms.add(export.id)
    exports_info.append(export.id)
    statements.append(
        replace(
            Assign(
                targets=[replace(Name(id=export.id, ctx=Store()), export)],
                value=replace(Constant(value=export.id), export),
            ),
            expr_stmt,
        )
    )
```

**New code** — same pattern as `-private`:

```python
if isinstance(export, Name):
    # Bare atom: generate zero-arity PredicateMeta class
    transformer._atoms.add(export.id)
    exports_info.append(export.id)
    if export.id not in transformer._seen_functors:
        transformer._seen_functors[export.id] = []
        statements.append(
            _make_functor_class_ast(export.id, [], expr_stmt)
        )
```

#### 2c. `compiler_v2.py` `_process_declarations`

**File:** `clausal/logic/compiler_v2.py`

**Current code** (lines 333-349):

```python
def _process_declarations(module_items: list, module_dict: dict) -> None:
    """Process -module and -private declarations: create PredicateMeta classes
    and atom assignments."""
    for item in module_items:
        if isinstance(item, (ModuleDeclItem, PrivateDeclItem)):
            exports = item.exports if isinstance(item, ModuleDeclItem) else item.items
            for entry in exports:
                if isinstance(entry, str):
                    # Atom: assign string to module dict.
                    module_dict.setdefault(entry, entry)
                elif isinstance(entry, tuple):
                    functor_name, field_names = entry
                    if functor_name not in module_dict or not isinstance(
                        module_dict.get(functor_name), PredicateMeta
                    ):
                        cls = make_predicate(functor_name, field_names)
                        module_dict[functor_name] = cls
```

**Change:** The `isinstance(entry, str)` branch handles atoms that were emitted as
bare strings by the old code. After Phase 2a/2b, the EmbedTransformer now emits
PredicateMeta class definitions instead of string assignments, so this code path
should also create zero-field PredicateMeta classes as a fallback (for the case where
the module is loaded via `compiler_v2` directly without going through EmbedTransformer):

```python
if isinstance(entry, str):
    # Atom: create zero-arity PredicateMeta class.
    if entry not in module_dict or not isinstance(
        module_dict.get(entry), PredicateMeta
    ):
        cls = make_predicate(entry, [])
        module_dict[entry] = cls
```

**Gotcha:** The `module_dict.setdefault(entry, entry)` pattern means if the
EmbedTransformer already put a PredicateMeta class in `module_dict[entry]`, it
won't be overwritten. The new code's `if entry not in module_dict` guard preserves
this behavior.

#### Gotcha: `private_info` format

In `_handle_private_directive`, `private_info` accumulates items that become
`PrivateDeclItem(items=private_info)`. For bare atoms, the current code appends
the string name: `private_info.append(item.id)`. This string later reaches
`_process_declarations` in `compiler_v2.py` where `isinstance(entry, str)` handles it.

After the change, bare atoms in `private_info` are still strings (that's fine — the
string tells `_process_declarations` which atoms to set up). The important thing is
that `_process_declarations` now creates a PredicateMeta class instead of assigning
a string.

#### Tests:

**Python-side test** (new file or add to existing test):

```python
def test_private_atoms_are_predicate_meta():
    """Atoms declared in -private should be zero-field PredicateMeta classes."""
    import importlib
    mod = importlib.import_module("tests.fixtures.static_pred")
    # 'a' and 'b' are declared as -private([a, b])
    assert isinstance(mod.a, PredicateMeta)
    assert mod.a._fields == ()
    assert mod.a._arity == 0
    assert mod.a() is mod.a  # Phase 1 behavior

def test_private_atoms_have_identity():
    import importlib
    mod = importlib.import_module("tests.fixtures.static_pred")
    assert mod.a is not mod.b
    assert mod.a is mod.a
```

**Clausal-side test** — update `tests/fixtures/static_pred.clausal`:

The existing file:
```clausal
-module(static_pred, [Fact(X, Y)])
-private([a, b])

Fact(a, 1),
Fact(b, 2),

Test("fact a") <- Fact(a, 1)
Test("fact b") <- Fact(b, 2)
```

This should continue to work unchanged — `a` in `Fact(a, 1)` refers to the atom
class, and unification matches by identity (same class object on both sides).

**Critical: update `tests/conformity/iso_unification.clausal`**

Currently (lines 30-33):
```clausal
Test("atom unifies with itself") <- (
    X_ is a,
    X_ == a
)
```

After the change, `a` is a zero-field PredicateMeta class. `X_ is a` binds `X_` to the
class. `X_ == a` checks structural equality. Since `a == a` is `True` for classes
(identity), this still passes.

**Critical: `Test("purple is not a color") <- (not Color("purple"))` in map_coloring.clausal**

At line 63 of `clausal/examples/map_coloring.clausal`:
```clausal
Test("purple is not a color") <- (not Color("purple"))
```

Here `"purple"` is a string literal, not a declared atom. `Color(Red)` stores the
PredicateMeta class `Red`. Unifying `Red` with `"purple"` (a string) correctly fails
because they are different objects and `type.__eq__` returns `False`. This test
continues to pass.

**Critical: `a == a` semantics for PredicateMeta classes**

When `a` is a class, `a == a` is `True` by Python identity. But `a == b` is `False`
because class `__eq__` defaults to identity comparison. The `__eq__` that PredicateMeta
generates (`_make_eq`) is set on instances, not on the metaclass, so it doesn't
interfere with class-level `==`.

---

### Phase 3: TermTransformer atom handling — verify, no changes needed

**File:** `clausal/templating/term_rewriting.py`

**Current code** (`visit_Name`, line 834-836):

```python
# Atom: declared in -module(...) export list — keep as plain Name reference.
if identifier in transformer.atoms:
    return replace(Name(id=identifier, ctx=load), name)
```

This emits a bare `Name` reference to `red` in the generated Python AST. After Phase 2,
`red` in the module namespace is a PredicateMeta class instead of a string. The bare
name reference loads whatever is in the namespace — so this works correctly without
changes.

**Verify the following still works:**

1. **`transformer._atoms` set population**: atoms are added via `transformer._atoms.add(item.id)`
   in both `-private` and `-module` handlers. This is unchanged — atom names are still
   strings in the set, used only for name classification in the TermTransformer.

2. **DCG handling** (line 2971):
   ```python
   dcg_atoms = transformer._atoms - dcg_call_names
   term_transformer = TermTransformer(atoms=dcg_atoms, import_remap=transformer._import_remap)
   ```
   This subtraction uses set difference on strings — unaffected by the runtime
   representation change.

3. **All TermTransformer instantiation sites** (lines 2077, 2145, 2305, 2971, 3051):
   all pass `atoms=transformer._atoms` — a set of strings. No change needed.

---

### Phase 4: Update type-checking builtins

**File:** `clausal/logic/builtins/type_checks.py`

#### 4a. Add `IsAtom/1`

After `IsStr/1` (line 34), add:

```python
@_builtin("IsAtom", 1)
def _is_atom__1(x, trail, k):
    """IsAtom(X) — succeeds if X is a zero-arity PredicateMeta (a declared atom)."""
    x_val = deref(x)
    if (
        not is_var(x_val)
        and isinstance(x_val, type)
        and isinstance(x_val, PredicateMeta)
        and not x_val._fields
    ):
        yield None
```

**Import needed:** Add `PredicateMeta` to the imports at the top of the file.
Currently (lines 7-8):
```python
from clausal.logic.predicate import is_term_instance, term_field_names
```
→
```python
from clausal.logic.predicate import PredicateMeta, is_term_instance, term_field_names
```

#### 4b. `IsStr/1` — no change

`IsStr/1` (line 29-34) checks `isinstance(x_val, str)`. Since PredicateMeta classes
are not strings, this correctly excludes declared atoms. No change needed.

#### 4c. Update `IsCallable/1`

**Current code** (lines 79-88):

```python
@_builtin("IsCallable", 1)
def _callable__1(x, trail, k):
    """callable(X) — succeeds if X is an atom or compound."""
    x_val = deref(x)
    if is_var(x_val):
        return
    if isinstance(x_val, (str, Compound, KWTerm)):
        yield None
    elif is_term_instance(x_val):
        yield None
```

**Change:** Add a check for zero-arity PredicateMeta:

```python
@_builtin("IsCallable", 1)
def _callable__1(x, trail, k):
    """callable(X) — succeeds if X is an atom or compound."""
    x_val = deref(x)
    if is_var(x_val):
        return
    if isinstance(x_val, (str, Compound, KWTerm)):
        yield None
    elif is_term_instance(x_val):
        yield None
    elif isinstance(x_val, PredicateMeta) and not x_val._fields:
        yield None
```

Note: `is_term_instance` returns `False` for classes (it has an `isinstance(obj, type)`
guard), so the existing branches don't catch zero-arity atoms. The new branch handles
them explicitly.

#### 4d. Update `_check_type`

**Current code** (lines 107-139), relevant parts:

```python
elif type_name in ("atom", "string", "str"):
    return isinstance(term, str)
```
→
```python
elif type_name in ("atom", "string", "str"):
    if isinstance(term, str):
        return True
    if isinstance(term, PredicateMeta) and not term._fields:
        return True
    return False
```

And the `callable` branch (lines 121-127):
```python
elif type_name == "callable":
    return (
        isinstance(term, (str, Compound, KWTerm))
        or is_term_instance(term)
        or (isinstance(term, type) and hasattr(term, '_get_dispatch'))
        or hasattr(term, '_get_dispatch')
    )
```

The third line already catches PredicateMeta classes (they have `_get_dispatch`).
No change needed for `callable`.

#### 4e. No explicit `IsAtomic/1` builtin exists

There's no `IsAtomic/1` currently — it would need to be added if needed. For now,
skip unless ISO conformance tests require it.

#### Tests:

**Python-side** (add to conformity tests or a new test file):

```python
from clausal.logic.predicate import PredicateMeta

class red(metaclass=PredicateMeta):
    _fields = ()

class point(metaclass=PredicateMeta):
    _fields = ("x", "y")

def test_is_atom_declared_atom():
    """IsAtom succeeds for zero-arity PredicateMeta."""
    assert succeeds("IsAtom", red)

def test_is_atom_string_fails():
    """IsAtom fails for plain strings."""
    assert not succeeds("IsAtom", "hello")

def test_is_atom_compound_fails():
    """IsAtom fails for predicates with fields."""
    assert not succeeds("IsAtom", point(x=1, y=2))

def test_is_str_string():
    """IsStr still works for plain strings."""
    assert succeeds("IsStr", "hello")

def test_is_str_declared_atom_fails():
    """IsStr fails for declared atoms."""
    assert not succeeds("IsStr", red)

def test_is_callable_declared_atom():
    """IsCallable succeeds for declared atoms."""
    assert succeeds("IsCallable", red)
```

**Clausal-side** (update `tests/conformity/iso_type_checking.clausal`):

Currently (lines 21-24):
```clausal
-private([Hello, Abc])
```

After the change, these become zero-arity classes. Update type-checking tests:

```clausal
Test("declared atom: IsAtom succeeds") <- IsAtom(Hello)
Test("string: IsStr succeeds") <- IsStr("hello")
Test("declared atom: IsStr fails") <- (not IsStr(Hello))
Test("declared atom: IsCallable succeeds") <- IsCallable(Hello)
```

**Note:** The existing test `Test("atom: string succeeds") <- IsStr(Hello)` at
`iso_type_checking.clausal` will **FAIL** after this change because `Hello` is
now a PredicateMeta class, not a string. This test must be updated to reflect
the new semantics.

---

### Phase 5: Update term inspection builtins and helpers

#### 5a. `_functor_name` in `_helpers.py`

**File:** `clausal/logic/builtins/_helpers.py`

**Current code** (lines 12-24):

```python
def _functor_name(term: Any) -> str | None:
    """Return the functor name of a ground term, or None."""
    if isinstance(term, Compound):
        return term.functor if isinstance(term.functor, str) else None
    if isinstance(term, KWTerm):
        return term.functor
    if is_term_instance(term):
        return type(term).__name__
    if isinstance(term, list):
        return "[]" if len(term) == 0 else "."
    if isinstance(term, (bool, int, float, str, bytes)) or term is None:
        return repr(term) if not isinstance(term, str) else term
    return None
```

**Problem:** For a zero-arity PredicateMeta class `red`:
- `isinstance(red, Compound)` → False
- `isinstance(red, KWTerm)` → False
- `is_term_instance(red)` → **False** (it's a class, not an instance)
- `isinstance(red, (bool, int, float, str, bytes))` → False
- Falls through to `return None` ← **BUG**

**Fix:** Add a branch for zero-arity PredicateMeta before the fallback:

```python
def _functor_name(term: Any) -> str | None:
    """Return the functor name of a ground term, or None."""
    if isinstance(term, Compound):
        return term.functor if isinstance(term.functor, str) else None
    if isinstance(term, KWTerm):
        return term.functor
    if is_term_instance(term):
        return type(term).__name__
    if isinstance(term, list):
        return "[]" if len(term) == 0 else "."
    if isinstance(term, (bool, int, float, str, bytes)) or term is None:
        return repr(term) if not isinstance(term, str) else term
    # Zero-arity PredicateMeta class: the class IS the atom
    if isinstance(term, PredicateMeta) and not term._fields:
        return term.__name__
    return None
```

**Import needed:** Add `PredicateMeta` to imports (line 8):
```python
from clausal.logic.predicate import PredicateMeta, is_term_instance, term_field_names
```

#### 5b. `_arity` in `_helpers.py`

**Current code** (lines 27-39):

```python
def _arity(term: Any) -> int | None:
    """Return the arity of a ground term, or None."""
    if isinstance(term, Compound):
        return len(term.args)
    if isinstance(term, KWTerm):
        return len(term)
    if is_term_instance(term):
        return len(term_field_names(term))
    if isinstance(term, list):
        return 0 if len(term) == 0 else 2
    if isinstance(term, (bool, int, float, str, bytes)) or term is None:
        return 0
    return None
```

**Same problem:** Falls through to `None` for zero-arity PredicateMeta.

**Fix:**

```python
    # Zero-arity PredicateMeta class: arity is 0
    if isinstance(term, PredicateMeta) and not term._fields:
        return 0
    return None
```

#### 5c. `_is_ground` in `_helpers.py`

**Current code** (lines 81-96):

```python
def _is_ground(term: Any) -> bool:
    if isinstance(term, (bool, int, float, str, bytes)) or term is None:
        return True
    # ...
    return True  # ← catch-all returns True
```

The catch-all `return True` at the end handles unknown types including PredicateMeta
classes. Zero-arity atoms are ground, so this is correct. **No change needed.**

#### 5d. `_is_compound` in `_helpers.py`

**Current code** (lines 74-78):

```python
def _is_compound(term: Any) -> bool:
    return (
        isinstance(term, (Compound, KWTerm))
        or is_term_instance(term)
    )
```

For zero-arity atoms, `is_term_instance` returns `False` (it's a class), and
`isinstance(red, (Compound, KWTerm))` is `False`. So `_is_compound(red)` returns
`False` — **correct** (atoms are not compounds).

#### 5e. `_args_list` in `_helpers.py`

**Current code** (lines 63-71) falls through to `return []` for unknown types.
For zero-arity atoms, this returns `[]` — **correct**.

#### 5f. `Functor/3` in `inspection.py`

**File:** `clausal/logic/builtins/inspection.py`

**Decomposition mode** (lines 42-54):

```python
f_val = _functor_name(term_val)  # After 5a fix: returns "red"
a_val = _arity(term_val)          # After 5b fix: returns 0
```

With the `_helpers.py` fixes, `Functor(red, F, A)` correctly yields `F = "red", A = 0`.

**But wait:** `_functor_name` returns the string `"red"`, and `Functor/3` then
unifies `name` with that string. So `Functor(red, Name, 0)` gives `Name = "red"`
(a string), not `Name = red` (the class). This is actually correct for ISO semantics
where functor names are atoms — but in our system, should the functor name of a
declared atom be the atom itself?

**Decision:** Return the atom class as the functor name. Change `_functor_name` to:

```python
# Zero-arity PredicateMeta class: the class IS the atom AND the functor name
if isinstance(term, PredicateMeta) and not term._fields:
    return term  # Return the class itself, not its __name__ string
```

This means `Functor(red, Name, 0)` gives `Name = red` (the class). More consistent
with the design principle that the class IS the atom.

**Type annotation change:** `_functor_name` return type becomes `str | type | None`
(or just `Any`).

**Construction mode** (lines 25-41):

```python
if arity_val == 0:
    constructed = name_val  # Atom is constructed directly
```

If `name_val` is the `red` class (from `Functor(T, red, 0)`), then `constructed = red`.
`unify(term, red, trail)` binds `T` to `red`. **Correct.**

If `arity_val > 0` (line 37):
```python
constructed = Compound(str(name_val), args)
```

`str(name_val)` for a class gives `"<class 'red'>"` — **BUG**. This needs to use
`name_val.__name__` if `name_val` is a PredicateMeta:

```python
else:
    functor_str = name_val.__name__ if isinstance(name_val, PredicateMeta) else str(name_val)
    args = tuple(Var() for _ in range(arity_val))
    constructed = Compound(functor_str, args)
```

#### 5g. `Unpack/2` in `inspection.py`

**Decomposition** (lines 85-94):

```python
f_val = _functor_name(term_val)  # Returns red (the class) after our fix
decomposed = [f_val] + _args_list(term_val)  # [red] for atoms
```

`Unpack(red, L)` → `L = [red]`. **Correct.**

**Construction** (lines 96-111):

```python
f_val = deref(lst_val[0])  # red (the class)
if len(args_vals) == 0:
    constructed = f_val  # atom → red
```

`Unpack(T, [red])` → `T = red`. **Correct.**

For non-zero arity (line 107):
```python
constructed = Compound(str(f_val), tuple(args_vals))
```

Same `str(f_val)` bug as Functor/3. Apply same fix.

#### 5h. `_copy_term` in `inspection.py`

**Current code** (lines 117-141):

```python
def _copy_term(term: Any, var_map: dict) -> Any:
    term = deref(term)
    if is_var(term): ...
    if isinstance(term, (bool, int, float, str, bytes)) or term is None:
        return term
    # ... Compound, KWTerm, term_instance branches ...
    return term  # ← catch-all
```

For zero-arity atoms (PredicateMeta classes), none of the branches before the catch-all
match, so it returns `term` unchanged. **Correct** — atoms are ground, no copying needed.

#### Tests:

**Clausal-side** (update `tests/conformity/iso_term_manipulation.clausal`):

Current tests like:
```clausal
Test("construct atom: Functor(T, a, 0)") <- (
    Functor(T_, a, 0),
    T_ == a
)
```

After the change, `a` is a PredicateMeta class. `Functor(T_, a, 0)` constructs by
setting `T_ = a` (the class). `T_ == a` succeeds. **Still passes.**

```clausal
Test("decompose atom: 'a' =.. X") <- (
    Unpack(a, X_),
    X_ == [a]
)
```

`Unpack(a, X_)` → `X_ = [a]` (list containing the class). `X_ == [a]` succeeds
because unification of lists recurses, and `a == a` at the element level. **Still passes.**

**Python-side tests:**

```python
def test_functor_decompose_atom():
    """Functor/3 decomposes a declared atom to (name, 0)."""
    name, arity = Var(), Var()
    # Use the builtin with red as term
    result = _call_binding("Functor", red, name, arity)
    assert result[0] is red   # functor name is the atom class itself
    assert result[1] == 0

def test_univ_decompose_atom():
    """Unpack/2 decomposes a declared atom to [atom]."""
    lst = Var()
    result = _call_binding("Unpack", red, lst)
    assert result == [red]

def test_functor_construct_atom():
    """Functor/3 constructs an atom from (name, 0)."""
    term = Var()
    result = _call_binding("Functor", term, red, 0)
    assert result is red
```

---

### Phase 6: Update character/string builtins

**File:** `clausal/logic/builtins/chars.py`

Several builtins assume atoms are strings via `isinstance(va, str)` checks. These need
to also handle zero-arity PredicateMeta classes.

**Add a shared helper** at the top of the file (after imports):

```python
from clausal.logic.predicate import PredicateMeta

def _atom_to_str(val: Any) -> str | None:
    """Extract a string name from an atom value.

    Returns the string for str atoms, __name__ for zero-arity PredicateMeta
    classes, or None if val is not an atom.
    """
    if isinstance(val, str):
        return val
    if isinstance(val, PredicateMeta) and not val._fields:
        return val.__name__
    return None
```

#### 6a. `AtomChars/2` (lines 175-212)

**Current check** (line 189):
```python
if not isinstance(va, str):
    raise LogicException(type_error("atom", va, "atom_chars/2"))
```

**Change to:**
```python
atom_str = _atom_to_str(va)
if atom_str is None:
    raise LogicException(type_error("atom", va, "atom_chars/2"))
```

And then use `atom_str` instead of `va`:
```python
mark = trail.mark()
if unify(chars, list(atom_str), trail):
    yield None
trail.undo(mark)
```

**Reverse direction** (Chars → Atom, lines 195-210): When constructing an atom from
a char list, the result should be a string (not a PredicateMeta class), since the atom
is being dynamically constructed. `"".join(elems)` already produces a string. This is
correct — dynamically-constructed atoms from `atom_chars` are undeclared atoms (strings).

#### 6b. `AtomCodes/2` (lines 217-252)

Same pattern as `AtomChars/2`.

#### 6c. `AtomLength/2` (lines 159-170)

```python
if not isinstance(va, str):
    raise LogicException(type_error("atom", va, "atom_length/2"))
mark = trail.mark()
if unify(length, len(va), trail):
```

**Change to:**
```python
atom_str = _atom_to_str(va)
if atom_str is None:
    raise LogicException(type_error("atom", va, "atom_length/2"))
mark = trail.mark()
if unify(length, len(atom_str), trail):
```

#### 6d. `UpcaseAtom/2` (lines 129-140), `DowncaseAtom/2` (lines 143-154)

Same pattern — use `_atom_to_str` and operate on the extracted string.

#### 6e. `AtomConcat/3` (lines 257-298), `SubAtom/5` (lines 303-361)

These also check `isinstance(va, str)`. Apply the same `_atom_to_str` pattern.

**Note:** For operations that produce a new atom value (like `UpcaseAtom`), the result
is a string, not a PredicateMeta class. This is correct — the uppercased version is
a new undeclared atom.

#### Tests:

```python
class hello(metaclass=PredicateMeta):
    _fields = ()

def test_atom_chars_declared_atom():
    """AtomChars decomposes a declared atom to its characters."""
    chars = Var()
    result = _call_binding("AtomChars", hello, chars)
    assert result == ["h", "e", "l", "l", "o"]

def test_atom_length_declared_atom():
    length = Var()
    result = _call_binding("AtomLength", hello, length)
    assert result == 5

def test_upcase_declared_atom():
    upper = Var()
    result = _call_binding("UpcaseAtom", hello, upper)
    assert result == "HELLO"  # result is a string, not a PredicateMeta
```

---

### Phase 7: Compiler verification

**File:** `clausal/logic/compiler.py`

#### First-argument indexing

The `_build_arg_index()` function (around line 7078) returns `None` when
`arity == 0`:

```python
if arity == 0 or pos >= arity or len(clauses) < threshold:
    return None
```

This means zero-arity predicates get no indexing, falling through to sequential
clause search. This is correct and efficient for atoms (typically 0-1 clauses).

#### Dispatch compilation

For zero-arity predicates, the compilation pipeline at lines 5563-5641 creates a
simple dispatch function with no argument extraction. Verify that:

1. `compile_predicate_trampoline(functor, 0, clauses, ...)` works — it should,
   since arity is just used to determine how many args to destructure.

2. The compiled dispatch function signature for arity-0 is
   `fn(this_gen, parent, trail)` with no predicate args. Calling it from
   `cls._get_dispatch()(this_gen, parent, trail)` should work.

#### Verification test:

```clausal
# tests/fixtures/atom_predicate.clausal
-module(atom_predicate, [Test(DESC)])
-private([hello, greet])

# hello is a zero-arity predicate with a clause body
greet :- print("hello world")

Test("zero-arity predicate call") <- greet
Test("atom identity") <- (X_ is hello, X_ == hello)
```

This tests that:
1. A zero-arity predicate declared as an atom can have clauses
2. Calling it works through the dispatch machinery
3. Atom identity is preserved through unification

---

### Phase 8: `make_atom` helper

**File:** `clausal/logic/predicate.py`

Add after `make_predicate` (line 274):

```python
def make_atom(name: str) -> PredicateMeta:
    """Create a zero-arity PredicateMeta atom.

    The returned class IS the atom value: ``a = make_atom("a"); a() is a``.
    Each call creates a NEW class — call once and reuse the result.

    Equivalent to ``make_predicate(name, [])``.
    """
    return make_predicate(name, [])
```

Update `__all__` (line 277):
```python
__all__ = ["PredicateMeta", "_MISSING", "is_term_instance", "is_atom",
           "term_field_names", "make_predicate", "make_atom"]
```

#### Tests:

```python
from clausal.logic.predicate import make_atom

def test_make_atom_returns_class(self):
    a = make_atom("a")
    assert isinstance(a, PredicateMeta)
    assert a._fields == ()
    assert a._arity == 0

def test_make_atom_call_returns_self(self):
    a = make_atom("a")
    assert a() is a

def test_make_atom_different_calls_different_identity(self):
    """Each make_atom call creates a distinct atom."""
    a1 = make_atom("a")
    a2 = make_atom("a")
    assert a1 is not a2  # Different classes, same name

def test_make_atom_hashable(self):
    a = make_atom("a")
    d = {a: 42}
    assert d[a()] == 42

def test_make_atom_unify(self):
    from clausal.logic.variables import Var, Trail, unify, deref
    a = make_atom("a")
    b = make_atom("b")
    trail = Trail()
    x = Var()
    assert unify(x, a, trail)
    assert deref(x) is a
    assert not unify(a, b, trail)
```

---

### Phase 9: Update `_is_ground` and `_collect_vars` for completeness

**File:** `clausal/logic/builtins/_helpers.py` (`_is_ground`, lines 81-96)

The catch-all `return True` handles PredicateMeta classes. But for clarity and
robustness, add an explicit branch:

```python
if isinstance(term, (bool, int, float, str, bytes)) or term is None:
    return True
# Zero-arity PredicateMeta atoms are ground
if isinstance(term, type) and isinstance(term, PredicateMeta) and not term._fields:
    return True
```

**File:** `clausal/logic/builtins/inspection.py` (`_copy_term`, lines 117-141)

Same — add explicit branch for clarity:

```python
if isinstance(term, (bool, int, float, str, bytes)) or term is None:
    return term
# Zero-arity PredicateMeta atoms: ground, return as-is
if isinstance(term, type) and isinstance(term, PredicateMeta) and not term._fields:
    return term
```

**File:** `clausal/logic/builtins/inspection.py` (`_collect_vars`, lines 155-180)

Same — add explicit early return:

```python
if isinstance(term, (bool, int, float, str, bytes)) or term is None:
    return
# Zero-arity PredicateMeta atoms: no variables
if isinstance(term, type) and isinstance(term, PredicateMeta) and not term._fields:
    return
```

---

### Phase 10: Update documentation and compatibility report

**File:** `docs/iso_prolog_compatibility_report.md`

Update Issue 3 (lines 108-163) to reflect the PredicateMeta approach:

- Replace the `Atom(str)` class proposal with the zero-field PredicateMeta design
- Update the type-checking table to include `IsAtom/1`
- Note that undeclared atoms remain as strings (no `Atom` wrapper needed for now)
- Update the migration section

**File:** Tutorial pages that reference atoms — check for any that say
"atoms are strings" and update.

---

## Existing Test Files That Will Need Updates

These files have tests that assume atoms are strings and will fail after the change:

### 1. `tests/test_predicate_meta.py`

- **Line 89-91** `test_zero_arity`: `assert isinstance(t, atom)` — will fail because
  `atom()` now returns `atom` (the class), and `isinstance(cls, cls)` is `False`
- **Line 112** `test_repr_zero_arity`: `assert repr(atom()) == "atom()"` — will fail
  because `repr(atom)` (the class) gives the PredicateMeta class repr
- **Line 373-375** `test_zero_arity_fields`: `term_field_names(atom())` — will fail
  because `term_field_names` expects an instance, not a class

### 2. `tests/conformity/iso_type_checking.clausal`

- Tests that check `IsStr(Hello)` will fail — `Hello` is now a class
- Need to add `IsAtom` tests and update `IsStr` tests

### 3. `tests/conformity/test_iso_type_checking.py`

- Python tests for `atom/1` that pass strings may need corresponding declared-atom tests

### 4. `tests/conformity/test_iso_term_manipulation.py`

- Tests using `"a"` as atom argument to Functor/3 and Unpack/2 still work (strings
  are still valid data). But new tests should verify PredicateMeta atom behavior.

### 5. `tests/conformity/test_iso_unification.py`

- Tests use `"a"`, `"b"` as string atoms. These continue to work (string ≠ string
  comparison). But should add tests with PredicateMeta atoms.

### 6. `tests/fixtures/builtins_types.clausal`

- `Test("is atom") <- CheckAtom("hello")` — still works (string)
- But add test for declared atom: `Test("is declared atom") <- IsAtom(SomeDeclaredAtom)`

### 7. `tests/fixtures/builtins_inspect.clausal`

- `Test("functor atom") <- (GetFunctor("hello", FUNCTOR, ARITY), FUNCTOR == "hello", ARITY == 0)`
  — still works (string atom)
- But add test for declared atom case

---

## Migration Notes

### What breaks

- **`-private` atom representation changes from `str` to `PredicateMeta` class.**
  Any code that does `isinstance(atom_val, str)` to check for atoms will fail for
  declared atoms.

- **String operations on atoms** (`atom_val.upper()`, f-string `f"{atom}"`, etc.)
  need `atom.__name__` or `_atom_to_str()` instead.

- **`repr(red)` changes** from `'red'` (string repr) to `<Predicate red/0, ...>`
  (PredicateMeta class repr). Consider adding a shorter repr for zero-arity — see
  Open Questions.

- **Cached `.pyc` files** in `__pycache__` will contain the old string-based atoms.
  A cache clear or cache version bump is needed.

### What doesn't break

- **`unify(red, red, trail)`** — works via pointer identity (C level, line 886)
- **`red == red`** — works (same object, class identity)
- **`{red: "value"}`** — works (classes are hashable via `type.__hash__`)
- **`match x: case red: ...`** — works (identity match)
- **All existing predicate code with fields** — unchanged (Phase 1 change only
  affects the zero-arity path)
- **Strings as atoms** — `"hello"` still works as an atom in unification, type
  checks (via `IsStr`), and builtins

### Backward compatibility

The `-private` directive change is the main breaking change. Any compiled `.clausal`
file that relied on atoms being strings will need updating. Since `__pycache__`
stores compiled bytecode, a cache clear is needed after this change.

---

## Open Questions

1. **Repr for zero-arity atoms.** `<Predicate red/0, 0 clause(s), compiled>` is verbose.
   Should we override `__repr__` on PredicateMeta to return just the name for zero-field
   classes? E.g., `repr(red)` → `"red"`. This would be a small change in
   `PredicateMeta.__repr__` (line 226):

   ```python
   def __repr__(cls) -> str:
       if not cls._fields:
           return cls.__name__
       compiled = "compiled" if cls._dispatch_fn is not None else "uncompiled"
       # ... rest unchanged
   ```

2. **Interning across `make_atom` calls.** Should `make_atom("red")` return the same
   class if called twice? Currently `make_predicate` creates a new class each time.
   For declared atoms this doesn't matter (one declaration per module), but for
   runtime-created atoms it might. A registry could be added:

   ```python
   _atom_registry: dict[str, PredicateMeta] = {}

   def make_atom(name: str) -> PredicateMeta:
       if name in _atom_registry:
           return _atom_registry[name]
       cls = make_predicate(name, [])
       _atom_registry[name] = cls
       return cls
   ```

3. **Prolog translation atoms.** When translating Prolog `foo(bar, baz)`, should `bar`
   and `baz` (undeclared atoms appearing as arguments) become `make_atom("bar")` calls?
   Or stay as strings? For now, recommendation is to keep them as strings (Option B)
   and defer to a later phase.

4. **`__hash__` on zero-field instances.** PredicateMeta sets `cls.__hash__ = None`
   (line 108). This affects instances, not the class itself. Since `red() is red`
   (the class), `hash(red())` uses `type.__hash__`. Verify with a test.

5. **`GenSym/2` output type.** Currently produces `f"{prefix_d}_{count}"` (a string).
   Should it produce a PredicateMeta atom? Probably not — dynamically-generated atoms
   don't need the predicate machinery. Keep as string.

---

## Summary of Changes by File

| File | Change | Lines affected |
|------|--------|---------------|
| `clausal/logic/predicate.py` | `__call__` returns `cls` for zero-arity; add `is_atom()`; add `make_atom()` | 124-147, new functions |
| `clausal/templating/term_rewriting.py` | `-private` and `-module` bare atoms → `_make_functor_class_ast(name, [])` | ~2425-2437, ~2477-2490 |
| `clausal/logic/compiler_v2.py` | `_process_declarations` atom branch creates PredicateMeta | 340-342 |
| `clausal/logic/builtins/type_checks.py` | Add `IsAtom/1`; update `IsCallable/1`; update `_check_type` | 29-34 (new), 79-88, 107-139 |
| `clausal/logic/builtins/_helpers.py` | `_functor_name` and `_arity` handle zero-arity PredicateMeta | 12-24, 27-39 |
| `clausal/logic/builtins/inspection.py` | `Functor/3` and `Unpack/2` handle PredicateMeta atoms; `str()` fixes | 33-37, 87-90, 105-107, + explicit branches in `_copy_term`, `_collect_vars` |
| `clausal/logic/builtins/chars.py` | Add `_atom_to_str` helper; update all `isinstance(va, str)` checks | 129-140, 143-154, 159-170, 175-212, 217-252, 257-298, 303-361 |
| `clausal/logic/compiler.py` | Verify only — zero-arity dispatch already works | ~7078 (no change) |
| `tests/test_predicate_meta.py` | Update zero-arity tests; add atom identity tests | 89-91, 112, 373-375, new class |
| `tests/conformity/iso_type_checking.clausal` | Update `IsStr` tests; add `IsAtom` tests | 21-24+ |
| `tests/conformity/iso_term_manipulation.clausal` | Verify existing tests pass; add declared-atom tests | 19-56 |
| `docs/iso_prolog_compatibility_report.md` | Update Issue 3 to reflect PredicateMeta approach | 108-163 |

## Execution Order

The phases should be implemented in order (1 → 10) because:

- Phase 1 (PredicateMeta `__call__`) is the foundation — everything else depends on
  zero-arity `cls() is cls` behavior
- Phase 2 (directive changes) depends on Phase 1 for atoms to work correctly
- Phase 3 (verify TermTransformer) can be done in parallel with Phase 2
- Phases 4-6 (builtins) can be done in parallel with each other, but after Phase 1
- Phase 7 (compiler verification) can be done after Phase 2
- Phase 8 (`make_atom`) is independent, can be done any time after Phase 1
- Phase 9 (groundness/copy helpers) can be done in parallel with Phases 4-6
- Phase 10 (docs) should be last

After all phases, run the full test suite (`pytest`) and fix any regressions.
