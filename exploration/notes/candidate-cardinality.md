# How many candidates a lookup returns, and what to do about it

Written 22 August 2026. When a locator lookup or a search returns more than one
record, something has to decide which records are worth evaluating. The rule
today is a constant. This note measures what the rule is applied to, which
turns out to be two different problems that need opposite treatments.

## 1. The rule today

`validation/candidate_selection.py`:

```python
CANDIDATE_SELECTION_LIMIT = 3
selected_count = total if total <= CANDIDATE_SELECTION_LIMIT else 0
```

It is not a top-3. **More than three candidates selects zero**, and the whole
branch below is marked deferred. The reasoning is defensible — picking three of
twenty-nine arbitrarily would be worse than declining — but the effect is that
the citations with the most retrieved evidence are the ones that get none of it
looked at.

## 2. What the ambiguous results actually contain

From the locator probe, 94 of the 817 answered locators came back ambiguous.
Re-reading 68 of those from the cache, at no request cost:

| records returned | locators |
|---:|---:|
| 2 | 54 |
| 3 | 2 |
| 4 to 32 | 12 |

Two records is 79% of the ambiguity. Twelve locators are over the limit and are
deferred entirely.

## 3. The two-record case is one case recorded twice

CourtListener holds the same decision more than once — a Harvard import and a
scraped copy, a panel opinion and its rehearing, a record whose name field is
empty. Collapsing on a normalized name with prefix matching resolves 35 of the
68 to a single case. Reading the remaining two-record ones by hand, essentially
all of them are also one case, and the reason a string rule missed them is
instructive:

| locator | first record | second record | why the rule missed it |
|---|---|---|---|
| `828 F.2d 123` | Grasty v. Amalgamated Clothing **&** Textile Workers Uni | Grasty v. Amalgamated Clothing **And** Textile Workers U | truncated at different lengths |
| `198 F.3d 1083` | Free Speech Coalition v. **Reno** | Free Speech Coalition v. **Janet** Reno | a first name inserted |
| `338 F.3d 23` | Savard v. **Rhode Island** | Savard v. **RI** | abbreviation |
| `343 F.3d 1143` | Giebeler v. **M & B** Associates | Giebeler v. Associates | dropped party words |
| `244 F.3d 1152` | Local Joint Executive Board of Culinary… | *(empty)* | no name at all |
| `398 F.3d 868` | Johnson v. Karnes | Johnson **II** v. Karnes | appeal-stage marker |

Every one of these is decidable by a person in a second, and none is decidable
by a rule that will not also merge cases that differ. Normalization is
open-ended in the way that party names are open-ended: an insertion, an
abbreviation, a truncation, an ampersand, an empty field, a roman numeral.

This is the honest case for a model at this step. The question is narrow —
*are these two records the same decision?* — and it comes with strong
programmatic evidence to guard against a wrong answer: the two records share a
locator, and a date, and a court. A model that says "different" for two records
with the same locator, date, and court should be overruled; a model that says
"same" for records with different dates should have to say why.

## 4. The high-cardinality case is a different problem entirely

The twelve locators over the limit do not shrink when duplicates are collapsed,
because they are not duplicates:

```
554 F.2d 1071  -> 31 distinct cases: United States v. Maldonado-Farias,
                  United States v. Chambers, United States v. Luna, ...
788 F.2d 9     -> 27 distinct cases: In re Acker, Saunders v. McDonnell
                  Douglas, Snowden v. City of Tucson, ...
 21 F.3d 1115  -> 26 distinct cases
```

These are **table-of-decisions pages**. The Federal Reporter prints unpublished
dispositions in a table, many to a page, so one volume-and-page really does name
dozens of unrelated cases. The locator is not ambiguous by accident; it is
insufficient by design.

Deduplication cannot help here and neither can a bigger limit. The only thing
that separates 31 cases sharing a page is **the case name the filing wrote** —
which the pipeline has, and which the current design never brings to this step.

## 5. What follows

The two problems need opposite handling, and the constant treats them alike.

**For duplicates:** collapse before counting. The limit should apply to distinct
cases, not to returned records. On this data that turns 54 two-record results
into single-candidate results and removes them from the decision entirely.

**For table pages:** do not collapse, and do not defer. Match the filing's own
case name against the returned records. Thirty-one candidates with a case name
to match on is an easier problem than three candidates without one, so the
current rule has the difficulty backwards.

**For the limit itself:** it should bound *work*, not *evidence*. Deferring
everything above a threshold discards retrieved records that were already paid
for with a request. Ranking them and evaluating the top few, while recording
that the rest were not looked at, keeps the honesty without the waste — and
recording what was dropped is a rule this project already applies elsewhere.

## 6. What to measure next

1. How often a returned candidate set contains the case the filing actually
   named, for the twelve deferred locators. If the answer is usually, deferring
   them is losing real answers.
2. Whether collapsing on locator, date, and court alone — no name at all — is
   enough for the two-record case. That would need no model, and section 3 says
   it probably is not, but it is one query away from being known rather than
   assumed.
3. What the same distributions look like for the opinion-search results, which
   this note has not examined. Search returns a result count that can be in the
   hundreds, and the same all-or-nothing rule applies to it.
