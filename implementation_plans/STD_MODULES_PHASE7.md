# Std Modules Phase 7 — Optional / Low Priority

**Status: DONE**

**Depends on:** Module adapter pattern (`clausal/modules/py/*.py`), builtin registry (`clausal/logic/builtins/`), `_import_stdlib` infrastructure.

**Goal:** Thin convenience wrappers for crypto hashing, HTTP requests, TCP sockets, unique atom generation (GenSym), and minor charsio additions. These are "nice-to-have" since `++()` interop covers the underlying Python functionality.

**Non-goal:** Full reimplementation of Python's networking or cryptography APIs.

---

## Context

Phase 7 is the final phase of the standard modules plan (`STD_MODULES_OVERVIEW.md`). Phases 1-6 are complete. Phase 7 items were originally described as "Optional / Low Priority" because Python interop (`++()`) already covers the underlying functionality. However, named predicates improve readability, discoverability, and composability with logic programming patterns (backtracking, unification).

The original overview grouped everything under a monolithic `crypto` module and prefixed predicates with acronyms (`TcpConnect`, `HttpGet`, `HmacVerify`). This conflicts with Clausal's naming conventions:
- **Capitalized acronyms** (e.g. `TCP`, `HTTP`, `HMAC`, `URL`) look like logic variables
- **One-concern-per-module** with short predicate names (e.g. `tcp.Connect`, `http.Get`, `hmac.Sign`) is cleaner

---

## Design Decisions

1. **Zero mandatory third-party deps.** All modules wrap stdlib only (`hashlib`, `hmac`, `urllib`, `socket`). Optional soft-import of `cryptography`/`requests` for enhanced functionality.

2. **Handle-based for stateful resources.** TCP sockets use opaque Python `socket.socket` objects (same pattern as `scipy_interpolate` spline handles).

3. **GenSym is a builtin**, not a module — goes in `clausal/logic/builtins/inspection.py` alongside other term-manipulation builtins.

4. **Charsio extras are minimal.** Only `NumberChars/2` and `NumberCodes/2` in `chars.py`. `ReadFromChars/2` (parse term from string) deferred — requires a full `.clausal` parser.

5. **One concern per module.** Acronym predicates (`HMAC`, `TCP`, `HTTP`, `URL`) live in their own lowercase modules so predicates can use short unqualified names. Module names follow Python style (lowercase): `py.hash`, `py.hmac`, `py.pbkdf2`, `py.http`, `py.url`, `py.tcp`.

6. **Naming:** `GenSym` (camelCase — the universal name for "generate symbol", a Prolog/Lisp standard). All other predicates use TitleCase as usual.

---

## Architecture Reference

### Module adapter pattern

Every `clausal/modules/py/*.py` module follows this exact structure (see `py/random.py` for the canonical example):

```python
# 1. Safe stdlib import (avoids name collision with clausal's import hook)
from clausal.modules.py import _import_stdlib
_hashlib = _import_stdlib("hashlib")

# 2. Standard imports
from typing import Callable
from clausal.logic.variables import Var, deref, is_var, unify
from clausal.logic.trampoline import DONE

# 3. Adapter class — one per module, provides _get_dispatch() protocol
class _HashPredicate:
    __slots__ = ("_name", "_dispatch_fns")

    def __init__(self, name: str) -> None:
        self._name = name
        self._dispatch_fns: dict[int, Callable] = {}

    def _register(self, arity: int, fn: Callable) -> None:
        self._dispatch_fns[arity] = fn

    def _get_dispatch(self) -> Callable:
        if len(self._dispatch_fns) == 1:
            return next(iter(self._dispatch_fns.values()))
        return self._multi_dispatch

    def _multi_dispatch(self, this_generator, parent, *args):
        arity = len(args) - 1  # exclude trail
        fn = self._dispatch_fns.get(arity)
        if fn is None:
            yield (parent, DONE)
            return
        yield from fn(this_generator, parent, *args)

    def __repr__(self) -> str:
        arities = sorted(self._dispatch_fns)
        return f"hash.{self._name}/{arities}"

# 4. Simple-to-trampoline wrapper
def _simple_to_trampoline(simple_fn):
    def trampoline_fn(this_generator, parent, *args):
        for _ in simple_fn(*args, None):
            yield (parent, None)
        yield (parent, DONE)
    return trampoline_fn

# 5. Predicate implementations — simple-mode: fn(*args, trail, k) → yields None
def _hash_3(algorithm, data, hex_out, trail, k):
    ...
    if unify(hex_out, result, trail):
        yield None

# 6. Build and export predicate objects
Hash = _HashPredicate("Hash")
Hash._register(3, _simple_to_trampoline(_hash_3))
```

### Alias pattern

Each module has a backward-compat alias at `clausal/modules/MODULE_mod.py`:

