# Open search as a loop: what it is for, what it does, and what to measure first

The design for the stage after identity. It is not built. This note says what
would justify building it, what its shape is, and which measurement has to
come first.

## 1. Its population

The identity stage leaves a root in one of two states that open search can act
on:

- **`DEFER_TO_SEARCH`**: the archive holds nothing at the locator, the lookup
  failed, a candidate was judged undeterminable, or the case is cited by
  docket number
- **`AMBIGUOUS_IDENTITY`**: a crowded page the filing's case name separated
  nothing on

Both are absences. Neither is evidence that the citation is bad, and the
current pipeline stops there with nothing to say. `agentic-search-population.md`
counts the unresolved bucket on LePhantomCite at 94 in 1,334 citations, 70 of
them Westlaw or LEXIS numbers, and the ambiguous leftover at 9. Those counts
are the population the loop inherits, and they are small on that corpus because
the corpus is old reported cases. On real filings the share of unpublished and
recent decisions is larger, and that is where the archive is thin.

## 2. Why the current search stage is not enough

`validation/case_search/` is single-shot. It prepares one case-name query,
sends it to the opinion index and the RECAP index, and evaluates what comes
back. It never sends a second query. If the first returns nothing, or 111
results, the attempt is over.

What a second query should be depends on what the first returned, and on what
kind of citation this is:

- A `WL` or `LEXIS` number is unreachable by the cluster search, because the
  search index does not carry vendor citations. It may be reachable by
  full-text search for opinions that *cite* it (section 4).
- A docket citation wants the docket index, scoped to its court.
- A name search that returned too much wants a court or a year added; one that
  returned nothing wants a party dropped, or a spelling relaxed.
- A recent decision the archive has not imported wants the court's own site.

Coding that as a fixed decision tree is what the current stage would grow into,
and it would be wrong at every leaf the tree did not anticipate. The choice of
next move is a judgement over the result set, so a model makes it, inside a
graph that fixes which moves exist and what each may spend.

## 3. Shape

A state graph, in LangGraph, with a small fixed set of nodes and model-chosen
transitions between them. LangGraph is chosen for two things: it enforces that
transitions are the ones declared, so a model cannot invent a move, and it
records the trajectory as state, which is what the paper needs to show about
an agentic component. Mellea makes every model call inside a node.

State carried through the graph:

- the record, read-only here: the filing's citation as the identity stage left
  it, its context window, and the identity trace
- the moves made so far, each with its query, what it returned, and the
  model's stated reason for choosing it
- the budget left, in requests per index and in model calls
- candidates gathered so far, each with provenance

Nodes:

| node | sends | what it does |
|---|---|---|
| `choose` | one model call | reads the state and picks the next move, or stops, with a reason |
| `cluster_search` | one request | CourtListener opinion search with a query the model wrote |
| `docket_search` | one request | CourtListener docket search, scoped to a court |
| `citing_search` | one request | full-text search for opinions quoting the locator string (section 4) |
| `web_search` | one request | the open web, restricted to the domain tiers in `experimental/web_refutation/domains.py` |
| `read` | one fetch | retrieve one candidate's text for the judge |
| `judge` | one model call | the composite identity judgement, reused from the identity stage, over one candidate |
| `stop` | nothing | writes the outcome |

`choose` is the only node that decides anything. Every other node does one
thing and returns what it got. The graph's edges say `choose` may go to any
search node or to `judge` or `stop`; every search node returns to `choose`;
`judge` returns to `choose` unless it established identity, in which case it
goes to `stop`.

Hard limits, outside the model's reach: a cap on moves per citation, a cap on
requests per index per citation, and a per-run request budget the graph reads
before every search node and refuses to exceed. The budget is an input to
`choose`, so the model plans around it rather than discovering it by refusal.
`exploration/AUDIT.md` section 4 on `experiment/general-explorations` describes
the two throttling windows that make the budget non-negotiable.

## 4. The move worth building first: a ruling that cites the locator

A citation the archive cannot resolve may still be *quoted* by an opinion the
archive holds. `2019 WL 1234567` as a cluster is not in the search index;
`"2019 WL 1234567"` as a string in an opinion's text may be. When it is, the
citing opinion carries the case name, the court and the year beside the
locator, in a court's own words, and it usually carries a sentence about what
the case held.

That is stronger evidence than a search snippet, and it is reachable with the
cluster search endpoint the client already has, by querying the opinion text
rather than the citation field. It also answers the pinpoint question for free
when the citing opinion quotes the cited page.

**This is the measurement to run first, before any graph is built.** Take the
70 vendor-number locators from the population note and the 15 reporter
locators the lookup missed, send each as a quoted string to the opinion search,
and count how many return at least one citing opinion whose text states a case
name that agrees with the filing's. That costs 85 requests, and its answer is
whether the loop's best move works on the population it exists for. If it
recovers most of them, the loop is justified by that move alone. If it
recovers few, the loop's case rests on the open web, which is a different and
weaker kind of evidence.

## 5. What the trace records

Every move is a node in the record's trace, so an open-search trajectory is
read the same way an identity trace is: what was sent, what came back, why the
next move was chosen. The model's reason for each choice is recorded verbatim.
When the loop establishes identity, the resolution names the node that did,
and the candidate's provenance says whether it came from the archive, a citing
opinion, or a web page and which domain tier that page was in.

Reproducibility is measured, not designed for. Two runs over one citation may
take different paths; whether they reach the same verdict is a property of the
agent worth reporting, and a divergence is a finding rather than a bug.

## 6. What is not decided

- Which web search provider. None is in the repository; the domain tiers are
  the only web-facing code.
- Whether `judge` reuses the identity stage's composite judgement unchanged, or
  a variant that also takes the citing opinion's sentence about the case.
- Whether the open-web tier may establish identity at all, or only refute. The
  domain tiers say a commercial publisher may not support a refutation; the
  same table should say what each tier may support here.
