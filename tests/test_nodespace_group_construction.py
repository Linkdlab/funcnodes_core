import pytest

from funcnodes_core import GroupNode, Node, NodeInput, NodeOutput, NodeSpace


class GroupConstructionSourceNode(Node):
    """External test source used to drive grouped and ungrouped graphs."""

    node_id = "test_group_construction_source"
    node_name = "Group Construction Source"
    default_trigger_on_create = False
    value = NodeOutput(id="value", type=int)

    async def func(self) -> int:
        value = self.outputs["value"].value
        return value if value is not None else 0


class GroupConstructionAddOneNode(Node):
    """Selected internal test node that increments incoming integer values."""

    node_id = "test_group_construction_add_one"
    node_name = "Group Construction Add One"
    default_trigger_on_create = False
    value = NodeInput(id="value", type=int)
    result = NodeOutput(id="result", type=int)

    async def func(self, value: int) -> int:
        result = value + 1
        self.outputs["result"].value = result
        return result


class GroupConstructionDoubleNode(Node):
    """Selected internal test node that doubles incoming integer values."""

    node_id = "test_group_construction_double"
    node_name = "Group Construction Double"
    default_trigger_on_create = False
    value = NodeInput(id="value", type=int)
    result = NodeOutput(id="result", type=int)

    async def func(self, value: int) -> int:
        result = value * 2
        self.outputs["result"].value = result
        return result


class GroupConstructionSinkNode(Node):
    """External test sink whose input records the final propagated value."""

    node_id = "test_group_construction_sink"
    node_name = "Group Construction Sink"
    default_trigger_on_create = False
    value = NodeInput(id="value", type=int, default=0)

    async def func(self, value: int) -> int:
        return value


def build_groupable_space() -> tuple[
    NodeSpace,
    GroupConstructionSourceNode,
    GroupConstructionAddOneNode,
    GroupConstructionDoubleNode,
    GroupConstructionSinkNode,
]:
    """Build a four-node graph with two middle nodes suitable for grouping."""

    space = NodeSpace()
    source = GroupConstructionSourceNode()
    add_one = GroupConstructionAddOneNode()
    double = GroupConstructionDoubleNode()
    sink = GroupConstructionSinkNode()
    for node in (source, add_one, double, sink):
        space.add_node_instance(node)

    source.outputs["value"].connect(add_one.inputs["value"])
    add_one.outputs["result"].connect(double.inputs["value"])
    double.outputs["result"].connect(sink.inputs["value"])
    return space, source, add_one, double, sink


def test_group_nodes_as_node_moves_selected_nodes_and_preserves_internal_edges():
    space, source, add_one, double, sink = build_groupable_space()

    group = space.group_nodes_as_node([add_one.uuid, double.uuid], name="Math Group")

    assert isinstance(group, GroupNode)
    assert group.name == "Math Group"
    assert {node.uuid for node in space.nodes} == {source.uuid, sink.uuid, group.uuid}
    assert {node.uuid for node in group.iter_inner_nodes()} == {
        add_one.uuid,
        double.uuid,
    }
    assert (add_one.uuid, "result", double.uuid, "value") in {
        tuple(edge) for edge in group.inner_nodespace.serialize_edges()
    }


def test_group_nodes_as_node_converts_crossing_edges_to_gateway_boundaries():
    space, source, add_one, double, sink = build_groupable_space()

    group = space.group_nodes_as_node([add_one.uuid, double.uuid])
    input_binding = next(iter(group.input_bindings.values()))
    output_binding = next(iter(group.output_bindings.values()))

    assert set(group.input_bindings) == {f"in_{add_one.uuid}_value"}
    assert set(group.output_bindings) == {f"out_{double.uuid}_result"}
    assert (
        source.uuid,
        "value",
        group.uuid,
        input_binding["public_io"],
    ) in {tuple(edge) for edge in space.serialize_edges()}
    assert (
        group.group_input_node_uuid,
        input_binding["gateway_io"],
        add_one.uuid,
        "value",
    ) in {tuple(edge) for edge in group.inner_nodespace.serialize_edges()}
    assert (
        double.uuid,
        "result",
        group.group_output_node_uuid,
        output_binding["gateway_io"],
    ) in {tuple(edge) for edge in group.inner_nodespace.serialize_edges()}
    assert (
        group.uuid,
        output_binding["public_io"],
        sink.uuid,
        "value",
    ) in {tuple(edge) for edge in space.serialize_edges()}


async def test_group_nodes_as_node_preserves_mixed_graph_trigger_result():
    baseline, baseline_source, _, _, baseline_sink = build_groupable_space()
    grouped, grouped_source, add_one, double, grouped_sink = build_groupable_space()
    grouped.group_nodes_as_node([add_one.uuid, double.uuid])

    baseline_source.outputs["value"].set_value(3)
    await baseline.await_done()
    grouped_source.outputs["value"].set_value(3)
    await grouped.await_done()

    assert baseline_sink.inputs["value"].value == 8
    assert grouped_sink.inputs["value"].value == 8


async def test_group_nodes_as_node_replays_existing_external_source_value_safely():
    space, source, add_one, double, sink = build_groupable_space()
    source.outputs["value"].set_value(4)
    await space.await_done()
    sink.inputs["value"].set_value(0, does_trigger=False)

    space.group_nodes_as_node([add_one.uuid, double.uuid])
    await space.await_done()

    assert sink.inputs["value"].value == 10


def test_group_nodes_as_node_rejects_invalid_selection_without_partial_mutation():
    space, source, add_one, double, sink = build_groupable_space()
    before_nodes = {node.uuid for node in space.nodes}
    before_edges = {tuple(edge) for edge in space.serialize_edges()}

    with pytest.raises(ValueError, match="not found"):
        space.group_nodes_as_node([add_one.uuid, "missing-node"])

    assert {node.uuid for node in space.nodes} == before_nodes
    assert {tuple(edge) for edge in space.serialize_edges()} == before_edges
    assert source.outputs["value"].connections == [add_one.inputs["value"]]
    assert add_one.outputs["result"].connections == [double.inputs["value"]]
    assert double.outputs["result"].connections == [sink.inputs["value"]]
