"""Executable node group primitives.

This module contains the first building blocks for Blender-style node groups.
The current implementation is intentionally limited to the in-memory structure
needed by the early grouping milestones:

- `GroupInputNode` is the internal gateway for values entering a group.
- `GroupOutputNode` is the internal gateway for values leaving a group.
- `GroupNode` is a normal `Node` with its own internal `NodeSpace` and exactly
  one input gateway plus one output gateway.

The actual trigger barrier, boundary value mirroring, full group serialization,
and node-selection grouping APIs are intentionally handled by later milestones.
The classes here should therefore stay additive and should not change global
connection behavior in `NodeIO`.
"""

from __future__ import annotations

from typing import Any, Iterator, Literal, TYPE_CHECKING, cast
from typing_extensions import NotRequired, TypedDict

from .io import NodeInput, NodeInputSerialization, NodeOutput, NodeOutputSerialization
from .node import Node, NodeJSON

if TYPE_CHECKING:
    from .nodespace import NodeSpace


class GroupInterfaceBinding(TypedDict):
    """Persistent in-memory description of one public group boundary IO.

    A binding records the relationship between one public IO on the outer
    `GroupNode` and the matching gateway IO inside the group's internal
    `NodeSpace`.

    For `direction == "input"`:

    - `public_io` names a `GroupNode.inputs` entry.
    - `gateway_node` is the `GroupInputNode` UUID.
    - `gateway_io` names a `GroupInputNode.outputs` entry.

    For `direction == "output"`:

    - `public_io` names a `GroupNode.outputs` entry.
    - `gateway_node` is the `GroupOutputNode` UUID.
    - `gateway_io` names a `GroupOutputNode.inputs` entry.

    The remaining fields mirror normal `NodeIO` metadata so later milestones can
    serialize, reconstruct, or update the boundary without deriving everything
    from live IO objects.
    """

    id: str
    direction: Literal["input", "output"]
    public_io: str
    gateway_node: str
    gateway_io: str
    name: str
    type: Any
    description: NotRequired[str]
    required: NotRequired[bool]
    default: NotRequired[Any]
    allow_multiple: NotRequired[bool]
    does_trigger: NotRequired[bool]
    render_options: NotRequired[dict[str, Any]]
    value_options: NotRequired[dict[str, Any]]


_COMMON_IO_KEYS = (
    "id",
    "uuid",
    "name",
    "type",
    "description",
    "allow_multiple",
    "render_options",
    "value_options",
    "hidden",
    "emit_value_set",
)
_INPUT_ONLY_IO_KEYS = ("required", "default", "does_trigger")


