"""-module export elements: every spelling the engine reads crosses; anything else is refused.

``_convert_module_directive`` used to recognise only a call template and a bare
name, and silently DROPPED every other element. So ``-module(m, [edge/2])``,
the ISO predicate-indicator spelling the engine accepts and pins (ruling R6b;
tests/test_clauseless_export.py ISO_PI), exported NOTHING, and the emitted
module's export list shrank without a word.

The engine also reads the QUOTED forms ``'Edge'/2`` and ``'edge'(A, B)``
(``_predicate_export_spec``): for a capital-initial predicate the quoted form
is the only spelling, because bare ``Edge`` is a variable. A quoted name
crosses as written, and only when the literal rule makes it an atom.
"""

import pytest

from clausal.tools.clausal_to_prolog import clausal_source_to_prolog

_BODY = "edge(A, B) <- (A == B)\nnode(A) <- (A == 1)\n"


def _module_line(out):
    return next(line for line in out.splitlines() if line.startswith(":- module("))


def test_the_iso_predicate_indicator_crosses():
    # nv
    out = clausal_source_to_prolog("-module(m, [edge/2])\n\n" + _BODY)
    assert _module_line(out) == ":- module(m, [edge/2])."


def test_a_call_template_crosses():
    # nv
    out = clausal_source_to_prolog("-module(m, [edge(A, B)])\n\n" + _BODY)
    assert _module_line(out) == ":- module(m, [edge/2])."


def test_both_spellings_in_one_list():
    # nv
    out = clausal_source_to_prolog("-module(m, [edge/2, node(A)])\n\n" + _BODY)
    assert _module_line(out) == ":- module(m, [edge/2, node/1])."


@pytest.mark.parametrize("element", ["edge/two", "edge/-1", "edge/2.0", "3", "'edge'", "m.edge"])
def test_an_unclassifiable_element_is_refused(element):
    # nv
    with pytest.raises(NotImplementedError, match="is not an export element"):
        clausal_source_to_prolog(f"-module(m, [{element}])\n\n" + _BODY)


def test_a_quoted_capital_initial_indicator_crosses_as_written():
    """Measured 2026-09-26: the emitted ``:- module(m, ['Edge'/2]).`` plus
    ``'Edge'(1, 10).`` imports and answers ``[1-10,2-20]`` on both Scryer and
    Trealla."""
    # nv
    out = clausal_source_to_prolog("-module(m, ['Edge'/2])\n\n'Edge'(A, B) <- (A == B)\n")
    assert _module_line(out) == ":- module(m, ['Edge'/2])."


def test_a_quoted_functor_call_template_crosses_as_written():
    # nv
    out = clausal_source_to_prolog("-module(m, ['Edge'(A, B)])\n\n'Edge'(A, B) <- (A == B)\n")
    assert _module_line(out) == ":- module(m, ['Edge'/2])."


def test_a_quoted_lowercase_name_is_the_same_atom_as_the_bare_one():
    # nv
    out = clausal_source_to_prolog("-module(m, ['edge'(A, B)])\n\n" + _BODY)
    assert _module_line(out) == ":- module(m, [edge/2])."


@pytest.mark.parametrize("mode", ["", "-double_quotes(atom)\n", "-double_quotes(chars)\n"],
                         ids=["default", "atom", "chars"])
def test_a_double_quoted_name_is_refused_in_every_mode(mode):
    """As the engine refuses it (``_refuse_double_quoted_functor``, ISO 6.3.3):
    a double-quoted literal is never an atom spelling, whatever the mode. The
    first version of this accepted it in atom mode -- the translator's literal
    rule is mode-sensitive, the engine's functor rule is not."""
    # nv
    with pytest.raises(NotImplementedError, match="is not an export element"):
        clausal_source_to_prolog(
            mode + '-module(m, ["Edge"/2])\n\n\'Edge\'(A, B) <- (A == B)\n')


@pytest.mark.parametrize("element", ["'foo bar'/2", "'foo bar'(A, B)", "'class'/1", "'class'(A)"])
def test_a_quoted_name_must_be_a_plain_name(element):
    """As the engine requires (``_quoted_head_functor_name``: ``isidentifier()``
    and not a Python keyword), because it binds a declared functor as a
    module-level name."""
    # nv
    with pytest.raises(NotImplementedError, match="is not an export element"):
        clausal_source_to_prolog(f"-module(m, [{element}])\n\n" + _BODY)


def test_a_quoted_template_counts_keyword_arguments_into_its_arity():
    """The engine declares ``'Edge'(A, b=B)`` as Edge/2 -- measured
    2026-09-26, ``declared_kind('Edge', 2) == 'predicate'``, and a clause at
    arity 3 then conflicts with it."""
    # nv
    out = clausal_source_to_prolog("-module(m, ['Edge'(A, b=B)])\n\n'Edge'(A, B) <- (A == B)\n")
    assert _module_line(out) == ":- module(m, ['Edge'/2])."


def test_a_bare_template_with_keyword_arguments_is_refused():
    """The engine refuses it ("written with keyword arguments"), so counting
    it would accept an entry the engine rejects."""
    # nv
    with pytest.raises(NotImplementedError, match="is not an export element"):
        clausal_source_to_prolog("-module(m, [edge(A, b=B)])\n\n" + _BODY)


