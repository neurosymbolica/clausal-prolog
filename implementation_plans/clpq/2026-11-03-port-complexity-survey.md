# CLP(Q) port: complexity survey (2026-11-03)

Where does the Holzbaur port (`CLAUSAL_CLPQ=holzbaur`,
`clausal/logic/clpq/`) grow faster than clp(q,r) 1.3.3's own algorithm
needs?  This is a map for later implementation-only fixes. No solver code
was changed. Every fix proposed here has to give exactly the same answers,
residuals and variable order as now.

- Script: `benchmarks/clpq_port_scaling.py` (`--list` names the 28 cases).
  Each point runs in its own subprocess. The script counts the
  algorithm's units of work at each n, profiles the largest n with
  cProfile, and with `--scryer` runs the same shape on Scryer's copy of
  the 1.3.3 text (`tests/_oracles.SCRYER`).
- Run: `python benchmarks/clpq_port_scaling.py --jobs 12 --cap 60 --scryer --profile --json out.json`,
  base commit 785b9dc2, 32 cores, load 5 to 7. Times are the minimum of
  3 runs, or of 1 run past 5 s. The port's D24 resource caps were
  lifted (the default; `--caps` keeps them), so that the curves show
  1.3.3's algorithm. With the caps on, `dump_large` raises
  `resource_error(clpq_projection)` at n = 200.
- This base does **not** contain commit 7a573135 (branch r32-varvar),
  which made `bind_varvar` about 1.8 times faster. The `bind_varvar`
  numbers below are from before that fix.
- Scryer evaluates rationals through an interpreted `eval_q`, so only
  its exponents are compared, never its times. Its `time/1` inference
  count is the cleaner exponent. Scryer's copy is "1.3.3's algorithm" as
  far as this survey can tell. It is not SICStus.

## What the counters are

| Counter | Meaning |
|---|---|
| `rows_read` | calls of `linear_forms.normal_form_substitute`, i.e. rows the back substitution looks at (bv.pl `bs/3`) |
| `terms_scanned` | the terms of those rows, which `delete_factor_homogeneous` scans to find the variable |
| `rows_rewritten`, `terms_read` | the rows that held the variable, and their terms (the merge work) |
| `back_substitutions`, `pivots` | calls of `back_substitute_variables`, `pivot` and `pivot_ignoring_bounds` |
| `bb_nodes` | calls of `branch_and_bound_reoptimize` (one per node) |
| `fm_cross` | rows built by Fourier-Motzkin `crossproduct` |
| `python_calls` | cProfile's total, a proxy for interpreter work |

If time grows with the same exponent as the algorithm's units, and
Scryer's inferences grow with that exponent too, the cost is 1.3.3's
own. If time or `python_calls` grows faster than the units, the port
spends more per unit as n grows, and that is overhead.

## Results (measured)

"top" is the slope between the two largest sizes. The slope over all
sizes is in brackets.

