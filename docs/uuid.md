# Clausal — UUIDs (`uuid` module)

## Overview

The `uuid` module provides predicates for generating, converting, and inspecting UUIDs backed by Python's `uuid` module. It produces and consumes real `uuid.UUID` objects.

```clausal
-import_from(uuid, [UUIDv4, UUIDStr, UUIDVersion, IsUUID])

MakeId(ID) <- (
    UUIDv4(U),
    UUIDStr(U, ID)
)

Main <- (
    MakeId(ID),
    ++print(f"Generated ID: {ID}")
)
```

Or via [module import](import.md):

```clausal
-import_module(uuid)

Main <- (
    uuid.UUIDv4(U),
    uuid.UUIDStr(U, S),
    ++print(S)
)
```

---

## Import

```clausal
-import_from(uuid, [
    UUIDv4, UUIDv1, UUIDv3, UUIDv5,
    UUIDStr, UUIDHex, UUIDUrn, UUIDBytes, UUIDInt,
    UUIDVersion, UUIDFields, IsUUID
])
```

The module name is `uuid` in Clausal (internally mapped to `uuid_mod` to avoid shadowing Python's stdlib).

---

## Generation predicates

| Predicate | Mode | Description |
|-----------|------|-------------|
| `UUIDv4(U)` | `-U` | Random v4 UUID |
| `UUIDv1(U)` | `-U` | Time-based v1 UUID |
| `UUIDv3(NS, NAME, U)` | `+NS, +NAME, -U` | MD5 namespace UUID |
| `UUIDv5(NS, NAME, U)` | `+NS, +NAME, -U` | SHA-1 namespace UUID |

### Namespace aliases

For `UUIDv3` and `UUIDv5`, the namespace argument accepts string aliases or raw `uuid.UUID` objects:

| Alias | UUID constant |
|-------|---------------|
| `"dns"` | `uuid.NAMESPACE_DNS` |
| `"url"` | `uuid.NAMESPACE_URL` |
| `"oid"` | `uuid.NAMESPACE_OID` |
| `"x500"` | `uuid.NAMESPACE_X500` |

```clausal
--8<-- "tests/fixtures/docs/uuid_sigs.txt:generation_examples"
```

---

## Conversion predicates

All conversion predicates are **bidirectional**: pass a ground UUID to decompose, or a ground representation to construct via [unification](syntax.md).

| Predicate | Mode | Description |
|-----------|------|-------------|
| `UUIDStr(U, S)` | `?U, ?S` | UUID ↔ hyphenated string (`"550e8400-e29b-..."`) |
| `UUIDHex(U, H)` | `?U, ?H` | UUID ↔ 32-char hex string |
| `UUIDUrn(U, URN)` | `?U, ?URN` | UUID ↔ URN string (`"urn:uuid:..."`) |
| `UUIDBytes(U, B)` | `?U, ?B` | UUID ↔ 16-byte `bytes` object |
| `UUIDInt(U, N)` | `?U, ?N` | UUID ↔ 128-bit integer |

```clausal
--8<-- "tests/fixtures/docs/uuid_sigs.txt:conversion_examples"
```

---

## Inspection predicates

| Predicate | Mode | Description |
|-----------|------|-------------|
| `UUIDVersion(U, V)` | `+U, -V` | Extract version number (1, 3, 4, 5) |
| `UUIDFields(U, TL, TM, TH, CSH, CSL, NODE)` | `+U, -TL, -TM, -TH, -CSH, -CSL, -NODE` | Decompose into 6 integer fields |
| `IsUUID(U)` | `+U` | Type test — succeeds if U is a `uuid.UUID` |

```clausal
--8<-- "tests/fixtures/docs/uuid_sigs.txt:inspection_examples"
```

---

??? example "Examples"

    ### Session tokens

    ```clausal
    --8<-- "tests/fixtures/docs/uuid_sigs.txt:session_tokens"
    ```

    ### Deterministic IDs

    ```clausal
    --8<-- "tests/fixtures/docs/uuid_sigs.txt:deterministic_ids"
    ```

---

*See also: [Python Interop](python_integration.md) — `++()` escape for additional UUID operations · [Database Ops](database_ops.md) — using UUIDs as fact keys.*
