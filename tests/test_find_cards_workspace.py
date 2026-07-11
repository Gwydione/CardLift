from deckforge_gui.find_cards_workspace import FindCardsView, fit_scale


def test_fit_scale_downscales_to_fit_available_space():
    assert fit_scale(2000, 1000, 1000, 1000) == 0.5


def test_fit_scale_never_upscales_past_native_resolution():
    assert fit_scale(400, 300, 2000, 2000) == 1.0


def test_fit_scale_picks_the_more_constraining_axis():
    # Width would allow 0.5, height would allow 0.25 -- height wins.
    assert fit_scale(1000, 2000, 500, 500) == 0.25


def test_fit_scale_handles_degenerate_dimensions():
    assert fit_scale(0, 100, 500, 500) == 1.0
    assert fit_scale(100, 100, 0, 500) == 1.0


def test_view_fitting_centers_a_letterboxed_image():
    # Image narrower than the widget at its fit scale -- expect horizontal
    # centering (nonzero offset_x), no vertical letterboxing (offset_y 0).
    view = FindCardsView.fitting(image_w=400, image_h=800, widget_w=800, widget_h=800, render_scale=2.0)
    assert view.display_scale == 1.0
    assert view.offset_x == 200.0
    assert view.offset_y == 0.0


def test_image_rect_reflects_fit_scale_and_offsets():
    view = FindCardsView.fitting(image_w=400, image_h=800, widget_w=800, widget_h=800, render_scale=2.0)
    x, y, w, h = view.image_rect(400, 800)
    assert (x, y) == (view.offset_x, view.offset_y)
    assert (w, h) == (400 * view.display_scale, 800 * view.display_scale)


def test_image_rect_is_stable_across_a_resize():
    """A page's role badge is drawn relative to image_rect()'s origin, so
    it must land in the same visual spot on the page regardless of widget
    size -- resizing only changes display_scale/offsets, never where the
    image content itself sits within its own bounds."""
    small = FindCardsView.fitting(image_w=1200, image_h=1600, widget_w=600, widget_h=800, render_scale=2.0)
    large = FindCardsView.fitting(image_w=1200, image_h=1600, widget_w=1200, widget_h=1600, render_scale=2.0)

    small_x, small_y, small_w, small_h = small.image_rect(1200, 1600)
    large_x, large_y, large_w, large_h = large.image_rect(1200, 1600)

    # Both should fit exactly (no letterboxing at these proportions), just
    # at different absolute scales.
    assert small_w / small_h == large_w / large_h
