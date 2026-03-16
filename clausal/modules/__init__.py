"""clausal.modules — standard library modules for Clausal.

This package acts as the top-level search path for Clausal module imports.
When a .clausal file uses ``-import_from(regex, [Match, ...])`` or
``-import_module(regex)``, the import machinery looks here (as
``clausal.modules.regex``) if the bare module name is not found.
"""
