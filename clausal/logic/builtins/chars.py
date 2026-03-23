"""Character/string builtins (Phase 2): CharType/2, CharCode/2, UpcaseAtom/2,
DowncaseAtom/2, AtomLength/2, AtomChars/2, AtomCodes/2, AtomConcat/3,
SubAtom/5.

These predicates are *relations* — they participate in unification and
backtracking (e.g. AtomConcat(A, B, "hello") enumerates splits, CharType(C,
digit) enumerates digits).  Pure Python string methods can't do this.
"""

from __future__ import annotations

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.exceptions import LogicException, instantiation_error, type_error
from clausal.logic.builtins._registry import _builtin


# ── CharType/2 ───────────────────────────────────────────────────────────────

_CHAR_TYPES = {
    "alpha": str.isalpha,
    "digit": str.isdigit,
    "alnum": str.isalnum,
    "space": str.isspace,
    "upper": str.isupper,
    "lower": str.islower,
    "ascii": lambda c: ord(c) < 128,
    "punct": lambda c: not c.isalnum() and not c.isspace() and c.isprintable(),
    "print": str.isprintable,
    "control": lambda c: ord(c) < 32 or ord(c) == 127,
}

# Pre-compute ASCII chars for enumeration (Type bound, Char unbound).
_ASCII_CHARS = [chr(i) for i in range(128)]

# Pre-compute type membership for each char.
_CHAR_TO_TYPES: dict[str, list[str]] = {}
for _c in _ASCII_CHARS:
    _CHAR_TO_TYPES[_c] = [t for t, fn in _CHAR_TYPES.items() if fn(_c)]

# Pre-compute chars for each type.
_TYPE_TO_CHARS: dict[str, list[str]] = {}
for _t in _CHAR_TYPES:
    _TYPE_TO_CHARS[_t] = [c for c in _ASCII_CHARS if _CHAR_TYPES[_t](c)]


@_builtin("CharType", 2)
def _char_type__2(char, type_, trail, k):
    """CharType(Char, Type) — character classification as a relation.

    Both bound → test.  Char bound → enumerate types.  Type bound → enumerate
    chars.  Both unbound → instantiation_error.
    """
    vc = deref(char)
    vt = deref(type_)
    c_bound = not is_var(vc)
    t_bound = not is_var(vt)

    if not c_bound and not t_bound:
        raise LogicException(instantiation_error("char_type/2"))

    if c_bound:
        if not isinstance(vc, str) or len(vc) != 1:
            return  # fail — not a single character

        if t_bound:
            # Both bound → test
            if not isinstance(vt, str):
                return
            fn = _CHAR_TYPES.get(vt)
            if fn is not None and fn(vc):
                yield None
        else:
            # Char bound, Type unbound → enumerate matching types
            for t_name in _CHAR_TO_TYPES.get(vc, []):
                mark = trail.mark()
                if unify(type_, t_name, trail):
                    yield None
                trail.undo(mark)
    else:
        # Type bound, Char unbound → enumerate matching chars
        if not isinstance(vt, str):
            return
        chars = _TYPE_TO_CHARS.get(vt)
        if chars is None:
            return
        for c in chars:
            mark = trail.mark()
            if unify(char, c, trail):
                yield None
            trail.undo(mark)


# ── CharCode/2 ──────────────────────────────────────────────────────────────

@_builtin("CharCode", 2)
def _char_code__2(char, code, trail, k):
    """CharCode(Char, Code) — bidirectional char ↔ integer code point.

    Char bound → unify Code with ord(Char).  Code bound → unify Char with
    chr(Code).  Both bound → test equality.  Both unbound → instantiation_error.
    """
    vc = deref(char)
    vn = deref(code)
    c_bound = not is_var(vc)
    n_bound = not is_var(vn)

    if not c_bound and not n_bound:
        raise LogicException(instantiation_error("char_code/2"))

    if c_bound:
        if not isinstance(vc, str) or len(vc) != 1:
            raise LogicException(type_error("character", vc, "char_code/2"))
        expected = ord(vc)
        mark = trail.mark()
        if unify(code, expected, trail):
            yield None
        trail.undo(mark)
    elif n_bound:
        if not isinstance(vn, int) or vn < 0:
            raise LogicException(type_error("integer", vn, "char_code/2"))
        mark = trail.mark()
        if unify(char, chr(vn), trail):
            yield None
        trail.undo(mark)


