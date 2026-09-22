# `--w4lib.pred(X)` in a `.clausal` host with `-import_module` dies in `seam.dotted()`

Found 2026-09-22 by engine-lane, probing the W4 boundary. Main 05ebcd91.

    -module(host, [])
    -import_module(w4lib)          # w4lib declares pred/1
    def build():
        return --w4lib.pred(X)

    AttributeError: 'LoadAttr' object has no attribute 'value'
      seam.py:216 seam_term -> :103 build -> :65 dotted

`dotted()` walks a `LoadAttr` expecting `.value`; the node it gets has a
different attribute name for its base. The 2026-09-21 dotted-runtime-module
landing covered the harness's form (a Python-bound module object read
through a rewriter thunk); this is the same shape written in a `.clausal`
host with the module bound by a directive, and it never worked. Nobody hits
it today because the downstream harness dropped the `--` form, but the W4
ruling ("`--` should work anywhere") makes it load-bearing. Fix is small
(read the node's actual base attribute); TDD it with this exact fixture.
