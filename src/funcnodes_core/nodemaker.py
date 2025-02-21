from __future__ import annotations
from abc import ABC
from typing import Callable, Type, Any, List, Optional, Tuple, Dict
import inspect
from warnings import warn
from exposedfunctionality import assure_exposed_method
from exposedfunctionality.func import ExposedMethodKwargs, ExposedMethodKwargsKeys
from exposedfunctionality.function_parser import ReturnType
from .node import (
    Node,
    NodeClassDictsKeys,
    NodeClassDict,
    _get_nodeclass_inputs,
    NodeMeta,
)
from .io import NodeInput, NodeOutput
from functools import wraps, partial
from .utils.functions import (
    ExecutorWrapper,
    make_run_in_new_thread,
    make_run_in_new_process,
    make_async_if_needed,
)

from weakref import WeakValueDictionary
import warnings

try:
    from typing import Unpack
except ImportError:
    from typing_extensions import Unpack

from ._logging import FUNCNODES_LOGGER


def node_class_maker(
    id: Optional[str] = None,
    func: Callable[..., ReturnType] = None,
    superclass: Type[Node] = Node,
    separate_thread: bool = False,
    separate_process: bool = False,
    **kwargs: Unpack[NodeClassDict],
) -> Type[Node]:
    """
    Creates a node class from a function.

    Args:
      id (str, optional): The id of the node. Defaults to None.
      func (Callable[..., ReturnType], optional): The function to be wrapped. Defaults to None.
      superclass (Type[Node], optional): The superclass of the node. Defaults to Node.
      **kwargs (Unpack[NodeClassDict]): Keyword arguments for the node class.

    Returns:
      Type[Node]: The created node class.

    Raises:
      ValueError: If the superclass is not a subclass of Node.
      ValueError: If the node_id is not set.
    """
    if superclass != Node and not issubclass(superclass, Node):
        raise ValueError("superclass must be a subclass of Node")

    if "node_id" not in kwargs:
        if id is None:
            raise ValueError("node_id not set")
        else:
            kwargs["node_id"] = id
    in_func = assure_exposed_method(func)

    if separate_process and separate_thread:
        raise ValueError("separate_thread and separate_process cannot both be True")

    inputs = [
        NodeInput.from_serialized_input(ip)
        for ip in in_func.ef_funcmeta["input_params"]
        if ip["name"] != "node"
    ]

    requires_node_input = any(
        ip["name"] == "node" for ip in in_func.ef_funcmeta["input_params"]
    )

    outputs = [
        NodeOutput.from_serialized_output(op)
        for op in in_func.ef_funcmeta["output_params"]
    ]

    if separate_process:
        asyncfunc = make_run_in_new_process(in_func)
    elif separate_thread:
        asyncfunc = make_run_in_new_thread(in_func)
    else:
        asyncfunc = make_async_if_needed(in_func)

    @wraps(asyncfunc)
    async def _wrapped_func(self: Node, *args, **kwargs):
        """
        A wrapper for the exposed function that sets the output values of the node.
        """

        if requires_node_input:
            kwargs["node"] = self

        outs = await asyncfunc(*args, **kwargs)
        if len(outputs) > 1:
            for op, out in zip(outputs, outs):
                self.outputs[op.name].value = out
        elif len(outputs) == 1:
            self.outputs[outputs[0].name].value = outs
        return outs

    kwargs.setdefault("node_name", in_func.ef_funcmeta.get("name", id))
    kwargs.setdefault(
        "description", (in_func.ef_funcmeta.get("docstring") or {}).get("summary", "")
    )
    cls_dict = {"func": _wrapped_func, "o_func": func, **kwargs}

    for ip in inputs:
        cls_dict["input_" + ip.uuid] = ip
    for op in outputs:
        cls_dict["output_" + op.uuid] = op
    try:
        name = "".join(
            x.capitalize()
            for x in in_func.ef_funcmeta.get("name", in_func.__name__)
            .lower()
            .split("_")
        )
    except AttributeError:
        raise
    if name.endswith("node"):
        name = name[:-4]
    if not name.endswith("Node"):
        name += "Node"

    if "__doc__" not in cls_dict:
        cls_dict["__doc__"] = in_func.__doc__

    cls_dict["__module__"] = in_func.__module__

    _Node: Type[Node] = type(
        name,
        (superclass,),
        cls_dict,
    )

    return _Node


