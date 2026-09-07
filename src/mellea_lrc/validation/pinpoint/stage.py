"""The pinpoint stage: for every citation that names a page, what that page carries.

Identity settled which case a filing cites. This stage takes each citation
that also names a page -- the full citation, and every `Id. at 570`,
`556 U.S. at 678` and `Iqbal at 678` that returns to the same authority
through the citation tree -- and puts the filing's words beside the page's.

Four steps per citation, each a node on its trace:

1. **scope**: the citation states a pin cite, its authority resolved to a
   cluster, and the pin is a reporter page rather than a star page or a
   paragraph;
2. **page**: the page is cut from the cluster's opinions along the filing's
   reporter's own pagination, with the tail of the page before and the head
   of the page after;
3. **quotes**: every quotation the filing writes near the citation is
   searched on the page, beside it, and through all of the cluster's
   opinions -- no model, and a quotation that is nowhere in the case is a
   fact;
4. **reading**: one model call reads the filing around the citation and the
   page, and answers with located quotations from each: the words the filing
   attributes to the citation, and the passage on the page on that subject.

The conclusion never says a page supports a proposition. It says what was
found: the quoted words are on the page, or elsewhere, or nowhere; a passage
on the subject is on the page, or beside it, or nothing on the page concerns
it. A pin cite is called false only on a fact of absence, and a citation
that makes no page-level claim of its own -- `see generally`, a `citing`
parenthetical, a bare share of a string cite -- is not tested.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mellea_lrc.core.citations import FullCaseCitation, ShortCaseCitation
from mellea_lrc.core.spans import Span
from mellea_lrc.courtlistener import CourtListenerError
from mellea_lrc.text import fuzzy
from mellea_lrc.validation.identity.stage import IdentifiedDocument
from mellea_lrc.validation.pinpoint.citing import CitingWindow, citing_window
from mellea_lrc.validation.pinpoint.mellea_reading import run_mellea_pinpoint_reading
from mellea_lrc.validation.pinpoint.pages import (
    PaginatedOpinion,
    RetrievedPage,
    citation_index,
    cut_page,
    marker_index_for,
    opinion_order,
    paginate,
    pin_pages,
)
from mellea_lrc.validation.types import (
    CandidateEvaluationNode,
    ExactLocatorLookupNode,
    IdentityOutcome,
    IdentityReason,
    IdentityResolutionNode,
    MelleaPinpointReadingNode,
    PageRetrievalNode,
    PageRetrievalOutcome,
    PinpointOutcome,
    PinpointRelation,
    PinpointResolutionNode,
    PinpointScope,
    PinpointScopeNode,
    QuoteCheckNode,
    QuoteFinding,
    QuoteFindingOutcome,
    ValidationNodeStatus,
)

if TYPE_CHECKING:
    from mellea import MelleaSession

    from mellea_lrc.courtlistener.opinion_models import CourtListenerOpinionCluster
    from mellea_lrc.courtlistener.protocols import CourtListenerServiceClient
    from mellea_lrc.validation.record import CitationRecord

QUOTE_MIN_SCORE = 0.85
"""How close the page's words must be to the filing's quotation to count as the same words."""
SHORT_QUOTE_WORDS = 4
"""Quotations shorter than this are searched exactly (after normalisation) and never fuzzily."""
MIN_DEFECT_QUOTE_WORDS = 6
"""A quotation shorter than this found elsewhere or a turn away decides nothing on its own; one
absent from every opinion of the case decides whatever its length, and the reading turns it into
a misquotation when the page carries the content in other words."""
VOCABULARY_GUARD = 0.5
"""When the model finds nothing on the subject but this share of the attribution's distinctive
words is on the page, the absence is not believed and the outcome is undetermined."""
_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]{4,}")
_STOP = frozenset(
    """about above after again against because before being below between could
    court during either every further having herein hereof itself might other
    plaintiff plaintiffs defendant defendants should their there these those
    through under until where which while whose would shall state states united
    supra infra motion order party parties claim claims filed""".split()
)


@dataclass(frozen=True, slots=True)
class PinpointSummary:
    """What the stage concluded over one document."""

    checked: int
    outcomes: dict[str, int]


async def pinpoint_document(
    identified: IdentifiedDocument,
    *,
    client: CourtListenerServiceClient,
    session: MelleaSession | None = None,
) -> IdentifiedDocument:
    """Check every pin cite in the document against its page. Nodes are appended to the records."""
    text = identified.source.text
    citations = identified.source.citations
    opinions: dict[str, dict[str, PaginatedOpinion]] = {}
    for record in identified.records:
        scope = record.append(_scope(record, identified))
        if scope.outcome is not PinpointScope.IN_SCOPE:
            record.append(_resolution_from_scope(record, scope))
            continue
        root = identified.record(scope.authority_id) if scope.authority_id else record
        reporter, volume, first_page = _reporter_volume_page(record, root)
        page_node = page = None
        # The archive may hold the page under several clusters that agree on
        # the case; the one the identity stage settled on need not be the one
        # whose text is paginated. Each agreeing cluster is tried in turn.
        for cluster_id in _clusters_to_try(root, scope.cluster_id):
            cluster = _cluster_of(root, cluster_id)
            page_node, page = _retrieve(
                record, scope, cluster_id, cluster, reporter, volume, first_page, client, opinions
            )
            if page is not None:
                break
        assert page_node is not None
        record.append(page_node)
        if page is not None:
            # Every agreeing cluster's opinions are read for the quote
            # search: the archive holds a case twice as often as not, and
            # the words may be in the copy the page was not cut from.
            for other_id in _clusters_to_try(root, scope.cluster_id):
                if other_id not in opinions:
                    _read_opinions(record, other_id, _cluster_of(root, other_id), client, opinions)
        if page is None:
            record.append(_resolution_unretrieved(record, scope, page_node))
            continue
        window = citing_window(record.source, citations, text)
        searchable_opinions = {
            oid: op
            for cid in _clusters_to_try(root, scope.cluster_id)
            for oid, op in opinions.get(cid, {}).items()
        }
        quotes = record.append(_quote_check(record, window, page, searchable_opinions, page_node, first_page))
        reading = record.append(
            await run_mellea_pinpoint_reading(
                node_id=f"{record.citation_id}:pinpoint_reading",
                depends_on=(page_node.node_id, quotes.node_id),
                window=window,
                page=page,
                record=_describe_record(root),
                pin_cite=str(record.citation.pin_cite),
                quotes=quotes.quotes,
                session=session,
            )
        )
        opinion_reading = None
        if (
            reading.status is ValidationNodeStatus.SUCCEEDED
            and reading.outcome is PinpointRelation.NONE
            and page.labels
            and quotes.outcome not in (QuoteFindingOutcome.ABSENT, QuoteFindingOutcome.ELSEWHERE)
        ):
            # Nothing on the page: before that is called irrelevance, the
            # whole opinion is read once, and a passage found elsewhere in
            # it names the page the filing should have cited.
            whole = _whole_opinion(page, opinions.get(page_node.cluster_id or "", {}))
            if whole is not None:
                opinion_reading = record.append(
                    await run_mellea_pinpoint_reading(
                        node_id=f"{record.citation_id}:opinion_reading",
                        depends_on=(reading.node_id,),
                        window=window,
                        page=whole,
                        record=_describe_record(root),
                        pin_cite=str(record.citation.pin_cite),
                        quotes=quotes.quotes,
                        session=session,
                        text_scope="opinion",
                    )
                )
        record.append(
            _conclude(
                record,
                scope,
                page_node,
                page,
                quotes,
                reading,
                window,
                searchable_opinions,
                first_page,
                opinion_reading,
            )
        )
    return identified


def _scope(record: CitationRecord, identified: IdentifiedDocument) -> PinpointScopeNode:
    node_id = f"{record.citation_id}:pinpoint_scope"
    pin = getattr(record.citation, "pin_cite", None)
    if not pin:
        return _scope_node(
            node_id, PinpointScope.NO_PIN_CITE, None, None, None, None, "The citation names no page."
        )
    pages = pin_pages(pin)
    resolution = identified.resolution_of(record.citation_id) if record.authority_id else None
    authority_id = record.authority_id
    if resolution is None:
        return _scope_node(
            node_id,
            PinpointScope.NO_AUTHORITY,
            authority_id,
            None,
            pin,
            pages.form,
            "The citation is attributed to no case authority.",
        )
    established = resolution.outcome is IdentityOutcome.CONFIRMED_IDENTITY or (
        resolution.outcome is IdentityOutcome.WRONG_IDENTITY
        and resolution.reason is IdentityReason.FIELD_DISAGREEMENT
    )
    if not established or resolution.cluster_id is None:
        return _scope_node(
            node_id,
            PinpointScope.IDENTITY_NOT_ESTABLISHED,
            authority_id,
            resolution.cluster_id,
            pin,
            pages.form,
            f"The authority's identity is {resolution.outcome.value}"
            + (f" ({resolution.reason.value})" if resolution.reason else "")
            + ", so there is no page to read.",
        )
    if not pages.labels:
        return _scope_node(
            node_id,
            PinpointScope.PIN_FORM,
            authority_id,
            resolution.cluster_id,
            pin,
            pages.form,
            f"The pin cite '{pin}' is a {pages.form}, not a reporter page.",
        )
    return _scope_node(
        node_id,
        PinpointScope.IN_SCOPE,
        authority_id,
        resolution.cluster_id,
        pin,
        pages.form,
        f"Pin cite '{pin}' names page{'s' if len(pages.labels) > 1 else ''} {', '.join(pages.labels)} of the resolved case.",
    )


def _scope_node(node_id, outcome, authority_id, cluster_id, pin, form, message) -> PinpointScopeNode:
    return PinpointScopeNode(
        node_id=node_id,
        status=ValidationNodeStatus.SUCCEEDED,
        outcome=outcome,
        authority_id=authority_id,
        cluster_id=cluster_id,
        pin_cite=pin,
        pin_form=form,
        depends_on=(),
        status_message="Pinpoint scope decided.",
        outcome_message=message,
    )


def _cluster_of(root: CitationRecord, cluster_id: str | None) -> CourtListenerOpinionCluster | None:
    """The lookup record for the resolved cluster, from the root's own trace."""
    for node in root.trace.nodes:
        if isinstance(node, CandidateEvaluationNode) and str(node.cluster_id) == str(cluster_id):
            record = node.record
            if hasattr(record, "citations"):
                return record
    for node in root.trace.nodes:
        if isinstance(node, ExactLocatorLookupNode):
            for cluster in (node.cluster, *node.candidate_clusters):
                if cluster is not None and str(cluster.cluster_id) == str(cluster_id):
                    return cluster
    return None


