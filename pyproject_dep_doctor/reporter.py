"""Reporting and formatting utilities for pyproject-dep-doctor diagnostics."""

from __future__ import annotations

import json
from typing import Optional

from .models import DoctorReport, IssueSeverity


class Reporter:
    """Formats DoctorReport instances into terminal text, JSON, Markdown, or GitHub Actions annotations."""

    def __init__(self, report: DoctorReport, use_color: bool = True):
        self.report = report
        self.use_color = use_color

    def _color(self, text: str, color_code: str) -> str:
        if not self.use_color:
            return text
        return f"\033[{color_code}m{text}\033[0m"

    def red(self, text: str) -> str:
        return self._color(text, "1;31")

    def green(self, text: str) -> str:
        return self._color(text, "1;32")

    def yellow(self, text: str) -> str:
        return self._color(text, "1;33")

    def cyan(self, text: str) -> str:
        return self._color(text, "1;36")

    def bold(self, text: str) -> str:
        return self._color(text, "1")

    def dim(self, text: str) -> str:
        return self._color(text, "2")

    def format_text(self) -> str:
        """Render a clean, human-readable terminal report."""
        lines = []
        lines.append(self.bold(f"=== pyproject-dep-doctor Report for {self.report.path} ==="))
        lines.append("")

        if not self.report.issues:
            lines.append(self.green("✓ All dependency version constraints are valid and compatible!"))
            lines.append(
                self.dim(
                    f"Checked {self.report.total_dependencies_checked} dependencies across "
                    f"{len(set(self.report.checked_packages))} unique packages."
                )
            )
            return "\n".join(lines)

        for issue in self.report.issues:
            if issue.severity == IssueSeverity.ERROR:
                tag = self.red("[ERROR]")
            elif issue.severity == IssueSeverity.WARNING:
                tag = self.yellow("[WARNING]")
            else:
                tag = self.cyan("[INFO]")

            loc = f":{issue.line_number}" if issue.line_number else ""
            groups_str = f" in {', '.join(issue.groups)}" if issue.groups else ""

            lines.append(f"{tag} {self.bold(issue.package)}{loc}{groups_str}")
            lines.append(f"  {issue.message}")
            if issue.suggested_fix:
                lines.append(f"  {self.green('Suggested Fix:')} {issue.suggested_fix}")
            lines.append("")

        summary = self.report.summary
        lines.append(self.bold("Summary:"))
        err_str = self.red(f"{summary['errors']} error(s)") if summary["errors"] else "0 errors"
        warn_str = self.yellow(f"{summary['warnings']} warning(s)") if summary["warnings"] else "0 warnings"
        info_str = f"{summary['info']} info"

        lines.append(
            f"  {err_str}, {warn_str}, {info_str} | "
            f"{summary['total_dependencies']} dependencies checked ({summary['unique_packages']} packages)."
        )

        return "\n".join(lines)

    def format_json(self, indent: int = 2) -> str:
        """Serialize report to structured JSON."""
        return json.dumps(self.report.to_dict(), indent=indent)

    def format_markdown(self) -> str:
        """Render report as a formatted Markdown document suitable for PR comments."""
        lines = []
        lines.append(f"# Dependency Health Report: `{self.report.path}`\n")

        summary = self.report.summary
        status_icon = "❌" if summary["errors"] > 0 else ("⚠️" if summary["warnings"] > 0 else "✅")
        lines.append(
            f"**Status:** {status_icon} | **Errors:** {summary['errors']} | "
            f"**Warnings:** {summary['warnings']} | **Dependencies:** {summary['total_dependencies']}\n"
        )

        if not self.report.issues:
            lines.append("No dependency issues or version conflicts detected. Everything is healthy! 🎉")
            return "\n".join(lines)

        lines.append("| Severity | Package | Groups | Message | Suggested Fix |")
        lines.append("|---|---|---|---|---|")

        for issue in self.report.issues:
            sev_badge = (
                "🔴 Error" if issue.severity == IssueSeverity.ERROR
                else ("🟡 Warning" if issue.severity == IssueSeverity.WARNING else "ℹ️ Info")
            )
            grp = "<br>".join(f"`{g}`" for g in issue.groups) if issue.groups else "-"
            fix = f"`{issue.suggested_fix}`" if issue.suggested_fix else "-"
            msg = issue.message.replace("|", "\\|")
            lines.append(f"| {sev_badge} | **{issue.package}** | {grp} | {msg} | {fix} |")

        return "\n".join(lines)

    def format_github(self) -> str:
        """Format issues as GitHub Actions workflow commands (::error and ::warning)."""
        lines = []
        path = self.report.path
        for issue in self.report.issues:
            cmd = "error" if issue.severity == IssueSeverity.ERROR else "warning"
            line_part = f",line={issue.line_number}" if issue.line_number else ""
            msg = issue.message
            if issue.suggested_fix:
                msg += f" (Fix: {issue.suggested_fix})"
            lines.append(f"::{cmd} file={path}{line_part}::{msg}")
        return "\n".join(lines)