| Operation (case) | n | seconds | port exponent | Scryer exponent (inferences) | work exponent (unit) | class |
|---|---|---|---|---|---|---|
| post chain `X1 =< ... =< Xn` (`chain_le`; `chain_lt` the same) | 100..1600 | .035 .15 .91 5.5 49.7 | 3.2 (2.6) | 2.91 | rows_read 2.0, **terms_scanned 3.0** | inherent, but removable by implementation (R1). **After R1b: n = 100..3200 .027 .092 .38 1.86 8.6 42.9, slope 2.15 (top 2.3)** |
| post equalities `Xi + Xi+1 = 1` (`chain_eq`) | 100..3200 | .006 .. .20 | 1.0 | 1.0 | - | inherent, linear |
| post n dense rows of n terms (`dense_rows`) | 5..80 | .001 .0044 .016 .069 .37 | 2.4 (2.1) | 2.26 | python_calls 2.6 (normal_form_add merges) | inherent, partly removable (R3) |
| post disequations on a chain (`diseq`) | 100..1600 | .014 .044 .17 .81 3.7 | 2.2 (2.0) | 1.9 (manual run, 100..400) | python_calls 1.95 | inherent |
| post the path LP (`lp_post`) | 25..800 | .002 .. .075 | 1.0 | - | - | linear |
| bind a chain to numbers in one unification (`bind_numbers`) | 50..800 | .011 .042 .18 1.0 7.9 | **3.0** (2.35) | **1.96** | terms_scanned 3.0, terms_read 2.0 | **unclear: the port does more work than Scryer's copy** (R2). **After R1b: n = 50..1600 .010 .033 .14 .59 2.9 13.5, slope 2.10 (top 2.2)**: the cubic term was the scan |
| var-var binding of a chain (`bind_varvar`) | 25..400 | .012 .061 .39 3.4 33.9 | 3.3 (2.9) | 2.85 | terms_read 3.0 | inherent (D24, Low 8); overhead partly removed on r32-varvar (7a573135). After R1b and R4: unchanged within noise (paired n = 200: 1.64 s against 1.60 s): its rows almost all hold the variable, so there is nothing to skip |
| `sup` of a sum over a bounded chain (`sup_chain`) | 50..1600 | .005 .020 .074 .31 1.5 6.8 | 2.2 (2.1) | 1.98 | terms_read 2.0, 1 pivot | inherent |
| `inf(Xn - X1)` (`inf_chain`) | 50..1600 | 0.0001 .. 0.003 | 1.25 | - | - | linear |
| `maximize` path LP (`lp_maximize`) | 25..800 | .010 .026 .094 .35 1.4 9.1 | 2.7 (1.96) | 1.99 | pivots 1.0, rows_read 2.0, python_calls 1.98 | inherent (the 2.7 top slope is noise: calls grow 1.98). After R1b and R4: paired n = 400 1.19 s against 1.14 s |
| `bb_inf` 0/1 knapsack (`bb_knapsack`) | 5..40 | .003 .037 .058 .61 4.6 1.7 .31 4.1 | depends on the instance | depends on the instance | time follows bb_nodes (4..7958) | inherent (the search) |
| `bb_inf` wide, `Xi >= 1/2` (`bb_wide`) | 25..400 | .005 .012 .030 .090 .29 | 1.7 (1.4) | 1.87 | rows 2.0, 1 node (bb narrows the bounds) | inherent |
| `dump` onto `[X1, Xn]` of a bounded chain (`dump_small`) | 25..200 | .11 .68 6.3 38.8 | 2.6 (2.9) | 2.92 | pivots 2.0, terms_read 3.0, fm_cross 1.0 | inherent (redundancy checks) |
| `dump` onto all n chain variables (`dump_large`) | 25..200 | .025 .14 1.0 7.8 | 3.0 (2.8) | 2.89 | terms_read 3.0 | inherent |
| `dump` onto 2 of n variables, 2n random 3-term rows (`dump_sparse`) | 6..24 | .027 .037 .14 .11 .088 .56 .75 | about 2 (noisy, varies by instance) | - | fm_cross 23..63 | typical: no FM blow-up seen |
| `entailed(X1 =< Xn)` on a chain (`entailed`) | 50..1600 | .0002 .. .0045 | 1.4 | 1.0 | python_calls 1.0 | linear |
| post `Zi = Xi*Yi` (`nonlinear_post`) | 100..3200 | .004 .. .12 | 1.0 | - | - | linear |
| wake them by binding the Yi (`nonlinear_wake`) | 100..1600 | .015 .049 .20 1.2 4.8 | 2.0 (2.1) | 1.9 (manual, 100..400) | python_calls 2.0 | inherent |
| n rounds of mark, `Xi >= 50`, undo (`backtrack_rounds`) | 50..400 | .098 .76 6.5 56 | 3.1 | 2.9 (manual, 25..100) | terms_read 3.0 | inherent; the undo itself is negligible |
| chain with a mark per link, then undo all (`backtrack_deep`) | 100..1600 | as `chain_le` | 3.0 | - | as `chain_le` | marks and undos cost nothing measurable. **After R1b: as `chain_le`, n = 3200 41 s, slope 2.15** |
| `{S = X1 + ... + Xn}`, left-leaning (`left_sum`) | 250..8000 | .033 .12 .48 1.9 7.5 29.8 | 2.0 | 1.99 | python_calls 2.0 | inherent, but removable by implementation (R3) |
| n independent components, then `sup` (`components`) | 100..3200 | .011 .. .33 | 0.9 | - | 1 back substitution | linear |
| engine path: `go(N, S)` from a `.clausal` file (`engine_chain`) against the bare API (`engine_chain_bare`) | 100..1600 | engine .057 .23 1.17 7.5 51.5; bare .045 .18 1.01 6.6 46.4 | 2.8 against 2.8 | - | same | engine overhead 1.27x at n = 100, 1.11x at 1600: additive per goal, same exponent |
| engine `{_ = 0 + _ + ...}` (`engine_left_sum`) | 250..4000 | .037 .. 7.6 | 2.0 | - | - | same as bare `left_sum` |

