"""Module-private atom mangling for the ``-hide`` directive (P3-1 Task 6).

Design authority: ``implementation_plans/tagged-tuple-term-representation.md``
§1a (atoms become global interned strs by spelling; module-local symbols are
**opt-in** via a Ciao-style ``-hide`` directive) and §1b (the Phase 3
rulings, recorded 2026-09-03/04):

    "Atom scope: global by spelling; ``-hide`` mangles with a
    READER-UNWRITABLE separator. [...] the compiler renames them to
    ``module⟨SEP⟩name`` where ⟨SEP⟩ is a character the Clausal reader
    refuses inside any atom token, QUOTED OR NOT [...] The guarantee is
    uniqueness + analysis soundness, not runtime security [...] Runtime
    construction via ``atom_chars/2`` etc. CAN forge the mangled name;
    documented out-of-warranty, optionally linted, not blocked. [...]
    Printing: the writer renders the human form (``m.my_atom``); the
    runtime str keeps ⟨SEP⟩."

Ruling R1 originally fixed ⟨SEP⟩ at U+E000 (the first Unicode private-use
codepoint) — not NUL, which renders invisibly and confuses debuggers/
terminals; U+E000 renders visibly (typically as a placeholder glyph) and is
outside every legitimate identifier/graphic-token class.

R1-revised (user-ratified 2026-09-05, proposed during P3-2 close-out)
supersedes that choice: ⟨SEP⟩ is now **US, 0x1F** (the ASCII "Unit
Separator" control character), for four reasons recorded at proposal time
(``todo/done/r1-revised-separator-us-0x1f-2026-09-05.md``):

  * No C-string hazard: unlike NUL, 0x1F is an ordinary byte to every C
    twin — nothing terminates early on it.
  * CPython storage (the strongest argument): a single U+E000 anywhere in
    a str forces the WHOLE string into UCS-2 (2 bytes/char) representation
    and off the compact-ASCII comparison/hash fast paths; 0x1F keeps
    ASCII module/name atoms in Latin-1 (1 byte/char) storage. This halves
    mangled-atom memory, not just the separator's own footprint.
  * Byte-clean interop: 0x1F travels in-band to non-Unicode Prologs (e.g.
    GNU Prolog) without a wider encoding; a structural (module, name)
    codec at foreign boundaries becomes an option rather than a necessity
    on some paths.
  * Accepted trade-offs (a wash, not a regression): the collision profile
    shifts from PUA-in-data (icon fonts embedding U+E000) to
    US-in-data (delimited-record pipelines using 0x1F as a field
    separator) — both remain the same documented out-of-warranty forgery
    class (see ``demangle``/``is_mangled`` below). Debugger visibility
    worsens (0x1F is an invisible control character, unlike U+E000's
    visible placeholder glyph); this is mitigated by writer demangling
    (``demangle_for_display``) being the actual display path — raw
    mangled strs are not meant to be eyeballed.

This module is the SINGLE SOURCE OF TRUTH for the separator: every other
consumer (``clausal/templating/term_rewriting.py``'s ``-hide`` handling and
``visit_Name`` substitution, the reified-term renderers) imports
``HIDDEN_SEP``/``mangle``/``is_mangled``/``demangle*`` from here rather than
hardcoding the codepoint.

The toklex reserved class (``clausal/tools/toklex/specs/clausal.toklex.pl``,
``class(reserved, [...])``) is a SEPARATE, textual copy of the same
codepoint — the surface reader is a standalone Prolog-DCG-driven spec file,
not Python, so it cannot import this module.  R1(-revised) requires the two
to name the identical codepoint; keep them in lockstep by hand (see the
toklex spec's own comment for the cross-reference back to this module).
"""

from __future__ import annotations

import sys

#: The reserved codepoint separating a mangled atom's owning module name
#: from its bare spelling (design doc §1b, ruling R1-revised, 2026-09-05:
#: US, 0x1F — see the module docstring above for the full rationale and
#: for R1's original U+E000 choice this supersedes).  The Clausal surface
#: reader refuses this codepoint inside any atom token — quoted or not —
#: so a hidden atom's mangled spelling cannot be typed by hand in ordinary
#: source; only the compiler (this module's ``mangle``, called from the
#: owning module's own ``-hide`` handling) and out-of-warranty runtime
#: forgery (``atom_chars/2`` et al. building the str from individual
#: characters — §1b, documented, not blocked) can produce it.
HIDDEN_SEP = "\x1f"