def _reporter_volume_page(
    record: CitationRecord, root: CitationRecord
) -> tuple[str | None, str | None, str | None]:
    """The reporter, volume and first page the pin cite is written against: the citation's own, else its root's."""
    for citation in (record.citation, root.citation):
        if (
            isinstance(citation, FullCaseCitation | ShortCaseCitation)
            and citation.reporter is not None
            and citation.volume
        ):
            first_page = citation.page if isinstance(citation, FullCaseCitation) else None
            if first_page is None and isinstance(root.citation, FullCaseCitation):
                first_page = root.citation.page
            return citation.reporter.canonical, citation.volume, first_page
    return None, None, None


def _clusters_to_try(root: CitationRecord, resolved: str | None) -> tuple[str, ...]:
    """The resolved cluster first, then every other cluster the identity stage found agreeing."""
    order: list[str] = [resolved] if resolved else []
    for node in root.trace.nodes:
        if isinstance(node, IdentityResolutionNode):
            for cluster_id in node.agreeing_cluster_ids:
                if cluster_id not in order:
                    order.append(cluster_id)
    return tuple(order)


def _read_opinions(
    record: CitationRecord,
    cluster_id: str,
    cluster: CourtListenerOpinionCluster | None,
    client: CourtListenerServiceClient,
    opinions: dict[str, dict[str, PaginatedOpinion]],
) -> tuple[str, ...]:
    """Fetch and paginate every opinion of a cluster once; raises on a failed fetch."""
    paginated = opinions.setdefault(cluster_id, {})
    read: list[str] = []
    if cluster is None:
        return ()
    for opinion_id in cluster.sub_opinion_ids:
        if opinion_id not in paginated:
            opinion = record.opinions.get(opinion_id) or client.get_opinion(opinion_id)
            record.opinions[opinion_id] = opinion
            paginated[opinion_id] = paginate(opinion)
        read.append(opinion_id)
    return tuple(read)


