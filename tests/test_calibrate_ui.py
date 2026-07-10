import pytest

from deckforge.calibrate_ui import (
    MAX_ZOOM,
    ViewTransform,
    build_result_text,
    clamp,
    cleared_temporary_pan_state,
    coordinate_readout_position,
    crosshair_display_position,
    crosshair_enabled_after_escape,
    crosshair_enabled_after_reset,
    display_scale,
    format_pointer_readout,
    infer_second_cell,
    is_pan_gesture,
    normalize_box,
    pan_active,
    pan_mode_after_escape,
    parse_cell_label,
    predicted_neighbor_box,
    recompute_view_for_resize,
    wheel_direction,
)
from deckforge.measure import BACK_FIELDS, FRONT_FIELDS, CardMeasurement, MeasureError, PixelBox


class TestDisplayScale:
    def test_image_larger_than_max_is_shrunk(self) -> None:
        assert display_scale(2600, 3400, 1300, 850) == pytest.approx(0.25)

    def test_image_smaller_than_max_is_not_upscaled(self) -> None:
        assert display_scale(400, 300, 1300, 850) == 1.0

    def test_width_or_height_can_independently_bind(self) -> None:
        # width binds tighter than height
        assert display_scale(2600, 100, 1300, 850) == pytest.approx(0.5)


class TestNormalizeBox:
    def test_already_ordered_is_unchanged(self) -> None:
        assert normalize_box(10, 20, 110, 220) == (10, 20, 110, 220)

    def test_reversed_corners_are_reordered(self) -> None:
        assert normalize_box(110, 220, 10, 20) == (10, 20, 110, 220)

    def test_mixed_order_corners_are_reordered(self) -> None:
        # e.g. lower-left then upper-right
        assert normalize_box(10, 220, 110, 20) == (10, 20, 110, 220)


class TestParseCellLabel:
    def test_parses_row_col(self) -> None:
        assert parse_cell_label("r1c2") == (1, 2)

    def test_uppercase_accepted(self) -> None:
        assert parse_cell_label("R0C3") == (0, 3)

    def test_malformed_label_raises(self) -> None:
        with pytest.raises(MeasureError, match="rNcN"):
            parse_cell_label("row1col2")


class TestPredictedNeighborBox:
    def test_right_neighbor_is_offset_by_width_plus_gap(self) -> None:
        box = predicted_neighbor_box(
            PixelBox(100, 200, 300, 500), card_width=200, card_height=300,
            gap_x=20, gap_y=10, direction="right",
        )
        assert box == PixelBox(320, 200, 520, 500)

    def test_below_neighbor_is_offset_by_height_plus_gap(self) -> None:
        box = predicted_neighbor_box(
            PixelBox(100, 200, 300, 500), card_width=200, card_height=300,
            gap_x=20, gap_y=10, direction="below",
        )
        assert box == PixelBox(100, 510, 300, 810)

    def test_invalid_direction_raises(self) -> None:
        with pytest.raises(ValueError):
            predicted_neighbor_box(
                PixelBox(0, 0, 10, 10), card_width=10, card_height=10,
                gap_x=0, gap_y=0, direction="up",
            )


class TestInferSecondCell:
    def test_card_to_the_right_is_next_column_same_row(self) -> None:
        first = PixelBox(0, 0, 200, 300)
        second = PixelBox(220, 0, 420, 300)  # one cell-width+gap to the right
        assert infer_second_cell(0, 0, first, second, cell_width=220, cell_height=310) == (0, 1)

    def test_card_below_is_next_row_same_column(self) -> None:
        first = PixelBox(0, 0, 200, 300)
        second = PixelBox(0, 310, 200, 610)  # one cell-height+gap down
        assert infer_second_cell(0, 0, first, second, cell_width=220, cell_height=310) == (1, 0)

    def test_two_cells_over_is_recognized(self) -> None:
        first = PixelBox(0, 0, 200, 300)
        second = PixelBox(440, 0, 640, 300)
        assert infer_second_cell(0, 0, first, second, cell_width=220, cell_height=310) == (0, 2)

    def test_overlapping_click_returns_none(self) -> None:
        first = PixelBox(0, 0, 200, 300)
        second = PixelBox(5, 5, 205, 305)
        assert infer_second_cell(0, 0, first, second, cell_width=220, cell_height=310) is None

    def test_zero_cell_size_returns_none(self) -> None:
        first = PixelBox(0, 0, 200, 300)
        second = PixelBox(220, 0, 420, 300)
        assert infer_second_cell(0, 0, first, second, cell_width=0, cell_height=310) is None


