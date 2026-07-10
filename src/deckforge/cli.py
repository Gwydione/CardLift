"""
cli.py - argparse entry point. Thin on purpose: all real logic lives in
exporter.py / cropper.py / geometry.py / profile.py / pdf_renderer.py, so
this file only parses args, loads a profile, and calls one method.
"""

from __future__ import annotations

import argparse
import sys
import traceback
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

NEW_USER_HINT = (
    "New to DeckForge? Start with:\n"
    "  python extract.py --profile <name> --calibrate\n"
    "It walks you through calibrating a deck step by step, and each "
    "command tells you what to run next."
)


class DeckForgeArgParser(argparse.ArgumentParser):
    """Adds a "start here" hint to the one error a first-time user is
    most likely to hit: running the tool without picking a mode flag
    (--preview/--export/etc.) at all. Everything else falls back to
    argparse's normal error() behavior."""

    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        extra = f"\n{NEW_USER_HINT}\n" if "one of the arguments" in message and "required" in message else ""
        self.exit(2, f"{self.prog}: error: {message}\n{extra}")


def format_export_summary(written: list[Path], output_dir: Path) -> str:
    """Formats the --export completion message: what was produced, where
    it landed, and what a first-time user would naturally do with it
    next. Kept separate from DeckExporter.export() itself so the export
    logic stays free of presentation concerns -- this only describes
    files that already exist."""
    front_paths = [p for p in written if p.name.startswith("front_")]
    back_paths = [p for p in written if p.name == "back.png"]

    size_note = ""
    if front_paths:
        try:
            from PIL import Image
            with Image.open(front_paths[0]) as im:
                size_note = f" at {im.width}x{im.height}px each"
        except Exception:
            pass

    parts = []
    if front_paths:
        plural = "s" if len(front_paths) != 1 else ""
        parts.append(f"{len(front_paths)} card front{plural}{size_note}")
    if back_paths:
        parts.append("1 back design")
    produced = " and ".join(parts) if parts else "no files"

    lines = [f"Export complete: {produced}.", f"Files are in {output_dir}/:"]
    shown = written[:3]
    for p in shown:
        lines.append(f"  {p.name}")
    if len(written) > len(shown):
        lines.append(f"  ... and {len(written) - len(shown)} more")

    lines.append(
        "\nThese PNGs are ready to use as a custom deck in tabletop "
        "platforms such as PlayingCards.io or Tabletop Simulator -- most "
        "accept a folder of individual card face images plus one shared "
        "back image."
    )
    lines.append(
        "\nNext: run --contact-sheet for one image showing every card at "
        "a glance -- a quick way to catch a mistake before importing."
    )
    return "\n".join(lines)


