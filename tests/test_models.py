"""Unit tests for pyproject_dep_doctor.models."""

from packaging.markers import Marker
from packaging.specifiers import SpecifierSet

from pyproject_dep_doctor.models import (
    DependencyDeclaration,
    DependencyIssue,
    DoctorReport,
    IssueSeverity,
    IssueType,
    canonicalize_name,
)


def test_canonicalize_name():
    assert canonicalize_name("Requests") == "requests"
    assert canonicalize_name("foo_bar") == "foo-bar"
    assert canonicalize_name("foo.bar-baz") == "foo-bar-baz"
    assert canonicalize_name("foo--bar__baz") == "foo-bar-baz"


def test_issue_severity_and_type_str():
    assert str(IssueSeverity.ERROR) == "error"
    assert str(IssueSeverity.WARNING) == "warning"
    assert str(IssueSeverity.INFO) == "info"

    assert str(IssueType.VERSION_CONFLICT) == "version_conflict"
    assert str(IssueType.SYNTAX_ERROR) == "syntax_error"
    assert str(IssueType.DUPLICATE_DEPENDENCY) == "duplicate_dependency"
    assert str(IssueType.UNPINNED_DEPENDENCY) == "unpinned_dependency"


def test_dependency_declaration():
    decl = DependencyDeclaration(
        name="requests",
        raw_spec="requests>=2.28.0; sys_platform == 'linux'",
        group="project.dependencies",
        specifier=SpecifierSet(">=2.28.0"),
        marker=Marker("sys_platform == 'linux'"),
        extras={"socks", "security"},
        line_number=14,
        is_optional=False,
    )

    assert decl.canonical_name == "requests"
    assert decl.spec_str == ">=2.28.0"
    assert not decl.is_optional
    assert decl.line_number == 14

    data = decl.to_dict()
    assert data["name"] == "requests"
    assert data["canonical_name"] == "requests"
    assert data["group"] == "project.dependencies"
    assert data["specifier"] == ">=2.28.0"
    assert 'sys_platform == "linux"' in data["marker"] or "sys_platform == 'linux'" in data["marker"]
    assert data["extras"] == ["security", "socks"]
    assert data["line_number"] == 14
    assert data["is_optional"] is False


def test_dependency_issue():
    decl = DependencyDeclaration(
        name="urllib3",
        raw_spec="urllib3<2.0.0",
        group="project.dependencies",
        specifier=SpecifierSet("<2.0.0"),
    )
    issue = DependencyIssue(
        issue_type=IssueType.VERSION_CONFLICT,
        severity=IssueSeverity.ERROR,
        package="urllib3",
        message="Incompatible versions",
        groups=["project.dependencies", "project.optional-dependencies.test"],
        declarations=[decl],
        suggested_fix="urllib3>=2.0.0",
        line_number=38,
    )

    d = issue.to_dict()
    assert d["issue_type"] == "version_conflict"
    assert d["severity"] == "error"
    assert d["package"] == "urllib3"
    assert d["message"] == "Incompatible versions"
    assert d["groups"] == ["project.dependencies", "project.optional-dependencies.test"]
    assert len(d["declarations"]) == 1
    assert d["suggested_fix"] == "urllib3>=2.0.0"
    assert d["line_number"] == 38


def test_doctor_report():
    # Clean report
    clean_report = DoctorReport(
        path="pyproject.toml",
        issues=[],
        total_dependencies_checked=5,
        checked_packages=["pkg1", "pkg2", "pkg1"],
    )
    assert clean_report.is_valid is True
    assert clean_report.has_errors is False
    assert clean_report.has_warnings is False
    assert clean_report.summary["errors"] == 0
    assert clean_report.summary["warnings"] == 0
    assert clean_report.summary["info"] == 0
    assert clean_report.summary["total_issues"] == 0
    assert clean_report.summary["total_dependencies"] == 5
    assert clean_report.summary["unique_packages"] == 2

    # Report with warning and error
    err_issue = DependencyIssue(
        issue_type=IssueType.VERSION_CONFLICT,
        severity=IssueSeverity.ERROR,
        package="pkg-a",
        message="Error found",
    )
    warn_issue = DependencyIssue(
        issue_type=IssueType.UNPINNED_DEPENDENCY,
        severity=IssueSeverity.WARNING,
        package="pkg-b",
        message="Warning found",
    )
    info_issue = DependencyIssue(
        issue_type=IssueType.OVERLAPPING_CONSTRAINT,
        severity=IssueSeverity.INFO,
        package="pkg-c",
        message="Info note",
    )

    dirty_report = DoctorReport(
        path="pyproject.toml",
        issues=[err_issue, warn_issue, info_issue],
        total_dependencies_checked=3,
        checked_packages=["pkg-a", "pkg-b", "pkg-c"],
    )
    assert dirty_report.is_valid is False
    assert dirty_report.has_errors is True
    assert dirty_report.has_warnings is True
    assert dirty_report.summary["errors"] == 1
    assert dirty_report.summary["warnings"] == 1
    assert dirty_report.summary["info"] == 1

    d = dirty_report.to_dict()
    assert d["path"] == "pyproject.toml"
    assert d["is_valid"] is False
    assert len(d["issues"]) == 3