Manual Scryer runs (programs in the survey session, the same shapes):
`\+ \+ {X >= 50}` over a bounded chain, n = 25/50/100: 0.35M, 2.5M, 19.0M
inferences. Disequations n = 100/200/400: 0.24M, 0.88M, 3.4M.
Non-linear wake-up n = 100/200/400: 0.40M, 1.49M, 5.74M.

## Ranked findings and proposed fixes

Ranked by user impact: how common the shape is, multiplied by how much
time it costs at sizes people use.

### R1. The row-membership scan in back substitution: cubic posting, about 10x to win (inherent in 1.3.3's text, removable by implementation)

- **Measured.** Every back substitution reads every row of the
  component (`rows_read` = n^2 for a chain of n). For each row,
  `delete_factor_homogeneous` (linear_forms.py) scans the whole row in
  Python, calling `deref` on each term, to learn whether the substituted
  variable is in it. In a chain most rows hold about n/3 terms, so
  `terms_scanned` grows as n^3 (85.7M at n = 800), but `terms_read` (the
  rows actually rewritten) grows only as n. In the chain_le profile at
  n = 400, this scan is 2.17 s of 3.81 s cumulative (1.39 s own time
  plus 11.8M `deref` calls). The same scan dominates `backtrack_deep`
  (84 s of its 160 s profile), `engine_chain`, `bind_numbers` and
  `lp_maximize`.
- **Is it 1.3.3's?** Yes. store.pl `delete_factor_hom/4` in Scryer's copy
  continues on both `<` and `>`, so it is a full scan, and Scryer's chain
  posting grows as n^2.91. The exponent is therefore 1.3.3's. But the
  scan only answers "is V in this row, and with which coefficient",
  and an index can answer that without changing anything else.
- **Fix (implementation only).** Make the scan for an absent variable
  cheap:
  - (a) Run the scan in C, e.g.
    `operator.indexOf(map(deref, map(itemgetter(0), terms)), variable)`.
    Var compares by identity, which was checked: `Var.__eq__` is
    `object.__eq__`. This keeps the semantics exactly; the gain is the
    constant factor of the scan, about 5 to 10x on the dominant term.
  - (b) A per-row set of variable ids, built when the `LinearForm` is
    made, so that a row without the variable is skipped in O(1). The
    exponent falls from 3 to 2 (rows_read). It needs the invariant that
    a row's variables are unbound, or that the set is checked against
    `deref`. D3's stand-in renaming rebuilds rows (`_rename_in_form`),
    so the set must be rebuilt there too.
- **Expected gain.** chain_le at n = 800 is 5.5 s now. With (a), about
  1 s. With (b), about 0.3 s, quadratic.