```python
"""Backward compatibility — canonical implementation in clausal.modules.py.hash."""
from clausal.modules.py.hash import *  # noqa: F401,F403
from clausal.modules.py.hash import (  # noqa: F401 — re-export internals for tests
    _HashPredicate, _simple_to_trampoline,
    _hash_3, _hash_bytes_3,
)
```

### Builtin pattern

Builtins use the `@_builtin` decorator from `clausal/logic/builtins/_registry.py`:

```python
from clausal.logic.builtins._registry import _builtin

@_builtin("GenSym", 2)
def _gensym__2(prefix, atom, trail, k):
    """GenSym(Prefix, Atom) — generate unique atom."""
    prefix_d = deref(prefix)
    if is_var(prefix_d) or not isinstance(prefix_d, str):
        return
    ...
    if unify(atom, result, trail):
        yield None
```

The decorator auto-wraps to trampoline protocol and registers in `_BUILTINS` dict.

### Test patterns

**Module tests** (see `tests/test_random_module.py`):

```python
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.modules.py.hash import Hash, _hash_3
from clausal.logic.trampoline import DONE

def simple_solutions(fn, *args):
    trail = Trail()
    results = list(fn(*args, trail, None))
    return results, trail

def trampoline_solutions(pred, *args):
    trail = Trail()
    dispatch = pred._get_dispatch()
    gen = dispatch(None, None, *args, trail)
    solutions = []
    for parent, value in gen:
        if value is DONE:
            break
        solutions.append(value)
    return solutions, trail
```

**Builtin tests** (see `tests/test_chars.py`):

```python
from clausal.logic.variables import Var, Trail, unify, deref
from clausal.logic.builtins import get_builtin_dispatch
from clausal.logic.trampoline import StepGenerator, solutions

def _run(name, arity, *args, trail=None):
    if trail is None:
        trail = Trail()
    dispatch = get_builtin_dispatch(name, arity, None)
    return len(solutions(StepGenerator(dispatch, None, *args, trail)))
```

**Builtin tests via solve** (see `tests/test_term_inspection.py`):

```python
from clausal.logic.database import Module
from clausal.logic.solve import solve
from clausal.logic.variables import Var, Trail, deref
from clausal.terms import Compound, Call, LoadName

def goal(functor, *args):
    return Call(func=LoadName(name=functor), args=list(args), kwargs=[])

def sol_var(goal, var):
    mod = Module("test")
    trail = Trail()
    return [deref(var) for _ in solve(goal, mod, trail)]
```

---

## Sub-phases

### 7a — GenSym/2 (Builtin)

**Modified:** `clausal/logic/builtins/inspection.py`, `tests/test_term_inspection.py`

| Predicate | Description |
|---|---|
| `GenSym/2` | `GenSym(Prefix, Atom)` — append monotonic counter to Prefix. `GenSym("x", A)` → `"x_1"`, `"x_2"`, etc. Counter is NOT trailed (impure, matches Prolog semantics). Thread-safe via lock. |

#### Implementation

Add to the end of `clausal/logic/builtins/inspection.py`:

```python
import threading

_gensym_counters: dict[str, int] = {}
_gensym_lock = threading.Lock()

@_builtin("GenSym", 2)
def _gensym__2(prefix, atom, trail, k):
    """GenSym(Prefix, Atom) — generate a unique atom by appending a counter.

    Counter is global and monotonically increasing. NOT trailed — survives
    backtracking. This is intentional and matches Prolog's gensym/2 semantics.
    """
    prefix_d = deref(prefix)
    if is_var(prefix_d) or not isinstance(prefix_d, str):
        return
    with _gensym_lock:
        count = _gensym_counters.get(prefix_d, 0) + 1
        _gensym_counters[prefix_d] = count
    result = f"{prefix_d}_{count}"
    if unify(atom, result, trail):
        yield None
```

Key points:
- Counter dict is module-level, shared across all calls
- `threading.Lock` for thread safety
- Counter increments permanently even on backtracking (impure)
- Prefix must be a ground string; unbound prefix → fail (silent return)

#### Tests (~8)

Add `TestGenSym` class to `tests/test_term_inspection.py`:

```python
class TestGenSym:
    def setup_method(self):
        """Reset gensym counters between tests."""
        from clausal.logic.builtins.inspection import _gensym_counters
        _gensym_counters.clear()

    def test_basic(self):
        """GenSym("x", A) → "x_1"."""
        a = Var()
        vals = sol_var(goal("GenSym", "x", a), a)
        assert vals == ["x_1"]

    def test_sequential(self):
        """Two calls increment: "x_1", "x_2"."""

    def test_different_prefixes(self):
        """Different prefixes have independent counters."""

    def test_unbound_prefix_fails(self):
        """GenSym(X, A) with unbound X → no solutions."""

    def test_non_string_prefix_fails(self):
        """GenSym(42, A) → no solutions."""

    def test_counter_survives_backtracking(self):
        """Counter does NOT reset on backtracking."""
        # Use a goal that succeeds then fails, generating gensym atoms.
        # After failure, next gensym should continue from incremented counter.

    def test_atom_already_bound_unification(self):
        """GenSym("x", "x_1") succeeds if counter is at 1."""

    def test_thread_safety(self):
        """Concurrent gensym calls produce unique atoms."""
        import threading
        results = []
        def gen():
            a = Var()
            sol_var(goal("GenSym", "t", a), a)
            results.append(deref(a))
        threads = [threading.Thread(target=gen) for _ in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(set(results)) == 10  # all unique
```

