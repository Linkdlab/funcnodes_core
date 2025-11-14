import asyncio

import pytest

import funcnodes_core as fn
from funcnodes_core.utils.serialization import Encdata, JSONEncoder


async def test_datapaths():
    @fn.NodeDecorator(
        "test_datapaths.n1",
    )
    def n1(a: int = 0, b: int = 1) -> int:
        return a + b

    node1 = n1(name="n1")
    node2 = n1(name="n2")
    node3 = n1(name="n3")
    node4 = n1(name="n4")
    node1.outputs["out"] > node3.inputs["a"]
    node2.outputs["out"] > node3.inputs["b"]
    node3.outputs["out"] > node4.inputs["a"]
    await fn.run_until_complete(node1, node2, node3, node4)

    # print(node4.inputs["a"].datapath.src_repr())
    assert (
        "\n".join(
            [lin.strip() for lin in node4.inputs["a"].datapath.src_repr().splitlines()]
        )
        == """n1(a)
n1(b) -> n1(out) -> n3(a)
n2(a)                     -> n3(out) -> n4(a)
n2(b) -> n2(out) -> n3(b)"""
    )
    assert node4.inputs["a"].datapath.done()


async def test_datapaths_done():
    @fn.NodeDecorator(
        "test_datapaths.n1",
    )
    async def n1(a: int = 0, b: int = 1) -> int:
        await asyncio.sleep(1)
        return a + b

    node1 = n1(name="n1")
    assert node1.inputs["a"].datapath.done() is False
    await asyncio.sleep(0.5)
    assert node1.inputs["a"].datapath.done() is False
    await asyncio.sleep(1)
    assert node1.inputs["a"].datapath.done()


@pytest.fixture(scope="module")
def datapath_cls():
    @fn.NodeDecorator(
        "test_datapaths.helper",
    )
    def helper(a: int = 0) -> int:
        return a

    node = helper(name="helper-node")
    return type(node.inputs["a"].datapath)


class _DummyNode:
    def __init__(self, name: str, *, in_trigger_soon: bool = False):
        self.name = name
        self.in_trigger_soon = in_trigger_soon


def test_datapath_done_respects_breaking_nodes(datapath_cls):
    node = _DummyNode("breaker", in_trigger_soon=True)
    datapath = datapath_cls(node, "out")

    assert datapath.done() is False
    assert datapath.done(breaking_nodes=[node]) is True


def test_datapath_done_handles_missing_node_reference(datapath_cls):
    node = _DummyNode("ghost")
    datapath = datapath_cls(node, "ghost-out")

    datapath.node_ref = lambda: None  # simulate collected node

    assert datapath.done() is True
    assert str(datapath) == "Unknown Node(ghost-out)"


def test_datapath_handler_encodes_source_graph(datapath_cls):
    source = datapath_cls(_DummyNode("source"), "out")
    target = datapath_cls(_DummyNode("target"), "in")
    target.add_src_path(source)

    handler_result = None
    for encoder in JSONEncoder.encoder_registry[type(target)]:
        result = encoder(target, preview=True)
        if isinstance(result, Encdata):
            candidate = result
        else:
            data, handled = result
            candidate = Encdata(data=data, handeled=handled)
        if candidate.handeled:
            handler_result = candidate
            break

    assert handler_result is not None
    assert handler_result.data == target.src_graph()
    assert handler_result.done is False

    encoded = JSONEncoder.apply_custom_encoding(target)
    assert encoded == [[[[], [[]]]]]