class TestBuildResultText:
    def test_includes_patch_and_no_mutation_notice(self) -> None:
        m = CardMeasurement(0, 0, PixelBox(0, 0, 100, 200))
        current = dict(zip(FRONT_FIELDS, (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)))
        text = build_result_text(
            profile_name="solo_cards", page_num=1, is_back=False,
            measurements=[m], current=current, field_names=FRONT_FIELDS,
            scale=1.0, fallback_gap_x=0.0, fallback_gap_y=0.0,
        )
        assert "Measured 1 card(s)" in text
        assert '"card_width": 0.000 -> 100.000' in text
        assert "was NOT modified" in text

    def test_uses_back_field_names(self) -> None:
        m = CardMeasurement(0, 0, PixelBox(0, 0, 100, 200))
        current = dict(zip(BACK_FIELDS, (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)))
        text = build_result_text(
            profile_name="solo_cards", page_num=5, is_back=True,
            measurements=[m], current=current, field_names=BACK_FIELDS,
            scale=1.0, fallback_gap_x=0.0, fallback_gap_y=0.0,
        )
        assert '"back_card_width"' in text

    def test_raises_measure_error_for_no_measurements(self) -> None:
        with pytest.raises(MeasureError):
            build_result_text(
                profile_name="solo_cards", page_num=1, is_back=False,
                measurements=[], current={}, field_names=FRONT_FIELDS,
                scale=1.0, fallback_gap_x=0.0, fallback_gap_y=0.0,
            )


class TestClamp:
    def test_within_range_is_unchanged(self) -> None:
        assert clamp(5.0, 0.0, 10.0) == 5.0

    def test_below_range_is_raised_to_lo(self) -> None:
        assert clamp(-5.0, 0.0, 10.0) == 0.0

    def test_above_range_is_lowered_to_hi(self) -> None:
        assert clamp(50.0, 0.0, 10.0) == 10.0


class TestWheelDirection:
    def test_windows_style_positive_delta_zooms_in(self) -> None:
        assert wheel_direction(120) == 1

    def test_windows_style_negative_delta_zooms_out(self) -> None:
        assert wheel_direction(-120) == -1

    def test_macos_style_small_positive_delta_zooms_in(self) -> None:
        assert wheel_direction(1) == 1

    def test_macos_style_small_negative_delta_zooms_out(self) -> None:
        assert wheel_direction(-2) == -1

    def test_large_magnitude_does_not_change_direction(self) -> None:
        # Only the sign matters -- an unusually large delta (a fast
        # trackpad fling, or a mouse driver reporting big steps) must not
        # produce a bigger zoom jump than a single notch.
        assert wheel_direction(1200) == wheel_direction(120) == 1

    def test_zero_delta_is_a_no_op(self) -> None:
        assert wheel_direction(0) == 0


