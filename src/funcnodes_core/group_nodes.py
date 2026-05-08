"""Executable node group primitives.

This module contains the first building blocks for Blender-style node groups.
The implementation is intentionally additive: group nodes use normal `Node`,
`NodeIO`, `NodeSpace`, and edge behavior instead of special-casing global
connection logic.

- `GroupInputNode` is the internal gateway for values entering a group.
- `GroupOutputNode` is the internal gateway for values leaving a group.
- `GroupNode` is a normal `Node` with its own internal `NodeSpace`, exactly
  one input gateway plus one output gateway, and simple boundary value
  mirroring plus a trigger barrier.

The serialized representation stores the internal graph in a versioned payload
under the outer node's `properties["group"]` entry. User properties remain
ordinary node properties; deserialization strips the group payload before it
delegates to the base `Node` deserializer so the live property bag is not
polluted with implementation state.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Any, Iterator, Literal, TYPE_CHECKING, cast
from typing_extensions import NotRequired, TypedDict
from uuid import uuid4

from .exceptions import InTriggerError, NodeKeyError
from .io import (
    NoValue,
    NodeInput,
    NodeInputSerialization,
    NodeOutput,
    NodeOutputSerialization,
)
from .node import FullNodeJSON, Node, NodeJSON, NodeTriggerError, get_nodeclass
from .eventmanager import MessageInArgs

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


class GroupNodePayload(TypedDict):
    """Versioned serialized representation of a `GroupNode` internals.

    The payload is stored as one value inside the outer node serialization so a
    `GroupNode` can still round-trip through existing `NodeSpace` machinery.

    Attributes:
        version: Schema version for future migrations.
        inner_nodespace: Serialized private `NodeSpace`, including gateway
            nodes, user/internal nodes, edges, properties, and legacy groups.
        input_gateway_node: UUID of the one `GroupInputNode` inside
            `inner_nodespace`.
        output_gateway_node: UUID of the one `GroupOutputNode` inside
            `inner_nodespace`.
        input_bindings: Public-input boundary bindings keyed by stable boundary
            id.
        output_bindings: Public-output boundary bindings keyed by stable
            boundary id.
    """

    version: int
    inner_nodespace: dict[str, Any]
    input_gateway_node: str
    output_gateway_node: str
    input_bindings: dict[str, GroupInterfaceBinding]
    output_bindings: dict[str, GroupInterfaceBinding]


GROUP_NODE_PAYLOAD_VERSION = 1
GROUP_NODE_PROPERTY_KEY = "group"


class GroupRuntimeStatus(TypedDict):
    """Runtime status payload added under `GroupNode.status()["group"]`.

    The base `Node.status()` dictionary remains unchanged for all other nodes.
    `GroupNode` appends this nested payload so group-aware callers can inspect
    internal execution state without reaching into private attributes.
    """

    inner_node_count: int
    inner_busy: bool
    inner_triggering_nodes: list[str]
    gateway_nodes: dict[str, str]
    input_bindings: dict[str, GroupInterfaceBinding]
    output_bindings: dict[str, GroupInterfaceBinding]


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
    """Resolve or generate the stable boundary id from creation kwargs.

    The public API accepts both `id` and `uuid` because `NodeIO` itself accepts
    both names. When neither is supplied, a private-style UUID is generated so
    UI callers can create untyped boundaries without exposing implementation IDs.
    The returned value is always a string and is used as the binding key as well
    as the default public/gateway IO id.
    """

    boundary_id = kwargs.get("id", kwargs.get("uuid")) or f"_{uuid4().hex}"
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
        "allow_multiple",
        "render_options",
        "value_options",
    ):
        if key in serialized:
            binding[key] = serialized[key]  # type: ignore[literal-required]
    input_metadata_source = public_io if direction == "input" else gateway_io
    input_metadata = input_metadata_source.serialize(drop=False)
    for key in ("required", "default", "does_trigger"):
        if key in input_metadata:
            binding[key] = input_metadata[key]  # type: ignore[literal-required]
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

    def __init__(self, *args: Any, **kwargs: Any):
        """Initialize a structural input gateway without trigger IO ports.

        Gateway nodes are edited as group boundary surfaces. Keeping normal
        `_triggerinput`/`_triggeroutput` ports on them exposes meaningless
        handles in the frontend and makes boundary wiring ambiguous.
        """

        super().__init__(*args, **kwargs)
        self._remove_default_trigger_io()

    def _remove_default_trigger_io(self) -> None:
        """Remove inherited default trigger ports from this gateway instance."""

        for input_ in list(self._inputs):
            if input_.uuid == "_triggerinput":
                self.remove_input(input_)
        for output in list(self._outputs):
            if output.uuid == "_triggeroutput":
                self.remove_output(output)

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
            **kwargs: Standard `NodeOutput` constructor options. The id or uuid
                must be unique among this gateway's outputs when provided.

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
            if io_id in {"_triggerinput", "_triggeroutput"}:
                continue
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
        self._remove_default_trigger_io()


class GroupOutputNode(Node):
    """Internal gateway that exposes group public outputs as internal inputs.

    A public output on `GroupNode` is represented inside the group by a matching
    input on this node. Later trigger/value mirroring will read these inputs
    after the internal graph settles and copy them to the public outputs.
    """

    node_id = "funcnodes_core.group.output"
    node_name = "Group Output"
    default_trigger_on_create = False

    def __init__(self, *args: Any, **kwargs: Any):
        """Initialize a structural output gateway without trigger IO ports.

        The output gateway only represents public group outputs as inputs inside
        the group. Default trigger handles do not carry boundary values and
        should not appear as editable connection points.
        """

        super().__init__(*args, **kwargs)
        self._remove_default_trigger_io()

    def _remove_default_trigger_io(self) -> None:
        """Remove inherited default trigger ports from this gateway instance."""

        for input_ in list(self._inputs):
            if input_.uuid == "_triggerinput":
                self.remove_input(input_)
        for output in list(self._outputs):
            if output.uuid == "_triggeroutput":
                self.remove_output(output)

    async def func(self, **kwargs):
        """No-op trigger function.

        The output gateway is a structural collection of inputs. It does not
        compute values by itself.
        """

        return None

    def add_gateway_input(self, **kwargs: Any) -> NodeInput:
        """Create and attach one dynamic internal input.

        Args:
            **kwargs: Standard `NodeInput` constructor options. The id or uuid
                must be unique among this gateway's inputs when provided.

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
            if io_id in {"_triggerinput", "_triggeroutput"}:
                continue
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
        self._remove_default_trigger_io()