def mangle(module_name: str, atom: str) -> str:
    """Compiler-rename ``atom`` into ``module_name``'s hidden namespace.

    Returns ``f"{module_name}{HIDDEN_SEP}{atom}"``, interned (``sys.intern``)
    so repeated calls for the same ``(module_name, atom)`` pair return the
    identical str object — atoms remain global-by-spelling identity (§1b/
    R2), it is simply the MANGLED spelling that is now module-scoped:
    every reference to a hidden atom within its owning module compiles to
    this same interned Constant (``term_rewriting.py``'s ``visit_Name``),
    so they unify with each other; a different module's same-spelled bare
    atom is a different, unmangled (or differently-mangled) str and does
    not unify with it at all.
    """
    return sys.intern(f"{module_name}{HIDDEN_SEP}{atom}")


def is_mangled(value) -> bool:
    """True if *value* is an ATOM whose spelling carries ``HIDDEN_SEP`` — i.e.
    is (or forges, per §1b's documented-out-of-warranty allowance) a mangled
    hidden-atom spelling.  False for anything that is not an atom.

    2026-09-06-atoms-as-cells-strings §5.3: these three helpers are
    SPELLING-level and accept "the atom as well as the spelling" — the cell
    ``("m\\x1fbar",)`` and the bare ``str`` ``"m\\x1fbar"`` alike — because
    every renderer reaches them holding one or the other (``terms.py`` has
    already unwrapped slot 0; ``io.py`` has not).  A ``str`` argument is NOT
    being treated as an atom term here; ``HIDDEN_SEP`` is reader-unwritable,
    so a string carrying it is the same documented out-of-warranty forgery
    the module docstring describes.
    """
    if type(value) is str:
        return HIDDEN_SEP in value
    return is_atom(value) and HIDDEN_SEP in value[0]


def demangle(value) -> tuple[str, str]:
    """Split a mangled atom (or its bare spelling) back into
    ``(module_name, atom)``.

    Raises ``ValueError`` if *value* is not mangled (``is_mangled`` false).
    Splits on the FIRST ``HIDDEN_SEP`` occurrence: a genuine ``mangle()``
    output never contains a second one (module/atom names are ordinary
    Clausal identifiers, and the surface reader refuses ``HIDDEN_SEP``
    inside any atom token — R1 — so neither half can itself carry the
    separator via the normal compiler path); a hand-forged str containing
    more than one is out-of-warranty input and gets the same first-split
    treatment rather than an error, matching ``demangle_for_display``'s
    best-effort spirit.
    """
    if not is_mangled(value):
        raise ValueError(f"not a mangled atom: {value!r}")
    text = value if type(value) is str else value[0]
    module_name, _, atom = text.partition(HIDDEN_SEP)
    return module_name, atom


def demangle_for_display(value) -> str:
    """Human-readable qualified form for printing (§1b: "Printing: the
    writer renders the human form (``m.my_atom``); the runtime str keeps
    ⟨SEP⟩") — ``"module⟨SEP⟩name"`` becomes ``"module.name"``, matching how
    qualified predicate references already render (dotted chain).

    Non-mangled input is returned unchanged (an ATOM is answered with its
    SPELLING — §5.3's unwrap; anything that is not an atom comes back as it
    arrived), so every renderer's atom case can call this unconditionally
    rather than branching on ``is_mangled`` itself first.
    """
    if not is_mangled(value):
        return spelling(value) if is_atom(value) else value
    module_name, atom = demangle(value)
    return f"{module_name}.{atom}"


