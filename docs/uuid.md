# Clausal Prolog — UUIDs (`uuid` module)

Examples on this page are [Clausal Prolog](clausal_prolog.md) (`.clausal`),
which uses ISO Prolog syntax.

## Overview

The `uuid` module provides predicates for generating, converting, and inspecting UUIDs backed by Python's `uuid` module. It produces and consumes real `uuid.UUID` objects.

```clausal
:- use_module(library(py_uuid), [uuid_v4/1, uuid_str/2]).

make_id(ID) :-
    uuid_v4(U),
    uuid_str(U, ID).

main :-
    make_id(ID),
    format("Generated ID: ~s~n", [ID]).

test("make_id") :-
    make_id(ID),
    length(ID, 36).
```

Or via [module import](import.md):

```clausal
:- use_module(library(py_uuid)).

main :-
    py_uuid:uuid_v4(U),
    py_uuid:uuid_str(U, S),
    format("~s~n", [S]).

test("qualified calls") :-
    py_uuid:uuid_v4(U),
    py_uuid:is_uuid(U).
```

---

## Import

```clausal
:- use_module(library(py_uuid), [
    uuid_v4/1, uuid_v1/1, uuid_v3/3, uuid_v5/3,
    uuid_str/2, uuid_hex/2, uuid_urn/2, uuid_bytes/2, uuid_int/2,
    uuid_version/2, uuid_fields/7, is_uuid/1
]).
```

A `.clausal` file reaches the module through its library facade,
`library(py_uuid)`. The module name is `uuid` in the [seam](syntax.md),
`-import_from(uuid, [...])` (internally mapped to `uuid_mod` to avoid
shadowing Python's stdlib).

---

## Generation predicates

| Predicate | Mode | Description |
|-----------|------|-------------|
| `uuid_v4(U)` | `-U` | Random v4 UUID |
| `uuid_v1(U)` | `-U` | Time-based v1 UUID |
| `uuid_v3(NS, NAME, U)` | `+NS, +NAME, -U` | MD5 namespace UUID |
| `uuid_v5(NS, NAME, U)` | `+NS, +NAME, -U` | SHA-1 namespace UUID |

### Namespace aliases

For `uuid_v3` and `uuid_v5`, the namespace argument accepts an alias or a raw `uuid.UUID` object. An
alias is an atom, or the same name as a string (`"dns"`):

| Alias | UUID constant |
|-------|---------------|
| `dns` | `uuid.NAMESPACE_DNS` |
| `url` | `uuid.NAMESPACE_URL` |
| `oid` | `uuid.NAMESPACE_OID` |
| `x500` | `uuid.NAMESPACE_X500` |

```text
--8<-- "tests/fixtures/docs/uuid_sigs.txt:generation_examples"
```

---

## Conversion predicates

All conversion predicates are **bidirectional**: pass a ground UUID to decompose, or a ground representation to construct via [unification](syntax.md).

| Predicate | Mode | Description |
|-----------|------|-------------|
| `uuid_str(U, S)` | `?U, ?S` | UUID ↔ hyphenated string (`"550e8400-e29b-..."`) |
| `uuid_hex(U, H)` | `?U, ?H` | UUID ↔ 32-char hex string |
| `uuid_urn(U, URN)` | `?U, ?URN` | UUID ↔ URN string (`"urn:uuid:..."`) |
| `uuid_bytes(U, B)` | `?U, ?B` | UUID ↔ 16-byte `bytes` object |
| `uuid_int(U, N)` | `?U, ?N` | UUID ↔ 128-bit integer |

```text
--8<-- "tests/fixtures/docs/uuid_sigs.txt:conversion_examples"
```

---

## Inspection predicates

| Predicate | Mode | Description |
|-----------|------|-------------|
| `uuid_version(U, V)` | `+U, -V` | Extract version number (1, 3, 4, 5) |
| `uuid_fields(U, TL, TM, TH, CSH, CSL, NODE)` | `+U, -TL, -TM, -TH, -CSH, -CSL, -NODE` | Decompose into 6 integer fields |
| `is_uuid(U)` | `+U` | Type test — succeeds if U is a `uuid.UUID` |

```text
--8<-- "tests/fixtures/docs/uuid_sigs.txt:inspection_examples"
```

---

??? example "Examples"

    ### Session tokens

    ```clausal
    --8<-- "tests/fixtures/docs/uuid_examples.clausal:session_tokens"
    ```

    ### Deterministic IDs

    ```clausal
    --8<-- "tests/fixtures/docs/uuid_examples.clausal:deterministic_ids"
    ```

---

*See also: [Python Interop](python_integration.md) — the seam's `++()` escape for additional UUID operations · [Database Ops](database_ops.md) — using UUIDs as fact keys.*