MAX_OPINION_CHARS = 120_000
"""When an opinion carries no page markers, the whole of it stands in for the page, up to this length."""
MIN_PAGE_CHARS = 100
"""A cut page shorter than this is not a page: the markers around it are misplaced, and nothing
can be absent from it."""


def _retrieve(
    record: CitationRecord,
    scope: PinpointScopeNode,
    cluster_id: str,
    cluster: CourtListenerOpinionCluster | None,
    reporter: str | None,
    volume: str | None,
    first_page: str | None,
    client: CourtListenerServiceClient,
    opinions: dict[str, dict[str, PaginatedOpinion]],
) -> tuple[PageRetrievalNode, RetrievedPage | None]:
    node_id = f"{scope.node_id}:page_retrieval"
    labels = pin_pages(scope.pin_cite).labels
    reporter_citation = f"{volume} {reporter} {first_page or ''}".strip() if reporter and volume else None

    def node(outcome, index, read, page, message, error=None):
        return _page_node(
            node_id,
            scope,
            cluster_id,
            outcome,
            reporter_citation,
            index,
            labels,
            read,
            page,
            message,
            error=error,
        )

    if cluster is None:
        return node(
            PageRetrievalOutcome.NO_TEXT, None, (), None, "The cluster's record is not on the trace."
        ), None
    try:
        read = _read_opinions(record, cluster_id, cluster, client, opinions)
    except CourtListenerError as exc:
        return node(
            PageRetrievalOutcome.FAILED, None, (), None, "An opinion could not be fetched.", exc.message
        ), None
    paginated = opinions[cluster_id]
    if not any(op.text.strip() for op in paginated.values()):
        return node(
            PageRetrievalOutcome.NO_TEXT, None, read, None, "The cluster's opinions carry no text."
        ), None
    if not any(op.markers for op in paginated.values()):
        # No reporter pagination at all -- the archive's own scrape of a
        # recent opinion. The page cannot be cut; the opinion can be read.
        lead = min(paginated.values(), key=lambda op: (opinion_order(op.opinion_type), op.opinion_id))
        if len(lead.text) > MAX_OPINION_CHARS:
            return node(
                PageRetrievalOutcome.NO_PAGE,
                None,
                read,
                None,
                f"The opinions carry no page markers and the lead opinion is {len(lead.text):,} characters, too long to stand in for the page.",
            ), None
        page = RetrievedPage(
            opinion_id=lead.opinion_id,
            opinion_type=lead.opinion_type,
            citation_index="",
            labels=(),
            text=lead.text,
            span=Span(0, len(lead.text)),
            before="",
            after="",
        )
        return node(
            PageRetrievalOutcome.WHOLE_OPINION,
            None,
            read,
            page,
            f"The opinions carry no page markers; the whole of opinion {lead.opinion_id} ({lead.opinion_type}) stands in for page {labels[0]}.",
        ), page
    # The marker index is read from the page numbers themselves; the
    # cluster's citation list is consulted only when the numbers do not decide.
    index = marker_index_for(tuple(paginated.values()), first_page, labels) or citation_index(
        cluster.citations, volume=volume, reporter=reporter
    )
    if index is None:
        listed = ", ".join(f"{c.volume} {c.reporter} {c.page}" for c in cluster.citations) or "none"
        return node(
            PageRetrievalOutcome.NO_REPORTER,
            None,
            read,
            None,
            f"No opinion's page markers fit {reporter_citation}; the cluster's citations are {listed}.",
        ), None
    found: list[tuple[int, RetrievedPage]] = []
    for opinion in paginated.values():
        page = cut_page(opinion, index, labels, first_page=first_page)
        if page is not None:
            found.append((opinion_order(opinion.opinion_type), page))
    if not found:
        held = sorted(
            {label for op in paginated.values() for label in op.labels(index) if label.isdigit()}, key=int
        )
        span = f"{held[0]} to {held[-1]}" if held else "none"
        return node(
            PageRetrievalOutcome.NO_PAGE,
            index,
            read,
            None,
            f"No opinion marks page {labels[0]} in {reporter_citation}; the pages marked run {span}.",
        ), None
    # The court's opinion first, unless its copy of the page is empty: a lead
    # opinion that ends on the cited page leaves the marker with nothing
    # after it, and the combined opinion holds the page in full.
    found.sort(key=lambda item: (len(item[1].text.strip()) < MIN_PAGE_CHARS, item[0]))
    page = found[0][1]
    if len(page.text.strip()) < MIN_PAGE_CHARS:
        return node(
            PageRetrievalOutcome.NO_PAGE,
            index,
            read,
            None,
            f"The text between the markers for page {labels[0]} holds {len(page.text.strip())} characters; "
            "the markers are misplaced and the page cannot be read.",
        ), None
    return node(
        PageRetrievalOutcome.FOUND,
        index,
        read,
        page,
        f"Page {', '.join(page.labels)} cut from opinion {page.opinion_id} ({page.opinion_type}) of cluster {cluster_id}.",
    ), page


