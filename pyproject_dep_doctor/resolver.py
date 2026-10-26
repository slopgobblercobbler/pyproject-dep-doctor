"""Automated dependency resolution and constraint unification strategies."""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional, Set, Tuple
from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version

from .compatibility import (
    are_markers_exclusive,
    are_specifiers_compatible,
    extract_versions_from_specifier,
    intersect_specifiers,
    simplify_specifier_set,
)
from .models import (
    DependencyDeclaration,
    canonicalize_name,
)
from .pypi import PyPIClient


class ResolutionStrategy(str, Enum):
    """Resolution strategy for resolving conflicting or differing version constraints."""
    INTERSECT = "intersect"
    LATEST = "latest"
    LOOSEN = "loosen"

    def __str__(self) -> str:
        return self.value


class FixAction:
    """Represents a specific modification to a dependency specification."""

    def __init__(
        self,
        package: str,
        group: str,
        old_spec: str,
        new_spec: Optional[str],
        reason: str,
        action_type: str = "replace",  # "replace" or "remove"
    ):
        self.package = package
        self.group = group
        self.old_spec = old_spec
        self.new_spec = new_spec
        self.reason = reason
        self.action_type = action_type

    def __repr__(self) -> str:
        if self.action_type == "remove":
            return f"<FixAction REMOVE '{self.old_spec}' from {self.group} ({self.reason})>"
        return f"<FixAction REPLACE '{self.old_spec}' -> '{self.new_spec}' in {self.group} ({self.reason})>"

    def to_dict(self) -> Dict[str, str]:
        return {
            "package": self.package,
            "group": self.group,
            "old_spec": self.old_spec,
            "new_spec": self.new_spec or "",
            "action_type": self.action_type,
            "reason": self.reason,
        }


