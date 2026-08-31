# The citation tree: short forms as their own claims

A brief for whoever takes this on. The module is on this branch and its tests
pass against `main`. It is **not wired into the pipeline**, and wiring it in is
the work.

## 1. What it does

A filing does not cite an authority once. It cites it in full, then returns to
it as `Id. at 570`, `550 U.S. at 563`, or by party name — and each return visit
usually names a **different page** and attaches a **different proposition** to
it.

`build_citation_tree` resolves every citation, transitively, to the full
citation that introduced its authority. `Id.` may point at a short form that
points at the full citation, and the chain is followed.

## 2. Why it is worth doing

**Validating only full citations checks one claim per authority and skips every
other claim made about it** — which is the larger part of what a brief actually
asserts. An authority cited at pages 563, 570 and 578 is three distinct claims
about three distinct pages, each verifiable on its own and each capable of
being wrong on its own.

Two properties follow:

- Identity is resolved once per authority, not once per occurrence. Ten
  references to one case cost one lookup.
- Pinpoint claims multiply, which is the point.

This connects to a gap measured elsewhere. The reference dataset labels three
citation-shaped defect classes at roughly even weight, and **wrong pincite is
the largest at 39%** — the one class the hallucination miner cannot see at all,
because an order quotes the citation and not the passage. See section 8.9 of
`exploration/AUDIT.md` on `experiment/reference-dataset`. The tree is the structure
that makes those claims addressable.

## 3. What the module already gets right

**Nothing is invented.** A citation eyecite could not attribute is reported
rather than guessed at, because attaching a claim to the wrong authority checks
it against the wrong page.

**Two failures that look alike in a count mean opposite things**, and they are
reported separately:

- *out of scope* — positive evidence the citation names something other than a
  case: a statute, a journal article, an unparseable span, or an `id.`
  resolving to one of those. On false-citation-bench this is 252 of 894, and
  every one is correct behaviour.
- *unattributed* — no such evidence. A case citation that could not be traced,
  or a reference that reached no antecedent. On the same corpus this is 20, and
  it is the number that measures the tree.

Reporting those as one figure would read as a 30% failure rate for what is, in
case citations, one. Read individually the 20 are defensible: one real short
form quoted inside another case's parenthetical and never given in full, and
nineteen `Id.` of which seventeen carry a paragraph pin cite and are probably
references into a pleading's own numbered allegations. That evidence is
deliberately not acted on, because several state courts number opinion
paragraphs in the public-domain format.

## 4. What to build

1. **Wire the tree into extraction**, so a `ValidatedDocument` carries
   occurrences grouped under their authority rather than a flat list.
2. **Make each occurrence its own pinpoint claim.** The identity lookup happens
   once for the authority; the pinpoint check runs per occurrence, against that
   occurrence's own page and its own proposition.
3. **Measure what that adds.** How many additional checkable claims does a real
   filing contain once short forms are counted? On the corpus, how many of them
   fail? That number has not been measured and is a finding either way.

## 5. One thing to know before you start

The original commit also touched
`src/mellea_lrc/validation/pinpoint_retrieval/reporter_page.py`, and **that file
has since been reworked on `main` by PR #80** (locator parsing and grounding).
Cherry-picking the original commits onto `main` conflicts there. This branch
therefore carries only the self-contained module and its tests; the pinpoint
side needs to be redone against the current `reporter_page.py` rather than
lifted.

The original commits, if you want to read what was done there, are `9ed7161`
and `85e3310` on `experiment/reference-dataset`.

## 6. Standing constraints

Nothing is committed or pushed to `origin`; work goes to `woody-fork`. No
dataset is pushed anywhere — everything under `local/` is git-ignored.