# ── Public atom API (spec 2026-09-06-atoms-as-cells-strings-design §6.1) ──
#
# THE FLIP (Stage B, Task 11): an atom IS the arity-0 cell ``("bar",)`` — a
# 1-tuple whose slot 0 is the interned spelling — and a plain ``str`` is a
# STRING (the list of its char atoms), not an atom.  Callers written against
# these five names survived the flip unchanged.  Equality is the semantics;
# ``mint`` interns slot 0 as an optimisation only (never rely on ``is``, not
# even for the tuple: two ``mint`` calls return distinct, equal tuples).

#: The spelling of the ONE atom that is not a cell: ISO's reserved ``'[]'``,
#: which IS the empty list (fix round 1, item 2, operator-ruled 2026-09-07).
#: Scryer round-trips it — ``atom_chars(X, ['[', ']'])`` gives ``X = []``,
#: ``T =.. [[]]`` gives ``T = []``, ``functor(T, [], 0)`` gives ``T = []``,
#: ``atom_concat('[', ']', X)`` gives ``X = []`` — so ``mint`` canonicalises
#: it rather than minting a distinct ``("[]",)`` cell that would compare
#: unequal to the empty list it denotes.
NIL_SPELLING = "[]"


def mint(spelling: str):
    """Return the canonical atom for *spelling* — the cell ``(spelling,)``,
    except for ``'[]'``, which IS the empty list and is returned as ``[]``.

    The spelling is ``sys.intern``ed so equality between two equal atoms hits
    the identity fast path on slot 0 (spec §5.2).  There is deliberately NO
    process-wide atom TABLE either: nothing here maps a spelling back to a
    single canonical tuple, so two ``mint`` calls return distinct (equal)
    cells and no structure grows with the number of atoms ever made.

    Interning is permanent on this CPython — an interned string is immortal
    for the life of the interpreter — so ``mint`` is for **bounded**
    producers: compiler-emitted constants, declared atoms, the seeded pool,
    dict/JSON keys.  **Unbounded enumerators do not come here**:
    ``char_atom`` and the C result helpers (``char_atom_obj``,
    ``atom_from_str``) build the cell WITHOUT interning, because
    ``char_type/2`` alone visits ~49,000 characters and each interned
    spelling would be pinned forever (see ``char_atom``'s docstring and spec
    §5.2).  ``sub_atom/5``/``atom_concat/3`` are split between the two: their
    **Python** paths (``builtins/chars.py``) mint every substring and split
    half, so those pin; their C-accelerated paths
    (``_chars_core.atom_concat_split_find``/``sub_atom_search``/
    ``sub_atom_enum``) build the cell through ``atom_from_str``, which does
    not intern.  So the residual pinning §5.2 records is real, but only on
    the fallback paths — the twins deliberately differ here, and the
    difference is invisible to a program because equality is by ``==``.
    """
    if type(spelling) is not str:
        raise TypeError(f"mint: spelling must be a str, got {type(spelling).__name__}")
    if spelling == NIL_SPELLING:
        # ISO 6.3.5 / the fix-round-1 ruling: ``'[]'`` IS the empty list, so
        # there is no ``("[]",)`` cell to hand back.  A FRESH list every
        # call -- a list is mutable, so no instance may be shared.
        return []
    return (sys.intern(spelling),)


#: The HASHABLE spelling of nil, and the canonical form of a nil DICT KEY
#: (fix round 2, item 2, operator-ruled 2026-09-07).  ``mint("[]")`` answers
#: the empty LIST, which is mutable and therefore unhashable, so a nil atom
#: reaching a key position would crash with a raw ``TypeError``.  The empty
#: TUPLE is the same term — ``spelling(())`` is ``"[]"``, ``atomic(())`` is
#: true, ``()`` unifies with ``[]`` — and it is hashable, so it is what a
#: key position uses.
NIL_KEY: tuple = ()


def key_of(spelling: str):
    """The atom for *spelling* when it is going into a KEY position.

    :func:`mint` with one substitution: ``'[]'`` answers :data:`NIL_KEY`
    (the empty tuple) rather than the empty list, because a dict key must be
    hashable.  The two are the same term, so nothing downstream can tell
    them apart by unification or by ``atom/1``; only ``hash`` can.

    Use this — not ``mint`` — wherever the result is immediately used as a
    dict key: JSON object keys (``modules/py/json.py``), attribute names
    (``builtins/attributes.py``), and the ``py.*`` wrapper option tables
    (``modules/py/__init__.py``).
    """
    if type(spelling) is not str:
        raise TypeError(
            f"key_of: spelling must be a str, got {type(spelling).__name__}")
    if spelling == NIL_SPELLING:
        return NIL_KEY
    return (sys.intern(spelling),)


