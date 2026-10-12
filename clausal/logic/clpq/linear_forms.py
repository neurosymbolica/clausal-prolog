# Ported from clp(q,r) version 1.3.3, file store.pl
# (c) Copyright 1992,1993,1994,1995 Austrian Research Institute for
# Artificial Intelligence (OFAI).  Author: Christian Holzbaur.
# See clausal/logic/clpq/PROVENANCE.md.
"""Linear forms: store.pl.

1.3.3's linear form `[Inhomogeneous, Rest | Terms]`, with `Terms = [X*K, ...]`
sorted by the variables' order (variable_ordering.compare_variable_order),
is the record `LinearForm(constant, rest, terms)`; `terms` is a list of
`(variable, coefficient)` pairs in the same order.  Coefficients and
constants are rationals (arithmetic.py).  A function may hand back a list
it was given, as 1.3.3 shares list tails (test_multiply_linear_factor shows
the form itself coming back for a factor of 1).

A predicate that can fail returns None where it fails.
"""
from clausal.logic.clpq.arithmetic import (
    ONE, ZERO, add, arithmetic_normalize, compare, divide, is_zero,
    make_rational, multiply, negate, sign, to_number)
from clausal.logic.clpq.attributes import state_of
from clausal.logic.clpq.variable_ordering import (
    compare_order_values, compare_variable_order)
from clausal.logic.variables import deref, is_var

MINUS_ONE = (-1, 1)


class LinearForm:
    """store.pl's `[Inhomogeneous, Rest | Terms]` (decompose/4 splits it)."""
    __slots__ = ("constant", "rest", "terms")

    def __init__(self, constant, rest, terms):
        self.constant = constant
        self.rest = rest
        self.terms = terms

    def __repr__(self):
        return f"LinearForm({self.constant!r}, {self.rest!r}, {self.terms!r})"


def normalize_scalar(scalar):
    """store.pl, normalize_scalar/2: the constant form [N, 0]."""
    return LinearForm(make_rational(scalar[0], scalar[1]), ZERO, [])


def renormalize(form):
    """store.pl, renormalize/2: re-sort a form after bindings and changed
    orders, folding bound variables into the constant
    (test_renormalize_follows_an_imposed_order,
    test_renormalize_folds_bound_variables_into_the_constant)."""
    length = len(form.terms)
    if length == 0:
        # DEVIATIONS.md D5 (test_renormalize_of_an_empty_homogeneous_part_raises)
        raise ValueError("renormalize: empty homogeneous part")
    balanced = renormalize_balanced(length, form.terms, 0)
    if balanced is None:
        return None
    return add_linear_forms(LinearForm(form.constant, form.rest, []), balanced[0])


def renormalize_balanced(count, terms, start):
    """store.pl, renormalize_log/4: the sum of terms[start:start+count] as a
    form, by halving.  Returns (form, start + count), or None.  The
    recursion halves its input, so its depth is log2(count)
    (test_renormalize_recursion_is_logarithmic)."""
    if count == 1:
        return renormalize_balanced_one(terms[start]), start + 1
    if count == 2:
        form_a = renormalize_balanced_one(terms[start])
        form_b = renormalize_balanced_one(terms[start + 1])
        form = add_linear_forms(form_a, form_b)
        if form is None:
            return None
        return form, start + 2
    first = count >> 1
    second = count - first
    left = renormalize_balanced(first, terms, start)
    if left is None:
        return None
    right = renormalize_balanced(second, terms, left[1])
    if right is None:
        return None
    form = add_linear_forms(left[0], right[0])
    if form is None:
        return None
    return form, right[1]


def renormalize_balanced_one(term):
    """store.pl, renormalize_log_one/3."""
    variable = deref(term[0])
    if is_var(variable):
        return LinearForm(ZERO, ZERO, [(variable, term[1])])
    # A bound variable is any engine number: arithmetic_normalize reads a
    # float as 1.3.3's get_rational/3 does
    # (test_renormalize_folds_a_variable_bound_to_a_float).
    return normalize_scalar(multiply(arithmetic_normalize(variable), term[1]))


# ----------------------------------------------------------- sparse vector stuff

def add_linear_forms_scaled(form_a, factor_a, form_b, factor_b):
    """store.pl, add_linear_ff/5: factor_a*form_a + factor_b*form_b."""
    terms = add_homogeneous_parts_scaled(form_a.terms, factor_a,
                                         form_b.terms, factor_b)
    if terms is None:
        return None
    constant = add(multiply(form_a.constant, factor_a),
                   multiply(form_b.constant, factor_b))
    rest = add(multiply(form_a.rest, factor_a), multiply(form_b.rest, factor_b))
    return LinearForm(constant, rest, terms)


