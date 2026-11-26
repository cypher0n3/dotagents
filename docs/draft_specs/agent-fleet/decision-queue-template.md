# Operator Decision Queue

## Overview

This is a template for the lead agent's operator decision queue.
Location: `agent_files/lead/decision-queue.md`

## Open Decisions

Each decision card includes an ID, description, options, recommendation, and silent default.

### Decision Format

```text
## D001: [Short Title]

**Context:** Brief description of what requires a decision.

#### Decision Format Options

- A: First option with brief description.
- B: Second option with brief description.
- C: Third option with brief description.

**Recommendation:** Option [A/B/C].

**Reason:** One sentence explaining the recommendation.

**Silent Default:** What happens if no answer arrives within [timeframe].
Work [continues/pauses/redirects] with assumption [X].

**Status:** OPEN | ANSWERED [date] | SUPERSEDED

**Answer:** [Recorded answer when resolved]
```

## Example Decision Cards

These examples demonstrate the decision card format.

### D001: API Rate Limit Strategy

Context: The external API has a rate limit of 100 requests per minute.
Current usage peaks at 120 requests per minute during batch operations.

#### D001 Options

- A: Add request queuing with backoff when rate limit hit.
- B: Reduce batch size to stay under limit.
- C: Request rate limit increase from API provider.

Recommendation: Option A.

Reason: Queuing provides automatic adaptation and handles temporary spikes.

Silent Default: If no answer arrives within 24 hours, work continues with Option A implemented.

Status: OPEN

### D002: Test Coverage Target

Context: Current test coverage is 85 percent.
CI enforces minimum 80 percent.

#### D002 Options

- A: Raise CI minimum to 90 percent.
- B: Keep CI minimum at 80 percent, aim for 90 percent without enforcement.
- C: Raise CI minimum to 95 percent.

Recommendation: Option A.

Reason: 90 percent is achievable and provides good defect detection without perfection paralysis.

Silent Default: If no answer arrives within 48 hours, work continues with CI minimum unchanged at 80 percent.

Status: OPEN

## Resolved Decisions Archive

Move resolved decisions here with their final answers and resolution dates.

### D000: Example Resolved Decision

Context: Example of a resolved decision.

#### D000 Options

- A: First option.
- B: Second option.

Recommendation: Option A.

Reason: Example reason.

Silent Default: Example default.

Status: ANSWERED 2026-11-20

Answer: Option A selected by operator on 2026-11-20.
Implementation completed in commit abc123.

## Review Checklist

Before publishing a decision queue cut:

- [ ] Every decision card has a unique ID.
- [ ] Every decision has a clear context.
- [ ] Every decision lists at least two options.
- [ ] Every decision has a recommendation with reason.
- [ ] Every decision has a silent default that does not strand work.
- [ ] Every decision marked ANSWERED has been verified against owning unit's RESOLVED sections.
- [ ] No phantom decisions (copies without corresponding open questions in owning units).
- [ ] All resolved decisions moved to archive with dates and answers.

## Staleness Scan Triggers

A landed operator answer triggers a staleness scan:

1. Find all decision cards blocked on that answer.
2. Update their status to ANSWERED.
3. Find all todo board items blocked on those decisions.
4. Re-evaluate their blockers and dispatch if no other blocker remains.
5. Move resolved decision cards to archive.
