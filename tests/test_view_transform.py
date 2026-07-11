import pytest

from deckforge_gui.view_transform import (
    ViewTransform,
    clamp,
    display_scale,
    is_pan_gesture,
    pan_active,
    recompute_view_for_resize,
    wheel_direction,
)

MAX_ZOOM = 8.0


class TestClamp:
    def test_within_range_is_unchanged(self) -> None:
        assert clamp(5.0, 0.0, 10.0) == 5.0

    def test_below_range_is_raised_to_lo(self) -> None:
        assert clamp(-5.0, 0.0, 10.0) == 0.0

    def test_above_range_is_lowered_to_hi(self) -> None:
        assert clamp(50.0, 0.0, 10.0) == 10.0


class TestDisplayScale:
    def test_image_larger_than_max_is_shrunk(self) -> None:
        assert display_scale(2600, 3400, 1300, 850) == pytest.approx(0.25)

    def test_image_smaller_than_max_is_not_upscaled(self) -> None:
        assert display_scale(400, 300, 1300, 850) == 1.0

    def test_width_or_height_can_independently_bind(self) -> None:
        assert display_scale(2600, 100, 1300, 850) == pytest.approx(0.5)

    def test_degenerate_dims_return_one(self) -> None:
        assert display_scale(0, 300, 1300, 850) == 1.0
        assert display_scale(400, 300, 0, 850) == 1.0


class TestWheelDirection:
    def test_windows_style_positive_delta_zooms_in(self) -> None:
        assert wheel_direction(120) == 1

    def test_windows_style_negative_delta_zooms_out(self) -> None:
        assert wheel_direction(-120) == -1

    def test_macos_style_small_delta_still_normalizes(self) -> None:
        assert wheel_direction(1) == 1
        assert wheel_direction(-2) == -1

    def test_large_magnitude_does_not_change_direction(self) -> None:
        assert wheel_direction(1200) == wheel_direction(120) == 1

    def test_zero_delta_is_a_no_op(self) -> None:
        assert wheel_direction(0) == 0


class TestIsPanGesture:
    def test_middle_button_always_pans(self) -> None:
        assert is_pan_gesture("middle", space_held=False, pan_mode=False) is True

    def test_ordinary_left_button_is_a_click(self) -> None:
        assert is_pan_gesture("left", space_held=False, pan_mode=False) is False

    def test_left_button_pans_with_space_held(self) -> None:
        assert is_pan_gesture("left", space_held=True, pan_mode=False) is True

    def test_left_button_pans_in_persistent_pan_mode(self) -> None:
        assert is_pan_gesture("left", space_held=False, pan_mode=True) is True

    def test_other_buttons_never_pan(self) -> None:
        assert is_pan_gesture("right", space_held=True, pan_mode=True) is False


class TestPanActive:
    def test_no_pan_state_is_inactive(self) -> None:
        assert pan_active(pan_mode=False, space_held=False, panning=False) is False

    def test_persistent_pan_mode_is_active(self) -> None:
        assert pan_active(pan_mode=True, space_held=False, panning=False) is True

    def test_spacebar_hold_is_active(self) -> None:
        assert pan_active(pan_mode=False, space_held=True, panning=False) is True

    def test_active_drag_is_active(self) -> None:
        assert pan_active(pan_mode=False, space_held=False, panning=True) is True


