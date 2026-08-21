# Overnight session, 21 August 2026

What was checked, built and measured while you were asleep. Everything here is
committed on `experiment/lephantomcite`, except the backend fix which is also on
its own branch `fix/strict-structured-output`.

---

## 1. The model switch was not clean, and is now

`openai/gpt-5.6-luna` via OpenRouter answers, and reports itself as that model.
But **3 of 8 live evaluations failed** on a real incompatibility, not on
judgement.

OpenAI-compatible providers in strict mode reject a `response_format` schema
whose `required` array omits any key in `properties`. Pydantic drops a field
from `required` as soon as it carries a default, so

```python
evidence_quote: str | None = None
```

produced a schema the provider refused outright: the call came back
`invalid_json_schema` and the node recorded a failure. The previous endpoint was
lenient about this; Azure and OpenAI are not. Mellea even logs a warning that it
assumes you are *not* on the OpenAI platform.

Four models carried defaults — the party proposal, the citing-proposition
proposal, the pinpoint proposal, and the experimental docket proposal. An absent
value is now a required key whose type admits null, which is how strict mode
expresses optionality. The prompts already asked for `null` rather than an
omitted key, so only the schemas changed.

**All 8 live evaluations now pass.** New offline tests pin the shape for every
model the pipeline hands to Mellea, so a defaulted field cannot come back
silently.

This is worth a line in the paper's reproducibility section: a provider swap
changed which requirements were satisfiable, and nothing in the pipeline's own
logic moved.

---

## 2. Extraction on LePhantomCite: 1,236 of 1,237

Their benchmark has no extraction stage to compare against — the agent reads the
excerpt and writes citations into a natural-language belief state, so a citation
it never noticed and one it noticed and judged wrongly are the same event in its
F1.

Measured symmetrically: each benchmark citation string is run through the same
extractor as the excerpt it came from, compared on the resulting identifier with
punctuation, spacing and case removed. Short forms count.

| | |
|---|---:|
| excerpts | 390 |
| stated identifiers | 1,237 |
| recovered | **1,236 (99.9%)** |
| excerpts recovered whole | 387 / 390 |

The single miss is a defect in **their** released data, not ours: one row states
`25 F. App'x at 541` beside the correct `425 F. App'x at 541` — a truncated
duplicate. Our extractor is right to find only the second. It is still counted
as a miss, because a coverage number that discards rows it dislikes is not a
coverage number. Report it that way and say why.

---

## 3. Fabricated citations: 31 of 31, offline, no model

The strongest result of the night, and the cheapest.

A citation naming a reporter series that does not exist can be refuted without
asking anyone. `446 Cal. Rptr. 4th` is not a series, so no volume or page of it
is, and the reporter database says so before any request is sent.

| | |
|---|---:|
| injected `non_existent_citation` refuted offline | **31 / 31** |
| sound citations wrongly refuted | **0 / 1,023** |
| network calls | 0 |
| model calls | 0 |

For comparison, their paper reports GPT-5's agent at roughly 95% recall on this
category using up to 30 agentic steps with web and CourtListener search.

Two things make this defensible rather than a trick:

- It is a **positive refutation**, not an inference from absence. The claim is
  "no such series exists", which is checkable, not "we could not find it".
- Reporter **variations** count as real. `Fed. Appx.` is how a filing often
  spells `F. App'x`, and calling a real reporter fabricated because a brief
  abbreviated it differently would be the worst error this check could make.

**One false positive was found and fixed.** `80 Fed. Reg. 64,545` came back
refuted. That is the Federal Register — a real publication that is not a case
reporter — and CourtListener rejects its abbreviation exactly as it rejects a
fabricated series. It reaches a lookup at all because eyecite types the *short*
form as a short case citation while typing the full form correctly as a law
citation. There is now an `out_of_scope` outcome and a small explicit set of
non-case sources. Say this in the paper: the false positive was real, it was
found by running the check, and the mechanism is named.

---

## 4. The pinpoint check can now say "not on this page"

The blocker identified in [07-architecture-comparison.md](07-architecture-comparison.md)
is closed, and closed in a way that respects the original design rather than
overriding it.

The old instruction said, deliberately: *one retrieved page is not sufficient
evidence to make a negative judgment about the citation.* That is correct — the
authority may support the proposition on a page this operation never saw. But
the pincite question is not about the citation, it is about the **page**, and
those are different claims.

So the new outcome is `absent_from_page`, and it is a claim about the page
alone: the page was retrieved, it is on the proposition's subject, and it does
not carry the proposition. No verdict asserts anything about the citation, and
the schema still refuses one that would.

An absence must be grounded like a support: the quote names the passage on the
page closest to the proposition's subject, which is what separates a finding
from a failure to look. Where the two are close the instruction takes the
conservative side.

**That conservatism is measurable and you should expect it to cost recall.** A
first test case — a page about school segregation, a proposition about busing
funding — came back `inconclusive` with the reasoning *"the page addresses
racial segregation and equal educational opportunities, not whether a school
district must fund busing"*. The model reasoned correctly and declined to
assert. A sharper case (the remedial holding of the same litigation, decided on
a page this one is not) returns `absent_from_page` reliably. Live tests cover
all three verdicts.

---

## 5. A new capability: verbatim quotation checking

Their `misquote` category is 41 eval records and GPT-5 scores 82.6% on it. A
brief that quotes an opinion makes a claim no model is needed to check.

