# Deciding what a citation refers to, and when it is made up

23 August 2026. Two questions that have to be answered together, because
neither has an answer on its own: when a citation's name and its locator
disagree, which one is the citation *about*; and what would have to be true
before we are entitled to say a citation was invented rather than mistaken.

## 1. A citation is over-determined, and that is what makes this decidable

`Anderson v. Liberty Lobby, Inc., 447 U.S. 242, 106 S. Ct. 2505, 91 L. Ed. 2d
202 (1986)` carries eight independently checkable fields: two party names, a
volume, a reporter, a page, two parallel citations, and a year. A court and a
pin cite are common on top of that.

Each field is a separate claim about the same document. That redundancy is the
resource. A citation with a single field could only ever be right or
unresolvable; a citation with eight can be *diagnosed*, because the fields
disagree with each other in a specific pattern.

## 2. The referent is the reading that leaves the fewest fields wrong

The question "is the name the citation, or is the locator" has no general
answer and does not need one. It is settled per citation by counting.

**The referent is the document that the largest number of independent fields
agree on.** Every other field is then the defect.

Two worked cases, both real, both from `aux_train`:

| citation as written | fields pointing at | fields pointing elsewhere | referent | defect |
|---|---|---|---|---|
| *Anderson v. Liberty Lobby*, **447** U.S. 242, 106 S. Ct. 2505, 91 L. Ed. 2d 202 (1986) | 477 U.S. 242 — name, page, both parallel cites, year | volume `447` | *Anderson* | wrong volume |
| *Heartland Regional Med. Ctr. v. **Sebelius***, 415 F.3d 24 (D.C. Cir. 2005) | 415 F.3d 24 — volume, reporter, page, court, year, and the first party | second party `Sebelius` | the case at 415 F.3d 24 | wrong party |

This is not a guess about what the drafter meant. It is a statement about
evidence: one field being wrong is a commoner event than six being wrong, and
the reading that requires fewer independent errors is the better-supported one.
It is the same principle a spelling corrector runs on, applied to a record with
eight columns instead of one string.

Two consequences worth stating:

- **The rule is refusable.** When the fields split evenly — a name resolving to
  one case and a locator resolving to another, with nothing else to break the
  tie — there is no referent and the correct output is that there is none. A
  two-field citation is often exactly this, and it is why bare `name, volume
  reporter page` is the hardest shape in the corpus.
- **The rule needs the name recorded verbatim.** Counting fields is impossible
  if one of the fields was never captured. This is what
  `derived/case_names.jsonl` exists for, and it is why the name has to be the
  filing's own text rather than an archive's — a name fetched from the archive
  agrees with the archive by construction and contributes no count.

## 3. "Made up" is a verdict about a search, not about a citation

Fabrication cannot be observed. Only failure to find can be observed. So the
definition has to name the search that failed and state its reach:

> A citation is **fabricated** when no reading of it reaches a real document,
> and the searches that established this were capable of finding one had it
> existed.

The second clause carries the whole weight. Without it, "fabricated" means
"absent from whatever we happened to query", which is a fact about the corpus
and is repeatedly false — 68 of 90 unresolved citations in this project are
real cases published only in Westlaw and LEXIS.

## 4. Three searches, and why one is never enough

| search | question it answers | can it confirm? | can it refute? |
|---|---|---|---|
| **locator** — lookup by volume, reporter, page | is there a case at this address | no — the service normalises a mid-case page to its covering case and reports it sound | yes — a page that sits *inside* another case is positive evidence |
| **name** — party or full-text search | does a case by this name exist at all | yes | no — absence from a corpus is a fact about the corpus |
| **metadata** — court plus year plus parties | does a case of this shape exist | weakly | no |

The confirm/refute columns are opposite for the first two rows, and that
opposition is the design. A fabrication claim needs **a refutation from the
locator side and a silence from the name side**, and the silence only counts
when the corpus is known to cover the claimed court and year. Where coverage
cannot be established, the honest verdict is `unresolvable`, not `fabricated`.

This is what makes fabrication "earn its position", to use the phrasing that
prompted this: it is the strictest claim in the taxonomy and it costs three
searches, while a mismatch costs one.

## 5. One tier that costs no search at all

Before any of the above: **a locator can name a namespace that does not
exist.** `531 N.E.4th 224`, `423 F.5th 938`, `671 F. Supp. 4th 395` — no such
reporter series was ever published, so no document can sit at those addresses
and no corpus needs consulting to know it.

All **126** `non_existent_citation` labels in `aux_train` are this shape. They
are the cheapest and most certain findings available, and they are currently
invisible because eyecite does not type an unknown series as a citation at all.
Reaching them is a rule about the reporter table, not a retrieval problem.

The same tier catches an impossible combination of real fields: `F.2d` ended in
1993, so `739 F.2d 131 (4th Cir. 2014)` is refuted by arithmetic. Section 3 of
`unrecorded-defects.md` has three of these that are real drafting errors.

## 6. The proposed labels

The corpus's current `non_existent_citation` conflates section 3 and section 5,
which have completely different evidential standing. Splitting them:

| label | when |
|---|---|
| `sound` | a referent exists and every field agrees with it |
| `impossible` | the reporter series does not exist, or the fields contradict each other by arithmetic — no search performed |
| `wrong_locator` | the name is the referent; one or more of volume, reporter, first page or pin cite disagrees |
| `wrong_description` | the locator is the referent; a party, court or year disagrees |
| `ambiguous` | fields split evenly and no referent is better supported |
| `unresolvable` | nothing resolves, and at least one of the three searches lacked reach |
| `fabricated` | nothing resolves, and all three searches had reach |

Every label above `sound` should carry the field that disagreed and the field
count that decided the referent, because a verdict that does not say which
field it convicted cannot be checked by a reader and cannot be appealed.

## 7. What this changes in the code

1. **The name check and the first-page check currently answer separately.** They
   are two of the eight fields. They should feed one referent decision rather
   than each emitting a verdict, or the same citation gets convicted twice for
   one error.
2. **Parallel citations are unused and are the cheapest strong evidence.** Both
   *Anderson* defects in section 2 are decided by them alone, offline, with no
   allowance spent. Nothing in the project reads them today.
3. **Coverage has to become a queryable property.** Section 3's second clause
   is unenforceable until a search can state which courts and years it covers.
   Until then no `fabricated` verdict is defensible and the label should not be
   emitted at all.
4. **`impossible` needs no retrieval and is not built.** It is the largest
   single label class in `aux_train` and the cheapest to reach.
