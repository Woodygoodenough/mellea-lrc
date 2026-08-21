# Venues and the fall calendar

Dates verified 2026-08-21 against the official CFP pages. Re-check before
relying on any of them; workshop dates in particular move.

## Reachable now

### JURIX 2026 — the one to take

| | |
|---|---|
| abstract | **28 August 2026** (recommended) |
| paper | **5 September 2026, AoE** |
| notification | 8 October 2026 |
| conference | Toulouse, 8 December 2026, in person |
| format | long 10pp, short 5pp, poster 2pp, excluding refs; IOS Press style |
| review | single-blind |
| submission | EasyChair, `jurix2026` |

Fifteen days. A 10-page long paper is writable from what exists today — see
plan A in [04-paper-plans.md](04-paper-plans.md) — because it needs no new
experiments, only the ablation numbers finished and the head-to-head dropped.

JURIX is the established European AI-and-Law conference with proceedings
published by IOS Press. It is a real conference, not a workshop, and it is the
right first venue for a system-plus-dataset paper. Presenting in Toulouse in
December also puts the work in front of the AI-and-Law community before the
2027 conference cycle, which matters more for the career question than the
line on the CV does.

The single-blind review is worth noting: the IBM collaboration is visible to
reviewers, which is a mild positive here.

## Closed, and why

### NLLP 2026 (at EMNLP, Budapest, 28 October)

Direct submission closed **18 August 2026** — three days ago. The remaining
path, 27 August, accepts only ARR submissions with meta-reviews ready or
EMNLP 2026 rejections with reviews. We have neither. This one is gone; note it
for 2027, since it is otherwise the natural workshop home and it explicitly
lists "agentic applications for conducting tasks in the legal domain" and
"legal reasoning and chain-of-thought grounded in legal sources."

## The spring cycle — where the anchor paper goes

### ACL Rolling Review

10-week cycles, five a year. The August 2026 cycle opened 3 August and closes
11 October 2026; reviews 7 September, author response 14–24 September,
meta-reviews 8 October. The next cycle opens after that. Check
`aclrollingreview.org/dates` for the October cycle's exact submission deadline
— that is the realistic target for the anchor paper, committing to ACL 2027 or
NAACL 2027.

Plan the anchor paper to hit an ARR deadline in **mid-to-late October 2026**.
That gives six weeks after JURIX submission to run the experiments JURIX will
not include.

### ICAIL 2027

The 22nd ICAIL, run by IAAIL. The executive committee's stated preference is
**June 2027**; the host was still being selected as of the last public notice,
so no CFP yet. Expect a call in late 2026 with a deadline in January or
February 2027. This is the highest-prestige venue in AI and Law and the right
home for the anchor paper if the ARR route stalls.

Ignore every "ICAIL 2027" result from waset.org and conferenceindex.org. Those
are predatory listings with no connection to IAAIL.

### Resource and demo tracks

- **ACL/EMNLP demo track** — the frontend, once it shows the node graph and
  spans. Demo papers are 6 pages, reviewed on whether the system works and is
  useful, and are a legitimate publication. Low risk, high fit.
- **NeurIPS Datasets & Benchmarks / ACL resource track / LREC** — for the
  scaled benchmark, once it exists. This is the second paper, not the first.

### Longer-horizon, higher-prestige

- **Journal of Empirical Legal Studies** — where Magesh et al. landed. If the
  sanctions-tracker corpus produces a longitudinal empirical result (who files
  hallucinated citations, in which courts, sanctioned how), that is a JELS or
  law-review paper rather than an NLP one, and it reaches an audience that
  will actually change practice.
- **Artificial Intelligence and Law (Springer)** — the journal extension of a
  JURIX or ICAIL paper. Standard path: publish at JURIX, extend, submit to the
  journal. Worth planning for from the start, because it means the JURIX paper
  should leave deliberate room to grow rather than cramming everything in.

## Proposed fall calendar

| when | what |
|---|---|
| 21–27 Aug | decide JURIX; finish the ablation numbers; write the abstract |
| 28 Aug | JURIX abstract submitted |
| 28 Aug – 4 Sep | write the JURIX long paper; run the LePhantomCite head-to-head if it fits, cut it if it does not |
| 5 Sep | JURIX submission |
| 8 Sep – 10 Oct | anchor-paper experiments: abstention framing formalized, head-to-head completed, proposition decomposition built and measured |
| mid-Oct | ARR submission for the anchor paper |
| Oct – Nov | benchmark scaling from the sanctions tracker; frontend to demo quality |
| 8 Oct | JURIX notification |
| Nov | camera-ready; start the resource paper |
| 8 Dec | JURIX, Toulouse |
| Jan – Feb 2027 | ICAIL 2027 submission; demo track; journal extension |

The load-bearing decision is the first row. Everything after it is
conditional on committing to JURIX this week.

## Sources

- [JURIX 2026 call for papers](https://www.irit.fr/jurix2026/call-for-papers/)
- [NLLP 2026 call for papers](https://nllpw.org/workshop/call/)
- [ACL Rolling Review dates](https://aclrollingreview.org/dates)
- [IAAIL — call to host ICAIL 2027](https://iaail.org/call-for-expressions-of-interest-to-host-icail-2027/)
