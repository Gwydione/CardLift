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

BACK ROLE: ANY NUMBER OF PAGES, MOSTLY-DERIVED MODE
------------------------------------------------------
The BACK role is symmetric with FRONT -- any number of pages may hold it
simultaneously. How many currently do mostly determines the deck's
BackMode (see back_mode()): zero means Front Only (pending an explicit
"no back" confirmation -- see below), and two or more means Paired Back
Pages, where each BACK-role page pairs positionally with a FRONT-role page
(see paired_back_page_for()). Earlier revisions of this module capped BACK
at a single page, evicting whichever page held it before -- that cap is
gone now that Paired Back Pages needs several BACK pages at once, but
nothing about the zero-page behavior below changed.

EXACTLY ONE BACK PAGE IS GENUINELY AMBIGUOUS
------------------------------------------------
Unlike zero or 2+, a count of exactly one BACK page cannot, by itself,
tell CardLift which mode the user means: one marked page could be a
Shared Back (a single design applied to every Front card), or it could be
a one-page Paired Backs deck -- exactly one Front sheet paired with
exactly one Back sheet, each internally a full grid of unique cards. Page
count alone cannot distinguish these, so `_single_back_page_is_paired` is
an explicit override consulted only in this one case (see back_mode()).
It defaults to False (Shared Back), preserving every existing single-
back-page deck's behavior exactly -- the override exists purely so a user
can opt into the Paired reading when that's what they actually have.
set_role()/clear_role() reset it the instant the BACK-page count moves
away from exactly one, the same "a new fact supersedes an earlier
explicit answer" rule already applied to back_confirmed_none below --
letting a stale override silently reappear once the count returns to one
later would be its own bug, the same class DEVELOPER.md's "Select Card
Pages redesign"/"Alpha Polish" sections already document being fixed
elsewhere in this app.

Because "no shared back" is a valid Deck state that must be distinguished
from "haven't decided yet" (CORE_CONCEPTS.md), that answer is tracked
explicitly via back_confirmed_none rather than inferred from the absence
of a Back-role page. This distinction only applies to the zero-BACK-pages
case -- see should_prompt_shared_back() for how/when the GUI is expected
to ask for that explicit answer, and note it never fires once two or more
BACK pages exist, since marking multiple BACK pages is itself an explicit
answer with nothing left to confirm.

THREE STATES, ONE METHOD (Front Only / Shared Back only)
-----------------------------------------------------------
Downstream consumers of the *zero-or-one-BACK-page* decision need to
distinguish three, and only three, possibilities: a page is assigned, the
user explicitly confirmed there is none, or the question is still
unresolved. shared_back_status() returns a single SharedBackStatus rather
than making callers combine back_page() and back_confirmed_none
themselves -- an earlier version of this module exposed just the two
independent facts, and Calibrate ended up treating "no page assigned"
(which is true for both CONFIRMED_NONE and UNRESOLVED) as if it always
meant CONFIRMED_NONE. Any code that needs to branch on this decision
should match on the enum, not re-derive it from back_page()/
back_confirmed_none directly.

shared_back_status()/shared_back_resolved() are scoped to that
zero-or-one-page decision only and are not meaningful once back_mode() is
PAIRED -- callers must check back_mode() first and only consult these for
the NONE/SHARED cases, the same way they already have to check
front_page_count() before anything else here matters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class PageRole(Enum):
    FRONT = "front"
    BACK = "back"


class SharedBackStatus(Enum):
    """The Deck's Shared Back decision, as one tri-state fact instead of
    two independently-checked booleans. See "THREE STATES, ONE METHOD"
    above and shared_back_status(). Scoped to the zero-or-one-BACK-page
    case only -- see BackMode for the deck-level mode this composes
    with."""
    UNRESOLVED = "unresolved"
    ASSIGNED = "assigned"
    CONFIRMED_NONE = "confirmed_none"


class BackMode(Enum):
    """Which of CardLift's three deck-level back configurations the
    current page markings represent -- mostly derived from how many pages
    currently hold the BACK role (see FindCardsState.back_mode()), except
    at exactly one page, where count alone is genuinely ambiguous (see
    this module's docstring, "EXACTLY ONE BACK PAGE IS GENUINELY
    AMBIGUOUS") and back_mode() also consults the explicit
    _single_back_page_is_paired override. Still never stored
    independently as a BackMode value itself, so it can't drift out of
    sync with the page roles (and, for the one-page case, the override
    flag) it's computed from.

    Deliberately independent of SharedBackStatus's CONFIRMED_NONE/
    UNRESOLVED distinction: NONE covers both "confirmed no back" and "not
    yet decided" for the zero-BACK-pages case -- callers that need that
    distinction still use shared_back_status()."""
    NONE = "none"
    SHARED = "shared"
    PAIRED = "paired"


