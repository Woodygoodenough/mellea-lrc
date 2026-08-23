"""Offline indexes over published case reports.

The validation pipeline asks CourtListener whether a case sits at a volume and
page, and when the answer is no it stops -- correctly, because the free record
is incomplete and an absence is not evidence of fabrication. That leaves a
bucket of citations with no verdict.

:mod:`~mellea_lrc.caselaw.cap_index` reads the Caselaw Access Project's static
files, which publish Harvard's digitisation of the printed reporters with each
case's **page range**. Knowing the range rather than only the first page turns
some of those silences into positive evidence: a cited page that falls inside a
case rather than starting one names a real case at the wrong page, and the
index can say which case. It is offline and free of any request allowance, in
the same spirit as :mod:`~mellea_lrc.statutes.us_code`.
"""

from mellea_lrc.caselaw.cap_index import (
    BASE_URL,
    CapCase,
    CapIndex,
    PageOutcome,
    PageVerdict,
    reporter_slug,
    volume_metadata_url,
)
from mellea_lrc.caselaw.case_name_check import (
    CaseNameFinding,
    NameVerdict,
    check_case_name,
    compare_case_name,
)
from mellea_lrc.caselaw.first_page_check import (
    FirstPageFinding,
    LaterReferenceEvidence,
    check_first_pages,
)

__all__ = [
    "BASE_URL",
    "CapCase",
    "CapIndex",
    "CaseNameFinding",
    "FirstPageFinding",
    "LaterReferenceEvidence",
    "NameVerdict",
    "PageOutcome",
    "PageVerdict",
    "check_case_name",
    "check_first_pages",
    "compare_case_name",
    "reporter_slug",
    "volume_metadata_url",
]
