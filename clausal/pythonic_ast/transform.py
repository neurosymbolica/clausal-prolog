
def _transform_node_list(nodes: list, transform) -> list:
    """Transform a list of nodes; returns the original list if nothing changed.
    Node items that are REMOVED are removed from the output list.
    If transform returns a list, its contents are spliced in (one-to-many).
    """
    # Local import to avoid the nodes <-> transform module cycle.
    from .nodes import REMOVED
    result = []
    changed = False
    node_iter = iter(nodes)
    for node in node_iter:
        transformed_node = transform(node)
        if transformed_node is REMOVED:
            # A10-F016: honour the documented REMOVED sentinel — drop the node
            # instead of appending the sentinel object into the output.
            changed = True
            break
        elif isinstance(transformed_node, list):
            result.extend(transformed_node)
            changed = True
            break
        elif transformed_node is not node:
            result.append(transformed_node)
            changed = True
            break
        else:
            result.append(node)
    for node in node_iter:
        transformed_node = transform(node)
        if transformed_node is REMOVED:
            continue
        elif isinstance(transformed_node, list):
            result.extend(transformed_node)
        else:
            result.append(transformed_node)
    return result if changed else nodes

