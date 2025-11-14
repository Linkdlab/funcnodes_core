import asyncio

import pytest

import funcnodes_core as fn
from pytest_funcnodes import funcnodes_test


def _create_test_enum():
    class TestEnum(fn.DataEnum):
        A = 1
        B = 2
        C = 3

    return TestEnum


def test_enum():
    TestEnum = _create_test_enum()

    assert TestEnum.A.value == 1
    assert TestEnum.interfere("A") == TestEnum.A
    assert TestEnum.interfere(1) == TestEnum.A
    assert TestEnum.interfere(TestEnum.A) == TestEnum.A
    assert TestEnum.v("A") == 1
    assert TestEnum.v(1) == 1
    assert TestEnum.v(TestEnum.A) == 1

    with pytest.raises(ValueError):
        TestEnum.interfere("X")
    with pytest.raises(ValueError):
        TestEnum.interfere(4)


@funcnodes_test
async def test_enum_val():
    TestEnum = _create_test_enum()

    assert TestEnum.A.value == 1

    @fn.NodeDecorator(node_id="test_enum_val")
    def test_enum_node(a: TestEnum) -> TestEnum:
        a = TestEnum.interfere(a)
        return a

    node = test_enum_node()
    node.inputs["a"].value = "A"
    async with asyncio.timeout(1):
        await node
    out = node.outputs["out"].value
    assert out == TestEnum.A

    node = test_enum_node()
    node.inputs["a"].value = 1
    await node
    out = node.outputs["out"].value
    assert out == TestEnum.A

    node = test_enum_node()
    node.inputs["a"].value = TestEnum.A
    await node
    out = node.outputs["out"].value
    assert out == TestEnum.A


@funcnodes_test
async def test_enum_use():
    TestEnum = _create_test_enum()

    assert TestEnum.v("A") == 1

    @fn.NodeDecorator(node_id="test_enum_use")
    def test_enum_node(a: TestEnum) -> int:
        a = TestEnum.v(a)
        return a + 1

    node = test_enum_node()
    node.inputs["a"].value = "A"
    await node
    out = node.outputs["out"].value
    assert out == 2

    node = test_enum_node()
    node.inputs["a"].value = 1
    await node
    out = node.outputs["out"].value
    assert out == 2

    node = test_enum_node()
    node.inputs["a"].value = "1"
    await node
    out = node.outputs["out"].value
    assert out == 2

    node = test_enum_node()
    node.inputs["a"].value = TestEnum.A
    await node
    out = node.outputs["out"].value
    assert out == 2


@funcnodes_test
async def test_enum_default():
    TestEnum = _create_test_enum()

    assert TestEnum.v("A") == 1

    @fn.NodeDecorator(node_id="test_enum_default")
    def test_enum_node(a: TestEnum = TestEnum.A) -> int:
        a = TestEnum.v(a)
        return a + 1

    node = test_enum_node()
    await node
    out = node.outputs["out"].value
    assert out == 2

    node = test_enum_node()
    await node
    out = node.outputs["out"].value
    assert out == 2

    node = test_enum_node()
    await node
    out = node.outputs["out"].value
    assert out == 2