- **Risk.** (a) none: the same rows, the same order and the same
  results. (b) low to medium: a stale set would silently skip a row. It
  needs a debug assertion mode that cross-checks the set against the
  scan over the clpq_port suite. Neither fix changes iteration order,
  variable creation or residual text.

- **Status (2026-11-03, measured).** (b) is done; (a) was tried and
  backed out.
  - (a) The C scan (`operator.indexOf` over the ids of the
    dereferenced variables) was no faster on long rows: about 45 ns a
    term either way on CPython 3.13 (300 terms: 14.4 us against
    13.6 us). On the short rows of a pivot it was 2 to 4 times slower,
    mostly the ValueError a miss raises, and lp_maximize n = 400 went
    from 1.18 s to 1.46 s. The estimate of 5 to 10x did not hold.
  - (b) Each `LinearForm` keeps `variable_ids`: the ids of its term
    variables as they are, and as they dereference when the index is
    built. The index is built at the row's second scan, because building
    it costs about two scans. Indexing at the first scan made
    `bind_varvar` 45% slower, since there nearly every row read is
    rewritten. A form never changes, so the trail needs nothing: it puts
    back old forms, and each carries its own index. The index can go
    stale only if a variable of the row is bound to another variable
    after the row was indexed. The D3 hook replaces bound members by
    stand-ins before anything reads the rows.
    `CLAUSAL_CLPQ_CHECK_ROW_INDEX=1` checks every skip against a full
    scan. The clpq_port suite, the full differential and
    `tests/test_clpq*.py` pass with it on and off, and the differential's
    goldens and traces are unchanged.
  - Paired runs against the base, minimum of 3, sequential, load 8 to
    10 on 32 cores:

    | case | base | after |
    |---|---|---|
    | `chain_le` n = 800 | 6.52 s | 1.53 s |
    | `bind_numbers` n = 800 | 7.07 s | 2.46 s |
    | `bind_varvar` n = 200 | 1.64 s | 1.60 s |
    | `lp_maximize` n = 400 | 1.19 s | 1.14 s |
    | `dump_large` n = 100 | 0.76 s | 0.75 s |
    | `sup_chain` n = 800 | 1.21 to 1.23 s | 1.26 to 1.31 s |

    `sup_chain` does no index work (cProfile: 4.98 s against 4.89 s), so
    its difference is the box's noise.
  - Exponents, from the slope between n = 400 and n = 800, run with 7
    jobs as the baseline was: `chain_le` from 2.92 to 2.29,
    `backtrack_deep` from 2.89 to 2.21 and `bind_numbers` from 2.76 to
    2.32. Over every size up to 3200 (1600 for `bind_numbers`) the
    slopes are 2.15, 2.15 and 2.10. `terms_scanned` in the table still
    counts each row's length, not the terms that are now read.
  - `nf_coeff_of` (`normal_form_coefficient_homogeneous`) was left as it
    is. It is an ordered scan that stops early, and it matches by order
    key, not identity: a stand-in shares its variable's order, so an
    identity index would not answer the same.

### R2. Binding a solved chain to numbers: the port is cubic where Scryer's copy is quadratic (unclear, investigate first)

- **Measured.** For `bind_numbers` (`L = [0, ..., n-1]` after posting
  the chain), the port's time grows as n^3.0 (7.9 s at 800), and
  `terms_scanned` grows as n^3. Scryer's copy grows as n^1.96 by
  inferences (8.5M at n = 400; at about 21 inferences a term that is
  about 0.4M terms, against the port's 10.8M scanned).
- Binding one variable at a time, first to last: the port rewrote
  n^2/2 rows with 10.7M terms read at n = 400 (2.3 s, cubic), while
  Scryer's copy stayed quadratic (0.58M, 2.19M, 8.55M inferences at
  100/200/400). Binding last to first, Scryer's copy is cubic too
  (3.1M, 22.3M, 169M), and so is the port.
