"""Domain model for the entries on one CourtListener docket.

A docket entry is the court's own record that something was filed or entered
on a day. Read against a citation that states a docket number, a court and an
exact date, the entries answer a question no index can: whether the court
entered a decision that day at all.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CourtListenerDocketEntry:
    """One line of a docket: what was entered, when, and how the clerk described it."""

    entry_id: int | None
    docket_id: str | None
    entry_number: int | None
    date_filed: str | None
    description: str | None
    document_ids: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class CourtListenerDocketEntries:
    """The entries one query returned, and how many the docket holds for it."""

    docket_id: str
    count: int | None
    entries: tuple[CourtListenerDocketEntry, ...]
    next_cursor: str | None = None

    def on(self, date: str) -> tuple[CourtListenerDocketEntry, ...]:
        """Every entry dated exactly as given."""
        return tuple(entry for entry in self.entries if entry.date_filed == date)
