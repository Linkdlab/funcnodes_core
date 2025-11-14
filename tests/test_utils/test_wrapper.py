import inspect

import pytest

from funcnodes_core.utils.wrapper import (
    NoOverrideMixin,
    savemethod,
    saveproperty,
    signaturewrapper,
)


def test_signaturewrapper_sets_signature_on_inner_function():
    def reference(
        a: int, b: str = "b", *, flag: bool = True
    ) -> str:  # pragma: no cover - helper
        return f"{a}-{b}-{flag}"

    @signaturewrapper(reference)
    def fallback(*args, **kwargs):
        return args, kwargs

    wrapped_signature = inspect.signature(fallback)
    assert wrapped_signature == inspect.signature(reference)

    result = fallback(1, "two", flag=False)
    assert result == ((1, "two"), {"flag": False})


def test_signaturewrapper_preserves_metadata():
    def reference(a: int) -> str:
        """Reference documentation."""
        return str(a)

    @signaturewrapper(reference)
    def fallback(a):
        """fallback docstring."""
        return str(a)

    assert fallback.__name__ == reference.__name__
    assert fallback.__doc__ == reference.__doc__


def test_saveproperty_registration_blocks_override():
    class SecureBase(NoOverrideMixin):
        def __init__(self):
            self._value = 0

        @saveproperty
        def value(self):
            return self._value

    assert "value" in SecureBase.__save_properties__
    assert isinstance(SecureBase.__save_properties__["value"], saveproperty)

    class Child(SecureBase):
        pass

    child = Child()
    child._value = 42
    assert child.value == 42

    with pytest.raises(TypeError) as excinfo:

        class BadChild(SecureBase):
            @property
            def value(self):
                return -1

    assert "saveproperty 'value'" in str(excinfo.value)


def test_savemethod_registration_blocks_override_and_binds():
    call_log = []

    class SecureBase(NoOverrideMixin):
        @savemethod
        def compute(self, number: int):
            call_log.append(number)
            return number + 1

    descriptor = SecureBase.__save_methods__["compute"]
    assert descriptor.name == "compute"
    assert SecureBase.compute is descriptor

    instance = SecureBase()
    assert instance.compute(5) == 6
    assert call_log == [5]

    with pytest.raises(TypeError) as excinfo:

        class BadChild(SecureBase):
            def compute(self, number: int):
                return number * 2

    assert "savemethod 'compute'" in str(excinfo.value)
