# Clausal Prolog — UUIDs (`uuid` module)

## Overview

The `uuid` module provides predicates for generating, converting, and inspecting UUIDs backed by Python's `uuid` module. It produces and consumes real `uuid.UUID` objects.

```seam
-import_from(uuid, [uuid_v4, uuid_str, uuid_version, is_uuid])

make_id(ID) <- (
    uuid_v4(U),
    uuid_str(U, ID)
)

main <- (
    make_id(ID),
    ++print(f"Generated ID: {ID}")
)
```

Or via [module import](import.md):

```seam
-import_module(uuid)

main <- (
    uuid.uuid_v4(U),
    uuid.uuid_str(U, S),
    ++print(S)
)
```

---

## Import

```seam
-import_from(uuid, [
    uuid_v4, uuid_v1, uuid_v3, uuid_v5,
    uuid_str, uuid_hex, uuid_urn, uuid_bytes, uuid_int,
    uuid_version, uuid_fields, is_uuid
])
```

The module name is `uuid` in the seam (internally mapped to `uuid_mod` to avoid shadowing Python's stdlib).

---

## Generation predicates

| Predicate | Mode | Description |
|-----------|------|-------------|
| `uuid_v4(U)` | `-U` | Random v4 UUID |
| `uuid_v1(U)` | `-U` | Time-based v1 UUID |
| `uuid_v3(NS, NAME, U)` | `+NS, +NAME, -U` | MD5 namespace UUID |
| `uuid_v5(NS, NAME, U)` | `+NS, +NAME, -U` | SHA-1 namespace UUID |

### Namespace aliases

For `uuid_v3` and `uuid_v5`, the namespace argument accepts string aliases or raw `uuid.UUID` objects:

| Alias | UUID constant |
|-------|---------------|
| `"dns"` | `uuid.NAMESPACE_DNS` |
| `"url"` | `uuid.NAMESPACE_URL` |
| `"oid"` | `uuid.NAMESPACE_OID` |
| `"x500"` | `uuid.NAMESPACE_X500` |

```seam
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

```seam
--8<-- "tests/fixtures/docs/uuid_sigs.txt:conversion_examples"
```

---

## Inspection predicates

| Predicate | Mode | Description |
|-----------|------|-------------|
| `uuid_version(U, V)` | `+U, -V` | Extract version number (1, 3, 4, 5) |
| `uuid_fields(U, TL, TM, TH, CSH, CSL, NODE)` | `+U, -TL, -TM, -TH, -CSH, -CSL, -NODE` | Decompose into 6 integer fields |
| `is_uuid(U)` | `+U` | Type test — succeeds if U is a `uuid.UUID` |

```seam
--8<-- "tests/fixtures/docs/uuid_sigs.txt:inspection_examples"
```

---

??? example "Examples"

    ### Session tokens

    ```seam
    --8<-- "tests/fixtures/docs/uuid_sigs.txt:session_tokens"
    ```

    ### Deterministic IDs

    ```seam
    --8<-- "tests/fixtures/docs/uuid_sigs.txt:deterministic_ids"
    ```

---

*See also: [Python Interop](python_integration.md) — `++()` escape for additional UUID operations · [Database Ops](database_ops.md) — using UUIDs as fact keys.*
