import pytest

from funcnodes_core import (
    GroupInputNode,
    GroupOutputNode,
    Node,
    NodeInput,
    NodeOutput,
)


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
