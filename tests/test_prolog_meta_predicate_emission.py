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
* A ``-meta_predicate`` written above ``-module`` stayed above it. Imported via
  use_module, that declaration still takes in Scryer but silently does NOT in
  Trealla, where a caller-module goal handed to the meta predicate then FAILS
  with no error.
"""

from clausal.tools.clausal_to_prolog import clausal_source_to_prolog


def _meta_lines(text):
    return [line for line in text.splitlines() if "meta_predicate" in line]


def _first_directive(text):
    return next(line for line in text.splitlines() if line.strip())


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


def test_meta_predicate_above_module_is_emitted_below_it():
    # nv
    out = clausal_source_to_prolog(
        "-meta_predicate(foo('?', 1), bar('?', 2))\n\n"
        "-module(lib, [foo, bar])\n\n"
        "foo(A, B) <- (call(B, A))\n"
        "bar(A, B) <- (call(B, A, A))\n")
    assert _first_directive(out).startswith(":- module(lib, ")
    assert len(_meta_lines(out)) == 2
