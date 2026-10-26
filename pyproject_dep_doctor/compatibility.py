"""Dependency version compatibility, conflict detection, and specifier mathematics."""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Set, Tuple
from packaging.markers import Marker
from packaging.specifiers import InvalidSpecifier, Specifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from .models import (
    DependencyDeclaration,
    DependencyIssue,
    IssueSeverity,
    IssueType,
    canonicalize_name,
)


def are_markers_exclusive(marker1: Optional[Marker], marker2: Optional[Marker]) -> bool:
    """Determine whether two environment markers are mutually exclusive.

    If markers target incompatible operating systems, python versions, or platforms,
    the two dependencies cannot be activated at the same time and therefore do not conflict.
    """
    if not marker1 or not marker2:
        return False

    str1 = str(marker1).strip()
    str2 = str(marker2).strip()
    if str1 == str2:
        return False

    # Check for platform exclusivity
    exclusive_platforms = [
        {"win32", "windows"},
        {"linux", "linux2"},
        {"darwin", "macos", "osx"},
        {"cygwin"},
        {"freebsd"},
    ]

    plat_regex = re.compile(
        r"""(?:sys_platform|os_name|platform_system)\s*==\s*['"]([^'"]+)['"]""",
        re.IGNORECASE,
    )
    m1_platforms = set(plat_regex.findall(str1))
    m2_platforms = set(plat_regex.findall(str2))

    if m1_platforms and m2_platforms:
        # Check if they belong to different exclusive groups
        def get_group(plat: str) -> Optional[int]:
            low = plat.lower()
            for idx, grp in enumerate(exclusive_platforms):
                if low in grp:
                    return idx
            return None

        grp1 = {get_group(p) for p in m1_platforms if get_group(p) is not None}
        grp2 = {get_group(p) for p in m2_platforms if get_group(p) is not None}

        if grp1 and grp2 and grp1.isdisjoint(grp2):
            return True

    return False


def extract_versions_from_specifier(spec_set: SpecifierSet) -> Set[Version]:
    """Extract all explicit Version literals from a SpecifierSet."""
    versions = set()
    for spec in spec_set:
        v_str = spec.version.rstrip(".*")
        try:
            versions.add(Version(v_str))
        except InvalidVersion:
            # Try stripping trailing characters or wildcard
            cleaned = re.sub(r"[^\d.]", "", v_str)
            if cleaned:
                try:
                    versions.add(Version(cleaned))
                except InvalidVersion:
                    pass
    return versions


def generate_candidate_versions(spec_set: SpecifierSet) -> List[Version]:
    """Generate a comprehensive set of test candidate versions to evaluate specifier satisfaction."""
    candidates: Set[Version] = {
        Version("0.0.1"),
        Version("0.1.0"),
        Version("1.0.0"),
        Version("2.0.0"),
        Version("3.0.0"),
        Version("4.0.0"),
        Version("5.0.0"),
        Version("10.0.0"),
    }

    base_versions = extract_versions_from_specifier(spec_set)
    for v in base_versions:
        candidates.add(v)
        major = v.major
        minor = v.minor if v.minor is not None else 0
        micro = v.micro if v.micro is not None else 0

        # Boundary neighbor points
        try:
            candidates.add(Version(f"{major}.{minor}.{micro + 1}"))
            if micro > 0:
                candidates.add(Version(f"{major}.{minor}.{micro - 1}"))
            candidates.add(Version(f"{major}.{minor + 1}.0"))
            if minor > 0:
                candidates.add(Version(f"{major}.{minor - 1}.0"))
            candidates.add(Version(f"{major + 1}.0.0"))
            if major > 0:
                candidates.add(Version(f"{major - 1}.0.0"))
        except InvalidVersion:
            pass

    # Midpoints between versions
    sorted_versions = sorted(list(base_versions))
    for i in range(len(sorted_versions) - 1):
        v1 = sorted_versions[i]
        v2 = sorted_versions[i + 1]
        if v1.major == v2.major and v1.minor == v2.minor and (v2.micro - v1.micro > 1):
            mid_micro = (v1.micro + v2.micro) // 2
            try:
                candidates.add(Version(f"{v1.major}.{v1.minor}.{mid_micro}"))
            except InvalidVersion:
                pass

    return sorted(list(candidates))


