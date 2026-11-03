"""The CLP(FD) and CLP(B) C types must free themselves safely.

Two defects, both in C ``tp_dealloc`` functions
(todo/done/c-dealloc-untrack-and-bdd-free-recursion-2026-10-13.md):

- **Untrack first.**  FDVar and the constraint types (the ``Constraint`` base
  and its Eq/Ne/Lt/Le, AllDiff, Sum and ScalarProduct subtypes) are GC types.  Their
  deallocs dropped their fields while the dying object (refcount 0) was
  still on the collector's lists.  Any code that runs during that drop -- a
  ``__del__`` on a field -- could then reach the corpse: ``gc.get_objects()``
  returned it (resurrecting a freed object) and ``gc.collect()`` traversed
  it.  CPython's rule: ``PyObject_GC_UnTrack(self)`` before anything else.

- **Deep chains.**  A dealloc that drops a reference to an object of its own
  type recurses once per link.  The FD/constraint types take the trashcan
  (``Py_TRASHCAN_BEGIN``); BDDNode is not a GC type, so it cannot, and frees
  deep node chains through an explicit pending stack instead.

Each case runs in a subprocess (helpers from test_dealloc_long_chains), so a
segfault fails one test rather than killing the run.  The chain cases cap
the child's C stack so a modest chain overflows it without the fix.
"""

import textwrap
from pathlib import Path

import pytest

from tests.test_dealloc_long_chains import _CAPPED_STACK, _ROOT, _run

_PRELUDE = (
    "import clausal.logic.clpfd\n"
    "import clausal.logic._clpfd_propagate as _p, clausal.logic._clpb_core as _b\n"
    "print('CEXT', _p.__file__)\n"
    "print('CEXT', _b.__file__)\n"
)


def _go(code, **kwargs):
    return _run(_PRELUDE + textwrap.dedent(code), **kwargs)


def _assert_clean(proc, marker):
    assert proc.returncode == 0, (
        f"exit {proc.returncode}\nstdout:\n{proc.stdout[-2000:]}\n"
        f"stderr:\n{proc.stderr[-2000:]}")
    assert marker in proc.stdout, proc.stdout[-2000:]
    exts = [line.split(" ", 1)[1] for line in proc.stdout.splitlines()
            if line.startswith("CEXT ")]
    assert len(exts) == 2, proc.stdout[-2000:]
    for path in exts:
        assert Path(path).resolve().is_relative_to(_ROOT), (
            f"child loaded {path}, not this tree's extension under {_ROOT}")


# Constructors: each builds one object whose fields include ``payload``.
_MAKERS = {
    "FDVar": "lambda x: _p.FDVar(x)",
    "FDVar.constraints": "lambda x: _p.FDVar(((0, 1),), x)",
    "EqConstraint": "lambda x: _p.EqConstraint(x, 1)",
    "NeConstraint": "lambda x: _p.NeConstraint(1, x)",
    "LtConstraint": "lambda x: _p.LtConstraint(x, 1)",
    "LeConstraint": "lambda x: _p.LeConstraint(x, 1)",
    "AllDiffConstraint": "lambda x: _p.AllDiffConstraint(x)",
    "SumConstraint": "lambda x: _p.SumConstraint((), x)",
    "ScalarProductConstraint": "lambda x: _p.ScalarProductConstraint(x, (), 1)",
}


@pytest.mark.parametrize("kind", list(_MAKERS))
@pytest.mark.parametrize("probe", ["get_objects", "collect"])
def test_dying_object_is_untracked_before_its_fields_drop(kind, probe):
    # The field's __del__ runs while the owner is being freed.  The owner
    # must already be off the collector's lists: get_objects() must not see
    # it, and a collection must not traverse it.
    proc = _go(f"""
        import gc
        make = {_MAKERS[kind]}
        seen = []
        class Probe:
            def __del__(self):
                if {probe!r} == 'get_objects':
                    seen.extend(o for o in gc.get_objects()
                                if id(o) == owner_id)
                else:
                    gc.collect()
        for _ in range(50):
            obj = make(Probe())
            owner_id = id(obj)
            del obj
            assert not seen, ('dying owner still tracked', len(seen))
        gc.collect()
        print("UNTRACKED")
    """)
    _assert_clean(proc, "UNTRACKED")


_CHAINS = {
    "FDVar": "lambda x: _p.FDVar(x)",
    "EqConstraint": "lambda x: _p.EqConstraint(x, 1)",
    "AllDiffConstraint": "lambda x: _p.AllDiffConstraint(x)",
    "SumConstraint": "lambda x: _p.SumConstraint((), x)",
    "ScalarProductConstraint": "lambda x: _p.ScalarProductConstraint(x, (), 1)",
}


@pytest.mark.parametrize("kind", list(_CHAINS))
@pytest.mark.parametrize("how", ["refcount", "collector"])
def test_fd_long_chain_frees(kind, how):
    # A 200k-link chain of one type, freed by ``del`` (refcount cascade) or
    # hung off a reference cycle so the collector's tp_clear starts it.
    proc = _go(f"""
        import gc
        gc.disable()
        make = {_CHAINS[kind]}
        head = 0
        for _ in range(200_000):
            head = make(head)
        if {how!r} == 'collector':
            cyc = []
            cyc.append(cyc)
            cyc.append(head)
            del cyc
        del head
        gc.collect()
        print("FREED")
    """, stack=_CAPPED_STACK)
    _assert_clean(proc, "FREED")


@pytest.mark.parametrize("shape", ["high", "low", "both"])
def test_bdd_deep_node_chain_frees(shape):
    # A BDD over 1M variables whose nodes form one chain; the last reference
    # dropped frees it all.  "both" shares each child between high and low.
    proc = _go(f"""
        import gc
        gc.disable()
        import sys
        from clausal.logic._clpb_core import BDDNode
        blocks = sys.getallocatedblocks()
        node = 1
        for v in reversed(range(1_000_000)):
            if {shape!r} == 'high':
                node = BDDNode(v, node, 0)
            elif {shape!r} == 'low':
                node = BDDNode(v, 0, node)
            else:
                node = BDDNode(v, node, node)
        del node, v
        # Every node went back to the allocator (none stranded on the
        # pending stack, which is itself released after a deep free).
        leaked = sys.getallocatedblocks() - blocks
        assert leaked < 100, leaked
        print("FREED")
    """, stack=_CAPPED_STACK)
    _assert_clean(proc, "FREED")


def test_bdd_free_with_reentrant_field():
    # A node's field may be any object (the Python constructor takes any);
    # its __del__ may build and drop another deep BDD while a deep free is
    # under way.  Everything must still be freed, exactly once.
    proc = _go("""
        import gc, sys
        from clausal.logic._clpb_core import BDDNode
        freed = []
        class Leaf:
            def __del__(self):
                n = 1
                for v in range(5000):
                    n = BDDNode(v, n, 0)
                del n
                freed.append(1)
        node = Leaf()
        for v in range(300_000):
            node = BDDNode(v, node, Leaf() if v % 1000 == 0 else 0)
        del node
        assert len(freed) == 301, len(freed)
        print("FREED")
    """, stack=_CAPPED_STACK)
    _assert_clean(proc, "FREED")
