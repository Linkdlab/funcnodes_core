import pytest

from funcnodes_core import Node, NodeInput, NodeOutput, NodeSpace
from pytest_funcnodes import setup, teardown


class GroupingDummyNode(Node):
    node_id = "ns_grouping_dummy_node"
    node_name = "Grouping Dummy Node"
    default_trigger_on_create = False
    myinput = NodeInput(id="input", type=int, default=1)
    myoutput = NodeOutput(id="output", type=int)

    async def func(self, input: int) -> int:
        return input


class GroupingPropagatingNode(Node):
    node_id = "ns_grouping_propagating_node"
    node_name = "Grouping Propagating Node"
    default_trigger_on_create = False
    myinput = NodeInput(id="input", type=int, default=1)
    myoutput = NodeOutput(id="output", type=int)

    async def func(self, input: int) -> int:
        self.outputs["output"].value = input
        return input


@pytest.fixture
def nodespace():
    setup()
    space = NodeSpace()
    space.lib.add_node(GroupingDummyNode, "basic")
    try:
        yield space
    finally:
        teardown()


def test_serialize_deserialize_preserves_groups(nodespace):
    node1 = GroupingDummyNode()
    node2 = GroupingDummyNode()
    nodespace.add_node_instance(node1)
    nodespace.add_node_instance(node2)
    nodespace.groups.add_group(
        "parent",
        node_ids=[node1.uuid],
        meta={"label": "Parent"},
    )
    nodespace.groups.add_group(
        "child",
        node_ids=[node2.uuid],
        parent_group="parent",
        meta={"label": "Child"},
    )

    serialized_nodespace = nodespace.serialize()

    other = NodeSpace()
    other.lib.add_node(GroupingDummyNode, "basic")
    other.deserialize(serialized_nodespace)

    assert serialized_nodespace["groups"] == other.serialize_groups()
    assert other.groups.find_group_of_node(node1.uuid) == "parent"
    assert other.groups.find_group_of_node(node2.uuid) == "child"
    assert other.groups.get_group("child")["parent_group"] == "parent"


def test_remove_node_ungroups_node_and_cleans_empty_groups(nodespace):
    node1 = GroupingDummyNode()
    node2 = GroupingDummyNode()
    nodespace.add_node_instance(node1)
    nodespace.add_node_instance(node2)
    nodespace.groups.add_group("solo", node_ids=[node1.uuid])
    nodespace.groups.add_group("kept", node_ids=[node2.uuid])

    nodespace.remove_node_instance(node1)

    assert nodespace.groups.find_group_of_node(node1.uuid) is None
    assert nodespace.groups.get_group("solo") is None
    assert nodespace.groups.find_group_of_node(node2.uuid) == "kept"
    assert nodespace.groups.get_group("kept") is not None


async def test_groups_do_not_affect_edges_or_trigger_propagation(nodespace):
    source = GroupingDummyNode()
    sink = GroupingPropagatingNode()
    source["output"].connect(sink["input"])
    nodespace.add_node_instance(source)
    nodespace.add_node_instance(sink)
    nodespace.groups.add_group("visual-only", node_ids=[source.uuid])

    source["output"].set_value(42)
    await sink.wait_for_trigger_finish()

    assert nodespace.serialize_edges() == [
        (source.uuid, "output", sink.uuid, "input")
    ]
    assert sink.inputs["input"].value == 42
    assert sink.outputs["output"].value == 42
    assert nodespace.groups.find_group_of_node(source.uuid) == "visual-only"
