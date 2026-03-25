# Clausal — Crypto Modules (`hash`, `hmac`, `pbkdf2`)

## Overview

Three small modules wrapping Python's `hashlib` and `hmac` stdlib for
cryptographic hashing, message authentication, and key derivation. All modules
use only the standard library — no third-party dependencies.

```clausal
-import_from(py.hash, [Hash])
-import_from(py.hmac, [Sign, Verify])
-import_from(py.pbkdf2, [Derive])

CheckIntegrity(DATA, EXPECTED) <- (
    Hash("sha256", DATA, COMPUTED),
    COMPUTED == EXPECTED
)

SignMessage(KEY, MSG, SIG) <- Sign(KEY, MSG, SIG)

VerifyMessage(KEY, MSG, SIG) <- Verify(KEY, MSG, SIG)
```

---

## `py.hash` — Cryptographic Hashing

```clausal
-import_from(py.hash, [Hash, HashBytes])
```

| Predicate | Mode | Description |
|-----------|------|-------------|
| `Hash(Algorithm, Data, Hex)` | `+Algo, +Data, -Hex` | Hex digest via `hashlib` |
| `HashBytes(Algorithm, Data, Bytes)` | `+Algo, +Data, -Bytes` | Raw digest bytes |

**Supported algorithms:** `"sha256"`, `"sha512"`, `"md5"`, `"sha1"`, `"sha384"`,
`"sha3_256"`, `"sha3_512"`, `"blake2b"`, `"blake2s"` (anything `hashlib.new()` accepts).

**Data** can be a string (UTF-8 encoded) or `bytes`.

```clausal
# skip
Hash("sha256", "abc", HEX)
# HEX = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"

Hash("md5", "", HEX)
# HEX = "d41d8cd98f00b204e9800998ecf8427e"

HashBytes("sha256", "abc", RAW)
# RAW is 32 bytes
```

Fails silently if the algorithm is unknown, or if `Algorithm` or `Data` is unbound.

---

## `py.hmac` — Message Authentication

```clausal
-import_from(py.hmac, [Sign, Verify])
```

| Predicate | Mode | Description |
|-----------|------|-------------|
| `Sign(Key, Data, Hex)` | `+Key, +Data, -Hex` | HMAC-SHA256 signature |
| `Sign(Algorithm, Key, Data, Hex)` | `+Algo, +Key, +Data, -Hex` | HMAC with specified algorithm |
| `Verify(Key, Data, Hex)` | `+Key, +Data, +Hex` | Verify HMAC-SHA256 (constant-time) |
| `Verify(Algorithm, Key, Data, Hex)` | `+Algo, +Key, +Data, +Hex` | Verify with specified algorithm |

`Key` and `Data` can be strings (UTF-8 encoded) or `bytes`. `Verify` uses
`hmac.compare_digest` for constant-time comparison.

```clausal
# skip
Sign("secret-key", "message", SIG)
Verify("secret-key", "message", SIG)   # succeeds

Sign("sha512", "key", "data", SIG)     # SHA-512 HMAC
```

---

## `py.pbkdf2` — Key Derivation

```clausal
-import_from(py.pbkdf2, [Derive])
```

| Predicate | Mode | Description |
|-----------|------|-------------|
| `Derive(Password, Salt, Iterations, DerivedKey)` | `+Pw, +Salt, +Iter, -DK` | PBKDF2-HMAC-SHA256, 32-byte key |
| `Derive(Password, Salt, Iterations, KeyLength, DerivedKey)` | `+Pw, +Salt, +Iter, +KL, -DK` | Custom key length |

`DerivedKey` is a hex string. `Password` and `Salt` can be strings or `bytes`.
`Iterations` must be a positive integer.

```clausal
# skip
Derive("password", "salt", 100000, HASH)
# HASH is a 64-character hex string (32 bytes)

Derive("password", "salt", 100000, 64, HASH)
# HASH is a 128-character hex string (64 bytes)
```

---

??? example "Examples"

    ### File integrity check

    ```clausal
# skip
    -import_from(py.hash, [Hash])
    -import_from(py.files, [ReadFileToString])

    FileHash(PATH, HASH) <- (
        ReadFileToString(PATH, CONTENT),
        Hash("sha256", CONTENT, HASH)
    )
    ```

    ### API request signing

    ```clausal
# skip
    -import_from(py.hmac, [Sign])

    SignedRequest(KEY, BODY, SIGNATURE) <- (
        Sign("sha256", KEY, BODY, SIGNATURE)
    )
    ```

    ### Password hashing

    ```clausal
# skip
    -import_from(py.pbkdf2, [Derive])

    HashPassword(PASSWORD, SALT, HASH) <- Derive(PASSWORD, SALT, 100000, HASH)
    ```

---

*See also: [Python Interop](python_integration.md) — `++()` escape for
additional cryptography operations · [UUID](uuid.md) — UUID generation with
hash-based variants (v3, v5).*