def _page_node(
    node_id, scope, cluster_id, outcome, reporter_citation, index, labels, read, page, message, *, error=None
) -> PageRetrievalNode:
    if outcome in (PageRetrievalOutcome.FOUND, PageRetrievalOutcome.WHOLE_OPINION):
        status = ValidationNodeStatus.SUCCEEDED
    elif outcome is PageRetrievalOutcome.FAILED:
        status = ValidationNodeStatus.FAILED
    else:
        status = ValidationNodeStatus.SKIPPED
    return PageRetrievalNode(
        node_id=node_id,
        status=status,
        outcome=outcome,
        cluster_id=cluster_id,
        reporter_citation=reporter_citation,
        citation_index=index,
        labels=tuple(page.labels) if page else tuple(labels),
        opinion_id=page.opinion_id if page else None,
        opinion_type=page.opinion_type if page else None,
        page_text=page.text if page else None,
        before=page.before if page else None,
        after=page.after if page else None,
        opinions_read=tuple(read),
        depends_on=(scope.node_id,),
        status_message="Page retrieval completed."
        if outcome in (PageRetrievalOutcome.FOUND, PageRetrievalOutcome.WHOLE_OPINION)
        else "Page retrieval did not produce a page.",
        outcome_message=message,
        error=error,
    )


def _quote_check(
    record: CitationRecord,
    window: CitingWindow,
    page: RetrievedPage,
    paginated: dict[str, PaginatedOpinion],
    page_node: PageRetrievalNode,
    first_page: str | None,
) -> QuoteCheckNode:
    node_id = f"{page_node.node_id}:quote_check"
    findings: list[QuoteFinding] = []
    whole = not page.labels
    for quotation in window.quotations:
        shared = (bool(window.string_members) and not quotation.in_parenthetical) or quotation.alternative
        needle = searchable(quotation.text)
        short = len(needle.split()) < SHORT_QUOTE_WORDS
        score_floor = 1.0 if short else QUOTE_MIN_SCORE
        outcome = QuoteFindingOutcome.ABSENT
        opinion_id = label = None
        page_span = None
        score = None
        if matches := _find(needle, page.text, score_floor):
            outcome = QuoteFindingOutcome.FOUND_UNPAGED if whole else QuoteFindingOutcome.ON_PAGE
            opinion_id, page_span, score = (
                page.opinion_id,
                Span(matches[0].start, matches[0].end),
                matches[0].score,
            )
            label = None if whole else _label_in_page(page, matches[0].start)
        elif any(_find(needle, side, score_floor) for side in (page.before, page.after) if side):
            outcome, opinion_id = QuoteFindingOutcome.ADJACENT, page.opinion_id
            label = _adjacent_label(page, needle, score_floor)
        else:
            for opinion in sorted(
                paginated.values(), key=lambda op: (opinion_order(op.opinion_type), op.opinion_id)
            ):
                if matches := _find(needle, opinion.text, score_floor):
                    opinion_id, score = opinion.opinion_id, matches[0].score
                    index = marker_index_for((opinion,), first_page, page.labels or (first_page or "",))
                    label = opinion.label_at(matches[0].start, index) if index else None
                    if label is None:
                        # The words are in this opinion, and its text carries no
                        # page marker before them: the page cannot be told.
                        outcome = QuoteFindingOutcome.FOUND_UNPAGED
                    elif label in page.labels:
                        outcome = QuoteFindingOutcome.ON_PAGE
                    else:
                        outcome = QuoteFindingOutcome.ELSEWHERE
                    break
        findings.append(
            QuoteFinding(
                text=quotation.text,
                filing_span=quotation.span,
                in_parenthetical=quotation.in_parenthetical,
                shared=shared,
                outcome=outcome,
                opinion_id=opinion_id,
                label=label,
                page_span=page_span,
                score=score,
            )
        )
    # A short quotation decides nothing when it is merely elsewhere or a turn
    # away, but one that is in no opinion of the case at all is a fact
    # however short: `particularly disfavored` was two words and nowhere.
    owned = [
        f
        for f in findings
        if not f.shared
        and (
            len(f.text.split()) >= MIN_DEFECT_QUOTE_WORDS
            or (f.outcome is QuoteFindingOutcome.ABSENT and _distinctive(f.text))
        )
    ]
    order = [
        QuoteFindingOutcome.ABSENT,
        QuoteFindingOutcome.ELSEWHERE,
        QuoteFindingOutcome.FOUND_UNPAGED,
        QuoteFindingOutcome.ADJACENT,
        QuoteFindingOutcome.ON_PAGE,
    ]
    worst = min((f.outcome for f in owned), key=order.index, default=None)
    return QuoteCheckNode(
        node_id=node_id,
        status=ValidationNodeStatus.SUCCEEDED,
        outcome=worst,
        quotes=tuple(findings),
        depends_on=(page_node.node_id,),
        status_message="Quote check completed.",
        outcome_message=(
            "The filing quotes nothing near the citation."
            if not findings
            else "; ".join(
                f"'{f.text[:60]}': {f.outcome.value}"
                + (f" (p. {f.label})" if f.label else "")
                + (" [shared]" if f.shared else "")
                for f in findings
            )
        ),
    )


