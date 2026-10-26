# pyproject-dep-doctor

[![CI](https://github.com/slopgobblercobbler/pyproject-dep-doctor/actions/workflows/ci.yml/badge.svg)](https://github.com/slopgobblercobbler/pyproject-dep-doctor/actions/workflows/ci.yml)
[![Python Versions](https://img.shields.io/badge/python-3.9%20%7C%203.10%20%7C%203.11%20%7C%203.12-blue)](https://pypi.org/project/pyproject-dep-doctor/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Code Style](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A production-grade CLI and diagnostic library to analyze `pyproject.toml` dependencies, detect version constraint conflicts across optional dependency groups and extras, validate against PyPI, and automatically heal conflicting requirements.

---

## 🔍 Why pyproject-dep-doctor?

Modern Python projects rely heavily on `pyproject.toml` standards (PEP 621, Poetry, PDM, PEP 735 dependency groups). However, maintaining compatible constraints across `[project.dependencies]`, multiple optional extras (`[project.optional-dependencies]`), and developer dependency groups is error-prone:

- **Cross-Group Clashes**: Main dependencies specify `urllib3<2.0.0` while `dev` or `test` extras require `urllib3>=2.0.0`, breaking developer installations.
- **Duplicate & Redundant Specs**: Packages declared in multiple places with disjoint, overlapping, or identical version specifications.
- **Unsatisfiable PyPI Versions**: Pinned constraints targeting releases that were yanked or do not exist on PyPI.
- **Silent CI Breakages**: Incompatibilities often go unnoticed until users run `pip install .[all]` or automated lockfile generators fail cryptically.

`pyproject-dep-doctor` inspects your project specifications, solves version constraint intersections analytically using PEP 440 mathematics, and generates non-destructive automated fixes.

---

## ✨ Features

- **Multi-Format Standards Support**:
  - **PEP 621**: Standard `[project.dependencies]` and `[project.optional-dependencies]`
  - **Poetry**: `[tool.poetry.dependencies]`, `[tool.poetry.group.<name>.dependencies]`, and legacy `[tool.poetry.dev-dependencies]` (including Poetry caret `^` and tilde `~` translation to PEP 440)
  - **PEP 735**: Modern `[dependency-groups]` tables
  - **PDM**: `[tool.pdm.dev-dependencies]`
- **PEP 440 & PEP 508 Constraint Mathematics**:
  - Analytical interval overlap and disjointness detection
  - Simplification of redundant constraint clauses (e.g., `>=1.0.0,>=2.0.0` $\rightarrow$ `>=2.0.0`)
- **Environment Marker Awareness**:
  - Understands platform-exclusive markers (e.g. `sys_platform == 'win32'` vs `sys_platform == 'linux'`) to avoid false-positive conflict alarms on cross-platform dependencies.
- **Automated Fixers & Unification**:
  - Resolves conflicts using configurable strategies: `intersect`, `latest`, or `loosen`.
  - In-place file modification with comment preservation and automatic `.bak` backups.
  - Dry-run mode displaying unified diffs.
- **PyPI Availability Validation**:
  - Concurrently queries PyPI to verify that packages exist and that declared version constraints match published releases.
  - Full offline mode (`--offline`) for isolated environments and air-gapped CI.
- **Multi-Output Reporting**:
  - Human-friendly color terminal reports.
  - Machine-readable JSON output for automated pipelines.
  - Markdown tables for Pull Request summaries.
  - GitHub Actions annotations (`::error` and `::warning`).

---

## 📦 Installation

### From PyPI
```bash
pip install pyproject-dep-doctor
```

### From Source
```bash
git clone https://github.com/slopgobblercobbler/pyproject-dep-doctor.git
cd pyproject-dep-doctor
pip install -e .
```

---

## 🚀 Quick Start

### 1. Diagnose Dependencies
Run `check` against your local `pyproject.toml`:

```bash
# Analyze current directory pyproject.toml
pyproject-dep-doctor check

# Offline analysis (no network queries to PyPI)
pyproject-dep-doctor check --offline

# Check a specific file with strict enforcement
pyproject-dep-doctor check path/to/pyproject.toml --strict
```

### 2. Output Formats
Generate report in different formats for CI or reporting:

```bash
# JSON output
pyproject-dep-doctor check --format json --output report.json

# Markdown output (ideal for GitHub Actions PR comments)
pyproject-dep-doctor check --format markdown

# GitHub Actions workflow annotations
pyproject-dep-doctor check --format github
```

### 3. Automatically Fix Conflicts
Heal conflicting dependencies directly in `pyproject.toml`:

```bash
# Preview proposed fixes without altering files
pyproject-dep-doctor fix --dry-run

# Apply fixes using the 'intersect' strategy (tightest compatible constraint)
pyproject-dep-doctor fix

# Apply fixes using the 'latest' strategy (favor highest modern version)
pyproject-dep-doctor fix --strategy latest

# Apply fixes without generating a .bak backup file
pyproject-dep-doctor fix --no-backup
```

---

## 🛠️ CLI Reference

### Global Flags
- `-V, --version`: Display tool version and exit.
- `-h, --help`: Display help and command usage.

### `pyproject-dep-doctor check [PATH]`
Analyze `pyproject.toml` dependencies and report version conflicts.

| Option | Flag | Description |
|---|---|---|
| `PATH` | (positional) | Path to `pyproject.toml` (default: `./pyproject.toml`). |
| `--format` | `-f` | Output format: `text` (default), `json`, `markdown`, `github`. |
| `--offline` | | Skip PyPI remote queries; perform local constraint analysis only. |
| `--strict` | | Enforce strict mode (treat unpinned dependencies and warnings as errors). |
| `--ignore` | | Space-separated list of package names to ignore during checks. |
| `--group` | | Specific dependency groups to check (e.g. `project.dependencies dev`). |
| `--output` | `-o` | Write report to file path instead of stdout. |
| `--no-color` | | Disable ANSI terminal color styling. |

### `pyproject-dep-doctor fix [PATH]`
Automatically resolve dependency conflicts and update `pyproject.toml`.

| Option | Flag | Description |
|---|---|---|
| `PATH` | (positional) | Path to `pyproject.toml` (default: `./pyproject.toml`). |
| `--strategy`| `-s` | Resolution strategy: `intersect` (default), `latest`, `loosen`. |
| `--dry-run` | | Preview changes as unified diff without modifying files on disk. |
| `--no-backup`| | Do not generate a `.bak` backup file before writing changes. |
| `--offline` | | Skip remote queries to PyPI during resolution. |
| `--no-color`| | Disable ANSI terminal color styling. |

### Resolution Strategies
- **`intersect`** *(default)*: Computes the mathematical intersection of all declared constraints. If bounds are mutually compatible, tightens the range to guarantee satisfaction everywhere.
- **`latest`**: Selects the highest lower bound across all declarations to modernize older requirements.
- **`loosen`**: Merges bounds to span the widest possible range (`>=min_lower,<max_upper`), maximizing compatibility.

### Exit Codes
- **`0`**: Success. No errors or conflicts discovered (or fixes successfully applied).
- **`1`**: Dependency errors discovered (or warnings under `--strict`).
- **`2`**: Invalid CLI arguments or target file not found.

---

## 🐍 Python API Usage

You can also embed `pyproject-dep-doctor` directly inside your Python tooling:

```python
from pyproject_dep_doctor import (
    parse_pyproject,
    DependencyChecker,
    DependencyResolver,
    ResolutionStrategy,
    fix_pyproject,
)

# 1. Parse pyproject.toml
declarations, syntax_issues = parse_pyproject("pyproject.toml")

# 2. Check for conflicts
checker = DependencyChecker(declarations, strict=False)
issues = checker.check()
for issue in issues:
    print(f"[{issue.severity.upper()}] {issue.package}: {issue.message}")

# 3. Apply automated fixes programmatically
modified_text, diff, applied_actions = fix_pyproject(
    "pyproject.toml",
    strategy=ResolutionStrategy.INTERSECT,
    dry_run=True,
)
print(diff)
```

---

## 🤖 GitHub Actions Workflow Example

Add `pyproject-dep-doctor` to your GitHub Actions CI matrix:

```yaml
name: Dependency Doctor
on: [push, pull_request]

jobs:
  check-dependencies:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install pyproject-dep-doctor
      - run: pyproject-dep-doctor check --format github --strict
```

---

## 🤝 Contributing

Contributions are welcome! Please follow these steps:
1. Fork repository and create your feature branch: `git checkout -b feature/my-feature`.
2. Install dependencies: `pip install -e ".[test]"`.
3. Run test suite: `pytest -v`.
4. Submit a Pull Request.

---

## 📄 License

This project is licensed under the terms of the [MIT License](LICENSE).
Copyright (c) 2026 slopggobblercobbler81.
