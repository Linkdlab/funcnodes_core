import time
from dataclasses import dataclass

import asyncio

from funcnodes_core.utils.nodeutils import (
    get_deep_connected_nodeset,
    run_until_complete,
)
from funcnodes_core.nodemaker import NodeDecorator

import funcnodes_core as fn

from pytest_funcnodes import funcnodes_test
import pytest


@NodeDecorator("dummy_nodefor testnodeutils")
async def identity(input: int) -> int:
    # add a little delay
    await asyncio.sleep(fn.node.NodeConstants.TRIGGER_SPEED_FAST * 1)
    return input


class TKNode(fn.Node):
    node_id = "tknode"
    ip1 = fn.NodeInput(uuid="ip1", type=int)
    ip2 = fn.NodeInput(uuid="ip2", type=int)

    op1 = fn.NodeOutput(uuid="op1", type=int)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.outputs["op1"].value = 0

    async def func(self, ip1, ip2):
        self.outputs["op1"].value += 1


@dataclass
class NodeChain:
    node1: fn.Node
    node2: fn.Node
    node3: fn.Node


@pytest.fixture
async def node_chain():
    node1 = identity()
    node2 = identity()
    node3 = identity()

    node1.outputs["out"].connect(node2.inputs["input"])
    node2.outputs["out"].connect(node3.inputs["input"])
    node1.inputs["input"].value = 10

    try:
        yield NodeChain(node1=node1, node2=node2, node3=node3)
    finally:
        for node in (node1, node2, node3):
            node.cleanup()


@funcnodes_test
async def test_get_deep_connected_nodeset(node_chain: NodeChain):
    nodeset = get_deep_connected_nodeset(node_chain.node1)
    assert node_chain.node1 in nodeset
    assert node_chain.node2 in nodeset
    assert node_chain.node3 in nodeset


@funcnodes_test
async def test_get_deep_connected_nodeset_with_node_in(node_chain: NodeChain):
    nodeset = get_deep_connected_nodeset(node_chain.node1, {node_chain.node2})
    assert node_chain.node1 in nodeset
    assert node_chain.node2 in nodeset
    assert node_chain.node3 not in nodeset

    nodeset = get_deep_connected_nodeset(node_chain.node1, {node_chain.node1})
    assert node_chain.node1 in nodeset
    assert node_chain.node2 not in nodeset
    assert node_chain.node3 not in nodeset


@funcnodes_test
async def test_run_until_complete_all_triggered(node_chain: NodeChain):
    await run_until_complete(node_chain.node1, node_chain.node2, node_chain.node3)
    assert node_chain.node1.outputs["out"].value == 10
    assert node_chain.node2.outputs["out"].value == 10
    assert node_chain.node3.outputs["out"].value == 10


@funcnodes_test
async def test_node_progress(node_chain: NodeChain):
    collected = []

    def progress_callback(src, info, *args, **kwargs):
        collected.append(info)

    node1 = node_chain.node1
    await node1
    node1.on("progress", progress_callback)

    await node1

    assert len(collected) == 2, (
        "There should be two progress updates. One for triggering and one for idle."
    )
    assert collected[0]["prefix"] == "triggering"
    assert collected[1]["prefix"] == "idle"


@funcnodes_test
async def test_trigger_conut():
    node = TKNode(pretrigger_delay=0.1)
    await node
    assert node.outputs["op1"].value == 0
    node.inputs["ip1"].value = 1
    node.inputs["ip2"].value = 2
    await node
    assert node.outputs["op1"].value == 1

    ts1 = time.time()

    for _ in range(10):
        await node
    te1 = time.time()
    tw1 = te1 - ts1
    assert tw1 < 2
    assert node.outputs["op1"].value == 11

    ts2 = time.time()
    for i in range(10):
        node.inputs["ip1"].value = i
        await node
    te2 = time.time()
    tw2 = te2 - ts2
    assert node.outputs["op1"].value == 21
    assert tw2 < 2

    while node.in_trigger:
        await asyncio.sleep(0.0)

    pt = node.outputs["op1"].value
    node.inputs["ip1"].value = pt
    ts3 = time.time()
    while node.in_trigger:
        await asyncio.sleep(0.01)
    te3 = time.time()

    tw3 = te3 - ts3
    assert tw3 < 0.2
    assert node.outputs["op1"].value == 22

    node.inputs["ip1"].value = 10
    await asyncio.sleep(0.2)  # the delay is large, trigger twice
    node.inputs["ip2"].value = 20
    await node
    assert node.outputs["op1"].value == 24

    node.inputs["ip1"].value = 11
    await asyncio.sleep(0.05)  # the delay is small, trigger once
    node.inputs["ip2"].value = 21
    await node
    assert node.outputs["op1"].value == 25


@funcnodes_test
async def test_trigger_fast():
    node = TKNode()
    node.pretrigger_delay = 0.0
    node.inputs["ip1"].value = 1
    node.inputs["ip2"].value = 2
    await node
    assert node.outputs["op1"].value == 1

    ts1 = time.time()
    for _ in range(100):
        await node
    te1 = time.time()
    tw1 = te1 - ts1
    assert tw1 < 0.5
    assert node.outputs["op1"].value == 101