---

### 7b — NumberChars/2, NumberCodes/2 (Builtin)

**Modified:** `clausal/logic/builtins/chars.py`, `tests/test_chars.py`

| Predicate | Description |
|---|---|
| `NumberChars/2` | `NumberChars(Number, Chars)` — bidirectional number ↔ char-list. Forward: `str(N)` → `list(s)`. Reverse: `"".join(chars)` → `int` or `float`. |
| `NumberCodes/2` | `NumberCodes(Number, Codes)` — bidirectional number ↔ code-point-list. Same as NumberChars but with `ord()`/`chr()`. |

#### Implementation

Add to the end of `clausal/logic/builtins/chars.py`, following the exact pattern of `AtomChars/2` (lines 173-212) and `AtomCodes/2` (lines 215-252):

```python
# ── NumberChars/2 ──────────────────────────────────────────────────────────────

@_builtin("NumberChars", 2)
def _number_chars__2(number, chars, trail, k):
    """NumberChars(Number, Chars) — bidirectional number ↔ char-list conversion.

    Number bound → unify Chars with list(str(Number)).
    Chars bound (list of single-char strings) → parse as int or float.
    Both bound → test equality.
    """
    vn = deref(number)
    vc = deref(chars)
    n_bound = not is_var(vn)
    c_bound = not is_var(vc)

    if n_bound:
        if not isinstance(vn, (int, float)):
            raise LogicException(type_error("number", vn, "number_chars/2"))
        mark = trail.mark()
        if unify(chars, list(str(vn)), trail):
            yield None
        trail.undo(mark)
    elif c_bound:
        if not isinstance(vc, list):
            raise LogicException(type_error("list", vc, "number_chars/2"))
        elems = []
        for elem in vc:
            e = deref(elem)
            if is_var(e):
                raise LogicException(instantiation_error("number_chars/2"))
            if not isinstance(e, str) or len(e) != 1:
                raise LogicException(type_error("character", e, "number_chars/2"))
            elems.append(e)
        s = "".join(elems)
        try:
            parsed = int(s)
        except ValueError:
            try:
                parsed = float(s)
            except ValueError:
                return  # fail — not a valid number
        mark = trail.mark()
        if unify(number, parsed, trail):
            yield None
        trail.undo(mark)
    else:
        raise LogicException(instantiation_error("number_chars/2"))


# ── NumberCodes/2 ──────────────────────────────────────────────────────────────

@_builtin("NumberCodes", 2)
def _number_codes__2(number, codes, trail, k):
    """NumberCodes(Number, Codes) — bidirectional number ↔ code-point-list.

    Number bound → unify Codes with [ord(c) for c in str(Number)].
    Codes bound (list of ints) → join as chars, parse as int or float.
    """
    vn = deref(number)
    vc = deref(codes)
    n_bound = not is_var(vn)
    c_bound = not is_var(vc)

    if n_bound:
        if not isinstance(vn, (int, float)):
            raise LogicException(type_error("number", vn, "number_codes/2"))
        mark = trail.mark()
        if unify(codes, [ord(c) for c in str(vn)], trail):
            yield None
        trail.undo(mark)
    elif c_bound:
        if not isinstance(vc, list):
            raise LogicException(type_error("list", vc, "number_codes/2"))
        elems = []
        for elem in vc:
            e = deref(elem)
            if is_var(e):
                raise LogicException(instantiation_error("number_codes/2"))
            if not isinstance(e, int):
                raise LogicException(type_error("integer", e, "number_codes/2"))
            elems.append(chr(e))
        s = "".join(elems)
        try:
            parsed = int(s)
        except ValueError:
            try:
                parsed = float(s)
            except ValueError:
                return
        mark = trail.mark()
        if unify(number, parsed, trail):
            yield None
        trail.undo(mark)
    else:
        raise LogicException(instantiation_error("number_codes/2"))
```

Note: `bool` is a subclass of `int` in Python. The check `isinstance(vn, (int, float))` will accept `True`/`False`. This is acceptable — `str(True)` → `"True"` which is not a numeric string, but that's an edge case. If desired, add `if isinstance(vn, bool): return` before the check.

#### Tests (~10)

Add `TestNumberChars` and `TestNumberCodes` classes to `tests/test_chars.py`:

