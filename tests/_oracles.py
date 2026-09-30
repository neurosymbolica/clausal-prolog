"""Where the external Prolog oracles live -- the ONE definition.

Every test that runs a real Prolog system imports its path from here, so the
reference binary is chosen in one place and can be overridden per run:

    CLAUSAL_SCRYER=/path/to/scryer-prolog  CLAUSAL_TREALLA=/path/to/tpl

The Scryer default is the clean build (upstream master plus library(clpq)),
NOT /workspace/scryer-prolog, whose binary is built from uncommitted clpz
work-in-progress that drops constraints and prints trace lines.
tests/test_oracle_paths.py fails if a test hardcodes that path again.

Each caller keeps its own policy for a missing binary (skip, fail, or the
CLAUSAL_ISO_ALLOW_NO_SCRYER opt-out); this module only names the path.
"""
import os

SCRYER = os.environ.get(
    "CLAUSAL_SCRYER", "/workspace/scryer-prolog-clpq/target/release/scryer-prolog")
TREALLA = os.environ.get("CLAUSAL_TREALLA", "/workspace/trealla-prolog/tpl")
