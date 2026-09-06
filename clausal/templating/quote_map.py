"""Recovering the quote character that ``ast`` erases.

``ast.parse`` keeps a string literal's VALUE and throws its spelling away:
``'foo'`` and ``"foo"`` both arrive as ``Constant(value='foo')``.  The
strings design (spec §7) needs the two apart — a single-quoted literal is an
atom in every mode, a double-quoted one follows the module's
``-double_quotes`` mode, and a double-quoted literal is never a functor
(ISO 6.3.3) — so the compiler rebuilds the distinction from the token
stream and keys it by source position.  ``clausal/fmt/emit.py``'s
``_prefer_double_quotes`` is the existing precedent for tokenize-based
quote recovery in this tree.

The join between the two views is the column, and the two views count
columns differently:

* ``tokenize`` reports CHARACTER offsets;
* ``ast.col_offset`` / ``end_col_offset`` are UTF-8 **BYTE** offsets.

So the map stores byte columns, converted by encoding the line prefix —
the same reasoning ``term_rewriting._is_arrow_adjacent`` already applies to
``ast`` columns.

Each STRING token contributes TWO entries, its start and its end.  A
literal written by implicit concatenation (``"a" "b"``) is a single
``Constant`` spanning several tokens: its start position is the first
token's start and its end position is the LAST token's end, so the pair
answers "did this literal begin and end in the same style?" without the map
having to model concatenation at all.

f-strings are absent by construction: since Python 3.12 they tokenize as
``FSTRING_START``/``FSTRING_MIDDLE``/``FSTRING_END``, never ``STRING``.
They are also never ``Constant`` nodes, so nothing looks them up.
"""

import tokenize

__all__ = ["build_quote_map", "quote_of"]

# The prefix letters a string literal may carry before its opening quote.
# ``f`` is deliberately absent — an f-string is not a STRING token (and not a
# Constant), so it never reaches this module.
_STRING_PREFIX_LETTERS = "bBrRuU"


def _byte_col(source_lines: list[str], lineno: int, char_col: int) -> int | None:
    """Convert a 1-based line / 0-based CHARACTER column to a byte column.

    Returns ``None`` when *lineno* is outside *source_lines* — tokenize can
    report a position one past the last line (``ENDMARKER``), and a caller
    that trimmed its source should not crash the compiler over it.
    """
    if not 1 <= lineno <= len(source_lines):
        return None
    return len(source_lines[lineno - 1][:char_col].encode("utf-8"))


def build_quote_map(source_lines: list[str]) -> dict[tuple[int, int], str]:
    """Map ``(lineno, byte col_offset)`` → quote character for every literal.

    *source_lines* is the file's lines WITH line endings (what
    ``str.splitlines(keepends=True)`` produces and what ``EmbedTransformer``
    already carries).  Both the start and the end position of each STRING
    token are keyed, both to the same character.

    Falsy input (``None``, ``[]`` — the REPL/IPython transform site, which
    has no file to read) yields an empty map, and so does a tokenize
    failure: text that cannot be tokenized cannot be parsed either, so
    ``ast.parse`` is already raising the real error — this module has
    nothing better to say and no business pre-empting it.  This is the ONLY
    emptiness guard; callers pass whatever they have.
    """
    lines = list(source_lines or ())
    quote_map: dict[tuple[int, int], str] = {}
    try:
        for token in tokenize.generate_tokens(iter(lines).__next__):
            if token.type != tokenize.STRING:
                continue
            text = token.string
            prefix_len = len(text) - len(text.lstrip(_STRING_PREFIX_LETTERS))
            if prefix_len >= len(text):  # pragma: no cover — not a literal
                continue
            quote = text[prefix_len]
            if quote not in ("'", '"'):  # pragma: no cover — not a literal
                continue
            for lineno, char_col in (token.start, token.end):
                byte_col = _byte_col(lines, lineno, char_col)
                if byte_col is not None:
                    quote_map[(lineno, byte_col)] = quote
    except (tokenize.TokenError, SyntaxError, IndentationError, ValueError):
        return {}
    return quote_map


def quote_of(quote_map: dict[tuple[int, int], str], node) -> str | None:
    """The quote character *node* was written with, or ``None`` if unknown.

    ``None`` is the honest answer for a synthetic ``Constant`` (no position
    in any file), for a node from a source that was compiled without
    ``source_lines`` (the REPL/IPython transform site), and for any node
    that is not a string literal.  It is never an error: every caller reads
    it as "no opinion" and falls back to the pre-strings behaviour.

    The one thing that IS an error is a literal whose first and last tokens
    disagree — ``"a" 'b'``.  Implicit concatenation makes one term out of
    several tokens, and there is no defensible answer to "which mode does
    this literal follow?" when the author wrote both (spec §7).

    That error is raised as a BARE ``SyntaxError`` — message only, no
    position tuple.  This module holds neither the filename nor the source
    text, and a ``SyntaxError`` carrying ``filename=None`` is worse than one
    carrying nothing: ``syntax_diagnostics.enrich_syntax_error`` bails on
    ``exc.filename != filename``, so a half-filled position silently opts
    the error OUT of the caret window it looks like it is asking for.
    Positioning is the caller's job, and callers inside the compiler do it
    through ``term_rewriting._quote_of_positioned``.
    """
    lineno = getattr(node, "lineno", None)
    col = getattr(node, "col_offset", None)
    if lineno is None or col is None:
        return None
    start = quote_map.get((lineno, col))
    end_lineno = getattr(node, "end_lineno", None)
    end_col = getattr(node, "end_col_offset", None)
    end = None
    if end_lineno is not None and end_col is not None:
        end = quote_map.get((end_lineno, end_col))
    if start is not None and end is not None and start != end:
        raise SyntaxError(
            "mixed quote styles in one literal: an implicitly concatenated "
            "string literal must be written entirely in one style, because "
            "the style is what decides whether it is an atom or a string"
        )
    return start
