import asyncio
import time
from typing import Annotated, Tuple


import funcnodes_core as fn
from pytest_funcnodes import funcnodes_test


class DummyNode(fn.Node):
    node_id = "dummy_nodedec"
    input = fn.NodeInput(
        id="input",
        type=int,
        default=1,
        description="i1",
        value_options={"options": [1, 2]},
    )
    output = fn.NodeOutput(id="output", type=int)
    default_render_options = {"data": {"src": "input"}}

    async def func(self, input: int) -> int:  # noqa: A003 - matching fn signature
        self.outputs["output"].value = input
        return input


@funcnodes_test
async def test_update_value_options_decorator():
    @fn.NodeDecorator(
        "test_decorator_update_value",
        description="Test decorator for updating value.",
        default_io_options={
            "obj": {
                "on": {
                    "after_set_value": fn.decorator.update_other_io_options(
                        "key", lambda x: list(x.keys())
                    )
                }
            }
        },
    )
    def select(obj: dict, key: str):
        return obj[key]

    node = select()

    assert len(node.inputs) == 3, (
        f"Node should have 3 inputs: obj,key and _triggerinput, but has {node.inputs.keys()}."
    )

    node["obj"] = {"key1": "value1", "key2": "value2"}
    await node

    assert hasattr(node["key"], "value_options"), (
        "Node-key has no value_options attribute."
    )
    assert "options" in node["key"].value_options, (
        "Node-key has no value_options.options attribute."
    )
    assert node["key"].value_options["options"] == ["key1", "key2"]


@funcnodes_test
async def test_node_input_param():
    called_node = []

    @fn.NodeDecorator(
        "test_node_input_param",
        description="Test decorator for node param",
    )
    def select(a: int, node: fn.Node) -> int:
        called_node.append(node)
        return a + 1

    node = select()

    assert len(node.inputs) == 2, (
        f"Node should have 3 inputs: a and _triggerinput, but has {node.inputs.keys()}."
    )

    node["a"] = 1

    await node

    assert node.outputs["out"].value == 2
    assert len(called_node) == 1
    assert called_node[0] == node


@funcnodes_test
async def test_update_multiple_value_options_decorator():
    @fn.NodeDecorator(
        "test_update_multiple_value_decorator",
        description="Test decorator for updating value.",
        default_io_options={
            "obj": {
                "on": {
                    "after_set_value": [
                        fn.decorator.update_other_io_options(
                            "key1", lambda x: list(x.keys())
                        ),
                        fn.decorator.update_other_io_options(
                            "key2", lambda x: list(x.keys()) + list(x.keys())
                        ),
                    ],
                }
            }
        },
    )
    def select(obj: dict, key1: str, key2: str) -> Tuple[str, str]:
        return obj[key1], obj[key2]

    node = select()
    node["obj"] = {"key1": "value1", "key2": "value2"}
    await node

    assert hasattr(node["key1"], "value_options"), (
        "Node-key1 has no value_options attribute."
    )
    assert "options" in node["key1"].value_options, (
        "Node-key1 has no value_options.options attribute."
    )
    assert node["key1"].value_options["options"] == ["key1", "key2"]

    assert hasattr(node["key2"], "value_options"), (
        "Node-key2 has no value_options attribute."
    )
    assert "options" in node["key2"].value_options, (
        "Node-key2 has no value_options.options attribute."
    )
    assert node["key2"].value_options["options"] == ["key1", "key2", "key1", "key2"]


@funcnodes_test
async def test_update_multiple_value_options_with_one_decorator():
    @fn.NodeDecorator(
        "test_update_multiple_value_with_one_decorator",
        description="Test decorator for updating value.",
        default_io_options={
            "obj": {
                "on": {
                    "after_set_value": fn.decorator.update_other_io_options(
                        ["key1", "key2"], lambda x: list(x.keys())
                    ),
                }
            }
        },
    )
    def select(obj: dict, key1: str, key2: str) -> Tuple[str, str]:
        return obj[key1], obj[key2]

    node = select()
    node["obj"] = {"key1": "value1", "key2": "value2"}
    await node

    assert hasattr(node["key1"], "value_options"), (
        "Node-key1 has no value_options attribute."
    )
    assert "options" in node["key1"].value_options, (
        "Node-key1 has no value_options.options attribute."
    )
    assert node["key1"].value_options["options"] == ["key1", "key2"]

    assert hasattr(node["key2"], "value_options"), (
        "Node-key2 has no value_options attribute."
    )
    assert "options" in node["key2"].value_options, (
        "Node-key2 has no value_options.options attribute."
    )
    assert node["key2"].value_options["options"] == ["key1", "key2"]


