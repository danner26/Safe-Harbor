"""Tank form validation tests."""

from __future__ import annotations

import pytest
from werkzeug.datastructures import MultiDict

from safeharbor.blueprints.tanks.forms import TankForm
from safeharbor.models.tank import PROFILE_WATER_TYPES


def _form_data(*, water_type: str, profile_key: str) -> MultiDict[str, str]:
    return MultiDict(
        {
            "name": "Validation Tank",
            "water_type": water_type,
            "profile_key": profile_key,
            "volume": "",
            "volume_unit": "L",
            "setup_date": "",
            "substrate": "",
            "equipment_notes": "",
            "timezone": "UTC",
        }
    )


@pytest.mark.parametrize(
    ("profile_key", "water_type"),
    list(PROFILE_WATER_TYPES.items()),
)
def test_tank_form_accepts_profiles_for_their_water_type(
    app,
    profile_key: str,
    water_type: str,
) -> None:
    with app.test_request_context(method="POST"):
        form = TankForm(formdata=_form_data(water_type=water_type, profile_key=profile_key))

        assert form.validate() is True


@pytest.mark.parametrize(
    ("water_type", "profile_key"),
    [
        ("fresh", "reef_sw"),
        ("salt", "coldwater_fw"),
        ("brackish", "planted_fw"),
    ],
)
def test_tank_form_rejects_profiles_for_other_water_types(
    app,
    water_type: str,
    profile_key: str,
) -> None:
    with app.test_request_context(method="POST"):
        form = TankForm(formdata=_form_data(water_type=water_type, profile_key=profile_key))

        assert form.validate() is False
        assert (
            f"Profile {profile_key!r} is not valid for {water_type!r} tanks."
            in form.profile_key.errors
        )