class TestIsPanGesture:
    def test_middle_button_always_pans(self) -> None:
        assert is_pan_gesture("middle", space_held=False, pan_mode=False) is True
        assert is_pan_gesture("middle", space_held=True, pan_mode=False) is True
        assert is_pan_gesture("middle", space_held=False, pan_mode=True) is True

    def test_ordinary_left_button_is_a_calibration_click(self) -> None:
        # No Pan mode, no Spacebar -- an ordinary left click must remain a
        # calibration click, never a pan.
        assert is_pan_gesture("left", space_held=False, pan_mode=False) is False

    def test_left_button_pans_with_space_held(self) -> None:
        assert is_pan_gesture("left", space_held=True, pan_mode=False) is True

    def test_left_button_pans_in_persistent_pan_mode(self) -> None:
        assert is_pan_gesture("left", space_held=False, pan_mode=True) is True

    def test_left_button_pans_when_both_space_and_pan_mode_are_active(self) -> None:
        assert is_pan_gesture("left", space_held=True, pan_mode=True) is True

    def test_other_buttons_never_pan(self) -> None:
        assert is_pan_gesture("right", space_held=True, pan_mode=True) is False


class TestPanModeAfterEscape:
    def test_escape_exits_persistent_pan_mode(self) -> None:
        assert pan_mode_after_escape(True) is False

    def test_escape_is_a_no_op_when_pan_mode_already_off(self) -> None:
        assert pan_mode_after_escape(False) is False


class TestClearedTemporaryPanState:
    def test_persistent_pan_mode_survives_spacebar_release(self) -> None:
        # Releasing Spacebar (or losing focus) always clears the temporary
        # space_held flag, but must never turn off a persistent Pan mode
        # the user deliberately selected via the Pan button.
        space_held, pan_mode = cleared_temporary_pan_state(pan_mode=True)
        assert space_held is False
        assert pan_mode is True

    def test_pan_mode_off_stays_off(self) -> None:
        space_held, pan_mode = cleared_temporary_pan_state(pan_mode=False)
        assert space_held is False
        assert pan_mode is False


class TestViewTransformRoundTrip:
    @pytest.mark.parametrize(
        "scale,offset_x,offset_y",
        [
            (1.0, 0.0, 0.0),
            (0.25, 0.0, 0.0),  # a "Fit to Window" style shrink
            (1.0, 0.0, 0.0),  # "100%"
            (8.0, -500.0, -300.0),  # high zoom, panned
            (0.1, 50.0, 20.0),  # min-zoom-ish, panned into positive space
            (2.5, -123.4, 67.8),
        ],
    )
    def test_canvas_to_image_inverts_image_to_canvas(self, scale, offset_x, offset_y) -> None:
        view = ViewTransform(scale, offset_x, offset_y)
        for img_x, img_y in [(0.0, 0.0), (1000.0, 2000.0), (37.5, 912.25)]:
            cx, cy = view.image_to_canvas(img_x, img_y)
            back_x, back_y = view.canvas_to_image(cx, cy)
            assert back_x == pytest.approx(img_x)
            assert back_y == pytest.approx(img_y)

    def test_image_to_canvas_inverts_canvas_to_image(self) -> None:
        view = ViewTransform(3.0, 40.0, -15.0)
        for cx, cy in [(0.0, 0.0), (1300.0, 820.0), (650.5, 410.25)]:
            img_x, img_y = view.canvas_to_image(cx, cy)
            back_cx, back_cy = view.image_to_canvas(img_x, img_y)
            assert back_cx == pytest.approx(cx)
            assert back_cy == pytest.approx(cy)


