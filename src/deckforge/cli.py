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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

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

    except (ProfileError, PDFRenderError, ExportError, GeometryError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    return 0
