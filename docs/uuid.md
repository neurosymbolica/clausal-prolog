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

Or via module import:

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
# skip
UUIDv3("dns", "example.com", U)
UUIDv5("url", "https://example.com", U)
```

---

## Conversion predicates

All conversion predicates are **bidirectional**: pass a ground UUID to decompose, or a ground representation to construct.

| Predicate | Mode | Description |
|-----------|------|-------------|
| `UUIDStr(U, S)` | `?U, ?S` | UUID ↔ hyphenated string (`"550e8400-e29b-..."`) |
| `UUIDHex(U, H)` | `?U, ?H` | UUID ↔ 32-char hex string |
| `UUIDUrn(U, URN)` | `?U, ?URN` | UUID ↔ URN string (`"urn:uuid:..."`) |
| `UUIDBytes(U, B)` | `?U, ?B` | UUID ↔ 16-byte `bytes` object |
| `UUIDInt(U, N)` | `?U, ?N` | UUID ↔ 128-bit integer |

```clausal
# skip
% Generate a UUID and get its string form
UUIDv4(U), UUIDStr(U, S)

% Parse a UUID from a string
UUIDStr(U, "550e8400-e29b-41d4-a716-446655440000")

% Convert to hex
UUIDHex(U, "550e8400e29b41d4a716446655440000")
```

---

## Inspection predicates

| Predicate | Mode | Description |
|-----------|------|-------------|
| `UUIDVersion(U, V)` | `+U, -V` | Extract version number (1, 3, 4, 5) |
| `UUIDFields(U, TL, TM, TH, CSH, CSL, NODE)` | `+U, -TL, -TM, -TH, -CSH, -CSL, -NODE` | Decompose into 6 integer fields |
| `IsUUID(U)` | `+U` | Type test — succeeds if U is a `uuid.UUID` |

```clausal
# skip
% Check that a UUID is version 4
UUIDv4(U), UUIDVersion(U, 4)

% Type-check
IsUUID(U)
```

---

??? example "Examples"

    ### Session tokens

    ```clausal
# skip
    -import_from(uuid, [UUIDv4, UUIDStr])
    
    NewSession(USERID, TOKEN) <- (
        UUIDv4(U),
        UUIDStr(U, TOKEN)
    )
    ```

    ### Deterministic IDs

    ```clausal
# skip
    -import_from(uuid, [UUIDv5, UUIDStr])
    
    ResourceId(TYPE, NAME, ID) <- (
        UUIDv5("url", NAME, U),
        UUIDStr(U, ID)
    )
    ```
