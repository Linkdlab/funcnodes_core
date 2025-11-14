import funcnodes_core as fn
from funcnodes_core.io import NodeInput
from funcnodes_core.nodespace import NodeSpace
from funcnodes_core.utils.saving import (
    serialize_nodeio_for_saving,
    serialize_node_for_saving,
    serialize_nodespace_for_saving,
)


def test_serialize_nodeio_for_saving_drops_runtime_value():
    io = NodeInput(id="alpha", type=int, default=0)
    io.value = 5

    serialized = serialize_nodeio_for_saving(io)

    assert serialized["id"] == "alpha"
    assert "value" not in serialized


def test_serialize_node_for_saving_omits_trigger_input_and_redundant_fields():
    @fn.NodeDecorator("test_saving_simple")
    def sample(alpha: int, beta: str = "x") -> str:
        return beta

    node = sample()

    serialized = serialize_node_for_saving(node)

    assert "_triggerinput" not in serialized["io"]
    assert serialized["io"]["alpha"]["is_input"] is True
    assert "value" not in serialized["io"]["alpha"]
    assert "type" not in serialized["io"]["alpha"]
    assert serialized["io"]["beta"]["is_input"] is True
    assert serialized["io"]["out"]["is_input"] is False


def test_serialize_node_for_saving_keeps_instance_specific_changes():
    @fn.NodeDecorator("test_saving_overrides")
    def sample(alpha: int, beta: str = "x") -> str:  # noqa: ARG001 - required by decorator
        return beta

    node = sample()
    node.reset_inputs_on_trigger = True
    node.description = "custom-description"
    node.render_options["theme"] = "dark"
    node.set_property("density", 0.5)

    node.inputs["alpha"]._description = "Alpha input"
    node.inputs["alpha"].update_value_options(options=["alpha"])
    node.inputs["alpha"]._default_render_options = {"style": "slider"}

    serialized = serialize_node_for_saving(node)
    alpha_io = serialized["io"]["alpha"]

    assert serialized["reset_inputs_on_trigger"] is True
    assert serialized["description"] == "custom-description"
    assert serialized["render_options"] == {"theme": "dark"}
    assert serialized["properties"] == {"density": 0.5}

    assert alpha_io["description"] == "Alpha input"
    assert alpha_io["render_options"] == {"style": "slider"}
    assert alpha_io["value_options"]["options"] == ["alpha"]


def test_serialize_nodespace_for_saving_collects_nodes_edges_and_props():
    @fn.NodeDecorator("test_space_source")
    def source(val: int) -> int:
        return val

    @fn.NodeDecorator("test_space_sink")
    def sink(val: int) -> int:
        return val

    source_node = source()
    sink_node = sink()
    source_node.outputs["out"].connect(sink_node.inputs["val"])

    space = NodeSpace()
    space.add_node_instance(source_node)
    space.add_node_instance(sink_node)
    space.set_property("label", {"color": "blue"})

    serialized = serialize_nodespace_for_saving(space)

    assert len(serialized["nodes"]) == 2
    assert serialized["prop"] == {"label": {"color": "blue"}}
    assert serialized["groups"] == {}
    assert serialized["edges"] == [[source_node.uuid, "out", sink_node.uuid, "val"]]
