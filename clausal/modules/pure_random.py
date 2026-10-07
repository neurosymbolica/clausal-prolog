"""clausal.modules.pure_random — a PURE, state-threaded random-number library.

Operator ruling 2026-10-07.  There is no global generator and no hidden
state: the generator state is the ordinary term ``rng(Seed, N)`` -- the seed
the caller chose and the number of draws taken so far -- and every predicate
is a relation from an input state ``S0`` to an output state ``S``::

    rng_seed(+Seed, -S)
    random(-X, +S0, -S)                         % float in [0, 1)
    random_between(+L, +H, -X, +S0, -S)          % integer in [L, H]
    random_member(-X, +List, +S0, -S)
    random_permutation(+List, -Perm, +S0, -S)
    random_sample(+List, +K, -Sample, +S0, -S)

Because the state is a binding, backtracking restores it: re-running a goal
from the same ``S0`` gives the same answer, on every run, in every process.
The last two arguments are the DCG pair, so a grammar body threads the state
with no plumbing (``phrase(dice(Xs), S0, S)``).  Import it from the seam with
``-import_from(pure_random, [...])`` and from Clausal Prolog or ``.pl`` with
``:- use_module(library(pure_random), [...])``.

Reproducibility guarantee
-------------------------
For a given ``(Seed, N)`` the N-th draw is a fixed float, on every platform
and every supported Python version:

1. *Seed material.*  The seed is encoded as bytes: an integer as
   ``b"i" + its decimal spelling``, an atom or a string as ``b"t" + its text
   in UTF-8`` (the atom ``abc`` and the string ``"abc"`` are the same seed;
   the integer ``5`` and the atom ``'5'`` are not).  The draw index is its
   decimal spelling.  The material is
   ``SHA-256(b"clausal.pure_random.v1\\0" + seed_bytes + b"\\0" + index)``,
   read as a big-endian integer.  Python's ``hash()`` is never used: it is
   salted per process.
2. *The float.*  ``random.Random(material).random()``.  CPython documents
   ``random()`` as reproducible for a given integer seed across versions
   (the Mersenne Twister's ``init_by_array`` and ``genrand_res53``); this
   module relies on nothing else from ``random``.  ``randint``,
   ``randrange``, ``choice``, ``shuffle`` and ``sample`` are NOT used: their
   algorithms have changed between Python versions.
3. *The engine's own mappings* turn draws into everything else, and are
   part of this guarantee:

   - 53 bits per draw: ``int(f * 2**53)`` is exact, since ``random()``
     returns a multiple of ``2**-53``;
   - an integer in ``[L, H]`` (``R = H - L + 1`` values): take
     ``max(1, ceil(b / 53))`` draws, ``b = (R - 1).bit_length()``, join their
     53-bit chunks (first draw most significant), keep the low ``b`` bits,
     and REJECT and repeat while the value is ``>= R``.  Unbiased, and at
     least one draw per call;
   - ``random_member/4``: the element at index ``random_between(0, n-1)``;
   - ``random_permutation/4``: Fisher-Yates from the END: for ``i`` from
     ``n-1`` down to ``1``, swap position ``i`` with ``random_between(0, i)``;
   - ``random_sample/5``: Fisher-Yates from the FRONT for ``K`` steps: for
     ``i`` from ``0`` to ``K-1``, swap position ``i`` with
     ``random_between(i, n-1)``; the sample is the first ``K`` positions, in
     the order they were drawn.

   Each predicate's output state is ``rng(Seed, N + D)``, D the draws it
   consumed.

The golden-value tests (``tests/test_pure_random.py``) pin fixed seeds to
fixed outputs, so a change in any of this -- or in Python -- fails loudly.

Errors (never a silent failure)
-------------------------------
- ``S0`` unbound, or ``rng(Seed, N)`` with an unbound component:
  ``instantiation_error``.
- ``S0`` bound but not ``rng(Seed, N)`` with a valid seed and an integer
  ``N >= 0``: ``type_error(rng_state, S0)``.
- ``rng_seed/2``: an unbound seed is ``instantiation_error``; a seed that is
  not an integer, an atom or a string is ``type_error(rng_seed, Seed)``.
- ``random_between/5``: ``L``/``H`` unbound -> ``instantiation_error``; not
  integers -> ``type_error(integer, _)``; ``L > H`` (an empty range) ->
  ``domain_error(not_less_than(L), H)``.
- A list argument: partial -> ``instantiation_error``; not a list ->
  ``type_error(list, _)``.  ``random_member/4`` on ``[]`` ->
  ``domain_error(non_empty_list, [])`` (ISO's domain).
- ``random_sample/5``: ``K`` not an integer -> ``type_error(integer, K)``;
  ``K < 0`` -> ``domain_error(not_less_than_zero, K)``; ``K`` greater than
  the list's length -> ``domain_error(not_greater_than(Len), K)``.

Scryer's ``library(random)`` has the impure ``random/1``,
``random_integer/3`` (upper bound EXCLUSIVE), ``set_random/1`` and
``maybe/0``.  This library shares the leading arguments of ``random/1``
(``random(X, S0, S)``) and takes the inclusive ``random_between`` name for
the integer case, so it never means Scryer's exclusive ``random_integer``.

The library is pure and deterministic: it reads no clock, no OS entropy and
no global state, so it is safe to allow under a sandbox.
"""

