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


def test_point_to_widget_and_back_round_trips():
    view = FindCardsView.fitting(image_w=1200, image_h=1600, widget_w=600, widget_h=600, render_scale=2.0)
    x_pt, y_pt = 150.25, 300.5
    wx, wy = view.point_to_widget(x_pt, y_pt)
    back_x, back_y = view.widget_to_point(wx, wy)
    assert back_x == x_pt
    assert back_y == y_pt


def test_point_to_widget_is_stable_across_a_resize():
    """The same stored PDF-point marker must land on the same visual spot
    on the page relative to its content, independent of widget size --
    resizing only changes display_scale/offsets, never the stored point."""
    small = FindCardsView.fitting(image_w=1200, image_h=1600, widget_w=600, widget_h=800, render_scale=2.0)
    large = FindCardsView.fitting(image_w=1200, image_h=1600, widget_w=1200, widget_h=1600, render_scale=2.0)

    x_pt, y_pt = 100.0, 200.0
    small_wx, small_wy = small.point_to_widget(x_pt, y_pt)
    large_wx, large_wy = large.point_to_widget(x_pt, y_pt)

    # Fraction of the way across the *displayed image* should match at any
    # widget size, even though the raw widget-pixel position differs.
    small_frac_x = (small_wx - small.offset_x) / (1200 * small.display_scale)
    large_frac_x = (large_wx - large.offset_x) / (1200 * large.display_scale)
    assert round(small_frac_x, 6) == round(large_frac_x, 6)

    small_frac_y = (small_wy - small.offset_y) / (1600 * small.display_scale)
    large_frac_y = (large_wy - large.offset_y) / (1600 * large.display_scale)
    assert round(small_frac_y, 6) == round(large_frac_y, 6)

    # And converting each back through its own view recovers the same point.
    assert small.widget_to_point(small_wx, small_wy) == (x_pt, y_pt)
    assert large.widget_to_point(large_wx, large_wy) == (x_pt, y_pt)
