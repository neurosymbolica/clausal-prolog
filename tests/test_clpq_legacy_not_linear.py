"""The default CLP(Q) solver refuses what it cannot linearise with an ISO
error, never a Python TypeError.

A non-linear operand is ``domain_error(linear_expression, Operand)`` (the
``CLAUSAL_CLPQ=holzbaur`` port delays it instead; docs/clpq.md).  An operand
that is no arithmetic expression is nf.pl's ``type_error(expression,
Culprit)``, as ``entailed/1`` and the port raise.  The solver is called
directly, so these hold whatever ``CLAUSAL_CLPQ`` says.
"""
import pytest

from clausal.logic.clpq import legacy
from clausal.logic.exceptions import LogicException, type_error
from clausal.logic.variables import Trail, Var, deref, is_var
from clausal.terms import Mult


def _raised(call):
    with pytest.raises(LogicException) as caught:
        call()
    return caught.value.term


def _is_a_product_of_variables(term):
    """The culprit is a copy (an error carries fresh variables)."""
    return (type(term) is Mult and is_var(deref(term.left))
            and is_var(deref(term.right)))


def _context(name):
    functor, arity = name.rsplit("/", 1)
    return ("/", functor, int(arity))


@pytest.mark.parametrize("post, context", [
    (legacy.q_eq, "{}/1"), (legacy.q_ne, "{}/1"),
    (legacy.q_le, "=</2"), (legacy.q_lt, "</2"),
    (legacy.q_ge, "=</2"), (legacy.q_gt, "</2"),
], ids=["=", "=\\=", "=<", "<", ">=", ">"])
def test_a_non_linear_constraint_is_a_domain_error(post, context):
    # A bound names the comparison it posts, as its other errors do:
    # X >= Y posts Y =< X.
    x, y = Var(), Var()
    product = Mult(left=x, right=y)
    term = _raised(lambda: post(product, 10, Trail()))
    assert term[1][:2] == ("domain_error", "linear_expression"), term
    assert _is_a_product_of_variables(term[1][2]), term
    assert term[2] == _context(context), term


@pytest.mark.parametrize("objective, context", [
    (lambda e, t: legacy.sup(e, Var(), t), "sup/2"),
    (lambda e, t: legacy.inf(e, Var(), t), "inf/2"),
    (lambda e, t: legacy.maximize(e, Var(), t), "maximize/1"),
    (lambda e, t: legacy.minimize(e, Var(), t), "minimize/1"),
    (lambda e, t: legacy.bb_inf([], e, Var(), t), "bb_inf/3"),
], ids=["sup", "inf", "maximize", "minimize", "bb_inf"])
def test_a_non_linear_objective_is_a_domain_error(objective, context):
    t = Trail()
    x, y = Var(), Var()
    assert legacy.q_ge(x, 1, t) and legacy.q_ge(y, 1, t)
    product = Mult(left=x, right=y)
    term = _raised(lambda: objective(product, t))
    assert term[1][:2] == ("domain_error", "linear_expression"), term
    assert _is_a_product_of_variables(term[1][2]), term
    assert term[2] == _context(context), term


def test_an_operand_that_is_no_expression_is_a_type_error():
    x = Var()
    culprit = [1, 2]
    term = _raised(lambda: legacy.q_eq(Mult(left=x, right=culprit), 10, Trail()))
    assert term == type_error("expression", culprit, "normal_form/2")
