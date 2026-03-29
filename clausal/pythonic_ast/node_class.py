from dataclasses import dataclass, fields
from .transform import _transform_node_list

_unspecified = object()

# Primitive scalar type names — anything else in an annotation is a Node subclass.
_PRIMITIVE_NAMES = frozenset({'str', 'int', 'float', 'bool', 'bytes', 'complex'})


def _field_kind(f):
    """Classify a dataclass field as 'node', 'optional_node', 'node_list', or 'plain'.

    With ``from __future__ import annotations`` (PEP 563), every annotation is
    stored as a plain string, so we parse it directly instead of trying to use
    it as a live type object (which was the original bug).

    Rules:
      Optional[X] where X is a non-primitive  → 'optional_node'
      list[X]     where X is a non-primitive  → 'node_list'
      list[X]     where X is a primitive       → 'plain'
      any primitive scalar                     → 'plain'
      anything else (Node, Params, ForClause…) → 'node'
    """
    s = f.type if isinstance(f.type, str) else repr(f.type)
    s = s.strip()

    optional = False
    if s.startswith('Optional[') and s.endswith(']'):
        s = s[9:-1].strip()
        optional = True

    if s.startswith('list[') and s.endswith(']'):
        elem = s[5:-1].strip()
        return 'plain' if elem in _PRIMITIVE_NAMES else 'node_list'

    if s in _PRIMITIVE_NAMES:
        return 'plain'

    return 'optional_node' if optional else 'node'


# ── The decorator ─────────────────────────────────────────────────────────────

def node_class(NodeClass):
    """
    Decorator that applies @dataclass and generates three methods via closures:

    visit_children(self, visit)
      — calls visit() on every Node / list[Node] field
    transform_children(self, transform)
      — returns self.transform_fields(...) with
        transformed Node / list[Node] fields
    __call__(self, *, <fields>=…)
      — returns a copy with selectively replaced fields
    """
    NodeClass = dataclass(NodeClass)

    all_fields = fields(NodeClass)
    user_fields = [f for f in all_fields if f.name != "position"]

    if not user_fields:
        return NodeClass

    classified = [(f, _field_kind(f)) for f in user_fields]

    # ── visit_children(self, visit) -> None ───────────────────────────────

    _visit_spec = [(f.name, kind) for f, kind in classified
                   if kind in ("node", "optional_node", "node_list")]

    if _visit_spec:
        def visit_children(self, visit, _spec=_visit_spec):
            for name, kind in _spec:
                val = getattr(self, name)
                if kind == "node":
                    visit(val)
                elif kind == "optional_node":
                    if val is not None:
                        visit(val)
                else:  # node_list
                    for elem in val:
                        visit(elem)
        NodeClass.visit_children = visit_children
    # else: inherits Node.visit_children (no-op)

    # ── transform_children(self, transform) ───────────────────────────────

    _transform_spec = [(f.name, kind) for f, kind in classified
                       if kind in ("node", "optional_node", "node_list")]

    if _transform_spec:
        def transform_children(self, transform, _spec=_transform_spec,
                               _tl=_transform_node_list):
            kwargs = {}
            for name, kind in _spec:
                val = getattr(self, name)
                if kind == "node":
                    kwargs[name] = transform(val)
                elif kind == "optional_node":
                    kwargs[name] = transform(val) if val is not None else None
                else:  # node_list
                    kwargs[name] = _tl(val, transform)
            return self.transform_fields(**kwargs)
        NodeClass.transform_children = transform_children
    # else: inherits Node.transform_children (returns self)

    # ── __call__(self, *, <user_fields>=_unspecified) ─────────────────────

    _call_fields = tuple(f.name for f in user_fields)

    def __call__(self, _fields=_call_fields, _unspec=_unspecified, **kwargs):
        kw = {"position": self.position}
        for name in _fields:
            val = kwargs.pop(name, _unspec)
            kw[name] = getattr(self, name) if val is _unspec else val
        if kwargs:
            raise TypeError(f"Unexpected keyword arguments: {set(kwargs)}")
        return self.__class__(**kw)
    NodeClass.__call__ = __call__

    return NodeClass
