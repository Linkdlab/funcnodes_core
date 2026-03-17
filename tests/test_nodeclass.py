import gc
from unittest.mock import patch

import pytest

import funcnodes_core as fn
from funcnodes_core.node import (
    AsyncEventManager,
    InTriggerError,
    Node,
    NodeIdAlreadyExistsError,
    NodeInput,
    NodeKeyError,
    NodeMeta,
    NodeOutput,
    TriggerStack,
    get_nodeclass,
    register_node,
)
from pytest_funcnodes import funcnodes_test


class DummyNode(Node):
    node_id = "dummy_node"
    input = NodeInput(
        id="input",
        type=int,
        default=1,
        description="i1",
        value_options={"options": [1, 2]},
    )
    output = NodeOutput(id="output", type=int)
    default_render_options = {"data": {"src": "input"}}

    async def func(self, input: int) -> int:  # noqa: A003 - matching fn signature
        self.outputs["output"].value = input
        return input


def make_counter_node(node_id: str, *, does_trigger: bool = True):
    resolved_node_id = node_id

    class CounterNode(Node):
        node_id = resolved_node_id
        value = NodeInput(id="value", type=int, does_trigger=does_trigger)
        output = NodeOutput(id="output", type=int)

        def __init__(self, *args, **kwargs):
            super().__init__(*args, pretrigger_delay=0.0, **kwargs)
            self.call_count = 0

        async def func(self, value: int):
            self.call_count += 1
            self.outputs["output"].value = value

    return CounterNode


@funcnodes_test
async def test_nodeclass_initialization():
    with pytest.raises(TypeError):
        Node()  # type: ignore

    test_node = DummyNode()
    assert isinstance(test_node.asynceventmanager, AsyncEventManager)
    assert test_node.uuid is not None
    assert not test_node._reset_inputs_on_trigger


@funcnodes_test
async def test_node_add_input_output():
    test_node = DummyNode()
    test_input = NodeInput(id="test_input")
    test_output = NodeOutput(id="test_output")
    test_node.add_input(test_input)
    test_node.add_output(test_output)

    assert "test_input" in test_node.inputs
    assert "test_output" in test_node.outputs
    assert len(test_node.inputs) == 3  # includes _triggerinput
    assert len(test_node.outputs) == 3  # includes _triggeroutput


@funcnodes_test
async def test_node_ready_to_trigger():
    test_node = DummyNode()
    await test_node
    assert test_node.ready_to_trigger()


@funcnodes_test
async def test_node_trigger():
    test_node = DummyNode()
    await test_node
    trigger_stack = test_node.trigger()

    assert isinstance(trigger_stack, TriggerStack)
    assert test_node.inputs["input"].value == 1
    assert test_node.outputs["output"].value == 1


@funcnodes_test
async def test_node_trigger_when_already_triggered_raises_error():
    test_node = DummyNode()
    with pytest.raises(InTriggerError):
        test_node.trigger()
        test_node.trigger()


@funcnodes_test
async def test_double_node_id():
    class DoubleNode1(Node):
        node_id = "dummy_node"

        async def func(self):
            return None

    with pytest.raises(NodeIdAlreadyExistsError) as exc:

        class DoubleNode2(Node):
            node_id = "dummy_node"

            async def func(self):
                return None

    assert str(exc.value).startswith("Node with id 'dummy_node' already exists")


@funcnodes_test
async def test_await_trigger():
    test_node = DummyNode()
    await test_node.await_trigger()
    test_node.trigger()
    await test_node.await_trigger()


@funcnodes_test
async def test_trigger_stack():
    test_node = DummyNode()
    await test_node
    trigger_stack = test_node.trigger()
    await trigger_stack
    assert trigger_stack.done()

    new_trigger_stack = test_node.trigger(triggerstack=trigger_stack)
    assert trigger_stack is new_trigger_stack
    assert not trigger_stack.done()


