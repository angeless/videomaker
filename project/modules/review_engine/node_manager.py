"""NodeManager — DAG-based render pipeline with selective re-execution.

Defines a 10-node dependency graph for the render pipeline. Each node
has a state (pending/running/done/failed/skipped) and can be selectively
re-run based on mode (auto/skip/force).
"""

import logging
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class NodeState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Node:
    name: str
    depends_on: List[str] = field(default_factory=list)
    state: NodeState = NodeState.PENDING
    artifact_key: Optional[str] = None  # key in artifact store


# The 10-node pipeline DAG
NODE_GRAPH: Dict[str, List[str]] = {
    "transcode":      [],
    "analyze":        ["transcode"],
    "thumbnails":     ["transcode"],
    "waveform":       ["transcode"],
    "apply_edits":    ["analyze"],
    "render_frames":  ["apply_edits"],
    "merge_audio":    ["render_frames"],
    "enhance_audio":  ["merge_audio"],
    "add_bgm":        ["enhance_audio"],
    "final_export":   ["add_bgm", "thumbnails", "waveform"],
}


class NodeManager:
    """Manage the render pipeline DAG."""

    def __init__(self, graph: Optional[Dict[str, List[str]]] = None):
        self._graph = graph or NODE_GRAPH
        self._nodes: Dict[str, Node] = {}
        for name, deps in self._graph.items():
            self._nodes[name] = Node(name=name, depends_on=list(deps))
        self._validate_no_cycles()

    def _validate_no_cycles(self) -> None:
        """Topological sort to detect cycles."""
        in_degree = {n: 0 for n in self._graph}
        for deps in self._graph.values():
            for d in deps:
                in_degree[d] = in_degree.get(d, 0)  # ensure key exists

        # Build adjacency (parent → children)
        children: Dict[str, List[str]] = {n: [] for n in self._graph}
        for name, deps in self._graph.items():
            for d in deps:
                children[d].append(name)

        queue = deque(n for n, deg in in_degree.items() if deg == 0)
        # Recount in_degree from graph
        in_deg = {n: len(deps) for n, deps in self._graph.items()}
        queue = deque(n for n, d in in_deg.items() if d == 0)
        visited = 0
        q = deque(queue)
        while q:
            node = q.popleft()
            visited += 1
            for child in children.get(node, []):
                in_deg[child] -= 1
                if in_deg[child] == 0:
                    q.append(child)

        if visited != len(self._graph):
            raise ValueError("DAG contains a cycle")

    def get_execution_order(self) -> List[str]:
        """Return nodes in topological order (Kahn's algorithm)."""
        children: Dict[str, List[str]] = {n: [] for n in self._graph}
        for name, deps in self._graph.items():
            for d in deps:
                children[d].append(name)

        in_deg = {n: len(deps) for n, deps in self._graph.items()}
        queue = deque(sorted(n for n, d in in_deg.items() if d == 0))
        order = []

        while queue:
            node = queue.popleft()
            order.append(node)
            for child in sorted(children.get(node, [])):
                in_deg[child] -= 1
                if in_deg[child] == 0:
                    queue.append(child)

        return order

    def get_affected_nodes(self, changed_node: str) -> List[str]:
        """Get all downstream nodes affected by a change (BFS)."""
        children: Dict[str, List[str]] = {n: [] for n in self._graph}
        for name, deps in self._graph.items():
            for d in deps:
                children[d].append(name)

        visited: Set[str] = set()
        queue = deque([changed_node])
        affected = []

        while queue:
            node = queue.popleft()
            for child in children.get(node, []):
                if child not in visited:
                    visited.add(child)
                    affected.append(child)
                    queue.append(child)

        return affected

    def get_state(self, node_name: str) -> NodeState:
        return self._nodes[node_name].state

    def set_state(self, node_name: str, state: NodeState) -> None:
        self._nodes[node_name].state = state

    def get_all_states(self) -> Dict[str, str]:
        return {n: node.state.value for n, node in self._nodes.items()}

    def plan_execution(
        self,
        changed_node: str,
        mode_overrides: Optional[Dict[str, str]] = None,
        cached_artifacts: Optional[Set[str]] = None,
    ) -> Dict[str, List[str]]:
        """Decide which nodes to run/skip based on mode and cache.

        Args:
            changed_node: The node that triggered re-execution
            mode_overrides: {node_name: "auto"|"skip"|"force"}
            cached_artifacts: Set of node names that have cached artifacts

        Returns:
            {"run": [...], "skip": [...], "reason": {node: reason}}
        """
        mode_overrides = mode_overrides or {}
        cached_artifacts = cached_artifacts or set()

        # changed_node + all downstream
        to_evaluate = [changed_node] + self.get_affected_nodes(changed_node)
        # Keep topological order
        topo_order = self.get_execution_order()
        to_evaluate_ordered = [n for n in topo_order if n in to_evaluate]

        run = []
        skip = []
        reasons = {}

        for node in to_evaluate_ordered:
            mode = mode_overrides.get(node, "auto")

            if mode == "skip":
                skip.append(node)
                reasons[node] = "mode=skip (forced)"
            elif mode == "force":
                run.append(node)
                reasons[node] = "mode=force (forced rerun)"
            else:  # auto
                if node in cached_artifacts and node != changed_node:
                    skip.append(node)
                    reasons[node] = "auto: cached artifact exists"
                else:
                    run.append(node)
                    reasons[node] = "auto: no cache or is changed node"

        return {"run": run, "skip": skip, "reason": reasons}
