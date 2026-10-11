# Ported from clp(q,r) version 1.3.3, file class.pl
# (c) Copyright 1992,1993,1994,1995 Austrian Research Institute for
# Artificial Intelligence (OFAI).  Author: Christian Holzbaur.
# See clausal/logic/clpq/PROVENANCE.md.
"""Components: class.pl, the connected components of constrained variables.

A component is a hidden variable whose COMPONENT_KEY attribute holds a
ComponentRecord: 1.3.3's `component_attributes(All, AllT, Basis, Priority)`.
Records are immutable by convention and replaced through put_attr, so the
trail undoes every change (test_a_basis_add_is_undone_to_the_mark).

Two components merge when their variables are unified, as in 1.3.3: the
engine binds one to the other and calls verify_component, class.pl's
verify_attributes/3
(test_a_merge_through_verify_component_is_undone_to_two_components).

Lists.  1.3.3's member list `All` is an open list whose tail `AllT` is a
variable, so a merge appends by binding the tail (`Lat = Lb`).  The port
keeps that shape: a ListCell chain whose last `rest` is an unbound Var
(open), or None (closed, `[]`).  The basis is a closed chain.  bv.pl builds
member lists too (`equate_components/3`), so the cell type is shared.
"""
from clausal.logic.clpq.variable_ordering import combine
from clausal.logic.variables import (
    PlainVar, Var, deref, get_attr, is_var, put_attr, register_attr_hook, unify)

COMPONENT_KEY = "clpq_holzbaur_component"


class ComponentRecord:
    """class.pl's `component_attributes(All, AllT, Basis, Priority)`."""
    __slots__ = ("members", "tail", "basis", "priority")

    def __init__(self, members, tail, basis, priority):
        self.members = members
        self.tail = tail
        self.basis = basis
        self.priority = priority


class ListCell:
    """A Prolog list cell `[head|rest]`.  `rest` is a ListCell, None (`[]`)
    or a variable (an open tail, which unification may bind to a list)."""
    __slots__ = ("head", "rest")

    def __init__(self, head, rest):
        self.head = head
        self.rest = rest


# ---------------------------------------------------------------- list helpers

def open_list(elements):
    """`[E1, ..., En|Tail]` with a fresh Tail: returns (list, Tail).  With no
    elements the list is Tail itself."""
    tail = Var()
    result = tail
    i = len(elements) - 1
    while i >= 0:
        result = ListCell(elements[i], result)
        i -= 1
    return result, tail


def closed_list(elements):
    """`[E1, ..., En]`; None for `[]`."""
    result = None
    i = len(elements) - 1
    while i >= 0:
        result = ListCell(elements[i], result)
        i -= 1
    return result


def list_elements(items):
    """The elements of an open or closed list, up to its tail."""
    result = []
    node = deref(items)
    while type(node) is ListCell:
        result.append(node.head)
        node = deref(node.rest)
    return result


def _identical_variable(element, variable):
    """`variable == element` as 1.3.3 sees it inside verify_attributes/3,
    before the binding: *element* reaches *variable* along its bindings.  A
    Clausal hook runs after the binding, so *variable* may be bound already
    and is not dereferenced
    (test_delete_first_matches_a_variable_through_its_bindings)."""
    while type(element) is Var or type(element) is PlainVar:
        if element is variable:
            return True
        if not element.is_bound:
            return False
        element = element.value
    return False


# ---------------------------------------------------------------- the hook

def verify_component(record, other, trail):
    """class.pl, verify_attributes/3: the hook for COMPONENT_KEY.  *record*
    is the bound component's (X's), *other* what it was bound to (Y).
    class.pl's Later is always [], so the hook returns True or False.

    A Y with no attributes at all takes X's record: SICStus binds a plain
    variable to an attributed one without calling the hook, and this engine
    binds by age instead (test_component_new_puts_the_record_on_a_plain_variable).
    """
    other = deref(other)
    if not is_var(other):                       # var(Y), required
        return False
    record_other = get_attr(other, COMPONENT_KEY)
    if record_other is None:
        if not other.attrs:
            put_attr(other, COMPONENT_KEY, record, trail)
            return True
        return False                            # get_atts(Y, ...) fails
    if not unify(record.tail, record_other.members, trail):    # Lat = Lb
        return False
    basis = _append(record.basis, record_other.basis)
    priority = combine(record.priority, record_other.priority)
    put_attr(other, COMPONENT_KEY,
             ComponentRecord(record.members, record_other.tail, basis,
                             priority), trail)
    return True


