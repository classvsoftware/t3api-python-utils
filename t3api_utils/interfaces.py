
from typing import List, ParamSpec, Protocol, TypeVar, runtime_checkable


P = ParamSpec("P")
T = TypeVar("T")

@runtime_checkable
class HasData(Protocol[T]):
    """
    A protocol representing any object that exposes a `data` attribute
    containing a list of items of type `T`.
    """

    data: List[T]