@funcnodes_test
async def test_update_other_io_value_options():
    @fn.NodeDecorator(
        "test_decorator_update_value",
        description="Test decorator for updating value.",
        default_io_options={
            "obj": {
                "on": {
                    "after_set_value": fn.decorator.update_other_io_value_options(
                        "key", lambda x: {"options": list(x.keys())}
                    )
                }
            }
        },
    )
    def select(obj: dict, key: str):
        return obj[key]

    node = select()
    node["obj"] = {"key1": "value1", "key2": "value2"}
    await node

    assert hasattr(node["key"], "value_options"), (
        "Node-key has no value_options attribute."
    )
    assert "options" in node["key"].value_options, (
        "Node-key has no value_options.options attribute."
    )
    assert node["key"].value_options["options"] == ["key1", "key2"]


@funcnodes_test
async def test_update_other_io_value_options_multiple_calls():
    @fn.NodeDecorator(
        "test_update_multiple_value_decorator",
        description="Test decorator for updating value.",
        default_io_options={
            "obj": {
                "on": {
                    "after_set_value": [
                        fn.decorator.update_other_io_value_options(
                            "key1", lambda x: {"options": list(x.keys())}
                        ),
                        fn.decorator.update_other_io_value_options(
                            "key2",
                            lambda x: {"options": list(x.keys()) + list(x.keys())},
                        ),
                    ],
                }
            }
        },
    )
    def select(obj: dict, key1: str, key2: str) -> Tuple[str, str]:
        return obj[key1], obj[key2]

    node = select()
    node["obj"] = {"key1": "value1", "key2": "value2"}
    await node

    assert hasattr(node["key1"], "value_options"), (
        "Node-key1 has no value_options attribute."
    )
    assert "options" in node["key1"].value_options, (
        "Node-key1 has no value_options.options attribute."
    )
    assert node["key1"].value_options["options"] == ["key1", "key2"]

    assert hasattr(node["key2"], "value_options"), (
        "Node-key2 has no value_options attribute."
    )
    assert "options" in node["key2"].value_options, (
        "Node-key2 has no value_options.options attribute."
    )
    assert node["key2"].value_options["options"] == ["key1", "key2", "key1", "key2"]


@funcnodes_test
async def test_update_other_io_value_options_multiple_multipleios():
    @fn.NodeDecorator(
        "test_update_multiple_value_with_one_decorator",
        description="Test decorator for updating value.",
        default_io_options={
            "obj": {
                "on": {
                    "after_set_value": fn.decorator.update_other_io_value_options(
                        ["key1", "key2"], lambda x: {"options": list(x.keys())}
                    ),
                }
            }
        },
    )
    def select(obj: dict, key1: str, key2: str) -> Tuple[str, str]:
        return obj[key1], obj[key2]

    node = select()
    node["obj"] = {"key1": "value1", "key2": "value2"}
    await node

    assert hasattr(node["key1"], "value_options"), (
        "Node-key1 has no value_options attribute."
    )
    assert "options" in node["key1"].value_options, (
        "Node-key1 has no value_options.options attribute."
    )
    assert node["key1"].value_options["options"] == ["key1", "key2"]

    assert hasattr(node["key2"], "value_options"), (
        "Node-key2 has no value_options attribute."
    )
    assert "options" in node["key2"].value_options, (
        "Node-key2 has no value_options.options attribute."
    )
    assert node["key2"].value_options["options"] == ["key1", "key2"]


@funcnodes_test
async def test_superclass():
    class BaseNode(fn.Node):
        """
        `Abstract` base class does not need a `func` method or a `node_id`
        """

        my_id = fn.NodeOutput(id="my_id", type=int)

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.outputs["my_id"].value = id(self)

    @fn.NodeDecorator(node_id="my_node", superclass=BaseNode)
    def my_node(input1: int, input2: int) -> int:
        return input1 + input2

    ins = my_node()
    ins["input1"] = 1
    ins["input2"] = 2
    await ins

    assert ins.outputs["out"].value == 3
    assert ins.outputs["my_id"].value == id(ins)


