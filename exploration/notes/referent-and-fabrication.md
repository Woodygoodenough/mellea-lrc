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

## 6. A routing gate, three tags under it, and the detail recorded underneath

The temptation here is a label per mechanism -- wrong volume, wrong series,
wrong first page, wrong pin cite, fabricated, unresolvable. That is premature,
and the corpus says so. The opposite mistake is flattening far enough that a
routing decision ends up sitting next to a classification, which section 6.2
is about.

### 6.1 The only labelled distribution available is a generator's

| label | `aux_train` | `eval` |
|---|---:|---:|
| `content_misrepresentation` | 36.3% | 40.8% |
| `non_existent_citation` | 16.0% | 10.0% |
| `case_name_mismatch` | 16.0% | 19.6% |
| `misquote` | 15.9% | 13.1% |
| `wrong_pincite` | 15.8% | 16.5% |

786 labelled citations in `aux_train`, four of the five classes within 0.2
points of each other. That is a sampling plan, not a measurement. Nothing in
either file says how often these defects occur in filings people actually
served, so a schema calibrated on it is calibrated on the generator.

Two further facts from the same table:

- **`content_misrepresentation` and `misquote` are 52% of `aux_train`.** They
  are about what the cited case *says*, and no amount of citation resolution
  reaches them. A taxonomy built around resolution alone -- which is what a
  labels-per-mechanism list becomes -- silently declares the largest half of
  the observed defects out of scope.
- **The 17 defects in `unrecorded-defects.md` came out of a corpus of 910
  excerpts.** One free-text sample of that size is not enough to know whether
  "wrong volume" and "wrong series" behave differently, and until they are
  known to, they should not be different labels.

### 6.2 The gate comes first, and it is not a defect class

Resolution is a routing decision before it is a classification:

> **Does any reading of this citation reach a document?**

`non_existent` is the answer *no*, and it is decisive on its own. It is not one
defect among several — it says there is no object, so every check after it has
no input. A pin-cite check with nothing to check the pin cite against does not
return a wrong answer, it returns an undefined one. Grouping it with
`wrong_pincite` under a shared "address" tag, as an earlier draft of this note
did, puts the two opposite answers to the gate in the same box.

It is also the cheapest question in the pipeline and the earliest answerable.
126 of `aux_train`'s labels invent a reporter series, and no document can sit at
an address whose namespace was never published — no retrieval, no allowance, no
corpus.

```
does any reading reach a document?
│
├── no ──> non_existent                     terminal; nothing downstream applies
│          └── standing: internal | absent
│
└── yes ─> a document is in hand
           ├── identity   it is not the case named
           ├── locator    it is the right case, a locator field is not
           └── content    it is the right case, it does not say this
```

Four tags, and the first one routes.

### 6.3 Where the five corpus labels land

| label | tag |
|---|---|
| `non_existent_citation` | **`non_existent`** — the gate answered no |
| `case_name_mismatch` | `identity` |
| `wrong_pincite` | `locator` |
| `content_misrepresentation` | `content` |
| `misquote` | `content` |

Nothing left over, nothing invented. The three tags under the gate are ordered
the same way as before and for the same reason: an `identity` verdict on a
citation whose locator is wrong compared against whatever happened to sit at
the wrong page, and a `content` verdict on a wrong identity is meaningless for
the same reason. That ordering is the pipeline — a stage that has not cleared
blocks the ones after it rather than reporting alongside them.

### 6.4 The sub-type info under each tag

Recorded, not labelled, so the tree can be recut without re-annotating.

**Under `non_existent`, `standing` is the whole substance**, because the tag is
a claim about a failed search and is only as strong as that search:

- **`internal`** — settled inside the document and certain. The reporter series
  does not exist; `F.2d` carries a 2014 date; a pin cite lies outside the case
  its own citation names. No retrieval performed, so no corpus can be wrong.
- **`absent`** — every search came back empty. The weakest standing in the
  taxonomy, and the one most often misreported: absence from a corpus is a fact
  about the corpus. Carries the `searches` record from section 3 — which ran,
  what each returned, what each covers — and until coverage is queryable this
  is as far as a verdict may go. *Fabricated* against *unresolvable* is this
  record, not a label.

**Under the other three**, `fields` is what section 2 counts to pick the
referent: which agreed with the document in hand, which disagreed. *Wrong
locator* against *wrong description* falls out of it, computed, and can be
tested for whether it predicts anything before it is given a name.

### 6.5 What this buys

Four tags is what a reader can hold, the first one is a routing decision rather
than a judgement, and the granularity the seven labels would have committed to
is present in the record for when the data supports it.

## 7. What this changes in the code

1. **The name check and the first-page check currently answer separately.** They
   are two of the eight fields and they sit at two different levels of the
   tree. They should feed one referent decision rather than each emitting a
   verdict, or the same citation is convicted twice for one error -- and a name
   check that fires on a wrong address is answering a question that has not
   cleared yet.
2. **Parallel citations are unused and are the cheapest strong evidence.** Both
   *Anderson* defects in section 2 are decided by them alone, offline, with no
   allowance spent. Nothing in the project reads them today.
3. **Coverage has to become a queryable property.** Section 3's second clause
   is unenforceable until a search can state which courts and years it covers.
   Until then `standing: absent` is as far as a verdict may go.
4. **The gate is not built, and it is the first thing that runs.** `standing:
   internal` needs no retrieval at all: the invented reporter series alone are
   126 of `aux_train`'s labels, and they are the cheapest and most certain
   findings available. Nothing downstream should run on a citation the gate
   has answered no for.
5. **`content` is 52% of the labelled defects and nothing in the project
   addresses it.** Recording it as a tag the pipeline does not yet reach is
   more honest than a taxonomy that does not mention it.