def as_dict_key(key):
    """*key* in its canonical DICT-KEY form.

    The empty list in any spelling — ``[]``, ``""``, ``b""``, ``()`` — is the
    one atom ``'[]'``, so all four must be ONE key.  Only ``()`` is both
    hashable and unambiguous (a ``str`` key ``""`` would otherwise be a
    different key from ``b""``), so every nil spelling normalises to it.
    Everything else passes through untouched.

    ``DictTerm`` applies this on construction and on every lookup, so a
    program cannot observe the difference.
    """
    if type(key) in (list, str, bytes, tuple) and len(key) == 0:
        return NIL_KEY
    return key


def is_atom(term) -> bool:
    """True iff *term* is an atom (the TERM test; a zero-field predicate class
    is not an atom — see ``predicate.is_atom_value`` for the value-level
    widening that still admits one).

    An atom is the arity-0 cell: a 1-tuple whose slot 0 is a ``str`` (THE
    DISCIPLINE, ``cells.py:53-64``).  A plain ``str`` is a STRING and is not
    an atom (spec §6.3)."""
    return type(term) is tuple and len(term) == 1 and type(term[0]) is str


def spelling(atom) -> str:
    """The spelling of *atom*; ``TypeError`` for a non-atom.

    The EMPTY LIST — ``[]``, ``""``, ``b""``, ``()`` — is the reserved atom
    ``'[]'`` (fix round 1, item 2) and answers ``"[]"``, the two bracket
    characters ``atom_length/2`` and ``atom_chars/2`` read.  ``is_atom``
    above stays the arity-0-CELL shape test, so it answers False for it; the
    TERM-level question "is this an atom?" is ``atom/1`` /
    ``type_checks._is_atom_term``, which admits both.
    """
    if type(atom) is tuple and len(atom) == 1 and type(atom[0]) is str:
        return atom[0]
    if type(atom) in (list, str, bytes, tuple) and len(atom) == 0:
        return NIL_SPELLING
    raise TypeError(f"not an atom: {atom!r}")


def char_atom(ch: str):
    """The atom whose spelling is the single character *ch*.

    Deliberately does NOT ``sys.intern`` the spelling, unlike ``mint``.  Two
    reasons, and they point the same way:

    * There is nothing to gain.  CPython already hands out singletons for
      every Latin-1 character, so an ASCII/Latin-1 char spelling is canonical
      before this function sees it, and comparing two 1-character strings is
      O(1) whether or not they are the same object.
    * There is something to lose.  ``sys.intern`` is permanent on CPython
      (an interned string is immortal and stays in the interned table for the
      life of the interpreter), and ``char_type/2`` enumerates over the whole
      Unicode alphabet — ``char_type(C, alpha)`` alone visits ~49,000
      characters.  Interning each would pin one immortal string per character
      ever enumerated, which is precisely the "enumeration garbage must not
      be pinned" rule spec §5.2 states for the atom table.

    Equality is unaffected: two char atoms of the same character compare
    equal by tuple ``==`` either way.
    """
    if type(ch) is not str or len(ch) != 1:
        raise ValueError(f"char_atom: expected a 1-char str, got {ch!r}")
    return (ch,)


def is_char_atom(term) -> bool:
    """True iff *term* is an atom whose spelling is one character."""
    return (
        type(term) is tuple
        and len(term) == 1
        and type(term[0]) is str
        and len(term[0]) == 1
    )


__all__ = [
    "HIDDEN_SEP", "NIL_SPELLING", "NIL_KEY", "mangle", "is_mangled",
    "demangle", "demangle_for_display", "mint", "key_of", "as_dict_key",
    "is_atom", "spelling", "char_atom", "is_char_atom",
]
