# `_dims` Rekey to Atoms Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `quantity._dims` a plain dict keyed by unit ATOMS (plain `str`) backed by an
atom -> unit-metadata registry, so a quantity becomes a marshal-clean true value and the P4
retirement of predicate objects can proceed.

**Architecture:** Four sequenced, independently gated steps. The registry lands first with nothing
depending on it; `_dims` becomes a plain dict with a proxy VIEW on the property; every site that
reads METADATA off a dimension key moves to the registry while keys are still predicate objects;
only then are the keys flipped to atoms. That order exists for one concrete reason, spelled out in
Task 4.

**Tech Stack:** Python 3.13, pytest. `/workspace/clausal/venv/bin/python` is the interpreter; the
suite must be run from the worktree.

**Spec:** `docs/superpowers/specs/2026-09-14-retire-predicatemeta-section4-answer.md` — the
sections `quantity RULED — 2026-09-15` and `The dims map: a DICT inside, a TUPLE on the wire`.

## Global Constraints

- **The atom is a plain `str`**, and it is exactly what `clausal/terms.py:_unit_identifier(key)`
  returns today. Not a 1-tuple: `_dims` is internal Python, and a `str` key makes `sorted()` work
  (it raises `TypeError` on predicate objects today) and makes the wire form fall out of
  `tuple(d.items())` as `('dimensions', ('euro', 1))`.
- **`_unit_identifier` is injective over the live vocabulary.** MEASURED: 262 distinct dimension
  key objects -> 262 distinct identifiers, 0 collisions, across `units` plus 181 country modules.
  Task 1 pins this as a permanent gate test, because the whole rekey is unsound without it.
- **The gate is a failure-SET diff, never a count.** Use
  `/home/node/.claude/jobs/af5b4bbe/tmp/gate_iso_l3.sh <out.raw>` then `failure_diff.py`. Do NOT
  use `gate_run.sh` — it `cd`s to the main checkout and gates the wrong tree.
- **Regenerate the baseline in THIS tree.** Never trust a remembered number.
- **Nothing is promoted by this plan.** It stays on `feat/iso-l3-lowering-2026-09-14`. Units are
  live corpus vocabulary, so promotion needs the ORACLE gate (harness-batch-lane's 28 sealed
  scorers), not the engine suite. A green suite is exactly what missed the date breakage.
- `quantity.__hash__` is `hash((self._value, frozenset(self._dims.items())))`. It never touches
  `_dims` directly, which is why a plain dict costs it nothing — but it DOES mean a caller who
  mutates `_dims` silently corrupts an already-hashed value. That is why the property returns a
  view rather than the dict.

---

### Task 1: The unit-metadata registry

**Files:**
- Create: `clausal/modules/_unit_registry.py`
- Test: `tests/test_unit_registry.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `UnitInfo` — frozen dataclass: `name: str`, `is_currency: bool = False`,
    `iso_code: str | None = None`, `scale: int | None = None`, `symbol: str | None = None`,
    `historical: bool = False`, `start: str | None = None`, `end: str | None = None`
  - `register(atom: str, info: UnitInfo) -> None` — raises `ValueError` on a conflicting re-register
  - `info(atom: str) -> UnitInfo | None`
  - `is_currency(atom: str) -> bool`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_unit_registry.py
import pytest
from clausal.modules import _unit_registry as R


def test_register_and_look_up():
    R.register("testium", R.UnitInfo(name="testium"))
    assert R.info("testium").name == "testium"
    assert R.is_currency("testium") is False


def test_currency_metadata_round_trips():
    R.register("testbuck", R.UnitInfo(name="testbuck", is_currency=True,
                                      iso_code="TBK", scale=2, symbol="T$"))
    got = R.info("testbuck")
    assert (got.is_currency, got.iso_code, got.scale, got.symbol) == (True, "TBK", 2, "T$")
    assert R.is_currency("testbuck") is True


def test_unknown_atom_is_none_not_an_error():
    assert R.info("no_such_unit") is None
    assert R.is_currency("no_such_unit") is False


def test_re_registering_the_same_info_is_allowed():
    info = R.UnitInfo(name="idem")
    R.register("idem", info)
    R.register("idem", R.UnitInfo(name="idem"))      # equal value, not a conflict


def test_conflicting_re_register_raises():
    R.register("clash", R.UnitInfo(name="clash", scale=2))
    with pytest.raises(ValueError, match="clash"):
        R.register("clash", R.UnitInfo(name="clash", scale=3))
```

