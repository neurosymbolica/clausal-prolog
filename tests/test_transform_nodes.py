import pytest
from clausal.transform_nodes import _transform_node_list


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def identity(node):
    return node


def remove_all(node):
    return []


def wrap(node):
    return ("wrapped", node)


# ---------------------------------------------------------------------------
# empty / trivial inputs
# ---------------------------------------------------------------------------

def test_empty_list_returns_empty_list():
    result = _transform_node_list([], identity)
    assert result == []


def test_single_node_unchanged():
    node = object()
    result = _transform_node_list([node], identity)
    assert result == [node]


def test_single_node_removed():
    result = _transform_node_list([object()], remove_all)
    assert result == []


def test_single_node_transformed():
    node = "a"
    result = _transform_node_list([node], wrap)
    assert result == [("wrapped", "a")]


# ---------------------------------------------------------------------------
# nothing changes
# ---------------------------------------------------------------------------

def test_all_unchanged_returns_list_equal_to_original():
    nodes = [1, 2, 3]
    result = _transform_node_list(nodes, identity)
    assert result == nodes


def test_all_unchanged_returns_same_object_as_input():
    # When nothing changes the function must return the exact same list object,
    # not a copy — callers use identity comparison to detect no-ops.
    nodes = [1, 2, 3]
    result = _transform_node_list(nodes, identity)
    assert result is nodes


# ---------------------------------------------------------------------------
# removal
# ---------------------------------------------------------------------------

def test_first_node_removed():
    nodes = ["a", "b", "c"]
    result = _transform_node_list(nodes, lambda n: [] if n == "a" else n)
    assert result == ["b", "c"]


def test_middle_node_removed():
    nodes = ["a", "b", "c"]
    result = _transform_node_list(nodes, lambda n: [] if n == "b" else n)
    assert result == ["a", "c"]


def test_last_node_removed():
    nodes = ["a", "b", "c"]
    result = _transform_node_list(nodes, lambda n: [] if n == "c" else n)
    assert result == ["a", "b"]


def test_all_nodes_removed():
    nodes = ["a", "b", "c"]
    result = _transform_node_list(nodes, remove_all)
    assert result == []


def test_multiple_adjacent_nodes_removed():
    nodes = ["a", "b", "c", "d"]
    remove_set = {"b", "c"}
    result = _transform_node_list(nodes, lambda n: [] if n in remove_set else n)
    assert result == ["a", "d"]


def test_multiple_non_adjacent_nodes_removed():
    nodes = ["a", "b", "c", "d", "e"]
    remove_set = {"a", "c", "e"}
    result = _transform_node_list(nodes, lambda n: [] if n in remove_set else n)
    assert result == ["b", "d"]


# ---------------------------------------------------------------------------
# transformation (replacement)
# ---------------------------------------------------------------------------

def test_first_node_transformed():
    nodes = ["a", "b", "c"]
    result = _transform_node_list(nodes, lambda n: n.upper() if n == "a" else n)
    assert result == ["A", "b", "c"]


def test_middle_node_transformed():
    nodes = ["a", "b", "c"]
    result = _transform_node_list(nodes, lambda n: n.upper() if n == "b" else n)
    assert result == ["a", "B", "c"]


def test_last_node_transformed():
    nodes = ["a", "b", "c"]
    result = _transform_node_list(nodes, lambda n: n.upper() if n == "c" else n)
    assert result == ["a", "b", "C"]


def test_all_nodes_transformed():
    nodes = ["a", "b", "c"]
    result = _transform_node_list(nodes, str.upper)
    assert result == ["A", "B", "C"]


def test_transformation_uses_identity_comparison_not_equality():
    # Two distinct objects that compare equal must be treated as a
    # transformation because `transformed_node is not node` is True.
    class EqualToAnything:
        def __eq__(self, other):
            return True

    original = EqualToAnything()
    replacement = EqualToAnything()
    assert original == replacement  # sanity check
    assert original is not replacement

    result = _transform_node_list([original], lambda n: replacement)
    assert result[0] is replacement


# ---------------------------------------------------------------------------
# mixed removal and transformation
# ---------------------------------------------------------------------------

def test_remove_and_transform_different_nodes():
    nodes = ["a", "b", "c", "d"]

    def transform(n):
        if n == "b":
            return []
        if n == "c":
            return n.upper()
        return n

    result = _transform_node_list(nodes, transform)
    assert result == ["a", "C", "d"]


def test_transform_first_then_remove_later():
    nodes = ["a", "b", "c"]

    def transform(n):
        if n == "a":
            return n.upper()
        if n == "c":
            return []
        return n

    result = _transform_node_list(nodes, transform)
    assert result == ["A", "b"]