def add_homogeneous_parts_scaled(terms_a, factor_a, terms_b, factor_b):
    """store.pl, add_linear_ffh/5,7.  The recursion of add_linear_ffh/7,
    unrolled into a two-way merge; its argument swap becomes the two
    indices.  Only a variable in both lists has its zero sum dropped
    (test_a_zero_factor_keeps_unmerged_terms_as_1_3_3_does)."""
    if not terms_a:                                     # add_linear_ffh/5
        return multiply_homogeneous_part(terms_b, factor_b)
    result = []
    i = 0
    j = 0
    while i < len(terms_a) and j < len(terms_b):
        x, coefficient_x = terms_a[i]
        y, coefficient_y = terms_b[j]
        relation = compare_variable_order(x, y)
        if relation is None:
            return None
        if relation == 0:
            coefficient = add(multiply(coefficient_x, factor_a),
                              multiply(coefficient_y, factor_b))
            if not is_zero(coefficient):
                result.append((x, coefficient))
            i += 1
            j += 1
        elif relation < 0:
            result.append((x, multiply(coefficient_x, factor_a)))
            i += 1
        else:
            result.append((y, multiply(coefficient_y, factor_b)))
            j += 1
    while i < len(terms_a):                             # mult_hom on the rest of A
        result.append((terms_a[i][0], multiply(terms_a[i][1], factor_a)))
        i += 1
    while j < len(terms_b):                             # mult_hom on the rest of B
        result.append((terms_b[j][0], multiply(terms_b[j][1], factor_b)))
        j += 1
    return result


def add_linear_forms_first_scaled(form_a, factor_a, form_b):
    """store.pl, add_linear_f1/4: factor_a*form_a + form_b."""
    terms = add_homogeneous_parts_first_scaled(form_a.terms, factor_a, form_b.terms)
    if terms is None:
        return None
    constant = add(multiply(form_a.constant, factor_a), form_b.constant)
    rest = add(multiply(form_a.rest, factor_a), form_b.rest)
    return LinearForm(constant, rest, terms)


def add_homogeneous_parts_first_scaled(terms_a, factor_a, terms_b):
    """store.pl, add_linear_f1h/4,6, unrolled into a two-way merge."""
    if not terms_a:                                     # add_linear_f1h/4
        return terms_b
    result = []
    i = 0
    j = 0
    while i < len(terms_a) and j < len(terms_b):
        x, coefficient_x = terms_a[i]
        y, coefficient_y = terms_b[j]
        relation = compare_variable_order(x, y)
        if relation is None:
            return None
        if relation == 0:
            coefficient = add(multiply(coefficient_x, factor_a), coefficient_y)
            if not is_zero(coefficient):
                result.append((x, coefficient))
            i += 1
            j += 1
        elif relation < 0:
            result.append((x, multiply(coefficient_x, factor_a)))
            i += 1
        else:
            result.append((y, coefficient_y))
            j += 1
    while i < len(terms_a):                             # mult_hom on the rest of A
        result.append((terms_a[i][0], multiply(terms_a[i][1], factor_a)))
        i += 1
    while j < len(terms_b):                             # the rest of B, as it is
        result.append(terms_b[j])
        j += 1
    return result


def add_linear_forms(form_a, form_b):
    """store.pl, add_linear_11/3: form_a + form_b."""
    terms = add_homogeneous_parts(form_a.terms, form_b.terms)
    if terms is None:
        return None
    return LinearForm(add(form_a.constant, form_b.constant),
                      add(form_a.rest, form_b.rest), terms)


def add_homogeneous_parts(terms_a, terms_b):
    """store.pl, add_linear_11h/3,5, unrolled into a two-way merge."""
    if not terms_a:                                     # add_linear_11h/3
        return terms_b
    if not terms_b:                                     # add_linear_11h/5, clause 1
        return terms_a
    result = []
    i = 0
    j = 0
    while i < len(terms_a) and j < len(terms_b):
        x, coefficient_x = terms_a[i]
        y, coefficient_y = terms_b[j]
        relation = compare_variable_order(x, y)
        if relation is None:
            return None
        if relation == 0:
            coefficient = add(coefficient_x, coefficient_y)
            if not is_zero(coefficient):
                result.append((x, coefficient))
            i += 1
            j += 1
        elif relation < 0:
            result.append(terms_a[i])
            i += 1
        else:
            result.append(terms_b[j])
            j += 1
    while i < len(terms_a):
        result.append(terms_a[i])
        i += 1
    while j < len(terms_b):
        result.append(terms_b[j])
        j += 1
    return result


def multiply_linear_factor(form, factor):
    """store.pl, mult_linear_factor/3.  A factor of 1 returns *form* itself
    ("avoid copy")."""
    if compare(factor, ONE) == 0:
        return form
    return LinearForm(multiply(form.constant, factor), multiply(form.rest, factor),
                      multiply_homogeneous_part(form.terms, factor))


