"""Unit tests for pyproject_dep_doctor.cli."""

from pathlib import Path
import pytest

from pyproject_dep_doctor.cli import build_parser, check_file, main


def test_cli_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "pyproject-dep-doctor 0.1.0" in captured.out


def test_check_file_not_found():
    with pytest.raises(FileNotFoundError):
        check_file("does_not_exist_file.toml")


def test_cli_check_valid(tmp_path, valid_toml, capsys):
    test_file = tmp_path / "pyproject.toml"
    test_file.write_text(valid_toml, encoding="utf-8")

    code = main(["check", str(test_file), "--offline", "--no-color"])
    assert code == 0
    captured = capsys.readouterr()
    assert "All dependency version constraints are valid and compatible!" in captured.out


def test_cli_check_conflicts(tmp_path, conflicting_toml, capsys):
    test_file = tmp_path / "pyproject.toml"
    test_file.write_text(conflicting_toml, encoding="utf-8")

    code = main(["check", str(test_file), "--offline", "--no-color"])
    assert code == 1
    captured = capsys.readouterr()
    assert "[ERROR] urllib3" in captured.out


def test_cli_check_formats(tmp_path, conflicting_toml, capsys):
    test_file = tmp_path / "pyproject.toml"
    test_file.write_text(conflicting_toml, encoding="utf-8")

    # JSON format
    code_json = main(["check", str(test_file), "--format", "json", "--offline"])
    assert code_json == 1
    out_json = capsys.readouterr().out
    assert '"is_valid": false' in out_json

    # Markdown format
    code_md = main(["check", str(test_file), "--format", "markdown", "--offline"])
    assert code_md == 1
    out_md = capsys.readouterr().out
    assert "| 🔴 Error |" in out_md

    # GitHub format
    code_gh = main(["check", str(test_file), "--format", "github", "--offline"])
    assert code_gh == 1
    out_gh = capsys.readouterr().out
    assert "::error file=" in out_gh


def test_cli_check_output_file(tmp_path, valid_toml):
    test_file = tmp_path / "pyproject.toml"
    test_file.write_text(valid_toml, encoding="utf-8")
    out_file = tmp_path / "report.json"

    code = main(["check", str(test_file), "--format", "json", "--output", str(out_file), "--offline"])
    assert code == 0
    assert out_file.exists()
    assert '"is_valid": true' in out_file.read_text(encoding="utf-8")


def test_cli_check_strict_and_ignore(tmp_path, unpinned_toml, capsys):
    test_file = tmp_path / "pyproject.toml"
    test_file.write_text(unpinned_toml, encoding="utf-8")

    # Non-strict check on unpinned returns 0 (warnings only)
    code_normal = main(["check", str(test_file), "--offline", "--no-color"])
    assert code_normal == 0

    # Strict check returns 1
    code_strict = main(["check", str(test_file), "--strict", "--offline", "--no-color"])
    assert code_strict == 1

    # Ignoring all unpinned packages returns 0 even in strict mode
    code_ignored = main(["check", str(test_file), "--strict", "--ignore", "requests", "flask", "--offline"])
    assert code_ignored == 0


def test_cli_check_file_not_found(capsys):
    code = main(["check", "non_existent_file.toml"])
    assert code == 2
    captured = capsys.readouterr()
    assert "Error: File 'non_existent_file.toml' does not exist." in captured.err


def test_cli_default_command(tmp_path, valid_toml, capsys):
    test_file = tmp_path / "pyproject.toml"
    test_file.write_text(valid_toml, encoding="utf-8")

    # Default to check when path given directly
    code = main([str(test_file), "--offline", "--no-color"])
    assert code == 0
    assert "All dependency version constraints are valid and compatible!" in capsys.readouterr().out


def test_cli_fix_dry_run(tmp_path, conflicting_toml, capsys):
    test_file = tmp_path / "pyproject.toml"
    test_file.write_text(conflicting_toml, encoding="utf-8")

    code = main(["fix", str(test_file), "--dry-run", "--strategy", "latest"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Dry run preview" in captured.out
    # Content shouldn't be altered
    assert test_file.read_text(encoding="utf-8") == conflicting_toml


def test_cli_fix_apply(tmp_path, conflicting_toml, capsys):
    test_file = tmp_path / "pyproject.toml"
    test_file.write_text(conflicting_toml, encoding="utf-8")

    code = main(["fix", str(test_file), "--strategy", "intersect"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Successfully applied" in captured.out
    assert (tmp_path / "pyproject.toml.bak").exists()


def test_cli_fix_no_issues_needed(tmp_path, capsys):
    clean_toml = """\
[project]
name = "perfect-pkg"
version = "0.1.0"
dependencies = [
    "requests>=2.28.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
]
"""
    test_file = tmp_path / "pyproject.toml"
    test_file.write_text(clean_toml, encoding="utf-8")

    code = main(["fix", str(test_file), "--offline"])
    assert code == 0
    captured = capsys.readouterr()
    assert "No conflicts or fixes needed" in captured.out


def test_cli_fix_file_not_found(capsys):
    code = main(["fix", "non_existent_target.toml"])
    assert code == 2
    assert "Error: File 'non_existent_target.toml' does not exist." in capsys.readouterr().err