class GroupNode(Node):
    """Executable group node.

    `GroupNode` is the public node that behaves as one executable boundary
    around a private internal graph. It owns:

    - an internal `NodeSpace`
    - one `GroupInputNode`
    - one `GroupOutputNode`
    - in-memory boundary bindings
    - dynamic public boundary IO add/remove APIs
    - public input to gateway output mirroring on trigger
    - gateway input to public output mirroring on trigger
    - an internal trigger barrier
    - versioned serialization for the private graph and boundary bindings

    Node-selection grouping APIs are intentionally left for later milestones.
    """

    node_id = "funcnodes_core.group"
    node_name = "Group"
    default_trigger_on_create = False
    default_inner_trigger_settle_limit = 100

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
        self._inner_trigger_errors: list[Exception] = []
        self._queued_trigger_task: asyncio.Task | None = None
        self._inner_nodespace = NodeSpace()
        self._group_input_node = GroupInputNode()
        self._group_output_node = GroupOutputNode()
        self._inner_nodespace.add_node_instance(self._group_input_node)
        self._inner_nodespace.add_node_instance(self._group_output_node)
        self._group_input_node_uuid = self._group_input_node.uuid
        self._group_output_node_uuid = self._group_output_node.uuid
        self._attach_inner_nodespace_events()
        self.on("before_trigger", self._raise_if_inner_busy_before_trigger)

    def _attach_inner_nodespace_events(self) -> None:
        """Subscribe this group to its private nodespace event stream.

        The internal `NodeSpace` already re-emits node events as nodespace-level
        events. Subscribing to its wildcard stream lets the outer `GroupNode`
        provide namespaced debug events such as `inner_node_trigger_error`
        without adding listeners to every inner node individually.
        """

        self._inner_nodespace.off("*", self._on_inner_nodespace_event)
        self._inner_nodespace.on("*", self._on_inner_nodespace_event)

    def _on_inner_nodespace_event(
        self, event: str, src: "NodeSpace", **data: Any
    ) -> None:
        """Re-emit one internal nodespace event from the outer group.

        Args:
            event: Original internal event name emitted by the private
                `NodeSpace`.
            src: Private nodespace that emitted the event. It is accepted to
                match wildcard listener signatures and intentionally not
                forwarded as the public event source.
            **data: Original event payload, for example node UUIDs or trigger
                errors.

        The namespaced event keeps the original payload and adds
        `inner_event`. A generic `inner_event` emission is also sent so callers
        can subscribe once and inspect all inner activity.
        """

        payload = dict(data)
        if "node" in payload:
            payload["inner_node"] = payload.pop("node")
        payload["inner_event"] = event
        self.emit(f"inner_{event}", MessageInArgs(src=self, **payload))
        self.emit("inner_event", MessageInArgs(src=self, **payload))
        if event == "node_trigger_error" and "error" in payload:
            self._inner_trigger_errors.append(payload["error"])
        if event in {"triggerdone", "node_trigger_error"}:
            self._schedule_queued_trigger()

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

    def group_runtime_status(self) -> GroupRuntimeStatus:
        """Return group-specific runtime and boundary introspection data.

        Returns:
            A JSON-compatible status payload that describes the private graph
            size, whether internal work is active or queued, which inner nodes
            are currently busy, gateway UUIDs, and deep-copied boundary binding
            dictionaries.
        """

        inner_nodes = list(self.iter_inner_nodes())
        triggering_nodes = [
            node.uuid for node in self._inner_trigger_nodes() if node.in_trigger_soon
        ]
        return GroupRuntimeStatus(
            inner_node_count=len(inner_nodes),
            inner_busy=not self._inner_idle(),
            inner_triggering_nodes=triggering_nodes,
            gateway_nodes={
                "input": self.group_input_node_uuid,
                "output": self.group_output_node_uuid,
            },
            input_bindings=deepcopy(self.input_bindings),
            output_bindings=deepcopy(self.output_bindings),
        )

    def status(self) -> dict[str, Any]:
        """Return normal node status plus a group-specific `group` section.

        The base status keys are preserved unchanged. Group-aware consumers can
        inspect the additional nested payload while existing consumers that only
        know normal `Node.status()` can continue to read the usual keys.
        """

        status = cast(dict[str, Any], super().status())
        status["group"] = self.group_runtime_status()
        return status

    def _emit_boundary_io_event(
        self,
        *,
        event: str,
        direction: Literal["input", "output"],
        boundary_id: str,
        binding: GroupInterfaceBinding,
    ) -> None:
        """Emit a public event for a dynamic group boundary IO change.

        Args:
            event: Event name to emit, for example `io_added` or `io_removed`.
            direction: Boundary direction.
            boundary_id: Stable boundary id affected by the change.
            binding: Binding snapshot for the public/gateway IO pair.

        The event payload is intentionally small and serializable. It identifies
        the boundary and carries a deep copy of the binding so event listeners
        cannot mutate the group's live binding tables.
        """

        self.emit(
            event,
            MessageInArgs(
                src=self,
                direction=direction,
                boundary_id=boundary_id,
                binding=deepcopy(binding),
            ),
        )

    @staticmethod
    def _ensure_boundary_id_is_stable(
        boundary_id: str, kwargs: dict[str, Any]
    ) -> None:
        """Reject update calls that try to change a stable boundary id.

        Boundary ids are durable mapping keys and serialized public/gateway IO
        ids. Renaming a boundary therefore means updating its display metadata,
        not changing the id used by existing edges and bindings.

        Args:
            boundary_id: Existing stable boundary id being updated.
            kwargs: Update keyword arguments supplied by the caller.

        Raises:
            ValueError: If ``id`` or ``uuid`` is present and differs from
                ``boundary_id``.
        """

        for key in ("id", "uuid"):
            if key in kwargs and str(kwargs[key]) != boundary_id:
                raise ValueError("Boundary id cannot be changed")

    @staticmethod
    def _apply_common_io_update(
        target: NodeInput | NodeOutput, template: NodeInput | NodeOutput
    ) -> None:
        """Copy mutable common IO metadata from a template onto live IO.

        The live IO object is kept in place so existing edges remain connected.
        A temporary IO instance is used to validate constructor-compatible
        metadata such as serialized type, render options, and value options
        before this method updates protected storage on the existing object.
        """

        target.name = template.name
        target._description = template.serialize(drop=False).get("description")
        target._sertype = template.serialize(drop=False)["type"]
        target._allow_multiple = template._allow_multiple
        target._default_render_options = template.render_options
        target._default_value_options = template._default_value_options
        target._value_options = template._value_options
        target.hidden = template.hidden
        target._emit_value_set = template._emit_value_set

    @staticmethod
    def _apply_input_only_update(target: NodeInput, template: NodeInput) -> None:
        """Copy mutable input-only metadata from a template onto live input IO."""

        target.required = template.required
        target._does_trigger = template.does_trigger
        target._default = template.default
        if target.value is NoValue:
            target._value = template.default

    def _update_binding_from_live_io(
        self,
        *,
        boundary_id: str,
        direction: Literal["input", "output"],
        public_io: NodeInput | NodeOutput,
        gateway_node: Node,
        gateway_io: NodeInput | NodeOutput,
    ) -> GroupInterfaceBinding:
        """Refresh one stored binding from the current public/gateway IO state.

        Args:
            boundary_id: Stable boundary id to update.
            direction: Boundary direction.
            public_io: Current public IO on the outer group node.
            gateway_node: Internal gateway node for the boundary.
            gateway_io: Current gateway IO matching ``public_io``.

        Returns:
            The refreshed binding stored in the matching binding table.
        """

        binding = _binding_from_io(
            boundary_id=boundary_id,
            direction=direction,
            public_io=public_io,
            gateway_node=gateway_node,
            gateway_io=gateway_io,
        )
        if direction == "input":
            self._input_bindings[boundary_id] = binding
        else:
            self._output_bindings[boundary_id] = binding
        return binding

    def serialize_group_payload(self) -> GroupNodePayload:
        """Serialize the internal group graph and boundary binding table.

        Returns:
            A versioned payload that can be stored inside the outer node's
            serialized `properties`. The returned dictionaries are deep copies
            of the live binding state so callers cannot mutate the group by
            modifying the serialized value.
        """

        return GroupNodePayload(
            version=GROUP_NODE_PAYLOAD_VERSION,
            inner_nodespace=cast(dict[str, Any], self.inner_nodespace.serialize()),
            input_gateway_node=self.group_input_node_uuid,
            output_gateway_node=self.group_output_node_uuid,
            input_bindings=deepcopy(self.input_bindings),
            output_bindings=deepcopy(self.output_bindings),
        )

    def _attach_group_payload(self, data: dict[str, Any]) -> None:
        """Attach the current group payload to an existing node serialization.

        Args:
            data: Mutable serialized node dictionary produced by the base
                `Node` serializer. The method updates only the `properties`
                entry, preserving any user properties already present.
        """

        properties = dict(data.get("properties", {}))
        properties[GROUP_NODE_PROPERTY_KEY] = self.serialize_group_payload()
        data["properties"] = properties

    def serialize(self, drop=True) -> NodeJSON:
        """Serialize the group node including its internal graph payload.

        The outer node continues to use the normal `Node.serialize` shape. The
        only extension is `properties["group"]`, which contains the private
        nodespace, gateway UUIDs, and boundary binding dictionaries.
        """

        serialized = super().serialize(drop=drop)
        self._attach_group_payload(cast(dict[str, Any], serialized))
        return serialized

    def full_serialize(self, with_io_values=False) -> FullNodeJSON:
        """Serialize the full group node state including internal graph data.

        `NodeSpace.full_serialize` calls this method when building live status
        snapshots. Adding the same group payload here keeps complete snapshots
        capable of reconstructing a group if a caller persists them.
        """

        serialized = super().full_serialize(with_io_values=with_io_values)
        self._attach_group_payload(cast(dict[str, Any], serialized))
        return serialized

    @staticmethod
    def _group_payload_from_data(data: NodeJSON) -> GroupNodePayload | None:
        """Extract and validate a group payload from serialized node data.

        Args:
            data: Serialized outer `GroupNode` data.

        Returns:
            The validated group payload, or `None` for older serializations that
            do not yet contain executable group internals.

        Raises:
            ValueError: If the payload exists but is not a supported schema.
        """

        properties = cast(dict[str, Any], data.get("properties", {}))
        payload = properties.get(GROUP_NODE_PROPERTY_KEY)
        if payload is None:
            return None
        if not isinstance(payload, dict):
            raise ValueError("Group payload must be a dictionary")
        if payload.get("version") != GROUP_NODE_PAYLOAD_VERSION:
            raise ValueError(
                f"Unsupported group payload version {payload.get('version')}"
            )
        return cast(GroupNodePayload, payload)

    @staticmethod
    def _node_data_without_group_payload(data: NodeJSON) -> NodeJSON:
        """Return base-node data with the private group payload removed.

        The payload is serialized as a property for compatibility with the
        existing node schema, but it is implementation state rather than a user
        property. Removing it before `Node.deserialize` prevents
        `GroupNode.properties` from retaining a stale copy.
        """

        base_data = cast(NodeJSON, dict(data))
        properties = dict(cast(dict[str, Any], data.get("properties", {})))
        properties.pop(GROUP_NODE_PROPERTY_KEY, None)
        if properties:
            base_data["properties"] = properties  # type: ignore[typeddict-item]
        else:
            base_data.pop("properties", None)
        return base_data

    def _clear_group_boundary_io(self) -> None:
        """Remove existing public boundary IO before replacing group state.

        Deserialization is a replacement operation. If callers reuse a
        `GroupNode` instance, dynamic public IO from the previous group shape
        must be disconnected and removed before the serialized public boundary
        IO is recreated.
        """

        for binding in list(self._input_bindings.values()):
            public_input = self.inputs.get(binding["public_io"])
            if public_input is not None:
                public_input.disconnect()
                self.remove_input(public_input)
        for binding in list(self._output_bindings.values()):
            public_output = self.outputs.get(binding["public_io"])
            if public_output is not None:
                public_output.disconnect()
                self.remove_output(public_output)
        self._input_bindings = {}
        self._output_bindings = {}

    @staticmethod
    def _register_inner_node_classes(
        nodespace: "NodeSpace", payload: GroupNodePayload
    ):
        """Expose registered inner node classes to an internal `NodeSpace`.

        `NodeSpace.deserialize` resolves node classes only through its local
        library. Group payloads therefore seed the private library with every
        currently registered node class referenced by the serialized inner
        graph. Missing classes are intentionally skipped so `NodeSpace` can use
        its existing `PlaceHolderNode` fallback.
        """

        for node_data in payload.get("inner_nodespace", {}).get("nodes", []):
            node_id = node_data.get("node_id")
            if not node_id:
                continue
            try:
                node_cls = get_nodeclass(node_id)
            except NodeKeyError:
                continue
            nodespace.lib.add_node(node_cls, "group")

    @classmethod
    def _deserialize_inner_nodespace(cls, payload: GroupNodePayload) -> "NodeSpace":
        """Build a private `NodeSpace` from serialized group payload data.

        Args:
            payload: Validated version-1 group payload.

        Returns:
            A fresh `NodeSpace` containing deserialized gateway, internal nodes,
            edges, properties, and legacy grouping metadata.

        Raises:
            ValueError: If the restored gateway UUIDs do not point to the
                expected gateway node types.
        """

        from .nodespace import NodeSpace

        inner_nodespace = NodeSpace()
        cls._register_inner_node_classes(inner_nodespace, payload)
        inner_nodespace.deserialize(cast(Any, payload["inner_nodespace"]))

        input_gateway = inner_nodespace.get_node_by_id(payload["input_gateway_node"])
        output_gateway = inner_nodespace.get_node_by_id(payload["output_gateway_node"])
        if not isinstance(input_gateway, GroupInputNode):
            raise ValueError("Group input gateway payload does not restore a gateway")
        if not isinstance(output_gateway, GroupOutputNode):
            raise ValueError("Group output gateway payload does not restore a gateway")

        return inner_nodespace

    @staticmethod
    def _serialized_public_io_for_binding(
        *,
        data: NodeJSON,
        binding: GroupInterfaceBinding,
        is_input: bool,
    ) -> dict[str, Any]:
        """Create serialized public IO data for boundary reconstruction.

        The primary source is the outer node's serialized `io` entry because it
        contains current user-facing names, values, and render metadata. Binding
        metadata is used as a fallback so payloads remain recoverable if future
        serializers omit optional IO fields.
        """

        io_map = cast(dict[str, dict[str, Any]], data.get("io", {}))
        public_io_id = binding["public_io"]
        serialized = _serialized_io_with_id(public_io_id, io_map.get(public_io_id, {}))
        serialized.setdefault("is_input", is_input)
        serialized.setdefault("name", binding.get("name", public_io_id))
        serialized.setdefault("type", binding.get("type", "Any"))

        fallback_keys = (
            "description",
            "allow_multiple",
            "render_options",
            "value_options",
        )
        if is_input:
            fallback_keys = fallback_keys + _INPUT_ONLY_IO_KEYS
        for key in fallback_keys:
            if key in binding and key not in serialized:
                serialized[key] = binding[key]  # type: ignore[literal-required]
        return serialized

    def _restore_public_boundaries(
        self, data: NodeJSON, payload: GroupNodePayload
    ) -> None:
        """Recreate public dynamic IO and binding tables from a payload.

        Gateway dynamic IO is restored by the gateway node deserializers inside
        `_deserialize_inner_nodespace`. This method handles only the public
        `GroupNode` side and then stores deep copies of the binding dictionaries
        so the live group is independent from the input serialization object.
        """

        for boundary_id, binding in payload.get("input_bindings", {}).items():
            serialized = self._serialized_public_io_for_binding(
                data=data,
                binding=binding,
                is_input=True,
            )
            public_input_id = serialized["id"]
            if public_input_id not in self.inputs:
                self.add_input(
                    NodeInput.from_serialized_nodeio(
                        cast(NodeInputSerialization, serialized)
                    )
                )
            self._input_bindings[boundary_id] = deepcopy(binding)

        for boundary_id, binding in payload.get("output_bindings", {}).items():
            serialized = self._serialized_public_io_for_binding(
                data=data,
                binding=binding,
                is_input=False,
            )
            public_output_id = serialized["id"]
            if public_output_id not in self.outputs:
                self.add_output(
                    NodeOutput.from_serialized_nodeio(
                        cast(NodeOutputSerialization, serialized)
                    )
                )
            self._output_bindings[boundary_id] = deepcopy(binding)

    def deserialize(self, data: NodeJSON):
        """Deserialize a group node and restore its private executable graph.

        Older data without a group payload still deserializes as a plain
        `GroupNode` with the default empty internal graph created by
        `__init__`. Version-1 payloads replace the internal nodespace, restore
        both gateway UUIDs, recreate dynamic public boundary IO, and finally
        delegate ordinary node fields to `Node.deserialize`.
        """

        payload = self._group_payload_from_data(data)
        if payload is not None:
            self._clear_group_boundary_io()
            self._inner_nodespace = self._deserialize_inner_nodespace(payload)
            self._attach_inner_nodespace_events()
            self._group_input_node_uuid = payload["input_gateway_node"]
            self._group_output_node_uuid = payload["output_gateway_node"]
            self._group_input_node = self.group_input_node
            self._group_output_node = self.group_output_node
            self._restore_public_boundaries(data, payload)

        super().deserialize(self._node_data_without_group_payload(data))

    def add_group_input(self, **kwargs: Any) -> NodeInput:
        """Create one public input boundary.

        This creates two IO objects:

        - a public `NodeInput` on the outer `GroupNode`
        - a matching `NodeOutput` on the internal `GroupInputNode`

        Args:
            **kwargs: Standard `NodeInput` constructor options. `id` or `uuid`
                may be provided as a stable boundary id; otherwise one is
                generated. Input-only options such as `required`, `default`,
                and `does_trigger` are applied only to the public input.

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

        binding = _binding_from_io(
            boundary_id=boundary_id,
            direction="input",
            public_io=public_input,
            gateway_node=self.group_input_node,
            gateway_io=gateway_output,
        )
        self._input_bindings[boundary_id] = binding
        self._emit_boundary_io_event(
            event="io_added",
            direction="input",
            boundary_id=boundary_id,
            binding=binding,
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
        self._emit_boundary_io_event(
            event="io_removed",
            direction="input",
            boundary_id=boundary_id,
            binding=binding,
        )
        return public_input, gateway_output

    def add_group_output(self, **kwargs: Any) -> NodeOutput:
        """Create one public output boundary.

        This creates two IO objects:

        - a public `NodeOutput` on the outer `GroupNode`
        - a matching `NodeInput` on the internal `GroupOutputNode`

        Args:
            **kwargs: Standard boundary IO options. `id` or `uuid` may be
                provided as a stable boundary id; otherwise one is generated.
                Input-only options such as `required`, `default`, and
                `does_trigger` are applied only to the internal gateway input.

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

        binding = _binding_from_io(
            boundary_id=boundary_id,
            direction="output",
            public_io=public_output,
            gateway_node=self.group_output_node,
            gateway_io=gateway_input,
        )
        self._output_bindings[boundary_id] = binding
        self._emit_boundary_io_event(
            event="io_added",
            direction="output",
            boundary_id=boundary_id,
            binding=binding,
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
        self._emit_boundary_io_event(
            event="io_removed",
            direction="output",
            boundary_id=boundary_id,
            binding=binding,
        )
        return public_output, gateway_input

    def update_group_input(self, boundary_id: str, **kwargs: Any) -> NodeInput:
        """Update display and metadata for one public input boundary.

        The stable boundary id cannot change because it anchors serialized
        bindings and existing edges. Mutable IO metadata is applied to both the
        public `GroupNode` input and the matching `GroupInputNode` output, while
        input-only options such as ``required`` and ``does_trigger`` apply only
        to the public input.

        Args:
            boundary_id: Stable id of the input boundary to update.
            **kwargs: Standard `NodeInput` constructor-style metadata. ``id``
                or ``uuid`` may be repeated only if it matches ``boundary_id``.

        Returns:
            The updated public `NodeInput`.

        Raises:
            ValueError: If the boundary is missing or the update attempts to
                change its stable id.
        """

        if boundary_id not in self._input_bindings:
            raise ValueError(f"Group input '{boundary_id}' not found")
        self._ensure_boundary_id_is_stable(boundary_id, kwargs)

        binding = self._input_bindings[boundary_id]
        public_input = self.get_input(binding["public_io"])
        gateway_output = self.group_input_node.get_output(binding["gateway_io"])

        input_kwargs = {
            **public_input.serialize(drop=False),
            **kwargs,
            "id": public_input.uuid,
        }
        gateway_kwargs = {
            **gateway_output.serialize(drop=False),
            **_select_kwargs(kwargs, _COMMON_IO_KEYS),
            "id": gateway_output.uuid,
        }
        public_template = NodeInput(**input_kwargs)
        gateway_template = NodeOutput(**gateway_kwargs)

        self._apply_common_io_update(public_input, public_template)
        self._apply_input_only_update(public_input, public_template)
        self._apply_common_io_update(gateway_output, gateway_template)

        refreshed_binding = self._update_binding_from_live_io(
            boundary_id=boundary_id,
            direction="input",
            public_io=public_input,
            gateway_node=self.group_input_node,
            gateway_io=gateway_output,
        )
        self._emit_boundary_io_event(
            event="io_updated",
            direction="input",
            boundary_id=boundary_id,
            binding=refreshed_binding,
        )
        return public_input

    def update_group_output(self, boundary_id: str, **kwargs: Any) -> NodeOutput:
        """Update display and metadata for one public output boundary.

        The public `GroupNode` output and internal `GroupOutputNode` input keep
        their existing object identities and connections. Common IO metadata is
        mirrored to both sides. Input-only options such as ``required`` and
        ``does_trigger`` apply to the internal gateway input because that input
        is the triggerable side of an output boundary.

        Args:
            boundary_id: Stable id of the output boundary to update.
            **kwargs: Standard boundary IO metadata. ``id`` or ``uuid`` may be
                repeated only if it matches ``boundary_id``.

        Returns:
            The updated public `NodeOutput`.

        Raises:
            ValueError: If the boundary is missing or the update attempts to
                change its stable id.
        """

        if boundary_id not in self._output_bindings:
            raise ValueError(f"Group output '{boundary_id}' not found")
        self._ensure_boundary_id_is_stable(boundary_id, kwargs)

        binding = self._output_bindings[boundary_id]
        public_output = self.get_output(binding["public_io"])
        gateway_input = self.group_output_node.get_input(binding["gateway_io"])

        public_kwargs = {
            **public_output.serialize(drop=False),
            **_select_kwargs(kwargs, _COMMON_IO_KEYS),
            "id": public_output.uuid,
        }
        gateway_kwargs = {
            **gateway_input.serialize(drop=False),
            **kwargs,
            "id": gateway_input.uuid,
        }
        public_template = NodeOutput(**public_kwargs)
        gateway_template = NodeInput(**gateway_kwargs)

        self._apply_common_io_update(public_output, public_template)
        self._apply_common_io_update(gateway_input, gateway_template)
        self._apply_input_only_update(gateway_input, gateway_template)

        refreshed_binding = self._update_binding_from_live_io(
            boundary_id=boundary_id,
            direction="output",
            public_io=public_output,
            gateway_node=self.group_output_node,
            gateway_io=gateway_input,
        )
        self._emit_boundary_io_event(
            event="io_updated",
            direction="output",
            boundary_id=boundary_id,
            binding=refreshed_binding,
        )
        return public_output

    def _inner_trigger_nodes(self) -> list[Node]:
        """Return all nodes that participate in the internal trigger barrier.

        Gateway nodes are included intentionally. They are structural no-op
        nodes, but their inputs may still receive values through normal
        FuncNodes connection logic. Including them makes the idle check reflect
        the actual internal nodespace state instead of relying on special cases.
        """

        return list(self.inner_nodespace.nodes)

    def _inner_idle(self) -> bool:
        """Return whether the entire internal nodespace is currently idle.

        A node is considered non-idle when it is already triggering or when it
        has a pending trigger request that can run as soon as the scheduler gets
        a chance. This is the extra readiness condition that makes the group act
        like one outer node instead of exposing internal in-flight work.
        """

        for node in self._inner_trigger_nodes():
            if node.in_trigger or node.will_trigger:
                return False
        return True

    def additional_ready_to_trigger(self) -> bool:
        """Return whether group-specific trigger constraints are satisfied.

        The base `Node.ready_to_trigger()` already checks normal input readiness
        and the outer node trigger state. This hook adds the group contract: a
        group is ready only when every internal node, including nested groups
        and gateway nodes, is idle and has no immediately runnable queued
        trigger request.
        """

        return self._inner_idle()

    async def _trigger_queued_when_ready(self) -> None:
        """Trigger a queued group request once the group becomes ready.

        `Node.request_trigger()` can queue a request while the group is waiting
        on inner work. This helper is scheduled from request and inner event
        paths so that the queued request starts after the internal graph becomes
        idle, but never concurrently with active group or inner execution.
        """

        try:
            for _ in range(self.default_inner_trigger_settle_limit):
                if not self._requests_trigger:
                    return
                if self.ready_to_trigger():
                    self.trigger()
                    return
                running_tasks = [
                    task
                    for node in self._inner_trigger_nodes()
                    if (task := getattr(node, "_trigger_task", None)) is not None
                    and not task.done()
                ]
                if running_tasks:
                    await asyncio.gather(
                        *(asyncio.shield(task) for task in running_tasks),
                        return_exceptions=True,
                    )
                else:
                    await asyncio.sleep(0)
        finally:
            self._queued_trigger_task = None

    def _schedule_queued_trigger(self) -> None:
        """Ensure a background task exists for a queued group trigger request.

        The scheduler is intentionally local to `GroupNode`; it does not alter
        global `NodeSpace` behavior. If no event loop is running or no request is
        queued, the method is a no-op.
        """

        if not self._requests_trigger:
            return
        if self._queued_trigger_task is not None and not self._queued_trigger_task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._queued_trigger_task = loop.create_task(self._trigger_queued_when_ready())

    def request_trigger(self):
        """Request a group trigger without starting while inner work is busy.

        The base implementation is still responsible for normal node semantics.
        After delegating to it, this override schedules queued group requests so
        they can start automatically once active inner nodes have finished.
        """

        super().request_trigger()
        self._schedule_queued_trigger()

    @staticmethod
    def _is_source_like_inner_node(node: Node) -> bool:
        """Return whether an inner node should start from a group trigger alone.

        Nodes with no public data inputs behave like sources in the private
        graph. They cannot be triggered by input propagation, so the group starts
        them explicitly when it runs.
        """

        return all(input_.uuid == "_triggerinput" for input_ in node.inputs.values())

    def _trigger_ready_inner_nodes_once(self) -> None:
        """Start source-like and nested inner nodes once for this trigger.

        Value propagation usually requests downstream internal triggers through
        normal input semantics. This method starts ready internal source nodes
        and nested groups that otherwise may not receive such a request, without
        re-running ordinary downstream nodes whose inputs already triggered them.
        """

        for node in self._inner_trigger_nodes():
            if isinstance(node, (GroupInputNode, GroupOutputNode)):
                continue
            should_start = isinstance(node, GroupNode) or self._is_source_like_inner_node(
                node
            )
            if should_start and node.ready_to_trigger():
                node.trigger()

    def _raise_inner_trigger_errors(self) -> None:
        """Raise the first captured inner trigger error on the outer group.

        Inner nodes report trigger failures through their private `NodeSpace`.
        Promoting the first captured error from `GroupNode.func()` lets the base
        node trigger machinery emit a normal `NodeTriggerError` on the outer
        group as well.
        """

        if not self._inner_trigger_errors:
            return
        error = self._inner_trigger_errors[0]
        if isinstance(error, NodeTriggerError):
            raise error
        raise NodeTriggerError.from_error(error)

    async def _await_inner_quiescence(self) -> None:
        """Wait until the internal nodespace has no active or ready work.

        Internal propagation can create new trigger tasks while earlier trigger
        tasks are completing. For that reason this method uses a fixed-point
        loop:

        1. trigger any ready inner node with a pending request
        2. await all currently running inner trigger tasks
        3. repeat until no inner node is active or ready-to-trigger

        Raises:
            TimeoutError: If the internal graph does not settle within
                `default_inner_trigger_settle_limit` iterations. The base
                `Node.__call__` machinery will turn that into a normal node
                trigger error.
        """

        for _ in range(self.default_inner_trigger_settle_limit):
            for node in self._inner_trigger_nodes():
                node.trigger_if_requested()

            running_tasks = [
                task
                for node in self._inner_trigger_nodes()
                if (task := getattr(node, "_trigger_task", None)) is not None
                and not task.done()
            ]
            if running_tasks:
                await asyncio.gather(*running_tasks)
                self._raise_inner_trigger_errors()
                continue

            self._raise_inner_trigger_errors()
            if self._inner_idle():
                return

            await asyncio.sleep(0)

        raise TimeoutError("Group inner nodes did not settle after trigger")

    def _raise_if_inner_busy_before_trigger(self, **kwargs: Any) -> None:
        """Reject a new outer trigger when the internal graph is busy.

        `Node.trigger` is a protected `savemethod`, so `GroupNode` cannot
        override it directly. Instead, each group instance subscribes this guard
        to its own `before_trigger` event. The base trigger implementation emits
        that event before it creates the group trigger task, which gives the
        group a supported hook for enforcing the boundary rule.

        Raises:
            InTriggerError: If any internal node is active or queued to trigger.
        """

        if not self._inner_idle():
            raise InTriggerError("Group inner nodes are already in trigger")

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

    def _copy_public_inputs_to_gateway_outputs(self) -> None:
        """Mirror ready public group inputs to internal gateway outputs.

        Each input binding maps one public `GroupNode` input to one
        `GroupInputNode` output. Copying through `NodeOutput.set_value` reuses
        existing output-to-input propagation for any internal nodes connected to
        that gateway output.

        Inputs whose value is `NoValue` are skipped. This allows optional or
        not-yet-provided boundaries to exist without forcing an internal value.
        """

        for binding in self.input_bindings.values():
            public_input = self.get_input(binding["public_io"])
            value = public_input.value
            if value is NoValue:
                continue
            gateway_output = self.group_input_node.get_output(binding["gateway_io"])
            gateway_output.set_value(value)

    def _copy_gateway_inputs_to_public_outputs(self) -> None:
        """Mirror ready internal gateway inputs to public group outputs.

        Each output binding maps one `GroupOutputNode` input to one public
        `GroupNode` output. Copying through `NodeOutput.set_value` ensures that
        downstream external connections see the value through the standard
        FuncNodes propagation path.

        Gateway inputs whose value is `NoValue` are skipped so unset optional
        outputs do not overwrite public output state or raise during this
        milestone's simple trigger flow.
        """

        for binding in self.output_bindings.values():
            gateway_input = self.group_output_node.get_input(binding["gateway_io"])
            value = gateway_input.value
            if value is NoValue:
                continue
            public_output = self.get_output(binding["public_io"])
            public_output.set_value(value)

    async def func(self, **kwargs):
        """Run the current simple group trigger flow.

        The current milestone mirrors values across the group boundary in two
        phases:

        1. public inputs -> `GroupInputNode` outputs
        2. `GroupOutputNode` inputs -> public outputs

        Between those two phases it waits for all internal trigger work to
        finish. This means downstream external nodes only see public group
        outputs after the internal graph has reached quiescence.
        """

        self._inner_trigger_errors = []
        self._copy_public_inputs_to_gateway_outputs()
        self._trigger_ready_inner_nodes_once()
        await self._await_inner_quiescence()
        self._copy_gateway_inputs_to_public_outputs()
        return None
