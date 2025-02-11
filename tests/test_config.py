import unittest
import os
import warnings


class TestDecorator(unittest.IsolatedAsyncioTestCase):
    def test_in_node_test_varaset(self):
        import funcnodes_core as fn

        fn.config.set_in_test()

        self.assertTrue(fn.config.get_in_test())
        self.assertTrue(fn.config._IN_NODE_TEST)
        pid = os.getpid()
        self.assertEqual(
            os.path.basename(fn.config._BASE_CONFIG_DIR), "funcnodes_test" + f"_{pid}"
        )

    def test_config_access_deprecation(self):
        import funcnodes_core as fn

        # make sure a deprecation warning is issued when accessing the deprecated attribute
        with self.assertWarns(DeprecationWarning):
            fn.config.CONFIG
        # make sure a deprecation warning is issued when accessing the deprecated attribute
        with self.assertWarns(DeprecationWarning):
            fn.config.CONFIG_DIR

        with self.assertWarns(DeprecationWarning):
            fn.config.BASE_CONFIG_DIR

    def test_no_deprecation_warning(self):
        # make sure no deprecation warning is issued when accessing the new attribute
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)

    def test_config_not_laoded(self):
        import funcnodes_core as fn

        fn.config.set_in_test()
        self.assertTrue(
            fn.config._CONFIG_CHANGED,
            f"Expected {fn.config._CONFIG_CHANGED} to be True",
        )