class NodeDecoratorKwargs(ExposedMethodKwargs, NodeClassDict, total=False):
    """
    Keyword arguments for the node_class_maker function.
    """

    superclass: Optional[Type[Node]]
    separate_thread: Optional[bool]
    separate_process: Optional[bool]


def NodeDecorator(
    id: Optional[str] = None, **kwargs: Unpack[NodeDecoratorKwargs]
) -> Callable[..., Type[Node]]:
    """Decorator to create a Node class from a function."""

    # Ensure node_id is set
    if "node_id" not in kwargs:
        if id is None:
            raise ValueError("node_id not set")
        else:
            kwargs["node_id"] = id

    def decorator(func: Callable[..., ReturnType]) -> Type[Node]:
        """
        Decorator for creating a Node class from a function.
        """
        # Prepare function and node class arguments
        exposed_method_kwargs: ExposedMethodKwargs = {
            v: kwargs[v]
            for v in ExposedMethodKwargsKeys
            if v in kwargs  # type: ignore
        }
        node_class_kwargs: NodeClassDict = {
            v: kwargs[v]
            for v in NodeClassDictsKeys
            if v in kwargs  # type: ignore
        }

        # Assure the method is exposed for node functionality
        if isinstance(func, ExecutorWrapper):
            _func = func.func
            _func = assure_exposed_method(_func, **exposed_method_kwargs)
            func.ef_funcmeta = _func.ef_funcmeta
            func._is_exposed_method = True

        func = assure_exposed_method(func, **exposed_method_kwargs)

        if "seperate_thread" in kwargs:
            warnings.warn(
                "The 'seperate_thread' argument is deprecated (typo), use 'separate_thread' instead.",
                DeprecationWarning,
            )
        # Create the node class
        return node_class_maker(
            id,
            func,
            superclass=kwargs.get("superclass", Node),
            separate_thread=kwargs.get(
                "separate_thread",
                kwargs.get("seperate_thread", False),
            ),  # fallback for typo in old versions
            separate_process=kwargs.get("separate_process", False),
            **node_class_kwargs,
        )

    return decorator


class NodeClassMixinNodeFunction:
    def __init__(
        self,
        function: Callable[..., ReturnType],
        instance_node_specials: dict,
        **kwargs,
    ):
        kwargs.setdefault("default_trigger_on_create", False)
        self.function = function
        self._node_create_params = kwargs

        self._node_create_params = kwargs
        self._instance_node_specials = instance_node_specials

        self.triggers = trigger_decorator(self)
        # self.nodes = lambda ins: ins.get_nodes(self.function.__name__)
        # self.nodeclass = lambda ins: self.get_nodeclass(self.function.__name__)

    @property
    def name(self):
        return self.function.__name__

    def nodes(self, ins: NodeClassMixin) -> List[Node]:
        return ins.get_nodes(self.name)

    def __call__(self, *args: Any, **kwds: Any) -> Any:
        return self.function(*args, **kwds)