```python
class TestNumberChars:
    def test_int_forward(self):
        """NumberChars(42, C) → ["4", "2"]."""
        v = Var()
        assert _run("NumberChars", 2, 42, v) == 1
        assert deref(v) == ["4", "2"]

    def test_int_reverse(self):
        """NumberChars(N, ["4", "2"]) → N = 42."""

    def test_float_forward(self):
        """NumberChars(3.14, C) → ["3", ".", "1", "4"]."""

    def test_float_reverse(self):
        """NumberChars(N, ["3", ".", "1", "4"]) → N = 3.14."""

    def test_negative(self):
        """NumberChars(-5, C) → ["-", "5"]."""

    def test_invalid_chars_fails(self):
        """NumberChars(N, ["a", "b"]) → no solutions."""

    def test_both_bound_consistent(self):
        """NumberChars(42, ["4", "2"]) → succeeds."""

    def test_both_bound_inconsistent(self):
        """NumberChars(42, ["4", "3"]) → fails."""

    def test_both_unbound_raises(self):
        """NumberChars(N, C) with both unbound → instantiation error."""

class TestNumberCodes:
    def test_int_forward(self):
        """NumberCodes(42, C) → [52, 50]."""

    def test_int_reverse(self):
        """NumberCodes(N, [52, 50]) → N = 42."""
```

---

### 7c — Crypto Modules (py.hash, py.hmac, py.pbkdf2)

Three separate modules, each wrapping one stdlib concern.

#### 7c-i: `py.hash` — Cryptographic Hashing

**New files:** `clausal/modules/py/hash.py`, `clausal/modules/hash_mod.py`

| Predicate | Description |
|---|---|
| `Hash/3` | `Hash(Algorithm, Data, Hex)` — hash via `hashlib`. Data is string (UTF-8) or bytes. Hex is hex digest string. Algorithms: `"sha256"`, `"sha512"`, `"md5"`, `"sha1"`, `"sha384"`, `"sha3_256"`, `"sha3_512"`, `"blake2b"`, `"blake2s"`. |
| `HashBytes/3` | `HashBytes(Algorithm, Data, Bytes)` — like Hash but returns raw `bytes` object. |

**Usage in `.clausal`:**

```python
-import_from(py.hash, [Hash, HashBytes])

check_integrity(DATA, EXPECTED_HASH) <- (
    Hash("sha256", DATA, COMPUTED),
    COMPUTED == EXPECTED_HASH
)
```

**Implementation sketch:**

```python
from clausal.modules.py import _import_stdlib
_hashlib = _import_stdlib("hashlib")

def _hash_3(algorithm, data, hex_out, trail, k):
    algo = deref(algorithm)
    data_d = deref(data)
    if is_var(algo) or not isinstance(algo, str):
        return
    if is_var(data_d):
        return
    # Encode string to bytes
    if isinstance(data_d, str):
        data_bytes = data_d.encode("utf-8")
    elif isinstance(data_d, bytes):
        data_bytes = data_d
    else:
        return
    try:
        h = _hashlib.new(algo)
    except ValueError:
        return  # unknown algorithm
    h.update(data_bytes)
    if unify(hex_out, h.hexdigest(), trail):
        yield None
```

