"""Build _gprolog_ext C extension.

Finds GNU Prolog via GPROLOG_HOME or by probing standard paths.
GNU Prolog MUST be compiled with --disable-regs for shared-library
embedding (prevents WAM registers from hijacking callee-saved CPU
registers).
"""
import os
import glob
import subprocess
from setuptools import setup, Extension

def find_gprolog_root():
    """Locate the versioned GNU Prolog directory (containing lib/ and include/)."""
    # 1. GPROLOG_HOME
    home = os.environ.get("GPROLOG_HOME")
    if home and os.path.isfile(os.path.join(home, "include", "gprolog.h")):
        return home

    # 2. Infer from gprolog binary
    try:
        which = subprocess.check_output(["which", "gprolog"], text=True).strip()
        if which:
            bin_dir = os.path.dirname(which)
            prefix = os.path.dirname(bin_dir)
            # Check <prefix>/gprolog-*/include/gprolog.h
            for entry in glob.glob(os.path.join(prefix, "gprolog-*")):
                if os.path.isfile(os.path.join(entry, "include", "gprolog.h")):
                    return entry
            if os.path.isfile(os.path.join(prefix, "include", "gprolog.h")):
                return prefix
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # 3. Common paths
    for base in ["/usr/lib", "/usr/local/lib", "/opt"]:
        for entry in glob.glob(os.path.join(base, "gprolog*")):
            if os.path.isfile(os.path.join(entry, "include", "gprolog.h")):
                return entry

    raise RuntimeError(
        "Could not find GNU Prolog installation.\n"
        "Set GPROLOG_HOME to the versioned directory containing lib/ and include/.\n"
        "Example: GPROLOG_HOME=/usr/lib/gprolog-1.5.0\n"
        "GNU Prolog MUST be compiled with --disable-regs for embedding."
    )


root = find_gprolog_root()
lib_dir = os.path.join(root, "lib")
inc_dir = os.path.join(root, "include")

# Collect the standalone .o files (Prolog-compiled builtin registrations)
extra_objects = []
for obj in ["all_pl_bips.o", "all_fd_bips.o", "debugger.o", "top_level.o"]:
    path = os.path.join(lib_dir, obj)
    if os.path.exists(path):
        extra_objects.append(path)

# Static archives to link
libraries = []
extra_link_args = []
for lib_name in ["engine_pl", "bips_pl", "engine_fd", "bips_fd", "linedit"]:
    archive = os.path.join(lib_dir, f"lib{lib_name}.a")
    if os.path.exists(archive):
        extra_link_args.append(archive)

extra_link_args.append("-lm")

ext = Extension(
    "_gprolog_ext",
    sources=["_gprolog_ext.c"],
    include_dirs=[inc_dir],
    extra_objects=extra_objects,
    extra_link_args=extra_link_args,
)

setup(ext_modules=[ext])