class TestZoomedAt:
    def test_pointer_anchored_point_stays_put_when_zooming_in(self) -> None:
        view = ViewTransform(1.0, 0.0, 0.0)
        pointer = (400.0, 300.0)
        before_img = view.canvas_to_image(*pointer)

        new_view = view.zoomed_at(*pointer, new_scale=2.0, min_scale=0.1, max_scale=8.0)
        after_img = new_view.canvas_to_image(*pointer)

        assert after_img[0] == pytest.approx(before_img[0])
        assert after_img[1] == pytest.approx(before_img[1])
        assert new_view.scale == 2.0

    def test_pointer_anchored_point_stays_put_when_zooming_out(self) -> None:
        view = ViewTransform(2.0, -100.0, -50.0)
        pointer = (250.0, 175.0)
        before_img = view.canvas_to_image(*pointer)

        new_view = view.zoomed_at(*pointer, new_scale=0.5, min_scale=0.1, max_scale=8.0)
        after_img = new_view.canvas_to_image(*pointer)

        assert after_img[0] == pytest.approx(before_img[0])
        assert after_img[1] == pytest.approx(before_img[1])
        assert new_view.scale == 0.5

    def test_clamps_at_maximum_zoom(self) -> None:
        view = ViewTransform(1.0, 0.0, 0.0)
        new_view = view.zoomed_at(100.0, 100.0, new_scale=50.0, min_scale=0.1, max_scale=MAX_ZOOM)
        assert new_view.scale == MAX_ZOOM

    def test_clamps_at_minimum_zoom(self) -> None:
        view = ViewTransform(1.0, 0.0, 0.0)
        new_view = view.zoomed_at(100.0, 100.0, new_scale=0.001, min_scale=0.1, max_scale=8.0)
        assert new_view.scale == 0.1

    def test_repeated_zoom_in_and_out_returns_to_original_scale(self) -> None:
        # Order of zoom operations shouldn't matter for where a fixed
        # point ends up, as long as the scale returns to the same value.
        view = ViewTransform(1.0, 0.0, 0.0)
        pointer = (640.0, 400.0)
        img_before = view.canvas_to_image(*pointer)

        zoomed_in = view.zoomed_at(*pointer, new_scale=4.0, min_scale=0.1, max_scale=8.0)
        back = zoomed_in.zoomed_at(*pointer, new_scale=1.0, min_scale=0.1, max_scale=8.0)

        assert back.scale == pytest.approx(1.0)
        img_after = back.canvas_to_image(*pointer)
        assert img_after[0] == pytest.approx(img_before[0])
        assert img_after[1] == pytest.approx(img_before[1])


class TestViewTransformClamped:
    def test_content_larger_than_viewport_is_clamped_into_range(self) -> None:
        # A 4000x3000 image at scale=1 (4000x3000 content) in an 800x600
        # viewport dragged way past its bounds should clamp back so the
        # image can't be dragged fully out of view.
        view = ViewTransform(1.0, 5000.0, 5000.0)
        clamped = view.clamped(canvas_w=800.0, canvas_h=600.0, image_w=4000.0, image_h=3000.0)
        assert clamped.offset_x == 0.0
        assert clamped.offset_y == 0.0

        view = ViewTransform(1.0, -9000.0, -9000.0)
        clamped = view.clamped(canvas_w=800.0, canvas_h=600.0, image_w=4000.0, image_h=3000.0)
        assert clamped.offset_x == 800.0 - 4000.0
        assert clamped.offset_y == 600.0 - 3000.0

    def test_content_smaller_than_viewport_is_centered(self) -> None:
        # A 400x300 image at scale=1 in an 800x600 viewport should be
        # centered regardless of whatever offset it started at.
        view = ViewTransform(1.0, 999.0, -999.0)
        clamped = view.clamped(canvas_w=800.0, canvas_h=600.0, image_w=400.0, image_h=300.0)
        assert clamped.offset_x == pytest.approx(200.0)
        assert clamped.offset_y == pytest.approx(150.0)

    def test_within_range_offset_is_unchanged(self) -> None:
        view = ViewTransform(1.0, -100.0, -50.0)
        clamped = view.clamped(canvas_w=800.0, canvas_h=600.0, image_w=4000.0, image_h=3000.0)
        assert clamped.offset_x == -100.0
        assert clamped.offset_y == -50.0


