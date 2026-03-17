import pytest

import funcnodes_core as fn
from funcnodes_core.node import Node, NodeInput, NodeOutput
from pytest_funcnodes import funcnodes_test


UNSPECIFIED = object()


def make_counter_node(node_id: str, *, does_trigger: bool = True):
    resolved_node_id = node_id

    class CounterNode(Node):
        node_id = resolved_node_id
        value = NodeInput(id="value", type=int, does_trigger=does_trigger)
        output = NodeOutput(id="output", type=int)

        def __init__(self, *args, **kwargs):
            super().__init__(*args, pretrigger_delay=0.0, **kwargs)
            self.call_count = 0

        async def func(self, value: int):
            self.call_count += 1
            self.outputs["output"].value = value

    return CounterNode


def build_nodes(scenario_name: str, node_flags: dict[str, bool]) -> dict[str, Node]:
    nodes: dict[str, Node] = {}
    for name, does_trigger in node_flags.items():
        node_cls = make_counter_node(
            f"trigger_matrix_{scenario_name.lower()}_{name.lower()}",
            does_trigger=does_trigger,
        )
        nodes[name] = node_cls()
    return nodes


def connect_nodes(
    nodes: dict[str, Node], connections: list[tuple[str, str, str]]
) -> None:
    for connection_type, src, dst in connections:
        if connection_type == "forward":
            nodes[src].inputs["value"].connect(nodes[dst].inputs["value"])
        elif connection_type == "output":
            nodes[src].outputs["output"].connect(nodes[dst].inputs["value"])
        else:
            raise ValueError(f"Unknown connection type: {connection_type}")


def apply_action(nodes: dict[str, Node], action: dict[str, object]) -> None:
    node = nodes[action["node"]]  # type: ignore[index]
    value = action["value"]
    does_trigger = action.get("does_trigger", UNSPECIFIED)

    if action["io"] == "input":
        setter = node.inputs["value"].set_value
    elif action["io"] == "output":
        setter = node.outputs["output"].set_value
    else:
        raise ValueError(f"Unknown io type: {action['io']}")

    if does_trigger is UNSPECIFIED:
        setter(value)
    else:
        setter(value, does_trigger=does_trigger)  # type: ignore[arg-type]


async def run_scenario(scenario: dict[str, object]) -> None:
    nodes = build_nodes(scenario["name"], scenario["node_flags"])  # type: ignore[arg-type]
    connect_nodes(nodes, scenario["connections"])  # type: ignore[arg-type]
    apply_action(nodes, scenario["action"])  # type: ignore[arg-type]
    await fn.run_until_complete(*nodes.values())

    expected_counts = scenario["expected_counts"]  # type: ignore[assignment]
    for name, expected_count in expected_counts.items():
        assert nodes[name].call_count == expected_count


