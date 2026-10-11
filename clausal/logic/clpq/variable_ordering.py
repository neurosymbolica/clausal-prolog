# Ported from clp(q,r) version 1.3.3, file ordering.pl
# (c) Copyright 1992,1993,1994,1995 Austrian Research Institute for
# Artificial Intelligence (OFAI).  Author: Christian Holzbaur.
# See clausal/logic/clpq/PROVENANCE.md.
"""Variable ordering: ordering.pl, the order comparison of itf3.pl's
nf_ordering/3 expansion, and the library(ugraphs) predicates ordering.pl
uses.

The order value.  A constrained variable's `variable_order` field holds what
1.3.3's `order/1` attribute holds: a fresh variable (bv.pl
`variable_intern`: `variable_order(_)`), which project.pl's `order/3` may
later bind to an integer.  `compare_order_values` is 1.3.3's `compare/3` on
two such values: an unbound value sorts before any integer, two unbound
values by creation (`Var._id`), two integers by value.  DEVIATIONS.md D4
records how creation order relates to SICStus's standard order of variables
(test_variable_order_follows_creation_and_is_an_identity,
test_order_values_bound_by_projection_sort_after_unbound_ones_by_number).

A graph is 1.3.3's ugraph: a list of `(vertex, neighbours)` pairs sorted by
vertex, each `neighbours` a sorted list without duplicates.  An edge is a
`(from, to)` pair.
"""
from clausal.logic.clpq.attributes import state_of
from clausal.logic.exceptions import LogicException, system_error
from clausal.logic.variables import deref, is_var, unify


# ---------------------------------------------------------------- the order

def compare_order_values(order_a, order_b):
    """itf3.pl, nf_ordering/3 expansion: compare(Rel, Oa, Ob) on two order
    values.  Returns -1, 0 or 1."""
    order_a = deref(order_a)
    order_b = deref(order_b)
    if is_var(order_a):
        if is_var(order_b):
            id_a = order_a._id
            id_b = order_b._id
            return (id_a > id_b) - (id_a < id_b)
        return -1
    if is_var(order_b):
        return 1
    return (order_a > order_b) - (order_a < order_b)


def compare_variable_order(variable_a, variable_b):
    """itf3.pl, nf_ordering/3 (store.pl's original, moved by SICStus into a
    goal expansion): get_atts(A, order(Oa)), get_atts(B, order(Ob)),
    compare(Rel, Oa, Ob).  Returns -1, 0 or 1, or None where a get_atts
    fails (a variable without an order)."""
    state_a = state_of(variable_a)
    state_b = state_of(variable_b)
    if state_a is None or state_b is None:
        return None
    order_a = state_a.variable_order
    order_b = state_b.variable_order
    if order_a is None or order_b is None:
        return None
    return compare_order_values(order_a, order_b)


# ---------------------------------------------------------------- standard order of vertices

def _vertex_key(term):
    """Standard order of a vertex: a variable by creation, before every
    non-variable.  Non-variables need no order among themselves, because
    normalize/2 drops them (test_normalize_after_bindings_and_aliasing)."""
    term = deref(term)
    if is_var(term):
        return (0, term._id)
    return (1, 0)


def _edge_key(edge):
    return (_vertex_key(edge[0]), _vertex_key(edge[1]))


def _pair_key(pair):
    return _vertex_key(pair[0])


def _identical(term_a, term_b):
    """==/2 on two dereferenced vertices."""
    if term_a is term_b:
        return True
    if is_var(term_a) or is_var(term_b):
        return False
    return type(term_a) is type(term_b) and term_a == term_b


def _sort_vertices(terms):
    """sort/2 on vertices: dereferenced, ordered, duplicates removed."""
    keyed = []
    for term in terms:
        keyed.append(deref(term))
    keyed.sort(key=_vertex_key)
    result = []
    for term in keyed:
        if result and _identical(result[-1], term):
            continue
        result.append(term)
    return result


def _ord_union(set_a, set_b):
    """library(ordsets) ord_union/3 on two sorted vertex lists."""
    result = []
    i = 0
    j = 0
    while i < len(set_a) and j < len(set_b):
        key_a = _vertex_key(set_a[i])
        key_b = _vertex_key(set_b[j])
        if key_a < key_b:
            result.append(set_a[i])
            i += 1
        elif key_a > key_b:
            result.append(set_b[j])
            j += 1
        else:
            result.append(set_a[i])
            i += 1
            j += 1
    while i < len(set_a):
        result.append(set_a[i])
        i += 1
    while j < len(set_b):
        result.append(set_b[j])
        j += 1
    return result