@funcnodes_test
async def test_forwarded_input_respects_target_does_trigger_flag():
    ForwardSourceNode = make_counter_node("forward_source_node_test")
    ForwardTargetNode = make_counter_node(
        "forward_target_node_test", does_trigger=False
    )

    node_a = ForwardSourceNode()
    node_b = ForwardTargetNode()
    node_a.inputs["value"].connect(node_b.inputs["value"])

    node_a.inputs["value"].value = 42
    await fn.run_until_complete(node_a, node_b)

    assert node_a.inputs["value"].value == 42
    assert node_b.inputs["value"].value == 42
    assert node_a.call_count == 1
    assert node_b.call_count == 0
    assert node_a.outputs["output"].value == 42
    assert node_b.outputs["output"].value is fn.NoValue


@funcnodes_test
async def test_forwarded_input_uses_target_flag_when_source_flag_disables_self_only():
    ForwardSourceNode = make_counter_node(
        "forward_source_node_no_trigger_test", does_trigger=False
    )
    ForwardTargetNode = make_counter_node("forward_target_node_allow_test")

    node_a = ForwardSourceNode()
    node_b = ForwardTargetNode()
    node_a.inputs["value"].connect(node_b.inputs["value"])

    node_a.inputs["value"].value = 42
    await fn.run_until_complete(node_a, node_b)

    assert node_a.call_count == 0
    assert node_b.call_count == 1
    assert node_b.inputs["value"].value == 42
    assert node_b.outputs["output"].value == 42


@funcnodes_test
async def test_forwarded_input_propagates_explicit_false_downstream():
    ForwardSourceNode = make_counter_node("forward_source_node_explicit_false_test")
    ForwardTargetNode = make_counter_node("forward_target_node_explicit_false_test")

    node_a = ForwardSourceNode()
    node_b = ForwardTargetNode()
    node_a.inputs["value"].connect(node_b.inputs["value"])

    node_a.inputs["value"].set_value(42, does_trigger=False)
    await fn.run_until_complete(node_a, node_b)

    assert node_a.call_count == 0
    assert node_b.call_count == 0
    assert node_b.inputs["value"].value == 42
    assert node_b.outputs["output"].value is fn.NoValue


@funcnodes_test
async def test_forwarded_input_triggers_downstream_when_both_allow_triggering():
    ForwardSourceNode = make_counter_node("forward_source_node_trigger_test")
    ForwardTargetNode = make_counter_node("forward_target_node_trigger_test")

    node_a = ForwardSourceNode()
    node_b = ForwardTargetNode()
    node_a.inputs["value"].connect(node_b.inputs["value"])

    node_a.inputs["value"].value = 42
    await fn.run_until_complete(node_a, node_b)

    assert node_a.call_count == 1
    assert node_b.call_count == 1
    assert node_b.outputs["output"].value == 42


@funcnodes_test
async def test_forward_chain_skips_non_triggering_middle_node_but_triggers_downstream():
    NodeA = make_counter_node("forward_chain_source_node_test")
    NodeB = make_counter_node("forward_chain_middle_node_test", does_trigger=False)
    NodeC = make_counter_node("forward_chain_target_node_test")

    node_a = NodeA()
    node_b = NodeB()
    node_c = NodeC()

    node_a.inputs["value"].connect(node_b.inputs["value"])
    node_b.inputs["value"].connect(node_c.inputs["value"])

    node_a.inputs["value"].value = 42
    await fn.run_until_complete(node_a, node_b, node_c)

    assert node_a.call_count == 1
    assert node_b.call_count == 0
    assert node_c.call_count == 1
    assert node_b.inputs["value"].value == 42
    assert node_c.inputs["value"].value == 42
    assert node_b.outputs["output"].value is fn.NoValue
    assert node_c.outputs["output"].value == 42


@funcnodes_test
async def test_output_set_value_respects_explicit_false_downstream():
    SourceNode = make_counter_node("output_source_node_explicit_false_test")
    TargetNode = make_counter_node("output_target_node_explicit_false_test")

    node_a = SourceNode()
    node_b = TargetNode()
    node_a.outputs["output"].connect(node_b.inputs["value"])

    node_a.outputs["output"].set_value(42, does_trigger=False)
    await fn.run_until_complete(node_a, node_b)

    assert node_b.inputs["value"].value == 42
    assert node_b.call_count == 0
    assert node_b.outputs["output"].value is fn.NoValue


