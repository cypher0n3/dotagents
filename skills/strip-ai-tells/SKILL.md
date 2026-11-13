---
name: strip-ai-tells
description: "Rewrites AI-sounding prose until it reads as human-written. Use this skill when a draft reads like AI wrote it: em dashes, colon splices, negative parallelism, empty intensifiers, slogan rhythm, and the same point restated across sections."
user-invocable: true
---
# Strip AI Tells

## When to Use

The user wants prose that reads as human-written.
Typical phrasings are "strip the AI tells", "de-AI this", "make this sound less like AI", "remove the em dashes", "this reads like ChatGPT wrote it", "humanize this draft", and "reads like an AI note to self".

This is not a full proofread, so grammar and ordinary punctuation stay out of scope.
Typos and misnamed people, organizations, products, and acronyms are in scope.

## Scope

Work on the whole document by default.
When the user has selected or named a section, restrict to it and say which range.

Leave quoted or copied material alone unless the user asked for a full sweep.
Say which sections you skipped and why.

## Make the Edits Reviewable

Turn on the editor's change tracking or revision mode before the first edit, when the environment has one.
Say in one line that you turned it on.
Never turn it off during the rewrite.

Make the edits silently only when the user asks.
A plain file under version control needs no extra step.
Read [Word and Office JS Mechanics](references/word-office-js.md) when the document is open in Word or when writing the file directly.

## Inventory Before Editing