def test_remove_first_then_transform_later():
    nodes = ["a", "b", "c"]

    def transform(n):
        if n == "a":
            return []
        if n == "b":
            return n.upper()
        return n

    result = _transform_node_list(nodes, transform)
    assert result == ["B", "c"]


# ---------------------------------------------------------------------------
# return type
# ---------------------------------------------------------------------------

def test_always_returns_a_list():
    assert isinstance(_transform_node_list([], identity), list)
    assert isinstance(_transform_node_list([1], identity), list)
    assert isinstance(_transform_node_list([1], remove_all), list)
    assert isinstance(_transform_node_list([1], wrap), list)


def test_unchanged_result_is_same_object_so_mutations_are_shared():
    # When nothing changes the returned list IS the input list, so mutations
    # to one are visible through the other (a consequence of the identity
    # return, not a bug to defend against here).
    nodes = ["a", "b", "c"]
    result = _transform_node_list(nodes, identity)
    nodes.append("d")
    assert result is nodes
    assert "d" in result


# ---------------------------------------------------------------------------
# list expansion (one-to-many)
# ---------------------------------------------------------------------------

def test_first_node_expanded_to_multiple():
    nodes = ["a", "b", "c"]
    result = _transform_node_list(nodes, lambda n: ["X", "Y"] if n == "a" else n)
    assert result == ["X", "Y", "b", "c"]


def test_middle_node_expanded_to_multiple():
    nodes = ["a", "b", "c"]
    result = _transform_node_list(nodes, lambda n: ["X", "Y"] if n == "b" else n)
    assert result == ["a", "X", "Y", "c"]


def test_last_node_expanded_to_multiple():
    nodes = ["a", "b", "c"]
    result = _transform_node_list(nodes, lambda n: ["X", "Y"] if n == "c" else n)
    assert result == ["a", "b", "X", "Y"]


def test_node_expanded_to_empty_list_acts_like_removal():
    nodes = ["a", "b", "c"]
    result = _transform_node_list(nodes, lambda n: [] if n == "b" else n)
    assert result == ["a", "c"]


def test_node_expanded_to_single_item_list():
    nodes = ["a", "b", "c"]
    result = _transform_node_list(nodes, lambda n: ["Z"] if n == "b" else n)
    assert result == ["a", "Z", "c"]


def test_all_nodes_expanded():
    nodes = ["a", "b"]
    result = _transform_node_list(nodes, lambda n: [n, n.upper()])
    assert result == ["a", "A", "b", "B"]


def test_multiple_nodes_expanded():
    nodes = ["a", "b", "c"]
    expand = {"a", "c"}
    result = _transform_node_list(nodes, lambda n: [n, n.upper()] if n in expand else n)
    assert result == ["a", "A", "b", "c", "C"]


def test_expansion_and_removal_mixed():
    nodes = ["a", "b", "c", "d"]

    def transform(n):
        if n == "b":
            return ["X", "Y"]
        if n == "c":
            return []
        return n

    result = _transform_node_list(nodes, transform)
    assert result == ["a", "X", "Y", "d"]


def test_expansion_and_single_replacement_mixed():
    nodes = ["a", "b", "c"]

    def transform(n):
        if n == "a":
            return n.upper()
        if n == "b":
            return ["X", "Y"]
        return n

    result = _transform_node_list(nodes, transform)
    assert result == ["A", "X", "Y", "c"]


def test_expansion_triggers_changed_flag():
    # Returning a list (even [node]) must be treated as changed, so the
    # original list object must NOT be returned.
    nodes = ["a"]
    result = _transform_node_list(nodes, lambda n: [n])
    assert result is not nodes
    assert result == ["a"]


# ---------------------------------------------------------------------------
# transform is called exactly once per node
# ---------------------------------------------------------------------------

def test_transform_called_once_per_node():
    calls = []

    def counting_transform(node):
        calls.append(node)
        return node

    nodes = ["x", "y", "z"]
    _transform_node_list(nodes, counting_transform)
    assert calls == nodes


def test_transform_called_once_per_node_when_first_removed():
    calls = []

    def counting_transform(node):
        calls.append(node)
        return [] if node == "x" else node

    nodes = ["x", "y", "z"]
    _transform_node_list(nodes, counting_transform)
    assert calls == nodes


def test_transform_called_once_per_node_when_first_transformed():
    calls = []

    def counting_transform(node):
        calls.append(node)
        return node.upper() if node == "x" else node

    nodes = ["x", "y", "z"]
    _transform_node_list(nodes, counting_transform)
    assert calls == nodes
