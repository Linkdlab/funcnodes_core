from __future__ import annotations

from typing import Any, cast

from .io import NodeInput, NodeInputSerialization, NodeOutput, NodeOutputSerialization
from .node import Node, NodeJSON


def _serialized_io_with_id(io_id: str, data: dict[str, Any]) -> dict[str, Any]:
    serialized = dict(data)
    serialized.setdefault("id", io_id)
    return serialized


class GroupInputNode(Node):
    """Internal gateway that exposes group public inputs as internal outputs."""

    node_id = "funcnodes_core.group.input"
    node_name = "Group Input"
    default_trigger_on_create = False

    async def func(self, **kwargs):
        return None

    def add_gateway_output(self, **kwargs: Any) -> NodeOutput:
        output = NodeOutput(**kwargs)
        self.add_output(output)
        return output

    def remove_gateway_output(self, output: str | NodeOutput) -> NodeOutput:
        if isinstance(output, str):
            output = self.get_output(output)
        output.disconnect()
        self.remove_output(output)
        return output

    def deserialize(self, data: NodeJSON):
        for io_id, io_data in data.get("io", {}).items():
            serialized = _serialized_io_with_id(io_id, io_data)
            if serialized.get("is_input"):
                continue
            if io_id not in self.outputs:
                self.add_output(
                    NodeOutput.from_serialized_nodeio(
                        cast(NodeOutputSerialization, serialized)
                    )
                )

        super().deserialize(data)


class GroupOutputNode(Node):
    """Internal gateway that exposes group public outputs as internal inputs."""

    node_id = "funcnodes_core.group.output"
    node_name = "Group Output"
    default_trigger_on_create = False

    async def func(self, **kwargs):
        return None

    def add_gateway_input(self, **kwargs: Any) -> NodeInput:
        input_ = NodeInput(**kwargs)
        self.add_input(input_)
        return input_

    def remove_gateway_input(self, input_: str | NodeInput) -> NodeInput:
        if isinstance(input_, str):
            input_ = self.get_input(input_)
        input_.disconnect()
        self.remove_input(input_)
        return input_

    def deserialize(self, data: NodeJSON):
        for io_id, io_data in data.get("io", {}).items():
            serialized = _serialized_io_with_id(io_id, io_data)
            if not serialized.get("is_input"):
                continue
            if io_id not in self.inputs:
                self.add_input(
                    NodeInput.from_serialized_nodeio(
                        cast(NodeInputSerialization, serialized)
                    )
                )

        super().deserialize(data)