def are_specifiers_compatible(s1: SpecifierSet, s2: SpecifierSet) -> bool:
    """Check if two SpecifierSets have a non-empty intersection (can be satisfied simultaneously)."""
    if not s1 or not s2:
        return True

    try:
        combined_str = f"{s1},{s2}" if str(s1) and str(s2) else str(s1) or str(s2)
        combined = SpecifierSet(combined_str)
    except InvalidSpecifier:
        return False

    # Analytical interval boundary check
    lower_bounds: List[Tuple[Version, bool]] = []  # (Version, is_inclusive)
    upper_bounds: List[Tuple[Version, bool]] = []  # (Version, is_inclusive)
    exact_bounds: List[Version] = []

    for spec in combined:
        op = spec.operator
        v_str = spec.version.rstrip(".*")
        try:
            ver = Version(v_str)
        except InvalidVersion:
            continue

        if op == "==":
            if not spec.version.endswith(".*"):
                exact_bounds.append(ver)
        elif op == ">=":
            lower_bounds.append((ver, True))
        elif op == ">":
            lower_bounds.append((ver, False))
        elif op == "<=":
            upper_bounds.append((ver, True))
        elif op == "<":
            upper_bounds.append((ver, False))
        elif op == "~=":
            lower_bounds.append((ver, True))
            # ~= X.Y means >= X.Y, == X.*
            parts = v_str.split(".")
            if len(parts) > 1:
                try:
                    up = Version(f"{parts[0]}.{int(parts[1]) + 1}.0")
                    upper_bounds.append((up, False))
                except (ValueError, InvalidVersion):
                    pass

    # Check exact bounds first
    for ex in exact_bounds:
        if ex not in combined:
            return False

    # Check interval: max(lower) vs min(upper)
    if lower_bounds and upper_bounds:
        max_lower, max_lower_inc = max(lower_bounds, key=lambda x: x[0])
        min_upper, min_upper_inc = min(upper_bounds, key=lambda x: x[0])

        if max_lower > min_upper:
            return False
        if max_lower == min_upper and (not max_lower_inc or not min_upper_inc):
            return False

    # Evaluate against candidate samples
    candidates = generate_candidate_versions(combined)
    for c in candidates:
        if c in combined:
            return True

    # If no candidate matched, test if either exact bound or midpoint matches
    if exact_bounds:
        return all(eb in combined for eb in exact_bounds)

    return False


def simplify_specifier_set(spec_set: SpecifierSet) -> SpecifierSet:
    """Simplify and eliminate redundant clauses in a SpecifierSet."""
    if not spec_set:
        return SpecifierSet("")

    clauses = list(spec_set)
    if len(clauses) <= 1:
        return spec_set

    # Group by operator type
    lower_bounds: List[Tuple[Version, bool, Specifier]] = []
    upper_bounds: List[Tuple[Version, bool, Specifier]] = []
    others: List[Specifier] = []

    for spec in clauses:
        op = spec.operator
        v_str = spec.version.rstrip(".*")
        try:
            ver = Version(v_str)
        except InvalidVersion:
            others.append(spec)
            continue

        if op == ">=":
            lower_bounds.append((ver, True, spec))
        elif op == ">":
            lower_bounds.append((ver, False, spec))
        elif op == "<=":
            upper_bounds.append((ver, True, spec))
        elif op == "<":
            upper_bounds.append((ver, False, spec))
        else:
            others.append(spec)

    retained: List[str] = []

    if lower_bounds:
        # Tightest lower bound is the maximum
        max_lower = max(lower_bounds, key=lambda x: (x[0], not x[1]))
        retained.append(str(max_lower[2]))

    if upper_bounds:
        # Tightest upper bound is the minimum
        min_upper = min(upper_bounds, key=lambda x: (x[0], x[1]))
        retained.append(str(min_upper[2]))

    for spec in others:
        spec_str = str(spec)
        if spec_str not in retained:
            retained.append(spec_str)

    try:
        return SpecifierSet(",".join(retained))
    except InvalidSpecifier:
        return spec_set