class NodeClassMixinInstanceNodeFunction:
    def __init__(
        self,
        instance: NodeClassMixin,
        function: NodeClassMixinNodeFunction,
    ) -> None:
        self.instance = instance
        self.function = function

    def __call__(self, *args: Any, **kwds: Any) -> Any:
        return self.function(self.instance, *args, **kwds)

    @property
    def name(self):
        return self.function.name

    def create_node(self):
        """
        Creates a new node for a NodeClassMixin method.

        Args:
          nodeclassmixininst (NodeClassMixin): The NodeClassMixin instance.
          method (Callable): The method to be bound to the node class.
          method_name (str): The name of the method.

        Returns:
          None

        Side Effects:
          Adds the node class to the _node_classes dictionary.
        """

        if not isinstance(self.function, NodeClassMixinNodeFunction):
            raise ValueError("method is not a NodeClassMixinNodeFunction")

        # first we define a unique id for the node
        node_id = f"{self.instance.NODECLASSID}.{self.instance.uuid}.{self.name}"

        # hecking if the method is actually in the class
        if getattr(self.instance, self.name) is None:
            raise ValueError("method not found in class")

        # if (
        #     getattr(nodeclassmixininst, method_name).__func__ != method
        # ):  # __func__  is the unbound method
        #     raise ValueError(
        #         "class method is not the same as the method passed to the function:"
        #         f"{getattr(nodeclassmixininst, method_name)}, {method}"
        #     )

        # then we create the node class
        _node_create_params = {
            "id": node_id,
            #        "trigger_on_create": False,
            **self.function._node_create_params,
        }
        _node_create_params["superclass"] = NodeClassNode
        _node_create_params.setdefault(
            "name", self.name.title()
        )  # default name is the method name

        # create a partial method that is bound to the nodeclassmixininst
        partial_method = wraps(self.function.function)(
            partial(self.function.function, self.instance)
        )

        # create the node class
        nodeclass: Type[NodeClassNode] = NodeDecorator(**_node_create_params)(
            partial_method
        )

        if not issubclass(nodeclass, NodeClassNode):
            raise ValueError("node class is not a subclass of NodeClassNode")

        # nodeclass should keep track of its instances:

        # add instances to the class

        self.instance._node_classes[self.name] = nodeclass
        # if the method is called directly on the class, it should also trigger the corresponding nodes
        instance_node_specials = self.function._instance_node_specials
        trigger_on_call = instance_node_specials.get("trigger_on_call", None)
        if trigger_on_call is None:
            trigger_on_call = len(_get_nodeclass_inputs(nodeclass)) == 0

        if trigger_on_call:

            def _trigger_on_call_wrapper(*args, **kwargs):
                """
                A wrapper method that triggers the corresponding nodes when called.


                Returns:
                Any: The result of the original method.

                Side Effects:
                Triggers the corresponding nodes.
                """
                res = self(*args, **kwargs)

                for node in nodeclass._instances.values():  # pylint: disable=protected-access
                    node.request_trigger()
                return res

            setattr(self.instance, self.name, _trigger_on_call_wrapper)

    def nodes(self, instance=None) -> List[Node]:
        if instance is not None:
            warn(
                "instance argument for NodeClassMixinInstanceNodeFunction.nodes is deprecated",
                DeprecationWarning,
            )
        return self.instance.get_nodes(self.name)

    def nodeclass(self, instance=None) -> Type[NodeClassNode]:
        if instance is not None:
            warn(
                "instance argument for NodeClassMixinInstanceNodeFunction.nodeclass is deprecated",
                DeprecationWarning,
            )

        return self.instance.get_nodeclass(self.name)


def instance_nodefunction(
    trigger_on_call: Optional[bool] = None, **kwargs: Unpack[NodeDecoratorKwargs]
):
    """
    Decorator for creating instance node functions.

    Args:
      trigger_on_call (bool, optional): Whether to trigger the node when the
        underlying NodeClassMixin-function is called.
        If None, the node will be triggered if it has no inputs.
        Defaults to None.
      **kwargs (Unpack[NodeDecoratorKwargs]): Keyword arguments for the decorator.

    Returns:
      Callable: The decorated function.

    Raises:
      ValueError: If the function is not an instance_nodefunction.
    """
    kwargs.setdefault("default_trigger_on_create", False)

    def decorator(func):
        """
        Inner decorator for instance_nodefunction.
        """

        return NodeClassMixinNodeFunction(
            func, {"trigger_on_call": trigger_on_call}, **kwargs
        )

    return decorator


def trigger_decorator(target_func: NodeClassMixinNodeFunction):
    """
    A decorator that triggers the corresponding nodes when the function is called.

    Args:
      target_func: A function wrapped in instance_nodefunction.

    Returns:
      Callable: The decorated function.

    Raises:
      ValueError: If the function is not an instance_nodefunction.

    Examples:
      >>> class MyNodeClass(NodeClassMixin):
      >>>   NODECLASSID = "my_node_class"
      >>>
      >>>   @instance_nodefunction
      >>>   def add(self, a, b):
      >>>     return a + b
      >>>
      >>>   @add.triggers
      >>>   def eval(self, a, b):
      >>>     # calling this function will trigger the add nodes for this instance
    """

    def decorator(func):
        """
        Inner decorator for trigger_decorator.
        """
        if not isinstance(target_func, NodeClassMixinNodeFunction):
            raise ValueError("trigger can only be used on instance_nodefunctions")

        @wraps(func)
        def func_wrapper(instance: NodeClassMixin, *args, **kwargs):
            """
            Wraps a function to handle callings
            """
            res = func(instance, *args, **kwargs)
            for node in target_func.nodes(ins=instance):
                node.request_trigger()
            return res

        return func_wrapper

    return decorator


