from pathlib import Path

import pytest

from deckforge.exporter import DeckExporter, DeckForgePaths, ExportError
from deckforge.profile import CardLayout, DeckProfile


def make_layout(**overrides) -> CardLayout:
    data = dict(
        first_page=2, last_page=3, rows=2, cols=2,
        left=0.0, top=0.0, card_width=100.0, card_height=150.0, gap_x=0.0, gap_y=0.0,
        trim_left=0.0, trim_right=0.0, trim_top=0.0, trim_bottom=0.0,
        name=None,
    )
    data.update(overrides)
    return CardLayout(**data)


def make_profile(layouts: list[CardLayout], back_page: int = 99, **overrides) -> DeckProfile:
    data = dict(
        name="test_deck", pdf_file="deck.pdf", layouts=layouts, back_page=back_page,
        render_scale=4.0, trim_left=0.0, trim_right=0.0, trim_top=0.0, trim_bottom=0.0,
    )
    data.update(overrides)
    return DeckProfile(**data)


def make_exporter(profile: DeckProfile, tmp_path: Path) -> DeckExporter:
    return DeckExporter(profile, DeckForgePaths.from_project_root(tmp_path))


class TestCardNumberForSingleLayout:
    def test_numbers_are_continuous_row_major_within_a_page(self, tmp_path: Path) -> None:
        layout = make_layout(first_page=2, last_page=2, rows=2, cols=2)
        exporter = make_exporter(make_profile([layout]), tmp_path)
        assert exporter._card_number_for(2, 0, 0) == 1
        assert exporter._card_number_for(2, 0, 1) == 2
        assert exporter._card_number_for(2, 1, 0) == 3
        assert exporter._card_number_for(2, 1, 1) == 4

    def test_numbers_continue_across_pages_ascending(self, tmp_path: Path) -> None:
        layout = make_layout(first_page=2, last_page=3, rows=2, cols=2)
        exporter = make_exporter(make_profile([layout]), tmp_path)
        assert exporter._card_number_for(2, 1, 1) == 4  # last card of page 2
        assert exporter._card_number_for(3, 0, 0) == 5  # first card of page 3

    def test_page_outside_layout_returns_none(self, tmp_path: Path) -> None:
        layout = make_layout(first_page=2, last_page=3)
        exporter = make_exporter(make_profile([layout]), tmp_path)
        assert exporter._card_number_for(99, 0, 0) is None


class TestCardNumberForMultipleLayouts:
    def test_numbers_are_continuous_across_layouts_in_profile_order(self, tmp_path: Path) -> None:
        main = make_layout(first_page=1, last_page=1, rows=2, cols=2, name="Main")  # 4 cards
        boss = make_layout(first_page=5, last_page=5, rows=1, cols=1, name="Boss")  # 1 card
        exporter = make_exporter(make_profile([main, boss]), tmp_path)
        assert exporter._card_number_for(1, 0, 0) == 1
        assert exporter._card_number_for(1, 1, 1) == 4
        assert exporter._card_number_for(5, 0, 0) == 5  # continues after main layout's 4 cards

    def test_numbering_follows_profile_order_not_page_order(self, tmp_path: Path) -> None:
        # "later" layout (by page number) listed FIRST in the profile
        later = make_layout(first_page=10, last_page=10, rows=1, cols=1, name="Later pages")
        earlier = make_layout(first_page=1, last_page=1, rows=1, cols=1, name="Earlier pages")
        exporter = make_exporter(make_profile([later, earlier]), tmp_path)
        # profile order wins: page 10 (first in profile) gets card #1
        assert exporter._card_number_for(10, 0, 0) == 1
        assert exporter._card_number_for(1, 0, 0) == 2


