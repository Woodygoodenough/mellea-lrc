# Splitting this work between two agents

Two agents on one branch overwrite each other. This file defines a boundary so
they do not.

The split is deliberately unequal. **The primary agent decides what the system
asserts and what the numbers mean. The second agent supplies what those
decisions need.** That is not a comment on capability — it is that decisions of
the first kind require holding the whole project in view and being willing to
discard earlier work, and two agents doing that in parallel produce conclusions
that have to be reconciled rather than combined.

Head of `experiment/reference-dataset` when this was written: `9db046d`.

---

## 1. Which work goes where, and why

Looking at what actually moved this project, the useful line is not by
subsystem. It is between deciding and supplying.

**Decisions, which stay with the primary agent.** Every one of these was a
choice to discard or restate something rather than to add to it:

- deleting a working text-based margin rule after measuring it against the
  page geometry;
- adding two citations no reader can extract into the denominator, which took
  the headline score from 100% to 99.7%;
- rejecting a reporter-year check after all 37 of its findings turned out
  false;
- setting the boundary a pin-cite check may assert by reading 25 adjudicated
  records rather than by trusting a model.

None of these could have been split. Each needed the whole context, and each
made an earlier result worse on purpose.

**Supply, which is where a second agent adds hours without adding
reconciliation cost.** This is the work that was slow rather than difficult:
converting 109 PDFs, harvesting filings from the archive, waiting out the API
allowance, downloading bulk data, building fixtures, running a measurement
whose shape was already decided.

---

## 2. Setting up the second worktree

A git branch can only be checked out in one worktree, so the second agent needs
its own branch.

**Check what you branched from before doing anything.** A subagent given an
isolated worktree by the Agent tool is branched from the repository's default
branch, not from whatever the parent agent has checked out. The first subagent
run on this project was handed instructions referring to a module and a
function parameter that exist on `experiment/reference-dataset` and not on `main`;
it was working from `main` and correctly reported both as missing. It adapted
and the work was still usable, but only because it said so rather than guessing.

    git merge-base --is-ancestor experiment/reference-dataset HEAD && echo ok

If that fails, rebase or branch again from `experiment/reference-dataset` before
starting, and say in your report which base you used.

```bash
git fetch woody-fork
git worktree add ../mellea-lrc-b -b experiment/reference-dataset-b experiment/reference-dataset
cd ../mellea-lrc-b
uv sync
cp ../mellea-lrc/.env .          # secrets are gitignored and not carried by a worktree
git push -u woody-fork experiment/reference-dataset-b
```

Merge into `experiment/reference-dataset` when a piece is finished, not
continuously.

---

## 3. What the second agent does

Each item names what to produce and the shape it should arrive in. **Where a
task says "do not decide", it means produce the candidates and leave the call.**

### 3.1 Load the United States Code and answer one question

Report section 18. 642 of 704 statute citations in the corpora are federal and
parse into title, section and subsection. The Office of the Law Revision
Counsel publishes the Code as bulk XML with amendment history.

Produce: a local index answering *does this title and section exist*, and *is
it currently in force*, for a `(title, section)` pair. A module under
`src/mellea_lrc/statutes/`, with tests, and a short note in `handoff-b.md`
giving the base rate — how many of the 642 name a provision that is not there.

**Do not decide** what verdict a missing provision should produce, or how
statutes enter the validation pipeline. Report the counts.

### 3.2 Extend the corpus miner past the easy case

Report section 13. `scripts/miner/` finds sanctions orders and identifies which
filing an order accuses, when the order names a docket number. It does not
handle the case where the order names an attorney and a motion but no number —
"attorney Jason Castro had filed a motion littered with fabricated cases".

Produce: for each such order, a ranked list of candidate docket entries with
the evidence for each. The reference implementation at
`~/CodingProjects/caseSearchLangGraph/targets/` calls this the `docket_only`
tier and is worth reading first.

**Do not decide** which candidate is the offending filing where it is not
obvious, and do not add anything to the corpus. Produce candidates with
evidence; adjudication is a primary-agent task, and every corpus record so far
was settled by looking at the printed page.

