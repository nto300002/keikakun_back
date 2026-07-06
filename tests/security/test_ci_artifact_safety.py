from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
CI_FRONTEND_WORKFLOW = ROOT / ".github/workflows/ci-frontend.yml"
PLAYWRIGHT_CONFIG = ROOT / "k_front/playwright.config.ts"


def test_ci_artifacts_are_failure_only_with_short_retention():
    if not CI_FRONTEND_WORKFLOW.exists():
        pytest.skip("repository root workflow files are not mounted in this test environment")

    workflow = CI_FRONTEND_WORKFLOW.read_text(encoding="utf-8")

    assert "Upload Playwright HTML report" in workflow
    assert "Upload server logs on failure" in workflow
    assert "Upload test results on failure" in workflow
    assert "if: failure()" in workflow
    assert "retention-days: 14" not in workflow
    assert workflow.count("retention-days: 7") >= 3


def test_playwright_artifacts_are_failure_scoped():
    if not PLAYWRIGHT_CONFIG.exists():
        pytest.skip("frontend files are not mounted in this test environment")

    config = PLAYWRIGHT_CONFIG.read_text(encoding="utf-8")

    assert "trace: 'off'" in config
    assert "screenshot: 'only-on-failure'" in config
    assert "video: 'retain-on-failure'" in config
