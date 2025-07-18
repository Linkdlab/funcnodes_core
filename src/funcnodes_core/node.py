from __future__ import annotations
import gc
from typing import (
    Dict,
    Type,
    Optional,
    TypedDict,
    List,
    NotRequired,
    Literal,
    Tuple,
    Any,
    TYPE_CHECKING,
)
from abc import ABC, ABCMeta, abstractmethod
import asyncio
import inspect
from uuid import uuid4
from weakref import WeakValueDictionary, ref
import time
from enum import IntFlag, auto

from funcnodes_core.utils.wrapper import NoOverrideMixin, savemethod, saveproperty
from .exceptions import (
    IONotFoundError,
    InTriggerError,
    NodeIdAlreadyExistsError,
    NodeKeyError,
    NodeReadyError,
)
from .io import (
    NodeInput,
    NodeOutput,
    NoValue,
    NodeInputStatus,
    NodeOutputStatus,
    NodeInputSerialization,
    NodeOutputSerialization,
    FullNodeIOJSON,
    NodeIOSerialization,
    NodeIOClassSerialization,
    IORenderOptions,
    NodeInputOptions,
    NodeOutputOptions,
    InputReadyState,
)
from .triggerstack import TriggerStack
from .eventmanager import (
    AsyncEventManager,
    MessageInArgs,
    emit_before,
    emit_after,
    EventEmitterMixin,
)
from .utils.serialization import JSONEncoder

from .utils.data import (
    deep_fill_dict,
)
from .utils.nodeutils import run_until_complete
from .utils.nodetqdm import NodeTqdm, TqdmState, tqdm
from funcnodes_core._logging import get_logger, FUNCNODES_LOGGER
from .config import get_config

if TYPE_CHECKING:
    from .nodespace import NodeSpace


triggerlogger = get_logger("trigger")


class NodeTriggerError(Exception):
    @classmethod
    def from_error(cls, error: Exception):
        return cls(str(error)).with_traceback(error.__traceback__)


def _get_nodeclass_inputs(node: Type[Node] | Node) -> Dict[str, NodeInput]:
    """
    Iterates over the attributes of a Node instance and returns the ones that are instances of NodeInput.

    Args:
        node (Node): The instance of the Node to parse.

    Returns:
        List[NodeInput]: The list of NodeInput instances found in the node.
    """
    inputs: Dict[str, NodeInput] = {}
    nodeclass = node if isinstance(node, type) else node.__class__
    classattr = list(nodeclass.__dict__.keys())
    for attr_name in dir(node):
        if attr_name not in classattr:
            classattr.append(attr_name)

    for attr_name in classattr:
        try:
            attr = getattr(node, attr_name)
            if isinstance(attr, NodeInput):
                inputs[attr_name] = attr
        except AttributeError:
            pass
    return inputs


def _get_nodeclass_outputs(node: Type[Node] | Node) -> Dict[str, NodeOutput]:
    """
    Iterates over the attributes of a Node instance and returns the ones that are instances of NodeOutput.

    Args:
        node (Node): The instance of the Node to parse.

    Returns:
        List[NodeOutput]: The list of NodeOutput instances found in the node.
    """
    outputs: Dict[str, NodeOutput] = {}
    nodeclass = node if isinstance(node, type) else node.__class__
    classattr = list(nodeclass.__dict__.keys())
    for attr_name in dir(node):
        if attr_name not in classattr:
            classattr.append(attr_name)

    for attr_name in classattr:
        try:
            attr = getattr(node, attr_name)
            if isinstance(attr, NodeOutput):
                outputs[attr_name] = attr
        except AttributeError:
            pass
    return outputs


def _parse_nodeclass_io(node: Node):
    """
    Iterates over the attributes of a Node instance and parses the ones that are instances of NodeInput or NodeOutput.
    It then adds these as inputs or outputs to the class instance.

    Args:
        node (Node): The instance of the Node to parse.

    Returns:
        None
    """
    inputs = _get_nodeclass_inputs(node)

    outputs = _get_nodeclass_outputs(node)
    for ipid, ip in inputs.items():
        ser: NodeInputOptions = ip.to_dict()
        node_io_render: NodeInputSerialization = node.render_options.get("io", {}).get(
            ip.uuid, {}
        )

        node_io_options: NodeInputOptions = node.io_options.get(ip.uuid, {})

        if node_io_render:
            deep_fill_dict(
                ser["render_options"], node_io_render, overwrite_existing=True
            )

        if node_io_options:
            deep_fill_dict(ser, node_io_options, overwrite_existing=True)

        node.add_input(
            NodeInput(
                **ser,
                class_default=ip.default,
            )
        )

    for opid, op in outputs.items():
        ser: NodeOutputOptions = op.to_dict()
        node_io_render: NodeOutputSerialization = node.render_options.get("io", {}).get(
            op.uuid, {}
        )
        node_io_options: NodeInputOptions = node.io_options.get(op.uuid, {})

        if node_io_render:
            deep_fill_dict(
                ser["render_options"], node_io_render, overwrite_existing=True
            )

        if node_io_options:
            deep_fill_dict(ser, node_io_options, overwrite_existing=True)

        node.add_output(
            NodeOutput(
                **ser,
            )
        )


