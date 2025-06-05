import unittest
from unittest.mock import Mock
from funcnodes_core import (
    NodeInput,
    NodeOutput,
    NodeConnectionError,
    MultipleConnectionsError,
)
import json
from funcnodes_core.io import raise_allow_connections, NodeAlreadyDefinedError, NoValue

import funcnodes_core as fn

fn.config.set_in_test(fail_on_warnings=[DeprecationWarning])


class TestNodeIO(unittest.TestCase):
    def setUp(self):
        self.input_1 = NodeInput(id="input1")
        self.output_1 = NodeOutput(id="output1")
        self.input_2 = NodeInput(id="input2")
        self.output_2 = NodeOutput(id="output2")

    def test_create_node_io(self):
        self.assertEqual(self.input_1.name, "input1")
        self.assertEqual(self.output_1.name, "output1")

    def test_connections(self):
        self.assertEqual(len(self.output_1.connections), 0)
        self.assertEqual(self.output_1.connections, self.output_1._connected)

    def test_json(self):
        serialized_input = self.input_1._repr_json_()
        self.assertEqual(
            serialized_input,
            {
                "name": "input1",
                "id": "input1",
                "is_input": True,
                "type": "Any",
                "node": None,
                "render_options": {},
                "value_options": {},
                "connected": False,
                "does_trigger": True,
                "full_id": None,
                "default": "<NoValue>",
                "required": True,
                "hidden": False,
                "emit_value_set": True,
            },
        )

        self.assertEqual(json.loads(json.dumps(serialized_input)), serialized_input)

    def test_full_ser(self):
        serialized_input = self.input_1.full_serialize(with_value=True)
        self.assertEqual(
            serialized_input,
            {
                "name": "input1",
                "id": "input1",
                "is_input": True,
                "type": "Any",
                "node": None,
                "value": NoValue,
                "render_options": {},
                "value_options": {},
                "connected": False,
                "does_trigger": True,
                "full_id": None,
                "default": NoValue,
                "required": True,
                "hidden": False,
                "emit_value_set": True,
            },
        )

    def test_serialize_node_io(self):
        serialized_input = self.input_1.serialize()
        self.assertEqual(
            serialized_input,
            {
                "id": "input1",
                "is_input": True,
                "type": "Any",
                "value": NoValue,
                "emit_value_set": True,
            },
        )
        serialized_output = self.output_1.serialize()
        self.assertEqual(
            serialized_output,
            {
                "type": "Any",
                "id": "output1",
                "is_input": False,
                "value": NoValue,
                "emit_value_set": True,
            },
        )

    def test_connect_input_to_output(self):
        self.input_1.connect(self.output_1)
        self.assertIn(self.output_1, self.input_1.connections)
        self.assertIn(self.input_1, self.output_1.connections)

    def test_connect_output_to_input(self):
        self.output_1.connect(self.input_1)
        self.assertIn(self.input_1, self.output_1.connections)
        self.assertIn(self.output_1, self.input_1.connections)

    def test_connection_exceptions(self):
        with self.assertRaises(NodeConnectionError):
            self.output_1.connect(self.output_2)

    def test_multiple_connections_error(self):
        self.input_1.connect(self.output_1)
        with self.assertRaises(MultipleConnectionsError):
            self.input_1.connect(self.output_2)

    def test_allow_multiple_connections(self):
        self.input_1._allow_multiple = True
        self.input_1.connect(self.output_1)
        self.input_1.connect(self.output_2)  # Should not raise an exception
        self.assertEqual(len(self.input_1.connections), 2)

    def test_connect_same_multiple_times(self):
        self.input_1.connect(self.output_1)
        self.input_1.connect(self.output_1)
        self.assertEqual(len(self.input_1.connections), 1)

    def test_disconnect(self):
        self.input_1.connect(self.output_1)
        self.input_1.disconnect(self.output_1)
        self.assertNotIn(self.output_1, self.input_1.connections)
        self.assertNotIn(self.input_1, self.output_1.connections)

        self.input_1.connect(self.output_1)
        self.input_1.d(self.output_1)
        self.assertNotIn(self.output_1, self.input_1.connections)
        self.assertNotIn(self.input_1, self.output_1.connections)

    def test_disconnect_all(self):
        self.output_1.connect(self.input_1)
        self.output_1.connect(self.input_2)
        self.output_1.disconnect()
        self.assertEqual(len(self.output_1.connections), 0)
        self.assertEqual(len(self.input_1.connections), 0)
        self.assertEqual(len(self.input_2.connections), 0)

    def test_input_forward(self):
        self.input_1.connect(self.output_1)

        self.output_1.set_value(123)

        self.assertEqual(self.input_1.value, 123)
        self.input_1.connect(self.input_2)
        self.assertEqual(self.input_2.value, 123)

        self.output_1.set_value(456)
        self.assertEqual(self.input_1.value, 456)
        self.assertEqual(self.input_2.value, 456)

    def test_set_value(self):
        test_value = 123
        self.input_1.value = test_value
        self.assertEqual(self.input_1.value, test_value)

    def test_connect_with_replace(self):
        self.input_1.connect(self.output_1)
        self.input_1.connect(self.output_2, replace=True)
        self.assertEqual(len(self.input_1.connections), 1)
        self.assertEqual(len(self.output_1.connections), 0)
        self.assertEqual(len(self.output_2.connections), 1)

    def test_set_node(self):
        node = Mock()
        self.input_1.node = node
        self.assertEqual(self.input_1.node, node)

    def test_double_set_node(self):
        node = Mock()
        self.input_1.node = node
        self.assertEqual(self.input_1.node, node)
        self.input_1.node = (
            node  # should not raise an exception since it's the same node
        )
        self.assertEqual(self.input_1.node, node)

        node2 = Mock()

        with self.assertRaises(NodeAlreadyDefinedError):
            self.input_1.node = node2

    def test_trigger_input(self):
        # mock with a trigger functan that returs the input
        node = Mock(trigger=Mock())

        self.input_1.value = 123
        stack = self.input_1.trigger()
        self.assertEqual(len(stack), 0)

        self.input_1.node = node

        ts = Mock()
        self.input_1.trigger(triggerstack=ts)

        node.trigger.assert_called_once_with(triggerstack=ts)

    def test_trigger_output(self):
        node = Mock(trigger=Mock(), inputs=dict())
        self.assertEqual(len(self.output_1.trigger()), 0)
        self.output_1.node = node
        self.input_1.node = node
        self.output_1.value = 123
        self.input_1.connect(self.output_1)

        ts = Mock()
        self.output_1.trigger(triggerstack=ts)

        node.trigger.assert_called_once_with(triggerstack=ts)

    def test_reset_default_on_connect(self):
        self.input_1.default = 123
        self.assertEqual(self.input_1.value, 123)
        self.input_1.connect(self.output_1)
        self.assertEqual(self.input_1.value, NoValue)
        self.assertEqual(self.input_1.default, NoValue)
        self.output_1.value = 456
        self.assertEqual(self.input_1.value, 456)

    def test_input_default_factory(self):
        class TestNode(fn.Node):
            node_id = "testnode"
            ip = NodeInput[int](default=NodeInput.DefaultFactory(lambda ip: 123))

            async def func(self, ip: int):
                pass

        ip = TestNode().inputs["ip"]
        self.assertTrue(hasattr(ip._default, "_is_default_factory"))
        self.assertEqual(ip.default, 123, ip._default)
        self.assertEqual(ip.value, 123)


