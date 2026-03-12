from setuptools import setup, Extension

ext_variables = Extension(
    "clausal.logic.variables._variables",
    sources=["clausal/logic/variables/_variables.c"],
    extra_compile_args=["-O2", "-Wall", "-Wextra"],
)

ext_trampoline = Extension(
    "clausal.logic._trampoline",
    sources=["clausal/logic/_trampoline.c"],
    extra_compile_args=["-O2", "-Wall", "-Wextra"],
)

setup(ext_modules=[ext_variables, ext_trampoline])
