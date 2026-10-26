"""Unit tests for pyproject_dep_doctor.pypi."""

import json
import urllib.error
from unittest.mock import MagicMock, patch

from packaging.specifiers import SpecifierSet
from packaging.version import Version

from pyproject_dep_doctor.models import (
    DependencyDeclaration,
    IssueSeverity,
    IssueType,
)
from pyproject_dep_doctor.pypi import PyPIClient


def make_mock_response(status_code: int, data: dict):
    resp = MagicMock()
    resp.status = status_code
    resp.read.return_value = json.dumps(data).encode("utf-8")
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = None
    return resp


def test_pypi_client_offline():
    client = PyPIClient(offline=True)
    assert client.fetch_package_data("requests") is None
    assert client.get_available_versions("requests") == []
    assert client.get_latest_version("requests") is None

    decl = DependencyDeclaration(
        name="requests",
        raw_spec="requests>=2.0.0",
        group="project.dependencies",
        specifier=SpecifierSet(">=2.0.0"),
    )
    assert client.validate_declaration(decl) is None
    assert client.validate_declarations([decl]) == []


def test_pypi_client_success_and_caching():
    client = PyPIClient(offline=False)
    fake_data = {
        "info": {"version": "2.28.2"},
        "releases": {
            "2.28.0": [],
            "2.28.1": [],
            "2.28.2": [],
            "3.0.0a1": [],
        },
    }

    mock_resp = make_mock_response(200, fake_data)

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        data = client.fetch_package_data("requests")
        assert data is not None
        assert "releases" in data

        # Second call should use cache
        data2 = client.fetch_package_data("requests")
        assert data2 == data
        assert mock_urlopen.call_count == 1

    versions = client.get_available_versions("requests")
    assert Version("2.28.0") in versions
    assert Version("3.0.0a1") in versions

    latest = client.get_latest_version("requests")
    assert latest == Version("2.28.2")


def test_pypi_client_not_found():
    client = PyPIClient(offline=False)
    http_error = urllib.error.HTTPError("url", 404, "Not Found", {}, None)

    with patch("urllib.request.urlopen", side_effect=http_error):
        decl = DependencyDeclaration(
            name="nonexistent-pkg-9999",
            raw_spec="nonexistent-pkg-9999>=1.0.0",
            group="project.dependencies",
            specifier=SpecifierSet(">=1.0.0"),
        )
        issue = client.validate_declaration(decl)
        assert issue is not None
        assert issue.issue_type == IssueType.PYPI_NOT_FOUND
        assert issue.severity == IssueSeverity.ERROR


def test_pypi_client_no_matching_version():
    client = PyPIClient(offline=False)
    fake_data = {
        "releases": {
            "1.0.0": [],
            "1.1.0": [],
        },
    }
    mock_resp = make_mock_response(200, fake_data)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        decl = DependencyDeclaration(
            name="old-pkg",
            raw_spec="old-pkg>=2.0.0",
            group="project.dependencies",
            specifier=SpecifierSet(">=2.0.0"),
        )
        issue = client.validate_declaration(decl)
        assert issue is not None
        assert issue.issue_type == IssueType.PYPI_NO_MATCHING_VERSION
        assert issue.severity == IssueSeverity.ERROR


def test_pypi_validate_declarations_concurrent():
    client = PyPIClient(offline=False)
    fake_data = {
        "releases": {"1.0.0": []},
    }
    mock_resp = make_mock_response(200, fake_data)

    d1 = DependencyDeclaration(
        name="pkg-one",
        raw_spec="pkg-one>=1.0.0",
        group="project.dependencies",
        specifier=SpecifierSet(">=1.0.0"),
    )
    d2 = DependencyDeclaration(
        name="pkg-two",
        raw_spec="pkg-two>=9.0.0",
        group="project.dependencies",
        specifier=SpecifierSet(">=9.0.0"),
    )

    with patch("urllib.request.urlopen", return_value=mock_resp):
        # Ignore pkg-two
        issues = client.validate_declarations([d1, d2], ignore_packages={"pkg-two"})
        assert len(issues) == 0

        # Don't ignore pkg-two
        issues_all = client.validate_declarations([d1, d2])
        assert len(issues_all) == 1
        assert issues_all[0].package == "pkg-two"
