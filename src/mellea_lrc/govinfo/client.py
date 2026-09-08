"""A client for the Government Publishing Office's United States Courts Opinions.

Three calls, all keyed by what a filing writes: a search by court code and
docket number for the case's package, the package's summary for its caption
and its docket number as the court writes it, and its granules for every
opinion deposited with the day each was issued. The API needs a free key,
read from ``GOVINFO_API_KEY``.

Court codes are courts-db identifiers (`laed`, `ca7`, `ncmd`), and
``casenumber`` matches a docket number roughly as a filing writes it:
`05-4206` finds `2:05-cv-04206`, so the office prefix and the zero padding
need not be reconstructed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

import requests

from mellea_lrc.govinfo.models import GovinfoCase, GovinfoOpinion

if TYPE_CHECKING:
    from collections.abc import Mapping

DEFAULT_BASE_URL = "https://api.govinfo.gov/"
COLLECTION = "USCOURTS"


class GovinfoError(RuntimeError):
    """A request to govinfo that did not answer."""

    def __init__(self, message: str, *, status: int | None = None, retryable: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.retryable = retryable


class GovinfoServiceClient(Protocol):
    """What a docket lookup needs from govinfo."""

    def find_case(self, court_code: str, docket_number: str) -> tuple[GovinfoCase, ...]:
        """Every case the collection holds under this court and docket number, opinions included."""
        ...


@dataclass(frozen=True, slots=True)
class GovinfoConfig:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: float = 60.0

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> GovinfoConfig | None:
        env = os.environ if environ is None else environ
        key = env.get("GOVINFO_API_KEY", "").strip()
        if not key:
            return None
        return cls(api_key=key, base_url=env.get("GOVINFO_BASE_URL", DEFAULT_BASE_URL))


class GovinfoClient:
    """The client. ``session`` is injectable so a test can stand in for the service."""

    def __init__(self, config: GovinfoConfig, session: requests.Session | None = None) -> None:
        self.config = config
        self.session = session or requests.Session()
        self.requests = 0

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> GovinfoClient | None:
        config = GovinfoConfig.from_env(environ)
        return cls(config) if config else None

    def find_case(self, court_code: str, docket_number: str) -> tuple[GovinfoCase, ...]:
        """Every case under this court and docket number, each with its deposited opinions."""
        query = f"collection:{COLLECTION} AND casenumber:({_case_number_query(docket_number)}) AND courtcode:({court_code})"
        payload = self._post(
            "search", {"query": query, "pageSize": 100, "offsetMark": "*", "resultLevel": "default"}
        )
        package_ids: list[str] = []
        for hit in payload.get("results", []) or []:
            package_id = hit.get("packageId")
            if isinstance(package_id, str) and package_id not in package_ids:
                package_ids.append(package_id)
        return tuple(self.case(package_id) for package_id in package_ids)

    def case(self, package_id: str) -> GovinfoCase:
        """One package with every opinion deposited in it."""
        summary = self._get(f"packages/{package_id}/summary", {})
        granules = self._get(f"packages/{package_id}/granules", {"pageSize": 100, "offsetMark": "*"})
        opinions = tuple(
            GovinfoOpinion(
                package_id=package_id,
                granule_id=str(item.get("granuleId")),
                title=item.get("title"),
                date_issued=item.get("dateIssued"),
            )
            for item in granules.get("granules", []) or []
            if item.get("granuleId")
        )
        return GovinfoCase(
            package_id=package_id,
            court_code=summary.get("courtCode"),
            case_number=summary.get("caseNumber"),
            title=summary.get("title"),
            case_type=summary.get("caseType"),
            date_issued=summary.get("dateIssued"),
            opinions=tuple(sorted(opinions, key=lambda item: item.date_issued or "")),
        )

    def opinion(self, package_id: str, granule_id: str) -> GovinfoOpinion:
        """One deposited opinion's summary: the clerk's docket text and where its PDF is."""
        summary = self._get(f"packages/{package_id}/granules/{granule_id}/summary", {})
        return GovinfoOpinion(
            package_id=package_id,
            granule_id=granule_id,
            title=summary.get("title"),
            date_issued=summary.get("dateIssued"),
            docket_text=summary.get("docketText"),
            pdf_link=(summary.get("download") or {}).get("pdfLink"),
        )

    def _post(self, path: str, body: dict[str, object]) -> dict[str, object]:
        return self._send("POST", path, json=body)

    def _get(self, path: str, params: dict[str, object]) -> dict[str, object]:
        return self._send("GET", path, params=params)

    def _send(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, object] | None = None,
        json: dict[str, object] | None = None,
    ) -> dict[str, object]:
        url = self.config.base_url.rstrip("/") + "/" + path
        query = {"api_key": self.config.api_key, **(params or {})}
        self.requests += 1
        try:
            response = self.session.request(
                method, url, params=query, json=json, timeout=self.config.timeout_seconds
            )
        except requests.Timeout as exc:
            raise GovinfoError("govinfo request timed out", retryable=True) from exc
        except requests.RequestException as exc:
            raise GovinfoError(f"govinfo request failed: {exc}", retryable=True) from exc
        if response.status_code == 429:
            raise GovinfoError("govinfo rate limit reached", status=429, retryable=True)
        if response.status_code >= 400:
            raise GovinfoError(f"govinfo answered {response.status_code}", status=response.status_code)
        try:
            payload = response.json()
        except ValueError as exc:
            raise GovinfoError("govinfo returned no JSON") from exc
        if not isinstance(payload, dict):
            raise GovinfoError("govinfo returned an unexpected shape")
        return payload


def _case_number_query(docket_number: str) -> str:
    """The year and sequence a filing wrote, which is what `casenumber:` matches on."""
    from mellea_lrc.validation.docket_lookup.numbers import docket_core

    core = docket_core(docket_number)
    return f"{core[0]}-{core[1]}" if core else docket_number.strip()


__all__ = ["GovinfoClient", "GovinfoConfig", "GovinfoError", "GovinfoServiceClient"]
