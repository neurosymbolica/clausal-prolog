# W4b-1 — Term-Shape Rehome Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give a declared functor's field names a home that does not need the `PredicateMeta` class, so W4b-2 can flip the handle and W4b-3 can delete the class without thirty call sites changing twice.

**Architecture:** One accessor — `predicate.field_names_for` — generalised from the existing `term_field_names_of_class`, with four arms: `@dataclass` class, `PredicateMeta` class (deleted at W4b-3), a NAME resolved through the registry chain, and `None`. Three minters that bypass every registry are wired up. Then the ~63 engine `isinstance(…, PredicateMeta)` sites are READ and split into shape sites (which migrate) and identity sites (which stay and become W4b-2's input). Additive throughout: the class keeps working.

**Tech Stack:** Python 3.13, pytest (house suite ~16.8k tests, ~3 min), `tools/w3_package_gate.sh`. **No C file is touched**, so no `setup.py build_ext`, no `.so` build, and no rename-swap under live importers.

**Spec:** `docs/superpowers/specs/2026-09-22-w4b1-term-shape-rehome-design.md`

**Scope note (the four W4b sub-projects):** `implementation_plans/w4b-class-retirement-scope-2026-09-22.md`

## Global Constraints

- **Work in a worktree off `main`.** Never `git checkout` a branch in the shared clone `/workspace/clausal` — a peer can be mid-edit. Create the room:
  ```bash
  git -C /workspace/clausal worktree add -b feat/w4b1-term-shape-2026-09-22 <room> main
  ln -s /workspace/clausal/venv <room>/venv
  cp $(find /workspace/clausal -name '*.so' -not -path '*/venv/*') <room>/clausal/logic/variables/ 2>/dev/null || true
  ```
  Copy each `.so` to the directory it came from, not all into one.
- **Run pytest FROM the room.** `cd <room> && ./venv/bin/python -m pytest …`. Before trusting any number, assert the engine is the room's:
  ```bash
  ./venv/bin/python -c "import clausal, sys; assert clausal.__file__.startswith('<room>'), clausal.__file__; print('engine OK', clausal.__file__)"
  ```
  A SCRIPT file puts its own directory on `sys.path` instead, and you silently test canonical.
- **Gate command:**
  ```bash
  ./venv/bin/python -m pytest tests -q -rfE -p no:cacheprovider \
      --continue-on-collection-errors --ignore=tests/test_clportools.py > out.txt 2>&1
  grep -E "^(FAILED|ERROR) " out.txt | sed -E 's/ - .*//' | sort -u > out.set
  ```
  **Regenerate the baseline on `main` at the start.** Never trust a baseline number written in a file or in memory. Assert the extracted set is non-empty before comparing (`wc -l out.set`), and gate on pytest's own exit status, never on a piped `tail`.
- **Package gate:** `./tools/w3_package_gate.sh <venv> <room> <out-prefix>` — NEW 0 / GONE 0.
- **No pytest-timeout and no pytest-randomly** are installed. Wrap a run that may hang in shell `timeout`; order is already deterministic.
- **Stage explicit paths only.** Never `git add -A` and never `git stash` in the shared clone — both sweep up other lanes' in-progress work. Run `git branch --show-current` before every commit.
- **Closed-side terms never enter commits.** Scan the range before landing.
- **zsh:** write `"${VAR}:path"` for a `git rev:path` argument — a bare `$VAR:path` is a history modifier. `grep -c` exits 1 on zero matches, so never gate a `&&` chain on it.
- **Commit trailers**, on every commit:
  ```
  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01G3Bi6ruQWgu7WHKrYWPTT9
  ```

## File Structure

| file | responsibility | task |
|---|---|---|
| `clausal/logic/predicate.py` | `field_names_for` (the one accessor); `term_field_names_of_class` becomes its alias | 1 |
| `tests/test_field_names_for.py` | the accessor's four arms and the `()` / `None` contract | 1 |
| `clausal/logic/compiler_v2.py` | `_preregister_specializations` gains a `db` parameter and registers | 2 |
| `clausal/logic/term_expansion.py` | registers `term_expansion/4` with `lm.db` | 2 |
| `clausal/modules/py/datetime.py` | `_DatePattern` — re-read, then registered or left with a corrected comment | 2 |
| `tests/test_declaration_registration.py` | one test per gap minter, plus a pin on each already-covered route | 2 |
| `tools/w4b1_census/plugin.py` | the completeness census: a pytest plugin instrumenting `field_names_for` | 3 |
| `tools/w4b1_census/README.md` | how to run it, and what each number means | 3 |
| `implementation_plans/w4b1-site-classification-2026-09-22.md` | the site-by-site read: every `isinstance` site, shape or identity, with the reason | 4 |
| the migrated shape sites | per Task 4's classification | 5 |

---

### Task 1: The accessor

**Files:**
- Modify: `clausal/logic/predicate.py` — `term_field_names_of_class` (1537–1558), `__all__` (~1811)
- Create: `tests/test_field_names_for.py`

**Interfaces:**
- Produces: `clausal.logic.predicate.field_names_for(value, *, arity=None, db=None, namespace=None) -> tuple[str, ...] | None`. `()` means *declared with zero fields*; `None` means *not term-shaped or not declared*. `term_field_names_of_class(cls)` survives as `field_names_for(cls)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_field_names_for.py
"""W4b-1: one accessor for a declared functor's field names (spec
docs/superpowers/specs/2026-09-22-w4b1-term-shape-rehome-design.md).

The contract that matters is the DECLAREDNESS one: ``None`` means the value
names nothing declared, ``()`` means declared with zero fields, and the
length of the tuple is the arity.  Arm 3 (a NAME) is the point of the
change: at W4b-2 a module attribute becomes a mangled atom, and arm 3
already answers for it."""
import dataclasses

import pytest

from clausal.logic.atoms import mangle
from clausal.logic.database import Database
from clausal.logic.cells import FUNCTOR_SIGNATURES_KEY
from clausal.logic.predicate import (
    field_names_for, make_predicate, term_field_names_of_class,
)


@dataclasses.dataclass
class Point:
    x: int
    y: int


def test_arm1_dataclass_class_yields_declared_fields():
    assert field_names_for(Point) == ("x", "y")


def test_arm2_predicate_class_yields_its_fields():
    Pt = make_predicate("Pt", ["x", "y"])
    assert field_names_for(Pt) == ("x", "y")


def test_arm3_name_resolves_through_the_database():
    db = Database()
    db.declare_functor("edge", ("from_", "to"))
    assert field_names_for("edge", arity=2, db=db) == ("from_", "to")


def test_arm3_reads_register_signature_too():
    """signature_for chains _signatures BEFORE _declared, and -specialize
    registers through register_signature only."""
    db = Database()
    db.register_signature("spec_pred", 1, ("only",))
    assert field_names_for("spec_pred", arity=1, db=db) == ("only",)


def test_arm3_name_resolves_through_a_namespace_with_no_db():
    ns = {FUNCTOR_SIGNATURES_KEY: {"vec": ("x", "y")}}
    assert field_names_for("vec", namespace=ns) == ("x", "y")


def test_arm3_mangled_name_resolves_against_its_OWN_module_db(monkeypatch):
    """A handle carries its module.  The caller's db must not be consulted
    for a mangled name -- that would answer for the wrong predicate."""
    import clausal.logic.predicate as predmod

    owner_db = Database()
    owner_db.declare_functor("hidden", ("a",))
    caller_db = Database()
    caller_db.declare_functor("hidden", ("WRONG", "ALSO_WRONG"))

    monkeypatch.setattr(
        predmod, "_db_for_module_name", lambda name: owner_db, raising=False)
    assert field_names_for(mangle("owner", "hidden"), arity=1,
                           db=caller_db) == ("a",)


def test_arm4_a_non_class_non_name_value_is_None():
    assert field_names_for(42) is None
    assert field_names_for(object()) is None


def test_zero_field_declaration_is_empty_tuple_not_None():
    """The contract's sharp edge: ``p()`` is DECLARED with no fields, and
    that is not the same answer as 'nothing declared'."""
    P = make_predicate("P0", [])
    assert field_names_for(P) == ()
    assert field_names_for("never_declared", arity=0, db=Database()) is None


def test_two_arities_exact_read_beats_the_by_name_fallback():
    db = Database()
    db.declare_functor("p", ("a",))
    db.declare_functor("p", ("a", "b"))
    assert field_names_for("p", arity=1, db=db) == ("a",)
    assert field_names_for("p", arity=2, db=db) == ("a", "b")
    # No arity: the by-name read, which answers the LAST declaration.  Pinned
    # so the documented lossiness is a recorded property, not a surprise.
    assert field_names_for("p", db=db) == ("a", "b")


def test_term_field_names_of_class_still_answers_for_its_callers():
    Pt = make_predicate("PtAlias", ["x"])
    assert term_field_names_of_class(Pt) == ("x",)
    assert term_field_names_of_class(Point) == ("x", "y")
    assert term_field_names_of_class(42) is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `./venv/bin/python -m pytest tests/test_field_names_for.py -q -p no:cacheprovider`
Expected: collection error — `cannot import name 'field_names_for'`. That is the correct first failure; do not proceed until you have seen it.

- [ ] **Step 3: Implement**

In `clausal/logic/predicate.py`, replace the body of `term_field_names_of_class` (1537–1558) with the alias and add the accessor above it:

```python
def _db_for_module_name(module_name: str):
    """The Database of a LOADED module, by name, or None.

    Split out so the mangled-name arm can be tested without a real module
    load, and so the lookup has one home when W4b-2 adds callers.
    """
    import sys  # noqa: PLC0415
    mod = sys.modules.get(module_name)
    return getattr(mod, "db", None)


def field_names_for(value, *, arity=None, db=None, namespace=None):
    """Field names for a declared functor, or None.

    FIRST a declaredness reader, second a shape reader: ``None`` means the
    value names nothing declared, ``()`` means declared with ZERO fields (the
    0-arity predicate written ``p()``), and ``len()`` is the arity.  The
    compiler's dominant use of the signature registry is the presence test
    ("a declared functor, or an atom being applied as one?"), which never
    reads a name -- see the spec's premise check.

    Four arms, in order:

    1. a ``@dataclass`` class -> its declared field names.  Permanent.
    2. a ``PredicateMeta`` class -> ``cls._fields``.  DELETED AT W4b-3; it is
       the legacy answer and the census in ``tools/w4b1_census`` measures
       whether arm 3 agrees with it everywhere.
    3. a NAME (``str``, plain or mangled) -> the registry chain below.
       Permanent, and the point of the change: at W4b-2 a module attribute
       for a predicate becomes a mangled atom, and this arm already answers.
    4. anything else -> ``None``.
    """
    if isinstance(value, str):
        return _field_names_for_name(value, arity, db, namespace)
    if not isinstance(value, type):
        return None
    if isinstance(value, PredicateMeta):
        return value._fields
    if dataclasses.is_dataclass(value):
        return tuple(f.name for f in dataclasses.fields(value))
    return None


def _field_names_for_name(name, arity, db, namespace):
    """Arm 3.  Demangle -> exact db read -> by-name db read -> the
    namespace's exec-time carrier -> the builtin registry -> None."""
    from clausal.logic.atoms import demangle, is_mangled  # noqa: PLC0415
    if is_mangled(name):
        # A handle carries its module: resolve against the OWNER's db, never
        # the caller's, or a name declared in both answers for the wrong one.
        module_name, name = demangle(name)
        db = _db_for_module_name(module_name)
    if db is not None:
        if arity is not None:
            found = db.signature_for(name, arity)
            if found is not None:
                return found
        else:
            # ``signature_for`` needs an arity; the by-name read is the only
            # thing that can answer without one, and it resolves a two-arity
            # name to the LAST declaration (database.py:1010).
            found = db.declared_fields_by_name(name)
            if found is not None:
                return found
    if namespace is not None:
        from clausal.logic.cells import FUNCTOR_SIGNATURES_KEY  # noqa: PLC0415
        found = (namespace.get(FUNCTOR_SIGNATURES_KEY) or {}).get(name)
        if found is not None:
            return tuple(found)
    from clausal.logic.builtins import _BUILTIN_FIELDS  # noqa: PLC0415
    if arity is not None:
        return _BUILTIN_FIELDS.get((name, arity))
    for (functor, _a), fields in _BUILTIN_FIELDS.items():
        if functor == name:
            return fields
    return None


def term_field_names_of_class(cls: Any) -> tuple[str, ...] | None:
    """Field names for a term CLASS, or None.

    RETAINED ALIAS (W4b-1): ``field_names_for`` is the accessor now.  This
    name is in ``__all__`` and out-of-tree callers use it, so it survives
    until W4b-3 retires it with the class.  A ``str`` reaching here would
    take arm 3 with no db and no namespace, which is the same ``None`` the
    old class-only implementation gave -- no caller changes behaviour.
    """
    return field_names_for(cls)
```

Add `"field_names_for",` to `__all__` beside `"term_field_names_of_class"`.

- [ ] **Step 4: Run the new tests**

Run: `./venv/bin/python -m pytest tests/test_field_names_for.py -q -p no:cacheprovider`
Expected: 10 passed.

- [ ] **Step 5: Run the neighbours**

Run: `./venv/bin/python -m pytest tests/test_predicate_meta.py tests/test_term_inspection.py tests/test_funnel_accessors.py tests/test_instance_path_retired.py -q -p no:cacheprovider`
Expected: no NEW failures against the same files run on `main`. Compare, do not eyeball — this task is additive and any new failure means the alias changed behaviour.

- [ ] **Step 6: Commit**

```bash
git add clausal/logic/predicate.py tests/test_field_names_for.py
git commit   # message: "W4b-1: one accessor for a declared functor's field names"
```

---

### Task 2: Close the three registration gaps

**Files:**
- Modify: `clausal/logic/compiler_v2.py` — `_preregister_specializations` (1199–1231) and its caller
- Modify: `clausal/logic/term_expansion.py:314`
- Modify: `clausal/modules/py/datetime.py:204` (`_DatePattern`)
- Create: `tests/test_declaration_registration.py`

**Interfaces:**
- Consumes: `field_names_for` from Task 1.
- Produces: after each of the three mints, `db.signature_for(functor, arity)` answers with the same tuple the class carries.

**Before writing code — the spec's section 3 was verified during planning; do not re-derive it, but DO read `_DatePattern` yourself.** Three of the original six were already covered: `specialization.py` ×3 register through `_install_specialized`'s `db.register_signature` (specialization.py:388), and `builtins/_registry.py` ×2 are minted detached on purpose with `_BUILTIN_FIELDS` as their registry. Only the three files above are gaps.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_declaration_registration.py
"""W4b-1: every engine minter's declaration reaches a registry, so
``field_names_for`` can answer from a NAME after W4b-2 takes the class away.

Three gaps are closed here.  The two routes that were ALREADY covered are
pinned too, so a later change that removes the coverage fails here rather
than silently leaving a name unanswerable."""
from clausal.logic.database import Database
from clausal.logic.predicate import field_names_for


def test_preregistered_specialization_is_registered(tmp_path):
    from clausal.logic.compiler_v2 import _preregister_specializations
    from clausal.logic.specialization import _specialized_fields  # noqa: F401
    db = Database()
    module_dict = {}
    items = _specialize_items_fixture(module_dict)
    _preregister_specializations(items, module_dict, db)
    for name, fields in _expected_specializations(items, module_dict):
        assert db.signature_for(name, len(fields)) == fields, name


def test_term_expansion_class_is_registered():
    """term_expansion/4 is minted into a synthetic LogicModule; its own db
    must know the declaration."""
    from clausal.logic.term_expansion import _term_expansion_module
    lm = _term_expansion_module({})
    assert lm.db.signature_for("term_expansion", 4) == (
        "term", "expansion", "module_before", "module_after")


def test_specialize_route_still_registers_through_register_signature():
    """ALREADY COVERED (specialization.py:388) -- pinned so it stays so."""
    db = Database()
    db.register_signature("solve_natnum", 2, ("goal", "depth"))
    assert field_names_for("solve_natnum", arity=2, db=db) == ("goal", "depth")


def test_builtins_answer_from_the_builtin_registry_with_no_db():
    """ALREADY COVERED -- builtins are minted DETACHED on purpose and
    _BUILTIN_FIELDS is their registry.  Arm 3 must reach it."""
    from clausal.logic.builtins import _BUILTIN_FIELDS
    (functor, arity), fields = next(iter(_BUILTIN_FIELDS.items()))
    assert field_names_for(functor, arity=arity) == fields
```

The two helpers `_specialize_items_fixture` / `_expected_specializations` are fixture builders: read `tests/test_specialization_pipeline.py` for how that suite builds `SpecializeItem`s and a `module_dict`, and build the smallest pair that produces one pre-registered class. If that suite's fixtures are directly reusable, import them rather than writing new ones.

- [ ] **Step 2: Run to verify they fail**

Run: `./venv/bin/python -m pytest tests/test_declaration_registration.py -q -p no:cacheprovider`
Expected: the first two FAIL (`_preregister_specializations` takes 2 arguments; no `_term_expansion_module`), the last two PASS — they pin behaviour that already exists.

- [ ] **Step 3: Implement the two mechanical gaps**

`compiler_v2.py`: change the signature to `def _preregister_specializations(module_items: list, module_dict: dict, db: Any) -> None:` and, immediately after `module_dict[item.new_name] = cls` (1230), add:

```python
            # W4b-1: the class is not the only place these fields may be
            # read from.  Register the declaration so ``field_names_for``
            # answers from the NAME once W4b-2 makes the module attribute a
            # mangled atom.  ``_install_specialized`` registers again later
            # through ``register_signature``; both write the same tuple.
            db.declare_functor(item.new_name, tuple(fields))
```

Then update its single caller to pass the `db` it already holds. Find it:
```bash
grep -n "_preregister_specializations" clausal/logic/compiler_v2.py
```

`term_expansion.py`: extract the module construction at 305–320 into `_term_expansion_module(module_dict)` returning `lm` (so the test can build one without running an expansion), and add after `lm.module_dict["term_expansion"] = te_cls`:

```python
    # W4b-1: register the declaration on the synthetic module's own db, so
    # ``term_expansion/4`` is answerable by NAME and not only off the class.
    lm.db.declare_functor(
        "term_expansion", ("term", "expansion", "module_before", "module_after"))
```

- [ ] **Step 4: Run those two tests**

Run: `./venv/bin/python -m pytest tests/test_declaration_registration.py -q -p no:cacheprovider`
Expected: 4 passed.

- [ ] **Step 5: READ `_DatePattern` and decide — do not guess**

`clausal/modules/py/datetime.py:204` justifies `metaclass=PredicateMeta` like this:

> PredicateMeta (rather than a plain class) because the engine's clause copier rebuilds *term instances* with fresh variables on each resolution step, and it recognises them via PredicateMeta or @dataclass (``c_is_term_instance`` in logic/variables/_variables.c).

**W4a retired the instance path and deleted that C arm**, so the stated reason no longer holds: `_DatePattern(…)` now builds a cell like any other predicate class. Determine which of these is true by reading the module and running its tests, then do the matching thing:

- if nothing constructs a `_DatePattern` instance any more, it does not need the metaclass at all — but **converting it is NOT this task**; file a todo (`todo/datepattern-metaclass-premise-is-stale-2026-09-22.md`) recording the stale docstring, what W4a changed, and the measurement you made. Leave the class alone and correct the docstring to say what is actually true now.
- if it is still load-bearing as a declared functor, register it the way the other two were registered, with whatever db its module has.

Either way the docstring's stale claim is corrected in this task. Run:
```bash
./venv/bin/python -m pytest tests/ -q -p no:cacheprovider -k "date" 2>&1 | tail -5
```

- [ ] **Step 6: Commit**

```bash
git add clausal/logic/compiler_v2.py clausal/logic/term_expansion.py \
        clausal/modules/py/datetime.py tests/test_declaration_registration.py
# add todo/datepattern-metaclass-premise-is-stale-2026-09-22.md if you filed one
git commit   # message: "W4b-1: close the three registration gaps (three of six were already covered)"
```

---

### Task 3: The completeness census

**Files:**
- Create: `tools/w4b1_census/plugin.py`, `tools/w4b1_census/README.md`

**Interfaces:**
- Consumes: `field_names_for` (Task 1), the registrations (Task 2).
- Produces: a pytest plugin loadable with `-p tools.w4b1_census.plugin`, printing a report at session end.

**Why this task exists.** A green suite proves nothing about this change: arm 2 answers every call while the class exists, so the suite would be equally green with arm 3 completely broken. The census is the actual gate.

- [ ] **Step 1: Write the plugin, with its positive control first**

```python
# tools/w4b1_census/plugin.py
"""W4b-1 completeness census: does arm 3 (the NAME) agree with arm 2 (the
class) everywhere the suite asks?

Wraps ``predicate.field_names_for`` for the session and records, per call,
which arm answered and -- for every arm-2 answer -- what arm 3 WOULD have
said.  Prints N, the per-arm counts and the agreement table at session end.

Every number is printed with its denominator.  N == 0 is a REFUSAL, not a
pass: a census over an empty population is the commonest way an instrument
fails open.
"""
import collections

import pytest

_STATS = collections.Counter()
_RESIDUE = set()
_DISAGREED = []


def _shadow_arm3(cls):
    """What arm 3 would answer for the name this class is bound under."""
    from clausal.logic.predicate import field_names_for
    row = getattr(cls, "_row", None)
    db = getattr(row, "_db", None) if row is not None else None
    return field_names_for(cls.__name__,
                           arity=len(getattr(cls, "_fields", ()) or ()),
                           db=db)


def pytest_configure(config):
    import dataclasses

    import clausal.logic.predicate as predmod
    from clausal.logic.predicate import PredicateMeta

    original = predmod.field_names_for

    def counting(value, *, arity=None, db=None, namespace=None):
        result = original(value, arity=arity, db=db, namespace=namespace)
        _STATS["N"] += 1
        if isinstance(value, str):
            _STATS["arm3_name"] += 1
        elif isinstance(value, type) and isinstance(value, PredicateMeta):
            _STATS["arm2_class"] += 1
            try:
                shadow = _shadow_arm3(value)
            except Exception as exc:                      # noqa: BLE001
                shadow = ("<raised>", type(exc).__name__)
            if shadow is None:
                _STATS["arm2_shadow_unanswerable"] += 1
                _RESIDUE.add(value.__name__)
            elif shadow == result:
                _STATS["arm2_shadow_agreed"] += 1
            else:
                _STATS["arm2_shadow_disagreed"] += 1
                _DISAGREED.append((value.__name__, result, shadow))
        elif isinstance(value, type) and dataclasses.is_dataclass(value):
            _STATS["arm1_dataclass"] += 1
        else:
            _STATS["arm4_none"] += 1
        return result

    predmod.field_names_for = counting
    config._w4b1_restore = (predmod, original)


def pytest_unconfigure(config):
    predmod, original = config._w4b1_restore
    predmod.field_names_for = original


def pytest_terminal_summary(terminalreporter):
    w = terminalreporter.write_line
    n = _STATS["N"]
    w("")
    w("=" * 68)
    w("W4b-1 COMPLETENESS CENSUS")
    w("=" * 68)
    if n == 0:
        w("REFUSAL: N == 0 -- field_names_for was never called.  This is not")
        w("a pass.  The plugin did not load, or nothing under test reached")
        w("the accessor.  Fix the instrument before reading any other line.")
        return
    w(f"N (total field_names_for calls)          {n}")
    for key, label in (("arm1_dataclass", "arm 1  @dataclass class"),
                       ("arm2_class", "arm 2  PredicateMeta class"),
                       ("arm3_name", "arm 3  a NAME"),
                       ("arm4_none", "arm 4  not term-shaped")):
        c = _STATS[key]
        w(f"  {label:<38} {c:>7}  ({100.0 * c / n:.1f}% of {n})")
    a2 = _STATS["arm2_class"]
    w("")
    w(f"SHADOW READ, over the {a2} arm-2 answers (the denominator):")
    if a2 == 0:
        w("  arm 2 never answered -- the agreement table is VACUOUS.")
    else:
        for key, label in (("arm2_shadow_agreed", "agreed"),
                           ("arm2_shadow_disagreed", "DISAGREED"),
                           ("arm2_shadow_unanswerable", "could not answer")):
            c = _STATS[key]
            w(f"  {label:<38} {c:>7}  ({100.0 * c / a2:.1f}% of {a2})")
    if _DISAGREED:
        w("")
        w("DISAGREEMENTS (each is a defect, not a fallback):")
        for name, got, shadow in _DISAGREED[:40]:
            w(f"  {name}: arm2={got!r} arm3={shadow!r}")
        if len(_DISAGREED) > 40:
            w(f"  ... and {len(_DISAGREED) - 40} more (of {len(_DISAGREED)})")
    if _RESIDUE:
        w("")
        w(f"RESIDUE -- functors arm 3 could not answer ({len(_RESIDUE)}), BY NAME:")
        for name in sorted(_RESIDUE):
            w(f"  {name}")
        w("  Each must be explained by the out-of-tree make_predicate")
        w("  population named in the spec's section 3.  An unexplained name")
        w("  is a gap W4b-3 would turn into a silent failure.")
    w("=" * 68)
```

- [ ] **Step 2: Write the positive control and watch it fire**

```python
# tests/test_w4b1_census_positive_control.py
"""The census must be SEEN to report a disagreement before any real number
it prints is worth reading.  56 instruments in this project's ledger failed
open; this is how the 57th is prevented."""
from clausal.logic.database import Database
from clausal.logic.predicate import field_names_for, make_predicate


def test_a_planted_disagreement_is_visible_to_the_shadow_read():
    Pt = make_predicate("PlantedDisagreement", ["x", "y"])
    db = Pt._state_row()._db
    # Register DELIBERATELY WRONG fields at the class's own arity.
    db.register_signature("PlantedDisagreement", 2, ("WRONG", "ALSO_WRONG"))
    assert field_names_for(Pt) == ("x", "y")
    assert field_names_for("PlantedDisagreement", arity=2, db=db) == (
        "WRONG", "ALSO_WRONG")
```

Run with the plugin and CONFIRM the report names it:
```bash
./venv/bin/python -m pytest tests/test_w4b1_census_positive_control.py \
    -q -p no:cacheprovider -p tools.w4b1_census.plugin 2>&1 | tail -30
```
Expected: the `DISAGREEMENTS` section lists `PlantedDisagreement` with both tuples. **If it does not appear, the instrument is broken — fix it before running the real census.** Do not proceed on a report you have not seen fire.

- [ ] **Step 3: Run the real census over the whole suite**

```bash
./venv/bin/python -m pytest tests -q -rfE -p no:cacheprovider \
    --continue-on-collection-errors --ignore=tests/test_clportools.py \
    -p tools.w4b1_census.plugin > census.txt 2>&1
tail -60 census.txt
```

- [ ] **Step 4: Read the report against the fail conditions**

Fail on any of: `N == 0`; a non-zero `DISAGREED` count; a residue name not explained by out-of-tree `make_predicate`. A disagreement here may be a **pre-existing** bug this spec discovered rather than a defect in the change — in that case file a todo with the two tuples and the functor, and get a ruling before building on top of it. Do not "fix" it by widening arm 3 to match arm 2.

- [ ] **Step 5: Write the README with the numbers you actually got**

`tools/w4b1_census/README.md`: the command, what each line means, the fail conditions, the positive control and how to re-run it, and **the numbers from this run, dated**, with the note that they are re-derived rather than trusted.

- [ ] **Step 6: Commit**

```bash
git add tools/w4b1_census/ tests/test_w4b1_census_positive_control.py
git commit   # message: "W4b-1: the completeness census, with its positive control watched firing"
```

---

### Task 4: Read and classify all 63 engine `isinstance` sites

**Files:**
- Create: `implementation_plans/w4b1-site-classification-2026-09-22.md`

**Interfaces:**
- Produces: the classification every later task consumes — the SHAPE list (Task 5 migrates these) and the IDENTITY list (W4b-2's measured input).

**This task writes no code.** Its output is a document, and it is the task the spec exists to protect: the accessor is WIDER than the `isinstance` it replaces (arm 1 answers for a `@dataclass` class; `isinstance(x, PredicateMeta)` refuses one), so migrating an identity site silently widens it in a direction the house suite is poorly placed to catch.

- [ ] **Step 1: Enumerate the population, with its size printed**

```bash
grep -rn "isinstance([^)]*PredicateMeta" --include='*.py' clausal/ > sites.txt
wc -l sites.txt      # print the denominator; every later count is out of this
```
Expect 63 on `main` at `11623ba4`. If it differs, `main` moved — say so in the document and use YOUR number, not this one.

- [ ] **Step 2: Read every site and classify it**

For each, open the file at that line and read enough context to answer ONE question: *does this site want the field names / arity / declaredness (SHAPE), or does it want "this binding is a clausal declaration specifically, and not any term-shaped Python class" (IDENTITY)?*

Signals, not rules:
- reads `._fields`, or `not x._fields`, or calls `term_field_names_of_class` nearby → **SHAPE**
- decides whether a name is a functor or an atom applied as one → **SHAPE** (declaredness)
- guards a `_bind_row` / `_get_dispatch` / dispatch-install / module-binding decision → **IDENTITY**
- its `else` branch treats the value as an ordinary Python object → read harder; a `@dataclass` reaching that branch today is the thing that would change

Record each as a row: `file:line | SHAPE or IDENTITY | what it asks | would arm 1 change its answer?`

- [ ] **Step 3: Write the document**

`implementation_plans/w4b1-site-classification-2026-09-22.md`: the denominator, the table of all 63 rows, then the two totals — **and the totals must add up to the denominator.** Any site you could not classify goes in an explicit UNRESOLVED bucket with the reason; a silent choice is worse than an admitted gap. Note at the top that the spec's "~30 / ~33" was a grep-context estimate and this document supersedes it.

- [ ] **Step 4: Commit**

```bash
git add implementation_plans/w4b1-site-classification-2026-09-22.md
git commit   # message: "W4b-1: the site classification -- <N> shape, <M> identity, <K> unresolved"
```

---

### Task 5: Migrate the SHAPE sites

**Files:**
- Modify: every file in Task 4's SHAPE list
- Modify: the tests those sites are covered by, where an assertion names the old spelling

**Interfaces:**
- Consumes: Task 4's classification; `field_names_for` from Task 1.

- [ ] **Step 1: Migrate ONE file, the smallest in the SHAPE list, and gate it**

Pick the file with the fewest SHAPE sites. Rewrite each:

```python
# before
if isinstance(term, type) and isinstance(term, PredicateMeta) and not term._fields:
# after
if field_names_for(term) == ():
```
```python
# before
fields = getattr(cls, "_fields", None) if isinstance(cls, PredicateMeta) else None
# after
fields = field_names_for(cls)
```

For each site, ask the Task 4 question again as you edit: *would arm 1 change this site's answer?* If yes, and the widening is not wanted, the site was misclassified — move it to IDENTITY in the document and leave the code alone.

Run the gate command; compare against the `main` baseline. Expected NEW 0 / GONE 0.

- [ ] **Step 2: Commit that file alone**

```bash
git add <the one file> <its tests>
git commit   # message names the file and the site count
```

- [ ] **Step 3: Repeat Steps 1–2 per file, one commit each**

One file per commit so a reviewer can reject one migration while approving its neighbours, and so a bisect lands on a single file. Do not batch.

- [ ] **Step 4: Re-run the census and compare with Task 3's numbers**

```bash
./venv/bin/python -m pytest tests -q -rfE -p no:cacheprovider \
    --continue-on-collection-errors --ignore=tests/test_clportools.py \
    -p tools.w4b1_census.plugin > census_after.txt 2>&1
tail -60 census_after.txt
```
Expected: `arm3_name` has RISEN and `arm2_class` fallen by roughly the same amount; disagreements still 0; the residue set unchanged or smaller. A residue that GREW means a migration introduced a name nothing can answer for — find it before continuing.

- [ ] **Step 5: Both gates, final**

```bash
./venv/bin/python -m pytest tests -q -rfE -p no:cacheprovider \
    --continue-on-collection-errors --ignore=tests/test_clportools.py > final.txt 2>&1
grep -E "^(FAILED|ERROR) " final.txt | sed -E 's/ - .*//' | sort -u > final.set
wc -l final.set base.set
comm -13 base.set final.set    # NEW -- must be empty
comm -23 base.set final.set    # GONE -- must be empty
./tools/w3_package_gate.sh <venv> <room> pkg_after
```
Expected: NEW 0 / GONE 0 both ways.

- [ ] **Step 6: Barrier scan, then hand back for review**

```bash
git log main..HEAD -p | grep -niE "clausify|<the closed-side terms>" || echo "0 hits"
git log --oneline main..HEAD
```
Report: the census before/after, both gate results, the classification totals, and the residue list by name. Do NOT land without an explicit go — the landing rewrites source under any lane reading the tree.

---

## Self-Review

**Spec coverage.** Section 1 (the accessor) → Task 1. Section 2 (registry precedence) → Task 1's arm-3 chain, pinned by `test_arm3_reads_register_signature_too` and `test_builtins_answer_from_the_builtin_registry_with_no_db`. Section 3 (populating) → Task 2, with the three-of-six correction carried. Section 4 (classify, don't sweep) → Tasks 4 and 5. Tests → Tasks 1, 2, 3. Gate → Task 3 plus Task 5 Steps 4–5. Premise check → no task; it is a finding, not work.

**Type consistency.** `field_names_for(value, *, arity=None, db=None, namespace=None) -> tuple | None` is used with that spelling in Tasks 1, 2, 3 and 5. `_field_names_for_name` and `_db_for_module_name` are defined in Task 1 and referenced only there and in Task 3's `_shadow_arm3`. `db.signature_for(functor, arity)` and `db.declared_fields_by_name(functor)` are existing Database methods (database.py:992, 1010).

**Known imperfection, left deliberately.** Task 2's two fixture helpers (`_specialize_items_fixture`, `_expected_specializations`) are described rather than written, because `tests/test_specialization_pipeline.py` may already provide them and duplicating a fixture is worse than reading for one. That is the one place this plan asks the implementer to read instead of copy, and it says so.
