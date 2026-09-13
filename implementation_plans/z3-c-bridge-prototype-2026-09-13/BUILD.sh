#!/bin/sh
# Build the prototype bridge. Nothing here is part of the engine -- it is a
# measurement artefact kept so the numbers can be re-derived rather than trusted.
set -e
Z3DIR=/workspace/clausal/venv/lib/python3.13/site-packages/z3
PYINC=$(/workspace/clausal/venv/bin/python -c "import sysconfig;print(sysconfig.get_paths()['include'])")
gcc -O2 -fPIC -shared -o _z3bridge.so _z3bridge.c \
    -I"$PYINC" -I"$Z3DIR/include" -L"$Z3DIR/lib" -lz3 -Wl,-rpath,"$Z3DIR/lib"
/workspace/clausal/venv/bin/python bench.py
