# --- Hierarchical Grouping API ---
from typing import List, Dict, Any, Optional, TypedDict, Tuple
from uuid import uuid4

class NodeGroup(TypedDict, total=False):
    node_ids: List[str]
    child_groups: List[str]
    parent_group: Optional[str]
    meta: Dict[str, Any]
    position: Optional[Tuple[float, float]]




class GroupingLogic:
    """
    Manages a hierarchical grouping of nodes.

    This class maintains a consistent state where:
    1. A node can belong to at most one group.
    2. A group can have at most one parent.
    3. The hierarchy is a forest (a collection of trees), not a graph with cycles.

    It uses an internal map for efficient node-to-group lookups, ensuring that
    operations are fast and data integrity is maintained at all times.
    """

    def __init__(self):
        self._groups: Dict[str, NodeGroup] = {}
        self._node_to_group_map: Dict[str, str] = {}
        self._is_cleaning = False

    def add_group(self, group_id: str, node_ids: Optional[List[str]] = None, parent_group: Optional[str] = None, meta: Optional[Dict[str, Any]] = None) -> str:
        """
        Creates a new group, optionally associating nodes and a parent with it.
        This operation is atomic and safe from premature cleanup.

        Args:
            group_id: The unique identifier for the new group.
            node_ids: A list of node IDs to add to this new group.
            parent_group: The ID of the parent group.
            meta: Optional metadata for the group.

        Returns:
            The ID of the created group.
        """
        if group_id in self._groups:
            raise ValueError(f"Group with id '{group_id}' already exists.")

        # Step 1: Create the group object but do not connect it yet.
        self._groups[group_id] = NodeGroup(
            node_ids=[],
            child_groups=[],
            parent_group=None,
            meta=meta or {},
        )

        # Step 2: Populate the group with nodes. This makes it non-empty and
        # thus safe from being cleaned up as an "empty leaf".
        # This step might trigger cleanups if nodes are moved from other groups,
        # but our new group is safe.
        if node_ids:
            self.add_nodes_to_group(group_id, node_ids)
        
        # Step 3: NOW that the group is stable, set its parent. Any cleanup
        # triggered by this operation will not affect our new group.
        if parent_group:
            self.set_group_parent(group_id, parent_group)
        
        return group_id

    def remove_group(self, group_id: str, recursive: bool = False):
        """
        Removes a group.
        """
        if group_id not in self._groups:
            return

        group = self._groups[group_id]
        parent_id = group.get("parent_group")
        
        child_ids = list(group.get("child_groups", []))
        for child_id in child_ids:
            if recursive:
                self.remove_group(child_id, recursive=True)
            else:
                self.set_group_parent(child_id, parent_id)

        self.ungroup_nodes(list(group.get("node_ids", [])))

        if parent_id and parent_id in self._groups:
            if group_id in self._groups[parent_id]["child_groups"]:
                self._groups[parent_id]["child_groups"].remove(group_id)

        # Use .pop() to safely remove the key
        self._groups.pop(group_id, None)
        
        self._cleanup_empty_groups()

    def get_group(self, group_id: str) -> Optional[NodeGroup]:
        return self._groups.get(group_id)

    def get_all_groups(self) -> Dict[str, NodeGroup]:
        return self._groups

    def set_group_parent(self, child_id: str, parent_id: Optional[str]):
        """
        Sets or unsets the parent of a group, ensuring the hierarchy is valid.
        """
        if child_id not in self._groups:
            raise ValueError(f"Child group '{child_id}' not found.")
        if parent_id and parent_id not in self._groups:
            raise ValueError(f"Parent group '{parent_id}' not found.")
        if child_id == parent_id:
            raise ValueError("A group cannot be its own parent.")

        if parent_id in self.get_group_ancestors(child_id) + [child_id]:
             raise ValueError("Cannot set parent, as this would create a circular dependency.")

        old_parent_id = self._groups[child_id].get("parent_group")
        if old_parent_id and old_parent_id in self._groups:
            if child_id in self._groups[old_parent_id]["child_groups"]:
                self._groups[old_parent_id]["child_groups"].remove(child_id)

        self._groups[child_id]["parent_group"] = parent_id
        if parent_id:
            if child_id not in self._groups[parent_id]["child_groups"]:
                self._groups[parent_id]["child_groups"].append(child_id)
        
        self._cleanup_empty_groups()

    def add_nodes_to_group(self, group_id: str, node_ids: List[str]):
        """
        Adds a list of nodes to a group. If nodes are already in other groups,
        they are moved to this one.
        """
        if group_id not in self._groups:
            raise ValueError(f"Group '{group_id}' not found.")

        self.ungroup_nodes(node_ids)

        group = self._groups[group_id]
        for node_id in node_ids:
            if node_id not in group["node_ids"]:
                group["node_ids"].append(node_id)
            self._node_to_group_map[node_id] = group_id
    
    def remove_nodes_from_group(self, group_id: str, node_ids: List[str]):
        """
        Removes specific nodes from a given group.
        """
        if group_id not in self._groups:
            return
            
        group = self._groups[group_id]
        for node_id in node_ids:
            if node_id in group["node_ids"]:
                try:
                    group["node_ids"].remove(node_id)
                    if self._node_to_group_map.get(node_id) == group_id:
                        del self._node_to_group_map[node_id]
                except ValueError:
                    # Ignore if node was already removed somehow
                    pass
        
        self._cleanup_empty_groups()

    def ungroup_nodes(self, node_ids: List[str]):
        """
        Moves nodes out of whatever group they are in, making them ungrouped.
        """
        groups_to_cleanup = set()
        for node_id in node_ids:
            current_group_id = self.find_group_of_node(node_id)
            if current_group_id:
                groups_to_cleanup.add(current_group_id)
                group = self._groups[current_group_id]
                if node_id in group["node_ids"]:
                    group["node_ids"].remove(node_id)
                del self._node_to_group_map[node_id]
        
        # Only cleanup if any groups were actually modified
        if groups_to_cleanup:
            self._cleanup_empty_groups()

    def set_group_meta(self, group_id: str, meta: Dict[str, Any]):
        if group_id in self._groups:
            self._groups[group_id]["meta"] = meta
        else:
            raise ValueError(f"Group '{group_id}' not found.")

    def find_group_of_node(self, node_id: str) -> Optional[str]:
        return self._node_to_group_map.get(node_id)

    def get_group_ancestors(self, group_id: str) -> List[str]:
        ancestors = []
        current_id = self._groups.get(group_id, {}).get("parent_group")
        while current_id:
            ancestors.append(current_id)
            if current_id == self._groups.get(current_id, {}).get("parent_group"): break # Self-parent cycle
            current_id = self._groups.get(current_id, {}).get("parent_group")
        return ancestors

    def group_together(self, node_ids: Optional[List[str]] = None, group_ids: Optional[List[str]] = None, new_group_id: Optional[str] = None) -> str:
        """
        Creates a new group containing the specified nodes and child groups.

        This powerful method takes lists of nodes and existing groups and places
        them together under a new parent group. It intelligently determines the
        best location for this new group in the hierarchy by finding the common
        ancestor of all items being grouped.

        Args:
            node_ids: A list of node IDs to be placed directly in the new group.
            group_ids: A list of existing group IDs that will become children
                       of the new group.
            new_group_id: An optional ID for the new group. If not provided,
                          a unique ID will be generated.

        Returns:
            The ID of the newly created group.
        
        Raises:
            ValueError: If both node_ids and group_ids are empty, or if an
                        invalid grouping is attempted (e.g., making a group a
                        child of itself).
        """
        node_ids = node_ids or []
        group_ids = group_ids or []
        if not node_ids and not group_ids:
            raise ValueError("Cannot group with empty node_ids and group_ids.")

        gid = new_group_id or uuid4().hex
        if new_group_id and gid in self._groups:
            raise ValueError(f"Group with id '{gid}' already exists.")
        if gid in group_ids:
            raise ValueError("A group cannot be a child of itself.")

        pre_cleaning = self._is_cleaning
        self._is_cleaning = True
        try:
            # --- Step 1: Find the common ancestor for the new group ---
            original_node_group_ids = {self.find_group_of_node(nid) for nid in node_ids if self.find_group_of_node(nid)}
            all_involved_group_ids = {g for g in original_node_group_ids.union(set(group_ids)) if g in self._groups}

            common_ancestor_id = None
            if all_involved_group_ids:
                ancestor_chains = [[g] + self.get_group_ancestors(g) for g in all_involved_group_ids]
                if ancestor_chains:
                    common_ancestors = set(ancestor_chains[0])
                    for chain in ancestor_chains[1:]:
                        common_ancestors.intersection_update(set(chain))
                    
                    if common_ancestors:
                        tentative_ancestor = max(common_ancestors, key=lambda a_gid: ancestor_chains[0].index(a_gid))
                        
                        if tentative_ancestor in all_involved_group_ids:
                            # The common ancestor is one of the groups being moved.
                            # The new group's parent should be the parent of this group.
                            parent_group = self.get_group(tentative_ancestor)
                            common_ancestor_id = parent_group.get("parent_group") if parent_group else None
                        else:
                            common_ancestor_id = tentative_ancestor
            
            # --- Step 2: Create the new group and arrange nodes/children ---
            # Create the new group under the determined common ancestor.
            self.add_group(group_id=gid, parent_group=common_ancestor_id)
            
            # Move the specified nodes into the new group.
            if node_ids:
                self.add_nodes_to_group(gid, node_ids)
            
            # Reparent the specified groups to become children of the new group.
            for child_gid in group_ids:
                self.set_group_parent(child_gid, gid)

        finally:
            self._is_cleaning = pre_cleaning

        # Perform a final cleanup for any groups that became empty.
        self._cleanup_empty_groups()
        return gid

    def _cleanup_empty_groups(self):
        """
        Iteratively removes any groups that contain no nodes and no child groups.
        """
        if self._is_cleaning:
            return

        self._is_cleaning = True
        try:
            while True:
                empty_leaf_groups = [
                    gid for gid, group in self._groups.items()
                    if not group.get("node_ids") and not group.get("child_groups")
                ]
                
                if not empty_leaf_groups:
                    break

                for group_id in empty_leaf_groups:
                    self.remove_group(group_id)
        finally:
            self._is_cleaning = False

    def deserialize(self, group_data: Dict[str, NodeGroup]):
        """
        Loads the entire group state from a dictionary.
        """
        self._groups = group_data or {}
        self._node_to_group_map.clear()
        
        for group_id, group in self._groups.items():
            group.setdefault("node_ids", [])
            group.setdefault("child_groups", [])
            
            for node_id in group["node_ids"]:
                self._node_to_group_map[node_id] = group_id

    def serialize(self) -> Dict[str, NodeGroup]:
        return self.get_all_groups()