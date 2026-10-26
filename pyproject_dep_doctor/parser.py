"""Parser for pyproject.toml files supporting PEP 621, Poetry, Flit, and PEP 735 formats."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        import toml as tomllib  # type: ignore

from packaging.requirements import InvalidRequirement, Requirement

from .models import (
    DependencyDeclaration,
    DependencyIssue,
    IssueSeverity,
    IssueType,
    canonicalize_name,
)


def poetry_constraint_to_pep440(version_str: str) -> str:
    """Convert Poetry-style version constraints (^, ~, *) into standard PEP 440 specifiers."""
    version_str = version_str.strip()
    if not version_str or version_str == "*":
        return ""

    # Caret constraint ^X.Y.Z
    if version_str.startswith("^"):
        v = version_str[1:].strip()
        parts = v.split(".")
        try:
            major = int(parts[0])
            minor = int(parts[1]) if len(parts) > 1 else 0
            patch = int(parts[2]) if len(parts) > 2 else 0
        except ValueError:
            return f">={v}"

        if major > 0:
            return f">={v},<{major + 1}.0.0"
        elif minor > 0:
            return f">={v},<0.{minor + 1}.0"
        else:
            return f">={v},<0.0.{patch + 1}"

    # Tilde constraint ~X.Y.Z or ~1.2
    if version_str.startswith("~"):
        v = version_str[1:].strip()
        parts = v.split(".")
        try:
            major = int(parts[0])
            minor = int(parts[1]) if len(parts) > 1 else 0
        except ValueError:
            return f">={v}"

        if len(parts) == 1:
            return f">={v},<{major + 1}.0.0"
        return f">={v},<{major}.{minor + 1}.0"

    return version_str


class PyProjectParser:
    """Parses pyproject.toml and extracts dependency declarations and syntax errors."""

    def __init__(self, content: str, filepath: str = "pyproject.toml"):
        self.content = content
        self.filepath = filepath
        self.lines = content.splitlines()
        self.parsed_toml: Dict[str, Any] = {}
        self.declarations: List[DependencyDeclaration] = []
        self.syntax_issues: List[DependencyIssue] = []

    def parse(self) -> Tuple[List[DependencyDeclaration], List[DependencyIssue]]:
        """Parse TOML and return (declarations, syntax_issues)."""
        try:
            if hasattr(tomllib, "loads"):
                self.parsed_toml = tomllib.loads(self.content)
            else:
                self.parsed_toml = tomllib.loads(self.content)
        except Exception as e:
            self.syntax_issues.append(
                DependencyIssue(
                    issue_type=IssueType.SYNTAX_ERROR,
                    severity=IssueSeverity.ERROR,
                    package="pyproject.toml",
                    message=f"Failed to parse TOML format: {e}",
                    groups=[],
                    line_number=getattr(e, "lineno", 1) or 1,
                )
            )
            return [], self.syntax_issues

        self._parse_pep621()
        self._parse_poetry()
        self._parse_pep735()
        self._parse_pdm()

        return self.declarations, self.syntax_issues

    def _find_line_number(self, target_str: str, group_hint: Optional[str] = None) -> Optional[int]:
        """Attempt to find the 1-based line number for a dependency string."""
        clean_target = target_str.strip().strip("'\"")
        pkg_name = clean_target.split("<")[0].split(">")[0].split("=")[0].split("!")[0].split("~")[0].strip()

        # Try exact or substring match
        for idx, line in enumerate(self.lines, start=1):
            if clean_target in line:
                return idx

        # Fallback to package name match
        if pkg_name:
            for idx, line in enumerate(self.lines, start=1):
                if pkg_name in line and not line.strip().startswith("#"):
                    return idx

        return None

    def _add_requirement(self, raw_str: str, group: str, is_optional: bool = False):
        """Parse a PEP 508 requirement string and add declaration or record syntax error."""
        line_num = self._find_line_number(raw_str, group)
        try:
            req = Requirement(raw_str)
            decl = DependencyDeclaration(
                name=req.name,
                raw_spec=raw_str,
                group=group,
                specifier=req.specifier,
                marker=req.marker,
                extras=req.extras,
                line_number=line_num,
                is_optional=is_optional,
            )
            self.declarations.append(decl)
        except InvalidRequirement as e:
            pkg_guess = raw_str.split()[0] if raw_str else "unknown"
            self.syntax_issues.append(
                DependencyIssue(
                    issue_type=IssueType.SYNTAX_ERROR,
                    severity=IssueSeverity.ERROR,
                    package=pkg_guess,
                    message=f"Invalid PEP 508 requirement syntax '{raw_str}': {e}",
                    groups=[group],
                    line_number=line_num,
                )
            )

    def _parse_pep621(self):
        """Parse standard PEP 621 [project] table."""
        project = self.parsed_toml.get("project", {})
        if not isinstance(project, dict):
            return

        # Main dependencies
        dependencies = project.get("dependencies", [])
        if isinstance(dependencies, list):
            for dep in dependencies:
                if isinstance(dep, str):
                    self._add_requirement(dep, group="project.dependencies", is_optional=False)

        # Optional dependencies (extras)
        optional_deps = project.get("optional-dependencies", {})
        if isinstance(optional_deps, dict):
            for opt_group, deps in optional_deps.items():
                if isinstance(deps, list):
                    for dep in deps:
                        if isinstance(dep, str):
                            self._add_requirement(
                                dep,
                                group=f"project.optional-dependencies.{opt_group}",
                                is_optional=True,
                            )

    def _parse_poetry(self):
        """Parse Poetry format [tool.poetry.dependencies] and group tables."""
        tool = self.parsed_toml.get("tool", {})
        if not isinstance(tool, dict):
            return
        poetry = tool.get("poetry", {})
        if not isinstance(poetry, dict):
            return

        # Main dependencies
        deps = poetry.get("dependencies", {})
        if isinstance(deps, dict):
            for name, constraint in deps.items():
                if canonicalize_name(name) == "python":
                    continue
                self._parse_poetry_entry(name, constraint, group="tool.poetry.dependencies", is_optional=False)

        # Poetry 1.2+ groups
        groups = poetry.get("group", {})
        if isinstance(groups, dict):
            for group_name, group_data in groups.items():
                if isinstance(group_data, dict):
                    group_deps = group_data.get("dependencies", {})
                    is_opt = group_data.get("optional", False)
                    if isinstance(group_deps, dict):
                        for name, constraint in group_deps.items():
                            if canonicalize_name(name) == "python":
                                continue
                            self._parse_poetry_entry(
                                name,
                                constraint,
                                group=f"tool.poetry.group.{group_name}.dependencies",
                                is_optional=is_opt,
                            )

        # Poetry dev-dependencies (legacy)
        dev_deps = poetry.get("dev-dependencies", {})
        if isinstance(dev_deps, dict):
            for name, constraint in dev_deps.items():
                if canonicalize_name(name) == "python":
                    continue
                self._parse_poetry_entry(
                    name,
                    constraint,
                    group="tool.poetry.dev-dependencies",
                    is_optional=True,
                )

    def _parse_poetry_entry(self, name: str, constraint: Any, group: str, is_optional: bool):
        """Parse an individual Poetry table entry."""
        if isinstance(constraint, str):
            pep440_spec = poetry_constraint_to_pep440(constraint)
            raw_str = f"{name}{pep440_spec}" if pep440_spec else name
            self._add_requirement(raw_str, group=group, is_optional=is_optional)
        elif isinstance(constraint, dict):
            version_str = constraint.get("version", "")
            pep440_spec = poetry_constraint_to_pep440(version_str) if isinstance(version_str, str) else ""
            markers = constraint.get("markers", "")
            extras = constraint.get("extras", [])
            opt = constraint.get("optional", is_optional)

            spec_part = f"[{','.join(extras)}]" if extras else ""
            spec_part += pep440_spec
            raw_str = f"{name}{spec_part}"
            if markers:
                raw_str += f"; {markers}"
            self._add_requirement(raw_str, group=group, is_optional=opt)

    def _parse_pep735(self):
        """Parse PEP 735 dependency-groups."""
        groups = self.parsed_toml.get("dependency-groups", {})
        if isinstance(groups, dict):
            for grp_name, deps in groups.items():
                if isinstance(deps, list):
                    for dep in deps:
                        if isinstance(dep, str):
                            self._add_requirement(
                                dep,
                                group=f"dependency-groups.{grp_name}",
                                is_optional=True,
                            )

    def _parse_pdm(self):
        """Parse PDM dev-dependencies."""
        tool = self.parsed_toml.get("tool", {})
        if not isinstance(tool, dict):
            return
        pdm = tool.get("pdm", {})
        if not isinstance(pdm, dict):
            return
        dev_deps = pdm.get("dev-dependencies", {})
        if isinstance(dev_deps, dict):
            for grp_name, deps in dev_deps.items():
                if isinstance(deps, list):
                    for dep in deps:
                        if isinstance(dep, str):
                            self._add_requirement(
                                dep,
                                group=f"tool.pdm.dev-dependencies.{grp_name}",
                                is_optional=True,
                            )


def parse_pyproject(filepath_or_content: Union[str, Path]) -> Tuple[List[DependencyDeclaration], List[DependencyIssue]]:
    """Convenience helper to parse a pyproject file or string."""
    if isinstance(filepath_or_content, Path) or (
        isinstance(filepath_or_content, str) and ("\n" not in filepath_or_content and Path(filepath_or_content).is_file())
    ):
        p = Path(filepath_or_content)
        content = p.read_text(encoding="utf-8")
        parser = PyProjectParser(content, filepath=str(p))
    else:
        content = str(filepath_or_content)
        parser = PyProjectParser(content, filepath="pyproject.toml")
    return parser.parse()