class NodeMeta(ABCMeta):
    def __new__(  # pylint: disable=bad-mcs-classmethod-argument
        mcls,  # type: ignore
        name,
        bases,
        namespace,
        /,
        **kwargs,
    ):
        """
        Construct and return a new `Node` object. This is the metaclass for all Node types.
        This custom implementation of `__new__` is designed to automatically register the new class
        in a registry for Node types.

        Args:
            mcls: The metaclass instance.
            name (str): The name of the new class.
            bases (Tuple[type, ...]): A tuple of the base classes for the new class.
            namespace (Dict[str, Any]): The namespace containing the definitions for the new class.
            /: Indicates that the preceding arguments are positional-only.
            **kwargs: Extra keyword arguments.

        Returns:
            Type[Node]: A new class object of type Node.

        Raises:
            TypeError: If the new class is not a subclass of `Node`.
            NameError: If the class is `Node` itself and not an instance of it.
        """
        # Create the new class by invoking the superclass's `__new__` method.
        new_cls: Type[Node] = super().__new__(
            mcls,
            name,
            bases,
            namespace,
            **kwargs,  # type: ignore
        )

        try:
            if not issubclass(new_cls, Node):
                raise TypeError("NodeMeta can only be used with Node subclasses")
            # Register the new class in the global registry of node classes.
            if (
                not inspect.isabstract(new_cls)
                or new_cls.__dict__.get("node_id") is not None
            ):
                register_node(new_cls)
        except NameError:
            # This block catches the `NameError` that is thrown when `Node` is being defined.
            # Since `Node` itself is not yet defined when it's being created, it's normal to
            # get a `NameError` here. We ignore it unless the name is not 'Node'.
            if (
                name != "Node"
            ):  # pragma: no cover (this check probably isn't needed and cannot be tested)
                raise  # pragma: no cover (this check probably isn't needed and cannot be tested)

        return new_cls


class RenderOptionsData(IORenderOptions, total=False):
    src: str


class RenderOptions(TypedDict, total=False):
    data: RenderOptionsData
    io: Dict[str, IORenderOptions]


class NodeClassDict(TypedDict, total=False):
    node_id: str
    node_name: str
    default_reset_inputs_on_trigger: Optional[bool]
    description: Optional[str]
    default_render_options: Optional[RenderOptions]
    default_trigger_on_create: Optional[bool]
    default_io_options: Optional[Dict[str, NodeInputOptions | NodeOutputOptions]]
    __doc__: Optional[str]


NodeClassDictKeysValues = Literal[
    "node_id",
    "node_name",
    "default_reset_inputs_on_trigger",
    "description",
    "default_render_options",
    "default_trigger_on_create",
    "default_io_options",
]
NodeClassDictsKeys: List[NodeClassDictKeysValues] = [
    "node_id",
    "node_name",
    "default_reset_inputs_on_trigger",
    "description",
    "default_render_options",
    "default_trigger_on_create",
    "default_io_options",
]


class NodeConstants:
    TRIGGER_SPEED_FAST = 0.2
    TRIGGER_SPEED_MEDIUM = 1


class NodeFlags(IntFlag):
    TRIGGER_SPEED_FAST = auto()
    TRIGGER_SPEED_MEDIUM = auto()
    TRIGGER_SPEED_SLOW = auto()