class NodeClassNodeMeta(NodeMeta):
    """
    Metaclass for the NodeClassNode class.
    """

    def __new__(cls, name, bases, dct):
        """
        Creates a new NodeClassNode class.

        Args:
          cls (NodeClassNodeMeta): The class to be created.
          name (str): The name of the class.
          bases: The base classes.
          dct: The class dictionary.

        Returns:
          Type[NodeClassNode]: The new class.
        """
        new_cls: Type[NodeClassNode] = super().__new__(cls, name, bases, dct)  # type: ignore
        new_cls._instances = WeakValueDictionary()
        return new_cls


class NodeClassNode(Node, ABC, metaclass=NodeClassNodeMeta):
    """
    Special Node-subclass for NodeClassMixin instances,
    that keeps track of its instances.

    Attributes:
      _instances (WeakValueDictionary): A dictionary of all instances of the node class.
    """

    def __init__(self, *args, **kwargs):
        """
        Initializes a new instance of the NodeClassNode class.
        """
        super().__init__(*args, **kwargs)
        self.__class__._instances[self.uuid] = self

    def __init_subclass__(cls, **kwargs):
        cls._instances: WeakValueDictionary[str, NodeClassNode] = WeakValueDictionary()
        return super().__init_subclass__(**kwargs)

    def cleanup(self):
        if self.uuid in self.__class__._instances:
            # delete the instance from the class reference
            del self.__class__._instances[self.uuid]
        return super().cleanup()


