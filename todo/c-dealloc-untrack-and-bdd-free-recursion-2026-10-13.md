# C deallocs: FD and constraint types never untrack; BDDNode free recurses (2026-10-12)

Found by the GC-segfault fix review (heap-type audit).

1. **Missing untrack.** `FDVar_dealloc` and `ConstraintBase_dealloc` (`_clpfd_propagate.c:196, 265`)
   and the four constraint deallocs (`:321, 388, 427, 471`) belong to GC types but never call
   `PyObject_GC_UnTrack` before they clear their fields. It is the same class as the 2026-09-11
   Trail_dealloc fix. The risk is low today, since there are no finalizers or weakrefs on these
   types. Fix: call `PyObject_GC_UnTrack(self)` first in each.
2. **BDDNode free recursion.** `BDDNode_dealloc` (`_clpb_core.c:107`) recurses on high/low without a
   bound. The type is not a GC type, so the trashcan cannot apply. The depth is bounded by the BDD
   variable count. Switch to an explicit-stack free only if BDDs with tens of thousands of
   variables become real.