from __future__ import annotations

import hashlib as _hashlib
import random as _random

from clausal.logic.cells import chars_text, is_chars
from clausal.logic.exceptions import (
    LogicException, domain_error, instantiation_error, type_error,
)
from clausal.logic.variables import deref, is_var, unify, walk
from clausal.modules.py import ModulePredicate, simple_to_trampoline

#: The domain separator of the seed material: bump the version and every
#: golden value in the tests changes, which is the point.
_DOMAIN = b"clausal.pure_random.v1\0"

#: 2**53: one draw is 53 random bits.
_TWO53 = 9007199254740992


# ── State and seed ──────────────────────────────────────────────────────


def _seed_bytes(seed):
    """The stable byte encoding of a seed VALUE, or None when *seed* is
    not a seed (an integer, an atom or a string).  *seed* is dereferenced."""
    if type(seed) is int:
        return b"i" + str(seed).encode("ascii")
    if type(seed) is str:                      # an atom: its spelling
        return b"t" + seed.encode("utf-8", "surrogatepass")
    if is_chars(seed):                         # a string: its text
        return b"t" + chars_text(seed).encode("utf-8", "surrogatepass")
    return None


def _state(s0, pred):
    """``(seed_bytes, seed_term, n)`` of the state *s0*, or raise."""
    s0 = deref(s0)
    if is_var(s0):
        raise LogicException(instantiation_error(f"{pred}: state"))
    if not (type(s0) is tuple and len(s0) == 3 and s0[0] == "rng"
            and type(s0[0]) is str):
        raise LogicException(type_error("rng_state", walk(s0), pred))
    seed, n = deref(s0[1]), deref(s0[2])
    if is_var(seed) or is_var(n):
        raise LogicException(instantiation_error(f"{pred}: state"))
    sb = _seed_bytes(seed)
    if sb is None or type(n) is not int or n < 0:
        raise LogicException(type_error("rng_state", walk(s0), pred))
    return sb, seed, n


def _draw(sb, n):
    """The float of draw number *n* for the seed bytes *sb*: see the module
    docstring, point 1-2."""
    digest = _hashlib.sha256(
        _DOMAIN + sb + b"\0" + str(n).encode("ascii")).digest()
    return _random.Random(int.from_bytes(digest, "big")).random()


