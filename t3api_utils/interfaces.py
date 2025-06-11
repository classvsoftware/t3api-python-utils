
from typing import Any, Dict, List, ParamSpec, Protocol, TypeVar, runtime_checkable


P = ParamSpec("P")
T = TypeVar("T")

@runtime_checkable
class HasData(Protocol[T]):
    """
    A protocol representing any object that exposes a `data` attribute
    containing a list of items of type `T`.
    """

    data: List[T]
    
    
@runtime_checkable
class SerializableObject(Protocol):
    """
    Protocol defining the required structure for objects to be serialized.
    Each object must have an `index` (str), `license_number` (str), and a `to_dict()` method.
    """
    index: str
    license_number: str

    def to_dict(self) -> Dict[str, Any]: ...
