import asyncio

import pytest

from funcnodes_core import (
    GroupNode,
    GroupInputNode,
    GroupOutputNode,
    Node,
    NodeInput,
    NodeOutput,
    NodeSpace,
    NoValue,
)
from funcnodes_core.exceptions import InTriggerError


class GatewaySinkNode(Node):
    node_id = "test_group_nodes_sink"
    node_name = "Gateway Sink"
    default_trigger_on_create = False
    value = NodeInput(id="value", type=int, default=0)

    async def func(self, value: int) -> int:
        return value


class GatewaySourceNode(Node):
    node_id = "test_group_nodes_source"
    node_name = "Gateway Source"
    default_trigger_on_create = False
    value = NodeOutput(id="value", type=int)

    async def func(self) -> int:
        return 1


class SlowDoubleNode(Node):
    node_id = "test_group_nodes_slow_double"
    node_name = "Slow Double"
    default_trigger_on_create = False
    value = NodeInput(id="value", type=int)
    result = NodeOutput(id="result", type=int)

    async def func(self, value: int) -> int:
        await asyncio.sleep(0.05)
        result = value * 2
        self.outputs["result"].value = result
        return result


def test_gateway_nodes_are_public_node_classes_without_auto_trigger():
    input_gateway = GroupInputNode()
    output_gateway = GroupOutputNode()

    assert input_gateway.node_id == "funcnodes_core.group.input"
    assert output_gateway.node_id == "funcnodes_core.group.output"
    assert input_gateway.default_trigger_on_create is False
    assert output_gateway.default_trigger_on_create is False
    assert input_gateway.in_trigger is False
    assert output_gateway.in_trigger is False


def test_group_input_node_adds_and_removes_dynamic_outputs():
    gateway = GroupInputNode()

    output = gateway.add_gateway_output(
        id="threshold",
        name="Threshold",
        type=int,
        description="Public threshold input",
    )

    assert output is gateway.outputs["threshold"]
    assert output.is_input() is False
    assert output.name == "Threshold"
    assert output.serialize()["description"] == "Public threshold input"
    assert output.node is gateway

    with pytest.raises(ValueError, match="already exists"):
        gateway.add_gateway_output(id="threshold")

    removed = gateway.remove_gateway_output("threshold")

    assert removed is output
    assert "threshold" not in gateway.outputs


def test_group_input_node_removal_disconnects_dynamic_output():
    gateway = GroupInputNode()
    output = gateway.add_gateway_output(id="value", type=int)
    sink = GatewaySinkNode()
    output.connect(sink.inputs["value"])

    gateway.remove_gateway_output("value")

    assert output.connections == []
    assert sink.inputs["value"].connections == []


def test_group_output_node_adds_and_removes_dynamic_inputs():
    gateway = GroupOutputNode()

    input_ = gateway.add_gateway_input(
        id="result",
        name="Result",
        type=int,
        description="Public result output",
        required=False,
        does_trigger=False,
    )

    assert input_ is gateway.inputs["result"]
    assert input_.is_input() is True
    assert input_.name == "Result"
    assert input_.serialize()["description"] == "Public result output"
    assert input_.required is False
    assert input_.does_trigger is False
    assert input_.node is gateway

    with pytest.raises(ValueError, match="already exists"):
        gateway.add_gateway_input(id="result")

    removed = gateway.remove_gateway_input("result")

    assert removed is input_
    assert "result" not in gateway.inputs


def test_group_output_node_removal_disconnects_dynamic_input():
    gateway = GroupOutputNode()
    input_ = gateway.add_gateway_input(id="value", type=int)
    source = GatewaySourceNode()
    source.outputs["value"].connect(input_)

    gateway.remove_gateway_input("value")

    assert input_.connections == []
    assert source.outputs["value"].connections == []