# ── Parity: the exporter accepts exactly the export entries the ENGINE accepts ──
#
# Each case is loaded by the engine AND translated by the exporter, and the two
# verdicts must agree. This is the check that would have caught the first
# version of the quoted-name rule, which followed the translator's own literal
# rule and so accepted "Edge"/2 in atom mode where the engine refuses it.

_HEAD2 = "'Edge'(A, B) <- (A == B)\n"
_PARITY = [
    ("iso_pi", "", "edge/2", "edge(A, B) <- (A == B)\n"),
    ("template", "", "edge(A, B)", "edge(A, B) <- (A == B)\n"),
    ("sq_pi_cap", "", "'Edge'/2", _HEAD2),
    ("sq_tmpl_cap", "", "'Edge'(A, B)", _HEAD2),
    ("sq_tmpl_lower", "", "'edge'(A, B)", "edge(A, B) <- (A == B)\n"),
    ("dq_pi_default", "", '"Edge"/2', _HEAD2),
    ("dq_pi_atom", "-double_quotes(atom)\n", '"Edge"/2', _HEAD2),
    ("dq_pi_chars", "-double_quotes(chars)\n", '"Edge"/2', _HEAD2),
    ("sq_space_pi", "", "'foo bar'/2", "p(X) <- (X == 1)\n"),
    ("sq_space_tmpl", "", "'foo bar'(A, B)", "p(X) <- (X == 1)\n"),
    ("sq_kwd_pi", "", "'class'/1", "p(X) <- (X == 1)\n"),
    ("sq_kwd_tmpl", "", "'class'(A)", "p(X) <- (X == 1)\n"),
    ("sq_tmpl_kwarg", "", "'Edge'(A, b=B)", _HEAD2),
    ("bare_tmpl_kwarg", "", "edge(A, b=B)", "edge(A, B) <- (A == B)\n"),
    # reserved truth names -- the engine refuses them before looking at shape
    ("tv_true", "", "true", "p(X) <- (X == 1)\n"),
    ("tv_true_call", "", "true(X)", "p(X) <- (X == 1)\n"),
    ("tv_true_pi", "", "true/0", "p(X) <- (X == 1)\n"),
    ("tv_True", "", "True", "p(X) <- (X == 1)\n"),
    ("tv_True_call", "", "True(X)", "p(X) <- (X == 1)\n"),
    ("tv_false", "", "false", "p(X) <- (X == 1)\n"),
    ("tv_undefined", "", "undefined", "p(X) <- (X == 1)\n"),
    ("tv_Undefined", "", "Undefined", "p(X) <- (X == 1)\n"),
    ("tv_undefined_pi", "", "undefined/1", "p(X) <- (X == 1)\n"),
    ("tv_sq_true_pi", "", "'true'/0", "p(X) <- (X == 1)\n"),
    ("tv_sq_true_call", "", "'true'(X)", "p(X) <- (X == 1)\n"),
    ("tv_sq_false_call", "", "'false'(X)", "p(X) <- (X == 1)\n"),
    # a mixed-quote literal
    ("mixed_quote_pi", "", "'Ed' \"ge\"/2", _HEAD2),
]


@pytest.mark.parametrize("cid,prefix,element,clauses", _PARITY, ids=[c[0] for c in _PARITY])
def test_export_acceptance_matches_the_engine(tmp_path, cid, prefix, element, clauses):
    """Any load error counts as an engine refusal, recorded by type; the
    exporter must refuse with NotImplementedError. The engine loads through
    ``import_hook._load_module``, which compiles privately and does not claim
    the ``_MODULES_BY_PATH`` registry, so nothing but ``sys.modules`` needs
    undoing."""
    # nv
    import sys
    from clausal.import_hook import _load_module
    name = f"expparity_{cid}"
    src = f"{prefix}-module({name}, [{element}])\n\n{clauses}"
    path = tmp_path / f"{name}.clausal"
    path.write_text(src)
    sys.modules.pop(name, None)
    try:
        _load_module(name, str(path))
        engine = "accepts"
    except Exception as exc:          # any load failure is a refusal
        engine = f"refuses ({type(exc).__name__})"
    finally:
        sys.modules.pop(name, None)
    try:
        clausal_source_to_prolog(src)
        exporter = "accepts"
    except NotImplementedError:
        exporter = "refuses"
    assert (engine == "accepts") == (exporter == "accepts"), (
        f"{element!r}: engine {engine}, exporter {exporter}")


@pytest.mark.parametrize("element", ["true", "true(X)", "true/0", "'true'/0", "Undefined", "False"])
def test_a_truth_value_is_not_an_export(element):
    # nv
    with pytest.raises(NotImplementedError, match="truth values"):
        clausal_source_to_prolog(f"-module(m, [{element}])\n\np(X) <- (X == 1)\n")


def test_a_mixed_quote_name_is_refused_as_an_export_element():
    """``quote_of`` raises a positionless SyntaxError for it; the exporter
    folds that into its own refusal, which names the element."""
    # nv
    with pytest.raises(NotImplementedError, match="is not an export element"):
        clausal_source_to_prolog("-module(m, ['Ed' \"ge\"/2])\n\n" + _HEAD2)
