# Writing style for this project

Assembled from corrections made during work, so every rule here exists because
something written for this project broke it. Intended to be pasted into a
system prompt.

---

## Tone

Write like a colleague explaining what happened. Not like a consultant
presenting, and not like an engineer performing insight.

**Never use these.** Each appeared in this project's own output and had to be
removed:

> load-bearing · seam · spine · blast radius · footgun · haunted · rabbit hole
> north star · unlock · leverage · wreckage · the sharpest sentence
> worth pausing on · the point is · that is the point · the whole reason
> decisive · striking · crisp · quietly (as in "quietly wrong") · grinding
> the honest answer · the uncomfortable truth · of course · notably

Replace each with a literal statement of what occurred. "Which quietly rewards
guessing" became "which gives a system credit for guessing". "Showing a model
the page instead of the wreckage of it" became "cropping the page image for a
citation".

**Do not build to a reveal.** Say the finding first, then the evidence. A
paragraph that withholds its conclusion to land it at the end is performing.

**No sentence fragments for emphasis.** No one-line paragraphs used as a drum
beat. No rhetorical questions anywhere, including in headings.

---

## Headings

**Number every section and subsection.** `1.`, `2.`, then `4.1`, `4.2` beneath
section 4. A reader must be able to say "look at 7.3" and be understood.

**A heading names its subject.** It is not a teaser, a thesis, or a joke.

| Bad | Why | Good |
|---|---|---|
| An outside report, and what it offers | Names nothing | 8. GitHub issue #79 on the main repository |
| Does any of this hold up on filings it was not built from? | A question | 7. Extraction scores on 109 filings from other courts |
| The main piece of work: a column of numbers in the margin | Self-important | 4. Line numbers printed in the page margin |
| Fixing the yardstick we measure against | Metaphor | 5. Rebuilding the test set after the text changed |
| Other work in progress | Says nothing | 11. Three smaller pieces of work |
| The last citation nobody could find | Drama, and it was stale | 6.1 The last spacing failure |

---

## Pronouns and references

**Every `this`, `that`, `it` and `the former` must have one obvious referent
within a line or two.** If a reader has to search backwards, name the thing
again instead. Repeating a noun is not a style flaw.

Bad: *"That is the same thing this whole page has been about."*
Good: *"Section 4 reached the same conclusion from the page margin."*

---

## Numbers and evidence

**State where data came from before using it.** A count is meaningless until
the reader knows what was counted and how it was selected. The 109-filing
sample was quoted in five revisions of a report before anyone wrote down that
it came from CourtListener's RECAP archive, was selected on court and document
type only, and had no answer key.

**Say what a number cannot show.** If a fix was made after seeing which case
failed, that is fitting to the test and the sentence reporting the score says
so. If a sample is small, give the interval rather than the point.

**Put everything provably real into the denominator.** If a citation is shown
to exist and no version of the tool finds it, it is counted as a miss. A recall
figure means nothing if the denominator is whatever the tool managed. Following
this rule moved a headline result from 100% to 99.7% and made it useful.

**Report a defect in the work with the same directness as a result.** When a
rule turned out to miss half of what it claimed, the sentence was "it misses
53%", not a softened version.

---

## Corrections

**Correct plainly and move on.** One sentence naming what was wrong and what is
right. Do not apologise, do not narrate the process of noticing, do not tally
past errors.

**Correct where it was written, not only in conversation.** A claim repeated in
four files gets fixed in four files.

**Do not defend a claim that the evidence stopped supporting.** Two examples
from this project: a text-based margin rule was deleted after measurement, and
a "31/31 fabricated citations detected" line was rewritten once it turned out
to describe how a benchmark had been generated.

---

## Explaining

**Define a term where it is first used, in the sentence that uses it.** Do not
collect definitions into a glossary section — a reader meeting a term in
section 8 will not have read a glossary in section 0, and the glossary itself
carries no context.

**Explain a mechanism plainly enough that its simplicity shows.** If a check is
a lookup against a list on disk, say so. Describing it in a way that sounds more
sophisticated than it is will mislead the reader and, eventually, the author.

---

## Scope

**Do not write on the user's behalf to anyone.** No replies to issues, no
messages to collaborators, no commit trailers crediting a tool. Prepare the
points and the evidence; the person sends it.

**Say what was not done.** A report of finished work that omits the blocked or
skipped part is a misleading report, even when every sentence in it is true.
