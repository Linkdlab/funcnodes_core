from types import ModuleType
import unittest
import funcnodes_core as fnc
from importlib import reload
import funcnodes_basic


class TestSetup(unittest.TestCase):
    def test_setup(self):
        fnc.AVAILABLE_MODULES.clear()
        self.assertNotIn("funcnodes_basic", fnc.AVAILABLE_MODULES)
        fnc.setup()
        self.assertIn("funcnodes_basic", fnc.AVAILABLE_MODULES)
        fnc.setup()
        self.assertIn("funcnodes_basic", fnc.AVAILABLE_MODULES)

    def test_reload(self):
        fnc.setup()
        self.assertIn("funcnodes_basic", fnc.AVAILABLE_MODULES)
        module = fnc.AVAILABLE_MODULES["funcnodes_basic"].module
        self.assertIsNotNone(module)
        self.assertIsInstance(module, ModuleType)
        print(module)
        _ = funcnodes_basic.lists.list_length()
        reload(module)
        _ = funcnodes_basic.lists.list_length()
        reload(module)
