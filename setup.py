import sys
import sysconfig
from setuptools import setup, Extension

if sys.platform == "win32":
    # MSVC takes its own flag syntax and rejects -Wextra; setuptools already
    # passes /O2 /W3, its equivalents of the flags below.
    extra_compile_args = []
else:
    extra_compile_args = ["-O2", "-Wall", "-Wextra"]

# Free-threaded Python builds need the Py_GIL_DISABLED define
# so our #ifdef guards activate. setuptools sets it automatically
# for 3.13t+, but we also add it explicitly for clarity.
if sysconfig.get_config_var("Py_GIL_DISABLED"):
    extra_compile_args.append("-DPy_GIL_DISABLED=1")

ext_variables = Extension(
    "clausal.logic.variables._variables",
    sources=["clausal/logic/variables/_variables.c"],
    extra_compile_args=extra_compile_args,
)

ext_trampoline = Extension(
    "clausal.logic.runtime._trampoline",
    sources=["clausal/logic/runtime/_trampoline.c"],
    extra_compile_args=extra_compile_args,
)

ext_list_unify = Extension(
    "clausal.logic.runtime._list_unify",
    sources=["clausal/logic/runtime/_list_unify.c"],
    extra_compile_args=extra_compile_args,
)

ext_clpfd = Extension(
    "clausal.logic._clpfd_core",
    sources=["clausal/logic/_clpfd_core.c"],
    include_dirs=["clausal/logic"],
    extra_compile_args=extra_compile_args,
)

ext_tabling_core = Extension(
    "clausal.logic._tabling_core",
    sources=["clausal/logic/_tabling_core.c"],
    include_dirs=["clausal/logic"],
    extra_compile_args=extra_compile_args,
)

ext_clpfd_propagate = Extension(
    "clausal.logic._clpfd_propagate",
    sources=["clausal/logic/_clpfd_propagate.c"],
    include_dirs=["clausal/logic"],
    extra_compile_args=extra_compile_args,
)

ext_lists_core = Extension(
    "clausal.logic._lists_core",
    sources=["clausal/logic/_lists_core.c"],
    include_dirs=["clausal/logic"],
    extra_compile_args=extra_compile_args,
)

ext_constraints_dif = Extension(
    "clausal.logic._constraints_dif",
    sources=["clausal/logic/_constraints_dif.c"],
    include_dirs=["clausal/logic/variables"],
    extra_compile_args=extra_compile_args,
)

ext_arithmetic_core = Extension(
    "clausal.logic._arithmetic_core",
    sources=["clausal/logic/_arithmetic_core.c"],
    include_dirs=["clausal/logic/variables"],
    extra_compile_args=extra_compile_args,
)

ext_chars_core = Extension(
    "clausal.logic.builtins._chars_core",
    sources=["clausal/logic/builtins/_chars_core.c"],
    include_dirs=["clausal/logic"],
    extra_compile_args=extra_compile_args,
)

ext_clpr_core = Extension(
    "clausal.logic._clpr_core",
    sources=["clausal/logic/_clpr_core.c"],
    extra_compile_args=extra_compile_args,
    libraries=["m"],
)

ext_clpb_core = Extension(
    "clausal.logic._clpb_core",
    sources=["clausal/logic/_clpb_core.c"],
    extra_compile_args=extra_compile_args,
)

setup(ext_modules=[ext_variables, ext_trampoline, ext_list_unify, ext_clpfd,
                   ext_tabling_core, ext_clpfd_propagate, ext_lists_core,
                   ext_constraints_dif, ext_arithmetic_core, ext_chars_core,
                   ext_clpr_core, ext_clpb_core])
