# Clausal — Crypto Modules (`hash`, `hmac`, `pbkdf2`)

## Overview

Three small modules wrapping Python's `hashlib` and `hmac` stdlib for
cryptographic hashing, message authentication, and key derivation. All modules
use only the standard library — no third-party dependencies.

```clausal
-import_from(py.hash, [hash])
-import_from(py.hmac, [sign, verify])
-import_from(py.pbkdf2, [derive])

check_integrity(DATA, EXPECTED) <- (
    hash("sha256", DATA, COMPUTED),
    COMPUTED == EXPECTED
)

sign_message(KEY, MSG, SIG) <- sign(KEY, MSG, SIG)

verify_message(KEY, MSG, SIG) <- verify(KEY, MSG, SIG)
```

---

## `py.hash` — Cryptographic Hashing

```clausal
-import_from(py.hash, [hash, hash_bytes])
```

| Predicate | Mode | Description |
|-----------|------|-------------|
| `hash(Algorithm, Data, Hex)` | `+Algo, +Data, -Hex` | Hex digest via `hashlib`, as a string |
| `hash_bytes(Algorithm, Data, Bytes)` | `+Algo, +Data, -Bytes` | Raw digest bytes |

**Supported algorithms:** `"sha256"`, `"sha512"`, `"md5"`, `"sha1"`, `"sha384"`,
`"sha3_256"`, `"sha3_512"`, `"blake2b"`, `"blake2s"` (anything `hashlib.new()` accepts).

**Data** can be a string (UTF-8 encoded) or `bytes`.

```clausal
--8<-- "tests/fixtures/docs/crypto_sigs.txt:hash_examples"
```

Fails silently if the algorithm is unknown, or if `Algorithm` or `Data` is unbound.

---

## `py.hmac` — Message Authentication

```clausal
-import_from(py.hmac, [sign, verify])
```

| Predicate | Mode | Description |
|-----------|------|-------------|
| `sign(Key, Data, Hex)` | `+Key, +Data, -Hex` | HMAC-SHA256 signature |
| `sign(Algorithm, Key, Data, Hex)` | `+Algo, +Key, +Data, -Hex` | HMAC with specified algorithm |
| `verify(Key, Data, Hex)` | `+Key, +Data, +Hex` | verify HMAC-SHA256 (constant-time) |
| `verify(Algorithm, Key, Data, Hex)` | `+Algo, +Key, +Data, +Hex` | verify with specified algorithm |

`Key` and `Data` can be strings (UTF-8 encoded) or `bytes`. `verify` uses
`hmac.compare_digest` for constant-time comparison.

```clausal
--8<-- "tests/fixtures/docs/crypto_sigs.txt:hmac_examples"
```

---

## `py.pbkdf2` — Key Derivation

```clausal
-import_from(py.pbkdf2, [derive])
```

| Predicate | Mode | Description |
|-----------|------|-------------|
| `derive(Password, Salt, Iterations, DerivedKey)` | `+Pw, +Salt, +Iter, -DK` | PBKDF2-HMAC-SHA256, 32-byte key |
| `derive(Password, Salt, Iterations, KeyLength, DerivedKey)` | `+Pw, +Salt, +Iter, +KL, -DK` | Custom key length |

`DerivedKey` is a hex string. `Password` and `Salt` can be strings, atoms or `bytes`.
`Iterations` must be a positive integer.

```clausal
--8<-- "tests/fixtures/docs/crypto_sigs.txt:pbkdf2_examples"
```

---

??? example "Examples"

    ### File integrity check (using the [Files](files.md) module)

    ```clausal
    --8<-- "tests/fixtures/docs/crypto_sigs.txt:file_integrity"
    ```

    ### API request signing

    ```clausal
    --8<-- "tests/fixtures/docs/crypto_sigs.txt:api_signing"
    ```

    ### Password hashing

    ```clausal
    --8<-- "tests/fixtures/docs/crypto_sigs.txt:password_hashing"
    ```

---

*See also: [Python Interop](python_integration.md) — `++()` escape for
additional cryptography operations · [UUID](uuid.md) — UUID generation with
hash-based variants (v3, v5).*