@funcnodes_test
async def test_call_blocking_node():
    @fn.NodeDecorator(node_id="blocking_node")
    def BlockingNode(input: int) -> int:  # noqa: N802 - intentional casing
        start = time.time()
        while True:
            if time.time() - start > 1:
                break
        return input

    test_node1 = BlockingNode()
    test_node2 = BlockingNode()

    enternode = DummyNode()

    enternode.outputs["output"].connect(test_node1.inputs["input"])
    enternode.outputs["output"].connect(test_node2.inputs["input"])

    start = time.time()

    await fn.run_until_complete(enternode, test_node1, test_node2)
    end = time.time()
    assert enternode.outputs["output"].value == 1
    assert test_node1.outputs["out"].value == 1
    assert test_node2.outputs["out"].value == 1
    assert end - start >= 2


@funcnodes_test
async def test_call_separate_thread():
    @fn.NodeDecorator(node_id="non_blocking_node", separate_thread=True)
    def NoneBlockingNode(input: int) -> int:  # noqa: N802 - intentional casing
        print("Start")
        time.sleep(1)
        print("End")
        return input

    test_node1 = NoneBlockingNode()
    test_node2 = NoneBlockingNode()

    enternode = DummyNode()

    enternode.outputs["output"].connect(test_node1.inputs["input"])
    enternode.outputs["output"].connect(test_node2.inputs["input"])
    start = time.time()
    fn.FUNCNODES_LOGGER.info("Start wait")
    await fn.run_until_complete(enternode, test_node1, test_node2)
    fn.FUNCNODES_LOGGER.info("End wait")
    end = time.time()
    assert enternode.outputs["output"].value == 1
    assert test_node1.outputs["out"].value == 1
    assert test_node2.outputs["out"].value == 1
    assert end - start <= 2
    assert end - start >= 1


@funcnodes_test
async def test_call_separate_thread_output_trigger():
    @fn.NodeDecorator(node_id="non_blocking_node_t", separate_thread=True)
    def NoneBlockingNode(input: int) -> int:  # noqa: N802 - intentional casing
        print("Start")
        time.sleep(1)
        print("End")
        return input

    bn = NoneBlockingNode()
    dum = DummyNode()

    bn.outputs["out"].connect(dum.inputs["input"])
    bn.inputs["input"].value = 1
    await fn.run_until_complete(bn, dum)

    assert bn.outputs["out"].value == 1
    assert dum.inputs["input"].value == 1
    assert dum.outputs["output"].value == 1


@funcnodes_test
async def test_call_separate_process():
    @fn.NodeDecorator(node_id="non_blocking_node", separate_process=True)
    def NoneBlockingNode(input: int) -> int:  # noqa: N802 - intentional casing
        print("Start")
        time.sleep(2)
        print("End")
        return input

    test_node1 = NoneBlockingNode()
    test_node2 = NoneBlockingNode()

    enternode = DummyNode()

    enternode.outputs["output"].connect(test_node1.inputs["input"])
    enternode.outputs["output"].connect(test_node2.inputs["input"])
    start = time.time()
    fn.FUNCNODES_LOGGER.info("Start wait")
    await fn.run_until_complete(enternode, test_node1, test_node2)
    fn.FUNCNODES_LOGGER.info("End wait")
    end = time.time()
    assert enternode.outputs["output"].value == 1
    assert test_node1.outputs["out"].value == 1
    assert test_node2.outputs["out"].value == 1
    assert end - start <= 4
    assert end - start >= 2


@funcnodes_test
async def test_call_separate_process_output_trigger():
    @fn.NodeDecorator(node_id="non_blocking_node_t", separate_thread=True)
    def NoneBlockingNode(input: int) -> int:  # noqa: N802 - intentional casing
        print("Start")
        time.sleep(1)
        print("End")
        return input

    bn = NoneBlockingNode()
    dum = DummyNode()
    bn.inputs["input"].value = 1
    assert bn.inputs["input"].value == 1
    bn.outputs["out"].connect(dum.inputs["input"])
    await fn.run_until_complete(bn, dum)

    assert bn.outputs["out"].value == 1
    assert dum.inputs["input"].value == 1
    assert dum.outputs["output"].value == 1


