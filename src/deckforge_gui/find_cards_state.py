"""Select Card Pages state -- per-page semantic role (Front / Shared Back),
not a click location.

Deliberately free of any PySide6 import, same rationale as app_state.py and
session.py: this is the controller/session layer the GUI reads from, kept
separate from widget code and unit tested without opening a window.

Select Card Pages determines page *semantics*, nothing about geometry: for
each page the user pages through, they say whether it is a Front Page, the
Shared Back, or neither -- one role per page, mutually exclusive. It
deliberately does not derive rows/cols/card size or any precise crop
geometry; that is Calibrate's job (see calibrate_state.py), which consumes
these role assignments rather than rediscovering pages.

A page's role carries no coordinate. Earlier revisions of this module stored
a clicked (x, y) point per page, which implied a click's *location* on the
page mattered -- it never did. The state that matters is purely "what is
this whole page," so a page either has a role or it doesn't.

SHARED BACK: ONE PAGE, ONE EXPLICIT ANSWER
--------------------------------------------
Only one page may hold the Shared Back role at a time -- assigning it to a
new page silently moves it off whatever page held it before (see
set_role()). Because "no shared back" is a valid Deck state that must be
distinguished from "haven't decided yet" (CORE_CONCEPTS.md), that answer is
tracked explicitly via back_confirmed_none rather than inferred from the
absence of a Back-role page. See should_prompt_shared_back() for how/when
the GUI is expected to ask for that explicit answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class PageRole(Enum):
    FRONT = "front"
    BACK = "back"


@dataclass
class FindCardsState:
    current_page: int = 1
    furthest_page_viewed: int = 1
    continue_attempted: bool = False
    back_confirmed_none: bool = False
    _roles: dict[int, PageRole] = field(default_factory=dict)

    # -- role assignment ---------------------------------------------------

    def set_role(self, page_num: int, role: PageRole) -> None:
        """Assigns `role` to `page_num`, overwriting any role that page
        already had. Assigning BACK moves the Shared Back role off any
        other page that held it (only one is ever supported) and clears
        back_confirmed_none -- a page picked as the back supersedes an
        earlier "no shared back" answer."""
        if role is PageRole.BACK:
            for other_page in [p for p, r in self._roles.items() if r is PageRole.BACK and p != page_num]:
                del self._roles[other_page]
            self.back_confirmed_none = False
        self._roles[page_num] = role

    def clear_role(self, page_num: int) -> None:
        self._roles.pop(page_num, None)

    def role_for_page(self, page_num: int) -> PageRole | None:
        return self._roles.get(page_num)

    def toggle_front(self, page_num: int) -> None:
        """The Select Card Pages workspace's primary per-page control:
        clicking it a second time on the same page clears the role rather
        than re-assigning it, so the common "I marked the wrong page"
        correction is just clicking the same button again."""
        if self.role_for_page(page_num) is PageRole.FRONT:
            self.clear_role(page_num)
        else:
            self.set_role(page_num, PageRole.FRONT)

    def toggle_back(self, page_num: int) -> None:
        if self.role_for_page(page_num) is PageRole.BACK:
            self.clear_role(page_num)
        else:
            self.set_role(page_num, PageRole.BACK)

    # -- reading the current assignment ------------------------------------

    def front_pages(self) -> list[int]:
        return sorted(p for p, r in self._roles.items() if r is PageRole.FRONT)

    def front_page_count(self) -> int:
        return len(self.front_pages())

    def back_page(self) -> int | None:
        for page_num, role in self._roles.items():
            if role is PageRole.BACK:
                return page_num
        return None

    # -- the Shared Back decision -------------------------------------------

    def confirm_no_shared_back(self) -> None:
        """No-op if a page is already assigned the Back role -- the two
        facts (a real Shared Back page, and an explicit "none") must never
        be true at once. The GUI never offers this action while a page is
        assigned (see FindCardsWorkspace._refresh_deck_summary()), but the
        guard holds regardless of caller discipline."""
        if self.back_page() is not None:
            return
        self.back_confirmed_none = True
        self.continue_attempted = False

    def shared_back_resolved(self) -> bool:
        """True once the Shared Back question has a real answer -- a page,
        or an explicit "none" -- as opposed to simply not having been
        addressed yet."""
        return self.back_page() is not None or self.back_confirmed_none

    def note_continue_attempted(self) -> None:
        """Called when the user tries to leave (Continue) while the Shared
        Back question is still unresolved -- the fallback trigger for
        should_prompt_shared_back() below, for sessions that never browse
        all the way to the PDF's last page."""
        self.continue_attempted = True

    def note_page_viewed(self, page_num: int) -> None:
        """Tracks how far into the PDF the user has browsed, the same
        monotonic "furthest reached" idiom app_state.AppState uses for
        workflow steps -- reached_last_page() below is a pull-based read
        of this, not a separate signal."""
        if page_num > self.furthest_page_viewed:
            self.furthest_page_viewed = page_num

    def reached_last_page(self, page_count: int) -> bool:
        return page_count > 0 and self.furthest_page_viewed >= page_count

    def should_prompt_shared_back(self, page_count: int) -> bool:
        """Whether the Deck Summary's Shared Back line should show its
        inline "Confirm there's no Shared Back" action right now. Two
        triggers, both routed through this single condition so they read
        as one moment rather than two: reaching the end of the PDF (the
        common case -- the user has now seen every page) or having already
        tried to Continue once while unresolved (the fallback, for a
        session that never reaches the last page)."""
        if self.front_page_count() == 0 or self.shared_back_resolved():
            return False
        return self.reached_last_page(page_count) or self.continue_attempted

    # -- new/replacement PDF -------------------------------------------------

    def clear_all(self) -> None:
        self._roles.clear()
        self.back_confirmed_none = False
        self.continue_attempted = False
        self.current_page = 1
        self.furthest_page_viewed = 1


def find_cards_status_text(state: FindCardsState, page_count: int) -> str:
    """Bottom status-bar text for Select Card Pages -- the same two facts
    (Front count, Shared Back answer) the workspace's own Deck Summary
    shows, condensed to one line. See FindCardsWorkspace._refresh_deck_
    summary() for the richer in-workspace rendering, including the inline
    "Confirm there's no Shared Back" action this plain text doesn't need
    to represent."""
    if not page_count:
        return "Ready — open a PDF to begin."
    front_count = state.front_page_count()
    if front_count == 0:
        return "Ready — mark at least one page as a Front Page."
    noun = "page" if front_count == 1 else "pages"
    front_clause = f"{front_count} front {noun} marked"

    back_page = state.back_page()
    if back_page is not None:
        back_clause = f"Shared Back: page {back_page}"
    elif state.back_confirmed_none:
        back_clause = "Shared Back: none"
    elif state.should_prompt_shared_back(page_count):
        back_clause = "Shared Back: not yet decided"
    else:
        back_clause = "Shared Back: not yet"
    return f"{front_clause}. {back_clause}."
