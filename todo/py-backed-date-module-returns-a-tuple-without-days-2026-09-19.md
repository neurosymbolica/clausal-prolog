# A py-backed date module answers a tuple where `.days` is read

Uncovered 2026-09-19 while clearing a STALE SPELLING that had been masking it.

## What happens

`tests/test_transitive_py_module_import.py` runs two py-backed date modules in
a subprocess and asserts `days_between(2026,1,1, 2026,4,1, N), N == 90`. It
now fails with:

    AttributeError: 'tuple' object has no attribute 'days'

A date subtraction is producing a TUPLE — the term representation — where the
Python side still reads `.days` off a `timedelta`. That is the term-shape
change meeting a py-backed module that was written against the object.

## Why nobody had seen it

Two layers of masking, and the second is the interesting one:

1. Both tests `skipif` on "no project venv interpreter with an installed
   clausal distribution found". A WORKTREE has no `venv/`, so they SKIP there
   and only RUN in the checkout — which is why a worktree suite reads two
   fewer failures than the checkout at the same sha, and why a worktree
   baseline UNDER-COUNTS by two. A skip is not a pass; `-rs` shows it.
2. In the checkout they did run, and failed on a retired `Test(` spelling in
   their own inline `.seam` source (TitleCase has been a load error since
   2026-09-10). That refusal happened at LOAD, before the date code ran, so
   the real defect never surfaced. Fixing the one-word spelling is what
   exposed it.

## What to do

Find where the subtraction result is built and either return the `timedelta`
or teach the reader the tuple shape. The two tests are the reproduction; run
them from the CHECKOUT (a worktree skips them), or point the skipif at a venv.

**Do not re-mask it.** The failure count does not improve by reverting the
spelling fix — it just goes back to failing for a reason that is not the
problem.