- [ ] **Step 2: Run to verify it fails**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_unit_registry.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'clausal.modules._unit_registry'`

- [ ] **Step 3: Write the implementation**

```python
"""Unit metadata, keyed by the unit's ATOM.

A unit was never a predicate: it is a named entry in a table, and the atom is
its name. This module IS that table.

Data-only by design, like ``_ratio_data``: it must never import
``clausal.modules.units``, because importing that builds 84 Quantity constants
and turns the CLP units side channel on for the whole process.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UnitInfo:
    """Everything about a unit that is NOT its dimensions or its ratio.

    Dimensions and ratio live on the quantity and the unit constant; this is
    the display and currency metadata that used to hang off the predicate
    object serving as a dimension key.
    """
    name: str
    is_currency: bool = False
    iso_code: str | None = None
    scale: int | None = None
    symbol: str | None = None
    historical: bool = False
    start: str | None = None
    end: str | None = None


#: atom -> UnitInfo. Global and append-only; see ``register``.
_TABLE: dict[str, UnitInfo] = {}


def register(atom: str, unit_info: UnitInfo) -> None:
    """Record *unit_info* under *atom*.

    Re-registering an EQUAL value is allowed -- module reloads and test
    re-imports do it routinely. A CONFLICTING one raises, because two units
    sharing an atom is exactly the unsoundness
    ``test_unit_identifiers_are_injective`` exists to catch, and silently
    keeping one of them would hide it.
    """
    existing = _TABLE.get(atom)
    if existing is not None and existing != unit_info:
        raise ValueError(
            f"unit atom {atom!r} is already registered with different metadata: "
            f"{existing!r} vs {unit_info!r}")
    _TABLE[atom] = unit_info


def info(atom: str) -> UnitInfo | None:
    """The metadata for *atom*, or None if it names no known unit."""
    return _TABLE.get(atom)


def is_currency(atom: str) -> bool:
    """Whether *atom* names a currency. False for an unknown atom."""
    entry = _TABLE.get(atom)
    return entry is not None and entry.is_currency
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /workspace/clausal-bug-fix/.claude/worktrees/iso-l3 && /workspace/clausal/venv/bin/python -m pytest tests/test_unit_registry.py -q`
Expected: PASS, 5 passed

- [ ] **Step 5: Add the injectivity gate test**

This is the precondition for the entire rekey. It goes in its own file so it reads as a gate
rather than a unit test.

```python
# tests/test_unit_identifier_injective.py
"""The rekey's precondition: one atom per dimension, forever.

