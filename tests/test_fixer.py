"""Unit tests for pyproject_dep_doctor.fixer."""

from pathlib import Path
from pyproject_dep_doctor.fixer import PyProjectFixer, fix_pyproject
from pyproject_dep_doctor.resolver import FixAction, ResolutionStrategy


def test_fixer_replace_and_diff():
    content = """\
[project]
name = "demo"
dependencies = [
    "requests<2.0.0",
]
"""
    fixer = PyProjectFixer(content)
    action = FixAction(
        package="requests",
        group="project.dependencies",
        old_spec="requests<2.0.0",
        new_spec="requests>=2.28.0",
        reason="Update requests",
        action_type="replace",
    )
    mod, applied = fixer.apply_actions([action])
    assert len(applied) == 1
    assert '"requests>=2.28.0"' in mod
    assert '"requests<2.0.0"' not in mod

    diff = fixer.get_diff("pyproject.toml")
    assert "-    \"requests<2.0.0\"," in diff
    assert "+    \"requests>=2.28.0\"," in diff


def test_fixer_remove():
    content = """\
[project]
name = "demo"
dependencies = [
    "requests>=2.0.0",
    "requests>=2.0.0",
]
"""
    fixer = PyProjectFixer(content)
    action = FixAction(
        package="requests",
        group="project.dependencies",
        old_spec="requests>=2.0.0",
        new_spec=None,
        reason="Remove duplicate",
        action_type="remove",
    )
    mod, applied = fixer.apply_actions([action])
    assert len(applied) == 1
    # Only one occurrence should remain
    assert mod.count("requests>=2.0.0") == 1


def test_fix_pyproject_in_memory(conflicting_toml):
    mod_content, diff, applied = fix_pyproject(
        conflicting_toml,
        strategy=ResolutionStrategy.INTERSECT,
        dry_run=True,
    )
    assert len(applied) > 0
    assert diff != ""


def test_fix_pyproject_file_mod(tmp_path, duplicate_toml):
    test_file = tmp_path / "pyproject.toml"
    test_file.write_text(duplicate_toml, encoding="utf-8")

    # Dry run should not touch disk
    mod_content, diff, applied = fix_pyproject(
        test_file,
        strategy=ResolutionStrategy.INTERSECT,
        dry_run=True,
        backup=True,
    )
    assert test_file.read_text(encoding="utf-8") == duplicate_toml
    assert not (tmp_path / "pyproject.toml.bak").exists()

    # Actual fix should modify file and create .bak
    mod_content, diff, applied = fix_pyproject(
        test_file,
        strategy=ResolutionStrategy.INTERSECT,
        dry_run=False,
        backup=True,
    )
    assert test_file.read_text(encoding="utf-8") == mod_content
    assert (tmp_path / "pyproject.toml.bak").exists()
    assert (tmp_path / "pyproject.toml.bak").read_text(encoding="utf-8") == duplicate_toml


def test_fix_pyproject_no_backup(tmp_path, duplicate_toml):
    test_file = tmp_path / "pyproject.toml"
    test_file.write_text(duplicate_toml, encoding="utf-8")

    fix_pyproject(
        test_file,
        strategy=ResolutionStrategy.INTERSECT,
        dry_run=False,
        backup=False,
    )
    assert not (tmp_path / "pyproject.toml.bak").exists()
