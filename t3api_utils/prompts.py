"""Questions for scripts a person runs: ``confirm()``, ``ask()`` and ``choose()``.

They match the library's own prompts and pickers. Without a terminal (or
Jupyter) they raise :class:`~t3api_utils.errors.NotInteractive` instead of
hanging, and Ctrl-C raises ``KeyboardInterrupt`` to the caller.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar, overload

from t3api_utils import _console
from t3api_utils.pickers import choose

T = TypeVar("T")

__all__ = ["ask", "choose", "confirm"]


def confirm(question: str, *, default: bool = False) -> bool:
    """Ask a yes/no question. The default answer is no.

    ```python
    if t3.confirm(f"Submit {len(rows)} rows to Metrc?"):
        ...
    ```

    Raises:
        NotInteractive: there's no terminal to ask in.
    """
    _console.require_interactive(f"The question {question!r}")
    return _console.confirm(question, default=default)


@overload
def ask(question: str, *, default: str | None = None) -> str: ...


@overload
def ask(question: str, *, default: str | None = None, parse: Callable[[str], T]) -> T: ...


def ask(
    question: str,
    *,
    default: str | None = None,
    parse: Callable[[str], object] | None = None,
) -> object:
    """Ask for a value. An empty answer takes ``default``, or asks again if there's none.

    ``parse`` turns the answer into something else. If it raises
    ``ValueError``, the message is shown and the question asked again:

    ```python
    quantity = t3.ask("Quantity", parse=float)
    when = t3.ask("Date (YYYY-MM-DD)", default=str(date.today()), parse=date.fromisoformat)
    ```

    Raises:
        NotInteractive: there's no terminal to ask in.
    """
    _console.require_interactive(f"The question {question!r}")
    while True:
        answer = _console.ask(question, default=default)
        if parse is None:
            return answer
        try:
            return parse(answer)
        except ValueError as exc:
            _console.error(str(exc) or f"{answer!r} isn't valid.")
