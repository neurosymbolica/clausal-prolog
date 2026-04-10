# Naming Consistency Audit for Existing Wrappers

Audit existing library wrappers for naming consistency with the
"least surprise for library users" convention established in
`implementation_plans/EXTERNAL_WRAPPER_CHECKLIST.md`.

The convention: use the library's own names. Don't normalise case.
Don't abbreviate unless domain-standard.

## Wrappers to check

- [ ] `py/sklearn.py` — are algorithm names matching sklearn's API?
- [ ] `py/scipy_spatial.py` — `CrossDistance` vs scipy's `cdist`
- [ ] `py/scipy_optimize.py`
- [ ] `py/scipy_linalg.py`
- [ ] `py/scipy_stats.py`
- [ ] `py/scipy_interpolate.py`
- [ ] `py/scipy_signal.py`
- [ ] `py/scipy_integrate.py`
- [ ] `py/scipy_fft.py`
- [ ] `spacy_module.py`
- [ ] `py/sympy.py`
- [ ] Any other `py/*.py` modules

## What to look for

- Predicate names that normalised case (CamelCase -> snake_case) where
  the library uses CamelCase
- Abbreviated names that aren't domain-standard (`cdist`, `pdist`, etc.)
- Names that diverge from the library's API for no clear reason
- TitleCase predicates that should now follow library convention

## Note

Some existing wrappers predate this convention and may use TitleCase
predicate names. This is a cleanup task, not urgent — existing code
works fine. But new wrappers should follow the convention from the start.
