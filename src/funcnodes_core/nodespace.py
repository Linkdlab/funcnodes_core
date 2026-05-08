from typing import List, Dict, TypedDict, Tuple, Any, Optional, TYPE_CHECKING
import json
from uuid import uuid4
import traceback

from .grouping_logic import GroupingLogic, NodeGroup

from .node import (
    FullNodeJSON,
    NodeJSON,
    PlaceHolderNode,
    NodeTriggerError,
    Node,
    run_until_complete,
)  #
from .io import NodeInput, NodeOutput


from .lib import FullLibJSON, Library, NodeClassNotFoundError, Shelf, flatten_shelf


from .eventmanager import EventEmitterMixin, MessageInArgs, emit_after
from .utils.serialization import JSONEncoder, JSONDecoder, Encdata

if TYPE_CHECKING:
    from .group_nodes import GroupNode


class NodeException(Exception):
    """
    Base exception class for node exceptions.
    """

    pass


class FullNodeSpaceJSON(TypedDict):
    """
    FullNodeSpaceJSON for a full serilization including temporary properties
    """

    nodes: List[FullNodeJSON]
    edges: List[Tuple[str, str, str, str]]
    prop: Dict[str, Any]
    lib: FullLibJSON
    groups: Dict[str, NodeGroup]


class NodeSpaceJSON(TypedDict, total=False):
    """
    NodeSpaceJSON is the interface for the serialization of a NodeSpace
    """

    nodes: List[NodeJSON]
    edges: List[Tuple[str, str, str, str]]
    prop: Dict[str, Any]
    groups: Dict[str, NodeGroup]


