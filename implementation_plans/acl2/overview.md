# Lisp and ACL2 on Clausal terms — investigation and plan (2026-10-06)

Question (operator, 2026-10-06): Clausal's terms are functor-first tuples,
`('f', a, b)` -- essentially S-expressions. Can a Lisp run on them, sanely
callable from Clausal, Python or the seam? Could it run (interpret) ACL2? Does
talking to a real ACL2 have to be another process?

## 1. A Lisp on Clausal terms: yes

**Representation.** Inside an interpreter the tuples can be used freely --
`(f)` as `('f',)`, `(1 2)` as `(1, 2)` -- since Clausal's reservations (the
1-tuple, a non-`str` head) only matter at the boundary. At the boundary, a
canonical mapping gives every Lisp object exactly one term, so Lisp `equal` is
Clausal unification:

| Lisp | Clausal term |
|---|---|
| symbol (incl. `nil`, `t`) | atom |
| integer, rational, string | `int`, `Fraction`, `('$chars', s)` |
| `(f a ...)`, symbol head, 2+ items | the cell `('f', a, ...)` -- a Prolog compound |
| other proper list | `('()', ...)` -- the engine's tuple-data cell (`cells.TUPLE_TAG`) |
| `(a . b)` | `('$cons', a, b)` (Clausal lists are never improper: `terms.py`) |

**Prototype** (`sexpr_lisp_prototype.py`, ~300 lines): reader, printer and an
evaluator for the applicative core (quote, if, let/let*, lambda, defun,
cond/and/or, conses, rationals). Verified: `app`, `rev`, `fact`, lambda
application, rationals, dotted pairs. A `.clausal` fact
`defun(app, x(y), if(endp(x), y, cons(car(x), app(cdr(x), y))))` is the same
term the Lisp reader builds from `(defun app (x y) ...)`, and a cut-free
Clausal Prolog simplifier rewrote
`(if (equal x x) (+ (car (cons a b)) 0) (car (cons a b)))` to `a` by
unification, its output then evaluated by the Lisp.

**Costs (measured).** Flat tuples are forms, not conses: `cdr` copies, so list
recursion is quadratic (1,000 elements 16 ms, 4,000 0.5 s). The tree-walking
evaluator is ~200x slower than Python (`fib 20`: 0.15 s); compiling defuns to
Python, as Clausal compiles clauses, would recover most of that.

## 2. Interpreting ACL2: possible, large, speed-bound

Survey of the 44 files in `*acl2-files*` plus `acl2.lisp`, `acl2-fns.lisp`,
`acl2-init.lisp` (excluding the 174k-line `doc.lisp`), with a tolerant CL
reader (`acl2_survey.py`, output in `acl2_survey_output.txt`):

- **ACL2's own language**: ~270k lines, ~8,300 top-level forms (5,763
  `defun`, 1,247 `defmacro`, 387 `defconst`, 260 `defthm`). Almost
  self-contained: beyond what the sources define it needs CL special forms
  (`let`, `flet`, `setq`, `return-from`) and a handful of primitives. An
  interpreter needs `defmacro`, backquote, `mv`, `state`, and ACL2's ~30
  primitives; everything else is defined in ACL2.
- **Raw Common Lisp**: ~36k lines, ~1,300 top-level forms (`*-raw` files,
  `acl2-fns`, `acl2-init`, 244 `#-acl2-loop-only` blocks), using ~440 CL
  operators the sources do not define: hash tables, `loop` (188 uses),
  `format` (227), `setf`/`push`/`incf`, packages, plists, arrays, streams and
  files, `defstruct`, `eval`/`compile`, `catch`/`throw`, readtables, plus
  hons/memoize/serialize internals. This is ACL2's host interface (how
  defuns and `*1*` functions are installed, the world's property-list cache,
  `ld`, I/O) -- to be reimplemented in Python rather than interpreted, and
  ACL2's soundness rests on it.
