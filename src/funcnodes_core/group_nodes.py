from __future__ import annotations

from typing import Any, Iterator, TYPE_CHECKING, cast

from .io import NodeInput, NodeInputSerialization, NodeOutput, NodeOutputSerialization
from .node import Node, NodeJSON

if TYPE_CHECKING:
    from .nodespace import NodeSpace


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


class GroupNode(Node):
    """Executable group skeleton with an internal nodespace and gateway nodes."""

    node_id = "funcnodes_core.group"
    node_name = "Group"
    default_trigger_on_create = False

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)

        from .nodespace import NodeSpace

        self._inner_nodespace = NodeSpace()
        self._group_input_node = GroupInputNode()
        self._group_output_node = GroupOutputNode()
        self._inner_nodespace.add_node_instance(self._group_input_node)
        self._inner_nodespace.add_node_instance(self._group_output_node)
        self._group_input_node_uuid = self._group_input_node.uuid
        self._group_output_node_uuid = self._group_output_node.uuid

    @property
    def inner_nodespace(self) -> "NodeSpace":
        return self._inner_nodespace

    @property
    def group_input_node_uuid(self) -> str:
        return self._group_input_node_uuid

    @property
    def group_output_node_uuid(self) -> str:
        return self._group_output_node_uuid

    @property
    def group_input_node(self) -> GroupInputNode:
        node = self.inner_nodespace.get_node_by_id(self.group_input_node_uuid)
        if not isinstance(node, GroupInputNode):
            raise TypeError("Configured group input gateway is not a GroupInputNode")
        return node

    @property
    def group_output_node(self) -> GroupOutputNode:
        node = self.inner_nodespace.get_node_by_id(self.group_output_node_uuid)
        if not isinstance(node, GroupOutputNode):
            raise TypeError("Configured group output gateway is not a GroupOutputNode")
        return node

    def iter_inner_nodes(self, include_gateways: bool = False) -> Iterator[Node]:
        gateway_ids = {self.group_input_node_uuid, self.group_output_node_uuid}
        for node in self.inner_nodespace.nodes:
            if not include_gateways and node.uuid in gateway_ids:
                continue
            yield node

    async def func(self, **kwargs):
        return None
