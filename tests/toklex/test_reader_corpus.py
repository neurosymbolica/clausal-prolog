"""Task 6: corpus integration.

Runs the whole reader stack (toklex L0 -> Pratt L1 -> ReaderItems) over the
real Scryer Prolog library corpus (``/workspace/scryer-prolog/src/lib``).

``lists.pl`` head, verified by reading the file directly: it opens with a
block comment, then ``:- module(lists, [...]).`` as the first item, matching
the brief's spot-check assumption exactly -- no adjustment needed.

``nested_comments=False``: the reader's ``PrologReader``/``read_module``
default (``nested_comments=True``) is a *clausal-dialect* choice (clausal's
own ``/* /* */ */`` nests). Real Scryer/SWI/ISO library source never nests
block comments -- and at least one corpus file (``crypto.pl``) contains a
stray ``/*`` inside its opening comment that, read with the nesting default,
swallows the entire rest of the file as one unterminated comment (zero items
back, not even a SyntaxIssue). ``nested_comments=False`` is an existing,
already-tested toggle (see ``tests/toklex/test_iso_spec.py::
test_strict_iso_comments_flag``) -- reading genuinely external Prolog
dialect source with it is a call-site choice, not a reader code change.
Verified this doesn't regress any other corpus file (same failing-file set
before/after). See the Task 6 report for the parked design question this
raises (nested_comments not wired through the ``dialect`` param).
"""

import glob

import pytest

from clausal.tools.prolog_reader import SyntaxIssue, read_module

CORPUS = sorted(glob.glob("/workspace/scryer-prolog/src/lib/**/*.pl", recursive=True))

# Per-file exceptions: path -> higher allowance, for files that trip the
# global issue-rate gate from well-understood DIALECT causes (never a reader
# defect -- see the Task 6 report for the per-file root-cause classification
# and the exact SyntaxIssue messages backing each number below).
_EXCEPTIONS: dict[str, int] = {
    # 36 issues / 326 items. 35 are `:- non_counted_backtracking Name/Arity.`
    # directives: `non_counted_backtracking` is declared `op(700, fx, ...)`
    # in ops_and_meta_predicates.pl, a SEPARATE library file the real system
    # loads before builtins.pl; read standalone, builtins.pl has no op
    # declaration in scope for it (a cross-file module-load-order dependency,
    # not a defect in this file's own syntax). The 1 remaining issue is
    # `(|)` -- a bare `|` atom in parens, at op/3's ISO permission_error
    # clause -- which requires `|` to already be usable as a plain atom;
    # ISO's solo-char set is only `! , ;`, so this is a Scryer/SWI-style
    # liberalization our SWI-default op table doesn't carry.
    "/workspace/scryer-prolog/src/lib/builtins.pl": 36,
    # 9 issues / 98 items, all `#=`/`#>=` -- library(clpz) constraint
    # operators. clpz.pl declares these via its own op directives when
    # loaded normally; read standalone, crypto.pl (which merely
    # `:- use_module(library(clpz))`s them) has no op declaration for them
    # in scope. Same cross-file dependency shape as non_counted_backtracking.
    "/workspace/scryer-prolog/src/lib/crypto.pl": 9,
    # 6 issues / 47 items, all `:- non_counted_backtracking Name/Arity.` --
    # same cross-file op-context gap as builtins.pl above.
    "/workspace/scryer-prolog/src/lib/iso_ext.pl": 6,
    # 5 issues / 96 items, all `Expected ')', got 'var'` on `//Spec`,
    # `/Spec`, `@Name` prefix uses. xpath.pl declares these ops NOT via a
    # top-level `:- op(...)` directive but as `op(400, fx, //)` etc. terms
    # embedded inside the `:- module(xpath, [...]).` export list -- a
    # SWI/Scryer module-system extension (op declarations inside a module's
    # export list are applied as a side effect of loading the module) that
    # this reader, by design, only interprets for literal top-level
    # `:- op(...)` directive items, not data nested inside another
    # directive's argument list.
    "/workspace/scryer-prolog/src/lib/xpath.pl": 5,
    # 3 issues / 23 items: 1 is `:- attribute when_list/1.` (SWI/SICStus
    # attribute-variable-library directive syntax, not ISO); 2 are
    # `Goal+\Var^(...)` -- the yall/lambda library's `+\` partial-application
    # operator, exactly the "partial-application syntax" dialect gap flagged
    # going in.
    "/workspace/scryer-prolog/src/lib/when.pl": 3,
}


def _allowance(path, n_items):
    return _EXCEPTIONS.get(path, max(2, n_items // 20))


@pytest.mark.parametrize("path", CORPUS or
    [pytest.param(None, marks=pytest.mark.skip(reason="corpus absent"))])
def test_corpus_reads_with_low_issue_rate(path):
    src = open(path, encoding="utf-8").read()
    items = read_module(src, nested_comments=False)
    assert items, path
    issues = [i for i in items if isinstance(i, SyntaxIssue)]
    # dialect gaps (0'\ shapes the old tokenizer also rejected, exotic ops)
    # may produce issues; the gate is that the reader RECOVERS and the
    # overwhelming majority of items parse.
    assert len(issues) <= _allowance(path, len(items)), (
        path, len(issues), len(items), issues[:3])


@pytest.mark.parametrize("path", CORPUS or
    [pytest.param(None, marks=pytest.mark.skip(reason="corpus absent"))])
def test_corpus_never_raises(path):
    """read_module must never raise on any corpus file -- lexical/parse
    trouble must always surface as a SyntaxIssue item, never an exception."""
    src = open(path, encoding="utf-8").read()
    try:
        read_module(src, nested_comments=False)
    except Exception as exc:  # pragma: no cover - defect if this ever fires
        pytest.fail(f"read_module raised on {path}: {exc!r}")


def test_spot_check_known_file():
    src = open("/workspace/scryer-prolog/src/lib/lists.pl", encoding="utf-8").read()
    items = read_module(src, nested_comments=False)
    from clausal.tools.prolog_reader import Clause, Directive
    assert isinstance(items[0], Directive)          # :- module(...)
    assert any(isinstance(i, Clause) for i in items)
    assert not any(isinstance(i, SyntaxIssue) for i in items)
