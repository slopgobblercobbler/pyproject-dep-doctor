"""Unit tests for pyproject_dep_doctor.resolver."""

from packaging.specifiers import SpecifierSet
from pyproject_dep_doctor.parser import parse_pyproject
from pyproject_dep_doctor.resolver import (
    DependencyResolver,
    FixAction,
    ResolutionStrategy,
)


def test_fix_action():
    act = FixAction(
        package="requests",
        group="project.dependencies",
        old_spec="requests<2.0.0",
        new_spec="requests>=2.28.0",
        reason="Align versions",
        action_type="replace",
    )
    assert act.package == "requests"
    assert act.action_type == "replace"
    assert "REPLACE" in repr(act)
    d = act.to_dict()
    assert d["package"] == "requests"
    assert d["old_spec"] == "requests<2.0.0"
    assert d["new_spec"] == "requests>=2.28.0"

    rm_act = FixAction(
        package="requests",
        group="project.dependencies",
        old_spec="requests>=2.28.0",
        new_spec=None,
        reason="Remove duplicate",
        action_type="remove",
    )
    assert rm_act.action_type == "remove"
    assert "REMOVE" in repr(rm_act)


def test_resolve_duplicates(duplicate_toml):
    decls, _ = parse_pyproject(duplicate_toml)
    resolver = DependencyResolver(decls, strategy=ResolutionStrategy.INTERSECT)
    actions = resolver.resolve()

    assert len(actions) == 2
    replace_act = next(a for a in actions if a.action_type == "replace")
    remove_act = next(a for a in actions if a.action_type == "remove")

    assert replace_act.package == "pydantic"
    assert "pydantic>=2.0.0" in replace_act.new_spec
    assert remove_act.package == "pydantic"
    assert remove_act.action_type == "remove"


def test_resolve_identical_duplicates():
    toml_str = """\
[project]
name = "identical-dup"
version = "0.1.0"
dependencies = [
    "requests>=2.28.0",
    "requests>=2.28.0",
]
"""
    decls, _ = parse_pyproject(toml_str)
    resolver = DependencyResolver(decls)
    actions = resolver.resolve()

    assert len(actions) == 1
    assert actions[0].action_type == "remove"
    assert actions[0].package == "requests"


def test_resolve_conflicts_intersect(conflicting_toml):
    decls, _ = parse_pyproject(conflicting_toml)
    resolver = DependencyResolver(decls, strategy=ResolutionStrategy.INTERSECT)
    actions = resolver.resolve()

    assert len(actions) > 0
    urllib3_actions = [a for a in actions if a.package == "urllib3"]
    assert len(urllib3_actions) > 0


def test_resolve_conflicts_latest(conflicting_toml):
    decls, _ = parse_pyproject(conflicting_toml)
    resolver = DependencyResolver(decls, strategy=ResolutionStrategy.LATEST)
    actions = resolver.resolve()

    assert len(actions) > 0
    # For requests, main is >=2.28.0, docs is <2.25.0 -> latest should pick >=2.28.0
    req_actions = [a for a in actions if a.package == "requests"]
    assert any("2.28.0" in (a.new_spec or "") for a in req_actions)


def test_resolve_conflicts_loosen():
    toml_str = """\
[project]
name = "loosen-app"
version = "0.1.0"
dependencies = [
    "urllib3>=1.26.0,<2.0.0",
]

[project.optional-dependencies]
dev = [
    "urllib3>=2.0.0,<3.0.0",
]
"""
    decls, _ = parse_pyproject(toml_str)
    resolver = DependencyResolver(decls, strategy=ResolutionStrategy.LOOSEN)
    actions = resolver.resolve()

    assert len(actions) > 0
    # Loosen combines min lower and max upper: >=1.26.0,<3.0.0
    for act in actions:
        if act.package == "urllib3" and act.new_spec:
            assert ">=1.26.0" in act.new_spec
            assert "<3.0.0" in act.new_spec


def test_resolve_exclusive_markers_no_action(exclusive_markers_toml):
    decls, _ = parse_pyproject(exclusive_markers_toml)
    resolver = DependencyResolver(decls)
    actions = resolver.resolve()
    assert len(actions) == 0