# ── UpcaseAtom/2, DowncaseAtom/2 ────────────────────────────────────────────

@_builtin("UpcaseAtom", 2)
def _upcase_atom__2(atom, upper, trail, k):
    """UpcaseAtom(Atom, Upper) — unify Upper with uppercase version of Atom."""
    va = deref(atom)
    if is_var(va):
        raise LogicException(instantiation_error("upcase_atom/2"))
    if not isinstance(va, str):
        raise LogicException(type_error("atom", va, "upcase_atom/2"))
    mark = trail.mark()
    if unify(upper, va.upper(), trail):
        yield None
    trail.undo(mark)


@_builtin("DowncaseAtom", 2)
def _downcase_atom__2(atom, lower, trail, k):
    """DowncaseAtom(Atom, Lower) — unify Lower with lowercase version of Atom."""
    va = deref(atom)
    if is_var(va):
        raise LogicException(instantiation_error("downcase_atom/2"))
    if not isinstance(va, str):
        raise LogicException(type_error("atom", va, "downcase_atom/2"))
    mark = trail.mark()
    if unify(lower, va.lower(), trail):
        yield None
    trail.undo(mark)


# ── AtomLength/2 ────────────────────────────────────────────────────────────

@_builtin("AtomLength", 2)
def _atom_length__2(atom, length, trail, k):
    """AtomLength(Atom, Length) — unify Length with the length of Atom."""
    va = deref(atom)
    if is_var(va):
        raise LogicException(instantiation_error("atom_length/2"))
    if not isinstance(va, str):
        raise LogicException(type_error("atom", va, "atom_length/2"))
    mark = trail.mark()
    if unify(length, len(va), trail):
        yield None
    trail.undo(mark)


# ── AtomChars/2 ─────────────────────────────────────────────────────────────

@_builtin("AtomChars", 2)
def _atom_chars__2(atom, chars, trail, k):
    """AtomChars(Atom, Chars) — bidirectional atom ↔ char-list conversion.

    Atom bound → unify Chars with list(Atom).
    Chars bound (list of length-1 strings) → unify Atom with "".join(Chars).
    Both bound → test equality.
    """
    va = deref(atom)
    vc = deref(chars)
    a_bound = not is_var(va)
    c_bound = not is_var(vc)

    if a_bound:
        if not isinstance(va, str):
            raise LogicException(type_error("atom", va, "atom_chars/2"))
        mark = trail.mark()
        if unify(chars, list(va), trail):
            yield None
        trail.undo(mark)
    elif c_bound:
        if not isinstance(vc, list):
            raise LogicException(type_error("list", vc, "atom_chars/2"))
        # Deref each element and validate
        elems = []
        for elem in vc:
            e = deref(elem)
            if is_var(e):
                raise LogicException(instantiation_error("atom_chars/2"))
            if not isinstance(e, str) or len(e) != 1:
                raise LogicException(type_error("character", e, "atom_chars/2"))
            elems.append(e)
        mark = trail.mark()
        if unify(atom, "".join(elems), trail):
            yield None
        trail.undo(mark)
    else:
        raise LogicException(instantiation_error("atom_chars/2"))


# ── AtomCodes/2 ─────────────────────────────────────────────────────────────

@_builtin("AtomCodes", 2)
def _atom_codes__2(atom, codes, trail, k):
    """AtomCodes(Atom, Codes) — bidirectional atom ↔ code-point-list conversion.

    Atom bound → unify Codes with [ord(c) for c in Atom].
    Codes bound (list of ints) → unify Atom with "".join(chr(c) for c in Codes).
    """
    va = deref(atom)
    vc = deref(codes)
    a_bound = not is_var(va)
    c_bound = not is_var(vc)

    if a_bound:
        if not isinstance(va, str):
            raise LogicException(type_error("atom", va, "atom_codes/2"))
        mark = trail.mark()
        if unify(codes, [ord(c) for c in va], trail):
            yield None
        trail.undo(mark)
    elif c_bound:
        if not isinstance(vc, list):
            raise LogicException(type_error("list", vc, "atom_codes/2"))
        elems = []
        for elem in vc:
            e = deref(elem)
            if is_var(e):
                raise LogicException(instantiation_error("atom_codes/2"))
            if not isinstance(e, int):
                raise LogicException(type_error("integer", e, "atom_codes/2"))
            elems.append(chr(e))
        mark = trail.mark()
        if unify(atom, "".join(elems), trail):
            yield None
        trail.undo(mark)
    else:
        raise LogicException(instantiation_error("atom_codes/2"))