What it needs instead is the citation conventions that make a faithful quotation
differ from its source *on purpose* — `. . .` for omitted text, `[W]here` for a
changed first letter, `[the plaintiff]` for a substitution, `(internal quotation
marks omitted)` as the quoter's note. Without them a naive comparison reports a
defect on an honest Bluebook quotation, which is worse than not checking at all.

Alignment is word-level against the best-matching window on the page, so a
substitution is reported as **the pair of words that differ**:

| citing text | outcome |
|---|---|
| faithful quotation | `verbatim` |
| `[w]here …` with `. . .` | `verbatim` |
| `(internal quotation marks omitted)` | `verbatim` |
| `factual detail, accepted as accurate` | `altered`, naming `detail→matter`, `accurate→true` |
| a fabricated quotation | `not_on_page` |
| four common words | `uncheckable` |

The vocabulary keeps a contradiction apart from an absence, as everywhere else:
`altered` is a positive finding, `not_on_page` may only mean the pinpoint is
wrong and asserts nothing.

It is wired into the found-locator route as a node, serializes and round-trips,
and adds no model call. It has not yet been run against the benchmark — that
needs reporter pages, and therefore CourtListener.

Its **reachability** is measured, though, and it is favourable:

| | |
|---|---:|
| quoted passages across the 390 excerpts | 1,523 |
| long enough to locate on a page | 1,048 |
| excerpts carrying at least one checkable quotation | 262 (67%) |
| **`misquote` excerpts carrying one** | **36 / 36 (100%)** |

So the check can render a verdict on every record in the category it targets,
given the pages — the ceiling is not the constraint. And at 67% of excerpts
overall it is a broadly applicable capability rather than a niche one.

---

## 6. Infrastructure

**The Modal cache proxy works and matters.** After the R2 secret fix, a cold
lookup takes ~9s and a repeat ~0.6s. Every lookup the probe makes populates the
cache, so a re-run is cheap. That is what will make the pincite experiment
affordable.

**CourtListener rate-limits hard.** Roughly 7 lookups a minute sustained,
whatever the worker count. The probe now retries with capped exponential backoff
and **checkpoints every lookup to JSONL**, so an interrupted run resumes and a
run that never finishes is still readable. The first attempt wrote nothing until
the end and lost its work; that is fixed.

**A run is in flight.** `local/exploration/results/locator-probe.checkpoint.jsonl`
is filling at ~7/min against 1,197 distinct locators. It should finish overnight.
Note that it started before the `out_of_scope` fix, so reclassify `refuted` rows
whose `detail` names a non-case source when you read it.

---

## 7. What did not happen

- **No pincite number yet.** It needs the full pipeline over their excerpts,
  which needs reporter pages, which needs CourtListener — and the probe is
  saturating that. `run_validation.py` is written and ready; run it with
  `--label wrong_pincite` (43 excerpts) once the cache is warm.
- **No misquote number yet**, same reason.
- **The aggregation still treats `absent_from_page` as merely "not supports"**,
  which is correct but blunt. Whether a citation summary should report a
  misrepresentation finding is a separate design question.
- **No re-run of false-citation-bench.** Item 0 on the roadmap is still open,
  and now has one more reason: the structured-output fix changes which nodes
  fail, so the old numbers are stale for a second, independent reason.

---

## 7b. The scoring path is complete

`evaluate.py` reads a validation sweep and scores it per defect type, with
**abstentions held out of the confusion matrix** rather than folded into either
label. Coverage is reported next to accuracy, and every uncovered citation is
named by the outcome that abstained. So the morning run is two commands:

```bash
uv run --env-file .env python -m evaluations.lephantomcite.run_validation \
  --dataset <dir>/eval.jsonl --output-dir run-pincite --label wrong_pincite

uv run python -m evaluations.lephantomcite.evaluate \
  --run-dir run-pincite --output pincite-evaluation.json
```

A finding is credited only against the type it speaks to: a quotation finding
cannot answer a case-name label. `wrong_pincite` and `content_misrepresentation`
share a node but are scored apart, because the benchmark labels them apart.

---

## 8. What I would do next, in order

1. **Let the probe finish**, then read `locator-probe.json`. The number to look
   for is the `unresolved` rate on *sound* citations — that is the abstention
   cost, and it is the direct counterpart to their measured 24.0% (GPT-5) and
   65.9% (Qwen3.5) false-flag rates on CourtListener-absent citations.
2. **Run `--label wrong_pincite`** over 43 excerpts. Compare to 18.2%. This is
   still the experiment that decides the paper's framing.
3. **Run `--label misquote`** over 36 excerpts. Compare to 82.6%. The quotation
   check should do well here and it costs no model calls.
4. **Re-run false-citation-bench** on current `main` and redo the error
   analysis.
5. Only then decide JURIX scope.

---

## Test and commit state

204 offline tests pass, 13 skipped, plus 8 live evaluations against
`gpt-5.6-luna`. Ruff clean and formatted.

| commit | what |
|---|---|
| `fix: express an absent structured-output value as a nullable required field` | the backend fix |
| `feat: let the pinpoint check report that a page does not carry the proposition` | `absent_from_page` |
| `feat: check a filed quotation against the page it is attributed to` | the quotation decision logic |
| `feat: measure extraction and identity coverage on LePhantomCite` | dataset, extraction coverage, locator probe |
| `feat: refute a fabricated reporter series before any request is sent` | offline refutation, README, checkpointing |
| `feat: run the quotation check as part of the found-locator route` | node, wiring, serialization |
| `fix: a citation to a real non-case publication is out of scope, not fabricated` | the false positive found and fixed |
