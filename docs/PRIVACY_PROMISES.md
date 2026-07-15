# DeckForge Privacy Promises

This page is not a legal Privacy Policy — DeckForge doesn't collect
anything today that would require one. It's something more basic: a
plain-language statement of what DeckForge actually does with your
files, written from the code, not from aspiration. If DeckForge ever
starts collecting or transmitting data in a way that *would* need a
formal policy, we'll say so here first, and a real policy will follow.

These promises describe DeckForge's alpha behavior (`0.1.0-alpha`) as
verified against the code. They're commitments about how DeckForge is
built, not just a description of how it happens to work right now.

---

## The promises

### 1. The core workflow works offline, with no account.

Opening a PDF, calibrating its card grid, reviewing suggested cards, and
exporting card images — DeckForge's entire day-to-day workflow — runs on
your own computer. No internet connection and no account are required.
That's true today, and it will stay true: whatever else DeckForge adds
later, this core workflow will keep working exactly as it does now,
fully offline.

### 2. Nothing about your deck — or you — leaves your computer automatically.

Your PDFs, the card images DeckForge exports, and the local diagnostic
log DeckForge keeps for itself are never transmitted anywhere. The
current app has no analytics and no telemetry, and it doesn't collect
personal information beyond what already lives on your own filesystem
(like the names of files and folders you choose to work with).

### 3. Diagnostic logs stay on your computer, and we're upfront about their limits.

DeckForge keeps a small rotating log file on your own machine to help
diagnose problems — never uploaded, never sent anywhere. In normal use,
it records short, descriptive names, not full file paths. When
something genuinely unexpected goes wrong, though, the crash detail we
capture can still include a full file path — for example, a folder name
you chose, or your Windows username as part of DeckForge's own install
location. If you ever share `deckforge.log` publicly (say, in a bug
report), skim it first.

### 4. Any future feature that sends data off your device will be optional, and we'll say so first.

If DeckForge ever adds something that needs the network — exporting
straight to an online platform, for instance — it won't turn on by
default, it won't be required to use the core workflow above, and we'll
tell you plainly what it sends and why before it ever sends anything.

### 5. DeckForge only writes what you asked it to.

The only files DeckForge creates are the card images you export to the
folder you choose, plus its own local diagnostic log. It doesn't install
background services, doesn't create hidden data stores elsewhere on your
system, and doesn't need elevated permissions to run.

---

## For contributors: checking a change against these promises

These promises are a design constraint, not just a description. Before
adding or changing anything that touches file I/O, logging, or the
network, check it against:

1.  Does this cause DeckForge to send anything off the user's device
    that it didn't send before?
2.  If yes — is it off by default, and is the user told what's being
    sent and why *before* it happens?
3.  Does the core open → calibrate → review → export workflow still
    work fully with this turned off, or with no network connection at
    all?
4.  Does this add to what gets logged? If so, does normal-operation
    logging still avoid full file paths?
5.  If you're touching exception handling: are you preserving debugging
    value without silently expanding what a crash log can capture?
    Document the tradeoff instead of deciding it silently.
6.  Would a careful engineer who reads the *code* — not just this
    document — reach the same conclusion this document states? If not,
    fix the code or fix this document; don't leave them disagreeing.

If a change would make one of the five promises above false, that's not
necessarily a reason not to ship it — but it is a reason to update this
document in the same change, not after the fact. See
`ENGINEERING_STANDARDS.md`'s Definition of Done: "security and privacy
implications have been considered" means checked against this list.