_BRACKET = re.compile(r"\[([^\]]{1,40})\]")
_ELLIPSIS = re.compile(r"\s*(?:\.\s*\.\s*\.|\N{HORIZONTAL ELLIPSIS})\s*")


def searchable(quotation: str) -> str:
    """The quotation as it would appear on the page: `[n]eglect` is `neglect`, an ellipsis is a break."""
    return " ".join(_BRACKET.sub(r"\1", quotation).split())


def _find(needle: str, haystack: str, floor: float):
    """Find a quotation, or every fragment of it when it is written with ellipses."""
    if not needle or not haystack:
        return ()
    fragments = [f for f in _ELLIPSIS.split(needle) if len(f.split()) >= 2]
    if len(fragments) <= 1:
        return fuzzy.find_all(needle, haystack, min_score=floor)
    found = [fuzzy.find_all(f, haystack, min_score=floor) for f in fragments]
    if all(found):
        # Report the first fragment's place; every fragment is somewhere in the text.
        return found[0]
    return ()


def _distinctive(quotation: str) -> bool:
    """Whether a short quotation is worth an absence: `by law,` is not, `Cash for Kids` and `sole purpose` are.

    Three words, or two of which one is a distinctive word; a trailing comma
    or colon means the marks were misread and the fragment is not the quote.
    """
    text = " ".join(quotation.split())
    if text.endswith((",", ":", ";")):
        return False
    words = text.split()
    if len(words) >= 3:
        return True
    return len(words) == 2 and any(w.lower() not in _STOP for w in _WORD.findall(text))


def _label_in_page(page: RetrievedPage, offset: int) -> str:
    """Which page of a range an offset in the cut text falls on, by the `[*label]` turns."""
    label = page.labels[0]
    for match in re.finditer(r"\[\*(\d+)\]", page.text):
        if match.start() <= offset:
            label = match.group(1)
    return label


def _adjacent_label(page: RetrievedPage, quote: str, floor: float) -> str | None:
    first = int(page.labels[0]) if page.labels[0].isdigit() else None
    last = int(page.labels[-1]) if page.labels[-1].isdigit() else None
    if page.before and _find(quote, page.before, floor):
        return str(first - 1) if first is not None else None
    return str(last + 1) if last is not None else None


def _describe_record(root: CitationRecord) -> str:
    resolution = root.resolution
    if resolution is None:
        return "unknown"
    return f"{resolution.case_name or 'unnamed'} ({resolution.court_id or 'court unknown'}, {resolution.date_filed or 'date unknown'})"


def _vocabulary_on_page(attribution: str | None, page: RetrievedPage) -> float | None:
    if not attribution:
        return None
    words = {w.lower() for w in _WORD.findall(attribution)} - _STOP
    if not words:
        return None
    text = f"{page.before} {page.text} {page.after}"
    found = sum(1 for w in words if fuzzy.find_word(w, text, min_score=0.85))
    return round(found / len(words), 2)


MIN_CONTRADICTION_WORDS = 6
MAX_CLAIM_WORDS = 40
"""A contradiction or a partial attribution is judged on a proposition, not on a paragraph of argument."""
MAX_MISSING_WORDS = 3
"""A partial attribution is a misquote when what the page never states is a term -- `constructive
trust` -- not an elaboration of the filer's own."""
_ARGUMENT = re.compile(
    r"\b(?:plaintiffs?|defendants?|here|this court|this case|the court should|ecf|dkt|docket no|exhibit|"
    r"mr\.|ms\.|mrs\.|counsel for|movant|respondent|petitioner)\b",
    re.IGNORECASE,
)


def _is_proposition(attribution: str | None) -> bool:
    """Whether the filing's words state a proposition rather than argue the case at hand.

    `Constructive trust and unjust enrichment are unavailable where an express
    contract governs` is a proposition; `Because Defendant has not shown a
    concrete basis for freezing discovery, it has not carried its burden` is
    argument, and what argument adds beyond the page is not a misquotation.
    """
    if not attribution:
        return False
    words = attribution.split()
    return len(words) <= MAX_CLAIM_WORDS and not _ARGUMENT.search(attribution)


