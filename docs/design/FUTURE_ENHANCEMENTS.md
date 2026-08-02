# Future Enhancements

This document captures product improvements discovered through
real-world use of **CardLift**.

Items in this document are intentionally **not commitments**. They exist
so valuable ideas uncovered during development, testing, and day-to-day
use are not be lost. They should be reviewed periodically when planning
future releases.

------------------------------------------------------------------------

# Workflow Accelerators

## Pattern-Based Page Assignment

**Status:** Idea

### Problem

Many print-and-play products follow predictable page layouts. Assigning
Front and Back roles page-by-page becomes repetitive and unnecessary.

### Examples

-   Odd pages = Front, Even pages = Back
-   Odd pages = Back, Even pages = Front
-   First half of the document = Front, Second half = Back
-   Apply the remaining unassigned pages as Front
-   Apply the remaining unassigned pages as Back

### Design Principle

Automate common page-assignment patterns while **always preserving full
manual control**. These actions should be accelerators---not
replacements---for the existing workflow.

### Possible User Experience

An **Assign Pages...** action could eventually include:

-   Every page as Front
-   Odd = Front, Even = Back
-   Odd = Back, Even = Front
-   First half = Front, Second half = Back
-   Clear assignments

Users could then make any exceptions manually using the existing
page-selection interface.

### Discovery

This enhancement was identified while testing **Multiple Back Modes**
using the **Doom Pilgrim** deck. It would dramatically reduce repetitive
clicking for many common print-and-play products while leaving unusual
layouts fully supported.

------------------------------------------------------------------------

# Candidate Enhancements

Additional ideas discovered during development or testing should be
added here rather than buried in chat history or implementation
documents.

Each enhancement should include:

-   Status
-   Problem
-   Design Principle
-   Possible User Experience
-   Discovery / Context