# ---------------------------------------------------------------- library(ugraphs)

def add_vertices(graph, vertices):
    """SICStus library(ugraphs), add_vertices/3."""
    new_graph = []
    for vertex in _sort_vertices(vertices):
        new_graph.append((vertex, []))
    return graph_union(graph, new_graph)


def add_edges(graph, edges):
    """SICStus library(ugraphs), add_edges/3 (and its group_edges/3,4)."""
    dereferenced = []
    for edge in edges:
        dereferenced.append((deref(edge[0]), deref(edge[1])))
    dereferenced.sort(key=_edge_key)
    edge_set = []
    for edge in dereferenced:                       # sort/2 removes duplicates
        if edge_set and _identical(edge_set[-1][0], edge[0]) \
                and _identical(edge_set[-1][1], edge[1]):
            continue
        edge_set.append(edge)
    endpoints = []
    for edge in edge_set:
        endpoints.append(edge[0])
        endpoints.append(edge[1])
    new_graph = []
    k = 0
    for vertex in _sort_vertices(endpoints):        # group_edges/3
        neighbours = []
        while k < len(edge_set) and _identical(edge_set[k][0], vertex):
            neighbours.append(edge_set[k][1])
            k += 1
        new_graph.append((vertex, neighbours))
    return graph_union(graph, new_graph)


def graph_union(graph_a, graph_b):
    """SICStus library(ugraphs), graph_union/3,8."""
    if not graph_b:
        return graph_a
    result = []
    i = 0
    j = 0
    while i < len(graph_a) and j < len(graph_b):
        key_a = _vertex_key(graph_a[i][0])
        key_b = _vertex_key(graph_b[j][0])
        if key_a < key_b:
            result.append(graph_a[i])
            i += 1
        elif key_a > key_b:
            result.append(graph_b[j])
            j += 1
        else:
            result.append((graph_a[i][0], _ord_union(graph_a[i][1], graph_b[j][1])))
            i += 1
            j += 1
    while i < len(graph_a):
        result.append(graph_a[i])
        i += 1
    while j < len(graph_b):
        result.append(graph_b[j])
        j += 1
    return result


def top_sort(graph):
    """SICStus library(ugraphs), top_sort/2,4 (with fanin_counts,
    get_top_elements and dec_counts).  Vertices whose in-degree reaches zero
    go on a stack, so the most recently freed is taken first
    (test_top_sort_pops_newly_free_vertices_last_in_first_out).  Returns
    None where top_sort/2 fails: a cycle, or an edge to a non-vertex."""
    in_degree = {}
    for vertex, _ in graph:
        in_degree[_vertex_key(vertex)] = 0
    for _, neighbours in graph:
        for neighbour in neighbours:
            key = _vertex_key(neighbour)
            if key not in in_degree:
                return None
            in_degree[key] += 1
    by_key = {}
    for pair in graph:
        by_key[_vertex_key(pair[0])] = pair
    free = []                                       # get_top_elements/4
    remaining = 0
    for pair in graph:
        if in_degree[_vertex_key(pair[0])] == 0:
            free.append(pair)
        else:
            remaining += 1
    free.reverse()                                  # the stack's top is the end
    result = []
    while free:                                     # top_sort/4
        vertex, neighbours = free.pop()
        result.append(vertex)
        for neighbour in neighbours:                # dec_counts/7
            key = _vertex_key(neighbour)
            in_degree[key] -= 1
            if in_degree[key] == 0:
                remaining -= 1
                free.append(by_key[key])
    if remaining != 0:
        return None
    return result


# ---------------------------------------------------------------- ordering.pl

