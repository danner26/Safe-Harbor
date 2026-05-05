"""Visual regression smoke: 4 baselines (home + styleguide, light + dark)."""

from __future__ import annotations

from playwright.sync_api import Page

from tests.visual.conftest import BASE_URL, assert_screenshot_matches_baseline


def _login_via_fixture(page: Page) -> None:
    """Authenticate via the dev_bp test fixture so the home dashboard renders.

    Phase 1b adds login-required-by-default; without this hop, hitting / as
    anonymous redirects to /login and we'd be screenshotting that instead."""
    page.goto(f"{BASE_URL}/__test/visual-fixtures/login-as-admin")
    page.wait_for_url("**/admin/invites", timeout=5_000)


def _seed_home_dashboard(page: Page) -> None:
    """Seed the data-bearing dashboard state expected by home baselines."""
    page.goto(f"{BASE_URL}/__test/visual-fixtures/seed-home-dashboard")
    page.wait_for_load_state("networkidle")
    assert page.url.rstrip("/") == BASE_URL


def _stabilize_recorded_at(page: Page) -> None:
    """Keep datetime-local fields stable across the screenshot helper's reload."""
    page.add_init_script(
        """
        window.addEventListener("DOMContentLoaded", () => {
          const recordedAt = document.querySelector("#recorded_at");
          if (recordedAt) recordedAt.value = "2026-04-15T12:00";
        });
        """
    )


def test_home_light(page: Page) -> None:
    _seed_home_dashboard(page)
    assert_screenshot_matches_baseline(page, "home", "light")


def test_home_dark(page: Page) -> None:
    _seed_home_dashboard(page)
    assert_screenshot_matches_baseline(page, "home", "dark")


def test_styleguide_light(page: Page) -> None:
    page.goto(f"{BASE_URL}/dev/styleguide")
    assert_screenshot_matches_baseline(page, "styleguide", "light")


def test_styleguide_dark(page: Page) -> None:
    page.goto(f"{BASE_URL}/dev/styleguide")
    assert_screenshot_matches_baseline(page, "styleguide", "dark")


def test_login_light(page: Page) -> None:
    page.goto(f"{BASE_URL}/login")
    assert_screenshot_matches_baseline(page, "login", "light")


def test_register_light(page: Page) -> None:
    # We need a valid token to render the form. The visual job's seed has an
    # admin + a fresh invite for "visual-fixture@x.com"; the conftest fixture
    # below produces it on first request via a /__test/visual-fixtures helper
    # endpoint that's gated on app.testing only.
    page.goto(f"{BASE_URL}/__test/visual-fixtures/invite-link")
    page.wait_for_url("**/register/**", timeout=5_000)
    assert_screenshot_matches_baseline(page, "register", "light")


def test_invites_list_light(page: Page) -> None:
    # Log in as the seeded admin via a test helper that sets the session cookie.
    page.goto(f"{BASE_URL}/__test/visual-fixtures/login-as-admin")
    page.wait_for_url("**/admin/invites", timeout=5_000)
    assert_screenshot_matches_baseline(page, "invites_list", "light")


def test_tanks_list_light(page: Page) -> None:
    page.goto(f"{BASE_URL}/__test/visual-fixtures/seed-tanks")
    page.wait_for_url("**/tanks", timeout=5_000)
    for label in ("Nominal", "Watch", "Action needed"):
        assert page.get_by_text(label).count() >= 1
    assert_screenshot_matches_baseline(page, "tanks_list", "light")


def test_tank_detail_light(page: Page) -> None:
    page.goto(f"{BASE_URL}/__test/visual-fixtures/seed-tank-detail")
    page.wait_for_url("**/tanks/**", timeout=5_000)
    assert_screenshot_matches_baseline(page, "tank_detail", "light")


def test_tank_detail_with_photo_light(page: Page) -> None:
    page.goto(f"{BASE_URL}/__test/visual-fixtures/seed-tank-with-photo")
    page.wait_for_url("**/tanks/**", timeout=5_000)
    assert_screenshot_matches_baseline(page, "tank_detail_with_photo", "light")


def test_animals_list_light(page: Page) -> None:
    page.goto(f"{BASE_URL}/__test/visual-fixtures/seed-animals-list")
    page.wait_for_url("**/animals", timeout=5_000)
    assert_screenshot_matches_baseline(page, "animals_list", "light")


def test_animal_detail_light(page: Page) -> None:
    page.goto(f"{BASE_URL}/__test/visual-fixtures/seed-animal-detail")
    page.wait_for_url("**/animals/**", timeout=5_000)
    assert_screenshot_matches_baseline(page, "animal_detail", "light")


def test_animal_detail_with_photo_light(page: Page) -> None:
    page.goto(f"{BASE_URL}/__test/visual-fixtures/seed-animal-with-photo")
    page.wait_for_url("**/animals/**", timeout=5_000)
    assert_screenshot_matches_baseline(page, "animal_detail_with_photo", "light")


def test_settings_account_light(page: Page) -> None:
    _login_via_fixture(page)
    page.goto(f"{BASE_URL}/settings/account")
    assert_screenshot_matches_baseline(page, "settings_account", "light")


def test_settings_display_light(page: Page) -> None:
    _login_via_fixture(page)
    page.goto(f"{BASE_URL}/settings/display")
    assert_screenshot_matches_baseline(page, "settings_display", "light")


def test_settings_system_admin_light(page: Page) -> None:
    page.goto(f"{BASE_URL}/__test/visual-fixtures/seed-settings-system-admin")
    page.wait_for_url("**/settings/system", timeout=5_000)
    assert_screenshot_matches_baseline(page, "settings_system_admin", "light")


def test_quick_add_light(page: Page) -> None:
    _stabilize_recorded_at(page)
    page.goto(f"{BASE_URL}/__test/visual-fixtures/seed-quick-add")
    page.wait_for_url("**/measurements/quick-add**", timeout=5_000)
    assert_screenshot_matches_baseline(page, "quick_add", "light")


def test_batch_entry_light(page: Page) -> None:
    _stabilize_recorded_at(page)
    page.goto(f"{BASE_URL}/__test/visual-fixtures/seed-batch-entry")
    page.wait_for_url("**/measurements/batch**", timeout=5_000)
    assert_screenshot_matches_baseline(page, "batch_entry", "light")


def test_measurements_history_light(page: Page) -> None:
    page.goto(f"{BASE_URL}/__test/visual-fixtures/seed-history-with-data")
    page.wait_for_url("**/tanks/**/history", timeout=5_000)
    assert_screenshot_matches_baseline(page, "measurements_history", "light")


def test_history_with_badges_and_attribution_light(page: Page) -> None:
    page.goto(f"{BASE_URL}/__test/visual-fixtures/seed-history-with-badges-and-attribution")
    page.wait_for_url("**/tanks/**/history", timeout=5_000)
    assert_screenshot_matches_baseline(page, "history_with_badges_and_attribution", "light")


def test_measurement_edit_light(page: Page) -> None:
    _stabilize_recorded_at(page)
    page.goto(f"{BASE_URL}/__test/visual-fixtures/seed-measurement-edit")
    page.wait_for_url("**/measurements/**/edit", timeout=5_000)
    assert_screenshot_matches_baseline(page, "measurement_edit", "light")