class TestVisibleSourceRect:
    def test_fit_to_window_shows_the_whole_image(self) -> None:
        # A 4000x2000 image fit into an 800x400 viewport (scale=0.2) with
        # no panning should report the entire image as visible.
        view = ViewTransform.fitting(0.2, canvas_w=800.0, canvas_h=400.0, image_w=4000.0, image_h=2000.0)
        rect = view.visible_source_rect(800.0, 400.0, 4000.0, 2000.0)
        assert rect == (0.0, 0.0, 4000.0, 2000.0)

    def test_zoomed_and_panned_subregion(self) -> None:
        view = ViewTransform(2.0, -1000.0, -500.0)
        rect = view.visible_source_rect(canvas_w=800.0, canvas_h=600.0, image_w=4000.0, image_h=3000.0)
        assert rect == pytest.approx((500.0, 250.0, 900.0, 550.0))

    def test_clipping_at_every_image_edge(self) -> None:
        # Viewport hangs off the top-left corner of the image.
        view = ViewTransform(1.0, 300.0, 300.0)
        rect = view.visible_source_rect(canvas_w=800.0, canvas_h=600.0, image_w=100.0, image_h=100.0)
        assert rect == (0.0, 0.0, 100.0, 100.0)

        # Viewport hangs off the bottom-right corner of the image.
        view = ViewTransform(1.0, -3900.0, -2900.0)
        rect = view.visible_source_rect(canvas_w=800.0, canvas_h=600.0, image_w=4000.0, image_h=3000.0)
        assert rect == pytest.approx((3900.0, 2900.0, 4000.0, 3000.0))

    def test_image_smaller_than_viewport_reports_full_image_only(self) -> None:
        # Blank space around a centered small image must not stretch the
        # crop -- the visible rect is still exactly the image's own bounds.
        view = ViewTransform.fitting(1.0, canvas_w=800.0, canvas_h=600.0, image_w=400.0, image_h=300.0)
        rect = view.visible_source_rect(800.0, 600.0, 400.0, 300.0)
        assert rect == (0.0, 0.0, 400.0, 300.0)


class TestViewTransformFitting:
    def test_centers_image_smaller_than_viewport(self) -> None:
        view = ViewTransform.fitting(1.0, canvas_w=800.0, canvas_h=600.0, image_w=400.0, image_h=300.0)
        assert view.scale == 1.0
        assert view.offset_x == pytest.approx(200.0)
        assert view.offset_y == pytest.approx(150.0)

    def test_matches_display_scale_for_fit_to_window(self) -> None:
        fit_scale = display_scale(4000, 3000, 800, 600)
        view = ViewTransform.fitting(fit_scale, canvas_w=800.0, canvas_h=600.0, image_w=4000.0, image_h=3000.0)
        # At the fit scale, content exactly matches (or is smaller than)
        # one viewport dimension, so offset on that axis is 0.
        assert view.offset_x == pytest.approx(0.0)
        assert view.offset_y == pytest.approx(0.0)