def test_gateway_nodes_roundtrip_dynamic_io_serialization():
    input_gateway = GroupInputNode()
    input_gateway.add_gateway_output(
        id="external_value",
        name="External Value",
        type=int,
        description="Input boundary",
        allow_multiple=False,
    )
    output_gateway = GroupOutputNode()
    output_gateway.add_gateway_input(
        id="external_result",
        name="External Result",
        type=float,
        description="Output boundary",
        required=False,
        does_trigger=False,
    )

    input_serialized = input_gateway.serialize(drop=False)
    output_serialized = output_gateway.serialize(drop=False)

    restored_input_gateway = GroupInputNode()
    restored_output_gateway = GroupOutputNode()
    restored_input_gateway.deserialize(input_serialized)
    restored_output_gateway.deserialize(output_serialized)

    restored_output = restored_input_gateway.outputs["external_value"]
    restored_input = restored_output_gateway.inputs["external_result"]
    assert restored_output.name == "External Value"
    assert restored_output.serialize()["description"] == "Input boundary"
    assert restored_output.is_input() is False
    assert restored_input.name == "External Result"
    assert restored_input.serialize()["description"] == "Output boundary"
    assert restored_input.required is False
    assert restored_input.does_trigger is False


def test_group_node_is_node_with_internal_gateway_nodes():
    group = GroupNode()

    assert isinstance(group, Node)
    assert group.node_id == "funcnodes_core.group"
    assert group.node_name == "Group"
    assert group.default_trigger_on_create is False
    assert group.in_trigger is False

    assert isinstance(group.inner_nodespace, NodeSpace)
    assert isinstance(group.group_input_node, GroupInputNode)
    assert isinstance(group.group_output_node, GroupOutputNode)
    assert group.group_input_node is group.inner_nodespace.get_node_by_id(
        group.group_input_node_uuid
    )
    assert group.group_output_node is group.inner_nodespace.get_node_by_id(
        group.group_output_node_uuid
    )


def test_group_node_starts_with_only_normal_hidden_trigger_io():
    group = GroupNode()

    assert set(group.inputs) == {"_triggerinput"}
    assert set(group.outputs) == {"_triggeroutput"}
    assert group.inputs["_triggerinput"].hidden is True
    assert group.outputs["_triggeroutput"].hidden is True


def test_group_node_inner_iteration_can_include_or_skip_gateways():
    group = GroupNode()

    assert list(group.iter_inner_nodes()) == []

    inner_nodes = list(group.iter_inner_nodes(include_gateways=True))
    assert inner_nodes == [group.group_input_node, group.group_output_node]


def test_group_node_can_be_added_to_outer_nodespace_normally():
    space = NodeSpace()
    group = GroupNode()

    added = space.add_node_instance(group)

    assert added is group
    assert space.get_node_by_id(group.uuid) is group
    assert group.nodespace is space
    assert group.group_input_node.nodespace is group.inner_nodespace
    assert group.group_output_node.nodespace is group.inner_nodespace


def test_group_node_add_group_input_creates_public_input_gateway_output_and_binding():
    group = GroupNode()

    public_input = group.add_group_input(
        id="threshold",
        name="Threshold",
        type=int,
        description="Minimum value",
        required=False,
        default=3,
        does_trigger=False,
    )

    gateway_output = group.group_input_node.outputs["threshold"]
    binding = group.input_bindings["threshold"]

    assert public_input is group.inputs["threshold"]
    assert public_input.is_input() is True
    assert public_input.name == "Threshold"
    assert public_input.default == 3
    assert public_input.required is False
    assert public_input.does_trigger is False
    assert gateway_output.is_input() is False
    assert gateway_output.name == "Threshold"
    assert gateway_output.serialize()["description"] == "Minimum value"
    assert binding["id"] == "threshold"
    assert binding["direction"] == "input"
    assert binding["public_io"] == "threshold"
    assert binding["gateway_node"] == group.group_input_node_uuid
    assert binding["gateway_io"] == "threshold"