### 3.3 Keep the cache filling and the infrastructure alive

The nightly job needs about three more runs to finish the 497 outstanding
lookups. Watch it, report the outcome counts, and fix it when it breaks — it
has broken twice, once because the proxy's refusal wording was not recognised
and once because a slow response ended the whole run.

**This is the highest-value item on the list**, because everything in the
semantic layer is blocked on cached pages and nothing else can proceed without
them.

### 3.4 Run measurements whose shape is already decided

Two are specified and unstarted:

- The invented-reporter count against Charlotin's tracker of AI-fabrication
  cases, which is an order of magnitude larger than our 54 records. Report
  section 10.3 says exactly what to count and what would change the decision.
- Of the 25 adjudicated misrepresentation records, how many would be caught by
  `different_subject` or `states_the_contrary` given the page. That is the
  recall ceiling for the semantic layer and it is currently unknown. Section 7
  of `exploration/notes/pinpoint-design.md` specifies it.

**Do not redesign the measurement.** If the specification looks wrong, say so
in `handoff-b.md` and stop.

---

## 4. File ownership

Nothing outside your own column may be edited, including to fix something
obviously wrong. Describe defects in the other track's files; do not repair
them.

| Path | Owner |
|---|---|
| `src/mellea_lrc/preprocessing/**` | primary |
| `src/mellea_lrc/extraction/**` | primary |
| `src/mellea_lrc/validation/**` | primary |
| `src/mellea_lrc/experimental/**` | primary |
| `evaluations/extraction/**` | primary |
| `scripts/corpus/**` | primary |
| `data/**` (gitignored, local) | primary |
| | |
| `src/mellea_lrc/statutes/**` (does not exist yet) | second |
| `scripts/miner/**` | second |
| `scripts/courtlistener/**` | second |
| `scripts/modal/**` | second |
| `evaluations/lephantomcite/**` | second |

Tests follow their module. Neither edits `README.md`, `pyproject.toml`,
`.gitignore`, `src/mellea_lrc/core/**` or `src/mellea_lrc/courtlistener/**`
without writing a handoff entry first.

The primary agent owns `validation/**` because the pin-cite redesign is the
largest open design question and section 17 of the report is the argument for
how it should work.

---

## 5. Shared resources

**The CourtListener allowance is one pool** — three tokens, 125 requests each
per day, shared by both worktrees through the same proxy. The **second agent
owns it**, because the nightly job and the miner both need it and the nightly
job is on a schedule. The primary agent does not spend quota without a handoff
entry first. The reserved fourth token, reached with the `x-cl-pool: reserved`
header, is for small targeted experiments and is not part of the main budget.

**The response cache is additive.** Anything either fetches is free for the
other afterwards. Nobody deletes from it.

**The report artifact** is written by the primary agent. The second agent does
not publish to it; findings go into `handoff-b.md` and are folded in. Two
agents publishing one page overwrite each other and the page loses its voice.

**`exploration/notes/`** — write your own files, never edit the other's.

---

## 6. Handoff files

`exploration/handoff-a.md` and `exploration/handoff-b.md`, appended to, newest
entry first. Write an entry when you finish something the other depends on,
find a defect in their files, need to touch a file you do not own, or learn
something that changes what they should do.

An entry gives the date, what happened, and what the other should do about it.

---

## 7. Rules both follow

- **Push to `woody-fork` only.** Never `origin`, never `main`.
- **The dataset stays local.** `data/` is gitignored and nothing under it is
  pushed anywhere.
- **No commit trailers crediting a tool**, and nothing sent on the user's
  behalf to anyone — not GitHub issues, not collaborators.
- **A citation shown to exist goes into the denominator**, even when that
  lowers a score.
- **Report what a number cannot show.** If a fix was made after seeing which
  case failed, the sentence reporting the score says so.
- **`exploration/writing-style.md`** governs anything written for a reader.
- Run `uv run pytest` and `uv run ruff check` before every commit. One test
  suite is shared, so a break in yours blocks the other.
