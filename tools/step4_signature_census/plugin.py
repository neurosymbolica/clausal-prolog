"""Step-4 signature census: does the new source (the rewriter's
``HeadFieldNames`` module item) agree with the old one (the class's
``_fields``) at every step-4 arrival where both exist?

A pre-flip instrument, not a permanent test: after the PredicateMeta flip
there is no class to compare with, and the census has nothing to count.

Wraps ``compiler_v2.record_clause_source`` for the session.  Step 4 calls it
once per clause arrival, with the row the clause landed on, immediately
BEFORE it stamps ``row.signature`` from the module item.  The wrapper
records the row's signature as it arrived (``pre``) and what the name was
bound to.  The record is settled (``post`` = what the stamp left on the row)
when that clause's step-4 install ENDS: ``compiler_v2._load_gate`` is also
wrapped, and its ``WRITE_LOAD_CLAUSES`` context -- the ``with`` block both the
``record_clause_source`` call and the stamp sit inside -- settles on exit.
Nothing else runs between the stamp and that exit, so no later mutation of
the row can be counted as a step-4 result.  A record still pending when a
gate exits by exception is dropped (the clause was not installed), and one
still pending at session end is a census defect and fails the session.

Population N: arrivals that STAMP (``pre is None``) and whose name is bound
to a ``PredicateMeta`` class -- the only arrivals where both sources exist.
Denominator: every step-4 arrival.  Printed together, always.

Exit status:
* N == 0 is a REFUSAL (exit 3): an instrument over an empty population
  proves nothing.
* A mismatch outside the ALLOWED set, or an allowed key whose new answer is
  not the module's own declaration, fails the session (exit 3).
* A class arrival the stamp left with NO signature fails the session too:
  that is the regression this census exists to catch.

Run from the repo root:

    ./venv/bin/python -m pytest <targeted files> -q -p no:cacheprovider \\
        -p tools.step4_signature_census.plugin
"""
import collections

_STATS = collections.Counter()
_MISMATCH = []          # (module, key, post, cls_fields, declared, allowed)
_UNSTAMPED = []         # class arrivals left with no signature
_PENDING = []
_CONFIGURED = False

# Declare-then-import-then-define (design §3): the class bound under the
# name is the EXPORTER's, carrying unseated ``-dynamic``/``f/N`` placeholder
# names, while this module declares ``f(STATUS, CITATIONS)``.  The new source
# answers the declaration; that is the ruled correction.
ALLOWED = {("fnm_verdict", 2), ("impord_fverdict", 2)}


def _settle():
    while _PENDING:
        row, module_name, key, pre, cls_fields = _PENDING.pop()
        post = row.signature
        if pre is not None:
            _STATS["later"] += 1
            _STATS["later_unchanged" if post == pre else "later_CHANGED"] += 1
            continue
        if cls_fields is None:
            _STATS["stamp_noclass"] += 1
            _STATS["stamp_noclass_" + ("stamped" if post is not None
                                       else "unstamped")] += 1
            continue
        _STATS["N"] += 1
        if post is None:
            _UNSTAMPED.append((module_name, key))
            continue
        if tuple(post) == tuple(cls_fields):
            _STATS["agree"] += 1
            continue
        declared = row._db.declared_fields(*key)
        allowed = key in ALLOWED and declared is not None and \
            tuple(post) == tuple(declared)
        _STATS["mismatch_allowed" if allowed else "mismatch_UNEXPECTED"] += 1
        _MISMATCH.append((module_name, key, post, cls_fields, declared,
                          allowed))