If two distinct dimension keys ever share an identifier, rekeying _dims to
atoms SILENTLY MERGES THEM -- two different units become one, and every
dimensional check downstream is wrong without erroring. Measured 2026-09-15:
262 keys -> 262 identifiers, 0 collisions.
"""
import collections
import importlib
import pkgutil

import clausal.modules.countries as countries
from clausal.modules import units
from clausal.terms import _unit_identifier


def _all_dimension_keys():
    keys = {}

    def collect(mod):
        for name in dir(mod):
            value = getattr(mod, name, None)
            dims = getattr(value, "_dims", None)
            if isinstance(dims, dict) or type(dims).__name__ == "mappingproxy":
                for key in dims:
                    keys[id(key)] = key
            if getattr(value, "is_currency", False):
                keys[id(value)] = value

    collect(units)
    for mod_info in pkgutil.iter_modules(countries.__path__):
        if mod_info.name.startswith("_"):
            continue
        collect(importlib.import_module(f"clausal.modules.countries.{mod_info.name}"))
    return list(keys.values())


def test_unit_identifiers_are_injective():
    keys = _all_dimension_keys()
    # positive control: the population must be non-empty, or this test passes
    # by measuring nothing -- the failure mode this lane has hit ten times.
    assert len(keys) > 200, f"only {len(keys)} dimension keys found; the sweep is broken"

    by_identifier = collections.defaultdict(list)
    for key in keys:
        by_identifier[_unit_identifier(key)].append(key)

    collisions = {
        identifier: [getattr(k, "iso_code", None) or getattr(k, "_name", "?") for k in ks]
        for identifier, ks in by_identifier.items()
        if len(ks) > 1
    }
    assert not collisions, f"dimension atoms are not unique: {collisions}"
```

- [ ] **Step 6: Run the gate test**

Run: `cd /workspace/clausal-bug-fix/.claude/worktrees/iso-l3 && /workspace/clausal/venv/bin/python -m pytest tests/test_unit_identifier_injective.py -q -rA`
Expected: PASS, 1 passed

- [ ] **Step 7: Prove the gate test can FAIL**

A test that asserts a property must be shown capable of rejecting its negation, or it is a check
that verifies nothing.

Run:
```bash
cd /workspace/clausal-bug-fix/.claude/worktrees/iso-l3
/workspace/clausal/venv/bin/python - <<'PY'
import collections
# the same assertion, against a deliberately colliding population
by = collections.defaultdict(list); by['metre'] = ['keyA', 'keyB']
collisions = {i: ks for i, ks in by.items() if len(ks) > 1}
assert not collisions, f"dimension atoms are not unique: {collisions}"
PY
```
Expected: `AssertionError: dimension atoms are not unique: {'metre': ['keyA', 'keyB']}`

- [ ] **Step 8: Commit**

```bash
cd /workspace/clausal-bug-fix/.claude/worktrees/iso-l3
git add clausal/modules/_unit_registry.py tests/test_unit_registry.py tests/test_unit_identifier_injective.py
git commit -F - <<'MSG'
the unit-metadata registry, keyed by atom

A unit was never a predicate: it is a named entry in a table and the atom is its
name. This is that table, plus the precondition the whole rekey rests on --
_unit_identifier must be INJECTIVE, or rekeying _dims silently merges two units
into one and every dimensional check downstream is wrong without erroring.

Measured: 262 distinct dimension key objects -> 262 distinct identifiers, 0
collisions, across units plus 181 country modules. Pinned as a permanent gate
test with a positive control on the population size, because a sweep that finds
nothing otherwise passes by measuring nothing.

Data-only, like _ratio_data: it must never import clausal.modules.units, which
would build 84 Quantity constants and turn the CLP units side channel on for the
whole process.

Nothing consumes it yet.
MSG
```

---

### Task 2: `_dims` stored as a plain dict, exposed as a view

**Files:**
- Modify: `clausal/terms.py` — `quantity.__init__` (the `self._dims = MappingProxyType(...)`
  assignment, ~line 2393) and the `dims` property (~line 2418)
- Test: `tests/test_quantity_dims_storage.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `quantity._dims` is a `dict`; `quantity.dims` is a `MappingProxyType` over it.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_quantity_dims_storage.py
import marshal
from types import MappingProxyType

import pytest

from clausal.modules import units
from clausal.terms import Quantity


def test_dims_is_stored_as_a_plain_dict():
    q = Quantity(5, units.metre)
    assert type(q._dims) is dict


def test_dims_property_still_returns_an_immutable_view():
    q = Quantity(5, units.metre)
    assert isinstance(q.dims, MappingProxyType)
    with pytest.raises(TypeError):
        q.dims["metre"] = 99


def test_the_stored_dict_marshals():
    # the mappingproxy was the ONE thing blocking it; a plain dict marshals.
    q = Quantity(5, units.metre)
    assert marshal.loads(marshal.dumps({str(k): v for k, v in q._dims.items()}))


def test_hashing_and_equality_are_unaffected():
    a, b = Quantity(5, units.kilometre), Quantity(5000, units.metre)
    assert a == b and hash(a) == hash(b)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /workspace/clausal-bug-fix/.claude/worktrees/iso-l3 && /workspace/clausal/venv/bin/python -m pytest tests/test_quantity_dims_storage.py -q`
Expected: FAIL on `test_dims_is_stored_as_a_plain_dict` — `assert <class 'mappingproxy'> is dict`

- [ ] **Step 3: Store the dict, return a view**

In `clausal/terms.py`, in `quantity.__init__`, change:

```python
        self._dims = MappingProxyType({k: v for k, v in actual_dims.items() if v != 0})
```

to:

```python
        # A PLAIN DICT, not a mappingproxy. The proxy was the one thing blocking
        # marshalling (a plain {'metre': 1} marshals in 14 bytes), and it was
        # never needed for hashing: __hash__ goes through frozenset(...items())
        # and does not touch _dims. Immutability moves to the `dims` PROPERTY,
        # which is where callers reach it.
        self._dims = {k: v for k, v in actual_dims.items() if v != 0}
```

And change the `dims` property:

```python
    @property
    def dims(self) -> MappingProxyType:
        return self._dims
```

to:

```python
    @property
    def dims(self) -> MappingProxyType:
        # A VIEW over the stored dict. __hash__ is computed from _dims, so a
        # caller mutating it would silently corrupt an already-hashed value --
        # the guarantee has to survive even though the storage is now mutable.
        return MappingProxyType(self._dims)
```

Also, in the `isinstance(dims, Quantity)` branch of `__init__`, `self._dims = dims._dims` now
assigns a plain dict that the two quantities would SHARE. Change it to copy:

```python
            self._dims = dict(dims._dims)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /workspace/clausal-bug-fix/.claude/worktrees/iso-l3 && /workspace/clausal/venv/bin/python -m pytest tests/test_quantity_dims_storage.py -q`
Expected: PASS, 4 passed

- [ ] **Step 5: Run the units test files**

Run:
```bash
cd /workspace/clausal-bug-fix/.claude/worktrees/iso-l3
/workspace/clausal/venv/bin/python -m pytest tests/test_units.py tests/test_currency.py \
  tests/test_currency_minor_units.py tests/test_currency_money.py tests/test_currency_vocabulary.py \
  tests/test_quantity_decimal.py tests/test_quantity_rendering.py tests/test_ratio_units.py \
  tests/test_units_clp.py tests/test_prolog_quantity_units.py -q
```
Expected: no NEW failures versus the same command on the previous commit.

- [ ] **Step 6: Full failure-set gate**

```bash
/home/node/.claude/jobs/af5b4bbe/tmp/gate_iso_l3.sh /home/node/.claude/jobs/af5b4bbe/tmp/t2.raw
/workspace/clausal/venv/bin/python /home/node/.claude/jobs/af5b4bbe/tmp/failure_diff.py \
  /home/node/.claude/jobs/af5b4bbe/tmp/base_rekey.raw /home/node/.claude/jobs/af5b4bbe/tmp/t2.raw
```
Expected: `NEW 0`. Read the extraction SIZES it prints, not the verdict line.

- [ ] **Step 7: Commit**

```bash
cd /workspace/clausal-bug-fix/.claude/worktrees/iso-l3
git add clausal/terms.py tests/test_quantity_dims_storage.py
git commit -F - <<'MSG'
_dims is a plain dict; the `dims` property returns the view

The mappingproxy was the one thing blocking marshalling -- a plain {'metre': 1}
marshals in 14 bytes -- and it was never needed for hashing: __hash__ is
hash((self._value, frozenset(self._dims.items()))), which derives a key and does
not touch _dims. So _dims has ALWAYS been unhashable and a dict costs nothing.

Immutability moves to the PROPERTY, which is where callers reach it. That is not
cosmetic: __hash__ is computed from _dims, so a caller mutating it would
silently corrupt an already-hashed value.

The Quantity-as-dims branch now COPIES rather than aliasing, since a shared
plain dict would let one quantity's mutation reach another's.

Gate: failure-set diff vs base_rekey, NEW 0.
MSG
```

---

### Task 3: Metadata sites read the registry, not the key

**Files:**
- Modify: `clausal/modules/units.py` — `_make_unit_pred_base` (~147), `_make_unit_pred` (~161) to
  `register()` each unit
- Modify: `clausal/modules/countries/_currency.py` — `_make_currency` (~44-59) to `register()`
- Modify: `clausal/terms.py:2396` and `clausal/terms.py:2785`
- Modify: `clausal/logic/constants.py:375`
- Modify: `clausal/modules/currency.py:33`
- Test: `tests/test_unit_metadata_via_registry.py`

**Interfaces:**
- Consumes: `_unit_registry.register`, `.info`, `.is_currency`, `UnitInfo` from Task 1.
- Produces: `clausal/terms.py:_currency_info(key) -> UnitInfo | None` — the single choke point
  that turns a dimension key into its metadata. Task 4 changes only this function's internals.

**Why this task exists and must precede Task 4:** every metadata site is spelled
`getattr(key, "is_currency", False)`. Against a `str` atom that returns `False` — **silently**.
Flipping the keys first would turn every currency into a non-currency with no error anywhere.

**CORRECTION, found while reading the sites (2026-09-15).** The task is bigger than flipping four
predicates, because two sites do not merely TEST the key — they RETURN it as the currency object
and callers then read metadata off it:

* `clausal/modules/currency.py:_currency_of` returns `key`; `_quantize` reads `.scale` and
  `_format_money` reads `.scale`, `.symbol`, `.iso_code`, `._name`. Verified its three callers
  (`:203`, `:217`, `:226`) use `c` for metadata ONLY — never as a dims key or constructor — so
  returning a `UnitInfo` instead is a clean substitution.
* `clausal/terms.py.__format__` sets `cur = key` and passes it to `_format_money`.

`UnitInfo` already carries `scale`, `symbol` and `iso_code`. The one gap is `_format_money`'s
`currency._name`, which `UnitInfo` spells `name` — the same everyday word, since `UnitInfo.name`
is built from `_make_currency`'s `name`. So `_format_money` changes to `.name`.

**NOT a dims-key read; leave both alone:**

* `clausal/modules/currency.py:137` — that `c` is `deref(currency)`, a GOAL ARGUMENT: the unit
  predicate a rulebase passed in, which keeps its attributes.
* `clausal/terms.py` `__init__`'s `getattr(dims, "is_currency", False)` — `dims` is the unit
  predicate the caller passed, not a key.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_unit_metadata_via_registry.py
"""Metadata comes from the REGISTRY, not off the dimension key.