def test_group_node_add_group_output_creates_public_output_gateway_input_and_binding():
    group = GroupNode()

    public_output = group.add_group_output(
        id="result",
        name="Result",
        type=float,
        description="Computed value",
        required=False,
        does_trigger=False,
    )

    gateway_input = group.group_output_node.inputs["result"]
    binding = group.output_bindings["result"]

    assert public_output is group.outputs["result"]
    assert public_output.is_input() is False
    assert public_output.name == "Result"
    assert public_output.serialize()["description"] == "Computed value"
    assert gateway_input.is_input() is True
    assert gateway_input.name == "Result"
    assert gateway_input.required is False
    assert gateway_input.does_trigger is False
    assert binding["id"] == "result"
    assert binding["direction"] == "output"
    assert binding["public_io"] == "result"
    assert binding["gateway_node"] == group.group_output_node_uuid
    assert binding["gateway_io"] == "result"


def test_group_node_remove_group_input_disconnects_public_and_gateway_io():
    group = GroupNode()
    public_input = group.add_group_input(id="value", type=int)
    gateway_output = group.group_input_node.outputs["value"]
    external_source = GatewaySourceNode()
    internal_sink = GatewaySinkNode()
    external_source.outputs["value"].connect(public_input)
    gateway_output.connect(internal_sink.inputs["value"])

    removed_public, removed_gateway = group.remove_group_input("value")

    assert removed_public is public_input
    assert removed_gateway is gateway_output
    assert "value" not in group.inputs
    assert "value" not in group.group_input_node.outputs
    assert "value" not in group.input_bindings
    assert external_source.outputs["value"].connections == []
    assert public_input.connections == []
    assert gateway_output.connections == []
    assert internal_sink.inputs["value"].connections == []


def test_group_node_remove_group_output_disconnects_public_and_gateway_io():
    group = GroupNode()
    public_output = group.add_group_output(id="value", type=int)
    gateway_input = group.group_output_node.inputs["value"]
    internal_source = GatewaySourceNode()
    external_sink = GatewaySinkNode()
    internal_source.outputs["value"].connect(gateway_input)
    public_output.connect(external_sink.inputs["value"])

    removed_public, removed_gateway = group.remove_group_output("value")

    assert removed_public is public_output
    assert removed_gateway is gateway_input
    assert "value" not in group.outputs
    assert "value" not in group.group_output_node.inputs
    assert "value" not in group.output_bindings
    assert internal_source.outputs["value"].connections == []
    assert gateway_input.connections == []
    assert public_output.connections == []
    assert external_sink.inputs["value"].connections == []


def test_group_node_rejects_duplicate_boundary_ids_without_partial_mutation():
    group = GroupNode()
    group.add_group_input(id="value", type=int)
    group.add_group_output(id="result", type=int)
    input_count = len(group.inputs)
    output_count = len(group.outputs)
    gateway_output_count = len(group.group_input_node.outputs)
    gateway_input_count = len(group.group_output_node.inputs)

    with pytest.raises(ValueError, match="Group input .* already exists"):
        group.add_group_input(id="value", type=float)
    with pytest.raises(ValueError, match="Group output .* already exists"):
        group.add_group_output(id="result", type=float)

    assert len(group.inputs) == input_count
    assert len(group.outputs) == output_count
    assert len(group.group_input_node.outputs) == gateway_output_count
    assert len(group.group_output_node.inputs) == gateway_input_count
    assert group.inputs["value"].serialize(drop=False)["type"] == "int"
    assert group.outputs["result"].serialize(drop=False)["type"] == "int"


def test_group_node_remove_missing_boundary_ids_raises_clear_error():
    group = GroupNode()

    with pytest.raises(ValueError, match="Group input .* not found"):
        group.remove_group_input("missing")
    with pytest.raises(ValueError, match="Group output .* not found"):
        group.remove_group_output("missing")