class Node(NoOverrideMixin, EventEmitterMixin, ABC, metaclass=NodeMeta):
    """
    The base class for all nodes, making use of the custom metaclass `NodeMeta` to handle
    automatic registration. It inherits from `EventEmitterMixin` for event handling capabilities
    and from `ABC` to allow abstract methods, making it suitable for creating a variety of node types.
    """

    node_id: str
    node_name: str
    default_reset_inputs_on_trigger: bool = False
    description: Optional[str] = None

    default_render_options: RenderOptions = {}
    default_io_options: Dict[str, NodeInputOptions | NodeOutputOptions] = {}
    default_trigger_on_create: bool = True

    default_pretrigger_delay = float(
        get_config()["nodes"]["default_pretrigger_delay"]
    )  # 10ms

    _triggerinput = NodeInput(
        id="_triggerinput",
        name="( )",
        description="Trigger the node",
        default=None,
        required=False,
        hidden=True,
        emit_value_set=False,
    )
    _triggeroutput = NodeOutput(
        uuid="_triggeroutput",
        name="➡",
        description="Node was triggered",
        hidden=True,
        emit_value_set=False,
    )

    _class_io_serialized: Dict[str, NodeIOSerialization]

    @abstractmethod
    async def func(self, *args, **kwargs):
        """The function to be executed when the node is triggered."""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        ips = _get_nodeclass_inputs(cls)
        ops = _get_nodeclass_outputs(cls)

        cls._class_io_serialized: Dict[str, NodeIOSerialization] = {}

        for ipsid, ip in ips.items():
            if ip.uuid.startswith("_"):
                if ip.name == ip._uuid:
                    ip.name = ipsid
                ip._uuid = ipsid

        for opsid, op in ops.items():
            if op.uuid.startswith("_"):
                if op.name == op._uuid:
                    op.name = opsid
                op._uuid = opsid

        for io in list(ips.values()) + list(ops.values()):
            ipser = io.serialize()
            # check if it is present in the previous
            while ipser["id"] in cls._class_io_serialized:
                io._uuid = io.uuid + "_"

                FUNCNODES_LOGGER.warning(
                    "IO with id %s already exists in %s. Changing id to %s",
                    ipser["id"],
                    cls,
                    io.uuid,
                )
                ipser = ip.to_dict()

            cls._class_io_serialized[ipser["id"]] = ipser

    def __init__(
        self,
        uuid: Optional[str] = None,
        reset_inputs_on_trigger: Optional[bool] = None,
        name: Optional[str] = None,
        id: Optional[str] = None,  # fallback for uuid
        render_options: Optional[RenderOptions] = None,
        io_options: Optional[Dict[str, NodeInputOptions | NodeOutputOptions]] = None,
        trigger_on_create: Optional[bool] = None,
        pretrigger_delay: Optional[float] = None,
        properties: Optional[Dict[str, Any]] = None,
    ):
        super().__init__()
        self._properties = properties if isinstance(properties, dict) else {}
        self._inputs: List[NodeInput] = []
        self._inputs_dict: Optional[Dict[str, NodeInput]] = None
        self._outputs: List[NodeOutput] = []
        self._outputs_dict: Optional[Dict[str, NodeOutput]] = None
        self._triggerstack: Optional[TriggerStack] = None
        # flag whether the trigger has started but still not read the ios
        self._trigger_open = False
        self._requests_trigger = False
        self.asynceventmanager = AsyncEventManager(self)
        if uuid is None and id is not None:
            uuid = id
        self._uuid = uuid or uuid4().hex
        self._reset_inputs_on_trigger = reset_inputs_on_trigger
        self._pretrigger_delay = (
            float(pretrigger_delay)
            if pretrigger_delay is not None and float(pretrigger_delay) >= 0
            else float(self.default_pretrigger_delay)
        )
        self._name = name or f"{self.__class__.__name__}({self.uuid})"
        self._render_options = deep_fill_dict(
            render_options or RenderOptions(),  # type: ignore
            self.default_render_options,  # type: ignore
        )
        self._nodespace: ref[NodeSpace] = None

        self._io_options: Dict[str, NodeInputOptions | NodeOutputOptions] = (
            deep_fill_dict(
                io_options or {},  # type: ignore
                self.default_io_options,  # type: ignore
            )
        )

        self._disabled = False

        self._rolling_tigger_time = NodeConstants.TRIGGER_SPEED_FAST * 1.1
        self._trigger_speed_flag = NodeFlags.TRIGGER_SPEED_MEDIUM
        _parse_nodeclass_io(self)
        if trigger_on_create is None:
            self.trigger_on_create = self.default_trigger_on_create
        else:
            self.trigger_on_create = trigger_on_create
        if self.trigger_on_create:
            if self.ready_to_trigger():
                self.request_trigger()

        if not hasattr(self, "node_name") or self.node_name is None:
            self.node_name = self.__class__.__name__

    @saveproperty
    def pretrigger_delay(self):
        return self._pretrigger_delay

    @pretrigger_delay.setter
    def pretrigger_delay(self, value: float):
        if value is None:
            value = self.default_pretrigger_delay
        value = float(value)
        if value < 0:
            raise ValueError("Pretrigger delay cannot be negative")
        self._pretrigger_delay = value

    @saveproperty
    def progress(self) -> Type[tqdm]:
        return lambda *args, **kwargs: NodeTqdm(
            *args, broadcast_func=self._broadcast_progress, **kwargs
        )

    def _broadcast_progress(self, info: TqdmState):
        msg = MessageInArgs(src=self, info=info)
        self.emit("progress", msg)

    @saveproperty
    def properties(self):
        return self._properties

    def set_property(self, key: str, value: Any):
        self._properties[key] = value

    def get_property(self, key: str, default: Any = None):
        return self._properties.get(key, default)

    # region serialization
    @classmethod
    def serialize_cls(cls) -> SerializedNodeClass:
        """Serializes the node class into a dictionary."""
        ser = SerializedNodeClass(
            node_id=cls.node_id,
            inputs=[
                ip.serialize_class()
                for ip in _get_nodeclass_inputs(cls).values()
                if ip.uuid != "_triggerinput"
            ],
            outputs=[
                op.serialize_class()
                for op in _get_nodeclass_outputs(cls).values()
                if op.uuid != "_triggeroutput"
            ],
            description=cls.description,
            node_name=getattr(cls, "node_name", cls.__name__),
        )
        if cls.default_reset_inputs_on_trigger != Node.default_reset_inputs_on_trigger:
            ser["reset_inputs_on_trigger"] = cls.default_reset_inputs_on_trigger

        return ser

    def full_serialize(self, with_io_values=False) -> FullNodeJSON:
        ser: FullNodeJSON = {
            "name": self.name,
            "id": self.uuid,
            "node_id": self.node_id,
            "io": [
                iod.full_serialize(with_value=with_io_values)
                for iod in self._inputs + self._outputs
            ],
            "status": self.status(),
            "node_name": self.node_name,
            "description": self.description,
            "reset_inputs_on_trigger": self.reset_inputs_on_trigger,
        }

        renderopt = self.render_options
        if renderopt:
            ser["render_options"] = renderopt
        properties = self.properties
        if properties:
            ser["properties"] = properties
        return ser

    def deserialize(self, data: NodeJSON):
        """
        Deserializes a node from a json serializable dict.

        Args:
            data (NodeJSON): The data to deserialize

        Returns:
            None
        """
        if data["node_id"] != self.node_id:
            raise ValueError(
                f"Node id {data['node_id']} does not match node class id {self.node_id}"
            )

        if "name" in data:
            self._name = data["name"]
        if "id" in data:
            self._uuid = data["id"]
        if "reset_inputs_on_trigger" in data:
            self._reset_inputs_on_trigger = data["reset_inputs_on_trigger"]

        if "io" in data:
            for iod in self._inputs + self._outputs:
                if iod.uuid in data["io"]:
                    iod.deserialize(data["io"][iod.uuid])  # type: ignore

        if "description" in data and data["description"]:
            self.description = data["description"]

        if "render_options" in data:
            self._render_options = deep_fill_dict(
                data["render_options"],  # type: ignore
                self._render_options,  # type: ignore
            )

        if "properties" in data:
            self._properties = {
                **self._properties,
                **data["properties"],
            }

        if self.trigger_on_create:
            if self.ready_to_trigger():
                self.request_trigger()

    def serialize(self, drop=True) -> NodeJSON:
        """
        returns a json serializable dict of the node
        """

        ser = NodeJSON(
            name=self.name,
            id=self.uuid,
            node_id=self.node_id,
            node_name=self.node_name,
            io={},
        )

        for iod in self._inputs + self._outputs:
            if iod.uuid == "_triggerinput" or iod.uuid == "_triggeroutput":
                continue
            ioser = dict(iod.serialize(drop=drop))
            if drop:
                del ioser["id"]

                cls_ser = None
                if iod.uuid in self._class_io_serialized:
                    cls_ser = self._class_io_serialized[iod.uuid]

                if cls_ser:
                    if "description" in ioser:
                        if ioser["description"] == cls_ser.get("description", ""):
                            del ioser["description"]

                    if "default" in ioser:
                        if ioser["default"] == cls_ser.get("default", NoValue):
                            del ioser["default"]

                    if "type" in ioser:
                        if ioser["type"] == cls_ser.get("type", "Any"):
                            del ioser["type"]

                    if "value_options" in ioser:
                        if ioser["value_options"] == cls_ser.get("value_options", {}):
                            del ioser["value_options"]

                    if "render_options" in ioser:
                        if ioser["render_options"] == cls_ser.get("render_options", {}):
                            del ioser["render_options"]

                    if "default" in ioser:
                        if ioser["default"] == cls_ser.get("default", NoValue):
                            del ioser["default"]

            ser["io"][iod.uuid] = ioser

        if self.reset_inputs_on_trigger != self.default_reset_inputs_on_trigger:
            ser["reset_inputs_on_trigger"] = self.reset_inputs_on_trigger

        if self.description != self.__class__.description:
            ser["description"] = self.description

        renderopt = self.render_options
        if renderopt:
            ser["render_options"] = renderopt

        properties = self.properties
        if properties:
            ser["properties"] = properties

        return ser

    def _repr_json_(self) -> FullNodeJSON:
        return JSONEncoder.apply_custom_encoding(
            self.full_serialize(with_io_values=False)
        )

    # endregion serialization

    # region properties
    @saveproperty
    def uuid(self):
        """The unique identifier of the node."""
        return self._uuid

    @saveproperty
    def name(self):
        """The name of the node."""
        return self._name

    @name.setter
    def name(self, value):
        self._name = value or f"{self.__class__.__name__}({self.uuid})"

    @saveproperty
    def reset_inputs_on_trigger(self):
        """Whether to reset the inputs of the node when it is triggered."""
        return (
            self._reset_inputs_on_trigger
            if self._reset_inputs_on_trigger is not None
            else self.default_reset_inputs_on_trigger
        )

    @reset_inputs_on_trigger.setter
    def reset_inputs_on_trigger(self, value: bool):
        """Sets the reset inputs on trigger flag."""
        if value is None:
            value = self.default_reset_inputs_on_trigger
        if not isinstance(value, bool):
            raise ValueError("reset_inputs_on_trigger must be a boolean")
        self._reset_inputs_on_trigger = value

    @saveproperty
    def render_options(self):
        return self._render_options

    @saveproperty
    def io_options(self):
        return self._io_options

    @saveproperty
    def triggerstack(self) -> Optional[TriggerStack]:
        """The trigger stack associated with the node's execution."""
        return self._triggerstack

    @saveproperty
    def outputs(self) -> Dict[str, NodeOutput]:
        """returns a dictionary of the outputs of this node
        in the format {output.uuid:output}
        """
        if self._outputs_dict is None:
            self._outputs_dict = {op.uuid: op for op in self._outputs}

        return self._outputs_dict

    @saveproperty
    def o(self) -> Dict[str, NodeOutput]:
        """short for self.outputs"""
        return self.outputs

    @saveproperty
    def inputs(self) -> Dict[str, NodeInput]:
        """returns a dictionary of the inputs of this node
        in the format {input.uuid:input}
        """
        if self._inputs_dict is None:
            self._inputs_dict = {ip.uuid: ip for ip in self._inputs}
        return self._inputs_dict

    @saveproperty
    def i(self) -> Dict[str, NodeInput]:
        """short for self.inputs"""
        return self.inputs

    @saveproperty
    def in_trigger(self):
        """Whether the node is currently in a trigger state.
        checked if the triggerstack is not None and if it is done
        or if the _trigger_open flag is set
        """
        if self._triggerstack is not None:
            if self._triggerstack.done():
                self._triggerstack = None
        return self._triggerstack is not None or self._trigger_open

    @saveproperty
    def disabled(self) -> bool:
        """Getter and setter for the node disabled state.
        Parameters
        ----------
        value: bool
            The new disabled state
        Returns
        -------
        bool: The node disabled state
        """
        return self._disabled

    @emit_after()
    def set_nodespace(self, nodespace: NodeSpace):
        """Sets the node's nodespace"""
        if nodespace is None:
            self._nodespace = None
        else:
            self._nodespace = ref(nodespace)

    @saveproperty
    def nodespace(self) -> NodeSpace | None:
        """Getter for the node's nodespace"""
        if self._nodespace is None:
            return None
        return self._nodespace()

    @nodespace.setter
    def nodespace(self, value: NodeSpace | None):
        """Setter for the node's nodespace"""
        self.set_nodespace(value)

    # endregion properties

    # region node methods
    @savemethod
    def ready(self) -> bool:
        """Whether the node is ready"""
        return self.inputs_ready()

    @savemethod
    def ready_state(self) -> NodeReadyState:
        """Returns the ready state of the node"""
        return {
            "inputs": {ip.uuid: ip.ready_state() for ip in self._inputs},
        }

    @savemethod
    def ready_to_trigger(self):
        """Whether the node is ready to be triggered"""
        # check wherer a running eventloop is present
        try:
            _ = asyncio.get_running_loop()
        except RuntimeError:
            return False
        return self.ready() and not self.in_trigger

    @property
    def will_trigger(self) -> bool:
        """Whether the node will trigger when the trigger input is set."""
        if self.ready_to_trigger() and self._requests_trigger:
            return True

    @property
    def in_trigger_soon(self) -> bool:
        return self.in_trigger or self.will_trigger

    def __str__(self) -> str:
        """Returns a string representation of the node."""
        return f"{self.__class__.__name__}({self.uuid})"

    def status(self) -> NodeStatus:
        """Returns a dictionary containing the status of the node."""
        return NodeStatus(
            ready=self.ready(),
            ready_state=self.ready_state(),
            in_trigger=self.in_trigger,
            requests_trigger=self._requests_trigger,
            inputs={ip.uuid: ip.status() for ip in self._inputs},
            outputs={op.uuid: op.status() for op in self._outputs},
        )

    @saveproperty
    def is_working(self) -> bool:
        """Getter for the node working state.
        Returns
        -------
        bool: The node working state
        """

        if self.in_trigger:
            return True

        return False

    # endregion node methods

    # region input/output methods

    def add_input(self, node_input: NodeInput):
        """
        Adds a NodeInput object to the node's inputs and sets it as an attribute of the node.

        Args:
            node_input (NodeInput): The NodeInput object to add.

        Returns:
            None
        """
        ipid = node_input.uuid
        if ipid in map(lambda x: x.uuid, self._inputs):
            raise ValueError(f"Input with id {ipid} already exists")
        node_input.on("*", self.on_nodeio_event)
        self._inputs.append(node_input)
        node_input.node = self
        self._inputs_dict = None

    def remove_input(self, node_input: NodeInput):
        """
        Removes a NodeInput object from the node's inputs and unsets it as an attribute of the node.

        Args:
            node_input (NodeInput): The NodeInput object to remove.

        Returns:
            None
        """
        if node_input not in self._inputs:
            raise ValueError(f"Input with id {node_input.uuid} not found")
        node_input.off("*", self.on_nodeio_event)
        self._inputs.remove(node_input)
        self._inputs_dict = None

    def add_output(self, node_output: NodeOutput):
        """
        Adds a NodeOutput object to the node's outputs and sets it as an attribute of the node.

        Args:
            node_output (NodeOutput): The NodeOutput object to add.

        Returns:
            None
        """
        opid = node_output.uuid
        if opid in map(lambda x: x.uuid, self._outputs):
            raise ValueError(f"Output with id {opid} already exists")
        node_output.on("*", self.on_nodeio_event)
        node_output.node = self
        self._outputs.append(node_output)
        self._outputs_dict = None

    def remove_output(self, node_output: NodeOutput):
        """
        Removes a NodeOutput object from the node's outputs and unsets it as an attribute of the node.

        Args:
            node_output (NodeOutput): The NodeOutput object to remove.

        Returns:
            None
        """
        if node_output not in self._outputs:
            raise ValueError(f"Output with id {node_output.uuid} not found")
        node_output.off("*", self.on_nodeio_event)
        self._outputs.remove(node_output)
        self._outputs_dict = None

    def on_nodeio_event(self, event: str, src: NodeInput | NodeOutput, **data):
        """
        Handles events emitted by the node's inputs and outputs.

        Args:
            event (str): The event name.
            src (NodeInput | NodeOutput): The source of the event.
            **data: The event data.

        Returns:
            None
        """
        msg = {"io": src.uuid, **data}
        self.emit(event, msg)

    def inputs_ready(self):
        """Whether all the node's inputs are ready."""
        return all(map(lambda x: x.ready(), self._inputs))

    def get_input(self, uuid: str) -> NodeInput:
        """Returns the input with the given uuid.

        Args:
            uuid (str): The uuid of the input to return.

        Returns:
            NodeInput: The input with the given uuid.
        """
        for ip in self._inputs:
            if ip.uuid == uuid:
                return ip
        raise IONotFoundError(f"Input with uuid {uuid} not found")

    def get_output(self, uuid: str) -> NodeOutput:
        """Returns the output with the given uuid.

        Args:
            uuid (str): The uuid of the output to return.

        Returns:
            NodeOutput: The output with the given uuid.
        """
        for op in self._outputs:
            if op.uuid == uuid:
                return op
        raise IONotFoundError(f"Output with uuid {uuid} not found")

    def get_input_or_output(self, uuid: str) -> NodeInput | NodeOutput:
        """Returns the input or output with the given uuid.

        Args:
            uuid (str): The uuid of the input or output to return.

        Returns:
            NodeInput | NodeOutput: The input or output with the given uuid.
        """

        try:
            return self.get_input(uuid)
        except IONotFoundError:
            pass
        try:
            return self.get_output(uuid)
        except IONotFoundError:
            pass
        raise IONotFoundError(f"Input or Output with uuid {uuid} not found")

    # endregion input/output methods

    # region triggering

    @savemethod
    async def __call__(self) -> asyncio.Task:
        """
        Executes the node's function asynchronously and returns an asyncio.Task object.
        This method also handles the triggering of events before and after the function execution.

        Returns:
            asyncio.Task: The task object representing the asynchronous operation of the node's function.
        """

        # set the trigger event
        # just in case we set the flag again, this is the last time before the trigger
        # that inupts can be changed and be respected
        self._trigger_open = True
        pbar = None
        try:
            await self.asynceventmanager.set_and_clear("triggered")

            if self._trigger_speed_flag == NodeFlags.TRIGGER_SPEED_FAST:
                self.emit("triggerfast")
            else:
                pbar = self.progress(total=None, desc="triggering")
                self.emit("triggerstart")

            if self._pretrigger_delay > 0:
                await asyncio.sleep(self._pretrigger_delay)
            # no more changes please
            self._trigger_open = False

            # split into two assignes that ip.value does not have to be called twice
            kwargs = {ip.uuid: ip.value for ip in self._inputs}
            kwargs = {k: v for k, v in kwargs.items() if v is not NoValue}

            err = None
            _tigger_start_time = time.perf_counter()
            if "_triggerinput" in kwargs:
                del kwargs["_triggerinput"]
            try:
                # run the function
                ans = await self.func(**kwargs)
                # reset the inputs if requested
                if self.reset_inputs_on_trigger:
                    for ip in self._inputs:
                        ip.set_value(ip.default, does_trigger=False)
                # pbar.update(1)
                _trigger_time = time.perf_counter() - _tigger_start_time
                self._rolling_tigger_time = (
                    _trigger_time
                    if self._rolling_tigger_time is None
                    else (0.9 * self._rolling_tigger_time + 0.1 * _trigger_time)
                )
                self.outputs["_triggeroutput"].set_value(time.time())
                if pbar is not None:
                    pbar.set_description_str("idle", refresh=False)
            except Exception as e:
                triggerlogger.exception(e)
                err = e

            if self._trigger_speed_flag != NodeFlags.TRIGGER_SPEED_FAST:
                self.emit("triggerdone")

            if self._rolling_tigger_time <= NodeConstants.TRIGGER_SPEED_FAST:
                self._trigger_speed_flag = NodeFlags.TRIGGER_SPEED_FAST
            elif self._rolling_tigger_time <= NodeConstants.TRIGGER_SPEED_MEDIUM:
                self._trigger_speed_flag = NodeFlags.TRIGGER_SPEED_MEDIUM
            else:
                self._trigger_speed_flag = NodeFlags.TRIGGER_SPEED_SLOW
            # set the triggerdone event

            if err:
                self.error(NodeTriggerError.from_error(err))
                ans = err
            return ans
        finally:
            if pbar is not None:
                pbar.close()
            await self.asynceventmanager.set_and_clear("triggerdone")

    def trigger_if_requested(self, triggerstack: Optional[TriggerStack] = None) -> bool:
        """
        Triggers the node if it is ready to be triggered and a trigger has been requested.

        Args:
            triggerstack (Optional[TriggerStack]): The trigger stack to use for the operation, if any.

        Returns:
            bool: Whether the node was triggered.
        """
        if self._requests_trigger and self.ready_to_trigger():
            self.trigger(triggerstack)
            return True
        return False

    @emit_before()
    @emit_after()
    def request_trigger(self):
        """Requests the node to be triggered.
        If the node is ready to trigger, it triggers it, otherwise it sets the _requests_trigger attribute to True.
        """
        # if the node is ready to trigger, trigger it
        if self.ready_to_trigger():
            self.trigger()

        # if the node is about to trigger, but still not read the ios
        elif self._trigger_open:
            return
        else:
            # otherwise set the _requests_trigger attribute to True
            self._requests_trigger = True

    @savemethod
    async def await_trigger(self):
        """
        Asynchronously waits for the node to be ready to trigger and then triggers it
        or if node is in trigger waits for the trigger process to finish.

        Returns:
            The result of the trigger operation.
        """
        # if the node is ready to trigger, trigger it
        if self.ready_to_trigger():
            return await self.trigger()
        else:
            self._requests_trigger = True

        # wait for the trigger process to finish
        await self.asynceventmanager.wait("triggered")
        a = await self._triggerstack
        return a

    @savemethod
    async def wait_for_trigger_finish(self):
        if self.in_trigger:
            await self.asynceventmanager.wait("triggerdone")

    @savemethod
    async def await_until_complete(self):
        """
        Asynchronously runs the node until completion.
        """
        return await run_until_complete(self)

    @savemethod
    def __await__(self):
        """
        Allows an instance of Node to be awaited. This will request the node to be triggered and
        waits for the trigger process to finish.
        Yields:
            The result of awaiting the last task in the stack.
        """
        self.request_trigger()
        return run_until_complete(self).__await__()

    @savemethod
    @emit_before()
    @emit_after()
    def trigger(self, triggerstack: Optional[TriggerStack] = None) -> TriggerStack:
        """
        Triggers the node's execution. If the node is already in a trigger state, it raises an InTriggerError.

        Args:
            triggerstack (Optional[TriggerStack]): The trigger stack to use for the operation, if any.

        Returns:
            TriggerStack: The trigger stack associated with the node's execution.

        Raises:
            InTriggerError: If the node is already in a trigger state.
        """
        if self.in_trigger:
            raise InTriggerError("Node is already in trigger")
        if triggerstack is None:
            triggerstack = TriggerStack()

        triggerlogger.debug("triggering %s", self)
        self._trigger_open = True
        self._triggerstack = triggerstack
        self._triggerstack.append(asyncio.create_task(self()))
        self._requests_trigger = False
        return self._triggerstack

    # endregion triggering
    def cleanup(self):
        self.emit("cleanup")
        for ip in list(self._inputs):
            self.remove_input(ip)
        self._inputs.clear()
        for op in list(self._outputs):
            self.remove_output(op)

        super().cleanup()

    def __del__(self):
        self.cleanup()

    def __getitem__(self, item):
        return self.get_input_or_output(item)

    def __setitem__(self, key, value):
        if key in self.inputs:
            self.inputs[key].value = value
        elif key in self.outputs:
            self.outputs[key].value = value
        else:
            raise KeyError(f"No input or output named '{key}' found.")

    @classmethod
    async def inti_call(
        cls,
        /,
        node_init_kwargs: Optional[Dict[str, Any]] = None,
        return_dict: bool = False,
        raise_ready: bool = True,
        **kwargs,
    ):
        node = cls(**(node_init_kwargs or {}))
        for k, v in kwargs.items():
            node.inputs[k].value = v
        if not node.ready() and raise_ready:
            raise NodeReadyError(f"Node is not ready to trigger {node.status()}")
        await node

        if return_dict:
            return {op.uuid: op.value for op in node._outputs}

        returns = tuple(
            [op.value for op in node._outputs if op._uuid != "_triggeroutput"]
        )
        if len(returns) == 0:
            return None
        if len(returns) == 1:
            return returns[0]
        return returns