- **Speed**: interpretation is ~200x Python and Python is (estimated, not
  measured here) 30-100x SBCL on symbolic code: a pure interpreter makes the
  few-minute boot days and a small proof minutes. Compiling defuns to Python
  brings it to roughly 50x SBCL: a one-time few-hour boot (then snapshot the
  world), seconds per small proof.

Phases if pursued: (1) evaluator for ACL2's language running `axioms.lisp`'s
functions; (2) compile defuns to Python; (3) the raw layer in Python (world
and its cache, packages, `ld`/IO; hons and memoize stubbed); (4) boot the 44
files, snapshot, run `thm`. (1)-(2) weeks; (3)-(4) a research project. The
real ACL2 (below) is the trusted reference to test it against.

## 3. The real ACL2: `clausal-acl2` (implemented, phase 1)

**Process backend** (`packages/clausal-acl2`). The ACL2 Bridge
(`books/centaur/bridge`, Jared Davis): a socket server evaluating Lisp forms.
Protocol (from `bridge-raw.lsp`): the server sends `ACL2_BRIDGE_HELLO`, then
`READY` before each command; commands and replies are `TYPE LEN\nCONTENT\n`
with LEN in characters; a `LISP` command answers `STDOUT` messages, then
`RETURN` (`prin1` of the first value) or `ERROR`; `LISP_MV` returns the value
list. The JSON modes are lossy (symbols, strings and chars all become
strings), so the client parses `prin1` output with its own reader.

Events (`event/1`, `thm/1`) go through `ld` with `:ld-error-action :return!`
inside `bridge::in-main-thread`: the bridge evaluates commands in worker
threads, while memoization and hons -- which proofs use -- belong to the main
thread, which `bridge::start` leaves serving `in-main-thread` work. Success
is `ld`'s ERP being NIL.

**In-process** (not implemented). SBCL builds as a shared library
(`make-shared-library.sh` in SBCL's tree, `libsbcl.so`); quil-lang's
`sbcl-librarian` exposes Lisp functions to C and Python from it (SBCL >
2.1.10). An ACL2 saved core from the same SBCL could boot inside the Python
process and be called through `ctypes`, as `clausal-trealla` calls `libtpl`.
Costs: SBCL's signal handlers (and on some platforms its stop-the-world
signal), a fixed address range under 4 GB on x86, one Lisp per process, ACL2
not thread-safe, and a crash or runaway proof takes Python down. A second
backend behind the same interface if the process round trip (tens of
microseconds, against proofs of milliseconds to seconds) ever matters.

## Issues

- **Not run against a real ACL2.** No ACL2 or SBCL in the development
  sandbox. The client is tested against a fake bridge that follows
  `bridge-raw.lsp` (hello, READY, character-counted messages, STDOUT/RETURN/
  ERROR), and the real-ACL2 fixtures' logic passes against it. To confirm on
  a machine with ACL2: the `ld` return convention for an accepted vs
  rejected event (`(NIL :EOF state)` vs a non-NIL ERP) and that
  `bridge::in-main-thread` passes `ld`'s values through; then
  `python -m pytest packages/clausal-acl2`.
- **Seam friction.** ACL2 names used as data need `-private([...])`
  declarations, and Python keywords (`if`, `and`, `or`, `not`) cannot be
  seam functors at all -- hence `acl2_text/2`. Clausal Prolog (`.clausal`)
  writes ACL2 terms natively (`if(endp(x), y, ...)`), but reaches Python
  only through a `python_bridges` seam module, since no extension package
  ships `library(...)` facades yet
  (`todo/package-adapters-need-library-facades-2026-10-01.md`).
- Symbol case: an ACL2 name in upper case maps to a lowercase atom; a name
  with lowercase letters maps to `'|name|'`. A Clausal atom with capitals
  crosses out as its exact name between bars (and comes back bar-wrapped).
