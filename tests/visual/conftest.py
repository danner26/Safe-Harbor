"""Playwright fixtures + baseline-image helpers for visual-regression tests.

These tests run against a live app served on http://localhost:8000.
Caller (the test runner script or CI) is responsible for starting the
app before running these tests — typically via `docker compose up -d`
or `gunicorn safeharbor.wsgi:app` in the background.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from PIL import Image
from pixelmatch.contrib.PIL import pixelmatch
from playwright.sync_api import Page, sync_playwright

BASELINES_DIR = Path(__file__).parent / "baselines"
DIFFS_DIR = Path(__file__).parent / "diffs"
BASE_URL = "http://localhost:8000"

# Pixel-diff threshold. ~1% of a 1280x1024 image (~13K pixels) tolerates
# font rendering noise across runs without missing palette regressions.
DIFF_THRESHOLD_PIXELS = 13000


@pytest.fixture(scope="session")
def playwright_browser() -> Generator:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def page(playwright_browser) -> Generator[Page, None, None]:
    # Default context without an explicit color scheme — caller sets it via
    # assert_screenshot_matches_baseline which forces a reload after emulation.
    context = playwright_browser.new_context(viewport={"width": 1280, "height": 1024})
    page = context.new_page()
    yield page
    context.close()


def assert_screenshot_matches_baseline(page: Page, name: str, color_scheme: str) -> None:
    """Take a screenshot and compare to a committed baseline.

    On first run (no baseline exists), saves the actual screenshot AS the
    baseline and pytest.skip's the test — engineer commits the baseline,
    subsequent runs assert against it.

    Pixel-diff threshold is set in DIFF_THRESHOLD_PIXELS at module-level.
    Diff images go to tests/visual/diffs/ for inspection on failure.
    """
    # emulate_media changes the CSS media feature but a reload is needed for
    # the page to repaint with the new scheme after the initial load.
    page.emulate_media(color_scheme=color_scheme)
    page.reload(wait_until="networkidle")
    # networkidle fires before document.fonts finishes loading, which on a
    # variable web font (Fraunces) shifts vertical metrics by tens of pixels.
    # Wait for fonts so screenshots are reproducible across hosts.
    page.evaluate("() => document.fonts.ready")

    DIFFS_DIR.mkdir(exist_ok=True)
    BASELINES_DIR.mkdir(exist_ok=True)

    actual_path = DIFFS_DIR / f"{name}_{color_scheme}_actual.png"
    page.screenshot(path=str(actual_path), full_page=True)

    baseline_path = BASELINES_DIR / f"{name}_{color_scheme}.png"

    if not baseline_path.exists():
        # First run — promote actual to baseline, skip the test.
        actual_path.rename(baseline_path)
        pytest.skip(f"Baseline created at {baseline_path}; commit and re-run")

    baseline = Image.open(baseline_path).convert("RGB")
    actual = Image.open(actual_path).convert("RGB")

    # Width must match exactly (viewport is fixed at 1280). Allow small height
    # differences from rendering noise (font subpixel metrics, scrollbar) by
    # cropping both to the common minimum height before pixel-diffing.
    height_tolerance_px = 200
    if baseline.size[0] != actual.size[0]:
        raise AssertionError(
            f"Width mismatch for {name}_{color_scheme}: "
            f"baseline {baseline.size} vs actual {actual.size}"
        )
    height_diff = abs(baseline.size[1] - actual.size[1])
    if height_diff > height_tolerance_px:
        raise AssertionError(
            f"Height diff for {name}_{color_scheme} exceeds tolerance "
            f"({height_diff}px > {height_tolerance_px}px): "
            f"baseline {baseline.size} vs actual {actual.size}"
        )
    if baseline.size != actual.size:
        common_h = min(baseline.size[1], actual.size[1])
        baseline = baseline.crop((0, 0, baseline.size[0], common_h))
        actual = actual.crop((0, 0, actual.size[0], common_h))

    # pixelmatch's slow path writes RGBA-mode raw bytes into the output via
    # frombytes(..., "RGBA"), which requires this Image to be RGBA mode.
    # (The fast path for byte-identical images uses .paste() and is lenient,
    # which is why this only surfaces when actual ≠ baseline.)
    diff = Image.new("RGBA", baseline.size)
    diff_pixels = pixelmatch(baseline, actual, diff, threshold=0.1)
    diff_path = DIFFS_DIR / f"{name}_{color_scheme}_diff.png"
    diff.save(diff_path)

    if diff_pixels > DIFF_THRESHOLD_PIXELS:
        raise AssertionError(
            f"Visual regression for {name}_{color_scheme}: "
            f"{diff_pixels} pixels differ (threshold {DIFF_THRESHOLD_PIXELS}). "
            f"Inspect: {diff_path}"
        )
