"""Actionable diagnostics for an undeclared bare atom that is really a literal.

An undeclared bare atom raises the same generic message whatever its name::

    strict_atoms: undeclared atom 'null' in acme.pricing.tier_rules
      bare atom references must be one of:
        - listed in -module(...), -private([...]), -import_from(...)
        - qualified (e.g. other_module.atom)
        - obtained via global_atom('atom', Atom)

Five remedies, and for ``null`` not one of them is the right answer.  The right
answer is ``Undefined``.  See
``todo/lowercase-true-false-null-should-name-the-True-False-Unknown-literals.md``:
in a 24-run local-model formalization study, ``undeclared atom(s) in module``
burned 69 repair attempts across 21 of 24 runs with 65% never recovering, and
``true`` (38), ``false`` (18) and ``null`` (7) are 63 of the 241 mentions — a
quarter of every incident is an author writing the Python/JSON spelling of a
value the language already has.

``true``, ``false`` and ``undefined`` no longer reach this module: they are
parse-time aliases for ``True``, ``False`` and ``Undefined``
(``clausal.pythonic_ast.conversion_from_python_ast``), which retires the two
largest buckets of the study by accepting the spelling rather than diagnosing
it.  What is left here is the JSON/Python vocabulary that has no Clausal
meaning at all — ``null``, ``none``, ``nil``, ``maybe`` — plus ``unknown``, the
pre-rename spelling of ``Undefined``, which an older document or an author who
learned the earlier name will still write.

``Undefined`` earns a mention even when the misspelling is a boolean one: every
other atom in the language is lowercase, titlecase normally reads as a variable,
so the third truth value is the piece a reader is least likely to guess on their
own.

This module holds no ``clausal`` imports so that both raise sites — the
bare-atom-reference diagnostic in :mod:`clausal.logic.compiler_v2` and the
dict-key path in :mod:`clausal.import_hook` — can import it at module level.
"""

from __future__ import annotations

# Case-insensitive.  ``True``/``False``/``Undefined`` are already bound — as are
# the lowercase aliases ``true``/``false``/``undefined`` — and so never reach a
# raise site, which is why folding case here cannot shadow a spelling that
# works.  The corpus carries no bare ``nil``/``none``/``maybe``/``unknown``
# outside comments, so nothing legitimate collides with the set; a false
# positive would only add an off-target suggestion to an error that is already
# fatal.
#
# ``unknown`` is deliberately NOT an alias.  It was this value's name before the
# rename to ``Undefined`` (which follows XSB/SWI), and binding both spellings
# would leave the language with exactly the two-names-for-one-value ambiguity
# the rename set out to remove.  Diagnosing it instead retires the old name
# while still landing an author who writes it on the right one.
_TRUTH_LITERALS = {
    "null": "Undefined",
    "none": "Undefined",
    "nil": "Undefined",
    "unknown": "Undefined",
    "maybe": "Undefined",
}


def truth_literal_hint_lines(names, indent: str = "  ") -> list[str]:
    """Hint lines steering unknown-ish spellings at the real literal.

    Returns ``[]`` when no name matches, so a diagnostic about ordinary atoms
    keeps its wording byte-for-byte and the passing path costs one dict lookup
    per undeclared name.

    The three-value explanation is stated once however many names matched, but
    every matching name gets its own arrow.  Collapsing instead on the
    *literal* would leave a second synonym unmentioned — with `null` and `nil`
    both undeclared, the author would fix `null`, re-run, and meet `nil` on the
    next pass.

    Names are reported in first-seen order, de-duplicated.
    """
    matched: list[tuple[str, str]] = []
    seen: set[str] = set()
    for name in names:
        literal = _TRUTH_LITERALS.get(name.lower())
        if literal is None or name in seen:
            continue
        seen.add(name)
        matched.append((name, literal))

    if not matched:
        return []

    subject = ", ".join(f"`{name}`" for name, _ in matched)
    verb = "is not a literal" if len(matched) == 1 else "are not literals"
    lines = [
        f"{indent}{subject} {verb} in Clausal — the boolean literals are "
        f"`True`",
        f"{indent}and `False` (or `true`/`false`), and the third truth value "
        f"under",
        f"{indent}well-founded semantics is `Undefined` (or `undefined`).",
    ]
    # One bad name is the overwhelmingly common case; leave its arrow bare
    # rather than qualifying a name the reader just saw in the sentence above.
    if len(matched) == 1:
        lines.append(f"{indent}-> did you mean `{matched[0][1]}`?")
    else:
        lines.extend(
            f"{indent}-> `{name}`: did you mean `{literal}`?"
            for name, literal in matched
        )
    return lines