class RaiseAllowConnectionsTest(unittest.TestCase):
    def setUp(self):
        self.ip1 = NodeInput(name="ip1")
        self.ip2 = NodeInput(name="ip2")
        self.op1 = NodeOutput(name="op1")
        self.op2 = NodeOutput(name="op2")

    def test_ip2ip(self):
        with self.assertRaises(NodeConnectionError):
            raise_allow_connections(self.ip1, self.ip2)

    def test_op2op(self):
        with self.assertRaises(NodeConnectionError):
            raise_allow_connections(self.op1, self.op2)

    def test_ip2op(self):
        raise_allow_connections(self.ip1, self.op1)

    def test_double_connect(self):
        self.ip1.connect(self.op1)
        raise_allow_connections(self.ip1, self.op1)

    def test_forbidden_multiple_connections(self):
        self.ip1.connect(self.op1)
        # by default inputs do not allow multiple connections
        with self.assertRaises(MultipleConnectionsError):
            raise_allow_connections(self.ip1, self.op2)
        with self.assertRaises(MultipleConnectionsError):
            raise_allow_connections(self.op2, self.ip1)

        # but outputs do
        raise_allow_connections(self.ip2, self.op1)
        raise_allow_connections(self.op1, self.ip2)


def return_no_value():
    return NoValue


class TestNoValue(unittest.TestCase):
    def test_no_singleton(self):
        n1 = NoValue
        n2 = NoValue
        self.assertIs(n1, n2)

        self.assertIs(NoValue, NoValue.__class__())
        self.assertIs(NoValue, return_no_value())

    def test_singeton_threadsafe(self):
        import threading

        res = []

        def set_no_value():
            res.append(return_no_value())

        nv_thread = threading.Thread(target=set_no_value)
        nv_thread.start()
        nv_thread.join()

        self.assertIs(res[0], NoValue)

    def test_singleton_multiprocess(self):
        import multiprocessing

        pool = multiprocessing.Pool(1)

        res = pool.apply(return_no_value)
        self.assertIs(res, NoValue)

    def test_singleton_picklesave(self):
        import pickle

        pickled = pickle.dumps(NoValue)
        unpickled = pickle.loads(pickled)
        self.assertIs(NoValue, unpickled)


class TestIOExamples(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        fn.config.set_in_test(fail_on_warnings=[DeprecationWarning])

    async def test_io1(self):
        class IOModNode(fn.Node):
            node_id = "iomodnode"
            a = fn.NodeInput(
                value_options={"min": 0, "max": 1, "step": 0.1}, default=0.5, type=float
            )

            b = fn.NodeInput(
                render_options={"type": "color"}, type=str, default="#ff0000"
            )

            c = fn.NodeInput(
                value_options={"options": ["a", "b", "c"]}, default="a", type=str
            )
            d = fn.NodeInput(
                value_options={
                    "options": {
                        "type": "enum",
                        "keys": ["full", "empty"],
                        "values": [1, 0],
                    }
                }
            )

            async def func(self, a: float, b: str, c: str, d: float):
                self.inputs["a"].set_value(float(d), does_trigger=False)

        node = IOModNode()

        self.assertEqual(node.inputs["a"].value, 0.5)
        self.assertFalse(node.ready(), node.ready_state())
        node.inputs["d"].value = 1
        self.assertTrue(node.ready(), node.ready_state())
        await node

        self.assertEqual(node.inputs["a"].value, 1)