class TestZoomAnchorWithViewportClamping:
    """`_zoom_by_direction` always applies `.clamped()` after `.zoomed_at()`
    (matching the requirement to center an axis smaller than the
    viewport). That means pointer-anchoring only holds exactly on an axis
    once the zoomed content exceeds the viewport on that axis -- while an
    axis still has slack, it stays centered instead (which is itself
    smooth/non-jumpy, just not pointer-anchored). This test pins down that
    intentional interaction so it doesn't get "fixed" into a regression."""

    def test_axis_with_slack_stays_centered_through_zoom(self) -> None:
        # A 4000x400 image (very wide, short) in an 800x600 viewport at
        # scale=0.2: width fills the viewport (800), height has slack (80
        # of 600). Zooming in around an off-center pointer should keep the
        # short axis centered rather than tracking the pointer.
        view = ViewTransform.fitting(0.2, canvas_w=800.0, canvas_h=600.0, image_w=4000.0, image_h=400.0)
        pointer = (700.0, 100.0)  # near an edge, not the vertical center
        zoomed = view.zoomed_at(*pointer, new_scale=0.3, min_scale=0.1, max_scale=8.0)
        clamped = zoomed.clamped(800.0, 600.0, 4000.0, 400.0)
        expected_offset_y = (600.0 - 400.0 * 0.3) / 2
        assert clamped.offset_y == pytest.approx(expected_offset_y)

    def test_axis_without_slack_preserves_pointer_anchor(self) -> None:
        # Same image, but zoom in enough that both axes exceed the
        # viewport -- now the anchor should hold on both.
        view = ViewTransform.fitting(0.2, canvas_w=800.0, canvas_h=600.0, image_w=4000.0, image_h=400.0)
        pointer = (400.0, 300.0)
        img_before = view.canvas_to_image(*pointer)

        current = view
        for _ in range(25):  # 1.1x steps until height content clears 600px
            current = current.zoomed_at(*pointer, new_scale=current.scale * 1.1, min_scale=0.1, max_scale=8.0)
            current = current.clamped(800.0, 600.0, 4000.0, 400.0)

        assert 4000.0 * current.scale > 800.0
        assert 400.0 * current.scale > 600.0
        img_after = current.canvas_to_image(*pointer)
        assert img_after[0] == pytest.approx(img_before[0])
        assert img_after[1] == pytest.approx(img_before[1])


class TestCoordinateIntegrityAcrossViewChanges:
    """The acceptance requirement: the same rendered-image point must map
    back to the same image coordinates no matter what sequence of zoom/pan/
    fit/100% operations produced the current view."""

    def test_same_image_point_recovered_after_zoom_pan_and_fit_sequence(self) -> None:
        image_w, image_h = 4000.0, 3000.0
        canvas_w, canvas_h = 800.0, 600.0
        fit_scale = display_scale(int(image_w), int(image_h), int(canvas_w), int(canvas_h))

        target_img_point = (1234.5, 876.25)

        # View A: fit to window, click.
        view_a = ViewTransform.fitting(fit_scale, canvas_w, canvas_h, image_w, image_h)
        canvas_pt_a = view_a.image_to_canvas(*target_img_point)
        recovered_a = view_a.canvas_to_image(*canvas_pt_a)

        # View B: zoom in on some other point, pan around, then zoom to
        # 100%, then pan again -- an arbitrary sequence of view changes.
        view_b = view_a.zoomed_at(100.0, 100.0, 3.0, min_scale=0.1, max_scale=8.0)
        view_b = view_b.clamped(canvas_w, canvas_h, image_w, image_h)
        view_b = view_b.panned_by(-200.0, 150.0).clamped(canvas_w, canvas_h, image_w, image_h)
        view_b = ViewTransform.fitting(1.0, canvas_w, canvas_h, image_w, image_h)
        view_b = view_b.panned_by(75.0, -40.0).clamped(canvas_w, canvas_h, image_w, image_h)

        canvas_pt_b = view_b.image_to_canvas(*target_img_point)
        recovered_b = view_b.canvas_to_image(*canvas_pt_b)

        # Regardless of the very different views, clicking the same image
        # point recovers the same image-space coordinates.
        assert recovered_a[0] == pytest.approx(recovered_b[0])
        assert recovered_a[1] == pytest.approx(recovered_b[1])
        assert recovered_a[0] == pytest.approx(target_img_point[0])
        assert recovered_a[1] == pytest.approx(target_img_point[1])


class TestRecenteredForResize:
    def test_preserves_scale(self) -> None:
        view = ViewTransform(2.0, -100.0, -50.0)
        resized = view.recentered_for_resize(800.0, 600.0, 1600.0, 1200.0)
        assert resized.scale == 2.0

    def test_old_viewport_center_lands_on_new_viewport_center(self) -> None:
        view = ViewTransform(2.0, -100.0, -50.0)
        old_w, old_h = 800.0, 600.0
        new_w, new_h = 1600.0, 900.0
        img_at_old_center = view.canvas_to_image(old_w / 2, old_h / 2)

        resized = view.recentered_for_resize(old_w, old_h, new_w, new_h)
        img_at_new_center = resized.canvas_to_image(new_w / 2, new_h / 2)

        assert img_at_new_center[0] == pytest.approx(img_at_old_center[0])
        assert img_at_new_center[1] == pytest.approx(img_at_old_center[1])