@dataclass
class FindCardsState:
    current_page: int = 1
    furthest_page_viewed: int = 1
    continue_attempted: bool = False
    back_confirmed_none: bool = False
    _roles: dict[int, PageRole] = field(default_factory=dict)
    # Explicit override for the one case back_mode() cannot infer from
    # page count alone -- see this module's docstring, "EXACTLY ONE BACK
    # PAGE IS GENUINELY AMBIGUOUS". Only ever consulted when exactly one
    # page holds the BACK role; set_role()/clear_role() reset it back to
    # False (Shared Back, the default) the instant that count changes in
    # either direction, via _sync_single_back_page_intent().
    _single_back_page_is_paired: bool = False

    # -- role assignment ---------------------------------------------------

    def set_role(self, page_num: int, role: PageRole) -> None:
        """Assigns `role` to `page_num`, overwriting any role that page
        already had. BACK is symmetric with FRONT -- any number of pages
        may hold it simultaneously, so assigning it to a new page no
        longer evicts other BACK-role pages (see this module's docstring,
        "BACK ROLE: ANY NUMBER OF PAGES, MOSTLY-DERIVED MODE"). Still
        clears back_confirmed_none on a BACK assignment -- a page picked
        as a back supersedes an earlier "no shared back" answer. Also
        resyncs the single-back-page override (see
        _sync_single_back_page_intent()), since any role change can move
        the BACK-page count into or out of the one-page ambiguous case."""
        if role is PageRole.BACK:
            self.back_confirmed_none = False
        self._roles[page_num] = role
        self._sync_single_back_page_intent()

    def clear_role(self, page_num: int) -> None:
        self._roles.pop(page_num, None)
        self._sync_single_back_page_intent()

    def _sync_single_back_page_intent(self) -> None:
        """The single-back-page Paired override only means anything while
        exactly one page holds the BACK role -- once a role change moves
        the count away from exactly one (in either direction), the
        override is stale and must reset to its default (Shared Back),
        the same "a new fact supersedes an earlier explicit answer" rule
        already applied to back_confirmed_none in set_role(). Without
        this, marking a second Back page then later removing it back down
        to one page could silently resurrect a Paired override the user
        never re-confirmed for that specific configuration."""
        if len(self.back_pages()) != 1:
            self._single_back_page_is_paired = False

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

    def back_pages(self) -> list[int]:
        """Every page currently holding the BACK role, sorted -- the full
        set, regardless of back_mode(). Symmetric with front_pages()."""
        return sorted(p for p, r in self._roles.items() if r is PageRole.BACK)

    def back_page(self) -> int | None:
        """The single Shared Back page, when back_mode() is SHARED.
        Returns None both when no page holds the BACK role and when
        back_mode() is PAIRED -- including the one-page Paired case (see
        this module's docstring, "EXACTLY ONE BACK PAGE IS GENUINELY
        AMBIGUOUS"), where exactly one page holds BACK but the explicit
        override means it is not a Shared Back. Derives from back_mode()
        rather than raw page count so the two can never disagree -- a
        one-page Paired deck must never also appear to have a Shared
        Back. Callers wanting the full set regardless of mode should use
        back_pages() instead."""
        if self.back_mode() is not BackMode.SHARED:
            return None
        return self.back_pages()[0]

    # -- the Back Mode decision ----------------------------------------------

    def back_mode(self) -> BackMode:
        """The deck's back-page configuration. Zero pages yields NONE
        regardless of back_confirmed_none (callers needing the confirmed/
        unresolved distinction for that case use shared_back_status()
        instead); two or more pages always yields PAIRED. Exactly one page
        is the one case count alone cannot resolve (see this module's
        docstring, "EXACTLY ONE BACK PAGE IS GENUINELY AMBIGUOUS") --
        _single_back_page_is_paired is the explicit override consulted
        only there, defaulting to SHARED so every existing single-back-
        page deck keeps behaving exactly as before unless the user
        explicitly opts into the Paired reading."""
        count = len(self.back_pages())
        if count == 0:
            return BackMode.NONE
        if count == 1:
            return BackMode.PAIRED if self._single_back_page_is_paired else BackMode.SHARED
        return BackMode.PAIRED

    def mark_single_back_page_as_paired(self) -> None:
        """Explicit override for the one-page ambiguous case: this deck's
        single marked BACK page is a one-page Paired Backs deck (a full
        grid of unique cards paired with a single Front sheet), not a
        Shared Back. No-op unless exactly one page currently holds the
        BACK role -- the GUI only ever offers this action in that state
        (see FindCardsWorkspace._refresh_deck_summary()), but the guard
        holds regardless of caller discipline, the same defensive pattern
        confirm_no_shared_back() already uses."""
        if len(self.back_pages()) == 1:
            self._single_back_page_is_paired = True

    def mark_single_back_page_as_shared(self) -> None:
        """Reverses mark_single_back_page_as_paired() -- also this
        state's default, so this mainly lets the user flip back after
        having chosen Paired for the one-page case."""
        self._single_back_page_is_paired = False

    def paired_back_page_for(self, front_page_num: int) -> int | None:
        """The back page paired with `front_page_num` under Paired Back
        Pages' ordered-index pairing rule: the Nth page in the sorted
        front-page list pairs with the Nth page in the sorted back-page
        list (approved design decision -- based on sorted-list position,
        not literal PDF page-number arithmetic).

        Returns None when back_mode() is not PAIRED, when
        `front_page_num` isn't a marked Front Page, or when the front and
        back page counts are unbalanced and no Nth back page exists --
        None means "no defined pairing for this page right now", not an
        error. Callers that need to know whether the deck as a whole is
        correctly balanced should use paired_page_counts_balanced()
        rather than inferring it from individual None results."""
        if self.back_mode() is not BackMode.PAIRED:
            return None
        fronts = self.front_pages()
        try:
            index = fronts.index(front_page_num)
        except ValueError:
            return None
        backs = self.back_pages()
        if index >= len(backs):
            return None
        return backs[index]

    def paired_page_counts_balanced(self) -> bool:
        """Whether Paired Back Pages' "every front page pairs with a back
        page" assumption currently holds -- i.e. the front and back page
        counts match. Vacuously True when back_mode() is not PAIRED,
        since the assumption doesn't apply outside that mode. False means
        every front page beyond the shorter list's length has no defined
        pairing (paired_back_page_for() returns None for it) -- a
        supported-but-invalid state the UI is expected to report, not a
        state this method corrects or guesses at."""
        if self.back_mode() is not BackMode.PAIRED:
            return True
        return len(self.front_pages()) == len(self.back_pages())

    # -- the Shared Back decision -------------------------------------------

    def confirm_no_shared_back(self) -> None:
        """No-op if any page is already assigned the BACK role -- the two
        facts (a real back page, and an explicit "none") must never be
        true at once. Checks back_pages() rather than back_page() so this
        still correctly no-ops with two or more BACK pages assigned
        (Paired Back Pages), not only the single-page Shared Back case --
        back_page() alone returns None in that situation too, which would
        otherwise let this incorrectly confirm "no back" while Paired
        pages are actively assigned. The GUI never offers this action
        while a page is assigned (see
        FindCardsWorkspace._refresh_deck_summary()), but the guard holds
        regardless of caller discipline."""
        if self.back_pages():
            return
        self.back_confirmed_none = True
        self.continue_attempted = False

    def shared_back_status(self) -> SharedBackStatus:
        """The single authoritative answer to "what does this Deck's
        Shared Back look like right now" -- ASSIGNED, CONFIRMED_NONE, or
        UNRESOLVED. Callers (Calibrate included) should branch on this
        instead of checking back_page()/back_confirmed_none separately."""
        if self.back_page() is not None:
            return SharedBackStatus.ASSIGNED
        if self.back_confirmed_none:
            return SharedBackStatus.CONFIRMED_NONE
        return SharedBackStatus.UNRESOLVED

    def shared_back_resolved(self) -> bool:
        """True once the Shared Back question has a real answer -- a page,
        or an explicit "none" -- as opposed to simply not having been
        addressed yet. A convenience wrapper around shared_back_status()
        for callers that only need a yes/no (e.g. gating Continue)."""
        return self.shared_back_status() is not SharedBackStatus.UNRESOLVED

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
        session that never reaches the last page).

        Never fires once back_mode() is PAIRED: marking two or more BACK
        pages is itself an explicit answer, with nothing left for this
        prompt to confirm -- shared_back_resolved() alone can't detect
        this, since back_page() (which it's built on) returns None for
        PAIRED just as it does for the genuinely-unresolved zero-page
        case."""
        if self.front_page_count() == 0 or self.back_mode() is BackMode.PAIRED or self.shared_back_resolved():
            return False
        return self.reached_last_page(page_count) or self.continue_attempted

    # -- new/replacement PDF -------------------------------------------------

    def clear_all(self) -> None:
        self._roles.clear()
        self.back_confirmed_none = False
        self._single_back_page_is_paired = False
        self.continue_attempted = False
        self.current_page = 1
        self.furthest_page_viewed = 1


def continue_blocked_text(state: FindCardsState) -> str | None:
    """Message to show right next to Continue once a click has been
    blocked by an unresolved Shared Back decision -- None before any
    Continue attempt, and None again once resolved. Distinct from
    should_prompt_shared_back(), which only decides whether the Deck
    Summary's separate inline "Confirm there's no Shared Back" action is
    showing; this is the feedback for the failed click itself, so a
    Continue attempt doesn't look like it silently did nothing."""
    if state.continue_attempted and not state.shared_back_resolved():
        return "Choose a Shared Back or confirm that this deck has no Shared Back before continuing."
    return None


def back_summary_clause(state: FindCardsState) -> str:
    """The single authoritative description of the deck's back-page
    configuration, covering all four cases Select Card Pages must
    distinguish: an unresolved no-back decision, Front Only (confirmed
    none), Shared Back, and Paired Backs. Branches on back_mode() first
    (per that method's own docstring -- it's the source of truth for
    which deck-level configuration currently applies) and only falls back
    to shared_back_status() to tell CONFIRMED_NONE apart from UNRESOLVED
    within the zero-BACK-pages case, exactly as that method documents.

    Both find_cards_status_text() (the bottom status bar) and
    FindCardsWorkspace._refresh_deck_summary() (the in-workspace Deck
    Summary) call this rather than each re-deriving the mode-specific
    wording themselves -- see this module's callers for why duplicating
    that branch in the workspace was explicitly called out as a mistake to
    avoid. Returned without a trailing period so both callers can compose
    it into their own sentence.

    For PAIRED, also reports whether paired_page_counts_balanced() holds:
    when it doesn't, the clause names both counts and which side needs
    more pages, since Continue is blocked in that state and the message
    next to it must say what to do, not just that something is wrong."""
    mode = state.back_mode()
    if mode is BackMode.SHARED:
        return f"Shared Back: page {state.back_page()}"
    if mode is BackMode.PAIRED:
        front = state.front_page_count()
        back = len(state.back_pages())
        # "Paired Back Page" (singular) for the one-page case -- reachable
        # here only via the explicit single_back_page override, since
        # back_mode() would otherwise report SHARED at one page; "Paired
        # Backs" (plural) whenever 2+ pages hold the BACK role.
        label = "Paired Back Page" if back == 1 else "Paired Backs"
        if front == back:
            if back == 1:
                return f"{label}: page {state.back_pages()[0]}"
            return f"{label}: {front} pages each"
        if front > back:
            missing = front - back
            noun = "page" if missing == 1 else "pages"
            return f"{label}: {front} Front / {back} Back — mark {missing} more Back {noun} to continue"
        missing = back - front
        noun = "page" if missing == 1 else "pages"
        return f"{label}: {front} Front / {back} Back — mark {missing} more Front {noun} to continue"
    if state.shared_back_status() is SharedBackStatus.CONFIRMED_NONE:
        return "Front Only — no Back Pages"
    return "Back: not yet decided"


def find_cards_status_text(state: FindCardsState, page_count: int) -> str:
    """Bottom status-bar text for Select Card Pages -- the same two facts
    (Front count, back-configuration answer) the workspace's own Deck
    Summary shows, condensed to one line. See FindCardsWorkspace._refresh_
    deck_summary() for the richer in-workspace rendering, including the
    inline "Confirm there's no Back" action this plain text doesn't need
    to represent. back_summary_clause() is the shared source for the
    second sentence, so its wording can't drift between the two surfaces."""
    if not page_count:
        return "Ready — open a PDF to begin."
    front_count = state.front_page_count()
    if front_count == 0:
        return "Ready — mark at least one page as a Front Page."
    noun = "page" if front_count == 1 else "pages"
    front_clause = f"{front_count} front {noun} marked"
    return f"{front_clause}. {back_summary_clause(state)}."
