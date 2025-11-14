import sys
import warnings
from pathlib import Path
from types import ModuleType
from unittest import TestCase

from funcnodes_core.utils.deprecations import (
    FuncNodesDeprecationWarning,
    method_deprecated_decorator,
    path_module_attribute_to_getter,
)


class TestDeprecations(TestCase):
    def test_path_module_attribute_to_getter(self):
        # dont fail on warning
        warnings.simplefilter("always", FuncNodesDeprecationWarning)

        class Pseudomodle:
            def __init__(self):
                self._CONFIG = 1

            def get_config(self):
                return self._CONFIG

            def set_config(self, value):
                self._CONFIG = value

        pseudomodule = Pseudomodle()
        path_module_attribute_to_getter(
            pseudomodule, "CONFIG", pseudomodule.get_config, pseudomodule.set_config
        )

        with self.assertWarns(FuncNodesDeprecationWarning) as cm:
            self.assertEqual(pseudomodule.CONFIG, 1)

        print("W:", cm.warnings[0])
        self.assertEqual(Path(cm.filename).name, Path(__file__).name, cm.warning)

    def test_method_deprecated_decorator(self):
        # dont fail on warning
        warnings.simplefilter("always", FuncNodesDeprecationWarning)

        class Pseudomodle:
            @method_deprecated_decorator()
            def method(self):
                return 1

        pseudomodule = Pseudomodle()
        with self.assertWarns(FuncNodesDeprecationWarning) as cm:
            self.assertEqual(pseudomodule.method(), 1)

        self.assertEqual(Path(cm.filename).name, Path(__file__).name, cm.warnings[0])

    def test_path_module_attribute_to_getter_handles_module_name_and_setter(self):
        warnings.simplefilter("always", FuncNodesDeprecationWarning)

        module_name = "funcnodes_core.tests.fake_deprecations_module"
        fake_module = ModuleType(module_name)
        fake_module._value = 5

        def get_value():
            return fake_module._value

        def set_value(value):
            fake_module._value = value
            return value

        fake_module.get_value = get_value
        fake_module.set_value = set_value
        sys.modules[module_name] = fake_module

        try:
            path_module_attribute_to_getter(
                module_name, "VALUE", fake_module.get_value, fake_module.set_value
            )

            with self.assertWarns(FuncNodesDeprecationWarning):
                self.assertEqual(fake_module.VALUE, 5)

            with self.assertWarns(FuncNodesDeprecationWarning):
                fake_module.VALUE = 42

            self.assertEqual(fake_module.get_value(), 42)
        finally:
            sys.modules.pop(module_name, None)

    def test_path_module_attribute_to_getter_without_setter_returns_default(self):
        warnings.simplefilter("always", FuncNodesDeprecationWarning)

        class FakeModule:
            def __init__(self):
                self._value = 11
                self.calls = 0

            def get_value(self):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("boom")
                return self._value

        fake_module = FakeModule()

        default_value = path_module_attribute_to_getter(
            fake_module,
            "VALUE",
            fake_module.get_value,
            None,
            intital_default=-1,
        )

        self.assertEqual(default_value, -1)

        with self.assertWarns(FuncNodesDeprecationWarning):
            self.assertEqual(fake_module.VALUE, 11)

        with self.assertRaises(AttributeError):
            fake_module.VALUE = 99

        class Pseudomodle:
            @method_deprecated_decorator("new_method")
            def method(self):
                return 1

        pseudomodule = Pseudomodle()
        with self.assertWarns(FuncNodesDeprecationWarning) as cm:
            self.assertEqual(pseudomodule.method(), 1)

        self.assertEqual(Path(cm.filename).name, Path(__file__).name, cm.warnings[0])