@funcnodes_test
async def test_output_set_value_uses_target_does_trigger_flag_when_unspecified():
    SourceNode = make_counter_node("output_source_node_unspecified_test")
    TargetNode = make_counter_node(
        "output_target_node_unspecified_false_test", does_trigger=False
    )

    node_a = SourceNode()
    node_b = TargetNode()
    node_a.outputs["output"].connect(node_b.inputs["value"])

    node_a.outputs["output"].set_value(42)
    await fn.run_until_complete(node_a, node_b)

    assert node_b.inputs["value"].value == 42
    assert node_b.call_count == 0
    assert node_b.outputs["output"].value is fn.NoValue


@funcnodes_test
async def test_output_set_value_triggers_target_when_target_allows_triggering():
    SourceNode = make_counter_node("output_source_node_trigger_test")
    TargetNode = make_counter_node("output_target_node_trigger_test")

    node_a = SourceNode()
    node_b = TargetNode()
    node_a.outputs["output"].connect(node_b.inputs["value"])

    node_a.outputs["output"].set_value(42)
    await fn.run_until_complete(node_a, node_b)

    assert node_b.inputs["value"].value == 42
    assert node_b.call_count == 1
    assert node_b.outputs["output"].value == 42


@funcnodes_test
def test_nodeclass_string():
    test_node = DummyNode(uuid="test_uuid")
    assert str(test_node) == "DummyNode(test_uuid)"


@funcnodes_test
def test_node_status():
    test_node = DummyNode()
    assert test_node.status() == {
        "ready": True,
        "in_trigger": False,
        "requests_trigger": False,
        "inputs": {
            "input": {
                "connected": False,
                "has_node": True,
                "has_value": True,
                "ready": True,
                "required": True,
            },
            "_triggerinput": {
                "connected": False,
                "has_node": True,
                "has_value": True,
                "ready": True,
                "required": False,
            },
        },
        "outputs": {
            "output": {
                "connected": False,
                "has_node": True,
                "has_value": False,
                "ready": True,
            },
            "_triggeroutput": {
                "connected": False,
                "has_node": True,
                "has_value": False,
                "ready": True,
            },
        },
        "ready_state": {
            "inputs": {
                "_triggerinput": {"node": True, "value": True},
                "input": {"node": True, "value": True},
            },
        },
    }


@funcnodes_test
def test_get_unregistered_nodeclass():
    with pytest.raises(NodeKeyError):
        get_nodeclass("unregistered_nodeclass")


@funcnodes_test
async def test_delete_node():
    gc.collect()
    gc.set_debug(gc.DEBUG_LEAK)

    test_node = DummyNode()
    await test_node
    target_id = id(test_node)
    del test_node
    gc.collect()
    garbage = gc.garbage
    gc.set_debug(0)

    if any(id(obj) == target_id for obj in garbage):
        raise ValueError("Node not deleted")


@funcnodes_test
async def test_init_subclass_state():
    assert len(DummyNode._class_io_serialized) == 4


@funcnodes_test
async def test_serialize_nodeclass():
    expected = {
        "description": None,
        "inputs": [
            {
                "description": "i1",
                "type": "int",
                "uuid": "input",
            }
        ],
        "node_id": "dummy_node",
        "node_name": "DummyNode",
        "outputs": [
            {
                "description": None,
                "type": "int",
                "uuid": "output",
            }
        ],
    }
    assert DummyNode.serialize_cls() == expected


@funcnodes_test
async def test_serialize_node():
    node_a = DummyNode(uuid="aa")
    node_b = DummyNode(uuid="bb")

    node_a.inputs["input"].value = 2
    node_b.inputs["input"].connect(node_a.outputs["output"])
    await node_a
    await node_b

    assert node_b.outputs["output"].value == 2

    expected = {
        "id": "aa",
        "io": {
            "input": {"is_input": True, "value": 2, "emit_value_set": True},
            "output": {"is_input": False, "value": 2, "emit_value_set": True},
        },
        "name": "DummyNode(aa)",
        "node_id": "dummy_node",
        "node_name": "DummyNode",
        "render_options": {"data": {"src": "input"}},
    }
    assert node_a.serialize() == expected

    expected["id"] = "bb"
    expected["name"] = "DummyNode(bb)"
    assert node_b.serialize() == expected