def multiply_homogeneous_part(terms, factor):
    """store.pl, mult_hom/3.  Keeps zero products, as 1.3.3 does (its
    zero-dropping variant is commented out in store.pl)."""
    result = []
    for variable, coefficient in terms:
        result.append((variable, multiply(factor, coefficient)))
    return result


def normal_form_substitute(variable, form_variable, form_x):
    """store.pl, nf_substitute/4: replace *variable* in *form_x* by its
    definition *form_variable*.  None where *variable* is not in *form_x*."""
    deleted = delete_factor(variable, form_x)
    if deleted is None:
        return None
    form_w, coefficient = deleted
    return add_linear_forms_first_scaled(form_variable, coefficient, form_w)


def delete_factor(variable, form):
    """store.pl, delete_factor/4.  Returns (form without *variable*, its
    coefficient), or None."""
    deleted = delete_factor_homogeneous(variable, form.terms)
    if deleted is None:
        return None
    return LinearForm(form.constant, form.rest, deleted[0]), deleted[1]


def delete_factor_homogeneous(variable, terms):
    """store.pl, delete_factor_hom/4: the live version, which compares the
    variables themselves and continues on both (<) and (>), so it finds
    *variable* by identity (test_delete_factor_removes_one_variable).  Returns (terms without it, its coefficient), or
    None."""
    variable = deref(variable)
    for i in range(len(terms)):
        if deref(terms[i][0]) is variable:
            return terms[:i] + terms[i + 1:], terms[i][1]
    return None


def normal_form_coefficient_of(form, variable):
    """store.pl, nf_coeff_of/3: the coefficient of *variable* in *form*, or
    None."""
    state = state_of(variable)
    if state is None or state.variable_order is None:
        return None
    return normal_form_coefficient_homogeneous(form.terms, state.variable_order)


def normal_form_coefficient_homogeneous(terms, order):
    """store.pl, nf_coeff_hom/3: scan while the sought order is greater; stop
    at the first term not below it
    (test_coefficient_lookup_stops_once_past_the_variable)."""
    for variable, coefficient in terms:
        state = state_of(variable)
        if state is None or state.variable_order is None:
            return None
        relation = compare_order_values(order, state.variable_order)
        if relation == 0:
            return coefficient
        if relation < 0:
            return None
    return None


def normal_form_right_hand_side(form, x):
    """store.pl, nf_rhs_x/4.  Returns (rest + constant, coefficient of x), or
    None."""
    state = state_of(x)
    if state is None or state.variable_order is None:
        return None
    coefficient = normal_form_coefficient_homogeneous(form.terms, state.variable_order)
    if coefficient is None:
        return None
    return add(form.rest, form.constant), coefficient


def isolate(variable, form):
    """store.pl, isolate/3: solve 0 = form for *variable*."""
    deleted = delete_factor(variable, form)
    if deleted is None:
        return None
    form_0, coefficient = deleted
    return multiply_linear_factor(form_0, divide(MINUS_ONE, coefficient))


def independent(form, x):
    """store.pl, indep/2: *form* is exactly 1*x."""
    if len(form.terms) != 1:
        return False
    y, coefficient = form.terms[0]
    return (deref(x) is deref(y) and compare(coefficient, ONE) == 0
            and is_zero(form.constant))


def normal_form_to_sum(terms, constant):
    """store.pl, nf2sum/3: the term constant + sum K*X, written as 1.3.3
    writes it (cells '+', '-', '*').  The rationals become engine numbers
    (to_number), as normal_form_to_term writes them, so a term never holds
    a rational pair that reads as a compound
    (test_normal_form_to_sum_writes_engine_numbers)."""
    if not terms:
        return to_number(constant)
    if is_zero(constant):
        variable, coefficient = terms[0]
        if compare(coefficient, ONE) == 0:
            start = variable
        elif compare(coefficient, MINUS_ONE) == 0:
            start = ("-", variable)
        else:
            start = ("*", to_number(coefficient), variable)
        return homogeneous_to_sum(terms[1:], start)
    return homogeneous_to_sum(terms, to_number(constant))


def homogeneous_to_sum(terms, so_far):
    """store.pl, hom2sum/3, with engine numbers (see normal_form_to_sum)."""
    for variable, coefficient in terms:
        if compare(coefficient, ONE) == 0:
            so_far = ("+", so_far, variable)
        elif compare(coefficient, MINUS_ONE) == 0:
            so_far = ("-", so_far, variable)
        elif sign(coefficient) < 0:
            so_far = ("-", so_far, ("*", to_number(negate(coefficient)), variable))
        else:
            so_far = ("+", so_far, ("*", to_number(coefficient), variable))
    return so_far
