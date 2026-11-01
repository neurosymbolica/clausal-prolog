# The installed package ships `.seam` examples only, and its AGENTS.md links point at docs that are not installed

**Filed:** 2026-11-01, from a user reading the installed 1.3.0 from PyPI.
**Status:** open.

## Observed (1.3.0 wheel, cp313 manylinux, checked 2026-11-01)

- `clausal/examples/` holds 14 `.seam` programs (nqueens, sudoku,
  map_coloring, hanoi, graph, symbolic_diff, metainterpreters, dcg_state,
  ...) and no `.clausal` file, although `.clausal` (Clausal Prolog) has been
  the public surface since the extension flip (2026-10-02). A reader of the
  installed package concludes the seam is the format to write.
- The wheel ships the `AGENTS.md` maps but no user docs. `clausal/AGENTS.md`
  links `../docs/style.md`, `../docs/examples.md` and `../docs/public-api.md`,
  which do not exist in an installed tree. The docs are online
  (https://clausal.pl, `[project.urls]`), but nothing in the package says so.

## Do

1. Add Clausal Prolog (`.clausal`) versions of the examples (or replace the
   seam ones; keep a seam example or two where they show the Python
   boundary), and state in `clausal/examples/` which surface is public.
   Each example needs a test (as the seam ones have).
2. In the shipped `AGENTS.md` files, link docs by absolute URL
   (`https://clausal.pl/...`) or add one line saying where the docs live.
   Shipping `docs/` itself is not needed.
3. A wheel check that every relative link in a shipped `.md` resolves inside
   the wheel (could live in `tools/wheel_smoke.py`).