class _Stream:
    """Successive draws from ``(seed, n)``; ``n`` is where the next starts."""

    __slots__ = ("sb", "n")

    def __init__(self, sb, n):
        self.sb, self.n = sb, n

    def float(self):
        f = _draw(self.sb, self.n)
        self.n += 1
        return f

    def bits53(self):
        return int(self.float() * _TWO53)      # exact: random() is k / 2**53

    def below(self, r):
        """A uniform integer in ``[0, r)``, ``r >= 1``: rejection sampling
        over 53-bit chunks (module docstring, point 3)."""
        b = (r - 1).bit_length()
        chunks = max(1, -(-b // 53))
        mask = (1 << b) - 1
        while True:
            v = 0
            for _ in range(chunks):
                v = (v << 53) | self.bits53()
            v &= mask
            if v < r:
                return v


def _new_state(seed, n):
    return ("rng", seed, n)


# ── Argument checks ─────────────────────────────────────────────────────


def _integer(x, pred, arg):
    x = deref(x)
    if is_var(x):
        raise LogicException(instantiation_error(f"{pred}: argument {arg}"))
    if type(x) is not int:
        raise LogicException(type_error("integer", walk(x), pred))
    return x


def _proper_list(x, pred, arg):
    """*x* as a Python list of its elements (Scryer's ``must_be(list, X)``):
    a partial list is an instantiation_error, a non-list a type_error."""
    x = deref(x)
    if isinstance(x, list):
        return list(x)
    if is_var(x):
        raise LogicException(instantiation_error(f"{pred}: argument {arg}"))
    from clausal.terms import SegList  # noqa: PLC0415
    if isinstance(x, SegList):
        w = walk(x)
        if isinstance(w, list):
            return list(w)
        raise LogicException(instantiation_error(f"{pred}: argument {arg}"))
    raise LogicException(type_error("list", walk(x), pred))


# ── Predicates ──────────────────────────────────────────────────────────


def _rng_seed_2(seed, s, trail, k):
    """rng_seed(+Seed, -S): S is the initial state ``rng(Seed, 0)``."""
    seed = deref(seed)
    if is_var(seed):
        raise LogicException(instantiation_error("rng_seed/2: argument 1"))
    if _seed_bytes(seed) is None:
        raise LogicException(type_error("rng_seed", walk(seed), "rng_seed/2"))
    if unify(s, _new_state(seed, 0), trail):
        yield None


def _random_3(x, s0, s, trail, k):
    """random(-X, +S0, -S): X is a float in [0, 1)."""
    sb, seed, n = _state(s0, "random/3")
    st = _Stream(sb, n)
    f = st.float()
    if unify(x, f, trail) and unify(s, _new_state(seed, st.n), trail):
        yield None


def _random_between_5(lo, hi, x, s0, s, trail, k):
    """random_between(+L, +H, -X, +S0, -S): X is an integer in [L, H]."""
    pred = "random_between/5"
    lo, hi = _integer(lo, pred, 1), _integer(hi, pred, 2)
    if lo > hi:
        raise LogicException(domain_error(("not_less_than", lo), hi, pred))
    sb, seed, n = _state(s0, pred)
    st = _Stream(sb, n)
    v = lo + st.below(hi - lo + 1)
    if unify(x, v, trail) and unify(s, _new_state(seed, st.n), trail):
        yield None


def _random_member_4(x, lst, s0, s, trail, k):
    """random_member(-X, +List, +S0, -S): X is an element of List."""
    pred = "random_member/4"
    items = _proper_list(lst, pred, 2)
    if not items:
        raise LogicException(domain_error("non_empty_list", [], pred))
    sb, seed, n = _state(s0, pred)
    st = _Stream(sb, n)
    v = items[st.below(len(items))]
    if unify(x, v, trail) and unify(s, _new_state(seed, st.n), trail):
        yield None


def _random_permutation_4(lst, perm, s0, s, trail, k):
    """random_permutation(+List, -Perm, +S0, -S): Fisher-Yates."""
    pred = "random_permutation/4"
    items = _proper_list(lst, pred, 1)
    sb, seed, n = _state(s0, pred)
    st = _Stream(sb, n)
    for i in range(len(items) - 1, 0, -1):
        j = st.below(i + 1)
        items[i], items[j] = items[j], items[i]
    if unify(perm, items, trail) and unify(s, _new_state(seed, st.n), trail):
        yield None


def _random_sample_5(lst, kk, sample, s0, s, trail, k):
    """random_sample(+List, +K, -Sample, +S0, -S): K distinct positions."""
    pred = "random_sample/5"
    items = _proper_list(lst, pred, 1)
    size = _integer(kk, pred, 2)
    if size < 0:
        raise LogicException(domain_error("not_less_than_zero", size, pred))
    if size > len(items):
        raise LogicException(domain_error(
            ("not_greater_than", len(items)), size, pred))
    sb, seed, n = _state(s0, pred)
    st = _Stream(sb, n)
    for i in range(size):
        j = i + st.below(len(items) - i)
        items[i], items[j] = items[j], items[i]
    if (unify(sample, items[:size], trail)
            and unify(s, _new_state(seed, st.n), trail)):
        yield None


# ── Exports ─────────────────────────────────────────────────────────────

rng_seed = ModulePredicate("rng_seed", module="pure_random")
rng_seed._register(2, simple_to_trampoline(_rng_seed_2))

random = ModulePredicate("random", module="pure_random")
random._register(3, simple_to_trampoline(_random_3))

random_between = ModulePredicate("random_between", module="pure_random")
random_between._register(5, simple_to_trampoline(_random_between_5))

random_member = ModulePredicate("random_member", module="pure_random")
random_member._register(4, simple_to_trampoline(_random_member_4))

random_permutation = ModulePredicate("random_permutation",
                                     module="pure_random")
random_permutation._register(4, simple_to_trampoline(_random_permutation_4))

random_sample = ModulePredicate("random_sample", module="pure_random")
random_sample._register(5, simple_to_trampoline(_random_sample_5))
