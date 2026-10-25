"""``python -m clausal`` -- the ``clausal`` command (:mod:`clausal.cli`):
run a ``.clausal`` or ``.pl`` program, or, with no FILE, open the
interactive ``?-`` top-level (``--python`` for the Python REPL)."""
import sys

from clausal.cli import main

sys.exit(main())