- So 1.3.3's work depends on which variable `solve/5` picks
  (`select_dependent`, whose `preference/3` takes the later term on a
  tie). The port's choices, or the term order in its rows, differ from
  those of Scryer's copy on this shape.
- **Inferred.** Likely causes: the variable order of D4/D11 (creation
  order, which decides term order in rows and so the tie in
  `preference/3`), or D3's binding sequence (stand-ins: all of a
  unification's variables are bound before its hooks run).
  Unverified.
- **Next step.** Trace `select_dependent`'s choice per binding at
  n = 10 in the port and in Scryer's copy (in Scryer, a `print` in
  `solve/5`), and compare. If the choice differs, the cause is an
  ordering deviation, and changing it is **not** implementation-only:
  it can change residual text and variable order. Stop and rule on it.
  If the choice is the same, find the extra rewrites. That would be
  overhead.
- **Why it ranks high.** Labelling or binding the variables of a solved
  store is the commonest end of a CLP(Q) program.

### R3. Merging normal forms (`normal_form_add`, `_standard_order`): quadratic left-leaning sums (inherent in 1.3.3's text, removable by implementation)

- **Measured.** `{S = X1 + ... + Xn}` read left-leaning grows as n^2.0:
  1.9 s at n = 2,000 (the reported figure, reproduced) and 29.8 s at
  8,000. Scryer's copy grows as n^1.99, so the algorithm is 1.3.3's:
  nf.pl `nf_add` merges the k-term sum so far with the new monomial,
  which sorts last, so every merge walks all k terms.
- The port pays 3 µs per comparison, in `_standard_order`'s generic
  work stack: 5.8 s of a 12.3 s profile, with 2.0M comparisons at
  n = 2,000. The same merges are the cost of `dense_rows` (each row is
  an n-term left-leaning sum, so n^3 comparisons in all; python_calls
  grow 2.63 against the store's 0.9).
- **Fix (implementation only).**
  - (a) In `normal_form_add`, when `second` has one monomial (or, in
    general, by galloping), find its place by binary search with the
    same comparison, then slice and concatenate.
  - (b) A fast path in `compare_power_products` for the overwhelmingly
    common `[(var, 1)]` against `[(var, 1)]`: compare the `_id`s
    directly after `deref`, as `_standard_order` already does.

  The result is identical because the comparison is a total order on
  distinct power products, and equal ones still combine (dropping a
  zero coefficient) as now.
- **Expected gain.** left_sum at n = 2,000 from 1.9 s to about 0.05 s.
  The remaining list copies run in C, so the exponent is effectively
  about 1 below n of about 10^4. dense_rows gains about 2x.
- **Risk.** Low. Equal keys must combine exactly as now; the existing
  normal_form tests pin the output order. Monomial order is the
  sorted order either way.

### R4. Merge kernel constant factors (`add_homogeneous_parts*`, `compare_variable_order`) (overhead per unit, not asymptotic)

- **Measured.** `add_homogeneous_parts_first_scaled` and its siblings
  are the top own-time entry in `bind_varvar` (23.7 s of a 100 s
  profile), `dump_large`, `sup_chain`, `bb_knapsack`, `dump_sparse` and
  `backtrack_rounds`. Under them, `compare_variable_order` reads two
  states per comparison: 21M `compare_order_values` calls in
  bind_varvar n = 200.
- Commit 7a573135 (r32-varvar) already makes the merge look each
  term's order up once (`variable_ordering.order_key`), measured at
  1.8x on bind_varvar. It is not in this base.
- **Fix.** Merge r32-varvar, then apply the same order-key-once pattern
  to `add_homogeneous_parts_scaled` and `add_homogeneous_parts`.
  Rational arithmetic (`make_rational` plus `gcd`, about 10% in most
  profiles) could skip the gcd when one factor is 1 or -1.
- **Expected gain.** 1.5 to 2x across pivot-heavy work (sup, LP, bb_inf,
  dump). The exponent is unchanged.
- **Risk.** None if the comparisons and their outcomes are kept, as
  7a573135 did.

- **Status (2026-11-03, measured).** Done for `add_homogeneous_parts_scaled`
  (add_linear_ffh/7) and `add_homogeneous_parts` (add_linear_11h/5). Both
  now look each term's order up once (at most one lookup a term in
  `tests/clpq_port/test_row_scans.py`, against 78 for 45 terms before).
  The comparisons and their outcomes are the same, and the identity gate
  passes. The gain is small: in the sup_chain n = 800 profile the two
  merges went from 0.92 s and 0.69 s cumulative to 0.74 s and 0.57 s.
  No other merge in the port compares by `compare_variable_order` at
  each step (`projection.py` compares once). The gcd short cut for a
  factor of 1 or -1 was not attempted.

