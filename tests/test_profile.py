import json
from pathlib import Path

import pytest

from deckforge.profile import CardLayout, DeckProfile, GridGeometry, ProfileError, load_profile


def base_profile_dict(**overrides) -> dict:
    """Minimal valid LEGACY profile payload (all required keys, no
    optional back_* overrides, no 'layouts'). Individual tests
    overlay/override fields."""
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


def layout_dict(**overrides) -> dict:
    """Minimal valid entry for a 'layouts' list."""
    data = {
        "first_page": 2,
        "last_page": 4,
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
    }
    data.update(overrides)
    return data


def layouts_profile_dict(layouts: list[dict], **overrides) -> dict:
    """Minimal valid LAYOUTS-mode profile payload."""
    data = {
        "pdf_file": "deck.pdf",
        "back_page": 99,
        "render_scale": 4,
        "trim_left": 1.0,
        "trim_right": 1.0,
        "trim_top": 1.0,
        "trim_bottom": 1.0,
        "layouts": layouts,
    }
    data.update(overrides)
    return data


def write_profile(profiles_dir: Path, name: str, data: dict) -> None:
    profiles_dir.mkdir(parents=True, exist_ok=True)
    (profiles_dir / f"{name}.json").write_text(json.dumps(data))


class TestLoadProfileLegacy:
    def test_loads_valid_profile(self, tmp_path: Path) -> None:
        write_profile(tmp_path, "my_deck", base_profile_dict())
        profile = load_profile("my_deck", tmp_path)
        assert isinstance(profile, DeckProfile)
        assert profile.name == "my_deck"
        assert len(profile.layouts) == 1
        assert profile.layouts[0].rows == 2
        assert profile.layouts[0].cols == 2
        assert profile.layouts[0].card_width == 100.0
        assert profile.layouts[0].first_page == 2
        assert profile.layouts[0].last_page == 4
        assert profile.layouts[0].name is None
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

    def test_missing_common_key_raises(self, tmp_path: Path) -> None:
        data = base_profile_dict()
        del data["render_scale"]
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
        assert profile.layouts[0].rows == 2

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

    def test_neither_layouts_nor_legacy_fields_raises(self, tmp_path: Path) -> None:
        data = {
            "back_page": 5, "render_scale": 4,
            "trim_left": 1.0, "trim_right": 1.0, "trim_top": 1.0, "trim_bottom": 1.0,
        }
        write_profile(tmp_path, "my_deck", data)
        with pytest.raises(ProfileError, match="missing required keys"):
            load_profile("my_deck", tmp_path)


class TestBackGeometry:
    def test_front_geometry_matches_layout_fields(self, tmp_path: Path) -> None:
        write_profile(tmp_path, "my_deck", base_profile_dict())
        profile = load_profile("my_deck", tmp_path)
        geometry = profile.layouts[0].geometry()
        assert geometry == GridGeometry(
            left=10.0, top=20.0, card_width=100.0, card_height=150.0, gap_x=0.0, gap_y=0.0,
        )

    def test_back_geometry_falls_back_to_first_layout_when_unset(self, tmp_path: Path) -> None:
        write_profile(tmp_path, "my_deck", base_profile_dict())
        profile = load_profile("my_deck", tmp_path)
        assert profile.back_geometry() == profile.layouts[0].geometry()
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
        # front (layout) geometry is unaffected by back overrides
        assert profile.layouts[0].geometry() == GridGeometry(
            left=10.0, top=20.0, card_width=100.0, card_height=150.0, gap_x=0.0, gap_y=0.0,
        )
        assert profile.uses_back_override() is True

    def test_partial_back_override_falls_back_field_by_field(self, tmp_path: Path) -> None:
        data = base_profile_dict(back_card_width=90.0)
        write_profile(tmp_path, "my_deck", data)
        profile = load_profile("my_deck", tmp_path)
        back = profile.back_geometry()
        assert back.card_width == 90.0
        assert back.card_height == 150.0  # falls back to first-layout value
        assert back.left == 10.0  # falls back to first-layout value
        assert profile.uses_back_override() is True

    def test_back_trim_uses_top_level_trim_fields(self, tmp_path: Path) -> None:
        data = base_profile_dict(trim_left=3.0, trim_right=4.0, trim_top=5.0, trim_bottom=6.0)
        write_profile(tmp_path, "my_deck", data)
        profile = load_profile("my_deck", tmp_path)
        back_trim = profile.back_trim()
        assert (back_trim.left, back_trim.right, back_trim.top, back_trim.bottom) == (3.0, 4.0, 5.0, 6.0)
        # legacy mode: the same top-level trim also governs the (only) front layout
        front_trim = profile.layouts[0].trim()
        assert (front_trim.left, front_trim.right, front_trim.top, front_trim.bottom) == (3.0, 4.0, 5.0, 6.0)