class TestRecomputeViewForResize:
    def test_fit_mode_recalculates_fitted_transform_for_new_canvas(self) -> None:
        view = ViewTransform.fitting(0.25, canvas_w=800.0, canvas_h=600.0, image_w=4000.0, image_h=2000.0)
        new_view = recompute_view_for_resize(
            view, is_fit=True,
            old_canvas_w=800.0, old_canvas_h=600.0,
            new_canvas_w=1600.0, new_canvas_h=1200.0,
            image_w=4000.0, image_h=2000.0,
        )
        expected_scale = display_scale(4000, 2000, 1600, 1200)
        assert new_view.scale == pytest.approx(expected_scale)

    def test_manual_zoom_preserves_scale_and_center_point_before_clamping(self) -> None:
        # A scale/offset combination where zooming won't hit the clamp on
        # either axis at the new size, so the pointer-anchored center is
        # exactly preserved.
        view = ViewTransform(2.0, -3000.0, -2000.0)
        old_w, old_h = 800.0, 600.0
        center_img_before = view.canvas_to_image(old_w / 2, old_h / 2)

        new_view = recompute_view_for_resize(
            view, is_fit=False,
            old_canvas_w=old_w, old_canvas_h=old_h,
            new_canvas_w=1600.0, new_canvas_h=1200.0,
            image_w=4000.0, image_h=3000.0,
        )

        assert new_view.scale == pytest.approx(2.0)
        center_img_after = new_view.canvas_to_image(1600.0 / 2, 1200.0 / 2)
        assert center_img_after[0] == pytest.approx(center_img_before[0])
        assert center_img_after[1] == pytest.approx(center_img_before[1])

    def test_result_is_clamped_and_centered_for_the_new_viewport(self) -> None:
        # A small image in a much bigger new viewport must end up centered
        # in that new viewport, not left at a stale offset.
        view = ViewTransform(1.0, 999.0, -999.0)
        new_view = recompute_view_for_resize(
            view, is_fit=False,
            old_canvas_w=800.0, old_canvas_h=600.0,
            new_canvas_w=2000.0, new_canvas_h=1500.0,
            image_w=400.0, image_h=300.0,
        )
        assert new_view.offset_x == pytest.approx((2000.0 - 400.0) / 2)
        assert new_view.offset_y == pytest.approx((1500.0 - 300.0) / 2)

    def test_does_not_require_or_touch_calibration_measurements(self) -> None:
        # The resize decision is made purely from view/canvas/image
        # geometry -- it has no way to see or mutate calibration state,
        # so measurements taken before a resize are untouched by it.
        measurements = [CardMeasurement(0, 0, PixelBox(10, 20, 110, 220))]
        view = ViewTransform.fitting(0.25, canvas_w=800.0, canvas_h=600.0, image_w=4000.0, image_h=2000.0)
        recompute_view_for_resize(
            view, is_fit=True,
            old_canvas_w=800.0, old_canvas_h=600.0,
            new_canvas_w=1600.0, new_canvas_h=1200.0,
            image_w=4000.0, image_h=2000.0,
        )
        assert measurements == [CardMeasurement(0, 0, PixelBox(10, 20, 110, 220))]