async def test_group_node_trigger_copies_public_inputs_to_gateway_outputs():
    group = GroupNode()
    group.add_group_input(id="value", type=int, does_trigger=False)
    internal_sink = GatewaySinkNode()
    group.inner_nodespace.add_node_instance(internal_sink)
    group.group_input_node.outputs["value"].connect(internal_sink.inputs["value"])
    group.inputs["value"].set_value(17, does_trigger=False)

    await group.trigger()

    assert group.group_input_node.outputs["value"].value == 17
    assert internal_sink.inputs["value"].value == 17


async def test_group_node_trigger_copies_gateway_inputs_to_public_outputs():
    group = GroupNode()
    public_output = group.add_group_output(
        id="result",
        type=int,
        required=False,
        does_trigger=False,
    )
    external_sink = GatewaySinkNode()
    public_output.connect(external_sink.inputs["value"])

    group.group_output_node.inputs["result"].set_value(23, does_trigger=False)

    assert public_output.value is NoValue
    assert external_sink.inputs["value"].value == 0

    await group.trigger()

    assert public_output.value == 23
    assert external_sink.inputs["value"].value == 23


async def test_group_node_trigger_skips_unset_gateway_outputs():
    group = GroupNode()
    public_output = group.add_group_output(
        id="optional",
        type=int,
        required=False,
        does_trigger=False,
    )

    await group.trigger()

    assert public_output.value is NoValue


async def test_group_node_trigger_waits_for_internal_async_nodes_before_output():
    group = GroupNode()
    group.add_group_input(id="value", type=int, does_trigger=False)
    public_output = group.add_group_output(
        id="result",
        type=int,
        required=False,
        does_trigger=False,
    )
    slow = SlowDoubleNode()
    group.inner_nodespace.add_node_instance(slow)
    group.group_input_node.outputs["value"].connect(slow.inputs["value"])
    slow.outputs["result"].connect(group.group_output_node.inputs["result"])
    group.inputs["value"].set_value(21, does_trigger=False)

    triggerstack = group.trigger()
    await asyncio.sleep(0.01)

    assert public_output.value is NoValue

    await triggerstack

    assert public_output.value == 42
    assert group.group_output_node.inputs["result"].value == 42


async def test_group_node_downstream_outputs_trigger_after_internal_completion():
    group = GroupNode()
    group.add_group_input(id="value", type=int, does_trigger=False)
    public_output = group.add_group_output(
        id="result",
        type=int,
        required=False,
        does_trigger=False,
    )
    slow = SlowDoubleNode()
    external_sink = GatewaySinkNode()
    group.inner_nodespace.add_node_instance(slow)
    group.group_input_node.outputs["value"].connect(slow.inputs["value"])
    slow.outputs["result"].connect(group.group_output_node.inputs["result"])
    public_output.connect(external_sink.inputs["value"])
    group.inputs["value"].set_value(10, does_trigger=False)

    triggerstack = group.trigger()
    await asyncio.sleep(0.01)

    assert external_sink.inputs["value"].value == 0

    await triggerstack

    assert external_sink.inputs["value"].value == 20


async def test_group_node_trigger_rejects_when_inner_node_is_active():
    group = GroupNode()
    slow = SlowDoubleNode()
    group.inner_nodespace.add_node_instance(slow)

    slow.inputs["value"].set_value(4)
    await asyncio.sleep(0.01)

    assert slow.in_trigger is True
    with pytest.raises(InTriggerError):
        group.trigger()

    await slow.wait_for_trigger_finish()


