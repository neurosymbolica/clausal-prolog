# Clausal Prolog — Crypto Modules (`hash`, `hmac`, `pbkdf2`)

!!! note "Clausal Prolog and the seam"

    Examples on this page are [Clausal Prolog](clausal_prolog.md)
    (`.clausal`, ISO Prolog syntax). It imports the Python modules `py.hash`,
    `py.hmac` and `py.pbkdf2` through their facades `library(hash)`,
    `library(hmac)` and `library(pbkdf2)` (see
    [Importing Prolog](importing_prolog.md)); the [seam](syntax.md) imports
    them directly, as `-import_from(py.hash, [...])`.

## Overview

Three small modules wrapping Python's `hashlib` and `hmac` stdlib for
cryptographic hashing, message authentication, and key derivation. All modules
use only the standard library — no third-party dependencies.

```clausal
:- use_module(library(hash), [hash/3]).
:- use_module(library(hmac), [sign/3, verify/3]).
:- use_module(library(pbkdf2), [derive/4]).

check_integrity(Data, Expected) :-
    hash("sha256", Data, Computed),
    Computed == Expected.

sign_message(Key, Msg, Sig) :-
    sign(Key, Msg, Sig).

verify_message(Key, Msg, Sig) :-
    verify(Key, Msg, Sig).

test("integrity") :-
    check_integrity("abc", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad").

test("sign and verify") :-
    sign_message("k", "hello", Sig),
    verify_message("k", "hello", Sig),
    \+ verify_message("k", "goodbye", Sig).
```

---

## `py.hash` — Cryptographic Hashing

```clausal
:- use_module(library(hash), [hash/3, hash_bytes/3]).
```

| Predicate | Mode | Description |
|-----------|------|-------------|
| `hash(Algorithm, Data, Hex)` | `+Algo, +Data, -Hex` | Hex digest via `hashlib`, as a string |
| `hash_bytes(Algorithm, Data, Bytes)` | `+Algo, +Data, -Bytes` | Raw digest bytes, as a list of byte values |

**Supported algorithms:** `"sha256"`, `"sha512"`, `"md5"`, `"sha1"`, `"sha384"`,
`"sha3_256"`, `"sha3_512"`, `"blake2b"`, `"blake2s"` (anything `hashlib.new()` accepts).

**Data** can be a string (UTF-8 encoded) or `bytes`.

```text
--8<-- "tests/fixtures/docs/crypto_sigs.txt:hash_examples"
```

An unknown algorithm raises `domain_error(hash_algorithm, Algorithm)`
(`hash("nope", "abc", H)` raises
`error(domain_error(hash_algorithm, "nope"), hash/3)`), and an unbound
`Algorithm` or `Data` raises `instantiation_error`.

---

## `py.hmac` — Message Authentication

```clausal
:- use_module(library(hmac), [sign/3, sign/4, verify/3, verify/4]).
```

| Predicate | Mode | Description |
|-----------|------|-------------|
| `sign(Key, Data, Hex)` | `+Key, +Data, -Hex` | HMAC-SHA256 signature |
| `sign(Algorithm, Key, Data, Hex)` | `+Algo, +Key, +Data, -Hex` | HMAC with specified algorithm |
| `verify(Key, Data, Hex)` | `+Key, +Data, +Hex` | verify HMAC-SHA256 (constant-time) |
| `verify(Algorithm, Key, Data, Hex)` | `+Algo, +Key, +Data, +Hex` | verify with specified algorithm |

`Key` and `Data` can be strings (UTF-8 encoded) or `bytes`. `verify` uses
`hmac.compare_digest` for constant-time comparison.

```text
--8<-- "tests/fixtures/docs/crypto_sigs.txt:hmac_examples"
```

---

## `py.pbkdf2` — Key Derivation

```clausal
:- use_module(library(pbkdf2), [derive/4, derive/5]).
```

| Predicate | Mode | Description |
|-----------|------|-------------|
| `derive(Password, Salt, Iterations, DerivedKey)` | `+Pw, +Salt, +Iter, -DK` | PBKDF2-HMAC-SHA256, 32-byte key |
| `derive(Password, Salt, Iterations, KeyLength, DerivedKey)` | `+Pw, +Salt, +Iter, +KL, -DK` | Custom key length |

`DerivedKey` is a hex string. `Password` and `Salt` can be strings, atoms or `bytes`.
`Iterations` must be a positive integer.

```text
--8<-- "tests/fixtures/docs/crypto_sigs.txt:pbkdf2_examples"
```

---

??? example "Examples"

    ### File integrity check (using the [Files](files.md) module)

    ```clausal
    --8<-- "tests/fixtures/docs/crypto_examples.clausal:file_integrity"
    ```

    ### API request signing

    ```clausal
    --8<-- "tests/fixtures/docs/crypto_examples.clausal:api_signing"
    ```

    ### Password hashing

    ```clausal
    --8<-- "tests/fixtures/docs/crypto_examples.clausal:password_hashing"
    ```

---

*See also: [Python Interop](python_integration.md) — the seam's `++()`
escape for additional cryptography operations · [UUID](uuid.md) — UUID generation with
hash-based variants (v3, v5).*
