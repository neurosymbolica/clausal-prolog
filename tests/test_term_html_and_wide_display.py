"""The HTML renderer and the wide (multi-line) display speak terms.

todo/done/display-multiline-hide-demangle-gap-2026-09-05.md.  ``term_html``
(Jupyter/IPython display) predated the atoms-as-str flip: it printed an ATOM
as a double-quoted STRING (``"foo"``), a STRING as the cell
``$chars("abc")``, and a ``-hide`` atom with its raw internal separator; the
wide ``term_pformat`` cell branch printed a hidden functor raw too.
"""
from clausal.logic.atoms import mangle
from clausal.logic.cells import chars
from clausal.terms import term_html, term_pformat


def _text(html):
    import re
    return re.sub(r"<[^>]+>", "", html).replace("&#x27;", "'").replace(
        "&quot;", '"')


def test_html_atom_string_and_hidden_atom():
    assert _text(term_html("foo")) == "foo"
    assert 'class="clausal-atom"' in term_html("foo")
    assert _text(term_html("A b")) == "'A b'"
    assert _text(term_html(chars("abc"))) == '"abc"'
    assert 'class="clausal-string"' in term_html(chars("abc"))
    assert _text(term_html(chars(""))) == "[]"
    assert _text(term_html(mangle("m", "s"))) == "m.s"
    assert _text(term_html((mangle("m", "s"), 1))) == "m.s(1)"
    assert _text(term_html(("f", "x"))) == "f(x)"


def test_wide_display_demangles_a_hidden_functor():
    out = term_pformat((mangle("m", "secret"), *range(40)), width=20)
    assert out.startswith("m.secret(\n")
    assert "\x1f" not in out
