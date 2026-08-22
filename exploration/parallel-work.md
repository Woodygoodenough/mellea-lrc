# Splitting this work between two agents

Two agents working the same branch will overwrite each other. This file defines
a boundary so they do not. Read it before starting, and treat the file
ownership table as binding rather than advisory.

Current head of `experiment/lephantomcite` when this was written: `ccfe54c`.

---

## 1. Setting up the second worktree

A git branch can only be checked out in one worktree, so the second agent needs
its own branch. From the main checkout:

```bash
git fetch woody-fork
git worktree add ../mellea-lrc-b -b experiment/lephantomcite-b experiment/lephantomcite
cd ../mellea-lrc-b
uv sync
cp ../mellea-lrc/.env .          # secrets are gitignored and not carried by the worktree
```

Push only to `woody-fork`, never to `origin`:

```bash
git push -u woody-fork experiment/lephantomcite-b
```

Both branches merge back into `experiment/lephantomcite` when a piece of work
is finished, not continuously.

---

## 2. File ownership

Nothing outside your own column may be edited, including to fix something
obviously wrong in it. If you find a defect in the other track's files, write it
down in your handoff file (section 5) and leave the code alone.

| Path | Owner |
|---|---|
| `src/mellea_lrc/preprocessing/**` | **A** |
| `src/mellea_lrc/extraction/**` | **A** |
| `src/mellea_lrc/experimental/relaxed_eyecite_extractor.py` | **A** |
| `src/mellea_lrc/experimental/page_crops.py` | **A** |
| `src/mellea_lrc/experimental/layout_review.py` | **A** |
| `evaluations/extraction/**` | **A** |
| `scripts/corpus/**` | **A** |
| `data/false-citation-bench-v2/**` (gitignored, local) | **A** |
| | |
| `src/mellea_lrc/validation/**` | **B** |
| `src/mellea_lrc/statutes/**` (does not exist yet; B creates it) | **B** |
| `src/mellea_lrc/experimental/grounded_adjudication/**` | **B** |
| `evaluations/lephantomcite/**` | **B** |
| `scripts/miner/**` | **B** |
| `scripts/courtlistener/**` | **B** |
| `scripts/modal/**` | **B** |

Tests follow their module: a test file named after a module belongs to that
module's owner. `tests/test_margin_line_numbers.py` is A's,
`tests/test_lephantomcite_locator_probe.py` is B's. A new test file belongs to
whoever owns the code it tests.

**Neither track edits** `README.md`, `pyproject.toml`, `.gitignore`,
`src/mellea_lrc/core/**`, or `src/mellea_lrc/courtlistener/**` without saying so
in the handoff file first. Those are small, shared, and where a silent conflict
would hurt most.

---

## 3. What each track is doing

### Track A — reading the document

Getting citations out of a PDF correctly, and keeping the test set honest.

- Citations split across table cells (report section 12). Two are known, both
  verified on the page, and neither is reachable by any change to the citation
  reader. Options are Docling's table settings, reading table regions from the
  page image, or accepting the loss and recording it.
- Page headers that Docling labels inconsistently, extending the rule in 4.4.
- Keeping the answer key correct: every disagreement between readers settled
  against the printed page, and every citation shown to exist added to the
  denominator.
- Whatever comes out of GitHub issue #79 that touches extraction.

### Track B — checking the citation

Everything after a citation has been found.

- **Pin cite redesign**, report section 17. The design is written in
  `exploration/notes/pinpoint-design.md` and is the largest single piece of
  open work. Split the one verdict into the sequence in section 5 of that note,
  so the deterministic answers are reached before a model is asked anything.
- **Statute checking**, report section 18 and
  `exploration/notes/statute-validation.md`. Entirely new code. Start with
  whether a federal provision exists, from the United States Code bulk XML.
  642 of 704 statute citations in the corpora are federal and parse cleanly.
- **The corpus miner**, report section 13. `scripts/miner/` finds sanctions
  orders and identifies which filing they accuse. The open piece is the case
  where an order names an attorney and a motion but no docket number.
- The nightly cache job and the Modal proxy.

---

## 4. Shared resources and the rules for them

**The CourtListener allowance is one pool, not two.** Three tokens, 125
requests each per day, shared by both worktrees through the same proxy. Track B
owns it, because the miner and the cache job both need it. **Track A must not
run anything that spends quota** without B agreeing first — a single sweep can
take the whole day's budget and leave the nightly job with nothing.

The reserved fourth token exists for small targeted experiments. Ask for it with
the `x-cl-pool: reserved` header rather than taking from the main pool.

**The response cache is shared and additive.** Anything either track fetches is
stored and free for the other afterwards. Nobody deletes from it.

**`exploration/notes/`** — write your own files, never edit the other's. Name
them for their subject.

**The report artifact** at `claude.ai/code/artifact/8c8acdcc-c9da-4588-a683-a49795764d7f`
is written by **A**. B does not publish to it. B writes findings into
`exploration/handoff-b.md` and A folds them into the report, which keeps a
single voice and avoids two agents overwriting one page.

---

## 5. Handoff files

Each track keeps one file, appended to rather than rewritten, newest entry
first. These are how the two tracks talk.

- `exploration/handoff-a.md`
- `exploration/handoff-b.md`

Write an entry when you:

- finish something the other track's work depends on;
- find a defect in the other track's files (describe it, do not fix it);
- need to touch a file you do not own;
- learn something that changes what the other track should do.

An entry gives the date, what happened, and what the other track should do
about it, if anything.

---

## 6. Rules both tracks follow

- **Push to `woody-fork` only.** Never to `origin`, and never to `main`.
- **The dataset stays local.** `data/` is gitignored and nothing under it is
  pushed anywhere.
- **No commit trailers crediting a tool**, and no messages sent on the user's
  behalf to anyone — not GitHub issues, not collaborators.
- **A citation shown to exist goes into the denominator.** If a check finds a
  real citation no reader extracts, it is added to the answer key and the
  scores are restated, even when that lowers them.
- **Report what a number cannot show.** If a fix was made after seeing which
  case failed, the sentence reporting the score says so.
- **`exploration/writing-style.md`** governs anything written for a reader.
- Run `uv run pytest` and `uv run ruff check` before every commit. Both tracks
  share one test suite, so a break in yours blocks the other.
