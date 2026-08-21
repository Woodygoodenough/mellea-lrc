# Exploration: turning mellea-lrc into a paper

Written 2026-08-21. Working notes, not a commitment. Everything here is
scoped against what the repository actually contains today (26 filings,
79 annotations, 21 node types, the 8B/30B x repair ablation, the
extraction and validation evaluators).

## Contents

| file | what it is |
|---|---|
| [00-assets.md](00-assets.md) | inventory of what we already have that is publishable, with the numbers |
| [01-landscape.md](01-landscape.md) | who else is working on this, what they published in 2026, where we actually differ |
| [02-venues.md](02-venues.md) | real deadlines, and what is still reachable this fall |
| [03-directions.md](03-directions.md) | the full catalog of research directions — fifteen of them, each with claim / build / measure / risk |
| [04-paper-plans.md](04-paper-plans.md) | four concrete paper skeletons: title, claim, sections, experiments, figures |
| [05-engineering.md](05-engineering.md) | feature roadmap, each item mapped to the paper claim it serves |
| [06-objections.md](06-objections.md) | the reviews we will get, and what has to exist to answer them |
| [07-architecture-comparison.md](07-architecture-comparison.md) | their implementation read line by line, and where our architecture is and is not better |
| [08-roadmap.md](08-roadmap.md) | **the plan** — gates, four tracks, the benchmark-scaling pipeline, and the calendar |
| [09-session-log.md](09-session-log.md) | what was built and measured overnight on 21 August, and what to run next |

Supporting artifacts the analysis reads:

| path | what it is |
|---|---|
| [notes/further-improvements.md](notes/further-improvements.md) | the known-defects register: diagnosed failures, and the ones deliberately left alone |
| [notes/presentation-notes.md](notes/presentation-notes.md) | the August walkthrough the stale evaluation figures come from |
| [timing/](timing/) | per-node timings and status counts for the four ablation arms |

## External material this analysis reads

Neither is committed here. Fetch them alongside the checkout, outside the
repository:

```bash
# The Princeton agent. No LICENSE file, so all rights reserved by default:
# readable and citable, not vendorable. Do not commit it.
git clone --depth 1 https://github.com/princeton-polaris-lab/legal-hallucination-agent

# LePhantomCite. CC BY 4.0.
hf download ai-law-society-lab/Legal_Phantom_Citation --repo-type dataset \
  --local-dir lephantomcite
```

## The short version

Three findings drove everything below.

**One.** The obvious paper — "we built a legal citation checker and a small
benchmark" — is no longer novel. Between May and July 2026 at least five
groups published on legal citation hallucination, including Liu, Stammbach
and Henderson at Princeton, whose LePhantomCite has 1,300 excerpts to our 79
records and evaluates five frontier models. Submitting the obvious paper
means being compared to that and losing on scale.

**Two.** We have three things none of them have, and each is a paper-grade
claim on its own: real court-adjudicated false citations rather than injected
ones; an outcome vocabulary that keeps *unresolvable* apart from *false*,
which is the correct epistemics for this task and which nobody else models;
and a verdict trace that grounds every claim in a character span. Our 100%
precision and 100% specificity on identity verification are a consequence of
the second of those, not an accident.

**Three.** The one honest weakness — the pinpoint check, 3 of 9 verdicts
wrong — is not a bug to hide before submission. It is the open research
problem, we have already diagnosed its structural cause (compound
propositions evaluated atomically), and it is the most promising direction
in this whole document.

**The recommendation.** Do not aim at a workshop. Aim at JURIX 2026 now — a
long paper is due 5 September 2026, fifteen days out, and one is writable
from what already exists. Then spend the fall building the anchor paper for
ACL/ICAIL 2027 around abstention-aware verification and proposition
decomposition. Details in [02-venues.md](02-venues.md) and
[04-paper-plans.md](04-paper-plans.md).

NLLP 2026 is out: direct submissions closed 18 August, three days ago, and
the 27 August path requires an ARR submission with a meta-review already in
hand.