def ordering(term, trail):
    """ordering.pl, ordering/1.  A constraint is the cell ('<', A, B) or
    ('>', A, B), or a list.  Returns False where ordering/1 fails."""
    term = deref(term)
    if is_var(term):                                    # clause 1
        return False
    if type(term) is tuple and len(term) == 3 and term[0] == ">":
        term = ("<", term[2], term[1])                  # clause 2
    if type(term) is tuple and len(term) == 3 and term[0] == "<":
        component = join_component([term[1], term[2]], trail)     # clause 3
        priority = _component_priority(component)
        if priority is not None:
            graph = add_edges([], [(term[1], term[2])])
            _put_component_priority(component, combine(priority, graph), trail)
            return True
        return True                                     # clause 5
    if type(term) is list and term:                     # clause 4
        component = join_component(term, trail)
        priority = _component_priority(component)
        if priority is not None:
            if len(term) == 1:
                graph = add_vertices([], term)
            else:
                graph = add_edges([], generate_edges(term))
            _put_component_priority(component, combine(priority, graph), trail)
            return True
    return True                                         # clause 5


def _component_priority(component):
    """class.pl class_get_prio/2 (component_get_priority), or None where it
    fails.  A
    join_component that met no variable leaves Class a fresh variable, and
    get_atts on it fails."""
    if component is None:
        return None
    from clausal.logic.clpq.components import component_get_priority
    return component_get_priority(component)


def _put_component_priority(component, priority, trail):
    """class.pl class_put_prio/2 (component_put_priority)."""
    from clausal.logic.clpq.components import component_put_priority
    component_put_priority(component, priority, trail)


def arrangement(component):
    """ordering.pl, arrangement/2.  Returns the variables in priority order;
    raises system_error(unsatisfiable_ordering) where 1.3.3 calls illarg
    (DEVIATIONS.md D6, test_a_cyclic_ordering_raises_the_system_error)."""
    priority = _component_priority(component)
    if priority is not None:
        result = top_sort(normalize(priority))
        if result is not None:
            return result
    raise LogicException(system_error("unsatisfiable_ordering", "arrangement/2"))


def join_component(terms, trail):
    """ordering.pl, join_class/2.  Every variable in *terms* joins one
    component; returns it, or None when *terms* holds no variable (1.3.3
    leaves Class unbound).  Joining two components is the unification of
    their Class variables, which class.pl's hook merges."""
    component = None
    for term in terms:
        term = deref(term)
        if is_var(term):
            from clausal.logic.clpq.bounded_simplex import variable_intern
            own = variable_intern(term, trail)
            if component is None:
                component = own
            elif not unify(component, own, trail):
                return None
    return component


def combine(graph_a, graph_b):
    """ordering.pl, combine/3."""
    return graph_union(normalize(graph_a), normalize(graph_b))


def normalize(graph):
    """ordering.pl, normalize/2."""
    if not graph:
        return []
    pairs = []
    for vertex, neighbours in graph:
        pairs.append((deref(vertex), neighbours))
    pairs.sort(key=_pair_key)                           # keysort/2 is stable
    return normalize_vertices(group(pairs))


def normalize_vertices(pairs):
    """ordering.pl, normalize_vertices/2."""
    result = []
    for vertex, neighbours in pairs:
        normal = normalize_vertex(vertex, neighbours)
        if normal is not None:
            result.append(normal)
    return result


def normalize_vertex(vertex, neighbours):
    """ordering.pl, normalize_vertex/3.  None where it fails (a bound
    vertex)."""
    vertex = deref(vertex)
    if not is_var(vertex):
        return None
    return (vertex, strip_nonvariable(_sort_vertices(neighbours), vertex))


def strip_nonvariable(neighbours, vertex):
    """ordering.pl, strip_nonvar/3: drop *vertex* itself, and everything from
    the first non-variable on (variables sort first)."""
    result = []
    for neighbour in neighbours:
        neighbour = deref(neighbour)
        if neighbour is vertex:
            continue
        if not is_var(neighbour):
            break
        result.append(neighbour)
    return result


def generate_edges(terms):
    """ordering.pl, gen_edges//1 and gen_edges//2: an edge from each element
    to every later one."""
    edges = []
    for i in range(len(terms)):
        for j in range(i + 1, len(terms)):
            edges.append((terms[i], terms[j]))
    return edges


def group(pairs):
    """ordering.pl, group/2,4: join the neighbour lists of consecutive pairs
    whose vertices are identical."""
    result = []
    for vertex, neighbours in pairs:
        if result and _identical(result[-1][0], vertex):
            result[-1] = (result[-1][0], result[-1][1] + neighbours)
        else:
            result.append((vertex, neighbours))
    return result