class TestLoadProfileLayouts:
    def test_loads_single_layout(self, tmp_path: Path) -> None:
        data = layouts_profile_dict([layout_dict(name="Main deck")])
        write_profile(tmp_path, "my_deck", data)
        profile = load_profile("my_deck", tmp_path)
        assert len(profile.layouts) == 1
        assert profile.layouts[0].name == "Main deck"
        assert profile.layouts[0].first_page == 2
        assert profile.layouts[0].last_page == 4

    def test_loads_multiple_non_overlapping_layouts(self, tmp_path: Path) -> None:
        data = layouts_profile_dict([
            layout_dict(first_page=1, last_page=2, name="Main"),
            layout_dict(first_page=3, last_page=3, rows=1, cols=1, name="Boss"),
        ])
        write_profile(tmp_path, "my_deck", data)
        profile = load_profile("my_deck", tmp_path)
        assert [l.name for l in profile.layouts] == ["Main", "Boss"]
        # profile order is preserved
        assert profile.layouts[0].first_page == 1
        assert profile.layouts[1].first_page == 3

    def test_layout_name_is_optional(self, tmp_path: Path) -> None:
        data = layouts_profile_dict([layout_dict()])
        write_profile(tmp_path, "my_deck", data)
        profile = load_profile("my_deck", tmp_path)
        assert profile.layouts[0].name is None
        assert profile.layouts[0].display_name(0) == "layout 1"

    def test_empty_layouts_list_raises(self, tmp_path: Path) -> None:
        data = layouts_profile_dict([])
        write_profile(tmp_path, "my_deck", data)
        with pytest.raises(ProfileError, match="at least one layout"):
            load_profile("my_deck", tmp_path)

    def test_layouts_and_legacy_fields_together_raises(self, tmp_path: Path) -> None:
        data = layouts_profile_dict([layout_dict()])
        data["first_front_page"] = 2
        data["last_front_page"] = 4
        data["rows"] = 2
        data["cols"] = 2
        data["left"] = 0.0
        data["top"] = 0.0
        data["card_width"] = 10.0
        data["card_height"] = 10.0
        data["gap_x"] = 0.0
        data["gap_y"] = 0.0
        write_profile(tmp_path, "my_deck", data)
        with pytest.raises(ProfileError, match="has both 'layouts' and legacy"):
            load_profile("my_deck", tmp_path)

    def test_overlapping_layout_ranges_raise(self, tmp_path: Path) -> None:
        data = layouts_profile_dict([
            layout_dict(first_page=1, last_page=3),
            layout_dict(first_page=3, last_page=5),
        ])
        write_profile(tmp_path, "my_deck", data)
        with pytest.raises(ProfileError, match="overlapping layout page ranges"):
            load_profile("my_deck", tmp_path)

    def test_back_page_overlapping_a_layout_raises(self, tmp_path: Path) -> None:
        data = layouts_profile_dict([layout_dict(first_page=1, last_page=5)], back_page=3)
        write_profile(tmp_path, "my_deck", data)
        with pytest.raises(ProfileError, match="back_page.*overlap|overlap.*back_page"):
            load_profile("my_deck", tmp_path)

    def test_first_page_after_last_page_raises(self, tmp_path: Path) -> None:
        data = layouts_profile_dict([layout_dict(first_page=5, last_page=2)])
        write_profile(tmp_path, "my_deck", data)
        with pytest.raises(ProfileError, match="greater than last_page"):
            load_profile("my_deck", tmp_path)

    def test_layout_missing_required_key_raises(self, tmp_path: Path) -> None:
        bad_layout = layout_dict()
        del bad_layout["card_width"]
        data = layouts_profile_dict([bad_layout])
        write_profile(tmp_path, "my_deck", data)
        with pytest.raises(ProfileError, match="layout 1.*missing required keys"):
            load_profile("my_deck", tmp_path)

    def test_layout_unknown_key_raises(self, tmp_path: Path) -> None:
        data = layouts_profile_dict([layout_dict(bogus_field=123)])
        write_profile(tmp_path, "my_deck", data)
        with pytest.raises(ProfileError, match="layout 1.*unrecognized keys"):
            load_profile("my_deck", tmp_path)

    def test_layout_underscore_keys_are_comments(self, tmp_path: Path) -> None:
        data = layouts_profile_dict([layout_dict(_comment="note")])
        write_profile(tmp_path, "my_deck", data)
        profile = load_profile("my_deck", tmp_path)
        assert profile.layouts[0].rows == 2

    def test_layout_zero_card_size_raises(self, tmp_path: Path) -> None:
        data = layouts_profile_dict([layout_dict(card_width=0)])
        write_profile(tmp_path, "my_deck", data)
        with pytest.raises(ProfileError, match="hasn't been.*calibrated|positive point values"):
            load_profile("my_deck", tmp_path)

    def test_layouts_must_be_a_list(self, tmp_path: Path) -> None:
        data = layouts_profile_dict(layout_dict())  # dict, not a list
        write_profile(tmp_path, "my_deck", data)
        with pytest.raises(ProfileError, match="at least one layout"):
            load_profile("my_deck", tmp_path)

    def test_each_layout_owns_its_own_trim(self, tmp_path: Path) -> None:
        data = layouts_profile_dict([
            layout_dict(first_page=1, last_page=1, trim_left=9.0, trim_right=9.0, trim_top=9.0, trim_bottom=9.0),
            layout_dict(first_page=2, last_page=2, trim_left=1.0, trim_right=1.0, trim_top=1.0, trim_bottom=1.0),
        ], trim_left=0.0, trim_right=0.0, trim_top=0.0, trim_bottom=0.0)
        write_profile(tmp_path, "my_deck", data)
        profile = load_profile("my_deck", tmp_path)
        assert profile.layouts[0].trim().left == 9.0
        assert profile.layouts[1].trim().left == 1.0
        # the top-level trim (0.0) is separate -- it governs the back page only
        assert profile.back_trim().left == 0.0

    def test_layouts_mode_processed_in_profile_order(self, tmp_path: Path) -> None:
        data = layouts_profile_dict([
            layout_dict(first_page=5, last_page=6, name="Second in file, later pages"),
            layout_dict(first_page=1, last_page=2, name="First in file, earlier pages"),
        ])
        write_profile(tmp_path, "my_deck", data)
        profile = load_profile("my_deck", tmp_path)
        # profile (JSON list) order is preserved, not sorted by page number
        assert [l.name for l in profile.layouts] == [
            "Second in file, later pages", "First in file, earlier pages",
        ]


