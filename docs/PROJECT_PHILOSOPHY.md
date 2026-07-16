# Project Philosophy

## Why This Document Exists

CardLift began as a personal tool to solve a frustrating problem:
extracting cards from print-and-play PDFs should not require
image-editing expertise, complicated workflows, or hours of repetitive
manual work.

As the project matured, it became clear that this was software that
other people might choose to trust with their time, their files, and
their feedback.

This document explains the principles that guide the project.

It is not a legal document or a technical specification. Those topics
are covered elsewhere in the project's documentation.

Instead, it describes the values that influence how CardLift is
engineered, maintained, and shared.

------------------------------------------------------------------------

## Why CardLift Exists

CardLift exists to make complicated PDF extraction feel simple.

The project is intentionally focused on a narrow problem: helping
tabletop gamers transform print-and-play card PDFs into clean, organized
image files suitable for virtual tabletops, digital play, or personal
use.

The goal is not to become a general-purpose PDF editor, graphics
application, or image-processing tool.

Every feature should make this workflow simpler, more reliable, or more
approachable. Features that do not directly support that goal should be
carefully questioned before being added.

When new ideas compete with that focus, simplicity takes precedence over
feature count.

------------------------------------------------------------------------

## Scope Before Features

CardLift is intentionally specialized.

Its purpose is to solve one workflow exceptionally well rather than many
workflows adequately.

Ideas that expand beyond the project's core purpose should be evaluated
carefully. A feature is valuable only if it strengthens the primary
workflow without making the application more difficult to understand or
maintain.

Choosing not to implement a feature is often as important as choosing to
implement one.

The project values clarity over flexibility, focus over breadth, and
consistency over novelty.

------------------------------------------------------------------------

## AI-Assisted Engineering

CardLift is developed using modern AI-assisted engineering practices.

Artificial intelligence is treated as a professional engineering tool
rather than an autonomous software developer. AI is used to explore
ideas, review designs, identify potential defects, challenge
assumptions, improve documentation, and assist with implementation.

**Human judgment remains the final authority for engineering
decisions.**

AI recommendations are treated as engineering input---not engineering
fact. Suggestions are expected to be questioned, verified, tested, and,
when appropriate, rejected.

Engineering decisions are informed by evidence, independent review,
testing, and experience. The goal is not to replace engineering judgment
with AI, but to improve engineering judgment through thoughtful
collaboration, critical evaluation, and verification.

The software produced by this project remains the responsibility of the
humans who choose to build, review, and release it.

------------------------------------------------------------------------

## Engineering Before Popularity

CardLift is guided by a simple principle:

**Stability and functionality are more valuable than feature count.**

The project intentionally favors careful engineering over rapid
expansion.

New features are welcomed when they improve the core workflow, but they
should not come at the expense of reliability, maintainability, or user
trust.

This philosophy influences how the project is developed.

Significant changes are reviewed before they are implemented whenever
practical. Engineering decisions are documented when they are expected
to influence future development. Problems are investigated before
solutions are chosen, and testing is considered part of implementation
rather than something added afterward.

The project intentionally prefers a smaller, well-understood application
over a larger application whose behavior is uncertain.

Features may be postponed if they cannot yet be implemented with
sufficient confidence or quality.

------------------------------------------------------------------------

## Respect the User

Every interaction with CardLift should demonstrate respect for the
person using it.

That means respecting:

-   their time
-   their files
-   their privacy
-   their expectations
-   their trust

The application should communicate clearly whenever practical. Users
should understand what the software is doing, why it is doing it, and
what to expect next.

Errors should be honest. Limitations should be acknowledged rather than
hidden. Recovery from mistakes should be straightforward whenever
possible.

CardLift should avoid unnecessary complexity, surprising behavior, and
collecting information unrelated to its purpose.

Users are not expected to understand PDF rendering, image processing, or
calibration algorithms. The software exists to make those technical
details approachable while producing reliable results.

------------------------------------------------------------------------

## Sharing the Project

CardLift is being shared because it is intended to be useful to the
tabletop gaming community.

The decision to make the project available is intended to benefit the
tabletop gaming community, not to maximize downloads, build a large
contributor community, or create a commercial product.

Users should feel comfortable understanding how the application works,
how it handles their files, and how engineering decisions are made.

Openness is intended to build trust through transparency, not simply
because it is common practice.

------------------------------------------------------------------------

## Maintaining CardLift

CardLift is maintained by a single developer in his spare time.

Bug reports, suggestions, and constructive feedback are always
appreciated.

Contributions may be welcomed, but acceptance is not guaranteed. Every
proposed change should be evaluated against the principles described in
this document and the long-term health of the project.

The project makes no promises regarding feature schedules, issue
response times, or release frequency.

Sustainable maintenance is more important than rapid development.

------------------------------------------------------------------------

## Licensing and Distribution

CardLift depends on several outstanding open-source projects, and their
work makes this application possible.

The project is committed to respecting both the legal requirements and
the spirit of those licenses.

Licensing decisions should support the long-term goals of the project,
provide appropriate credit to third-party software, and allow users to
understand both their rights and their responsibilities.

The legal details of licensing, attribution, and redistribution are
documented separately in the project's LICENSE and NOTICE files.

------------------------------------------------------------------------

## Looking Forward

CardLift will continue to evolve.

Features will change.

Platforms will expand.

Implementation details will improve.

The principles described in this document are intended to endure.

They represent the standards against which future decisions should be
measured.
