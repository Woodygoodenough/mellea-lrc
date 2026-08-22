"""A local index over the United States Code, for statute citations.

The rest of the validation pipeline checks citations to court decisions and
does not touch citations to statutes at all -- but in the two corpora this
project measures against, statutes are 16% and 29% of citations
respectively, all silently unchecked. :mod:`~mellea_lrc.statutes.us_code`
answers the cheapest version of that question: given a title and section
parsed out of a federal citation, does the United States Code Office of the
Law Revision Counsel's bulk XML say that provision exists, and is it
currently in force (as opposed to repealed, omitted, renumbered, or
transferred elsewhere)? That is a field check in the same spirit as
:mod:`~mellea_lrc.validation.field_checks.court_check`, not a citation
validator on its own -- it says nothing about whether a filing quoted the
section correctly, only whether the section it named is real.
"""

from mellea_lrc.statutes.us_code import (
    DEFAULT_RELEASE_POINT,
    ProvisionStatus,
    UscLookupResult,
    UsCodeIndex,
    title_zip_url,
)

__all__ = [
    "DEFAULT_RELEASE_POINT",
    "ProvisionStatus",
    "UsCodeIndex",
    "UscLookupResult",
    "title_zip_url",
]
