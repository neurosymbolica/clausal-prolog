# `functor/3` mints an atom from a @dataclass CLASS instead of refusing it

**Found:** 2026-09-24, while verifying that F2b's migration of rows 43/44 had
not widened the ISO atomicity gate. **It had not — main does the same**, so
this is PRE-EXISTING, not a migration regression.

## Measured, identically on main and on the F2b branch

    @dataclasses.dataclass
    class SomeDataclass: x: int

    _construct_named(SomeDataclass, (), "functor/3")  ->  ('SomeDataclass',)
    _construct_named("plain_atom",  (), "functor/3")  ->  ('plain_atom',)
    _construct_named(42,            (), "functor/3")  ->  LogicException type_error

So an `int` is refused as non-atomic, but a Python `@dataclass` CLASS is
silently turned into the atom named after it.

## Why

`field_names_for(SomeDataclass)` answers `('x',)` via its @dataclass arm, so
`_ctor_fields is not None`; the `isinstance(name_val, type)` gate (added in
W4b-1's final fix wave, `98753d39`) then admits it to the class-construction
arm; the requested arity (0) does not match the field count (1), so it falls
through to minting `name_val.__name__` as an atom. The ISO atomicity gate
further down — which lists `PredicateMeta` beside `int`/`float`/`bool`/`bytes`
— is never reached.

## Is it wrong?

Probably. A Python dataclass class is not an atomic term, and `functor/3`'s
own comment cites ISO 8.5.1.3(e) for refusing non-atomic culprits. Binding
`T` to an atom named after an arbitrary Python class is a silent coercion
nobody chose.

**Severity is low**: a dataclass class can only reach a goal from Python, not
from `.clausal` source, so no conforming program can trigger it. It is a
Python-boundary sharp edge, not a language bug.

## Not fixed here because

It is outside F2b's scope (F2b migrated the binding test, not the
construction path) and the fix is a judgement call: either the @dataclass arm
should not admit a class to term CONSTRUCTION at all, or the arity-mismatch
fallthrough should raise rather than mint. Both are behaviour changes to a
builtin and deserve their own decision.