### R5. Projection (`dump/3`): cubic for chains, dominated by the redundancy checks (inherent)

- **Measured.** `dump_small` (2 targets of an n-chain) does n^2 pivots
  and n^3 terms (6.3 s at n = 100, 38.8 s at 200). Scryer's copy grows
  as n^2.92.
- The profile at n = 50: 2.69 s of 3.1 s is in
  `redundancy.redundancy_variables` (one `redundant/4` per bound, each a
  trial post with a pivot). Fourier-Motzkin itself is small:
  `fm_cross` is linear for chains, and 23 to 63 rows for 2n random
  three-term rows at n = 6 to 24, with no exponential blow-up in the
  shapes measured. FM is exponential only in adversarial stores, which
  were not constructed here.
- `dump_large` is cubic for the same reason, and passes the default
  `clpq_projection` cap at n = 200.
- **Fix.** None asymptotic; R1 and R4 lower the constant.
- **Risk.** -

### R6. Var-var binding (inherent, known: D24 Low 8)

Measured here before 7a573135: n^3.3 top (33.9 s at n = 400), Scryer
n^2.85. `terms_read` grows as exactly n^3/3, 1.3.3's count. The
remaining port overhead in the profile is `_rename_in_form` (8.3 s of
100 s), which 7a573135's `isdisjoint` already cuts. Not redone.

### R7. Everything else is inherent with the same exponent as Scryer's copy

`sup_chain` (2.1 against 1.98), `lp_maximize` (calls 1.98 against
1.99), `diseq` (2.0 against 1.9), `nonlinear_wake` (2.0 against 1.9),
`backtrack_rounds` (3.0 against 2.9), `bb_wide` (1.7 against 1.87) and
`bb_knapsack` (time follows nodes; Scryer is the same).

Linear: `chain_eq`, `lp_post`, `nonlinear_post`, `components`,
`entailed`, `inf_chain`.

Backtracking adds nothing measurable: `backtrack_deep` equals
`chain_le`, and no undo function appears in any profile's top 25.

The engine path costs 1.1 to 1.3 times the bare API, with the same
exponent.

## What is measured and what is inferred

- **Measured:** every time, count and exponent above; the profiles'
  top entries; the Scryer inference counts; the one-at-a-time and
  reverse-order binding runs in R2.
- **Inferred:**
  - R1's and R3's expected gains are estimates from the profiles'
    shares, not from prototypes.
  - R2's cause (ordering or D3) is a hypothesis.
  - "Inherent" means the exponent matches Scryer's copy of the 1.3.3
    text on the same shape. Scryer's copy may itself differ from
    SICStus 1.3.3 in variable order, which is the open question in R2.
- **Not covered:**
  - adversarial Fourier-Motzkin stores;
  - very large coefficients (D24's caps cover them);
  - `bb_inf` instances chosen for a large search;
  - memory use.

## Reproduce

```
CLAUSAL_CLPQ=holzbaur python benchmarks/clpq_port_scaling.py --point chain_le 400 --count   # one point
python benchmarks/clpq_port_scaling.py chain_le left_sum bind_numbers --scryer --profile
```