INPUT_FORWARDING_SCENARIOS = [
    {
        "name": "input_forward_tt_unspecified",
        "node_flags": {"A": True, "B": True},
        "connections": [("forward", "A", "B")],
        "action": {"node": "A", "io": "input", "value": 1},
        "expected_counts": {"A": 1, "B": 1},
    },
    {
        "name": "input_forward_ft_unspecified",
        "node_flags": {"A": False, "B": True},
        "connections": [("forward", "A", "B")],
        "action": {"node": "A", "io": "input", "value": 1},
        "expected_counts": {"A": 0, "B": 1},
    },
    {
        "name": "input_forward_tf_unspecified",
        "node_flags": {"A": True, "B": False},
        "connections": [("forward", "A", "B")],
        "action": {"node": "A", "io": "input", "value": 1},
        "expected_counts": {"A": 1, "B": 0},
    },
    {
        "name": "input_forward_ff_unspecified",
        "node_flags": {"A": False, "B": False},
        "connections": [("forward", "A", "B")],
        "action": {"node": "A", "io": "input", "value": 1},
        "expected_counts": {"A": 0, "B": 0},
    },
    {
        "name": "input_forward_tt_explicit_false",
        "node_flags": {"A": True, "B": True},
        "connections": [("forward", "A", "B")],
        "action": {"node": "A", "io": "input", "value": 1, "does_trigger": False},
        "expected_counts": {"A": 0, "B": 0},
    },
    {
        "name": "input_forward_chain_tft_unspecified",
        "node_flags": {"A": True, "B": False, "C": True},
        "connections": [("forward", "A", "B"), ("forward", "B", "C")],
        "action": {"node": "A", "io": "input", "value": 1},
        "expected_counts": {"A": 1, "B": 0, "C": 1},
    },
    {
        "name": "input_forward_chain_tft_explicit_false",
        "node_flags": {"A": True, "B": False, "C": True},
        "connections": [("forward", "A", "B"), ("forward", "B", "C")],
        "action": {"node": "A", "io": "input", "value": 1, "does_trigger": False},
        "expected_counts": {"A": 0, "B": 0, "C": 0},
    },
    {
        "name": "input_forward_chain_ftft_unspecified",
        "node_flags": {"A": False, "B": True, "C": False, "D": True},
        "connections": [
            ("forward", "A", "B"),
            ("forward", "B", "C"),
            ("forward", "C", "D"),
        ],
        "action": {"node": "A", "io": "input", "value": 1},
        "expected_counts": {"A": 0, "B": 1, "C": 0, "D": 1},
    },
    {
        "name": "input_forward_fanout_t_tf_unspecified",
        "node_flags": {"A": True, "B": True, "C": False},
        "connections": [("forward", "A", "B"), ("forward", "A", "C")],
        "action": {"node": "A", "io": "input", "value": 1},
        "expected_counts": {"A": 1, "B": 1, "C": 0},
    },
    {
        "name": "input_forward_fanout_t_tt_explicit_false",
        "node_flags": {"A": True, "B": True, "C": True},
        "connections": [("forward", "A", "B"), ("forward", "A", "C")],
        "action": {"node": "A", "io": "input", "value": 1, "does_trigger": False},
        "expected_counts": {"A": 0, "B": 0, "C": 0},
    },
    {
        "name": "input_forward_tt_explicit_true",
        "node_flags": {"A": True, "B": True},
        "connections": [("forward", "A", "B")],
        "action": {"node": "A", "io": "input", "value": 1, "does_trigger": True},
        "expected_counts": {"A": 1, "B": 1},
    },
    {
        "name": "input_forward_tf_explicit_true",
        "node_flags": {"A": True, "B": False},
        "connections": [("forward", "A", "B")],
        "action": {"node": "A", "io": "input", "value": 1, "does_trigger": True},
        "expected_counts": {"A": 1, "B": 1},
    },
    {
        "name": "input_forward_ft_explicit_true",
        "node_flags": {"A": False, "B": True},
        "connections": [("forward", "A", "B")],
        "action": {"node": "A", "io": "input", "value": 1, "does_trigger": True},
        "expected_counts": {"A": 1, "B": 1},
    },
    {
        "name": "input_forward_ff_explicit_true",
        "node_flags": {"A": False, "B": False},
        "connections": [("forward", "A", "B")],
        "action": {"node": "A", "io": "input", "value": 1, "does_trigger": True},
        "expected_counts": {"A": 1, "B": 1},
    },
    {
        "name": "input_forward_chain_tft_explicit_true",
        "node_flags": {"A": True, "B": False, "C": True},
        "connections": [("forward", "A", "B"), ("forward", "B", "C")],
        "action": {"node": "A", "io": "input", "value": 1, "does_trigger": True},
        "expected_counts": {"A": 1, "B": 1, "C": 1},
    },
    {
        "name": "input_forward_chain_tff_explicit_true",
        "node_flags": {"A": True, "B": False, "C": False},
        "connections": [("forward", "A", "B"), ("forward", "B", "C")],
        "action": {"node": "A", "io": "input", "value": 1, "does_trigger": True},
        "expected_counts": {"A": 1, "B": 1, "C": 1},
    },
    {
        "name": "input_forward_fanout_t_ft_explicit_true",
        "node_flags": {"A": True, "B": False, "C": True},
        "connections": [("forward", "A", "B"), ("forward", "A", "C")],
        "action": {"node": "A", "io": "input", "value": 1, "does_trigger": True},
        "expected_counts": {"A": 1, "B": 1, "C": 1},
    },
    {
        "name": "input_forward_diamond",
        "node_flags": {"A": True, "B": True, "C": True, "D": True, "E": False},
        "connections": [
            ("forward", "A", "B"),
            ("forward", "A", "C"),
            ("forward", "B", "D"),
            ("forward", "C", "E"),
        ],
        "action": {"node": "A", "io": "input", "value": 1},
        "expected_counts": {"A": 1, "B": 1, "C": 1, "D": 1, "E": 0},
    },
]