"""A contradiction needs a whole claim on the filing's side; a fragment such as `the Sixth service
proper.` from a broken window contradicts nothing."""
MIN_ELSEWHERE_WORDS = 8
"""An attribution at least this long that the opinion carries verbatim on another page names that page."""


def _attribution_elsewhere(
    attribution: str | None,
    page: RetrievedPage,
    opinions: dict[str, PaginatedOpinion],
    first_page: str | None,
) -> tuple[str, str] | None:
    """Where the filing's own words for the content sit in the opinion, when it is not the cited page.

    A filing that copies a sentence without quotation marks and pins it to
    the wrong page is caught here: the sentence is searched like a quotation.
    """
    if not attribution or page.labels == ():
        return None
    needle = searchable(attribution)
    if len(needle.split()) < MIN_ELSEWHERE_WORDS:
        return None
    for opinion in sorted(opinions.values(), key=lambda op: (opinion_order(op.opinion_type), op.opinion_id)):
        if not (matches := fuzzy.find_all(needle, opinion.text, min_score=QUOTE_MIN_SCORE)):
            continue
        index = marker_index_for((opinion,), first_page, page.labels)
        label = opinion.label_at(matches[0].start, index) if index else None
        if label is not None and label not in page.labels:
            return opinion.opinion_id, label
        return None
    return None


def _whole_opinion(page: RetrievedPage, opinions: dict[str, PaginatedOpinion]) -> RetrievedPage | None:
    """The opinion the page came from, whole, as a page to read; None when it is too long."""
    opinion = opinions.get(page.opinion_id)
    if opinion is None or not opinion.text.strip() or len(opinion.text) > MAX_OPINION_CHARS:
        return None
    return RetrievedPage(
        opinion_id=opinion.opinion_id,
        opinion_type=opinion.opinion_type,
        citation_index=page.citation_index,
        labels=(),
        text=opinion.text,
        span=Span(0, len(opinion.text)),
        before="",
        after="",
    )


def _missing_absent(missing: str | None, opinions: dict[str, PaginatedOpinion]) -> bool:
    """Whether the words the page does not state are in no opinion of the case either."""
    if not missing:
        return False
    terms = [w for w in _WORD.findall(missing) if w.lower() not in _STOP]
    if not terms:
        return False
    return not any(
        fuzzy.find_word(term, opinion.text, min_score=0.9) for term in terms for opinion in opinions.values()
    )


