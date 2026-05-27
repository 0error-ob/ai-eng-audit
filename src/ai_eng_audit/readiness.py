"""Readiness checklist — does this repo have the shared context an AI agent
needs to participate safely?

Each check is a presence test on a known file path (or a small set of known
paths for files that have multiple conventional locations). The checker reads
**file existence only**, never file content. This is the privacy boundary
between the readiness command and the scan command — scan reads metadata
about commits/PRs, readiness reads which files exist at which paths.

Output is a flat checklist, not a score. The tool deliberately does NOT
emit "X / 10" or "ready / not ready" verdicts — those would require external
judgments the methodology declines to make.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


_CheckFn = Callable[[Path], "CheckOutcome"]


@dataclass(frozen=True)
class CheckOutcome:
    """Result of a single presence check."""

    present: bool
    found_at: str | None  # relative path string when present


@dataclass(frozen=True)
class ReadinessCheck:
    """One item in the readiness checklist, with its result attached."""

    key: str  # localization key + stable identifier
    category: str  # localization key for the section header
    present: bool
    found_at: str | None


@dataclass
class ReadinessResult:
    """Output of a readiness scan."""

    repo_path: Path
    checks: list[ReadinessCheck] = field(default_factory=list)


# ---------- individual check implementations ----------


def _exists_any(repo: Path, candidates: list[str]) -> CheckOutcome:
    """True if any of the candidate relative paths exists under repo."""
    for c in candidates:
        if (repo / c).exists():
            return CheckOutcome(present=True, found_at=c)
    return CheckOutcome(present=False, found_at=None)


def _ci_workflow(repo: Path) -> CheckOutcome:
    """GitHub Actions / GitLab CI / CircleCI / Jenkins / Azure Pipelines."""
    gh = repo / ".github" / "workflows"
    if gh.is_dir() and any(
        f.suffix in {".yml", ".yaml"} for f in gh.iterdir() if f.is_file()
    ):
        return CheckOutcome(present=True, found_at=".github/workflows/")
    return _exists_any(
        repo,
        [
            ".gitlab-ci.yml",
            ".circleci/config.yml",
            "Jenkinsfile",
            "azure-pipelines.yml",
            ".buildkite/pipeline.yml",
            ".drone.yml",
        ],
    )


def _tests_dir(repo: Path) -> CheckOutcome:
    """Conventional test locations: tests/, test/, spec/, __tests__/."""
    for d in ("tests", "test", "spec", "__tests__"):
        candidate = repo / d
        if candidate.is_dir() and any(candidate.iterdir()):
            return CheckOutcome(present=True, found_at=f"{d}/")
    return CheckOutcome(present=False, found_at=None)


def _lint_config(repo: Path) -> CheckOutcome:
    """Linter / formatter config: Ruff / ESLint / Flake8 / Prettier / Biome /
    Rubocop / Golangci-lint / clippy. Checks dedicated files; misses configs
    embedded in pyproject.toml or package.json (those would need content read)."""
    return _exists_any(
        repo,
        [
            ".ruff.toml",
            "ruff.toml",
            ".eslintrc",
            ".eslintrc.json",
            ".eslintrc.js",
            ".eslintrc.yml",
            "eslint.config.js",
            "eslint.config.mjs",
            ".flake8",
            ".prettierrc",
            ".prettierrc.json",
            ".prettierrc.yml",
            "biome.json",
            ".rubocop.yml",
            ".golangci.yml",
            ".golangci.yaml",
            "clippy.toml",
        ],
    )


def _readme(repo: Path) -> CheckOutcome:
    return _exists_any(
        repo, ["README.md", "README.rst", "README.txt", "README"]
    )


def _contributing(repo: Path) -> CheckOutcome:
    return _exists_any(
        repo,
        [
            "CONTRIBUTING.md",
            "CONTRIBUTING.rst",
            "CONTRIBUTING",
            "docs/CONTRIBUTING.md",
            ".github/CONTRIBUTING.md",
        ],
    )


def _license(repo: Path) -> CheckOutcome:
    return _exists_any(
        repo,
        [
            "LICENSE",
            "LICENSE.md",
            "LICENSE.txt",
            "LICENSE-MIT",
            "LICENSE-APACHE",
            "COPYING",
        ],
    )


def _codeowners(repo: Path) -> CheckOutcome:
    return _exists_any(
        repo, [".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"]
    )


def _pr_template(repo: Path) -> CheckOutcome:
    return _exists_any(
        repo,
        [
            ".github/pull_request_template.md",
            ".github/PULL_REQUEST_TEMPLATE.md",
            ".github/PULL_REQUEST_TEMPLATE/",
            "docs/pull_request_template.md",
        ],
    )


def _gitignore(repo: Path) -> CheckOutcome:
    return _exists_any(repo, [".gitignore"])


def _env_example(repo: Path) -> CheckOutcome:
    return _exists_any(
        repo, [".env.example", ".env.template", ".env.sample", "env.example"]
    )


# ---------- checklist definition (ordered) ----------


@dataclass(frozen=True)
class _CheckSpec:
    key: str
    category: str
    checker: _CheckFn


CHECKS: list[_CheckSpec] = [
    # CI / Testing
    _CheckSpec("ci_workflow", "ci_testing", _ci_workflow),
    _CheckSpec("tests_dir", "ci_testing", _tests_dir),
    _CheckSpec("lint_config", "ci_testing", _lint_config),
    # Documentation
    _CheckSpec("readme", "documentation", _readme),
    _CheckSpec("contributing", "documentation", _contributing),
    _CheckSpec("license", "documentation", _license),
    # Collaboration flow
    _CheckSpec("codeowners", "collaboration", _codeowners),
    _CheckSpec("pr_template", "collaboration", _pr_template),
    # Config / Security
    _CheckSpec("gitignore", "config_security", _gitignore),
    _CheckSpec("env_example", "config_security", _env_example),
]


def compute_readiness(repo_path: Path) -> ReadinessResult:
    """Run every check against repo_path and return the assembled checklist."""
    checks: list[ReadinessCheck] = []
    for spec in CHECKS:
        outcome = spec.checker(repo_path)
        checks.append(
            ReadinessCheck(
                key=spec.key,
                category=spec.category,
                present=outcome.present,
                found_at=outcome.found_at,
            )
        )
    return ReadinessResult(repo_path=repo_path.resolve(), checks=checks)
