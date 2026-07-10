import json
from pathlib import Path

import pytest

from deckforge.profile import DeckProfile, GridGeometry, ProfileError, load_profile


def base_profile_dict(**overrides) -> dict:
    """Minimal valid profile payload (all required keys, no optional
    back_* overrides). Individual tests overlay/override fields."""
    data = {
        "pdf_file": "deck.pdf",
        "first_front_page": 2,
        "last_front_page": 4,
        "back_page": 5,
        "rows": 2,
        "cols": 2,
        "left": 10.0,
        "top": 20.0,
        "card_width": 100.0,
        "card_height": 150.0,
        "gap_x": 0.0,
        "gap_y": 0.0,
        "trim_left": 1.0,
        "trim_right": 1.0,
        "trim_top": 1.0,
        "trim_bottom": 1.0,
        "render_scale": 4,
    }
    data.update(overrides)
    return data


def write_profile(profiles_dir: Path, name: str, data: dict) -> None:
    profiles_dir.mkdir(parents=True, exist_ok=True)
    (profiles_dir / f"{name}.json").write_text(json.dumps(data))


class TestLoadProfile:
    def test_loads_valid_profile(self, tmp_path: Path) -> None:
        write_profile(tmp_path, "my_deck", base_profile_dict())
        profile = load_profile("my_deck", tmp_path)
        assert isinstance(profile, DeckProfile)
        assert profile.name == "my_deck"
        assert profile.rows == 2
        assert profile.cols == 2
        assert profile.card_width == 100.0
        assert profile.render_scale == 4

    def test_missing_profile_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ProfileError, match="not found"):
            load_profile("does_not_exist", tmp_path)

    def test_missing_required_key_raises(self, tmp_path: Path) -> None:
        data = base_profile_dict()
        del data["card_width"]
        write_profile(tmp_path, "my_deck", data)
        with pytest.raises(ProfileError, match="missing required keys"):
            load_profile("my_deck", tmp_path)

    def test_unknown_key_raises(self, tmp_path: Path) -> None:
        data = base_profile_dict(bogus_field=123)
        write_profile(tmp_path, "my_deck", data)
        with pytest.raises(ProfileError, match="unrecognized keys"):
            load_profile("my_deck", tmp_path)

    def test_underscore_prefixed_keys_are_treated_as_comments(self, tmp_path: Path) -> None:
        data = base_profile_dict(_comment="not a real field")
        write_profile(tmp_path, "my_deck", data)
        profile = load_profile("my_deck", tmp_path)
        assert profile.rows == 2

    @pytest.mark.parametrize("field", ["card_width", "card_height"])
    def test_zero_card_size_raises(self, tmp_path: Path, field: str) -> None:
        data = base_profile_dict(**{field: 0})
        write_profile(tmp_path, "my_deck", data)
        with pytest.raises(ProfileError, match="hasn't been.*calibrated|positive point values"):
            load_profile("my_deck", tmp_path)

    @pytest.mark.parametrize("field", ["card_width", "card_height"])
    def test_negative_card_size_raises(self, tmp_path: Path, field: str) -> None:
        data = base_profile_dict(**{field: -5})
        write_profile(tmp_path, "my_deck", data)
        with pytest.raises(ProfileError):
            load_profile("my_deck", tmp_path)

    def test_malformed_json_raises_profile_error(self, tmp_path: Path) -> None:
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "my_deck.json").write_text('{"rows": 2, "cols": 2,}')  # trailing comma
        with pytest.raises(ProfileError, match="not valid JSON"):
            load_profile("my_deck", tmp_path)

    def test_pdf_file_is_optional(self, tmp_path: Path) -> None:
        data = base_profile_dict()
        del data["pdf_file"]
        write_profile(tmp_path, "my_deck", data)
        profile = load_profile("my_deck", tmp_path)
        assert profile.pdf_file is None


class TestBackGeometry:
    def test_front_geometry_matches_front_fields(self, tmp_path: Path) -> None:
        write_profile(tmp_path, "my_deck", base_profile_dict())
        profile = load_profile("my_deck", tmp_path)
        geometry = profile.front_geometry()
        assert geometry == GridGeometry(
            left=10.0, top=20.0, card_width=100.0, card_height=150.0, gap_x=0.0, gap_y=0.0,
        )

    def test_back_geometry_falls_back_to_front_when_unset(self, tmp_path: Path) -> None:
        write_profile(tmp_path, "my_deck", base_profile_dict())
        profile = load_profile("my_deck", tmp_path)
        assert profile.back_geometry() == profile.front_geometry()
        assert profile.uses_back_override() is False

    def test_back_geometry_uses_overrides_when_set(self, tmp_path: Path) -> None:
        data = base_profile_dict(
            back_left=46.0,
            back_top=71.75,
            back_card_width=153.62,
            back_card_height=218.75,
            back_gap_x=21.0,
            back_gap_y=21.0,
        )
        write_profile(tmp_path, "my_deck", data)
        profile = load_profile("my_deck", tmp_path)
        assert profile.back_geometry() == GridGeometry(
            left=46.0, top=71.75, card_width=153.62, card_height=218.75, gap_x=21.0, gap_y=21.0,
        )
        # front geometry is unaffected by back overrides
        assert profile.front_geometry() == GridGeometry(
            left=10.0, top=20.0, card_width=100.0, card_height=150.0, gap_x=0.0, gap_y=0.0,
        )
        assert profile.uses_back_override() is True

    def test_partial_back_override_falls_back_field_by_field(self, tmp_path: Path) -> None:
        data = base_profile_dict(back_card_width=90.0)
        write_profile(tmp_path, "my_deck", data)
        profile = load_profile("my_deck", tmp_path)
        back = profile.back_geometry()
        assert back.card_width == 90.0
        assert back.card_height == 150.0  # falls back to front value
        assert back.left == 10.0  # falls back to front value
        assert profile.uses_back_override() is True
