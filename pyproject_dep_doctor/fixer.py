"""Applies automated dependency fixes to pyproject.toml with format and comment preservation."""

from __future__ import annotations

import difflib
import re
import shutil
from pathlib import Path
from typing import List, Optional, Tuple, Union

from .parser import PyProjectParser
from .resolver import DependencyResolver, FixAction, ResolutionStrategy


class PyProjectFixer:
    """Applies dependency FixActions to pyproject.toml content."""

    def __init__(self, content: str, filepath: Optional[str] = None):
        self.original_content = content
        self.filepath = filepath
        self.modified_content = content
        self.applied_actions: List[FixAction] = []

    def apply_actions(self, actions: List[FixAction]) -> Tuple[str, List[FixAction]]:
        """Apply a list of FixActions to the TOML text, preserving formatting and comments."""
        lines = self.original_content.splitlines(keepends=True)

        for action in actions:
            success = False
            if action.action_type == "replace" and action.new_spec:
                lines, success = self._apply_replace(lines, action.old_spec, action.new_spec)
            elif action.action_type == "remove":
                lines, success = self._apply_remove(lines, action.old_spec)

            if success:
                self.applied_actions.append(action)

        self.modified_content = "".join(lines)
        return self.modified_content, self.applied_actions

    def _apply_replace(self, lines: List[str], old_spec: str, new_spec: str) -> Tuple[List[str], bool]:
        """Replace old_spec string literal with new_spec inside TOML array or value."""
        new_lines: List[str] = []
        replaced = False

        # Pattern matching old_spec inside quotes
        escaped_old = re.escape(old_spec)
        pattern = re.compile(rf"""(['"]){escaped_old}(['"])""")

        for line in lines:
            if not replaced and pattern.search(line):
                new_line = pattern.sub(rf"\g<1>{new_spec}\g<2>", line)
                new_lines.append(new_line)
                replaced = True
            else:
                new_lines.append(line)

        return new_lines, replaced

    def _apply_remove(self, lines: List[str], old_spec: str) -> Tuple[List[str], bool]:
        """Remove a line declaring old_spec, adjusting surrounding comma if needed."""
        new_lines: List[str] = []
        removed = False

        escaped_old = re.escape(old_spec)
        pattern = re.compile(rf"""['"]{escaped_old}['"]""")

        for line in lines:
            if not removed and pattern.search(line):
                # Omit this line
                removed = True
                continue
            new_lines.append(line)

        return new_lines, removed

    def get_diff(self, filename: str = "pyproject.toml") -> str:
        """Produce unified diff representation between original and modified content."""
        orig_lines = self.original_content.splitlines(keepends=True)
        mod_lines = self.modified_content.splitlines(keepends=True)
        diff = difflib.unified_diff(
            orig_lines,
            mod_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            lineterm="",
        )
        return "".join(diff)


def fix_pyproject(
    filepath_or_content: Union[str, Path],
    strategy: ResolutionStrategy = ResolutionStrategy.INTERSECT,
    dry_run: bool = False,
    backup: bool = True,
) -> Tuple[str, str, List[FixAction]]:
    """Convenience function to resolve and apply fixes to pyproject.toml.

    Returns:
        Tuple of (modified_content, diff_string, applied_actions)
    """
    is_path = False
    path_obj: Optional[Path] = None

    if isinstance(filepath_or_content, Path) or (
        isinstance(filepath_or_content, str) and ("\n" not in filepath_or_content and Path(filepath_or_content).is_file())
    ):
        is_path = True
        path_obj = Path(filepath_or_content)
        content = path_obj.read_text(encoding="utf-8")
        filename = path_obj.name
    else:
        content = str(filepath_or_content)
        filename = "pyproject.toml"

    parser = PyProjectParser(content, filepath=filename)
    declarations, _ = parser.parse()

    resolver = DependencyResolver(declarations, strategy=strategy)
    actions = resolver.resolve()

    fixer = PyProjectFixer(content, filepath=filename)
    modified_content, applied = fixer.apply_actions(actions)
    diff = fixer.get_diff(filename=filename)

    if is_path and path_obj and not dry_run and applied:
        if backup:
            bak_path = path_obj.with_suffix(path_obj.suffix + ".bak")
            shutil.copyfile(path_obj, bak_path)
        path_obj.write_text(modified_content, encoding="utf-8")

    return modified_content, diff, applied
