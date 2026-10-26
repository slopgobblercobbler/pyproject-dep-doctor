"""Data models and issue definitions for pyproject-dep-doctor."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.markers import Marker


def canonicalize_name(name: str) -> str:
    """Normalize a package name according to PEP 503."""
    return re.sub(r"[-_.]+", "-", name).lower()


class IssueSeverity(str, Enum):
    """Severity of a dependency diagnostic issue."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"

    def __str__(self) -> str:
        return self.value


class IssueType(str, Enum):
    """Categorized type of dependency diagnostic."""
    SYNTAX_ERROR = "syntax_error"
    DUPLICATE_DEPENDENCY = "duplicate_dependency"
    VERSION_CONFLICT = "version_conflict"
    INCOMPATIBLE_EXTRAS = "incompatible_extras"
    UNPINNED_DEPENDENCY = "unpinned_dependency"
    OVERLAPPING_CONSTRAINT = "overlapping_constraint"
    PYPI_NOT_FOUND = "pypi_not_found"
    PYPI_NO_MATCHING_VERSION = "pypi_no_matching_version"
    YANKED_RELEASE = "yanked_release"

    def __str__(self) -> str:
        return self.value


@dataclass
class DependencyDeclaration:
    """Represents a single dependency requirement entry parsed from pyproject.toml."""
    name: str
    raw_spec: str
    group: str
    specifier: SpecifierSet = field(default_factory=SpecifierSet)
    marker: Optional[Marker] = None
    extras: Set[str] = field(default_factory=set)
    line_number: Optional[int] = None
    is_optional: bool = False

    @property
    def canonical_name(self) -> str:
        """Returns the canonicalized name (PEP 503)."""
        return canonicalize_name(self.name)

    @property
    def spec_str(self) -> str:
        """Returns the specifier portion string."""
        return str(self.specifier) if self.specifier else ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert declaration to dictionary representation."""
        return {
            "name": self.name,
            "canonical_name": self.canonical_name,
            "raw_spec": self.raw_spec,
            "group": self.group,
            "specifier": str(self.specifier),
            "marker": str(self.marker) if self.marker else None,
            "extras": sorted(list(self.extras)),
            "line_number": self.line_number,
            "is_optional": self.is_optional,
        }


@dataclass
class DependencyIssue:
    """Represents a diagnostic issue identified during check."""
    issue_type: IssueType
    severity: IssueSeverity
    package: str
    message: str
    groups: List[str] = field(default_factory=list)
    declarations: List[DependencyDeclaration] = field(default_factory=list)
    suggested_fix: Optional[str] = None
    line_number: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert issue to serializable dict."""
        return {
            "issue_type": str(self.issue_type),
            "severity": str(self.severity),
            "package": self.package,
            "message": self.message,
            "groups": self.groups,
            "declarations": [d.to_dict() for d in self.declarations],
            "suggested_fix": self.suggested_fix,
            "line_number": self.line_number,
        }


@dataclass
class DoctorReport:
    """Represents the complete result of checking a pyproject.toml file."""
    path: str
    issues: List[DependencyIssue] = field(default_factory=list)
    total_dependencies_checked: int = 0
    checked_packages: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """True if there are no ERROR severity issues."""
        return not any(issue.severity == IssueSeverity.ERROR for issue in self.issues)

    @property
    def has_errors(self) -> bool:
        """True if at least one ERROR severity issue exists."""
        return any(issue.severity == IssueSeverity.ERROR for issue in self.issues)

    @property
    def has_warnings(self) -> bool:
        """True if at least one WARNING severity issue exists."""
        return any(issue.severity == IssueSeverity.WARNING for issue in self.issues)

    @property
    def summary(self) -> Dict[str, int]:
        """Summary breakdown of issue counts by severity."""
        return {
            "errors": sum(1 for i in self.issues if i.severity == IssueSeverity.ERROR),
            "warnings": sum(1 for i in self.issues if i.severity == IssueSeverity.WARNING),
            "info": sum(1 for i in self.issues if i.severity == IssueSeverity.INFO),
            "total_issues": len(self.issues),
            "total_dependencies": self.total_dependencies_checked,
            "unique_packages": len(set(self.checked_packages)),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert full report to dictionary."""
        return {
            "path": self.path,
            "is_valid": self.is_valid,
            "summary": self.summary,
            "issues": [issue.to_dict() for issue in self.issues],
        }
