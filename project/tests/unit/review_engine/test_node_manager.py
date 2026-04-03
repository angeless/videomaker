"""Tests for NodeManager — R7 + R8."""

import pytest

from modules.review_engine.node_manager import (
    NODE_GRAPH,
    NodeManager,
    NodeState,
)


class TestNodeManagerDAG:

    def test_topo_sort(self):
        """Topological order respects all dependencies."""
        mgr = NodeManager()
        order = mgr.get_execution_order()
        assert len(order) == len(NODE_GRAPH)
        # transcode must be first (no deps)
        assert order[0] == "transcode"
        # final_export must be last (depends on everything)
        assert order[-1] == "final_export"
        # Each node appears after its dependencies
        for node, deps in NODE_GRAPH.items():
            node_idx = order.index(node)
            for dep in deps:
                assert order.index(dep) < node_idx, f"{dep} should come before {node}"

    def test_affected_nodes(self):
        """Changing apply_edits affects all downstream nodes."""
        mgr = NodeManager()
        affected = mgr.get_affected_nodes("apply_edits")
        assert "render_frames" in affected
        assert "merge_audio" in affected
        assert "final_export" in affected
        # But not upstream
        assert "transcode" not in affected
        assert "analyze" not in affected

    def test_no_cycle(self):
        """Default graph has no cycles."""
        mgr = NodeManager()  # Would raise if cycles exist
        assert len(mgr.get_execution_order()) == 10

    def test_cycle_detection(self):
        """A cyclic graph raises ValueError."""
        cyclic = {"a": ["b"], "b": ["c"], "c": ["a"]}
        with pytest.raises(ValueError, match="cycle"):
            NodeManager(graph=cyclic)

    def test_status_tracking(self):
        """Node state transitions."""
        mgr = NodeManager()
        assert mgr.get_state("transcode") == NodeState.PENDING
        mgr.set_state("transcode", NodeState.RUNNING)
        assert mgr.get_state("transcode") == NodeState.RUNNING
        mgr.set_state("transcode", NodeState.DONE)
        assert mgr.get_state("transcode") == NodeState.DONE

    def test_leaf_node_no_downstream(self):
        """final_export has no downstream nodes."""
        mgr = NodeManager()
        affected = mgr.get_affected_nodes("final_export")
        assert affected == []


# ── R8: Selective re-run ──

class TestPlanExecution:

    def test_auto_skip_cached(self):
        """Auto mode skips cached nodes (except the changed one)."""
        mgr = NodeManager()
        plan = mgr.plan_execution(
            changed_node="apply_edits",
            cached_artifacts={"render_frames", "merge_audio", "enhance_audio", "add_bgm", "final_export"},
        )
        assert "apply_edits" in plan["run"]
        # Downstream cached nodes should be skipped
        assert "render_frames" in plan["skip"]

    def test_auto_run_missing(self):
        """Auto mode runs nodes without cached artifacts."""
        mgr = NodeManager()
        plan = mgr.plan_execution(
            changed_node="apply_edits",
            cached_artifacts=set(),
        )
        assert "apply_edits" in plan["run"]
        assert "render_frames" in plan["run"]
        assert len(plan["skip"]) == 0

    def test_force_rerun(self):
        """Force mode re-runs even with cache."""
        mgr = NodeManager()
        plan = mgr.plan_execution(
            changed_node="apply_edits",
            mode_overrides={"render_frames": "force"},
            cached_artifacts={"render_frames"},
        )
        assert "render_frames" in plan["run"]

    def test_only_downstream(self):
        """Only the changed node and its downstream are evaluated."""
        mgr = NodeManager()
        plan = mgr.plan_execution(changed_node="enhance_audio")
        all_nodes = plan["run"] + plan["skip"]
        assert "transcode" not in all_nodes
        assert "analyze" not in all_nodes
        assert "enhance_audio" in all_nodes
        assert "add_bgm" in all_nodes
        assert "final_export" in all_nodes
