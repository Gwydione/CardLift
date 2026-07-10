"""
cli.py - argparse entry point. Thin on purpose: all real logic lives in
exporter.py / cropper.py / geometry.py / profile.py / pdf_renderer.py, so
this file only parses args, loads a profile, and calls one method.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .exporter import DeckExporter, DeckForgePaths, ExportError
from .geometry import GeometryError
from .measure import (
    BACK_FIELDS,
    FRONT_FIELDS,
    MeasureError,
    derive_geometry,
    format_suggested_patch,
    parse_card_measurement,
)
from .pdf_renderer import PDFRenderError
from .profile import ProfileError, load_profile


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="extract.py",
        description="DeckForge: extract card images from a print-and-play PDF using a manual calibration profile.",
    )
    parser.add_argument(
        "--profile", required=True,
        help="Profile name (without .json), e.g. solo_cards",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--preview", action="store_true",
        help="Render first_front_page only, crop its cards, and write a calibration overlay + preview contact sheet to preview/.",
    )
    mode.add_argument(
        "--export", action="store_true",
        help="Export all front cards (front_001.png ...) + back.png to output/.",
    )
    mode.add_argument(
        "--contact-sheet", action="store_true", dest="contact_sheet",
        help="Build a QA contact sheet from everything currently in output/.",
    )
    mode.add_argument(
        "--overlay", action="store_true",
        help="Render one page (default: first_front_page) with every crop "
             "rectangle drawn over it, labeled by row/col and card number, "
             "and save to preview/calibration_overlay.png. Combine with "
             "--page to check a different page (e.g. back_page).",
    )
    mode.add_argument(
        "--inspect", type=int, metavar="CARD_NUM", default=None,
        help="Export a high-zoom inspection image of one front card "
             "(1-indexed, matching front_NNN.png numbering) to preview/, "
             "with the crop boundary and a margin of surrounding page "
             "content shown, e.g. --inspect 1",
    )
    mode.add_argument(
        "--measure", action="store_true",
        help="Convert pixel coordinates you read off a rendered preview/"
             "overlay image (see --preview, --overlay) back into PDF "
             "points, and print a suggested left/top/card_width/"
             "card_height/gap_x/gap_y patch for the profile. Does not "
             "render, crop, or modify the profile -- combine with one or "
             "two --card options.",
    )
    mode.add_argument(
        "--calibrate", action="store_true",
        help="Open a small interactive window showing the rendered page: "
             "click a card's upper-left then lower-right corner and it "
             "prints the same suggested patch as --measure, without "
             "having to read pixel coordinates by hand. Does not modify "
             "the profile -- combine with --page to calibrate a different "
             "page (e.g. back_page).",
    )
    parser.add_argument(
        "--page", type=int, default=None,
        help="Page number to use with --overlay, --measure, or "
             "--calibrate (default: the profile's first_front_page). "
             "Only valid together with one of those.",
    )
    parser.add_argument(
        "--card", action="append", default=[], metavar="rRcC:X1,Y1,X2,Y2",
        help="Only valid with --measure. One measured card cell: which "
             "grid cell it is (e.g. r0c0), then the pixel coordinates of "
             "its top-left and bottom-right corners as read off a "
             "rendered image, e.g. --card r0c0:240,420,960,1360. Repeat "
             "with a second cell in a different row and/or column to "
             "also derive gap_x/gap_y.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.page is not None and not (args.overlay or args.measure or args.calibrate):
        parser.error("--page is only valid together with --overlay, --measure, or --calibrate")
    if args.card and not args.measure:
        parser.error("--card is only valid together with --measure")
    if args.measure and not args.card:
        parser.error("--measure requires at least one --card")

    project_root = Path(__file__).resolve().parent.parent.parent
    paths = DeckForgePaths.from_project_root(project_root)

    try:
        profile = load_profile(args.profile, paths.profiles_dir)
        exporter = DeckExporter(profile, paths)

        if args.preview:
            written = exporter.preview()
            print("Wrote:")
            for p in written:
                print(f"  {p}")
            print(
                "\nOpen calibration_overlay.png: blue = raw cell, red = saved "
                "crop. Adjust profiles/{}.json and re-run --preview until the "
                "red boxes land exactly on card edges (see README 'Calibrating "
                "a new deck').".format(args.profile)
            )

        elif args.export:
            written = exporter.export()
            print(f"Exported {len(written)} files to {paths.output_dir}/")

        elif args.contact_sheet:
            sheet_path = exporter.contact_sheet()
            print(f"Wrote {sheet_path}")

        elif args.overlay:
            overlay_path = exporter.overlay(args.page)
            print(f"Wrote {overlay_path}")
            print(
                "\nblue = raw cell, red = saved crop. Adjust profiles/{}.json "
                "and re-run until the red boxes land exactly on card edges "
                "(see README 'Calibrating a new deck').".format(args.profile)
            )

        elif args.inspect is not None:
            inspect_path = exporter.inspect(args.inspect)
            print(f"Wrote {inspect_path}")
            print(
                "\nblue = raw cell, red = saved crop. Anything outside the "
                "red box is excluded from the export."
            )

        elif args.measure:
            page_num = args.page if args.page is not None else profile.first_front_page
            is_back = page_num == profile.back_page

            measurements = [parse_card_measurement(spec) for spec in args.card]
            resolved = profile.back_geometry() if is_back else profile.front_geometry()
            result = derive_geometry(
                measurements,
                scale=profile.render_scale,
                fallback_gap_x=resolved.gap_x,
                fallback_gap_y=resolved.gap_y,
            )

            field_names = BACK_FIELDS if is_back else FRONT_FIELDS
            current = dict(zip(field_names, (
                resolved.left, resolved.top,
                resolved.card_width, resolved.card_height,
                resolved.gap_x, resolved.gap_y,
            )))

            grid_label = f"back grid, page {page_num}" if is_back else f"front grid, page {page_num}"
            print(f"Measured {len(measurements)} card(s) on the {grid_label} "
                  f"at render_scale={profile.render_scale}:")
            for m in measurements:
                print(f"  r{m.row}c{m.col}: px({m.box.x1:g},{m.box.y1:g})-"
                      f"({m.box.x2:g},{m.box.y2:g})")
            for w in result.warnings:
                print(f"  WARNING: {w}")

            print(f"\nSuggested patch for profiles/{args.profile}.json:")
            print(format_suggested_patch(result, current, field_names))
            print(
                f"\nThis is a suggestion only -- profiles/{args.profile}.json "
                f"was NOT modified. Copy the values you want into the JSON "
                f"by hand, then re-run --preview or --overlay to check them."
            )

        elif args.calibrate:
            from .calibrate_ui import run_calibration

            page_image, page_num, is_back = exporter.render_calibration_page(args.page)
            print(f"Opening calibration window for page {page_num} of profiles/{args.profile}.json.")
            print(
                "Click two corners of a card, then follow the on-screen steps. "
                "Nothing is saved automatically -- you'll copy the suggested "
                "values into the profile JSON yourself at the end."
            )
            run_calibration(
                profile=profile, profile_name=args.profile,
                page_image=page_image, page_num=page_num, is_back=is_back,
            )

    except (ProfileError, PDFRenderError, ExportError, GeometryError, MeasureError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    return 0
