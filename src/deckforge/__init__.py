"""
CardLift - extract individual playing cards from print-and-play PDFs.

This package is intentionally split into small, single-purpose modules so
that each stage of the pipeline (loading a profile, rendering PDF pages,
computing grid geometry, cropping cards, building contact sheets, and
orchestrating the whole thing) can be tested, replaced, or extended on its
own. See README.md for the full architecture rationale.
"""

__version__ = "0.1.1-alpha"