class TestPanActive:
    def test_no_pan_state_is_inactive(self) -> None:
        assert pan_active(pan_mode=False, space_held=False, panning=False) is False

    def test_persistent_pan_mode_is_active(self) -> None:
        assert pan_active(pan_mode=True, space_held=False, panning=False) is True

    def test_spacebar_hold_is_active(self) -> None:
        assert pan_active(pan_mode=False, space_held=True, panning=False) is True

    def test_active_drag_is_active(self) -> None:
        assert pan_active(pan_mode=False, space_held=False, panning=True) is True


class TestCrosshairDisplayPosition:
    def test_visible_in_normal_calibration_mode(self) -> None:
        pointer = (120.0, 340.0)
        assert crosshair_display_position(
            enabled=True, pan_mode=False, space_held=False, panning=False, pointer=pointer,
        ) == pointer

    def test_disabled_by_the_crosshair_toggle(self) -> None:
        pointer = (120.0, 340.0)
        assert crosshair_display_position(
            enabled=False, pan_mode=False, space_held=False, panning=False, pointer=pointer,
        ) is None

    def test_suppressed_by_persistent_pan_mode(self) -> None:
        pointer = (120.0, 340.0)
        assert crosshair_display_position(
            enabled=True, pan_mode=True, space_held=False, panning=False, pointer=pointer,
        ) is None

    def test_suppressed_by_temporary_spacebar_pan_mode(self) -> None:
        pointer = (120.0, 340.0)
        assert crosshair_display_position(
            enabled=True, pan_mode=False, space_held=True, panning=False, pointer=pointer,
        ) is None

    def test_suppressed_during_an_active_pan_drag(self) -> None:
        pointer = (120.0, 340.0)
        assert crosshair_display_position(
            enabled=True, pan_mode=False, space_held=False, panning=True, pointer=pointer,
        ) is None

    def test_leaving_the_canvas_hides_it(self) -> None:
        # A None pointer is what _on_canvas_leave records -- must hide
        # regardless of the toggle or pan state being otherwise "visible".
        assert crosshair_display_position(
            enabled=True, pan_mode=False, space_held=False, panning=False, pointer=None,
        ) is None


class TestCoordinateReadoutPosition:
    def test_visible_in_normal_calibration_mode(self) -> None:
        pointer = (50.0, 60.0)
        assert coordinate_readout_position(
            pan_mode=False, space_held=False, panning=False, pointer=pointer,
        ) == pointer

    def test_suppressed_by_persistent_pan_mode(self) -> None:
        pointer = (50.0, 60.0)
        assert coordinate_readout_position(
            pan_mode=True, space_held=False, panning=False, pointer=pointer,
        ) is None

    def test_suppressed_by_temporary_spacebar_pan_mode(self) -> None:
        pointer = (50.0, 60.0)
        assert coordinate_readout_position(
            pan_mode=False, space_held=True, panning=False, pointer=pointer,
        ) is None

    def test_suppressed_during_an_active_pan_drag(self) -> None:
        pointer = (50.0, 60.0)
        assert coordinate_readout_position(
            pan_mode=False, space_held=False, panning=True, pointer=pointer,
        ) is None

    def test_leaving_the_canvas_hides_it(self) -> None:
        assert coordinate_readout_position(
            pan_mode=False, space_held=False, panning=False, pointer=None,
        ) is None


class TestCrosshairEnabledAfterReset:
    def test_start_over_does_not_reset_crosshair_preference(self) -> None:
        assert crosshair_enabled_after_reset(True) is True
        assert crosshair_enabled_after_reset(False) is False


class TestCrosshairEnabledAfterEscape:
    def test_escape_does_not_change_crosshair_preference(self) -> None:
        assert crosshair_enabled_after_escape(True) is True
        assert crosshair_enabled_after_escape(False) is False


class TestFormatPointerReadout:
    def test_formats_rounded_original_pixel_coordinates(self) -> None:
        assert format_pointer_readout(1432.4, 2876.6) == "X 1432  Y 2877"

    def test_formats_zero(self) -> None:
        assert format_pointer_readout(0.0, 0.0) == "X 0  Y 0"