class TestViewTransformRoundTrip:
    @pytest.mark.parametrize(
        "scale,offset_x,offset_y",
        [
            (1.0, 0.0, 0.0),
            (0.25, 0.0, 0.0),
            (8.0, -500.0, -300.0),
            (0.1, 50.0, 20.0),
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

    def test_clamps_at_maximum_zoom(self) -> None:
        view = ViewTransform(1.0, 0.0, 0.0)
        new_view = view.zoomed_at(100.0, 100.0, new_scale=50.0, min_scale=0.1, max_scale=MAX_ZOOM)
        assert new_view.scale == MAX_ZOOM

    def test_clamps_at_minimum_zoom(self) -> None:
        view = ViewTransform(1.0, 0.0, 0.0)
        new_view = view.zoomed_at(100.0, 100.0, new_scale=0.001, min_scale=0.1, max_scale=8.0)
        assert new_view.scale == 0.1


class TestViewTransformClamped:
    def test_content_larger_than_viewport_is_clamped_into_range(self) -> None:
        view = ViewTransform(1.0, 5000.0, 5000.0)
        clamped = view.clamped(canvas_w=800.0, canvas_h=600.0, image_w=4000.0, image_h=3000.0)
        assert clamped.offset_x == 0.0
        assert clamped.offset_y == 0.0

    def test_content_smaller_than_viewport_is_centered(self) -> None:
        view = ViewTransform(1.0, 999.0, -999.0)
        clamped = view.clamped(canvas_w=800.0, canvas_h=600.0, image_w=400.0, image_h=300.0)
        assert clamped.offset_x == pytest.approx(200.0)
        assert clamped.offset_y == pytest.approx(150.0)


class TestVisibleSourceRect:
    def test_fit_shows_the_whole_image(self) -> None:
        view = ViewTransform.fitting(0.2, canvas_w=800.0, canvas_h=400.0, image_w=4000.0, image_h=2000.0)
        rect = view.visible_source_rect(800.0, 400.0, 4000.0, 2000.0)
        assert rect == (0.0, 0.0, 4000.0, 2000.0)

    def test_zoomed_and_panned_subregion(self) -> None:
        view = ViewTransform(2.0, -1000.0, -500.0)
        rect = view.visible_source_rect(canvas_w=800.0, canvas_h=600.0, image_w=4000.0, image_h=3000.0)
        assert rect == pytest.approx((500.0, 250.0, 900.0, 550.0))


class TestViewTransformFitting:
    def test_centers_image_smaller_than_viewport(self) -> None:
        view = ViewTransform.fitting(1.0, canvas_w=800.0, canvas_h=600.0, image_w=400.0, image_h=300.0)
        assert view.scale == 1.0
        assert view.offset_x == pytest.approx(200.0)
        assert view.offset_y == pytest.approx(150.0)

    def test_matches_display_scale_for_fit(self) -> None:
        fit_scale = display_scale(4000, 3000, 800, 600)
        view = ViewTransform.fitting(fit_scale, canvas_w=800.0, canvas_h=600.0, image_w=4000.0, image_h=3000.0)
        assert view.offset_x == pytest.approx(0.0)
        assert view.offset_y == pytest.approx(0.0)


class TestCoordinateIntegrityAcrossViewChanges:
    def test_same_image_point_recovered_after_zoom_pan_and_fit_sequence(self) -> None:
        image_w, image_h = 4000.0, 3000.0
        canvas_w, canvas_h = 800.0, 600.0
        fit_scale = display_scale(int(image_w), int(image_h), int(canvas_w), int(canvas_h))
        target_img_point = (1234.5, 876.25)

        view_a = ViewTransform.fitting(fit_scale, canvas_w, canvas_h, image_w, image_h)
        canvas_pt_a = view_a.image_to_canvas(*target_img_point)
        recovered_a = view_a.canvas_to_image(*canvas_pt_a)

        view_b = view_a.zoomed_at(100.0, 100.0, 3.0, min_scale=0.1, max_scale=8.0)
        view_b = view_b.clamped(canvas_w, canvas_h, image_w, image_h)
        view_b = view_b.panned_by(-200.0, 150.0).clamped(canvas_w, canvas_h, image_w, image_h)
        view_b = ViewTransform.fitting(1.0, canvas_w, canvas_h, image_w, image_h)
        view_b = view_b.panned_by(75.0, -40.0).clamped(canvas_w, canvas_h, image_w, image_h)

        canvas_pt_b = view_b.image_to_canvas(*target_img_point)
        recovered_b = view_b.canvas_to_image(*canvas_pt_b)

        assert recovered_a[0] == pytest.approx(recovered_b[0])
        assert recovered_a[1] == pytest.approx(recovered_b[1])


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
