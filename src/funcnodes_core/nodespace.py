from typing import List, Dict, TypedDict, Tuple, Any
import json
from uuid import uuid4
import traceback

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


class NodeSpaceJSON(TypedDict, total=False):
    """
    NodeSpaceJSON is the interface for the serialization of a NodeSpace
    """

    nodes: List[NodeJSON]
    edges: List[Tuple[str, str, str, str]]
    prop: Dict[str, Any]


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
            self.remove_node_instance(node)
        for node in data:
            try:
                node_cls = self.lib.get_node_by_id(node["node_id"])
            except NodeClassNotFoundError:
                node_cls = PlaceHolderNode
            node_instance = node_cls()
            node_instance.deserialize(node)
            self.add_node_instance(node_instance)

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
        )
        return json.loads(json.dumps(ret, cls=JSONEncoder), cls=JSONDecoder)

    def clear(self):
        """clear removes all nodes and edges from the nodespace"""
        for node in self.nodes:
            self.remove_node_instance(node)

        self._properties = {}

    # endregion serialization

    # region nodes
    # region add/remove nodes

    def add_node_instance(self, node: Node):
        """add_node_instance adds a node instance to the nodespace

        Parameters
        ----------
        node : Node
            the node to add
        """
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
            self.remove_node_instance(src)
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

    def remove_node_instance(self, node: Node) -> str:
        """
        Removes a node instance from the NodeSpace.

        Args:
          node (Node): The node instance to remove.

        Returns:
          str: The UUID of the removed node.
        """
        if node.uuid not in self._nodes:
            raise ValueError(f"node with uuid '{node.uuid}' not found in nodespace")

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