class NodeReadyState(TypedDict):
    """A dictionary containing the ready state of a node"""

    inputs: Dict[str, InputReadyState]


class NodeStatus(TypedDict):
    """A dictionary containing the status of a node.

    Attributes:
        ready (bool): Whether the node is ready.
        in_trigger (bool): Whether the node is in trigger.
        requests_trigger (bool): Whether the node requests a trigger.
        inputs (Dict[str, NodeInputStatus]): The status of the node's inputs.
        outputs (Dict[str, NodeOutputStatus]): The status of the node's outputs.

    """

    ready: bool
    ready_state: NodeReadyState
    in_trigger: bool

    requests_trigger: bool
    inputs: Dict[str, NodeInputStatus]
    outputs: Dict[str, NodeOutputStatus]


class BaseNodeJSON(TypedDict):
    node_id: str
    node_name: str


class SerializedNodeClass(BaseNodeJSON, total=False):
    """A dictionary containing the serialized data of a node.

    Attributes:
        node_id (str): The id of the node.
        node_name (str): The name of the node.
        inputs (Dict[str, NodeInput]): The inputs of the node.
        outputs (Dict[str, NodeOutput]): The outputs of the node.
        description (Optional[str]): The description of the node.
        reset_inputs_on_trigger (bool): Whether to reset the inputs of the node when it is triggered.
    """

    inputs: List[NodeIOClassSerialization]
    outputs: List[NodeIOClassSerialization]
    description: Optional[str]
    reset_inputs_on_trigger: Optional[bool]
    trigger_on_create: bool