OUTPUT_PROPAGATION_SCENARIOS = [
    {
        "name": "output_to_input_t_unspecified",
        "node_flags": {"A": True, "B": True},
        "connections": [("output", "A", "B")],
        "action": {"node": "A", "io": "output", "value": 1},
        "expected_counts": {"A": 0, "B": 1},
    },
    {
        "name": "output_to_input_f_unspecified",
        "node_flags": {"A": True, "B": False},
        "connections": [("output", "A", "B")],
        "action": {"node": "A", "io": "output", "value": 1},
        "expected_counts": {"A": 0, "B": 0},
    },
    {
        "name": "output_to_input_t_explicit_false",
        "node_flags": {"A": True, "B": True},
        "connections": [("output", "A", "B")],
        "action": {"node": "A", "io": "output", "value": 1, "does_trigger": False},
        "expected_counts": {"A": 0, "B": 0},
    },
    {
        "name": "output_forward_chain_ft_unspecified",
        "node_flags": {"A": True, "B": False, "C": True},
        "connections": [("output", "A", "B"), ("forward", "B", "C")],
        "action": {"node": "A", "io": "output", "value": 1},
        "expected_counts": {"A": 0, "B": 0, "C": 1},
    },
    {
        "name": "output_forward_chain_ft_explicit_false",
        "node_flags": {"A": True, "B": False, "C": True},
        "connections": [("output", "A", "B"), ("forward", "B", "C")],
        "action": {"node": "A", "io": "output", "value": 1, "does_trigger": False},
        "expected_counts": {"A": 0, "B": 0, "C": 0},
    },
    {
        "name": "output_to_input_t_explicit_true",
        "node_flags": {"A": True, "B": True},
        "connections": [("output", "A", "B")],
        "action": {"node": "A", "io": "output", "value": 1, "does_trigger": True},
        "expected_counts": {"A": 0, "B": 1},
    },
    {
        "name": "output_to_input_f_explicit_true",
        "node_flags": {"A": True, "B": False},
        "connections": [("output", "A", "B")],
        "action": {"node": "A", "io": "output", "value": 1, "does_trigger": True},
        "expected_counts": {"A": 0, "B": 0},
    },
    {
        "name": "output_forward_chain_ft_explicit_true",
        "node_flags": {"A": True, "B": False, "C": True},
        "connections": [("output", "A", "B"), ("forward", "B", "C")],
        "action": {"node": "A", "io": "output", "value": 1, "does_trigger": True},
        "expected_counts": {"A": 0, "B": 0, "C": 1},
    },
    {
        "name": "output_forward_chain_tf_explicit_true",
        "node_flags": {"A": True, "B": True, "C": False},
        "connections": [("output", "A", "B"), ("forward", "B", "C")],
        "action": {"node": "A", "io": "output", "value": 1, "does_trigger": True},
        "expected_counts": {"A": 0, "B": 1, "C": 0},
    },
    {
        "name": "output_forward_chain_ff_explicit_true",
        "node_flags": {"A": True, "B": False, "C": False},
        "connections": [("output", "A", "B"), ("forward", "B", "C")],
        "action": {"node": "A", "io": "output", "value": 1, "does_trigger": True},
        "expected_counts": {"A": 0, "B": 0, "C": 0},
    },
    {
        "name": "output_fanout_explicit_true",
        "node_flags": {"A": True, "B": False, "C": True},
        "connections": [("output", "A", "B"), ("output", "A", "C")],
        "action": {"node": "A", "io": "output", "value": 1, "does_trigger": True},
        "expected_counts": {"A": 0, "B": 0, "C": 1},
    },
]


MIXED_PROPAGATION_SCENARIOS = [
    {
        "name": "execution_chain_output_output",
        "node_flags": {"A": True, "B": True, "C": True},
        "connections": [("output", "A", "B"), ("output", "B", "C")],
        "action": {"node": "A", "io": "output", "value": 1},
        "expected_counts": {"A": 0, "B": 1, "C": 1},
    },
    {
        "name": "input_then_execution_chain_output_false",
        "node_flags": {"A": True, "B": True, "C": False},
        "connections": [("forward", "A", "B"), ("output", "B", "C")],
        "action": {"node": "A", "io": "input", "value": 1},
        "expected_counts": {"A": 1, "B": 1, "C": 0},
    },
    {
        "name": "mixed_output_diamond",
        "node_flags": {"A": True, "B": False, "C": True, "D": True, "E": True},
        "connections": [
            ("output", "A", "B"),
            ("output", "A", "C"),
            ("forward", "B", "D"),
            ("output", "C", "E"),
        ],
        "action": {"node": "A", "io": "output", "value": 1},
        "expected_counts": {"A": 0, "B": 0, "C": 1, "D": 1, "E": 1},
    },
]


@pytest.mark.parametrize(
    "scenario", INPUT_FORWARDING_SCENARIOS, ids=lambda s: s["name"]
)
@funcnodes_test
async def test_input_forwarding_trigger_matrix(scenario):
    await run_scenario(scenario)


@pytest.mark.parametrize(
    "scenario", OUTPUT_PROPAGATION_SCENARIOS, ids=lambda s: s["name"]
)
@funcnodes_test
async def test_output_propagation_trigger_matrix(scenario):
    await run_scenario(scenario)


@pytest.mark.parametrize(
    "scenario", MIXED_PROPAGATION_SCENARIOS, ids=lambda s: s["name"]
)
@funcnodes_test
async def test_mixed_trigger_propagation_matrix(scenario):
    await run_scenario(scenario)
