from __future__ import annotations
import enum
from exposedfunctionality.function_parser.types import add_type
from typing import Union, Any, TypeVar, Type


ET = TypeVar("ET", bound="DataEnum")


class DataEnum(enum.Enum):
    """
    Base class for data enums. They should be used as a type hint for a function argument for funcnodes.
    In the function the value can be accessed by using the v method.
    The reson for this is to be more robust that the values to the function can be
    passed as the Enum, as a value or as a enum key.

    Example:
    ```python
    class TestEnum(DataEnum):
        A = 1
        B = 2
        C = 3

    @NodeDecorator(node_id="test_enum")
    def test_enum_node(a: TestEnum) -> int:
        a = TestEnum.v(a)
        return a
    """

    def __init_subclass__(cls) -> None:
        add_type(
            cls,
            cls.__name__,
        )

        cls._lookup = {}
        for member in cls:
            cls._lookup[member.name] = member
            try:
                if member.value not in cls._lookup:
                    cls._lookup[member.value] = member
            except TypeError:
                pass
            if str(member.value) not in cls._lookup:
                cls._lookup[str(member.value)] = member

    @classmethod
    def interfere(cls: Type[ET], a: Union[ET, str, Any]) -> ET:
        if isinstance(a, cls):
            return a
        if a in cls._lookup:
            return cls._lookup[a]
        try:
            return cls(a)
        except ValueError as e:
            if isinstance(a, str):
                if a.startswith(cls.__name__ + "."):
                    a = a[len(cls.__name__) + 1 :]
                    if a in cls._lookup:
                        return cls._lookup[a]

            raise e

    @classmethod
    def v(cls: Type[ET], a: Union[ET, str, Any]) -> Any:
        return cls.interfere(a).value
