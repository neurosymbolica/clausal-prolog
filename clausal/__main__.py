"""``python -m clausal`` -- the ``clausal`` command (:mod:`clausal.cli`):
run a ``.clausal`` or ``.pl`` program, or, with no FILE, start the
interactive REPL."""
import sys

from clausal.cli import main

sys.exit(main())