@funcnodes_test
async def test_to_thread():
    @fn.NodeDecorator(node_id="my_node")
    async def my_node(input1: int, input2: int) -> int:
        def heavy_task(input1, input2):
            time.sleep(1)
            return input1 + input2

        return await asyncio.to_thread(heavy_task, input1, input2)

    test_node1 = my_node()
    test_node2 = my_node()

    test_node1.inputs["input1"].value = 1
    test_node1.inputs["input2"].value = 2
    test_node2.inputs["input1"].value = 3
    test_node2.inputs["input2"].value = 4

    start = time.time()
    await fn.run_until_complete(test_node1, test_node2)
    end = time.time()

    assert test_node1.outputs["out"].value == 3
    assert test_node2.outputs["out"].value == 7
    assert end - start <= 2
    assert end - start >= 1


@funcnodes_test
def test_description():
    @fn.NodeDecorator(
        node_id="my_node1", description="This is a node created with the decorator"
    )
    def my_node1(ip: int) -> float:
        return ip / 2

    @fn.NodeDecorator(node_id="my_node2")
    def my_node2(ip: int) -> float:
        """This is a node created with the decorator and a docstring"""
        return ip / 2

    class MyNode(fn.Node):
        node_name = "My Node Class"
        node_id = "my_node3"
        description = "This is a node created with the class"

        ip = fn.NodeInput(id="ip", type=int)

        async def func(self, ip):
            self.outputs["output1"].value = ip / 2

    assert my_node1().description == "This is a node created with the decorator"
    assert (
        my_node2().description
        == "This is a node created with the decorator and a docstring"
    )
    assert MyNode().description == "This is a node created with the class"


@funcnodes_test
async def test_io_rename():
    @fn.NodeDecorator(
        node_id="my_node",
        inputs=[
            {"name": "a"},
            {"name": "b"},
        ],
    )
    def myfunction(
        var_name_i_dont_like_a: int = 1, var_name_i_dont_like_b: int = 2
    ) -> int:
        return var_name_i_dont_like_a + var_name_i_dont_like_b

    node = myfunction()

    await node

    assert node.outputs["out"].value == 3


@funcnodes_test
async def test_decorator_with_pipe_union_type():
    @fn.NodeDecorator(node_id="my_node")
    def my_node(a: int | str) -> int:
        return a

    node = my_node()
    node["a"] = 1
    await node
    assert node.outputs["out"].value == 1

    ser = node.full_serialize()
    print(ser)
    a_input = next(io for io in ser["io"] if io["id"] == "a" and io["is_input"])
    assert a_input["type"] == {"anyOf": ["int", "str"]}


@funcnodes_test
async def test_decorator_with_annotated_type():
    @fn.NodeDecorator(node_id="my_node")
    def my_node(
        a: Annotated[
            int,
            fn.InputMeta(
                name="b",
                description="A",
                default=1,
                does_trigger=False,
                hidden=True,
            ),
        ],
    ) -> Annotated[int, fn.OutputMeta(name="c", description="C")]:
        return a + 1

    node = my_node()

    import pprint

    pprint.pprint(node.serialize())
    assert node.inputs["a"].value == 1
    assert node.inputs["a"].name == "b"
    assert node.inputs["a"].does_trigger is False
    assert node.inputs["a"].hidden is True

    await node
    assert node.outputs["c"].value == 2


@funcnodes_test
async def test_decorator_with_annotated_type_and_on():
    @fn.NodeDecorator(node_id="my_node")
    def my_node(
        a: Annotated[
            dict[str, int],
            fn.InputMeta(
                name="b",
                description="A",
                default=1,
                does_trigger=False,
                hidden=True,
                on={
                    "after_set_value": fn.decorator.update_other_io_options(
                        "k",
                        list,
                    )
                },
            ),
        ],
        k: str,
    ) -> Annotated[int, fn.OutputMeta(name="c", description="C")]:
        return a[k]

    ins1 = my_node()
    ins2 = my_node()
    ins1["a"] < {"k1": 1, "k2": 2}
    ins2["a"] < {"k3": 3, "k4": 4}
    assert ins1.inputs["k"].value_options["options"] == ["k1", "k2"]
    assert ins2.inputs["k"].value_options["options"] == ["k3", "k4"]
    ins1["k"] = "k1"
    ins2["k"] = "k3"
    await fn.run_until_complete(ins1, ins2)
    assert ins1.outputs["c"].value == 1
    assert ins2.outputs["c"].value == 3