**Known test vectors** (from [RFC 6234](https://datatracker.ietf.org/doc/html/rfc6234), NIST):

```python
# SHA-256 of "abc"
"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"

# MD5 of "" (empty string)
"d41d8cd98f00b204e9800998ecf8427e"

# SHA-1 of "abc"
"a9993e364706816aba3e25717850c26c9cd0d89d"
```

#### 7c-ii: `py.hmac` — Message Authentication

**New files:** `clausal/modules/py/hmac.py`, `clausal/modules/hmac_mod.py`

| Predicate | Description |
|---|---|
| `Sign/3` | `Sign(Key, Data, Hex)` — HMAC-SHA256 signature. Key and Data are strings (or bytes). Hex is hex digest. |
| `Sign/4` | `Sign(Algorithm, Key, Data, Hex)` — HMAC with specified algorithm. |
| `Verify/3` | `Verify(Key, Data, Hex)` — verify HMAC-SHA256. Uses `hmac.compare_digest` for constant-time comparison. Succeeds or fails. |
| `Verify/4` | `Verify(Algorithm, Key, Data, Hex)` — verify with specified algorithm. |

**Usage in `.clausal`:**

```python
-import_from(py.hmac, [Sign, Verify])

sign_message(KEY, MESSAGE, SIGNATURE) <- Sign(KEY, MESSAGE, SIGNATURE)
check_message(KEY, MESSAGE, SIGNATURE) <- Verify(KEY, MESSAGE, SIGNATURE)
```

**Implementation sketch:**

```python
from clausal.modules.py import _import_stdlib
_hmac = _import_stdlib("hmac")
_hashlib = _import_stdlib("hashlib")

def _sign_3(key, data, hex_out, trail, k):
    """Sign/3: HMAC-SHA256 (default algorithm)."""
    return _sign_4("sha256", key, data, hex_out, trail, k)

def _sign_4(algorithm, key, data, hex_out, trail, k):
    algo = deref(algorithm)
    key_d, data_d = deref(key), deref(data)
    if is_var(algo) or is_var(key_d) or is_var(data_d):
        return
    key_b = key_d.encode("utf-8") if isinstance(key_d, str) else key_d
    data_b = data_d.encode("utf-8") if isinstance(data_d, str) else data_d
    if not isinstance(key_b, bytes) or not isinstance(data_b, bytes):
        return
    try:
        h = _hmac.new(key_b, data_b, getattr(_hashlib, algo, None) or algo)
    except (ValueError, AttributeError):
        return
    if unify(hex_out, h.hexdigest(), trail):
        yield None

def _verify_3(key, data, hex_in, trail, k):
    return _verify_4("sha256", key, data, hex_in, trail, k)

def _verify_4(algorithm, key, data, hex_in, trail, k):
    # Compute HMAC, then compare_digest
    ...
    if _hmac.compare_digest(computed, expected):
        yield None
```

**Known test vector** (from [RFC 4231](https://datatracker.ietf.org/doc/html/rfc4231)):

```python
# HMAC-SHA256 with key=b"\x0b"*20, data=b"Hi There"
"b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7"
```

#### 7c-iii: `py.pbkdf2` — Key Derivation

**New files:** `clausal/modules/py/pbkdf2.py`, `clausal/modules/pbkdf2_mod.py`

| Predicate | Description |
|---|---|
| `Derive/5` | `Derive(Password, Salt, Iterations, KeyLength, DerivedKey)` — PBKDF2-HMAC-SHA256. All inputs must be ground. DerivedKey is hex string. |
| `Derive/4` | `Derive(Password, Salt, Iterations, DerivedKey)` — default KeyLength=32 bytes. |

**Usage in `.clausal`:**

```python
-import_from(py.pbkdf2, [Derive])

hash_password(PASSWORD, SALT, HASH) <- Derive(PASSWORD, SALT, 100000, HASH)
```

**Implementation sketch:**

```python
def _derive_5(password, salt, iterations, key_length, derived_key, trail, k):
    pw = deref(password)
    sa = deref(salt)
    it = deref(iterations)
    kl = deref(key_length)
    if any(is_var(x) for x in (pw, sa, it, kl)):
        return
    pw_b = pw.encode("utf-8") if isinstance(pw, str) else pw
    sa_b = sa.encode("utf-8") if isinstance(sa, str) else sa
    if not isinstance(it, int) or it <= 0:
        return
    if not isinstance(kl, int) or kl <= 0:
        return
    dk = _hashlib.pbkdf2_hmac("sha256", pw_b, sa_b, it, dklen=kl)
    if unify(derived_key, dk.hex(), trail):
        yield None

def _derive_4(password, salt, iterations, derived_key, trail, k):
    yield from _derive_5(password, salt, iterations, 32, derived_key, trail, k)
```

#### Crypto tests (~20)

**Single test file:** `tests/test_crypto_modules.py` covering all three modules.

```python
class TestHash:
    def test_sha256_known_vector(self):
        """Hash("sha256", "abc", H) → known hex digest."""
    def test_sha512(self): ...
    def test_md5(self): ...
    def test_sha1(self): ...
    def test_bytes_input(self): ...
    def test_unknown_algorithm_fails(self): ...
    def test_unbound_data_fails(self): ...
    def test_unbound_algorithm_fails(self): ...
    def test_trampoline_protocol(self): ...

class TestHashBytes:
    def test_returns_bytes(self): ...
    def test_length_matches_algorithm(self):
        """SHA-256 → 32 bytes, SHA-512 → 64 bytes."""

class TestHmacSign:
    def test_sha256_known_vector(self):
        """RFC 4231 test case 2."""
    def test_different_key_different_result(self): ...
    def test_unbound_key_fails(self): ...
    def test_custom_algorithm(self):
        """Sign("sha512", KEY, DATA, HEX)."""
    def test_trampoline_protocol(self): ...

class TestHmacVerify:
    def test_correct_hmac_succeeds(self): ...
    def test_incorrect_hmac_fails(self): ...
    def test_uses_constant_time_comparison(self):
        """Verify internally calls hmac.compare_digest."""

class TestPbkdf2:
    def test_known_derivation(self): ...
    def test_different_iterations_different_result(self): ...
    def test_default_key_length(self):
        """Derive/4 uses 32-byte key length."""
    def test_unbound_password_fails(self): ...
```

---

### 7d — HTTP & URL Modules (py.http, py.url)

Two separate modules: HTTP for requests, URL for manipulation.

#### 7d-i: `py.http` — HTTP Requests

**New files:** `clausal/modules/py/http.py`, `clausal/modules/http_mod.py`

| Predicate | Description |
|---|---|
| `Get/2` | `Get(Url, Body)` — GET request, body as string. Fails on HTTP error. |
| `Get/3` | `Get(Url, Headers, Body)` — GET with custom headers (DictTerm). |
| `Post/3` | `Post(Url, Data, Body)` — POST string data, body as string. |
| `Post/4` | `Post(Url, Data, Headers, Body)` — POST with custom headers. |
| `Request/3` | `Request(Options, Status, Body)` — General request. Options DictTerm: `"url"` (required), `"method"` (default `"GET"`), `"headers"` (DictTerm), `"data"` (string), `"timeout"` (seconds, default 30). Returns status code — does NOT fail on 4xx/5xx. |
| `JSONGet/2` | `JSONGet(Url, Term)` — GET + parse JSON response into DictTerm/list. |
| `JSONPost/3` | `JSONPost(Url, Term, ResponseTerm)` — POST JSON body + parse JSON response. |

**Usage in `.clausal`:**

```python
-import_from(py.http, [Get, JSONGet, Post, Request])

fetch_page(URL, BODY) <- Get(URL, BODY)

fetch_api(URL, DATA) <- JSONGet(URL, DATA)

post_data(URL, PAYLOAD, RESPONSE) <- (
    JSONPost(URL, PAYLOAD, RESPONSE)
)
```

**Implementation notes:**

- Primary backend: `urllib.request.Request` + `urllib.request.urlopen` (stdlib, zero deps)
- Soft-import `requests`: `try: _requests = _import_stdlib("requests"); _HAS_REQUESTS = True except ImportError: _HAS_REQUESTS = False`
- `JSONGet/2` and `JSONPost/3` reuse `_python_to_clausal` and `_clausal_to_python` from `clausal.modules.py.json` (import them directly)
- `Get/2` catches `urllib.error.HTTPError` and `urllib.error.URLError` — fails silently
- `Request/3` catches exceptions too but returns status code via `e.code` for HTTP errors
- `DictTerm` headers: iterate `.data` items, set each as request header
- Default timeout: 30 seconds
- Response body: `response.read().decode("utf-8")`

#### 7d-ii: `py.url` — URL Utilities

**New files:** `clausal/modules/py/url.py`, `clausal/modules/url_mod.py`

| Predicate | Description |
|---|---|
| `Encode/2` | `Encode(String, Encoded)` — URL-encode via `urllib.parse.quote`. |
| `Decode/2` | `Decode(Encoded, String)` — URL-decode via `urllib.parse.unquote`. |
| `Parse/2` | `Parse(Url, Parts)` — parse URL into DictTerm: `{scheme, host, port, path, query, fragment}`. Port is int or None. |
| `Join/2` | `Join(Parts, Url)` — assemble URL string from DictTerm parts. |

**Usage in `.clausal`:**

```python
-import_from(py.url, [Encode, Decode, Parse])

safe_param(RAW, SAFE) <- Encode(RAW, SAFE)

get_host(URL, HOST) <- (
    Parse(URL, PARTS),
    py.json.Get(PARTS, "host", HOST)
)
```

**Implementation notes:**

- `urllib.parse.quote(string, safe="")` for Encode (encode everything)
- `urllib.parse.unquote(string)` for Decode
- `urllib.parse.urlparse(url)` for Parse → DictTerm with named fields
- `urllib.parse.urlunparse(...)` for Join ← read fields from DictTerm
- `DictTerm` import from `clausal.terms`

#### HTTP/URL tests (~20)

**Single test file:** `tests/test_http_module.py` covering both py.http and py.url.

**Testing strategy:** Mock `urllib.request.urlopen` via `unittest.mock.patch`. No real network calls.

```python
from unittest.mock import patch, MagicMock

class TestHttpGet:
    @patch("clausal.modules.py.http._urlopen")
    def test_get_200(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"hello"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        body = Var()
        sols, _ = simple_solutions(_get_2, "http://example.com", body)
        assert len(sols) == 1
        assert deref(body) == "hello"

    @patch("clausal.modules.py.http._urlopen")
    def test_get_404_fails(self, mock_urlopen):
        from urllib.error import HTTPError
        mock_urlopen.side_effect = HTTPError(None, 404, "Not Found", {}, None)
        sols, _ = simple_solutions(_get_2, "http://example.com", Var())
        assert len(sols) == 0

    def test_unbound_url_fails(self): ...
    def test_get_with_headers(self): ...

class TestHttpPost:
    def test_post_200(self): ...
    def test_post_data_sent(self): ...
    def test_post_with_headers(self): ...

class TestHttpRequest:
    def test_returns_status_code(self): ...
    def test_non_200_still_succeeds(self): ...
    def test_timeout_option(self): ...

class TestHttpJson:
    def test_json_get_parses_dict(self): ...
    def test_json_post_serializes_and_parses(self): ...
    def test_invalid_json_fails(self): ...

class TestUrlEncode:
    def test_encode_special_chars(self):
        """Encode("hello world", E) → "hello%20world"."""
    def test_decode_round_trip(self): ...

class TestUrlParse:
    def test_parse_full_url(self):
        """Parse("https://example.com:8080/path?q=1#frag", P) → DictTerm."""
    def test_parse_simple_url(self): ...

class TestUrlJoin:
    def test_join_round_trip(self): ...
```

---

### 7e — TCP Module (py.tcp)

**New files:** `clausal/modules/py/tcp.py`, `clausal/modules/tcp_mod.py`, `tests/test_tcp_module.py`

| Predicate | Description |
|---|---|
| `Connect/3` | `Connect(Host, Port, Socket)` — connect to TCP server, bind opaque socket handle. |
| `Listen/3` | `Listen(Host, Port, ServerSocket)` — create listening socket. Uses `SO_REUSEADDR`. Port `0` = ephemeral. |
| `Accept/2` | `Accept(ServerSocket, ClientSocket)` — accept incoming connection. Blocks until connection arrives. |
| `Send/2` | `Send(Socket, Data)` — send string (UTF-8 encoded) via `sendall()`. |
| `Receive/2` | `Receive(Socket, Data)` — receive up to 4096 bytes, decode UTF-8. |
| `Receive/3` | `Receive(Socket, BufferSize, Data)` — custom buffer size. |
| `Close/1` | `Close(Socket)` — close socket. Always succeeds. |
| `SetTimeout/2` | `SetTimeout(Socket, Seconds)` — set socket timeout (float). `None` for blocking. |

**Usage in `.clausal`:**

```python
-import_from(py.tcp, [Connect, Send, Receive, Close])

send_and_receive(HOST, PORT, MESSAGE, RESPONSE) <- (
    Connect(HOST, PORT, SOCKET),
    Send(SOCKET, MESSAGE),
    Receive(SOCKET, RESPONSE),
    Close(SOCKET)
)
```

**Implementation sketch:**

```python
from clausal.modules.py import _import_stdlib
_socket = _import_stdlib("socket")

def _connect_3(host, port, sock_out, trail, k):
    host_d, port_d = deref(host), deref(port)
    if is_var(host_d) or not isinstance(host_d, str):
        return
    if is_var(port_d) or not isinstance(port_d, int):
        return
    try:
        s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        s.connect((host_d, port_d))
    except (OSError, _socket.error):
        return
    if unify(sock_out, s, trail):
        yield None

def _listen_3(host, port, server_out, trail, k):
    host_d, port_d = deref(host), deref(port)
    if is_var(host_d) or not isinstance(host_d, str):
        return
    if is_var(port_d) or not isinstance(port_d, int):
        return
    try:
        s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        s.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
        s.bind((host_d, port_d))
        s.listen(5)
    except (OSError, _socket.error):
        return
    if unify(server_out, s, trail):
        yield None

def _accept_2(server_sock, client_out, trail, k):
    server_d = deref(server_sock)
    if is_var(server_d) or not isinstance(server_d, _socket.socket):
        return
    try:
        client, addr = server_d.accept()
    except (OSError, _socket.error):
        return
    if unify(client_out, client, trail):
        yield None

def _send_2(sock, data, trail, k):
    sock_d, data_d = deref(sock), deref(data)
    if is_var(sock_d) or not isinstance(sock_d, _socket.socket):
        return
    if is_var(data_d):
        return
    if isinstance(data_d, str):
        data_bytes = data_d.encode("utf-8")
    elif isinstance(data_d, bytes):
        data_bytes = data_d
    else:
        return
    try:
        sock_d.sendall(data_bytes)
    except (OSError, _socket.error):
        return
    yield None

def _receive_2(sock, data_out, trail, k):
    yield from _receive_3(sock, 4096, data_out, trail, k)

def _receive_3(sock, bufsize, data_out, trail, k):
    sock_d = deref(sock)
    bufsize_d = deref(bufsize)
    if is_var(sock_d) or not isinstance(sock_d, _socket.socket):
        return
    if is_var(bufsize_d) or not isinstance(bufsize_d, int):
        return
    try:
        raw = sock_d.recv(bufsize_d)
    except (OSError, _socket.error):
        return
    if not raw:
        return  # connection closed
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        # Return raw bytes if not valid UTF-8
        if unify(data_out, raw, trail):
            yield None
        return
    if unify(data_out, text, trail):
        yield None

def _close_1(sock, trail, k):
    sock_d = deref(sock)
    if is_var(sock_d) or not isinstance(sock_d, _socket.socket):
        return
    try:
        sock_d.close()
    except (OSError, _socket.error):
        pass
    yield None

def _set_timeout_2(sock, seconds, trail, k):
    sock_d, sec_d = deref(sock), deref(seconds)
    if is_var(sock_d) or not isinstance(sock_d, _socket.socket):
        return
    if is_var(sec_d):
        return
    timeout = None if sec_d is None else float(sec_d)
    sock_d.settimeout(timeout)
    yield None
```

#### TCP tests (~20)

**Test file:** `tests/test_tcp_module.py`

**Testing strategy:** Loopback echo server in a background thread for integration tests. Unit tests for argument validation.

```python
import threading

def _echo_server(host, port, ready_event, stop_event):
    """Simple echo server for testing."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((host, port))
    s.listen(1)
    s.settimeout(5)
    ready_event.set()
    try:
        client, _ = s.accept()
        data = client.recv(4096)
        if data:
            client.sendall(data)  # echo back
        client.close()
    except socket.timeout:
        pass
    finally:
        s.close()

@pytest.fixture
def echo_server():
    """Start an echo server on localhost, yield (host, port), clean up."""
    ready = threading.Event()
    stop = threading.Event()
    # Use port 0 for ephemeral port
    # ... start thread, wait for ready, yield, join ...

class TestConnect:
    def test_connect_to_echo_server(self, echo_server): ...
    def test_connection_refused_fails(self): ...
    def test_unbound_host_fails(self): ...

class TestListenAccept:
    def test_listen_and_accept(self): ...
    def test_ephemeral_port(self): ...

class TestSendReceive:
    def test_echo_round_trip(self, echo_server):
        """Connect, send, receive echoed data, close."""
    def test_receive_custom_buffer_size(self, echo_server): ...
    def test_send_closed_socket_fails(self): ...
    def test_receive_closed_socket_fails(self): ...

class TestClose:
    def test_close_succeeds(self, echo_server): ...
    def test_double_close_harmless(self): ...

class TestSetTimeout:
    def test_timeout_causes_receive_fail(self): ...

class TestTcpIntegration:
    def test_full_echo_trampoline(self, echo_server):
        """Full test via trampoline protocol."""
    def test_clausal_import(self):
        """Verify -import_from(py.tcp, [Connect]) works."""
```

---

## Implementation Order

1. **7a — GenSym** (simplest, one function in existing file, ~8 tests)
2. **7b — NumberChars/NumberCodes** (two functions following existing AtomChars pattern, ~10 tests)
3. **7c — hash/hmac/pbkdf2** (three small modules, stdlib only, known test vectors, ~20 tests)
4. **7d — http/url** (two modules, mock-based tests, ~20 tests)
5. **7e — tcp** (one module, most complex due to lifecycle + loopback tests, ~20 tests)

Total: ~78 tests across all sub-phases.

---

## File Summary

### New files
| File | Sub-phase |
|---|---|
| `clausal/modules/py/hash.py` | 7c |
| `clausal/modules/hash_mod.py` | 7c |
| `clausal/modules/py/hmac.py` | 7c |
| `clausal/modules/hmac_mod.py` | 7c |
| `clausal/modules/py/pbkdf2.py` | 7c |
| `clausal/modules/pbkdf2_mod.py` | 7c |
| `clausal/modules/py/http.py` | 7d |
| `clausal/modules/http_mod.py` | 7d |
| `clausal/modules/py/url.py` | 7d |
| `clausal/modules/url_mod.py` | 7d |
| `clausal/modules/py/tcp.py` | 7e |
| `clausal/modules/tcp_mod.py` | 7e |
| `tests/test_crypto_modules.py` | 7c |
| `tests/test_http_module.py` | 7d |
| `tests/test_tcp_module.py` | 7e |
| `implementation_plans/STD_MODULES_PHASE7.md` | all |

### Modified files
| File | Change | Sub-phase |
|---|---|---|
| `clausal/logic/builtins/inspection.py` | Add GenSym/2 | 7a |
| `clausal/logic/builtins/chars.py` | Add NumberChars/2, NumberCodes/2 | 7b |
| `tests/test_term_inspection.py` | Add TestGenSym class | 7a |
| `tests/test_chars.py` | Add TestNumberChars, TestNumberCodes classes | 7b |
| `clausal/modules/py/__init__.py` | Add import examples to docstring | 7c-7e |
| `implementation_plans/STD_MODULES_OVERVIEW.md` | Mark Phase 7, link plan | all |

---

## Verification

After each sub-phase:
1. `python -m pytest tests/test_term_inspection.py -x -v` (7a)
2. `python -m pytest tests/test_chars.py -x -v` (7b)
3. `python -m pytest tests/test_crypto_modules.py -x -v` (7c)
4. `python -m pytest tests/test_http_module.py -x -v` (7d)
5. `python -m pytest tests/test_tcp_module.py -x -v` (7e)
6. Final: `python -m pytest tests/ -x` (full suite, confirm no regressions)
