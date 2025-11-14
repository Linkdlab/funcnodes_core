import pytest

from funcnodes_core.grouping_logic import GroupingLogic


def test_group_together_merges_nodes_and_groups_under_common_ancestor():
    logic = GroupingLogic()
    logic.add_group("root")
    logic.add_group("alpha", parent_group="root", node_ids=["n1"])
    logic.add_group("beta", parent_group="root", node_ids=["n2"])

    merged_id = logic.group_together(
        node_ids=["n1"],
        group_ids=["beta"],
        new_group_id="merged",
    )

    assert merged_id == "merged"
    merged = logic.get_group("merged")
    assert merged is not None
    assert merged["parent_group"] == "root"
    assert logic.find_group_of_node("n1") == "merged"
    assert logic.get_group("beta")["parent_group"] == "merged"
    # alpha became empty after moving n1 and should be cleaned up automatically
    assert logic.get_group("alpha") is None


def test_group_together_uses_parent_of_involved_group_when_needed():
    logic = GroupingLogic()
    logic.add_group("root")
    logic.add_group("mid", parent_group="root", node_ids=["keep-mid"])
    logic.add_group("leaf_a", parent_group="mid", node_ids=["a"])
    logic.add_group("leaf_b", parent_group="mid", node_ids=["b"])

    combo_id = logic.group_together(
        node_ids=["b"],
        group_ids=["mid"],
        new_group_id="combo",
    )

    assert combo_id == "combo"
    assert logic.get_group("combo")["parent_group"] == "root"
    assert logic.get_group("mid")["parent_group"] == "combo"
    assert logic.find_group_of_node("b") == "combo"
    # leaf_b lost its nodes and children, so it should be removed
    assert logic.get_group("leaf_b") is None
    assert logic.get_group_ancestors("mid") == ["combo", "root"]


def test_set_group_parent_rejects_cycles():
    logic = GroupingLogic()
    logic.add_group("g1", node_ids=["root-node"])
    logic.add_group("g2", parent_group="g1", node_ids=["child-node"])
    logic.add_group("g3", parent_group="g2", node_ids=["leaf-node"])

    with pytest.raises(ValueError):
        logic.set_group_parent("g2", "g2")

    with pytest.raises(ValueError):
        logic.set_group_parent("g3", "g1")

    assert logic.get_group("g1")["parent_group"] is None
    assert logic.get_group("g2")["parent_group"] == "g1"
    assert logic.get_group("g3")["parent_group"] == "g2"
