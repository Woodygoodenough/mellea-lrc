"""Deterministic verification of quotations against the page they cite."""

from mellea_lrc.validation.quotation.quotation_check import run_quotation_check
from mellea_lrc.validation.quotation.verbatim import (
    QuotationFinding,
    QuotationOutcome,
    check_quotation,
    check_quotations,
    find_quotations,
)

__all__ = [
    "QuotationFinding",
    "QuotationOutcome",
    "check_quotation",
    "check_quotations",
    "find_quotations",
    "run_quotation_check",
]
