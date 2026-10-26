"""pyproject-dep-doctor: Diagnose and heal pyproject.toml dependency conflicts."""

__version__ = "0.1.0"
__author__ = "slopggobblercobbler81"
__license__ = "MIT"

from .models import (
    DependencyDeclaration,
    DependencyIssue,
    DoctorReport,
    IssueSeverity,
    IssueType,
)
from .parser import PyProjectParser, parse_pyproject
from .compatibility import DependencyChecker
from .resolver import DependencyResolver, ResolutionStrategy
from .fixer import PyProjectFixer, fix_pyproject
from .pypi import PyPIClient

__all__ = [
    "__version__",
    "DependencyDeclaration",
    "DependencyIssue",
    "DoctorReport",
    "IssueSeverity",
    "IssueType",
    "PyProjectParser",
    "parse_pyproject",
    "DependencyChecker",
    "DependencyResolver",
    "ResolutionStrategy",
    "PyProjectFixer",
    "fix_pyproject",
    "PyPIClient",
]
