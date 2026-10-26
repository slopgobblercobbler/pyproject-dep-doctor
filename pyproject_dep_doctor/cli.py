"""Command Line Interface for pyproject-dep-doctor using standard argparse."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__
from .compatibility import DependencyChecker
from .fixer import fix_pyproject
from .models import DoctorReport, IssueSeverity
from .parser import parse_pyproject
from .pypi import PyPIClient
from .reporter import Reporter
from .resolver import ResolutionStrategy


def build_parser() -> argparse.ArgumentParser:
    """Construct the command line parser for pyproject-dep-doctor."""
    parser = argparse.ArgumentParser(
        prog="pyproject-dep-doctor",
        description="Diagnose and heal pyproject.toml dependency version conflicts and compatibility issues.",
    )
    parser.add_argument(
        "--version",
        "-V",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", help="Subcommand to execute")

    # 'check' subcommand
    check_parser = subparsers.add_parser(
        "check",
        help="Analyze pyproject.toml dependencies and report version conflicts.",
    )
    check_parser.add_argument(
        "path",
        nargs="?",
        default="pyproject.toml",
        help="Path to pyproject.toml file (default: pyproject.toml)",
    )
    check_parser.add_argument(
        "--format",
        "-f",
        choices=["text", "json", "markdown", "github"],
        default="text",
        help="Output format (default: text)",
    )
    check_parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip PyPI remote queries and perform local constraint analysis only.",
    )
    check_parser.add_argument(
        "--strict",
        action="store_true",
        help="Enforce strict mode (treat unpinned dependencies and warnings as errors).",
    )
    check_parser.add_argument(
        "--ignore",
        nargs="*",
        default=[],
        help="List of package names to ignore during checks.",
    )
    check_parser.add_argument(
        "--group",
        nargs="*",
        default=[],
        help="Specific dependency groups to check (e.g. project.dependencies dev).",
    )
    check_parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI color output.",
    )
    check_parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Save report output to specified file path instead of stdout.",
    )

    # 'fix' subcommand
    fix_parser = subparsers.add_parser(
        "fix",
        help="Automatically resolve dependency conflicts and update pyproject.toml.",
    )
    fix_parser.add_argument(
        "path",
        nargs="?",
        default="pyproject.toml",
        help="Path to pyproject.toml file (default: pyproject.toml)",
    )
    fix_parser.add_argument(
        "--strategy",
        "-s",
        choices=["intersect", "latest", "loosen"],
        default="intersect",
        help="Resolution strategy for version conflicts (default: intersect).",
    )
    fix_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes as unified diff without modifying files on disk.",
    )
    fix_parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create a .bak backup file before modifying.",
    )
    fix_parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip PyPI remote queries during resolution.",
    )
    fix_parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI color output.",
    )

    return parser


def check_file(
    path: str,
    offline: bool = False,
    strict: bool = False,
    ignore: Optional[List[str]] = None,
    group: Optional[List[str]] = None,
) -> DoctorReport:
    """Programmatic entry point to check a pyproject.toml file and return a DoctorReport."""
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    declarations, syntax_issues = parse_pyproject(file_path)

    checker = DependencyChecker(
        declarations=declarations,
        ignore_packages=ignore or [],
        strict=strict,
        checked_groups=group or [],
    )
    issues = list(syntax_issues)
    issues.extend(checker.check())

    # PyPI compatibility checking
    if not offline:
        pypi_client = PyPIClient(offline=False)
        pypi_issues = pypi_client.validate_declarations(
            declarations=declarations,
            ignore_packages=set(ignore or []),
        )
        issues.extend(pypi_issues)

    checked_packages = [d.name for d in declarations]
    return DoctorReport(
        path=str(file_path),
        issues=issues,
        total_dependencies_checked=len(declarations),
        checked_packages=checked_packages,
    )


def execute_check(args: argparse.Namespace) -> int:
    """Handle execution of 'check' command."""
    target_path = Path(args.path)
    if not target_path.exists():
        sys.stderr.write(f"Error: File '{args.path}' does not exist.\n")
        return 2

    try:
        report = check_file(
            path=str(target_path),
            offline=args.offline,
            strict=args.strict,
            ignore=args.ignore,
            group=args.group,
        )
    except Exception as e:
        sys.stderr.write(f"Error checking {args.path}: {e}\n")
        return 2

    reporter = Reporter(report, use_color=not args.no_color)
    if args.format == "json":
        output = reporter.format_json()
    elif args.format == "markdown":
        output = reporter.format_markdown()
    elif args.format == "github":
        output = reporter.format_github()
    else:
        output = reporter.format_text()

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
    else:
        print(output)

    # Return 1 if there are errors, or if strict mode is active and there are warnings
    if report.has_errors:
        return 1
    if args.strict and report.has_warnings:
        return 1
    return 0


def execute_fix(args: argparse.Namespace) -> int:
    """Handle execution of 'fix' command."""
    target_path = Path(args.path)
    if not target_path.exists():
        sys.stderr.write(f"Error: File '{args.path}' does not exist.\n")
        return 2

    strategy = ResolutionStrategy(args.strategy)
    try:
        modified_content, diff, actions = fix_pyproject(
            target_path,
            strategy=strategy,
            dry_run=args.dry_run,
            backup=not args.no_backup,
        )
    except Exception as e:
        sys.stderr.write(f"Error fixing {args.path}: {e}\n")
        return 2

    if not actions:
        print(f"pyproject-dep-doctor: No conflicts or fixes needed for '{args.path}'. Everything is in order!")
        return 0

    if args.dry_run:
        print(f"--- Dry run preview for '{args.path}' ({len(actions)} actions) ---")
        if diff:
            print(diff)
        else:
            for act in actions:
                print(f"  * {act}")
        return 0

    print(f"pyproject-dep-doctor: Successfully applied {len(actions)} fix(es) to '{args.path}'.")
    for act in actions:
        print(f"  * {act.reason}: '{act.old_spec}' -> '{act.new_spec}'")

    if not args.no_backup:
        print(f"  (Original saved as '{args.path}.bak')")

    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """Main CLI entry point."""
    if argv is None:
        argv = sys.argv[1:]

    parser = build_parser()

    # If first argument looks like a file path or flags, default to 'check'
    if argv and argv[0] not in ("check", "fix", "-h", "--help", "-V", "--version"):
        # Prepend 'check' so 'pyproject-dep-doctor pyproject.toml' works naturally
        argv = ["check"] + argv
    elif not argv:
        argv = ["check"]

    args = parser.parse_args(argv)

    if args.command == "fix":
        return execute_fix(args)
    else:
        return execute_check(args)


if __name__ == "__main__":
    sys.exit(main())
