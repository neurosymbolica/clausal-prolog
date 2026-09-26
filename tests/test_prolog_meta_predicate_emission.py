"""A multi-spec ``-meta_predicate`` crosses as ONE directive PER SPEC, after ``:- module``.

Three defects, one fixture each, all measured on both target engines:

* ``-meta_predicate(a(...), b(...))`` was emitted literally as meta_predicate/2.
  Scryer refuses the file (``domain_error(directive, meta_predicate/2)``);
  Trealla warns and DROPS the declarations. The comma-list ISO permits,
  ``meta_predicate((a(...), b(...)))``, is no escape: Scryer rejects it with
  ``syntax_error(invalid_meta_predicate_decl)``. One directive per spec is the
  only spelling both engines accept.
* The hand-written directive did not suppress the generated one, because the
  indicator reader only understood the one-argument shape -- so every
  predicate it named was declared twice.
* The ONE-argument comma-list spelling, ``meta_predicate((a, b))``, must be
  split as well: it is the spelling Scryer rejects, and left whole it would
  also suppress the generated fallback.
* A ``-meta_predicate`` written above ``-module`` stayed above it. Imported via
  use_module, that declaration still takes in Scryer but silently does NOT in
  Trealla, where a caller-module goal handed to the meta predicate then FAILS
  with no error.
"""

from clausal.tools.clausal_to_prolog import clausal_source_to_prolog


def _meta_lines(text):
    return [line for line in text.splitlines() if "meta_predicate" in line]


def test_multi_spec_directive_splits_one_per_spec():
    # nv
    out = clausal_source_to_prolog(
        "-meta_predicate(foo('?', 1), bar('?', 2))\n\n"
        "foo(A, B) <- (call(B, A))\n"
        "bar(A, B) <- (call(B, A, A))\n")
    assert _meta_lines(out) == [
        ":- meta_predicate(foo(?, 1)).",
        ":- meta_predicate(bar(?, 2)).",
    ]


def test_single_spec_directive_is_unchanged():
    # nv
    out = clausal_source_to_prolog(
        "-meta_predicate(foo('?', 1))\n\nfoo(A, B) <- (call(B, A))\n")
    assert _meta_lines(out) == [":- meta_predicate(foo(?, 1))."]


def _directives(text):
    return [line for line in text.splitlines() if line.startswith(":- ")]


_BODY = "foo(A, B) <- (call(B, A))\nbar(A, B) <- (call(B, A, A))\n"


def test_one_argument_comma_list_is_split_too():
    """The ISO comma-list spelling is exactly the one Scryer rejects
    (syntax_error(invalid_meta_predicate_decl)). It must be split, not passed
    through -- the indicator reader counts its specs as declared, so an unsplit
    comma-list would also suppress the generated fallback."""
    # nv
    out = clausal_source_to_prolog(
        "-meta_predicate((foo('?', 1), bar('?', 2)))\n\n" + _BODY)
    assert _meta_lines(out) == [
        ":- meta_predicate(foo(?, 1)).",
        ":- meta_predicate(bar(?, 2)).",
    ]


def test_meta_predicate_above_module_is_emitted_below_it():
    # nv
    out = clausal_source_to_prolog(
        "-meta_predicate(foo('?', 1), bar('?', 2))\n\n"
        "-module(lib, [foo(A, B), bar(A, B)])\n\n" + _BODY)
    directives = _directives(out)
    assert directives[0] == ":- module(lib, [foo/2, bar/2])."
    assert directives[1:] == [
        ":- meta_predicate(foo(?, 1)).",
        ":- meta_predicate(bar(?, 2)).",
    ]


def test_only_the_module_line_moves():
    """Everything written above -module keeps its relative order and stays
    ahead of the generated prelude; only the module line moves to the top.
    Pinned for op/3 and a flag because those were the reorder's open question:
    measured on both engines, an op above `:- module` is a syntax error in
    Trealla (and in both when the op is exported), and a use_module above it is
    an existence_error in Scryer. Below the module line all of them work."""
    # nv
    out = clausal_source_to_prolog(
        "-op(700, xfx, implies)\n"
        "-double_quotes(chars)\n"
        "-module(lib, [foo(A, B), bar(A, B)])\n\n" + _BODY)
    directives = _directives(out)
    assert directives[0] == ":- module(lib, [foo/2, bar/2])."
    assert directives[1:3] == [
        ":- op(700, xfx, implies).",
        ":- set_prolog_flag(double_quotes, chars).",
    ]
    assert directives[3:] == [
        ":- meta_predicate(foo(?, 1)).",
        ":- meta_predicate(bar(?, 2)).",
    ]


def test_a_second_module_directive_is_still_filtered():
    """Every module directive goes through the export filter, as it always
    did; the first rewrite of the reorder let a second one through unfiltered.
    The second one stays where it was written, and the generated block is NOT
    repeated after it. Exports are written as Clausal call templates -- a bare
    name crosses as Name/0, and ``foo/2`` is not an export element at all --
    so the filter has something to keep and something to drop."""
    # nv
    out = clausal_source_to_prolog(
        "-module(lib, [foo(A, B)])\n"
        "-module(lib2, [bar(A, B), nothere(X)])\n\n" + _BODY)
    assert _directives(out) == [
        ":- module(lib, [foo/2]).",
        ":- meta_predicate(foo(?, 1)).",
        ":- meta_predicate(bar(?, 2)).",
        ":- module(lib2, [bar/2]).",
    ]
    # ...and where it was written relative to the CLAUSES, not only to the
    # other directives: the source puts it above both clauses.
    lines = [line for line in out.splitlines() if line.strip()]
    second = lines.index(":- module(lib2, [bar/2]).")
    first_clause = next(i for i, line in enumerate(lines) if not line.startswith(":- "))
    assert second < first_clause


def test_meta_above_module_lands_ahead_of_the_generated_prelude():
    """A -meta_predicate written above -module comes out BELOW the module line
    but AHEAD of the generated prelude (here the clpz import). Measured
    2026-09-26 on both engines, through use_module with a caller-module goal, a
    2-meta, a library(lambda) goal passed through the meta predicate and #= in
    the body: the answer is identical with the meta declaration ahead of or
    behind the generated imports. So this order is harmless -- pinned so a
    change to it is a decision, not an accident."""
    # nv
    out = clausal_source_to_prolog(
        "-meta_predicate(apply1(1, '?'))\n\n"
        "-module(lib, [apply1(G, X), five(Z)])\n\n"
        "apply1(G, X) <- (call(G, X))\n"
        "five(Z) <- (Z == 2 + 3)\n")
    assert _directives(out) == [
        ":- module(lib, [apply1/2, five/1]).",
        ":- meta_predicate(apply1(1, ?)).",
        ":- use_module(library(clpz), [(#=)/2]).",
    ]