def test_group_node_serializes_versioned_group_payload():
    group = GroupNode()
    group.set_property("owner", "user")
    group.add_group_input(id="value", type=int, name="Value", does_trigger=False)
    group.add_group_output(
        id="result",
        type=int,
        name="Result",
        required=False,
        does_trigger=False,
    )
    slow = SlowDoubleNode()
    group.inner_nodespace.add_node_instance(slow)
    group.group_input_node.outputs["value"].connect(slow.inputs["value"])
    slow.outputs["result"].connect(group.group_output_node.inputs["result"])

    serialized = group.serialize()
    payload = serialized["properties"]["group"]

    assert serialized["properties"]["owner"] == "user"
    assert payload["version"] == 1
    assert payload["input_gateway_node"] == group.group_input_node_uuid
    assert payload["output_gateway_node"] == group.group_output_node_uuid
    assert payload["input_bindings"] == group.input_bindings
    assert payload["output_bindings"] == group.output_bindings
    assert [node["node_id"] for node in payload["inner_nodespace"]["nodes"]] == [
        "funcnodes_core.group.input",
        "funcnodes_core.group.output",
        "test_group_nodes_slow_double",
    ]
    assert payload["inner_nodespace"]["edges"] == [
        [group.group_input_node_uuid, "value", slow.uuid, "value"],
        [slow.uuid, "result", group.group_output_node_uuid, "result"],
    ]


async def test_group_node_deserializes_dynamic_io_bindings_and_internal_graph():
    group = GroupNode()
    group.set_property("owner", "user")
    group.add_group_input(id="value", type=int, name="Value", does_trigger=False)
    group.add_group_output(
        id="result",
        type=int,
        name="Result",
        required=False,
        does_trigger=False,
    )
    slow = SlowDoubleNode()
    group.inner_nodespace.add_node_instance(slow)
    group.group_input_node.outputs["value"].connect(slow.inputs["value"])
    slow.outputs["result"].connect(group.group_output_node.inputs["result"])
    serialized = group.serialize()

    restored = GroupNode()
    restored.deserialize(serialized)

    assert set(restored.inputs) == {"_triggerinput", "value"}
    assert set(restored.outputs) == {"_triggeroutput", "result"}
    assert restored.inputs["value"].name == "Value"
    assert restored.outputs["result"].name == "Result"
    assert restored.get_property("owner") == "user"
    assert restored.get_property("group") is None
    assert (
        restored.input_bindings
        == serialized["properties"]["group"]["input_bindings"]
    )
    assert (
        restored.output_bindings
        == serialized["properties"]["group"]["output_bindings"]
    )
    assert isinstance(restored.group_input_node, GroupInputNode)
    assert isinstance(restored.group_output_node, GroupOutputNode)
    assert len(list(restored.iter_inner_nodes())) == 1

    restored.inputs["value"].set_value(7, does_trigger=False)
    await restored.trigger()

    assert restored.outputs["result"].value == 14


def test_group_node_rejects_unsupported_group_payload_version():
    group = GroupNode()
    serialized = group.serialize()
    serialized["properties"]["group"]["version"] = 999

    with pytest.raises(ValueError, match="Unsupported group payload version"):
        GroupNode().deserialize(serialized)


async def test_nodespace_roundtrips_group_node_with_internal_graph():
    group = GroupNode()
    group.add_group_input(id="value", type=int, does_trigger=False)
    group.add_group_output(id="result", type=int, required=False, does_trigger=False)
    slow = SlowDoubleNode()
    group.inner_nodespace.add_node_instance(slow)
    group.group_input_node.outputs["value"].connect(slow.inputs["value"])
    slow.outputs["result"].connect(group.group_output_node.inputs["result"])
    space = NodeSpace()
    space.lib.add_node(GroupNode, "groups")
    space.add_node_instance(group)

    serialized = space.serialize()

    restored_space = NodeSpace()
    restored_space.lib.add_node(GroupNode, "groups")
    restored_space.deserialize(serialized)
    restored_group = restored_space.get_node_by_id(group.uuid)

    assert isinstance(restored_group, GroupNode)
    assert restored_group.input_bindings == group.input_bindings
    assert restored_group.output_bindings == group.output_bindings
    assert len(list(restored_group.iter_inner_nodes())) == 1

    restored_group.inputs["value"].set_value(9, does_trigger=False)
    await restored_group.trigger()

    assert restored_group.outputs["result"].value == 18
