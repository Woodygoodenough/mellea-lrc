# What a full whitespace relaxation costs, measured

Written 31 August 2026, over 103 documents and 2,603 citations: the 77 mined
filings in `local/mined-corpus/` and the 26 in `local/test_data/`.

Two questions were put and both are answerable from the corpus rather than from
reasoning about the regexes.

## 1. The whitespace collapse becomes redundant

`_get_citations_with_recovered_spans` collapses runs of repeated inline
whitespace before extraction and remaps every span afterwards, because Docling
leaves those runs and eyecite's literal single spaces break on them.

With both joins relaxed and the punctuation inside the reporter group relaxed:

| | citations |
|---|---|
| found either way | 2,603 |
| found **only** with the collapse | **0** |
| found only without it | 0 |

The collapse recovers nothing the relaxed tokenizer does not already reach. It
costs a pass over the text and a span remap for no gain.

It is still worth keeping while both backends exist: they share one
collapse-and-remap path, which is what keeps them directly comparable. That is
a reason to keep it, not evidence it is doing work.

## 2. Widening the reporter-to-page join is not only about margins

The join between reporter and page is bounded to a single newline by default,
and opened to `\s*` only for text whose margins have been removed. Widening it
everywhere changes the parse in 6 of the 103 documents. **Two of the six are
correct recoveries and four are errors.**

| document | layout-adjusted? | what changes | |
|---|---|---|---|
| `69912445_21` | yes | gains `214 F.3d 1058` | correct |
| `71920595_40` | yes | `, 487 U.S.⏎⏎317.` → gains `487 U.S. 317` | correct |
| `test_data/3` | **no** | `214 F.3d` + gutter 1–28 + `1058` → page `1` | wrong |
| `70607460_15` | yes | `206 P. 327` → `206 P.3 27` | wrong |
| `72050145_17` | yes | `607 F.3d 355` → `130 S.Ct. 607` | wrong |
| `69912445_49` | yes | `Fed. R. Civ. P. 11(b)(2)` → `1 Fed.R. 1` | wrong |

**Two of the four errors destroy a citation that parsed correctly before.**
`206 P. 327` and `607 F.3d 355` both disappear. That is worse than adding a bad
citation: a lost one reports nothing to check, which is the failure mode the
whole relaxation exists to remove.

## 3. Preprocessing is necessary and not sufficient

The margin rule runs by default in Docling preprocessing, so most of the corpus
is already adjusted — 4 of 77 mined documents still carry a gutter against 8 of
26 in the older `test_data`.

That split is what makes the answer clean. **Only the margin failure occurs in
unadjusted text. The other three occur in text the rule has already cleaned**,
and none of them involves margins:

- a reporter eating a digit off the page number
- two adjacent citations gluing across a break, destroying the second
- a procedural rule read as a case citation

So removing margin line numbers fixes one error in four and leaves both
recoveries. Saying "we will handle it in preprocessing" is true about the
margin case and wrong about the rest.

## 4. What this means for the upstream PR

freelawproject/eyecite #339 relaxes both joins to `\s*` unconditionally. On this
corpus that buys 2 recoveries and 4 errors, and 3 of the 4 are not addressable
by any preprocessing of the page furniture.

That is not an argument against merging it — the same corpus shows the
relaxation recovering citations nothing else reaches, and the errors are rare.
It is an argument for the failure mode being written down, because it is
invisible to a regression check that counts citations: a wrong page is not a
lost citation, and two of the four changes leave the count unchanged while
changing what was found.