def _serialized_io_with_id(io_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of serialized IO data with an explicit `id`.

    `Node.serialize(drop=True)` stores IO data in a dictionary keyed by IO id and
    omits the nested `"id"` field. Dynamic gateway deserialization needs the id
    value in the nested payload before it can call `NodeInput`/`NodeOutput`
    reconstruction helpers.
    """

    serialized = dict(data)
    serialized.setdefault("id", io_id)
    return serialized


def _select_kwargs(data: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    """Copy only supported keyword arguments from `data`.

    Boundary creation receives kwargs that may include both input-only and
    output-compatible options. This helper keeps object construction explicit so
    `NodeInput` does not receive output-only data and `NodeOutput` does not
    receive input-only data.
    """

    return {key: data[key] for key in keys if key in data}


def _boundary_id(kind: str, kwargs: dict[str, Any]) -> str:
    """Resolve and validate the stable boundary id from creation kwargs.

    The public API accepts both `id` and `uuid` because `NodeIO` itself accepts
    both names. The returned value is always a string and is used as the binding
    key as well as the default public/gateway IO id.
    """

    boundary_id = kwargs.get("id", kwargs.get("uuid"))
    if not boundary_id:
        raise ValueError(f"Group {kind} id is required")
    return str(boundary_id)


def _binding_from_io(
    *,
    boundary_id: str,
    direction: Literal["input", "output"],
    public_io: NodeInput | NodeOutput,
    gateway_node: Node,
    gateway_io: NodeInput | NodeOutput,
) -> GroupInterfaceBinding:
    """Create a binding record from live public and gateway IO objects.

    The binding is generated after the IO objects are successfully attached, so
    it stores their final UUIDs. Metadata is copied from the public IO because
    that is the surface external users interact with.
    """

    serialized = public_io.serialize(drop=False)
    binding = GroupInterfaceBinding(
        id=boundary_id,
        direction=direction,
        public_io=public_io.uuid,
        gateway_node=gateway_node.uuid,
        gateway_io=gateway_io.uuid,
        name=serialized.get("name", boundary_id),
        type=serialized.get("type", "Any"),
    )
    for key in (
        "description",
        "required",
        "default",
        "allow_multiple",
        "does_trigger",
        "render_options",
        "value_options",
    ):
        if key in serialized:
            binding[key] = serialized[key]  # type: ignore[literal-required]
    return binding


class GroupInputNode(Node):
    """Internal gateway that exposes group public inputs as internal outputs.

    A public input on `GroupNode` is represented inside the group by a matching
    output on this node. Later trigger/value mirroring will copy public input
    values to these outputs, allowing normal output-to-input propagation inside
    the internal graph.
    """

    node_id = "funcnodes_core.group.input"
    node_name = "Group Input"
    default_trigger_on_create = False

    async def func(self, **kwargs):
        """No-op trigger function.

        Gateway nodes are structural nodes. They exist so normal FuncNodes IO
        and edge logic can be reused at group boundaries, not to compute values
        themselves.
        """

        return None

    def add_gateway_output(self, **kwargs: Any) -> NodeOutput:
        """Create and attach one dynamic internal output.

        Args:
            **kwargs: Standard `NodeOutput` constructor options. The caller must
                provide an id or uuid that is unique among this gateway's
                outputs.

        Returns:
            The newly attached `NodeOutput`.

        Raises:
            ValueError: Raised by `Node.add_output` if the output id already
                exists.
        """

        output = NodeOutput(**kwargs)
        self.add_output(output)
        return output

    def remove_gateway_output(self, output: str | NodeOutput) -> NodeOutput:
        """Disconnect and remove a dynamic internal output.

        Args:
            output: Either the output id or the live `NodeOutput` instance.

        Returns:
            The removed `NodeOutput`. It is disconnected and no longer belongs
            to this gateway's output mapping.
        """

        if isinstance(output, str):
            output = self.get_output(output)
        output.disconnect()
        self.remove_output(output)
        return output

    def deserialize(self, data: NodeJSON):
        """Deserialize this gateway and recreate dynamic outputs first.

        Base `Node.deserialize` can only apply serialized IO data to IO objects
        that already exist. This override scans the serialized node IO mapping,
        recreates any output entries that are not present yet, and then lets the
        base class apply common node and IO state.
        """

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
    """Internal gateway that exposes group public outputs as internal inputs.

    A public output on `GroupNode` is represented inside the group by a matching
    input on this node. Later trigger/value mirroring will read these inputs
    after the internal graph settles and copy them to the public outputs.
    """

    node_id = "funcnodes_core.group.output"
    node_name = "Group Output"
    default_trigger_on_create = False

    async def func(self, **kwargs):
        """No-op trigger function.

        The output gateway is a structural collection of inputs. It does not
        compute values by itself.
        """

        return None

    def add_gateway_input(self, **kwargs: Any) -> NodeInput:
        """Create and attach one dynamic internal input.

        Args:
            **kwargs: Standard `NodeInput` constructor options. The caller must
                provide an id or uuid that is unique among this gateway's
                inputs.

        Returns:
            The newly attached `NodeInput`.

        Raises:
            ValueError: Raised by `Node.add_input` if the input id already
                exists.
        """

        input_ = NodeInput(**kwargs)
        self.add_input(input_)
        return input_

    def remove_gateway_input(self, input_: str | NodeInput) -> NodeInput:
        """Disconnect and remove a dynamic internal input.

        Args:
            input_: Either the input id or the live `NodeInput` instance.

        Returns:
            The removed `NodeInput`. It is disconnected and no longer belongs to
            this gateway's input mapping.
        """

        if isinstance(input_, str):
            input_ = self.get_input(input_)
        input_.disconnect()
        self.remove_input(input_)
        return input_

    def deserialize(self, data: NodeJSON):
        """Deserialize this gateway and recreate dynamic inputs first.

        Base `Node.deserialize` can only apply serialized IO data to IO objects
        that already exist. This override scans the serialized node IO mapping,
        recreates any input entries that are not present yet, and then lets the
        base class apply common node and IO state.
        """

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
    """Executable group node skeleton.

    `GroupNode` is the public node that will eventually behave as a complete
    executable node group. In the current milestone it owns the structural
    pieces only:

    - an internal `NodeSpace`
    - one `GroupInputNode`
    - one `GroupOutputNode`
    - in-memory boundary bindings
    - dynamic public boundary IO add/remove APIs

    It deliberately does not yet mirror values across the boundary, wait for
    internal triggers, serialize its internal graph, or provide group-from-
    selection APIs. Those behaviors are implemented in later milestones.
    """

    node_id = "funcnodes_core.group"
    node_name = "Group"
    default_trigger_on_create = False

    def __init__(self, *args: Any, **kwargs: Any):
        """Initialize the group and its private internal node space.

        Args:
            *args: Positional arguments forwarded to `Node`.
            **kwargs: Keyword arguments forwarded to `Node`.

        The internal nodespace is created after base node initialization so the
        outer `GroupNode` remains a normal `Node` from the perspective of any
        parent `NodeSpace`. Gateway nodes are added immediately and their UUIDs
        are stored so later serialization can refer to stable ids.
        """

        super().__init__(*args, **kwargs)

        from .nodespace import NodeSpace

        self._input_bindings: dict[str, GroupInterfaceBinding] = {}
        self._output_bindings: dict[str, GroupInterfaceBinding] = {}
        self._inner_nodespace = NodeSpace()
        self._group_input_node = GroupInputNode()
        self._group_output_node = GroupOutputNode()
        self._inner_nodespace.add_node_instance(self._group_input_node)
        self._inner_nodespace.add_node_instance(self._group_output_node)
        self._group_input_node_uuid = self._group_input_node.uuid
        self._group_output_node_uuid = self._group_output_node.uuid

    @property
    def inner_nodespace(self) -> "NodeSpace":
        """The private node space that contains the group's internal graph."""

        return self._inner_nodespace

    @property
    def group_input_node_uuid(self) -> str:
        """UUID of the internal `GroupInputNode` gateway."""

        return self._group_input_node_uuid

    @property
    def group_output_node_uuid(self) -> str:
        """UUID of the internal `GroupOutputNode` gateway."""

        return self._group_output_node_uuid

    @property
    def group_input_node(self) -> GroupInputNode:
        """Return the internal input gateway by UUID.

        The lookup goes through `inner_nodespace` instead of returning the cached
        object directly so future deserialization can replace the internal
        nodespace while preserving this accessor contract.
        """

        node = self.inner_nodespace.get_node_by_id(self.group_input_node_uuid)
        if not isinstance(node, GroupInputNode):
            raise TypeError("Configured group input gateway is not a GroupInputNode")
        return node

    @property
    def group_output_node(self) -> GroupOutputNode:
        """Return the internal output gateway by UUID.

        The lookup goes through `inner_nodespace` instead of returning the cached
        object directly so future deserialization can replace the internal
        nodespace while preserving this accessor contract.
        """

        node = self.inner_nodespace.get_node_by_id(self.group_output_node_uuid)
        if not isinstance(node, GroupOutputNode):
            raise TypeError("Configured group output gateway is not a GroupOutputNode")
        return node

    @property
    def input_bindings(self) -> dict[str, GroupInterfaceBinding]:
        """Boundary bindings for public group inputs.

        Keys are stable boundary ids. Values map outer `GroupNode.inputs` to
        inner `GroupInputNode.outputs`.
        """

        return self._input_bindings

    @property
    def output_bindings(self) -> dict[str, GroupInterfaceBinding]:
        """Boundary bindings for public group outputs.

        Keys are stable boundary ids. Values map outer `GroupNode.outputs` to
        inner `GroupOutputNode.inputs`.
        """

        return self._output_bindings

    def add_group_input(self, **kwargs: Any) -> NodeInput:
        """Create one public input boundary.

        This creates two IO objects:

        - a public `NodeInput` on the outer `GroupNode`
        - a matching `NodeOutput` on the internal `GroupInputNode`

        Args:
            **kwargs: Standard `NodeInput` constructor options. `id` or `uuid`
                is required and becomes the stable boundary id. Input-only
                options such as `required`, `default`, and `does_trigger` are
                applied only to the public input.

        Returns:
            The newly attached public `NodeInput`.

        Raises:
            ValueError: If the boundary id is missing or already used.
        """

        boundary_id = _boundary_id("input", kwargs)
        if boundary_id in self._input_bindings or boundary_id in self.inputs:
            raise ValueError(f"Group input '{boundary_id}' already exists")
        if boundary_id in self.group_input_node.outputs:
            raise ValueError(f"Group input gateway '{boundary_id}' already exists")

        common_kwargs = _select_kwargs(kwargs, _COMMON_IO_KEYS)
        common_kwargs.setdefault("id", boundary_id)
        public_input = NodeInput(
            **common_kwargs,
            **_select_kwargs(kwargs, _INPUT_ONLY_IO_KEYS),
        )
        gateway_output = self.group_input_node.add_gateway_output(**common_kwargs)
        try:
            self.add_input(public_input)
        except Exception:
            self.group_input_node.remove_gateway_output(gateway_output)
            raise

        self._input_bindings[boundary_id] = _binding_from_io(
            boundary_id=boundary_id,
            direction="input",
            public_io=public_input,
            gateway_node=self.group_input_node,
            gateway_io=gateway_output,
        )
        return public_input

    def remove_group_input(self, boundary_id: str) -> tuple[NodeInput, NodeOutput]:
        """Remove one public input boundary.

        Both the public input and the matching internal gateway output are
        disconnected before removal.

        Args:
            boundary_id: Stable id of the input boundary to remove.

        Returns:
            A tuple of `(removed_public_input, removed_gateway_output)`.

        Raises:
            ValueError: If no input binding exists for `boundary_id`.
        """

        if boundary_id not in self._input_bindings:
            raise ValueError(f"Group input '{boundary_id}' not found")
        binding = self._input_bindings.pop(boundary_id)
        public_input = self.get_input(binding["public_io"])
        gateway_output = self.group_input_node.get_output(binding["gateway_io"])

        public_input.disconnect()
        self.remove_input(public_input)
        self.group_input_node.remove_gateway_output(gateway_output)
        return public_input, gateway_output

    def add_group_output(self, **kwargs: Any) -> NodeOutput:
        """Create one public output boundary.

        This creates two IO objects:

        - a public `NodeOutput` on the outer `GroupNode`
        - a matching `NodeInput` on the internal `GroupOutputNode`

        Args:
            **kwargs: Standard boundary IO options. `id` or `uuid` is required
                and becomes the stable boundary id. Input-only options such as
                `required`, `default`, and `does_trigger` are applied only to the
                internal gateway input.

        Returns:
            The newly attached public `NodeOutput`.

        Raises:
            ValueError: If the boundary id is missing or already used.
        """

        boundary_id = _boundary_id("output", kwargs)
        if boundary_id in self._output_bindings or boundary_id in self.outputs:
            raise ValueError(f"Group output '{boundary_id}' already exists")
        if boundary_id in self.group_output_node.inputs:
            raise ValueError(f"Group output gateway '{boundary_id}' already exists")

        common_kwargs = _select_kwargs(kwargs, _COMMON_IO_KEYS)
        common_kwargs.setdefault("id", boundary_id)
        public_output = NodeOutput(**common_kwargs)
        gateway_input = self.group_output_node.add_gateway_input(
            **common_kwargs,
            **_select_kwargs(kwargs, _INPUT_ONLY_IO_KEYS),
        )
        try:
            self.add_output(public_output)
        except Exception:
            self.group_output_node.remove_gateway_input(gateway_input)
            raise

        self._output_bindings[boundary_id] = _binding_from_io(
            boundary_id=boundary_id,
            direction="output",
            public_io=public_output,
            gateway_node=self.group_output_node,
            gateway_io=gateway_input,
        )
        return public_output

    def remove_group_output(self, boundary_id: str) -> tuple[NodeOutput, NodeInput]:
        """Remove one public output boundary.

        Both the public output and the matching internal gateway input are
        disconnected before removal.

        Args:
            boundary_id: Stable id of the output boundary to remove.

        Returns:
            A tuple of `(removed_public_output, removed_gateway_input)`.

        Raises:
            ValueError: If no output binding exists for `boundary_id`.
        """

        if boundary_id not in self._output_bindings:
            raise ValueError(f"Group output '{boundary_id}' not found")
        binding = self._output_bindings.pop(boundary_id)
        public_output = self.get_output(binding["public_io"])
        gateway_input = self.group_output_node.get_input(binding["gateway_io"])

        public_output.disconnect()
        self.remove_output(public_output)
        self.group_output_node.remove_gateway_input(gateway_input)
        return public_output, gateway_input

    def iter_inner_nodes(self, include_gateways: bool = False) -> Iterator[Node]:
        """Iterate over nodes in the internal graph.

        Args:
            include_gateways: When `False`, skip the structural gateway nodes
                and return only user/internal graph nodes. When `True`, include
                the `GroupInputNode` and `GroupOutputNode` in nodespace order.

        Yields:
            Internal `Node` instances.
        """

        gateway_ids = {self.group_input_node_uuid, self.group_output_node_uuid}
        for node in self.inner_nodespace.nodes:
            if not include_gateways and node.uuid in gateway_ids:
                continue
            yield node

    async def func(self, **kwargs):
        """No-op group trigger function for the skeleton milestone.

        Later milestones will replace this with boundary value mirroring and an
        internal trigger barrier. Returning `None` for now keeps the group as a
        valid `Node` without changing execution semantics.
        """

        return None
