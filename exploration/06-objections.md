# The reviews we will get

Written as the objection, then what has to exist in the paper to answer it.
Anything without an answer is a reason to change the plan, not a reason to
hope.

---

**"26 documents and 79 records is too small to support these claims."**

The most likely rejection reason, and it is fair. Answers, in order of
strength:

1. State what the labels *are*. These are not crowd annotations or injected
   errors; a federal judge found these citations defective in a written order,
   and we verified each against that order's own text. Scarcity is a property
   of adjudicated ground truth. Say so in the abstract, not the limitations.
2. Report the derived sets, which are larger and independently useful: 594
   extraction spans, 423 validation occurrences, 36 mismatches spread over 14
   of the 26 filings so no system can win by learning which document is bad.
3. Show the scaling path is real and underway — Direction D, with the tracker
   and the RECAP plumbing that already exists — rather than gesturing at
   "future work."
4. Do not overclaim. Every number in the paper needs its denominator adjacent
   to it. "3 of 9" is more honest and more persuasive than "33% error rate."

---

**"How is this different from LePhantomCite?"**

Certain to be asked. The answer is four sentences and they should appear in
the introduction:

- Their errors are injected into pre-2022 briefs; ours occurred and were
  adjudicated.
- Their system is a frontier model doing unbounded agentic search at 15.3 steps
  per excerpt; ours is a fixed 21-check decomposition running an 8B model
  locally.
- They score F1 over a binary label; we treat unresolvable as a third answer
  and report abstention next to accuracy.
- They identify restricted database access as their central limitation; we
  quantify it.

If the head-to-head from Direction A lands, this objection becomes a table and
stops being an objection.

---

**"Isn't this what KeyCite and Shepard's already do?"**

No, and the distinction has to be stated precisely rather than dismissed.
KeyCite verifies that a case exists and reports how later courts treated it. It
does not read the sentence in your brief and ask whether the page you cited
supports the proposition you attached to it. That is the pinpoint check, and it
is what catches misrepresentation as distinct from fabrication. Also: KeyCite
requires a subscription, and it emits a signal rather than a trace.

Note honestly that we do *not* do negative treatment today (Direction H), so we
are not claiming to replace those products.

---

**"100% precision is implausible."**

It is a small-sample artifact and should be presented as one. The defensible
version is: zero confident errors observed on 364 confident verdicts, with a
confidence interval, and a design argument for *why* the errors fall on one
side — the aggregation abstains when evidence is missing rather than asserting
a problem, so an unchecked field can never produce a false positive.

Also disclose the Beery case, where our confident mismatch may be wrong because
CourtListener's docket metadata is wrong. It is the one known candidate
counterexample and volunteering it is worth more than the point it costs.

---

**"The semantic layer barely works."**

True. 3 of 9 verdicts wrong, and 6 of 15 real misrepresentation cases never
attempted. Put it in the results section, not the limitations, with the
structural diagnosis attached: the check evaluates compound propositions
atomically, and Whitehaven is the worked example. A failure with a mechanism is
a research contribution. A failure without one is a weakness.

The identity layer's claim does not depend on the semantic layer's, and the
paper should make the two independently assessable so a reviewer can reject the
second without rejecting the first.

---

**"Why should anyone care about an 8B model when GPT-5 exists?"**

Two answers, and the first is the one that matters in a legal venue:
privileged material and attorney work product cannot be sent to a third-party
API. That is a professional-responsibility constraint, not a cost preference.
The second is cost — roughly 1,500 model calls per 26 documents, and the
frontier arm's price per document should be in the paper next to ours.

---

**"The evaluation is not reproducible."**

Currently correct, and it is the objection with the cheapest fix. Today the
evaluation needs a paid CourtListener quota and two hours, and CourtListener's
index changes over time, so the numbers are not reproducible even by us next
year. Direction O — a frozen response cache shipped with the dataset — removes
the objection entirely for about a week of work. Do it.

---

**"Extraction is eyecite; what did you contribute?"**

The whitespace-recovery layer and the measurement behind it. The Docling versus
CourtListener-plain-text comparison — 96.6% versus 90.4%, with 46 of the 56
lost locators recoverable by whitespace collapse alone — is a real,
mechanistic finding about a preprocessing choice everyone else makes silently.
Frame extraction as "we measured what preprocessing costs you" rather than as
"we built an extractor," which we did not.

---

**"You never compare against any baseline."**

Currently true and it is the most damaging gap. Minimum acceptable: a
plain-prompt LLM baseline on our own benchmark. That is a day's work and there
is no excuse for the paper going out without it. Better: the full head-to-head
from Direction A.

---

**"The abstention framing is just selective prediction, which is old."**

Correct, and concede it immediately. The contribution is not the framework, it
is the application: the safety property specific to this task, the
demonstration that current legal-citation benchmarks are miscalibrated for it,
and the re-scoring that shows the recoding choice moves published numbers by
several points. Cite the selective-prediction literature properly and position
as application rather than invention. A reviewer who feels you were trying to
pass off known machinery as new will reject on that alone.

---

**"Case law only. Real briefs cite statutes."**

Concede and scope it. The corpus contains statutory references we do not
annotate or check. Say so in the dataset description and in the limitations,
with the reason: statutes have no case-name / court / year identity triad, and
their real problem is temporal validity, which is a different research problem
(Direction L). A stated scope boundary is respected; a silent one is punished
when a reviewer finds it.

---

## The two that should change the plan

Of everything above, two objections have no adequate answer today, and both are
fixable before September:

- **No baseline.** One day of work. Do it.
- **Not reproducible.** One week of work. Do it.

Neither is a research problem. Both will otherwise be the first two things a
reviewer writes.
