"""A test clause whose body is exactly ``true`` (or that is a fact) keeps
its name and its option.

The database stores ``H :- true`` exactly as the fact ``H``: each ground
head argument becomes a fresh variable plus a leading ``Unify`` body goal
(``Clause.hoisted``).  The runner read the raw head, so on both front ends
``test(name) :- true.`` was collected as ``_0`` and run as ``test(_)``, and
``test(name, fail) :- true.`` failed collection with ``test('_0', 'fail'):
unknown test option `'fail'```.  ``clausal.testing._clause_args`` reads the
hoisted arguments back.
"""

from __future__ import annotations

import pytest

from clausal.testing import collect_tests, load_clausal_module, run_test

PL = """\
q(X, X) :- true.
test(fact_form).
test(true_body) :- true.
test(conj_true_body) :- true, true.
test(neg_true_body, fail) :- true.
test(neg_fail_body, fail) :- fail.
test(var_true_body) :- q(1, Y), Y == 1.
test('quoted name', fail) :- true.
"""

SEAM = """\
q(X, X) <- True
test("fact_form"),
test("true_body") <- True
test("conj_true_body") <- (True, True)
test("neg_true_body", fail) <- True
test("neg_fail_body", fail) <- False
test("var_true_body") <- (q(1, Y), Y == 1)
test("quoted name", fail) <- True
"""

NAMES = ["fact_form", "true_body", "conj_true_body", "neg_true_body",
         "neg_fail_body", "var_true_body", "quoted name"]

#: name -> passed.  ``neg_true_body`` and ``quoted name`` are ``fail`` tests
#: whose goal succeeds: they FAIL (and are not errors).
PASSED = {"fact_form": True, "true_body": True, "conj_true_body": True,
          "neg_true_body": False, "neg_fail_body": True,
          "var_true_body": True, "quoted name": False}


@pytest.fixture(params=[("tb_seam.clausal", SEAM, None),
                        ("tb_seam2.seam", SEAM, None),
                        ("tb_native.pl", PL, "native"),
                        ("tb_translated.pl", PL, "translator")],
                ids=["clausal", "seam", "pl-native", "pl-translator"])
def true_body_module(request, tmp_path, monkeypatch):
    name, text, frontend = request.param
    if frontend is not None:
        monkeypatch.setenv("CLAUSAL_PL_FRONTEND", frontend)
    p = tmp_path / name
    p.write_text(text)
    return load_clausal_module(p)


def test_true_body_tests_keep_their_names(true_body_module):
    assert collect_tests(true_body_module) == NAMES


def test_true_body_tests_run_their_own_clause(true_body_module):
    for name in NAMES:
        r = run_test(true_body_module, name)
        assert r.error is None, (name, r.error)
        assert r.passed is PASSED[name], name
    assert run_test(true_body_module, "neg_true_body").negative