def friendly_error(e: Exception) -> str:
    """Prepends a plain-language cause and suggested next step to a
    caught DeckForge exception, keeping the original technical message
    underneath as "Details:" for debugging. Matches on substrings of the
    existing exception messages rather than introducing new error codes,
    so this stays in sync with profile.py/pdf_renderer.py/exporter.py/
    geometry.py/measure.py without those modules needing to know about
    presentation at all."""
    detail = str(e)

    if isinstance(e, ProfileError):
        if "not found at" in detail:
            explanation = (
                "DeckForge can't find that profile. Likely cause: no "
                "profiles/<name>.json file exists yet, or --profile is "
                "misspelled.\nNext step: create the profile JSON (see "
                "README 'Calibrating a new deck') or check the spelling."
            )
        elif "is not valid JSON" in detail:
            explanation = (
                "DeckForge couldn't read that profile file because it "
                "isn't valid JSON -- likely a typo such as a missing "
                "comma, quote, or brace.\nNext step: open the file and "
                "compare its structure against profiles/solo_cards.json."
            )
        elif "has both 'layouts' and legacy" in detail:
            explanation = (
                "This profile mixes the old flat front-grid fields with "
                "the new 'layouts' list -- DeckForge needs one or the "
                "other.\nNext step: remove the legacy first_front_page/"
                "last_front_page/rows/cols/left/top/card_width/"
                "card_height/gap_x/gap_y fields if using 'layouts', or "
                "remove 'layouts' if using the legacy flat fields."
            )
        elif "must include at least one layout" in detail:
            explanation = (
                "This profile's 'layouts' list is empty -- DeckForge "
                "needs at least one layout describing where the front "
                "cards are.\nNext step: add a layout entry with "
                "first_page/last_page/rows/cols/left/top/card_width/"
                "card_height/gap_x/gap_y/trim_* values."
            )
        elif "overlapping layout page ranges" in detail:
            explanation = (
                "Two layouts in this profile claim the same page -- each "
                "page can only belong to one layout.\nNext step: fix the "
                "first_page/last_page range on the layouts named below so "
                "they don't overlap."
            )
        elif "back_page" in detail and "overlap" in detail:
            explanation = (
                "This profile's back_page is also claimed by one of its "
                "layouts -- the shared back must be a page no layout "
                "uses.\nNext step: change back_page, or adjust the "
                "layout's first_page/last_page so it no longer includes "
                "that page."
            )
        elif "greater than last_page" in detail:
            explanation = (
                "One of this profile's layouts has first_page after "
                "last_page -- only contiguous (first_page <= last_page) "
                "ranges are supported.\nNext step: fix that layout's "
                "first_page/last_page, or split it into two layouts if "
                "the pages really aren't contiguous."
            )
        elif "missing required keys" in detail:
            explanation = (
                "This profile is missing information DeckForge needs "
                "before it can find your cards.\nNext step: add the "
                "listed fields (see README 'Profiles' for what each one "
                "means)."
            )
        elif "unrecognized keys" in detail:
            explanation = (
                "This profile has a field name DeckForge doesn't "
                "recognize -- likely a typo.\nNext step: check the field "
                "name against README 'Profiles', or prefix it with '_' if "
                "it's meant as a comment."
            )
        elif "hasn't been" in detail or "positive point values" in detail:
            explanation = (
                "This profile hasn't been calibrated yet -- card_width/"
                "card_height are still 0.\nNext step: run --calibrate (or "
                "--measure) to get real values, then --preview to check "
                "them."
            )
        else:
            explanation = "DeckForge couldn't load this profile."

    elif isinstance(e, PDFRenderError):
        if "out of range" in detail:
            explanation = (
                "That page doesn't exist in this PDF.\nNext step: check "
                "first_front_page/last_front_page/back_page in the "
                "profile (or --page) against the PDF's actual page count."
            )
        elif "not found" in detail:
            explanation = (
                "DeckForge can't find the source PDF for this deck.\n"
                "Next step: place the PDF in sample_decks/ (or the "
                "project root) using the filename given by 'pdf_file' in "
                "the profile."
            )
        else:
            explanation = "DeckForge had a problem reading the PDF."

    elif isinstance(e, ExportError):
        if "no 'pdf_file' set" in detail:
            explanation = (
                "This profile doesn't say which PDF to open.\nNext step: "
                'add "pdf_file": "your-deck.pdf" to the profile JSON.'
            )
        elif "could not find" in detail:
            explanation = (
                "DeckForge can't find the PDF named in this profile.\n"
                "Next step: place it in sample_decks/ (or the project "
                "root)."
            )
        elif "is not assigned to any layout" in detail:
            explanation = (
                "That page isn't part of this profile's card layout -- "
                "it's outside every layout's front-page range and isn't "
                "the shared back page either.\nNext step: check the page "
                "number against the profile's layouts/back_page, or omit "
                "--page to use the default."
            )
        elif "out of range" in detail:
            explanation = (
                "That card number doesn't exist in this deck.\nNext "
                "step: pick a number within the range shown below."
            )
        elif "identical dimensions" in detail:
            explanation = (
                "Something is inconsistent in the grid geometry -- cards "
                "are coming out different sizes.\nNext step: re-check "
                "rows/cols/card_width/card_height/gap_x/gap_y in the "
                "profile with --overlay."
            )
        else:
            explanation = "DeckForge couldn't complete the export."

    elif isinstance(e, GeometryError):
        explanation = (
            "The trim values leave nothing to crop for at least one "
            "card.\nNext step: reduce trim_left/trim_right/trim_top/"
            "trim_bottom in the profile."
        )

    elif isinstance(e, MeasureError):
        explanation = (
            "DeckForge couldn't understand one of the --card "
            "measurements.\nNext step: check the format against the "
            "README 'Measuring a new deck fast' example "
            "(rNcN:x1,y1,x2,y2)."
        )

    else:
        explanation = "DeckForge couldn't complete that command."

    return f"{explanation}\n\nDetails: {detail}"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = DeckForgeArgParser(
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
            print(
                "\nNext: once the red boxes look right, run --export to "
                "produce the full deck of image files."
            )

        elif args.export:
            written = exporter.export()
            print(format_export_summary(written, paths.output_dir))

        elif args.contact_sheet:
            sheet_path = exporter.contact_sheet()
            print(f"Wrote {sheet_path}")
            print(
                "\nOpen it to check every card at a glance -- this is the "
                "fastest way to catch a page that drifted relative to the "
                "others. If it all looks right, the deck in output/ is ready "
                "to import."
            )

        elif args.overlay:
            overlay_path = exporter.overlay(args.page)
            print(f"Wrote {overlay_path}")
            print(
                "\nblue = raw cell, red = saved crop. Adjust profiles/{}.json "
                "and re-run until the red boxes land exactly on card edges "
                "(see README 'Calibrating a new deck').".format(args.profile)
            )
            print(
                "\nNext: once this page looks right, run --preview to check "
                "the front grid too (if you haven't already), then --export."
            )

        elif args.inspect is not None:
            inspect_path = exporter.inspect(args.inspect)
            print(f"Wrote {inspect_path}")
            print(
                "\nblue = raw cell, red = saved crop. Anything outside the "
                "red box is excluded from the export."
            )
            print(
                "\nNext: adjust trim_left/trim_right/trim_top/trim_bottom in "
                "profiles/{}.json if needed, then re-run --preview to confirm "
                "the change across the whole page.".format(args.profile)
            )

        elif args.measure:
            page_num = args.page if args.page is not None else profile.layouts[0].first_page
            resolution = exporter.resolve_page(page_num)

            measurements = [parse_card_measurement(spec) for spec in args.card]
            resolved = resolution.geometry
            result = derive_geometry(
                measurements,
                scale=profile.render_scale,
                fallback_gap_x=resolved.gap_x,
                fallback_gap_y=resolved.gap_y,
            )

            field_names = BACK_FIELDS if resolution.is_back else FRONT_FIELDS
            current = dict(zip(field_names, (
                resolved.left, resolved.top,
                resolved.card_width, resolved.card_height,
                resolved.gap_x, resolved.gap_y,
            )))

            print(f"Measured {len(measurements)} card(s) on the {resolution.label} "
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

            page_image, resolution = exporter.render_calibration_page(args.page)
            print(f"Opening calibration window for page {resolution.page_num} of profiles/{args.profile}.json.")
            print(
                "Click two corners of a card, then follow the on-screen steps. "
                "Nothing is saved automatically -- you'll copy the suggested "
                "values into the profile JSON yourself at the end."
            )
            run_calibration(
                profile=profile, profile_name=args.profile,
                page_image=page_image, resolution=resolution,
            )

    except (ProfileError, PDFRenderError, ExportError, GeometryError, MeasureError) as e:
        print(f"ERROR: {friendly_error(e)}", file=sys.stderr)
        return 1
    except Exception:
        print(
            "ERROR: DeckForge hit a problem it doesn't have a specific "
            "explanation for. This is likely a bug, or an unusual PDF -- "
            "if it keeps happening, please report it with the details "
            "below.\n\n"
            f"Details:\n{traceback.format_exc()}",
            file=sys.stderr,
        )
        return 1

    return 0
