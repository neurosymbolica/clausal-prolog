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

    2026-09-06-atoms-as-cells-strings §5.3: the atom itself is accepted
    beside its bare spelling, so a caller holding ``("m\\x1fbar",)`` need not
    unwrap first.  Under Stage A's dual-accepting ``is_atom`` a plain ``str``
    is still an atom, so this is a no-op widening today.
    """
    return is_atom(value) and HIDDEN_SEP in spelling(value)


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
    module_name, _, atom = spelling(value).partition(HIDDEN_SEP)
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
# Plan 0 bodies: an atom IS its spelling (a plain str) on this tree.  Stage B
# of the same plan rewrites the five bodies below to the arity-0 cell
# ``(spelling,)`` — callers written against these names survive that flip
# unchanged.  Equality is the semantics; ``mint`` returns a canonical object
# as an optimisation only (never rely on ``is``).

def mint(spelling: str):
    """Return the canonical atom for *spelling*."""
    if type(spelling) is not str:
        raise TypeError(f"mint: spelling must be a str, got {type(spelling).__name__}")
    return sys.intern(spelling)


def is_atom(term) -> bool:
    """True iff *term* is an atom (the TERM test; a zero-field predicate class
    is not an atom — see ``predicate.is_atom_value`` for the value-level
    widening that still admits one).

    Stage A dual-acceptance (2026-09-06-atoms-as-cells-strings, controller
    ruling on Task 2): today's ``str`` atom AND the arity-0 cell
    ``("bar",)`` the Stage B flip will make canonical are both atoms here.
    Task 11 narrows this to the cell only."""
    return type(term) is str or (
        type(term) is tuple and len(term) == 1 and type(term[0]) is str
    )


def spelling(atom) -> str:
    """The spelling of *atom*; ``TypeError`` for a non-atom."""
    if type(atom) is str:
        return atom
    if is_atom(atom):
        return atom[0]
    raise TypeError(f"not an atom: {atom!r}")


def char_atom(ch: str):
    """The atom whose spelling is the single character *ch*."""
    if type(ch) is not str or len(ch) != 1:
        raise ValueError(f"char_atom: expected a 1-char str, got {ch!r}")
    return mint(ch)


def is_char_atom(term) -> bool:
    """True iff *term* is an atom whose spelling is one character."""
    return is_atom(term) and len(spelling(term)) == 1


__all__ = [
    "HIDDEN_SEP", "mangle", "is_mangled", "demangle", "demangle_for_display",
    "mint", "is_atom", "spelling", "char_atom", "is_char_atom",
]
