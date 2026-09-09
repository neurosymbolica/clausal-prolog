"""Execute the bytes-as-lists doc-example fixture.

The fixture ``tests/fixtures/docs/bytes_as_lists_examples.clausal`` claims in
its header that "every test/1 clause here is executed by the test suite, so the
examples in the documentation are guaranteed to stay correct." The doc-snippet
coverage checker only verifies the file *exists* and *contains* Test clauses —
it never runs them. This test makes the guarantee real: it loads the fixture
and drives test/1, so a regression in any documented example fails loudly.
"""
from pathlib import Path

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref

_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "docs" / "bytes_as_lists_examples.clausal"
)


def test_bytes_doc_examples_all_pass():
    # nv  — every test/1 clause body must succeed; count locks against silent drops
    mod = _load_module("bytes_doc_examples", str(_FIXTURE)).__dict__["$module"]
    X = Var()
    names = [deref(X) for _ in call("test", X, module=mod)]
    assert len(names) == 24
    # no duplicate / dropped example names
    assert len(set(names)) == 24
