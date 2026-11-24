"""Render Sphinx roles in docstrings as inline code for mkdocstrings.

The source docstrings use ``:func:`name``` style references. The Google
docstring parser leaves them as literal text, so this griffe extension turns
them into plain inline code (``~pkg.mod.Name`` becomes ``Name``). It is
loaded from mkdocs.yml and only affects the docs build.
"""

from __future__ import annotations

import re
from typing import Any

import griffe

_ROLE = re.compile(r":(?:func|meth|class|attr|mod|exc|data|obj):`(~?)([^`]+)`")


def _replace(match: re.Match[str]) -> str:
    short, target = match.group(1), match.group(2)
    return f"`{target.rsplit('.', 1)[-1] if short else target}`"


class SphinxRoles(griffe.Extension):
    def on_instance(self, *, obj: griffe.Object, **kwargs: Any) -> None:
        if obj.docstring is not None:
            obj.docstring.value = _ROLE.sub(_replace, obj.docstring.value)
