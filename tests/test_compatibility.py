"""Unit tests for pyproject_dep_doctor.compatibility."""

from packaging.markers import Marker
from packaging.specifiers import SpecifierSet
from packaging.version import Version

from pyproject_dep_doctor.compatibility import (
    DependencyChecker,
    are_markers_exclusive,
    are_specifiers_compatible,
    extract_versions_from_specifier,
    generate_candidate_versions,
    intersect_specifiers,
    simplify_specifier_set,
)
from pyproject_dep_doctor.models import IssueSeverity, IssueType
from pyproject_dep_doctor.parser import parse_pyproject


def test_are_markers_exclusive():
    # None markers
    assert are_markers_exclusive(None, None) is False
    assert are_markers_exclusive(Marker("sys_platform == 'win32'"), None) is False
    assert are_markers_exclusive(None, Marker("sys_platform == 'linux'")) is False

    # Identical markers
    m_win = Marker("sys_platform == 'win32'")
    assert are_markers_exclusive(m_win, m_win) is False

    # Exclusive platforms
    m_linux = Marker("sys_platform == 'linux'")
    assert are_markers_exclusive(m_win, m_linux) is True

    m_darwin = Marker("sys_platform == 'darwin'")
    assert are_markers_exclusive(m_win, m_darwin) is True
    assert are_markers_exclusive(m_linux, m_darwin) is True

    # Same platform family
    m_win_alias = Marker("sys_platform == 'windows'")
    assert are_markers_exclusive(m_win, m_win_alias) is False

    # Non-exclusive markers (e.g. python version)
    m_py39 = Marker("python_version >= '3.9'")
    m_py310 = Marker("python_version >= '3.10'")
    assert are_markers_exclusive(m_py39, m_py310) is False


def test_extract_versions_from_specifier():
    spec = SpecifierSet(">=2.28.0,<3.0.0,!=2.29.1")
    versions = extract_versions_from_specifier(spec)
    assert Version("2.28.0") in versions
    assert Version("3.0.0") in versions
    assert Version("2.29.1") in versions


def test_generate_candidate_versions():
    spec = SpecifierSet(">=1.5.0,<2.0.0")
    candidates = generate_candidate_versions(spec)
    assert Version("1.5.0") in candidates
    assert Version("2.0.0") in candidates
    # Boundary neighbors
    assert Version("1.5.1") in candidates
    assert Version("1.4.0") in candidates


def test_are_specifiers_compatible():
    # Overlapping ranges
    s1 = SpecifierSet(">=2.0.0,<3.0.0")
    s2 = SpecifierSet(">=2.5.0,<4.0.0")
    assert are_specifiers_compatible(s1, s2) is True

    # Mutually disjoint ranges
    s3 = SpecifierSet("<2.0.0")
    s4 = SpecifierSet(">=2.0.0")
    assert are_specifiers_compatible(s3, s4) is False

    # Exact equality vs range
    s5 = SpecifierSet("==2.1.0")
    s6 = SpecifierSet(">=2.0.0,<3.0.0")
    assert are_specifiers_compatible(s5, s6) is True

    s7 = SpecifierSet("==1.0.0")
    assert are_specifiers_compatible(s7, s6) is False

    # Conflicting exact equalities
    s8 = SpecifierSet("==2.0.0")
    s9 = SpecifierSet("==2.0.1")
    assert are_specifiers_compatible(s8, s9) is False

    # Empty specifiers
    assert are_specifiers_compatible(SpecifierSet(""), SpecifierSet(">=1.0.0")) is True
    assert are_specifiers_compatible(SpecifierSet(""), SpecifierSet("")) is True


def test_simplify_specifier_set():
    assert simplify_specifier_set(SpecifierSet("")) == SpecifierSet("")

    # Lower bound simplification
    s_lower = SpecifierSet(">=1.0.0,>=1.5.0,>=2.0.0")
    simplified = simplify_specifier_set(s_lower)
    assert str(simplified) == ">=2.0.0"

    # Upper bound simplification
    s_upper = SpecifierSet("<3.0.0,<2.5.0,<4.0.0")
    simplified_up = simplify_specifier_set(s_upper)
    assert str(simplified_up) == "<2.5.0"


def test_intersect_specifiers():
    assert intersect_specifiers(SpecifierSet(""), SpecifierSet(">=1.0.0")) == SpecifierSet(">=1.0.0")
    assert intersect_specifiers(SpecifierSet(">=1.0.0"), SpecifierSet("")) == SpecifierSet(">=1.0.0")

    s1 = SpecifierSet(">=1.0.0")
    s2 = SpecifierSet(">=2.0.0")
    res = intersect_specifiers(s1, s2)
    assert str(res) == ">=2.0.0"


def test_checker_valid_toml(valid_toml):
    decls, syntax_issues = parse_pyproject(valid_toml)
    checker = DependencyChecker(decls)
    issues = checker.check()
    assert len(issues) == 0


def test_checker_conflicts(conflicting_toml):
    decls, _ = parse_pyproject(conflicting_toml)
    checker = DependencyChecker(decls)
    issues = checker.check()

    assert len(issues) >= 2
    err_packages = {issue.package for issue in issues if issue.severity == IssueSeverity.ERROR}
    assert "urllib3" in err_packages
    assert "requests" in err_packages


def test_checker_duplicates(duplicate_toml):
    decls, _ = parse_pyproject(duplicate_toml)
    checker = DependencyChecker(decls)
    issues = checker.check()

    # pydantic appears twice with different constraints (>=1.8.0 and >=2.0.0) which are compatible
    assert len(issues) == 1
    issue = issues[0]
    assert issue.package == "pydantic"
    assert issue.issue_type == IssueType.DUPLICATE_DEPENDENCY
    assert issue.severity == IssueSeverity.WARNING


def test_checker_exclusive_markers(exclusive_markers_toml):
    decls, _ = parse_pyproject(exclusive_markers_toml)
    checker = DependencyChecker(decls)
    issues = checker.check()
    # pywin32 and uvloop are on win32 vs linux, should not conflict
    assert len(issues) == 0


def test_checker_unpinned(unpinned_toml):
    decls, _ = parse_pyproject(unpinned_toml)

    # Standard check: unpinned produces WARNING
    checker = DependencyChecker(decls, strict=False)
    issues = checker.check()
    assert len(issues) == 2
    assert all(i.issue_type == IssueType.UNPINNED_DEPENDENCY for i in issues)
    assert all(i.severity == IssueSeverity.WARNING for i in issues)

    # Strict check: unpinned produces ERROR
    strict_checker = DependencyChecker(decls, strict=True)
    strict_issues = strict_checker.check()
    assert len(strict_issues) == 2
    assert all(i.severity == IssueSeverity.ERROR for i in strict_issues)


def test_checker_ignore_and_groups():
    toml_str = """\
[project]
name = "demo"
version = "0.1.0"
dependencies = [
    "requests",
    "flask",
]

[project.optional-dependencies]
dev = [
    "urllib3>=2.0.0",
]
"""
    decls, _ = parse_pyproject(toml_str)

    # Ignore requests
    checker = DependencyChecker(decls, ignore_packages=["requests"])
    issues = checker.check()
    assert not any(i.package == "requests" for i in issues)
    assert any(i.package == "flask" for i in issues)

    # Filter by group
    grp_checker = DependencyChecker(decls, checked_groups=["project.optional-dependencies.dev"])
    grp_issues = grp_checker.check()
    assert len(grp_issues) == 0