register_attr_hook(COMPONENT_KEY, verify_component)


def _append(list_a, list_b):
    """append/3 on a closed list *list_a*."""
    elements = list_elements(list_a)
    result = list_b
    i = len(elements) - 1
    while i >= 0:
        result = ListCell(elements[i], result)
        i -= 1
    return result


# ---------------------------------------------------------------- class.pl

def component_new(component, members, tail, basis, trail):
    """class.pl, component_new/4: `put_atts(Su, component_attributes(All,
    AllT, Basis, [])), Su = Class`.  Returns False where the unification
    fails."""
    hidden = Var()
    put_attr(hidden, COMPONENT_KEY,
             ComponentRecord(members, tail, basis, []), trail)
    return unify(hidden, component, trail)


def component_get_priority(component):
    """class.pl, component_get_priority/2.  None where get_atts fails."""
    record = get_attr(component, COMPONENT_KEY)
    if record is None:
        return None
    return record.priority


def component_put_priority(component, priority, trail):
    """class.pl, component_put_priority/2.  False where get_atts fails."""
    record = get_attr(component, COMPONENT_KEY)
    if record is None:
        return False
    put_attr(component, COMPONENT_KEY,
             ComponentRecord(record.members, record.tail, record.basis,
                             priority), trail)
    return True


def component_drop(component, variable, trail):
    """class.pl, component_drop/2."""
    record = get_attr(component, COMPONENT_KEY)
    if record is None:
        return False
    members = delete_first(record.members, variable)
    basis = delete_first(record.basis, variable)
    put_attr(component, COMPONENT_KEY,
             ComponentRecord(members, record.tail, basis, record.priority),
             trail)
    return True


def component_all_variables(component):
    """class.pl, component_all_variables/2: the open member list, or None
    where get_atts fails."""
    record = get_attr(component, COMPONENT_KEY)
    if record is None:
        return None
    return record.members


def component_basis(component):
    """class.pl, component_basis/2: the basis (None is `[]`).  Where get_atts
    fails it is None too; a caller that must tell the two apart reads the
    record."""
    record = get_attr(component, COMPONENT_KEY)
    if record is None:
        return None
    return record.basis


def component_basis_add(component, variable, trail):
    """class.pl, component_basis_add/3.  Returns NewBasis, or False where
    get_atts fails."""
    record = get_attr(component, COMPONENT_KEY)
    if record is None:
        return False
    new_basis = ListCell(variable, record.basis)
    put_attr(component, COMPONENT_KEY,
             ComponentRecord(record.members, record.tail, new_basis,
                             record.priority), trail)
    return new_basis


def component_basis_drop(component, variable, trail):
    """class.pl, component_basis_drop/2.  Always succeeds."""
    record = get_attr(component, COMPONENT_KEY)
    if record is not None:                                      # clause 1
        basis = delete_first(record.basis, variable)
        if basis is not record.basis:           # Basis0 \== Basis
            put_attr(component, COMPONENT_KEY,
                     ComponentRecord(record.members, record.tail, basis,
                                     record.priority), trail)
    return True                                                 # clause 2


def component_basis_pivot(component, enter, leave, trail):
    """class.pl, component_basis_pivot/3."""
    record = get_attr(component, COMPONENT_KEY)
    if record is None:
        return False
    basis = ListCell(enter, delete_first(record.basis, leave))
    put_attr(component, COMPONENT_KEY,
             ComponentRecord(record.members, record.tail, basis,
                             record.priority), trail)
    return True


def delete_first(items, variable):
    """class.pl, delete_first/3: *items* without the first element identical
    to *variable*, keeping an open tail.  Where nothing is deleted 1.3.3
    rebuilds an equal list; the port returns *items* itself, so `is not`
    answers component_basis_drop's `\\==`
    (test_delete_first_of_an_absent_element_gives_the_list_itself)."""
    prefix = []
    node = deref(items)
    while type(node) is ListCell:                               # clause 3
        if _identical_variable(node.head, variable):
            result = node.rest
            i = len(prefix) - 1
            while i >= 0:
                result = ListCell(prefix[i], result)
                i -= 1
            return result
        prefix.append(node.head)
        node = deref(node.rest)
    return items                                # clauses 1 and 2