def pytest_configure(config):
    global _CONFIGURED
    if _CONFIGURED:
        raise RuntimeError(
            "tools.step4_signature_census.plugin loaded twice in one "
            "process -- refusing to double-wrap record_clause_source.")
    import clausal.logic.compiler_v2 as cv2
    from clausal.logic.predicate import PredicateMeta

    import contextlib

    original = cv2.record_clause_source
    original_gate = cv2._load_gate

    @contextlib.contextmanager
    def settling_gate(db, functor, arity, author, kind, *args, **kwargs):
        with original_gate(db, functor, arity, author, kind,
                           *args, **kwargs) as value:
            if kind != cv2.WRITE_LOAD_CLAUSES:
                yield value
                return
            _STATS["gates"] += 1
            try:
                yield value
            except BaseException:
                _STATS["dropped"] += len(_PENDING)
                _PENDING.clear()
                raise
            _settle()

    def counting(row, module_name, module_dict):
        if _PENDING:
            # An arrival with the previous one unsettled means the gate
            # wrapper missed an exit: count it, never silently settle late.
            _STATS["LATE"] += len(_PENDING)
            _PENDING.clear()
        _STATS["arrivals"] += 1
        functor, arity = row.key
        binding = module_dict.get(functor)
        cls_fields = (tuple(binding._fields)
                      if isinstance(binding, PredicateMeta) else None)
        _PENDING.append((row, module_name, (functor, arity), row.signature,
                         cls_fields))
        return original(row, module_name, module_dict)

    cv2.record_clause_source = counting
    cv2._load_gate = settling_gate
    config._s4sig_restore = (cv2, original, original_gate)
    _CONFIGURED = True


def pytest_unconfigure(config):
    global _CONFIGURED
    restore = getattr(config, "_s4sig_restore", None)
    if restore is not None:
        cv2, original, original_gate = restore
        cv2.record_clause_source = original
        cv2._load_gate = original_gate
    _CONFIGURED = False


def _verdict():
    if _PENDING:
        _STATS["LATE"] += len(_PENDING)
        _PENDING.clear()
    if _STATS["N"] == 0:
        return "REFUSED"
    if _STATS["mismatch_UNEXPECTED"] or _UNSTAMPED or _STATS["LATE"]:
        return "FAILED"
    return "OK"


def pytest_sessionfinish(session, exitstatus):
    if _verdict() != "OK" and session.exitstatus == 0:
        session.exitstatus = 3


def pytest_terminal_summary(terminalreporter):
    w = terminalreporter.write_line
    verdict = _verdict()
    total = _STATS["arrivals"]
    n = _STATS["N"]
    w("")
    w("=" * 68)
    w("STEP-4 SIGNATURE CENSUS (HeadFieldNames vs pred_cls._fields)")
    w("=" * 68)
    w(f"step-4 arrivals (denominator)                 {total}")
    if n == 0:
        w("REFUSAL: N == 0 -- no stamping arrival had a class to compare")
        w("with.  This is not a pass: the plugin did not load, or nothing")
        w("under test loaded a module with clauses.")
        return
    w(f"N: stamping arrivals bound to a class         {n}  "
      f"({100.0 * n / total:.1f}% of {total})")
    w(f"  new source == pred_cls._fields              {_STATS['agree']} / {n}")
    w(f"  mismatch, ALLOWED (== own declaration)      "
      f"{_STATS['mismatch_allowed']} / {n}")
    w(f"  mismatch, UNEXPECTED                        "
      f"{_STATS['mismatch_UNEXPECTED']} / {n}")
    w(f"  class arrival left UNSTAMPED                {len(_UNSTAMPED)} / {n}")
    ns = _STATS["stamp_noclass"]
    w(f"stamping arrivals NOT bound to a class        {ns}  "
      f"(stamped {_STATS['stamp_noclass_stamped']} / {ns})")
    w(f"clause-install gates settled                  {_STATS['gates']}  "
      f"(records dropped on a raising gate {_STATS['dropped']}; "
      f"settled LATE {_STATS['LATE']} -- must be 0)")
    lt = _STATS["later"]
    w(f"later-clause arrivals (already stamped)       {lt}  "
      f"(unchanged {_STATS['later_unchanged']} / {lt})")
    if _MISMATCH:
        w("")
        w("mismatches (module, key, new, class, declared, allowed):")
        for rec in _MISMATCH:
            w(f"  {rec}")
    if _UNSTAMPED:
        w("")
        w("UNSTAMPED class arrivals:")
        for rec in sorted(set(_UNSTAMPED)):
            w(f"  {rec}")
    w(f"VERDICT: {verdict}")
