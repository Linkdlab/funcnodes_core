import funcnodes_core as fn
import unittest
import os


class TestDecorator(unittest.IsolatedAsyncioTestCase):
    def test_in_node_test_varaset(self):
        fn.config.IN_NODE_TEST = True

        self.assertTrue(fn.config.IN_NODE_TEST)
        self.assertTrue(fn.config.This.IN_NODE_TEST)
        self.assertEqual(os.path.basename(fn.config.BASE_CONFIG_DIR), "funcnodes_test")