class DependencyResolver:
    """Computes automated fixes for duplicates, version conflicts, and out-of-sync constraints."""

    def __init__(
        self,
        declarations: List[DependencyDeclaration],
        strategy: ResolutionStrategy = ResolutionStrategy.INTERSECT,
        pypi_client: Optional[PyPIClient] = None,
    ):
        self.declarations = declarations
        self.strategy = strategy
        self.pypi_client = pypi_client or PyPIClient(offline=True)

    def resolve(self) -> List[FixAction]:
        """Compute all fix actions necessary to harmonize dependencies."""
        actions: List[FixAction] = []

        # Group declarations by canonical package name
        pkg_map: Dict[str, List[DependencyDeclaration]] = {}
        for decl in self.declarations:
            pkg_map.setdefault(decl.canonical_name, []).append(decl)

        for pkg_name, decls in pkg_map.items():
            # 1. Resolve duplicates within each group
            group_map: Dict[str, List[DependencyDeclaration]] = {}
            for d in decls:
                group_map.setdefault(d.group, []).append(d)

            for group, group_decls in group_map.items():
                if len(group_decls) > 1:
                    actions.extend(self._resolve_group_duplicates(pkg_name, group, group_decls))

            # Update working declarations after duplicates resolved
            effective_decls = [group_decls[0] for group_decls in group_map.values()]

            # 2. Resolve cross-group conflicts
            if len(effective_decls) > 1:
                cross_actions = self._resolve_cross_group_conflicts(pkg_name, effective_decls)
                actions.extend(cross_actions)

        return actions

    def _resolve_group_duplicates(
        self,
        pkg_name: str,
        group: str,
        decls: List[DependencyDeclaration],
    ) -> List[FixAction]:
        """Resolve multiple declarations of the same package in a single group."""
        actions: List[FixAction] = []
        specs = [d.raw_spec for d in decls]

        # Check if identical
        if len(set(specs)) == 1:
            # Keep first, remove subsequent duplicates
            for duplicate in decls[1:]:
                actions.append(
                    FixAction(
                        package=pkg_name,
                        group=group,
                        old_spec=duplicate.raw_spec,
                        new_spec=None,
                        reason="Deduplicate identical requirement",
                        action_type="remove",
                    )
                )
            return actions

        # Differing constraints: combine specifiers
        combined_spec = decls[0].specifier
        for d in decls[1:]:
            combined_spec = intersect_specifiers(combined_spec, d.specifier)

        # Build replacement target
        extras_set = set()
        for d in decls:
            extras_set.update(d.extras)
        extras_str = f"[{','.join(sorted(extras_set))}]" if extras_set else ""

        # Check markers
        marker_str = ""
        for d in decls:
            if d.marker:
                marker_str = f"; {d.marker}"
                break

        unified_spec_str = str(combined_spec)
        new_requirement = f"{decls[0].name}{extras_str}{unified_spec_str}{marker_str}"

        # Replace first declaration with unified requirement
        actions.append(
            FixAction(
                package=pkg_name,
                group=group,
                old_spec=decls[0].raw_spec,
                new_spec=new_requirement,
                reason="Merge multiple declarations into unified requirement",
                action_type="replace",
            )
        )

        # Remove redundant subsequent entries
        for duplicate in decls[1:]:
            actions.append(
                FixAction(
                    package=pkg_name,
                    group=group,
                    old_spec=duplicate.raw_spec,
                    new_spec=None,
                    reason="Remove duplicate after merging",
                    action_type="remove",
                )
            )

        return actions

    def _resolve_cross_group_conflicts(
        self,
        pkg_name: str,
        decls: List[DependencyDeclaration],
    ) -> List[FixAction]:
        """Resolve conflicts or discrepancies across different dependency groups."""
        actions: List[FixAction] = []

        # Filter out mutually exclusive markers (e.g. windows vs linux)
        conflicting_pairs: List[Tuple[DependencyDeclaration, DependencyDeclaration]] = []
        for i in range(len(decls)):
            for j in range(i + 1, len(decls)):
                d1, d2 = decls[i], decls[j]
                if not are_markers_exclusive(d1.marker, d2.marker):
                    if not are_specifiers_compatible(d1.specifier, d2.specifier) or (
                        d1.specifier != d2.specifier and self.strategy != ResolutionStrategy.INTERSECT
                    ):
                        conflicting_pairs.append((d1, d2))

        if not conflicting_pairs:
            # Check if we should harmonize compatible differing constraints
            has_different_specs = any(d.specifier != decls[0].specifier for d in decls)
            if not has_different_specs:
                return actions

            # Compute intersection for all declarations
            unified_spec = decls[0].specifier
            for d in decls[1:]:
                unified_spec = intersect_specifiers(unified_spec, d.specifier)

            for d in decls:
                if d.specifier != unified_spec:
                    extras_str = f"[{','.join(sorted(d.extras))}]" if d.extras else ""
                    marker_str = f"; {d.marker}" if d.marker else ""
                    new_req = f"{d.name}{extras_str}{unified_spec}{marker_str}"
                    actions.append(
                        FixAction(
                            package=pkg_name,
                            group=d.group,
                            old_spec=d.raw_spec,
                            new_spec=new_req,
                            reason=f"Harmonize constraint across groups to '{unified_spec}'",
                            action_type="replace",
                        )
                    )
            return actions

        # If there are active conflicts
        target_spec = self._compute_target_specifier(decls)

        for d in decls:
            if d.specifier != target_spec:
                extras_str = f"[{','.join(sorted(d.extras))}]" if d.extras else ""
                marker_str = f"; {d.marker}" if d.marker else ""
                new_req = f"{d.name}{extras_str}{target_spec}{marker_str}"
                actions.append(
                    FixAction(
                        package=pkg_name,
                        group=d.group,
                        old_spec=d.raw_spec,
                        new_spec=new_req,
                        reason=f"Resolve version conflict using strategy '{self.strategy.value}'",
                        action_type="replace",
                    )
                )

        return actions

    def _compute_target_specifier(self, decls: List[DependencyDeclaration]) -> SpecifierSet:
        """Calculate target SpecifierSet based on the configured resolution strategy."""
        if self.strategy == ResolutionStrategy.INTERSECT:
            # Attempt intersecting where possible
            combined = decls[0].specifier
            for d in decls[1:]:
                if are_specifiers_compatible(combined, d.specifier):
                    combined = intersect_specifiers(combined, d.specifier)
                else:
                    # If incompatible, default to main dependency if present, or latest
                    main_decl = next((x for x in decls if x.group == "project.dependencies"), None)
                    if main_decl:
                        return main_decl.specifier
                    return self._select_latest_specifier(decls)
            return combined

        elif self.strategy == ResolutionStrategy.LATEST:
            return self._select_latest_specifier(decls)

        elif self.strategy == ResolutionStrategy.LOOSEN:
            # Loosen bounds: find minimum lower bound and maximum upper bound
            lower_versions: List[Version] = []
            upper_versions: List[Version] = []

            for d in decls:
                for spec in d.specifier:
                    v_str = spec.version.rstrip(".*")
                    try:
                        ver = Version(v_str)
                        if spec.operator in (">=", ">"):
                            lower_versions.append(ver)
                        elif spec.operator in ("<=", "<"):
                            upper_versions.append(ver)
                    except InvalidVersion:
                        pass

            clauses = []
            if lower_versions:
                clauses.append(f">={min(lower_versions)}")
            if upper_versions:
                clauses.append(f"<{max(upper_versions)}")

            if clauses:
                return SpecifierSet(",".join(clauses))
            return decls[0].specifier

        return decls[0].specifier

    def _select_latest_specifier(self, decls: List[DependencyDeclaration]) -> SpecifierSet:
        """Find the declaration specifying the highest/most modern version."""
        scored: List[Tuple[Optional[Version], DependencyDeclaration]] = []
        for d in decls:
            versions = extract_versions_from_specifier(d.specifier)
            max_v = max(versions) if versions else None
            scored.append((max_v, d))

        scored.sort(key=lambda x: (x[0] is not None, x[0]))
        return scored[-1][1].specifier
