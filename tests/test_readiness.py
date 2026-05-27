"""Unit tests for the readiness checklist."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai_eng_audit.readiness import CHECKS, compute_readiness


def _touch(repo: Path, rel: str, content: str = "") -> Path:
    """Create a file at repo/rel, creating parent dirs as needed."""
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _check(result, key: str):
    return next(c for c in result.checks if c.key == key)


class EmptyRepoTests(unittest.TestCase):
    def test_empty_repo_marks_everything_missing(self):
        with tempfile.TemporaryDirectory() as d:
            result = compute_readiness(Path(d))
            self.assertTrue(all(not c.present for c in result.checks))
            self.assertEqual(len(result.checks), len(CHECKS))


class CITestingChecksTests(unittest.TestCase):
    def test_github_workflows_detected(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _touch(repo, ".github/workflows/ci.yml", "name: ci\n")
            result = compute_readiness(repo)
            self.assertTrue(_check(result, "ci_workflow").present)
            self.assertEqual(
                _check(result, "ci_workflow").found_at, ".github/workflows/"
            )

    def test_gitlab_ci_detected(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _touch(repo, ".gitlab-ci.yml", "stages:\n")
            result = compute_readiness(repo)
            self.assertTrue(_check(result, "ci_workflow").present)
            self.assertEqual(
                _check(result, "ci_workflow").found_at, ".gitlab-ci.yml"
            )

    def test_empty_workflows_dir_does_not_count(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            (repo / ".github" / "workflows").mkdir(parents=True)
            # no yml inside
            result = compute_readiness(repo)
            self.assertFalse(_check(result, "ci_workflow").present)

    def test_tests_directory_detected(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _touch(repo, "tests/test_foo.py")
            result = compute_readiness(repo)
            self.assertTrue(_check(result, "tests_dir").present)

    def test_spec_directory_detected(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _touch(repo, "spec/something_spec.rb")
            result = compute_readiness(repo)
            self.assertTrue(_check(result, "tests_dir").present)

    def test_lint_config_detected(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _touch(repo, ".eslintrc.json", "{}")
            result = compute_readiness(repo)
            self.assertTrue(_check(result, "lint_config").present)


class DocumentationChecksTests(unittest.TestCase):
    def test_readme_md_detected(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _touch(repo, "README.md", "# foo")
            result = compute_readiness(repo)
            self.assertTrue(_check(result, "readme").present)

    def test_readme_rst_detected(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _touch(repo, "README.rst", "foo\n===\n")
            result = compute_readiness(repo)
            self.assertTrue(_check(result, "readme").present)

    def test_contributing_in_docs(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _touch(repo, "docs/CONTRIBUTING.md")
            result = compute_readiness(repo)
            self.assertTrue(_check(result, "contributing").present)

    def test_license_variants(self):
        for fname in ("LICENSE", "LICENSE.md", "COPYING", "LICENSE-MIT"):
            with tempfile.TemporaryDirectory() as d:
                repo = Path(d)
                _touch(repo, fname)
                result = compute_readiness(repo)
                self.assertTrue(
                    _check(result, "license").present, f"{fname} should count"
                )


class CollaborationChecksTests(unittest.TestCase):
    def test_codeowners_in_github(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _touch(repo, ".github/CODEOWNERS", "* @team\n")
            result = compute_readiness(repo)
            self.assertTrue(_check(result, "codeowners").present)

    def test_pr_template_detected(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _touch(repo, ".github/pull_request_template.md")
            result = compute_readiness(repo)
            self.assertTrue(_check(result, "pr_template").present)


class ConfigSecurityChecksTests(unittest.TestCase):
    def test_gitignore_detected(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _touch(repo, ".gitignore", "*.pyc\n")
            result = compute_readiness(repo)
            self.assertTrue(_check(result, "gitignore").present)

    def test_env_example_variants(self):
        for fname in (".env.example", ".env.template", ".env.sample"):
            with tempfile.TemporaryDirectory() as d:
                repo = Path(d)
                _touch(repo, fname, "KEY=value\n")
                result = compute_readiness(repo)
                self.assertTrue(
                    _check(result, "env_example").present, f"{fname} should count"
                )


class CompleteRepoTest(unittest.TestCase):
    def test_full_repo_passes_all_checks(self):
        """A realistic repo with all expected files should mark every check present."""
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _touch(repo, ".github/workflows/ci.yml")
            _touch(repo, "tests/test_x.py")
            _touch(repo, ".eslintrc.json")
            _touch(repo, "README.md")
            _touch(repo, "CONTRIBUTING.md")
            _touch(repo, "LICENSE")
            _touch(repo, ".github/CODEOWNERS")
            _touch(repo, ".github/pull_request_template.md")
            _touch(repo, ".gitignore")
            _touch(repo, ".env.example")

            result = compute_readiness(repo)
            missing = [c.key for c in result.checks if not c.present]
            self.assertEqual(missing, [], f"unexpected misses: {missing}")


if __name__ == "__main__":
    unittest.main()