@funcnodes_test
def test_input_name_differs_id():
    class TestNode(Node):
        node_id = "test_node_diff_id"
        ip1 = NodeInput(id="input")

        async def func(self, input: int) -> int:  # noqa: A003
            return input

    instance = TestNode()
    assert "input" in instance.inputs


@funcnodes_test
def test_input_no_id():
    class TestNode(Node):
        node_id = "test_node_no_id"
        ip1 = NodeInput()

        async def func(self, ip1: int) -> int:  # noqa: A003
            return ip1

    instance = TestNode()
    assert "ip1" in instance.inputs

    ip = instance.inputs["ip1"]
    assert ip.uuid == "ip1"
    assert ip.name == "ip1"


@funcnodes_test
def test_saveprop_overwrite():
    with pytest.raises(TypeError):

        class TestNode(Node):
            node_id = "test_node_prop_overwrite"
            name = NodeInput()

            async def func(self, name: int) -> int:  # noqa: A003
                return name


@funcnodes_test
def test_savemethod_overwrite():
    with pytest.raises(TypeError):

        class TestNode(Node):
            node_id = "test_node_method_overwrite"

            def __call__(self):
                return None

            async def func(self) -> int:
                return 0


@funcnodes_test
def test_custom_property():
    class TestNode(Node):
        node_id = "test_node_custom_property"

        async def func(self) -> int:
            return 1

    instance = TestNode()
    instance.set_property("pos", (1, 2))
    assert instance.get_property("pos") == (1, 2)
    serialized = instance.serialize()
    assert serialized["properties"] == {"pos": (1, 2)}

    other = TestNode()
    assert other.get_property("pos") is None
    other.deserialize(serialized)
    assert other.get_property("pos") == (1, 2)


@funcnodes_test
async def test_init_call():
    @fn.NodeDecorator("init_call")
    def func(a: int) -> int:
        return a * 10

    dictout = await func.initialize_and_call(a=2, return_dict=True)
    assert dictout == {
        "out": 20,
        "_triggeroutput": dictout["_triggeroutput"],
    }
    assert await func.initialize_and_call(a=2) == 20
    assert await func.initialize_and_call(raise_ready=False) is fn.NoValue

    with pytest.raises(fn.exceptions.NodeReadyError):
        await func.initialize_and_call()


@funcnodes_test
def test_meta_creates_new_class_correctly():
    with patch("funcnodes_core.node.register_node") as mock_register_node:

        class BaseNodeClass(Node):
            node_id = "meta_base"

            async def func(self, *args, **kwargs):  # noqa: ANN002, ANN003
                return None

        NewNodeClass = NodeMeta(
            "NewNodeClass", (BaseNodeClass,), {"node_id": "new_node_class"}
        )
        assert issubclass(NewNodeClass, BaseNodeClass)
        mock_register_node.assert_called_with(NewNodeClass)


@funcnodes_test
def test_meta_raises_type_error_for_non_nodeclass_subclass():
    with pytest.raises(TypeError):

        class InvalidNodeClass(metaclass=NodeMeta):
            pass


@funcnodes_test
def test_meta_catches_name_error_for_base_nodeclass_definition():
    with pytest.raises(TypeError):

        class NodeClass(metaclass=NodeMeta):
            pass


@funcnodes_test
def test_meta_registers_class():
    class BaseNodeClass(Node):
        node_id = "test_meta_registers_class"

        async def func(self):
            return None

    with patch(
        "funcnodes_core.node.register_node", side_effect=register_node
    ) as mock_register_node:
        NewNodeClass = NodeMeta(
            "NewNodeClass", (BaseNodeClass,), {"node_id": "new_node_class_meta"}
        )
        assert issubclass(NewNodeClass, BaseNodeClass)
        mock_register_node.assert_called_once_with(NewNodeClass)


@funcnodes_test
def test_meta_raises_error_on_duplicate_registration():
    class BaseNodeClass(Node):
        node_id = "test_meta_duplicate"

        async def func(self):
            return None

    with pytest.raises(NodeIdAlreadyExistsError):

        class AnotherBaseNodeClass(BaseNodeClass):
            node_id = "test_meta_duplicate"