class TestLocateCard:
    def test_locates_card_within_single_layout(self, tmp_path: Path) -> None:
        layout = make_layout(first_page=2, last_page=3, rows=2, cols=2)
        exporter = make_exporter(make_profile([layout]), tmp_path)
        found_layout, page_num, row, col = exporter._locate_card(5)
        assert found_layout is layout
        assert (page_num, row, col) == (3, 0, 0)

    def test_locates_card_in_second_layout(self, tmp_path: Path) -> None:
        main = make_layout(first_page=1, last_page=1, rows=2, cols=2, name="Main")
        boss = make_layout(first_page=5, last_page=5, rows=1, cols=1, name="Boss")
        exporter = make_exporter(make_profile([main, boss]), tmp_path)
        found_layout, page_num, row, col = exporter._locate_card(5)
        assert found_layout is boss
        assert (page_num, row, col) == (5, 0, 0)

    def test_out_of_range_raises_friendly_error(self, tmp_path: Path) -> None:
        layout = make_layout(first_page=2, last_page=2, rows=2, cols=2)
        exporter = make_exporter(make_profile([layout]), tmp_path)
        with pytest.raises(ExportError, match="out of range"):
            exporter._locate_card(999)
        with pytest.raises(ExportError, match="out of range"):
            exporter._locate_card(0)


class TestResolvePage:
    def test_resolves_front_page_to_its_layout(self, tmp_path: Path) -> None:
        layout = make_layout(first_page=2, last_page=3, rows=3, cols=3)
        exporter = make_exporter(make_profile([layout], back_page=4), tmp_path)
        resolution = exporter.resolve_page(2)
        assert resolution.is_back is False
        assert resolution.layout is layout
        assert resolution.rows == 3 and resolution.cols == 3
        assert resolution.label == "front grid, page 2"

    def test_resolves_back_page(self, tmp_path: Path) -> None:
        layout = make_layout(first_page=2, last_page=3)
        exporter = make_exporter(make_profile([layout], back_page=4), tmp_path)
        resolution = exporter.resolve_page(4)
        assert resolution.is_back is True
        assert resolution.layout is None
        assert resolution.label == "back grid, page 4"

    def test_back_page_grid_shape_falls_back_to_first_layout(self, tmp_path: Path) -> None:
        layout = make_layout(first_page=2, last_page=3, rows=5, cols=6)
        exporter = make_exporter(make_profile([layout], back_page=4), tmp_path)
        resolution = exporter.resolve_page(4)
        assert (resolution.rows, resolution.cols) == (5, 6)

    def test_unassigned_page_raises_friendly_error(self, tmp_path: Path) -> None:
        layout = make_layout(first_page=2, last_page=3)
        exporter = make_exporter(make_profile([layout], back_page=4), tmp_path)
        with pytest.raises(ExportError, match="is not assigned to any layout"):
            exporter.resolve_page(99)

    def test_multi_layout_label_identifies_the_selected_layout(self, tmp_path: Path) -> None:
        main = make_layout(first_page=1, last_page=1, name="Main")
        boss = make_layout(first_page=5, last_page=5, name="Boss")
        exporter = make_exporter(make_profile([main, boss], back_page=9), tmp_path)
        assert exporter.resolve_page(1).label == "front grid (Main), page 1"
        assert exporter.resolve_page(5).label == "front grid (Boss), page 5"

    def test_multi_layout_without_names_uses_positional_label(self, tmp_path: Path) -> None:
        first = make_layout(first_page=1, last_page=1)
        second = make_layout(first_page=5, last_page=5)
        exporter = make_exporter(make_profile([first, second], back_page=9), tmp_path)
        assert exporter.resolve_page(1).label == "front grid (layout 1), page 1"
        assert exporter.resolve_page(5).label == "front grid (layout 2), page 5"

    def test_single_layout_label_is_unchanged_from_legacy_wording(self, tmp_path: Path) -> None:
        layout = make_layout(first_page=2, last_page=3, name="Only layout")
        exporter = make_exporter(make_profile([layout], back_page=4), tmp_path)
        # even a named single layout keeps the old plain "front grid" wording
        assert exporter.resolve_page(2).label == "front grid, page 2"
