"""Contract tests for PEP 621/639 metadata, CI matrix, gitignore hygiene, and documentation parity."""

from __future__ import annotations

import json
import re
from pathlib import Path

try:
    import tomllib
except ImportError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib

import ellmos_homecontrol
from ellmos_homecontrol.cli import main

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_pyproject_pep621_and_pep639_metadata():
    """Verify PEP 621 metadata, PEP 639 license expression without redundant classifier, and frozen version."""
    pyproject_path = REPO_ROOT / "pyproject.toml"
    assert pyproject_path.is_file()
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    project = data["project"]
    assert any("setuptools>=77.0.3" in req for req in data["build-system"]["requires"])
    assert project["name"] == "ellmos-homecontrol"
    assert project["version"] == "0.1.0"
    assert ellmos_homecontrol.__version__ == project["version"]
    assert project["requires-python"] == ">=3.10"
    assert project["license"] == "MIT"
    assert "LICENSE" in project["license-files"]
    assert "CONTRIBUTING.md" in project["license-files"]
    assert project["dependencies"] == []

    classifiers = project["classifiers"]
    assert not any(c.startswith("License ::") for c in classifiers), (
        "PEP 639 license string must not be combined with License :: OSI Approved classifiers"
    )
    for py_ver in ("3.10", "3.11", "3.12", "3.13"):
        assert f"Programming Language :: Python :: {py_ver}" in classifiers

    urls = project["urls"]
    for key in (
        "Homepage",
        "Repository",
        "Documentation",
        "Issues",
        "Changelog",
        "Contributing",
        "Security",
        "Parent Organization",
        "Umbrella Ecosystem",
    ):
        assert urls[key].startswith("https://github.com/")


def test_pytest_options_have_no_relative_basetemp():
    """Verify pytest addopts avoids relative --basetemp and excludes temp/cache dirs from collection."""
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    ini_opts = data["tool"]["pytest"]["ini_options"]
    addopts = ini_opts.get("addopts", "")
    assert "--basetemp" not in addopts
    assert ini_opts.get("xfail_strict") is True

    norecurse = set(ini_opts.get("norecursedirs", []))
    for required_dir in (".git", ".pytest_cache", ".pytest_temp", ".pytest_tmp*", "__pycache__", "build", "dist"):
        assert required_dir in norecurse


def test_ellmos_module_manifest_parity():
    """Verify ellmos-module.v2.json matches pyproject.toml metadata and entrypoints."""
    manifest = json.loads((REPO_ROOT / "ellmos-module.v2.json").read_text(encoding="utf-8"))
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]

    assert manifest["schema"] == "ellmos.module.v2"
    assert manifest["id"] == project["name"]
    assert manifest["name"] == project["name"]
    assert manifest["version"] == project["version"]
    assert manifest["repository"] == project["urls"]["Repository"]
    assert manifest["entrypoints"]["cli"] == project["scripts"]["ellmos-homecontrol"]


def test_required_hygiene_and_community_files_exist():
    """Verify community, packaging, security, and PEP 561 marker files exist."""
    required = [
        "LICENSE",
        "README.md",
        "README_de.md",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "CODE_OF_CONDUCT.md",
        "MANIFEST.in",
        "src/ellmos_homecontrol/py.typed",
        ".github/dependabot.yml",
        ".github/labels.yml",
        ".github/ISSUE_TEMPLATE/bug_report.md",
        ".github/ISSUE_TEMPLATE/feature_request.md",
        ".github/workflows/ci.yml",
        ".github/workflows/auto-assign.yml",
        ".github/workflows/label-sync.yml",
        ".github/workflows/stale.yml",
    ]
    for rel in required:
        assert (REPO_ROOT / rel).is_file(), f"Missing required hygiene file: {rel}"


def test_gitignore_excludes_locks_caches_and_conflicts():
    """Verify .gitignore excludes multi-agent locks, sync conflicts, secrets, and pytest temp dirs."""
    content = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in (
        ".pytest_cache/",
        ".pytest_temp/",
        ".pytest_tmp*/",
        ".ruff_cache/",
        "LOCK.txt",
        "LOCK.*.txt",
        "LOCK-CACHE*.md",
        "*-WORKSTATION-LG*",
        "*-ASUS-GEI*",
        "*MARKETING-LOG.txt",
        ".env",
        "*.db",
    ):
        assert pattern in content, f".gitignore missing pattern: {pattern}"


def test_ci_workflow_matrix_and_gates():
    """Verify CI workflow enforces OS/Python matrix, concurrency, pip check, ruff, compileall, and pytest."""
    ci_text = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    for token in (
        "contents: read",
        "cancel-in-progress: true",
        "fail-fast: false",
        "ubuntu-latest",
        "windows-latest",
        "macos-latest",
        '"3.10"',
        '"3.11"',
        '"3.12"',
        '"3.13"',
        "python -m pip check",
        "python -m compileall -q src tests",
        "python -m ruff check src tests",
        "python -m pytest -ra -v",
    ):
        assert token in ci_text

    auto_assign = (REPO_ROOT / ".github" / "workflows" / "auto-assign.yml").read_text(encoding="utf-8")
    assert "github.event.pull_request.user.type != 'Bot'" in auto_assign


def test_security_and_changelog_content():
    """Verify SECURITY.md uses private vulnerability reporting without placeholder emails and CHANGELOG has Unreleased."""
    security = (REPO_ROOT / "SECURITY.md").read_text(encoding="utf-8")
    assert "Private Vulnerability Reporting" in security
    assert "Advisories" in security
    assert "lukas@geiger.sh" not in security

    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## [Unreleased]" in changelog
    assert "## [0.1.0]" in changelog


def test_readme_bilingual_parity_and_local_links():
    """Verify README.md and README_de.md link to each other, reference existing files, and keep banner."""
    en_text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    de_text = (REPO_ROOT / "README_de.md").read_text(encoding="utf-8")

    assert "assets/banner.svg" in en_text
    assert "assets/banner.svg" in de_text
    assert "(README_de.md)" in en_text
    assert "(README.md)" in de_text

    for doc_name, text in (("README.md", en_text), ("README_de.md", de_text)):
        assert "v0.1.0" in text
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
            if target.startswith(("http://", "https://", "#")):
                continue
            assert (REPO_ROOT / target).exists(), f"{doc_name} links to missing local path: {target}"


def test_cli_subcommands_smoke(capsys):
    """Verify CLI list, get, set --confirm, and scene commands produce valid JSON output."""
    assert main(["list", "--adapter", "fritzbox"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert len(listed) == 1
    assert listed[0]["device_id"] == "fritz.dect200.office"

    assert main(["get", "ha.light.studio_main"]) == 0
    got = json.loads(capsys.readouterr().out)
    assert got["device_id"] == "ha.light.studio_main"

    assert main(["set", "shelly.appliance.washer", '{"on": true}', "--confirm"]) == 0
    updated = json.loads(capsys.readouterr().out)
    assert updated["state"]["on"] is True

    assert main(["scene", "evening_calm"]) == 0
    scene_res = json.loads(capsys.readouterr().out)
    assert scene_res["scene_id"] == "evening_calm"