This is what makes Task 4 safe. Every metadata read used to be
getattr(key, "is_currency", False), which against a str atom returns False
SILENTLY -- so flipping keys first would turn every currency into a
non-currency with no error anywhere.
"""
from clausal.modules import _unit_registry as R
from clausal.modules import units
from clausal.modules.countries import european_union
from clausal.terms import Quantity, _currency_info


def test_every_unit_constant_is_registered():
    for name in ("metre", "second", "kilogram", "dimensionless"):
        assert R.info(name) is not None, f"{name} is not in the registry"


def test_a_currency_is_registered_with_its_metadata():
    got = R.info("euro")
    assert got is not None and got.is_currency
    assert (got.iso_code, got.scale, got.symbol) == ("EUR", 2, "€")


def test_a_base_unit_is_registered_and_is_not_a_currency():
    assert R.is_currency("metre") is False


def test_currency_info_resolves_a_dimension_key():
    q = Quantity(1550.00, european_union.euro)
    (key, _exp), = q.dims.items()
    got = _currency_info(key)
    assert got is not None and got.iso_code == "EUR"


def test_currency_info_is_none_for_a_non_currency_dimension():
    q = Quantity(5, units.metre)
    (key, _exp), = q.dims.items()
    assert _currency_info(key) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /workspace/clausal-bug-fix/.claude/worktrees/iso-l3 && /workspace/clausal/venv/bin/python -m pytest tests/test_unit_metadata_via_registry.py -q`
Expected: FAIL — `ImportError: cannot import name '_currency_info' from 'clausal.terms'`

- [ ] **Step 3: Add the choke point in `clausal/terms.py`**

Add next to `_unit_identifier` (~line 2157):

```python
def _currency_info(key):
    """The currency metadata for a dimension *key*, or None.

    THE single place that turns a dimension key into its metadata. It takes a
    key rather than an atom so that it works both before and after the rekey:
    today `key` is a unit predicate, afterwards it is the atom itself, and
    `_unit_identifier` already answers both.

    Every caller used to read `getattr(key, "is_currency", False)` directly.
    That spelling returns False for a str -- SILENTLY -- so it could not
    survive the rekey, and one choke point is what makes the flip a
    one-function change.
    """
    from clausal.modules import _unit_registry          # noqa: PLC0415
    entry = _unit_registry.info(_unit_identifier(key))
    return entry if entry is not None and entry.is_currency else None
```

- [ ] **Step 4: Register every unit at construction**

In `clausal/modules/units.py`, `_make_unit_pred_base`, after `pred._dims = frozen_dims`:

```python
    from clausal.modules import _unit_registry          # noqa: PLC0415
    _unit_registry.register(name, _unit_registry.UnitInfo(name=name))
```

In `_make_unit_pred`, after `pred._dims = frozen_dims`:

```python
    from clausal.modules import _unit_registry          # noqa: PLC0415
    _unit_registry.register(name, _unit_registry.UnitInfo(name=name))
```

In `clausal/modules/countries/_currency.py`, `_make_currency`, immediately before `return pred`:

```python
    from clausal.modules import _unit_registry          # noqa: PLC0415
    from clausal.terms import _unit_identifier          # noqa: PLC0415
    # keyed by the BINDING name, which is what _unit_identifier answers and what
    # a rulebase writes -- not `name`, which `dollar` shares twenty-two ways.
    _unit_registry.register(
        _unit_identifier(pred),
        _unit_registry.UnitInfo(name=name, is_currency=True, iso_code=iso_code,
                                scale=scale, symbol=symbol, historical=historical,
                                start=start, end=end))
```

- [ ] **Step 5: Move the four metadata sites onto the choke point**

`clausal/terms.py:2396` — inside `quantity.__init__`:

```python
            for _k in self._dims:
                if getattr(_k, "is_currency", False):
```
becomes
```python
            for _k in self._dims:
                if _currency_info(_k) is not None:
```

`clausal/terms.py:2785` — inside `__format__`:

```python
            if exp == 1 and getattr(key, "is_currency", False):
                cur = key
```
becomes
```python
            if exp == 1 and _currency_info(key) is not None:
                cur = key
```

`clausal/logic/constants.py:375`:

```python
        if exponent == 1 and getattr(key, "is_currency", False):
```
becomes
```python
        from clausal.terms import _currency_info        # noqa: PLC0415
        if exponent == 1 and _currency_info(key) is not None:
```

`clausal/modules/currency.py:33`:

```python
    if exp == 1 and getattr(key, "is_currency", False):
```
becomes
```python
    from clausal.terms import _currency_info            # noqa: PLC0415
    if exp == 1 and _currency_info(key) is not None:
```

- [ ] **Step 6: Run to verify it passes**

Run: `cd /workspace/clausal-bug-fix/.claude/worktrees/iso-l3 && /workspace/clausal/venv/bin/python -m pytest tests/test_unit_metadata_via_registry.py -q`
Expected: PASS, 5 passed

- [ ] **Step 7: Confirm no `is_currency` read remains on a dimension key**

Run:
```bash
cd /workspace/clausal-bug-fix/.claude/worktrees/iso-l3
grep -rn --include='*.py' 'getattr([_a-z]*k[a-z]*, *["'"'"']is_currency' clausal/ | tee /dev/stderr | wc -l
```
Expected: `0`. The `tee` prints any survivors; the count is the evidence line — read it, not the
absence of output.

Note: `getattr(dims, "is_currency", False)` in `quantity.__init__` (~2401) is NOT a dimension-key
read — `dims` there is the unit predicate passed in by the caller, not a key. Leave it.

- [ ] **Step 8: Full failure-set gate**

```bash
/home/node/.claude/jobs/af5b4bbe/tmp/gate_iso_l3.sh /home/node/.claude/jobs/af5b4bbe/tmp/t3.raw
/workspace/clausal/venv/bin/python /home/node/.claude/jobs/af5b4bbe/tmp/failure_diff.py \
  /home/node/.claude/jobs/af5b4bbe/tmp/base_rekey.raw /home/node/.claude/jobs/af5b4bbe/tmp/t3.raw
```
Expected: `NEW 0`.

- [ ] **Step 9: Commit**

```bash
cd /workspace/clausal-bug-fix/.claude/worktrees/iso-l3
git add clausal/terms.py clausal/modules/units.py clausal/modules/countries/_currency.py \
        clausal/logic/constants.py clausal/modules/currency.py \
        tests/test_unit_metadata_via_registry.py
git commit -F - <<'MSG'
unit metadata comes from the registry, not off the dimension key

Behaviour-preserving, and it is what makes the rekey safe. Every metadata read
was spelled getattr(key, "is_currency", False). Against a str atom that returns
False -- SILENTLY -- so flipping the keys first would have turned every currency
into a non-currency with no error anywhere.

_currency_info(key) is now the single choke point. It takes a KEY rather than an
atom deliberately, so it works on both sides of the flip: _unit_identifier
already answers for a predicate and for the atom itself, so Task 4 changes this
one function's internals and nothing else.

Four sites moved: terms.py __init__ and __format__, constants.py, currency.py.
The getattr(dims, ...) in __init__ is NOT a key read -- dims there is the unit
predicate the caller passed -- and is left alone.

Gate: failure-set diff vs base_rekey, NEW 0.
MSG
```

---

### Task 4: Flip the keys to atoms

**Files:**
- Modify: `clausal/modules/units.py:147-148` (`_make_unit_pred_base`), `:161-163` (`_make_unit_pred`)
- Modify: `clausal/modules/countries/_currency.py:53`
- Modify: `clausal/terms.py` — `_currency_info` internals, `_dim_name`, `_unit_identifier`
- Test: `tests/test_dims_keyed_by_atoms.py`

**Interfaces:**
- Consumes: `_currency_info` from Task 3; the registry from Task 1.
- Produces: `quantity._dims` keyed by `str`; `sorted(q._dims.items())` works.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dims_keyed_by_atoms.py
import marshal

from clausal.modules import units
from clausal.modules.countries import european_union
from clausal.terms import Quantity


def test_dims_keys_are_plain_strings():
    q = Quantity(5, units.metre)
    assert [type(k) for k in q.dims] == [str]
    assert list(q.dims) == ["metre"]


def test_a_currency_key_is_its_binding_atom():
    q = Quantity(1550.00, european_union.euro)
    assert list(q.dims) == ["euro"]


def test_the_whole_dims_dict_now_marshals_unchanged():
    q = Quantity(5, units.metre)
    assert marshal.loads(marshal.dumps(q._dims)) == {"metre": 1}


def test_dims_can_now_be_SORTED():
    # sorted() raised TypeError on predicate-object keys: '<' not supported
    # between instances of '_UnitsPredicate'. That is why the canonical sort
    # was downstream of this rekey.
    q = Quantity(1, units.metre) * Quantity(1, units.second)
    assert sorted(q._dims.items()) == [("metre", 1), ("second", 1)]


def test_the_wire_form_falls_out_of_the_sorted_items():
    q = Quantity(1, units.metre) * Quantity(1, units.second)
    wire = ("dimensions", *sorted(q._dims.items()))
    assert wire == ("dimensions", ("metre", 1), ("second", 1))
    assert dict(wire[1:]) == q._dims          # dict() accepts the pair form


def test_currency_behaviour_survives_the_flip():
    q = Quantity(155000, european_union.eur_cent)
    assert str(q) == "1550.00 (euro)"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /workspace/clausal-bug-fix/.claude/worktrees/iso-l3 && /workspace/clausal/venv/bin/python -m pytest tests/test_dims_keyed_by_atoms.py -q`
Expected: FAIL on `test_dims_keys_are_plain_strings` — `[<class '_UnitsPredicate'>] != [str]`

- [ ] **Step 3: Flip the three construction sites**

`clausal/modules/units.py`, `_make_unit_pred_base` — replace:
```python
    frozen_dims = {pred: 1}   # pred already exists; self-referential key is fine
    pred._dims = frozen_dims
```
with:
```python
    # Keyed by the ATOM, not by `pred`. A unit was never a predicate: it is a
    # named entry in the registry, and the atom is its name. This is also what
    # makes _dims marshal and makes sorted() work on it.
    pred._dims = {name: 1}
```

`clausal/modules/units.py`, `_make_unit_pred` — `dims` arrives keyed by predicate objects from
callers such as `_make_unit_pred("newton", {kilogram: 1, metre: 1, second: -2})`. Normalise:
```python
    frozen_dims = {k: v for k, v in dims.items() if v != 0}
```
becomes:
```python
    from clausal.terms import _unit_identifier          # noqa: PLC0415
    # Callers still pass {kilogram: 1, metre: 1, ...} -- predicate objects, for
    # readability at the definition site. Normalise to atoms here so there is
    # ONE place that knows both spellings.
    frozen_dims = {
        (k if type(k) is str else _unit_identifier(k)): v
        for k, v in dims.items() if v != 0
    }
```

`clausal/modules/countries/_currency.py` — replace:
```python
    pred._dims = {pred: 1}          # self-referential key — a base dimension
```
with:
```python
    # The binding atom, not `pred`: a currency is a base dimension whose NAME
    # is what a rulebase writes. `name` is the everyday word, which `dollar`
    # shares twenty-two ways; the binding is the identifier.
    pred._dims = {}                 # set below, once the binding is known
```
and, immediately after the `_unit_registry.register(...)` call added in Task 3, before `return pred`:
```python
    pred._dims = {_unit_identifier(pred): 1}
```

- [ ] **Step 4: Make `_dim_name` and `_unit_identifier` atom-aware**

`clausal/terms.py:_dim_name` already handles a `str` via its `str(k)` fallback — leave it.

`_unit_identifier` reads `getattr(key, "iso_code", None)`, which is `None` for a `str`, so it falls
through to `_dim_name` and returns the atom. Correct as written. Add the note:

```python
    # An ATOM key answers itself: getattr(str, "iso_code", None) is None, so it
    # falls through to _dim_name, which returns the string. That is why this
    # function works unchanged on both sides of the rekey.
    code = getattr(key, "iso_code", None)
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd /workspace/clausal-bug-fix/.claude/worktrees/iso-l3 && /workspace/clausal/venv/bin/python -m pytest tests/test_dims_keyed_by_atoms.py -q`
Expected: PASS, 6 passed

- [ ] **Step 6: Run every units test file**

Run:
```bash
cd /workspace/clausal-bug-fix/.claude/worktrees/iso-l3
/workspace/clausal/venv/bin/python -m pytest tests/test_units.py tests/test_currency.py \
  tests/test_currency_minor_units.py tests/test_currency_money.py tests/test_currency_vocabulary.py \
  tests/test_module_constant_units.py tests/test_prolog_quantity_units.py tests/test_quantity_decimal.py \
  tests/test_quantity_head_literal.py tests/test_quantity_rendering.py tests/test_ratio_units.py \
  tests/test_units.py tests/test_units_clp.py tests/test_units_lowercase_names.py \
  tests/test_unit_identifier_injective.py -q
```
Expected: no NEW failures versus the same command at Task 3's commit. Record both lists and diff
them; do not compare counts.

- [ ] **Step 7: Full failure-set gate**

```bash
/home/node/.claude/jobs/af5b4bbe/tmp/gate_iso_l3.sh /home/node/.claude/jobs/af5b4bbe/tmp/t4.raw
/workspace/clausal/venv/bin/python /home/node/.claude/jobs/af5b4bbe/tmp/failure_diff.py \
  /home/node/.claude/jobs/af5b4bbe/tmp/base_rekey.raw /home/node/.claude/jobs/af5b4bbe/tmp/t4.raw
```
Expected: `NEW 0`. This is the task most likely to move the set — `_dims` is touched by 114
references across 8 files, and `units_clp.py` (10) and `arithmetic.py` (5) are not edited by this
plan, so they are where a break would surface.

- [ ] **Step 8: Commit**

```bash
cd /workspace/clausal-bug-fix/.claude/worktrees/iso-l3
git add clausal/modules/units.py clausal/modules/countries/_currency.py clausal/terms.py \
        tests/test_dims_keyed_by_atoms.py
git commit -F - <<'MSG'
_dims is keyed by ATOMS

The narrow thing P4 actually needs from quantity. A unit was never a predicate:
it is a named entry in a table and the atom is its name.

Three construction sites flipped. _make_unit_pred still ACCEPTS predicate-keyed
dims, because {kilogram: 1, metre: 1, second: -2} is how the definitions read,
and normalises to atoms in one place rather than rewriting 84 definitions.

_unit_identifier and _dim_name work unchanged on both sides: getattr(str,
"iso_code", None) is None, so an atom falls through and answers itself.

What this buys, measured: _dims marshals (the object still cannot -- marshal
takes only basic types -- but the VALUE is now true data), and sorted() works on
it, where predicate keys raised TypeError: '<' not supported between instances
of '_UnitsPredicate'. The canonical sort was downstream of this commit.

Gate: failure-set diff vs base_rekey, NEW 0.
MSG
```

---

## Not in this plan, deliberately

- **The transfer form, the registry TO_TERM/FROM_TERM entries, and `quantity_number/2`.** They sit
  on top of this and want their own plan.
- **Promotion.** Nothing here leaves `feat/iso-l3-lowering-2026-09-14`. Units are live corpus
  vocabulary, so promotion needs the ORACLE gate — harness-batch-lane's 28 sealed scorers — and
  `eu/procurement/selection_criteria` is the canary to run first, being the one units-DECLARING
  domain with an unexplained reading.
- **`units_clp.py` and `arithmetic.py`.** Not edited, but they hold 15 `_dims` references between
  them and are where a rekey break would surface. Task 4's gate is what covers them.