def intersect_specifiers(s1: SpecifierSet, s2: SpecifierSet) -> SpecifierSet:
    """Compute the intersection of two compatible SpecifierSets."""
    if not s1 and not s2:
        return SpecifierSet("")
    if not s1:
        return s2
    if not s2:
        return s1

    combined_str = f"{s1},{s2}"
    try:
        combined = SpecifierSet(combined_str)
        return simplify_specifier_set(combined)
    except InvalidSpecifier:
        return s1


class DependencyChecker:
    """Analyzes declared dependencies for version conflicts, duplicates, and constraints."""

    def __init__(
        self,
        declarations: List[DependencyDeclaration],
        ignore_packages: Optional[Iterable[str]] = None,
        strict: bool = False,
        checked_groups: Optional[Iterable[str]] = None,
    ):
        self.declarations = declarations
        self.ignore_packages = {canonicalize_name(p) for p in (ignore_packages or [])}
        self.strict = strict
        self.checked_groups = set(checked_groups) if checked_groups else None
        self.issues: List[DependencyIssue] = []

    def check(self) -> List[DependencyIssue]:
        """Perform all checks and return discovered issues."""
        # Filter declarations if specific groups are targeted
        active_decls = [
            d for d in self.declarations
            if (not self.checked_groups or d.group in self.checked_groups)
            and d.canonical_name not in self.ignore_packages
        ]

        # 1. Group declarations by canonical package name
        pkg_map: Dict[str, List[DependencyDeclaration]] = {}
        for decl in active_decls:
            pkg_map.setdefault(decl.canonical_name, []).append(decl)

        # 2. Check each package
        for pkg_name, decls in pkg_map.items():
            self._check_package_declarations(pkg_name, decls)

        return self.issues

    def _check_package_declarations(self, pkg_name: str, decls: List[DependencyDeclaration]):
        """Run all compatibility and lint rules on declarations of a package."""
        # 2a. Check duplicates in the SAME group
        group_map: Dict[str, List[DependencyDeclaration]] = {}
        for d in decls:
            group_map.setdefault(d.group, []).append(d)

        for group, group_decls in group_map.items():
            if len(group_decls) > 1:
                self._check_duplicates_in_group(pkg_name, group, group_decls)

        # 2b. Check unpinned dependencies
        for d in decls:
            if not d.specifier and not d.is_optional:
                severity = IssueSeverity.WARNING if not self.strict else IssueSeverity.ERROR
                self.issues.append(
                    DependencyIssue(
                        issue_type=IssueType.UNPINNED_DEPENDENCY,
                        severity=severity,
                        package=pkg_name,
                        message=f"Package '{pkg_name}' in '{d.group}' has no version constraint pin.",
                        groups=[d.group],
                        declarations=[d],
                        suggested_fix=f"Specify a version constraint, e.g. '{pkg_name}>=1.0.0'",
                        line_number=d.line_number,
                    )
                )

        # 2c. Check cross-group conflicts
        groups = list(group_map.keys())
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                g1, g2 = groups[i], groups[j]
                for d1 in group_map[g1]:
                    for d2 in group_map[g2]:
                        self._check_pair_compatibility(pkg_name, d1, d2)

    def _check_duplicates_in_group(self, pkg_name: str, group: str, decls: List[DependencyDeclaration]):
        """Check duplicate package declarations in the same group."""
        specs = [d.raw_spec for d in decls]
        unique_specs = set(specs)

        first_decl = decls[0]
        if len(unique_specs) == 1:
            # Redundant exact duplicate
            self.issues.append(
                DependencyIssue(
                    issue_type=IssueType.DUPLICATE_DEPENDENCY,
                    severity=IssueSeverity.WARNING,
                    package=pkg_name,
                    message=f"Duplicate entry for '{pkg_name}' found in '{group}'.",
                    groups=[group],
                    declarations=decls,
                    suggested_fix=f"Remove duplicate declaration '{decls[0].raw_spec}'",
                    line_number=first_decl.line_number,
                )
            )
        else:
            # Duplicate with different version constraints
            compatible = True
            for i in range(len(decls)):
                for j in range(i + 1, len(decls)):
                    if not are_markers_exclusive(decls[i].marker, decls[j].marker):
                        if not are_specifiers_compatible(decls[i].specifier, decls[j].specifier):
                            compatible = False
                            break

            if not compatible:
                self.issues.append(
                    DependencyIssue(
                        issue_type=IssueType.VERSION_CONFLICT,
                        severity=IssueSeverity.ERROR,
                        package=pkg_name,
                        message=f"Conflicting duplicate specifications for '{pkg_name}' in '{group}': {specs}",
                        groups=[group],
                        declarations=decls,
                        suggested_fix="Consolidate duplicate declarations to a single compatible constraint.",
                        line_number=first_decl.line_number,
                    )
                )
            else:
                self.issues.append(
                    DependencyIssue(
                        issue_type=IssueType.DUPLICATE_DEPENDENCY,
                        severity=IssueSeverity.WARNING,
                        package=pkg_name,
                        message=f"Multiple overlapping specifications for '{pkg_name}' in '{group}': {specs}",
                        groups=[group],
                        declarations=decls,
                        suggested_fix="Merge into a single unified version requirement.",
                        line_number=first_decl.line_number,
                    )
                )

    def _check_pair_compatibility(
        self,
        pkg_name: str,
        d1: DependencyDeclaration,
        d2: DependencyDeclaration,
    ):
        """Check compatibility between two declarations in different groups."""
        # If environment markers are mutually exclusive (e.g. windows vs linux), no conflict
        if are_markers_exclusive(d1.marker, d2.marker):
            return

        # Check if version constraints conflict
        if not are_specifiers_compatible(d1.specifier, d2.specifier):
            suggested = None
            if d1.specifier and d2.specifier:
                suggested = f"Align constraints between '{d1.group}' ({d1.specifier}) and '{d2.group}' ({d2.specifier})"

            issue_type = (
                IssueType.VERSION_CONFLICT
                if ("project.dependencies" in (d1.group, d2.group))
                else IssueType.INCOMPATIBLE_EXTRAS
            )

            self.issues.append(
                DependencyIssue(
                    issue_type=issue_type,
                    severity=IssueSeverity.ERROR,
                    package=pkg_name,
                    message=(
                        f"Incompatible version constraints for '{pkg_name}': "
                        f"'{d1.raw_spec}' in {d1.group} conflicts with '{d2.raw_spec}' in {d2.group}"
                    ),
                    groups=[d1.group, d2.group],
                    declarations=[d1, d2],
                    suggested_fix=suggested,
                    line_number=d1.line_number or d2.line_number,
                )
            )
        else:
            # Compatible, but check if one tightens or overlaps without exact match
            if d1.specifier and d2.specifier and str(d1.specifier) != str(d2.specifier):
                # Check if one is main dependencies and the other is optional
                is_main_and_extra = ("project.dependencies" in (d1.group, d2.group)) and (
                    d1.is_optional or d2.is_optional
                )
                if is_main_and_extra and self.strict:
                    self.issues.append(
                        DependencyIssue(
                            issue_type=IssueType.OVERLAPPING_CONSTRAINT,
                            severity=IssueSeverity.INFO,
                            package=pkg_name,
                            message=(
                                f"Version constraints for '{pkg_name}' differ between {d1.group} "
                                f"('{d1.spec_str}') and {d2.group} ('{d2.spec_str}')."
                            ),
                            groups=[d1.group, d2.group],
                            declarations=[d1, d2],
                            suggested_fix="Harmonize version constraints across main and optional groups.",
                            line_number=d1.line_number or d2.line_number,
                        )
                    )
