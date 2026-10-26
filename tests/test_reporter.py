"""Unit tests for pyproject_dep_doctor.reporter."""

import json

from pyproject_dep_doctor.models import (
    DependencyDeclaration,
    DependencyIssue,
    DoctorReport,
    IssueSeverity,
    IssueType,
)
from pyproject_dep_doctor.reporter import Reporter


def test_reporter_clean_report():
    report = DoctorReport(
        path="pyproject.toml",
        issues=[],
        total_dependencies_checked=4,
        checked_packages=["a", "b", "c", "d"],
    )
    reporter = Reporter(report, use_color=False)

    text = reporter.format_text()
    assert "All dependency version constraints are valid and compatible!" in text
    assert "Checked 4 dependencies" in text

    json_str = reporter.format_json()
    data = json.loads(json_str)
    assert data["is_valid"] is True
    assert data["summary"]["total_issues"] == 0

    md = reporter.format_markdown()
    assert "Dependency Health Report: `pyproject.toml`" in md
    assert "No dependency issues or version conflicts detected." in md

    gh = reporter.format_github()
    assert gh == ""


def test_reporter_with_issues():
    issue_err = DependencyIssue(
        issue_type=IssueType.VERSION_CONFLICT,
        severity=IssueSeverity.ERROR,
        package="urllib3",
        message="Incompatible version constraints",
        groups=["project.dependencies", "project.optional-dependencies.dev"],
        suggested_fix="urllib3>=2.0.0",
        line_number=12,
    )
    issue_warn = DependencyIssue(
        issue_type=IssueType.UNPINNED_DEPENDENCY,
        severity=IssueSeverity.WARNING,
        package="click",
        message="Unpinned dependency",
        groups=["project.dependencies"],
        line_number=15,
    )
    issue_info = DependencyIssue(
        issue_type=IssueType.OVERLAPPING_CONSTRAINT,
        severity=IssueSeverity.INFO,
        package="requests",
        message="Differing constraints",
        groups=["project.dependencies"],
    )

    report = DoctorReport(
        path="pyproject.toml",
        issues=[issue_err, issue_warn, issue_info],
        total_dependencies_checked=5,
        checked_packages=["urllib3", "click", "requests"],
    )

    # Color format
    rep_color = Reporter(report, use_color=True)
    text_color = rep_color.format_text()
    assert "[ERROR]" in text_color
    assert "[WARNING]" in text_color
    assert "[INFO]" in text_color
    assert "\033[" in text_color

    # Plain text format
    rep_plain = Reporter(report, use_color=False)
    text_plain = rep_plain.format_text()
    assert "[ERROR]" in text_plain
    assert "\033[" not in text_plain
    assert "urllib3:12" in text_plain
    assert "Suggested Fix: urllib3>=2.0.0" in text_plain
    assert "1 error(s), 1 warning(s), 1 info" in text_plain

    # JSON format
    json_out = rep_plain.format_json()
    data = json.loads(json_out)
    assert data["is_valid"] is False
    assert len(data["issues"]) == 3
    assert data["issues"][0]["package"] == "urllib3"

    # Markdown format
    md_out = rep_plain.format_markdown()
    assert "| 🔴 Error | **urllib3** |" in md_out
    assert "| 🟡 Warning | **click** |" in md_out
    assert "| ℹ️ Info | **requests** |" in md_out

    # GitHub format
    gh_out = rep_plain.format_github()
    assert "::error file=pyproject.toml,line=12::Incompatible version constraints (Fix: urllib3>=2.0.0)" in gh_out
    assert "::warning file=pyproject.toml,line=15::Unpinned dependency" in gh_out
