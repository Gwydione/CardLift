"""Application-frame navigation/state model.

Deliberately free of any GUI toolkit import so it can be unit tested without
opening a window, and so a future controller/session layer can drive it the
same way the widgets do -- see calibrate_ui.py's ViewTransform for the same
pattern already used elsewhere in this project.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class WorkflowStep(Enum):
    DECK = "deck"
    FIND_CARDS = "find_cards"
    CALIBRATE_CARDS = "calibrate_cards"
    CALIBRATE_BACK = "calibrate_back"
    REVIEW_CARDS = "review_cards"
    EXPORT = "export"


WORKFLOW_ORDER: tuple[WorkflowStep, ...] = (
    WorkflowStep.DECK,
    WorkflowStep.FIND_CARDS,
    WorkflowStep.CALIBRATE_CARDS,
    WorkflowStep.CALIBRATE_BACK,
    WorkflowStep.REVIEW_CARDS,
    WorkflowStep.EXPORT,
)

CALIBRATE_STEPS = (WorkflowStep.CALIBRATE_CARDS, WorkflowStep.CALIBRATE_BACK)

STEP_LABELS: dict[WorkflowStep, str] = {
    WorkflowStep.DECK: "Deck",
    WorkflowStep.FIND_CARDS: "Select Card Pages",
    WorkflowStep.CALIBRATE_CARDS: "Fronts",
    WorkflowStep.CALIBRATE_BACK: "Shared Back",
    WorkflowStep.REVIEW_CARDS: "Review Cards",
    WorkflowStep.EXPORT: "Export",
}

# (headline, body) -- short and task-oriented, "show" not "teach".
GUIDANCE: dict[WorkflowStep, tuple[str, str]] = {
    WorkflowStep.DECK: (
        "Bring in your PDF.",
        "Choose the print-and-play PDF you want to turn into cards.",
    ),
    WorkflowStep.FIND_CARDS: (
        "Show DeckForge your cards.",
        "Mark each page as a card front or the shared back. Most pages "
        "(instructions, reference material) need no marking at all.",
    ),
    WorkflowStep.CALIBRATE_CARDS: (
        "Show DeckForge a front card.",
        "Click the upper-left corner of a card — use its cutting guide if "
        "it has one, otherwise the card's outer edge.",
    ),
    WorkflowStep.CALIBRATE_BACK: (
        "Show DeckForge the card back.",
        "Click the upper-left corner of the back design — use its cutting "
        "guide if it has one, otherwise the design's outer edge.",
    ),
    WorkflowStep.REVIEW_CARDS: (
        "Check your cards.",
        "Look over every card before you export the deck.",
    ),
    WorkflowStep.EXPORT: (
        "Save your finished deck.",
        "Export your cards as image files, ready to import.",
    ),
}

STATUS: dict[WorkflowStep, str] = {
    WorkflowStep.DECK: "Ready — Open a PDF to begin.",
    WorkflowStep.FIND_CARDS: "Ready — mark your card fronts (and shared back, if any).",
    WorkflowStep.CALIBRATE_CARDS: "Ready — Click the upper-left corner of a card (its cutting guide, if it has one).",
    WorkflowStep.CALIBRATE_BACK: "Ready — Click the upper-left corner of the back design (its cutting guide, if it has one).",
    WorkflowStep.REVIEW_CARDS: "Ready — review your cards.",
    WorkflowStep.EXPORT: "Ready to export.",
}

PAN_STATUS = "Pan mode — Drag to move the page. Press Esc to finish."


@dataclass
class AppState:
    current_step: WorkflowStep = WorkflowStep.DECK
    furthest_step: WorkflowStep = WorkflowStep.DECK
    pan_mode: bool = False
    guidance_collapsed: bool = False

    def select_step(self, step: WorkflowStep) -> None:
        self.current_step = step
        if WORKFLOW_ORDER.index(step) > WORKFLOW_ORDER.index(self.furthest_step):
            self.furthest_step = step
        if step not in CALIBRATE_STEPS:
            self.pan_mode = False

    def is_reached(self, step: WorkflowStep) -> bool:
        return WORKFLOW_ORDER.index(step) <= WORKFLOW_ORDER.index(self.furthest_step)

    def set_pan_mode(self, active: bool) -> None:
        self.pan_mode = active

    def toggle_pan_mode(self) -> bool:
        self.pan_mode = not self.pan_mode
        return self.pan_mode

    def exit_pan_mode(self) -> None:
        self.pan_mode = False

    def toggle_guidance_collapsed(self) -> bool:
        self.guidance_collapsed = not self.guidance_collapsed
        return self.guidance_collapsed

    def guidance_text(self) -> tuple[str, str]:
        return GUIDANCE[self.current_step]

    def status_text(self) -> str:
        if self.current_step in CALIBRATE_STEPS and self.pan_mode:
            return PAN_STATUS
        return STATUS[self.current_step]