class NodeJSON(BaseNodeJSON):
    name: str
    id: str
    io: Dict[str, NodeIOSerialization]
    reset_inputs_on_trigger: NotRequired[Optional[bool]]
    description: NotRequired[Optional[str]]
    render_options: NotRequired[RenderOptions]


class FullNodeJSON(BaseNodeJSON):
    name: str
    id: str
    io: List[FullNodeIOJSON]
    status: NodeStatus
    render_options: NotRequired[RenderOptions]
    reset_inputs_on_trigger: NotRequired[Optional[bool]]
    properties: NotRequired[Dict[str, Any]]


# region node registry
REGISTERED_NODES: WeakValueDictionary[str, Type[Node]] = WeakValueDictionary()
ALLOW_REGISTERED_NODES_OVERRIDE = False


def _get_node_src(node: Type[Node]) -> str:
    try:
        file = inspect.getfile(node)
    except Exception:
        file = "<unknown file>"
    try:
        line = inspect.getsourcelines(node)[1]
    except Exception:
        line = "<unknown line>"

    try:
        module = node.__module__
    except Exception:
        module = "<unknown module>"
    return f"{module}({file}:{line})"


def register_node(node_class: Type[Node]):
    """
    Registers a node class by adding it to the REGISTERED_NODES dictionary with its 'node_id' as the key.
    If the 'node_id' already exists in the dictionary, it raises a NodeIdAlreadyExistsError.

    Args:
        node_class (Type[Node]): The class of the node to register.

    Raises:
        NodeIdAlreadyExistsError: If a node with the same 'node_id' is already registered.
    """
    node_id = node_class.node_id
    if node_id in REGISTERED_NODES:
        gc.collect()  # collect garbage to remove weak references

    if node_id in REGISTERED_NODES and not ALLOW_REGISTERED_NODES_OVERRIDE:
        old_node = REGISTERED_NODES[node_id]
        allow = (  # same class in same module, so probably the same node
            old_node.__module__ + old_node.__name__
            == node_class.__module__ + node_class.__name__
        )

        if not allow:
            raise NodeIdAlreadyExistsError(
                f"Node with id '{node_id}' already exists at {_get_node_src(REGISTERED_NODES[node_id])}"
            )

    REGISTERED_NODES[node_id] = node_class


