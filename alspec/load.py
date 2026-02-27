from __future__ import annotations

import re
from typing import Any

from alspec.spec import Spec


def load_spec_from_file(path: str) -> Spec | str:
    """Load a .py file, locate the ``*_spec()`` entry-point, and return the Spec.

    The function searches the executed module's namespace for:

    1. Any callable whose name ends in ``_spec``.
    2. Falls back to any callable that, when called with no arguments, returns
       a :class:`~alspec.spec.Spec` instance.

    Returns the :class:`~alspec.spec.Spec` on success, or an error string on
    any failure.
    """
    try:
        source = open(path).read()
    except OSError as e:
        return f"Could not read file: {e}"

    namespace: dict[str, Any] = {}
    try:
        exec("from alspec import *", namespace)
        exec("from alspec.helpers import *", namespace)
    except Exception as e:
        return f"Failed to import alspec builtins: {e}"

    try:
        exec(compile(source, path, "exec"), namespace)
    except Exception as e:
        return f"Code execution failed: {e}"

    # 1. Prefer functions whose name ends in _spec.
    candidates = [
        (name, obj)
        for name, obj in namespace.items()
        if callable(obj) and re.search(r"_spec$", name) and not name.startswith("_")
    ]

    # 2. If nothing matches the naming convention, probe every callable.
    if not candidates:
        candidates = [
            (name, obj)
            for name, obj in namespace.items()
            if callable(obj) and not name.startswith("_")
        ]

    if not candidates:
        return "No callable spec-factory function found in file"

    # Try each candidate in order; return the first Spec we get back.
    last_err = ""
    for name, fn in candidates:
        try:
            result = fn()
        except Exception as e:
            last_err = f"'{name}()' raised: {e}"
            continue
        match result:
            case Spec():
                return result
            case _:
                last_err = f"'{name}()' returned {type(result).__name__}, expected Spec"

    return last_err or "No suitable spec-factory function found"
