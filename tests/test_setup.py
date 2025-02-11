from types import ModuleType
import unittest
import funcnodes_core as fnc
from importlib import reload

import funcnodes_core as fn

fn.config.set_in_test(fail_on_warnings=[DeprecationWarning])
import funcnodes_basic  # noqa # pylint: disable=unused-import


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
        nodespace = fnc.NodeSpace()
        nodespace.lib.add_shelf(funcnodes_basic.NODE_SHELF)
        _ = funcnodes_basic.lists.list_length()
        reload(module)
        reload(funcnodes_basic)
        reload(funcnodes_basic.lists)

        print(list(fnc.lib.SHELFE_REGISTRY.keys()))