def get_nodeclass(node_id: str) -> Type[Node]:
    """Returns the node class with the given id

    Args:
        node_id (str): The id of the node class to return

    Raises:
        NodeKeyError: If the node with the given id is not registered

    Returns:
        Type[Node]: The node class with the given id
    """
    if node_id not in REGISTERED_NODES:
        raise NodeKeyError(f"Node with id {node_id} not registered")
    return REGISTERED_NODES[node_id]


# endregion node registry


class PlaceHolderNode(Node):
    node_id = "placeholder"
    node_name = "placeholder node"

    async def func(self, *args, **kwargs):
        raise NotImplementedError(
            "This is a placeholder node and should not be triggered"
        )

    def deserialize(self, data: NodeJSON):
        self.node_id = data["node_id"]
        self.node_name = data["node_name"]

        for ip in self._inputs:
            self.remove_input(ip)

        for op in self._outputs:
            self.remove_output(op)

        if "name" in data:
            self._name = data["name"]
        if "id" in data:
            self._uuid = data["id"]
        if "reset_inputs_on_trigger" in data:
            self._reset_inputs_on_trigger = data["reset_inputs_on_trigger"]

        if "io" in data:
            for iod, iodate in data["io"].items():
                if iodate["is_input"]:
                    self.add_input(NodeInput.from_serialized_nodeio(iodate))  # type: ignore
                else:
                    self.add_output(NodeOutput.from_serialized_nodeio(iodate))  # type: ignore

        if "description" in data and data["description"]:
            self.description = data["description"]

        if "render_options" in data:
            self._render_options = deep_fill_dict(
                data["render_options"],  # type: ignore
                self._render_options,  # type: ignore
            )

        if "properties" in data:
            self._properties = {
                **self._properties,
                **data["properties"],
            }


def nodeencoder(obj, preview=False) -> Tuple[Any, bool]:
    """
    Encodes Nodes
    """
    if isinstance(obj, Node):
        ser: FullNodeJSON = obj.full_serialize(with_io_values=False)
        # io values should be serialized as preview
        serios = []
        for iod in ser["io"]:
            serios.append(JSONEncoder.apply_custom_encoding(iod, preview=True))

        ser["io"] = serios

        return ser, True
    return obj, False


JSONEncoder.prepend_encoder(nodeencoder)  # prepand to skip __repr_json__ method
