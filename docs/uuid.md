# Clausal — UUIDs (`uuid` module)

## Overview

The `uuid` module provides predicates for generating, converting, and inspecting UUIDs backed by Python's `uuid` module. It produces and consumes real `uuid.UUID` objects.

```clausal
-import_from(uuid, [Uuid4, UuidStr, UuidVersion, IsUuid])

MakeId(Id_) <- (
    Uuid4(U_) and
    UuidStr(U_, Id_)
)

Main <- (
    MakeId(Id_) and
    ++print(f"Generated ID: {Id_}")
)
```

Or via module import:

```clausal
-import_module(uuid)

Main <- (
    uuid.Uuid4(U_) and
    uuid.UuidStr(U_, S_) and
    ++print(S_)
)
```

---

## Import

```clausal
-import_from(uuid, [
    Uuid4, Uuid1, Uuid3, Uuid5,
    UuidStr, UuidHex, UuidUrn, UuidBytes, UuidInt,
    UuidVersion, UuidFields, IsUuid
])
```

The module name is `uuid` in Clausal (internally mapped to `uuid_mod` to avoid shadowing Python's stdlib).

---

## Generation predicates

| Predicate | Mode | Description |
|-----------|------|-------------|
| `Uuid4(U)` | `-U` | Random v4 UUID |
| `Uuid1(U)` | `-U` | Time-based v1 UUID |
| `Uuid3(Ns, Name, U)` | `+Ns, +Name, -U` | MD5 namespace UUID |
| `Uuid5(Ns, Name, U)` | `+Ns, +Name, -U` | SHA-1 namespace UUID |

### Namespace aliases

For `Uuid3` and `Uuid5`, the namespace argument accepts string aliases or raw `uuid.UUID` objects:

| Alias | UUID constant |
|-------|---------------|
| `"dns"` | `uuid.NAMESPACE_DNS` |
| `"url"` | `uuid.NAMESPACE_URL` |
| `"oid"` | `uuid.NAMESPACE_OID` |
| `"x500"` | `uuid.NAMESPACE_X500` |

```clausal
Uuid3("dns", "example.com", U_)
Uuid5("url", "https://example.com", U_)
```

---

## Conversion predicates

All conversion predicates are **bidirectional**: pass a ground UUID to decompose, or a ground representation to construct.

| Predicate | Mode | Description |
|-----------|------|-------------|
| `UuidStr(U, S)` | `?U, ?S` | UUID ↔ hyphenated string (`"550e8400-e29b-..."`) |
| `UuidHex(U, H)` | `?U, ?H` | UUID ↔ 32-char hex string |
| `UuidUrn(U, Urn)` | `?U, ?Urn` | UUID ↔ URN string (`"urn:uuid:..."`) |
| `UuidBytes(U, B)` | `?U, ?B` | UUID ↔ 16-byte `bytes` object |
| `UuidInt(U, N)` | `?U, ?N` | UUID ↔ 128-bit integer |

```clausal
% Generate a UUID and get its string form
Uuid4(U_) and UuidStr(U_, S_)

% Parse a UUID from a string
UuidStr(U_, "550e8400-e29b-41d4-a716-446655440000")

% Convert to hex
UuidHex(U_, "550e8400e29b41d4a716446655440000")
```

---

## Inspection predicates

| Predicate | Mode | Description |
|-----------|------|-------------|
| `UuidVersion(U, V)` | `+U, -V` | Extract version number (1, 3, 4, 5) |
| `UuidFields(U, TL, TM, TH, CSH, CSL, Node)` | `+U, -TL, -TM, -TH, -CSH, -CSL, -Node` | Decompose into 6 integer fields |
| `IsUuid(U)` | `+U` | Type test — succeeds if U is a `uuid.UUID` |

```clausal
% Check that a UUID is version 4
Uuid4(U_) and UuidVersion(U_, 4)

% Type-check
IsUuid(U_)
```

---

## Examples

### Session tokens

```clausal
-import_from(uuid, [Uuid4, UuidStr])

NewSession(UserId_, Token_) <- (
    Uuid4(U_) and
    UuidStr(U_, Token_)
)
```

### Deterministic IDs

```clausal
-import_from(uuid, [Uuid5, UuidStr])

ResourceId(Type_, Name_, Id_) <- (
    Uuid5("url", Name_, U_) and
    UuidStr(U_, Id_)
)
```
