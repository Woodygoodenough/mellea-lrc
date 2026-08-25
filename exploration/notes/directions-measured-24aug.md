# Seven directions, measured against the labels

24 August 2026. A day spent measuring candidate checks rather than building
them, so that the order they get merged in can be argued from numbers. Nothing
here is wired into the pipeline.

Two things in this note matter more than the individual measurements: what the
corpus labels actually are (section 1), and how often a measurement inverted on
a second look (section 9).

## 1. Half the labels are not about citations

The dataset's own README documents one field, `hallucinations`, mapping
**hallucinated text span -> type**. The keys are spans, not citations, and what
kind of span differs by class:

| class (eval) | citation-shaped | prose |
|---|---|---|
| `content_misrepresentation` | 0 | 131 |
| `misquote` | 0 | 46 |
| `case_name_mismatch` | 52 | 16 |
| `wrong_pincite` | 53 | 2 |
| `non_existent_citation` | 31 | 0 |

`content_misrepresentation` and `misquote` label the fabricated claim and the
altered quote. Together that is roughly half the eval spans.

**A checker whose unit is the citation cannot locate half the labelled
defects**, never mind judge them. For those two classes the unit is a passage
and the citation is only the pointer used to check it. That decides whether
findings attach to citations or to spans, so it wants settling before anything
is merged.

Two smaller things found in the same place:

* `optional` appears 22 times in eval and never in train. It is in neither the
  README taxonomy nor its count table.
* The file carries both `list_hallucinations` and `list_hallucination_types`,
  and their keys differ in 183 of 390 eval rows. Only the first matches the
  README's published counts. Any figure reported later has to name which field
  it came from; the ones in this note use `list_hallucinations`.

## 2. The reporter-series rule reproduces the class exactly -- and already existed

A citation naming a series its reporter never published cannot address
anything: the North Eastern Reporter stops at `N.E.3d`, so `531 N.E.4th 224` is
impossible without any lookup.

Hit counts against the README's published per-split totals:

| split | README `non_existent_citation` | rule hits | false positives |
|---|---|---|---|
| train | 126 | 126 | 0 |
| eval | 32 | 32 | 0 |

Exact on both. The generator builds this class **only** by advancing a real
reporter's series, which the README's own example confirms
(`133 S. Ct. 1017` -> `446 Cal. Rptr. 4th 183`). So the rule does not
approximate the class, it inverts the construction -- and that is also its
limit. An invented case in a series that exists is outside what it can see, and
no figure here says anything about hallucinations produced any other way.

**This rule already existed.** `names_no_real_reporter` in
`evaluations/lephantomcite/locator_probe.py` does the same job, and
[[unrecorded-defects]] section 7 says so plainly. It was rebuilt without
checking. On this corpus the two agree on every citation-shaped labelled span
-- 116 of 116 in train, 31 of 31 in eval, no disagreement in either direction.

They differ off-corpus, and one difference is a defect:

| citation | new rule | `names_no_real_reporter` | truth |
|---|---|---|---|
| `151 Fed 2nd 240` | quiet | **flags** | real: `Fed.` is a registered variation of `F.` |
| `12 Nonesuch Rptr. 3d 45` | quiet | flags | unknown, which is not the same as invented |
| `531 N.E.4th 224` | flags | flags | fabricated |

The existing rule flags anything whose reporter is absent from its known set.
The new one flags only an impossible series **of a family that exists**, so a
reporter the database lacks, or a real one written loosely, stays quiet. Since
`reporters-db` is extensive but not exhaustive, and [[reporter-year-check]]
already records its date ranges being wrong for some series, treating absence
as evidence is the riskier polarity.

Whichever survives, one should be deleted. Two rules answering the same
question that disagree off-corpus is worse than either alone.

## 3. That class is invisible to extraction, and only that class

How many labelled citations eyecite never produces at all:

| label | not extracted | total |
|---|---|---|
| `non_existent_citation` | **119 (100%)** | 119 |
| `case_name_mismatch` | 19 (16%) | 118 |
| `misquote` | 11 (9%) | 125 |
| `content_misrepresentation` | 16 (6%) | 284 |
| `wrong_pincite` | 6 (5%) | 124 |