class NodeSpace(EventEmitterMixin):
    """
    NodeSpace is a manager and container for nodes and edges between them.
    Also it contains a reference to a library of nodes.
    """

    def __init__(self, id: str | None = None):
        """
        Initializes a new NodeSpace object.

        Args:
          id (str | None): Optional ID for the NodeSpace. Defaults to None.

        """
        super().__init__()
        self._nodes: Dict[str, Node] = {}
        self._properties: Dict[str, Any] = {}  # public properties are serialized
        self._secret_properties: Dict[  # secret properties are not serialized
            str, Any
        ] = {}
        self.groups = GroupingLogic()
        self._allow_group_gateway_nodes = False
        self.lib = Library()
        if id is None:
            id = uuid4().hex
        self._id = id

    # region Properties
    @property
    def id(self) -> str:
        """
        Returns the ID of the NodeSpace.

        Returns:
          str: The ID of the NodeSpace.
        """
        return self._id

    @property
    def nodes(self) -> List[Node]:
        """
        Returns a list of all nodes in the NodeSpace.

        Returns:
          List[Node]: A list of all nodes in the NodeSpace.
        """
        return list(self._nodes.values())

    @property
    def edges(self) -> List[Tuple[NodeOutput, NodeInput]]:
        """
        Returns a list of all edges in the NodeSpace.

        Returns:
          List[Tuple[NodeOutput, NodeInput]]: A list of all edges in the NodeSpace.
        """
        edges: List[Tuple[NodeOutput, NodeInput]] = []
        for node in self.nodes:
            for output in node.outputs.values():
                for input in output.connections:
                    edges.append((output, input))

            for inputstart in node.inputs.values():
                for inputend in inputstart.get_forward_connections():
                    edges.append((inputstart, inputend))

        return edges

    def set_property(self, key: str, value: Any, secret=False):
        """
        Sets a property in the NodeSpace.

        Args:
          key (str): The key of the property to set.
          value (Any): The value to set the property to.
        """
        # make sure value is json serializable and key is a string
        if not isinstance(key, str):
            raise ValueError("key must be a string")

        try:
            json.dumps(value)
        except Exception as e:
            raise ValueError(f"value must be json serializable: {e}")

        if secret:
            self.set_secret_property(key, value)
        else:
            self._properties[key] = value

    def get_secret_property(self, key: str) -> Any:
        """
        Gets a secret property from the NodeSpace.

        Args:
          key (str): The key of the property to get.

        Returns:
          Any: The value of the property.
        """
        return self._secret_properties.get(key)

    def set_secret_property(self, key: str, value: Any):
        """
        Sets a secret property in the
        NodeSpace.

        Args:
          key (str): The key of the property to set.
          value (Any): The value to set the property to.
        """
        self._secret_properties[key] = value

    def get_property(self, key: str) -> Any:
        """
        Gets a property from the NodeSpace.

        Args:
          key (str): The key of the property to get.

        Returns:
          Any: The value of the property.
        """
        return self._properties.get(key, self._secret_properties.get(key))

    def remove_property(self, key: str, ignore_secret=False, ignore_public=False):
        """
        Removes a property from the NodeSpace.

        Args:
            key (str): The key of the property to remove.
            ignore_secret (bool): Whether to ignore secret properties. Defaults to False.
            ignore_public (bool): Whether to ignore public properties. Defaults to False.
        """
        if not ignore_secret:
            self._secret_properties.pop(key, None)
        if not ignore_public:
            self._properties.pop(key, None)

    # endregion Properties

    # region serialization
    def full_serialize(self, with_io_values=False) -> FullNodeSpaceJSON:
        """
        Serializes the NodeSpace and all of its nodes and edges.

        Returns:
          FullNodeSpaceJSON: A JSON object containing the serialized NodeSpace.
        """
        return {
            "nodes": self.full_nodes_serialize(with_io_values=with_io_values),
            "prop": self._properties,
            "lib": self.lib.full_serialize(),
            "edges": self.serialize_edges(),
            "groups": self.serialize_groups(),
        }

    def full_nodes_serialize(self, with_io_values=False) -> List[FullNodeJSON]:
        """
        Serializes all nodes in the NodeSpace.

        Returns:
          List[FullNodeJSON]: A list of JSON objects containing the serialized nodes.
        """
        return [
            node.full_serialize(with_io_values=with_io_values) for node in self.nodes
        ]

    def deserialize_nodes(self, data: List[NodeJSON]):
        """
        deserialize_nodes deserializes a list of nodes

        Parameters
        ----------
        data : List[NodeJSON]
            the nodes to deserialize

        Returns
        -------
        Dict[str, Node]
            the deserialized nodes
        """
        for node in self.nodes:
            self.remove_node_instance(
                node,
                _allow_group_gateway=self._allow_group_gateway_nodes,
            )
        for node in data:
            try:
                node_cls = self.lib.get_node_by_id(node["node_id"])
            except NodeClassNotFoundError:
                node_cls = PlaceHolderNode
            node_instance = node_cls()
            node_instance.deserialize(node)
            self.add_node_instance(
                node_instance,
                _allow_group_gateway=self._allow_group_gateway_nodes,
            )

    def deserialize_edges(self, data: List[Tuple[str, str, str, str]]):
        """
        Deserializes the edges in the NodeSpace.

        Args:
          data (List[Tuple[str, str, str, str]]): A list of tuples containing the UUIDs and IDs of the connected nodes.
        """
        for output_uuid, output_id, input_uuid, input_id in data:
            try:
                output = self.get_node_by_id(output_uuid).get_input_or_output(output_id)
                input = self.get_node_by_id(input_uuid).get_input_or_output(input_id)
                if isinstance(output, NodeOutput) and isinstance(input, NodeInput):
                    input.connect(output)
                else:
                    output.connect(input)
            except Exception:
                pass

    def serialize_nodes(self) -> List[NodeJSON]:
        """serialize_nodes serializes the nodes in the nodespace

        Returns
        -------
        List[NodeJSON]
            the serialized nodes
        """
        ret = []
        for node in self.nodes:
            ret.append(node.serialize())
        return json.loads(json.dumps(ret, cls=JSONEncoder), cls=JSONDecoder)

    def serialize_edges(self) -> List[Tuple[str, str, str, str]]:
        """
        Serializes the edges in the NodeSpace.

        Returns:
          List[Tuple[str, str, str, str]]: A list of tuples containing the UUIDs and IDs of the connected nodes.
        """
        return [
            (output.node.uuid, output.uuid, input.node.uuid, input.uuid)
            for output, input in self.edges
            if output.node is not None and input.node is not None
        ] + [
            (output.node.uuid, output.uuid, input.node.uuid, input.uuid)
            for output, input in self.edges
            if output.node is not None and input.node is None
        ]

    def serialize_groups(self) -> Dict[str, NodeGroup]:
        return self.groups.serialize()

    def deserialize_groups(self, data: Dict[str, NodeGroup]):
        self.groups.deserialize(data)

    def deserialize(self, data: NodeSpaceJSON):
        """
        deserialize deserializes the nodespace from a dictionary

        Parameters
        ----------
        data : NodeSpaceJSON
            the data to deserialize
        """
        self.clear()
        self._properties = data.get("prop", {})
        self.deserialize_nodes(data.get("nodes", []))
        self.deserialize_edges(data.get("edges", []))
        self.deserialize_groups(data.get("groups", {}))

    def serialize(self) -> NodeSpaceJSON:
        """serialize serializes the nodespace to a dictionary

        Returns
        -------
        NodeSpaceSerializationInterface
            the serialized nodespace
        """
        ret = NodeSpaceJSON(
            nodes=self.serialize_nodes(),
            edges=self.serialize_edges(),
            prop=self._properties,
            groups=self.serialize_groups(),
        )
        return json.loads(json.dumps(ret, cls=JSONEncoder), cls=JSONDecoder)

    def clear(self):
        """clear removes all nodes and edges from the nodespace"""
        for node in self.nodes:
            self.remove_node_instance(
                node,
                _allow_group_gateway=self._allow_group_gateway_nodes,
            )
        self.groups = GroupingLogic()
        self._properties = {}

    # endregion serialization

    # region nodes
    # region add/remove nodes

    @staticmethod
    def _is_group_gateway_node(node: Node) -> bool:
        """Return whether `node` is an internal executable-group gateway."""

        from .group_nodes import GroupInputNode, GroupOutputNode

        return isinstance(node, (GroupInputNode, GroupOutputNode))

    @staticmethod
    def _raise_manual_group_gateway_error() -> None:
        """Raise the shared error for manual group gateway node mutations."""

        raise ValueError("Group gateway nodes are managed by GroupNode")

    def add_node_instance(self, node: Node, *, _allow_group_gateway: bool = False):
        """add_node_instance adds a node instance to the nodespace

        Parameters
        ----------
        node : Node
            the node to add
        _allow_group_gateway : bool
            Internal-only switch used by `GroupNode` to create or restore its
            required gateway nodes. Public callers must not pass this flag.
        """
        if self._is_group_gateway_node(node) and not _allow_group_gateway:
            self._raise_manual_group_gateway_error()
        if node.uuid in self._nodes:
            raise ValueError(f"node with uuid '{node.uuid}' already exists")
        self._nodes[node.uuid] = node
        node.nodespace = self
        node.on("*", self.on_node_event)
        node.on_error(self.on_node_error)
        node_ser = node.full_serialize(with_io_values=False)
        msg = MessageInArgs(node=node_ser)
        self.emit("node_added", msg)

        return node

    def on_node_event(self, event: str, src: Node, **data):
        """
        Handles events emitted by nodes in the NodeSpace.

        Args:
          event (str): The name of the event.
          src (Node): The node that emitted the event.
          **data: Additional data passed with the event.
        """
        if event == "cleanup":
            # Gateway cleanup can be emitted during owning GroupNode teardown or
            # garbage collection. Public remove_node_instance still rejects
            # gateway removals; this path only prevents destructor warnings.
            self.remove_node_instance(
                src,
                _allow_group_gateway=(
                    self._allow_group_gateway_nodes
                    or self._is_group_gateway_node(src)
                ),
            )
            return
        msg = MessageInArgs(node=src.uuid, **data)
        self.emit(event, msg)

    def on_node_error(self, src: Node, error: Exception):
        """
        Handles errors emitted by nodes in the NodeSpace.

        Args:
          src (Node): The node that emitted the error.
          error (Exception): The error that was emitted.
        """
        key = "node_error"
        if isinstance(error, NodeTriggerError):
            key = "node_trigger_error"
        self.emit(
            key,
            MessageInArgs(
                node=src.uuid, error=error, tb=traceback.format_exception(error)
            ),
        )

    def remove_node_instance(
        self,
        node: Node,
        *,
        _allow_group_gateway: bool = False,
    ) -> str:
        """
        Removes a node instance from the NodeSpace.

        Args:
          node (Node): The node instance to remove.
          _allow_group_gateway: Internal-only switch used by `GroupNode` when
            ungrouping or replacing its private gateway nodes.

        Returns:
          str: The UUID of the removed node.
        """
        if self._is_group_gateway_node(node) and not _allow_group_gateway:
            self._raise_manual_group_gateway_error()
        if node.uuid not in self._nodes:
            raise ValueError(f"node with uuid '{node.uuid}' not found in nodespace")
        self.groups.ungroup_nodes([node.uuid])
        node = self._nodes.pop(node.uuid)
        node.nodespace = None
        node.off("*", self.on_node_event)

        for output in node.outputs.values():
            for input in output.connections:
                if input.node is not None:
                    if input.node.uuid in self._nodes:
                        output.disconnect(input)
        for input in node.inputs.values():
            for output in input.connections:
                if output.node is not None:
                    if output.node.uuid in self._nodes:
                        output.disconnect(input)

        msg = MessageInArgs(node=node.uuid)
        self.emit("node_removed", msg)
        uuid = node.uuid
        node.cleanup()
        del node
        return uuid

    def add_node_by_id(self, id: str, **kwargs):
        """
        Adds a new node instance to the NodeSpace using its ID.

        Args:
          id (str): The ID of the node to add.
          **kwargs: Additional keyword arguments to pass to the node constructor.

        Returns:
          Node: The newly added node instance.
        """
        # find node in lib
        node_cls = self.lib.get_node_by_id(id)
        if node_cls is None:
            raise ValueError(f"node with id '{id}' not found in lib")

        node = node_cls(**kwargs)
        return self.add_node_instance(node)

    def remove_node_by_id(self, nid: str) -> str | None:
        """
        Removes a node from the nodespace by its id.

        Args:
          nid (str): The id of the node to remove.

        Returns:
          str | None: The id of the removed node, or None if the node was not found.
        """
        try:
            return self.remove_node_instance(self.get_node_by_id(nid))
        except ValueError:
            pass

    # endregion add/remove nodes

    def get_node_by_id(self, nid: str) -> Node:
        """
        Gets a node from the nodespace by its id.

        Args:
          nid (str): The id of the node to get.

        Returns:
          Node: The node with the given id.
        """
        if nid not in self._nodes:
            raise ValueError(f"node with id '{nid}' not found in nodespace")
        return self._nodes[nid]

    # endregion nodes

    # region executable grouping

    @staticmethod
    def _group_boundary_id(prefix: str, node: Node, io: NodeInput | NodeOutput) -> str:
        """Build a stable public boundary id for a crossing edge endpoint.

        Args:
          prefix: Directional boundary prefix. Incoming selected inputs use
            ``"in"`` and outgoing selected outputs use ``"out"``.
          node: Selected node that owns the internal endpoint.
          io: Internal endpoint represented at the group boundary.

        Returns:
          A deterministic id that is unique for the selected endpoint inside the
          new group.
        """

        return f"{prefix}_{node.uuid}_{io.uuid}"

    @staticmethod
    def _group_boundary_options(
        boundary_id: str, io: NodeInput | NodeOutput
    ) -> Dict[str, Any]:
        """Copy public IO metadata for a generated group boundary.

        Args:
          boundary_id: Stable id to use for the public and gateway IO pair.
          io: Existing selected endpoint whose user-facing metadata should be
            mirrored at the group boundary.

        Returns:
          Keyword options suitable for `GroupNode.add_group_input` or
          `GroupNode.add_group_output`.

        Runtime values are intentionally dropped. Group construction rewires the
        graph topology; it does not snapshot transient IO values into the new
        boundary.
        """

        options = dict(io.serialize(drop=False))
        options["id"] = boundary_id
        options.pop("is_input", None)
        options.pop("value", None)
        return options

    def _validate_group_node_selection(self, node_ids: List[str]) -> Dict[str, Node]:
        """Validate a group-from-selection request before any mutation.

        Args:
          node_ids: UUIDs of nodes that should move into the new executable
            group.

        Returns:
          A dictionary of selected node UUIDs to live nodes.

        Raises:
          ValueError: If the selection is empty, contains duplicates, references
            a missing node, selects gateway implementation nodes directly, or
            includes a node that is currently active or queued.
        """

        if not node_ids:
            raise ValueError("Cannot create a group from an empty selection")
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("Cannot create a group from duplicate node ids")

        from .group_nodes import GroupInputNode, GroupOutputNode

        selected: Dict[str, Node] = {}
        for node_id in node_ids:
            if node_id not in self._nodes:
                raise ValueError(f"Selected node '{node_id}' not found in nodespace")
            node = self._nodes[node_id]
            if isinstance(node, (GroupInputNode, GroupOutputNode)):
                raise ValueError("Cannot group internal group gateway nodes directly")
            if node.in_trigger or node.will_trigger:
                raise ValueError(f"Selected node '{node_id}' is currently triggering")
            selected[node_id] = node
        return selected

    def _collect_group_node_crossing_edges(
        self, selected_ids: set[str]
    ) -> tuple[
        List[tuple[NodeOutput, NodeInput]],
        List[tuple[NodeOutput, NodeInput]],
    ]:
        """Collect supported edges that cross a selected group boundary.

        Args:
          selected_ids: UUIDs of nodes that will move into the group.

        Returns:
          A tuple ``(incoming_edges, outgoing_edges)``. Incoming edges originate
          outside the selection and target a selected input. Outgoing edges
          originate at a selected output and target an outside input.

        Raises:
          ValueError: If a crossing edge uses input-forwarding rather than a
            normal output-to-input connection. Forwarding is preserved for fully
            internal selected edges, but crossing forwarding needs a dedicated
            boundary policy and is rejected before mutation in this milestone.
        """

        incoming_edges: List[tuple[NodeOutput, NodeInput]] = []
        outgoing_edges: List[tuple[NodeOutput, NodeInput]] = []
        for source_io, target_input in self.edges:
            source_node = source_io.node
            target_node = target_input.node
            if source_node is None or target_node is None:
                continue

            source_selected = source_node.uuid in selected_ids
            target_selected = target_node.uuid in selected_ids
            if source_selected == target_selected:
                continue
            if not isinstance(source_io, NodeOutput):
                raise ValueError(
                    "Grouping crossing input-forward edges is not supported"
                )
            if source_selected:
                outgoing_edges.append((source_io, target_input))
            else:
                incoming_edges.append((source_io, target_input))
        return incoming_edges, outgoing_edges

    def _detach_node_instance_for_grouping(self, node: Node) -> Node:
        """Detach a node from this parent space without destroying its IO.

        `remove_node_instance()` is intentionally not used for group
        construction because it disconnects same-space edges and calls
        `Node.cleanup()`, which removes the IO objects that must survive inside
        the group. This helper performs only the ownership/event bookkeeping
        needed to move a live node into another `NodeSpace`.

        Args:
          node: Live node currently owned by this `NodeSpace`.

        Returns:
          The same node instance, now detached from this space.

        Raises:
          ValueError: If the node is not owned by this space.
        """

        if node.uuid not in self._nodes:
            raise ValueError(f"node with uuid '{node.uuid}' not found in nodespace")
        self.groups.ungroup_nodes([node.uuid])
        moved = self._nodes.pop(node.uuid)
        moved.nodespace = None
        moved.off("*", self.on_node_event)
        moved.off_error(self.on_node_error)
        self.emit("node_removed", MessageInArgs(node=moved.uuid))
        return moved

    def group_nodes_as_node(
        self,
        node_ids: List[str],
        *,
        group_id: Optional[str] = None,
        name: Optional[str] = None,
    ) -> Node:
        """Replace selected nodes with one executable `GroupNode`.

        Args:
          node_ids: UUIDs of parent-space nodes to move into the new group.
          group_id: Optional UUID for the new outer `GroupNode`.
          name: Optional display name for the new outer `GroupNode`.

        Returns:
          The created `GroupNode` instance.

        The method converts every supported crossing edge through generated
        gateway boundaries:

        - external output -> selected input becomes external output -> group
          public input and group input gateway output -> selected input.
        - selected output -> external input becomes selected output -> group
          output gateway input and group public output -> external input.

        Selected-to-selected edges are left connected while the selected nodes
        move into the group, so their topology and UUIDs are preserved. All
        validation happens before mutation for the invalid-selection cases this
        milestone supports.
        """

        from .group_nodes import GroupNode

        selected = self._validate_group_node_selection(node_ids)
        selected_ids = set(selected)
        incoming_edges, outgoing_edges = self._collect_group_node_crossing_edges(
            selected_ids
        )

        group = GroupNode(uuid=group_id, name=name)
        if group.uuid in self._nodes:
            raise ValueError(f"node with uuid '{group.uuid}' already exists")

        incoming_boundaries: Dict[tuple[str, str], str] = {}
        for _, internal_input in incoming_edges:
            internal_node = internal_input.node
            if internal_node is None:
                continue
            key = (internal_node.uuid, internal_input.uuid)
            if key not in incoming_boundaries:
                boundary_id = self._group_boundary_id(
                    "in", internal_node, internal_input
                )
                group.add_group_input(
                    **self._group_boundary_options(boundary_id, internal_input)
                )
                incoming_boundaries[key] = boundary_id

        outgoing_boundaries: Dict[tuple[str, str], str] = {}
        for internal_output, _ in outgoing_edges:
            internal_node = internal_output.node
            if internal_node is None:
                continue
            key = (internal_node.uuid, internal_output.uuid)
            if key not in outgoing_boundaries:
                boundary_id = self._group_boundary_id(
                    "out", internal_node, internal_output
                )
                boundary_options = self._group_boundary_options(
                    boundary_id, internal_output
                )
                boundary_options["does_trigger"] = False
                group.add_group_output(**boundary_options)
                outgoing_boundaries[key] = boundary_id

        for external_output, internal_input in incoming_edges:
            external_output.disconnect(internal_input)
        for internal_output, external_input in outgoing_edges:
            internal_output.disconnect(external_input)

        for node_id in node_ids:
            group.inner_nodespace.add_node_instance(
                self._detach_node_instance_for_grouping(selected[node_id])
            )

        self.lib.add_node(GroupNode, "groups")
        self.add_node_instance(group)

        for _, internal_input in incoming_edges:
            internal_node = internal_input.node
            if internal_node is None:
                continue
            boundary_id = incoming_boundaries[(internal_node.uuid, internal_input.uuid)]
            binding = group.input_bindings[boundary_id]
            group.group_input_node.outputs[binding["gateway_io"]].connect(
                internal_input
            )

        for internal_output, external_input in outgoing_edges:
            internal_node = internal_output.node
            if internal_node is None:
                continue
            boundary_id = outgoing_boundaries[
                (internal_node.uuid, internal_output.uuid)
            ]
            binding = group.output_bindings[boundary_id]
            internal_output.connect(
                group.group_output_node.inputs[binding["gateway_io"]]
            )
            group.outputs[binding["public_io"]].connect(external_input)

        for external_output, internal_input in incoming_edges:
            internal_node = internal_input.node
            if internal_node is None:
                continue
            boundary_id = incoming_boundaries[(internal_node.uuid, internal_input.uuid)]
            binding = group.input_bindings[boundary_id]
            external_output.connect(group.inputs[binding["public_io"]])

        return group

    def create_group_node(
        self,
        node_ids: List[str],
        *,
        group_id: Optional[str] = None,
        name: Optional[str] = None,
    ) -> Node:
        """Alias for `group_nodes_as_node`.

        The shorter name is useful for callers that think in terms of creating a
        new executable node, while `group_nodes_as_node` makes the replacement
        behavior explicit. Both APIs share the same implementation and
        guarantees.
        """

        return self.group_nodes_as_node(node_ids, group_id=group_id, name=name)

    @staticmethod
    def _legacy_group_display_name(group_id: str, group: NodeGroup) -> str:
        """Resolve a display name for a materialized legacy group.

        Args:
          group_id: Legacy `GroupingLogic` group id.
          group: Legacy group data.

        Returns:
          The best available group display name. The bridge prefers explicit
          ``meta["name"]``, then existing UI-style ``meta["label"]``, and falls
          back to the stable group id.
        """

        meta = group.get("meta", {})
        name = meta.get("name", meta.get("label", group_id))
        return str(name)

    @staticmethod
    def _copy_legacy_group_metadata(
        group: "GroupNode", group_id: str, legacy_group: NodeGroup
    ) -> None:
        """Copy UI-only legacy metadata onto an executable group node.

        Args:
          group: Newly materialized executable group.
          group_id: Original legacy group id.
          legacy_group: Snapshot of the legacy `NodeGroup` dictionary.

        Metadata that has no first-class `Node` field is stored as regular node
        properties under explicit ``legacy_group_*`` keys. A
        ``meta["render_options"]`` dictionary is also merged into the group
        node's render options because that is the normal core rendering surface.
        """

        meta = dict(legacy_group.get("meta", {}))
        group.set_property("legacy_group_id", group_id)
        group.set_property("legacy_group_meta", meta)

        if "position" in legacy_group:
            group.set_property("legacy_group_position", legacy_group["position"])
        if "collapsed" in meta:
            group.set_property("legacy_group_collapsed", meta["collapsed"])
        if "open" in meta:
            group.set_property("legacy_group_open", meta["open"])

        render_options = meta.get("render_options")
        if isinstance(render_options, dict):
            group.render_options.update(render_options)

    def materialize_group(self, group_id: str) -> "GroupNode":
        """Convert one legacy UI group into an executable `GroupNode`.

        Args:
          group_id: Existing `GroupingLogic` group id to materialize.

        Returns:
          The created executable `GroupNode`.

        The bridge intentionally does not run during `NodeSpace.deserialize`.
        Old files keep their top-level ``"groups"`` data until callers
        explicitly invoke this method. For this milestone, only direct
        ``node_ids`` are materialized; legacy groups with child groups are
        rejected before mutation so hierarchy flattening is never implicit.

        Raises:
          ValueError: If the group is missing, has child groups, or has no direct
            nodes to materialize.
        """

        legacy_group = self.groups.get_group(group_id)
        if legacy_group is None:
            raise ValueError(f"Legacy group '{group_id}' not found")
        if legacy_group.get("child_groups"):
            raise ValueError(
                f"Legacy group '{group_id}' has child groups and cannot be "
                "materialized automatically"
            )

        node_ids = list(legacy_group.get("node_ids", []))
        if not node_ids:
            raise ValueError(f"Legacy group '{group_id}' has no nodes")

        legacy_snapshot = NodeGroup(
            node_ids=node_ids,
            child_groups=list(legacy_group.get("child_groups", [])),
            parent_group=legacy_group.get("parent_group"),
            meta=dict(legacy_group.get("meta", {})),
        )
        if "position" in legacy_group:
            legacy_snapshot["position"] = legacy_group["position"]

        group = self.group_nodes_as_node(
            node_ids,
            name=self._legacy_group_display_name(group_id, legacy_snapshot),
        )
        self._copy_legacy_group_metadata(group, group_id, legacy_snapshot)
        if self.groups.get_group(group_id) is not None:
            self.groups.remove_group(group_id, recursive=False)
        return group

    def _validate_ungroup_target(self, group_node_uuid: str) -> "GroupNode":
        """Validate an executable group can be ungrouped before mutation.

        Args:
          group_node_uuid: UUID of the parent-space node that should be
            ungrouped.

        Returns:
          The live `GroupNode` instance.

        Raises:
          ValueError: If the target is missing, is not a `GroupNode`, contains
            active inner work, or would introduce UUID conflicts in the parent
            space.
        """

        from .group_nodes import GroupNode

        if group_node_uuid not in self._nodes:
            raise ValueError(f"Group node '{group_node_uuid}' not found")
        group = self._nodes[group_node_uuid]
        if not isinstance(group, GroupNode):
            raise ValueError(f"Node '{group_node_uuid}' is not a GroupNode")
        if group.in_trigger or group.will_trigger or not group._inner_idle():
            raise ValueError(f"Group node '{group_node_uuid}' is currently triggering")

        for inner_node in group.iter_inner_nodes():
            if inner_node.uuid in self._nodes:
                raise ValueError(
                    f"Cannot ungroup node with conflicting uuid '{inner_node.uuid}'"
                )
        return group

    @staticmethod
    def _ungroup_input_edges(
        group: "GroupNode",
    ) -> List[tuple[NodeOutput, NodeInput]]:
        """Collect direct edges represented by group input boundaries.

        Args:
          group: `GroupNode` instance being ungrouped.

        Returns:
          Direct edges to recreate after inner nodes move back to the parent
          space. Each edge connects an external output to an internal input.
        """

        direct_edges: List[tuple[NodeOutput, NodeInput]] = []
        for binding in group.input_bindings.values():
            public_input = group.inputs[binding["public_io"]]
            gateway_output = group.group_input_node.outputs[binding["gateway_io"]]
            for external_output in public_input.connections:
                if not isinstance(external_output, NodeOutput):
                    continue
                for internal_input in gateway_output.connections:
                    direct_edges.append((external_output, internal_input))
        return direct_edges

    @staticmethod
    def _ungroup_output_edges(
        group: "GroupNode",
    ) -> List[tuple[NodeOutput, NodeInput]]:
        """Collect direct edges represented by group output boundaries.

        Args:
          group: `GroupNode` instance being ungrouped.

        Returns:
          Direct edges to recreate after inner nodes move back to the parent
          space. Each edge connects an internal output to an external input.
        """

        direct_edges: List[tuple[NodeOutput, NodeInput]] = []
        for binding in group.output_bindings.values():
            gateway_input = group.group_output_node.inputs[binding["gateway_io"]]
            public_output = group.outputs[binding["public_io"]]
            for internal_output in gateway_input.connections:
                if not isinstance(internal_output, NodeOutput):
                    continue
                for external_input in public_output.connections:
                    direct_edges.append((internal_output, external_input))
        return direct_edges

    @staticmethod
    def _disconnect_group_boundary_edges(group: "GroupNode") -> None:
        """Disconnect every edge that crosses or touches group gateway IO.

        Args:
          group: `GroupNode` instance being ungrouped.

        The disconnect phase is separated from the reconnect phase so the
        parent space never temporarily contains both gateway-mediated and direct
        copies of the same crossing edge.
        """

        for binding in group.input_bindings.values():
            group.inputs[binding["public_io"]].disconnect()
            group.group_input_node.outputs[binding["gateway_io"]].disconnect()

        for binding in group.output_bindings.values():
            group.group_output_node.inputs[binding["gateway_io"]].disconnect()
            group.outputs[binding["public_io"]].disconnect()

    def ungroup_node(self, group_node_uuid: str) -> List[Node]:
        """Replace one executable `GroupNode` with its internal nodes.

        Args:
          group_node_uuid: UUID of the parent-space `GroupNode` to ungroup.

        Returns:
          The restored inner nodes, excluding the structural gateway nodes.

        Boundary rewiring is the inverse of `group_nodes_as_node`:

        - external output -> group public input plus gateway output -> internal
          input becomes external output -> internal input.
        - internal output -> gateway input plus group public output -> external
          input becomes internal output -> external input.

        Only one layer is ungrouped. If an inner node is itself a `GroupNode`, it
        is moved back to the parent as a normal node and remains grouped
        internally.
        """

        group = self._validate_ungroup_target(group_node_uuid)
        incoming_edges = self._ungroup_input_edges(group)
        outgoing_edges = self._ungroup_output_edges(group)
        restored_nodes = list(group.iter_inner_nodes())

        self._disconnect_group_boundary_edges(group)

        for node in restored_nodes:
            detached = group.inner_nodespace._detach_node_instance_for_grouping(node)
            self.add_node_instance(detached)

        group.inner_nodespace.remove_node_instance(
            group.group_input_node,
            _allow_group_gateway=True,
        )
        group.inner_nodespace.remove_node_instance(
            group.group_output_node,
            _allow_group_gateway=True,
        )
        self.remove_node_instance(group)

        for internal_output, external_input in outgoing_edges:
            internal_output.connect(external_input)
        for external_output, internal_input in incoming_edges:
            external_output.connect(internal_input)

        return restored_nodes

    # endregion executable grouping

    # region edges
    # region add/remove edges
    # endregion add/remove edges
    # endregion edges

    # region lib
    @emit_after()
    def add_shelf(self, shelf: Shelf):
        """
        Adds a shelf to the nodespace's library.

        Args:
          shelf (Shelf): The shelf to add.

        Returns:
          Library: The updated library.
        """
        self.lib.add_shelf(shelf)
        return self.lib

    @emit_after()
    def remove_shelf(self, shelf: Shelf, with_nodes=True):
        """
        Removes a shelf from the nodespace's library.
        This also removes all nodes in the shelf from the nodespace if they are not used in other shelves.

        Args:
          shelf (Shelf): The shelf to remove.
            with_nodes (bool): Whether to remove the nodes in the shelf from the nodespace. Defaults to True.

        Returns:
          Library: The updated library.
        """

        self.lib.remove_shelf(shelf)
        if with_nodes:
            nodes, _ = flatten_shelf(shelf)

            for node in nodes:
                try:
                    self.lib.get_node_by_id(node.node_id)
                except NodeClassNotFoundError:
                    for nodespacenode in self.nodes:
                        if nodespacenode.node_id == node.node_id:
                            self.remove_node_instance(nodespacenode)
        return self.lib

    # endregion lib
    async def await_done(
        self,
    ):
        """await_done waits until all nodes are done"""
        return await run_until_complete(*self.nodes)


def nodespaceendcoder(obj, preview=False):
    if isinstance(obj, NodeSpace):
        return Encdata(
            data={
                "nodes": JSONEncoder.apply_custom_encoding(obj.nodes, preview=False),
                "prop": JSONEncoder.apply_custom_encoding(
                    obj._properties, preview=False
                ),
                "lib": JSONEncoder.apply_custom_encoding(obj.lib, preview=False),
                "edges": JSONEncoder.apply_custom_encoding(
                    obj.serialize_edges(), preview=False
                ),
            },
            handeled=True,
            done=True,
        )
    return Encdata(data=obj, handeled=False)


JSONEncoder.add_encoder(nodespaceendcoder)
