"""Unit tests for pyproject_dep_doctor.parser."""

from pathlib import Path
import pytest

from pyproject_dep_doctor.parser import (
    PyProjectParser,
    parse_pyproject,
    poetry_constraint_to_pep440,
)
from pyproject_dep_doctor.models import IssueType, IssueSeverity


def test_poetry_constraint_to_pep440():
    # Wildcards and empty
    assert poetry_constraint_to_pep440("") == ""
    assert poetry_constraint_to_pep440("*") == ""

    # Caret constraints
    assert poetry_constraint_to_pep440("^1.2.3") == ">=1.2.3,<2.0.0"
    assert poetry_constraint_to_pep440("^0.2.3") == ">=0.2.3,<0.3.0"
    assert poetry_constraint_to_pep440("^0.0.4") == ">=0.0.4,<0.0.5"
    assert poetry_constraint_to_pep440("^invalid") == ">=invalid"

    # Tilde constraints
    assert poetry_constraint_to_pep440("~1.2.3") == ">=1.2.3,<1.3.0"
    assert poetry_constraint_to_pep440("~1.2") == ">=1.2,<1.3.0"
    assert poetry_constraint_to_pep440("~1") == ">=1,<2.0.0"
    assert poetry_constraint_to_pep440("~invalid") == ">=invalid"

    # Standard PEP 440 untouched
    assert poetry_constraint_to_pep440(">=2.0.0,<3.0.0") == ">=2.0.0,<3.0.0"


def test_parse_pep621(valid_toml):
    parser = PyProjectParser(valid_toml, filepath="pyproject.toml")
    decls, issues = parser.parse()

    assert len(issues) == 0
    assert len(decls) == 6

    main_decls = [d for d in decls if d.group == "project.dependencies"]
    assert len(main_decls) == 3
    names = [d.name for d in main_decls]
    assert "requests" in names
    assert "click" in names
    assert "pydantic" in names
    assert all(not d.is_optional for d in main_decls)

    opt_decls = [d for d in decls if d.is_optional]
    assert len(opt_decls) == 3
    groups = {d.group for d in opt_decls}
    assert "project.optional-dependencies.dev" in groups
    assert "project.optional-dependencies.docs" in groups


def test_parse_poetry(poetry_toml):
    parser = PyProjectParser(poetry_toml)
    decls, issues = parser.parse()

    assert len(issues) == 0
    # python should be skipped, so requests and fastapi in main, pytest and requests in dev
    names = [d.name for d in decls]
    assert "python" not in names
    assert "requests" in names
    assert "fastapi" in names
    assert "pytest" in names

    groups = {d.group for d in decls}
    assert "tool.poetry.dependencies" in groups
    assert "tool.poetry.group.dev.dependencies" in groups


def test_parse_poetry_dict_and_legacy_dev():
    toml_str = """\
[tool.poetry]
name = "dict-poetry"
version = "0.1.0"

[tool.poetry.dependencies]
python = "^3.9"
foo = { version = "^1.2.0", markers = "sys_platform == 'win32'", extras = ["extra1", "extra2"], optional = true }

[tool.poetry.dev-dependencies]
bar = "~2.1.0"
"""
    parser = PyProjectParser(toml_str)
    decls, issues = parser.parse()

    assert len(issues) == 0
    foo_decl = next(d for d in decls if d.name == "foo")
    assert foo_decl.is_optional is True
    assert foo_decl.group == "tool.poetry.dependencies"
    assert "extra1" in foo_decl.extras
    assert "extra2" in foo_decl.extras
    assert foo_decl.marker is not None
    assert 'sys_platform == "win32"' in str(foo_decl.marker) or "sys_platform == 'win32'" in str(foo_decl.marker)

    bar_decl = next(d for d in decls if d.name == "bar")
    assert bar_decl.group == "tool.poetry.dev-dependencies"
    assert bar_decl.is_optional is True


def test_parse_pep735_and_pdm():
    toml_str = """\
[project]
name = "pep735-app"
version = "0.1.0"
dependencies = ["flask>=2.0.0"]

[dependency-groups]
lint = ["ruff>=0.1.0", "black>=23.0"]
test = ["pytest>=7.0.0"]

[tool.pdm.dev-dependencies]
docs = ["sphinx>=4.0.0"]
"""
    parser = PyProjectParser(toml_str)
    decls, issues = parser.parse()

    assert len(issues) == 0
    groups = {d.group for d in decls}
    assert "project.dependencies" in groups
    assert "dependency-groups.lint" in groups
    assert "dependency-groups.test" in groups
    assert "tool.pdm.dev-dependencies.docs" in groups


def test_parse_invalid_toml():
    invalid_toml = "broken [ unclosed table ] = {{"
    parser = PyProjectParser(invalid_toml)
    decls, issues = parser.parse()

    assert len(decls) == 0
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.SYNTAX_ERROR
    assert issues[0].severity == IssueSeverity.ERROR
    assert "Failed to parse TOML" in issues[0].message


def test_parse_invalid_pep508(syntax_error_toml):
    parser = PyProjectParser(syntax_error_toml)
    decls, issues = parser.parse()

    assert len(decls) == 0
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.SYNTAX_ERROR
    assert issues[0].severity == IssueSeverity.ERROR
    assert "Invalid PEP 508" in issues[0].message


def test_parse_pyproject_helper(tmp_path, valid_toml):
    # From string
    decls1, issues1 = parse_pyproject(valid_toml)
    assert len(issues1) == 0
    assert len(decls1) == 6

    # From file path
    test_file = tmp_path / "pyproject.toml"
    test_file.write_text(valid_toml, encoding="utf-8")

    decls2, issues2 = parse_pyproject(test_file)
    assert len(issues2) == 0
    assert len(decls2) == 6

    decls3, issues3 = parse_pyproject(str(test_file))
    assert len(issues3) == 0
    assert len(decls3) == 6
