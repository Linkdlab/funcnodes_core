import funcnodes_core as fn
import asyncio


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