class NodeClassMixin(ABC):
    """
    The NodeClassMixin can be used on any class to
    transform its methods into node classes.
    Each instance of the class will have its own Nodeclassess,
    making them independend from each other.
    This is especially useful for creating nodes that are
    bound to each other in a specific way, which can be mediated
    by the respective class.

    Attributes:
      NODECLASSID (str): The unique id of the class, forwardet to the node.
      IS_ABSTRACT (bool): Whether the node class is abstract or not.

    Examples:
      >>> class MyNodeClass(NodeClassMixin):
      >>>   NODECLASSID = "my_node_class"
      >>>
      >>>   @instance_nodefunction
      >>>   def add(self, a, b):
      >>>     return a + b
      >>>
      >>>   @add.triggers
      >>>   def eval(self, a, b):
      >>>     # calling this function will trigger the add nodes for this instance
    """

    NODECLASSID: str = None  # type: ignore
    IS_ABSTRACT = True

    @classmethod
    def __init_subclass__(cls, **kwargs):
        """
        Called when a new subclass of NodeClassMixin is created.
        Ensures that NODECLASSID is defined unless the class is abstract.
        """

        super().__init_subclass__(**kwargs)

        # Ensure IS_ABSTRACT defaults to False if not explicitly set in the subclass
        if "IS_ABSTRACT" not in cls.__dict__:
            cls.IS_ABSTRACT = False

        # Check for abstract classes
        if inspect.isabstract(cls) or getattr(cls, "IS_ABSTRACT", False):
            return

        # Ensure NODECLASSID is defined if not abstract
        if cls.NODECLASSID is None:
            raise ValueError(f"NODECLASSID not set for {cls.__name__}")

    def __init__(self, *args, **kwargs):
        """
        Initializes a new instance of the NodeClassMixin class.
        """
        if getattr(self, "IS_ABSTRACT", False):
            raise ValueError("Cannot instantiate abstract NodeClassMixin")
        super().__init__(*args, **kwargs)
        self._node_classes: WeakValueDictionary[
            str, Type[NodeClassNode]
        ] = {}  # maps method names to node classes
        self._uuid = None
        self._nodes_created = False
        self._name = None

        self._instance_node_functions: Dict[
            str, NodeClassMixinInstanceNodeFunction
        ] = {}

        self._make_instance_node_functions()

    def _make_instance_node_functions(self):
        for method, name in self.get_all_nodefunctions():
            insfunc = NodeClassMixinInstanceNodeFunction(self, method)
            self._instance_node_functions[name] = insfunc
            setattr(
                self,
                name,
                insfunc,
            )

    @classmethod
    def get_all_nodefunctions(
        cls: Type[NodeClassMixin],
    ) -> List[Tuple[NodeClassMixinNodeFunction, str]]:
        """
        Gets all node functions for the given class.

        Args:
        cls (Type[NodeClassMixin]): The class to get the node functions for.

        Returns:
        List[Tuple[NodeClassMixinNodeFunction, str]]: A list of tuples containing the node functions and their names.
        """
        nodefuncs: List[Tuple[NodeClassMixinNodeFunction, str]] = []
        for parent in cls.__mro__:
            for name, method in parent.__dict__.items():
                if isinstance(method, NodeClassMixinNodeFunction):
                    nodefuncs.append((method, name))
        return nodefuncs

    @property
    def uuid(self):
        """
        Gets the uuid of the NodeClassMixin instance.

        Args:
          self (NodeClassMixin): The NodeClassMixin instance.

        Returns:
          str: The uuid of the instance.

        Raises:
          ValueError: If the uuid is not set.
        """
        if self._uuid is None:
            raise ValueError("uuid not set, please set using <instance>.uuid = uuid")
        return self._uuid

    @uuid.setter
    def uuid(self, value):
        """
        Sets the uuid of the NodeClassMixin instance.
        """
        if self._uuid is not None:
            raise ValueError("uuid already set")
        self._uuid = value

    @property
    def name(self):
        if not self._name:
            return f"{self.__class__.__name__}({self.uuid})"
        return str(self._name)

    @name.setter
    def name(self, value):
        self._name = value

    def create_nodes(self) -> None:
        """
        Creates all node classes for the NodeClassMixin instance.

        Args:
          self (NodeClassMixin): The NodeClassMixin instance.

        Returns:
          None

        """
        if self._nodes_created:
            return
        for name, method in self._instance_node_functions.items():
            method.create_node()

        self._nodes_created = True

    def get_nodes(self, method_name) -> List[Node]:
        """
        Gets all instances of a node class for a given method name.

        Args:
          method_name (str): The name of the method to get node instances for.

        Returns:
          List[Node]: A list of all instances of the node class for the given method name.
        """
        return list(
            self.get_nodeclass(  # pylint: disable=protected-access
                method_name
            )._instances.values()
        )

    def get_nodeclass(self, method_name) -> Type[NodeClassNode]:
        """
        Gets the node class for a given method name.

        Args:
          method_name (str): The name of the method to get the node class for.

        Returns:
          Type[NodeClassNode]: The node class for the given method name.
        """
        self.create_nodes()
        return self._node_classes[method_name]

    def get_all_nodeclasses(self) -> List[Type[NodeClassNode]]:
        """
        Gets all node classes for the node mixin.

        Returns:
          List[Type[NodeClassNode]]: A list of all node classes for the node mixin.
        """
        self.create_nodes()
        return list(self._node_classes.values())

    def get_all_nodes(self) -> List[NodeClassNode]:
        """
        Gets all node instances for the node mixin.

        Returns:
          List[NodeClassNode]: A list of all node instances for the node mixin.
        """
        nodes = []
        for m in self.get_all_nodeclasses():
            nodes.extend(
                list(m._instances.values())  # pylint: disable=protected-access
            )
        return nodes

    def cleanup(self):
        for node in self.get_all_nodes():
            node.cleanup()
            del node  # node.__del__

        for k in list(self._node_classes):
            try:
                del self._node_classes[k]
            except Exception as e:
                FUNCNODES_LOGGER.exception(e)

        # in case parent class has a cleanup method
        if hasattr(super(), "cleanup"):
            super().cleanup()

    def __del__(self):
        self.cleanup()