def _conclude(
    record: CitationRecord,
    scope: PinpointScopeNode,
    page_node: PageRetrievalNode,
    page: RetrievedPage,
    quotes: QuoteCheckNode,
    reading: MelleaPinpointReadingNode,
    window: CitingWindow,
    opinions: dict[str, PaginatedOpinion],
    first_page: str | None,
    opinion_reading: MelleaPinpointReadingNode | None = None,
) -> PinpointResolutionNode:
    node_id = f"{record.citation_id}:pinpoint_resolution"
    depends = (scope.node_id, page_node.node_id, quotes.node_id, reading.node_id) + (
        (opinion_reading.node_id,) if opinion_reading is not None else ()
    )
    whole = not page.labels
    vocabulary = _vocabulary_on_page(reading.attribution, page)
    on_text_quote = next(
        (
            q
            for q in quotes.quotes
            if q.outcome in (QuoteFindingOutcome.ON_PAGE, QuoteFindingOutcome.FOUND_UNPAGED) and q.page_span
        ),
        None,
    )
    read_ok = reading.status is ValidationNodeStatus.SUCCEEDED and reading.outcome is not None
    same_here = (
        read_ok and reading.outcome is PinpointRelation.SAME_CONTENT and reading.passage_span is not None
    )
    decided_by = quotes.node_id
    kinds: tuple[str, ...] = ()
    misquoted = False
    where = "the opinion" if whole else "the cited page"
    # Quoted words are decided by the program. Absence in a shared sentence
    # proves nothing about this member; absence in the citation's own
    # parenthetical, or in a sentence it alone closes, is a fact about it.
    if quotes.outcome is QuoteFindingOutcome.ABSENT and same_here:
        outcome, kinds, misquoted = PinpointOutcome.QUOTE_ALTERED, ("misquote",), True
        message = (
            f"The words in the filing's quotation marks are not the court's; {where} says the same thing in other "
            f"words: {reading.passage!r}."
        )
    elif quotes.outcome is QuoteFindingOutcome.ABSENT:
        absent = next(q for q in quotes.quotes if q.outcome is QuoteFindingOutcome.ABSENT and not q.shared)
        outcome, misquoted = PinpointOutcome.QUOTE_ABSENT, True
        nothing_anywhere = (whole and read_ok and reading.outcome is PinpointRelation.NONE) or (
            opinion_reading is not None
            and opinion_reading.status is ValidationNodeStatus.SUCCEEDED
            and opinion_reading.outcome is PinpointRelation.NONE
        )
        kinds = ("irrelevant", "misquote") if nothing_anywhere else ("misquote",)
        message = f"The quoted words {absent.text!r} are in no opinion of the case" + (
            ", and nothing in the opinion concerns the subject." if nothing_anywhere else "."
        )
    elif quotes.outcome is QuoteFindingOutcome.ELSEWHERE:
        elsewhere_quote = next(
            q for q in quotes.quotes if q.outcome is QuoteFindingOutcome.ELSEWHERE and not q.shared
        )
        outcome, kinds = PinpointOutcome.QUOTE_ELSEWHERE, ("wrong_page",)
        message = (
            f"The quoted words are in the opinion on page {elsewhere_quote.label}, not on the cited page."
        )
    elif on_text_quote is not None:
        outcome = PinpointOutcome.QUOTE_IN_OPINION if whole else PinpointOutcome.QUOTE_ON_PAGE
        message = (
            "The filing's quoted words are in the opinion, whose text carries no page markers."
            if whole
            else "The filing's quoted words are on the cited page."
        )
    elif quotes.outcome is QuoteFindingOutcome.FOUND_UNPAGED:
        outcome = PinpointOutcome.QUOTE_IN_OPINION
        message = "The filing's quoted words are in an opinion whose text carries no page markers; the page cannot be told."
    elif quotes.outcome is QuoteFindingOutcome.ADJACENT:
        outcome = PinpointOutcome.PASSAGE_ADJACENT
        message = "The filing's quoted words are on the neighbouring page, a turn away from the cited one."
    elif not read_ok:
        decided_by = reading.node_id
        outcome = PinpointOutcome.UNDETERMINED
        message = f"The reading did not pass its guards: {reading.error or 'no reading'}."
    elif reading.attribution_scope == "none" or reading.signal in ("see generally", "compare"):
        decided_by = reading.node_id
        outcome = PinpointOutcome.NOT_TESTABLE
        message = "The citation makes no page-level claim of its own here."
    elif (
        reading.outcome is PinpointRelation.CONTRADICTS
        and reading.passage_span is not None
        and len((reading.attribution or "").split()) >= MIN_CONTRADICTION_WORDS
        and _is_proposition(reading.attribution)
    ):
        decided_by = reading.node_id
        outcome, kinds = PinpointOutcome.PASSAGE_CONTRADICTS, ("misquote",)
        message = f"{where.capitalize()} states the opposite of the filing's words ({reading.voice or 'voice unread'}): {reading.passage!r}."
    elif reading.outcome is PinpointRelation.PARTIAL and reading.passage_span is not None:
        decided_by = reading.node_id
        if (
            _missing_absent(reading.missing, opinions)
            and len((reading.missing or "").split()) <= MAX_MISSING_WORDS
            and _is_proposition(reading.attribution)
        ):
            outcome, kinds = PinpointOutcome.PASSAGE_PARTIAL, ("misquote",)
            message = (
                f"{where.capitalize()} states part of what the filing attributes to it, and {reading.missing!r} "
                "appears nowhere in any opinion of the case."
            )
        else:
            outcome = PinpointOutcome.PASSAGE_IN_OPINION if whole else PinpointOutcome.PASSAGE_ON_PAGE
            message = (
                f"{where.capitalize()} carries a passage on the subject; the reading found {reading.missing!r} "
                "unstated there, but the words are elsewhere in the opinion, so nothing is called."
            )
    elif reading.outcome in (PinpointRelation.SAME_CONTENT, PinpointRelation.RELATED_SUBJECT):
        decided_by = reading.node_id
        adjacent = reading.passage_location in ("before", "after")
        if whole:
            outcome = PinpointOutcome.PASSAGE_IN_OPINION
        elif adjacent:
            outcome = PinpointOutcome.PASSAGE_ADJACENT
        else:
            outcome = PinpointOutcome.PASSAGE_ON_PAGE
        message = (
            f"The {'opinion' if whole else ('page beside the cited one' if adjacent else 'page')} carries a passage on the subject"
            f" ({reading.outcome.value}, {reading.voice or 'voice unread'})."
        )
    else:
        decided_by = reading.node_id
        elsewhere = _attribution_elsewhere(reading.attribution, page, opinions, first_page)
        if vocabulary is not None and vocabulary >= VOCABULARY_GUARD:
            outcome = PinpointOutcome.UNDETERMINED
            message = f"The reading found nothing on the subject, but {vocabulary:.0%} of the attribution's distinctive words are on the page."
        elif reading.attribution_scope == "shared":
            outcome = PinpointOutcome.UNDETERMINED
            message = "Nothing on the page concerns the subject, but the sentence is shared by a string cite and may rest on another member."
        elif elsewhere is not None:
            outcome, kinds = PinpointOutcome.PASSAGE_ELSEWHERE, ("wrong_page",)
            message = f"The filing's words for the content are in the opinion on page {elsewhere[1]}, not on the cited page."
        elif whole:
            outcome, kinds = PinpointOutcome.PASSAGE_ABSENT_FROM_OPINION, ("irrelevant",)
            message = f"Nothing in the opinion concerns the subject; it discusses: {reading.page_subjects or 'unread'}"
        elif opinion_reading is None or opinion_reading.status is not ValidationNodeStatus.SUCCEEDED:
            outcome = PinpointOutcome.UNDETERMINED
            message = "Nothing on the cited page concerns the subject, and the whole opinion could not be read to say whether it is elsewhere."
        elif opinion_reading.outcome is PinpointRelation.NONE:
            outcome, kinds = PinpointOutcome.PASSAGE_ABSENT, ("irrelevant",)
            message = (
                f"Nothing on the cited page or anywhere in the opinion concerns the subject; the opinion discusses: "
                f"{opinion_reading.page_subjects or reading.page_subjects or 'unread'}"
            )
        else:
            decided_by = opinion_reading.node_id
            found_label = _label_of_opinion_span(page, opinions, first_page, opinion_reading)
            # Only the same content elsewhere makes a wrong page; a passage on
            # the subject that says something else is shown, not called.
            if (
                found_label is not None
                and found_label not in page.labels
                and opinion_reading.outcome is PinpointRelation.SAME_CONTENT
            ):
                outcome, kinds = PinpointOutcome.PASSAGE_ELSEWHERE, ("wrong_page",)
                message = (
                    f"Nothing on the cited page concerns the subject; the opinion carries a passage on it on page "
                    f"{found_label} ({opinion_reading.outcome.value}): {opinion_reading.passage!r}."
                )
            elif found_label is not None and found_label not in page.labels:
                outcome = PinpointOutcome.UNDETERMINED
                message = (
                    f"Nothing on the cited page concerns the subject; the opinion discusses it on page {found_label} "
                    f"in other terms ({opinion_reading.outcome.value}): {opinion_reading.passage!r}."
                )
            else:
                outcome = PinpointOutcome.UNDETERMINED
                message = "Nothing on the cited page concerns the subject; the opinion carries a passage on it whose page could not be told."
    passage_label = None
    if reading.passage_span is not None and reading.passage_location == "page" and not whole:
        passage_label = _label_in_page(page, reading.passage_span.start)
    elif reading.passage_location in ("before", "after") and reading.passage:
        passage_label = _adjacent_label(page, reading.passage, 0.0)
    passage_span = (
        reading.passage_span
        if reading.passage_span is not None
        else (on_text_quote.page_span if on_text_quote else None)
    )
    passage_text = (
        reading.passage
        if reading.passage_span is not None
        else (
            page.text[on_text_quote.page_span.start : on_text_quote.page_span.end]
            if on_text_quote and on_text_quote.page_span
            else None
        )
    )
    return PinpointResolutionNode(
        node_id=node_id,
        status=ValidationNodeStatus.SUCCEEDED,
        outcome=outcome,
        false_pin_cite=bool(kinds),
        defect_kinds=kinds,
        authority_id=scope.authority_id,
        cluster_id=page_node.cluster_id,
        pin_cite=scope.pin_cite,
        labels=page.labels,
        attribution_span=reading.attribution_span,
        attribution=reading.attribution,
        passage_opinion_id=page.opinion_id if passage_span is not None else None,
        passage_label=passage_label or (on_text_quote.label if on_text_quote else None),
        passage_span=passage_span,
        passage=passage_text,
        voice=reading.voice,
        signal=reading.signal or window.signal,
        vocabulary_on_page=vocabulary,
        decided_by=decided_by,
        depends_on=depends,
        status_message="Pinpoint decided.",
        outcome_message=message,
        misquoted=misquoted,
        text_scope="opinion" if whole else "page",
    )


