"""Hermetic tests for executor-agnostic write-set scheduling."""
from control_plane.execution_plan import plan_write_set_groups


def test_no_targets_overlap_runs_each_in_own_group():
    groups = plan_write_set_groups([["a.py"], ["b.py"], ["c.py"]])
    assert groups == [[0], [1], [2]]


def test_overlapping_targets_share_a_serial_group():
    groups = plan_write_set_groups([["a.py", "shared.py"], ["shared.py", "b.py"], ["c.py"]])
    assert [0, 1] in groups
    assert [2] in groups
    assert len(groups) == 2


def test_transitive_overlap_merges_into_one_group():
    # a~b (x), b~c (y) => a,b,c all serial
    groups = plan_write_set_groups([["x"], ["x", "y"], ["y"]])
    assert groups == [[0, 1, 2]]


def test_empty_targets_agent_conflicts_with_all():
    groups = plan_write_set_groups([["a.py"], [], ["b.py"]])
    assert groups == [[0, 1, 2]]


def test_path_normalization_detects_overlap():
    groups = plan_write_set_groups([["src/app.py"], ["src\\app.py"]])
    assert groups == [[0, 1]]


def test_empty_input_returns_empty():
    assert plan_write_set_groups([]) == []


def test_single_agent_single_group():
    assert plan_write_set_groups([["a.py"]]) == [[0]]
