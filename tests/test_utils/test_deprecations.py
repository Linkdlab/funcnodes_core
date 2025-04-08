from unittest import TestCase
from funcnodes_core.utils.deprecations import (
    FuncNodesDeprecationWarning,
    path_module_attribute_to_getter,
    method_deprecated_decorator,
)
import warnings


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
        self.assertEqual(cm.filename.lower(), __file__.lower(), cm.warning)

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

        self.assertEqual(cm.filename.lower(), __file__.lower(), cm.warnings[0])

        class Pseudomodle:
            @method_deprecated_decorator("new_method")
            def method(self):
                return 1

        pseudomodule = Pseudomodle()
        with self.assertWarns(FuncNodesDeprecationWarning) as cm:
            self.assertEqual(pseudomodule.method(), 1)

        self.assertEqual(cm.filename, __file__, cm.warnings[0])