Count each pattern in scope before changing anything.
Note names, typos, and figures in the same pass; [Check Names and Typos](#check-names-and-typos) and [Deliverable Defaults](#deliverable-defaults) cover them.
Do not re-read the document; the text is usually already in context.

### Punctuation and Glyphs

- Em dashes, every one in the document, except inside a required marking such as a draft or handling banner.
- En dashes used as separators.
  Date and number ranges stay.
- Colon splices, where a colon joins two independent clauses.
  List lead-ins, bullet labels, titles and subtitles, and labeled caveats are legitimate.
  Two colons in one sentence is always a hit.
- Symbol shorthand in prose: arrows, multiplication signs, inequality signs, check marks, and bullets standing in for words, such as "8x/day" or "source > destination".
- Mixed apostrophes or quotes: straight and curly forms in the same document.

### Word Choice

- "Not X but Y" parallelism: "rather than", "instead of", "it's not just X, it's Y", "not merely".
- Empty intensifiers and consultant filler: genuinely, actively, deliberately, organically, truly, simply, seamlessly, robustly, holistically, significant, substantial, comprehensive, leverage, foster, empower, streamline, "best practices".
- Triads and filler: three-item lists where two carry the meaning, plus "at minimum", "from day one", "going forward", "alike", "that said", "it's worth noting".

### Sentence Shape

- Tidy payoff tails: sentences ending on ", so" plus a payoff.
  A few are fine, and a run of them is the tell.
- Date-led openings: a sentence opening with a date or season in a document that is not a timeline.
  Move the date inside the sentence.
- Passive with a known actor.
- Counting lead-ins: a sentence announcing how many things follow.
- Moral tags: an abstract lesson tacked onto a fact.
  Cut it, or move the point to the section that already draws that conclusion.
- Notes to self: an instruction sitting in a narrative section.
  Tell what happened when the source supports it, or move or cut the instruction.
- Slogan runs: short sentences with the same rhythm in a row.
  Make them a list, or merge them into one or two sentences with different shapes.

### Document Shape

- Mid-sentence bold: emphasis phrases bolded inside a sentence.

Also note these, and change them only when the user directs it:

- Broken cross-references.
- Claims the document cannot support.
- Jargon repeated past usefulness.
- Metaphors that do not hold.
- The same finding restated in three or more places.
- Inconsistencies between parallel documents.
- Acronyms used before they are defined.
- Attribution you are unsure about.

Stop when you have a per-pattern count.

## Rewrite

Work section by section.
Make one edit per changed phrase, and batch related phrases only when there are many.

Recast each em dash and colon splice by what the join is doing.
Use a period when the halves stand alone, parentheses for an aside, a comma for apposition, and "by" or "which" for a gerund tail.
Leave a colon the inventory calls legitimate.

Vary the replacement.
If "rather than" or ", so" carries every contrast, half the sentences now share a rhythm.
Rotate through subordination, two sentences, or dropping the contrast.
Replacing every join with the same mark is its own tell.

Keep the replaced span minimal.
Change what needs changing plus enough neighbors to make the match unique.
Editors cap the length of a search string, so a long paragraph needs a distinctive fragment, never the whole thing.

Preserve meaning.
Dropping "deliberately" is fine.
Dropping the clause it modified is not.

Spell symbols out as words that match the rest of the document, such as "eight times per day" or "at least 1,000".
An arrow inside a file path can become `>`.

Never type list bullets or heading numbers into replacement text.
The document's list and heading formatting generates them, so a typed one doubles the marker.

Drop mid-sentence bold on emphasis phrases.

Stop when every counted instance is resolved or consciously kept.

## Check Names and Typos

### Use the Canonical List

Use a canonical list of names, titles, and acronyms when the user, repository, or project skill provides one.
Only formal documents feed or confirm it; the draft, a transcript, and meeting notes never do.
The list may record, per entry, known wrong forms that must never appear.
Search for each "never" form by full name, surname alone, and initials.

Ask about each name missing from the list or using an expansion the list does not give.
Correct directly only when the text is a plain spelling variant of a canonical entry or a "never" form mapping to exactly one entry.
Ask about everything else.

- Ask one at a time, in document order, showing exact text, location, surrounding words, and closest list entry.
- Offer to accept it, remove and reword (writing "TBD" where a name is still needed), or change to the closest entry or user's correction.
- Apply the answer to every instance in scope.
- In an unattended run, leave as written, highlight, and put at top of the flag list.

### Flag Name and Owner Problems

- Two spellings of the same name in one document.
- Wrong affiliation or role.
- Transcription artifacts: names or acronyms that look phonetically guessed.
- Look-alike acronyms: a real acronym one letter away from the right one, which passes a spell check.
- Missing or invented owners: an action, risk, decision, or quote with no owner or date, credited to someone the source does not name, or, in a handoff document, not saying which party carries it out.
  Write "TBD" where the source names no one, and never assign an owner yourself.

Fix misspellings, doubled words, and wrong-word substitutions such as their and there directly.
Leave intentional terms, product spellings, and quoted material alone.

Stop when every name is on the canonical list, asked about, or flagged, and no typo remains.

## Deliverable Defaults

Apply these when the document is a deliverable and the user has not said otherwise.

Credit actions to the group the document already uses, not to a named person.
Leave a person named when naming people is already that document's practice.
An identifier containing a name stays as-is.
Use the bare group name, not group plus role.

Keep the voice active, concise, and high information density, and keep rewrites light.

Run these checks, and flag what they find unless the item says to fix it.

- Figures: each one traces to the source, matches everywhere it appears, and adds up.
  Give both locations of a mismatch, and do not pick a winner.
- Dates: each weekday matches its computed date, a status document carries an "as of" date, and past deadlines read as past.
  Fix date format inconsistencies to the document's existing convention.
- Audience: settle whether the reader is internal or external, and ask when the markings, footer, and folder do not say.
  In an external document, flag internal-only content such as pricing, staffing talk, leftover comments and tracked changes, speaker notes, internal links, and personal data outside where the document allows it.
- Accessibility: images and charts have alt text, headings use heading styles, tables have header rows, color is never the only signal, and link text names its target.
  Add alt text when the content is clear.

## Watch for Formatting Leaks

Replacing a span inherits the formatting at the start of the range and flattens whatever was inside.
Check each batch before moving on.

Replacing text starting inside a bold run makes the whole insertion bold.
Clear bold on the portion that should not carry it.

Inline monospace tokens inside a replaced span come back in the body font.
Find each token, compare its font against a surviving instance, and restore it.

Match the document's existing apostrophe and quote style.
Search a known word with a straight apostrophe and again with a curly one; whichever matches is the house style.
Use it in every insertion, including where a word is split across text runs.

When you add a sentence or paragraph, copy the font, size, color, alignment, and spacing from a sibling paragraph of the same role.
For a new list item, copy the sibling item's paragraph style.
Do not rely on the style default.

When you touch a table, keep its header fill identical to the other tables.

Stop when reading the batch back shows the same fonts, weights, and fills.

## Re-Scan Until a Pass Finds Nothing

Re-run the inventory over the rewritten text, including phrases you introduced, especially ", so", "which", colons, and "by".
Include names, typos, and figures.
Fix what the pass turns up, then run it again.
Stop when a complete pass produces zero findings, not after a fixed number of rounds.
Two passes is the usual minimum.

## Verify, and Verify the Verifier

Run whatever visual or rendered verification the environment offers.
A tool inspecting a rendered or extracted copy reports predictable false positives, so fix only what you can confirm.

A lost hyphen on a word wrapping across a line is an extraction artifact.
A hard line break reported mid-paragraph is usually ordinary wrapping.
For a font, color, size, or spacing complaint, read the property off the paragraph and a sibling.
Matching values mean the finding is wrong.

Then, for a deliverable, check the file.

- No placeholder markers, such as "TBD", "TODO", "XXX", or lorem, outside a sentence legitimately using them.
  TBDs from the names step belong in the flag list.
- No Markdown leakage in a non-Markdown document: doubled asterisks, backticks, heading marks, or a bracketed link.
- The document title is set, and the author metadata is what the user expects.
- Cover, filename, footer, and revision history agree on version and date.
- Table of contents page numbers and cross-references are correct.
- Every rendered page looks right: headers and footers, page breaks, tables cut off at the edge, images that did not load.
- Tracked changes and comments are gone when the user wants a clean file.
  In that case, turn change tracking off in the handed-back file.

## Report

Keep the report short.

- One line of counts: which patterns came out, how many of each, including typos and names fixed, and how many passes.
- A flag list under a bold header.
  One line each, with location, for every item noted and not changed, with unanswered name questions first.
- Names the user confirmed or corrected, ready to add to the canonical list with source and date.

Never silently fix a factual or structural problem.