class TestLayoutForPage:
    def test_resolves_page_within_a_layout(self, tmp_path: Path) -> None:
        data = layouts_profile_dict([
            layout_dict(first_page=1, last_page=2, name="Main"),
            layout_dict(first_page=3, last_page=3, name="Boss"),
        ])
        write_profile(tmp_path, "my_deck", data)
        profile = load_profile("my_deck", tmp_path)
        assert profile.layout_for_page(1).name == "Main"
        assert profile.layout_for_page(2).name == "Main"
        assert profile.layout_for_page(3).name == "Boss"

    def test_unassigned_page_returns_none(self, tmp_path: Path) -> None:
        data = layouts_profile_dict([layout_dict(first_page=1, last_page=2)])
        write_profile(tmp_path, "my_deck", data)
        profile = load_profile("my_deck", tmp_path)
        assert profile.layout_for_page(99) is None


class TestCardLayout:
    def test_card_count(self) -> None:
        layout = CardLayout(
            first_page=1, last_page=3, rows=2, cols=3,
            left=0, top=0, card_width=1, card_height=1, gap_x=0, gap_y=0,
            trim_left=0, trim_right=0, trim_top=0, trim_bottom=0,
        )
        assert layout.card_count() == 3 * 2 * 3  # 3 pages x 6 cards/page
