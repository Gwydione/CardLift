from collections import Counter
from pathlib import Path

from deckforge.cell_export import export_cells
from deckforge.cropper import CardCropper
from deckforge.pdf_renderer import PDFRenderer
from deckforge.profile import GridGeometry, TrimValues

SAMPLE_PDF = Path(__file__).resolve().parent.parent / "sample_decks" / "Solo-cards-digital.pdf"

# Real, --preview-verified geometry from profiles/solo_cards.json, minus
# trim (cell_export.py always crops at zero trim -- see its module
# docstring), so tests exercise real page/card dimensions rather than
# synthetic numbers.
FRONT_GEOMETRY = GridGeometry(
    left=35.75, top=61.25, card_width=174.58, card_height=239.75, gap_x=0.0, gap_y=0.0,
)
BACK_GEOMETRY = GridGeometry(
    left=46.0, top=71.75, card_width=153.62, card_height=218.75, gap_x=21.0, gap_y=21.0,
)
BACK_PAGE = 8
RENDER_SCALE = 1.0
_ZERO_TRIM = TrimValues(0.0, 0.0, 0.0, 0.0)


class _CountingRenderer:
    """Wraps a real PDFRenderer, recording every render_page() call so
    tests can assert a page was only rendered once even when requested
    cells arrive out of page order."""

    def __init__(self, real: PDFRenderer) -> None:
        self._real = real
        self.calls: list[int] = []

    def render_page(self, page_number: int, scale: float):
        self.calls.append(page_number)
        return self._real.render_page(page_number, scale)


class TestExportCellsOrderingAndNumbering:
    def test_output_count_matches_cell_count(self, tmp_path: Path) -> None:
        cells = [(2, 0, 0), (2, 0, 1), (3, 1, 2)]
        with PDFRenderer(SAMPLE_PDF) as renderer:
            written = export_cells(renderer, RENDER_SCALE, FRONT_GEOMETRY, cells, tmp_path)
        assert [p.name for p in written] == ["front_001.png", "front_002.png", "front_003.png"]
        assert all(p.exists() for p in written)

    def test_numbering_follows_caller_order_not_page_or_grid_order(self, tmp_path: Path) -> None:
        # Deliberately out of page order (page 3 before page 2) and out of
        # row-major order within page 2 -- front_NNN numbering must track
        # this exact sequence, not re-sort it.
        cells = [(3, 0, 0), (2, 1, 1), (2, 0, 0)]
        with PDFRenderer(SAMPLE_PDF) as renderer:
            written = export_cells(renderer, RENDER_SCALE, FRONT_GEOMETRY, cells, tmp_path)

        with PDFRenderer(SAMPLE_PDF) as renderer:
            cropper = CardCropper(RENDER_SCALE)
            expected_first = cropper.crop_card(
                renderer.render_page(3, RENDER_SCALE), FRONT_GEOMETRY, _ZERO_TRIM, 0, 0,
            )
            actual_first = _open(written[0])
            assert expected_first.tobytes() == actual_first.tobytes()

    def test_crops_the_exact_requested_cell(self, tmp_path: Path) -> None:
        # front_001.png for cell (2, 1, 2) must be pixel-identical to a
        # direct CardCropper crop of that same cell -- not some other
        # cell, and not silently re-including a neighbor.
        with PDFRenderer(SAMPLE_PDF) as renderer:
            written = export_cells(renderer, RENDER_SCALE, FRONT_GEOMETRY, [(2, 1, 2)], tmp_path)

        with PDFRenderer(SAMPLE_PDF) as renderer:
            cropper = CardCropper(RENDER_SCALE)
            expected = cropper.crop_card(
                renderer.render_page(2, RENDER_SCALE), FRONT_GEOMETRY, _ZERO_TRIM, 1, 2,
            )
        actual = _open(written[0])
        assert expected.tobytes() == actual.tobytes()


class TestBackHandling:
    def test_back_omitted_writes_no_back_file(self, tmp_path: Path) -> None:
        with PDFRenderer(SAMPLE_PDF) as renderer:
            written = export_cells(renderer, RENDER_SCALE, FRONT_GEOMETRY, [(2, 0, 0)], tmp_path)
        assert not (tmp_path / "back.png").exists()
        assert "back.png" not in [p.name for p in written]

    def test_back_given_writes_back_file_last(self, tmp_path: Path) -> None:
        with PDFRenderer(SAMPLE_PDF) as renderer:
            written = export_cells(
                renderer, RENDER_SCALE, FRONT_GEOMETRY, [(2, 0, 0)], tmp_path,
                back=(BACK_PAGE, BACK_GEOMETRY),
            )
        assert (tmp_path / "back.png").exists()
        assert written[-1].name == "back.png"

    def test_empty_cells_with_back_only(self, tmp_path: Path) -> None:
        with PDFRenderer(SAMPLE_PDF) as renderer:
            written = export_cells(
                renderer, RENDER_SCALE, FRONT_GEOMETRY, [], tmp_path,
                back=(BACK_PAGE, BACK_GEOMETRY),
            )
        assert [p.name for p in written] == ["back.png"]


class TestPageRenderCaching:
    def test_each_distinct_page_rendered_at_most_once(self, tmp_path: Path) -> None:
        # Interleaved, non-page-grouped cells across pages 2 and 3, plus a
        # back on page 8 -- each page number must still only be rendered
        # once (see cell_export.export_cells()'s internal page cache).
        cells = [(2, 0, 0), (3, 0, 0), (2, 0, 1), (3, 0, 1), (2, 0, 2)]
        with PDFRenderer(SAMPLE_PDF) as real:
            counting = _CountingRenderer(real)
            export_cells(
                counting, RENDER_SCALE, FRONT_GEOMETRY, cells, tmp_path,
                back=(BACK_PAGE, BACK_GEOMETRY),
            )
        assert Counter(counting.calls) == Counter({2: 1, 3: 1, 8: 1})


class TestOutputDirectory:
    def test_creates_missing_output_directory(self, tmp_path: Path) -> None:
        target = tmp_path / "nested" / "export"
        assert not target.exists()
        with PDFRenderer(SAMPLE_PDF) as renderer:
            export_cells(renderer, RENDER_SCALE, FRONT_GEOMETRY, [(2, 0, 0)], target)
        assert target.exists()
        assert (target / "front_001.png").exists()


def _open(path: Path):
    from PIL import Image
    return Image.open(path)
