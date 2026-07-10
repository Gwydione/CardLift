# DeckForge Engineering Standards

## Purpose

DeckForge is intended to become a publicly released desktop application
for tabletop gamers.

These standards exist to ensure that every change improves the software
without sacrificing quality, maintainability, security, or user trust.

The goal is not simply to make DeckForge work.

The goal is to make DeckForge a product that other people can
confidently install, use, and contribute to.

------------------------------------------------------------------------

# Core Philosophy

Implementation quality is as important as functionality.

AI is used as an implementation assistant, not as an architectural
authority.

Every contribution---whether written by a person or generated with
AI---should meet the same engineering standards.

------------------------------------------------------------------------

# Engineering Priorities

When tradeoffs are required, optimize for:

1.  Correctness
2.  Maintainability
3.  Security
4.  Privacy
5.  Testability
6.  Readability
7.  Performance
8.  Development speed

Fast code that is difficult to understand or maintain is not a
successful outcome.

------------------------------------------------------------------------

# Architecture

Respect existing architecture.

Do not redesign stable components simply because another implementation
is possible.

Before proposing a significant refactor:

-   identify the problem
-   explain why it matters
-   explain the tradeoffs
-   recommend the smallest change that solves the problem

Prefer composition over duplication.

Keep responsibilities focused.

Avoid unnecessary coupling between modules.

The GUI should call the engine---not duplicate it.

------------------------------------------------------------------------

# Code Quality

Prefer:

-   simple code over clever code
-   explicit behavior over implicit behavior
-   readable names over abbreviations
-   small focused functions
-   cohesive modules
-   meaningful comments that explain why, not what

Avoid speculative abstractions.

Implement functionality because it is needed---not because it might
someday be useful.

------------------------------------------------------------------------

# Security

Treat all external input as untrusted.

Validate inputs.

Fail safely.

Provide friendly user-facing error messages while preserving useful
technical detail for debugging.

Avoid introducing unnecessary attack surface.

------------------------------------------------------------------------

# Privacy

DeckForge is a local-first desktop application.

Unless explicitly approved, do not introduce:

-   telemetry
-   analytics
-   cloud processing
-   background network requests
-   unnecessary data collection

Users should be able to trust that their PDFs remain on their own
computer.

------------------------------------------------------------------------

# Dependencies

Introduce new dependencies conservatively.

Before adding one, ask:

-   Is it necessary?
-   Is it well maintained?
-   Does it increase packaging complexity?
-   Does it introduce security or licensing concerns?

Favor fewer, well-supported dependencies.

------------------------------------------------------------------------

# Testing

Protect existing behavior.

Whenever practical:

-   add tests for new non-trivial logic
-   preserve regression tests
-   avoid reducing test coverage
-   verify the full test suite passes

Visual changes should also be verified manually.

------------------------------------------------------------------------

# AI Collaboration

AI should assist implementation---not replace engineering judgment.

Before implementing significant work:

-   understand the existing architecture
-   review the documentation
-   propose an approach
-   identify risks
-   ask questions when requirements conflict

Avoid broad speculative refactors.

Generated code should be understandable enough that a human contributor
can confidently maintain it.

------------------------------------------------------------------------

# Documentation

Keep documentation synchronized with implementation.

When architectural or workflow decisions change:

-   update documentation
-   keep examples current
-   record important design decisions

The repository should remain the primary source of truth.

------------------------------------------------------------------------

# Definition of Done

A feature is complete when:

-   functionality meets the intended user experience
-   architecture remains clean
-   documentation reflects the change
-   tests pass
-   new behavior is appropriately tested
-   security and privacy implications have been considered
-   the implementation is something the team would be comfortable
    maintaining for years

------------------------------------------------------------------------

# Guiding Principle

> Build software that future contributors---including your future
> self---will be grateful to inherit.