# ── AtomConcat/3 ─────────────────────────────────────────────────────────────

@_builtin("AtomConcat", 3)
def _atom_concat__3(a, b, c, trail, k):
    """AtomConcat(A, B, C) — string concatenation as a relation.

    A+B bound → forward concat.  C bound + A or B bound → prefix/suffix check.
    C bound + both A,B unbound → enumerate all splits.
    """
    va, vb, vc = deref(a), deref(b), deref(c)
    a_bound = not is_var(va) and isinstance(va, str)
    b_bound = not is_var(vb) and isinstance(vb, str)
    c_bound = not is_var(vc) and isinstance(vc, str)

    if a_bound and b_bound:
        # Forward: A + B → C
        mark = trail.mark()
        if unify(c, va + vb, trail):
            yield None
        trail.undo(mark)
    elif c_bound and a_bound:
        # C and A bound: check prefix, unify remainder
        if vc.startswith(va):
            mark = trail.mark()
            if unify(b, vc[len(va):], trail):
                yield None
            trail.undo(mark)
    elif c_bound and b_bound:
        # C and B bound: check suffix, unify prefix
        if vc.endswith(vb):
            mark = trail.mark()
            if unify(a, vc[:len(vc) - len(vb)], trail):
                yield None
            trail.undo(mark)
    elif c_bound:
        # C bound, A and B unbound: enumerate all splits
        for i in range(len(vc) + 1):
            mark = trail.mark()
            if unify(a, vc[:i], trail) and unify(b, vc[i:], trail):
                yield None
            trail.undo(mark)
    else:
        # C unbound and not enough info to compute it
        raise LogicException(instantiation_error("atom_concat/3"))


# ── SubAtom/5 ────────────────────────────────────────────────────────────────

@_builtin("SubAtom", 5)
def _sub_atom__5(atom, before, length, after, sub, trail, k):
    """SubAtom(Atom, Before, Length, After, Sub) — substring relation.

    Atom must be bound.  Relates Atom to its substrings with position info:
    Before + Length + After = len(Atom), Sub = Atom[Before:Before+Length].
    """
    va = deref(atom)
    if is_var(va):
        raise LogicException(instantiation_error("sub_atom/5"))
    if not isinstance(va, str):
        raise LogicException(type_error("atom", va, "sub_atom/5"))

    n = len(va)
    vs = deref(sub)

    # Optimization: if Sub is bound, use str.find to locate occurrences.
    if not is_var(vs) and isinstance(vs, str):
        sub_len = len(vs)
        start = 0
        while True:
            pos = va.find(vs, start)
            if pos == -1:
                break
            b, l, a = pos, sub_len, n - pos - sub_len
            mark = trail.mark()
            if (unify(before, b, trail) and unify(length, l, trail)
                    and unify(after, a, trail)):
                yield None
            trail.undo(mark)
            start = pos + 1
        return

    # General case: enumerate (Before, Length) pairs.
    # Narrow ranges when Before or Length is bound.
    vb = deref(before)
    vl = deref(length)

    if not is_var(vb) and isinstance(vb, int):
        b_range = range(vb, vb + 1) if 0 <= vb <= n else range(0)
    else:
        b_range = range(n + 1)

    for b in b_range:
        if not is_var(vl) and isinstance(vl, int):
            if vl < 0 or b + vl > n:
                continue
            l_range = range(vl, vl + 1)
        else:
            l_range = range(n - b + 1)

        for l in l_range:
            a = n - b - l
            s = va[b:b + l]
            mark = trail.mark()
            if (unify(before, b, trail) and unify(length, l, trail)
                    and unify(after, a, trail) and unify(sub, s, trail)):
                yield None
            trail.undo(mark)
