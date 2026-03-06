from setuptools import setup, Extension

ext = Extension(
    "clausal.logic.variables._variables",
    sources=["clausal/logic/variables/_variables.c"],
    extra_compile_args=["-O2", "-Wall", "-Wextra"],
)

setup(ext_modules=[ext])
