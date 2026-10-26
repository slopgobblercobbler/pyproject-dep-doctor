"""Fixtures and test helpers for pyproject-dep-doctor test suite."""

import sys
from pathlib import Path

# Ensure root package is discoverable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

VALID_PEP621_TOML = """\
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "sample-package"
version = "1.0.0"
dependencies = [
    "requests>=2.28.0,<3.0.0",
    "click>=8.0.0",
    "pydantic>=2.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "requests>=2.28.0",
]
docs = [
    "sphinx>=5.0.0",
]
"""

CONFLICTING_PEP621_TOML = """\
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "conflicting-package"
version = "1.0.0"
dependencies = [
    "urllib3<2.0.0",
    "requests>=2.28.0",
]

[project.optional-dependencies]
test = [
    "pytest>=7.0.0",
    "urllib3>=2.0.0",
]
docs = [
    "sphinx>=5.0.0",
    "requests<2.25.0",
]
"""

DUPLICATE_DEPS_TOML = """\
[project]
name = "dup-package"
version = "0.1.0"
dependencies = [
    "pydantic>=1.8.0",
    "pydantic>=2.0.0",
    "requests>=2.28.0",
]
"""

POETRY_TOML = """\
[tool.poetry]
name = "poetry-app"
version = "0.1.0"

[tool.poetry.dependencies]
python = "^3.9"
requests = "^2.28.0"
fastapi = "~0.95.0"

[tool.poetry.group.dev.dependencies]
pytest = "^7.2.0"
requests = "^2.30.0"
"""

EXCLUSIVE_MARKERS_TOML = """\
[project]
name = "cross-platform-app"
version = "1.0.0"
dependencies = [
    "pywin32>=300; sys_platform == 'win32'",
    "uvloop>=0.16.0; sys_platform == 'linux'",
]
"""

UNPINNED_TOML = """\
[project]
name = "unpinned-app"
version = "1.0.0"
dependencies = [
    "requests",
    "flask",
]
"""

SYNTAX_ERROR_TOML = """\
[project]
name = "syntax-error-app"
version = "1.0.0"
dependencies = [
    "requests ==== 2.0.0 @@ invalid PEP 508",
]
"""

@pytest.fixture
def valid_toml():
    return VALID_PEP621_TOML

@pytest.fixture
def conflicting_toml():
    return CONFLICTING_PEP621_TOML

@pytest.fixture
def duplicate_toml():
    return DUPLICATE_DEPS_TOML

@pytest.fixture
def poetry_toml():
    return POETRY_TOML

@pytest.fixture
def exclusive_markers_toml():
    return EXCLUSIVE_MARKERS_TOML

@pytest.fixture
def unpinned_toml():
    return UNPINNED_TOML

@pytest.fixture
def syntax_error_toml():
    return SYNTAX_ERROR_TOML