def _label_of_opinion_span(
    page: RetrievedPage,
    opinions: dict[str, PaginatedOpinion],
    first_page: str | None,
    opinion_reading: MelleaPinpointReadingNode,
) -> str | None:
    """The reporter page a passage located in the whole opinion falls on."""
    if opinion_reading.passage_span is None:
        return None
    opinion = opinions.get(page.opinion_id)
    if opinion is None:
        return None
    index = marker_index_for((opinion,), first_page, page.labels or (first_page or "",))
    if index is None:
        return None
    label = opinion.label_at(opinion_reading.passage_span.start, index)
    if label is None:
        head = opinion.head_labels(index, first_page)
        return head[-1] if head else None
    return label


def _resolution_from_scope(record: CitationRecord, scope: PinpointScopeNode) -> PinpointResolutionNode:
    return _bare_resolution(record, scope, (scope.node_id,), scope.outcome_message or "Out of scope.")


def _resolution_unretrieved(
    record: CitationRecord, scope: PinpointScopeNode, page_node: PageRetrievalNode
) -> PinpointResolutionNode:
    return _bare_resolution(
        record, scope, (scope.node_id, page_node.node_id), page_node.outcome_message or "No page."
    )


def _bare_resolution(
    record: CitationRecord, scope: PinpointScopeNode, depends: tuple[str, ...], message: str
) -> PinpointResolutionNode:
    return PinpointResolutionNode(
        node_id=f"{record.citation_id}:pinpoint_resolution",
        status=ValidationNodeStatus.SKIPPED,
        outcome=PinpointOutcome.NOT_RETRIEVED,
        false_pin_cite=False,
        authority_id=scope.authority_id,
        cluster_id=scope.cluster_id,
        pin_cite=scope.pin_cite,
        labels=(),
        attribution_span=None,
        attribution=None,
        passage_opinion_id=None,
        passage_label=None,
        passage_span=None,
        passage=None,
        voice=None,
        signal=None,
        vocabulary_on_page=None,
        decided_by=depends[-1],
        depends_on=depends,
        status_message="Pinpoint not checked.",
        outcome_message=message,
    )


def summarize(identified: IdentifiedDocument) -> PinpointSummary:
    """Outcome counts over the document's pinpoint resolutions."""
    counts: dict[str, int] = {}
    checked = 0
    for record in identified.records:
        for node in record.trace.nodes:
            if isinstance(node, PinpointResolutionNode):
                checked += node.outcome is not PinpointOutcome.NOT_RETRIEVED
                counts[node.outcome.value] = counts.get(node.outcome.value, 0) + 1
    return PinpointSummary(checked, counts)


__all__ = ["PinpointSummary", "pinpoint_document", "summarize"]
