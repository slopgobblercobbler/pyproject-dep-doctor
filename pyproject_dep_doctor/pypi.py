"""PyPI API client and compatibility validation."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Set
from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version

from .models import (
    DependencyDeclaration,
    DependencyIssue,
    IssueSeverity,
    IssueType,
    canonicalize_name,
)

PYPI_URL_TEMPLATE = "https://pypi.org/pypi/{package}/json"


class PyPIClient:
    """Interacts with the PyPI JSON API to validate package availability and version satisfiability."""

    def __init__(self, offline: bool = False, timeout: float = 3.0, max_workers: int = 5):
        self.offline = offline
        self.timeout = timeout
        self.max_workers = max_workers
        self._cache: Dict[str, Optional[Dict[str, Any]]] = {}

    def fetch_package_data(self, package_name: str) -> Optional[Dict[str, Any]]:
        """Fetch package metadata from PyPI JSON API with in-memory caching."""
        canon = canonicalize_name(package_name)
        if self.offline:
            return None

        if canon in self._cache:
            return self._cache[canon]

        url = PYPI_URL_TEMPLATE.format(package=canon)
        headers = {"User-Agent": "pyproject-dep-doctor/0.1.0"}
        req = urllib.request.Request(url, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    self._cache[canon] = data
                    return data
        except urllib.error.HTTPError as e:
            if e.code == 404:
                # Package does not exist
                self._cache[canon] = {"error": "not_found", "status": 404}
                return self._cache[canon]
            self._cache[canon] = None
        except Exception:
            # Network timeout, DNS failure, or offline environment
            self._cache[canon] = None

        return None

    def get_available_versions(self, package_name: str) -> List[Version]:
        """Retrieve all valid released versions for a package on PyPI."""
        data = self.fetch_package_data(package_name)
        if not data or "releases" not in data:
            return []

        versions: List[Version] = []
        for ver_str in data["releases"].keys():
            try:
                versions.append(Version(ver_str))
            except InvalidVersion:
                continue
        return sorted(versions)

    def get_latest_version(self, package_name: str) -> Optional[Version]:
        """Return the latest non-prerelease version available on PyPI."""
        versions = self.get_available_versions(package_name)
        stable = [v for v in versions if not v.is_prerelease and not v.is_devrelease]
        return stable[-1] if stable else (versions[-1] if versions else None)

    def validate_declaration(self, decl: DependencyDeclaration) -> Optional[DependencyIssue]:
        """Validate a single dependency declaration against PyPI."""
        if self.offline:
            return None

        data = self.fetch_package_data(decl.name)
        if not data:
            return None

        if data.get("error") == "not_found":
            return DependencyIssue(
                issue_type=IssueType.PYPI_NOT_FOUND,
                severity=IssueSeverity.ERROR,
                package=decl.name,
                message=f"Package '{decl.name}' in '{decl.group}' was not found on PyPI.",
                groups=[decl.group],
                declarations=[decl],
                suggested_fix=f"Verify the package name '{decl.name}' on https://pypi.org/",
                line_number=decl.line_number,
            )

        releases = data.get("releases", {})
        if not releases:
            return None

        # Check if version specifier can be satisfied by existing releases
        all_versions = self.get_available_versions(decl.name)
        if not all_versions:
            return None

        if decl.specifier:
            matching = [v for v in all_versions if v in decl.specifier]
            if not matching:
                latest = self.get_latest_version(decl.name)
                latest_str = f" Latest release is {latest}." if latest else ""
                return DependencyIssue(
                    issue_type=IssueType.PYPI_NO_MATCHING_VERSION,
                    severity=IssueSeverity.ERROR,
                    package=decl.name,
                    message=(
                        f"No available PyPI release for '{decl.name}' satisfies constraint "
                        f"'{decl.specifier}' (in {decl.group}).{latest_str}"
                    ),
                    groups=[decl.group],
                    declarations=[decl],
                    suggested_fix=f"Adjust version constraint to match available versions (e.g. '>={latest}')" if latest else None,
                    line_number=decl.line_number,
                )

        return None

    def validate_declarations(
        self,
        declarations: List[DependencyDeclaration],
        ignore_packages: Optional[Set[str]] = None,
    ) -> List[DependencyIssue]:
        """Concurrently validate multiple declarations against PyPI."""
        if self.offline or not declarations:
            return []

        ignore = ignore_packages or set()
        active = [d for d in declarations if d.canonical_name not in ignore]
        issues: List[DependencyIssue] = []

        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(active) or 1)) as executor:
            future_to_decl = {executor.submit(self.validate_declaration, d): d for d in active}
            for future in as_completed(future_to_decl):
                try:
                    res = future.result()
                    if res:
                        issues.append(res)
                except Exception:
                    pass

        return issues