eyecite's patterns come from the same reporter database, so a fabricated series
matches nothing and returns as *no citation* rather than a bad one. The class is
not merely hard to detect downstream, it never arrives.

This reframes what the rule is for. It is not one detector among several; it
closes a blind spot that swallows a whole class. It also means any accuracy
figure computed over extracted citations has a denominator missing 119 items,
all of them false.

## 4. Case name against cluster metadata: the best-covered check available now

The cluster's `case_name` comes from `lookup_citation`, which is fully cached,
so this runs today over every resolved locator rather than the subset whose
opinions are warm.

| label | names disagree | agree |
|---|---|---|
| `case_name_mismatch` | 34 | 0 |
| `content_misrepresentation` | 0 | 99 |
| `wrong_pincite` | 0 | 39 |
| `misquote` | 0 | 12 |
| unlabelled | 20 | 472 |

It caught every `case_name_mismatch` that reached it and fired on none of the
150 citations defective in some other way. Clean separation: it answers its own
question and stays quiet about the rest.

Two limits, the second more serious:

* **It sees about half the class.** 34 checked against the README's 63, because
  a citation reaches the check only if eyecite supplies plaintiff and defendant
  *and* the locator resolves.
* **The 4% unlabelled rate is unexplained.** 20 citations flagged that carry no
  mismatch label. Some are probably my label attachment, which matched on volume
  prefix; others may be normalisation failures of the kind [[unrecorded-defects]]
  section 8 already lists -- given names against a surname-only caption, a split
  surname, a one-word caption. Until those 20 are read one at a time the
  precision is unestablished, and twenty false alarms a run would cost more than
  thirty-four true ones are worth.

This also shows the name asymmetry from its other side. A name **can** refute
once the locator resolves, because the cluster is then authoritative. What it
cannot do is refute an *unresolved* citation, where 68 of 90 turned out to be
real cases printed only in Westlaw. Same signal, opposite reliability depending
on resolution -- which is the argument [[locator-decides]] makes for treating
resolution as the routing gate.

## 5. Directions that do not pay

**Edition date ranges.** After excluding citations the series rule already
catches: one hit in 211 checked. [[reporter-year-check]] reached the same
conclusion in more detail on a different corpus, including that some of
`reporters-db`'s ranges are simply wrong. Confirmed, not reopened.

**Reporter against court.** Unmeasured: my probe was too crude to draw from --
it flagged `577 S.E.2d 29 (Ga. Ct. App. 2003)`, which is correct, since Georgia
publishes in the South Eastern Reporter. Doing it properly needs `courts-db` to
resolve court strings to jurisdictions and compare against `mlz_jurisdiction`.
There is also a structural reason to expect little: every mismatched pairing
found in this data is *also* a fabricated series, so it would duplicate section
2. [[unrecorded-defects]] section 8 recommends building it, on evidence from a
different corpus; that recommendation is not contradicted here, only unsupported
on this one.

**Pin cite below the first page.** `550 U.S. 544, 127, 569` cites a page before
the case begins. Perfect precision -- it fires on `wrong_pincite` and nothing
else -- but 5 hits in train and 1 in eval. It is also not really a pin-cite
error: the `127` is the *S. Ct. volume* of the parallel citation with its
reporter dropped.

## 6. Parallel citations, and two citation forms nothing handles

93% of resolved citations (623) carry at least one parallel address on their
cluster; 30% carry three, 30% carry four. Entirely unused. Note the figure is
conditioned on resolution succeeding, so it says nothing about whether the
unresolved ones have parallels.

A first attempt to use them to rescue unresolved locators -- "does a citation
within 60 characters resolve?" -- reported a 10% rescue rate and **is invalid**.
The neighbours it found were subsequent history, not parallels:

```
84 F.3d 18, cert. denied, 515 U.S. 1159
873 F.2d 701, cert. denied, 493 U.S. 1023
```

Those are different dispositions at different addresses, so the first resolving
says nothing about the second.

The correct test -- does the neighbour's cluster itself list the unresolved
address -- kills the idea:

```
unresolved locator occurrences in eval : 354
  with any neighbouring citation       : 329
  neighbour's cluster lists the address: 2
```

Two of 354, and neither is a parallel: `651 F.2d 983` against `651 F.2d 999` is
one case cited at two pages, not a second reporter. **The genuine rescue rate is
zero.** The entire gap between this and the invalid 10% was subsequent history.

So parallels remain worth something as a cross-check on citations that already
resolve -- 93% have one, and two independent addresses agreeing is the only
offline purchase found on the confirm-side asymmetry in [[locator-decides]] --
but they do not raise the resolution ceiling. That ceiling has to be attacked by
classifying what is in it, not by finding second addresses for it.

The failed attempt surfaced two forms the pipeline has no concept of:

* **Subsequent history.** `cert. denied`, `aff'd`, `rev'd`, `vacated` introduce
  a real address for a real disposition that is not the case being cited. Right
  now those go through the locator like anything else and, on failing, are
  indistinguishable from fabrications. Cert-denial pages are also thinly indexed,
  so some of the unresolved population is probably this rather than absence.
* **Westlaw citations** (`2015 WL 6531272`) have no reporter and can never
  resolve through CourtListener. They belong out of scope, the way
  `NON_CASE_SOURCES` already handles the Federal Register, rather than counted as
  unresolved.

Both are offline and cheap, and both clean a denominator that currently makes
resolution look worse than it is.

## 7. Quote checking has a well-defined input

| eval `misquote` | |
|---|---|
| spans | 46 |
| located verbatim in the text | 44 |
| quote-delimited | 43 of 44 |
| a citation follows within 120 characters | 32 |

Quotes are reliably marked, so a checker can find its own target rather than
needing the ground-truth span, and the median span is 113 characters -- long
enough that a verbatim match means something.

**Attribution is the weak link, not extraction.** Fourteen quotes have no
citation after them within 120 characters; they are attributed by a preceding
citation or an `Id.`. So quote checking depends on resolving which case a quote
belongs to, which is the existing short-form and antecedent problem rather than
new work.

Of the two prose classes this is much the more tractable: exact matching against
`html_with_citations`, no model, 42 eval labels, opinions already cached for the
316 fully-warm citations. `content_misrepresentation` at 131 needs semantic
judgement and is a different order of difficulty.

## 8. What is measurable today, and what is waiting on the cache

487 of 1,068 opinion documents are stored. Clusters land whole -- only 2 of 668
are partly cached -- so **316 citations run start to finish offline** with no
cache-miss failures mixed into the results.

| direction | needs | eval labels |
|---|---|---|
| reporter series | nothing | 32 |
| case name | lookup cache only | 63 |
| pin cite below first page | nothing | 53 |
| subsequent history / Westlaw scope | nothing | -- |
| verbatim misquote | opinion text | 42 |
| content misrepresentation | opinion text + a model | 131 |

The two classes needing opinion text are also the two largest. Warming has
roughly a day and a half left.

## 9. How often these numbers were wrong the first time

Four measurements inverted on a second look, and three failed the same way.

**Parsing a reporter by taking the text between the volume and the first
number.** That yields `F.3d at` for a short form and `F. Supp.` for
`F. Supp. 2d` -- so a date-range check silently compares against the wrong
series' range. It produced three separate wrong tables before being caught. The
fix is to match against the known reporter vocabulary, longest name first,
rather than guessing where the reporter ends. Worth extracting as a shared
helper before more rules are built on it.

**A window too small to see what it was looking for.** The first quote
measurement reported 5 of 46 spans quote-delimited, using a 3-character window.
Widened to 12, it is 43 of 44. The first number argued that quote boundaries
cannot be trusted and would have pushed section 7 toward a model-based
extractor; it was an artifact.

**A neighbour test that measured the wrong relation** -- section 6.

The common shape is a heuristic that produces a plausible number, where the
number is plausible because it is measuring something adjacent to the intended
thing. None of these announced themselves; each was caught by reading the
examples the measurement printed. **Every figure in this note should be treated
as provisional until re-derived**, and any of them that ends up in the paper
needs its measurement re-read first.
